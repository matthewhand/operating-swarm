"""Operator-facing seat diagnostic: *broken, and here is the exact thing to do*.

A sweep of a real host found 53 of 93 seats broken, and almost none of them
were code bugs — they were credits to top up, a key to add, a binary to
install, a remote pointed at the wrong port. Reading a sweep log to learn that
is not a workflow; this module is.

It is a **read-only** report. Nothing is written: no config, no library, no
secrets store, no database row. Every verdict comes from a probe that already
exists in the codebase, and every bucket from the *shape of that probe's
failure*, never from a per-seat table:

* ``api``    -> :func:`swarm.core.llm_profile_probe.probe_llm_profile`
  (``action="test"`` is a real one-token chat call, so a pass is a real turn).
* ``cli``    -> :func:`swarm.core.seat_health.probe_seat` (binary on PATH +
  ``--version``). Liveness only: a reachable binary proves nothing about the
  credentials or the model behind it.
* ``remote`` -> :func:`swarm.core.remotes.check_health` (TCP + HTTP health).

Why liveness is not enough, stated plainly: ``grok`` answers ``--version`` and
fails every real turn with ``402 Payment Required``. So a passing probe is
reported as ``unverified``, never ``ok``. ``ok`` is reserved for seats where
*this run* proved a turn — which, without ``--deep``, is only the API seats.

Buckets and the evidence that selects them
-------------------------------------------

=========================  ====================================================
``quota``                 HTTP 402, or a body saying payment / credit / quota /
                          billing / usage exhausted / insufficient balance.
``auth``                  HTTP 401/403, ``llm_profile_probe``'s ``auth``
                          ``error_class``, a remote ``AUTH`` health state, or
                          ``llm_diagnostics.llm_credential_hint`` naming a
                          ``${VAR}`` the server process does not have.
``model_invalid``         ``error_class`` in ``{bad_model, model_missing}``, or a
                          400/404/422 whose body names the model — and the
                          remediation lists ids read back from the gateway's
                          real ``action="list_models"`` response.
``not_installed``         ``shutil.which(cmd[0])`` is None for a catalogued CLI.
``not_executable``        ``which`` resolved it but the OS would not run it (no
                          execute bit, wrong architecture). Different fix from
                          ``not_installed`` — do not reinstall a binary that is
                          already on disk.
``not_configured``        No base_url / model / remote entry, a catalog remote
                          that was never added, an unresolved ``${VAR}``, or a
                          composition seat with no delegate CLI.
``service_down``          TCP connect **refused** on the seat's own origin.
``unreachable``           DNS failure or a connect **timeout** (not a refusal).
``timeout``               The connect neither answered nor was refused. Genuinely
                          ambiguous from the client side (a filtered SYN looks
                          like a wedged service), so the remediation names both
                          causes rather than picking one.
``misconfigured``         The binary resolves on PATH but the seat is absent
                          from ``cli_agents`` — the binary is fine, the wiring
                          is not.
``timeout_risk``          A measured round trip consumed ``>= 70%`` of the
                          seat's own configured ``timeout``.
``probe_error``           The probe failed in a shape nothing here can name.
                          Emitted instead of a guess.
=========================  ====================================================

``probe_error`` exists so the last row is never a coin flip. A bucket that is a
guess is worse than no bucket.

Politeness
----------

Bounded by construction: ``--limit`` seats (default 200), short timeouts, at
most eight probes in flight, and — unless ``--deep`` is passed — no provider
call beyond the single ``action="test"`` probe per API seat. Broken API seats
get one extra **GET** (never a chat call) so the report can read the real
status code; the valid model ids come from ``action="list_models"``, which is
also a GET.

Secrets
-------

No secret reaches the report. Values are masked before they are formatted, and
credentials are only ever referenced by **env var name**. A literal secret in
``swarm_config.json`` is used to probe (process-local, restored immediately,
never formatted) because otherwise the probe would report a false 401.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import re
import shutil
import socket
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from swarm.core.seat_health import VALID_KINDS
from swarm.utils.redact import SENSITIVE_PATTERNS, redact_uri_credentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

VERDICT_OK = "ok"
VERDICT_BROKEN = "broken"
VERDICT_UNVERIFIED = "unverified"

#: The three seat kinds, re-exported from :mod:`swarm.core.seat_health` so a
#: caller never has to import two modules to ask "which kinds are there?".

BUCKET_QUOTA = "quota"
BUCKET_AUTH = "auth"
BUCKET_MODEL_INVALID = "model_invalid"
BUCKET_NOT_INSTALLED = "not_installed"
BUCKET_NOT_EXECUTABLE = "not_executable"
BUCKET_NOT_CONFIGURED = "not_configured"
BUCKET_SERVICE_DOWN = "service_down"
BUCKET_UNREACHABLE = "unreachable"
BUCKET_TIMEOUT = "timeout"
BUCKET_MISCONFIGURED = "misconfigured"
BUCKET_TIMEOUT_RISK = "timeout_risk"
BUCKET_PROBE_ERROR = "probe_error"

#: A passing probe only becomes ``ok`` when a real turn was proved.
PROVES_TURN = "turn"
PROVES_LIVENESS = "liveness"
PROVES_NOTHING = "nothing"

# ---------------------------------------------------------------------------
# bounds
# ---------------------------------------------------------------------------

#: Hard cap on seats probed in one run. One client must not become a load test.
MAX_SEATS = 200
#: Probes in flight. Eight is polite on a laptop and on someone else's LAN box.
MAX_WORKERS = 8
#: Short. A diagnostic that hangs is a diagnostic nobody runs.
API_TIMEOUT_S = 6.0
REMOTE_TIMEOUT_S = 3.0
TCP_TIMEOUT_S = 2.0
#: A round trip that eats this share of the seat's own timeout is a latent
#: timeout risk — the next slow turn gets killed mid-answer.
TIMEOUT_RISK_RATIO = 0.70
#: How many valid model ids a ``model_invalid`` remediation names.
MAX_MODEL_SUGGESTIONS = 6

#: How an answer is allowed to look before the bucket is quota rather than a
#: generic 4xx. Matched against the status code and the redacted body only.
_QUOTA_MARKERS = (
    "payment required",
    "insufficient_quota",
    "insufficient credit",
    "insufficient funds",
    "credit balance",
    "usage exhausted",
    "quota exceeded",
    "exceeded your current quota",
    "billing",
    "spending limit",
    "exhausted",
    "out of credit",
    "add credits",
    "top up",
)
_AUTH_MARKERS = (
    "invalid x-api-key",
    "invalid_api_key",
    "incorrect api key",
    "unauthorized",
    "authentication",
    "invalid token",
    "expired token",
    "no api key",
    "api key",
    "access key",
    "session token",
)
_MODEL_MARKERS = (
    "invalid model",
    "model not found",
    "unknown model",
    "does not exist",
    "model_not_found",
    "not served",
    "no such model",
)
_MISSING_MARKERS = (
    "is not installed",
    "not on path",
    "command not found",
    "no such file or directory",
)
#: The file is there and ``which`` found it, but the OS would not run it: wrong
#: architecture, no execute bit, a dangling interpreter. A different fix from
#: "not installed", and conflating the two sends the operator to reinstall a
#: binary that is already present.
_UNEXECUTABLE_MARKERS = (
    "could not be executed",
    "permission denied",
    "exec format error",
    "text file busy",
)
#: The connection worked; the answer did not arrive. Checked last so a quota or
#: auth body that merely mentions a timeout still wins on its own evidence.
_TIMEOUT_MARKERS = (
    "did not answer",
    "timed out",
    "timeout",
    "read timed out",
)
_UNCONFIGURED_MARKERS = (
    "not added as a remote",
    "no instance url",
    "not configured — no instance url",
    "no cli agents are configured",
    "no planner cli is configured",
    "no worker clis are configured",
    "no provider base_url or model configured",
    "base_url is empty",
    "is not configured",
)

#: Install commands for the CLIs whose upstream package is known. This is a
#: *remediation hint* table, never a bucket table: ``not_installed`` is still
#: decided by ``shutil.which`` returning nothing.
INSTALL_COMMANDS: dict[str, str] = {
    "ocr": "npm i -g @alibaba-group/open-code-review",
}

#: Config blocks that are composition seats: a seat with no provider of its own
#: that runs other seats. ``agent_team`` members are remotes, the rest are CLIs.
COMPOSITION_BLOCKS = (
    "cli_agent",
    "cli_ensemble",
    "cli_fusion",
    "cli_map",
    "cli_orchestrator",
    "cli_pipeline",
    "cli_planner",
    "cli_recurse",
    "cli_roundtable",
    "agent_team",
)

#: Strong markers only. A weak signature is worse than "something answered".
_ENDPOINT_MARKERS: tuple[tuple[str, str], ...] = (
    ("__next_data__", "a Next.js dashboard"),
    ("/_next/static/", "a Next.js dashboard"),
    ("openshell-gateway", "openshell-gateway"),
    ("llama.cpp", "llama.cpp"),
    ("llamafile", "llama.cpp"),
    ("<title>open webui", "Open WebUI"),
    ("n8n", "n8n"),
)

# ---------------------------------------------------------------------------
# redaction
# ---------------------------------------------------------------------------


class _Redactor:
    """Masks secrets in anything the report prints. Never raises."""

    def __init__(self, extra: Iterable[str] = ()) -> None:
        self._patterns = [re.compile(p) for p in SENSITIVE_PATTERNS]
        self._patterns.append(re.compile(r"sk-[A-Za-z0-9_\-]{4,}"))
        self._patterns.append(re.compile(r"(?i)\bbearer\s+\S+"))
        self._literals = {v for v in extra if isinstance(v, str) and len(v) >= 6}
        # Every env value that looks like a credential is a literal to mask.
        for name, value in os.environ.items():
            if not isinstance(value, str) or len(value) < 8:
                continue
            if any(needle in name.upper() for needle in ("KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE")):
                self._literals.add(value)

    def add(self, *values: str | None) -> None:
        for value in values:
            if isinstance(value, str) and len(value) >= 6:
                self._literals.add(value)

    def text(self, value: Any) -> str:
        out = "" if value is None else str(value)
        for literal in sorted(self._literals, key=len, reverse=True):
            if literal and literal in out:
                out = out.replace(literal, "[REDACTED]")
        for pattern in self._patterns:
            out = pattern.sub("[REDACTED]", out)
        return redact_uri_credentials(out).strip()

    def scrub(self, value: Any) -> Any:
        """Recursively redact a JSON-shaped value."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.scrub(v) for v in value)
        return value


