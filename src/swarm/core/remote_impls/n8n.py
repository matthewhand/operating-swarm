"""#812 slice 5 — n8n impl bodies, moved verbatim out of
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

__all__ = ['_n8n_list', '_n8n_matches_query', '_n8n_reply_text', '_n8n_send', '_n8n_split_session', '_n8n_trigger_node', '_n8n_webhook_path', '_n8n_workflows_payload']


def _n8n_workflows_payload(body: Any) -> list[Any]:
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            return data
        if isinstance(body.get("workflows"), list):
            return body["workflows"]
    if isinstance(body, list):
        return body
    return []


def _n8n_trigger_node(workflow: dict[str, Any]) -> dict[str, Any] | None:
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return None
    webhook: dict[str, Any] | None = None
    for node in nodes:
        if not isinstance(node, dict) or node.get("disabled"):
            continue
        ntype = str(node.get("type") or "").lower()
        if "chattrigger" in ntype:
            return node
        if ntype.endswith("webhook") or ntype.endswith(".webhook"):
            webhook = webhook or node
    return webhook


def _n8n_webhook_path(node: dict[str, Any]) -> str:
    params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
    path = str(params.get("path") or "").strip().strip("/")
    webhook_id = str(node.get("webhookId") or params.get("webhookId") or "").strip()
    ntype = str(node.get("type") or "").lower()
    if "chattrigger" in ntype:
        return webhook_id or path
    return path or webhook_id


def _n8n_matches_query(row: dict[str, Any], query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    hay = " ".join(
        str(row.get(key) or "")
        for key in ("id", "title", "snippet", "channel")
    ).lower()
    return q in hay


def _n8n_list(spec: RemoteSpec, timeout: float, query: str = "") -> OperateResult:
    """List n8n chat/webhook workflows as resumable sessions.

    GET /api/v1/workflows. Each chatTrigger (else webhook) flow is a session
    with resume key ``workflowId:webhookPath``. Cron/manual-only workflows
    are omitted. ``query`` filters id/title/channel client-or-server side.
    """
    from swarm.core.remote_harness import remote_session_from_dict

    headers = R._auth_headers(spec)
    result = R.http_json(
        "GET",
        f"{spec.base_url}/api/v1/workflows?limit=250",
        headers=headers,
        timeout=timeout,
    )
    workflows = _n8n_workflows_payload(result.body)
    normalized: list[dict[str, Any]] = []
    for wf in workflows:
        if not isinstance(wf, dict):
            continue
        wf_id = str(wf.get("id") or "").strip()
        if not wf_id:
            continue
        trigger = _n8n_trigger_node(wf)
        if trigger is None:
            continue
        path = _n8n_webhook_path(trigger)
        if not path:
            continue
        title = str(wf.get("name") or wf_id).strip()
        ntype = str(trigger.get("type") or "")
        channel = "chat" if "chattrigger" in ntype.lower() else "webhook"
        session = remote_session_from_dict(
            {
                "id": f"{wf_id}:{path}",
                "title": title,
                "snippet": channel,
                "source": "n8n",
                "updated_at": str(wf.get("updatedAt") or wf.get("updated_at") or "").strip(),
                "channel": title[:128],
                "thread_ts": path[:64],
            }
        )
        if session is None:
            continue
        row = session.as_dict()
        if _n8n_matches_query(row, query):
            normalized.append(row)
    data: dict[str, Any] = {"sessions": normalized, "source": "n8n"}
    if result.status in R._UP:
        return R.OperateResult(
            remote="n8n",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} n8n flow(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="n8n",
            op="list",
            ok=False,
            detail=(
                "n8n /api/v1/workflows requires a valid API key. "
                "Set remotes.n8n.api_key or N8N_API_KEY "
                "(Settings → n8n API on the n8n box)."
            ),
            http_status=result.status,
            data=data,
        )
    return R.OperateResult(
        remote="n8n",
        op="list",
        ok=False,
        detail=result.error or f"n8n list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _n8n_split_session(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    wf_id, sep, rest = sid.partition(":")
    if not sep or not wf_id or not rest:
        return "", ""
    return wf_id, rest


def _n8n_reply_text(body: Any, text: str = "") -> str:
    if isinstance(body, dict):
        for key in ("output", "text", "message", "json"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                nested = _n8n_reply_text(val, "")
                if nested:
                    return nested
        data = body.get("data")
        if isinstance(data, list) and data:
            nested = _n8n_reply_text(data[0], "")
            if nested:
                return nested
        if isinstance(data, dict):
            nested = _n8n_reply_text(data, "")
            if nested:
                return nested
    if isinstance(body, list) and body:
        nested = _n8n_reply_text(body[0], "")
        if nested:
            return nested
    raw = (text or "").strip()
    if raw.startswith("data:"):
        parts: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parts.append(payload)
                continue
            chunk = _n8n_reply_text(parsed, "")
            if chunk:
                parts.append(chunk)
        if parts:
            return "".join(parts)
    return raw


def _n8n_send(
    spec: R.RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> R.OperateResult:
    """Send into an existing n8n chat/webhook flow (never mints a workflow).

    ``session_id`` is ``workflowId:webhookPath`` from the session list.
    POST /webhook/<path> with ``action=sendMessage`` + ``sessionId`` resumes
    that flow's memory; inactive flows fall back to /webhook-test/<path>.
    """
    sid = (session_id or target or "").strip()
    wf_id, webhook_path = _n8n_split_session(sid)
    if not wf_id or not webhook_path:
        return R.OperateResult(
            remote="n8n",
            op="send",
            ok=False,
            detail=(
                "Pick an n8n workflow. Operating Swarm does not mint new "
                "workflows. Pass session_id as workflow:webhook "
                "(list the remote to see available flows)."
            ),
            gap="n8n_workflow_required",
        )
    if not prompt.strip():
        return R.OperateResult(remote="n8n", op="send", ok=False, detail="prompt is required")
    body = {
        "action": "sendMessage",
        "sessionId": sid,
        "chatInput": prompt,
    }
    headers = R._auth_headers(spec)
    prod = f"{spec.base_url}/webhook/{webhook_path}"
    result = R.http_json("POST", prod, headers=headers, body=body, timeout=timeout)
    if result.status == 404:
        test_url = f"{spec.base_url}/webhook-test/{webhook_path}"
        result = R.http_json("POST", test_url, headers=headers, body=body, timeout=timeout)
    reply = _n8n_reply_text(result.body, result.text)
    if result.status in R._UP and reply:
        return R.OperateResult(
            remote="n8n",
            op="send",
            ok=True,
            detail=f"n8n replied in flow {wf_id}",
            http_status=result.status,
            data={"response": reply, "thread": sid, "workflow": wf_id},
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="n8n",
            op="send",
            ok=False,
            detail="n8n chat requires a valid API key (Settings → n8n API).",
            http_status=result.status,
            data=result.body,
        )
    if result.status in R._UP and not reply:
        return R.OperateResult(
            remote="n8n",
            op="send",
            ok=False,
            detail="n8n returned an empty chat reply",
            http_status=result.status,
            data=result.body or result.text,
        )
    return R.OperateResult(
        remote="n8n",
        op="send",
        ok=False,
        detail=result.error or f"n8n send failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )



