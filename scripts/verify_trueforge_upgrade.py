#!/usr/bin/env python3
"""#1307 verification harness for the TrueForge instance upgrade/rebuild.

Runs the issue's checklist against the configured TrueForge instances and
prints a PASS/FAIL/SKIP table so a partial upgrade is diagnosable. Read-only:
never writes remote config, never mints a session (the send check always
resumes an existing session id), and never prints secrets — only payload key
names, counts, and statuses.

Usage:
    DJANGO_DEBUG=true .venv/bin/python scripts/verify_trueforge_upgrade.py
    ... --instance trueforge --instance trueforge-2 --send-timeout 20
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from swarm.core import remotes as remotes_core  # noqa: E402
from swarm.utils.dotenv_load import load_swarm_dotenv  # noqa: E402

DEFAULT_INSTANCES = ("trueforge", "trueforge-2")
SEND_PROMPT = "Reply with exactly OK"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

LIST_MARKER_KEYS = ("rows_are", "resume_key", "sessions")
GLOBAL_CHECKS = (
    "sample: required_actions",
    "sample: turn_state",
    "django: chat_persist_views import",
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization|api[_-]?key|bearer|token|cookie)\b\s*[=:]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"),
)


@dataclass
class Result:
    check: str
    status: str
    detail: str = ""


@dataclass
class SendObservation:
    result: Result
    live_turn: dict[str, Any] | None = None
    live_events: list[Any] = field(default_factory=list)
    awaiting_input: bool = False


def _scrub(text: Any) -> str:
    """Mask anything that looks like a credential before it reaches stdout."""
    out = str(text or "")
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("<redacted>", out)
    return out.replace("\n", " ").strip()


def _norm_state(turn_data: dict[str, Any] | None) -> str:
    try:
        return str(remotes_core._trueforge_turn_state(turn_data) or "")
    except Exception:
        return ""


def check_health(
    instance: str,
    *,
    config: dict[str, Any] | None = None,
    timeout: float = 3.0,
    health_fn: Callable[..., Any] | None = None,
) -> Result:
    """1. check_health(instance) — UP/DOWN, never raised, bounded by ``timeout``."""
    check = f"{instance}: health"
    fn = health_fn or remotes_core.check_health
    try:
        health = fn(instance, config=config, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — a probe crash is a FAIL, not a traceback
        return Result(check, FAIL, f"probe raised {type(exc).__name__}: {_scrub(exc)}")
    if health is None:
        return Result(check, FAIL, "probe returned no result")
    state = str(getattr(health, "state", "") or "UNKNOWN").upper()
    detail = _scrub(getattr(health, "detail", ""))
    version = getattr(health, "version", None)
    version_note = ""
    if isinstance(version, dict) and version:
        version_note = f" · version_keys={sorted(version)}"
    if bool(getattr(health, "ok", False)) and state == "UP":
        return Result(check, PASS, f"UP — {detail}{version_note}")
    if state == "DOWN":
        return Result(check, FAIL, f"offline — DOWN — {detail}{version_note}")
    return Result(check, FAIL, f"{state} — {detail}{version_note}")


def _raw_probe(
    instance: str,
    *,
    spec: Any = None,
    timeout: float = 5.0,
    http_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Independently GET /api/v1/agents + /api/v1/sessions and report shapes.

    Key names and counts only — never response values, never auth headers.
    """
    fn = http_fn or remotes_core.http_json
    spec = spec if spec is not None else remotes_core.load_remote(instance)
    base = (spec.base_url or "").rstrip("/")
    headers = remotes_core._auth_headers(spec)
    probe: dict[str, Any] = {"instance": instance, "errors": []}
    for label, path in (("agents", "/api/v1/agents"), ("sessions", "/api/v1/sessions")):
        try:
            resp = fn("GET", f"{base}{path}", headers=headers, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 — probe failure is data
            probe[f"{label}_status"] = None
            probe[f"{label}_rows"] = None
            probe[f"{label}_keys"] = []
            probe[f"{label}_row_keys"] = []
            probe["errors"].append(f"{label}: {type(exc).__name__}: {_scrub(exc)}")
            continue
        status = getattr(resp, "status", None)
        body = getattr(resp, "body", None)
        if isinstance(body, dict):
            body_keys = sorted(body)
            rows = body.get("data")
            if not isinstance(rows, list):
                rows = body.get(label)
            if not isinstance(rows, list):
                rows = body.get("sessions") if label == "sessions" else body.get("agents")
        elif isinstance(body, list):
            body_keys = ["<list>"]
            rows = body
        else:
            body_keys = []
            rows = []
        probe[f"{label}_status"] = status
        probe[f"{label}_keys"] = body_keys
        probe[f"{label}_rows"] = len(rows) if isinstance(rows, list) else None
        probe[f"{label}_row_keys"] = (
            sorted(rows[0]) if rows and isinstance(rows[0], dict) else []
        )
    return probe


def check_list(
    instance: str,
    *,
    config: dict[str, Any] | None = None,
    timeout: float = 5.0,
    operate_fn: Callable[..., Any] | None = None,
    probe_fn: Callable[..., Any] | None = None,
    spec: Any = None,
) -> tuple[Result, list[dict[str, Any]]]:
    """2. operate(instance, 'list') — sessions count + payload/row shape keys."""
    check = f"{instance}: list"
    fn = operate_fn or remotes_core.operate
    try:
        listed = fn(instance, "list", config=config, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return Result(check, FAIL, f"list raised {type(exc).__name__}: {_scrub(exc)}"), []
    if listed is None:
        return Result(check, FAIL, "list returned no result"), []
    if not bool(getattr(listed, "ok", False)):
        status = getattr(listed, "http_status", None)
        return (
            Result(check, FAIL, f"list failed (http {status}) — {_scrub(getattr(listed, 'detail', ''))}"),
            [],
        )
    data = getattr(listed, "data", None)
    if not isinstance(data, dict):
        return Result(check, FAIL, f"list payload is {type(data).__name__}, not a dict"), []
    missing = [key for key in LIST_MARKER_KEYS if key not in data]
    if missing:
        return (
            Result(
                check,
                FAIL,
                "removed/renamed field(s): " + ", ".join(missing) + f" (payload keys: {sorted(data)})",
            ),
            [],
        )
    raw_agents: list[Any] = []
    for key in ("data", "agents"):
        if isinstance(data.get(key), list):
            raw_agents = data[key]
            break
    sessions_raw = data.get("sessions")
    sessions = [row for row in sessions_raw if isinstance(row, dict)] if isinstance(sessions_raw, list) else []
    bad_rows = [
        row
        for row in sessions
        if not str(row.get("id") or row.get("session_id") or "").strip()
        or not str(row.get("title") or "").strip()
    ]

    probe: dict[str, Any] = {}
    probe_err = ""
    pfn = probe_fn or _raw_probe
    try:
        probe = pfn(instance, spec=spec, timeout=timeout) or {}
    except Exception as exc:  # noqa: BLE001
        probe_err = f"raw probe raised {type(exc).__name__}: {_scrub(exc)}"

    if bad_rows:
        return (
            Result(check, FAIL, f"session row shape changed ({len(bad_rows)} row(s) missing id/title)"),
            sessions,
        )
    if probe:
        raw_session_rows = probe.get("sessions_rows")
        raw_agents_rows = probe.get("agents_rows")
        if isinstance(raw_session_rows, int) and raw_session_rows > 0 and not sessions:
            return (
                Result(
                    check,
                    FAIL,
                    f"server exposes {raw_session_rows} session row(s) but integration parsed 0 — "
                    f"row shape changed (row keys: {probe.get('sessions_row_keys')})",
                ),
                sessions,
            )
        if isinstance(raw_agents_rows, int) and raw_agents_rows > 0 and not raw_agents:
            return (
                Result(
                    check,
                    FAIL,
                    f"server exposes {raw_agents_rows} agent row(s) but integration parsed 0 — "
                    f"agent shape changed (row keys: {probe.get('agents_row_keys')})",
                ),
                sessions,
            )
    detail = (
        f"agents={len(raw_agents)} sessions={len(sessions)} "
        f"payload_keys={sorted(data)} row_keys={sorted(sessions[0]) if sessions else []}"
    )
    if probe:
        detail += (
            f" · raw(agents={probe.get('agents_rows')}@{probe.get('agents_status')}, "
            f"sessions={probe.get('sessions_rows')}@{probe.get('sessions_status')})"
        )
    if probe_err:
        detail += f" · {probe_err}"
    return Result(check, PASS, detail), sessions


def send_headroom_note(elapsed: float, budget: float) -> str:
    """Flag a turn that already used half or more of its poll budget.

    A one-token resume measured 46–59s (#1307). Against a 90s budget that is
    most of the cap; the next slower turn times out.
    """
    if budget <= 0 or elapsed < 0.5 * budget:
        return ""
    return f" · headroom tight ({elapsed:.1f}s of {budget:.0f}s budget)"


def describe_send_budget(
    timeout: float | None,
    spec: Any | None = None,
) -> tuple[float, str]:
    """Resolved send poll budget and a one-line provenance label."""
    floor = float(getattr(remotes_core, "_TRUEFORGE_SEND_TIMEOUT_S", 180.0))
    resolved = float(remotes_core._trueforge_send_timeout_s(timeout, spec))
    if timeout is not None and timeout > 0:
        return resolved, f"{resolved:.1f}s (--send-timeout)"
    env_raw = os.environ.get("SWARM_TRUEFORGE_TIMEOUT", "").strip()
    if env_raw:
        try:
            env_val = float(env_raw)
        except ValueError:
            env_val = 0.0
        if env_val > 0 and env_val < floor and resolved + 1e-6 >= floor:
            return resolved, (
                f"{resolved:.0f}s (floor; SWARM_TRUEFORGE_TIMEOUT={env_raw}s "
                f"is below {floor:.0f}s — one-token resume measured 46-59s)"
            )
        if env_val > 0:
            return resolved, f"{resolved:.1f}s (SWARM_TRUEFORGE_TIMEOUT)"
    spec_timeout = getattr(spec, "timeout", None) if spec is not None else None
    if spec_timeout is not None:
        try:
            spec_val = float(spec_timeout)
        except (TypeError, ValueError):
            spec_val = 0.0
        if spec_val > 0 and abs(resolved - spec_val) < 0.01:
            return resolved, f"{resolved:.1f}s (remotes timeout)"
    return resolved, (
        f"{resolved:.1f}s (integration default; SWARM_TRUEFORGE_TIMEOUT unset)"
    )


def check_send(
    instance: str,
    session_id: str,
    *,
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
    operate_fn: Callable[..., Any] | None = None,
    spec: Any | None = None,
) -> SendObservation:
    """3. operate(instance, 'send', session_id=existing) — resumes, replies, elapsed.

    ``timeout=None`` lets the integration resolve its own budget
    (``SWARM_TRUEFORGE_TIMEOUT`` raised to the 180s floor when set lower, then
    ``spec.timeout``, then 180s), so the check measures the same bound
    production uses. A turn that already used half the budget is flagged:
    #1307 measured 46–59s resumes against a 90s cap.
    """
    check = f"{instance}: send resume"
    budget = float(remotes_core._trueforge_send_timeout_s(timeout, spec))
    if not session_id:
        return SendObservation(
            Result(check, FAIL, "no existing session id from list — cannot verify resume"),
        )
    fn = operate_fn or remotes_core.operate
    started = time.monotonic()
    try:
        sent = fn(
            instance,
            "send",
            prompt=SEND_PROMPT,
            config=config,
            timeout=timeout,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started
        return SendObservation(
            Result(check, FAIL, f"send raised after {elapsed:.1f}s: {type(exc).__name__}: {_scrub(exc)}")
        )
    elapsed = time.monotonic() - started
    if sent is None:
        return SendObservation(Result(check, FAIL, f"send returned no result after {elapsed:.1f}s"))
    data = getattr(sent, "data", None) if isinstance(getattr(sent, "data", None), dict) else {}
    live_turn = data.get("turn") if isinstance(data.get("turn"), dict) else None
    live_events = data.get("events") if isinstance(data.get("events"), list) else []
    if not bool(getattr(sent, "ok", False)):
        return SendObservation(
            Result(
                check,
                FAIL,
                f"send failed after {elapsed:.1f}s (http {getattr(sent, 'http_status', None)}) — "
                f"{_scrub(getattr(sent, 'detail', ''))}"
                + send_headroom_note(elapsed, budget),
            ),
            live_turn,
            live_events,
        )
    minted = str(data.get("session_created_for") or "").strip()
    resumed_as = str(data.get("session_id") or "").strip()
    if minted or (resumed_as and resumed_as != session_id):
        return SendObservation(
            Result(
                check,
                FAIL,
                f"minted a NEW session ({minted or resumed_as}) instead of resuming {session_id} "
                f"after {elapsed:.1f}s",
            ),
            live_turn,
            live_events,
        )
    turn_state = _norm_state(live_turn) or "unknown"
    reply = str(data.get("text") or getattr(sent, "detail", "") or "").strip()
    if not reply:
        return SendObservation(
            Result(check, FAIL, f"resumed {session_id} but no reply text (state={turn_state}, {elapsed:.1f}s)"),
            live_turn,
            live_events,
        )
    awaiting = bool(data.get("awaiting_input"))
    return SendObservation(
        Result(
            check,
            PASS,
            f"resumed {session_id} — state={turn_state} elapsed={elapsed:.1f}s "
            f"reply={_scrub(reply[:60])!r}"
            + (" · awaiting_input" if awaiting else "")
            + send_headroom_note(elapsed, budget),
        ),
        live_turn,
        live_events,
        awaiting_input=awaiting,
    )


SAMPLE_PAUSED_TURN: dict[str, Any] = {
    "state": {
        "status": "done",
        "output": None,
        "required_actions": [
            {
                "id": "act-verify-1",
                "type": "tool.response_required",
                "thread_id": "main",
                "tool_calls": [{"id": "chatcmpl-tool-verify", "source_event_id": "evt-1"}],
            }
        ],
    }
}

SAMPLE_ASK_EVENTS: list[Any] = [
    {"type": "turn.created", "state": {"status": "running"}},
    {
        "id": "evt-1",
        "type": "model.message",
        "content": "Let me confirm before continuing.",
        "thread_id": "main",
        "tool_calls": [
            {
                "id": "chatcmpl-tool-verify",
                "type": "function",
                "function": {
                    "name": "ask_user_question",
                    "arguments": json.dumps(
                        {
                            "question": "Which environment should I deploy to?",
                            "options": ["staging", "production"],
                        }
                    ),
                },
            }
        ],
    },
    {
        "id": "tool-evt",
        "type": "tool.response_required",
        "thread_id": "main",
        "tool_calls": [{"id": "chatcmpl-tool-verify", "source_event_id": "evt-1"}],
    },
]


def check_pending_question(
    *,
    turn_data: dict[str, Any] | None = None,
    events: list[Any] | None = None,
    live_turn: dict[str, Any] | None = None,
    live_events: list[Any] | None = None,
) -> Result:
    """4. required_actions / tool.response_required ask-user detection.

    The sample pinned from the live TrueForge pause shape must map to the local
    ask-user question; a live paused turn is reported when the server happens to
    expose one, without failing the check when it does not.
    """
    check = "sample: required_actions"
    sample_turn = SAMPLE_PAUSED_TURN if turn_data is None else turn_data
    sample_events = SAMPLE_ASK_EVENTS if events is None else events
    try:
        pending = remotes_core.trueforge_pending_question(
            sample_turn, sample_events, turn_id="verify-sample"
        )
    except Exception as exc:  # noqa: BLE001
        return Result(check, FAIL, f"detector raised {type(exc).__name__}: {_scrub(exc)}")
    if pending is None:
        return Result(
            check,
            FAIL,
            "paused-turn sample not detected — required_actions / tool.response_required "
            "shape may have changed",
        )
    question = pending.get("question") if isinstance(pending.get("question"), dict) else {}
    ask = str(question.get("ask") or "").strip()
    if not ask:
        return Result(check, FAIL, "detected a pending action but extracted no question text")
    choices = question.get("choices") if isinstance(question.get("choices"), list) else []
    live_note = "live server did not expose a paused ask-user state on the sampled turn"
    if live_turn is not None:
        try:
            live_pending = remotes_core.trueforge_pending_question(
                live_turn, live_events or [], turn_id="verify-live"
            )
        except Exception:  # noqa: BLE001
            live_pending = None
        live_note = (
            "live server exposed a paused ask-user state"
            if live_pending is not None
            else live_note
        )
    return Result(
        check,
        PASS,
        f"detector OK (ask={_scrub(ask[:50])!r}, choices={len(choices)}); {live_note}",
    )


TURN_STATE_SHAPES: tuple[tuple[dict[str, Any], str], ...] = (
    ({"state": "done"}, "done"),
    ({"state": "RUNNING"}, "running"),
    ({"state": {"status": "completed"}}, "completed"),
    ({"state": {"state": "finished"}}, "finished"),
    ({"status": "success"}, "success"),
)


def check_turn_state(*, live_turn: dict[str, Any] | None = None) -> Result:
    """5. _trueforge_turn_state on the known + live/upgraded shapes."""
    check = "sample: turn_state"
    problems: list[str] = []
    for turn, expected in TURN_STATE_SHAPES:
        try:
            got = remotes_core._trueforge_turn_state(turn)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{turn!r} raised {type(exc).__name__}")
            continue
        if got != expected:
            problems.append(f"{turn!r} -> {got!r} (want {expected!r})")
    live_note = ""
    if live_turn is not None:
        live_state = _norm_state(live_turn)
        if not live_state:
            problems.append(
                f"live turn state unrecognized (keys={sorted(live_turn) if isinstance(live_turn, dict) else type(live_turn).__name__})"
            )
        else:
            live_note = f" · live state={live_state!r}"
    if problems:
        return Result(check, FAIL, "; ".join(problems))
    return Result(check, PASS, f"handled {len(TURN_STATE_SHAPES)} shape(s){live_note}")


def _import_chat_persist_views() -> Any:
    return importlib.import_module("swarm.views.chat_persist_views")


def check_hydrate(
    *,
    importer: Callable[[], Any] | None = None,
    live_probe: Callable[[], Any] | None = None,
) -> Result:
    """6. Session-hydrate path (chat_persist_views) importable/working."""
    check = "django: chat_persist_views import"
    fn = importer or _import_chat_persist_views
    try:
        module = fn()
    except Exception as exc:  # noqa: BLE001
        return Result(check, FAIL, f"import failed: {type(exc).__name__}: {_scrub(exc)}")
    view = getattr(module, "chat_thread", None)
    if not callable(view):
        return Result(check, FAIL, "module imported but chat_thread view is missing")
    detail = "chat_persist_views.chat_thread importable"
    if live_probe is not None:
        try:
            hydrated = live_probe()
            if isinstance(hydrated, list):
                detail += f" · recent-turns hydrate returned {len(hydrated)} turn(s)"
            else:
                return Result(check, FAIL, f"hydrate probe returned {type(hydrated).__name__}, not a list")
        except Exception as exc:  # noqa: BLE001
            return Result(check, FAIL, f"hydrate probe raised {type(exc).__name__}: {_scrub(exc)}")
    return Result(check, PASS, detail)


def _recent_turns_probe(instance: str, session_id: str, timeout: float) -> Callable[[], Any]:
    def _probe() -> Any:
        from swarm.core.remote_impls.trueforge import read_trueforge_recent_turns

        return read_trueforge_recent_turns(instance, session_id, timeout=timeout)

    return _probe


def verify_instance(
    instance: str,
    *,
    config: dict[str, Any] | None = None,
    health_timeout: float = 3.0,
    op_timeout: float = 5.0,
    send_timeout: float | None = None,
    health_fn: Callable[..., Any] | None = None,
    operate_fn: Callable[..., Any] | None = None,
    probe_fn: Callable[..., Any] | None = None,
    hydrate_importer: Callable[[], Any] | None = None,
    hydrate_live_probe: Callable[[], Any] | None = None,
) -> list[Result]:
    """Run every check for one instance; each check passes or fails on its own."""
    results: list[Result] = []
    spec = None
    try:
        spec = remotes_core.load_remote(instance, config)
    except Exception:  # noqa: BLE001 — health reports the unconfigured case
        spec = None

    health = check_health(
        instance, config=config, timeout=health_timeout, health_fn=health_fn
    )
    results.append(health)

    live_turn: dict[str, Any] | None = None
    live_events: list[Any] = []
    if health.status != PASS:
        note = f"{instance} is not UP — live calls not attempted ({health.detail})"
        if "offline" in health.detail:
            note = f"offline — live calls not attempted ({health.detail})"
        results.append(Result(f"{instance}: list", SKIP, note))
        results.append(Result(f"{instance}: send resume", SKIP, note))
    else:
        listed, sessions = check_list(
            instance,
            config=config,
            timeout=op_timeout,
            operate_fn=operate_fn,
            probe_fn=probe_fn,
            spec=spec,
        )
        results.append(listed)
        if listed.status != PASS:
            results.append(
                Result(
                    f"{instance}: send resume",
                    SKIP,
                    "list did not verify a payload shape — resume not attempted",
                )
            )
        else:
            session_id = ""
            for row in sessions:
                session_id = str(row.get("id") or row.get("session_id") or "").strip()
                if session_id:
                    break
            observation = check_send(
                instance,
                session_id,
                config=config,
                timeout=send_timeout,
                operate_fn=operate_fn,
                spec=spec,
            )
            results.append(observation.result)
            live_turn = observation.live_turn
            live_events = observation.live_events
            if hydrate_live_probe is None and session_id:
                hydrate_live_probe = _recent_turns_probe(instance, session_id, op_timeout)

    if live_turn is None:
        pending_result = check_pending_question()
    else:
        pending_result = check_pending_question(live_turn=live_turn, live_events=live_events)
    results.append(pending_result)
    results.append(check_turn_state(live_turn=live_turn))
    results.append(
        check_hydrate(importer=hydrate_importer, live_probe=hydrate_live_probe)
    )
    return results


def discover_instances(config: dict[str, Any] | None = None) -> list[str]:
    """The two #1307 ids plus any other configured TrueForge instance."""
    found = list(DEFAULT_INSTANCES)
    try:
        for rid in remotes_core.configured_remote_ids(config):
            if rid in found:
                continue
            if remotes_core.is_trueforge_remote(rid, config):
                found.append(rid)
    except Exception:  # noqa: BLE001 — discovery is best-effort
        pass
    return found


def _boot_django() -> str:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
    import django

    django.setup()
    return f"Django ready ({os.environ['DJANGO_SETTINGS_MODULE']})"


def _merge_global_checks(results: list[Result]) -> list[Result]:
    """Global checks run once per instance; keep one row, preferring live detail."""
    out: list[Result] = []
    index: dict[str, int] = {}
    for row in results:
        if row.check not in GLOBAL_CHECKS:
            out.append(row)
            continue
        pos = index.get(row.check)
        if pos is None:
            index[row.check] = len(out)
            out.append(row)
            continue
        richer_new = ("live state=" in row.detail or "live server exposed" in row.detail)
        richer_old = ("live state=" in out[pos].detail or "live server exposed" in out[pos].detail)
        if richer_new and not richer_old:
            out[pos] = row
    return out


def _print_table(results: list[Result]) -> None:
    check_w = max([len("check")] + [len(r.check) for r in results])
    status_w = max([len("status")] + [len(r.status) for r in results])
    width = check_w + status_w + len("detail") + 4
    print()
    print(f"{'check':<{check_w}}  {'status':<{status_w}}  detail")
    print("-" * width)
    for row in results:
        detail = row.detail if len(row.detail) <= 200 else row.detail[:197] + "..."
        print(f"{row.check:<{check_w}}  {row.status:<{status_w}}  {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="#1307 TrueForge upgrade verification")
    parser.add_argument(
        "--instance",
        action="append",
        default=None,
        help="TrueForge remote id to verify (repeatable; default: configured instances)",
    )
    parser.add_argument("--health-timeout", type=float, default=3.0)
    parser.add_argument("--op-timeout", type=float, default=5.0)
    parser.add_argument(
        "--send-timeout",
        type=float,
        default=None,
        help="override the send poll budget (default: SWARM_TRUEFORGE_TIMEOUT "
        "raised to the 180s floor when lower, else the integration fallback)",
    )
    parser.add_argument("--json", action="store_true", help="emit the results as JSON")
    args = parser.parse_args(argv)

    print("=== #1307 TrueForge upgrade verification ===")
    for line in load_swarm_dotenv(project_root=REPO_ROOT):
        print(f"dotenv: {line}")
    try:
        print(_boot_django())
    except Exception as exc:  # noqa: BLE001
        print(f"django: setup failed — {type(exc).__name__}: {_scrub(exc)}")

    config: dict[str, Any] | None = None
    instances = args.instance or discover_instances(config)
    print(f"instances: {', '.join(instances)}")
    results: list[Result] = []
    for instance in instances:
        budget_spec = None
        try:
            budget_spec = remotes_core.load_remote(instance, config)
        except Exception:  # noqa: BLE001 — health reports an unconfigured instance
            budget_spec = None
        _resolved, budget_label = describe_send_budget(args.send_timeout, budget_spec)
        print(f"send budget ({instance}): {budget_label}")
        results.extend(
            verify_instance(
                instance,
                config=config,
                health_timeout=args.health_timeout,
                op_timeout=args.op_timeout,
                send_timeout=args.send_timeout,
            )
        )
    results = _merge_global_checks(results)

    if args.json:
        print(json.dumps([{"check": r.check, "status": r.status, "detail": r.detail} for r in results], indent=2))
    else:
        _print_table(results)

    passed = sum(1 for r in results if r.status == PASS)
    failed = sum(1 for r in results if r.status == FAIL)
    skipped = sum(1 for r in results if r.status == SKIP)
    print(f"\nsummary: {passed} pass, {failed} fail, {skipped} skip")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
