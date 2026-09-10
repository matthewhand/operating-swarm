"""REQ-104 / #795 — list and switch CLI-provider sessions (design A).

Selecting a provider session **mints a new Django/chat-store conversation**
bound to that CLI id. The previous swarm thread is not deleted (orphan +
optional prior-history pill). Compressions stay on the old conversation.

Listing prefers each CLI's own list argv or session store (Grok / agy /
OpenCode first). Django Select/New is not the SoT for CLI resume. CLIs
without a verified list degrade to paste-id + swarm-touch recents. Never
invent rows. Ids are scrubbed like REQ-52 (no secrets).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from swarm.core import chat_store, cli_catalog
from swarm.core.cli_session_stores import list_store_sessions
from swarm.core.cli_sessions import (
    get_cli_session,
    put_cli_session,
    sanitize_cli_session_id,
    session_notice_text,
)

logger = logging.getLogger(__name__)

PRIOR_HISTORY_KIND = "prior_history"
PRIOR_HISTORY_LABEL = "Prior history"
RECENT_LIMIT = cli_catalog.RECENT_SESSION_LIMIT
LIST_TIMEOUT = cli_catalog.LIST_SESSIONS_TIMEOUT
INDEX_SCHEMA = 1

RunList = Callable[[list[str], float], tuple[int | None, str, str]]


def switch_notice_text(cli_name: str, session_id: str | None, *, start_new: bool) -> str:
    """Honest status. Never claims restore."""
    if start_new or not session_id:
        return session_notice_text(cli_name, resumed=False)
    return f"Switched to {cli_name} session {session_id}."


def mint_cli_conversation_id(agent_id: str) -> str:
    """Filesystem-safe conversation id for a newly bound CLI session."""
    agent = chat_store.normalize_agent_id(agent_id)
    suffix = uuid.uuid4().hex[:16]
    return f"cli-{agent}-{suffix}"[:128]


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _index_path(user_key: str, *, base_dir: Path | None = None) -> Path | None:
    uk = chat_store.normalize_agent_id(user_key) if user_key else ""
    if not uk:
        return None
    return chat_store.store_dir(base_dir=base_dir) / "cli_session_index" / f"{uk}.json"


def _read_index(user_key: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    path = _index_path(user_key, base_dir=base_dir)
    if path is None or not path.is_file():
        return {"schema": INDEX_SCHEMA, "by_agent": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": INDEX_SCHEMA, "by_agent": {}}
    if not isinstance(data, dict):
        return {"schema": INDEX_SCHEMA, "by_agent": {}}
    agents = data.get("by_agent")
    if not isinstance(agents, dict):
        agents = {}
    return {"schema": INDEX_SCHEMA, "by_agent": agents}


def _write_index(user_key: str, data: dict[str, Any], *, base_dir: Path | None = None) -> None:
    path = _index_path(user_key, base_dir=base_dir)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def remember_recent_session(
    user_key: str,
    agent_id: str,
    cli_name: str,
    session_id: str,
    *,
    title: str = "",
    snippet: str = "",
    updated_at: str = "",
    base_dir: Path | None = None,
) -> None:
    """Record a swarm-touch for the recent list (ids + display metadata only)."""
    sid = sanitize_cli_session_id(session_id)
    if not sid or not user_key:
        return
    agent = chat_store.normalize_agent_id(agent_id)
    cli = chat_store.normalize_agent_id(cli_name)
    data = _read_index(user_key, base_dir=base_dir)
    by_agent = data.setdefault("by_agent", {})
    by_cli = by_agent.setdefault(agent, {})
    rows = [r for r in (by_cli.get(cli) or []) if isinstance(r, dict) and r.get("id") != sid]
    rows.insert(
        0,
        {
            "id": sid,
            "title": (title or sid)[:200],
            "snippet": (snippet or "")[:240],
            "updated_at": updated_at or _iso(),
            "source": "swarm",
        },
    )
    by_cli[cli] = rows[: RECENT_LIMIT * 2]
    _write_index(user_key, data, base_dir=base_dir)


def swarm_recent_sessions(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    limit: int = RECENT_LIMIT,
    base_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Last swarm-touch sessions for this CLI agent (SoT when the CLI cannot list)."""
    if not user_key:
        return []
    agent = chat_store.normalize_agent_id(agent_id)
    cli = chat_store.normalize_agent_id(cli_name)
    data = _read_index(user_key, base_dir=base_dir)
    rows = (data.get("by_agent") or {}).get(agent, {}).get(cli) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = sanitize_cli_session_id(row.get("id"))
        if not sid:
            continue
        out.append(
            {
                "id": sid,
                "title": str(row.get("title") or sid)[:200],
                "snippet": str(row.get("snippet") or "")[:240],
                "updated_at": str(row.get("updated_at") or ""),
                "source": "swarm",
            }
        )
        if len(out) >= limit:
            break
    return out


