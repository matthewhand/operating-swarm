"""#812 slice 5 — TrueForge impl bodies, moved verbatim out of
``swarm.core.remotes``. References to other moved names go
through ``R`` (the remotes module object) so monkeypatching on
``remotes`` still lands: behaviorally this is the same code.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import socket
import time
import urllib.error  # noqa: F401
import urllib.request  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlparse, urlunparse  # noqa: F401

import httpx

if TYPE_CHECKING:  # annotations only, never evaluated at runtime
    # These names are used in ANNOTATIONS ONLY -- 'from __future__ import
    # annotations' keeps them strings, never evaluated at runtime -- and a
    # runtime import of swarm.core.remotes here would close the import cycle
    # these modules exist to avoid: their bodies reach remotes through the
    # lazily-imported module object 'R' instead. Without this declaration
    # ruff F821 reports every one of those annotations as an undefined name
    # and a type checker resolves them to nothing.
    from swarm.core.remotes import OperateResult, RemoteSpec

R: Any = importlib.import_module("swarm.core.remotes")

__all__ = ['_trueforge_agent_id_shape', '_trueforge_create_session', '_trueforge_list', '_trueforge_required_actions', '_trueforge_resolve_agent_name', '_trueforge_routines', '_trueforge_send', '_trueforge_send_timeout_s', '_trueforge_sessions', '_trueforge_turn_state', '_trueforge_unwired_send', '_trueforge_collect_turn', '_trueforge_resume_pending', '_trueforge_session_turns', '_trueforge_turns_to_transcript', 'read_trueforge_recent_turns', 'trueforge_pending_question', 'trueforge_tool_response_body']


def _trueforge_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or R._OPERATE_TIMEOUT_S), 10.0)
    result = R.http_json(
        "GET",
        f"{base_url}/api/v1/agents",
        headers=R._auth_headers(spec),
        timeout=timeout_s,
    )
    if result.status in R._UP:
        agents = None
        if isinstance(result.body, dict):
            agents = result.body.get("agents") or result.body.get("data")
        elif isinstance(result.body, list):
            agents = result.body
        count = len(agents) if isinstance(agents, list) else (1 if agents else 0)
        # #810: fetch the real conversation sessions so the navbar History
        # picker resumes actual threads. Best-effort — an unreachable or
        # erroring /api/v1/sessions never fails the agents list.
        sessions = _trueforge_sessions(spec, timeout_s)
        # #425: these rows are *agents*. A send resume key is a session id, and
        # forwarding a row id as one produced "404 Session not found". Say what
        # the rows are so the caller can tell the two apart.
        payload = result.body if isinstance(result.body, dict) else {"data": result.body}
        return R.OperateResult(
            remote=spec.id,
            op="list",
            ok=True,
            detail=(
                f"TrueForge listed {count} agent(s) via GET /api/v1/agents — rows are agents; "
                "send resumes on session_id"
            ),
            http_status=result.status,
            data={**payload, "rows_are": "agents", "resume_key": "session_id", "sessions": sessions},
        )
    if result.status in R._AUTH:
        env_var = spec.api_key_env or f"{spec.id.upper()}_API_KEY"
        return R.OperateResult(
            remote=spec.id,
            op="list",
            ok=False,
            # #494: name the env var to export — never "set remotes.<id>.api_key",
            # which reads like the field takes a literal key (persist_remote refuses).
            detail=(
                f"TrueForge /api/v1/agents requires auth. Name the env var in "
                f"Settings → Remotes (e.g. {env_var}) and export it before calling."
            ),
            http_status=result.status,
            data=result.body,
            action=R._settings_action(spec.id),
        )
    return R.OperateResult(
        remote=spec.id,
        op="list",
        ok=False,
        detail=result.error or f"TrueForge list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _trueforge_turn_state(turn_data: dict[str, Any] | None) -> str:
    """Normalize TrueForge turn ``state`` from a string or ``{"status": ...}`` dict."""
    if not isinstance(turn_data, dict):
        return ""
    raw_state = turn_data.get("state")
    if isinstance(raw_state, dict):
        return str(raw_state.get("status") or raw_state.get("state") or "").strip().lower()
    return str(raw_state or turn_data.get("status") or "").strip().lower()


# TrueForge's built-in clarifying-question tool (RuntimeConfig.ask_user_questions).
_TRUEFORGE_ASK_TOOL_NAMES = frozenset({"ask_user_question"})


def _trueforge_required_actions(turn_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Pending actions on a finished turn, normalized (possibly empty).

    TrueForge ends a paused turn ``status: done`` with
    ``state.required_actions`` carrying ``tool.approval_required`` /
    ``tool.response_required`` / ``mcp.auth_required`` entries instead of a
    final model message. A plain completed turn has none.
    """
    if not isinstance(turn_data, dict):
        return []
    state = turn_data.get("state")
    if not isinstance(state, dict):
        return []
    actions = state.get("required_actions")
    if not isinstance(actions, list):
        return []
    return [a for a in actions if isinstance(a, dict)]


