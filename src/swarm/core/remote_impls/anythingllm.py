"""#812 slice 5 — AnythingLLM impl bodies, moved verbatim out of
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

__all__ = ['_anythingllm_chat_body', '_anythingllm_chat_urls', '_anythingllm_delta', '_anythingllm_fetch_threads', '_anythingllm_list', '_anythingllm_post_events', '_anythingllm_send', '_anythingllm_session_row', '_anythingllm_split_session', '_anythingllm_threads_payload', '_parse_sse_json_line', 'filter_anythingllm_sessions', 'iter_anythingllm_chat']


def filter_anythingllm_sessions(
    rows: list[dict[str, Any]], query: str = ""
) -> list[dict[str, Any]]:
    """Client-or-server search over AnythingLLM workspace/thread session rows."""
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


def _anythingllm_threads_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        nested = body.get("threads") or body.get("data") or body.get("items") or []
        return nested if isinstance(nested, list) else []
    return []


def _anythingllm_fetch_threads(
    spec: R.RemoteSpec, ws_slug: str, timeout: float
) -> list[Any]:
    result = R.http_json(
        "GET",
        f"{spec.base_url}/api/v1/workspace/{ws_slug}/threads",
        headers=R._auth_headers(spec),
        timeout=timeout,
    )
    if result.status not in R._UP:
        return []
    return _anythingllm_threads_payload(result.body)


def _anythingllm_session_row(
    *,
    session_id: str,
    title: str,
    snippet: str,
    channel: str,
    thread_ts: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    session = remote_session_from_dict(
        {
            "id": session_id,
            "title": title,
            "snippet": snippet,
            "source": "anythingllm",
            "updated_at": updated_at,
            "channel": channel[:128],
            "thread_ts": thread_ts[:64],
        }
    )
    return None if session is None else session.as_dict()


def _anythingllm_list(
    spec: R.RemoteSpec, timeout: float, query: str = ""
) -> R.OperateResult:
    """List AnythingLLM workspaces and threads as searchable, resumable sessions.

    GET /api/v1/workspaces returns each workspace (optional nested ``threads``).
    A workspace itself is a session (id = slug) so the main chat can be resumed.
    Each thread is ``workspace:thread``. Missing nested threads fall back to
    GET /api/v1/workspace/<slug>/threads. ``query`` filters title/id/channel.
    """
    result = R.http_json(
        "GET",
        f"{spec.base_url}/api/v1/workspaces",
        headers=R._auth_headers(spec),
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
    seen: set[str] = set()
    for ws in workspaces:
        if not isinstance(ws, dict):
            continue
        ws_slug = str(ws.get("slug") or ws.get("id") or "").strip()
        ws_name = str(ws.get("name") or ws_slug or "workspace").strip()
        if not ws_slug:
            continue
        workspace_row = _anythingllm_session_row(
            session_id=ws_slug,
            title=ws_name,
            snippet="workspace",
            channel=ws_name,
            updated_at=str(ws.get("updatedAt") or ws.get("lastUpdatedAt") or "").strip(),
        )
        if workspace_row is not None and ws_slug not in seen:
            seen.add(ws_slug)
            normalized.append(workspace_row)
        threads = ws.get("threads")
        if not isinstance(threads, list) or not threads:
            threads = _anythingllm_fetch_threads(spec, ws_slug, timeout)
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            thread_slug = str(thread.get("slug") or thread.get("id") or "").strip()
            if not thread_slug:
                continue
            sid = f"{ws_slug}:{thread_slug}"
            if sid in seen:
                continue
            row = _anythingllm_session_row(
                session_id=sid,
                title=str(thread.get("name") or f"{ws_name} thread").strip(),
                snippet=ws_name,
                channel=ws_name,
                thread_ts=thread_slug,
                updated_at=str(thread.get("updatedAt") or thread.get("updated_at") or "").strip(),
            )
            if row is None:
                continue
            seen.add(sid)
            normalized.append(row)
    normalized = filter_anythingllm_sessions(normalized, query)
    data: dict[str, Any] = {"sessions": normalized, "source": "anythingllm"}
    if result.status in R._UP:
        return R.OperateResult(
            remote="anythingllm",
            op="list",
            ok=True,
            detail=(
                f"listed {len(normalized)} AnythingLLM session(s) across "
                f"{len(workspaces)} workspace(s)"
            ),
            http_status=result.status,
            data=data,
        )
    if result.status in R._AUTH:
        return R.OperateResult(
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
    return R.OperateResult(
        remote="anythingllm",
        op="list",
        ok=False,
        detail=result.error or f"AnythingLLM list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _anythingllm_split_session(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    if ":" in sid:
        ws_slug, _, thread_slug = sid.partition(":")
        return ws_slug.strip(), thread_slug.strip()
    return sid, ""


def _anythingllm_chat_urls(spec: RemoteSpec, ws_slug: str, thread_slug: str) -> tuple[str, str]:
    base = f"{spec.base_url}/api/v1/workspace/{ws_slug}"
    if thread_slug:
        return f"{base}/thread/{thread_slug}/stream-chat", f"{base}/thread/{thread_slug}/chat"
    return f"{base}/stream-chat", f"{base}/chat"


def _anythingllm_chat_body(prompt: str, ws_slug: str, thread_slug: str) -> dict[str, Any]:
    body: dict[str, Any] = {"message": prompt, "mode": "chat"}
    if not thread_slug and ws_slug:
        # Workspace-level resume: AnythingLLM keys history by sessionId.
        body["sessionId"] = ws_slug
    return body


def _parse_sse_json_line(line: str) -> dict[str, Any] | None:
    text = (line or "").strip()
    if not text or text == "[DONE]":
        return None
    if text.startswith("data:"):
        text = text[5:].strip()
        if not text or text == "[DONE]":
            return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _anythingllm_delta(payload: dict[str, Any], assembled: str) -> str:
    text = str(payload.get("textResponse") or payload.get("text") or payload.get("content") or "")
    if not text:
        return ""
    if assembled and text.startswith(assembled):
        return text[len(assembled) :]
    if assembled and assembled.endswith(text):
        return ""
    return text


def iter_anythingllm_chat(
    spec: R.RemoteSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = R._ANYTHINGLLM_SEND_TIMEOUT_S,
) -> Any:
    """Yield ``(delta, done, error)`` from AnythingLLM stream-chat (sync fallback).

    Resume key is a workspace slug (main workspace chat) or ``workspace:thread``.
    Never mints a new thread.
    """
    sid = (session_id or target or "").strip()
    ws_slug, thread_slug = _anythingllm_split_session(sid)
    if not ws_slug:
        yield (
            "",
            True,
            (
                "Pick an AnythingLLM workspace or thread. Operating Swarm does not mint "
                "new threads. Pass session_id as workspace or workspace:thread "
                "(list the remote to see available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = timeout if timeout >= 30 else R._ANYTHINGLLM_SEND_TIMEOUT_S
    stream_url, sync_url = _anythingllm_chat_urls(spec, ws_slug, thread_slug)
    body = _anythingllm_chat_body(prompt, ws_slug, thread_slug)
    assembled = ""
    error = None
    done = False
    for event, http_status, fail in _anythingllm_post_events(
        spec, stream_url, body, chat_timeout, accept_sse=True
    ):
        if fail:
            error = fail
            break
        if http_status in R._AUTH:
            yield ("", True, "AnythingLLM chat requires a valid API key (Settings → API keys).")
            return
        if event is None:
            continue
        gateway_error = str(event.get("error") or "").strip()
        if gateway_error and gateway_error.lower() not in ("false", "0"):
            yield ("", True, f"AnythingLLM upstream error: {gateway_error}")
            return
        delta = _anythingllm_delta(event, assembled)
        if delta:
            assembled += delta
            close = bool(event.get("close"))
            yield (delta, close, None)
            if close:
                done = True
                break
        elif bool(event.get("close")):
            done = True
            yield ("", True, None)
            break
    if done:
        return
    if assembled and not error:
        yield ("", True, None)
        return
    # stream-chat missing/empty → synchronous thread/workspace chat.
    result = R.http_json(
        "POST",
        sync_url,
        headers=R._auth_headers(spec),
        body=body,
        timeout=chat_timeout,
    )
    payload = result.body if isinstance(result.body, dict) else {}
    text_response = str(payload.get("textResponse") or payload.get("text") or "").strip()
    gateway_error = str(payload.get("error") or "").strip()
    if result.status in R._UP and text_response:
        delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
        if delta:
            yield (delta, True, None)
        else:
            yield ("", True, None)
        return
    if result.status in R._AUTH:
        yield ("", True, "AnythingLLM chat requires a valid API key (Settings → API keys).")
        return
    if gateway_error:
        yield ("", True, f"AnythingLLM upstream error: {gateway_error}")
        return
    yield (
        "",
        True,
        error or result.error or f"AnythingLLM send failed (http {result.status})",
    )



def _anythingllm_post_events(
    spec: R.RemoteSpec,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Any:
    """Yield ``(event_dict|None, http_status, error)`` from stream-chat or JSON."""
    started = time.monotonic()
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
                    err = str(parsed.get("error") or parsed.get("message") or "").strip()
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
                        event = _parse_sse_json_line(line.decode("utf-8", errors="replace"))
                        if event is not None:
                            yield (event, status, "")
                return
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
            if text.lstrip().startswith("data:"):
                for line in text.splitlines():
                    event = _parse_sse_json_line(line)
                    if event is not None:
                        yield (event, status, "")
                return
            parsed = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            if isinstance(parsed, dict):
                yield (parsed, status, "")
            elif text.strip():
                yield ({"textResponse": text.strip()}, status, "")
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
        yield (parsed if isinstance(parsed, dict) else None, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        _ = started
        yield (None, None, f"{type(exc).__name__}: {exc}")


def _anythingllm_send(
    spec: R.RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> R.OperateResult:
    """Send into an existing AnythingLLM workspace or thread (never mints a new one).

    ``session_id`` is a workspace slug (main chat) or ``workspace:thread``.
    Prefers POST .../stream-chat and falls back to .../chat. AnythingLLM
    ``error`` bodies surface, never faked.
    """
    sid = (session_id or target or "").strip()
    ws_slug, thread_slug = _anythingllm_split_session(sid)
    if not ws_slug:
        return R.OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=(
                "Pick an AnythingLLM workspace or thread. Operating Swarm does not mint "
                "new threads. Pass session_id as workspace or workspace:thread "
                "(list the remote to see available sessions)."
            ),
            gap="anythingllm_thread_required",
        )
    if not prompt.strip():
        return R.OperateResult(remote="anythingllm", op="send", ok=False, detail="prompt is required")
    assembled = ""
    error = None
    http_status: int | None = None
    for delta, done, err in iter_anythingllm_chat(
        spec, prompt, session_id=sid, timeout=timeout
    ):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    label = thread_slug or ws_slug
    if assembled and not error:
        return R.OperateResult(
            remote="anythingllm",
            op="send",
            ok=True,
            detail=f"AnythingLLM replied in {label}",
            http_status=http_status or 200,
            data={"response": assembled, "thread": sid},
        )
    if error and "API key" in error:
        return R.OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
        )
    if error and error.startswith("AnythingLLM upstream error:"):
        return R.OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=error,
            data={"error": error},
        )
    if error and error == "prompt is required":
        return R.OperateResult(remote="anythingllm", op="send", ok=False, detail=error)
    if error and "does not mint" in error:
        return R.OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=error,
            gap="anythingllm_thread_required",
        )
    return R.OperateResult(
        remote="anythingllm",
        op="send",
        ok=False,
        detail=error or "AnythingLLM send failed",
    )


