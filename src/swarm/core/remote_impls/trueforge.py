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
from typing import Any
from urllib.parse import quote, urlparse, urlunparse  # noqa: F401

import httpx

R: Any = importlib.import_module("swarm.core.remotes")

__all__ = ['_trueforge_agent_id_shape', '_trueforge_create_session', '_trueforge_list', '_trueforge_resolve_agent_name', '_trueforge_routines', '_trueforge_send', '_trueforge_send_timeout_s', '_trueforge_sessions', '_trueforge_turn_state']


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


def _trueforge_send_timeout_s(timeout: float | None = None, spec: RemoteSpec | None = None) -> float:
    """Send/poll budget for TrueForge LLM turns (not health/list probes).

    ``R.operate()`` send uses ``R._OPERATE_SEND_TIMEOUT_S`` (list stays 8s). Treat
    those generic R.operate defaults as unset and resolve
    ``SWARM_TRUEFORGE_TIMEOUT``, then ``spec.timeout``, then 60s.
    """
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
            if env_val > 0:
                return env_val
        except ValueError:
            pass
    spec_timeout = getattr(spec, "timeout", None) if spec is not None else None
    if spec_timeout is not None:
        try:
            spec_val = float(spec_timeout)
            if spec_val > 0:
                return spec_val
        except (TypeError, ValueError):
            pass
    return R._TRUEFORGE_SEND_TIMEOUT_S


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
        sess_id, err = _trueforge_create_session(
            spec, base_url, (target or "").strip() or "orchestrator", timeout_s
        )
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
            agent_name = (target or "").strip() or requested_session
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
        time.sleep(0.1)

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
        },
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