def _default_run_list(
    argv: list[str],
    timeout: float,
    *,
    cwd: str | None = None,
) -> tuple[int | None, str, str]:
    env = os.environ.copy()
    env["PATH"] = cli_catalog.host_cli_path()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=cwd or None,
            env=env,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return None, "", "timed out"
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _iter_json_blobs(stdout: str):
    text = (stdout or "").strip()
    if not text:
        return
    try:
        yield json.loads(text)
        return
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _stamp_from_unix(value: Any) -> str:
    """Unix seconds or milliseconds → UTC ISO, or empty."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e12:  # milliseconds
            seconds /= 1000.0
        if seconds <= 0:
            return ""
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except (OSError, OverflowError, ValueError):
            return ""
    return ""


def _normalize_updated_at(raw: Any) -> str:
    if raw is None or isinstance(raw, bool):
        return ""
    if isinstance(raw, (int, float)):
        return _stamp_from_unix(raw)
    text = str(raw).strip()
    if not text:
        return ""
    if text.isdigit():
        return _stamp_from_unix(int(text))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00Z"
    return text[:64]


def _row_from_blob(blob: Any) -> dict[str, Any] | None:
    if isinstance(blob, str):
        sid = sanitize_cli_session_id(blob)
        if not sid:
            return None
        return {"id": sid, "title": sid, "snippet": "", "updated_at": "", "source": "provider"}
    if not isinstance(blob, dict):
        return None
    sid = sanitize_cli_session_id(
        blob.get("id")
        or blob.get("session_id")
        or blob.get("sessionId")
        or blob.get("thread_id")
        or blob.get("conversation_id")
        or blob.get("conversationId")
    )
    if not sid:
        return None
    title = str(blob.get("title") or blob.get("name") or sid)[:200]
    snippet = str(
        blob.get("snippet")
        or blob.get("preview")
        or blob.get("summary")
        or blob.get("first_prompt")
        or ""
    )[:240]
    updated = _normalize_updated_at(
        blob.get("updated_at")
        or blob.get("updatedAt")
        or blob.get("updated")
        or blob.get("mtime")
        or blob.get("last_activity")
        or blob.get("last_active")
    )
    return {
        "id": sid,
        "title": title,
        "snippet": snippet,
        "updated_at": updated,
        "source": "provider",
    }


# grok sessions list: "{id} {created:10} {updated:10} {status} {summary}"
_GROK_ROW_RE = re.compile(
    r"^(?P<id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s+"
    r"(?P<created>\S+)\s+(?P<updated>\S+)\s+(?P<status>\S+)\s+(?P<summary>.*)$"
)
_GROK_SKIP_PREFIXES = ("session id", "label:", "(no label)", "no sessions found")


def parse_grok_sessions_table(stdout: str) -> list[dict[str, Any]]:
    """Parse ``grok sessions list`` grouped text table. No fake rows."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith(_GROK_SKIP_PREFIXES):
            continue
        match = _GROK_ROW_RE.match(line)
        if not match:
            continue
        sid = sanitize_cli_session_id(match.group("id"))
        if not sid or sid in seen:
            continue
        seen.add(sid)
        summary = (match.group("summary") or "").strip()
        if summary in {"(no summary)", "(untitled)"}:
            summary = ""
        rows.append(
            {
                "id": sid,
                "title": (summary or sid)[:200],
                "snippet": summary[:240],
                "updated_at": _normalize_updated_at(match.group("updated")),
                "source": "provider",
            }
        )
    return rows


