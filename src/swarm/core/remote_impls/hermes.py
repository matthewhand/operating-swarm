"""#812 slice 5 — Hermes impl bodies, moved verbatim out of
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
    from swarm.core.remotes import OperateResult, RemoteSpec

R: Any = importlib.import_module("swarm.core.remotes")

__all__ = ['_hermes_find_job', '_hermes_job_status', '_hermes_job_text', '_hermes_jobs_from', '_hermes_list', '_hermes_poll_run', '_hermes_run_id', '_hermes_send', '_hermes_session_messages', '_hermes_messages_to_transcript', 'read_hermes_recent_turns']


def _hermes_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    headers = R._auth_headers(spec)
    models = R.http_json("GET", f"{spec.base_url}/v1/models", headers=headers, timeout=timeout)
    sessions = R.http_json("GET", f"{spec.base_url}/api/sessions", headers=headers, timeout=timeout)
    jobs = R.http_json("GET", f"{spec.base_url}/api/jobs", headers=headers, timeout=timeout)
    data: dict[str, Any] = {"models": models.body, "sessions": sessions.body, "jobs": jobs.body}
    statuses = [models.status, sessions.status, jobs.status]
    if any(s in R._UP for s in statuses):
        return R.OperateResult(
            remote="hermes",
            op="list",
            ok=True,
            detail="listed Hermes models/sessions/jobs (missing slices stay null)",
            http_status=next((s for s in statuses if s in R._UP), None),
            data=data,
        )
    if any(s in R._AUTH for s in statuses):
        return R.OperateResult(
            remote="hermes",
            op="list",
            ok=False,
            detail="Hermes list endpoints require API_SERVER_KEY (Bearer). Set remotes.hermes.api_key or HERMES_API_KEY.",
            http_status=401,
            data=data,
        )
    return R.OperateResult(
        remote="hermes",
        op="list",
        ok=False,
        detail=models.error or sessions.error or jobs.error or "Hermes list failed",
        http_status=models.status,
        data=data,
    )


def _hermes_run_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("run_id", "job_id", "id", "jobId", "runId"):
            val = payload.get(key)
            if isinstance(val, (str, int)) and str(val).strip():
                return str(val).strip()
        data = payload.get("data")
        if data is not payload:
            found = _hermes_run_id(data)
            if found:
                return found
    return ""


def _hermes_jobs_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("jobs", "data", "items", "sessions", "runs"):
        val = payload.get(key)
        if isinstance(val, list):
            return [item for item in val if isinstance(item, dict)]
    if _hermes_run_id(payload) or payload.get("status") or payload.get("state"):
        return [payload]
    return []


def _hermes_find_job(payload: Any, run_id: str) -> dict[str, Any] | None:
    needle = (run_id or "").strip()
    if not needle:
        return None
    for job in _hermes_jobs_from(payload):
        if _hermes_run_id(job) == needle:
            return job
    return None


def _hermes_job_text(job: Any) -> str:
    if isinstance(job, str) and job.strip():
        return job.strip()
    if not isinstance(job, dict):
        return ""
    for key in ("output", "result", "text", "response", "content", "message"):
        val = job.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        nested = _hermes_job_text(val)
        if nested:
            return nested
    choices = job.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            nested = _hermes_job_text(choice)
            if nested:
                return nested
    return ""


def _hermes_job_status(job: Any) -> str:
    if not isinstance(job, dict):
        return ""
    return str(job.get("status") or job.get("state") or "").strip().lower()


def _hermes_poll_run(
    spec: R.RemoteSpec,
    *,
    run_id: str,
    timeout: float,
    seed: Any = None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Poll Hermes jobs/runs until output or timeout. Returns (text, error, job)."""
    headers = R._auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    deadline = time.monotonic() + max(float(timeout), 0.0)
    http_timeout = min(R._HERMES_POLL_HTTP_TIMEOUT_S, max(float(timeout), 0.5))
    job = seed if isinstance(seed, dict) else None
    while True:
        if job is None or not _hermes_job_text(job):
            for path in (
                f"{base_url}/api/jobs/{run_id}",
                f"{base_url}/v1/runs/{run_id}",
                f"{base_url}/api/jobs",
                f"{base_url}/api/sessions",
            ):
                polled = R.http_json("GET", path, headers=headers, timeout=http_timeout)
                if polled.status not in R._UP:
                    continue
                found = _hermes_find_job(polled.body, run_id)
                if found is None and isinstance(polled.body, dict):
                    wrapper = any(k in polled.body for k in ("jobs", "sessions", "items", "runs"))
                    body_id = _hermes_run_id(polled.body)
                    if not wrapper and body_id in ("", run_id) and (
                        _hermes_job_text(polled.body) or _hermes_job_status(polled.body)
                    ):
                        found = polled.body
                if found:
                    job = found
                    if _hermes_job_text(job):
                        break
        text = _hermes_job_text(job)
        status = _hermes_job_status(job)
        if text and status in ("", "completed", "complete", "succeeded", "success", "done", "finished"):
            return text, "", job
        if status in ("failed", "error", "cancelled", "canceled"):
            err = ""
            if isinstance(job, dict):
                err = str(job.get("error") or job.get("message") or "").strip()
            return "", err or f"Hermes run {run_id} ended with status {status}", job
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "", "Hermes run timed out", job
        R.interruptible_sleep(min(max(R._HERMES_POLL_INTERVAL_S, 0.0), remaining))


