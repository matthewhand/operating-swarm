"""#812 slice 5 — Letta impl bodies, moved verbatim out of
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

__all__ = ['_letta_agents_payload', '_letta_assistant_text', '_letta_delta', '_letta_list', '_letta_post_events', '_letta_send', '_letta_session_row', '_letta_text_from_content', 'filter_letta_sessions', 'iter_letta_chat']


def filter_letta_sessions(rows: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    """Search Letta agent-session rows by id/title/snippet/channel."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            str(row.get(key) or "")
            for key in ("id", "title", "snippet", "channel", "thread_ts")
        ).lower()
        if needle in blob:
            out.append(row)
    return out


def _letta_agents_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        nested = body.get("agents") or body.get("data") or body.get("items") or []
        return nested if isinstance(nested, list) else []
    return []


def _letta_text_from_content(content: Any, *, strip: bool = False) -> str:
    if isinstance(content, str):
        return content.strip() if strip else content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip() if strip else item
                if text is not None:
                    parts.append(text)
            elif isinstance(item, dict):
                raw = item.get("text") or item.get("content")
                if raw is None:
                    continue
                text = str(raw).strip() if strip else str(raw)
                if text is not None:
                    parts.append(text)
        return "\n".join(parts).strip() if strip else "\n".join(parts)
    if isinstance(content, dict):
        raw = content.get("text") or content.get("content")
        if raw is None:
            return ""
        return str(raw).strip() if strip else str(raw)
    return ""


def _letta_assistant_text(payload: Any, *, strip: bool = False) -> str:
    """Pull visible assistant text out of a Letta messages response."""
    messages: list[Any]
    if isinstance(payload, dict):
        messages = payload.get("messages") or payload.get("data") or []
        if not isinstance(messages, list):
            messages = []
        if not messages and (payload.get("message_type") or payload.get("content")):
            messages = [payload]
    elif isinstance(payload, list):
        messages = payload
    else:
        messages = []
    parts: list[str] = []
    reasoning_parts: list[str] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("message_type") or item.get("role") or "").strip().lower()
        if kind in ("user_message", "user", "system_message", "system"):
            continue
        if kind in ("assistant_message", "assistant", "") or "assistant" in kind:
            text = _letta_text_from_content(item.get("content") or item.get("text"), strip=strip)
            if text is not None:
                parts.append(text)
                continue
        if kind == "reasoning_message":
            reasoning = str(item.get("reasoning") or "").strip()
            if reasoning:
                reasoning_parts.append(reasoning)
    if parts:
        return "\n".join(parts).strip() if strip else "\n".join(parts)
    return "\n".join(reasoning_parts).strip()


def _letta_session_row(agent: dict[str, Any]) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    agent_id = str(agent.get("id") or agent.get("agent_id") or "").strip()
    if not agent_id:
        return None
    name = str(agent.get("name") or agent.get("title") or agent_id).strip()
    snippet = str(agent.get("description") or agent.get("snippet") or "").strip()
    agent_type = str(agent.get("agent_type") or agent.get("type") or "").strip()
    session = remote_session_from_dict(
        {
            "id": agent_id,
            "title": name,
            "snippet": snippet[:240],
            "source": "letta",
            "updated_at": str(
                agent.get("updated_at") or agent.get("last_run_completion") or agent.get("created_at") or ""
            ).strip(),
            "channel": (agent_type or "agent")[:128],
            "thread_ts": agent_id[:64],
        }
    )
    return None if session is None else session.as_dict()


