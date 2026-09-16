"""#215: per-seat model-context usage (read-only introspection).

Counts tokens the seat would send: spliced summaries + uncovered messages +
system/instructions + tool-schema overhead, against the declared context
window. Estimate is chars/4 until a per-provider tokenizer is wired.
Never instantiates or runs a blueprint; live WS may pass an already-built
instance for a tighter overhead read.
"""

from __future__ import annotations

import json
from typing import Any

from swarm.core.chat_compact import context_for_conversation
from swarm.core.context_compress_policy import resolve_model_context_max

CONTEXT_USAGE_TYPE = "context_usage"
CHARS_PER_TOKEN = 4
SUMMARY_PREFIX = "[Conversation summary]"


def estimate_tokens(value: Any) -> int:
    """Heuristic token count (chars/4). Hook for a real tokenizer later."""
    if value is None:
        return 0
    if isinstance(value, str):
        blob = value
    else:
        try:
            blob = json.dumps(value, separators=(",", ":"), default=str, ensure_ascii=False)
        except TypeError:
            blob = str(value)
    if not blob:
        return 0
    return max(0, round(len(blob) / CHARS_PER_TOKEN))


def _unique_texts(chunks: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for chunk in chunks:
        text = (chunk or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return "\n\n".join(out)


def schema_from_tool(tool: Any) -> dict[str, Any] | None:
    """Read a tool's JSON schema without calling it."""
    if tool is None:
        return None
    if isinstance(tool, dict):
        return tool
    schema = getattr(tool, "_tool_schema", None)
    if isinstance(schema, dict) and schema:
        return schema
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
    description = getattr(tool, "description", None)
    params = getattr(tool, "params_json_schema", None)
    if not name and not params:
        return None
    row: dict[str, Any] = {}
    if name:
        row["name"] = str(name)
    if description:
        row["description"] = str(description)
    if params is not None:
        row["parameters"] = params
    return row or None


def _iter_agents(blueprint: Any):
    agents = getattr(blueprint, "agents", None)
    if isinstance(agents, dict):
        yield from agents.values()
    elif isinstance(agents, (list, tuple)):
        yield from agents
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None:
        yield starting


def _tools_from_agent(agent: Any) -> list[Any]:
    for attr in ("tools", "tool_list"):
        found = getattr(agent, attr, None)
        if isinstance(found, (list, tuple)):
            return list(found)
    return []


def overhead_from_blueprint(blueprint: Any) -> tuple[str, list[dict[str, Any]]]:
    """Instructions + tool schemas from an already-constructed blueprint."""
    chunks: list[str] = []
    schemas: list[dict[str, Any]] = []
    seen: set[str] = set()
    meta = getattr(blueprint, "metadata", None)
    if isinstance(meta, dict):
        for key in ("instructions", "description"):
            val = meta.get(key)
            if isinstance(val, str) and val.strip():
                chunks.append(val)
    for agent in _iter_agents(blueprint):
        text = getattr(agent, "instructions", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text)
        for tool in _tools_from_agent(agent):
            schema = schema_from_tool(tool)
            if not schema:
                continue
            key = json.dumps(schema, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            schemas.append(schema)
    return _unique_texts(chunks), schemas


def overhead_from_metadata(agent_id: str) -> tuple[str, list[dict[str, Any]]]:
    """Catalog metadata only — never constructs or runs a blueprint."""
    ident = (agent_id or "").strip()
    if not ident:
        return "", []
    try:
        from swarm.views.utils import get_available_blueprints_sync

        blueprints = get_available_blueprints_sync() or {}
    except Exception:
        return "", []
    info = blueprints.get(ident) if isinstance(blueprints, dict) else None
    if not isinstance(info, dict):
        return "", []
    meta = info.get("metadata") if isinstance(info.get("metadata"), dict) else {}
    cls = info.get("class_type")
    class_meta = getattr(cls, "metadata", None) if cls is not None else None
    if isinstance(class_meta, dict):
        # ClassVar metadata is richer; catalog row wins on conflict. Never instantiate.
        meta = {**class_meta, **meta}
    chunks: list[str] = []
    for key in ("instructions", "description"):
        val = meta.get(key) or info.get(key)
        if isinstance(val, str) and val.strip():
            chunks.append(val)
    schemas: list[dict[str, Any]] = []
    tools = info.get("tools")
    if isinstance(tools, list):
        schemas.extend(row for row in tools if isinstance(row, dict))
    reqs = meta.get("tool_requirements")
    if isinstance(reqs, dict) and not schemas:
        schemas = [{"name": str(name), "requirement": reqs[name]} for name in reqs]
    return _unique_texts(chunks), schemas


def breakdown_from_context(
    model_context: list[dict[str, Any]] | None,
    *,
    instructions: str = "",
    tool_schemas: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    messages = 0
    summaries = 0
    system = 0
    for row in model_context or []:
        if not isinstance(row, dict):
            continue
        tokens = estimate_tokens(row)
        role = str(row.get("role") or "")
        content = str(row.get("content") or "")
        if role == "system" and content.startswith(SUMMARY_PREFIX):
            summaries += tokens
        elif role == "system":
            system += tokens
        else:
            messages += tokens
    extra_system = estimate_tokens(instructions)
    # Instructions already spliced into a system row must not be double-counted.
    if extra_system and instructions and any(
        isinstance(row, dict)
        and str(row.get("role") or "") == "system"
        and instructions in str(row.get("content") or "")
        for row in (model_context or [])
    ):
        extra_system = 0
    return {
        "messages": messages,
        "summaries": summaries,
        "system": system + extra_system,
        "tools": estimate_tokens(tool_schemas or []),
    }


def usage_snapshot(
    *,
    conversation_id: str,
    agent_id: str,
    turns: list[dict[str, Any]] | None,
    model_id: str | None = None,
    profile: dict[str, Any] | None = None,
    instructions: str = "",
    tool_schemas: list[dict[str, Any]] | None = None,
    blueprint: Any = None,
) -> dict[str, Any]:
    """Read-only usage payload for the HTTP endpoint and WS ``context_usage`` event."""
    if blueprint is not None and (not instructions or tool_schemas is None):
        bp_instructions, bp_schemas = overhead_from_blueprint(blueprint)
        if not instructions:
            instructions = bp_instructions
        if tool_schemas is None:
            tool_schemas = bp_schemas
    if not instructions or tool_schemas is None:
        meta_instructions, meta_schemas = overhead_from_metadata(agent_id)
        if not instructions:
            instructions = meta_instructions
        if tool_schemas is None:
            tool_schemas = meta_schemas
    context = context_for_conversation(conversation_id, list(turns or []))
    parts = breakdown_from_context(
        context,
        instructions=instructions,
        tool_schemas=tool_schemas,
    )
    total = int(sum(parts.values()))
    window = resolve_model_context_max(profile=profile, model_id=model_id)
    pct = None
    if window is not None and window > 0:
        pct = min(100, round((total / window) * 100))
    return {
        "type": CONTEXT_USAGE_TYPE,
        "conversation_id": conversation_id or "",
        "agent_id": agent_id or "",
        "tokens": total,
        "window": window,
        "pct": pct,
        "estimate": True,
        "breakdown": parts,
    }
