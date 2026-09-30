"""OpenMuse remote — one task per OS session.

OpenMuse is a Hono/TypeScript agent server. Operating Swarm talks to it as a
single ``remote``: an OpenMuse **task** is the seat's conversation, and OS
never re-models its planner/goals/agents as OS seats or a
``TeamKindBase`` roster.

Verified routes (OpenMuse ``apps/server/src/app.ts``):

* ``POST /api/session`` body ``{accessKey?}`` → ``200 {token, mode}``. In
  ``live`` mode the access key is REQUIRED and must equal
  ``OPENMUSE_ACCESS_KEY`` (else ``401 "Access key is incorrect"``); in
  ``sample`` mode it is optional. The token is 32 random bytes
  base64url, session TTL 24h. Every other ``/api/*`` call needs
  ``Authorization: Bearer <token>`` (else ``401 "Sign in to OpenMuse"`` /
  ``"Session expired. Sign in again."``).
* ``GET  /api/agent`` — service snapshot. NO trailing slash: the slashed
  form is a different, unmounted route and 404s (Hono). Measured live:
  ``/api/agent`` -> 200 with ``tasks``; ``/api/agent/`` -> 404.
* ``POST /api/agent/tasks`` → ``201`` with the created task. Body is the
  ``createTaskSchema``: ``{title?, prompt, kind?, goalId?, input?}``.
  Rejects ``422`` on a schema failure, ``404 "Goal not found"``, and
  ``409 "Finish or cancel some tasks before adding more"`` at >=100
  non-terminal tasks.
* ``GET  /api/agent/tasks/:id`` — task detail: ``status``, plan steps, a
  pending ``question``, and an ``events`` stream.
* ``POST /api/agent/tasks/:id/control`` body ``{action}`` —
  ``pause`` / ``resume`` / ``cancel`` / ``retry``.
* ``POST /api/agent/tasks/:id/input`` — answer a pending question (form
  values / approvals).

Deliberately NOT modelled: ``/api/files/:id/content`` and
``/api/browsers/:id/(preview|console)`` authenticate with a signed
``?owner=&expires=&signature=`` HMAC query (15 min), not a bearer. This
impl never sends the session token to those routes, and does not touch
``/api/browsers*`` or ``/api/computer*`` at all.

Auth is declared the way every other remote declares it: an env-var
*name* (``OPENMUSE_ACCESS_KEY`` → ``api_key_env``), never a literal
secret. The value is read from the process env, used once to mint a
session token, then dropped: it is never returned, logged, or written
into any payload this module produces.

``/api/health`` cannot tell you the configured model is usable (#1660)
------------------------------------------------------------------------
``/api/health`` answers ``{ok, mode, agentConfigured, browserConfigured}``
and ``agentConfigured`` is ``config.model && <a provider key>`` — an
**existence** check, not a validity one. ``MODEL=hosted_vllm/nemotron-3.5-
lightning-free`` therefore reports ``agentConfigured: true`` and every task
then dies with ``Unknown provider "hosted_vllm" in "hosted_vllm/…"``.

Probed read-only 2026-09-28 on both live instances, unauthenticated and
with a valid session bearer, there is **no** route that exposes the model:
``/api/models``, ``/v1/models``, ``/api/agent/models``, ``/api/agent/
providers``, ``/api/agent/config``, ``/api/agent/capabilities``,
``/api/config`` and ``/openapi.json`` are all ``404``. The task index is
not mounted either, so the seat has no sessions to inspect. The only
authoritative statement OpenMuse ever makes about ``MODEL`` is the one it
makes when it refuses a turn.

So the strongest honest signal that exists is that refusal: latch the
instance's own verbatim message and report the seat DEGRADED until it
clears. Nothing here infers a bad model from silence, and no model turn is
ever started to find out — a health probe stays a cheap liveness GET. See
`_note_model_rejection` / `_active_model_rejection`.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
import time
from typing import Any
from urllib.parse import quote

R: Any = importlib.import_module("swarm.core.remotes")

logger = logging.getLogger(__name__)

__all__ = [
    "_openmuse_control",
    "_openmuse_health",
    "_openmuse_list",
    "_openmuse_operate",
    "_openmuse_resume_pending",
    "_openmuse_send",
    "openmuse_clear_model_rejection",
    "openmuse_clear_token_cache",
    "openmuse_pending_question",
    "openmuse_task_row",
    "openmuse_task_text",
]

# Task ids must survive CLI-session sanitize (``^[A-Za-z0-9._:-]{1,128}$``).
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_REMOTE_NAMES = frozenset({"openmuse", "open-muse", "open_muse"})

# createTaskSchema: ``prompt`` is 1..12000, ``title`` is 1..160.
_PROMPT_MAX = 12000

# A task is terminal once OpenMuse stops working on it. Anything else
# (queued / running / paused / unknown / missing) is polled until the
# send deadline — an unknown status name must never read as "finished".
_TERMINAL_STATES = frozenset(
    {
        "done",
        "complete",
        "completed",
        "finished",
        "succeeded",
        "success",
        "ok",
        "failed",
        "failure",
        "error",
        "errored",
        "cancelled",
        "canceled",
        "aborted",
        "stopped",
        "rejected",
        "timed_out",
        "timeout",
    }
)
_FAILED_STATES = frozenset(
    {
        "failed",
        "failure",
        "error",
        "errored",
        "cancelled",
        "canceled",
        "aborted",
        "stopped",
        "rejected",
        "timed_out",
        "timeout",
    }
)

# POST /api/agent/tasks/:id/control
_CONTROL_ACTIONS = ("pause", "resume", "cancel", "retry")

# ---------------------------------------------------------------------------
# Live wire contract — verified against a running OpenMuse instance
# ---------------------------------------------------------------------------
# `GET /api/agent/tasks/:id` does NOT return a bare task. It returns
# `{ task: AgentTask, files, browsers, events, artifacts }` — every task field
# (status / result / error / question / plan) lives one level down under "task",
# while the event stream stays at the top level. Reading the envelope directly
# makes every task look status-less, which would poll to the deadline forever.
_TASK_ENVELOPE_KEY = "task"


def _task_of(detail: Any) -> dict[str, Any]:
    """The AgentTask inside a task-detail envelope (or the row itself)."""
    if not isinstance(detail, dict):
        return {}
    inner = detail.get(_TASK_ENVELOPE_KEY)
    return inner if isinstance(inner, dict) else detail


# TaskStatus, verbatim from packages/domain/src/agent.ts. Anything outside the
# terminal set is non-terminal and must be polled; succeeded/failed/cancelled
# are the terminal three (the server's own `terminal` set in engine/service.ts).
LIVE_TASK_STATUSES = frozenset(
    {
        "queued",
        "running",
        "waiting_approval",
        "waiting_input",
        "scheduled",
        "paused",
        "succeeded",
        "failed",
        "cancelled",
    }
)
LIVE_TERMINAL_TASK_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
# Statuses that mean "the agent is waiting on the operator", not "done".
LIVE_QUESTION_STATUSES = frozenset({"waiting_input", "waiting_approval"})

# OpenMuse's Hono error envelope is `{"error": "..."}`, not FastAPI's "detail".
# Other builds and the proxied AG-UI surface use the others, so read them all.
_ERROR_KEYS = ("error", "detail", "message", "reason")


def _server_error(body: Any) -> str:
    """The server's human message from an OpenMuse error envelope."""
    if not isinstance(body, dict):
        return _as_text(body).strip()
    for key in _ERROR_KEYS:
        text = _as_text(body.get(key)).strip()
        if text:
            return text
    return ""