def parse_provider_sessions(stdout: str, *, cli_name: str = "") -> list[dict[str, Any]]:
    """Parse a CLI list command's stdout into sanitized session rows."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blob in _iter_json_blobs(stdout):
        items: list[Any]
        if isinstance(blob, list):
            items = blob
        elif isinstance(blob, dict):
            nested = blob.get("sessions") or blob.get("data") or blob.get("items")
            if isinstance(nested, list):
                items = nested
            else:
                items = [blob]
        else:
            continue
        for item in items:
            row = _row_from_blob(item)
            if row is None or row["id"] in seen:
                continue
            seen.add(row["id"])
            rows.append(row)
    if rows:
        return rows
    # Grok's official list is a text table (no --json on `sessions list`).
    if not cli_name or cli_name == "grok":
        return parse_grok_sessions_table(stdout)
    return []


def _list_cwd(cli_name: str, config: dict[str, Any] | None) -> str | None:
    entry = (config or {}).get("cli_agents") or {}
    if isinstance(entry, dict):
        block = entry.get(cli_name)
        if isinstance(block, dict):
            raw = block.get("list_cwd") or block.get("workdir")
            if isinstance(raw, str) and raw.strip():
                return os.path.expanduser(raw.strip())
    return None


def _session_list_cwd(
    cli_name: str,
    config: dict[str, Any] | None,
    *,
    agent_id: str | None = None,
    folder: str | None = None,
) -> str | None:
    """REQ-167: agent Folder wins; otherwise the existing catalog list cwd."""
    from swarm.core.agent_folder import resolve_session_cwd

    folder_cwd = resolve_session_cwd(agent_id=agent_id, raw=folder)
    if folder_cwd:
        return folder_cwd
    return _list_cwd(cli_name, config)


def _parse_warning(stdout: str, rows: list[dict[str, Any]]) -> str | None:
    text = (stdout or "").strip()
    if rows or not text:
        return None
    if "no sessions found" in text.lower():
        return None
    return "Session list had no parseable ids"


def list_provider_sessions(
    cli_name: str,
    *,
    config: dict[str, Any] | None = None,
    run_list: RunList | None = None,
    timeout: float | None = None,
    folder: str | None = None,
    agent_id: str | None = None,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Run the CLI list command or enumerate the provider store.

    Returns ``(can_list, rows, warning)``. ``can_list`` is False when there is
    no argv and no store — callers must not invent provider rows.
    """
    argv = cli_catalog.list_sessions_argv(cli_name, config)
    if argv:
        resolved_exe = cli_catalog.which_cli(argv[0])
        if resolved_exe is None and run_list is None:
            return True, [], f"{cli_name}: CLI not installed (no {argv[0]!r} on PATH)"
        resolved = [resolved_exe or argv[0], *argv[1:]]
        list_cwd = _session_list_cwd(
            cli_name, config, agent_id=agent_id, folder=folder
        )
        runner = run_list or (
            lambda command, limit: _default_run_list(
                command, limit, cwd=list_cwd
            )
        )
        code, stdout, stderr = runner(list(resolved), float(timeout or LIST_TIMEOUT))
        if code is None:
            return True, [], "Session list timed out"
        if code != 0:
            if code == 127:
                return True, [], f"{cli_name}: CLI not installed (no {argv[0]!r} on PATH)"
            detail = (stderr or stdout or "list failed").strip().splitlines()
            warning = detail[0][:200] if detail else "list failed"
            return True, [], warning
        rows = parse_provider_sessions(stdout, cli_name=cli_name)
        return True, rows, _parse_warning(stdout, rows)

    store = cli_catalog.list_sessions_store(cli_name, config)
    if not store:
        return False, [], "This CLI can't list sessions"
    store_dir = cli_catalog.list_sessions_store_dir(cli_name, config)
    return True, list_store_sessions(store, store_dir), None


