"""#812 slice 5 — Herdr impl bodies, moved verbatim out of
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

__all__ = ['_herdr_cli_health', '_herdr_health', '_herdr_interrogate', '_herdr_list', '_herdr_pane_text', '_herdr_raw_pane_text', '_herdr_reply_after_timeout', '_herdr_send', 'read_herdr_recent', 'read_herdr_recent_raw', 'sanitize_herdr_response']


def _herdr_cli_health(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:  # noqa: ARG001
    """Health via local herdr or SSH hop (never a guessed host)."""
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import herdr_client_from_spec, resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    mode = resolve_herdr_mode(spec)
    try:
        # #849: per-spec dispatch — named Herdr instances each get their own
        # client; from_remote_config() would hardcode the default "herdr" key.
        client = herdr_client_from_spec(spec)
        payload = client.workspace_list()
    except SSHNotConfiguredError as exc:
        return R.HealthResult(remote="herdr", ok=False, state="UNKNOWN", detail=str(exc))
    except Exception as exc:
        return R.HealthResult(
            remote="herdr",
            ok=False,
            state="DOWN",
            detail=f"Herdr {mode} health failed: {exc}",
        )
    detail = (
        f"ssh {spec.ssh_user}@{spec.ssh_host} · herdr workspace list"
        if mode == "ssh"
        else "local herdr workspace list (no SSH)"
    )
    return R.HealthResult(
        remote="herdr",
        ok=True,
        state="UP",
        detail=detail,
        version=R._extract_version(payload),
        url=spec.ssh_host if mode == "ssh" else "local",
    )


def _herdr_health(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> HealthResult | None:
    """SSH or local-CLI health. None means fall through to localhost HTTP."""
    from swarm.herdr.remote import uses_local_http_health

    if uses_local_http_health(spec):
        return None
    return _herdr_cli_health(spec, timeout, config)



def _herdr_list(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import (
        LIST_PATH,
        members_from_http_list,
        resolve_herdr_mode,
        uses_local_http_health,
    )
    from swarm.herdr.ssh import SSHNotConfiguredError

    if uses_local_http_health(spec):
        result = R.http_json(
            "GET",
            f"{spec.base_url}{LIST_PATH}",
            headers=R._auth_headers(spec),
            timeout=timeout,
        )
        if result.status in R._UP:
            members = members_from_http_list(result.body or {}, remote=spec.base_url)
            return R.OperateResult(
                remote="herdr",
                op="list",
                ok=True,
                detail=f"Herdr listed {len(members)} member(s) via GET {LIST_PATH}",
                http_status=result.status,
                data={"members": members, "raw": result.body},
            )
        if result.status in R._AUTH:
            return R.OperateResult(
                remote="herdr",
                op="list",
                ok=False,
                detail="Herdr GET /agents requires auth. Name the env var in Settings → Remotes (e.g. HERDR_API_KEY) and export it before calling.",
                http_status=result.status,
                data=result.body,
                action=R._settings_action("herdr"),
            )
        return R.OperateResult(
            remote="herdr",
            op="list",
            ok=False,
            detail=result.error or f"Herdr list failed (http {result.status})",
            http_status=result.status,
            data=result.body or result.text,
        )

    mode = resolve_herdr_mode(spec)
    from swarm.herdr.remote import herdr_client_from_spec

    try:
        # #849: per-spec dispatch (named instances, not the default key).
        client = herdr_client_from_spec(spec)
        members = client.discover_members()
    except SSHNotConfiguredError as exc:
        return R.OperateResult(remote="herdr", op="list", ok=False, detail=str(exc))
    except Exception as exc:
        return R.OperateResult(remote="herdr", op="list", ok=False, detail=f"Herdr list failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return R.OperateResult(
        remote="herdr",
        op="list",
        ok=True,
        detail=f"Herdr listed {len(members)} member(s) via {hop}",
        data={"members": members},
    )


def sanitize_herdr_response(text: str) -> str:
    """Strip Herdr banner artifacts and terminal TUI chrome (#790, #850).

    Pane captures regularly include the CLI's persistent bottom status bar,
    progress gauges, and full-width box-drawing separators. None of that is
    conversation — it never reaches chat output. Standard markdown pipe
    tables and user code blocks are strictly preserved.
    """
    if not text or not isinstance(text, str):
        return ""

    # Characters that only appear in TUI chrome, never in prose.
    _tui_gauge_chars = re.compile(r"[▀▄▌▐░▒▓█╹▁▂▃▅▆▇]+")
    _box_drawing_chars = "─━│┃┄┅┆┇┈┉├┝┞┟┠┯┰┱┲┴┵┶┷┸┼╀╁╂╃╄╅╆╇╈╉╊╋"
    _box_only = re.compile(f"^[{re.escape(_box_drawing_chars)}\\s]+$")
    # Status-bar keywords the known CLIs render on their persistent bottom line.
    _status_markers = re.compile(
        r"(ctrl\+[a-z]|commands\s*$|tokens?\s|\(\d+(?:\.\d+)?%\)|\d+(?:\.\d+)?%\s*$|^\s*⎇\s|\bv\d+(?:\.\d+)+\b|ctrl\+c\s+to\s+exit)",
        re.I,
    )

    def _is_table_row(line: str) -> bool:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2):
            return False
        if re.match(r"^\s*\|\s*\|\s*(?:summary|conversation)", stripped, re.I):
            return False
        if any(c in stripped for c in _box_drawing_chars) or _tui_gauge_chars.search(stripped):
            return False
        return True

    def _is_tui_chrome(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if _is_table_row(line):
            return False
        # Box-drawing-only rule/separator lines.
        if _box_only.match(stripped):
            return True
        has_box = any(c in stripped for c in _box_drawing_chars)
        has_gauge = bool(_tui_gauge_chars.search(stripped))
        has_status = bool(_status_markers.search(stripped))

        if (has_box or has_gauge) and has_status:
            return True
        without_gauge = _tui_gauge_chars.sub("", stripped)
        if has_gauge and len(without_gauge.strip()) <= 40:
            return True
        if has_status and (has_box or has_gauge or "ctrl+" in stripped.lower()):
            return True
        if re.match(r"^[┃│\|\s]{2,}\s*(?:Build|Session|Task|Model|Run|\w+)", stripped) and (
            has_box or has_gauge or has_status or "build" in stripped.lower()
        ):
            return True
        return False

    lines = text.splitlines()
    cleaned = []
    in_code_block = False
    in_header = True
    for line in lines:
        stripped = line.strip()
        # Preserve user code blocks entirely
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            cleaned.append(line)
            in_header = False
            continue
        if in_code_block:
            cleaned.append(line)
            continue

        if in_header:
            if re.match(
                r"^\s*\|\s*\|\s*(?:summary\s+of\s+(?:the\s+)?conversation|conversation\s+summary|summary)\s*\|\s*$",
                line,
                re.I,
            ):
                continue
            if re.match(r"^\s*\|[-:\s|]+\|\s*$", line):
                continue
            if not stripped and not cleaned:
                continue
            in_header = False

        if _is_tui_chrome(line):
            continue
        cleaned.append(line)

    while cleaned and _is_tui_chrome(cleaned[-1]):
        cleaned.pop()

    return "\n".join(cleaned).strip()


def _herdr_raw_pane_text(payload: Any) -> str:
    """Raw pane text from ``agent_read`` / prompt result without sanitization."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        text = payload.strip()
        if text.lower() in {"agent_prompted", '{"type":"agent_prompted"}'}:
            return ""
        return text
    if isinstance(payload, dict):
        ptype = str(payload.get("type") or "").strip().lower()
        if ptype == "agent_prompted":
            nested = payload.get("text") or payload.get("output") or payload.get("content")
            if nested is not None and nested is not payload:
                return _herdr_raw_pane_text(nested)
            return ""
        for key in ("text", "output", "content", "message", "result"):
            val = payload.get(key)
            if val is payload:
                continue
            found = _herdr_raw_pane_text(val)
            if found:
                return found
    return ""


def _herdr_pane_text(payload: Any) -> str:
    """Pane text from ``agent_read`` / prompt result — sanitized."""
    return sanitize_herdr_response(_herdr_raw_pane_text(payload))


def read_herdr_recent_raw(target: str, config: dict[str, Any] | None = None) -> str:
    """Read raw unsanitized recent pane text from Herdr for a given target pane/session."""
    if not target or not target.strip():
        return ""
    try:
        from swarm.core.remote_teams import herdr_client_from_settings

        client = herdr_client_from_settings(config=config)
        read = client.agent_read(target.strip(), source="recent", fmt="text")
        return _herdr_raw_pane_text(read)
    except Exception:
        R.logger.debug("Failed to read raw recent Herdr pane text for target %s", target, exc_info=True)
        return ""


def read_herdr_recent(target: str, config: dict[str, Any] | None = None) -> str:
    """Read recent pane text from Herdr for a given target pane/session."""
    return sanitize_herdr_response(read_herdr_recent_raw(target, config=config))


def _herdr_reply_after_timeout(
    client: Any,
    pane: str,
    before_seq: int | None,
) -> str:
    """Read the pane after a wait timeout, but only if the pane actually moved.

    #470: the stopped-state wait can expire while a reply is already on screen
    (an agent that settles in ``done`` used to be reported as a timeout and its
    reply thrown away). ``state_change_seq`` gates the read so an untouched pane
    can never hand stale text back as this turn's answer.
    """
    if client is None:
        return ""
    from swarm.herdr.client import extract_state_change_seq

    try:
        after_seq = extract_state_change_seq(client.agent_get(pane))
        if before_seq is None or after_seq is None or after_seq == before_seq:
            return ""
        read = client.agent_read(pane, source="recent", fmt="text")
    except Exception:
        return ""
    return _herdr_pane_text(read)


def _herdr_live_pane_ids(client: Any) -> list[str]:
    """#1144: pane ids that actually exist right now (best-effort, deduped)."""
    from swarm.herdr.client import members_from_agent_list, members_from_workspace_list

    try:
        rows = members_from_agent_list(client.agent_list(), remote="herdr")
    except Exception:
        try:
            rows = members_from_workspace_list(client.workspace_list(), remote="herdr")
        except Exception:
            return []
    ids: list[str] = []
    for row in rows or []:
        # members rows carry the routing target under ``name`` (pane id);
        # accept ``target``/``display`` spellings too.
        tid = str((row or {}).get("name") or (row or {}).get("target") or "").strip()
        if tid and tid not in ids:
            ids.append(tid)
    return ids


def _herdr_send(spec: RemoteSpec, prompt: str, target: str, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:
    from swarm.herdr.client import (
        WAIT_UNTIL_STOPPED,
        HerdrAgentMissingError,
        HerdrBlockedError,
        HerdrCLIError,
        HerdrClient,
        extract_agent_state,
        extract_state_change_seq,
    )
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    if not prompt.strip():
        return R.OperateResult(remote="herdr", op="send", ok=False, detail="prompt is required")
    mode = resolve_herdr_mode(spec)
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    timeout_s = float(timeout or R._OPERATE_SEND_TIMEOUT_S)
    timeout_ms = max(1, int(timeout_s * 1000))
    pane = (target or "").strip()
    client: Any = None
    before_seq: int | None = None
    try:
        from swarm.herdr.remote import herdr_client_from_spec

        # #849: per-spec dispatch (named instances, not the default key).
        client = herdr_client_from_spec(spec)
        # #728: an omitted target is no longer a dead end. One member in the
        # workspace → auto-target it; several → honest error naming every
        # choice (target + name) so the user can pick; discovery failure →
        # keep the original refusal copy.
        if not pane:
            try:
                members = client.discover_members()
            except Exception:
                members = []
            # discover_members() rows carry the CLI id under ``name`` (with
            # ``target``/``id`` absent); accept all three spellings and keep
            # the target→display-name pairing in one pass (no zip desync).
            rows: list[dict[str, str]] = []
            for m in members:
                if not isinstance(m, dict):
                    continue
                tid = str(m.get("target") or m.get("id") or m.get("name") or "").strip()
                if not tid:
                    continue
                label = str(m.get("display") or m.get("name") or "").strip()
                rows.append({"target": tid, "name": label})
            if len(rows) == 1:
                pane = rows[0]["target"]
            elif rows:
                names = ", ".join(
                    f"{r['target']} ({r['name']})"
                    if r["name"] and r["name"] != r["target"]
                    else r["target"]
                    for r in rows
                )
                return R.OperateResult(
                    remote="herdr",
                    op="send",
                    ok=False,
                    detail=(
                        f"Several Herdr agents are running — pick one: {names}. "
                        "Chat with a specific agent from the rail menu "
                        "(Select session) or name the pane id."
                    ),
                    data={"targets": [r["target"] for r in rows]},
                )
            else:
                return R.OperateResult(
                    remote="herdr",
                    op="send",
                    ok=False,
                    detail="target is required (Herdr pane / CLI id, e.g. w3:p1 or grok)",
                )
        # One `agent get` serves three jobs now: refuse a blocked pane with
        # its pending question surfaced (#740), remember where the pane was
        # so a post-timeout read cannot hand back stale text (#470), and —
        # since #728 — confirm the auto-targeted pane actually exists.
        try:
            state_payload = client.agent_get(pane)
        except Exception:
            state_payload = None
        before_seq = extract_state_change_seq(state_payload)
        if extract_agent_state(state_payload) == "blocked":
            raise HerdrBlockedError(pane)
        payload = client.agent_prompt(
            pane,
            prompt,
            wait=True,
            # idle | done | blocked — a finished turn settles in ``done`` and
            # never returns to ``idle``, so waiting on ``idle`` alone could only
            # expire (#470).
            until=WAIT_UNTIL_STOPPED,
            timeout_ms=timeout_ms,
            check_blocked=False,
        )
        read = client.agent_read(pane, source="recent", fmt="text")
        # #728: `target` may have arrived empty (auto-targeted); every
        # payload below must name the pane that actually answered.
        target = pane
    except SSHNotConfiguredError as exc:
        return R.OperateResult(remote="herdr", op="send", ok=False, detail=str(exc))
    except HerdrAgentMissingError as exc:
        # #1144: the bound pane was deleted — never dump the raw CLI JSON.
        # Offer the rebind path and name the panes that DO exist.
        available = _herdr_live_pane_ids(client)
        listing = ", ".join(available[:6]) if available else "none right now"
        return R.OperateResult(
            remote="herdr",
            op="send",
            ok=False,
            detail=(
                f"The Herdr pane {pane} no longer exists — the seat's binding is stale. "
                f"Rebind it (rail menu → Select session, or Settings → Remotes → herdr). "
                f"Live panes: {listing}."
            ),
            data={"target": pane, "missing": True, "available": available},
        )
    except HerdrBlockedError as exc:
        # #740: a blocked pane is a CLI sitting at an approval/question
        # prompt. Surface WHAT it is asking (the pane's recent text) and HOW
        # to answer it, instead of a bare "submit rejected".
        pending = ""
        if client is not None:
            try:
                raw = client.agent_read(pane, source="recent", fmt="text")
                pending = _herdr_pane_text(raw)
            except Exception:
                pending = ""
        target = pane
        detail = str(exc)
        if pending:
            detail = (
                f"{detail} The agent is waiting on: “{pending}” — "
                f"answer it in the Herdr pane ({pane}), then resend."
            )
        return R.OperateResult(
            remote="herdr",
            op="send",
            ok=False,
            detail=detail,
            data={"target": pane, "blocked": True, "pending_prompt": pending or None},
        )
    except HerdrCLIError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            # The wait expired — but the agent may have answered anyway (`done`
            # turns, slow TUIs). Read the pane before calling it a failure #470.
            rescued = _herdr_reply_after_timeout(client, pane, before_seq)
            if rescued:
                return R.OperateResult(
                    remote="herdr",
                    op="send",
                    ok=True,
                    detail=f"Herdr reply from {target} via {hop} (recovered after the wait timeout)",
                    data={
                        "target": target,
                        "text": rescued,
                        "response": rescued,
                        "raw_response": rescued,
                        "transport": mode,
                    },
                )
            return R.OperateResult(
                remote="herdr",
                op="send",
                ok=False,
                detail=f"Herdr send timed out after {timeout_s:.0f}s",
                data={"target": target},
                gap="herdr_reply_timeout",
            )
        return R.OperateResult(remote="herdr", op="send", ok=False, detail=f"Herdr send failed: {exc}")
    except Exception as exc:
        return R.OperateResult(remote="herdr", op="send", ok=False, detail=f"Herdr send failed: {exc}")
    raw_text = _herdr_raw_pane_text(read) or _herdr_raw_pane_text(payload)
    text = sanitize_herdr_response(raw_text)
    if not text:
        return R.OperateResult(
            remote="herdr",
            op="send",
            ok=False,
            detail=f"Herdr wait finished for {target} via {hop} but returned no pane text",
            data={
                "target": target,
                "response": payload,
                "raw_response": raw_text,
                "transport": mode,
            },
            gap="herdr_reply_empty",
        )
    return R.OperateResult(
        remote="herdr",
        op="send",
        ok=True,
        detail=f"Herdr reply from {target} via {hop}",
        data={
            "target": target,
            "text": text,
            "response": text,
            "raw_response": raw_text,
            "transport": mode,
        },
    )


def _herdr_interrogate(spec: RemoteSpec, target: str, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
    """Inspect one CLI/pane Herdr manages (agent get) over local or SSH hop."""
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    if not (target or "").strip():
        return R.OperateResult(
            remote="herdr",
            op="interrogate",
            ok=False,
            detail="target is required to interrogate a CLI Herdr manages (agy / pi / grok / pane id)",
        )
    from swarm.herdr.remote import herdr_client_from_spec

    mode = resolve_herdr_mode(spec)
    try:
        # #849: per-spec dispatch (named instances, not the default key).
        client = herdr_client_from_spec(spec)
        payload = client.agent_get(target.strip())
    except SSHNotConfiguredError as exc:
        return R.OperateResult(remote="herdr", op="interrogate", ok=False, detail=str(exc))
    except Exception as exc:
        return R.OperateResult(remote="herdr", op="interrogate", ok=False, detail=f"Herdr interrogate failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return R.OperateResult(
        remote="herdr",
        op="interrogate",
        ok=True,
        detail=f"Herdr interrogated {target} via {hop}",
        data={"target": target, "agent": payload, "transport": mode},
    )