def _openmuse_error(result: Any, token: str = "") -> str:
    """Redacted server message for a failed response, or "" when there is none."""
    body = getattr(result, "body", None)
    if body is None:
        return ""
    return _redact(_server_error(body), token)

# Poll cadence for GET /api/agent/tasks/:id. Module-level so a test (or a
# future remote-level knob) can shorten it without touching the loop.
_OPENMUSE_POLL_INTERVAL_S = 0.5

# Server session TTL is 24h; refresh a little early so a poll never races
# the expiry boundary.
_TOKEN_TTL_S = 23 * 3600.0

# instance id -> (minted_at_monotonic, token). Process memory only; the
# access key is never cached and never stored.
_TOKEN_CACHE: dict[str, tuple[float, str]] = {}
_TOKEN_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Spec / config helpers
# ---------------------------------------------------------------------------


def _base(spec: Any) -> str:
    return (getattr(spec, "base_url", "") or "").rstrip("/")


def _access_key(spec: Any) -> str:
    """The live access key, or "" — resolved from the env var, never stored."""
    key = str(getattr(spec, "api_key", "") or "").strip()
    if not key or R._is_unresolved_placeholder(key):
        return ""
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key


def _env_var(spec: Any) -> str:
    """Env-var NAME for the access key. The name is safe to print; the value is not."""
    return str(getattr(spec, "api_key_env", "") or "") or "OPENMUSE_ACCESS_KEY"


def _is_remote_label(spec: Any, value: str) -> bool:
    """True when *value* names the remote itself rather than one of its tasks."""
    key = (value or "").strip().lower()
    if not key:
        return False
    names = set(_REMOTE_NAMES)
    names.add(str(getattr(spec, "id", "") or "").strip().lower())
    names.add(str(getattr(spec, "kind", "") or "").strip().lower())
    return key in names


def _redact(text: str, *secrets: str) -> str:
    """Never let the access key or a session token reach a detail/log line."""
    out = str(text or "")
    for secret in secrets:
        token = str(secret or "").strip()
        if len(token) >= 4 and token in out:
            out = out.replace(token, "redacted")
    return out[:500]