@contextlib.contextmanager
def _env_override(pairs: dict[str, str]):
    """Temporarily bind env values a config block carries inline.

    ``swarm_config.json`` may hold ``cli_agents.<cli>.env.OPENAI_API_KEY``. The
    probe helpers read credentials from the environment by *name*, so the value
    has to be visible for the duration of the call — otherwise the probe would
    report a 401 that the real seat does not have. Process-local, restored in
    ``finally``, and never formatted into the report.
    """
    saved: dict[str, str | None] = {}
    try:
        for key, value in (pairs or {}).items():
            if not key or not isinstance(value, str) or not value:
                continue
            saved[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


# ---------------------------------------------------------------------------
# model shape
# ---------------------------------------------------------------------------


@dataclass
class SeatSpec:
    """One seat in the roster, plus everything needed to probe it."""

    kind: str
    seat_id: str
    label: str = ""
    origin: str = ""
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    missing_env: str = ""
    cli: str = ""
    timeout_s: float | None = None
    delegates_to: list[str] = field(default_factory=list)
    delegate_kinds: dict[str, str] = field(default_factory=dict)
    model_pin: str = ""
    inline_env: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "seat_id": self.seat_id,
            "label": self.label or self.seat_id,
            "origin": self.origin,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "cli": self.cli,
            "delegates_to": list(self.delegates_to),
            "note": self.note,
        }


@dataclass
class SeatFinding:
    """One seat's verdict, the bucket that explains it, and the fix."""

    kind: str
    seat_id: str
    label: str = ""
    origin: str = ""
    verdict: str = VERDICT_UNVERIFIED
    bucket: str = ""
    detail: str = ""
    remediation: str = ""
    proves: str = PROVES_NOTHING
    latency_ms: int = 0
    delegates_to: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, redactor: _Redactor | None = None) -> dict[str, Any]:
        scrub = redactor or _Redactor()
        return {
            "kind": self.kind,
            "seat_id": self.seat_id,
            "label": self.label or self.seat_id,
            "origin": self.origin,
            "verdict": self.verdict,
            "bucket": self.bucket,
            "detail": scrub.text(self.detail),
            "remediation": scrub.text(self.remediation),
            "proves": self.proves,
            "turn_proved": self.proves == PROVES_TURN,
            "latency_ms": int(self.latency_ms or 0),
            "delegates_to": list(self.delegates_to),
            "evidence": scrub.scrub(self.evidence or {}),
        }


# ---------------------------------------------------------------------------
# roster
# ---------------------------------------------------------------------------


def _swarm_config(explicit: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(explicit, dict):
        return explicit
    from swarm.core.llm_task_routing import load_swarm_config

    try:
        loaded = load_swarm_config()
    except Exception:  # noqa: BLE001 — a missing config is a finding, not a crash
        logger.debug("seat_doctor: swarm config unreadable", exc_info=True)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _custom_library_items() -> list[dict[str, Any]]:
    """``blueprint_library.json`` custom rows, or ``[]``."""
    try:
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        library = get_user_blueprint_library()
    except Exception:  # noqa: BLE001
        logger.debug("seat_doctor: blueprint library unreadable", exc_info=True)
        return []
    if not isinstance(library, dict):
        return []
    items = library.get("custom")
    return [row for row in items if isinstance(row, dict)] if isinstance(items, list) else []


def _library_installed() -> list[str]:
    try:
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        library = get_user_blueprint_library()
    except Exception:  # noqa: BLE001
        return []
    installed = (library or {}).get("installed") if isinstance(library, dict) else None
    return [str(name) for name in installed or [] if str(name).strip()]


def _expand_template(value: Any) -> str:
    """``${VAR}`` -> the env value, or ``""`` when unresolved."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not (text.startswith("${") and text.endswith("}")):
        return text
    return os.environ.get(text[2:-1].strip(), "").strip()


def _unresolved_env_name(value: Any) -> str:
    """The var name inside a ``${VAR}`` that substitution found nothing for."""
    text = str(value or "").strip()
    if text.startswith("${") and text.endswith("}") and len(text) > 3:
        inner = text[2:-1].strip()
        if inner and all(ch.isalnum() or ch == "_" for ch in inner):
            return inner
    return ""


def _api_key_env_name(profile: dict[str, Any]) -> str:
    """Env var *name* for a profile's key. Never the value."""
    from swarm.core.config_ownership import (
        is_placeholder,
        looks_like_env_name,
        placeholder_env_name,
    )

    for key in ("api_key", "apikey", "key"):
        raw = profile.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        if is_placeholder(raw):
            return placeholder_env_name(raw)
        if looks_like_env_name(raw):
            return raw.strip()
    provider = str(profile.get("provider") or "").strip()
    return f"{provider.upper()}_API_KEY" if provider else ""


def _cli_model_pin(entry: dict[str, Any]) -> tuple[str, str, str, dict[str, str]]:
    """``(model_pin, base_url, api_key_env, inline_env)`` from a CLI config entry.

    A CLI points at its provider through its own argv, so the pin is read off
    ``cmd`` rather than invented: ``--model x``, ``--openai-base-url URL``,
    ``--base-url URL``, ``--api-base URL``.
    """
    cmd = entry.get("cmd") if isinstance(entry, dict) else None
    argv = [str(part) for part in cmd] if isinstance(cmd, (list, tuple)) else []
    inline = {
        str(k): str(v)
        for k, v in ((entry or {}).get("env") or {}).items()
        if isinstance(v, str) and v
    }
    model_pin = ""
    base_url = ""
    for index, token in enumerate(argv):
        if "=" in token and token.split("=", 1)[0].lstrip("-") in {"model", "openai-base-url", "base-url", "api-base", "openai-api-base"}:
            flag, _, value = token.partition("=")
            target = flag.lstrip("-")
        elif token.startswith("--") and index + 1 < len(argv):
            target = token[2:]
            value = argv[index + 1]
        else:
            continue
        if target in {"model", "model-id"}:
            model_pin = value.strip()
        elif target in {"openai-base-url", "base-url", "api-base", "openai-api-base"}:
            base_url = value.strip()
    base_url = base_url or _expand_template(inline.get("OPENAI_BASE_URL", ""))
    api_key_env = "OPENAI_API_KEY" if ("OPENAI_API_KEY" in inline or "OPENAI_BASE_URL" in inline) else ""
    return model_pin, base_url, api_key_env, inline


def _walk_refs(value: Any, cli_names: set[str], remote_ids: set[str], out: list[tuple[str, str]]) -> None:
    """Collect ``(role, seat_id)`` for every configured CLI / remote referenced."""
    if isinstance(value, dict):
        for nested in value.values():
            _walk_refs(nested, cli_names, remote_ids, out)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _walk_refs(nested, cli_names, remote_ids, out)
        return
    if not isinstance(value, str):
        return
    text = value.strip()
    if text in cli_names or text in remote_ids:
        out.append(("", text))


def _role_refs(block: dict[str, Any], cli_names: set[str]) -> list[tuple[str, str]]:
    """``(role, cli)`` pairs for role-named keys (planner / router / judge)."""
    out: list[tuple[str, str]] = []
    if not isinstance(block, dict):
        return out
    for key, value in block.items():
        role = str(key or "").strip().lower()
        if role not in {"planner", "router", "judge", "reducer", "default_cli", "panel", "workers", "worker"}:
            continue
        if isinstance(value, str) and value.strip() in cli_names:
            out.append((role, value.strip()))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str) and item.strip() in cli_names:
                    out.append((role, item.strip()))
    return out