def _letta_list(spec: RemoteSpec, timeout: float, query: str = "") -> OperateResult:
    """List Letta agents as searchable, resumable sessions.

    GET /v1/agents/ returns memory agents (and workflow agents). Each agent is
    a resume key — send never mints a new one. ``query`` is passed as
    ``query_text`` and also applied client-side on title/id/snippet.
    """
    needle = (query or "").strip()
    path = f"{spec.base_url}/v1/agents/?limit=200"
    if needle:
        path += f"&query_text={quote(needle)}"
    result = R.http_json("GET", path, headers=R._auth_headers(spec), timeout=timeout)
    agents = _letta_agents_payload(result.body)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        row = _letta_session_row(agent)
        if row is None or row["id"] in seen:
            continue
        seen.add(row["id"])
        normalized.append(row)
    normalized = filter_letta_sessions(normalized, needle)
    data: dict[str, Any] = {"sessions": normalized, "source": "letta"}
    if result.status in R._UP:
        return R.OperateResult(
            remote=spec.id or "letta",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} Letta agent session(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote=spec.id or "letta",
            op="list",
            ok=False,
            detail=(
                "Letta /v1/agents/ requires a valid API key. "
                "Set remotes.letta.api_key or LETTA_API_KEY "
                "(self-hosted password, or Letta Cloud token)."
            ),
            http_status=result.status,
            data=data,
        )
    return R.OperateResult(
        remote=spec.id or "letta",
        op="list",
        ok=False,
        detail=result.error or f"Letta list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )



def _letta_post_events(
    spec: R.RemoteSpec,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Any:
    """Yield ``(event_dict|None, http_status, error)`` from stream or JSON."""
    req_headers = dict(R._auth_headers(spec))
    req_headers.setdefault("Content-Type", "application/json")
    if accept_sse:
        req_headers["Accept"] = "text/event-stream, application/json"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            if status not in R._UP:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace") if raw else ""
                parsed: Any = None
                if text.strip():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                err = ""
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or parsed.get("detail") or parsed.get("message") or "").strip()
                yield (parsed if isinstance(parsed, dict) else None, status, err or f"http {status}")
                return
            if "event-stream" in ctype:
                buf = b""
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        event = R._parse_sse_json_line(line.decode("utf-8", errors="replace"))
                        if event is not None:
                            yield (event, status, "")
                return
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
            if text.lstrip().startswith("data:"):
                for line in text.splitlines():
                    event = R._parse_sse_json_line(line)
                    if event is not None:
                        yield (event, status, "")
                return
            parsed = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            if parsed is not None:
                yield (parsed if isinstance(parsed, dict) else {"messages": parsed}, status, "")
            elif text.strip():
                yield ({"content": text.strip(), "message_type": "assistant_message"}, status, "")
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        err = ""
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or parsed.get("detail") or parsed.get("message") or "").strip()
        yield (parsed if isinstance(parsed, dict) else None, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        yield (None, None, f"{type(exc).__name__}: {exc}")


def _letta_delta(payload: dict[str, Any], assembled: str) -> str:
    kind = str(payload.get("message_type") or payload.get("role") or "").strip().lower()
    if kind in ("reasoning_message", "tool_call_message", "tool_return_message", "ping"):
        return ""
    text = _letta_assistant_text(payload, strip=False)
    if text is None:
        text = _letta_text_from_content(payload.get("content") or payload.get("text"), strip=False)
    if not text:
        return ""
    if assembled and text.startswith(assembled):
        return text[len(assembled) :]
    if assembled and assembled.endswith(text):
        return ""
    return text


def iter_letta_chat(
    spec: R.RemoteSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = R._LETTA_SEND_TIMEOUT_S,
) -> Any:
    """Yield ``(delta, done, error)`` from Letta stream, with sync fallback.

    Resume key is an existing Letta agent id. Never mints a new agent.
    """
    sid = (session_id or target or "").strip()
    if not sid:
        yield (
            "",
            True,
            (
                "Pick a Letta agent. Open Swarm does not mint new agents. "
                "Pass session_id as the agent id (list the remote to see "
                "available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = timeout if timeout >= 30 else R._LETTA_SEND_TIMEOUT_S
    encoded = quote(sid, safe="")
    stream_url = f"{spec.base_url}/v1/agents/{encoded}/messages/stream"
    sync_url = f"{spec.base_url}/v1/agents/{encoded}/messages"
    body = {"messages": [{"role": "user", "content": prompt}]}
    assembled = ""
    error = None
    stream_ok = False
    for event, http_status, fail in _letta_post_events(
        spec, stream_url, {**body, "stream_tokens": True}, chat_timeout, accept_sse=True
    ):
        if fail:
            error = fail
            break
        if http_status in R._AUTH:
            yield ("", True, "Letta chat requires a valid API key (LETTA_API_KEY).")
            return
        if http_status in R._UP:
            stream_ok = True
        if event is None:
            continue
        gateway_error = str(event.get("error") or event.get("detail") or "").strip()
        if gateway_error and gateway_error.lower() not in ("false", "0"):
            yield ("", True, f"Letta upstream error: {gateway_error}")
            return
        delta = _letta_delta(event, assembled)
        if delta:
            assembled += delta
            yield (delta, False, None)
    if assembled and not error:
        yield ("", True, None)
        return
    if stream_ok:
        yield ("", True, "Letta returned an empty reply.")
        return
    result = R.http_json(
        "POST",
        sync_url,
        headers=R._auth_headers(spec),
        body=body,
        timeout=chat_timeout,
    )
    text_response = _letta_assistant_text(result.body, strip=True)
    gateway_error = ""
    if isinstance(result.body, dict):
        gateway_error = str(result.body.get("error") or result.body.get("detail") or "").strip()
    if result.status in R._UP and text_response:
        delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
        if delta:
            yield (delta, True, None)
        else:
            yield ("", True, None)
        return
    if result.status in R._AUTH:
        yield ("", True, "Letta chat requires a valid API key (LETTA_API_KEY).")
        return
    if result.status == 404:
        yield (
            "",
            True,
            f"Letta agent '{sid}' was not found. List sessions and pick an existing agent.",
        )
        return
    if gateway_error:
        yield ("", True, f"Letta upstream error: {gateway_error}")
        return
    yield (
        "",
        True,
        error or result.error or f"Letta send failed (http {result.status})",
    )


def _letta_send(
    spec: R.RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> R.OperateResult:
    """Send into an existing Letta agent (never mints a new one)."""
    sid = (session_id or target or "").strip()
    if not sid:
        return R.OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=False,
            detail=(
                "Pick a Letta agent. Open Swarm does not mint new agents. "
                "Pass session_id as the agent id (list the remote to see "
                "available sessions)."
            ),
            gap="letta_agent_required",
        )
    if not prompt.strip():
        return R.OperateResult(remote=spec.id or "letta", op="send", ok=False, detail="prompt is required")
    assembled = ""
    error = None
    http_status: int | None = None
    for delta, done, err in iter_letta_chat(spec, prompt, session_id=sid, timeout=timeout):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    if assembled and not error:
        return R.OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=True,
            detail=f"Letta replied in agent {sid}",
            http_status=http_status or 200,
            data={"response": assembled, "agent": sid, "thread": sid},
        )
    if error and "API key" in error:
        return R.OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
        )
    if error and "not found" in error.lower():
        return R.OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=False,
            detail=error,
            http_status=404,
            gap="letta_agent_required",
        )
    return R.OperateResult(
        remote=spec.id or "letta",
        op="send",
        ok=False,
        detail=error or "Letta send failed",
        http_status=http_status,
    )


