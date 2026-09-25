"""#812 slice 5 — Flowise impl bodies, moved verbatim out of
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

__all__ = ['_flowise_chatflows_payload', '_flowise_fetch_messages', '_flowise_list', '_flowise_messages_payload', '_flowise_post_events', '_flowise_send', '_flowise_session_row', '_flowise_split_session', '_flowise_token_text', '_iter_sse_blocks', 'filter_flowise_sessions', 'iter_flowise_chat']


def filter_flowise_sessions(rows: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    """Case-insensitive substring filter over Flowise session rows."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(key) or "")
            for key in ("id", "title", "snippet", "channel", "thread_ts")
        )
        if needle in blob.lower():
            out.append(row)
    return out


def _flowise_chatflows_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("chatflows", "data", "flows"):
            val = body.get(key)
            if isinstance(val, list):
                return val
    return []


def _flowise_messages_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "messages", "chatmessages"):
            val = body.get(key)
            if isinstance(val, list):
                return val
    return []


def _flowise_session_row(
    *,
    session_id: str,
    title: str,
    snippet: str,
    channel: str,
    thread_ts: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    sid = (session_id or "").strip()
    if not sid:
        return None
    session = remote_session_from_dict(
        {
            "id": sid,
            "title": (title or sid).strip() or sid,
            "snippet": (snippet or "").strip(),
            "source": "flowise",
            "updated_at": (updated_at or "").strip(),
            "channel": (channel or "")[:128],
            "thread_ts": (thread_ts or "")[:64],
        }
    )
    return session.as_dict() if session is not None else None


def _flowise_fetch_messages(spec: RemoteSpec, flow_id: str, timeout: float) -> list[Any]:
    result = R.http_json(
        "GET",
        f"{spec.base_url}/api/v1/chatmessage/{flow_id}",
        headers=R._auth_headers(spec),
        timeout=min(float(timeout or R._DEFAULT_TIMEOUT_S), 4.0),
    )
    if result.status not in R._UP:
        return []
    return _flowise_messages_payload(result.body)


def _flowise_list(spec: RemoteSpec, timeout: float, query: str = "") -> OperateResult:
    """List Flowise chatflows and their chat sessions.

    GET /api/v1/chatflows is the catalog. Each flow is a resumable session
    (id = flowId). GET /api/v1/chatmessage/<flowId> groups existing chats
    as flowId:chatId so send can resume instead of minting a new thread.
    """
    headers = R._auth_headers(spec)
    result = R.http_json(
        "GET",
        f"{spec.base_url}/api/v1/chatflows",
        headers=headers,
        timeout=timeout,
    )
    flows = _flowise_chatflows_payload(result.body)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        flow_id = str(flow.get("id") or flow.get("_id") or "").strip()
        if not flow_id or flow_id in seen:
            continue
        seen.add(flow_id)
        flow_name = str(flow.get("name") or flow.get("label") or flow_id).strip() or flow_id
        flow_type = str(flow.get("type") or "CHATFLOW").strip()
        flow_row = _flowise_session_row(
            session_id=flow_id,
            title=flow_name,
            snippet=flow_type,
            channel=flow_name,
            updated_at=str(flow.get("updatedDate") or flow.get("updatedAt") or "").strip(),
        )
        if flow_row is not None:
            normalized.append(flow_row)
        grouped: dict[str, dict[str, str]] = {}
        for msg in _flowise_fetch_messages(spec, flow_id, timeout):
            if not isinstance(msg, dict):
                continue
            chat_id = str(msg.get("chatId") or msg.get("sessionId") or "").strip()
            if not chat_id or chat_id == flow_id:
                continue
            sid = f"{flow_id}:{chat_id}"
            if sid in seen:
                content = str(msg.get("content") or "").strip()
                role = str(msg.get("role") or "").lower()
                if content and role in ("usermessage", "userMessage", "user") and not grouped.get(sid, {}).get("title"):
                    grouped[sid]["title"] = content[:80]
                continue
            seen.add(sid)
            content = str(msg.get("content") or "").strip()
            role = str(msg.get("role") or "")
            title = content[:80] if content and "user" in role.lower() else chat_id
            grouped[sid] = {
                "title": title or chat_id,
                "snippet": content[:160],
                "updated_at": str(msg.get("createdDate") or msg.get("createdAt") or "").strip(),
            }
        for sid, meta in grouped.items():
            _, _, chat_id = sid.partition(":")
            row = _flowise_session_row(
                session_id=sid,
                title=meta.get("title") or chat_id,
                snippet=meta.get("snippet") or "",
                channel=flow_name,
                thread_ts=chat_id,
                updated_at=meta.get("updated_at") or "",
            )
            if row is not None:
                normalized.append(row)
    normalized = filter_flowise_sessions(normalized, query)
    data: dict[str, Any] = {"sessions": normalized, "source": "flowise"}
    if result.status in R._UP:
        return R.OperateResult(
            remote="flowise",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} Flowise flow/session(s) across {len(flows)} flow(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="flowise",
            op="list",
            ok=False,
            detail=(
                "Flowise /api/v1/chatflows requires a valid API key. "
                "Set remotes.flowise.api_key or FLOWISE_API_KEY."
            ),
            http_status=result.status,
            data=data,
        )
    return R.OperateResult(
        remote="flowise",
        op="list",
        ok=False,
        detail=result.error or f"Flowise list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _flowise_split_session(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    if not sid:
        return "", ""
    if ":" in sid:
        flow_id, _, chat_id = sid.partition(":")
        return flow_id.strip(), chat_id.strip()
    return sid, sid


def _flowise_token_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text or text == "[DONE]":
        return ""
    if text[:1] in "{\"[" :
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, dict):
            for key in ("token", "text", "content", "message"):
                val = parsed.get(key)
                if isinstance(val, str) and val:
                    return val
            nested = parsed.get("data")
            if isinstance(nested, str) and nested:
                return nested
            if isinstance(nested, dict):
                inner = nested.get("token") or nested.get("text")
                if isinstance(inner, str):
                    return inner
            return ""
        return ""
    return text


def _iter_sse_blocks(lines: list[str]):
    event_type = "message"
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                yield event_type, "\n".join(data_lines)
            event_type = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
    if data_lines:
        yield event_type, "\n".join(data_lines)



def _flowise_post_events(
    spec: R.RemoteSpec,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Any:
    """Yield ``(event_type, data_text, http_status, error)``."""
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
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
            if status not in R._UP:
                parsed: Any = None
                if text.strip():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                err = ""
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or parsed.get("message") or "").strip()
                yield ("error", text, status, err or f"http {status}")
                return
            if "event-stream" in ctype or text.lstrip().startswith(("event:", "data:")):
                for event_type, payload in _iter_sse_blocks(text.splitlines()):
                    yield (event_type, payload, status, "")
                return
            yield ("json", text, status, "")
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
            err = str(parsed.get("error") or parsed.get("message") or "").strip()
        yield ("error", text, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        yield ("error", "", None, f"{type(exc).__name__}: {exc}")


def iter_flowise_chat(
    spec: R.RemoteSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = R._FLOWISE_SEND_TIMEOUT_S,
) -> Any:
    """Yield ``(delta, done, error)`` from Flowise prediction (SSE then JSON)."""
    sid = (session_id or target or "").strip()
    flow_id, chat_id = _flowise_split_session(sid)
    if not flow_id:
        yield (
            "",
            True,
            (
                "Pick a Flowise flow or chat session. Operating Swarm does not mint "
                "new threads. Pass session_id as flowId or flowId:chatId "
                "(list the remote to see available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = timeout if timeout >= 30 else R._FLOWISE_SEND_TIMEOUT_S
    url = f"{spec.base_url}/api/v1/prediction/{flow_id}"
    body = {
        "question": prompt,
        "chatId": chat_id or flow_id,
        "streaming": True,
        "overrideConfig": {"sessionId": chat_id or flow_id},
    }
    assembled = ""
    error = None
    done = False
    for event_type, payload, http_status, fail in _flowise_post_events(
        spec, url, body, chat_timeout, accept_sse=True
    ):
        if fail:
            error = fail
            break
        if http_status in R._AUTH:
            yield ("", True, "Flowise chat requires a valid API key (FLOWISE_API_KEY).")
            return
        kind = (event_type or "").lower()
        if kind in ("error",) and payload:
            token = _flowise_token_text(payload) or payload.strip()
            yield ("", True, f"Flowise upstream error: {token}")
            return
        if kind in ("end", "complete", "done"):
            done = True
            yield ("", True, None)
            break
        if kind == "json":
            parsed: Any = None
            if payload.strip():
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = None
            text_response = ""
            if isinstance(parsed, dict):
                err = str(parsed.get("error") or parsed.get("message") or "").strip()
                if err and not parsed.get("text") and not parsed.get("token"):
                    yield ("", True, f"Flowise upstream error: {err}")
                    return
                text_response = str(
                    parsed.get("text") or parsed.get("textResponse") or parsed.get("answer") or ""
                ).strip()
            elif payload.strip():
                text_response = payload.strip()
            if text_response:
                delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
                if delta:
                    assembled += delta
                    yield (delta, True, None)
                else:
                    yield ("", True, None)
                done = True
                break
            continue
        if kind in ("token", "message", "data", ""):
            delta = _flowise_token_text(payload)
            if delta:
                assembled += delta
                yield (delta, False, None)
    if done:
        return
    if assembled and not error:
        yield ("", True, None)
        return
    sync_body = dict(body)
    sync_body["streaming"] = False
    result = R.http_json(
        "POST",
        url,
        headers=R._auth_headers(spec),
        body=sync_body,
        timeout=chat_timeout,
    )
    payload = result.body if isinstance(result.body, dict) else {}
    text_response = str(
        payload.get("text") or payload.get("textResponse") or payload.get("answer") or ""
    ).strip()
    gateway_error = str(payload.get("error") or "").strip()
    if result.status in R._UP and text_response:
        delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
        if delta:
            yield (delta, True, None)
        else:
            yield ("", True, None)
        return
    if result.status in R._AUTH:
        yield ("", True, "Flowise chat requires a valid API key (FLOWISE_API_KEY).")
        return
    if gateway_error:
        yield ("", True, f"Flowise upstream error: {gateway_error}")
        return
    yield (
        "",
        True,
        error or result.error or f"Flowise send failed (http {result.status})",
    )


def _flowise_send(
    spec: R.RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> R.OperateResult:
    """Send into an existing Flowise flow or chat session (never mints a new one)."""
    sid = (session_id or target or "").strip()
    flow_id, chat_id = _flowise_split_session(sid)
    if not flow_id:
        return R.OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=(
                "Pick a Flowise flow or chat session. Operating Swarm does not mint "
                "new threads. Pass session_id as flowId or flowId:chatId "
                "(list the remote to see available sessions)."
            ),
            gap="flowise_session_required",
        )
    if not prompt.strip():
        return R.OperateResult(remote="flowise", op="send", ok=False, detail="prompt is required")
    assembled = ""
    error = None
    for delta, done, err in iter_flowise_chat(spec, prompt, session_id=sid, timeout=timeout):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    label = chat_id or flow_id
    if assembled and not error:
        return R.OperateResult(
            remote="flowise",
            op="send",
            ok=True,
            detail=f"Flowise replied in {label}",
            http_status=200,
            data={"response": assembled, "thread": sid, "chatId": chat_id or flow_id},
        )
    if error and "API key" in error:
        return R.OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
        )
    if error and error.startswith("Flowise upstream error:"):
        return R.OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=error,
            data={"error": error},
        )
    if error and error == "prompt is required":
        return R.OperateResult(remote="flowise", op="send", ok=False, detail=error)
    if error and "does not mint" in error:
        return R.OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=error,
            gap="flowise_session_required",
        )
    return R.OperateResult(
        remote="flowise",
        op="send",
        ok=False,
        detail=error or "Flowise send failed",
    )



