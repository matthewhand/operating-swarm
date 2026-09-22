"""REQ-138 / #531 — cross-tool session hop (quota hop; no copy-paste).

Every CLI/API dropdown switch starts a **new** backend session and seeds it
with condensed prior context from the swarm thread. Switching back is also a
new session — never resume or patch the earlier native session.

Manual switch only. No automated quota failover. Secrets and tool noise are
omitted from the injected blob. Provider list/resume (#795 / #807) stays the
way to *attach* a native session; hop is the way to *leave* one.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from swarm.core import chat_store, cli_catalog
from swarm.core.cli_sessions import (
    clear_cli_session,
    sanitize_cli_session_id,
    session_notice_text,
)

logger = logging.getLogger(__name__)

HOP_KIND = "context_carried"
HOP_OBJECT = "cli_session_hop"
HOP_MODES = frozenset({"summary", "full"})
DEFAULT_HOP_MODE = "summary"
DEFAULT_TOKEN_BUDGET = 4000
FULL_TOKEN_BUDGET = 16_000
MAX_TOKEN_BUDGET = 128_000
MIN_TOKEN_BUDGET = 64
CONTEXT_KIND = "context_carried"

RunExport = Callable[[list[str], float], tuple[int | None, str, str]]

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+\b", re.IGNORECASE),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*\S+"
    ),
)
_TOOL_ROLES = frozenset({"tool", "function"})
_TOOL_KINDS = frozenset(
    {"tool", "tool_call", "tool_result", "function_call", "tool_output"}
)
_OMITTED = ("secrets", "tool_noise")


def normalize_hop_mode(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text in ("condensed", "compact"):
        return DEFAULT_HOP_MODE
    if text in HOP_MODES:
        return text
    return DEFAULT_HOP_MODE


def resolve_token_budget(mode: str, token_budget: Any = None) -> int:
    if token_budget is not None and str(token_budget).strip() != "":
        try:
            value = int(token_budget)
        except (TypeError, ValueError):
            value = DEFAULT_TOKEN_BUDGET if mode != "full" else FULL_TOKEN_BUDGET
    else:
        value = FULL_TOKEN_BUDGET if mode == "full" else DEFAULT_TOKEN_BUDGET
    return max(MIN_TOKEN_BUDGET, min(value, MAX_TOKEN_BUDGET))


def redact_injection_text(text: str) -> str:
    """Strip secret-shaped tokens from an injection blob. Never store raw secrets."""
    blob = text or ""
    for pattern in _SECRET_PATTERNS:
        blob = pattern.sub("[REDACTED]", blob)
    try:
        from swarm.utils.redact import redact_uri_credentials

        blob = redact_uri_credentials(blob)
    except Exception:
        pass
    return blob


def is_tool_noise(row: Any) -> bool:
    """True for tool/progress chrome that must not seed the next CLI."""
    if not isinstance(row, dict):
        return True
    role = str(row.get("role") or row.get("sender") or "").strip().lower()
    if role in _TOOL_ROLES:
        return True
    if row.get("tool_calls") or row.get("tool_call_id"):
        return True
    kind = str(row.get("kind") or row.get("source_kind") or "").strip().lower()
    if kind in _TOOL_KINDS:
        return True
    if role in ("status", "info"):
        return True
    if kind in {"prior_history", CONTEXT_KIND, "hop"}:
        return True
    return False


def turns_for_injection(messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """User/assistant/system turns only. Chrome, tools, and empty rows dropped."""
    from swarm.core.transcript_roles import is_chrome_message, is_ui_only_item

    out: list[dict[str, str]] = []
    for row in messages or []:
        if not isinstance(row, dict):
            continue
        if is_tool_noise(row) or is_chrome_message(row) or is_ui_only_item(row):
            continue
        role = str(row.get("role") or "user").strip().lower()
        if role not in ("user", "assistant", "system", "developer"):
            continue
        content = redact_injection_text(str(row.get("content") or "")).strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """tiktoken when available; word-count fallback. Never raises."""
    blob = text or ""
    if not blob:
        return 0
    try:
        from swarm.utils.context_utils import get_token_count

        return max(0, int(get_token_count(blob, model)))
    except Exception:
        return max(1, len(blob.split()) + 5)


def _header(from_cli: str, to_cli: str, mode: str) -> str:
    return (
        f"[Carried context from {from_cli} → {to_cli} — {mode}. "
        "Secrets and tool noise omitted.]"
    )


def _render_turns(turns: list[dict[str, str]]) -> str:
    if not turns:
        return ""
    if len(turns) == 1:
        return turns[0]["content"]
    lines = [f"{row['role'].upper()}: {row['content']}" for row in turns]
    return "\n\n".join(lines)


def build_injection_payload(
    messages: list[dict[str, Any]] | None,
    *,
    from_cli: str,
    to_cli: str,
    mode: str = DEFAULT_HOP_MODE,
    token_budget: Any = None,
) -> dict[str, Any]:
    """Condense a swarm transcript into a redacted injection blob."""
    hop_mode = normalize_hop_mode(mode)
    budget = resolve_token_budget(hop_mode, token_budget)
    source = str(from_cli or "").strip() or "prior"
    target = str(to_cli or "").strip() or "next"
    header = _header(source, target, hop_mode)
    turns = turns_for_injection(messages)
    kept: list[dict[str, str]] = []
    # Newest turns first so a budget cut keeps the end of the task.
    for row in reversed(turns):
        candidate = [row, *kept]
        text = f"{header}\n\n{_render_turns(candidate)}"
        if kept and estimate_tokens(text) > budget:
            continue
        kept = candidate
    body = _render_turns(kept)
    text = f"{header}\n\n{body}".strip() if body else header
    text = redact_injection_text(text)
    tokens = estimate_tokens(text)
    return {
        "text": text,
        "mode": hop_mode,
        "tokens": tokens,
        "token_budget": budget,
        "turn_count": len(kept),
        "omitted": list(_OMITTED),
        "from_cli": source,
        "to_cli": target,
        "empty": not bool(body),
    }


def hop_notice_text(
    from_cli: str,
    to_cli: str,
    *,
    mode: str,
    tokens: int,
    empty: bool = False,
    export_warning: str | None = None,
) -> str:
    """Single CLI-toggle status line (REQ-866). Includes ``(from → to)``."""
    head = (
        f"{session_notice_text(to_cli, resumed=False).rstrip('.')} "
        f"({from_cli} → {to_cli})."
    )
    if empty and export_warning:
        return f"{head} {export_warning} Nothing to carry."
    if empty:
        return f"{head} No prior context to carry from {from_cli}."
    line = f"{head} Carried {mode} context ({tokens} tokens)."
    if export_warning:
        return f"{line} {export_warning}"
    return line


def is_context_carried_notice(text: str | None) -> bool:
    blob = (text or "").strip()
    if " → " not in blob or "Carried " not in blob:
        return False
    return " context (" in blob or " context from " in blob


def hop_capability_row(name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """One CLI's list / resume / export / hop row (ids + capability only)."""
    policy = cli_catalog.session_policy(name) or {}
    export = cli_catalog.export_capability(name, config)
    return {
        "cli": chat_store.normalize_agent_id(name),
        "list": cli_catalog.list_capability(name, config),
        "resume": bool(policy.get("resume_argv")),
        "export": export,
        "hop": "new_session_plus_inject",
        "export_argv": cli_catalog.export_sessions_argv(name, config),
        "notes": (
            "Native transcript export, then seed the new CLI."
            if export == cli_catalog.EXPORT_CAPABILITY_TRANSCRIPT
            else "Summary inject from the swarm thread. No verified native export."
        ),
    }