def _hermes_send(
    spec: R.RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
) -> R.OperateResult:
    if not prompt.strip():
        return R.OperateResult(remote="hermes", op="send", ok=False, detail="prompt is required")
    headers = R._auth_headers(spec)
    body: dict[str, Any] = {"input": prompt}
    if session_id:
        body["session_id"] = session_id
    timeout_s = float(timeout or R._OPERATE_SEND_TIMEOUT_S)
    start_timeout = min(timeout_s, 10.0)
    result = R.http_json(
        "POST",
        f"{spec.base_url}/v1/runs",
        headers=headers,
        body=body,
        timeout=start_timeout,
    )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail="Hermes POST /v1/runs requires Bearer API_SERVER_KEY",
            http_status=result.status,
            data=result.body,
        )
    if result.status not in R._UP:
        return R.OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail=R._unreachable_detail(result, "Hermes send"),
            http_status=result.status,
            data=result.body or result.text,
        )
    payload = result.body if isinstance(result.body, dict) else {}
    run_id = _hermes_run_id(payload)
    immediate = _hermes_job_text(payload)
    status = _hermes_job_status(payload)
    if immediate and status in ("", "completed", "complete", "succeeded", "success", "done", "finished"):
        return R.OperateResult(
            remote="hermes",
            op="send",
            ok=True,
            detail="Hermes reply",
            http_status=result.status,
            data={"run_id": run_id, "text": immediate, "response": immediate},
        )
    if not run_id:
        return R.OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail="Hermes POST /v1/runs did not return a run id",
            http_status=result.status,
            data=payload or result.text,
            gap="hermes_run_id_missing",
        )
    poll_budget = max(timeout_s - start_timeout, timeout_s)
    text, err, job = _hermes_poll_run(spec, run_id=run_id, timeout=poll_budget, seed=payload)
    if text:
        data: dict[str, Any] = {"run_id": run_id, "text": text, "response": text}
        if isinstance(job, dict):
            data["job"] = job
        return R.OperateResult(
            remote="hermes",
            op="send",
            ok=True,
            detail="Hermes reply",
            http_status=result.status,
            data=data,
        )
    return R.OperateResult(
        remote="hermes",
        op="send",
        ok=False,
        detail=err or "Hermes run timed out",
        http_status=result.status,
        data={"run_id": run_id, "job": job},
        gap="hermes_reply_timeout" if "timed out" in (err or "") else "hermes_reply_failed",
    )


def _hermes_session_messages(
    spec: R.RemoteSpec, session_id: str, timeout: float
) -> list[dict[str, Any]]:
    """GET /api/sessions/{sid}/messages → raw message rows (chat hydration).

    Never raises: an unreachable or erroring harness returns ``[]`` and the
    caller renders an honest empty thread instead of fabricating one.
    """
    base_url = (spec.base_url or "").rstrip("/")
    sid = (session_id or "").strip()
    if not base_url or not sid:
        return []
    result = R.http_json(
        "GET",
        f"{base_url}/api/sessions/{quote(sid)}/messages",
        headers=R._auth_headers(spec),
        timeout=min(float(timeout or R._OPERATE_TIMEOUT_S), 12.0),
    )
    if result.status not in R._UP:
        return []
    body = result.body
    rows: Any = []
    if isinstance(body, dict):
        rows = body.get("data") or body.get("messages") or body.get("turns") or []
    elif isinstance(body, list):
        rows = body
    return [row for row in rows if isinstance(row, dict)]


def _hermes_messages_to_transcript(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Map Hermes messages → ``{role, content}`` transcript rows.

    Only user/assistant prose is rendered; tool call plumbing is not chat.
    Content may be a plain string or a list of ``{text}`` blocks.
    """
    out: list[dict[str, str]] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = row.get("content")
        text = ""
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            text = "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("text")
            ).strip()
        if text:
            out.append({"role": role, "content": text})
    return out


def read_hermes_recent_turns(
    remote_id: str,
    session_id: str,
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> list[dict[str, str]]:
    """Public hydration hook for chat_thread (Hermes session history).

    Resolves the remote spec (works with the bare kind id the SPA sends),
    fetches the session's messages, and maps them to transcript rows. Never
    raises — any failure is an empty list and the thread stays empty.
    """
    try:
        spec = R.load_remote(remote_id, config)
    except Exception:
        R.logger.debug(
            "hermes hydrate: cannot resolve remote %s", remote_id, exc_info=True
        )
        return []
    try:
        rows = _hermes_session_messages(
            spec, session_id, timeout or R._OPERATE_TIMEOUT_S
        )
    except Exception:
        R.logger.debug(
            "hermes hydrate: message fetch failed for %s/%s",
            remote_id,
            session_id,
            exc_info=True,
        )
        return []
    return _hermes_messages_to_transcript(rows)