def _origin_key(url: str) -> str:
    """``host:port`` of a base_url, so two spellings of one endpoint compare equal."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{host}:{port}"


def _link_cli_to_profile(
    spec: SeatSpec, profiles: dict[str, SeatSpec]
) -> str:
    """The LLM profile a CLI provably shares, or ``""``.

    A CLI resolves its own provider, so a model pin alone proves nothing — the
    namespace prefix selects a host OS cannot see. A link is only made when the
    CLI states the *same endpoint* (argv ``--openai-base-url`` / env
    ``OPENAI_BASE_URL``) **and** pins a model a profile with that endpoint
    serves. Anything looser would be a guess about where the seat actually
    talks to, and a guessed bucket is worse than no bucket.
    """
    origin = _origin_key(spec.base_url)
    if not origin or not spec.model_pin:
        return ""
    wanted = spec.model_pin.split("/", 1)[-1].strip()
    for name, profile in profiles.items():
        if _origin_key(profile.base_url) != origin:
            continue
        if wanted and wanted in {name, str(profile.model or "").strip()}:
            return name
    return ""


def enumerate_seats(config: dict[str, Any] | None = None) -> list[SeatSpec]:
    """Every seat the operator can send to, across api / cli / remote.

    Built from the stores the rail itself reads — designed agents, the custom
    library, ``cli_agents``, the CLI catalog, remote config, LLM profiles — so
    the roster cannot drift from what the UI shows. Composition seats carry
    ``delegates_to`` and inherit their delegate's bucket.
    """
    cfg = _swarm_config(config)
    from swarm.core import cli_catalog, remotes
    from swarm.core.agent_kind import classify_agent_kind
    from swarm.core.llm_task_routing import (
        iter_llm_profiles,
        model_id_for_profile,
        resolve_chat_model,
    )
    from swarm.core.router_designs import load_designs

    seats: dict[tuple[str, str], SeatSpec] = {}

    def add(spec: SeatSpec) -> None:
        key = (spec.kind, spec.seat_id)
        existing = seats.get(key)
        if existing is None:
            seats[key] = spec
            return
        # First writer wins the probe inputs; union the delegate edges.
        for delegate in spec.delegates_to:
            if delegate not in existing.delegates_to:
                existing.delegates_to.append(delegate)
        existing.delegate_kinds.update(spec.delegate_kinds)

    configured_clis = set(cli_catalog.configured_cli_names(cfg))
    discovered_clis = set(cli_catalog.discover_host_clis())
    cli_agents_block = cfg.get("cli_agents") if isinstance(cfg.get("cli_agents"), dict) else {}
    remote_ids = set(remotes.configured_remote_ids(cfg))

    # -- designed agents (GET /v1/agents/ roster) ---------------------------
    for row in load_designs():
        agent_id = str(row.get("agent_id") or "").strip()
        if not agent_id:
            continue
        explicit = str(row.get("kind") or row.get("agent_type") or "").strip() or None
        kind = classify_agent_kind(agent_id, explicit=explicit)
        if kind == "remote":
            target = str(row.get("remote") or "").strip() or agent_id.removeprefix("remote:")
            add(
                SeatSpec(
                    kind="remote",
                    seat_id=agent_id,
                    label=str(row.get("name") or agent_id),
                    origin="designed_agent",
                    delegates_to=[target] if target in remote_ids else [],
                    delegate_kinds={target: "remote"} if target in remote_ids else {},
                )
            )
            continue
        if kind == "cli":
            cli = str(row.get("cli") or "").strip() or (cli_catalog.cli_from_rail_id(agent_id) or "")
            add(
                SeatSpec(
                    kind="cli",
                    seat_id=agent_id,
                    label=str(row.get("name") or agent_id),
                    origin="designed_agent",
                    cli=cli,
                    delegates_to=[cli] if cli else [],
                    delegate_kinds={cli: "cli"} if cli else {},
                    note="" if cli else "design declares kind=cli but names no catalog CLI",
                )
            )
            continue
        add(
            SeatSpec(
                kind="api",
                seat_id=agent_id,
                label=str(row.get("name") or agent_id),
                origin="designed_agent",
                model=str(row.get("model") or "").strip(),
            )
        )

    # -- custom library rows -------------------------------------------------
    for row in _custom_library_items():
        seat_id = str(row.get("id") or "").strip()
        if not seat_id:
            continue
        kind = str(row.get("kind") or "").strip().lower()
        cli = str(row.get("cli") or "").strip()
        if kind == "cli" or (cli and kind != "api"):
            add(
                SeatSpec(
                    kind="cli",
                    seat_id=seat_id,
                    label=str(row.get("name") or seat_id),
                    origin="custom_library",
                    cli=cli,
                    delegates_to=[cli] if cli else [],
                    delegate_kinds={cli: "cli"} if cli else {},
                )
            )
        elif kind in {"api", "personality", ""} or row.get("agent_type") == "api":
            add(
                SeatSpec(
                    kind="api",
                    seat_id=seat_id,
                    label=str(row.get("name") or seat_id),
                    origin="custom_library",
                )
            )

    # -- rail rows -----------------------------------------------------------
    default_cli = ""
    try:
        payload = cli_catalog.cli_agents_catalog_payload(cfg)
        default_cli = str(payload.get("default_cli") or "").strip()
    except Exception:  # noqa: BLE001
        logger.debug("seat_doctor: cli catalog payload failed", exc_info=True)
    for row in cli_catalog.rail_cli_rows(cfg):
        seat_id = str(row.get("id") or "").strip()
        if row.get("kind") == "cli":
            target = str(row.get("cli") or "").strip() or default_cli
            add(
                SeatSpec(
                    kind="cli",
                    seat_id=seat_id or "cli_agent",
                    origin="rail_row",
                    cli=target,
                    delegates_to=[target] if target else [],
                    delegate_kinds={target: "cli"} if target else {},
                )
            )
        else:
            add(SeatSpec(kind="api", seat_id=seat_id or "api_agent", origin="rail_row"))

    # -- configured and discovered CLIs --------------------------------------
    for name in sorted(configured_clis):
        entry = cli_agents_block.get(name) if isinstance(cli_agents_block.get(name), dict) else {}
        pin, base_url, key_env, inline = _cli_model_pin(entry)
        add(
            SeatSpec(
                kind="cli",
                seat_id=f"{name}_agent",
                origin="cli_agents",
                cli=name,
                timeout_s=(entry or {}).get("timeout"),
                model_pin=pin,
                base_url=base_url,
                api_key_env=key_env,
                inline_env=inline,
                note="" if name in discovered_clis else "configured but its binary is not on PATH",
            )
        )
    for name in sorted(discovered_clis - configured_clis):
        add(
            SeatSpec(
                kind="cli",
                seat_id=f"{name}_agent",
                origin="discovered_on_path",
                cli=name,
                note="binary resolves on PATH but swarm_config.json has no cli_agents entry",
            )
        )

    # -- LLM profiles (the api provider/model endpoints) ---------------------
    for name, profile in iter_llm_profiles(cfg):
        base_url = _expand_template(profile.get("base_url"))
        missing = "" if base_url else _unresolved_env_name(profile.get("base_url"))
        add(
            SeatSpec(
                kind="api",
                seat_id=name,
                origin="llm_profile",
                base_url=base_url,
                model=model_id_for_profile(name, cfg),
                api_key_env=_api_key_env_name(profile),
                missing_env=missing,
                note=(
                    f"base_url is ${{{missing}}} and that variable is not set"
                    if missing
                    else ("" if base_url else "no base_url configured for this profile")
                ),
            )
        )

    # -- the chat profile, so api seats with no model of their own resolve ---
    try:
        chat_profile = resolve_chat_model(cfg).profile
    except Exception:  # noqa: BLE001
        chat_profile = ""
    if chat_profile:
        for spec in seats.values():
            if spec.kind == "api" and not spec.base_url and not spec.model:
                spec.delegates_to.append(chat_profile)
                spec.delegate_kinds[chat_profile] = "api"
                spec.note = f"no provider of its own; runs the {chat_profile!r} LLM profile"

    # -- composition seats ----------------------------------------------------
    composition_ids: set[str] = set()
    for key in COMPOSITION_BLOCKS:
        block = cfg.get(key)
        if not isinstance(block, dict) or not block:
            continue
        composition_ids.add(key)
        refs: list[tuple[str, str]] = []
        _walk_refs(block, configured_clis, remote_ids, refs)
        roles = _role_refs(block, configured_clis)
        delegates = sorted({name for _role, name in refs})
        delegated_roles = {name for _role, name in roles}
        unresolved = sorted({role for role, name in roles if name not in delegates})
        kinds = {name: ("remote" if name in remote_ids else "cli") for name in delegates}
        seat_kind = "cli"
        if delegates and all(k == "remote" for k in kinds.values()) or not delegates and not key.startswith("cli_"):
            seat_kind = "remote"
        spec = SeatSpec(
            kind=seat_kind,
            seat_id=key,
            origin="config_block",
            delegates_to=delegates,
            delegate_kinds=kinds,
            note=(
                "composition seat: runs " + ", ".join(delegates)
                if delegates
                else "no configured CLI or remote is wired into this block"
            ),
        )
        if unresolved and delegated_roles:
            spec.note += f"; role(s) {', '.join(unresolved)} resolve to nothing"
        add(spec)

    for name in _library_installed():
        if name in composition_ids:
            continue
        add(
            SeatSpec(
                kind="cli",
                seat_id=name,
                origin="library_installed",
                delegates_to=sorted(configured_clis),
                delegate_kinds=dict.fromkeys(sorted(configured_clis), "cli"),
                note="installed library seat with no provider of its own; composes the configured CLI agents",
            )
        )

    # -- remotes ---------------------------------------------------------------
    for rid in sorted(remote_ids):
        add(SeatSpec(kind="remote", seat_id=rid, origin="remote_config"))
    configured_now = set(remote_ids)
    for kind in remotes.REMOTE_KIND_IDS:
        if kind in configured_now:
            continue
        add(
            SeatSpec(
                kind="remote",
                seat_id=kind,
                origin="remote_catalog",
                note="catalog kind the operator has never added as a remote",
            )
        )

    ordered = sorted(seats.values(), key=lambda s: (s.kind, s.seat_id))
    _resolve_delegate_ids(ordered)
    _link_clis_to_profiles(ordered)
    return ordered[:MAX_SEATS]


def _link_clis_to_profiles(specs: list[SeatSpec]) -> None:
    """Point a CLI at the LLM profile it provably shares, so a dead account
    surfaces on the seats that actually spend it. Strictly evidence-based — see
    :func:`_link_cli_to_profile` for why a looser rule would be a guess.
    """
    profiles = {s.seat_id: s for s in specs if s.origin == "llm_profile"}
    if not profiles:
        return
    for spec in specs:
        if spec.kind != "cli" or spec.origin in {"config_block", "library_installed"}:
            continue
        linked = _link_cli_to_profile(spec, profiles)
        if linked:
            spec.delegates_to = [linked]
            spec.delegate_kinds = {linked: "api"}
            spec.note = f"same endpoint and model as the {linked!r} LLM profile"


def _resolve_delegate_ids(specs: list[SeatSpec]) -> None:
    """Rewrite delegate *names* into the seat ids that actually exist.

    A composition block says ``planner: "grok"`` and a rail row says
    ``cli: "grok"``, but the seat is ``grok_agent``. Without this pass the
    graph points at seats that were never probed, so a broken delegate would
    silently produce an ``unverified`` composition instead of its real bucket.
    """
    by_key = {(s.kind, s.seat_id): s for s in specs}
    # Prefer the canonical ``<cli>_agent`` seat over a rail row (``cli_agent``)
    # or a designed mirror, so a composition block always resolves to the seat
    # that actually runs the binary.
    priority = {"cli_agents": 0, "discovered_on_path": 1, "designed_agent": 2, "rail_row": 3}
    candidates: dict[tuple[str, str], list[tuple[int, tuple[str, str]]]] = {}
    for spec in specs:
        key = (spec.kind, spec.seat_id)
        rank = priority.get(spec.origin, 5)
        if spec.cli:
            candidates.setdefault(("cli", spec.cli), []).append((rank, key))
        if spec.kind == "remote":
            candidates.setdefault(("remote", spec.seat_id), []).append((rank, key))
    alias = {name: min(rows)[1] for name, rows in candidates.items()}
    for spec in specs:
        resolved: list[str] = []
        for name in spec.delegates_to:
            kind = spec.delegate_kinds.get(name, "cli")
            key = alias.get((kind, name)) or ((kind, name) if (kind, name) in by_key else None)
            target = key[1] if key else name
            if target != name:
                spec.delegate_kinds[target] = kind
            if target not in resolved:
                resolved.append(target)
        spec.delegates_to = resolved
        spec.delegate_kinds = {name: spec.delegate_kinds.get(name, "cli") for name in resolved}
    _retype_delegates_against_roster(specs, by_key)


def _retype_delegates_against_roster(
    specs: list[SeatSpec], by_key: dict[tuple[str, str], SeatSpec]
) -> None:
    """Trust the roster for a delegate's kind, and drop links it cannot back.

    ``resolve_chat_model`` can legitimately return a *CLI* id (the model picker
    spans api / cli / remote namespaces), so assuming "the chat delegate is an
    LLM profile" is a guess. If the name is not a seat at all, the edge is
    removed and the note says so — a dangling edge would otherwise show up as a
    permanently ``unverified`` placeholder.
    """
    kinds_by_name: dict[str, set[str]] = {}
    for kind, seat_id in by_key:
        kinds_by_name.setdefault(seat_id, set()).add(kind)
    for spec in specs:
        kept: list[str] = []
        dropped: list[str] = []
        for name in spec.delegates_to:
            actual = kinds_by_name.get(name)
            if not actual:
                dropped.append(name)
                continue
            if len(actual) == 1:
                spec.delegate_kinds[name] = next(iter(actual))
            kept.append(name)
        if dropped:
            spec.note = "; ".join(
                part for part in (spec.note, f"delegate(s) {', '.join(dropped)} are not seats in this roster") if part
            )
        spec.delegates_to = kept
        spec.delegate_kinds = {name: spec.delegate_kinds.get(name, "cli") for name in kept}


# ---------------------------------------------------------------------------
# evidence helpers
# ---------------------------------------------------------------------------


#: ``connect_ex`` errno -> the token the buckets are keyed on. Split out so the
#: mapping is testable without a network: it is the part that decides whether an
#: operator is told "start the service" or "the box is off".
_TCP_ERRNO_STATES: dict[int, str] = {
    errno.ECONNREFUSED: "refused",
    errno.EHOSTUNREACH: "no_route",
    errno.ENETUNREACH: "no_route",
    errno.ENETDOWN: "no_route",
    errno.EHOSTDOWN: "no_route",
    errno.EADDRNOTAVAIL: "no_route",
    errno.ETIMEDOUT: "timeout",
    errno.EINPROGRESS: "timeout",
    errno.EALREADY: "timeout",
    errno.EWOULDBLOCK: "timeout",
}


def _state_for_errno(code: int | None) -> str:
    if code == 0:
        return "open"
    if code is None:
        return "unresolved"
    return _TCP_ERRNO_STATES.get(int(code), "unresolved")


def _tcp_state(host: str, port: int, timeout: float = TCP_TIMEOUT_S) -> str:
    """``open`` / ``refused`` / ``timeout`` / ``no_route`` / ``unresolved``.

    The refusal / no-route distinction is the whole point: a refusal means the
    host is up with the service stopped, while no route means the host (or the
    firewall) is gone. Different fixes, so different buckets.

    ``connect_ex`` is used rather than ``socket.create_connection`` because the
    latter re-raises a non-blocking errno as ``OSError(errno, 'timed out')``,
    which reads exactly like a real timeout — a powered-off box would then be
    reported as "the service is wedged, restart it there".
    """
    if not host or not port:
        return "unresolved"
    try:
        infos = socket.getaddrinfo(host, int(port), 0, socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        return "unresolved"
    if not infos:
        return "unresolved"
    family, socktype, proto, _canon, sockaddr = infos[0]
    sock = socket.socket(family, socktype, proto)
    try:
        sock.settimeout(timeout)
        return _state_for_errno(sock.connect_ex(sockaddr))
    except OSError:
        return "unresolved"
    finally:
        sock.close()


def identify_endpoint(host: str, port: int, timeout: float = TCP_TIMEOUT_S) -> str:
    """Name the app that owns ``host:port``, or ``""`` when unsure.

    Only strong markers count. A weak guess would send an operator to the wrong
    dashboard, which is worse than saying "something is listening there".
    """
    from swarm.core.remotes import http_json

    state = _tcp_state(host, port, timeout)
    if state != "open":
        return ""
    for path in ("/v1/models", "/", "/api/health"):
        result = http_json("GET", f"http://{host}:{int(port)}{path}", timeout=min(timeout, 2.0))
        blob = f"{result.text or ''} {result.error or ''}".lower()
        server = str((result.headers or {}).get("Server") or (result.headers or {}).get("server") or "")
        blob = f"{blob} {server.lower()}"
        if not blob.strip():
            continue
        try:
            payload = result.body
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict) and payload.get("object") == "list" and isinstance(payload.get("data"), list):
            return "an OpenAI-compatible model server (llama.cpp or similar)"
        for marker, label in _ENDPOINT_MARKERS:
            if marker in blob:
                return label
    return ""


def _bucket_from_markers(text: str) -> str:
    low = (text or "").lower()
    if any(marker in low for marker in _QUOTA_MARKERS):
        return BUCKET_QUOTA
    if any(marker in low for marker in _MODEL_MARKERS):
        return BUCKET_MODEL_INVALID
    if any(marker in low for marker in _AUTH_MARKERS):
        return BUCKET_AUTH
    if any(marker in low for marker in _MISSING_MARKERS):
        return BUCKET_NOT_INSTALLED
    if any(marker in low for marker in _UNEXECUTABLE_MARKERS):
        return BUCKET_NOT_EXECUTABLE
    if any(marker in low for marker in _UNCONFIGURED_MARKERS):
        return BUCKET_NOT_CONFIGURED
    if any(marker in low for marker in _TIMEOUT_MARKERS):
        return BUCKET_TIMEOUT
    return ""


def _install_hint(cli: str) -> str:
    return INSTALL_COMMANDS.get(cli, f"install the `{cli}` CLI and make sure it is on PATH")


def _suggest_models(wanted: str, available: list[str]) -> list[str]:
    """Closest valid ids first: same vendor prefix, then shared stem, then rest."""
    if not available:
        return []
    target = (wanted or "").lower()

    def score(model: str) -> tuple[int, str]:
        low = model.lower()
        if low == target:
            return (0, model)
        head = target.split("-")[0]
        if head and low.startswith(head):
            return (1, model)
        stem = target.split("-")[0][:6]
        if len(stem) >= 4 and stem in low:
            return (2, model)
        return (3, model)

    return sorted(available, key=score)[:MAX_MODEL_SUGGESTIONS]


# ---------------------------------------------------------------------------
# per-kind probes
# ---------------------------------------------------------------------------


def _probe_api_seat(
    spec: SeatSpec,
    *,
    deep: bool,
    redactor: _Redactor,  # noqa: ARG001 — one calling convention for all three probers
) -> SeatFinding:
    """``action="test"`` — a real one-token chat call, so a pass is a real turn."""
    from swarm.core.llm_diagnostics import llm_credential_hint
    from swarm.core.llm_profile_probe import (
        ACTION_LIST_MODELS,
        ERROR_AUTH,
        ERROR_BAD_MODEL,
        ERROR_INVALID,
        ERROR_MISSING_KEY,
        ERROR_MODEL_MISSING,
        ERROR_TIMEOUT,
        hint_for,
        probe_llm_profile,
    )

    finding = SeatFinding(
        kind="api",
        seat_id=spec.seat_id,
        label=spec.label or spec.seat_id,
        origin=spec.origin,
        delegates_to=list(spec.delegates_to),
    )
    if not spec.base_url:
        hint = llm_credential_hint()
        finding.verdict = VERDICT_BROKEN
        finding.bucket = BUCKET_NOT_CONFIGURED
        finding.detail = spec.note or "no provider base_url configured for this seat"
        if spec.missing_env:
            finding.remediation = (
                f"set {spec.missing_env} in the server environment (.env or the user-config "
                f".env) — {spec.seat_id}'s base_url is ${{{spec.missing_env}}} and substitution "
                f"found nothing, so the seat has no endpoint at all"
            )
        elif hint:
            finding.remediation = (
                f"set a base_url for this LLM profile in swarm_config.json ({hint})"
            )
        else:
            finding.remediation = "set a base_url for this LLM profile in swarm_config.json"
        finding.evidence = {
            "probe": "config",
            "credential_hint": hint,
            "missing_env": spec.missing_env or None,
        }
        return finding

    started = time.monotonic()
    with _env_override(spec.inline_env):
        try:
            result = probe_llm_profile(
                base_url=spec.base_url,
                api_key_env=spec.api_key_env,
                model=spec.model,
                action="test",
                timeout=API_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 — a diagnostic never raises
            finding.verdict = VERDICT_BROKEN
            finding.bucket = BUCKET_PROBE_ERROR
            finding.detail = f"probe raised {type(exc).__name__}"
            finding.remediation = "re-run with --debug-logs; the probe itself failed before any HTTP call"
            finding.evidence = {"probe": "llm_profile_probe", "exception": type(exc).__name__}
            return finding
    finding.latency_ms = int(result.get("latency_ms") or (time.monotonic() - started) * 1000)

    available = [str(m) for m in (result.get("models") or [])]
    error_class = str(result.get("error_class") or "").strip()
    evidence: dict[str, Any] = {
        "probe": "llm_profile_probe",
        "action": "test",
        "base_url": spec.base_url,
        "model": spec.model,
        "error_class": error_class or None,
        "api_key_env": spec.api_key_env or None,
        "models_listed": len(available),
    }

    if result.get("ok") and error_class != ERROR_MODEL_MISSING:
        # A 1-token chat call came back 200: this run proved a turn.
        finding.verdict = VERDICT_OK
        finding.proves = PROVES_TURN
        finding.detail = f"1-token chat call accepted by {spec.base_url}"
        finding.remediation = ""
        budget = _seat_timeout(spec)
        if budget and finding.latency_ms >= TIMEOUT_RISK_RATIO * budget * 1000:
            finding.bucket = BUCKET_TIMEOUT_RISK
            finding.verdict = VERDICT_UNVERIFIED
            finding.proves = PROVES_NOTHING
            finding.detail = (
                f"a turn took {finding.latency_ms}ms against a {int(budget)}s seat budget"
            )
            finding.remediation = (
                "raise the seat timeout or move the endpoint closer; the next slow "
                "turn will be killed mid-answer"
            )
        finding.evidence = evidence
        return finding

    # --- failed: gather the real status without spending another chat call ---
    status, body_snippet, extra_models, models_status = _api_status(spec, deep=deep)
    evidence["http_status"] = status
    evidence["models_status"] = models_status
    if body_snippet:
        evidence["body"] = body_snippet
    if extra_models:
        available = extra_models
        evidence["models_listed"] = len(available)

    bucket = ""
    if status == 402 or _bucket_from_markers(body_snippet) == BUCKET_QUOTA:
        bucket = BUCKET_QUOTA
    if not bucket and error_class in {ERROR_BAD_MODEL, ERROR_MODEL_MISSING}:
        bucket = BUCKET_MODEL_INVALID
    if not bucket:
        bucket = _bucket_from_markers(f"{body_snippet} {result.get('hint') or ''}")
    if not bucket and error_class == ERROR_AUTH:
        bucket = BUCKET_AUTH
    if not bucket and error_class == ERROR_MISSING_KEY:
        bucket = BUCKET_AUTH
    if not bucket and error_class == ERROR_INVALID:
        bucket = BUCKET_NOT_CONFIGURED
    if not bucket and error_class == ERROR_TIMEOUT:
        bucket = BUCKET_TIMEOUT
    if not bucket and status in {401, 403}:
        bucket = BUCKET_AUTH

    # Model validation is real: the ids come from the gateway's own list.
    if bucket == BUCKET_MODEL_INVALID and not available and spec.base_url:
        with _env_override(spec.inline_env):
            try:
                listing = probe_llm_profile(
                    base_url=spec.base_url,
                    api_key_env=spec.api_key_env,
                    model="",
                    action=ACTION_LIST_MODELS,
                    timeout=API_TIMEOUT_S,
                )
                available = [str(m) for m in (listing.get("models") or [])]
                evidence["models_listed"] = len(available)
            except Exception:  # noqa: BLE001
                available = []
    if bucket == BUCKET_MODEL_INVALID and available and spec.model not in available:
        bucket = BUCKET_MODEL_INVALID

    if not bucket and error_class:
        bucket = BUCKET_PROBE_ERROR

    finding.verdict = VERDICT_BROKEN
    finding.bucket = bucket or BUCKET_PROBE_ERROR
    finding.proves = PROVES_NOTHING
    finding.evidence = evidence
    finding.detail = _api_detail(
        error_class,
        status,
        body_snippet,
        result.get("hint") or hint_for(error_class),
        finding.bucket,
    )
    finding.remediation = _api_remediation(
        spec,
        finding.bucket,
        available,
        llm_credential_hint() if finding.bucket == BUCKET_AUTH else "",
    )
    return finding


def _api_status(
    spec: SeatSpec, *, deep: bool
) -> tuple[int | None, str, list[str], int | None]:
    """One GET against the seat's own endpoint: real status + body shape.

    A GET, never a chat call — this is how the report reads ``402`` without
    spending a second completion. ``deep`` adds the chat re-probe for seats
    whose model *is* served but whose turn still fails.

    Returns ``(failing_status, body, models, models_route_status)``. The models
    route's own 200 is kept separate: it is not the call that failed, and
    reporting it next to a broken verdict would be a contradiction.
    """
    from swarm.core.llm_profile_probe import (
        ACTION_LIST_MODELS,
        chat_url,
        models_url,
        probe_llm_profile,
    )
    from swarm.core.remotes import http_json

    secret = os.environ.get(spec.api_key_env, "").strip() if spec.api_key_env else ""
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    models: list[str] = []
    try:
        result = http_json("GET", models_url(spec.base_url), headers=headers, timeout=API_TIMEOUT_S)
    except Exception:  # noqa: BLE001
        return None, "", models, None
    status = result.status
    models_status = result.status
    if result.status in {200, 201}:
        # The models route answered, so its 200 is NOT the status that failed —
        # the chat call is. Reporting "status 200" on a broken seat would be a
        # contradiction, so the models status goes to the evidence and the chat
        # verdict is carried by the probe's own classification instead.
        status = None
    # A 200 body is a model list, which is already reported as ``models_listed``.
    # Only a failing status has a body worth quoting.
    snippet = (
        f"{result.error or ''} {result.text or ''}"[:600]
        if result.status not in {200, 201}
        else ""
    )
    with _env_override(spec.inline_env):
        if result.status in {200, 201}:
            try:
                listing = probe_llm_profile(
                    base_url=spec.base_url,
                    api_key_env=spec.api_key_env,
                    model="",
                    action=ACTION_LIST_MODELS,
                    timeout=API_TIMEOUT_S,
                )
                models = [str(m) for m in (listing.get("models") or [])]
            except Exception:  # noqa: BLE001
                models = []
            if deep and spec.model:
                chat = http_json(
                    "POST",
                    chat_url(spec.base_url),
                    headers=headers,
                    body={
                        "model": spec.model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "stream": False,
                    },
                    timeout=API_TIMEOUT_S,
                )
                if chat.status not in {200, 201}:
                    status = chat.status
                    models_status = chat.status
                    snippet = (chat.error or "") + " " + (chat.text or "")[:600]
    return status, snippet, models, models_status


def _api_detail(
    error_class: str, status: int | None, body: str, hint: str, bucket: str
) -> str:
    """The evidence line.

    Only the *deciding* evidence is quoted. The generic hint that came with the
    probe is dropped when the HTTP status already overrode it — printing
    "could not reach host" next to a 402 would read as a contradiction and send
    the operator to the wrong page.
    """
    if status:
        lead = f"status {status}"
        tail_hint = "" if bucket != BUCKET_PROBE_ERROR else f" · {hint}"
    elif bucket == BUCKET_PROBE_ERROR:
        lead = error_class or "provider probe failed"
        tail_hint = f" · {hint}" if hint else ""
    else:
        lead = hint or error_class or "provider probe failed"
        tail_hint = ""
    snippet = " ".join(str(body or "").split())[:160]
    return f"{lead}{tail_hint}{f' — {snippet}' if snippet else ''}"


def _api_remediation(
    spec: SeatSpec, bucket: str, available: list[str], credential_hint: str
) -> str:
    host = urlparse(spec.base_url).hostname or spec.base_url
    if bucket == BUCKET_QUOTA:
        # Deliberately short: ``_with_dependent_count`` appends "N dependent
        # seats fail with it", so the base text must not also claim to know them.
        return (
            f"top up the credit/balance behind {host} — it answers 402 Payment Required, "
            f"which no config change fixes"
        )
    if bucket == BUCKET_AUTH:
        env = spec.api_key_env or "the profile's api_key"
        tail = f" ({credential_hint})" if credential_hint else ""
        return f"set {env} for this seat in the server environment or its profile{tail}"
    if bucket == BUCKET_MODEL_INVALID:
        if available:
            picks = ", ".join(_suggest_models(spec.model, available))
            return (
                f"{spec.model} is not served by {spec.base_url} — pick from the gateway's "
                f"model list: {picks}"
            )
        return (
            f"{spec.model} is not served by {spec.base_url} — list the gateway's models "
            f"(Settings → Profiles, or action=list_models) and pin one of them"
        )
    if bucket == BUCKET_NOT_CONFIGURED:
        return "set base_url / model for this LLM profile in swarm_config.json"
    if bucket == BUCKET_TIMEOUT:
        return (
            f"{spec.base_url} accepted the connection but did not answer within "
            f"{int(API_TIMEOUT_S)}s — check the gateway's queue/worker health, or move the endpoint"
        )
    if bucket == BUCKET_UNREACHABLE:
        return f"nothing answers at {spec.base_url} — start the provider or correct the base_url"
    if bucket == BUCKET_PROBE_ERROR:
        return (
            f"the provider rejected the probe at {spec.base_url} in a shape this report "
            f"will not guess at; read the body above and fix the provider config"
        )
    return f"inspect the provider answer above for {spec.base_url}"


def _probe_cli_seat(spec: SeatSpec, *, deep: bool, redactor: _Redactor) -> SeatFinding:
    """Liveness only: binary on PATH + ``--version``. Never a turn."""
    from swarm.core import seat_health
    from swarm.core.cli_catalog import executable_for

    finding = SeatFinding(
        kind="cli",
        seat_id=spec.seat_id,
        label=spec.label or spec.seat_id,
        origin=spec.origin,
        delegates_to=list(spec.delegates_to),
        proves=PROVES_LIVENESS,
    )
    name = spec.cli or (spec.seat_id.removesuffix("_agent") if spec.seat_id.endswith("_agent") else spec.seat_id)
    if spec.origin == "discovered_on_path":
        finding.verdict = VERDICT_BROKEN
        finding.bucket = BUCKET_MISCONFIGURED
        finding.detail = f"`{name}` resolves on PATH but has no cli_agents.{name} entry"
        finding.remediation = (
            f"add `cli_agents.{name}` to swarm_config.json (or Settings → CLI Agents); "
            f"until then the seat answers 'No CLI agents are configured'"
        )
        finding.evidence = {
            "probe": "shutil.which",
            "executable": executable_for(name) or name,
            "path": shutil.which(executable_for(name) or name),
            "configured": False,
        }
        return finding

    verdict = seat_health.probe_seat("cli", name or spec.seat_id, force=True, cli=name)
    finding.latency_ms = int(verdict.latency_ms or 0)
    reason = str(verdict.reason or "")
    finding.detail = reason or f"`{name} --version` answered"
    finding.evidence = {
        "probe": "seat_health.probe_seat(cli)",
        "cli": name,
        "configured": True,
        "state": verdict.state,
        "timeout_s": spec.timeout_s,
    }
    if spec.model_pin:
        finding.evidence["model_pin"] = spec.model_pin
    if spec.base_url:
        finding.evidence["base_url"] = spec.base_url
        finding.evidence["api_key_env"] = spec.api_key_env or None
    redactor.add(*(spec.inline_env.values() or ()))

    if verdict.state == seat_health.STATE_BROKEN:
        finding.verdict = VERDICT_BROKEN
        finding.proves = PROVES_NOTHING
        finding.bucket = _bucket_from_markers(reason) or BUCKET_NOT_INSTALLED
        path = shutil.which(executable_for(name) or name)
        if finding.bucket == BUCKET_NOT_INSTALLED:
            finding.remediation = _install_hint(name)
        elif finding.bucket == BUCKET_NOT_EXECUTABLE:
            finding.remediation = (
                f"`{name}` is on PATH at {path} but the OS will not run it — fix the execute "
                f"bit or install the build for this architecture; do not reinstall a binary "
                f"that is already there"
            )
            finding.evidence["path"] = path
        elif finding.bucket == BUCKET_TIMEOUT:
            finding.remediation = (
                f"`{name}` is on PATH but never answered `--version` — the binary is wedged "
                f"or is waiting on a provider it cannot reach; restart it, or raise "
                f"cli_agents.{name}.timeout"
            )
        else:
            finding.remediation = f"`{name}` is not usable here: {reason}"
        return finding

    # Alive. A real turn was not run, so this is never "ok".
    finding.verdict = VERDICT_UNVERIFIED
    finding.proves = PROVES_LIVENESS
    finding.remediation = ""
    if deep:
        from swarm.core import cli_models

        try:
            result = cli_models.list_models(name, timeout=10.0)
        except Exception:  # noqa: BLE001
            result = None
        if result is not None:
            finding.evidence["deep_probe"] = "cli_models.list_models"
            finding.evidence["deep_models"] = len(result.models)
            if result.warning:
                finding.evidence["deep_warning"] = redactor.text(result.warning)
                bucket = _bucket_from_markers(result.warning)
                if bucket in {BUCKET_AUTH, BUCKET_QUOTA, BUCKET_MODEL_INVALID, BUCKET_NOT_CONFIGURED, BUCKET_TIMEOUT}:
                    finding.verdict = VERDICT_BROKEN
                    finding.proves = PROVES_NOTHING
                    finding.bucket = bucket
                    finding.detail = redactor.text(result.warning)
                    finding.remediation = _cli_provider_remediation(bucket, name, spec, result.models)
    if finding.verdict == VERDICT_UNVERIFIED:
        budget = _seat_timeout(spec)
        if budget and finding.latency_ms >= TIMEOUT_RISK_RATIO * budget * 1000:
            finding.bucket = BUCKET_TIMEOUT_RISK
            finding.detail = (
                f"`{name} --version` took {finding.latency_ms}ms against a {int(budget)}s "
                f"seat timeout — a real turn has far more to do"
            )
            finding.remediation = (
                f"raise cli_agents.{name}.timeout above {int(budget)}s or move the provider closer"
            )
    return finding


def _cli_provider_remediation(
    bucket: str, name: str, spec: SeatSpec, models: list[str]
) -> str:
    if bucket == BUCKET_QUOTA:
        return (
            f"top up the credit behind `{name}`'s provider"
            + (f" ({spec.model_pin})" if spec.model_pin else "")
            + " — the model list call fails the same way a turn would"
        )
    if bucket == BUCKET_AUTH:
        env = spec.api_key_env or "the CLI's own provider key"
        return f"set {env} so `{name}` can authenticate to its provider"
    if bucket == BUCKET_MODEL_INVALID:
        picks = ", ".join(_suggest_models(spec.model_pin, models))
        return (
            f"`{name}` is pinned to {spec.model_pin}, which its provider does not serve"
            + (f" — try: {picks}" if picks else " — run the CLI's model list to see valid ids")
        )
    if bucket == BUCKET_NOT_CONFIGURED:
        return f"`{name}` has no provider configured (no model pin, no base URL, no key)"
    if bucket == BUCKET_TIMEOUT:
        return (
            f"`{name}`'s provider took longer than the probe window without refusing — "
            f"it is slow or unreachable; check the endpoint, then raise cli_agents.{name}.timeout"
        )
    return f"`{name}`'s provider rejected the model-list call; read the warning above"


def _probe_remote_seat(spec: SeatSpec, *, deep: bool, redactor: _Redactor) -> SeatFinding:
    """``check_health`` (TCP + HTTP). Public health says nothing about a turn."""
    from swarm.core import remotes

    finding = SeatFinding(
        kind="remote",
        seat_id=spec.seat_id,
        label=spec.label or spec.seat_id,
        origin=spec.origin,
        delegates_to=list(spec.delegates_to),
        proves=PROVES_LIVENESS,
    )
    try:
        resolved = remotes.load_remote(spec.seat_id)
    except Exception as exc:  # noqa: BLE001 — an unadded remote raises by design
        # ``load_remote`` refuses an opt-in kind the operator never added. The
        # catalog default is still the right thing to report on, so fall back to
        # it rather than giving up: the operator needs to know which field to set.
        try:
            resolved = remotes.default_spec(remotes.kind_of_instance(spec.seat_id))
        except Exception:  # noqa: BLE001
            finding.verdict = VERDICT_BROKEN
            finding.bucket = BUCKET_NOT_CONFIGURED
            finding.detail = f"remote spec could not be resolved ({type(exc).__name__})"
            finding.remediation = f"add {spec.seat_id} in Settings → Remotes, or remove the seat"
            finding.evidence = {"probe": "remotes.load_remote", "exception": type(exc).__name__}
            return finding

    host, port = resolved.origin()
    finding.evidence = {
        "probe": "remotes.check_health",
        "base_url": resolved.base_url,
        "host": host,
        "port": port,
        "health_path": resolved.health_path,
        "spec_source": resolved.source,
        "api_key_env": resolved.api_key_env or None,
        "cookie_env": resolved.session_cookie_env or None,
    }
    redactor.add(resolved.api_key, resolved.cookie)

    if not remotes.is_configured(spec.seat_id):
        finding.verdict = VERDICT_BROKEN
        finding.bucket = BUCKET_NOT_CONFIGURED
        placeholder = remotes.is_placeholder_base_url(resolved.base_url)
        finding.detail = (
            f"{remotes.kind_label(spec.seat_id)} was never added as a remote; the built-in "
            + (
                f"catalog default {resolved.base_url} is a placeholder address, not a live instance"
                if placeholder
                else f"catalog default {resolved.base_url or '(empty)'} is what the sidebar seat points at"
            )
        )
        finding.remediation = _remote_not_configured_remediation(spec.seat_id, resolved, host, port)
        finding.evidence["placeholder_default"] = placeholder
        if not placeholder:
            finding.evidence["tcp"] = _tcp_state(host, port)
            finding.evidence["listens_as"] = identify_endpoint(host, port) or None
        return finding

    try:
        health = remotes.check_health(spec.seat_id, timeout=REMOTE_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        finding.verdict = VERDICT_BROKEN
        finding.bucket = BUCKET_PROBE_ERROR
        finding.detail = f"health probe raised {type(exc).__name__}"
        finding.remediation = "re-run with --debug-logs; the health probe itself failed"
        finding.evidence["exception"] = type(exc).__name__
        return finding

    finding.latency_ms = int(health.latency_ms or 0)
    detail = str(health.detail or "")
    finding.detail = detail or f"health state {health.state}"
    finding.evidence.update(
        {
            "state": health.state,
            "http_status": health.http_status,
            "version_path": resolved.version_path,
        }
    )

    if health.ok:
        finding.verdict = VERDICT_UNVERIFIED
        finding.proves = PROVES_LIVENESS
        finding.remediation = ""
        finding.evidence["turn_note"] = (
            "health is a liveness route; no turn was run, so the seat is unverified"
        )
        # ``check_health`` deliberately calls a 401 "UP — the endpoint is alive".
        # True, and useless to an operator: nothing that *sends* will work until
        # the credential is there. The status is the evidence.
        if health.http_status in {401, 403}:
            finding.verdict = VERDICT_BROKEN
            finding.proves = PROVES_NOTHING
            finding.bucket = BUCKET_AUTH
            finding.detail = (
                f"http {health.http_status} on {resolved.health_path} — the service is alive "
                f"but refuses this credential"
            )
            finding.remediation = _remote_auth_remediation(BUCKET_AUTH, spec.seat_id, resolved)
            return finding
        if deep:
            operated = _remote_list(spec.seat_id)
            if operated is not None:
                finding.evidence["deep_probe"] = "remotes.operate(list)"
                ok, op_detail, status = operated
                if not ok:
                    bucket = BUCKET_AUTH if status in {401, 403} else _bucket_from_markers(op_detail)
                    if bucket:
                        finding.verdict = VERDICT_BROKEN
                        finding.proves = PROVES_NOTHING
                        finding.bucket = bucket
                        finding.detail = redactor.text(op_detail)
                        finding.remediation = _remote_auth_remediation(
                            bucket, spec.seat_id, resolved
                        )
        return finding

    finding.verdict = VERDICT_BROKEN
    finding.proves = PROVES_NOTHING
    # ``check_health`` already reports the two "nothing was contacted" gaps.
    # They are the strongest possible evidence and cost no probe time, so they
    # are consulted before anything else.
    if getattr(health, "gap", ""):
        finding.bucket = BUCKET_NOT_CONFIGURED
        finding.detail = detail or "the remote has no live instance URL"
        finding.remediation = _remote_not_configured_remediation(
            spec.seat_id, resolved, host, port
        )
        finding.evidence["health_gap"] = health.gap
        return finding

    tcp = _tcp_state(host, port)
    finding.evidence["tcp"] = tcp
    if health.state == "AUTH" or health.http_status in {401, 403}:
        finding.bucket = BUCKET_AUTH
        finding.remediation = _remote_auth_remediation(BUCKET_AUTH, spec.seat_id, resolved)
        return finding
    # Real transport outcome first. The generic prober's own wording
    # ("tcp H:P refused/timed out") covers two different failures, so text
    # markers must not be read until the socket has actually spoken.
    if tcp == "refused":
        finding.bucket = BUCKET_SERVICE_DOWN
        finding.remediation = (
            f"nothing is listening on {host}:{port} — start {remotes.kind_label(spec.seat_id)} "
            f"there, or remove the remote from Settings → Remotes"
        )
        return finding
    if tcp == "timeout":
        finding.bucket = BUCKET_TIMEOUT
        # A timed-out connect is genuinely ambiguous from here: a filtered SYN
        # looks exactly like a wedged service. Say both, do not pick one.
        finding.remediation = (
            f"{host}:{port} neither answered nor refused within {int(TCP_TIMEOUT_S)}s — "
            f"check the host is up and the firewall allows "
            f"{remotes.kind_label(spec.seat_id)}; if the box is fine, restart the service there"
        )
        return finding
    if tcp == "unresolved":
        finding.bucket = BUCKET_UNREACHABLE
        finding.remediation = (
            f"{host} does not resolve — fix the DNS/hostname for "
            f"{remotes.kind_label(spec.seat_id)}, or point its base_url at a real host"
        )
        return finding
    if tcp == "no_route":
        finding.bucket = BUCKET_UNREACHABLE
        finding.remediation = (
            f"there is no route to {host} — the box is powered off or the firewall drops it; "
            f"bring {host} back, or remove the remote from Settings → Remotes"
        )
        return finding
    # Something answered HTTP. Now its words are the evidence.
    marker_bucket = _bucket_from_markers(detail)
    if marker_bucket and marker_bucket != BUCKET_NOT_CONFIGURED:
        finding.bucket = marker_bucket
        base = (
            _remote_auth_remediation(marker_bucket, spec.seat_id, resolved)
            if marker_bucket in {BUCKET_AUTH, BUCKET_QUOTA}
            else f"the remote answered: {detail}"
        )
        finding.remediation = f"{base} (it said: {detail})" if marker_bucket in {BUCKET_AUTH, BUCKET_QUOTA} else base
        return finding
    finding.bucket = BUCKET_PROBE_ERROR
    finding.remediation = (
        f"{remotes.kind_label(spec.seat_id)} answered neither a health OK nor a recognisable "
        f"failure ({health.state}: {detail}) — read the detail above; this report will not guess"
    )
    return finding


def _remote_list(remote_id: str) -> tuple[bool, str, int | None] | None:
    from swarm.core.remotes import operate

    try:
        result = operate(remote_id, "list", timeout=8.0)
    except Exception:  # noqa: BLE001
        return None
    return bool(result.ok), str(result.detail or ""), result.http_status


def _remote_auth_remediation(bucket: str, remote_id: str, resolved: Any) -> str:
    from swarm.core.remotes import _ENV_BASE, _ENV_KEY, kind_label

    label = kind_label(remote_id)
    kind = resolved.kind or remote_id
    if bucket == BUCKET_AUTH:
        names = [
            name
            for name in (resolved.api_key_env, resolved.session_cookie_env)
            if name
        ] or [_ENV_KEY.get(kind, "API_KEY")]
        env_base = _ENV_BASE.get(kind, "")
        tail = f" or set {env_base}" if env_base else ""
        return f"set {' and '.join(names)} in the server environment{tail}; the remote answered an auth error"
    if bucket == BUCKET_QUOTA:
        return f"top up the credit behind {label} at {resolved.base_url}"
    if bucket == BUCKET_TIMEOUT:
        return (
            f"{label} at {resolved.base_url} did not answer and did not refuse within "
            f"{int(REMOTE_TIMEOUT_S)}s — check the host/firewall first, then restart {label} there"
        )
    return f"{label} rejected the request: check its auth and health config"


def _remote_not_configured_remediation(remote_id: str, resolved: Any, host: str, port: int) -> str:
    """Name the one field to fill, using what the port actually answers.

    A placeholder catalog default (``remotes.is_placeholder_base_url``) is
    already proof the remote was never pointed anywhere, so it short-circuits:
    probing it can only waste a timeout. A real default that has a listener
    gets the fingerprint, because ":8088 is llama.cpp" is the whole finding.
    """
    from swarm.core.remotes import (
        _ENV_BASE,
        _ENV_KEY,
        is_placeholder_base_url,
        kind_label,
    )

    label = kind_label(remote_id)
    kind = resolved.kind or remote_id
    env_key = _ENV_KEY.get(kind, "API_KEY")
    env_base = _ENV_BASE.get(kind, "")
    if not resolved.base_url:
        ssh = " or set HERDR_SSH_HOST" if kind == "herdr" else ""
        return (
            f"no base_url is set for {label} — run `swarm-cli remotes set {remote_id} "
            f"--base-url <url> --api-key-env {env_key}`{ssh}, or remove the seat"
        )
    if is_placeholder_base_url(resolved.base_url):
        return (
            f"no base_url is set; the catalog default {resolved.base_url} is a placeholder "
            f"address, not a live {label} — set {env_base or f'{label.upper()}_BASE_URL'} to "
            f"the real {label} host (key via {env_key}), or remove the seat"
        )
    owner = identify_endpoint(host, port) if host and port else ""
    if owner:
        return (
            f"no base_url is set; {host}:{port} answers as {owner}, not {label} — set "
            f"{env_base or f'{label.upper()}_BASE_URL'} to the real {label} host, or remove the seat"
        )
    return (
        f"no base_url is set; the catalog default {resolved.base_url} has no listener — set "
        f"{env_base or f'{label.upper()}_BASE_URL'} to the real {label} host (key via {env_key}), "
        f"or remove the seat"
    )


def _seat_timeout(spec: SeatSpec) -> float | None:
    """The seat's own turn budget, or ``None`` when it does not declare one.

    A risk needs a budget. Inventing a 240s default would flag every healthy
    300ms probe, so an undeclared timeout means "no claim", not "plenty of room".
    """
    value = spec.timeout_s
    if isinstance(value, (int, float)) and value and value > 0:
        return float(value)
    return None


# ---------------------------------------------------------------------------
# composition / propagation
# ---------------------------------------------------------------------------


def _probe_composition_seat(spec: SeatSpec) -> SeatFinding:
    """A seat with no provider of its own. It can only be as healthy as its delegates."""
    finding = SeatFinding(
        kind=spec.kind,
        seat_id=spec.seat_id,
        label=spec.label or spec.seat_id,
        origin=spec.origin,
        delegates_to=list(spec.delegates_to),
    )
    if not spec.delegates_to:
        finding.verdict = VERDICT_BROKEN
        finding.bucket = BUCKET_NOT_CONFIGURED
        finding.detail = spec.note or "this seat has no configured delegate to run"
        finding.remediation = (
            f"configure a delegate for {spec.seat_id} in swarm_config.json — the seat answers "
            f"'No CLI agents are configured' / 'No planner CLI is configured for {spec.seat_id}' "
            f"until one exists"
        )
        finding.evidence = {"probe": "config", "delegates_to": []}
        return finding
    finding.verdict = VERDICT_UNVERIFIED
    finding.proves = PROVES_NOTHING
    finding.detail = f"composition seat over {', '.join(spec.delegates_to)}"
    finding.remediation = ""
    finding.evidence = {"probe": "delegation", "delegates_to": list(spec.delegates_to)}
    return finding


def _apply_delegate_verdicts(
    specs: dict[tuple[str, str], SeatSpec],
    findings: dict[tuple[str, str], SeatFinding],
    probed: set[tuple[str, str]] | None = None,
) -> None:
    """Push a delegate's bucket onto every seat that runs it.

    This is how ``grok``'s 402 reaches ``cli_map`` / ``cli_fusion`` /
    ``hybrid_team``: the composition seat never calls the provider, so nothing
    else would connect those failures to the credit that is actually empty.

    A seat that was probed itself is only overridden when its delegate is
    *broken*; otherwise its own (liveness) evidence is more informative than a
    chain of healthy delegates.
    """
    probed = probed if probed is not None else set(findings)
    resolved: set[tuple[str, str]] = set()
    order = sorted(specs, key=lambda key: len(specs[key].delegates_to))
    for _ in range(len(order) + 1):
        progressed = False
        for key in order:
            if key in resolved:
                continue
            spec = specs[key]
            if not spec.delegates_to:
                # A leaf: its own probe is the whole story. Never overwrite it.
                resolved.add(key)
                progressed = True
                continue
            pending = [
                (spec.delegate_kinds.get(name, "cli"), name)
                for name in spec.delegates_to
            ]
            if any((kind, name) not in findings for kind, name in pending):
                continue
            if any((kind, name) not in resolved for kind, name in pending):
                continue
            resolved.add(key)
            progressed = True
            finding = findings[key]
            broken = [
                (name, findings[(kind, name)])
                for kind, name in pending
                if findings[(kind, name)].verdict == VERDICT_BROKEN
            ]
            if broken:
                name, root = broken[0]
                finding.verdict = VERDICT_BROKEN
                finding.proves = PROVES_NOTHING
                finding.bucket = root.bucket
                finding.detail = f"via {name}: {root.detail}"
                finding.remediation = root.remediation
                finding.evidence = {"via": name, "via_bucket": root.bucket, "delegate": root.evidence}
            elif key not in probed:
                finding.verdict = VERDICT_UNVERIFIED
                finding.proves = PROVES_NOTHING
                finding.evidence = {
                    "delegation": "all delegates reachable",
                    "delegate_states": {
                        name: findings[(kind, name)].verdict for kind, name in pending
                    },
                }
                finding.detail = (
                    "delegates answered liveness only; no turn was run for this composition seat"
                )
            else:
                finding.evidence["provider_delegate"] = pending[0][1]
                finding.evidence["provider_delegate_state"] = findings[pending[0]].verdict
        if not progressed:
            break
    for key in order:
        if key not in resolved:
            # A cycle, or a delegate that is not itself a seat.
            findings[key].evidence.setdefault("delegation", "unresolved (cycle or unknown delegate)")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def diagnose(
    config: dict[str, Any] | None = None,
    *,
    deep: bool = False,
    limit: int = MAX_SEATS,
    kinds: Iterable[str] | None = None,
) -> list[SeatFinding]:
    """Probe the roster and return one finding per seat, sorted worst-first.

    Read-only. ``deep`` is the only switch that spends more than the minimal
    probe per seat.
    """
    specs_list = enumerate_seats(config)
    wanted = {str(k).strip().lower() for k in kinds} if kinds else set()
    specs_list = [s for s in specs_list if not wanted or s.kind in wanted][: max(1, int(limit or MAX_SEATS))]

    specs: dict[tuple[str, str], SeatSpec] = {(s.kind, s.seat_id): s for s in specs_list}
    redactor = _Redactor()
    findings: dict[tuple[str, str], SeatFinding] = {}
    direct: list[tuple[str, str]] = []

    for spec in specs_list:
        if spec.origin in {"config_block", "library_installed"}:
            findings[(spec.kind, spec.seat_id)] = _probe_composition_seat(spec)
            continue
        if spec.kind == "api" and not spec.base_url and spec.delegates_to:
            # Resolved through its LLM profile; nothing to probe of its own.
            # The verdict is filled in by _apply_delegate_verdicts.
            findings[(spec.kind, spec.seat_id)] = SeatFinding(
                kind=spec.kind,
                seat_id=spec.seat_id,
                label=spec.label or spec.seat_id,
                origin=spec.origin,
                delegates_to=list(spec.delegates_to),
            )
            continue
        direct.append((spec.kind, spec.seat_id))

    def run(key: tuple[str, str]) -> tuple[tuple[str, str], SeatFinding]:
        spec = specs[key]
        if spec.kind == "api":
            finding = _probe_api_seat(spec, deep=deep, redactor=redactor)
        elif spec.kind == "cli":
            finding = _probe_cli_seat(spec, deep=deep, redactor=redactor)
        else:
            finding = _probe_remote_seat(spec, deep=deep, redactor=redactor)
        return key, finding

    if direct:
        workers = min(MAX_WORKERS, len(direct))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for key, finding in pool.map(run, direct):
                findings[key] = finding

    # Delegates that are only referenced (e.g. an LLM profile nobody else uses
    # is already a direct probe; a remote referenced by a team is too).
    for spec in specs_list:
        for name in spec.delegates_to:
            kind = spec.delegate_kinds.get(name, "cli")
            if (kind, name) not in findings:
                findings[(kind, name)] = SeatFinding(
                    kind=kind, seat_id=name, origin="referenced_only", verdict=VERDICT_UNVERIFIED
                )

    _apply_delegate_verdicts(specs, findings, set(direct))

    # Count who a broken seat takes down with it: every seat whose delegation
    # chain bottoms out at it.
    dependents: dict[tuple[str, str], set[str]] = {}
    for key in specs:
        root = _root_of(key, specs)
        if root is not None and root != key:
            dependents.setdefault(root, set()).add(key[1])

    rows: list[SeatFinding] = [findings[key] for key in findings]
    for key in findings:
        root = _root_of(key, specs)
        if root is None or root == key:
            continue
        root_finding = findings.get(root)
        if root_finding is None or root_finding.verdict != VERDICT_BROKEN:
            continue
        count = len(dependents.get(root, set()))
        if count:
            root_finding.remediation = _with_dependent_count(root_finding.remediation, count)

    order = {VERDICT_BROKEN: 0, VERDICT_UNVERIFIED: 1, VERDICT_OK: 2}
    rows.sort(key=lambda f: (order.get(f.verdict, 3), f.kind, f.seat_id))
    return rows


def _root_of(key: tuple[str, str], specs: dict[tuple[str, str], SeatSpec]) -> tuple[str, str] | None:
    """Walk delegates to the leaf seat a failure really lives on."""
    seen = {key}
    current = key
    for _ in range(8):
        spec = specs.get(current)
        if spec is None or not spec.delegates_to:
            return current
        nxt = None
        for name in spec.delegates_to:
            candidate = (spec.delegate_kinds.get(name, "cli"), name)
            if candidate in specs and candidate not in seen:
                nxt = candidate
                break
        if nxt is None:
            return current
        seen.add(nxt)
        current = nxt
    return current


def _with_dependent_count(remediation: str, count: int) -> str:
    if count <= 0 or "dependent" in remediation:
        return remediation
    noun = "seat" if count == 1 else "seats"
    verb = "fails" if count == 1 else "fail"
    return f"{remediation.rstrip('.')}; {count} dependent {noun} {verb} with it."


def report_payload(
    config: dict[str, Any] | None = None,
    *,
    deep: bool = False,
    limit: int = MAX_SEATS,
    kinds: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The JSON shape. Counters first, rows after — scripts read the summary."""
    redactor = _Redactor()
    findings = diagnose(config, deep=deep, limit=limit, kinds=kinds)
    rows = [f.as_dict(redactor) for f in findings]
    buckets: dict[str, int] = {}
    for row in rows:
        if row["bucket"]:
            buckets[row["bucket"]] = buckets.get(row["bucket"], 0) + 1
    return {
        "object": "seat_doctor_report",
        "deep": bool(deep),
        "read_only": True,
        "totals": {
            "seats": len(rows),
            "broken": sum(1 for r in rows if r["verdict"] == VERDICT_BROKEN),
            "unverified": sum(1 for r in rows if r["verdict"] == VERDICT_UNVERIFIED),
            "ok": sum(1 for r in rows if r["verdict"] == VERDICT_OK),
        },
        "buckets": dict(sorted(buckets.items(), key=lambda kv: -kv[1])),
        "results": rows,
    }