def merge_session_rows(
    provider: list[dict[str, Any]],
    swarm: list[dict[str, Any]],
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Provider activity wins; swarm-touch fills gaps. Newest first when stamped."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in swarm + provider:
        sid = row.get("id")
        if not sid:
            continue
        existing = by_id.get(sid)
        if existing is None or row.get("source") == "provider":
            merged = dict(row)
            if existing and not merged.get("updated_at"):
                merged["updated_at"] = existing.get("updated_at") or ""
            if existing and not merged.get("snippet"):
                merged["snippet"] = existing.get("snippet") or ""
            by_id[sid] = merged
    rows = list(by_id.values())

    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        stamp = str(row.get("updated_at") or "")
        return (0 if stamp else 1, stamp)

    rows.sort(key=sort_key, reverse=True)
    return rows[:limit]


def list_cli_sessions(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    config: dict[str, Any] | None = None,
    run_list: RunList | None = None,
    base_dir: Path | None = None,
    folder: str | None = None,
) -> dict[str, Any]:
    """Picker payload: provider list (if any) + recent swarm-touch rows."""
    from swarm.core.agent_folder import resolve_session_cwd

    # Validate Folder before listing so a bad path never silently uses another cwd.
    resolve_session_cwd(agent_id=agent_id, raw=folder)
    can_list, provider, warning = list_provider_sessions(
        cli_name,
        config=config,
        run_list=run_list,
        folder=folder,
        agent_id=agent_id,
    )
    recents = swarm_recent_sessions(user_key, agent_id, cli_name, base_dir=base_dir)
    sessions = merge_session_rows(provider, recents, limit=50)
    empty_reason = None
    if not sessions:
        if not can_list:
            empty_reason = "This CLI can't list sessions"
        else:
            empty_reason = "No sessions found"
    return {
        "object": "cli_session_list",
        "agent_id": chat_store.normalize_agent_id(agent_id),
        "cli": chat_store.normalize_agent_id(cli_name),
        "can_list": can_list,
        "list_capability": cli_catalog.list_capability(cli_name, config),
        "sessions": sessions,
        "recent": recents[:RECENT_LIMIT],
        "empty_reason": empty_reason,
        "warning": warning if can_list else None,
        "activity_sot": "provider" if can_list else "swarm",
    }


def _visible_turns(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    from swarm.core.transcript_roles import is_chrome_message

    out: list[dict[str, Any]] = []
    for row in messages or []:
        if not isinstance(row, dict):
            continue
        if is_chrome_message(row):
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        out.append(row)
    return out


def format_prior_history(messages: list[dict[str, Any]] | None) -> str:
    """Markdown archive for the expandable pill. Not sent as CLI turns."""
    from swarm.core.transcript_roles import is_chrome_message

    lines: list[str] = []
    for row in messages or []:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        if row.get("kind") == PRIOR_HISTORY_KIND:
            lines.append(f"**{PRIOR_HISTORY_LABEL}**\n{content}")
            continue
        if is_chrome_message(row):
            continue
        role = str(row.get("role") or "user").capitalize()
        lines.append(f"**{role}:** {content}")
    return "\n\n".join(lines).strip()


def _transcript_payload(
    turns: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Reconstructed display plus the split store (REQ-70 / #789)."""
    from swarm.core.transcript_roles import reconstruct_display

    return {
        "messages": reconstruct_display(turns, events),
        "turns": turns,
        "ui_events": events,
    }


def _same_bound_session(
    *,
    start_new: bool,
    session_id: str | None,
    stored: str | None,
    prior_visible: list[dict[str, Any]],
    imported: list[dict[str, Any]] | None,
) -> bool:
    if start_new:
        return not stored and not prior_visible
    if not session_id or session_id != stored:
        return False
    if imported:
        return False
    # Issue #139: empty / notice-only chat must re-read provider transcript
    # (explicit session_id + imported=None must not yield import=none).
    if not prior_visible:
        return False
    return True


def select_cli_session(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    session_id: str | None = None,
    start_new: bool = False,
    from_conversation_id: str = "",
    imported_messages: list[dict[str, Any]] | None = None,
    user: Any = None,
    base_dir: Path | None = None,
    title: str = "",
    snippet: str = "",
    folder: str | None = None,
) -> dict[str, Any]:
    """Design A: bind a new swarm conversation to a CLI session (or start fresh).

    Old thread is left on disk. Differing prior content becomes a prior-history
    pill on the new conversation. Old compressions are not copied.
    """
    from swarm.core.agent_folder import resolve_session_cwd

    agent = chat_store.normalize_agent_id(agent_id)
    # Fail before minting a conversation when Folder is set but unusable.
    resolve_session_cwd(agent_id=agent, raw=folder)
    cli = chat_store.normalize_agent_id(cli_name)
    sid = None if start_new else sanitize_cli_session_id(session_id)
    if not start_new and session_id and sid is None:
        raise ValueError("session_id is not a storeable CLI session id")

    prior = None
    if from_conversation_id:
        prior = chat_store.load(
            user_key, agent, conversation_id=from_conversation_id, base_dir=base_dir
        )
    if prior is None:
        prior = chat_store.load(user_key, agent, base_dir=base_dir)
    prior_messages = list((prior or {}).get("messages") or [])
    prior_events = list((prior or {}).get("ui_events") or [])
    prior_visible = _visible_turns(prior_messages)
    stored = get_cli_session(user_key, agent, cli, base_dir=base_dir)
    prior_cid = (prior or {}).get("conversation_id") or from_conversation_id or ""

    if _same_bound_session(
        start_new=start_new,
        session_id=sid,
        stored=stored,
        prior_visible=prior_visible,
        imported=imported_messages,
    ):
        return {
            "object": "cli_session_select",
            "agent_id": agent,
            "cli": cli,
            "conversation_id": prior_cid,
            "cli_session_id": stored,
            **_transcript_payload(prior_messages, prior_events),
            "status": (
                session_notice_text(cli, resumed=True)
                if stored
                else session_notice_text(cli, resumed=False)
            ),
            "collapsed_prior": False,
            "import": "none",
            "same_session": True,
        }

    from swarm.core.transcript_roles import append_event, append_turn, is_chrome_message

    provider_cwd: str | None = None
    provider_branch: str | None = None
    if not start_new and sid and imported_messages is None:
        try:
            from swarm.core.cli_session_stores import read_provider_transcript
            provider = read_provider_transcript(cli, sid)
        except Exception:
            logger.exception("Provider transcript import failed for %s/%s", cli, sid)
            provider = None
        if provider:
            imported = provider.get("turns") or []
            if imported:
                imported_messages = [
                    {"role": row.get("role"), "content": row.get("content")}
                    for row in imported
                    if isinstance(row, dict)
                ]
            provider_cwd = provider.get("cwd")
            provider_branch = provider.get("git_branch")

    new_cid = mint_cli_conversation_id(agent)
    turns: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    collapsed = False
    if prior_visible:
        archive = format_prior_history(prior_messages)
        if archive:
            append_event(
                turns,
                events,
                "system",
                archive,
                kind=PRIOR_HISTORY_KIND,
                from_conversation_id=prior_cid,
            )
            collapsed = True

    import_kind = "none"
    if imported_messages:
        imported_turns = False
        for row in imported_messages:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "assistant")
            content = str(row.get("content") or "")
            if not content.strip():
                continue
            if is_chrome_message(row) or role in ("status", "info"):
                append_event(turns, events, "status", content)
                continue
            if role not in ("user", "assistant"):
                continue
            append_turn(turns, events, role, content)
            imported_turns = True
        if imported_turns:
            import_kind = "full"

    notice = switch_notice_text(cli, sid, start_new=start_new)
    append_event(turns, events, "status", notice)

    chat_store.save(
        user_key,
        agent,
        turns,
        conversation_id=new_cid,
        session_id=new_cid,
        cli_sessions={cli: sid} if sid else {},
        ui_events=events,
        base_dir=base_dir,
    )
    # REQ-52 resume reads the default agent file + settings — bind the id
    # there too. The new conversation file already stores cli_sessions.
    put_cli_session(
        user_key,
        agent,
        cli,
        sid,
        base_dir=base_dir,
    )
    try:
        from swarm.core.agent_settings import set_cli_session_id

        set_cli_session_id(agent, sid)
    except Exception:
        logger.exception("Could not persist settings cli_session_id for %s", agent)

    if sid:
        remember_recent_session(
            user_key,
            agent,
            cli,
            sid,
            title=title or sid,
            snippet=snippet,
            base_dir=base_dir,
        )

    if user is not None:
        _bind_django_conversation(user, new_cid, turns)

    return {
        "object": "cli_session_select",
        "agent_id": agent,
        "cli": cli,
        "conversation_id": new_cid,
        "cli_session_id": sid,
        "folder": provider_cwd,
        "git_branch": provider_branch,
        **_transcript_payload(turns, events),
        "status": notice,
        "collapsed_prior": collapsed,
        "import": import_kind,
        "same_session": False,
        "from_conversation_id": prior_cid,
    }


def _bind_django_conversation(user, conversation_id: str, messages: list[dict[str, Any]]) -> None:
    """Create the new Django conversation. Never deletes the prior thread.

    ``messages`` is the model-turn list only. Status/info chrome stays in
    the file-store ``ui_events`` side channel.
    """
    try:
        from swarm.models import ChatConversation, ChatMessage
    except Exception:
        return
    if not getattr(user, "is_authenticated", False):
        student = user if getattr(user, "pk", None) is not None else None
    else:
        student = user
    try:
        chat, _created = ChatConversation.objects.get_or_create(
            conversation_id=conversation_id,
            defaults={"student": student},
        )
        if chat.student_id is None and student is not None:
            chat.student = student
            chat.save(update_fields=["student"])
        ChatMessage.objects.bulk_create(
            [
                ChatMessage(
                    conversation=chat,
                    sender=str(item.get("role") or "user"),
                    content=str(item.get("content") or ""),
                )
                for item in messages
            ]
        )
    except Exception:
        logger.exception("Could not bind Django conversation %s", conversation_id)
