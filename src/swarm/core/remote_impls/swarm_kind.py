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
from typing import Any
from urllib.parse import quote, urlparse, urlunparse  # noqa: F401

import httpx

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


def _swarm_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    """List child agents (blueprints / models) on a nested open-swarm."""
    result = _swarm_try_get(
        spec,
        ("/v1/blueprints/", "/v1/blueprints", "/v1/models/", "/v1/models"),
        timeout,
    )
    path = (result.headers or {}).get("x-swarm-path", "/v1/blueprints/")
    if result.status in R._UP:
        agents = _swarm_agents_from_body(result.body)
        return R.OperateResult(
            remote="swarm",
            op="list",
            ok=True,
            detail=f"nested swarm listed {len(agents)} agent(s) via GET {path}",
            http_status=result.status,
            data={"agents": agents, "path": path, "raw": result.body},
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="swarm",
            op="list",
            ok=False,
            detail=(
                "Nested swarm list requires Bearer auth. "
                "Set remotes.swarm.api_key or SWARM_REMOTE_API_KEY (env var name only)."
            ),
            http_status=result.status,
            data=result.body,
        )
    return R.OperateResult(
        remote="swarm",
        op="list",
        ok=False,
        detail=result.error or f"nested swarm list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _swarm_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    """Send one message to a child swarm via POST /v1/chat/completions/."""
    if not prompt.strip():
        return R.OperateResult(remote="swarm", op="send", ok=False, detail="prompt is required")
    model = (target or "").strip()
    headers = R._auth_headers(spec)
    listed: R.OperateResult | None = None
    if not model:
        listed = _swarm_list(spec, timeout)
        if listed.ok and isinstance(listed.data, dict):
            agents = listed.data.get("agents") or []
            if isinstance(agents, list) and agents and isinstance(agents[0], dict):
                model = str(agents[0].get("id") or "")
        if not model:
            return R.OperateResult(
                remote="swarm",
                op="send",
                ok=False,
                detail="Need a child blueprint id (target) or a working list.",
                http_status=listed.http_status,
                data=listed.data,
            )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    last = R.HttpResult(status=None, error="no paths")
    for path in ("/v1/chat/completions/", "/v1/chat/completions"):
        last = R.http_json(
            "POST",
            f"{spec.base_url}{path}",
            headers=headers,
            body=payload,
            timeout=timeout,
        )
        if last.status in R._UP:
            return R.OperateResult(
                remote="swarm",
                op="send",
                ok=True,
                detail=f"sent nested swarm turn via POST {path} model={model}",
                http_status=last.status,
                data={"model": model, "response": last.body or last.text},
            )
        if last.status in R._AUTH:
            return R.OperateResult(
                remote="swarm",
                op="send",
                ok=False,
                detail=(
                    "Nested swarm send requires Bearer auth. "
                    "Set remotes.swarm.api_key or SWARM_REMOTE_API_KEY (env var name only)."
                ),
                http_status=last.status,
                data=last.body,
            )
    return R.OperateResult(
        remote="swarm",
        op="send",
        ok=False,
        detail=last.error or f"nested swarm send failed (http {last.status})",
        http_status=last.status,
        data=last.body or last.text,
    )