def hop_capability_matrix(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Per-CLI hop table for docs / GET /v1/cli-sessions/hop/."""
    return {name: hop_capability_row(name, config) for name in cli_catalog.catalog_names()}


def normalize_cli_hop(raw: Any) -> dict[str, Any] | None:
    """Storeable pending-hop record, or None. Never keeps secret-shaped text."""
    if not isinstance(raw, dict):
        return None
    text = redact_injection_text(str(raw.get("text") or raw.get("payload") or ""))
    from_cli = chat_store.normalize_agent_id(str(raw.get("from_cli") or ""))
    to_cli = chat_store.normalize_agent_id(str(raw.get("to_cli") or ""))
    mode = normalize_hop_mode(raw.get("mode"))
    if not to_cli:
        return None
    pending = bool(raw.get("pending", True)) and bool(text)
    try:
        tokens = int(raw.get("tokens") or 0)
    except (TypeError, ValueError):
        tokens = estimate_tokens(text)
    return {
        "from_cli": from_cli,
        "to_cli": to_cli,
        "mode": mode,
        "text": text,
        "tokens": max(0, tokens),
        "pending": pending,
        "announced": bool(raw.get("announced")),
        "kind": str(raw.get("kind") or "cli"),
        "omitted": list(raw.get("omitted") or _OMITTED),
    }


def parse_exported_messages(stdout: str) -> list[dict[str, Any]]:
    """Best-effort transcript from fixture/CLI export stdout. No secrets kept."""
    text = (stdout or "").strip()
    if not text:
        return []
    blobs: list[Any] = []
    try:
        blobs.append(json.loads(text))
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                blobs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows: list[dict[str, Any]] = []
    for blob in blobs:
        items: list[Any]
        if isinstance(blob, list):
            items = blob
        elif isinstance(blob, dict):
            inner = blob.get("messages") or blob.get("turns") or blob.get("transcript")
            if isinstance(inner, list):
                items = inner
            elif blob.get("role") and blob.get("content") is not None:
                items = [blob]
            else:
                items = []
        else:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = redact_injection_text(str(item.get("content") or "")).strip()
            if not content or role not in ("user", "assistant", "system", "developer"):
                continue
            rows.append({"role": role, "content": content})
    return rows


def export_provider_transcript(
    cli_name: str,
    session_id: str,
    *,
    config: dict[str, Any] | None = None,
    run_export: RunExport | None = None,
    timeout: float = cli_catalog.LIST_SESSIONS_TIMEOUT,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Native transcript when export_argv exists; else (None, honest warning)."""
    sid = sanitize_cli_session_id(session_id)
    if not sid:
        return None, "session_id is not a storeable CLI session id"
    argv = cli_catalog.export_sessions_argv(cli_name, config)
    if not argv:
        return None, (
            f"{cli_name} cannot export a native transcript; used the swarm thread."
        )
    command = [part.replace("{session_id}", sid) for part in argv]
    runner = run_export or _default_run_export
    code, stdout, stderr = runner(command, float(timeout))
    if code is None:
        return None, f"{cli_name} transcript export timed out; used the swarm thread."
    if code != 0:
        detail = (stderr or stdout or "export failed").strip().splitlines()
        hint = detail[0][:160] if detail else "export failed"
        return None, f"{cli_name} cannot export that session ({hint}); used the swarm thread."
    rows = parse_exported_messages(stdout)
    if not rows:
        return None, (
            f"{cli_name} export returned no turns; used the swarm thread."
        )
    return rows, None


def _default_run_export(command: list[str], timeout: float) -> tuple[int | None, str, str]:
    import subprocess

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"{command[0]}: not found"
    except subprocess.TimeoutExpired:
        return None, "", "timed out"
    except OSError as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def apply_injection_to_prompt(payload_text: str, user_prompt: str) -> str:
    """Prefix the first new-session turn with the carried blob."""
    seed = (payload_text or "").strip()
    latest = (user_prompt or "").strip()
    if not seed:
        return latest
    if not latest:
        return seed
    if latest in seed and seed.endswith(latest):
        return seed
    return f"{seed}\n\nUSER: {latest}"


def _load_thread(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str = "",
    base_dir=None,
) -> dict[str, Any]:
    record = None
    if conversation_id:
        record = chat_store.load(
            user_key, agent_id, conversation_id=conversation_id, base_dir=base_dir
        )
    if record is None:
        record = chat_store.load(user_key, agent_id, base_dir=base_dir)
    return record or chat_store.empty_record(
        user_key=user_key,
        agent_id=agent_id,
        conversation_id=conversation_id,
    )


def hop_backend(
    user_key: str,
    agent_id: str,
    *,
    from_cli: str,
    to_cli: str,
    conversation_id: str = "",
    mode: str = DEFAULT_HOP_MODE,
    token_budget: Any = None,
    import_session_id: str | None = None,
    imported_messages: list[dict[str, Any]] | None = None,
    kind: str = "cli",
    to_kind: str | None = None,
    to_label: str | None = None,
    from_label: str | None = None,
    from_agent: str | None = None,
    config: dict[str, Any] | None = None,
    run_export: RunExport | None = None,
    announced: bool = True,
    base_dir=None,
    user: Any = None,
) -> dict[str, Any]:
    """Switch backends on the same swarm conversation: new session + seed.

    Never mints a new Django conversation (that is Select session / design A).
    Never resumes ``to_cli``'s prior native id — including a hop back.
    When ``user`` is provided the final thread is mirrored into Django
    ChatMessage rows (#901) so switch-away context handoff reads the local
    DB snapshot instantly — no export_argv subprocess, no remote calls.
    #900: ``to_kind`` generalizes the destination beyond CLIs — ``api`` and
    ``remote`` destinations consume the pending seed through
    :func:`apply_cross_kind_hop_messages` at their turn-assembly sites.
    ``from_agent`` reads the source thread from another seat's record
    (cross-kind hops store the pending seed under the *destination* seat,
    but the context lives with the *source*). ``to_label`` is the human
    backend name used in the status banner while ``to_cli`` stays the
    destination record id the consumer matches against.
    """
    agent = chat_store.normalize_agent_id(agent_id)
    source = chat_store.normalize_agent_id(from_cli)
    target = chat_store.normalize_agent_id(to_cli)
    kind_raw = str(to_kind if to_kind is not None else kind or "").strip().lower()
    hop_kind = kind_raw if kind_raw in ("cli", "api", "remote") else "cli"
    if not source or not target:
        raise ValueError("from_cli and to_cli are required")
    if source == target and not import_session_id and not imported_messages:
        raise ValueError("from_cli and to_cli must differ")

    record = _load_thread(
        user_key, agent, conversation_id=conversation_id, base_dir=base_dir
    )
    cid = conversation_id or str(record.get("conversation_id") or "")
    # #900: cross-kind hops read the source thread from the seat that owns
    # the context (the destination seat's own record is usually empty).
    if from_agent:
        source_agent = chat_store.normalize_agent_id(from_agent)
        if source_agent and source_agent != agent:
            record = _load_thread(
                user_key, source_agent, conversation_id=conversation_id, base_dir=base_dir
            )
    export_warning = None
    import_source = "swarm"
    imported: list[dict[str, Any]] | None = None
    if imported_messages:
        imported = parse_exported_messages(json.dumps(imported_messages))
        if not imported:
            imported = [row for row in imported_messages if isinstance(row, dict)]
        if imported:
            import_source = "transcript"
    elif import_session_id:
        imported, export_warning = export_provider_transcript(
            source,
            import_session_id,
            config=config,
            run_export=run_export,
        )
        if imported:
            import_source = "transcript"
    elif not (record.get("messages") or []) and user is not None:
        # #901: no native export requested and the JSON thread is empty —
        # fall back to the Django mirror (kept fresh by turn completion and
        # switch-away flushes). Instant, local, zero subprocess/remote calls.
        try:
            from swarm.core.thread_load import messages_from_db

            db_rows = messages_from_db(user, cid)
            if db_rows:
                imported = turns_for_injection(db_rows)
                import_source = "db_mirror"
        except Exception:
            logger.debug("hop DB-mirror fallback failed for %s", cid, exc_info=True)

    source_messages = imported if imported else list(record.get("messages") or [])
    payload = build_injection_payload(
        source_messages,
        from_cli=source,
        to_cli=target,
        mode=mode,
        token_budget=token_budget,
    )
    notice = hop_notice_text(
        str(from_label).strip() or source,
        str(to_label).strip() or target,
        mode=payload["mode"],
        tokens=int(payload["tokens"]),
        empty=bool(payload["empty"]),
        export_warning=export_warning,
    )

    sessions = chat_store.normalize_cli_sessions(record.get("cli_sessions"))
    sessions.pop(target, None)
    hop = None if payload["empty"] else {
        "from_cli": source,
        "to_cli": target,
        "mode": payload["mode"],
        "text": payload["text"],
        "tokens": payload["tokens"],
        "pending": True,
        "announced": bool(announced),
        "kind": hop_kind,
        "omitted": payload["omitted"],
    }

    from swarm.core.transcript_roles import append_event

    turns = list(record.get("messages") or [])
    events = list(record.get("ui_events") or [])
    append_event(turns, events, "status", notice, kind=CONTEXT_KIND)

    chat_store.save(
        user_key,
        agent,
        turns,
        conversation_id=cid,
        session_id=str(record.get("session_id") or ""),
        cli_sessions=sessions,
        ui_events=events,
        cli_hop=hop,
        active_cli=target,
        base_dir=base_dir,
    )
    if user is not None:
        try:
            from swarm.core.agent_sessions import mirror_thread_to_db

            mirror_thread_to_db(user, cid, turns, agent_id=agent)
        except Exception:
            logger.debug("hop DB mirror failed for %s", cid, exc_info=True)
    clear_cli_session(
        user_key,
        agent,
        target,
        conversation_id=cid,
        base_dir=base_dir,
    )
    try:
        from swarm.core.agent_settings import set_cli_session_id, stored_cli_session_id

        # Settings store is one id per agent — drop it so a hop-back cannot resume.
        if stored_cli_session_id(agent):
            set_cli_session_id(agent, None)
    except Exception:
        logger.debug("Could not clear settings cli_session_id after hop", exc_info=True)

    return {
        "object": HOP_OBJECT,
        "agent_id": agent,
        "conversation_id": cid,
        "from_cli": source,
        "to_cli": target,
        "kind": hop_kind,
        "cli_session_id": None,
        "mode": payload["mode"],
        "tokens": payload["tokens"],
        "token_budget": payload["token_budget"],
        "omitted": payload["omitted"],
        "empty": payload["empty"],
        "status": notice,
        "export_warning": export_warning,
        "import": import_source if imported else "swarm",
        "capability": hop_capability_row(source, config),
        "target_capability": hop_capability_row(target, config),
        "injection": {
            "text": payload["text"],
            "mode": payload["mode"],
            "tokens": payload["tokens"],
            "empty": payload["empty"],
        },
    }


def pending_hop(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    conversation_id: str = "",
    base_dir=None,
) -> dict[str, Any] | None:
    """Pending hop for ``cli_name``, or None."""
    record = _load_thread(
        user_key, agent_id, conversation_id=conversation_id, base_dir=base_dir
    )
    hop = normalize_cli_hop(record.get("cli_hop"))
    if not hop or not hop.get("pending"):
        return None
    target = chat_store.normalize_agent_id(cli_name)
    if hop.get("to_cli") != target:
        return None
    return hop


def consume_pending_hop(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    conversation_id: str = "",
    base_dir=None,
) -> dict[str, Any] | None:
    """Return and clear a matching pending hop."""
    hop = pending_hop(
        user_key,
        agent_id,
        cli_name,
        conversation_id=conversation_id,
        base_dir=base_dir,
    )
    if hop is None:
        return None
    record = _load_thread(
        user_key, agent_id, conversation_id=conversation_id, base_dir=base_dir
    )
    chat_store.save(
        user_key,
        agent_id,
        None,
        conversation_id=conversation_id or str(record.get("conversation_id") or ""),
        session_id=str(record.get("session_id") or ""),
        cli_hop=None,
        active_cli=chat_store.normalize_agent_id(cli_name),
        base_dir=base_dir,
    )
    return hop


def maybe_implicit_hop(
    user_key: str,
    agent_id: str,
    cli_name: str,
    messages: list[dict[str, Any]] | None,
    *,
    conversation_id: str = "",
    mode: str = DEFAULT_HOP_MODE,
    token_budget: Any = None,
    kind: str = "cli",
    config: dict[str, Any] | None = None,
    base_dir=None,
) -> dict[str, Any] | None:
    """If ``active_cli`` differs from this turn's CLI, hop then return the record."""
    record = _load_thread(
        user_key, agent_id, conversation_id=conversation_id, base_dir=base_dir
    )
    previous = chat_store.normalize_agent_id(str(record.get("active_cli") or ""))
    target = chat_store.normalize_agent_id(cli_name)
    if not previous or not target or previous == target:
        return None
    if pending_hop(
        user_key, agent_id, target, conversation_id=conversation_id, base_dir=base_dir
    ):
        return None
    return hop_backend(
        user_key,
        agent_id,
        from_cli=previous,
        to_cli=target,
        conversation_id=conversation_id or str(record.get("conversation_id") or ""),
        mode=mode,
        token_budget=token_budget,
        kind=kind,
        config=config,
        announced=False,
        base_dir=base_dir,
    )


def prepare_cli_turn(
    user_key: str,
    agent_id: str,
    cli_name: str,
    messages: list[dict[str, Any]] | None,
    full_prompt: str,
    latest_user: str,
    *,
    conversation_id: str = "",
    stored_session_id: str | None,
    can_resume: bool,
    mode: str = DEFAULT_HOP_MODE,
    token_budget: Any = None,
    config: dict[str, Any] | None = None,
    base_dir=None,
) -> dict[str, Any]:
    """Force a new session and seed the prompt when a hop is pending or implied."""
    maybe_implicit_hop(
        user_key,
        agent_id,
        cli_name,
        messages,
        conversation_id=conversation_id,
        mode=mode,
        token_budget=token_budget,
        config=config,
        base_dir=base_dir,
    )
    hop = consume_pending_hop(
        user_key,
        agent_id,
        cli_name,
        conversation_id=conversation_id,
        base_dir=base_dir,
    )
    if hop is None:
        return {
            "resume_id": stored_session_id if can_resume else None,
            "prompt": full_prompt if not can_resume else (latest_user or full_prompt),
            "hop": None,
            "notice": None,
        }
    seed = str(hop.get("text") or "")
    prompt = apply_injection_to_prompt(seed, latest_user or full_prompt)
    notice = None
    if not hop.get("announced"):
        notice = hop_notice_text(
            str(hop.get("from_cli") or ""),
            cli_name,
            mode=str(hop.get("mode") or DEFAULT_HOP_MODE),
            tokens=int(hop.get("tokens") or 0),
            empty=not bool(seed),
        )
    return {
        "resume_id": None,
        "prompt": prompt,
        "hop": hop,
        "notice": notice,
        "injection": seed,
    }


def apply_api_hop_messages(
    user_key: str,
    agent_id: str,
    messages: list[dict[str, Any]] | None,
    *,
    conversation_id: str = "",
    to_cli: str = "api",
    base_dir=None,
) -> list[dict[str, Any]]:
    """Prepend a system seed after an API backend hop. Same conversation."""
    hop = consume_pending_hop(
        user_key,
        agent_id,
        to_cli,
        conversation_id=conversation_id,
        base_dir=base_dir,
    )
    if hop is None:
        return list(messages or [])
    seed = str(hop.get("text") or "").strip()
    if not seed:
        return list(messages or [])
    out = list(messages or [])
    out.insert(0, {"role": "system", "content": seed})
    return out


def hop_defaults() -> dict[str, Any]:
    return {
        "object": "cli_session_hop_capabilities",
        "modes": sorted(HOP_MODES),
        "kinds": ["cli", "api", "remote"],
        "default_mode": DEFAULT_HOP_MODE,
        "default_token_budget": DEFAULT_TOKEN_BUDGET,
        "full_token_budget": FULL_TOKEN_BUDGET,
        "omitted": list(_OMITTED),
        "automated_failover": False,
        "same_conversation": True,
        "always_new_session": True,
        "clis": hop_capability_matrix(),
    }


def apply_cross_kind_hop_messages(
    user_key: str,
    agent_id: str,
    messages: list[dict[str, Any]] | None,
    *,
    to_kind: str,
    to_id: str = "",
    conversation_id: str = "",
    base_dir=None,
) -> list[dict[str, Any]]:
    """Consume a pending hop for a cross-kind destination (#900).

    API and remote turn-assembly sites call this instead of the CLI-specific
    prompt injection: the carried seed rides in as a ``system`` turn ahead of
    the model payload. ``to_id`` defaults to ``agent_id`` (remote harness
    seats store the hop under the seat id, not the framework name).
    """
    kind = str(to_kind or "").strip().lower()
    if kind not in ("api", "remote"):
        return list(messages or [])
    agent = chat_store.normalize_agent_id(agent_id)
    consume_id = chat_store.normalize_agent_id(to_id or agent)
    hop = consume_pending_hop(
        user_key,
        agent,
        consume_id,
        conversation_id=conversation_id,
        base_dir=base_dir,
    )
    if hop is None:
        return list(messages or [])
    seed = str(hop.get("text") or "").strip()
    if not seed:
        return list(messages or [])
    out = list(messages or [])
    if kind == "remote":
        # Server-managed remotes receive only the latest user turn — merge the
        # seed into it (remote analogue of ``apply_injection_to_prompt``).
        for i in range(len(out) - 1, -1, -1):
            row = out[i]
            if isinstance(row, dict) and row.get("role") == "user":
                out[i] = {**row, "content": f"{seed}\n\n{row.get('content', '')}"}
                return out
    out.insert(0, {"role": "system", "content": seed})
    return out