_COLUMNS = (("kind", 7), ("seat", 22), ("verdict", 11), ("bucket", 16))


def format_report(payload: dict[str, Any], *, show_all: bool = False) -> str:
    """Aligned plain text. Broken rows first; ``show_all`` includes the rest."""
    rows = payload.get("results") or []
    if not show_all:
        rows = [r for r in rows if r.get("verdict") == VERDICT_BROKEN]
    lines = ["  ".join(name.upper().ljust(width) for name, width in _COLUMNS) + "  REMEDIATION"]
    for row in rows:
        cells = [
            str(row.get("kind") or "").ljust(_COLUMNS[0][1]),
            str(row.get("seat_id") or "").ljust(_COLUMNS[1][1]),
            str(row.get("verdict") or "").upper().ljust(_COLUMNS[2][1]),
            (str(row.get("bucket") or "-")).ljust(_COLUMNS[3][1]),
        ]
        text = str(row.get("remediation") or row.get("detail") or "").replace("\n", " ")
        lines.append("  ".join(cells) + "  " + text)
    totals = payload.get("totals") or {}
    lines.append("")
    lines.append(
        "seats {seats} · broken {broken} · unverified {unverified} · ok {ok}".format(
            seats=totals.get("seats", 0),
            broken=totals.get("broken", 0),
            unverified=totals.get("unverified", 0),
            ok=totals.get("ok", 0),
        )
    )
    if not show_all:
        lines.append("(--all adds the unverified/ok rows; --deep proves a turn for more seats)")
    return "\n".join(lines)


__all__ = [
    "BUCKET_AUTH",
    "BUCKET_MISCONFIGURED",
    "BUCKET_MODEL_INVALID",
    "BUCKET_NOT_CONFIGURED",
    "BUCKET_NOT_EXECUTABLE",
    "BUCKET_NOT_INSTALLED",
    "BUCKET_PROBE_ERROR",
    "BUCKET_QUOTA",
    "BUCKET_SERVICE_DOWN",
    "BUCKET_TIMEOUT",
    "BUCKET_TIMEOUT_RISK",
    "BUCKET_UNREACHABLE",
    "MAX_SEATS",
    "VALID_KINDS",
    "SeatFinding",
    "SeatSpec",
    "VERDICT_BROKEN",
    "VERDICT_OK",
    "VERDICT_UNVERIFIED",
    "diagnose",
    "enumerate_seats",
    "format_report",
    "identify_endpoint",
    "report_payload",
]
