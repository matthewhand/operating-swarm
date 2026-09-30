"""Tencent Octop remote (#1365).

Octop is one self-hosted FastAPI process. Operating Swarm talks to it as a
single ``remote`` — experts and AgentTeams stay inside Octop and are never
re-modeled as OS seats or ``TeamKindBase`` rosters.

Verified routes (Octop ``src/octop/api``):

* ``GET /api/health`` — public liveness (``{"ok": true, ...}``).
* ``GET /api/agents`` — JWT, the caller's experts (and Octop AgentTeams).
* ``GET /api/agents/{agent_id}/threads`` — JWT, dashboard threads.
* ``WS /api/agents/{agent_id}/chat/ws?token=`` — dashboard turn. The legacy
  SSE ``POST .../chat/stream`` route is gone; send rides this socket.

Auth is a Bearer JWT (``POST /api/auth/login`` → ``access_token``), stored
the same way as other remotes: an env var name, never a literal secret.
Octop does not pin OS models — a remote model is valid only when that
remote's own config declares it.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import time
from typing import Any
from urllib.parse import quote, urlencode, urlparse, urlunparse

R: Any = importlib.import_module("swarm.core.remotes")

logger = logging.getLogger(__name__)

__all__ = ["_octop_list", "_octop_send", "_octop_apply_frame", "_octop_turn_text"]

# Resume keys are ``agent_id`` or ``agent_id:thread_id`` and must survive
# CLI-session sanitize (``^[A-Za-z0-9._:-]{1,128}$``).
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,60}$")
_REMOTE_NAMES = frozenset({"octop", "tencent-octop", "tencentoctop", "tencent_octop"})
_THREAD_FETCH_CAP = 8
_MAX_FRAMES = 4000


def _base(spec: Any) -> str:
    return (getattr(spec, "base_url", "") or "").rstrip("/")


def _token(spec: Any) -> str:
    key = str(getattr(spec, "api_key", "") or "").strip()
    if not key or R._is_unresolved_placeholder(key):
        return ""
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key


def _auth_gap(spec: Any, what: str) -> Any:
    env_var = spec.api_key_env or f"{spec.id.upper()}_API_KEY"
    return R.OperateResult(
        remote=spec.id,
        op=what,
        ok=False,
        detail=(
            f"Octop {what} requires a JWT. Name the env var in Settings → Remotes "
            f"(e.g. {env_var}) and export the access_token from POST /api/auth/login."
        ),
        http_status=401,
        gap="octop_auth",
        action=R._settings_action(spec.id),
    )


def _safe_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if _ID_RE.fullmatch(text) else ""


def _redact(text: str, token: str) -> str:
    cleaned = re.sub(r"(token=)[^&\s]+", r"\1redacted", text or "")
    if token and len(token) >= 8 and token in cleaned:
        cleaned = cleaned.replace(token, "redacted")
    return cleaned[:500]


def _is_remote_label(spec: Any, value: str) -> bool:
    key = (value or "").strip().lower()
    if not key:
        return False
    names = set(_REMOTE_NAMES)
    names.add(str(getattr(spec, "id", "") or "").strip().lower())
    names.add(str(getattr(spec, "kind", "") or "").strip().lower())
    return key in names


def _resume_pair(value: str) -> tuple[str, str] | None:
    """Split ``agent_id:thread_id``. A value with no colon is not a pair."""
    if ":" not in value:
        return None
    left, right = value.split(":", 1)
    return left.strip(), right.strip()


def _resolve_target(
    spec: Any, target: str, session_id: str | None
) -> tuple[str, str, str]:
    """Return ``(agent_id, thread_id, error)``.

    ``error`` is ``bad-id`` when a resume component is present but not a
    safe id, otherwise empty. Missing agent is an empty ``agent_id``.

    The chat seat puts the resume key on both ``session_id`` and ``target``.
    A caller that only has the target (operate, ``params.session``) still
    passes ``agent_id:thread_id`` there, so either field may carry the pair.
    """
    raw_target = (target or "").strip()
    session = (session_id or "").strip()
    if _is_remote_label(spec, raw_target):
        raw_target = ""
    agent = ""
    thread = ""
    pair = _resume_pair(session) or _resume_pair(raw_target)
    if pair:
        agent, thread = pair
    elif raw_target:
        agent = raw_target
        if session and session != raw_target:
            thread = session
    else:
        configured = str(getattr(spec, "agent", "") or "").strip()
        if configured and not _is_remote_label(spec, configured):
            agent = configured
            thread = session
        elif session:
            agent = session
    if agent and not _safe_id(agent):
        return "", "", "bad-id"
    if thread and not _safe_id(thread):
        return "", "", "bad-id"
    return _safe_id(agent), _safe_id(thread) if thread else "", ""


def _agent_rows(body: Any) -> list[dict[str, Any]]:
    rows: Any = body
    if isinstance(body, dict):
        rows = body.get("agents") or body.get("data") or body.get("items")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _matches_query(row: dict[str, Any], query: str) -> bool:
    needle = (query or "").strip().lower()
    if not needle:
        return True
    blob = " ".join(
        str(row.get(key) or "")
        for key in ("agent_id", "name", "description", "title", "thread_id")
    ).lower()
    return needle in blob


def _octop_headers(spec: Any) -> dict[str, str]:
    """Authorization Bearer for the resolved JWT, scheme stripped once."""
    headers = {"Accept": "application/json", "User-Agent": "open-swarm-remotes/1"}
    token = _token(spec)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _publish_agent(row: dict[str, Any]) -> dict[str, Any]:
    """Navbar pickers send ``id`` as the resume target.

    Octop's list row uses ``id`` for the database primary key and
    ``agent_id`` for the slug the WebSocket path needs. Publishing the
    slug as ``id`` keeps the generic remote picker from targeting ``12``.
    """
    agent_id = _safe_id(row.get("agent_id"))
    if not agent_id:
        return row
    published = dict(row)
    published["agent_id"] = agent_id
    published["id"] = agent_id
    return published


def _octop_threads(spec: Any, agent_id: str, timeout: float) -> list[dict[str, Any]]:
    result = R.http_json(
        "GET",
        f"{_base(spec)}/api/agents/{quote(agent_id, safe='')}/threads?limit=20",
        headers=_octop_headers(spec),
        timeout=timeout,
    )
    if result.status not in R._UP:
        return []
    rows = result.body if isinstance(result.body, list) else []
    return [row for row in rows if isinstance(row, dict)]


def _session_row(agent_id: str, thread: dict[str, Any]) -> dict[str, Any] | None:
    thread_id = _safe_id(thread.get("thread_id") or thread.get("id"))
    if not thread_id:
        return None
    key = f"{agent_id}:{thread_id}"
    if len(key) > 128:
        return None
    title = str(thread.get("title") or agent_id)
    return {
        "id": key,
        "title": title[:240],
        "snippet": str(thread.get("channel_type") or "")[:240],
        "source": "octop",
        "updated_at": str(thread.get("last_active") or thread.get("created_at") or ""),
        "agent_id": agent_id,
    }


def _octop_list(spec: Any, timeout: float, query: str = "") -> Any:
    token = _token(spec)
    if not token:
        return _auth_gap(spec, "list")
    timeout_s = min(float(timeout or R._OPERATE_TIMEOUT_S), 10.0)
    result = R.http_json(
        "GET",
        f"{_base(spec)}/api/agents",
        headers=_octop_headers(spec),
        timeout=timeout_s,
    )
    if result.status in R._AUTH:
        return _auth_gap(spec, "list")
    if result.status not in R._UP:
        return R.OperateResult(
            remote=spec.id,
            op="list",
            ok=False,
            detail=result.error or f"Octop list failed (http {result.status})",
            http_status=result.status,
            data=result.body or result.text,
        )
    published = [_publish_agent(row) for row in _agent_rows(result.body)]
    agents = [row for row in published if _matches_query(row, query)]
    sessions: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout_s
    fetched = 0
    # Thread titles are searchable even when the agent row itself does not
    # match. The cap still bounds how many agent thread lists we hit.
    for row in published:
        if fetched >= _THREAD_FETCH_CAP or time.monotonic() > deadline - 0.4:
            break
        agent_id = _safe_id(row.get("agent_id"))
        if not agent_id:
            continue
        remaining = max(0.4, min(3.0, deadline - time.monotonic()))
        for thread in _octop_threads(spec, agent_id, remaining):
            if (
                query
                and not _matches_query(row, query)
                and not _matches_query(thread, query)
            ):
                continue
            item = _session_row(agent_id, thread)
            if item is not None:
                sessions.append(item)
        fetched += 1
    return R.OperateResult(
        remote=spec.id,
        op="list",
        ok=True,
        detail=(
            f"Octop listed {len(agents)} agent(s) via GET /api/agents — rows are Octop "
            "agents (experts and AgentTeams stay inside Octop); send resumes on "
            "agent_id:thread_id"
        ),
        http_status=result.status,
        data={
            "agents": agents,
            "rows_are": "agents",
            "resume_key": "agent_id:thread_id",
            "sessions": sessions,
            "source": "octop",
        },
    )


def _octop_new_state() -> dict[str, Any]:
    return {
        "parts": {},
        "thread_id": "",
        "error": "",
        "gap": "",
        "done": False,
        "saw": False,
    }


def _frame_speaker(frame: dict[str, Any], agent_id: str) -> str:
    raw = frame.get("agent_id")
    if raw in (None, ""):
        raw = frame.get("agent")
    speaker = str(raw or "").strip()
    if not speaker or speaker == agent_id:
        return ""
    return speaker


def _octop_apply_frame(
    state: dict[str, Any], frame: dict[str, Any], agent_id: str
) -> None:
    """Fold one dashboard WS frame into *state*. Stops on the host ``done``."""
    if state.get("done") or not isinstance(frame, dict):
        return
    thread_id = _safe_id(frame.get("thread_id"))
    if thread_id:
        state["thread_id"] = thread_id
    ftype = str(frame.get("type") or "")
    if ftype == "turn_status":
        if frame.get("active") is False and state.get("saw"):
            state["done"] = True
        return
    if ftype == "token":
        state["saw"] = True
        speaker = _frame_speaker(frame, agent_id)
        content = frame.get("content")
        text = (
            content
            if isinstance(content, str)
            else ("" if content is None else str(content))
        )
        parts: dict[str, str] = state["parts"]
        if frame.get("team_snapshot"):
            parts[speaker] = text
        else:
            parts[speaker] = parts.get(speaker, "") + text
        return
    if ftype == "done":
        state["saw"] = True
        if frame.get("team_wrapup"):
            return
        if _frame_speaker(frame, agent_id) == "":
            state["done"] = True
        return
    if ftype == "error":
        state["saw"] = True
        state["done"] = True
        state["error"] = str(frame.get("message") or "Octop returned an error")[:500]
        state["gap"] = "octop_reply_failed"
        return
    if ftype == "hitl_required":
        state["saw"] = True
        state["done"] = True
        state["error"] = (
            "Octop paused this turn for approval in its dashboard. "
            "Finish the approval there, then retry."
        )
        state["gap"] = "octop_approval_required"


def _octop_turn_text(state: dict[str, Any]) -> str:
    parts: dict[str, str] = state.get("parts") or {}
    host = str(parts.get("") or "").strip()
    if host:
        return host
    others = [
        str(text).strip() for key, text in parts.items() if key and str(text).strip()
    ]
    return "\n\n".join(others)


def _ws_url(base_url: str, agent_id: str, token: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("octop base_url must be http or https")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"/api/agents/{quote(agent_id, safe='')}/chat/ws"
    query = urlencode({"token": token})
    return urlunparse((scheme, parsed.netloc, path, "", query, ""))


def _octop_connect(url: str, timeout: float) -> Any:
    from websockets.sync.client import connect

    return connect(
        url,
        open_timeout=min(timeout, 10.0),
        close_timeout=2,
        proxy=None,
        ping_interval=None,
        max_size=8 * 1024 * 1024,
    )


def _octop_read_turn(
    spec: Any, agent_id: str, thread_id: str, prompt: str, timeout: float, token: str
) -> dict[str, Any]:
    url = _ws_url(_base(spec), agent_id, token)
    frame: dict[str, Any] = {"type": "user_turn", "text": prompt}
    if thread_id:
        frame["thread_id"] = thread_id
    state = _octop_new_state()
    if thread_id:
        state["thread_id"] = thread_id
    deadline = time.monotonic() + timeout
    try:
        with _octop_connect(url, timeout) as ws:
            ws.send(json.dumps(frame))
            for _ in range(_MAX_FRAMES):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = ws.recv(timeout=remaining)
                except TimeoutError:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    _octop_apply_frame(state, payload, agent_id)
                if state.get("done"):
                    break
    except Exception as exc:
        message = _redact(f"{type(exc).__name__}: {exc}", token)
        text = _octop_turn_text(state)
        detail = f"Octop chat connection failed ({message})"
        if text:
            detail += f"\n\nPartial reply:\n{text}"
        return {
            "ok": False,
            "detail": detail,
            "gap": "octop_reply_failed",
            "text": text,
            "thread_id": state.get("thread_id") or thread_id,
            "http_status": None,
        }
    text = _octop_turn_text(state)
    resolved_thread = str(state.get("thread_id") or thread_id or "")
    if state.get("gap"):
        return {
            "ok": False,
            "detail": state.get("error") or "Octop turn failed",
            "gap": state["gap"],
            "text": text,
            "thread_id": resolved_thread,
            "http_status": None,
        }
    if not state.get("done"):
        detail = "Octop did not finish the turn before the timeout."
        if text:
            detail += f"\n\nPartial reply:\n{text}"
        return {
            "ok": False,
            "detail": detail,
            "gap": "octop_reply_timeout",
            "text": text,
            "thread_id": resolved_thread,
            "http_status": None,
        }
    if not text:
        return {
            "ok": False,
            "detail": "Octop finished the turn without assistant text.",
            "gap": "octop_reply_empty",
            "text": "",
            "thread_id": resolved_thread,
            "http_status": 200,
        }
    return {
        "ok": True,
        "detail": text,
        "gap": "",
        "text": text,
        "thread_id": resolved_thread,
        "http_status": 200,
    }


def _octop_send(
    spec: Any,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> Any:
    text = (prompt or "").strip()
    if not text:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail="prompt is required",
            gap="octop_prompt_required",
        )
    token = _token(spec)
    if not token:
        return _auth_gap(spec, "send")
    agent_id, thread_id, bad_id = _resolve_target(spec, target, session_id)
    if bad_id:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail="Octop resume key must look like agent_id or agent_id:thread_id.",
            gap="octop_agent_required",
        )
    if not agent_id:
        return R.OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=(
                "Octop send needs an agent id (the list rows are agents). "
                "Pass one as the target, set the remote's agent, or resume "
                "agent_id:thread_id."
            ),
            gap="octop_agent_required",
        )
    timeout_s = float(timeout or R._OPERATE_SEND_TIMEOUT_S)
    outcome = _octop_read_turn(spec, agent_id, thread_id, text, timeout_s, token)
    resolved_thread = _safe_id(outcome.get("thread_id"))
    session_key = f"{agent_id}:{resolved_thread}" if resolved_thread else agent_id
    return R.OperateResult(
        remote=spec.id,
        op="send",
        ok=bool(outcome.get("ok")),
        detail=str(outcome.get("detail") or ""),
        http_status=outcome.get("http_status"),
        gap=str(outcome.get("gap") or ""),
        data={
            "text": outcome.get("text") or "",
            "response": outcome.get("text") or "",
            "session_id": session_key,
            "agent_id": agent_id,
            "thread_id": resolved_thread,
            "source": "octop",
        },
    )
