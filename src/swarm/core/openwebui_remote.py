"""External Open WebUI remote: list chats, resume, stream.

This talks to a self-hosted **Open WebUI** box over HTTP. It is not
Operating Swarm's own WebUI (os-webui) and must never replace it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

_SEND_TIMEOUT_S = 45.0
_MAX_LIST_PAGES = 8
_PAGE_SIZE = 60


def send_timeout(timeout: float) -> float:
    return timeout if timeout >= 30 else _SEND_TIMEOUT_S


def _remotes():
    from swarm.core import remotes as remotes_core

    return remotes_core


def _filter_session_rows(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = (query or "").strip().lower()
    if not needle:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            str(row.get(key) or "") for key in ("id", "title", "snippet", "channel", "thread_ts")
        )
        if needle in blob.lower():
            out.append(row)
    return out


def _chat_rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if not isinstance(body, dict):
        return []
    for key in ("chats", "data", "items", "sessions"):
        val = body.get(key)
        if isinstance(val, list):
            return [item for item in val if isinstance(item, dict)]
    if body.get("id") or body.get("chat_id"):
        return [body]
    return []


def _chat_id(row: dict[str, Any]) -> str:
    nested = row.get("chat") if isinstance(row.get("chat"), dict) else {}
    return str(row.get("id") or row.get("chat_id") or nested.get("id") or "").strip()


def _chat_title(row: dict[str, Any]) -> str:
    nested = row.get("chat") if isinstance(row.get("chat"), dict) else {}
    return str(row.get("title") or nested.get("title") or row.get("name") or "").strip()


def _chat_snippet(row: dict[str, Any]) -> str:
    nested = row.get("chat") if isinstance(row.get("chat"), dict) else {}
    preview = row.get("snippet") or row.get("preview") or nested.get("preview") or ""
    if preview:
        return str(preview).strip()[:240]
    messages = nested.get("messages") if isinstance(nested.get("messages"), list) else row.get("messages")
    if isinstance(messages, list):
        for item in reversed(messages):
            if isinstance(item, dict) and item.get("content"):
                return str(item.get("content") or "").strip()[:240]
    return ""


def _chat_updated(row: dict[str, Any]) -> str:
    nested = row.get("chat") if isinstance(row.get("chat"), dict) else {}
    value = row.get("updated_at") or row.get("updatedAt") or nested.get("updated_at") or ""
    return str(value).strip()


def _session_row(row: dict[str, Any]) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    chat_id = _chat_id(row)
    if not chat_id:
        return None
    title = _chat_title(row) or chat_id
    session = remote_session_from_dict(
        {
            "id": chat_id,
            "title": title,
            "snippet": _chat_snippet(row),
            "source": "openwebui",
            "updated_at": _chat_updated(row),
            "channel": "Open WebUI",
            "thread_ts": chat_id[:64],
        }
    )
    return None if session is None else session.as_dict()


def _auth_detail() -> str:
    return (
        "Open WebUI requires a valid API key. Set remotes.openwebui.api_key or "
        "OPENWEBUI_API_KEY (Open WebUI → Settings → Account → API keys). "
        "This remote is an external Open WebUI instance, not Operating Swarm's WebUI."
    )


def _get_json(spec: Any, path: str, timeout: float) -> Any:
    r = _remotes()
    return r.http_json(
        "GET",
        f"{spec.base_url}{path}",
        headers=r._auth_headers(spec),
        timeout=timeout,
    )


def _list_via_search(spec: Any, query: str, timeout: float) -> Any:
    encoded = urllib.parse.quote(query.strip(), safe="")
    return _get_json(spec, f"/api/v1/chats/search?text={encoded}", timeout)


def _list_page(spec: Any, page: int | None, timeout: float) -> Any:
    if page is None:
        return _get_json(spec, "/api/v1/chats/", timeout)
    return _get_json(spec, f"/api/v1/chats/?page={page}", timeout)


def openwebui_list(spec: Any, timeout: float, query: str = "") -> Any:
    """List Open WebUI chats as resumable sessions. ``query`` filters when many."""
    r = _remotes()
    needle = (query or "").strip()
    result = None
    rows: list[dict[str, Any]] = []
    if needle:
        result = _list_via_search(spec, needle, timeout)
        if result.status in r._UP:
            rows = _chat_rows(result.body)
        elif result.status not in r._AUTH and (result.status is None or result.status == 404):
            result = None
    if result is None:
        result = _list_page(spec, None, timeout)
        if result.status == 404:
            result = _get_json(spec, "/api/chats", timeout)
        if result.status in r._UP:
            rows = _chat_rows(result.body)
            if len(rows) == _PAGE_SIZE:
                for page in range(2, _MAX_LIST_PAGES + 1):
                    extra = _list_page(spec, page, timeout)
                    if extra.status not in r._UP:
                        break
                    more = _chat_rows(extra.body)
                    if not more:
                        break
                    rows.extend(more)
                    if len(more) < _PAGE_SIZE:
                        break
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        session = _session_row(raw)
        if session is None or session["id"] in seen:
            continue
        seen.add(session["id"])
        normalized.append(session)
    if needle and result is not None and result.status in r._UP:
        # Search endpoint may ignore text; always apply a local filter too.
        normalized = _filter_session_rows(normalized, needle)
    data: dict[str, Any] = {"sessions": normalized, "source": "openwebui"}
    if result is not None and result.status in r._UP:
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} Open WebUI chat(s)",
            http_status=result.status,
            data=data,
        )
    if result is not None and result.status in r._AUTH:
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="list",
            ok=False,
            detail=_auth_detail(),
            http_status=result.status,
            data=data,
        )
    return r.OperateResult(
        remote=spec.id or "openwebui",
        op="list",
        ok=False,
        detail=(result.error if result is not None else None)
        or f"Open WebUI list failed (http {getattr(result, 'status', None)})",
        http_status=getattr(result, "status", None),
        data=data,
    )


def _openai_messages(payload: Any) -> list[dict[str, str]]:
    chat = payload.get("chat") if isinstance(payload, dict) else None
    root = chat if isinstance(chat, dict) else payload if isinstance(payload, dict) else {}
    raw = root.get("messages")
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role in ("user", "assistant", "system") and content:
                out.append({"role": role, "content": content})
        if out:
            return out
    history = root.get("history") if isinstance(root.get("history"), dict) else {}
    hist_msgs = history.get("messages")
    if isinstance(hist_msgs, dict):
        for item in hist_msgs.values():
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role in ("user", "assistant", "system") and content:
                out.append({"role": role, "content": content})
    return out


def _chat_model(payload: Any) -> str:
    chat = payload.get("chat") if isinstance(payload, dict) else None
    root = chat if isinstance(chat, dict) else payload if isinstance(payload, dict) else {}
    models = root.get("models") or (payload.get("models") if isinstance(payload, dict) else None) or []
    if isinstance(models, list) and models:
        first = models[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
        if isinstance(first, dict):
            return str(first.get("id") or first.get("name") or "").strip()
    model = root.get("model") or (payload.get("model") if isinstance(payload, dict) else "")
    return str(model or "").strip()


def _first_model(spec: Any, timeout: float) -> str:
    r = _remotes()
    for path in ("/api/models", "/api/v1/models"):
        result = _get_json(spec, path, timeout)
        if result.status not in r._UP:
            continue
        body = result.body
        rows: list[Any] = []
        if isinstance(body, dict):
            rows = body.get("data") or body.get("models") or []
        elif isinstance(body, list):
            rows = body
        for item in rows:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                mid = str(item.get("id") or item.get("name") or "").strip()
                if mid:
                    return mid
    return ""


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


def _delta_from_payload(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        text = str(delta.get("content") or message.get("content") or "")
        if text:
            return text
    return str(payload.get("content") or payload.get("text") or payload.get("response") or "")


def _post_events(
    spec: Any,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Iterator[tuple[dict[str, Any] | None, int | None, str]]:
    r = _remotes()
    req_headers = dict(r._auth_headers(spec))
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
            if status not in r._UP:
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
                    err = str(parsed.get("detail") or parsed.get("error") or parsed.get("message") or "").strip()
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
                yield ({"content": text.strip()}, status, "")
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
            err = str(parsed.get("detail") or parsed.get("error") or parsed.get("message") or "").strip()
        yield (parsed if isinstance(parsed, dict) else None, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        yield (None, None, f"{type(exc).__name__}: {exc}")


def _persist_completed(
    spec: Any,
    *,
    chat_id: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
) -> None:
    r = _remotes()
    r.http_json(
        "POST",
        f"{spec.base_url}/api/chat/completed",
        headers=r._auth_headers(spec),
        body={"chat_id": chat_id, "model": model, "messages": messages, "session_id": "open-swarm"},
        timeout=min(timeout, 8.0),
    )


def iter_openwebui_chat(
    spec: Any,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = _SEND_TIMEOUT_S,
) -> Iterator[tuple[str, bool, str | None]]:
    """Yield ``(delta, done, error)`` from Open WebUI chat completions.

    Resume key is an existing Open WebUI chat id. Never mints a new chat.
    """
    r = _remotes()
    sid = (session_id or target or "").strip()
    if not sid:
        yield (
            "",
            True,
            (
                "Pick an Open WebUI chat. Open Swarm does not mint new chats. "
                "Pass session_id as the chat id (list the remote to see available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = send_timeout(timeout)
    loaded = _get_json(spec, f"/api/v1/chats/{urllib.parse.quote(sid, safe='')}", chat_timeout)
    if loaded.status in r._AUTH:
        yield ("", True, _auth_detail())
        return
    if loaded.status not in r._UP:
        yield (
            "",
            True,
            loaded.error or f"Open WebUI chat {sid} was not found (http {loaded.status})",
        )
        return
    history = _openai_messages(loaded.body)
    model = _chat_model(loaded.body) or _first_model(spec, min(chat_timeout, 8.0))
    if not model:
        yield ("", True, "Open WebUI chat has no model. Pick a model in Open WebUI, then resume.")
        return
    messages = history + [{"role": "user", "content": prompt}]
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "chat_id": sid,
        "session_id": "open-swarm",
    }
    url = f"{spec.base_url}/api/chat/completions"
    assembled = ""
    stream_error = None
    for event, http_status, fail in _post_events(spec, url, body, chat_timeout, accept_sse=True):
        if http_status in r._AUTH:
            yield ("", True, _auth_detail())
            return
        if fail and not event:
            stream_error = fail
            break
        if event is None:
            continue
        gateway = str(event.get("error") or event.get("detail") or "").strip()
        if gateway and gateway.lower() not in ("false", "0"):
            yield ("", True, f"Open WebUI upstream error: {gateway}")
            return
        delta = _delta_from_payload(event)
        if delta:
            assembled += delta
            yield (delta, False, None)
    if assembled:
        persisted = messages + [{"role": "assistant", "content": assembled}]
        _persist_completed(spec, chat_id=sid, model=model, messages=persisted, timeout=chat_timeout)
        yield ("", True, None)
        return
    # Stream empty/missing → synchronous completions.
    sync_body = dict(body)
    sync_body["stream"] = False
    result = r.http_json(
        "POST",
        url,
        headers=r._auth_headers(spec),
        body=sync_body,
        timeout=chat_timeout,
    )
    payload = result.body if isinstance(result.body, dict) else {}
    text = _delta_from_payload(payload) if isinstance(payload, dict) else ""
    if result.status in r._UP and text.strip():
        assembled = text.strip()
        persisted = messages + [{"role": "assistant", "content": assembled}]
        _persist_completed(spec, chat_id=sid, model=model, messages=persisted, timeout=chat_timeout)
        yield (assembled, True, None)
        return
    if result.status in r._AUTH:
        yield ("", True, _auth_detail())
        return
    yield (
        "",
        True,
        stream_error or result.error or f"Open WebUI send failed (http {result.status})",
    )


def openwebui_send(
    spec: Any,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> Any:
    """Send into an existing Open WebUI chat (never mints a new one)."""
    r = _remotes()
    sid = (session_id or target or "").strip()
    if not sid:
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="send",
            ok=False,
            detail=(
                "Pick an Open WebUI chat. Open Swarm does not mint new chats. "
                "Pass session_id as the chat id (list the remote to see available sessions)."
            ),
            gap="openwebui_chat_required",
        )
    if not prompt.strip():
        return r.OperateResult(
            remote=spec.id or "openwebui", op="send", ok=False, detail="prompt is required"
        )
    assembled = ""
    error = None
    for delta, done, err in iter_openwebui_chat(
        spec, prompt, session_id=sid, target=target, timeout=timeout
    ):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    if assembled and not error:
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="send",
            ok=True,
            detail=f"Open WebUI replied in chat {sid}",
            http_status=200,
            data={"response": assembled, "chat_id": sid},
        )
    if error and "API key" in error:
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
            gap="openwebui_auth",
        )
    if error and error.startswith("Open WebUI upstream error:"):
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="send",
            ok=False,
            detail=error,
            data={"error": error},
        )
    if error == "prompt is required":
        return r.OperateResult(
            remote=spec.id or "openwebui", op="send", ok=False, detail=error
        )
    if error and "does not mint" in error:
        return r.OperateResult(
            remote=spec.id or "openwebui",
            op="send",
            ok=False,
            detail=error,
            gap="openwebui_chat_required",
        )
    return r.OperateResult(
        remote=spec.id or "openwebui",
        op="send",
        ok=False,
        detail=error or "Open WebUI send failed",
        data={"chat_id": sid},
    )
