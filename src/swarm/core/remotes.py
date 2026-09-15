"""Remote agent-harness connectivity: Hermes, OpenMousBot (id omb), Rakazo, Herdr, nested swarm.

Open Swarm is a harness *for* other harnesses. This module is the single
source of truth for:

* persisted ``remotes`` config (base URL + auth)
* honest health/version probes (one request, no retry/crash-loop)
* operate: list / send a job via each harness's real HTTP API
* opt-in catalog (REQ-59): only *configured* remotes appear in Settings / dropdowns

LAN defaults are operator facts (dev-worker-gpu / Windows2). They are not
invented cloud hosts. Do **not** point these remotes at Fly open-litellm;
the LAN LLM for *this* swarm is ``http://198.51.100.30:8000/v1``.

The ``swarm`` kind (alias ``open-swarm``) is another open-swarm *process*
reached over HTTP — own listen port, own local DB. Nesting is network
remote, not in-process recursion. v1 refuses a swarm base URL that matches
this server's listen URL. Do not auto-add this instance as its own remote;
a child is not required to nest the parent. The catalog default is the
unreachable stub ``http://127.0.0.1:9`` (not a LAN inventory).

Auth is optional per remote. Missing auth is reported honestly; we never
enable ``SWARM_ALLOW_ANONYMOUS`` and we never clone OpenMousBot source.
Persist api_key as an env-var placeholder (``${SWARM_REMOTE_API_KEY}``) —
never commit secrets.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Operate / health adapters (PR 318 + REQ-57). Extra kinds are addable in
# Settings (REQ-59). Herdr is opt-in (REQ-64): no baked LAN default.
REMOTE_IDS: tuple[str, ...] = ("hermes", "anythingllm", "omb", "rakazo", "herdr", "swarm", "trueforge")
REMOTE_KIND_IDS: tuple[str, ...] = ("hermes", "anythingllm", "omb", "rakazo", "herdr", "swarm", "trueforge")


def kind_of_instance(remote_id: str, config: dict[str, Any] | None = None) -> str:
    """Resolve the remote *kind* for a catalog id (REQ-856 / #211).

    Ids are either a bare kind (``trueforge``) or a named instance of a kind
    (``trueforge-2``, ``trueforge_prod``, ``trueforge_gpu``): the kind is the
    prefix before the first ``-`` / ``_`` that maps to a known kind, or the
    explicit ``kind`` specified in the configured remote entry. Unknown ids
    fall back to the whole id so existing behavior is unchanged.
    """
    raw = (remote_id or "").strip().lower()
    raw = _KIND_ALIASES.get(raw, raw)
    if raw in REMOTE_KIND_IDS:
        return raw
    if config and isinstance(config, dict):
        remotes_block = config.get("remotes")
        if isinstance(remotes_block, dict):
            entry = remotes_block.get(remote_id) or remotes_block.get(raw)
            if isinstance(entry, dict):
                k = entry.get("kind")
                if k:
                    k_str = _KIND_ALIASES.get(str(k).strip().lower(), str(k).strip().lower())
                    if k_str in REMOTE_KIND_IDS:
                        return k_str
    for sep in ("-", "_"):
        head, _, tail = raw.partition(sep)
        if tail and head in REMOTE_KIND_IDS:
            return head
    if raw.startswith("trueforge"):
        return "trueforge"
    if raw.startswith("anythingllm"):
        return "anythingllm"
    return raw or (remote_id or "")


def is_trueforge_remote(remote_id: str, config: dict[str, Any] | None = None) -> bool:
    """True if remote_id is a TrueForge harness instance."""
    return kind_of_instance(remote_id, config) == "trueforge"


def _instance_slug(remote_id: str, kind: str | None = None) -> str:
    """Uppercase env slug for a named instance: ``trueforge-2`` → ``2``,
    ``trueforge_prod`` → ``PROD``. Bare kinds get an empty slug."""
    raw = (remote_id or "").strip().lower()
    k = kind or kind_of_instance(raw)
    if k == raw:
        return ""
    tail = raw[len(k) + 1 :] if (raw.startswith(k) and len(raw) > len(k) and raw[len(k)] in ("-", "_")) else raw
    return re.sub(r"[^a-z0-9]+", "_", tail).strip("_").upper()
# Kinds that never appear until the user (or env) adds them.
OPT_IN_REMOTE_IDS: frozenset[str] = frozenset({"herdr", "anythingllm"})
REMOTE_KIND_LABELS: dict[str, str] = {
    "hermes": "Hermes",
    "anythingllm": "AnythingLLM",
    "omb": "OpenMousBot",
    "rakazo": "Rakazo",
    "herdr": "Herdr",
    "swarm": "Swarm",
    "trueforge": "TrueForge",
}
_KIND_ALIASES: dict[str, str] = {
    "openmausbot": "omb",
    "openmaus": "omb",
    "openmousbot": "omb",
    "rakoza": "rakazo",
    "open-swarm": "swarm",
    "openswarm": "swarm",
    "open_swarm": "swarm",
    "true_forge": "trueforge",
    "true-forge": "trueforge",
    "anything-llm": "anythingllm",
    "anything_llm": "anythingllm",
}

# REQ-11 default roster. ``swarm`` is in the catalog but is not auto-placed
# (do not auto-add this instance as its own remote).
_DEFAULT_PLACED: tuple[str, ...] = ("hermes", "omb", "rakazo")

# Team (REQ-11 vocabulary): agents that SEE and TALK to each other via
# openai-agents handoff / as_tool. This is NOT the /teams/ LLM-profile alias
# registry (DynamicTeamBlueprint). Remotes are Team *members*.
TEAM_VOCABULARY: dict[str, str] = {
    "team": (
        "A Team wires API agents, CLI agents, and remote agents "
        "(Hermes / OpenMousBot / Rakazo / Herdr / nested open-swarm) so they can see and "
        "talk to each other via openai-agents handoff or as_tool."
    ),
    "not_teams_page": (
        "The Django /teams/ JSON registry is LLM-profile aliases "
        "(DynamicTeamBlueprint) — not this Team. Prefer 'Profiles' for that surface."
    ),
}

_TOOL_NAMES: dict[str, str] = {
    "hermes": "consult_hermes",
    "anythingllm": "consult_anythingllm",
    "omb": "consult_omb",
    "rakazo": "consult_rakazo",
    "herdr": "consult_herdr",
    "swarm": "consult_swarm",
    "trueforge": "consult_trueforge",
}

# Verified operator LAN facts (not reachable from every cloud VM).
_DEFAULTS: dict[str, dict[str, Any]] = {
    "hermes": {
        "title": "Hermes Agent (dev-worker-gpu)",
        "host_label": "dev-worker-gpu",
        "base_url": "http://198.51.100.36:8642",
        "ui_url": "http://198.51.100.36:9119",
        "api_key": "${HERMES_API_KEY}",
        "health_path": "/health",
        "version_path": "/v1/models",
        "notes": (
            "Nous Hermes gateway on :8642 (GET /health, GET /v1/models, "
            "POST /v1/runs, GET /api/sessions, GET /api/jobs). Dashboard :9119 "
            "is operator chrome, not the operate API. Do not bounce Hermes "
            "to read config; do not delete SKILL.md on that box."
        ),
    },
    "omb": {
        "title": "OpenMousBot",
        "host_label": "Windows2",
        "base_url": "http://198.51.100.32:8802",
        "ui_url": "",
        "api_key": "${OMB_API_KEY}",
        "health_path": "/api/health",
        "version_path": "/api/health",
        "notes": (
            "OpenMousBot harness on :8802 (upstream default is :8799). "
            "GET /api/health, GET /api/bots, POST /api/bots, "
            "POST /api/bots/{id}/messages starts a turn (202). "
            "We talk HTTP only — no OpenMousBot source clone."
        ),
    },
    "rakazo": {
        "title": "Rakazo (Windows2)",
        "host_label": "Windows2",
        "base_url": "http://198.51.100.32:3100",
        "ui_url": "http://198.51.100.32:5173",
        "api_key": "${RAKAZO_API_KEY}",
        "cookie": "${RAKAZO_SESSION_COOKIE}",
        "health_path": "/health",
        "version_path": "/health",
        "notes": (
            "Rakazo API :3100, Vite UI :5173, tree C:\\rakazo. "
            "GET /health is public. bots.list / threads.send live under "
            "/rpc/* and require a Better Auth session (cookie or bearer). "
            "Health works without auth; operate fails honestly on 401."
        ),
    },
    "herdr": {
        "title": "Herdr",
        "host_label": "",
        "base_url": "",
        "ui_url": "",
        "api_key": "${HERDR_API_KEY}",
        "health_path": "/health",
        "version_path": "/health",
        "notes": (
            "Opt-in Herdr remote. SSH-shaped — not HTTP like OpenMousBot / "
            "Hermes / Rakazo. Local: talk to Herdr on this host (no SSH; "
            "localhost URL only when you choose that). Remote: SSH to the "
            "Herdr host, then herdr CLI there (agy / pi / grok). "
            "swarm-cli remotes set herdr --herdr-mode local | "
            "--herdr-mode ssh --ssh-host <host> --ssh-user <user> "
            "--ssh-identity-env HERDR_SSH_IDENTITY. No baked LAN host. "
            "Identity is an env-var name (path), never a private key."
        ),
    },
    "swarm": {
        "title": "Nested open-swarm",
        "host_label": "remote-swarm",
        "base_url": "http://127.0.0.1:9",
        "ui_url": "",
        "api_key": "${SWARM_REMOTE_API_KEY}",
        "health_path": "/health",
        "version_path": "/v1/models",
        "notes": (
            "Another open-swarm instance (own process, own local DB). "
            "GET /health, GET /v1/blueprints/ (agents), POST /v1/chat/completions/ "
            "(handoff). Auth is Bearer via remotes.swarm.api_key or "
            "SWARM_REMOTE_API_KEY — env var name only. Catalog default "
            "http://127.0.0.1:9 is an unreachable stub, not this server. "
            "v1 refuses a base URL that matches this process listen URL. "
            "Do not auto-add this instance as its own remote; a child is "
            "not required to nest the parent."
        ),
    },
    "anythingllm": {
        "title": "AnythingLLM",
        "host_label": "anythingllm",
        "base_url": "http://127.0.0.1:3001",
        "ui_url": "",
        "api_key": "${ANYTHINGLLM_API_KEY}",
        "health_path": "/api/v1/workspaces",
        "version_path": "/api/v1/workspaces",
        "notes": (
            "AnythingLLM document workspace (:3001, docker). API key from "
            "Settings → API keys; point ANYTHINGLLM_BASE_URL at your box. "
            "GET /api/v1/workspaces lists workspaces with their threads; each "
            "thread is a resumable session (resume key workspace:thread). "
            "POST /api/v1/workspace/<slug>/thread/<slug>/chat replies inside "
            "that thread; send requires a thread session id and never mints "
            "a new thread. Opt-in: not placed until + Add."
        ),
    },
    "trueforge": {
        "title": "TrueForge",
        "host_label": "trueforge",
        "base_url": "http://127.0.0.1:8791",
        "ui_url": "",
        "api_key": "${TRUEFORGE_API_KEY}",
        "health_path": "/healthz",
        "version_path": "/healthz",
        "notes": (
            "TrueForge agent server on :8791 (truefoundry/trueforge). "
            "GET /healthz, GET /api/v1/agents, "
            "POST /api/v1/sessions, POST /api/v1/sessions/{id}/turns, "
            "GET /api/v1/sessions/{id}/turns/{turn_id}, "
            "GET /api/v1/sessions/{id}/turns/{turn_id}/events. "
            "Auth is optional Bearer token via TRUEFORGE_API_KEY."
        ),
    },
}

_ENV_BASE = {
    "hermes": "HERMES_BASE_URL",
    "omb": "OMB_BASE_URL",
    "rakazo": "RAKAZO_BASE_URL",
    "herdr": "HERDR_BASE_URL",
    "swarm": "SWARM_REMOTE_BASE_URL",
    "trueforge": "TRUEFORGE_BASE_URL",
    "anythingllm": "ANYTHINGLLM_BASE_URL",
}
_ENV_KEY = {
    "hermes": "HERMES_API_KEY",
    "omb": "OMB_API_KEY",
    "rakazo": "RAKAZO_API_KEY",
    "herdr": "HERDR_API_KEY",
    "swarm": "SWARM_REMOTE_API_KEY",
    "trueforge": "TRUEFORGE_API_KEY",
    "anythingllm": "ANYTHINGLLM_API_KEY",
}
_ENV_UI = {"rakazo": "RAKAZO_UI_URL", "hermes": "HERMES_UI_URL"}
_ENV_COOKIE = {"rakazo": "RAKAZO_SESSION_COOKIE"}
_ENV_HERDR_SSH_HOST = "HERDR_SSH_HOST"
_ENV_HERDR_SSH_USER = "HERDR_SSH_USER"
_ENV_HERDR_SSH_PORT = "HERDR_SSH_PORT"
_ENV_HERDR_SSH_IDENTITY = "HERDR_SSH_IDENTITY"
_ENV_HERDR_SSH_AGENT = "HERDR_SSH_AGENT"

_UP = frozenset({200, 201, 202, 204})
_AUTH = frozenset({401, 403})
_FORBIDDEN_BASE_HINTS = ("fly.dev", "open-litellm", "openlitellm")

_DEFAULT_TIMEOUT_S = 3.0
_OPERATE_TIMEOUT_S = 8.0


class RemoteError(Exception):
    """Non-crash failure talking to a remote harness."""


@dataclass
class RemoteSpec:
    """Persisted + resolved connection for one remote harness."""

    id: str
    title: str
    host_label: str
    base_url: str
    ui_url: str = ""
    api_key: str = ""
    cookie: str = ""
    health_path: str = "/health"
    version_path: str = "/health"
    notes: str = ""
    source: str = "default"
    api_key_env: str = ""
    session_cookie_env: str = ""
    herdr_mode: str = ""
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_port: int = 22
    ssh_identity_env: str = ""
    ssh_agent: bool = True
    provenance: dict[str, Any] = field(default_factory=dict)
    kind: str = ""

    def origin(self) -> tuple[str, int]:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host, int(port)

    def public_dict(self) -> dict[str, Any]:
        """JSON-safe view with secrets redacted."""
        from swarm.core.remote_harness import capabilities_for

        kind = self.kind or kind_of_instance(self.id)
        is_instance = self.id != kind
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "host_label": self.host_label,
            "base_url": self.base_url,
            "ui_url": self.ui_url,
            "api_key_set": bool(self.api_key and not _is_unresolved_placeholder(self.api_key)),
            "cookie_set": bool(self.cookie and not _is_unresolved_placeholder(self.cookie)),
            "health_path": self.health_path,
            "version_path": self.version_path,
            "notes": self.notes,
            "kind": kind,
            "impl": kind,
            "instance": self.id if is_instance else "",
            "user_kind": "remote",
            "label": f"{kind_label(kind)} ({self.id})" if is_instance else kind_label(self.id),
            "source": self.source,
            "api_key_env": self.api_key_env,
            "session_cookie_env": self.session_cookie_env,
            "added": self.source in ("config", "env"),
            "provenance": dict(self.provenance),
            "capabilities": capabilities_for(kind).as_dict(),
            "member": {
                "kind": "remote",
                "talk": f"consult_{self.id.replace('-', '_')}" if is_instance else _TOOL_NAMES.get(kind, ""),
                "via": "as_tool",
                "place_in": "Team (handoff members — not /teams/ profile aliases)",
            },
        }
        if kind == "herdr":
            from swarm.herdr.remote import HOP_MODEL, resolve_herdr_mode

            mode = resolve_herdr_mode(self)
            payload["herdr_mode"] = mode
            payload["ssh_host"] = self.ssh_host
            payload["ssh_user"] = self.ssh_user
            payload["ssh_port"] = int(self.ssh_port or 22)
            payload["ssh_identity_env"] = self.ssh_identity_env
            payload["ssh_agent"] = bool(self.ssh_agent)
            payload["transport"] = "ssh" if mode == "ssh" else "local"
            payload["ssh_shaped"] = True
            payload["hop_model"] = HOP_MODEL
            if mode == "ssh" and self.ssh_host and self.ssh_user:
                port = f":{self.ssh_port}" if self.ssh_port and int(self.ssh_port) != 22 else ""
                payload["host_label"] = payload["host_label"] or f"{self.ssh_user}@{self.ssh_host}{port}"
            elif mode == "local":
                payload["host_label"] = payload["host_label"] or "local Herdr"
        return payload


@dataclass
class HealthResult:
    remote: str
    ok: bool
    state: str
    detail: str
    http_status: int | None = None
    version: Any = None
    latency_ms: int | None = None
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperateResult:
    remote: str
    op: str
    ok: bool
    detail: str
    http_status: int | None = None
    data: Any = None
    gap: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HttpResult:
    status: int | None
    body: Any = None
    text: str = ""
    error: str = ""
    url: str = ""
    latency_ms: int = 0
    headers: dict[str, str] = field(default_factory=dict)


def _is_unresolved_placeholder(value: str) -> bool:
    raw = (value or "").strip()
    return raw.startswith("${") and raw.endswith("}") and len(raw) > 3


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        expanded = os.path.expandvars(value)
        if _is_unresolved_placeholder(expanded):
            return ""
        return expanded
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _looks_like_forbidden_llm_proxy(url: str) -> bool:
    lowered = (url or "").lower()
    return any(hint in lowered for hint in _FORBIDDEN_BASE_HINTS)


def _normalize_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


def this_server_listen_port() -> int:
    """Port this process advertises (PORT / SWARM_PORT, default 8000)."""
    raw = os.environ.get("PORT") or os.environ.get("SWARM_PORT") or "8000"
    try:
        return int(raw)
    except ValueError:
        return 8000


def is_this_server_base_url(url: str) -> bool:
    """True when ``url`` is this server's own listen origin (loop-risk).

    v1 refuses adding a nested swarm whose base URL is this process. Explicit
    ``SWARM_LISTEN_URL`` wins; otherwise loopback (or HOST) + PORT matches.
    """
    normalized = _normalize_base_url(url)
    if not normalized:
        return False
    explicit = (os.environ.get("SWARM_LISTEN_URL") or "").strip()
    if explicit:
        other = _normalize_base_url(explicit)
        if other and _same_listen_origin(normalized, other):
            return True
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port != this_server_listen_port():
        return False
    bind_host = (os.environ.get("HOST") or "").strip().lower()
    if host in _LOOPBACK_HOSTS:
        return True
    if bind_host and host == bind_host:
        return True
    return False


def _same_listen_origin(left: str, right: str) -> bool:
    a = urlparse(_normalize_base_url(left))
    b = urlparse(_normalize_base_url(right))
    host_a = (a.hostname or "").lower()
    host_b = (b.hostname or "").lower()
    port_a = a.port or (443 if a.scheme == "https" else 80)
    port_b = b.port or (443 if b.scheme == "https" else 80)
    if port_a != port_b:
        return False
    if host_a == host_b:
        return True
    return host_a in _LOOPBACK_HOSTS and host_b in _LOOPBACK_HOSTS


def kind_label(remote_id: str) -> str:
    """UI kind label. OpenMousBot for ``omb`` — never the letters OMB."""
    rid = (remote_id or "").strip().lower()
    rid = _KIND_ALIASES.get(rid, rid)
    return REMOTE_KIND_LABELS.get(rid, rid)


def display_label(remote_id: str) -> str:
    """Alias of ``kind_label`` (REQ-62)."""
    return kind_label(remote_id)


def list_remote_kinds() -> list[dict[str, Any]]:
    """Kinds the user can add. Unused kinds do not appear as catalog rows.

    ``kind`` is the user-facing harness (always ``remote``). ``id`` / ``impl``
    is the implementation discriminator (REQ-203 / ADR-011).
    """
    from swarm.core.remote_harness import implementation_catalog

    catalog = implementation_catalog()
    if catalog:
        return catalog
    return [
        {
            "id": kid,
            "label": REMOTE_KIND_LABELS[kid],
            "kind": "remote",
            "impl": kid,
        }
        for kid in REMOTE_KIND_IDS
    ]


def remote_kind_catalog() -> list[dict[str, str]]:
    """Alias for ``list_remote_kinds`` (REQ-64 / Settings kind picker)."""
    return list_remote_kinds()


def kind_catalog() -> list[dict[str, str]]:
    """Alias of ``list_remote_kinds`` (REQ-62)."""
    return list_remote_kinds()


def _placeholder_env_name(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
        inner = raw[2:-1].strip()
        if inner and all(ch.isalnum() or ch == "_" for ch in inner):
            return inner
    return ""


def _as_env_name(value: str) -> str:
    raw = (value or "").strip()
    derived = _placeholder_env_name(raw)
    return derived or raw


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_ssh_port(value: Any, default: int = 22) -> int:
    if value in (None, ""):
        return default
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    if port < 1 or port > 65535:
        return default
    return port


def _opt_in_not_configured_message(remote_id: str) -> str:
    if remote_id == "herdr":
        from swarm.herdr.remote import not_configured_message

        return not_configured_message()
    return f"Remote '{remote_id}' is not configured"


# Shared marker so renderers (chat replies, health lines) can detect the
# never-added case and present it as a sentence instead of an op result.
NOT_ADDED_MARKER = "not added as a remote"


def _not_added_message(remote_id: str) -> str:
    """Actionable text when a catalog seat exists but the remote was never added.

    Non-opt-in remotes (hermes / omb / rakazo / swarm) carry LAN defaults, so
    ``load_remote`` succeeds while ``is_configured`` is False — the sidebar can
    show a seat (``remote:<id>``) that cannot be operated. The bare
    ``remote not added`` detail previously told the operator nothing about why
    or how to fix it (issue #129). The text contains ``NOT_ADDED_MARKER`` so
    renderers can drop the ``{remote} {op}: FAIL —`` prefix in chat replies.
    """
    rid = _require_kind_id(remote_id)
    label = kind_label(rid)
    env_base = _ENV_BASE.get(rid, "")
    env_key = _ENV_KEY.get(rid, "") or "API_KEY"
    key_hint = f" [--api-key-env {env_key}]" if env_key else ""
    env_hint = ""
    if env_base:
        env_hint = f", or set the {env_base} env var"
        if env_key and env_key != env_base:
            env_hint += f" (add {env_key} only if the endpoint requires a key)"
    return (
        f"{label} is {NOT_ADDED_MARKER} — the sidebar seat is a catalog "
        f"placeholder. Add it in Settings → Remotes or run "
        f"`swarm-cli remotes set {rid} --base-url <url>{key_hint}`"
        f"{env_hint}."
    )


def default_spec(remote_id: str) -> RemoteSpec:
    kind = _require_kind_id(remote_id)
    raw = dict(_DEFAULTS[kind])
    return RemoteSpec(id=remote_id, kind=kind, source="default", **raw)


def normalize_instance_id(remote_id: str) -> str:
    """Alias-normalized instance id: kinds stay kinds, instances keep their name."""
    raw = (remote_id or "").strip().lower()
    return _KIND_ALIASES.get(raw, raw)


def _require_kind_id(remote_id: str, config: dict[str, Any] | None = None) -> str:
    """Validate a remote id and return its **kind** (REQ-856).

    Accepts bare kinds (``trueforge``), aliases (``open-swarm``) and named
    instances (``trueforge-2``, ``trueforge_prod`` — returns ``trueforge``).
    Raises for unknown kinds so callers can reject bad ids as before.
    """
    kind = kind_of_instance(remote_id, config)
    if kind not in REMOTE_KIND_IDS:
        raise RemoteError(f"Unknown remote '{remote_id}'. Known: {', '.join(REMOTE_KIND_IDS)}")
    return kind


def _require_id(remote_id: str, config: dict[str, Any] | None = None) -> str:
    """Health/operate gate: accept bare kinds and named instances (REQ-856)."""
    return _require_kind_id(remote_id, config)


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    """Path we read/write remotes from. Prefers existing file, else XDG."""
    from swarm.core.config_loader import find_config_file
    from swarm.core.paths import get_user_config_dir_for_swarm

    if explicit:
        return Path(explicit).expanduser()
    found = find_config_file()
    if found:
        return found
    return get_user_config_dir_for_swarm() / "swarm_config.json"


def load_raw_config(config_path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    path = resolve_config_path(config_path)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, path
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("remotes: failed to read %s: %s", path, exc)
    return {}, path


def load_remote(remote_id: str, config: dict[str, Any] | None = None) -> RemoteSpec:
    """Defaults ← persisted remotes ← env bootstrap; force-env wins when set.

    Secrets (api_key / cookie) always resolve from env / ``${VAR}``.
    Non-secret URLs use ADR-002 hybrid precedence (#776): force-env >
    persisted file > env bootstrap > built-in default.
    """
    from swarm.core import config_ownership as ownership

    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    remotes_block = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    inst_id = (remote_id or "").strip().lower()
    inst_id = _KIND_ALIASES.get(inst_id, inst_id)

    block = remotes_block.get(inst_id)
    if not isinstance(block, dict):
        block = remotes_block.get(remote_id)
    if not isinstance(block, dict) and inst_id == "swarm":
        block = remotes_block.get("open-swarm")

    explicit_kind = ""
    if isinstance(block, dict):
        explicit_kind = str(block.get("kind") or "").strip().lower()
        explicit_kind = _KIND_ALIASES.get(explicit_kind, explicit_kind)

    kind = explicit_kind or kind_of_instance(inst_id, cfg)
    if kind not in REMOTE_KIND_IDS:
        raise RemoteError(f"Unknown remote '{remote_id}'. Known: {', '.join(REMOTE_KIND_IDS)}")

    if kind in OPT_IN_REMOTE_IDS and not is_configured(inst_id, cfg):
        raise RemoteError(_opt_in_not_configured_message(kind))

    spec = default_spec(kind)
    spec.id = inst_id
    spec.kind = kind
    if inst_id != kind:
        spec.title = f"{REMOTE_KIND_LABELS.get(kind, kind)} ({inst_id})"
        spec.host_label = inst_id

    persisted_base = ""
    persisted_ui = ""
    if isinstance(block, dict):
        spec.source = "config"
        for key in (
            "title",
            "host_label",
            "base_url",
            "ui_url",
            "api_key",
            "cookie",
            "health_path",
            "version_path",
            "notes",
            "api_key_env",
            "session_cookie_env",
            "herdr_mode",
            "ssh_host",
            "ssh_user",
            "ssh_identity_env",
        ):
            if key in block and block[key] is not None:
                setattr(spec, key, block[key])
        if "kind" in block and block["kind"]:
            spec.kind = str(block["kind"]).strip().lower()
        if "ssh_port" in block and block["ssh_port"] is not None:
            spec.ssh_port = _coerce_ssh_port(block["ssh_port"])
        if "ssh_agent" in block and block["ssh_agent"] is not None:
            spec.ssh_agent = _coerce_bool(block["ssh_agent"], default=True)
        persisted_base = str(block.get("base_url") or "").strip()
        persisted_ui = str(block.get("ui_url") or "").strip()

    inst_slug = _instance_slug(inst_id, kind)
    env_base_key = f"{kind.upper()}_{inst_slug}_BASE_URL" if inst_slug else (_ENV_BASE.get(kind) or "")
    kind_env_base_key = _ENV_BASE.get(kind) or ""
    env_base = os.environ.get(env_base_key, "").strip() if env_base_key else ""
    if not env_base and inst_slug and kind_env_base_key:
        env_base = os.environ.get(kind_env_base_key, "").strip()
    if env_base and (ownership.field_is_forced(env_base_key) or ownership.field_is_forced(kind_env_base_key) or not persisted_base):
        spec.base_url = env_base
        spec.source = "env"

    env_ui_key = _ENV_UI.get(kind) or ""
    env_ui = os.environ.get(env_ui_key, "").strip() if env_ui_key else ""
    if env_ui and (ownership.field_is_forced(env_ui_key) or not persisted_ui):
        spec.ui_url = env_ui

    # Secrets stay env-only: file may hold ${VAR}; live value comes from env.
    env_key_name = f"{kind.upper()}_{inst_slug}_API_KEY" if inst_slug else (_ENV_KEY.get(kind) or "")
    kind_env_key_name = _ENV_KEY.get(kind) or ""
    env_key = os.environ.get(env_key_name, "").strip() if env_key_name else ""
    if not env_key and inst_slug and kind_env_key_name:
        env_key = os.environ.get(kind_env_key_name, "").strip()
    if env_key:
        spec.api_key = env_key
    env_cookie = _ENV_COOKIE.get(kind)
    if env_cookie and os.environ.get(env_cookie, "").strip():
        spec.cookie = os.environ[env_cookie].strip()

    if not spec.api_key_env:
        spec.api_key_env = (
            _placeholder_env_name(str(spec.api_key or ""))
            or env_key_name
            or kind_env_key_name
            or ""
        )
    if not spec.session_cookie_env:
        spec.session_cookie_env = _placeholder_env_name(str(spec.cookie or ""))

    if kind == "herdr":
        env_ssh_host = os.environ.get(_ENV_HERDR_SSH_HOST, "").strip()
        if env_ssh_host and not str(spec.ssh_host or "").strip():
            spec.ssh_host = env_ssh_host
            spec.source = "env"
        env_ssh_user = os.environ.get(_ENV_HERDR_SSH_USER, "").strip()
        if env_ssh_user and not str(spec.ssh_user or "").strip():
            spec.ssh_user = env_ssh_user
        env_ssh_port = os.environ.get(_ENV_HERDR_SSH_PORT, "").strip()
        if env_ssh_port:
            spec.ssh_port = _coerce_ssh_port(env_ssh_port, default=spec.ssh_port)
        if not spec.ssh_identity_env:
            spec.ssh_identity_env = _ENV_HERDR_SSH_IDENTITY if os.environ.get(_ENV_HERDR_SSH_IDENTITY, "").strip() else ""
        if os.environ.get(_ENV_HERDR_SSH_AGENT, "").strip():
            spec.ssh_agent = _coerce_bool(os.environ.get(_ENV_HERDR_SSH_AGENT), default=spec.ssh_agent)
        spec.herdr_mode = str(spec.herdr_mode or "").strip().lower()
        spec.ssh_host = str(spec.ssh_host or "").strip()
        spec.ssh_user = str(spec.ssh_user or "").strip()
        spec.ssh_identity_env = _as_env_name(str(spec.ssh_identity_env or ""))
        spec.ssh_port = _coerce_ssh_port(spec.ssh_port)

    spec.base_url = _normalize_base_url(_expand(spec.base_url))
    spec.ui_url = _normalize_base_url(_expand(spec.ui_url)) if spec.ui_url else ""
    spec.api_key = str(_expand(spec.api_key) or "")
    spec.cookie = str(_expand(spec.cookie) or "")
    spec.health_path = spec.health_path or "/health"
    spec.version_path = spec.version_path or spec.health_path
    if not spec.health_path.startswith("/"):
        spec.health_path = "/" + spec.health_path
    if not spec.version_path.startswith("/"):
        spec.version_path = "/" + spec.version_path
    spec.provenance = {
        "base_url": ownership.badge_for(
            env_var=env_base_key,
            persisted=persisted_base,
            secret=False,
        ),
        "ui_url": ownership.badge_for(
            env_var=env_ui_key,
            persisted=persisted_ui,
            secret=False,
        ),
        "api_key": ownership.badge_for(
            env_var=spec.api_key_env or kind_env_key_name,
            persisted=f"${{{spec.api_key_env}}}" if spec.api_key_env else "",
            secret=True,
        ),
    }
    return spec


def load_all_remotes(config: dict[str, Any] | None = None) -> dict[str, RemoteSpec]:
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    out: dict[str, RemoteSpec] = {}
    for rid in REMOTE_IDS:
        if rid in OPT_IN_REMOTE_IDS and not is_configured(rid, cfg):
            continue
        out[rid] = load_remote(rid, cfg)
    for cid in configured_remote_ids(cfg):
        if cid not in out:
            try:
                spec = load_remote(cid, cfg)
                out[cid] = spec
            except RemoteError:
                continue
    return out


def configured_remote_ids(config: dict[str, Any] | None = None) -> list[str]:
    """Remote ids the user (or env) has actually added. Defaults do not count.

    Includes named instances (``trueforge_prod``, ``trueforge-2``) found in the
    ``remotes`` block whose kind resolves (REQ-856). Bare-kind ids are emitted once each.
    """
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    remotes = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    ids: list[str] = []
    for key in remotes:
        entry = remotes.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("archived") is True:
            continue
        raw = str(key).strip().lower()
        k = str(entry.get("kind") or "").strip().lower()
        k = _KIND_ALIASES.get(k, k)
        if not k or k not in REMOTE_KIND_IDS:
            try:
                k = kind_of_instance(raw, cfg)
                if k not in REMOTE_KIND_IDS:
                    continue
            except Exception:
                continue
        emitted = k if (raw == k or raw in _KIND_ALIASES) else str(key)
        if emitted not in ids:
            ids.append(emitted)
    for rid, env_name in _ENV_BASE.items():
        if os.environ.get(env_name, "").strip() and rid not in ids:
            persisted = remotes.get(rid)
            if isinstance(persisted, dict) and persisted.get("archived") is True:
                continue
            ids.append(rid)
    if os.environ.get(_ENV_HERDR_SSH_HOST, "").strip() and "herdr" not in ids:
        persisted = remotes.get("herdr")
        if not (isinstance(persisted, dict) and persisted.get("archived") is True):
            ids.append("herdr")
    order = {kid: index for index, kid in enumerate(REMOTE_KIND_IDS)}
    ids.sort(key=lambda item: order.get(kind_of_instance(item, cfg), len(order)))
    return ids


def list_configured_remotes(config: dict[str, Any] | None = None) -> list[RemoteSpec]:
    """Opt-in catalog: empty until the user adds a remote (REQ-59)."""
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    return [load_remote(rid, cfg) for rid in configured_remote_ids(cfg)]


def load_configured_remotes(config: dict[str, Any] | None = None) -> dict[str, RemoteSpec]:
    """Configured remotes as an id→spec map. Empty until + add (REQ-62)."""
    return {spec.id: spec for spec in list_configured_remotes(config)}


def load_added_remotes(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, RemoteSpec]:
    """CLI/Settings alias of ``load_configured_remotes``."""
    cfg = config if isinstance(config, dict) else load_raw_config(config_path)[0]
    return load_configured_remotes(cfg)


def added_remote_ids(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> list[str]:
    cfg = config if isinstance(config, dict) else load_raw_config(config_path)[0]
    return configured_remote_ids(cfg)


def is_configured(remote_id: str, config: dict[str, Any] | None = None) -> bool:
    try:
        _require_kind_id(remote_id, config)
    except RemoteError:
        return False
    c_ids = configured_remote_ids(config)
    normalized = normalize_instance_id(remote_id)
    return normalized in c_ids or remote_id in c_ids or (str(remote_id).strip().lower() in [c.lower() for c in c_ids])


def is_remote_added(remote_id: str, config: dict[str, Any] | None = None) -> bool:
    return is_configured(remote_id, config)


def load_placed_members(config: dict[str, Any] | None = None) -> list[str]:
    """Remote ids currently placed in the handoff Team (not /teams/ aliases).

    Missing ``agent_team.members`` means the REQ-11 roster (hermes / omb /
    rakazo) is placed. ``swarm`` stays catalog-only until explicitly placed —
    do not auto-add this instance as its own remote. An explicit empty list
    is an empty Team.
    """
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    block = cfg.get("agent_team") if isinstance(cfg.get("agent_team"), dict) else {}
    if "members" not in block:
        return list(_DEFAULT_PLACED)
    raw = block.get("members") or []
    if not isinstance(raw, list):
        return list(_DEFAULT_PLACED)
    out: list[str] = []
    for item in raw:
        try:
            _require_id(str(item), cfg)
        except RemoteError:
            continue
        inst_id = normalize_instance_id(str(item))
        if inst_id not in out:
            out.append(inst_id)
    return out


def list_team_members(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Remote harnesses as Team members (handoff / as_tool), not profile aliases."""
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    placed = set(load_placed_members(cfg))
    members = []
    for spec in load_all_remotes(cfg).values():
        pub = spec.public_dict()
        members.append(
            {
                "id": spec.id,
                "kind": "remote",
                "title": spec.title,
                "base_url": spec.base_url,
                "talk": pub["member"]["talk"],
                "via": "as_tool",
                "placed": spec.id in placed,
            }
        )
    return members


def agent_team_public(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Handoff Team roster (not /v1/teams/ Profiles aliases)."""
    cfg = config if isinstance(config, dict) else load_raw_config(config_path)[0]
    return {
        "object": "agent_team",
        "vocabulary": TEAM_VOCABULARY,
        "members": load_placed_members(cfg),
        "team_members": list_team_members(cfg),
        "not": "/v1/teams/ LLM-profile aliases (Profiles)",
    }


def persist_agent_team(
    members: list[str],
    *,
    config_path: str | Path | None = None,
) -> tuple[list[str], Path]:
    """Persist which remotes sit in the handoff Team (``agent_team.members``)."""
    resolved: list[str] = []
    for item in members:
        rid = _require_id(str(item))
        if rid not in resolved:
            resolved.append(rid)
    cfg, path = load_raw_config(config_path)
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    team = cfg.get("agent_team") if isinstance(cfg.get("agent_team"), dict) else {}
    team = dict(team)
    team["members"] = resolved
    cfg["agent_team"] = team
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Persisted agent_team.members=%s to %s", resolved, path)
    return resolved, path


def place_team_member(remote_id: str, *, config_path: str | Path | None = None) -> tuple[list[str], Path]:
    rid = _require_id(remote_id)
    cfg, path = load_raw_config(config_path)
    current = load_placed_members(cfg)
    if rid not in current:
        current.append(rid)
    return persist_agent_team(current, config_path=path)


def unplace_team_member(remote_id: str, *, config_path: str | Path | None = None) -> tuple[list[str], Path]:
    rid = _require_id(remote_id)
    cfg, path = load_raw_config(config_path)
    current = [m for m in load_placed_members(cfg) if m != rid]
    return persist_agent_team(current, config_path=path)


def _apply_herdr_persist(
    entry: dict[str, Any],
    *,
    herdr_mode: str | None,
    ssh_host: str | None,
    ssh_user: str | None,
    ssh_port: int | str | None,
    ssh_identity_env: str | None,
    ssh_agent: bool | str | None,
) -> None:
    """Persist local vs SSH Herdr fields. Never store a private key."""
    from swarm.herdr.remote import (
        HERDR_HTTP_REMOTE_REFUSED,
        HERDR_MODE_LOCAL,
        HERDR_MODE_SSH,
        is_localhost_base,
    )
    from swarm.herdr.ssh import looks_like_key_material

    if herdr_mode is not None:
        mode = str(herdr_mode).strip().lower()
        if mode and mode not in (HERDR_MODE_LOCAL, HERDR_MODE_SSH):
            raise RemoteError("herdr_mode must be 'local' or 'ssh'.")
        if mode:
            entry["herdr_mode"] = mode
    if ssh_host is not None:
        entry["ssh_host"] = str(ssh_host).strip()
    if ssh_user is not None:
        entry["ssh_user"] = str(ssh_user).strip()
    if ssh_port is not None:
        entry["ssh_port"] = _coerce_ssh_port(ssh_port)
    if ssh_identity_env is not None:
        raw_ident = str(ssh_identity_env)
        if looks_like_key_material(raw_ident):
            raise RemoteError(
                "Refusing to persist a private key. ssh_identity_env must be "
                "an env-var name whose value is a key *path*."
            )
        env_name = _as_env_name(raw_ident)
        if env_name:
            from swarm.core import config_ownership as ownership

            if not ownership.looks_like_env_name(env_name) and not ownership.is_placeholder(raw_ident):
                raise RemoteError(
                    "ssh_identity_env must be an env-var name or ${ENV}, not a key path or token."
                )
        entry["ssh_identity_env"] = env_name
    if ssh_agent is not None:
        entry["ssh_agent"] = _coerce_bool(ssh_agent, default=True)

    mode = str(entry.get("herdr_mode") or "").strip().lower()
    host = str(entry.get("ssh_host") or "").strip()
    user = str(entry.get("ssh_user") or "").strip()
    base = str(entry.get("base_url") or "").strip()
    if not mode:
        if host or user:
            mode = HERDR_MODE_SSH
            entry["herdr_mode"] = mode
        elif (base and is_localhost_base(base)) or (not base and not host and not user):
            mode = HERDR_MODE_LOCAL
            entry["herdr_mode"] = mode

    if mode == HERDR_MODE_SSH and (not host or not user):
        raise RemoteError(
            "Remote Herdr SSH needs ssh_host + ssh_user "
            "(optional ssh_identity_env / ssh_agent). "
            "This is not an HTTP remote. Refusing to guess a host."
        )
    if base and not is_localhost_base(base) and mode != HERDR_MODE_LOCAL and not (host and user):
        raise RemoteError(HERDR_HTTP_REMOTE_REFUSED)


def persist_remote(
    remote_id: str,
    *,
    kind: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    ui_url: str | None = None,
    cookie: str | None = None,
    session_cookie_env: str | None = None,
    herdr_mode: str | None = None,
    ssh_host: str | None = None,
    ssh_user: str | None = None,
    ssh_port: int | str | None = None,
    ssh_identity_env: str | None = None,
    ssh_agent: bool | str | None = None,
    config_path: str | Path | None = None,
) -> tuple[RemoteSpec, Path]:
    """Merge fields into ``remotes.<id>`` and write swarm_config.json."""
    cfg, path = load_raw_config(config_path)
    remotes = cfg.setdefault("remotes", {})
    if not isinstance(remotes, dict):
        remotes = {}
        cfg["remotes"] = remotes

    inst_id = normalize_instance_id(remote_id)
    resolved_kind = (kind or "").strip().lower()
    resolved_kind = _KIND_ALIASES.get(resolved_kind, resolved_kind)
    if not resolved_kind:
        resolved_kind = kind_of_instance(inst_id, cfg)
    if resolved_kind not in REMOTE_KIND_IDS:
        raise RemoteError(f"Unknown remote '{remote_id}'. Known: {', '.join(REMOTE_KIND_IDS)}")

    rid = inst_id
    entry = remotes.get(rid) if isinstance(remotes.get(rid), dict) else {}
    entry = dict(entry)
    entry["kind"] = resolved_kind
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    from swarm.core import config_ownership as ownership

    env_base_key = _ENV_BASE.get(resolved_kind) or ""
    if base_url is not None and env_base_key and ownership.field_is_forced(env_base_key):
        raise RemoteError(
            f"base_url is forced by env {env_base_key} (read-only). "
            f"Unset {ownership.FORCE_ENV_VAR} to persist Settings."
        )
    if base_url is not None:
        normalized = _normalize_base_url(base_url)
        if _looks_like_forbidden_llm_proxy(normalized):
            raise RemoteError(
                "Refusing to persist a Fly open-litellm URL as a harness remote. "
                "Hermes/OpenMousBot/Rakazo are LAN harnesses; LAN LLM is http://198.51.100.30:8000/v1."
            )
        if resolved_kind == "swarm" and is_this_server_base_url(normalized):
            raise RemoteError(
                "Refusing to nest this server as its own remote "
                f"(base_url {normalized} matches this process listen URL). "
                "Point remotes.swarm at another open-swarm process. "
                "A child is not required to nest the parent."
            )
        entry["base_url"] = normalized

    if api_key_env is not None:
        env_name = _placeholder_env_name(api_key_env) or api_key_env.strip()
        if env_name and not ownership.looks_like_env_name(env_name) and not ownership.is_placeholder(api_key_env):
            raise RemoteError("api_key_env must be an env-var name or ${ENV} placeholder, not a token.")
        entry["api_key_env"] = env_name
        if env_name:
            entry["api_key"] = f"${{{env_name}}}"
    elif api_key is not None:
        derived = _placeholder_env_name(api_key)
        if derived:
            entry["api_key"] = f"${{{derived}}}"
            entry["api_key_env"] = derived
        elif ownership.looks_like_env_name(api_key):
            entry["api_key_env"] = api_key.strip()
            entry["api_key"] = f"${{{api_key.strip()}}}"
        elif (api_key or "").strip() == "":
            entry["api_key"] = ""
            entry["api_key_env"] = ""
        else:
            raise RemoteError(
                "Refusing to persist a plaintext API key. Use api_key_env or ${ENV}."
            )
    if ui_url is not None:
        entry["ui_url"] = _normalize_base_url(ui_url) if ui_url else ""
    if session_cookie_env is not None:
        env_name = _as_env_name(session_cookie_env)
        if env_name and not ownership.looks_like_env_name(env_name) and not ownership.is_placeholder(session_cookie_env):
            raise RemoteError("session_cookie_env must be an env-var name, not a cookie value.")
        if env_name:
            entry["session_cookie_env"] = env_name
            entry["cookie"] = f"${{{env_name}}}"
        else:
            entry["session_cookie_env"] = ""
            entry["cookie"] = ""
    elif cookie is not None:
        derived = _placeholder_env_name(str(cookie))
        if derived:
            entry["cookie"] = f"${{{derived}}}"
            entry["session_cookie_env"] = derived
        elif ownership.looks_like_env_name(cookie):
            entry["session_cookie_env"] = str(cookie).strip()
            entry["cookie"] = f"${{{str(cookie).strip()}}}"
        elif str(cookie).strip() == "":
            entry["cookie"] = ""
            entry["session_cookie_env"] = ""
        else:
            raise RemoteError(
                "Refusing to persist a plaintext cookie. Use session_cookie_env or ${ENV}."
            )
    herdr_kwargs = {
        "herdr_mode": herdr_mode,
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "ssh_identity_env": ssh_identity_env,
        "ssh_agent": ssh_agent,
    }
    if resolved_kind != "herdr" and any(value is not None for value in herdr_kwargs.values()):
        raise RemoteError(
            "ssh_host / ssh_user / herdr_mode apply only to kind=herdr. "
            "Hermes / OpenMousBot / Rakazo / swarm stay HTTP remotes."
        )
    if resolved_kind == "herdr":
        _apply_herdr_persist(
            entry,
            herdr_mode=herdr_mode,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_identity_env=ssh_identity_env,
            ssh_agent=ssh_agent,
        )
    remotes[rid] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Persisted remotes.%s to %s", rid, path)
    return load_remote(rid, cfg), path


def delete_remote(
    remote_id: str,
    *,
    config_path: str | Path | None = None,
) -> tuple[str, Path]:
    """Remove ``remotes.<id>`` so the kind disappears from Settings / dropdowns."""
    inst_id = normalize_instance_id(remote_id)
    cfg, path = load_raw_config(config_path)
    remotes = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    rid = inst_id if inst_id in remotes else remote_id
    if rid not in remotes:
        raise RemoteError(f"Remote '{rid}' is not configured")
    remotes = dict(remotes)
    remotes.pop(rid, None)
    cfg["remotes"] = remotes
    team = cfg.get("agent_team") if isinstance(cfg.get("agent_team"), dict) else None
    if isinstance(team, dict) and isinstance(team.get("members"), list):
        team = dict(team)
        team["members"] = [item for item in team["members"] if str(item).strip().lower() != rid]
        cfg["agent_team"] = team
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Deleted remotes.%s from %s", rid, path)
    return rid, path


def add_remote(
    remote_id: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    ui_url: str | None = None,
    cookie: str | None = None,
    session_cookie_env: str | None = None,
    config_path: str | Path | None = None,
) -> tuple[RemoteSpec, Path]:
    """Add or update a remote (REQ-62). Stores api-key-env as ``${ENV}`` only."""
    return persist_remote(
        remote_id,
        base_url=base_url,
        api_key=api_key,
        api_key_env=api_key_env,
        ui_url=ui_url,
        cookie=cookie,
        session_cookie_env=session_cookie_env,
        config_path=config_path,
    )


def remove_remote(
    remote_id: str,
    *,
    config_path: str | Path | None = None,
) -> tuple[str, Path]:
    """Alias of ``delete_remote`` (REQ-62)."""
    return delete_remote(remote_id, config_path=config_path)


def _auth_headers(spec: RemoteSpec) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "open-swarm-remotes/1"}
    if spec.api_key:
        headers["Authorization"] = f"Bearer {spec.api_key}"
        headers["X-API-Key"] = spec.api_key
    if spec.cookie:
        headers["Cookie"] = spec.cookie
    return headers


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> HttpResult:
    """One-shot HTTP. Never raises for network/HTTP; never retries."""
    started = time.monotonic()
    req_headers = dict(headers or {})
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            parsed: Any = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            return HttpResult(
                status=getattr(resp, "status", None) or resp.getcode(),
                body=parsed,
                text=text,
                url=url,
                latency_ms=round((time.monotonic() - started) * 1000),
                headers={k.lower(): v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        return HttpResult(
            status=exc.code,
            body=parsed,
            text=text,
            error=f"http {exc.code}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return HttpResult(
            status=None,
            error=f"{type(exc).__name__}: {exc}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
        )


def _tcp_probe(host: str, port: int, timeout: float) -> float | None:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.monotonic() - started) * 1000)
    except OSError:
        return None


def _extract_version(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("version", "app", "status", "runtime", "pid", "data", "ok"):
            if key in payload:
                if key == "data" and isinstance(payload[key], list):
                    return {"models": [m.get("id") for m in payload[key] if isinstance(m, dict)][:8]}
                return {key: payload[key]}
        return {k: payload[k] for k in list(payload)[:6]}
    if payload is not None:
        return payload
    return None


def _herdr_cli_health(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:  # noqa: ARG001
    """Health via local herdr or SSH hop (never a guessed host)."""
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        payload = client.workspace_list()
    except SSHNotConfiguredError as exc:
        return HealthResult(remote="herdr", ok=False, state="UNKNOWN", detail=str(exc))
    except Exception as exc:
        return HealthResult(
            remote="herdr",
            ok=False,
            state="DOWN",
            detail=f"Herdr {mode} health failed: {exc}",
        )
    detail = (
        f"ssh {spec.ssh_user}@{spec.ssh_host} · herdr workspace list"
        if mode == "ssh"
        else "local herdr workspace list (no SSH)"
    )
    return HealthResult(
        remote="herdr",
        ok=True,
        state="UP",
        detail=detail,
        version=_extract_version(payload),
        url=spec.ssh_host if mode == "ssh" else "local",
    )


def _herdr_health(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> HealthResult | None:
    """SSH or local-CLI health. None means fall through to localhost HTTP."""
    from swarm.herdr.remote import uses_local_http_health

    if uses_local_http_health(spec):
        return None
    return _herdr_cli_health(spec, timeout, config)


def check_health(remote_id: str, *, config: dict[str, Any] | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> HealthResult:
    """Honest health/version. One attempt. Never raises."""
    try:
        spec = load_remote(remote_id, config)
    except RemoteError as exc:
        return HealthResult(remote=remote_id, ok=False, state="UNKNOWN", detail=str(exc))

    if not is_configured(spec.id, config):
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail=_not_added_message(spec.id))

    if spec.kind == "herdr" or kind_of_instance(spec.id, config) == "herdr":
        herdr_health = _herdr_health(spec, timeout, config)
        if herdr_health is not None:
            return herdr_health

    if not spec.base_url:
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail="base_url is empty")
    if _looks_like_forbidden_llm_proxy(spec.base_url):
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="UNKNOWN",
            detail="base_url looks like Fly open-litellm — refuse to probe as a harness remote",
            url=spec.base_url,
        )

    host, port = spec.origin()
    if not host or not port:
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail="unparseable base_url", url=spec.base_url)

    tcp_ms = _tcp_probe(host, port, timeout)
    if tcp_ms is None:
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="DOWN",
            detail=f"tcp {host}:{port} refused/timed out",
            url=spec.base_url,
        )

    health_url = f"{spec.base_url}{spec.health_path}"
    result = http_json("GET", health_url, headers=_auth_headers(spec), timeout=timeout)
    version = _extract_version(result.body)

    if result.status in _UP:
        # Cheap extra version probe when health has no useful body.
        if version is None and spec.version_path != spec.health_path:
            extra = http_json(
                "GET",
                f"{spec.base_url}{spec.version_path}",
                headers=_auth_headers(spec),
                timeout=timeout,
            )
            if extra.status in _UP:
                version = _extract_version(extra.body) or extra.body
            elif extra.status in _AUTH:
                version = {"auth_required": True, "path": spec.version_path}
        return HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=f"tcp {tcp_ms}ms · http {result.status} on {spec.health_path}",
            http_status=result.status,
            version=version,
            latency_ms=result.latency_ms,
            url=health_url,
        )
    if result.status in _AUTH:
        return HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=f"tcp {tcp_ms}ms · http {result.status} (auth required — endpoint is alive)",
            http_status=result.status,
            version=version or {"auth_required": True},
            latency_ms=result.latency_ms,
            url=health_url,
        )
    if result.status is not None:
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="DEGRADED",
            detail=f"tcp {tcp_ms}ms · http {result.status} on {spec.health_path}",
            http_status=result.status,
            version=version,
            latency_ms=result.latency_ms,
            url=health_url,
        )
    return HealthResult(
        remote=spec.id,
        ok=False,
        state="DEGRADED",
        detail=f"tcp {tcp_ms}ms · http probe failed: {result.error or 'no response'}",
        latency_ms=result.latency_ms,
        url=health_url,
    )


def check_all_health(*, config: dict[str, Any] | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> list[HealthResult]:
    return [check_health(rid, config=config, timeout=timeout) for rid in REMOTE_IDS]


def _hermes_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    headers = _auth_headers(spec)
    models = http_json("GET", f"{spec.base_url}/v1/models", headers=headers, timeout=timeout)
    sessions = http_json("GET", f"{spec.base_url}/api/sessions", headers=headers, timeout=timeout)
    jobs = http_json("GET", f"{spec.base_url}/api/jobs", headers=headers, timeout=timeout)
    data: dict[str, Any] = {"models": models.body, "sessions": sessions.body, "jobs": jobs.body}
    statuses = [models.status, sessions.status, jobs.status]
    if any(s in _UP for s in statuses):
        return OperateResult(
            remote="hermes",
            op="list",
            ok=True,
            detail="listed Hermes models/sessions/jobs (missing slices stay null)",
            http_status=next((s for s in statuses if s in _UP), None),
            data=data,
        )
    if any(s in _AUTH for s in statuses):
        return OperateResult(
            remote="hermes",
            op="list",
            ok=False,
            detail="Hermes list endpoints require API_SERVER_KEY (Bearer). Set remotes.hermes.api_key or HERMES_API_KEY.",
            http_status=401,
            data=data,
        )
    return OperateResult(
        remote="hermes",
        op="list",
        ok=False,
        detail=models.error or sessions.error or jobs.error or "Hermes list failed",
        http_status=models.status,
        data=data,
    )


def _hermes_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote="hermes", op="send", ok=False, detail="prompt is required")
    headers = _auth_headers(spec)
    body: dict[str, Any] = {"input": prompt}
    if session_id:
        body["session_id"] = session_id
    result = http_json(
        "POST",
        f"{spec.base_url}/v1/runs",
        headers=headers,
        body=body,
        timeout=timeout,
    )
    if result.status in _UP or result.status == 202:
        return OperateResult(
            remote="hermes",
            op="send",
            ok=True,
            detail="started Hermes run via POST /v1/runs",
            http_status=result.status,
            data=result.body or result.text,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail="Hermes POST /v1/runs requires Bearer API_SERVER_KEY",
            http_status=result.status,
            data=result.body,
        )
    return OperateResult(
        remote="hermes",
        op="send",
        ok=False,
        detail=result.error or f"Hermes send failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _omb_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 10.0)
    result = http_json("GET", f"{base_url}/api/bots", headers=_auth_headers(spec), timeout=timeout_s)
    if result.status in _UP:
        bots = None
        if isinstance(result.body, dict):
            bots = result.body.get("bots") or result.body.get("agents") or result.body.get("data")
        elif isinstance(result.body, list):
            bots = result.body
        count = len(bots) if isinstance(bots, list) else (1 if bots else 0)
        return OperateResult(
            remote="omb",
            op="list",
            ok=True,
            detail=f"OpenMousBot listed {count} bot(s) via GET /api/bots",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="omb",
            op="list",
            ok=False,
            detail="OpenMousBot /api/bots requires auth. Set remotes.omb.api_key or OMB_API_KEY.",
            http_status=result.status,
            data=result.body,
        )
    return OperateResult(
        remote="omb",
        op="list",
        ok=False,
        detail=result.error or f"OpenMousBot list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _omb_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote="omb", op="send", ok=False, detail="prompt is required")
    bot_id = (target or "").strip()
    headers = _auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 10.0)
    if not bot_id:
        listed = _omb_list(spec, timeout_s)
        bots = []
        if listed.ok and isinstance(listed.data, dict):
            bots = listed.data.get("bots") or listed.data.get("agents") or []
        elif listed.ok and isinstance(listed.data, list):
            bots = listed.data
        if isinstance(bots, list) and bots:
            first = bots[0] if isinstance(bots[0], dict) else {}
            bot_id = str(first.get("id") or "")
        if not bot_id:
            created = http_json("POST", f"{base_url}/api/bots", headers=headers, body={}, timeout=timeout_s)
            if created.status in _UP and isinstance(created.body, dict):
                bot = created.body.get("bot") or {}
                bot_id = str(bot.get("id") or "")
            if not bot_id:
                return OperateResult(
                    remote="omb",
                    op="send",
                    ok=False,
                    detail="No OpenMousBot bot id given and none could be listed/created",
                    http_status=created.status if "created" in locals() else listed.http_status,
                    data={"list": listed.data},
                )
    result = http_json(
        "POST",
        f"{base_url}/api/bots/{bot_id}/messages",
        headers=headers,
        body={"text": prompt},
        timeout=timeout_s,
    )
    if result.status in _UP or result.status == 202:
        return OperateResult(
            remote="omb",
            op="send",
            ok=True,
            detail=f"started OpenMousBot turn via POST /api/bots/{bot_id}/messages",
            http_status=result.status,
            data={"bot_id": bot_id, "response": result.body or result.text},
        )
    return OperateResult(
        remote="omb",
        op="send",
        ok=False,
        detail=result.error or f"OpenMousBot send failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _rakazo_rpc(spec: RemoteSpec, path: str, payload: dict[str, Any], timeout: float) -> HttpResult:
    url = f"{spec.base_url}{path}"
    headers = _auth_headers(spec)
    # oRPC envelope used by the mobile probe and Hono RPCHandler.
    return http_json("POST", url, headers=headers, body={"json": payload}, timeout=timeout)


def _rakazo_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    result = _rakazo_rpc(spec, "/rpc/bots/list", {}, timeout)
    if result.status in _UP:
        bots = result.body.get("json") if isinstance(result.body, dict) else result.body
        count = len(bots) if isinstance(bots, list) else "?"
        return OperateResult(
            remote="rakazo",
            op="list",
            ok=True,
            detail=f"Rakazo listed {count} bot(s) via POST /rpc/bots/list",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="rakazo",
            op="list",
            ok=False,
            detail=(
                "Rakazo /rpc/bots/list requires a Better Auth session. "
                "Health (GET /health) is public; operate is not. "
                "Set remotes.rakazo.cookie (or RAKAZO_SESSION_COOKIE) from a signed-in UI session, "
                "or a bearer if this deploy added API-key auth."
            ),
            http_status=result.status,
            data=result.body,
            gap="rakazo_rpc_requires_better_auth_session",
        )
    return OperateResult(
        remote="rakazo",
        op="list",
        ok=False,
        detail=result.error or f"Rakazo list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
        gap="rakazo_rpc_unusable" if result.status is None else "",
    )


def _rakazo_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote="rakazo", op="send", ok=False, detail="prompt is required")
    bot_id = (target or "").strip()
    if not bot_id:
        listed = _rakazo_list(spec, timeout)
        if not listed.ok:
            return OperateResult(
                remote="rakazo",
                op="send",
                ok=False,
                detail="Need a Rakazo botId (or a working list). " + listed.detail,
                http_status=listed.http_status,
                data=listed.data,
                gap=listed.gap,
            )
        bots = listed.data.get("json") if isinstance(listed.data, dict) else listed.data
        if isinstance(bots, list) and bots and isinstance(bots[0], dict):
            bot_id = str(bots[0].get("id") or "")
        if not bot_id:
            return OperateResult(
                remote="rakazo",
                op="send",
                ok=False,
                detail="Rakazo list returned no bot id; pass target=botId",
                data=listed.data,
            )
    result = _rakazo_rpc(
        spec,
        "/rpc/threads/send",
        {"botId": bot_id, "text": prompt},
        timeout,
    )
    if result.status in _UP:
        return OperateResult(
            remote="rakazo",
            op="send",
            ok=True,
            detail=f"sent Rakazo thread via POST /rpc/threads/send (bot {bot_id})",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="rakazo",
            op="send",
            ok=False,
            detail="Rakazo /rpc/threads/send requires Better Auth. Health still works without it.",
            http_status=result.status,
            data=result.body,
            gap="rakazo_rpc_requires_better_auth_session",
        )
    return OperateResult(
        remote="rakazo",
        op="send",
        ok=False,
        detail=result.error or f"Rakazo send failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _swarm_try_get(spec: RemoteSpec, paths: tuple[str, ...], timeout: float) -> HttpResult:
    last = HttpResult(status=None, error="no paths")
    for path in paths:
        last = http_json("GET", f"{spec.base_url}{path}", headers=_auth_headers(spec), timeout=timeout)
        if last.status in _UP or last.status in _AUTH:
            last.headers = {**(last.headers or {}), "x-swarm-path": path}
            return last
    return last


def _swarm_agents_from_body(body: Any) -> list[Any]:
    if isinstance(body, dict):
        items = body.get("data")
        if isinstance(items, list):
            return items
    if isinstance(body, list):
        return body
    return []


def _swarm_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    """List child agents (blueprints / models) on a nested open-swarm."""
    result = _swarm_try_get(
        spec,
        ("/v1/blueprints/", "/v1/blueprints", "/v1/models/", "/v1/models"),
        timeout,
    )
    path = (result.headers or {}).get("x-swarm-path", "/v1/blueprints/")
    if result.status in _UP:
        agents = _swarm_agents_from_body(result.body)
        return OperateResult(
            remote="swarm",
            op="list",
            ok=True,
            detail=f"nested swarm listed {len(agents)} agent(s) via GET {path}",
            http_status=result.status,
            data={"agents": agents, "path": path, "raw": result.body},
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="swarm",
            op="list",
            ok=False,
            detail=(
                "Nested swarm list requires Bearer auth. "
                "Set remotes.swarm.api_key or SWARM_REMOTE_API_KEY (env var name only)."
            ),
            http_status=result.status,
            data=result.body,
        )
    return OperateResult(
        remote="swarm",
        op="list",
        ok=False,
        detail=result.error or f"nested swarm list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _swarm_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    """Send one message to a child swarm via POST /v1/chat/completions/."""
    if not prompt.strip():
        return OperateResult(remote="swarm", op="send", ok=False, detail="prompt is required")
    model = (target or "").strip()
    headers = _auth_headers(spec)
    listed: OperateResult | None = None
    if not model:
        listed = _swarm_list(spec, timeout)
        if listed.ok and isinstance(listed.data, dict):
            agents = listed.data.get("agents") or []
            if isinstance(agents, list) and agents and isinstance(agents[0], dict):
                model = str(agents[0].get("id") or "")
        if not model:
            return OperateResult(
                remote="swarm",
                op="send",
                ok=False,
                detail="Need a child blueprint id (target) or a working list.",
                http_status=listed.http_status,
                data=listed.data,
            )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    last = HttpResult(status=None, error="no paths")
    for path in ("/v1/chat/completions/", "/v1/chat/completions"):
        last = http_json(
            "POST",
            f"{spec.base_url}{path}",
            headers=headers,
            body=payload,
            timeout=timeout,
        )
        if last.status in _UP:
            return OperateResult(
                remote="swarm",
                op="send",
                ok=True,
                detail=f"sent nested swarm turn via POST {path} model={model}",
                http_status=last.status,
                data={"model": model, "response": last.body or last.text},
            )
        if last.status in _AUTH:
            return OperateResult(
                remote="swarm",
                op="send",
                ok=False,
                detail=(
                    "Nested swarm send requires Bearer auth. "
                    "Set remotes.swarm.api_key or SWARM_REMOTE_API_KEY (env var name only)."
                ),
                http_status=last.status,
                data=last.body,
            )
    return OperateResult(
        remote="swarm",
        op="send",
        ok=False,
        detail=last.error or f"nested swarm send failed (http {last.status})",
        http_status=last.status,
        data=last.body or last.text,
    )


def _trueforge_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 10.0)
    result = http_json(
        "GET",
        f"{base_url}/api/v1/agents",
        headers=_auth_headers(spec),
        timeout=timeout_s,
    )
    if result.status in _UP:
        agents = None
        if isinstance(result.body, dict):
            agents = result.body.get("agents") or result.body.get("data")
        elif isinstance(result.body, list):
            agents = result.body
        count = len(agents) if isinstance(agents, list) else (1 if agents else 0)
        return OperateResult(
            remote=spec.id,
            op="list",
            ok=True,
            detail=f"TrueForge listed {count} agent(s) via GET /api/v1/agents",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote=spec.id,
            op="list",
            ok=False,
            detail=f"TrueForge /api/v1/agents requires auth. Set remotes.{spec.id}.api_key or {spec.api_key_env or 'TRUEFORGE_API_KEY'}.",
            http_status=result.status,
            data=result.body,
        )
    return OperateResult(
        remote=spec.id,
        op="list",
        ok=False,
        detail=result.error or f"TrueForge list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _trueforge_send(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    timeout: float = _OPERATE_TIMEOUT_S,
    *,
    session_id: str | None = None,
) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote=spec.id, op="send", ok=False, detail="prompt is required")
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = float(timeout or _OPERATE_TIMEOUT_S)
    start_time = time.monotonic()
    deadline = start_time + timeout_s

    # 1. Session id: reuse or create via POST /api/v1/sessions
    sess_id = (session_id or "").strip()
    if not sess_id:
        agent_name = (target or "").strip() or "orchestrator"
        sess_resp = http_json(
            "POST",
            f"{base_url}/api/v1/sessions",
            headers=_auth_headers(spec),
            body={"agent": {"name": agent_name}, "metadata": {}},
            timeout=min(5.0, timeout_s),
        )
        if sess_resp.status in _AUTH:
            return OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail=f"TrueForge POST /api/v1/sessions requires auth. Set remotes.{spec.id}.api_key or {spec.api_key_env or 'TRUEFORGE_API_KEY'}.",
                http_status=sess_resp.status,
                data=sess_resp.body,
            )
        if sess_resp.status not in _UP and sess_resp.status != 201:
            return OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail=sess_resp.error or f"TrueForge session create failed (http {sess_resp.status})",
                http_status=sess_resp.status,
                data=sess_resp.body or sess_resp.text,
            )
        body = sess_resp.body if isinstance(sess_resp.body, dict) else {}
        sess_id = str(
            (body.get("data") if isinstance(body.get("data"), dict) else {}).get("id")
            or body.get("id")
            or ""
        )
        if not sess_id:
            return OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail="TrueForge did not return a session id",
                http_status=sess_resp.status,
                data=sess_resp.body,
            )

    # 2. POST turn: POST /api/v1/sessions/{session_id}/turns
    remaining = max(1.0, deadline - time.monotonic())
    turn_resp = http_json(
        "POST",
        f"{base_url}/api/v1/sessions/{sess_id}/turns",
        headers=_auth_headers(spec),
        body={
            "input": [{"type": "user.message", "content": prompt}],
            "stream": False,
        },
        timeout=min(5.0, remaining),
    )
    if turn_resp.status in _AUTH:
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge POST /turns requires auth. Set remotes.{spec.id}.api_key or {spec.api_key_env or 'TRUEFORGE_API_KEY'}.",
            http_status=turn_resp.status,
            data=turn_resp.body,
        )
    if turn_resp.status not in _UP and turn_resp.status not in (201, 202):
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=turn_resp.error or f"TrueForge turn create failed (http {turn_resp.status})",
            http_status=turn_resp.status,
            data=turn_resp.body or turn_resp.text,
        )
    tbody = turn_resp.body if isinstance(turn_resp.body, dict) else {}
    turn_id = str(
        (tbody.get("data") if isinstance(tbody.get("data"), dict) else {}).get("id")
        or tbody.get("id")
        or ""
    )
    if not turn_id:
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail="TrueForge did not return a turn id",
            http_status=turn_resp.status,
            data=turn_resp.body,
        )

    # 3. Poll turn: GET /api/v1/sessions/{session_id}/turns/{turn_id}
    turn_data: dict[str, Any] = {}
    last_state = ""
    while time.monotonic() < deadline:
        poll_resp = http_json(
            "GET",
            f"{base_url}/api/v1/sessions/{sess_id}/turns/{turn_id}",
            headers=_auth_headers(spec),
            timeout=min(3.0, max(1.0, deadline - time.monotonic())),
        )
        if poll_resp.status in _AUTH:
            return OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail="TrueForge turn poll requires auth.",
                http_status=poll_resp.status,
                data=poll_resp.body,
            )
        if poll_resp.status in _UP:
            turn_data = (
                poll_resp.body.get("data", {})
                if isinstance(poll_resp.body, dict) and isinstance(poll_resp.body.get("data"), dict)
                else (poll_resp.body if isinstance(poll_resp.body, dict) else {})
            )
            last_state = str(turn_data.get("state") or "").strip().lower()
            if last_state in ("done", "completed", "finished", "success"):
                break
            if last_state in ("error", "failed", "cancelled", "canceled"):
                err_msg = (
                    turn_data.get("error")
                    or turn_data.get("message")
                    or f"TrueForge turn {turn_id} ended with state '{last_state}'"
                )
                return OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=str(err_msg),
                    http_status=poll_resp.status,
                    data=turn_data,
                )
        time.sleep(0.1)

    if last_state not in ("done", "completed", "finished", "success"):
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge turn {turn_id} timed out after {timeout_s:.1f}s (state: {last_state or 'unknown'})",
            data=turn_data,
        )

    # 4. Fetch events: GET /api/v1/sessions/{session_id}/turns/{turn_id}/events
    events_resp = http_json(
        "GET",
        f"{base_url}/api/v1/sessions/{sess_id}/turns/{turn_id}/events",
        headers=_auth_headers(spec),
        timeout=min(5.0, max(1.0, deadline - time.monotonic())),
    )
    events_data = events_resp.body
    events_list: list[Any] = []
    if isinstance(events_data, dict):
        events_list = events_data.get("data") or events_data.get("events") or []
    elif isinstance(events_data, list):
        events_list = events_data

    reply_text = ""
    for event in reversed(events_list):
        if isinstance(event, dict):
            etype = str(event.get("type") or "").lower()
            if etype in ("model.message", "assistant.message", "model_message", "message"):
                content = event.get("content")
                if isinstance(content, str) and content.strip():
                    reply_text = content.strip()
                    break
                elif isinstance(content, list):
                    parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("text")
                    ]
                    if parts:
                        reply_text = "".join(parts).strip()
                        break

    if not reply_text:
        reply_text = str(turn_data.get("output") or turn_data.get("result") or "")

    return OperateResult(
        remote=spec.id,
        op="send",
        ok=True,
        detail=reply_text or "TrueForge turn completed",
        http_status=200,
        data={
            "session_id": sess_id,
            "turn_id": turn_id,
            "turn": turn_data,
            "events": events_data,
        },
    )


def _trueforge_routines(spec: RemoteSpec, timeout: float = _OPERATE_TIMEOUT_S) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    if not base_url:
        return OperateResult(remote=spec.id, op="routines", ok=False, detail="base_url is empty")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 15.0)
    start_time = time.monotonic()
    deadline = start_time + timeout_s

    headers = _auth_headers(spec)
    result = http_json(
        "GET",
        f"{base_url}/api/v1/schedules?limit=25",
        headers=headers,
        timeout=min(5.0, timeout_s),
    )
    if result.status in _AUTH:
        return OperateResult(
            remote=spec.id,
            op="routines",
            ok=False,
            detail=f"TrueForge /api/v1/schedules requires auth. Set remotes.{spec.id}.api_key or {spec.api_key_env or 'TRUEFORGE_API_KEY'}.",
            http_status=result.status,
            data={"routines": []},
        )
    if result.status not in _UP:
        return OperateResult(
            remote=spec.id,
            op="routines",
            ok=False,
            detail=result.error or f"TrueForge schedules failed (http {result.status})",
            http_status=result.status,
            data={"routines": []},
        )

    schedules_data: list[Any] = []
    if isinstance(result.body, dict):
        schedules_data = (
            result.body.get("data")
            or result.body.get("schedules")
            or []
        )
    elif isinstance(result.body, list):
        schedules_data = result.body

    routines: list[dict[str, Any]] = []
    for schedule in schedules_data:
        if not isinstance(schedule, dict):
            continue
        schedule_id = schedule.get("id")
        manifest = schedule.get("manifest") if isinstance(schedule.get("manifest"), dict) else {}

        last_run = None
        if schedule_id and time.monotonic() < deadline:
            remaining = max(0.5, deadline - time.monotonic())
            runs_resp = http_json(
                "GET",
                f"{base_url}/api/v1/schedules/{schedule_id}/runs?limit=1",
                headers=headers,
                timeout=min(3.0, remaining),
            )
            if runs_resp.status in _UP:
                runs_list: list[Any] = []
                if isinstance(runs_resp.body, dict):
                    runs_list = runs_resp.body.get("data") or runs_resp.body.get("runs") or []
                elif isinstance(runs_resp.body, list):
                    runs_list = runs_resp.body
                if runs_list and isinstance(runs_list[0], dict):
                    lr = runs_list[0]
                    last_run = {
                        "id": lr.get("id"),
                        "name": lr.get("name"),
                        "scheduled_for": lr.get("scheduled_for"),
                        "status": lr.get("status"),
                    }

        routines.append({
            "id": schedule.get("id"),
            "name": schedule.get("name") or "",
            "agent": schedule.get("agent_name") or schedule.get("agent") or "",
            "cron": manifest.get("cron") or "",
            "timezone": manifest.get("timezone") or "",
            "task": manifest.get("task") or "",
            "status": manifest.get("status") or schedule.get("status") or "active",
            "created_at": schedule.get("created_at"),
            "last_run": last_run,
        })

    return OperateResult(
        remote=spec.id,
        op="routines",
        ok=True,
        detail=f"TrueForge listed {len(routines)} routine(s)",
        http_status=result.status,
        data={"routines": routines},
    )


def _herdr_list(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import (
        LIST_PATH,
        members_from_http_list,
        resolve_herdr_mode,
        uses_local_http_health,
    )
    from swarm.herdr.ssh import SSHNotConfiguredError

    if uses_local_http_health(spec):
        result = http_json(
            "GET",
            f"{spec.base_url}{LIST_PATH}",
            headers=_auth_headers(spec),
            timeout=timeout,
        )
        if result.status in _UP:
            members = members_from_http_list(result.body or {}, remote=spec.base_url)
            return OperateResult(
                remote="herdr",
                op="list",
                ok=True,
                detail=f"Herdr listed {len(members)} member(s) via GET {LIST_PATH}",
                http_status=result.status,
                data={"members": members, "raw": result.body},
            )
        if result.status in _AUTH:
            return OperateResult(
                remote="herdr",
                op="list",
                ok=False,
                detail="Herdr GET /agents requires auth. Set remotes.herdr.api_key or HERDR_API_KEY.",
                http_status=result.status,
                data=result.body,
            )
        return OperateResult(
            remote="herdr",
            op="list",
            ok=False,
            detail=result.error or f"Herdr list failed (http {result.status})",
            http_status=result.status,
            data=result.body or result.text,
        )

    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        members = client.discover_members()
    except SSHNotConfiguredError as exc:
        return OperateResult(remote="herdr", op="list", ok=False, detail=str(exc))
    except Exception as exc:
        return OperateResult(remote="herdr", op="list", ok=False, detail=f"Herdr list failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return OperateResult(
        remote="herdr",
        op="list",
        ok=True,
        detail=f"Herdr listed {len(members)} member(s) via {hop}",
        data={"members": members},
    )


def _herdr_send(spec: RemoteSpec, prompt: str, target: str, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
    from swarm.herdr.client import HerdrBlockedError, HerdrClient, extract_prompt_type
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    if not prompt.strip():
        return OperateResult(remote="herdr", op="send", ok=False, detail="prompt is required")
    if not (target or "").strip():
        return OperateResult(
            remote="herdr",
            op="send",
            ok=False,
            detail="target is required (Herdr pane / CLI id, e.g. w3:p1 or grok)",
        )
    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        payload = client.agent_prompt(target.strip(), prompt)
    except SSHNotConfiguredError as exc:
        return OperateResult(remote="herdr", op="send", ok=False, detail=str(exc))
    except HerdrBlockedError as exc:
        return OperateResult(remote="herdr", op="send", ok=False, detail=str(exc), data={"target": target})
    except Exception as exc:
        return OperateResult(remote="herdr", op="send", ok=False, detail=f"Herdr send failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return OperateResult(
        remote="herdr",
        op="send",
        ok=True,
        detail=f"Herdr prompted {target} via {hop} (type={extract_prompt_type(payload) or 'ok'})",
        data={"target": target, "response": payload, "transport": mode},
    )


def _herdr_interrogate(spec: RemoteSpec, target: str, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
    """Inspect one CLI/pane Herdr manages (agent get) over local or SSH hop."""
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    if not (target or "").strip():
        return OperateResult(
            remote="herdr",
            op="interrogate",
            ok=False,
            detail="target is required to interrogate a CLI Herdr manages (agy / pi / grok / pane id)",
        )
    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        payload = client.agent_get(target.strip())
    except SSHNotConfiguredError as exc:
        return OperateResult(remote="herdr", op="interrogate", ok=False, detail=str(exc))
    except Exception as exc:
        return OperateResult(remote="herdr", op="interrogate", ok=False, detail=f"Herdr interrogate failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return OperateResult(
        remote="herdr",
        op="interrogate",
        ok=True,
        detail=f"Herdr interrogated {target} via {hop}",
        data={"target": target, "agent": payload, "transport": mode},
    )


def _anythingllm_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    """List AnythingLLM workspace threads as sessions (id = workspace:thread).

    GET /api/v1/workspaces returns each workspace with its ``threads`` array
    (``slug`` + ``name``). We treat every thread as a resumable session; the
    workspace slug is the namespace so ids stay unique and unguessable.
    """
    from swarm.core.remote_harness import remote_session_from_dict

    headers = _auth_headers(spec)
    result = http_json(
        "GET",
        f"{spec.base_url}/api/v1/workspaces",
        headers=headers,
        timeout=timeout,
    )
    workspaces: Any
    body = result.body
    if isinstance(body, dict):
        workspaces = body.get("workspaces") or body.get("data") or []
    elif isinstance(body, list):
        workspaces = body
    else:
        workspaces = []
    normalized: list[dict[str, Any]] = []
    for ws in workspaces:
        if not isinstance(ws, dict):
            continue
        ws_slug = str(ws.get("slug") or ws.get("id") or "").strip()
        ws_name = str(ws.get("name") or ws_slug or "workspace").strip()
        threads = ws.get("threads")
        if not isinstance(threads, list):
            continue
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            thread_slug = str(thread.get("slug") or thread.get("id") or "").strip()
            if not ws_slug or not thread_slug:
                continue
            session = remote_session_from_dict(
                {
                    "id": f"{ws_slug}:{thread_slug}",
                    "title": str(thread.get("name") or f"{ws_name} thread").strip(),
                    "snippet": "",
                    "source": "anythingllm",
                    "updated_at": str(thread.get("updatedAt") or thread.get("updated_at") or "").strip(),
                    "channel": ws_name[:128],
                    "thread_ts": thread_slug[:64],
                }
            )
            if session is not None:
                normalized.append(session.as_dict())
    data: dict[str, Any] = {"sessions": normalized, "source": "anythingllm"}
    if result.status in _UP:
        return OperateResult(
            remote="anythingllm",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} AnythingLLM thread(s) across {len(workspaces)} workspace(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="anythingllm",
            op="list",
            ok=False,
            detail=(
                "AnythingLLM /api/v1/workspaces requires a valid API key. "
                "Set remotes.anythingllm.api_key or ANYTHINGLLM_API_KEY "
                "(Settings → API keys on the AnythingLLM box)."
            ),
            http_status=result.status,
            data=data,
        )
    return OperateResult(
        remote="anythingllm",
        op="list",
        ok=False,
        detail=result.error or f"AnythingLLM list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _anythingllm_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> OperateResult:
    """Send into an existing AnythingLLM thread (never mints a new one).

    ``session_id`` is ``workspace:thread`` — the thread slug comes from the
    session list. POST /api/v1/workspace/<ws>/thread/<thread>/chat replies
    inside that thread; AnythingLLM returns ``textResponse`` (or an ``error``
    string on upstream failures, e.g. a misconfigured chat model).
    """
    from dataclasses import replace

    sid = (session_id or target or "").strip()
    ws_slug, _, thread_slug = sid.partition(":")
    if not ws_slug or not thread_slug:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=(
                "Pick an AnythingLLM thread. Open Swarm does not mint new "
                "threads. Pass session_id as workspace:thread "
                "(list the remote to see available threads)."
            ),
            gap="anythingllm_thread_required",
        )
    if not prompt.strip():
        return OperateResult(remote="anythingllm", op="send", ok=False, detail="prompt is required")
    url = f"{spec.base_url}/api/v1/workspace/{ws_slug}/thread/{thread_slug}/chat"
    result = http_json(
        "POST",
        url,
        headers=_auth_headers(spec),
        body={"message": prompt, "mode": "chat"},
        timeout=timeout,
    )
    payload = result.body if isinstance(result.body, dict) else {}
    text_response = str(payload.get("textResponse") or payload.get("text") or "").strip()
    gateway_error = str(payload.get("error") or "").strip()
    if result.status in _UP and text_response:
        sources = payload.get("sources")
        data: dict[str, Any] = {
            "response": text_response,
            "thread": f"{ws_slug}:{thread_slug}",
        }
        if isinstance(sources, list) and sources:
            data["sources"] = sources[:10]
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=True,
            detail=f"AnythingLLM replied in thread {thread_slug}",
            http_status=result.status,
            data=data,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail="AnythingLLM chat requires a valid API key (Settings → API keys).",
            http_status=result.status,
            data=result.body,
        )
    if gateway_error:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=f"AnythingLLM upstream error: {gateway_error}",
            http_status=result.status,
            data=result.body,
        )
    return OperateResult(
        remote="anythingllm",
        op="send",
        ok=False,
        detail=result.error or f"AnythingLLM send failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def operate(
    remote_id: str,
    op: str,
    *,
    prompt: str = "",
    target: str = "",
    config: dict[str, Any] | None = None,
    timeout: float = _OPERATE_TIMEOUT_S,
    session_id: str | None = None,
) -> OperateResult:
    """List or send a job. Never raises; never crash-loops.

    ``session_id`` is a stored remote thread (#369-style). REQ-65 on-mode
    agents drop it so each task starts a new remote job.
    """
    try:
        from swarm.core.session_policy import resume_remote_session_id

        resume_id = resume_remote_session_id(remote_id, session_id)
        spec = load_remote(remote_id, config)
        rid = spec.id
        rkind = spec.kind or kind_of_instance(rid, config)
        action = (op or "list").strip().lower()
        if action in ("start", "job", "run"):
            action = "send"
        if action == "interrogate" and rkind != "herdr":
            return OperateResult(
                remote=rid,
                op=action,
                ok=False,
                detail="interrogate is Herdr-only (SSH or local CLI). HTTP remotes use list / send.",
            )
        from swarm.core.remote_harness import COMPUTER_OPS, computer_operate_stub

        if action in COMPUTER_OPS:
            return computer_operate_stub(rid, action)
        if action not in ("list", "send", "interrogate", "routines", "schedules"):
            return OperateResult(remote=rid, op=action, ok=False, detail=f"Unknown op '{op}'. Use list, send, or routines.")
        if not is_configured(rid, config):
            return OperateResult(remote=rid, op=action, ok=False, detail=_not_added_message(rid))
        if action in ("routines", "schedules"):
            if rkind == "trueforge" or spec.kind == "trueforge" or is_trueforge_remote(rid, config):
                return _trueforge_routines(spec, timeout)
            from swarm.core.remote_harness import unsupported_routines

            return unsupported_routines(rid)
        if rkind == "herdr":
            if action == "list":
                return _herdr_list(spec, timeout, config)
            if action == "interrogate":
                return _herdr_interrogate(spec, target, timeout, config)
            return _herdr_send(spec, prompt, target, timeout, config)
        if not spec.base_url:
            return OperateResult(remote=rid, op=action, ok=False, detail="base_url is empty")
        if _looks_like_forbidden_llm_proxy(spec.base_url):
            return OperateResult(
                remote=rid,
                op=action,
                ok=False,
                detail="Refusing to operate against a Fly open-litellm URL",
            )
        if rkind == "hermes":
            return _hermes_list(spec, timeout) if action == "list" else _hermes_send(
                spec, prompt, timeout, session_id=resume_id
            )
        if rkind == "anythingllm":
            return _anythingllm_list(spec, timeout) if action == "list" else _anythingllm_send(
                spec, prompt, timeout, session_id=resume_id
            )
        if rkind == "omb":
            return _omb_list(spec, timeout) if action == "list" else _omb_send(spec, prompt, target, timeout)
        if rkind == "rakazo":
            return _rakazo_list(spec, timeout) if action == "list" else _rakazo_send(spec, prompt, target, timeout)
        if rkind == "swarm":
            return _swarm_list(spec, timeout) if action == "list" else _swarm_send(spec, prompt, target, timeout)
        if rkind == "trueforge" or spec.kind == "trueforge" or is_trueforge_remote(rid, config):
            return _trueforge_list(spec, timeout) if action == "list" else _trueforge_send(
                spec, prompt, target, timeout, session_id=resume_id
            )
        return OperateResult(
            remote=rid,
            op=action,
            ok=False,
            detail=f"{kind_label(rid)} list/send is not implemented here",
        )
    except RemoteError as exc:  # opt-in not configured / bad id: surface as-is
        logger.warning("remotes.operate failed for %s %s: %s", remote_id, op, exc)
        return OperateResult(
            remote=str(remote_id),
            op=str(op),
            ok=False,
            detail=str(exc),
        )
    except Exception as exc:  # never let operate take down the process
        logger.warning("remotes.operate failed for %s %s: %s", remote_id, op, exc)
        return OperateResult(
            remote=str(remote_id),
            op=str(op),
            ok=False,
            detail=f"operate error: {exc}",
        )


def _bind_health(impl_id: str):
    def _health(spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:  # noqa: ARG001
        target_id = spec.id if hasattr(spec, "id") and spec.id else impl_id
        return check_health(target_id, config=config, timeout=timeout)

    return _health


def _bind_http_list(fn):
    def _list(spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
        return fn(spec, timeout)

    return _list


def _hermes_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",  # noqa: ARG001 — RemoteHarness.send signature
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _hermes_send(spec, prompt, timeout, session_id=session_id)


def _anythingllm_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _anythingllm_send(spec, prompt, timeout, session_id=session_id, target=target)


def _omb_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _omb_send(spec, prompt, target, timeout)


def _rakazo_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _rakazo_send(spec, prompt, target, timeout)


def _swarm_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _swarm_send(spec, prompt, target, timeout)


def _trueforge_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _trueforge_send(spec, prompt, target=target, timeout=timeout, session_id=session_id)


def _trueforge_routines_bound(
    spec: RemoteSpec,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
) -> OperateResult:
    return _trueforge_routines(spec, timeout=timeout)


def _herdr_list_bound(
    spec: RemoteSpec,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
) -> OperateResult:
    return _herdr_list(spec, timeout, config)


def _herdr_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _herdr_send(spec, prompt, target, timeout, config)


def _herdr_operate_bound(
    spec: RemoteSpec,
    op: str,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
    prompt: str = "",
    target: str = "",
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    if op == "interrogate":
        return _herdr_interrogate(spec, target, timeout, config)
    if op == "list":
        return _herdr_list(spec, timeout, config)
    return _herdr_send(spec, prompt, target, timeout, config)


def _install_remote_harnesses() -> None:
    """Map existing remotes.py adapters onto :class:`RemoteHarness` (REQ-203)."""
    from swarm.core.remote_harness import (
        BoundRemoteHarness,
        capabilities_for,
        register_harness,
    )

    register_harness(
        BoundRemoteHarness(
            impl_id="hermes",
            label="Hermes",
            capabilities=capabilities_for("hermes"),
            health_fn=_bind_health("hermes"),
            list_fn=_bind_http_list(_hermes_list),
            send_fn=_hermes_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="omb",
            label="OpenMousBot",
            capabilities=capabilities_for("omb"),
            health_fn=_bind_health("omb"),
            list_fn=_bind_http_list(_omb_list),
            send_fn=_omb_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="rakazo",
            label="Rakazo",
            capabilities=capabilities_for("rakazo"),
            health_fn=_bind_health("rakazo"),
            list_fn=_bind_http_list(_rakazo_list),
            send_fn=_rakazo_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="herdr",
            label="Herdr",
            capabilities=capabilities_for("herdr"),
            health_fn=_bind_health("herdr"),
            list_fn=_herdr_list_bound,
            send_fn=_herdr_send_bound,
            operate_fn=_herdr_operate_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="swarm",
            label="Swarm",
            capabilities=capabilities_for("swarm"),
            health_fn=_bind_health("swarm"),
            list_fn=_bind_http_list(_swarm_list),
            send_fn=_swarm_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="anythingllm",
            label="AnythingLLM",
            capabilities=capabilities_for("anythingllm"),
            health_fn=_bind_health("anythingllm"),
            list_fn=_bind_http_list(_anythingllm_list),
            send_fn=_anythingllm_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="trueforge",
            label="TrueForge",
            capabilities=capabilities_for("trueforge"),
            health_fn=_bind_health("trueforge"),
            list_fn=_bind_http_list(_trueforge_list),
            send_fn=_trueforge_send_bound,
            routines_fn=_trueforge_routines_bound,
        )
    )


_install_remote_harnesses()