def _scrub(value: Any, spec: Any, token: str = "") -> Any:
    """Deep-copy a payload with the access key / session token removed.

    Applied to every ``OperateResult.data`` this module builds so a
    misbehaving server echo can never carry a credential into the chat
    transcript, the rail payload, or a log line.
    """
    secrets = (_access_key(spec), token)

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            return _redact(node, *secrets) if secrets else node
        if isinstance(node, dict):
            return {str(k): _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if isinstance(node, tuple):
            return [_walk(item) for item in node]
        return node

    return _walk(value)


def _auth_gap(spec: Any, what: str, *, detail: str = "", status: int | None = None) -> Any:
    """401/403 as an actionable gap: name the env var, never the value."""
    env_var = _env_var(spec)
    reason = _redact(detail) or "OpenMuse refused the request"
    return R.OperateResult(
        remote=getattr(spec, "id", "openmuse"),
        op=what,
        ok=False,
        detail=(
            f"{reason}. OpenMuse needs a session: export the access key from "
            f"OPENMUSE_ACCESS_KEY as {env_var} in Settings → Remotes, then retry."
        ),
        http_status=status,
        gap="openmuse_auth",
        action=R._settings_action(getattr(spec, "id", "openmuse"), "api_key_env"),
    )


def _fail(
    spec: Any,
    op: str,
    detail: str,
    *,
    gap: str = "",
    status: int | None = None,
    data: Any = None,
    action: dict[str, Any] | None = None,
    token: str = "",
) -> Any:
    return R.OperateResult(
        remote=getattr(spec, "id", "openmuse"),
        op=op,
        ok=False,
        detail=_redact(detail, _access_key(spec), token),
        http_status=status,
        data=_scrub(data, spec, token),
        gap=gap,
        action=action,
    )


# ---------------------------------------------------------------------------
# Session token: mint once, cache, re-mint exactly once on a 401
# ---------------------------------------------------------------------------


def openmuse_clear_token_cache() -> None:
    """Drop every cached session token (test hook; also a sign-out).

    Also drops the latched model rejection (#1660): both are per-remote
    process state, and a caller that resets the remote must not inherit the
    previous one's verdict.
    """
    with _TOKEN_LOCK:
        _TOKEN_CACHE.clear()
    openmuse_clear_model_rejection()


def _token_cache_key(spec: Any) -> str:
    return f"{getattr(spec, 'id', '')}|{_base(spec)}"


# ---------------------------------------------------------------------------
# MODEL rejection latch (#1660)
# ---------------------------------------------------------------------------
# `/api/health` cannot see the model, and the instance mounts no route that
# can (see the module docstring for the live route inventory). The only
# authoritative word OpenMuse ever gives about `MODEL` is the refusal it
# returns when a task reaches the model. Latch that verbatim text so health
# stops saying UP for a seat that has already been told, in as many words,
# that its model is unusable.
#
# Deliberately narrow. A task fails for a hundred reasons, and a false
# positive here degrades a healthy seat. Two shapes qualify, both
# self-contained — nothing here has to guess which noun OpenMuse meant:
#
# 1. The instance names a provider it does not know AND that same word is the
#    prefix of a ``<provider>/<model>`` id it then refused. The backreference
#    is what makes it a MODEL complaint rather than some other provider-ish
#    noun: the live message is `Unknown provider "hosted_vllm" in
#    "hosted_vllm/nemotron-3.5-lightning-free". Supported: openai, anthropic,
#    google (…)`, so the refused provider and the refused model id agree. A
#    bare `Unknown provider "mcp"` does not, and does not latch.
# 2. The message itself blames a model id or an unconfigured provider — those
#    words are unambiguous on their own.
_PROVIDER_MODEL_COMPLAINT_RE = re.compile(
    r"(?:unknown|unsupported|unavailable)\s+provider\b"
    r"[^\n]{0,80}?([\w.-]+)\b[^\n]{0,80}?[\"“']?\1/"
)
_MODEL_ID_COMPLAINT_RES = (
    re.compile(r"(?:invalid|unknown|unsupported|unavailable|deprecated)\s+model\b"),
    re.compile(
        r"model[ _-](?:not[ _-]found|not[ _-]supported|not[ _-]available|is[ _-]invalid)"
    ),
    re.compile(r"no\s+such\s+model\b"),
    re.compile(r"provider[ _-]not[ _-]configured\b"),
)

# A latched rejection is evidence about the operator's `MODEL`, and the
# operator fixes `MODEL` by editing the OpenMuse host, not by talking to us.
# Keep it long enough that a health poll cannot launder a failed task back
# into a green light, and short enough that a fixed instance recovers on its
# own even if the operator never sends another task. Expiry reverts the seat
# to the pre-latch state — *unverified*, which is what a health-only probe
# has always been — never to a false "ok".
_MODEL_REJECTION_TTL_S = 30 * 60.0

# Same key space as the session tokens: instance id + base url, so two
# OpenMuse seats (LAN + public) never share a verdict.
_MODEL_REJECTIONS: dict[str, tuple[float, str]] = {}


def openmuse_clear_model_rejection() -> None:
    """Forget every latched MODEL rejection (test hook; also a sign-out)."""
    with _TOKEN_LOCK:
        _MODEL_REJECTIONS.clear()


def _model_rejection(text: str) -> str:
    """The server's own words when they blame the configured MODEL, else ``""``."""
    out = str(text or "").strip()
    if not out:
        return ""
    low = out.lower()
    if _PROVIDER_MODEL_COMPLAINT_RE.search(low):
        return out
    for pattern in _MODEL_ID_COMPLAINT_RES:
        if pattern.search(low):
            return out
    return ""


def _note_model_rejection(spec: Any, *texts: str) -> str:
    """Latch the first of *texts* that blames MODEL; return it, else ``""``.

    The reason is redacted *here*, at the one place it enters the process,
    because it is stored and then re-surfaced by a health probe: a server
    that echoes the caller's own key back inside its error text must not be
    able to park that key in a payload the UI will render.
    """
    reason = ""
    for text in texts:
        reason = _model_rejection(text)
        if reason:
            break
    if not reason:
        return ""
    reason = _redact(reason, _access_key(spec))
    with _TOKEN_LOCK:
        _MODEL_REJECTIONS[_token_cache_key(spec)] = (time.monotonic(), reason)
    # The server's words, not ours.
    logger.warning(
        "openmuse: %s rejected the configured MODEL — %s (seat health is now DEGRADED "
        "until a task succeeds)",
        getattr(spec, "id", "openmuse"),
        reason,
    )
    return reason


def _active_model_rejection(spec: Any) -> str:
    """The latched MODEL rejection for this seat, or ``""`` when there is none."""
    key = _token_cache_key(spec)
    now = time.monotonic()
    with _TOKEN_LOCK:
        entry = _MODEL_REJECTIONS.get(key)
        if entry is None:
            return ""
        if (now - entry[0]) >= _MODEL_REJECTION_TTL_S:
            _MODEL_REJECTIONS.pop(key, None)
            return ""
        return entry[1]


def _clear_model_rejection(spec: Any) -> None:
    """A turn ran and came back with an answer: the model is being served."""
    with _TOKEN_LOCK:
        _MODEL_REJECTIONS.pop(_token_cache_key(spec), None)


def _openmuse_token(
    spec: Any, *, force: bool = False, timeout: float = 5.0
) -> tuple[str, Any]:
    """Return ``(token, None)`` or ``("", OperateResult)``.

    Cached per remote instance for the server's 24h session TTL. ``force``
    is the single re-auth after a 401 — never called in a loop.
    """
    cache_key = _token_cache_key(spec)
    if not force:
        with _TOKEN_LOCK:
            cached = _TOKEN_CACHE.get(cache_key)
        if cached is not None and (time.monotonic() - cached[0]) < _TOKEN_TTL_S:
            return cached[1], None

    access = _access_key(spec)
    body: dict[str, Any] = {"accessKey": access} if access else {}
    result = R.http_json(
        "POST",
        f"{_base(spec)}/api/session",
        headers={"Accept": "application/json", "User-Agent": "open-swarm-remotes/1"},
        body=body,
        timeout=timeout,
    )
    if result.status in R._AUTH:
        return "", _auth_gap(
            spec,
            "sign in",
            detail=(
                "OpenMuse POST /api/session rejected the access key"
                if access
                else "OpenMuse POST /api/session requires an access key"
            ),
            status=result.status,
        )
    if result.status not in R._UP:
        return "", _fail(
            spec,
            "sign in",
            R._unreachable_detail(result, "OpenMuse POST /api/session"),
            gap="openmuse_unreachable",
            status=result.status,
            data=result.body or result.text or None,
        )
    token = ""
    if isinstance(result.body, dict):
        token = str(result.body.get("token") or "").strip()
    if not token:
        return "", _fail(
            spec,
            "sign in",
            "OpenMuse POST /api/session returned no token.",
            gap="openmuse_no_token",
            status=result.status,
            data=result.body,
        )
    with _TOKEN_LOCK:
        _TOKEN_CACHE[cache_key] = (time.monotonic(), token)
    # Never the token itself — the env var NAME is the only safe thing to log.
    logger.debug("openmuse: minted a session token for %s (key env %s)", cache_key, _env_var(spec))
    return token, None


def _openmuse_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": "open-swarm-remotes/1",
        "Authorization": f"Bearer {token}",
    }


def _openmuse_call(
    spec: Any,
    method: str,
    path: str,
    *,
    body: Any = None,
    timeout: float = 5.0,
) -> tuple[Any, Any, str]:
    """Authenticated call → ``(HttpResult | None, error_result, token)``.

    On success ``error_result`` is ``None``. On a mint/sign-in failure
    ``HttpResult`` is ``None`` and ``error_result`` is the ``OperateResult``
    to hand back verbatim.

    A **401** triggers exactly one re-mint and one retry — that is the status
    OpenMuse returns for "Sign in to OpenMuse" / "Session expired", i.e. the
    token really did go stale. A 403 is a policy refusal, not staleness, so it
    is returned as-is without burning a second mint. A 401 that survives the
    re-mint is reported as the auth gap, never looped on.
    """
    token, err = _openmuse_token(spec, timeout=timeout)
    if err is not None:
        return None, err, ""
    url = f"{_base(spec)}{path}"
    result = R.http_json(
        method, url, headers=_openmuse_headers(token), body=body, timeout=timeout
    )
    if result.status != 401:
        return result, None, token
    fresh, err = _openmuse_token(spec, force=True, timeout=timeout)
    if err is not None:
        return None, err, ""
    retry = R.http_json(
        method, url, headers=_openmuse_headers(fresh), body=body, timeout=timeout
    )
    if retry.status in R._AUTH:
        return (
            None,
            _auth_gap(
                spec,
                method.lower(),
                detail="OpenMuse still refuses the session after re-auth",
                status=retry.status,
            ),
            "",
        )
    return retry, None, fresh


# ---------------------------------------------------------------------------
# Task → session row / reply text / pending question
# ---------------------------------------------------------------------------


