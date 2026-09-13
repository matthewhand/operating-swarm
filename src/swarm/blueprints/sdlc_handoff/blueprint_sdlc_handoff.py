"""sdlc_handoff — forced BA → Engineer → Tester (and circular skeptic).

REQ-156 example blueprint. openai-agents ``handoff`` edges are the product:
each seat gets **only** the next hop. LLM-only freestyle cannot enforce that.

Variants:
    pipeline / forced-sequence   BA → Engineer → Tester (one-way)
    skeptic_loop / circular-skeptic   last skeptic punts back to Engineer

CLI and remote harnesses are **not** injected into this graph. They stay
native sessions and may sit on a mixed team (see the example pack).

Deterministic grammar (no LLM — same idea as ``software_dev``)::

    status | graph     print declared + live handoff edges
    variant <name>     switch pipeline vs skeptic_loop (also ``params.variant``)

Config block ``sdlc_handoff`` (optional)::

    {"sdlc_handoff": {"variant": "pipeline"}}
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

from openai import AsyncOpenAI

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.handoff_graph import (
    PIPELINE_GRAPH_ID,
    SKEPTIC_LOOP_GRAPH_ID,
    assert_edges_match,
    build_agents,
    format_graph,
    live_edges,
    load_example_graph,
)

logger = logging.getLogger(__name__)

VARIANT_ALIASES = {
    "pipeline": PIPELINE_GRAPH_ID,
    "forced-sequence": PIPELINE_GRAPH_ID,
    "forced_sequence": PIPELINE_GRAPH_ID,
    PIPELINE_GRAPH_ID: PIPELINE_GRAPH_ID,
    "skeptic_loop": SKEPTIC_LOOP_GRAPH_ID,
    "skeptic-loop": SKEPTIC_LOOP_GRAPH_ID,
    "circular": SKEPTIC_LOOP_GRAPH_ID,
    "circular-skeptic": SKEPTIC_LOOP_GRAPH_ID,
    "circular_skeptic": SKEPTIC_LOOP_GRAPH_ID,
    SKEPTIC_LOOP_GRAPH_ID: SKEPTIC_LOOP_GRAPH_ID,
}


class SdlcHandoffBlueprint(BlueprintBase):
    """API-only SDLC handoff graph: forced pipeline or circular skeptic."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "sdlc_handoff",
        "title": "SDLC handoff graph (BA / Engineer / Tester)",
        "description": (
            "Example openai-agents handoff graph: forced BA → Engineer → Tester, "
            "plus a circular skeptic that can punt back. API/blueprint only — "
            "CLI and remote harnesses stay native. Not extra Grok Bot seats."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["sdlc", "handoff", "openai-agents", "demo", "ba", "engineer", "tester"],
        "aliases": ["sdlc-handoff", "sdlc_pipeline"],
        "workflow": "handoff",
        "required_mcp_servers": [],
        "env_vars": [],
        "agents": [
            {"name": "ba", "role": "default", "seat": "ba"},
            {"name": "engineer", "role": "engineer", "seat": "engineer"},
            {"name": "tester", "role": "default", "seat": "tester"},
            {"name": "skeptic", "role": "skeptic", "seat": "skeptic"},
        ],
    }

    def __init__(self, blueprint_id: str = "sdlc_handoff", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}
        self._agents: dict[str, Any] = {}
        self._graph_id: str = PIPELINE_GRAPH_ID

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})
        self._agents = {}

    def _cfg(self) -> dict[str, Any]:
        block = (self._config or {}).get("sdlc_handoff") or {}
        return block if isinstance(block, dict) else {}

    def resolve_variant(self) -> str:
        raw = (
            self._params.get("variant")
            or self._cfg().get("variant")
            or PIPELINE_GRAPH_ID
        )
        key = str(raw).strip().lower().replace(" ", "-")
        if key not in VARIANT_ALIASES:
            raise ValueError(
                f"Unknown sdlc_handoff variant {raw!r}. "
                f"Use pipeline or skeptic_loop."
            )
        return VARIANT_ALIASES[key]

    def graph(self):
        graph_id = self.resolve_variant()
        self._graph_id = graph_id
        return load_example_graph(graph_id)

    def _build_agents(self) -> dict[str, Any]:
        if self._agents:
            return self._agents
        graph = self.graph()
        self._agents = build_agents(graph)
        return self._agents

    def _last_user_text(self, messages: list[dict[str, Any]]) -> str:
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                return str(m["content"]).strip()
        return support.render_prompt(messages).strip()

    def _parse(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        params = dict(self._params)
        action = str(params.get("action") or "").strip().lower()
        text = self._last_user_text(messages)
        if action in ("status", "graph", "edges", "who", "variant"):
            if action == "variant" and text:
                self._params["variant"] = text.strip()
                self._agents = {}
            return "graph", text
        if action:
            return "chat", text
        parts = text.split(None, 1)
        head = (parts[0].lower() if parts else "").rstrip(":")
        rest = parts[1] if len(parts) > 1 else ""
        if head in ("status", "graph", "edges", "who"):
            return "graph", rest
        if head == "variant" and rest:
            self._params["variant"] = rest.strip()
            self._agents = {}
            return "graph", rest
        return "chat", text

    def _status_text(self) -> str:
        graph = self.graph()
        agents = self._build_agents()
        live = live_edges(agents)
        assert_edges_match(graph, agents)
        return format_graph(graph, live=live)

    def _seat_id(self) -> str:
        graph = self.graph()
        known = set(graph.node_ids())
        params = dict(self._params)
        for key in ("seat", "target", "agent"):
            raw = str(params.get(key) or "").strip()
            if raw and raw not in {"all", "*"} and raw in known:
                return raw
        return graph.entry

    def _seat_instructions(self, seat: str) -> str:
        graph = self.graph()
        node = graph.node_map().get(seat)
        name = node.name if node else seat
        role = node.role if node else "default"
        extra = (node.instructions if node else "") or ""
        dest = ", ".join(graph.outgoing(seat)) or "nobody (finish this seat)"
        return (
            f"You are {name} (seat {seat}, role {role}) on the SDLC handoff graph. "
            f"When this seat is done, hand off only to: {dest}. "
            "Do not skip seats or invent others. Reply as this persona."
            + (f" {extra}" if extra else "")
        )

    def _llm_messages(self, messages: list[dict[str, Any]], seat: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = [
            {"role": "system", "content": self._seat_instructions(seat)}
        ]
        for item in messages or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")
            if role not in {"user", "assistant", "system", "developer"}:
                continue
            content = item.get("content")
            if content is None or content == "":
                continue
            mapped = "system" if role == "developer" else role
            out.append({"role": mapped, "content": str(content)})
        if len(out) == 1:
            out.append({"role": "user", "content": self._last_user_text(messages)})
        return out

    def _llm_client_kwargs(self) -> tuple[str, dict[str, Any]]:
        profile = self.get_llm_profile(self.llm_profile_name)
        base_url = (
            (profile or {}).get("base_url")
            or os.getenv("LITELLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
        )
        api_key = (
            (profile or {}).get("api_key")
            or os.getenv("LITELLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "ollama"
        )
        model_name = (
            (profile or {}).get("model")
            or os.getenv("LITELLM_MODEL")
            or os.getenv("DEFAULT_LLM")
            or os.getenv("OPENAI_MODEL")
        )
        if not model_name:
            raise RuntimeError(
                "No LLM model configured. Save an LLM profile (model + base URL) "
                "in Settings, or set LITELLM_MODEL/DEFAULT_LLM."
            )
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        return str(model_name), client_kwargs

    async def _chat_llm(self, messages: list[dict[str, Any]]) -> str:
        seat = self._seat_id()
        model_name, client_kwargs = self._llm_client_kwargs()
        client = AsyncOpenAI(**client_kwargs)
        response = await client.chat.completions.create(
            model=model_name,
            messages=self._llm_messages(messages, seat),
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise RuntimeError("LLM returned no choices")
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if not content:
            raise RuntimeError("LLM returned empty content")
        return str(content)

    async def run(self, messages: list[dict[str, Any]], **_kwargs) -> Any:
        action, _text = self._parse(messages)
        test_mode = os.environ.get("SWARM_TEST_MODE", "").lower() in ("1", "true", "yes")
        if action == "graph":
            try:
                body = self._status_text()
            except Exception as exc:
                logger.warning("sdlc_handoff graph status failed: %s", exc)
                body = f"sdlc_handoff: could not load example graph ({exc})"
                if not test_mode:
                    body += "\nCLI/remote harnesses stay native; only API gets this graph."
            yield support.message_chunk(
                body,
                final=True,
                meta=support.backend_meta(["sdlc_handoff", self._graph_id]),
            )
            return

        try:
            body = await self._chat_llm(messages)
        except Exception as exc:
            logger.warning("sdlc_handoff LLM call failed: %s", exc)
            body = (
                f"Error: LLM call failed ({exc}). "
                "Check the saved LLM profile (base URL + model). "
                "This seat does not echo the user message."
            )
        yield support.message_chunk(
            body,
            final=True,
            meta=support.backend_meta(["sdlc_handoff", self._seat_id()]),
        )


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        bp = SdlcHandoffBlueprint()
        async for chunk in bp.run([{"role": "user", "content": "graph"}]):
            msgs = chunk.get("messages") if isinstance(chunk, dict) else None
            if msgs:
                print(msgs[0].get("content") or "")

    asyncio.run(_main())
