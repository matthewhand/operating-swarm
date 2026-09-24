"""#812 slice 5 — OpenMousBot (omb) impl bodies, moved verbatim out of
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

__all__ = ['_omb_assistant_after', '_omb_auth_rejection_detail', '_omb_bot_target', '_omb_bots_from', '_omb_find_bot', '_omb_is_bot_text', '_omb_list', '_omb_message_text', '_omb_messages_from', '_omb_mint_dedicated_bot', '_omb_poll_assistant', '_omb_receipt_ids', '_omb_send', '_omb_turn_error', '_omb_turn_start_index', '_pairing_policy_reason', 'summarize_omb_bots']


def _omb_turn_start_index(msgs: list[Any], *, after_id: str = "", prompt: str = "") -> int:
    """Index of the first message row that belongs to the turn just submitted.

    Anything before it is history — a previous turn's failure must never be
    attributed to the new one (#471).
    """
    if after_id:
        for i, msg in enumerate(msgs):
            if str(msg.get("id") or "") == after_id:
                return i + 1
        return 0
    if prompt.strip():
        want = prompt.strip()
        for i, msg in enumerate(msgs):
            if str(msg.get("role") or "").lower() == "user" and _omb_message_text(msg) == want:
                return i + 1
    return 0


def _omb_turn_error(
    messages: list[Any], *, after_id: str = "", prompt: str = ""
) -> str:
    """Cause of a terminal remote-side turn failure, or ``""`` when there is none.

    A failed OMB turn ends with a non-text activity row rather than bot text::

        {"role": "bot", "kind": "activity",
         "tool": {"name": "error: Internal error", "ok": false}}

    ``_omb_is_bot_text`` deliberately skips activity rows, so without this the
    poller could only run out its deadline and report a misleading timeout while
    the cause sat on the thread (#471). Only rows after the submitted turn count;
    the newest failure wins.
    """
    msgs = [m for m in messages if isinstance(m, dict)]
    start = _omb_turn_start_index(msgs, after_id=after_id, prompt=prompt)
    detail = ""
    for msg in msgs[start:]:
        if str(msg.get("role") or "").lower() not in ("bot", "assistant", "model"):
            continue
        tool = msg.get("tool")
        if not isinstance(tool, dict) or tool.get("ok") is not False:
            continue
        name = str(tool.get("name") or "").strip() or "unknown error"
        if name.lower().startswith("error:"):
            name = name.split(":", 1)[1].strip() or "unknown error"
        detail = name
    return detail
R._HERMES_POLL_INTERVAL_S = 0.4
R._HERMES_POLL_HTTP_TIMEOUT_S = 8.0
R._ANYTHINGLLM_SEND_TIMEOUT_S = 90.0
R._LETTA_SEND_TIMEOUT_S = 90.0
R._FLOWISE_SEND_TIMEOUT_S = 90.0
R._N8N_SEND_TIMEOUT_S = 30.0
R._TRUEFORGE_SEND_TIMEOUT_S = 180.0
R._TRUEFORGE_DONE_STATES = frozenset({"done", "completed", "finished", "success"})
R._TRUEFORGE_ERROR_STATES = frozenset(
    {"error", "failed", "cancelled", "canceled", "crashed", "aborted", "killed", "timeout", "timed_out"}
)



def summarize_omb_bots(payload: Any) -> list[dict[str, str]]:
    """Map GET /api/bots (or R.operate list data) to ``{id, name}`` rows.

    Nested ``messages`` payloads are dropped — a live OMB dump can be hundreds
    of KB per bot and is not a navbar option.
    """
    raw: Any = payload
    if isinstance(payload, dict):
        raw = (
            payload.get("bots")
            or payload.get("agents")
            or payload.get("members")
            or payload.get("data")
            or []
        )
        if isinstance(raw, dict):
            raw = raw.get("bots") or raw.get("agents") or raw.get("data") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            bot_id = item.strip()
            name = bot_id
        elif isinstance(item, dict):
            bot_id = str(item.get("id") or item.get("bot_id") or "").strip()
            name = str(item.get("name") or item.get("title") or bot_id).strip() or bot_id
        else:
            continue
        if not bot_id or bot_id in seen:
            continue
        seen.add(bot_id)
        out.append({"id": bot_id, "name": name})
    return out


def _omb_mint_dedicated_bot(spec: RemoteSpec, headers: dict[str, str], timeout_s: float) -> HttpResult:
    base_url = (spec.base_url or "").rstrip("/")
    return R.http_json(
        "POST",
        f"{base_url}/api/bots",
        headers=headers,
        body={"name": R.OMB_DEDICATED_BOT_NAME},
        timeout=timeout_s,
    )


def _omb_bot_target(target: str) -> str:
    """Treat remote-kind ids as no bot so send does not POST /api/bots/omb."""
    raw = (target or "").strip()
    if not raw or raw.lower() in R._OMB_NON_BOT_TARGETS:
        return ""
    return raw


def _omb_message_text(msg: Any) -> str:
    if not isinstance(msg, dict):
        return ""
    for key in ("text", "content"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _omb_is_bot_text(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    role = str(msg.get("role") or "").lower()
    if role not in ("bot", "assistant", "model"):
        return False
    kind = str(msg.get("kind") or "text").lower()
    if kind in ("activity", "tool", "card", "screen", "image"):
        return False
    return bool(_omb_message_text(msg))


def _omb_messages_from(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("messages", "thread"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return []


def _omb_bots_from(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        bots = payload.get("bots") or payload.get("agents") or payload.get("data") or []
    else:
        bots = payload
    return bots if isinstance(bots, list) else []


def _omb_find_bot(payload: Any, bot_id: str) -> dict[str, Any] | None:
    """Resolve a listed bot by id, else by name (``_omb_send`` takes either)."""
    needle = (bot_id or "").strip()
    if not needle:
        return None
    by_name: dict[str, Any] | None = None
    for item in _omb_bots_from(payload):
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == needle:
            return item
        if by_name is None and str(item.get("name") or "") == needle:
            by_name = item
    return by_name


def _omb_receipt_ids(body: Any) -> tuple[str, str]:
    """threadId and user message id from POST /messages 202 receipt."""
    if not isinstance(body, dict):
        return "", ""
    thread_id = str(body.get("threadId") or "").strip()
    msg = body.get("message")
    user_id = ""
    if isinstance(msg, dict):
        user_id = str(msg.get("id") or "").strip()
        if not thread_id:
            thread_id = str(msg.get("threadId") or "").strip()
    return thread_id, user_id


def _omb_assistant_after(
    messages: list[Any], *, after_id: str = "", prompt: str = ""
) -> tuple[str, str]:
    """First bot text after the user turn. Returns (text, message_id)."""
    msgs = [m for m in messages if isinstance(m, dict)]
    start = 0
    if after_id:
        for i, msg in enumerate(msgs):
            if str(msg.get("id") or "") == after_id:
                start = i + 1
                break
    elif prompt.strip():
        want = prompt.strip()
        for i, msg in enumerate(msgs):
            if str(msg.get("role") or "").lower() == "user" and _omb_message_text(msg) == want:
                start = i + 1
    for msg in msgs[start:]:
        if _omb_is_bot_text(msg):
            return _omb_message_text(msg), str(msg.get("id") or "").strip()
    return "", ""


def _omb_poll_assistant(
    spec: R.RemoteSpec,
    *,
    bot_id: str,
    prompt: str,
    thread_id: str,
    after_id: str,
    timeout: float,
) -> tuple[str, str, str, str]:
    """Poll OMB until a bot text exists after the user turn.

    Returns ``(text, thread_id, error, message_id)``. Follow-ups on the same
    thread are not waited for here — ``omb_session_watch`` (issue #125).
    """
    headers = R._auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    deadline = time.monotonic() + max(float(timeout), 0.0)
    http_timeout = min(R._OMB_POLL_HTTP_TIMEOUT_S, max(float(timeout), 0.5))
    last_activity = ""
    saw_bot = False
    busy = True
    while True:
        listed = R.http_json(
            "GET",
            f"{base_url}/api/bots?messages=20",
            headers=headers,
            timeout=http_timeout,
        )
        bot = _omb_find_bot(listed.body, bot_id) if listed.status in R._UP else None
        messages: list[Any] = []
        if isinstance(bot, dict):
            saw_bot = True
            thread_id = thread_id or str(bot.get("threadId") or "").strip()
            last_activity = str(bot.get("activity") or "")
            busy = bool(bot.get("busy"))
            messages = _omb_messages_from(bot)
        if thread_id:
            page = R.http_json(
                "GET",
                f"{base_url}/api/threads/{thread_id}/messages?limit=40",
                headers=headers,
                timeout=http_timeout,
            )
            if page.status in R._UP:
                thread_msgs = _omb_messages_from(page.body)
                if thread_msgs:
                    messages = thread_msgs
        reply, reply_id = _omb_assistant_after(messages, after_id=after_id, prompt=prompt)
        if last_activity in ("dead", "no-signal"):
            return "", thread_id, f"OpenMousBot turn {last_activity.replace('-', ' ')}", ""
        settled = last_activity == "waiting-on-you" or (saw_bot and not busy)
        # #471: a failed turn ends with an error activity row, not bot text, so
        # the loop used to burn its whole budget and say "timed out" while the
        # cause was on the thread all along. A reply (if one arrives) wins.
        turn_error = "" if reply else _omb_turn_error(messages, after_id=after_id, prompt=prompt)
        if turn_error:
            return "", thread_id, f"{R.OMB_TURN_ERROR_PREFIX}{turn_error}", ""
        if reply:
            terminal = False
            for msg in reversed(messages):
                if isinstance(msg, dict) and _omb_is_bot_text(msg) and _omb_message_text(msg) == reply:
                    terminal = bool(msg.get("turnTerminal"))
                    break
            if terminal or settled:
                return reply, thread_id, "", reply_id
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if last_activity == "waiting-on-you" and not reply:
                return "", thread_id, "OpenMousBot is waiting for operator input", ""
            return "", thread_id, "OpenMousBot reply timed out", ""
        time.sleep(min(max(R._OMB_POLL_INTERVAL_S, 0.0), remaining))


_OMB_PAIRING_MARKERS = ("loopback host required", "pair this device", "device pairing", "loopback")


def _pairing_policy_reason(result: HttpResult) -> str:
    """The harness's own pairing/loopback reason, or '' (#541).

    Lets health keep reachability and authorisation as separate facts: "up but
    unpaired" must be distinguishable from "down" at a glance.
    """
    body = result.body if isinstance(result.body, dict) else {}
    for key in ("error", "message", "detail", "reason"):
        val = body.get(key)
        if isinstance(val, str) and any(m in val.lower() for m in _OMB_PAIRING_MARKERS):
            return val.strip()
    return ""


def _omb_auth_rejection_detail(spec: RemoteSpec, result: HttpResult, op_label: str) -> str:
    """Honest sentence for an OMB 401/403 — names the real cause (#541).

    - The harness's own reason is carried through when the body carries one;
      our text is fallback only.
    - A pairing/loopback policy rejection never mentions keys or settings:
      the key was accepted, so "set OMB_API_KEY" is misinformation that sends
      the operator to a fix that cannot work.
    - A genuinely missing key still gets the classic, correct hint.
    """
    body = result.body if isinstance(result.body, dict) else {}
    harness_reason = ""
    for key in ("error", "message", "detail", "reason"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            harness_reason = val.strip()
            break
    lowered = harness_reason.lower()
    key_set = bool((spec.api_key or "").strip()) and not R._is_unresolved_placeholder(spec.api_key)
    if harness_reason and any(marker in lowered for marker in _OMB_PAIRING_MARKERS):
        return (
            f"OpenMousBot refused this host: {harness_reason}. "
            "Pair this device with OpenMousBot, call it from its own host "
            "(loopback), or front it with a proxy. Your key is not the problem."
        )
    if not key_set:
        # #494: the field only accepts an env-var name (or ${PLACEHOLDER}) —
        # never a literal key. Name the variable to set, not the field to fill.
        return (
            f"OpenMousBot {op_label} requires auth. Name the env var in "
            "Settings → Remotes (e.g. OMB_API_KEY) and export it before calling."
        )
    if result.status == 401:
        return (
            f"OpenMousBot {op_label} rejected the configured key (http 401). "
            "Check the env var named in Settings → Remotes (OMB_API_KEY)."
        )
    return f"OpenMousBot {op_label} forbidden (http 403)" + (f": {harness_reason}" if harness_reason else "")


def _omb_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or R._OPERATE_TIMEOUT_S), 10.0)
    result = R.http_json(
        "GET",
        f"{base_url}{R._OMB_LIST_PATH}",
        headers=R._auth_headers(spec),
        timeout=timeout_s,
    )
    if result.status in R._UP:
        bots = summarize_omb_bots(result.body)
        return R.OperateResult(
            remote="omb",
            op="list",
            ok=True,
            detail=f"OpenMousBot listed {len(bots)} bot(s) via GET {R._OMB_LIST_PATH}",
            http_status=result.status,
            data={"bots": bots},
        )
    if result.status in R._AUTH:
        return R.OperateResult(
            remote="omb",
            op="list",
            ok=False,
            # #541: distinguish "key missing" from "policy refused this host"
            # instead of always claiming the config is at fault.
            detail=_omb_auth_rejection_detail(spec, result, "list"),
            http_status=result.status,
            data=result.body,
            gap=R.OMB_BOT_REQUIRED_GAP,
            # #494: only the missing-key case is fixed by Settings. A policy
            # refusal must not send the operator to a settings field.
            action=None if _pairing_policy_reason(result) else R._settings_action("omb"),
        )
    return R.OperateResult(
        remote="omb",
        op="list",
        ok=False,
        detail=result.error or f"OpenMousBot list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
        gap=R.OMB_BOT_REQUIRED_GAP,
    )


def _omb_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    if not prompt.strip():
        return R.OperateResult(remote="omb", op="send", ok=False, detail="prompt is required")
    bot_id = _omb_bot_target(target)
    headers = R._auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or R._OPERATE_TIMEOUT_S), 10.0)
    minted = False
    if bot_id:
        listed = _omb_list(spec, timeout_s)
        if listed.ok:
            found = _omb_find_bot(listed.data, bot_id)
            if found:
                bot_id = str(found.get("id") or bot_id)
        # Target already names a bot (id or name). Never mint a second one.
    else:
        # Never default to bots[0] (specialists). Mint a dedicated bot only
        # when the operator did not pick an agent.
        created = _omb_mint_dedicated_bot(spec, headers, timeout_s)
        if created.status in R._UP and isinstance(created.body, dict):
            bot = created.body.get("bot") or created.body
            if isinstance(bot, dict):
                bot_id = str(bot.get("id") or "").strip()
            minted = True
        if not bot_id:
            return R.OperateResult(
                remote="omb",
                op="send",
                ok=False,
                detail=(
                    "No OpenMousBot agent selected. Pick a listed bot id "
                    "(navbar / R.operate target); send will not guess bots[0] "
                    "and could not mint a dedicated open-swarm bot."
                ),
                http_status=created.status,
                data=created.body or created.text,
                gap=R.OMB_BOT_REQUIRED_GAP,
            )
    result = R.http_json(
        "POST",
        f"{base_url}/api/bots/{bot_id}/messages",
        headers=headers,
        body={"text": prompt},
        timeout=timeout_s,
    )
    if result.status not in R._UP:
        if result.status in R._AUTH:
            # #541: same honest classification as list — pairing policy vs key.
            return R.OperateResult(
                remote="omb",
                op="send",
                ok=False,
                detail=_omb_auth_rejection_detail(spec, result, "send"),
                http_status=result.status,
                data=result.body or result.text,
            )
        return R.OperateResult(
            remote="omb",
            op="send",
            ok=False,
            detail=R._unreachable_detail(result, "OpenMousBot send"),
            http_status=result.status,
            data=result.body or result.text,
        )
    thread_id, after_id = _omb_receipt_ids(result.body)
    poll_timeout = min(float(timeout or R._OMB_REPLY_TIMEOUT_S), R._OMB_REPLY_TIMEOUT_S)
    text, thread_id, err, message_id = _omb_poll_assistant(
        spec,
        bot_id=bot_id,
        prompt=prompt,
        thread_id=thread_id,
        after_id=after_id,
        timeout=poll_timeout,
    )
    if text:
        return R.OperateResult(
            remote="omb",
            op="send",
            ok=True,
            detail="OpenMousBot reply",
            http_status=result.status,
            data={
                "bot_id": bot_id,
                "text": text,
                "thread_id": thread_id,
                "message_id": message_id,
                "minted": minted,
            },
        )
    return R.OperateResult(
        remote="omb",
        op="send",
        ok=False,
        detail=err or "OpenMousBot reply timed out",
        http_status=result.status,
        data={"bot_id": bot_id, "thread_id": thread_id},
        # #471: the remote named a cause — keep it distinct from a real timeout.
        gap=(
            "omb_turn_error"
            if (err or "").startswith(R.OMB_TURN_ERROR_PREFIX)
            else "omb_reply_timeout"
            if "timed out" in (err or "")
            else "omb_reply_failed"
        ),
    )


