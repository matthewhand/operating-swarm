"""Routine Tools catalog, Open Pull Request hook (#1403), and extra tools (#1406).

``open_pull_request`` is a first-class routine tool. GitHub-issue triggers
default it on; every other trigger defaults it off. An explicit ``tools``
list (including empty) is the operator's choice and persists.

#1406 lets operators attach additional plugin / MCP catalog ids to the same
``tools`` list. Those ids come from the existing OS plugin/MCP catalog
(``plugin_catalog_ids``, ``tool_capabilities.CATALOG``, installed
``mcpServers``) — this module does not invent a second registry.

The run-path hook wraps ``gh pr create`` / ``gh pr edit`` — the same CLI
path self-update already documents. It never auto-merges, never creates a
PR without an explicit head branch (issue events have none; the server
checkout is not a head), and never copies token values into Issue/PR
bodies, logs, or return payloads. A PR URL in the agent reply counts only
when it belongs to the event's ``owner/repo``. Connector auth stays out
of Issues; builder defaults never include tokens.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from swarm.core.agent_memory import (
    DEFAULT_MEMORIES_FILENAME,
    MAX_MEMORIES_CONTENT,
    MEMORIES_DOC_OPS,
    normalize_memories_filename,
    normalize_memories_scope,
    run_memories_document_op,
)
from swarm.core.memory_scrubber import reject_credentials
from swarm.core.pr_opened import is_github_pr_url, parse_pr_opened
from swarm.core.schedule_triggers import reject_secrets
from swarm.core.self_update import extract_github_pr_url

logger = logging.getLogger(__name__)

TOOL_OPEN_PULL_REQUEST = "open_pull_request"
TOOL_MEMORIES = "memories"
KNOWN_ROUTINE_TOOLS = frozenset({TOOL_OPEN_PULL_REQUEST})
BUILTIN_ROUTINE_TOOLS = frozenset({TOOL_OPEN_PULL_REQUEST, TOOL_MEMORIES})
# Runtime name the agent sees. Same id as the picker row so the chat
# allowlist, which compares tool names exactly, keeps working.
MEMORIES_TOOL_NAME = TOOL_MEMORIES
# The Manage affordance: which builder fields own the document.
MEMORIES_MANAGE_OBJECT = "routine_memories"
MEMORIES_MANAGE_FIELDS: tuple[str, ...] = ("filename", "content")
MEMORIES_BRIEF_MARKER = "Memories tool enabled."
# MCP tool names are matched exactly by the chat allowlist. Hyphens and
# mixed case are part of the id; do not rewrite them.
_TOOL_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_TOKENISH_RE = re.compile(
    r"(ghp_|github_pat_|sk-|xai-|Bearer\s+[A-Za-z0-9._\-]{12,})",
    re.IGNORECASE,
)

# Presentation labels for the shipped plugin fixture (same ids as
# chat_plugin_tools.PLUGIN_CATALOG_IDS / frontend FIXTURE_PLUGIN_TOOLS).
_FIXTURE_TOOL_META: dict[str, dict[str, str]] = {
    "web_search": {
        "label": "Web Search",
        "description": "Search the public web without an API key.",
        "server_id": "duckduckgo",
        "server_name": "DuckDuckGo",
    },
    "web_fetch": {
        "label": "Web Fetch",
        "description": "Fetch and read a URL.",
        "server_id": "fetch",
        "server_name": "Fetch",
    },
    "browser_navigate": {
        "label": "Browser Navigate",
        "description": "Open a page in a local browser.",
        "server_id": "playwright",
        "server_name": "Playwright",
    },
    "browser_snapshot": {
        "label": "Browser Snapshot",
        "description": "Read the current page accessibility tree.",
        "server_id": "playwright",
        "server_name": "Playwright",
    },
    "browser_click": {
        "label": "Browser Click",
        "description": "Click an element on the current page.",
        "server_id": "playwright",
        "server_name": "Playwright",
    },
    "browser_type": {
        "label": "Browser Type",
        "description": "Type text into a focused field.",
        "server_id": "playwright",
        "server_name": "Playwright",
    },
    "read_file": {
        "label": "Read File",
        "description": "Read a file under the allowed path.",
        "server_id": "filesystem",
        "server_name": "Filesystem",
    },
    "write_file": {
        "label": "Write File",
        "description": "Write a file under the allowed path.",
        "server_id": "filesystem",
        "server_name": "Filesystem",
    },
    "list_directory": {
        "label": "List Directory",
        "description": "List files in a scoped folder.",
        "server_id": "filesystem",
        "server_name": "Filesystem",
    },
    "git_status": {
        "label": "Git Status",
        "description": "Show the working tree status.",
        "server_id": "git",
        "server_name": "Git",
    },
    "git_diff": {
        "label": "Git Diff",
        "description": "Show unstaged and staged diffs.",
        "server_id": "git",
        "server_name": "Git",
    },
    "git_log": {
        "label": "Git Log",
        "description": "List recent commits.",
        "server_id": "git",
        "server_name": "Git",
    },
    "get_current_time": {
        "label": "Current Time",
        "description": "Return the current time and timezone.",
        "server_id": "time",
        "server_name": "Time",
    },
    "convert_timezone": {
        "label": "Convert Timezone",
        "description": "Convert a timestamp between timezones.",
        "server_id": "time",
        "server_name": "Time",
    },
}

ROUTINE_TOOL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": TOOL_OPEN_PULL_REQUEST,
        "label": "Open Pull Request",
        "description": (
            "Open or update a GitHub pull request from this routine's agent run. "
            "Never auto-merges."
        ),
        "wired": True,
    },
    {
        "id": TOOL_MEMORIES,
        "label": "Memories",
        "description": (
            "Durable context in a memories file (MEMORIES.md by default). "
            "Manage sets the filename and the content the run loads."
        ),
        "wired": True,
        "manage": True,
        "manage_fields": list(MEMORIES_MANAGE_FIELDS),
        "default_filename": DEFAULT_MEMORIES_FILENAME,
    },
)

OPEN_PR_BRIEF = (
    "Open Pull Request tool is enabled. After the change is on a branch, "
    "open or update a GitHub pull request (gh pr create / gh pr edit). "
    "Do not merge. Do not put tokens or secrets in the PR title or body. "
    "If this run is for a GitHub issue, include Fixes #<number> in the body."
)

MEMORIES_BRIEF = (
    "{marker} Durable context lives in {filename}. Read it with the memories "
    "tool before acting on anything you were told to remember, and call the "
    "memories tool with operation='update' to leave what the next run needs. "
    "Never store tokens, secrets, or personal data in it."
)

# Explicit schema for the swarm.types.Tool fallback. The openai-agents
# function_tool derives the same shape from the callable signature.
MEMORIES_TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": list(MEMORIES_DOC_OPS),
            "description": (
                "create (fails if the document exists), read, update "
                "(fails if it is missing), or delete."
            ),
        },
        "content": {
            "type": "string",
            "description": "Markdown body. Used by create and update; ignored otherwise.",
        },
    },
    "required": ["operation"],
    "additionalProperties": False,
}

_ISSUE_EVENT_RE = re.compile(r"^issues(\.|$)")
# Token-shaped only. ``sk-`` / ``xai-`` also sit inside ordinary words
# (``task-management``, ``ask-operator``). Require a non-alphanumeric
# boundary. Short segments, underscores, and doubled hyphens may precede
# the tail (``sk-proj-``, ``sk-ant-api03-``, ``sk-proj-5-``, ``sk-proj--``)
# so a base64url key is still reached. The tail itself is a 20+ character
# alphanumeric run. Counting hyphens toward that length also matches
# kebab-case names such as ``xai-grok-4-fast-reasoning``.
_HOOK_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"ghp_[A-Za-z0-9]{16,}|"
    r"github_pat_[A-Za-z0-9_]{16,}|"
    r"sk-(?:[A-Za-z0-9_]{0,19}-){0,12}[A-Za-z0-9_]{20,}|"
    r"xai-(?:[A-Za-z0-9_]{0,19}-){0,12}[A-Za-z0-9_]{20,}|"
    r"Bearer\s+[A-Za-z0-9._-]{12,}"
    r")",
    re.IGNORECASE,
)

OpenPrRunner = Callable[..., dict[str, Any]]
_open_pr_runner: OpenPrRunner | None = None
PluginRuntimeApplier = Callable[..., Any]
_plugin_runtime_applier: PluginRuntimeApplier | None = None
MemoriesRuntimeApplier = Callable[..., Any]
_memories_runtime_applier: MemoriesRuntimeApplier | None = None


def set_open_pr_runner(runner: OpenPrRunner | None) -> None:
    """Install a test seam for the Open PR hook. ``None`` restores the default."""
    global _open_pr_runner
    _open_pr_runner = runner


def reset_open_pr_runner() -> None:
    """Drop the injected Open PR runner (test isolation)."""
    set_open_pr_runner(None)


def set_plugin_runtime_applier(applier: PluginRuntimeApplier | None) -> None:
    """Install a test seam for routine MCP attach. ``None`` restores the default."""
    global _plugin_runtime_applier
    _plugin_runtime_applier = applier


def reset_plugin_runtime_applier() -> None:
    """Drop the injected plugin runtime applier (test isolation)."""
    set_plugin_runtime_applier(None)


def set_memories_runtime_applier(applier: MemoriesRuntimeApplier | None) -> None:
    """Install a test seam for the Memories attach. ``None`` restores the default."""
    global _memories_runtime_applier
    _memories_runtime_applier = applier


def reset_memories_runtime_applier() -> None:
    """Drop the injected Memories runtime applier (test isolation)."""
    set_memories_runtime_applier(None)


def is_github_issue_trigger(trigger: dict[str, Any] | None) -> bool:
    """True when the trigger is a GitHub issue event (e.g. issues.opened)."""
    incoming = trigger if isinstance(trigger, dict) else {}
    if str(incoming.get("kind") or "").strip() != "github_event":
        return False
    event_type = str(incoming.get("event_type") or incoming.get("event") or "").strip()
    return bool(_ISSUE_EVENT_RE.match(event_type))


def default_tools_for_trigger(trigger: dict[str, Any] | None) -> list[str]:
    """Default-on Open PR for issue triggers; default-off otherwise."""
    if is_github_issue_trigger(trigger):
        return [TOOL_OPEN_PULL_REQUEST]
    return []


def tools_explicit_from(incoming: dict[str, Any] | None) -> bool:
    """Whether *incoming* records an operator/API tools choice.

    ``tools_explicit`` wins when present. A stored ``tools`` list without the
    flag counts as explicit so an operator-set list is not rewritten. Missing
    both keys (legacy rows) is unset — defaults follow the current trigger.
    """
    data = incoming if isinstance(incoming, dict) else {}
    if "tools_explicit" in data:
        return bool(data.get("tools_explicit"))
    return "tools" in data


def _slug_tool_id(raw: str) -> str:
    """Lowercase catalog-style id. Hyphens become underscores.

    Used only to recognize built-in hooks and to label an uninstalled
    connector row. Live MCP tool names must not pass through this.
    """
    return str(raw or "").strip().lower().replace("-", "_")


def _runtime_tool_id(raw: str) -> str:
    """Tool name as the MCP runtime registers it. Empty when not persistable."""
    name = str(raw or "").strip()
    if not name or not _TOOL_ID_RE.match(name):
        return ""
    return name


def _persist_tool_id(raw: str) -> str:
    """Id written on the routine.

    Built-ins fold to their canonical slug so ``Open-Pull-Request`` still
    enables the hook. Every other id is kept verbatim: the chat allowlist
    compares tool names exactly, and rewriting ``web-search`` to
    ``web_search`` drops the tool at run time.
    """
    stripped = str(raw or "").strip()
    folded = _slug_tool_id(stripped)
    if folded in BUILTIN_ROUTINE_TOOLS:
        return folded
    return _runtime_tool_id(stripped)


def normalize_routine_tools(raw: Any) -> list[str]:
    """Normalize a tools payload. Deduplicate. Reject secrets.

    Built-in ids (``open_pull_request``, ``memories``) fold to their
    canonical slug. Plugin/MCP ids persist as the catalog registered them
    (hyphens and case included). Other well-formed ids pass through so
    sibling tools and live MCP names can share the list. Missing-tool
    detect lives in ``routine_tool_suggestions`` (#1410), which is the
    single source of truth for that rule set (#1669) — this normalizer
    stores ids, it does not flag gaps.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        raise ValueError("tools must be a list of tool ids.")
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        tool_id = reject_secrets(str(item or "").strip(), "tools")
        if not tool_id:
            continue
        persisted = _persist_tool_id(tool_id)
        if not persisted:
            raise ValueError(
                f"Invalid routine tool id '{tool_id}'. "
                "Use a catalog id such as web_search or web-search "
                "(letters, numbers, underscore, hyphen)."
            )
        if persisted in seen:
            continue
        seen.add(persisted)
        out.append(persisted)
    return out


def public_routine_tools(
    incoming: dict[str, Any] | None,
    trigger: dict[str, Any] | None,
) -> tuple[list[str], bool]:
    """Return ``(effective tools, tools_explicit)`` for a stored or inbound row."""
    data = incoming if isinstance(incoming, dict) else {}
    explicit = tools_explicit_from(data)
    if explicit:
        return normalize_routine_tools(data.get("tools")), True
    return list(default_tools_for_trigger(trigger)), False


def routine_has_open_pr(tools: list[str] | None) -> bool:
    return TOOL_OPEN_PULL_REQUEST in (tools or [])


def append_open_pr_brief(instruction: str, tools: list[str] | None) -> str:
    """Append the Open PR capability brief when the tool is enabled."""
    text = str(instruction or "").strip()
    if not routine_has_open_pr(tools):
        return text
    if OPEN_PR_BRIEF in text:
        return text
    if text:
        return f"{text}\n\n---\n{OPEN_PR_BRIEF}"
    return OPEN_PR_BRIEF


def routine_tool_catalog() -> list[dict[str, Any]]:
    """Public catalog (deep-copied) for the Tools UI."""
    return json.loads(json.dumps(ROUTINE_TOOL_CATALOG))


def plugin_ids_from_routine_tools(tools: list[str] | None) -> list[str]:
    """Catalog / MCP ids on a routine — built-in hooks excluded."""
    return [tid for tid in (tools or []) if tid not in BUILTIN_ROUTINE_TOOLS]


def apply_routine_plugin_runtime(blueprint: Any, tools: list[str] | None) -> list[str]:
    """Attach selected plugin/MCP tools for a live routine run.

    Reuses ``apply_plugin_mcp_runtime`` (the chat path). No-op when the
    operator did not add catalog tools. Never logs token values.
    """
    plugin_ids = plugin_ids_from_routine_tools(tools)
    if not plugin_ids:
        return []
    applier = _plugin_runtime_applier
    if applier is not None:
        applier(blueprint, plugin_ids)
        return plugin_ids
    from swarm.core.mcp_plugins import apply_plugin_mcp_runtime, swarm_config

    apply_plugin_mcp_runtime(blueprint, swarm_config(), plugin_ids)
    return plugin_ids


# --- Memories tool (#1404) -----------------------------------------------
#
# The routine's Memories attachment is a *configured* document: the operator
# owns the filename and the initial content, the run loads both, and the agent
# manages the file afterwards through one tool. The filename is never taken
# from a tool call — the model can only pick an operation, never spell a path
# — and the document layer in ``agent_memory`` refuses anything that is not a
# bare name before ``FilesystemToolset`` ever sees it.


def routine_has_memories(tools: list[str] | None) -> bool:
    return TOOL_MEMORIES in (tools or [])


def public_memories_config(incoming: Any = None) -> dict[str, Any]:
    """Normalized Memories attachment for a config block or a routine row.

    Accepts either the ``memories`` block itself or a whole routine row (the
    nested ``memories`` key wins). Raises ``ValueError`` for an unusable
    filename, a traversal-shaped scope, credential-shaped content, or a body
    over the memory ceiling — the builder must refuse to persist one, and
    :func:`run_memories_tool` turns the same error into a tool result.
    """
    raw = incoming if isinstance(incoming, dict) else {}
    block = raw.get("memories") if isinstance(raw.get("memories"), dict) else raw
    filename = normalize_memories_filename(block.get("filename"))
    scope = normalize_memories_scope(block.get("scope"))
    content = reject_credentials(str(block.get("content") or ""), "memories content")
    if len(content) > MAX_MEMORIES_CONTENT:
        raise ValueError(f"memories content must be at most {MAX_MEMORIES_CONTENT} characters.")
    return {
        "object": MEMORIES_MANAGE_OBJECT,
        "filename": filename,
        "content": content,
        "present": bool(content),
        "scope": scope,
    }


def routine_memories_block(
    incoming: Any,
    tools: list[str] | None,
) -> dict[str, Any] | None:
    """The ``memories`` block to persist for *tools*, or ``None`` to clear it.

    Removing the Memories tool clears the attachment (#1404: "remove tool
    clears attachment"). The file on disk is left alone — the run simply stops
    reading it — so nothing stale is fed back into a later run.
    """
    if not routine_has_memories(tools):
        return None
    return public_memories_config(incoming)


def run_memories_tool(config: Any, operation: str, content: str = "") -> dict[str, Any]:
    """Run one Memories operation against the configured document."""
    try:
        cfg = public_memories_config(config)
    except ValueError as exc:
        return {
            "ok": False,
            "operation": str(operation or "")[:32],
            "filename": "",
            "error": str(exc),
        }
    return run_memories_document_op(
        operation,
        content=content,
        filename=cfg["filename"],
        scope=cfg["scope"],
    )


def memories_tool_callable(config: Any = None) -> Callable[..., dict[str, Any]]:
    """Plain callable carrying the runtime name/description (SDK-optional).

    An unusable attachment fails closed: every operation answers with the
    same error instead of quietly acting on a default document the operator
    never configured.
    """
    try:
        cfg: dict[str, Any] | None = public_memories_config(config)
        config_error = ""
    except ValueError as exc:
        cfg = None
        config_error = str(exc)
    name = (cfg or {}).get("filename") or DEFAULT_MEMORIES_FILENAME

    def memories(operation: str, content: str = "") -> dict[str, Any]:
        """Manage this routine's durable memories document.

        Args:
            operation: 'create' (fails when the document already exists),
                'read', 'update' (fails when it is missing), or 'delete'.
            content: The Markdown body. Used by 'create' and 'update';
                ignored by 'read' and 'delete'.
        """
        if cfg is None:
            return {
                "ok": False,
                "operation": str(operation or "")[:32],
                "filename": "",
                "error": config_error,
            }
        return run_memories_tool(cfg, operation, content)

    memories.name = MEMORIES_TOOL_NAME
    memories.description = (
        f"Durable context for this routine, stored in {name}. "
        "Read it before acting on anything you were told to remember, and "
        "update it with what the next run needs. Never store secrets, "
        "tokens, or personal data."
    )
    return memories


def memories_tool_objects(config: Any = None) -> list[Any]:
    """Tool objects the runtime already understands.

    ``openai-agents`` ``function_tool`` when the SDK is present, else
    ``swarm.types.Tool`` with an explicit ``input_schema`` — the same fallback
    the mailbox installer uses, so a CLI-only deployment still gets a tool.
    """
    fn = memories_tool_callable(config)
    try:
        from agents import function_tool
    except Exception:  # pragma: no cover - SDK optional
        logger.debug("agents SDK not available; memories tool -> swarm Tool")
    else:
        return [function_tool(fn)]
    from swarm.types import Tool

    return [
        Tool(
            name=MEMORIES_TOOL_NAME,
            func=fn,
            description=str(fn.description),
            input_schema=dict(MEMORIES_TOOL_INPUT_SCHEMA),
        )
    ]


def _blueprint_agents(blueprint: Any) -> list[Any]:
    agents: list[Any] = []
    raw = getattr(blueprint, "agents", None)
    if isinstance(raw, dict):
        agents.extend(raw.values())
    elif isinstance(raw, list):
        agents.extend(raw)
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None and not callable(starting) and starting not in agents:
        agents.append(starting)
    return agents


def _attach_memories_to_agent(agent: Any, tools: list[Any]) -> list[str]:
    attached: list[str] = []
    for attr in ("tools", "functions"):
        current = getattr(agent, attr, None)
        if not isinstance(current, list):
            continue
        have = {
            str(getattr(fn, "name", None) or getattr(fn, "__name__", "") or "")
            for fn in current
        }
        for tool in tools:
            name = str(getattr(tool, "name", None) or "")
            if not name or name in have:
                continue
            current.append(tool)
            have.add(name)
            attached.append(name)
    return attached


def apply_routine_memories_runtime(
    blueprint: Any,
    tools: list[str] | None,
    config: Any = None,
) -> list[str]:
    """Attach the Memories tool to a live routine run.

    Mirrors ``apply_routine_plugin_runtime``: existing agents plus the lazy
    ``create_starting_agent`` factory, so a graph built during the turn carries
    the tool too. ``[]`` when the operator did not add Memories.
    """
    if not routine_has_memories(tools):
        return []
    applier = _memories_runtime_applier
    if applier is not None:
        applier(blueprint, config)
        return [MEMORIES_TOOL_NAME]
    objects = memories_tool_objects(config)
    if not objects:
        return []
    attached: list[str] = []
    factory = getattr(blueprint, "create_starting_agent", None)
    if callable(factory) and not getattr(blueprint, "_routine_memories_wrapped", False):
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            agent = factory(*args, **kwargs)
            attached.extend(_attach_memories_to_agent(agent, objects))
            return agent

        blueprint.create_starting_agent = wrapped
        blueprint._routine_memories_wrapped = True
    for agent in _blueprint_agents(blueprint):
        attached.extend(_attach_memories_to_agent(agent, objects))
    return attached


def append_memories_brief(
    instruction: str,
    tools: list[str] | None,
    config: Any = None,
) -> str:
    """Append the Memories brief plus the configured content when enabled.

    This is the attachment: the durable context the operator wrote in the
    builder rides along with every run. The filename is validated config, so
    it is safe to interpolate, and the content already passed the credential
    gate in :func:`public_memories_config`.
    """
    text = str(instruction or "").strip()
    if not routine_has_memories(tools):
        return text
    if MEMORIES_BRIEF_MARKER in text:
        return text
    cfg = public_memories_config(config)
    brief = MEMORIES_BRIEF.format(marker=MEMORIES_BRIEF_MARKER, filename=cfg["filename"])
    if cfg["content"]:
        brief = f'{brief}\n\n<memories filename="{cfg["filename"]}">\n{cfg["content"]}\n</memories>'
    if text:
        return f"{text}\n\n---\n{brief}"
    return brief


def _title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[_\-\s]+", value) if part)


def _auth_reason(env_names: list[str]) -> str:
    """Honest disabled reason. Env *names* only — never values."""
    names = [n for n in env_names if n and not _TOKENISH_RE.search(n)]
    if not names:
        return "This connector needs configuration in Settings → Plugins."
    listed = ", ".join(names)
    return (
        f"Needs {listed} — set it in Settings → Plugins. "
        "Tokens stay out of this builder."
    )


def _public_picker_text(value: str) -> str:
    """Builder copy. Token-shaped text is replaced; env names are kept."""
    text = str(value or "").strip()
    if text and _TOKENISH_RE.search(text):
        return "This connector needs configuration in Settings → Plugins."
    return text


def _picker_item(
    *,
    tool_id: str,
    label: str,
    description: str,
    kind: str,
    source: str,
    server_id: str = "",
    server_name: str = "",
    wired: bool = True,
    available: bool = True,
    reason: str = "",
    can_live: bool = True,
    manage: bool = False,
    manage_fields: list[str] | tuple[str, ...] | None = None,
    default_filename: str = "",
) -> dict[str, Any]:
    clean_reason = _public_picker_text(reason)
    return {
        "id": tool_id,
        "label": _public_picker_text(label) or tool_id,
        "description": _public_picker_text(description),
        "kind": kind,
        "source": source,
        "server_id": server_id,
        "server_name": server_name,
        "wired": wired,
        "available": available,
        "reason": clean_reason,
        "can_live": can_live,
        # Present on every row so the picker does not branch on shape.
        "manage": manage,
        "manage_fields": [str(f) for f in (manage_fields or ())],
        "default_filename": default_filename,
    }


def compose_routine_picker_catalog(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Merge built-in routine tools with the existing plugin/MCP catalog.

    Not a second registry: rows come from ``ROUTINE_TOOL_CATALOG``, installed
    ``mcpServers``, ``tool_capabilities.CATALOG``, and ``PLUGIN_CATALOG_IDS``.
    Disabled rows carry an honest reason (env *names* only).
    """
    from swarm.core.chat_plugin_tools import PLUGIN_CATALOG_IDS
    from swarm.core.mcp_plugins import load_mcp_servers, missing_mcp_env_names
    from swarm.core.tool_capabilities import CATALOG as MCP_SERVER_CATALOG

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    cap = open_pr_capability()
    items.append(
        _picker_item(
            tool_id=TOOL_OPEN_PULL_REQUEST,
            label="Open Pull Request",
            description=(
                "Open or update a GitHub pull request from this routine's agent run. "
                "Never auto-merges."
            ),
            kind="builtin",
            source="routine",
            wired=True,
            available=True,
            reason="; ".join(cap.get("reasons") or []),
            can_live=bool(cap.get("can_live")),
        )
    )
    seen.add(TOOL_OPEN_PULL_REQUEST)

    if TOOL_MEMORIES not in seen:
        # ``wired`` stays False while the run path (#1404) has not been wired
        # into ``routine_jobs``: the tool, the Manage block, and the guarded
        # document all exist here, but nothing in the live turn calls
        # ``apply_routine_memories_runtime`` yet. Flipping it is a one-line
        # change plus the #1410 picker assertion.
        items.append(
            _picker_item(
                tool_id=TOOL_MEMORIES,
                label="Memories",
                description=(
                    "Durable context in a memories file (MEMORIES.md by "
                    "default). Manage sets the filename and the content the "
                    "run loads."
                ),
                kind="builtin",
                source="routine",
                wired=False,
                available=True,
                reason="",
                can_live=False,
                manage=True,
                manage_fields=list(MEMORIES_MANAGE_FIELDS),
                default_filename=DEFAULT_MEMORIES_FILENAME,
            )
        )
        seen.add(TOOL_MEMORIES)

    installed = load_mcp_servers(config)
    for server_name, spec in installed.items():
        if not isinstance(spec, Mapping):
            continue
        enabled = spec.get("enabled") is not False
        missing = missing_mcp_env_names(spec)
        server_id = _slug_tool_id(str(server_name))
        label = str(spec.get("label") or spec.get("name") or server_name).strip() or _title_case(server_id)
        discovered = spec.get("discovered_tools") or []
        provides = spec.get("provides") or []
        rows: list[tuple[str, str]] = []
        if isinstance(discovered, (list, tuple)):
            for tool in discovered:
                if isinstance(tool, Mapping):
                    name = _runtime_tool_id(str(tool.get("name") or ""))
                    desc = str(tool.get("description") or "").strip()
                else:
                    name = _runtime_tool_id(str(getattr(tool, "name", "") or ""))
                    desc = str(getattr(tool, "description", "") or "").strip()
                if name:
                    rows.append((name, desc))
        if not rows:
            for cap_id in provides if isinstance(provides, (list, tuple)) else []:
                name = _runtime_tool_id(str(cap_id))
                if name:
                    rows.append((name, ""))
        if not rows:
            rows.append((server_id, str(spec.get("note") or "").strip()))

        if not enabled:
            reason = f"MCP server '{label}' is disabled"
            available = False
        elif missing:
            reason = _auth_reason(missing)
            available = False
        else:
            reason = ""
            available = True

        for name, desc in rows:
            if name in seen:
                continue
            meta = _FIXTURE_TOOL_META.get(name, {})
            items.append(
                _picker_item(
                    tool_id=name,
                    label=meta.get("label") or _title_case(name),
                    description=desc or meta.get("description") or f"{label} tool",
                    kind="plugin",
                    source="mcp_plugins",
                    server_id=server_id,
                    server_name=label,
                    wired=available,
                    available=available,
                    reason=reason,
                    can_live=available,
                )
            )
            seen.add(name)

    for server in MCP_SERVER_CATALOG:
        server_id = _slug_tool_id(server.name)
        installed_spec = next(
            (spec for name, spec in installed.items() if _slug_tool_id(str(name)) == server_id),
            None,
        )
        missing_auth = [n for n in server.auth_env if not (os.environ.get(n) or "").strip()]
        if installed_spec is None and server.needs_auth and missing_auth:
            if server_id not in seen:
                items.append(
                    _picker_item(
                        tool_id=server_id,
                        label=_title_case(server.name),
                        description=server.note or f"{_title_case(server.name)} connector",
                        kind="mcp",
                        source="mcp_catalog",
                        server_id=server_id,
                        server_name=_title_case(server.name),
                        wired=False,
                        available=False,
                        reason=_auth_reason(missing_auth),
                        can_live=False,
                    )
                )
                seen.add(server_id)
            continue
        if installed_spec is not None:
            continue
        for cap_id in server.provides:
            tool_id = _runtime_tool_id(str(cap_id))
            if not tool_id or tool_id in seen:
                continue
            meta = _FIXTURE_TOOL_META.get(tool_id, {})
            items.append(
                _picker_item(
                    tool_id=tool_id,
                    label=meta.get("label") or _title_case(tool_id),
                    description=meta.get("description") or server.note or f"{_title_case(server.name)} capability",
                    kind="plugin",
                    source="mcp_catalog",
                    server_id=server_id,
                    server_name=meta.get("server_name") or _title_case(server.name),
                    wired=True,
                    available=True,
                    reason="",
                    can_live=True,
                )
            )
            seen.add(tool_id)

    for tool_id in PLUGIN_CATALOG_IDS:
        slug = _runtime_tool_id(tool_id)
        if not slug or slug in seen:
            continue
        meta = _FIXTURE_TOOL_META.get(slug, {})
        items.append(
            _picker_item(
                tool_id=slug,
                label=meta.get("label") or _title_case(slug),
                description=meta.get("description") or "Shipped catalog tool",
                kind="plugin",
                source="fixture",
                server_id=meta.get("server_id") or "",
                server_name=meta.get("server_name") or "",
                wired=True,
                available=True,
                reason="",
                can_live=True,
            )
        )
        seen.add(slug)

    return items


def public_routine_tool_catalog(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """API payload for ``GET /v1/routines/tool-catalog/``."""
    return {
        "object": "routine_tool_catalog",
        "items": compose_routine_picker_catalog(config),
    }


def open_pr_capability() -> dict[str, Any]:
    """Honest probe: can *this process* open or update a GitHub PR?

    Never reads token *values* into the result — only whether the env vars
    are set. ``wired`` is always True (this module is the hook).
    """
    reasons: list[str] = []
    gh_path = shutil.which("gh")
    if not gh_path:
        reasons.append("gh CLI is not on PATH")
    token_env_set = bool(
        (os.environ.get("GH_TOKEN") or "").strip()
        or (os.environ.get("GITHUB_TOKEN") or "").strip()
    )
    if not token_env_set:
        reasons.append("GH_TOKEN/GITHUB_TOKEN is not set")
    return {
        "id": TOOL_OPEN_PULL_REQUEST,
        "wired": True,
        "gh_available": bool(gh_path),
        "token_env_set": token_env_set,
        "can_live": not reasons,
        "reasons": reasons,
        "auto_merge": False,
    }


def open_pr_context_from_github_event(event: dict[str, Any] | None) -> dict[str, Any]:
    """Build a token-free Open PR context from a parsed GitHub webhook event."""
    incoming = event if isinstance(event, dict) else {}
    number = incoming.get("number")
    try:
        issue_number = int(number) if number is not None and str(number).strip() != "" else None
    except (TypeError, ValueError):
        issue_number = None
    title = str(incoming.get("title") or "").strip()
    if not title and issue_number is not None:
        title = f"Fixes #{issue_number}"
    body_parts: list[str] = []
    if issue_number is not None:
        body_parts.append(f"Fixes #{issue_number}")
    issue_body = str(incoming.get("body") or "").strip()
    if issue_body:
        body_parts.extend(["", issue_body[:4000]])
    return {
        "owner_repo": str(incoming.get("owner_repo") or "").strip(),
        "title": title,
        "body": "\n".join(body_parts).strip(),
        "branch": str(incoming.get("branch") or "").strip() or None,
        "issue_number": issue_number,
    }


def _pr_url_matches_repo(url: str, owner_repo: str) -> bool:
    """True when *url* is a pull request in *owner_repo* (case-insensitive)."""
    repo = str(owner_repo or "").strip().strip("/").lower()
    if repo.count("/") != 1:
        return False
    owner, name = repo.split("/", 1)
    if not owner or not name:
        return False
    marker = f"https://github.com/{owner}/{name}/pull/"
    return str(url or "").strip().lower().startswith(marker)


def _scrub_secretish(text: str, field: str) -> str:
    """Reject token-shaped strings so they never reach gh or a PR body.

    Tighter than ``reject_secrets``: a bare ``sk-`` prefix also matches
    words like ``task-`` in issue titles, and those must still be allowed.
    Kebab-case names such as ``xai-grok-4-fast-reasoning`` must pass too.
    """
    value = str(text or "")
    if _HOOK_SECRET_RE.search(value):
        raise ValueError(f"{field} must not contain secrets.")
    return value


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``gh`` with the given args. Never logs env values."""
    return subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _existing_pr_for_head(owner_repo: str, branch: str) -> dict[str, Any] | None:
    result = _run_gh(
        [
            "pr",
            "list",
            "--repo",
            owner_repo,
            "--head",
            branch,
            "--json",
            "url,number,title",
            "--limit",
            "1",
        ]
    )
    if result.returncode != 0:
        return None
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0] if isinstance(rows[0], dict) else {}
    url = str(row.get("url") or "").strip()
    if not is_github_pr_url(url):
        return None
    return row


def _payload_from_gh_stdout(stdout: str, *, title: str = "") -> dict[str, Any] | None:
    parsed = parse_pr_opened(stdout)
    if parsed and is_github_pr_url(parsed.get("url")):
        return parsed
    url = extract_github_pr_url(stdout)
    if not url:
        return None
    payload = parse_pr_opened({"type": "pr_opened", "url": url, "title": title})
    return payload


def _default_open_or_update_pr(
    *,
    owner_repo: str = "",
    title: str = "",
    body: str = "",
    branch: str | None = None,
    issue_number: int | None = None,
    reply: str = "",
    **_extra: Any,
) -> dict[str, Any]:
    """Create or update a PR via ``gh``. Skip honestly when not live-capable."""
    del issue_number
    existing_from_reply = extract_github_pr_url(reply)
    if existing_from_reply and _pr_url_matches_repo(existing_from_reply, owner_repo):
        payload = parse_pr_opened({"type": "pr_opened", "url": existing_from_reply, "title": title})
        return {
            "ok": True,
            "updated": False,
            "skipped": False,
            "reason": "",
            "url": existing_from_reply,
            "payload": payload,
            "auto_merge": False,
        }

    cap = open_pr_capability()
    if not cap["can_live"]:
        return {
            "ok": False,
            "updated": False,
            "skipped": True,
            "reason": "; ".join(cap["reasons"]),
            "url": None,
            "payload": None,
            "auto_merge": False,
        }

    repo = _scrub_secretish(str(owner_repo or "").strip(), "owner_repo")
    if not repo or "/" not in repo:
        return {
            "ok": False,
            "updated": False,
            "skipped": True,
            "reason": "owner/repo is required to open a pull request",
            "url": None,
            "payload": None,
            "auto_merge": False,
        }
    pr_title = _scrub_secretish(str(title or "").strip() or "Routine change", "title")
    pr_body = _scrub_secretish(str(body or "").strip(), "body")
    head = _scrub_secretish(str(branch or "").strip(), "branch") if branch else ""

    if not head:
        # Issue webhooks carry no head branch. ``gh pr create`` without
        # ``--head`` uses the server process's current branch, which is not
        # the agent's change. Skip instead of opening that PR.
        return {
            "ok": False,
            "updated": False,
            "skipped": True,
            "reason": "no head branch to open a pull request from",
            "url": None,
            "payload": None,
            "auto_merge": False,
        }

    existing = _existing_pr_for_head(repo, head)
    if existing:
        number = existing.get("number")
        edit_args = ["pr", "edit", str(number), "--repo", repo, "--title", pr_title]
        if pr_body:
            edit_args.extend(["--body", pr_body])
        edited = _run_gh(edit_args)
        url = str(existing.get("url") or "").strip()
        if edited.returncode != 0:
            return {
                "ok": False,
                "updated": False,
                "skipped": False,
                "reason": "gh pr edit failed",
                "url": url or None,
                "payload": None,
                "auto_merge": False,
            }
        payload = parse_pr_opened({"type": "pr_opened", "url": url, "number": number, "title": pr_title})
        return {
            "ok": True,
            "updated": True,
            "skipped": False,
            "reason": "",
            "url": url,
            "payload": payload,
            "auto_merge": False,
        }

    create_args = ["pr", "create", "--repo", repo, "--title", pr_title, "--head", head]
    if pr_body:
        create_args.extend(["--body", pr_body])
    created = _run_gh(create_args)
    payload = _payload_from_gh_stdout(created.stdout or created.stderr or "", title=pr_title)
    url = (payload or {}).get("url") if payload else None
    if created.returncode != 0 or not url:
        reason = "gh pr create failed"
        err = (created.stderr or created.stdout or "").strip()
        if err and not _HOOK_SECRET_RE.search(err):
            reason = err.splitlines()[0][:240]
        return {
            "ok": False,
            "updated": False,
            "skipped": False,
            "reason": reason,
            "url": url,
            "payload": payload,
            "auto_merge": False,
        }
    return {
        "ok": True,
        "updated": False,
        "skipped": False,
        "reason": "",
        "url": url,
        "payload": payload,
        "auto_merge": False,
    }


def run_open_pr_if_enabled(
    tools: list[str] | None,
    **context: Any,
) -> dict[str, Any] | None:
    """Invoke the Open PR hook when the tool is enabled. ``None`` when off."""
    if not routine_has_open_pr(tools):
        return None
    runner = _open_pr_runner or _default_open_or_update_pr
    try:
        for field in ("owner_repo", "title", "body", "branch"):
            value = context.get(field)
            if value:
                _scrub_secretish(str(value), field)
        result = runner(**context)
    except ValueError as exc:
        logger.info("Open PR hook refused secret-looking input: %s", exc)
        return {
            "ok": False,
            "updated": False,
            "skipped": True,
            "reason": "PR title/body must not contain secrets",
            "url": None,
            "payload": None,
            "auto_merge": False,
        }
    except Exception:
        logger.exception("Open PR hook failed")
        return {
            "ok": False,
            "updated": False,
            "skipped": False,
            "reason": "Open Pull Request hook failed",
            "url": None,
            "payload": None,
            "auto_merge": False,
        }
    if not isinstance(result, dict):
        return None
    result.setdefault("auto_merge", False)
    return result


def format_open_pr_note(result: dict[str, Any] | None) -> str:
    """Token-free conversation note for an Open PR hook result."""
    if not isinstance(result, dict):
        return ""
    url = result.get("url")
    if result.get("ok") and is_github_pr_url(url):
        action = "updated" if result.get("updated") else "opened"
        return f"Open Pull Request tool {action} {url}."
    reason = str(result.get("reason") or "").strip()
    if _HOOK_SECRET_RE.search(reason):
        reason = "Open Pull Request tool skipped."
    if result.get("skipped"):
        return f"Open Pull Request tool skipped: {reason}" if reason else "Open Pull Request tool skipped."
    return f"Open Pull Request tool failed: {reason}" if reason else "Open Pull Request tool failed."