def _as_text(value: Any) -> str:
    """Text out of the shapes a task body can carry. Nothing is invented."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "content", "value", "message", "answer"):
            inner = value.get(key)
            if isinstance(inner, str):
                return inner
        return ""
    if isinstance(value, list):
        parts = [_as_text(item) for item in value]
        if parts and all(part for part in parts):
            return "".join(parts)
    return ""


def _task_id_of(row: Any) -> str:
    """A task id from a bare task or a detail envelope."""
    if not isinstance(row, dict):
        return ""
    task = _task_of(row)
    raw = task.get("id") or task.get("task_id") or task.get("taskId") or ""
    text = str(raw or "").strip()
    return text if _ID_RE.match(text) else ""


def _task_rows(body: Any) -> list[dict[str, Any]]:
    """Task list out of a list body, a ``{tasks: [...]}`` envelope, or a snapshot."""
    rows: Any = body
    if isinstance(body, dict):
        rows = None
        for key in ("tasks", "data", "items"):
            inner = body.get(key)
            if isinstance(inner, list):
                rows = inner
                break
            if isinstance(inner, dict):
                nested = inner.get("tasks") or inner.get("items")
                if isinstance(nested, list):
                    rows = nested
                    break
        # ``GET /api/agent`` (no trailing slash) is a service snapshot: it
        # carries state, not a task list. An instance with nothing on it
        # yields no rows here.
        if rows is None:
            rows = []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def openmuse_task_row(task: Any) -> dict[str, Any] | None:
    """One OpenMuse task as an OS session row, or ``None`` when it is not one.

    Never fabricates: a task without a safe id is not a resumable session,
    so it is dropped rather than invented.
    """
    task_id = _task_id_of(task)
    if not task_id:
        return None
    title = str(task.get("title") or "").strip()
    if not title:
        prompt = str(task.get("prompt") or "").strip().replace("\n", " ")
        title = prompt[:80] or task_id
    return {
        "id": task_id,
        "title": title[:200],
        "snippet": str(task.get("status") or task.get("kind") or "")[:240],
        "source": "openmuse",
        "updated_at": str(
            task.get("updated_at")
            or task.get("updatedAt")
            or task.get("created_at")
            or task.get("createdAt")
            or ""
        ),
        "status": str(task.get("status") or ""),
        "kind": str(task.get("kind") or ""),
    }


def _matches_query(row: dict[str, Any], query: str) -> bool:
    """Filter on what the published row actually shows — never a hidden field."""
    needle = (query or "").strip().lower()
    if not needle:
        return True
    blob = " ".join(
        str(row.get(key) or "")
        for key in ("id", "title", "snippet", "status", "kind")
    ).lower()
    return needle in blob


_TEXT_KEYS = (
    "result",
    "output",
    "answer",
    "summary",
    "final_text",
    "final",
    "reply",
    "text",
    "content",
)
_EVENT_TEXT_HINTS = (
    "assistant",
    "message",
    "text",
    "final",
    "result",
    "answer",
    "completion",
    "output",
)


def _event_text(event: Any, *, allow_title: bool = True) -> str:
    """Prose carried by one RunEvent, if any.

    The live build puts the agent's words in `detail` (and sometimes repeats
    them in `title`); older/other shapes use `content`/`text`/`message`.

    `allow_title` is False for `step` events: their titles are progress chrome
    ("Plan the work", "Finish only when the outcome is achieved"), so falling
    back to a title there would turn a progress line into the reply.
    """
    if not isinstance(event, dict):
        return ""
    return _as_text(
        event.get("detail")
        or event.get("content")
        or event.get("text")
        or event.get("message")
        or event.get("result")
        or event.get("output")
        or (event.get("title") if allow_title else None)
    ).strip()


def _task_last_update(task: dict[str, Any]) -> str:
    """`state.lastUpdate` — where this build parks the agent's latest words.

    Verified live: on a task that answered "OK", `task.result` stayed empty and
    the only copy of the reply was `state.lastUpdate` plus a
    `kind: "step"` event titled "Agent update".
    """
    state = task.get("state")
    if not isinstance(state, dict):
        return ""
    for key in ("lastUpdate", "last_update", "lastMessage", "last_message"):
        text = _as_text(state.get(key)).strip()
        if text:
            return text
    return ""


def openmuse_task_text(detail: Any) -> str:
    """The agent's answer for a finished task.

    Order matters, and it is the order the live instances proved necessary:

    1. `task.result` — populated on some builds, empty string while working.
    2. a `kind: "result"` RunEvent (prose in `detail`).
    3. `task.state.lastUpdate` — where this build parks the latest words.
    4. the last `kind: "step"` event with real prose ("Agent update").

    Steps 3 and 4 exist because a build that answers in a `step` event and
    never fills `result` otherwise reads as an empty turn — the seat looks
    broken when the agent actually replied. Progress `step` events carry an
    empty `detail`, so they are skipped, and a real `result` still wins.
    """
    if not isinstance(detail, dict):
        return ""
    task = _task_of(detail)
    for key in _TEXT_KEYS:
        text = _as_text(task.get(key)).strip()
        if text:
            return text

    events = detail.get("events")
    if isinstance(events, dict):
        events = events.get("events") or events.get("data") or []
    rows = [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []

    for event in reversed(rows):
        etype = str(event.get("kind") or event.get("type") or "").lower()
        if etype and not any(hint in etype for hint in _EVENT_TEXT_HINTS):
            continue
        text = _event_text(event)
        if text:
            return text

    last_update = _task_last_update(task)
    if last_update:
        return last_update

    for event in reversed(rows):
        if str(event.get("kind") or "").lower() != "step":
            continue
        text = _event_text(event, allow_title=False)
        if text:
            return text
    return ""


def _task_state(detail: Any) -> str:
    """The task's own status, read through the detail envelope."""
    task = _task_of(detail)
    if not task:
        return ""
    raw = task.get("status")
    if isinstance(raw, dict):
        raw = raw.get("status") or raw.get("state") or ""
    return str(raw or task.get("state") or "").strip().lower()


