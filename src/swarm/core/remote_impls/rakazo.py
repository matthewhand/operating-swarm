"""#812 slice 5 — Rakazo impl bodies, moved verbatim out of
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

__all__ = ['_rakazo_list', '_rakazo_rpc', '_rakazo_send']


def _rakazo_rpc(spec: RemoteSpec, path: str, payload: dict[str, Any], timeout: float) -> HttpResult:
    url = f"{spec.base_url}{path}"
    headers = dict(R._auth_headers(spec))
    headers.setdefault("Content-Type", "application/json")
    started = time.monotonic()
    # httpx so respx can mock CI; never log header values.
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json={"json": payload})
        text = resp.text or ""
        parsed: Any = None
        if text.strip():
            try:
                parsed = resp.json()
            except ValueError:
                parsed = None
        return R.HttpResult(
            status=resp.status_code,
            body=parsed,
            text=text,
            error="" if resp.status_code < 400 else f"http {resp.status_code}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
            headers={k.lower(): v for k, v in resp.headers.items()},
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return R.HttpResult(
            status=None,
            error=f"{type(exc).__name__}: {exc}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
        )


def _rakazo_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    result = _rakazo_rpc(spec, "/rpc/bots/list", {}, timeout)
    if result.status in R._UP:
        bots = result.body.get("json") if isinstance(result.body, dict) else result.body
        count = len(bots) if isinstance(bots, list) else "?"
        return R.OperateResult(
            remote="rakazo",
            op="list",
            ok=True,
            detail=f"Rakazo listed {count} bot(s) via POST /rpc/bots/list",
            http_status=result.status,
            data=result.body,
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="rakazo",
            op="list",
            ok=False,
            detail=(
                "Rakazo /rpc/bots/list requires a Better Auth session. "
                "Health (GET /health) is public; R.operate is not. "
                "Export RAKAZO_SESSION_COOKIE and/or RAKAZO_API_KEY "
                "(env/secret-store names only; never persist values)."
            ),
            http_status=result.status,
            data=result.body,
            gap="rakazo_rpc_requires_better_auth_session",
        )
    return R.OperateResult(
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
        return R.OperateResult(remote="rakazo", op="send", ok=False, detail="prompt is required")
    bot_id = (target or "").strip()
    if not bot_id:
        listed = _rakazo_list(spec, timeout)
        if not listed.ok:
            return R.OperateResult(
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
            return R.OperateResult(
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
    if result.status in R._UP:
        return R.OperateResult(
            remote="rakazo",
            op="send",
            ok=True,
            detail=f"sent Rakazo thread via POST /rpc/threads/send (bot {bot_id})",
            http_status=result.status,
            data=result.body,
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="rakazo",
            op="send",
            ok=False,
            detail="Rakazo /rpc/threads/send requires Better Auth. Health still works without it.",
            http_status=result.status,
            data=result.body,
            gap="rakazo_rpc_requires_better_auth_session",
        )
    return R.OperateResult(
        remote="rakazo",
        op="send",
        ok=False,
        detail=R._unreachable_detail(result, "Rakazo send"),
        http_status=result.status,
        data=result.body or result.text,
    )