def _trueforge_parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """Function-call ``arguments`` are a JSON string (or already a mapping)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _trueforge_ask_question_from_action(
    action: dict[str, Any],
    events: list[Any],
    *,
    turn_id: str = "",
) -> dict[str, Any] | None:
    """Map an ``ask_user_question`` ``tool.response_required`` action.

    Returns the local ask-user shape (``{id, ask, choices, other}``) plus the
    resume coordinates needed to answer it, or ``None`` when the pending call
    is not a TrueForge ask-user question.
    """
    if str(action.get("type") or "").strip().lower() != "tool.response_required":
        return None
    thread_id = str(action.get("thread_id") or "main").strip() or "main"
    call_refs = action.get("tool_calls")
    if not isinstance(call_refs, list):
        return None

    # Index model.message tool calls by id so an action ref resolves to the
    # function name + arguments the model actually emitted.
    by_id: dict[str, dict[str, Any]] = {}
    for event in events or []:
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").lower() != "model.message":
            continue
        for call in event.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("id"):
                by_id[str(call["id"])] = call

    for ref in call_refs:
        if not isinstance(ref, dict):
            continue
        call_id = str(ref.get("id") or "").strip()
        call = by_id.get(call_id) or {}
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = str(function.get("name") or call.get("name") or "").strip().lower()
        if name not in _TRUEFORGE_ASK_TOOL_NAMES:
            continue
        args = _trueforge_parse_tool_arguments(function.get("arguments"))
        ask = str(args.get("question") or args.get("ask") or "").strip()
        if not ask:
            continue
        raw_options = args.get("options")
        if raw_options is None:
            raw_options = args.get("choices")
        if isinstance(raw_options, str):
            raw_options = [part.strip() for part in raw_options.split(",") if part.strip()]
        choices = (
            [str(opt).strip() for opt in raw_options if str(opt).strip()]
            if isinstance(raw_options, list)
            else []
        )
        return {
            "type": "ask_user_question",
            "action_id": str(action.get("id") or "").strip(),
            "thread_id": thread_id,
            "tool_call_id": call_id,
            "previous_turn_id": str(turn_id or "").strip(),
            "question": {
                "id": call_id or str(action.get("id") or "q"),
                "ask": ask,
                "choices": choices,
                "other": "Other",
            },
        }
    return None


def trueforge_pending_question(
    turn_data: dict[str, Any] | None,
    events: list[Any] | None = None,
    *,
    turn_id: str = "",
) -> dict[str, Any] | None:
    """First pending ``ask_user_question`` on a paused TrueForge turn, or None."""
    for action in _trueforge_required_actions(turn_data):
        found = _trueforge_ask_question_from_action(action, events or [], turn_id=turn_id)
        if found is not None:
            return found
    return None


def trueforge_tool_response_body(
    *,
    thread_id: str,
    tool_call_id: str,
    content: str,
    previous_turn_id: str = "",
) -> dict[str, Any]:
    """Body to resume a paused TrueForge turn with a client tool response.

    Mirrors the gateway ``UserToolResponseEvent`` input item on
    ``POST /api/v1/sessions/{session_id}/turns``; ``content`` is the answer.
    """
    body: dict[str, Any] = {
        "input": [
            {
                "type": "user.tool_response",
                "thread_id": thread_id or "main",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        ],
        "stream": False,
    }
    if previous_turn_id:
        body["previous_turn_id"] = previous_turn_id
    return body


def _trueforge_sessions(spec: RemoteSpec, timeout: float) -> list[dict[str, Any]]:
    """GET /api/v1/sessions → normalized session rows (#810).

    Shape: ``{id, agent, title, created_at}``. Title prefers the session's
    own title, then metadata.title, then ``<agent> <short-id>``. Never
    raises — a failure returns [] and the picker simply shows nothing.
    """
    base_url = (spec.base_url or "").rstrip("/")
    result = R.http_json(
        "GET",
        f"{base_url}/api/v1/sessions",
        headers=R._auth_headers(spec),
        timeout=timeout,
    )
    if result.status not in R._UP:
        return []
    body = result.body
    rows: Any = []
    if isinstance(body, dict):
        rows = body.get("sessions") or body.get("data") or []
    elif isinstance(body, list):
        rows = body
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        session_id = str(row.get("id") or row.get("session_id") or "").strip()
        if not session_id or session_id in seen:
            continue
        seen.add(session_id)
        agent_raw: Any = row.get("agent")
        if isinstance(agent_raw, dict):
            # #1099: the real API nests the agent as {type, id, name} —
            # normalize to its name instead of str()-ed dict garbage.
            agent_raw = agent_raw.get("name") or agent_raw.get("id") or ""
        agent = str(agent_raw or row.get("agent_id") or "").strip()
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        title = str(
            row.get("title")
            or metadata.get("title")
            or metadata.get("name")
            or (f"{agent} {session_id[:8]}" if agent else session_id)
        ).strip()
        out.append(
            {
                "id": session_id,
                "agent": agent,
                "title": title,
                "created_at": str(row.get("created_at") or row.get("createdAt") or "").strip(),
                # #1100: the API exposes per-session recent activity — surface it
                # so the picker can show it instead of an epoch-0 stamp.
                "updated_at": str(row.get("updated_at") or row.get("updatedAt") or "").strip(),
            }
        )
    return out


# #1307 live check: "Reply with exactly OK" session resumes took 46–59s on
# both TrueForge instances. A 90s SWARM_TRUEFORGE_TIMEOUT leaves ~30s of slack
# and the next slower turn dies as a timeout. The integration floor (#1126)
# stays 180s; the env var may raise it, not undercut it.
_TRUEFORGE_LOW_TIMEOUT_WARNED = False


def _trueforge_send_floor_s() -> float:
    return float(getattr(R, "_TRUEFORGE_SEND_TIMEOUT_S", 180.0))


def _note_low_trueforge_timeout(raw: str, floor: float) -> None:
    """Warn once per process when the env cap is raised to the send floor."""
    global _TRUEFORGE_LOW_TIMEOUT_WARNED
    if _TRUEFORGE_LOW_TIMEOUT_WARNED:
        return
    _TRUEFORGE_LOW_TIMEOUT_WARNED = True
    R.logger.warning(
        "SWARM_TRUEFORGE_TIMEOUT=%s is below the %.0fs TrueForge send floor "
        "(one-token resume measured 46-59s on #1307); using %.0fs",
        raw,
        floor,
        floor,
    )


def _trueforge_send_timeout_s(timeout: float | None = None, spec: RemoteSpec | None = None) -> float:
    """Send/poll budget for TrueForge LLM turns (not health/list probes).

    ``R.operate()`` send uses ``R._OPERATE_SEND_TIMEOUT_S`` (list stays 8s). Treat
    those generic R.operate defaults as unset and resolve
    ``SWARM_TRUEFORGE_TIMEOUT``, then ``spec.timeout``, then 180s.

    ``SWARM_TRUEFORGE_TIMEOUT`` may raise the budget above the 180s floor. A
    positive value at or below that floor is raised to the floor: a 90s cap
    measured too tight against 46–59s resumes (#1307). An explicit per-call
    timeout (anything other than the generic operate defaults) is kept even
    when shorter, so probes and tests can opt out. ``spec.timeout`` is a
    per-remote override and is not floored.
    """
    floor = _trueforge_send_floor_s()
    if timeout is not None:
        try:
            explicit = float(timeout)
        except (TypeError, ValueError):
            explicit = 0.0
        if explicit > 0 and explicit not in {R._OPERATE_TIMEOUT_S, R._OPERATE_SEND_TIMEOUT_S}:
            return explicit
    env_raw = os.environ.get("SWARM_TRUEFORGE_TIMEOUT", "").strip()
    if env_raw:
        try:
            env_val = float(env_raw)
        except ValueError:
            env_val = 0.0
        if env_val > 0:
            if env_val < floor:
                _note_low_trueforge_timeout(env_raw, floor)
                return floor
            return env_val
    spec_timeout = getattr(spec, "timeout", None) if spec is not None else None
    if spec_timeout is not None:
        try:
            spec_val = float(spec_timeout)
            if spec_val > 0:
                return spec_val
        except (TypeError, ValueError):
            pass
    return floor


_TRUEFORGE_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}$")


def _trueforge_agent_id_shape(value: str) -> bool:
    """#759: is this key an agent *id* (ULID) rather than a display name?

    TrueForge secondary agents are referenced by 26-char ULID; the session
    create schema rejects a ULID masquerading as ``agent.name`` (HTTP 400).
    Plain test ids like ``agent-1`` and real names stay name-shaped.
    """
    return bool(_TRUEFORGE_ULID_RE.match((value or "").strip()))


def _trueforge_resolve_agent_name(
    spec: R.RemoteSpec, base_url: str, agent_id: str, timeout_s: float
) -> str:
    """#759: look up an agent's display name via ``GET /api/v1/agents``.

    Best-effort: any failure (auth, unreachable, no match) returns ``''`` and
    the caller falls back to the schema-honest ``agent.id`` shape.
    """
    try:
        resp = R.http_json(
            "GET",
            f"{base_url}/api/v1/agents",
            headers=R._auth_headers(spec),
            timeout=min(5.0, timeout_s),
        )
    except Exception:
        return ""
    body = resp.body if isinstance(resp.body, dict) else {}
    rows = body.get("data") if isinstance(body.get("data"), list) else body.get("agents")
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "") == agent_id:
            return str(row.get("name") or "").strip()
    return ""


def _trueforge_create_session(
    spec: R.RemoteSpec, base_url: str, agent_name: str, timeout_s: float
) -> tuple[str, R.OperateResult | None]:
    """``POST /api/v1/sessions`` for one agent. Returns ``(session_id, error)``.

    Both the fresh-send path and the #425 recovery path start sessions the same
    way, so the auth / unreachable / id-missing sentences live here once.
    """
    name = (agent_name or "").strip() or "orchestrator"
    agent: dict[str, str] = {"name": name}
    if _trueforge_agent_id_shape(name):
        # #759: a ULID is an agent id, not a name. Resolve the display name;
        # when that fails, still send the schema-honest ``agent.id`` field.
        resolved = _trueforge_resolve_agent_name(spec, base_url, name, timeout_s)
        if resolved:
            agent["name"] = resolved
        agent["id"] = name
    sess_resp = R.http_json(
        "POST",
        f"{base_url}/api/v1/sessions",
        headers=R._auth_headers(spec),
        body={"agent": agent, "metadata": {}},
        timeout=min(5.0, timeout_s),
    )
    if sess_resp.status in R._AUTH:
        return "", R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge POST /api/v1/sessions requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=sess_resp.status,
            data=sess_resp.body,
            action=R._settings_action(spec.id),
        )
    if sess_resp.status not in R._UP and sess_resp.status != 201:
        # #1159: the gateway answers a bare 400 when the agent payload doesn't
        # match its schema (agent: {name}). Name the schema, the agent we
        # tried, and the gateway's own detail — never a naked "http 400".
        if sess_resp.status == 400:
            gateway = ""
            if isinstance(sess_resp.body, dict):
                gateway = str(
                    sess_resp.body.get("detail")
                    or sess_resp.body.get("error")
                    or sess_resp.body.get("message")
                    or ""
                ).strip()
            elif sess_resp.text:
                gateway = sess_resp.text.strip()[:200]
            detail = (
                f"TrueForge rejected the session create for agent '{name}' (http 400): "
                "the gateway expects {\"agent\": {\"name\": <real agent>}}."
            )
            if gateway:
                detail += f" Gateway said: {gateway}"
            detail += " Check the agent name in Settings → Remotes."
            return "", R.OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail=detail,
                http_status=sess_resp.status,
                data=sess_resp.body or sess_resp.text or None,
            )
        return "", R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=R._unreachable_detail(sess_resp, "TrueForge session create"),
            http_status=sess_resp.status,
            data=sess_resp.body or sess_resp.text or None,
        )
    body = sess_resp.body if isinstance(sess_resp.body, dict) else {}
    sess_id = str(
        (body.get("data") if isinstance(body.get("data"), dict) else {}).get("id")
        or body.get("id")
        or ""
    )
    if not sess_id:
        return "", R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail="TrueForge did not return a session id",
            http_status=sess_resp.status,
            data=sess_resp.body,
        )
    return sess_id, None


def _trueforge_unwired_send(spec: R.RemoteSpec, target: str = "") -> bool:
    """#1159: this send would use the remote's own name as the agent.

    Auto-resume must not list sessions first — the refusal happens before
    any wire call. A real target or a wired ``spec.agent`` is not a refusal.
    An empty target still defaults to ``orchestrator``.
    """
    agent_name = (
        (target or "").strip()
        or (getattr(spec, "agent", "") or "").strip()
        or "orchestrator"
    )
    ident = str(getattr(spec, "id", "") or "")
    return agent_name == ident or agent_name == "trueforge"


def _trueforge_send(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    timeout: float | None = None,
    *,
    session_id: str | None = None,
) -> R.OperateResult:
    if not prompt.strip():
        return R.OperateResult(remote=spec.id, op="send", ok=False, detail="prompt is required")
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = _trueforge_send_timeout_s(timeout, spec)
    start_time = time.monotonic()
    deadline = start_time + timeout_s

    # 1. Session id: reuse or create via POST /api/v1/sessions
    requested_session = (session_id or "").strip()
    sess_id = requested_session
    created_for = ""
    if not sess_id:
        # #1159: a trueforge seat with no agent wired used to pass the
        # REMOTE'S OWN NAME as the agent and eat a bare gateway 400. That is
        # never a valid agent name — fail fast with the rebind path, no wire
        # call at all. (Empty target keeps the legacy "orchestrator" default,
        # which is a real agent in a stock TrueForge install.)
        # #1159 uplift: a wired spec.agent outranks both the raw target and
        # the kind default — the operator's declared agent is authoritative
        # for a named instance.
        agent_name = (
            (target or "").strip()
            or (getattr(spec, "agent", "") or "").strip()
            or "orchestrator"
        )
        if _trueforge_unwired_send(spec, target):
            return R.OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail=(
                    "This TrueForge remote has no agent wired — the send would "
                    "use the remote's own name as the agent. Set an agent in "
                    "Settings → Remotes (or pick one from the rail menu)."
                ),
                data={"missing_agent": True, "rejected_agent_name": agent_name},
                action=R._settings_action(spec.id),
            )
        sess_id, err = _trueforge_create_session(spec, base_url, agent_name, timeout_s)
        if err is not None:
            return err

    # 2. POST turn: POST /api/v1/sessions/{session_id}/turns
    remaining = max(1.0, deadline - time.monotonic())
    turn_resp = R.http_json(
        "POST",
        f"{base_url}/api/v1/sessions/{sess_id}/turns",
        headers=R._auth_headers(spec),
        body={
            "input": [{"type": "user.message", "content": prompt}],
            "stream": False,
        },
        timeout=min(5.0, remaining),
    )
    if turn_resp.status in R._AUTH:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge POST /turns requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=turn_resp.status,
            data=turn_resp.body,
            action=R._settings_action(spec.id),
        )
    if turn_resp.status not in R._UP and turn_resp.status not in (201, 202):
        if requested_session and turn_resp.status == 404:
            # #425: a resume key taken straight off the list is an *agent* id,
            # and TrueForge will not turn one into a session. Start a session for
            # that name instead of handing back a bare "404 Session not found".
            # #1159 uplift: the wired agent outranks the raw resume key when
            # deriving the mint name — a remote's own id is not an agent name.
            agent_name = (
                (target or "").strip()
                or (getattr(spec, "agent", "") or "").strip()
                or requested_session
            )
            minted, mint_err = _trueforge_create_session(spec, base_url, agent_name, timeout_s)
            if mint_err is not None:
                return R.OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=(
                        f"There is no TrueForge session '{requested_session}' to resume, and a "
                        f"session for '{agent_name}' could not be started: {mint_err.detail}"
                    ),
                    http_status=mint_err.http_status,
                    data={"requested_session_id": requested_session, "agent": agent_name},
                    gap="trueforge_no_session",
                )
            created_for, sess_id = agent_name, minted
            turn_resp = R.http_json(
                "POST",
                f"{base_url}/api/v1/sessions/{sess_id}/turns",
                headers=R._auth_headers(spec),
                body={
                    "input": [{"type": "user.message", "content": prompt}],
                    "stream": False,
                },
                timeout=min(5.0, max(1.0, deadline - time.monotonic())),
            )
            if turn_resp.status not in R._UP and turn_resp.status not in (201, 202):
                return R.OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=(
                        f"There is no TrueForge session '{requested_session}' to resume, and the "
                        f"session started for '{agent_name}' did not accept the turn: "
                        f"{R._unreachable_detail(turn_resp, 'TrueForge turn create')}"
                    ),
                    http_status=turn_resp.status,
                    data={"requested_session_id": requested_session, "agent": agent_name},
                    gap="trueforge_no_session",
                )
        else:
            return R.OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail=R._unreachable_detail(turn_resp, "TrueForge turn create"),
                http_status=turn_resp.status,
                data=turn_resp.body or turn_resp.text or None,
            )
    return _trueforge_collect_turn(
        spec,
        base_url,
        sess_id,
        turn_resp,
        deadline=deadline,
        timeout_s=timeout_s,
        created_for=created_for,
    )


def _trueforge_collect_turn(
    spec: R.RemoteSpec,
    base_url: str,
    sess_id: str,
    turn_resp: Any,
    *,
    deadline: float,
    timeout_s: float,
    created_for: str = "",
) -> R.OperateResult:
    """Poll one posted turn to completion, fetch its events, build the result.

    Shared by the initial ``send`` (from a ``user.message`` turn) and the
    ask-user resume (from a ``user.tool_response`` turn) so the poll/parse/event
    logic — including the paused ``ask_user_question`` detection — lives once.
    """
    tbody = turn_resp.body if isinstance(turn_resp.body, dict) else {}
    turn_id = str(
        (tbody.get("data") if isinstance(tbody.get("data"), dict) else {}).get("id")
        or tbody.get("id")
        or ""
    )
    if not turn_id:
        return R.OperateResult(
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
        poll_resp = R.http_json(
            "GET",
            f"{base_url}/api/v1/sessions/{sess_id}/turns/{turn_id}",
            headers=R._auth_headers(spec),
            timeout=min(3.0, max(1.0, deadline - time.monotonic())),
        )
        if poll_resp.status in R._AUTH:
            return R.OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail="TrueForge turn poll requires auth.",
                http_status=poll_resp.status,
                data=poll_resp.body,
                action=R._settings_action(spec.id),
            )
        if poll_resp.status in R._UP:
            turn_data = (
                poll_resp.body.get("data", {})
                if isinstance(poll_resp.body, dict) and isinstance(poll_resp.body.get("data"), dict)
                else (poll_resp.body if isinstance(poll_resp.body, dict) else {})
            )
            last_state = _trueforge_turn_state(turn_data)
            if last_state in R._TRUEFORGE_DONE_STATES:
                break
            if last_state in R._TRUEFORGE_ERROR_STATES:
                state_dict = turn_data.get("state") if isinstance(turn_data.get("state"), dict) else {}
                err_msg = (
                    turn_data.get("error")
                    or turn_data.get("message")
                    or turn_data.get("detail")
                    or state_dict.get("error")
                    or state_dict.get("message")
                    or state_dict.get("detail")
                    or f"TrueForge turn {turn_id} ended with state '{last_state}'"
                )
                return R.OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=str(err_msg),
                    http_status=poll_resp.status,
                    data=turn_data,
                )
        R.interruptible_sleep(0.1)

    if last_state not in R._TRUEFORGE_DONE_STATES:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge turn {turn_id} timed out after {timeout_s:.1f}s (state: {last_state or 'unknown'})",
            data=turn_data,
        )

    # 4. Fetch events: GET /api/v1/sessions/{session_id}/turns/{turn_id}/events
    events_resp = R.http_json(
        "GET",
        f"{base_url}/api/v1/sessions/{sess_id}/turns/{turn_id}/events",
        headers=R._auth_headers(spec),
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

    # A turn can finish ``done`` while still paused on a client action — the
    # TrueForge ``ask_user_question`` tool ends exactly this way. Surface the
    # question (and the coordinates to answer it) instead of silently returning
    # the model's lead-in as if it were the final reply.
    pending = trueforge_pending_question(turn_data, events_list, turn_id=turn_id)
    if pending is not None:
        ask = str(pending["question"].get("ask") or "").strip()
        if ask and ask not in reply_text:
            reply_text = f"{reply_text}\n\n{ask}".strip() if reply_text else ask

    return R.OperateResult(
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
            # #686: the parsed human reply rides in ``text`` — the chat
            # renderer renders send results from this key and must never fall
            # back to dumping the transport payload (turn + every event) as a
            # raw JSON blob into the conversation.
            "text": reply_text,
            **({"session_created_for": created_for} if created_for else {}),
            **(
                {
                    "awaiting_input": True,
                    "pending_question": pending["question"],
                    "pending_action": {
                        "type": pending["type"],
                        "action_id": pending["action_id"],
                        "thread_id": pending["thread_id"],
                        "tool_call_id": pending["tool_call_id"],
                        "previous_turn_id": pending["previous_turn_id"],
                    },
                }
                if pending is not None
                else {}
            ),
        },
    )


def _trueforge_resume_pending(
    spec: R.RemoteSpec,
    *,
    session_id: str,
    pending_action: dict[str, Any],
    content: str,
    timeout: float | None = None,
) -> R.OperateResult:
    """Resume a paused TrueForge turn by POSTing the client tool response.

    Posts the ``user.tool_response`` body :func:`trueforge_tool_response_body`
    builds, then polls the new turn — which may itself pause on another
    question, in which case the result is again ``awaiting_input``.
    """
    base_url = (spec.base_url or "").rstrip("/")
    sess_id = (session_id or "").strip()
    action = pending_action if isinstance(pending_action, dict) else {}
    thread_id = str(action.get("thread_id") or "main").strip() or "main"
    tool_call_id = str(action.get("tool_call_id") or "").strip()
    previous_turn_id = str(action.get("previous_turn_id") or "").strip()
    if not sess_id or not tool_call_id:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=(
                "TrueForge resume needs the paused session id and tool_call_id; "
                "the question payload was incomplete."
            ),
        )
    timeout_s = _trueforge_send_timeout_s(timeout, spec)
    deadline = time.monotonic() + timeout_s
    body = trueforge_tool_response_body(
        thread_id=thread_id,
        tool_call_id=tool_call_id,
        content=content,
        previous_turn_id=previous_turn_id,
    )
    turn_resp = R.http_json(
        "POST",
        f"{base_url}/api/v1/sessions/{sess_id}/turns",
        headers=R._auth_headers(spec),
        body=body,
        timeout=min(5.0, timeout_s),
    )
    if turn_resp.status in R._AUTH:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge POST /turns requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=turn_resp.status,
            data=turn_resp.body,
            action=R._settings_action(spec.id),
        )
    if turn_resp.status not in R._UP and turn_resp.status not in (201, 202):
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=R._unreachable_detail(turn_resp, "TrueForge tool response"),
            http_status=turn_resp.status,
            data=turn_resp.body or turn_resp.text or None,
        )
    return _trueforge_collect_turn(
        spec,
        base_url,
        sess_id,
        turn_resp,
        deadline=deadline,
        timeout_s=timeout_s,
    )


def _trueforge_routines(spec: RemoteSpec, timeout: float = R._OPERATE_TIMEOUT_S) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    if not base_url:
        return R.OperateResult(remote=spec.id, op="routines", ok=False, detail="base_url is empty")
    timeout_s = min(float(timeout or R._OPERATE_TIMEOUT_S), 15.0)
    start_time = time.monotonic()
    deadline = start_time + timeout_s

    headers = R._auth_headers(spec)
    result = R.http_json(
        "GET",
        f"{base_url}/api/v1/schedules?limit=25",
        headers=headers,
        timeout=min(5.0, timeout_s),
    )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote=spec.id,
            op="routines",
            ok=False,
            detail=f"TrueForge /api/v1/schedules requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=result.status,
            data={"routines": []},
            action=R._settings_action(spec.id),
        )
    if result.status not in R._UP:
        return R.OperateResult(
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
            runs_resp = R.http_json(
                "GET",
                f"{base_url}/api/v1/schedules/{schedule_id}/runs?limit=1",
                headers=headers,
                timeout=min(3.0, remaining),
            )
            if runs_resp.status in R._UP:
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

    return R.OperateResult(
        remote=spec.id,
        op="routines",
        ok=True,
        detail=f"TrueForge listed {len(routines)} routine(s)",
        http_status=result.status,
        data={"routines": routines},
    )




def _trueforge_session_turns(spec: RemoteSpec, session_id: str, timeout: float) -> list[dict[str, Any]]:
    """GET /api/v1/sessions/{sid}/turns → raw turn rows (#1228 hydration).

    Never raises: an unreachable or erroring harness returns [] and the
    caller renders an honest empty thread instead of fabricating one.
    """
    base_url = (spec.base_url or "").rstrip("/")
    if not base_url or not session_id.strip():
        return []
    result = R.http_json(
        "GET",
        f"{base_url}/api/v1/sessions/{quote(session_id.strip())}/turns",
        headers=R._auth_headers(spec),
        timeout=min(float(timeout or R._OPERATE_TIMEOUT_S), 12.0),
    )
    if result.status not in R._UP:
        return []
    body = result.body
    rows: Any = []
    if isinstance(body, dict):
        rows = body.get("turns") or body.get("data") or []
    elif isinstance(body, list):
        rows = body
    return [row for row in rows if isinstance(row, dict)]


def _trueforge_turns_to_transcript(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Map TrueForge turns → ``{role, content}`` transcript rows.

    Each turn's ``input`` blocks supply the user row (type ``user.message``
    or plain ``message``); the last ``model.message``/``assistant.message``
    event content supplies the assistant row. Content blocks (a list of
    ``{text}`` parts) are joined. Malformed rows are skipped, not fatal.
    """
    out: list[dict[str, str]] = []
    for turn in turns:
        for block in turn.get("input") or []:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").lower()
            if btype not in ("user.message", "message", "user_message"):
                continue
            content = block.get("content")
            if isinstance(content, str) and content.strip():
                out.append({"role": "user", "content": content.strip()})
            elif isinstance(content, list):
                parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")]
                if "".join(parts).strip():
                    out.append({"role": "user", "content": "".join(parts).strip()})
        reply = ""
        for event in reversed(turn.get("events") or []):
            if not isinstance(event, dict):
                continue
            etype = str(event.get("type") or "").lower()
            if etype not in ("model.message", "assistant.message", "model_message", "message"):
                continue
            content = event.get("content")
            if isinstance(content, str) and content.strip():
                reply = content.strip()
                break
            if isinstance(content, list):
                parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")]
                if "".join(parts).strip():
                    reply = "".join(parts).strip()
                    break
        if reply:
            out.append({"role": "assistant", "content": reply})
    return out


def read_trueforge_recent_turns(
    remote_id: str,
    session_id: str,
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> list[dict[str, str]]:
    """Public hydration hook for chat_thread (#1228).

    Resolves the remote spec (works with the bare kind id the SPA sends),
    fetches the session's turns, and maps them to transcript rows. Never
    raises — any failure is an empty list and the thread stays empty.
    """
    try:
        spec = R.load_remote(remote_id, config)
    except Exception:
        R.logger.debug("trueforge hydrate: cannot resolve remote %s", remote_id, exc_info=True)
        return []
    try:
        turns = _trueforge_session_turns(spec, session_id, timeout or R._OPERATE_TIMEOUT_S)
    except Exception:
        R.logger.debug("trueforge hydrate: turn fetch failed for %s/%s", remote_id, session_id, exc_info=True)
        return []
    return _trueforge_turns_to_transcript(turns)