def _question_choices(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = _as_text(item).strip() if isinstance(item, dict) else str(item or "").strip()
        if text:
            out.append(text)
    return out


def openmuse_pending_question(
    detail: Any, *, task_id: str = ""
) -> dict[str, Any] | None:
    """First pending question on a task detail, in the shared ask-user shape.

    Mirrors :func:`swarm.core.remote_impls.trueforge.trueforge_pending_question`:
    a task that stopped on a question returns the normalized
    ``{id, ask, choices, other}`` question plus the coordinates needed to
    answer it (``POST /api/agent/tasks/<id>/input``).
    """
    if not isinstance(detail, dict):
        return None
    # `question` lives on the task, not on the envelope.
    raw = _task_of(detail).get("question")
    if raw in (None, "", {}, []):
        raw = detail.get("question") or detail.get("pending_question") or detail.get("pendingQuestion")
    if isinstance(raw, list):
        raw = next((item for item in raw if item), None)
    if raw in (None, "", {}, []):
        return None
    body = raw if isinstance(raw, dict) else {}
    ask = (
        _as_text(raw).strip()
        or str(
            body.get("question")
            or body.get("ask")
            or body.get("prompt")
            or body.get("text")
            or body.get("message")
            or ""
        ).strip()
    )
    if not ask:
        return None
    resolved_task = _task_id_of(detail) or str(task_id or "").strip()
    question_id = str(
        body.get("id")
        or body.get("question_id")
        or body.get("questionId")
        or body.get("key")
        or body.get("name")
        or ""
    ).strip()
    return {
        "type": "ask_user_question",
        "task_id": resolved_task,
        "question": {
            "id": question_id or resolved_task or "q",
            "ask": ask,
            "choices": _question_choices(
                body.get("choices") if body.get("choices") is not None else body.get("options")
            ),
            "other": "Other",
        },
    }


def _task_error_text(detail: Any) -> str:
    """Why a task failed: `task.error`, or its last `kind: "error"` event."""
    if not isinstance(detail, dict):
        return ""
    task = _task_of(detail)
    for key in ("error", "message", "failure", "reason", "detail"):
        text = _as_text(task.get(key)).strip()
        if text:
            return text
    state = task.get("state") if isinstance(task.get("state"), dict) else {}
    if isinstance(state, dict):
        for key in ("error", "message", "detail"):
            text = _as_text(state.get(key)).strip()
            if text:
                return text
    # A task can be waiting on the operator after an error event (the live
    # instance emits `kind: "error"` with the human reason in `detail`).
    events = detail.get("events")
    if isinstance(events, list):
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            if str(event.get("kind") or "").lower() != "error":
                continue
            text = _as_text(
                event.get("detail") or event.get("title") or event.get("message")
            ).strip()
            if text:
                return text
    return ""


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def _openmuse_health(spec: Any, timeout: float = R._DEFAULT_TIMEOUT_S) -> Any:
    """Honest health: the instance's real `GET /api/health`.

    Verified live: that route is unauthenticated and answers
    `{ok, mode, agentConfigured, browserConfigured}`. The agent snapshot
    (`/api/agent`) is 200 and carries `tasks`, so it must not be used as a
    liveness signal — a healthy instance can hold zero tasks.
    (`/api/agent/tasks` is genuinely 404, and `/api/agent/` is a 404 by
    routing, not by absence — see the session-list fallback.)

    Two verdicts on top of the route's own, both #1660:

    * ``agentConfigured: false`` is the instance saying it has no model at all.
      UP here would be a green seat that cannot answer anything.
    * a latched MODEL rejection (the instance already refused a turn with a
      `<provider>/<model>` message) is reported DEGRADED with that message
      verbatim. ``agentConfigured`` stays ``true`` through a bad MODEL by
      construction — it only checks that the string is non-empty — so reading
      it as a green light is the bug.

    Neither costs an extra request, and neither runs a model turn: this stays
    one cheap GET.
    """
    if not _base(spec):
        return R.HealthResult(
            remote=getattr(spec, "id", "openmuse"),
            ok=False,
            state="UNKNOWN",
            detail="base_url is empty",
        )
    budget = min(float(timeout or R._DEFAULT_TIMEOUT_S), 10.0)
    result, err, token = _openmuse_call(
        spec, "GET", "/api/health", timeout=max(1.0, budget / 2)
    )
    if err is not None:
        # A mint failure: the endpoint may well be up, we just cannot sign in.
        return R.HealthResult(
            remote=spec.id,
            ok=False,
            state="UNKNOWN",
            detail=_redact(err.detail or "OpenMuse sign-in failed"),
        )
    url = f"{_base(spec)}/api/health"
    if result.status in R._UP:
        snapshot = result.body if isinstance(result.body, dict) else {}
        mode = str(snapshot.get("mode") or "unknown")
        # Only an *explicit* false counts. A snapshot that omits the key is a
        # build that does not report it, which is not the same statement.
        reports_model = "agentConfigured" in snapshot
        configured = bool(snapshot.get("agentConfigured"))
        alive = (
            f"http {result.status} on /api/health "
            f"({mode} mode, agent {'configured' if configured else 'unconfigured'})"
        )
        scrubbed = _scrub(snapshot, spec, token) or None
        if reports_model and not configured:
            # The model config on the instance changed, so any rejection we
            # latched about it is stale by construction.
            _clear_model_rejection(spec)
            return R.HealthResult(
                remote=spec.id,
                ok=False,
                state="DEGRADED",
                detail=(
                    f"{alive} — the instance has no usable model, so every task "
                    "will fail. Set MODEL on the OpenMuse host as "
                    "<provider>/<model-id> and restart it."
                ),
                http_status=result.status,
                version=scrubbed,
                latency_ms=result.latency_ms,
                url=url,
            )
        rejected = _active_model_rejection(spec)
        if rejected:
            # `not served` is the phrase seat_doctor's model markers already
            # bucket on, and it is exactly what the instance said: this MODEL
            # is not something it serves.
            return R.HealthResult(
                remote=spec.id,
                ok=False,
                state="DEGRADED",
                detail=(
                    f"{alive} — but the configured MODEL is not served by this "
                    f"instance: {rejected}. Fix MODEL on the OpenMuse host as "
                    "<provider>/<model-id> (e.g. openai/<model-id>) and restart it."
                ),
                http_status=result.status,
                version=scrubbed,
                latency_ms=result.latency_ms,
                url=url,
            )
        return R.HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=alive,
            http_status=result.status,
            version=scrubbed,
            latency_ms=result.latency_ms,
            url=url,
        )
    if result.status in R._AUTH:
        return R.HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=f"http {result.status} on /api/health (endpoint alive, auth refused)",
            http_status=result.status,
            version={"auth_required": True},
            latency_ms=result.latency_ms,
            url=url,
        )
    return R.HealthResult(
        remote=spec.id,
        ok=False,
        state="DEGRADED",
        detail=_redact(
            f"http {result.status} on /api/health — "
            f"{result.error or 'no usable response'}"
        ),
        http_status=result.status,
        latency_ms=result.latency_ms,
        url=url,
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def _openmuse_list(spec: Any, timeout: float, query: str = "") -> Any:
    base = _base(spec)
    if not base:
        return _fail(spec, "list", "base_url is empty", gap="openmuse_no_base_url")
    timeout_s = min(float(timeout or R._OPERATE_TIMEOUT_S), 10.0)

    tasks: list[dict[str, Any]] = []
    source_path = "/api/agent/tasks"
    result, err, token = _openmuse_call(spec, "GET", source_path, timeout=timeout_s)
    if err is not None:
        return err
    if result.status in (404, 405):
        # This build mounts no task index. Fall back to the service snapshot.
        # NOTE THE MISSING TRAILING SLASH, and do not "tidy" it back in: the
        # snapshot route is `/api/agent`, and Hono treats `/api/agent/` as a
        # DIFFERENT, unmounted route that 404s. Measured on the live instance:
        #   GET /api/agent       -> 200 {"tasks":[...], goals, artifacts, ...}
        #   GET /api/agent/      -> 404
        # so requesting the slashed form made every OpenMuse seat look sessionless
        # and made this branch report a falsehood to the operator.
        source_path = "/api/agent"
        result, err, token = _openmuse_call(spec, "GET", source_path, timeout=timeout_s)
        if err is not None:
            return err
        if result.status in (404, 405):
            return R.OperateResult(
                remote=spec.id,
                op="list",
                ok=True,
                detail=(
                    "This OpenMuse build exposes no task list: GET /api/agent/tasks "
                    "and GET /api/agent both returned "
                    f"{result.status}. The seat has no enumerable sessions; a send "
                    "still creates a task and returns its id"
                ),
                http_status=result.status,
                data=_scrub(
                    {
                        "tasks": [],
                        "rows_are": "tasks",
                        "resume_key": "task_id",
                        "sessions": [],
                        # The picker needs a selectable target or the seat is
                        # unusable; "new task" is the one honest choice here.
                        "agents": _openmuse_agents([]),
                        "bots": _openmuse_agents([]),
                        "source": "openmuse",
                        "list_supported": False,
                    },
                    spec,
                    token,
                ),
            )
    if result.status in R._AUTH:
        return _auth_gap(
            spec, "list", detail="OpenMuse refused the session", status=result.status
        )
    if result.status not in R._UP:
        return _fail(
            spec,
            "list",
            R._unreachable_detail(result, f"OpenMuse GET {source_path}"),
            gap="openmuse_list_failed",
            status=result.status,
            data=result.body or result.text or None,
            token=token,
        )
    tasks = _task_rows(result.body)
    published = [row for row in (openmuse_task_row(task) for task in tasks) if row]
    matched = [row for row in published if _matches_query(row, query)]
    return R.OperateResult(
        remote=spec.id,
        op="list",
        ok=True,
        detail=(
            f"OpenMuse listed {len(matched)} of {len(published)} task(s) via GET "
            f"{source_path} — rows are OpenMuse tasks; send resumes on task_id"
        ),
        http_status=result.status,
        data=_scrub(
            {
                "tasks": matched,
                "rows_are": "tasks",
                "resume_key": "task_id",
                "sessions": matched,
                # Real tasks are selectable by id, so picking one resumes it.
                "agents": _openmuse_agents(matched),
                "bots": _openmuse_agents(matched),
                "source": "openmuse",
            },
            spec,
            token,
        ),
    )


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


# Sentinel the navbar picker offers when the instance mounts no task index, so
# the seat is still selectable and a send creates a real task. It is an explicit
# "start something new" affordance, NOT a fabricated session: it never appears
# as history, and the send path treats it as "no resume key".
NEW_TASK_ID = "new-task"
NEW_TASK_LABEL = "New OpenMuse task"


def _openmuse_agents(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Selectable targets for the navbar agent picker.

    The picker (`remoteAgentsFromOperate` -> `ombBotsFromOperate`) reads
    `agents` / `bots` from the list payload, so a list that carries only
    `sessions` leaves an OpenMuse seat with nothing to pick and send refuses
    with no target. Real tasks are offered by id, so picking one resumes it;
    with no task index the single honest choice is "start a new task".
    """
    agents = [
        {"id": str(row.get("id") or "").strip(), "name": str(row.get("title") or "").strip() or "OpenMuse task"}
        for row in rows
        if str(row.get("id") or "").strip()
    ]
    if not agents:
        agents = [{"id": NEW_TASK_ID, "name": NEW_TASK_LABEL}]
    return [{"id": a["id"], "name": a["name"] or a["id"]} for a in agents]


def _resolve_task_id(
    spec: Any, target: str, session_id: str | None
) -> tuple[str, str]:
    """Return ``(task_id, error)``; ``error`` is ``self`` / ``bad-id`` / "".

    Mirrors TrueForge's ``#1159`` guard: the remote's own name is never a
    task id, so a seat that never picked a task refuses before any wire
    call instead of asking OpenMuse for a task called "openmuse".

    The ``new-task`` sentinel means "no task yet" — it resolves to an empty
    id so the send creates one, rather than polling for a task that the
    instance has never heard of.
    """
    raw = (session_id or "").strip() or (target or "").strip()
    if not raw:
        raw = str(getattr(spec, "agent", "") or "").strip()
    if not raw:
        return "", ""
    if raw == NEW_TASK_ID:
        return "", ""
    if _is_remote_label(spec, raw):
        return "", "self"
    if not _ID_RE.match(raw):
        return "", "bad-id"
    return raw, ""


def _openmuse_task_result(
    spec: Any,
    task_id: str,
    detail: dict[str, Any],
    *,
    state: str,
    token: str,
    continued_from: str = "",
) -> Any:
    """Build the send result for a task the poll loop stopped on."""
    pending = openmuse_pending_question(detail, task_id=task_id)
    reply = openmuse_task_text(detail)
    # #1660: the instance ran a turn and produced an answer (or asked a
    # question — either way the model answered), so it is serving MODEL now.
    # That is the only recovery signal that actually proves the fix.
    _clear_model_rejection(spec)
    if pending is not None:
        ask = str(pending["question"].get("ask") or "").strip()
        if ask and ask not in reply:
            reply = f"{reply}\n\n{ask}".strip() if reply else ask
    return R.OperateResult(
        remote=spec.id,
        op="send",
        ok=True,
        detail=reply or f"OpenMuse task {task_id} finished with status '{state or 'unknown'}'",
        http_status=200,
        data=_scrub(
            {
                "session_id": task_id,
                "task_id": task_id,
                "status": state,
                "task": detail,
                "text": reply,
                "response": reply,
                "source": "openmuse",
                **({"continued_from": continued_from} if continued_from else {}),
                **(
                    {
                        "awaiting_input": True,
                        "pending_question": pending["question"],
                        "pending_action": {
                            "type": pending["type"],
                            "task_id": task_id,
                            "question_id": pending["question"]["id"],
                            "input_path": f"/api/agent/tasks/{task_id}/input",
                        },
                    }
                    if pending is not None
                    else {}
                ),
            },
            spec,
            token,
        ),
    )


def _openmuse_poll(
    spec: Any,
    task_id: str,
    detail: dict[str, Any],
    *,
    deadline: float,
    timeout_s: float,
    token: str = "",
    continued_from: str = "",
) -> Any:
    """Poll ``GET /api/agent/tasks/:id`` until terminal, paused, or out of time."""
    state = _task_state(detail)
    while True:
        if openmuse_pending_question(detail, task_id=task_id) is not None:
            return _openmuse_task_result(
                spec,
                task_id,
                detail,
                state=state,
                token=token,
                continued_from=continued_from,
            )
        if state in _TERMINAL_STATES:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _fail(
                spec,
                "send",
                (
                    f"OpenMuse task {task_id} did not finish before the "
                    f"{timeout_s:.1f}s deadline (status: {state or 'unknown'}). "
                    "It is still running on the OpenMuse instance — retry or "
                    "control it there."
                ),
                gap="openmuse_task_timeout",
                data={"session_id": task_id, "task_id": task_id, "status": state},
                token=token,
            )
        R.interruptible_sleep(min(_OPENMUSE_POLL_INTERVAL_S, remaining))
        result, err, used = _openmuse_call(
            spec,
            "GET",
            f"/api/agent/tasks/{quote(task_id, safe='')}",
            timeout=min(3.0, max(1.0, remaining)),
        )
        if err is not None:
            return err
        token = token or used
        if result.status == 404:
            return _fail(
                spec,
                "send",
                f"OpenMuse task {task_id} is gone (404).",
                gap="openmuse_task_missing",
                status=404,
                data={"session_id": task_id, "task_id": task_id},
                token=token,
            )
        if result.status in R._AUTH:
            return _auth_gap(
                spec, "send", detail="OpenMuse refused the session", status=result.status
            )
        if result.status not in R._UP:
            return _fail(
                spec,
                "send",
                R._unreachable_detail(result, f"OpenMuse GET task {task_id}"),
                gap="openmuse_poll_failed",
                status=result.status,
                data=result.body or result.text or None,
                token=token,
            )
        detail = result.body if isinstance(result.body, dict) else {}
        state = _task_state(detail)

    if state in _FAILED_STATES:
        reason = _task_error_text(detail) or f"status '{state}'"
        # #1660: the server just told us, in as many words, that the model is
        # not one it serves. Latch that before it is buried in a chat bubble,
        # so health stops saying UP for a seat that cannot answer anything.
        model_rejected = _note_model_rejection(spec, reason)
        return _fail(
            spec,
            "send",
            f"OpenMuse task {task_id} failed ({reason}).",
            gap="openmuse_model_rejected" if model_rejected else "openmuse_task_failed",
            status=200,
            data={
                "session_id": task_id,
                "task_id": task_id,
                "status": state,
                "task": detail,
                "text": openmuse_task_text(detail),
            },
            token=token,
        )
    return _openmuse_task_result(
        spec, task_id, detail, state=state, token=token, continued_from=continued_from
    )


def _openmuse_create_task(
    spec: Any, prompt: str, *, deadline: float, timeout_s: float
) -> Any:
    """``POST /api/agent/tasks`` then poll. Returns an :class:`OperateResult`."""
    result, err, token = _openmuse_call(
        spec,
        "POST",
        "/api/agent/tasks",
        body={"prompt": prompt},
        timeout=min(8.0, max(1.0, timeout_s)),
    )
    if err is not None:
        return err
    if result.status in R._AUTH:
        return _auth_gap(
            spec, "send", detail="OpenMuse refused the session", status=result.status
        )
    if result.status not in R._UP and result.status != 201:
        return _openmuse_create_failed(spec, result, token)
    task = result.body if isinstance(result.body, dict) else {}
    task_id = _task_id_of(task)
    if not task_id:
        return _fail(
            spec,
            "send",
            "OpenMuse POST /api/agent/tasks did not return a task id.",
            gap="openmuse_no_task_id",
            status=result.status,
            data=result.body,
            token=token,
        )
    return _openmuse_poll(
        spec, task_id, task, deadline=deadline, timeout_s=timeout_s, token=token
    )


def _openmuse_create_failed(spec: Any, result: Any, token: str) -> Any:
    """Map the documented createTask rejections onto honest gaps."""
    body = result.body if isinstance(result.body, dict) else {}
    server_detail = _server_error(body)
    status = result.status
    # #1660: a build that validates MODEL at create time rejects it here
    # rather than inside a task. Latch the same way, and report it as the
    # model rejection it is instead of a generic create failure.
    if _note_model_rejection(spec, server_detail):
        return _fail(
            spec,
            "send",
            (
                f"OpenMuse refused the task because its configured MODEL is not "
                f"served: {server_detail}. Fix MODEL on the OpenMuse host as "
                "<provider>/<model-id> and restart it."
            ),
            gap="openmuse_model_rejected",
            status=status,
            data=result.body,
            token=token,
        )
    if status == 422:
        return _fail(
            spec,
            "send",
            (
                f"OpenMuse rejected the prompt ({server_detail or 'schema validation failed'}). "
                "A task prompt must be 1-12000 characters."
            ),
            gap="openmuse_prompt_rejected",
            status=status,
            data=result.body,
            token=token,
        )
    if status == 404:
        return _fail(
            spec,
            "send",
            f"OpenMuse refused the task goal ({server_detail or 'Goal not found'}).",
            gap="openmuse_goal_missing",
            status=status,
            data=result.body,
            token=token,
        )
    if status == 409:
        return _fail(
            spec,
            "send",
            (
                f"{server_detail or 'Finish or cancel some tasks before adding more'}. "
                "This OpenMuse instance caps non-terminal tasks; cancel or finish "
                "one there, or control it from OS with op=cancel / op=retry."
            ),
            gap="openmuse_task_limit",
            status=status,
            data=result.body,
            token=token,
        )
    return _fail(
        spec,
        "send",
        R._unreachable_detail(result, "OpenMuse POST /api/agent/tasks"),
        gap="openmuse_create_failed",
        status=status,
        data=result.body or result.text or None,
        token=token,
    )


def _openmuse_send(
    spec: Any,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> Any:
    text = (prompt or "").strip()
    if not text:
        return _fail(spec, "send", "prompt is required", gap="openmuse_prompt_required")
    if len(text) > _PROMPT_MAX:
        return _fail(
            spec,
            "send",
            f"OpenMuse task prompts are limited to {_PROMPT_MAX} characters "
            f"(got {len(text)}).",
            gap="openmuse_prompt_rejected",
        )
    if not _base(spec):
        return _fail(spec, "send", "base_url is empty", gap="openmuse_no_base_url")
    task_id, task_err = _resolve_task_id(spec, target, session_id)
    if task_err == "self":
        return _fail(
            spec,
            "send",
            (
                f"This {R.kind_label(spec.id)} remote has no task wired — the send "
                "would use the remote's own name as a task id. Pick a task from the "
                "History picker, or set a task id in Settings → Remotes."
            ),
            gap="openmuse_task_required",
            action=R._settings_action(spec.id, "agent"),
            data={"missing_task": True, "rejected_task_name": spec.id},
        )
    if task_err == "bad-id":
        return _fail(
            spec,
            "send",
            "An OpenMuse resume key must be a task id (letters, digits, . _ -).",
            gap="openmuse_task_id_invalid",
        )

    timeout_s = float(timeout or R._OPERATE_SEND_TIMEOUT_S)
    deadline = time.monotonic() + timeout_s
    if not task_id:
        return _openmuse_create_task(spec, text, deadline=deadline, timeout_s=timeout_s)
    return _openmuse_continue_task(
        spec, task_id, text, deadline=deadline, timeout_s=timeout_s
    )


def _openmuse_continue_task(
    spec: Any, task_id: str, prompt: str, *, deadline: float, timeout_s: float
) -> Any:
    """Continue an existing task: answer its pending question, or feed it input.

    OpenMuse has no "append a prompt to a finished task" route — ``POST
    /api/agent/tasks/:id/input`` is the only documented way to put more
    into a task. When the server will not take that input (a terminal
    task with no question pending), this starts a fresh task instead of
    pretending the turn continued, and says so in the payload.
    """
    quoted = quote(task_id, safe="")
    probe, err, token = _openmuse_call(
        spec,
        "GET",
        f"/api/agent/tasks/{quoted}",
        timeout=min(5.0, max(1.0, timeout_s)),
    )
    if err is not None:
        return err
    if probe.status in R._AUTH:
        return _auth_gap(
            spec, "send", detail="OpenMuse refused the session", status=probe.status
        )
    if probe.status == 404:
        return _fail(
            spec,
            "send",
            (
                f"There is no OpenMuse task '{task_id}' on this instance (404). "
                "Start a new one by sending without a session id."
            ),
            gap="openmuse_task_missing",
            status=404,
            data={"requested_task_id": task_id},
            token=token,
        )
    if probe.status not in R._UP:
        return _fail(
            spec,
            "send",
            R._unreachable_detail(probe, f"OpenMuse GET task {task_id}"),
            gap="openmuse_task_missing",
            status=probe.status,
            data=probe.body or probe.text or None,
            token=token,
        )
    detail = probe.body if isinstance(probe.body, dict) else {}

    fed, err, fed_token = _openmuse_call(
        spec,
        "POST",
        f"/api/agent/tasks/{quoted}/input",
        # Live schema (engine/routes.ts): {answer: string(1..12000),
        # fields?: Record<string, string|boolean>}. A bare {"value": ...} is
        # rejected with 422 "expected string, received undefined".
        body={"answer": prompt},
        timeout=min(8.0, max(1.0, timeout_s)),
    )
    if err is not None:
        return err
    token = token or fed_token
    if fed.status in R._AUTH:
        return _auth_gap(
            spec, "send", detail="OpenMuse refused the session", status=fed.status
        )
    if fed.status not in R._UP:
        # The task would not take more input. A new task is the honest
        # fallback; the payload records what it continued from.
        fresh = _openmuse_create_task(
            spec, prompt, deadline=deadline, timeout_s=timeout_s
        )
        if fresh.ok and isinstance(fresh.data, dict):
            fresh.data["continued_from"] = task_id
            fresh.data["continued_from_rejected"] = (
                _server_detail(fed) or f"http {fed.status}"
            )
        return fresh
    body = fed.body if isinstance(fed.body, dict) else {}
    return _openmuse_poll(
        spec,
        task_id,
        body or detail,
        deadline=deadline,
        timeout_s=timeout_s,
        token=token,
        continued_from="",
    )


def _server_detail(result: Any) -> str:
    """The server's message from a failed response, envelope key and all."""
    return _openmuse_error(result)


# ---------------------------------------------------------------------------
# pending question resume (the /input answer path)
# ---------------------------------------------------------------------------


def _openmuse_resume_pending(
    spec: Any,
    *,
    session_id: str,
    pending_action: dict[str, Any],
    content: str,
    timeout: float | None = None,
) -> Any:
    """Answer a paused task's question via ``POST /api/agent/tasks/:id/input``.

    The result is again ``awaiting_input`` if OpenMuse asks something else.
    """
    task_id = str(
        (session_id or "").strip()
        or ((pending_action or {}).get("task_id") if isinstance(pending_action, dict) else "")
        or ""
    ).strip()
    if not task_id or _is_remote_label(spec, task_id):
        return _fail(
            spec,
            "send",
            (
                "OpenMuse resume needs the paused task id; the question payload was "
                "incomplete."
            ),
            gap="openmuse_task_required",
        )
    answer = (content or "").strip()
    if not answer:
        return _fail(
            spec, "send", "answer is required", gap="openmuse_answer_required"
        )
    timeout_s = float(timeout or R._OPERATE_SEND_TIMEOUT_S)
    deadline = time.monotonic() + timeout_s
    quoted = quote(task_id, safe="")
    fed, err, token = _openmuse_call(
        spec,
        "POST",
        f"/api/agent/tasks/{quoted}/input",
        # Same live schema as the continue path: {"answer": ...}.
        body={"answer": answer},
        timeout=min(8.0, timeout_s),
    )
    if err is not None:
        return err
    if fed.status in R._AUTH:
        return _auth_gap(
            spec, "send", detail="OpenMuse refused the session", status=fed.status
        )
    if fed.status not in R._UP:
        if fed.status == 404:
            return _fail(
                spec,
                "send",
                f"OpenMuse task {task_id} is gone (404); the question cannot be answered.",
                gap="openmuse_task_missing",
                status=404,
                data=fed.body,
                token=token,
            )
        return _fail(
            spec,
            "send",
            R._unreachable_detail(fed, f"OpenMuse POST task {task_id} input"),
            gap="openmuse_input_failed",
            status=fed.status,
            data=fed.body or fed.text or None,
            token=token,
        )
    body = fed.body if isinstance(fed.body, dict) else {}
    return _openmuse_poll(
        spec, task_id, body, deadline=deadline, timeout_s=timeout_s, token=token
    )


# ---------------------------------------------------------------------------
# control (pause / resume / cancel / retry)
# ---------------------------------------------------------------------------


def _openmuse_control(spec: Any, action: str, task_id: str, timeout: float) -> Any:
    """``POST /api/agent/tasks/:id/control`` with one of the four verbs."""
    verb = (action or "").strip().lower()
    if verb not in _CONTROL_ACTIONS:
        return _fail(
            spec,
            verb or "control",
            (
                f"OpenMuse control takes {' / '.join(_CONTROL_ACTIONS)} "
                f"(got '{verb or ''}')."
            ),
            gap="openmuse_unsupported_control",
        )
    resolved, task_err = _resolve_task_id(spec, task_id, None)
    if task_err or not resolved:
        return _fail(
            spec,
            verb,
            (
                "OpenMuse control needs a task id (the list rows are tasks). Pass one "
                "as the target, or resume one with a session id."
            ),
            gap="openmuse_task_required",
        )
    result, err, token = _openmuse_call(
        spec,
        "POST",
        f"/api/agent/tasks/{quote(resolved, safe='')}/control",
        body={"action": verb},
        timeout=min(5.0, max(1.0, float(timeout or R._OPERATE_TIMEOUT_S))),
    )
    if err is not None:
        return err
    if result.status in R._AUTH:
        return _auth_gap(
            spec, verb, detail="OpenMuse refused the session", status=result.status
        )
    if result.status == 404:
        return _fail(
            spec,
            verb,
            f"OpenMuse task {resolved} is gone (404).",
            gap="openmuse_task_missing",
            status=404,
            token=token,
        )
    if result.status == 409:
        return _fail(
            spec,
            verb,
            (
                f"{_server_detail(result) or 'OpenMuse refused that transition'}: the "
                f"task is not in a state that accepts {verb}."
            ),
            gap="openmuse_control_rejected",
            status=409,
            data=result.body,
            token=token,
        )
    if result.status not in R._UP:
        return _fail(
            spec,
            verb,
            R._unreachable_detail(result, f"OpenMuse POST task {resolved} control"),
            gap="openmuse_control_failed",
            status=result.status,
            data=result.body or result.text or None,
            token=token,
        )
    return R.OperateResult(
        remote=spec.id,
        op=verb,
        ok=True,
        detail=f"OpenMuse accepted {verb} on task {resolved}.",
        http_status=result.status,
        data=_scrub(
            {
                "session_id": resolved,
                "task_id": resolved,
                "action": verb,
                "task": result.body if isinstance(result.body, dict) else {},
                "source": "openmuse",
            },
            spec,
            token,
        ),
    )


def _openmuse_operate(
    spec: Any,
    op: str,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    prompt: str = "",  # noqa: ARG001
    target: str = "",
    session_id: str | None = None,
) -> Any:
    """Harness ``operate`` entry: the control verbs, plus list / send.

    ``BoundRemoteHarness.operate`` routes the computer-control verbs to its
    own stub before reaching here, so this only needs OpenMuse's own verbs.
    """
    from swarm.core.remote_harness import unsupported_operate

    action = (op or "").strip().lower()
    if action in _CONTROL_ACTIONS:
        return _openmuse_control(
            spec, action, target or (session_id or ""), timeout
        )
    if action == "list":
        return _openmuse_list(spec, timeout)
    if action == "send":
        return _openmuse_send(
            spec, prompt, timeout, session_id=session_id, target=target
        )
    return unsupported_operate("openmuse", action)
