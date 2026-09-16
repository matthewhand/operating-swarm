"""#812 slice 5 — nested-swarm (kind ``swarm``) impl bodies, moved
verbatim out of ``swarm.core.remotes``. References to other moved
names go through ``R`` (the remotes module object) so monkeypatching
on ``remotes`` still lands: behaviorally this is the same code.
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
    from swarm.core.remotes import HttpResult, OperateResult, RemoteSpec

R: Any = importlib.import_module("swarm.core.remotes")

__all__ = ['_swarm_agents_from_body', '_swarm_list', '_swarm_send', '_swarm_try_get']


def _swarm_try_get(spec: RemoteSpec, paths: tuple[str, ...], timeout: float) -> HttpResult:
    last = R.HttpResult(status=None, error="no paths")
    for path in paths:
        last = R.http_json("GET", f"{spec.base_url}{path}", headers=R._auth_headers(spec), timeout=timeout)
        if last.status in R._UP or last.status in R._AUTH:
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


def _swarm_auth_hint(spec: RemoteSpec) -> str:
    env_key = spec.api_key_env or R._ENV_KEY.get("swarm") or "SWARM_REMOTE_API_KEY"
    return (
        "OS-peer list/send requires Bearer auth against the child's /v1 surface. "
        f"Set remotes.{spec.id}.api_key or {env_key} (env var name only). "
        "On the child: API_AUTH_TOKEN or SWARM_API_KEY (see docs/AUTH.md)."
    )


def _swarm_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    """List child agents, sessions, and teams on a nested OS-peer."""
    from swarm.core.swarm_peer import (
        LIST_AGENT_PATHS,
        LIST_SESSION_PATHS,
        LIST_TEAM_PATHS,
        items_from_body,
        members_from_agents,
    )

    remote_id = spec.id or "swarm"
    agents_result = _swarm_try_get(spec, LIST_AGENT_PATHS, timeout)
    path = (agents_result.headers or {}).get("x-swarm-path", LIST_AGENT_PATHS[0])
    if agents_result.status in R._AUTH:
        return R.OperateResult(
            remote=remote_id,
            op="list",
            ok=False,
            detail=_swarm_auth_hint(spec),
            http_status=agents_result.status,
            data=agents_result.body,
        )
    if agents_result.status not in R._UP:
        return R.OperateResult(
            remote=remote_id,
            op="list",
            ok=False,
            detail=agents_result.error or f"OS-peer list failed (http {agents_result.status})",
            http_status=agents_result.status,
            data=agents_result.body or agents_result.text,
        )
    agents = items_from_body(agents_result.body, "data", "blueprints", "models")
    sessions_result = _swarm_try_get(spec, LIST_SESSION_PATHS, timeout)
    sessions = (
        items_from_body(sessions_result.body, "sessions", "data")
        if sessions_result.status in R._UP
        else []
    )
    teams_result = _swarm_try_get(spec, LIST_TEAM_PATHS, timeout)
    teams: list[Any] = []
    if teams_result.status in R._UP:
        body = teams_result.body
        if isinstance(body, dict):
            members = body.get("members") or body.get("team_members")
            if isinstance(members, list):
                teams = list(members)
            else:
                teams = items_from_body(body, "data", "teams")
        elif isinstance(body, list):
            teams = list(body)
    return R.OperateResult(
        remote=remote_id,
        op="list",
        ok=True,
        detail=(
            f"OS-peer listed {len(agents)} agent(s), {len(sessions)} session(s), "
            f"{len(teams)} team(s) via GET {path}"
        ),
        http_status=agents_result.status,
        data={
            "agents": agents,
            "sessions": sessions,
            "teams": teams,
            "members": members_from_agents(agents, remote=remote_id),
            "path": path,
            "raw": agents_result.body,
        },
    )


def _swarm_send(
    spec: RemoteSpec,
    prompt: str,
    target: str,
    timeout: float,
    *,
    session_id: str | None = None,
) -> OperateResult:
    """Send one chat turn to a child OS-peer via POST /v1/chat/completions/."""
    from swarm.core.swarm_peer import SEND_PATHS, agent_id, extract_completion_text

    remote_id = spec.id or "swarm"
    if not prompt.strip():
        return R.OperateResult(remote=remote_id, op="send", ok=False, detail="prompt is required")
    model = (target or "").strip()
    headers = R._auth_headers(spec)
    listed: R.OperateResult | None = None
    if not model:
        listed = _swarm_list(spec, timeout)
        if listed.ok and isinstance(listed.data, dict):
            agents = listed.data.get("agents") or []
            if isinstance(agents, list) and agents:
                model = agent_id(agents[0])
        if not model:
            return R.OperateResult(
                remote=remote_id,
                op="send",
                ok=False,
                detail="Need a child blueprint id (target) or a working list.",
                http_status=listed.http_status,
                data=listed.data,
            )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if session_id:
        payload["conversation_id"] = session_id
    last = R.HttpResult(status=None, error="no paths")
    for path in SEND_PATHS:
        last = R.http_json(
            "POST",
            f"{spec.base_url}{path}",
            headers=headers,
            body=payload,
            timeout=timeout,
        )
        if last.status in R._UP:
            return R.OperateResult(
                remote=remote_id,
                op="send",
                ok=True,
                detail=f"sent OS-peer turn via POST {path} model={model}",
                http_status=last.status,
                data={
                    "model": model,
                    "response": last.body or last.text,
                    "text": extract_completion_text(last.body),
                    "session_id": session_id or "",
                },
            )
        if last.status == 403 and _looks_like_csrf_rejection(last):
            # #1191: keyless parent + CSRF-enforcing child. Django folds CSRF
            # failures into 403 — distinguish them from real auth refusals by
            # body, dance browser-style, and only then treat 403 as auth.
            for dance_path in SEND_PATHS:
                danced = _swarm_csrf_dance_post(
                    spec, f"{spec.base_url}{dance_path}", payload, timeout
                )
                if danced.status in R._UP:
                    return R.OperateResult(
                        remote=remote_id,
                        op="send",
                        ok=True,
                        detail=(
                            f"sent OS-peer turn via CSRF dance POST {dance_path} model={model}"
                        ),
                        http_status=danced.status,
                        data={
                            "model": model,
                            "response": danced.body or danced.text,
                            "text": extract_completion_text(danced.body),
                            "session_id": session_id or "",
                        },
                    )
            last = danced
        if last.status in R._AUTH and not _looks_like_csrf_rejection(last):
            return R.OperateResult(
                remote=remote_id,
                op="send",
                ok=False,
                detail=_swarm_auth_hint(spec),
                http_status=last.status,
                data=last.body,
            )
        # #1191: a 403 that is really CSRF (or a failed dance) falls through to
        # the honest final return below — the child's answer is the truth.
    # #1191: prefer the child's own error message over a generic label.
    child_detail = ""
    if isinstance(last.body, dict) and last.body.get("detail"):
        child_detail = str(last.body["detail"])
    return R.OperateResult(
        remote=remote_id,
        op="send",
        ok=False,
        detail=last.error or child_detail or f"OS-peer send failed (http {last.status})",
        http_status=last.status,
        data=last.body or last.text,
    )


def _looks_like_csrf_rejection(result: HttpResult) -> bool:
    text = (result.text or "") + json.dumps(result.body) if isinstance(result.body, dict) else (result.text or "")
    return "CSRF" in text


def _swarm_csrf_dance_post(
    spec: RemoteSpec, url: str, payload: dict[str, Any], timeout: float
) -> HttpResult:
    """Browser-equivalent CSRF dance: collect the child's csrftoken cookie
    from GET /, then POST with the cookie jar plus X-CSRFToken and Referer.
    Uses a cookie-aware opener (http_json is one-shot, jar-less)."""
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar)
    )
    try:
        with opener.open(urllib.request.Request(f"{spec.base_url.rstrip('/')}/"), timeout=timeout) as resp:
            resp.read()
    except (urllib.error.URLError, OSError):
        return R.HttpResult(status=None, error="CSRF dance: could not fetch token page")
    token = ""
    for cookie in jar:
        if cookie.name == "csrftoken":
            token = cookie.value
            break
    if not token:
        return R.HttpResult(status=None, error="CSRF dance: child issued no csrftoken cookie")
    headers = {
        **R._auth_headers(spec),
        "Content-Type": "application/json",
        "X-CSRFToken": token,
        "Referer": f"{spec.base_url.rstrip('/')}/",
    }
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    started = time.monotonic()
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
            return R.HttpResult(
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
        return R.HttpResult(status=exc.code, body=parsed, text=text, url=url, headers={})
    except (urllib.error.URLError, OSError) as exc:
        return R.HttpResult(status=None, error=f"CSRF dance failed: {exc}")


