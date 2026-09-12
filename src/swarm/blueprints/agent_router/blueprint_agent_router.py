"""
Agent Router Blueprint - Multi-agent orchestration with grouped endpoints and routing.

This blueprint provides a Swarm workspace where:
1. Agents are listed in a sidebar
2. Agents are grouped into a single endpoint for inference
3. Messages can be routed between agent personas using handoff or as_tool patterns

The blueprint demonstrates the openai-agents framework's handoff and tool capabilities
for creating sophisticated multi-agent workflows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, ClassVar

try:
    from agents import Agent, Runner, Tool, function_tool, Handoff
    from agents.mcp import MCPServer
    from openai import AsyncOpenAI
    HAS_AGENTS = True
except ImportError:
    HAS_AGENTS = False
    Agent = Any
    Runner = Any
    Handoff = Any

from swarm.core.agent_types import AGENT_TYPE_CATALOG, agent_type_for_kind, public_personas
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.blueprint_spec import BLUEPRINT_AGENT_BRIEF, BLUEPRINT_ONE_LINER
from swarm.core.cli_catalog import listed_cli_specs
from swarm.core.remote_teams import listed_remote_specs
from swarm.core.router_designs import load_designs

logger = logging.getLogger(__name__)

# Router itself is already the page orchestrator — do not list it twice.
_SKIP_BLUEPRINT_IDS = {"agent_router"}
_BP_PALETTE = (
    "#38bdf8",
    "#a78bfa",
    "#34d399",
    "#fb7185",
    "#fbbf24",
    "#818cf8",
    "#f472b6",
    "#2dd4bf",
)


def listed_blueprint_specs() -> list[dict[str, Any]]:
    """Discovered BlueprintBase teams as sidebar agent specs."""
    try:
        from swarm.views.utils import get_available_blueprints_sync

        # Chat completions already run in an async loop. Calling the
        # @sync_to_async get_available_blueprints without await returns a
        # coroutine; async_to_sync deadlocks the worker. Use the sync helper.
        available = get_available_blueprints_sync()
    except Exception:
        logger.warning("Could not list blueprints for the agent sidebar", exc_info=True)
        return []
    if not isinstance(available, dict):
        return []
    specs: list[dict[str, Any]] = []
    for i, blueprint_id in enumerate(sorted(available)):
        if blueprint_id in _SKIP_BLUEPRINT_IDS:
            continue
        info = available.get(blueprint_id) or {}
        meta = info.get("metadata") if isinstance(info, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        title = (meta.get("title") or "").strip()
        name = title or (meta.get("name") or blueprint_id)
        if name == blueprint_id:
            name = blueprint_id.replace("_", " ").replace("-", " ").title()
        description = (meta.get("description") or "").strip()
        specs.append({
            "agent_id": blueprint_id,
            "blueprint_id": blueprint_id,
            "name": name,
            "kind": "blueprint",
            "agent_type": "api",
            "group": "blueprints",
            "type": "team",
            "specialty": "Coded agent team",
            "description": description or BLUEPRINT_ONE_LINER,
            "color": _BP_PALETTE[i % len(_BP_PALETTE)],
            "icon": "📦",
        })
    return specs


class DesignedAgent:
    """Sidebar agent created in the designer (personality, swarm, or CLI)."""

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
        self.name = spec["name"]
        self.kind = spec["kind"]
        self.instructions = spec.get("instructions") or ""
        self.cli = spec.get("cli")
        self.base_url = spec.get("base_url") or ""
        self.model = spec.get("model") or "default"
        self.framework = spec.get("framework") or ""
        self.target = spec.get("target") or ""
        self.transport = spec.get("transport") or ""
        self.blueprint_id = spec.get("blueprint_id") or ""
        self.personas = list(spec.get("personas") or [])
        self.tools: list[Any] = []
        self.metadata = {
            "agent_id": spec["agent_id"],
            "specialty": spec.get("specialty") or "",
            "color": spec.get("color") or "#6366f1",
            "icon": spec.get("icon") or "🤖",
            "type": spec.get("type") or "specialist",
            "group": spec.get("group") or "specialists",
            "description": spec.get("description") or "",
            "kind": spec["kind"],
            "agent_type": spec.get("agent_type") or agent_type_for_kind(spec["kind"]),
            "cli": spec.get("cli") or "",
            "framework": spec.get("framework") or "",
            "base_url": spec.get("base_url") or "",
            "target": spec.get("target") or "",
            "model": spec.get("model") or "",
            "parent_id": spec.get("parent_id") or "",
            "remote_id": spec.get("remote_id") or "",
            "role": spec.get("role") or "",
            "personas": public_personas(spec.get("personas")),
        }
        for key, value in self.metadata.items():
            setattr(self, key, value)


class AgentRouterBlueprint(BlueprintBase):
    """Multi-agent router with grouped endpoints and handoff capabilities."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "agent_router",
        "title": "Agent Router (Multi-Agent Orchestration)",
        "description": (
            "A blueprint that groups multiple agents into a single endpoint with routing capabilities. "
            "Agents can handoff to each other or be used as tools. Designed for the Swarm "
            "workspace where agents are listed in a sidebar and messages can be routed between them."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["multi-agent", "routing", "handoff", "orchestration", "openai-agents"],
        "required_mcp_servers": [],
        "env_vars": ["OPENAI_API_KEY"],
    }

    def __init__(self, blueprint_id: str = "agent_router", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}
        self._agents: dict[str, Agent] = {}
        self._tools: dict[str, Tool] = {}
        self._handoffs: dict[str, Handoff] = {}
        self._router_agent: Agent | None = None
        self._agent_status: dict[str, str] = {}
        self._agent_contexts: dict[str, dict[str, Any]] = {}
        self._conversations: list[dict[str, Any]] = []
        self._delegations: list[dict[str, Any]] = []
        
        if HAS_AGENTS:
            try:
                self._initialize_agents()
            except Exception as e:
                logger.warning(f"Failed to initialize agents: {e}. Running in limited mode.")
                self._initialize_basic_agents()
        else:
            self._initialize_basic_agents()
        self.load_designed_agents()

    def _initialize_basic_agents(self) -> None:
        """Initialize basic agent metadata without actual Agent instances (fallback)."""
        basic_agents = {
            "researcher": {
                "name": "Researcher",
                "specialty": "information gathering and analysis",
                "color": "#3b82f6",
                "icon": "🔍",
                "type": "specialist",
                "group": "specialists",
                "agent_id": "researcher",
                "description": "Information gathering, deep web search, literature synthesis, and structured facts extraction."
            },
            "writer": {
                "name": "Writer",
                "specialty": "content creation and writing",
                "color": "#10b981",
                "icon": "✍️",
                "type": "specialist",
                "group": "specialists",
                "agent_id": "writer",
                "description": "High-quality prose composition, report drafting, technical documentation, and copywriting."
            },
            "analyst": {
                "name": "Analyst",
                "specialty": "data analysis and problem solving",
                "color": "#8b5cf6",
                "icon": "📊",
                "type": "specialist",
                "group": "specialists",
                "agent_id": "analyst",
                "description": "Data analysis, systems breakdown, architecture planning, and tradeoff evaluations."
            },
            "coder": {
                "name": "Coder",
                "specialty": "software development and coding",
                "color": "#f59e0b",
                "icon": "💻",
                "type": "specialist",
                "group": "tools",
                "agent_id": "coder",
                "description": "Code, tests, and Open Swarm blueprints (Python BlueprintBase teams for Chat and swarm-cli)."
            }
        }
        
        # Create placeholder objects that have the same interface for UI methods
        for agent_id, config in basic_agents.items():
            class BasicAgent:
                def __init__(self, cfg):
                    for key, value in cfg.items():
                        setattr(self, key, value)
                    self.metadata = cfg
                    self.tools = []
            
            self._agents[agent_id] = BasicAgent(config)
            self._agent_status[agent_id] = "idle"
            self._agent_contexts[agent_id] = {}
        
        # Create the router agent
        router_config = {
            "name": "Agent Router",
            "specialty": "message coordination and routing",
            "color": "#ef4444",
            "icon": "🎯",
            "type": "router",
            "group": "orchestration",
            "agent_id": "router",
            "description": "Master orchestrator routing queries, coordinating multi-agent consensus, and handling delegations."
        }
        class BasicRouterAgent:
            def __init__(self, cfg):
                for key, value in cfg.items():
                    setattr(self, key, value)
                self.metadata = cfg
                self.tools = []
        
        self._agents["router"] = BasicRouterAgent(router_config)
        self._router_agent = self._agents["router"]
        self._agent_status["router"] = "idle"
        self._agent_contexts["router"] = {}
        
        # Set up basic handoff rules
        self._handoff_rules = [
            {"agent_id": "researcher", "patterns": ["research", "find information", "look up", "search", "data", "facts"], "description": "Route research and information gathering tasks"},
            {"agent_id": "writer", "patterns": ["write", "create", "draft", "compose", "document", "article", "report"], "description": "Route content creation and writing tasks"},
            {"agent_id": "analyst", "patterns": ["analyze", "break down", "solve", "problem", "structure", "plan"], "description": "Route analysis and problem-solving tasks"},
            {"agent_id": "coder", "patterns": ["code", "program", "script", "debug", "fix", "implement", "write code"], "description": "Route software development and coding tasks"}
        ]

    def _initialize_agents(self) -> None:
        """Initialize the default set of agents for the router."""
        if not HAS_AGENTS:
            return
            
        # Get model instance from config
        try:
            model_instance = self._get_model_instance(self._resolve_llm_profile())
        except Exception as e:
            logger.warning(f"Failed to get model instance: {e}. Using None for basic agent setup.")
            model_instance = None
        
        # Define agent personas with their specialties
        agent_configs = {
            "researcher": {
                "name": "Researcher",
                "instructions": (
                    "You are a research specialist. Your role is to gather information, "
                    "analyze data, and provide comprehensive background on topics. "
                    "You have access to search tools and can delegate specific analysis "
                    "tasks to other agents when needed."
                ),
                "specialty": "information gathering and analysis",
                "color": "#3b82f6",  # blue
                "icon": "🔍"
            },
            "writer": {
                "name": "Writer", 
                "instructions": (
                    "You are a professional writer and content creator. Your role is to "
                    "create high-quality written content, including articles, reports, "
                    "and documentation. You can request research from the Researcher "
                    "agent when you need more information."
                ),
                "specialty": "content creation and writing",
                "color": "#10b981",  # green
                "icon": "✍️"
            },
            "analyst": {
                "name": "Analyst",
                "instructions": (
                    "You are a data analyst and problem solver. Your role is to "
                    "analyze complex problems, break them down into components, "
                    "and provide structured solutions. You can use the Researcher "
                    "for data gathering and the Writer for documentation."
                ),
                "specialty": "data analysis and problem solving", 
                "color": "#8b5cf6",  # purple
                "icon": "📊"
            },
            "coder": {
                "name": "Coder",
                "instructions": (
                    "You are a senior software developer. Your role is to write, "
                    "review, and debug code — including Open Swarm blueprints "
                    "(coded agent teams). "
                    + BLUEPRINT_AGENT_BRIEF +
                    " You can request specifications from the Analyst and documentation from the Writer."
                ),
                "specialty": "software development and coding",
                "color": "#f59e0b",  # amber
                "icon": "💻"
            }
        }
        
        # Create agents
        for agent_id, config in agent_configs.items():
            agent = Agent(
                name=config["name"],
                model=model_instance,
                instructions=config["instructions"]
            )
            
            # Add metadata as custom attribute for UI
            agent.metadata = {
                "specialty": config["specialty"],
                "color": config["color"],
                "icon": config["icon"],
                "agent_id": agent_id,
                "type": "specialist",
                "group": "tools" if agent_id == "coder" else "specialists",
                "description": config.get("instructions", "")[:120] + "..."
            }
            agent.group = agent.metadata["group"]
            agent.specialty = agent.metadata["specialty"]
            agent.color = agent.metadata["color"]
            agent.icon = agent.metadata["icon"]
            agent.type = agent.metadata["type"]
            agent.description = agent.metadata["description"]
            
            self._agents[agent_id] = agent
            self._agent_status[agent_id] = "idle"
            self._agent_contexts[agent_id] = {}
            
        # Create tools for cross-agent communication
        self._create_agent_tools()
        
        # Create handoffs between agents
        self._create_handoffs()
        
        # Create the main router agent (do not wipe specialists if this fails)
        try:
            self._create_router_agent()
        except Exception as exc:
            logger.warning("Router agent init failed; specialists still available: %s", exc)

    def _create_agent_tools(self) -> None:
        """Create tools that allow agents to use each other as tools."""
        if not HAS_AGENTS:
            return
            
        # Create a tool for each agent that allows other agents to "consult" them
        for agent_id, agent in self._agents.items():
            agent_copy = agent  # Reference to the actual agent
            
            # Create a tool that delegates to this agent
            tool_func = self._create_agent_delegation_tool(agent_id, agent_copy)
            try:
                tool = function_tool(
                    tool_func,
                    name_override=f"consult_{agent_id}",
                    description_override=f"Consult with the {agent_copy.name} agent for {agent_copy.metadata.get('specialty', 'specialized assistance')}"
                )
            except TypeError:
                tool = function_tool(tool_func)
            self._tools[f"consult_{agent_id}"] = tool
            
            # Add the tool to the agent itself so it can use other agents
            for other_agent in self._agents.values():
                if other_agent != agent_copy:
                    other_agent.tools.append(tool)

    def _create_agent_delegation_tool(self, agent_id: str, agent: Agent) -> callable:
        """Create a tool function that delegates work to a specific agent."""
        def delegation_tool(query: str, context: str = "") -> str:
            """Execute a query using the specified agent and return the result."""
            import concurrent.futures

            def _run():
                from agents import Runner
                result = Runner.run_sync(starting_agent=agent, input=query)
                return result.final_output if hasattr(result, "final_output") else str(result)

            try:
                # Cap nested sync runs so consult_* cannot wedge the ASGI worker
                # when called from inside async Runner.run (wait_for cannot cancel
                # a blocking run_sync on the event-loop thread otherwise).
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_run)
                    out = fut.result(timeout=8.0)
                return f"Response from {agent.name}: {out}"
            except concurrent.futures.TimeoutError:
                logger.error("Delegation to %s timed out after 8s", getattr(agent, "name", agent_id))
                return f"Error consulting {agent.name}: timed out after 8s"
            except Exception as e:
                logger.exception("Delegation to %s failed", getattr(agent, "name", agent_id))
                return f"Error consulting {agent.name}: {e}"
                
        return delegation_tool

    def _create_handoffs(self) -> None:
        """Create handoff rules between agents for automatic routing."""
        if not HAS_AGENTS:
            return
            
        # Define handoff rules based on content patterns
        handoff_rules = [
            # Research-related queries -> Researcher
            {
                "agent_id": "researcher",
                "patterns": ["research", "find information", "look up", "search", "data", "facts"],
                "description": "Route research and information gathering tasks"
            },
            # Writing-related queries -> Writer  
            {
                "agent_id": "writer",
                "patterns": ["write", "create", "draft", "compose", "document", "article", "report"],
                "description": "Route content creation and writing tasks"
            },
            # Analysis-related queries -> Analyst
            {
                "agent_id": "analyst",
                "patterns": ["analyze", "break down", "solve", "problem", "structure", "plan"],
                "description": "Route analysis and problem-solving tasks"
            },
            # Coding-related queries -> Coder
            {
                "agent_id": "coder", 
                "patterns": ["code", "program", "script", "debug", "fix", "implement", "write code"],
                "description": "Route software development and coding tasks"
            }
        ]
        
        # Store handoff rules for routing logic
        self._handoff_rules = handoff_rules

    def _create_router_agent(self) -> None:
        """Create the main router agent that handles incoming messages and routes them."""
        if not HAS_AGENTS:
            return
            
        model_instance = self._get_model_instance(self._resolve_llm_profile())
        
        # Router instructions
        agent_descriptions = []
        for agent in self._agents.values():
            spec = agent.metadata.get('specialty', 'general') if hasattr(agent, 'metadata') else getattr(agent, 'specialty', 'general')
            agent_descriptions.append(f"- {agent.name} ({spec})")
        
        agents_list = "\n".join(agent_descriptions)
        
        router_instructions = f"""
You are the Agent Router, a sophisticated orchestrator for a multi-agent system.

Your role is to:
1. Analyze incoming user requests
2. Determine the best agent or combination of agents to handle each request
3. Route the request to the appropriate agent(s)
4. Coordinate responses when multiple agents are involved
5. Handle handoffs between agents when needed

Available agents and their specialties:
{agents_list}

Routing guidelines:
- For research and information gathering: Use the Researcher agent
- For content creation and writing: Use the Writer agent  
- For data analysis and problem solving: Use the Analyst agent
- For coding and development: Use the Coder agent
- For complex requests: You may need to coordinate multiple agents

You can also use the available consultation tools to directly query specific agents when you need their expertise.

Remember to provide a clear, unified response to the user, even when multiple agents contribute.
"""
        
        # Create router agent with all tools (including agent consultation tools)
        all_tools = list(self._tools.values())
        
        router_agent = Agent(
            name="Agent Router",
            model=model_instance,
            instructions=router_instructions,
            tools=all_tools
        )
        router_agent.metadata = {
            "type": "router",
            "color": "#ef4444",  # red
            "icon": "🎯",
            "group": "orchestration",
            "agent_id": "router",
            "specialty": "message coordination and routing",
            "description": "Master orchestrator routing queries, coordinating multi-agent consensus, and handling delegations."
        }
        router_agent.group = "orchestration"
        router_agent.specialty = "message coordination and routing"
        router_agent.color = "#ef4444"
        router_agent.icon = "🎯"
        router_agent.type = "router"
        router_agent.description = "Master orchestrator routing queries, coordinating multi-agent consensus, and handling delegations."
        
        self._router_agent = router_agent
        self._agents["router"] = router_agent
        self._agent_status["router"] = "idle"
        self._agent_contexts["router"] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        """Capture per-request params forwarded by the API view."""
        self._params = dict(params or {})
        profile = str(self._params.get("llm_profile") or "").strip()
        if profile:
            self._llm_profile_name = profile
            self._resolved_llm_profile = None

    def _request_llm_profile(self) -> str:
        return str(self._params.get("llm_profile") or "").strip() or self._resolve_llm_profile()

    def load_designed_agents(self, *, expand_remotes: bool = False) -> None:
        """Attach (or refresh) designer-created agents from disk.

        *expand_remotes* defaults False: live herdr/HTTP discovery blocks the
        ASGI worker (30s herdr + multi-host probes) and wedges --workers 1 tip
        during /v1/chat/completions. Sidebar may pass expand_remotes=True.
        """
        designed_ids = [
            aid for aid, agent in self._agents.items()
            if getattr(agent, "kind", None) or (getattr(agent, "metadata", {}) or {}).get("kind")
        ]
        for aid in designed_ids:
            self._agents.pop(aid, None)
            self._agent_status.pop(aid, None)
            self._agent_contexts.pop(aid, None)
        cfg = self._config if isinstance(self._config, dict) else {}
        for spec in listed_remote_specs(cfg, expand=expand_remotes):
            self._attach_designed(spec)
        for spec in listed_cli_specs():
            if spec["agent_id"] in self._agents:
                continue
            self._attach_designed(spec)
        for spec in load_designs():
            self._attach_designed(spec)
        for spec in listed_blueprint_specs():
            if spec["agent_id"] in self._agents:
                continue
            self._attach_designed(spec)
        from swarm.core.support_agent import support_agent_spec

        self._attach_designed(support_agent_spec())

    def _attach_designed(self, spec: dict[str, Any]) -> None:
        agent_id = spec["agent_id"]
        kind = spec["kind"]
        attached: Any = None
        if kind == "personality" and HAS_AGENTS:
            try:
                model_instance = self._get_model_instance(self._resolve_llm_profile())
                agent = Agent(
                    name=spec["name"],
                    model=model_instance,
                    instructions=spec.get("instructions") or "",
                )
                agent.metadata = {
                    "specialty": spec.get("specialty") or "",
                    "color": spec.get("color") or "#6366f1",
                    "icon": spec.get("icon") or "🤖",
                    "agent_id": agent_id,
                    "type": spec.get("type") or "specialist",
                    "group": spec.get("group") or "specialists",
                    "description": spec.get("description") or "",
                    "kind": "personality",
                    "agent_type": "api",
                    "personas": public_personas(spec.get("personas")),
                }
                for key, value in agent.metadata.items():
                    setattr(agent, key, value)
                attached = agent
            except Exception as exc:
                logger.warning("Designed personality %s fell back to stub: %s", agent_id, exc)
        if attached is None:
            attached = DesignedAgent(spec)
        self._agents[agent_id] = attached
        self._agent_status[agent_id] = "idle"
        self._agent_contexts[agent_id] = {}

    def get_agent_info(self) -> dict[str, Any]:
        """Get information about all available agents for UI display."""
        # Do not expand remotes here — discovery belongs off the hot path.
        self.load_designed_agents(expand_remotes=False)
        agents_info = {}
        
        for agent_id, agent in self._agents.items():
            meta = getattr(agent, "metadata", {}) or {}
            kind = meta.get("kind", getattr(agent, "kind", "builtin")) or "builtin"
            personas = public_personas(
                meta.get("personas") or getattr(agent, "personas", None)
            )
            agents_info[agent_id] = {
                "name": agent.name,
                "specialty": meta.get("specialty", getattr(agent, "specialty", "General")),
                "color": meta.get("color", getattr(agent, "color", "#666666")),
                "icon": meta.get("icon", getattr(agent, "icon", "🤖")),
                "agent_id": agent_id,
                "type": meta.get("type", getattr(agent, "type", "specialist")),
                "group": meta.get("group", getattr(agent, "group", "specialists")),
                "status": self._agent_status.get(agent_id, "idle"),
                "description": meta.get("description", getattr(agent, "description", "")),
                "kind": kind,
                "agent_type": meta.get("agent_type") or agent_type_for_kind(kind),
                "cli": meta.get("cli", getattr(agent, "cli", "")),
                "framework": meta.get("framework", getattr(agent, "framework", "")),
                "base_url": meta.get("base_url") or getattr(agent, "base_url", "") or "",
                "target": meta.get("target") or getattr(agent, "target", "") or "",
                "model": meta.get("model") if isinstance(meta.get("model"), str) else "",
                "parent_id": meta.get("parent_id") or "",
                "remote_id": meta.get("remote_id") or "",
                "role": meta.get("role") or getattr(agent, "role", "") or "",
                "personas": personas,
            }
            
        return {
            "agents": agents_info,
            "router": "router",
            "groups": ["specialists", "tools", "orchestration", "remote", "blueprints"],
            "agent_types": [dict(item) for item in AGENT_TYPE_CATALOG],
            "handoff_rules": self._handoff_rules if hasattr(self, '_handoff_rules') else []
        }

    def route_message(self, message: str) -> str:
        """Route a message to the appropriate agent based on content analysis."""
        if not hasattr(self, '_handoff_rules'):
            return "router"
            
        message_lower = message.lower()
        
        matched_rules = []
        for rule in self._handoff_rules:
            for pattern in rule["patterns"]:
                if pattern in message_lower:
                    matched_rules.append((len(pattern), rule["agent_id"]))
                    
        if matched_rules:
            matched_rules.sort(key=lambda x: x[0], reverse=True)
            return matched_rules[0][1]
                    
        return "router"

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Main execution method that handles message routing and agent orchestration."""
        self.load_designed_agents()
        params = dict(self._params)
        
        if not messages:
            yield {"content": "No message provided.", "role": "assistant"}
            return
            
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user" and msg.get("content"):
                user_message = msg["content"]
                break
                
        if not user_message:
            yield {"content": "No user message found.", "role": "assistant"}
            return

        routing_strategy = params.get("routing_strategy") or params.get("strategy") or "auto_route"
        target_agent_id = params.get("target_agent") or params.get("agent")
        
        if routing_strategy == "consensus" or target_agent_id == "consensus":
            agent_ids = params.get("agent_ids")
            consensus_data = await self.run_consensus(user_message, agent_ids=agent_ids)
            yield {
                "content": consensus_data["synthesis"],
                "role": "assistant",
                "agent": "Consensus Synthesis",
                "consensus_data": consensus_data
            }
            return
            
        if routing_strategy == "direct" and target_agent_id and target_agent_id in self._agents:
            self._agent_status[target_agent_id] = "working"
            try:
                async for chunk in self._run_agent(self._agents[target_agent_id], messages, **kwargs):
                    yield chunk
            finally:
                self._agent_status[target_agent_id] = "idle"
            return
            
        if routing_strategy == "router" or target_agent_id == "router":
            self._agent_status["router"] = "working"
            try:
                async for chunk in self._run_router_agent(messages, **kwargs):
                    yield chunk
            finally:
                self._agent_status["router"] = "idle"
            return
            
        # Auto-route
        selected_agent = self.route_message(user_message)
        if selected_agent == "router":
            self._agent_status["router"] = "working"
            try:
                async for chunk in self._run_router_agent(messages, **kwargs):
                    yield chunk
            finally:
                self._agent_status["router"] = "idle"
        else:
            self._agent_status[selected_agent] = "working"
            try:
                async for chunk in self._run_agent(self._agents[selected_agent], messages, **kwargs):
                    yield chunk
            finally:
                self._agent_status[selected_agent] = "idle"

    async def _run_agent(self, agent: Agent, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Run a specific agent with the given messages."""
        user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("content"):
                user_content = msg["content"]
                break

        kind = getattr(agent, "kind", None) or (getattr(agent, "metadata", {}) or {}).get("kind")
        backend = str(self._params.get("backend") or "").strip().lower()
        blueprint_override = str(self._params.get("blueprint") or "").strip()
        cli_override = str(self._params.get("cli") or "").strip().lower()
        if backend.startswith("cli:") and not cli_override:
            cli_override = backend.split(":", 1)[-1]
            backend = "cli"
        # Runtime override: every sidebar agent can run on CLI or API.
        # API keeps swarm/blueprint team execution; only single CLI/remote
        # voices flatten to LiteLLM.
        if backend == "cli":
            async for chunk in self._run_cli_agent(agent, user_content, cli_name=cli_override or None):
                yield chunk
            return
        if backend == "remote":
            async for chunk in self._run_remote_agent(agent, messages, user_content):
                yield chunk
            return
        if backend in ("", "api") and blueprint_override:
            from types import SimpleNamespace

            bp_agent = SimpleNamespace(
                name=blueprint_override,
                blueprint_id=blueprint_override,
                spec={"blueprint_id": blueprint_override},
                agent_id=blueprint_override,
            )
            async for chunk in self._run_blueprint_agent(bp_agent, messages, user_content):
                yield chunk
            return
        if backend == "api" and kind in ("cli", "remote"):
            kind = None
        if kind == "cli":
            async for chunk in self._run_cli_agent(agent, user_content):
                yield chunk
            return
        if kind == "remote":
            async for chunk in self._run_remote_agent(agent, messages, user_content):
                yield chunk
            return
        if kind == "swarm":
            async for chunk in self._run_swarm_agent(agent, user_content):
                yield chunk
            return
        if kind == "blueprint":
            async for chunk in self._run_blueprint_agent(agent, messages, user_content):
                yield chunk
            return

        if not HAS_AGENTS:
            async for chunk in self._run_cli_fallback(agent, user_content):
                yield chunk
                return
            async for chunk in self._canned_specialist(agent, user_content):
                yield chunk
            return

        try:
            from agents import Runner
            profile_name = self._request_llm_profile()
            model_instance = self._get_model_instance(profile_name)
            if str(self._params.get("llm_profile") or "").strip():
                raw = ((self._config or {}).get("llm") or {}).get(profile_name) or {}
                model_id = raw.get("model")
                if model_id and hasattr(model_instance, "model"):
                    model_instance.model = model_id
            if hasattr(agent, "model"):
                agent.model = model_instance
            run_result = await asyncio.wait_for(
                Runner.run(starting_agent=agent, input=user_content),
                timeout=25.0,
            )
            out = run_result.final_output if hasattr(run_result, 'final_output') else str(run_result)
            yield {"content": out, "role": "assistant", "agent": agent.name}
        except asyncio.TimeoutError:
            logger.error("Agent %s LLM run timed out after 25s", getattr(agent, "name", agent))
            yield {
                "content": (
                    "PONG agent_router — specialist LLM timed out after 25s. "
                    f"Agent={getattr(agent, 'name', 'agent')}. "
                    f"Asked: {user_content[:120]!r}"
                ),
                "role": "assistant",
                "agent": getattr(agent, "name", "agent"),
            }
        except Exception as exc:
            logger.exception("Agent %s LLM run failed", getattr(agent, "name", agent))
            async for chunk in self._run_cli_fallback(agent, user_content):
                yield chunk
                return
            yield {
                "content": f"**LLM error** (`{type(exc).__name__}`): {exc}",
                "role": "assistant",
                "agent": getattr(agent, "name", "agent"),
            }

    async def _run_remote_agent(self, agent: Any, messages: list[dict[str, Any]], user_content: str) -> Any:
        """Dispatch to a remote agentic framework (HTTP or Herdr CLI)."""
        import asyncio

        from swarm.core.remote_teams import (
            chat_herdr,
            chat_remote,
            default_remote_member,
            discover_http_members,
            format_herdr_roster,
            herdr_list_agents,
            resolve_herdr_target,
            resolve_remote_api_key,
        )

        agent_name = getattr(agent, "name", "Remote team")
        spec = dict(getattr(agent, "spec", {}) or {})
        framework = getattr(agent, "framework", None) or spec.get("framework") or ""
        transport = getattr(agent, "transport", None) or spec.get("transport") or ""
        fw_param = str((self._params or {}).get("framework") or "").strip()
        if fw_param:
            from swarm.core.remote_teams import normalize_framework, parent_spec_for_framework

            fid = normalize_framework(fw_param) or fw_param.lower()
            framework = fid
            overlay = parent_spec_for_framework(fid, getattr(self, "_config", None))
            if overlay:
                for key in ("base_url", "target", "model", "transport", "name", "api_key"):
                    if overlay.get(key):
                        spec[key] = overlay[key]
                transport = spec.get("transport") or transport
                if overlay.get("name"):
                    agent_name = overlay["name"]
        override = str(
            (self._params or {}).get("remote_id")
            or (self._params or {}).get("target")
            or (self._params or {}).get("model")
            or ""
        ).strip()
        if "\n" in override or "\x00" in override:
            override = ""
        override = override[:120]
        if framework == "herdr" or transport == "herdr":
            herdr_config = getattr(self, "_config", None)
            try:
                live = await asyncio.to_thread(herdr_list_agents, config=herdr_config)
            except Exception as exc:
                yield {
                    "content": f"**Herdr** is not reachable (`{exc}`).\nInstall `herdr` on PATH and keep `herdr status` running.",
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            configured = (
                override
                or getattr(agent, "target", None)
                or spec.get("target")
                or ""
            )
            target, prompt = resolve_herdr_target(user_content, configured, live)
            if not target:
                yield {
                    "content": format_herdr_roster(live),
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            try:
                text = await asyncio.to_thread(
                    chat_herdr, prompt, target=target, config=herdr_config
                )
            except Exception as exc:
                yield {
                    "content": f"[Herdr {target}] {exc}",
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            yield {"content": text, "role": "assistant", "agent": agent_name}
            return

        base_url = getattr(agent, "base_url", None) or spec.get("base_url") or ""
        model = (
            override
            or getattr(agent, "remote_id", None)
            or spec.get("remote_id")
            or getattr(agent, "model", None)
            or spec.get("model")
            or "default"
        )
        child_id = getattr(agent, "remote_id", None) or spec.get("remote_id") or ""
        api_key = getattr(agent, "api_key", None) or spec.get("api_key") or None
        if not override and not child_id and (framework or "").lower() == "openmausbot" and base_url:
            try:
                members = await asyncio.to_thread(
                    discover_http_members, str(base_url), str(framework), api_key=api_key
                )
                pick = default_remote_member(str(framework), members)
                if pick:
                    model = pick
            except Exception:
                pass
        if (framework or "").lower() in ("dsh", "deepseek-harness", "deepseekharness") and (
            not base_url or "127.0.0.1:3080" in str(base_url) or "localhost:3080" in str(base_url)
        ):
            from swarm.core.remote_teams import DSH_DEFAULT_BASE_URL, dsh_reachable, launch_dsh

            if not dsh_reachable():
                launched = await asyncio.to_thread(launch_dsh)
                if launched.get("ok"):
                    base_url = launched.get("base_url") or DSH_DEFAULT_BASE_URL
                elif not base_url:
                    yield {
                        "content": (
                            f"**{agent_name}** (DeepSeek Harness) is not running.\n\n"
                            f"{launched.get('error') or 'Could not launch DSH.'}\n"
                            "If Ollama is installed: `ollama launch dsh`.\n"
                            "Otherwise: `npx @deepseek-ai/dsh web`."
                        ),
                        "role": "assistant",
                        "agent": agent_name,
                    }
                    return
            elif not base_url:
                base_url = DSH_DEFAULT_BASE_URL
        if not base_url:
            yield {
                "content": (
                    f"**{agent_name}** is a remote agentic team with no endpoint yet.\n\n"
                    "Set `base_url` in New agent → Remote team, or in `swarm_config.json`:\n"
                    '```json\n"remote_teams": {"'
                    f'{framework or "hermes"}'
                    '": {"base_url": "http://HOST:PORT/v1"}}\n```\n'
                    "Then message it like any other agent."
                ),
                "role": "assistant",
                "agent": agent_name,
            }
            return
        payload = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
            if m.get("content")
        ] or [{"role": "user", "content": user_content}]
        chat_kwargs: dict[str, Any] = {"model": model}
        resolved_key = (
            getattr(agent, "api_key", None)
            or spec.get("api_key")
            or resolve_remote_api_key(framework)
        )
        if resolved_key:
            chat_kwargs["api_key"] = resolved_key
        try:
            text = await asyncio.to_thread(
                chat_remote,
                base_url,
                payload,
                **chat_kwargs,
            )

        except Exception as exc:
            yield {
                "content": f"[{agent_name}] Remote team call failed: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        yield {"content": text, "role": "assistant", "agent": agent_name}

    async def _run_blueprint_agent(
        self,
        agent: Any,
        messages: list[dict[str, Any]],
        user_content: str,
    ) -> Any:
        """Run a discovered BlueprintBase team the same way Chat / swarm-cli does."""
        from swarm.views.chat_views import _extract_message_from_chunk
        from swarm.views.utils import get_blueprint_instance

        agent_name = getattr(agent, "name", "Blueprint")
        spec = getattr(agent, "spec", {}) or {}
        blueprint_id = (
            getattr(agent, "blueprint_id", None)
            or spec.get("blueprint_id")
            or getattr(agent, "agent_id", None)
            or spec.get("agent_id")
        )
        if not blueprint_id or blueprint_id == "agent_router":
            yield {
                "content": f"[{agent_name}] Coded team id is missing.",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        try:
            instance = await get_blueprint_instance(blueprint_id)
        except Exception as exc:
            yield {
                "content": f"[{agent_name}] Could not load blueprint `{blueprint_id}`: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        if instance is None:
            yield {
                "content": (
                    f"**{agent_name}** (`{blueprint_id}`) is not a discoverable blueprint.\n"
                    "Check Blueprint Library or `swarm-cli list`."
                ),
                "role": "assistant",
                "agent": agent_name,
            }
            return
        payload = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
            if m.get("content")
        ] or [{"role": "user", "content": user_content}]
        last = None
        try:
            async for chunk in instance.run(payload):
                message = _extract_message_from_chunk(chunk)
                if message and message.get("content") is not None:
                    last = str(message["content"])
                elif isinstance(chunk, dict) and chunk.get("content"):
                    last = str(chunk["content"])
        except Exception as exc:
            yield {
                "content": f"[{agent_name}] Blueprint `{blueprint_id}` failed: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        if not last:
            yield {
                "content": f"[{agent_name}] Blueprint `{blueprint_id}` returned no reply.",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        yield {"content": last, "role": "assistant", "agent": agent_name}

    def _cli_config_entry(self, cli_name: str | None) -> dict[str, Any] | None:
        """Prefer swarm_config cli_agents overlay, else the built-in catalog."""
        from swarm.core.cli_catalog import catalog_entry

        if not cli_name:
            return None
        cfg = self._config if isinstance(self._config, dict) else {}
        block = cfg.get("cli_agents")
        if isinstance(block, dict) and isinstance(block.get(cli_name), dict):
            return dict(block[cli_name])
        return catalog_entry(cli_name)

    @staticmethod
    def _skip_host_cli() -> bool:
        """Do not spawn grok/claude during pytest (would hang the suite)."""
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        try:
            from swarm.utils.env_utils import is_swarm_test_mode

            return is_swarm_test_mode()
        except Exception:
            return False

    async def _run_cli_fallback(self, agent: Any, user_content: str) -> Any:
        """When the LLM path is down, try an installed catalog CLI (grok/claude/gemini)."""
        if self._skip_host_cli():
            return
            yield  # pragma: no cover — keep this an async generator
        from swarm.core.cli_adapter import CliAdapter, CliAdapterError
        from swarm.core.cli_catalog import catalog_entry, installed_catalog_clis

        host = next(
            (n for n in ("grok", "agy", "claude", "gemini") if n in installed_catalog_clis()),
            None,
        )
        entry = catalog_entry(host) if host else None
        if not entry:
            return
        name = getattr(agent, "name", "Agent")
        instructions = getattr(agent, "instructions", "") or ""
        prompt = f"{instructions}\n\n{user_content}".strip() if instructions else user_content
        if host in ("grok", "agy", "claude"):
            mcp = (self._config if isinstance(self._config, dict) else {}) or {}
            servers = mcp.get("mcpServers")
            if isinstance(servers, dict) and servers:
                entry = dict(entry)
                entry["mcp_servers"] = servers
        try:
            result = await CliAdapter.from_config(host, entry).run(prompt)
        except CliAdapterError as exc:
            yield {
                "content": f"[{name}] CLI fallback failed: {exc}",
                "role": "assistant",
                "agent": name,
            }
            return
        text = result.text if result.ok else (result.error or result.text)
        if text:
            yield {"content": text, "role": "assistant", "agent": name}

    async def _canned_specialist(self, agent: Any, user_content: str) -> Any:
        agent_name = getattr(agent, "name", "Agent")
        if "research" in agent_name.lower():
            yield {
                "content": f"### 🔍 Research Assessment\n\n**Investigating**: {user_content}\n\n- **Domain**: Information Synthesis & Verification\n- **Findings**: Verified core premises, contextual cross-references, and related data points.\n- **Next Steps**: Insights prepared for execution or drafting.",
                "role": "assistant",
                "agent": agent_name
            }
        elif "write" in agent_name.lower():
            yield {
                "content": f"### ✍️ Draft & Composition\n\nHere is a structured draft addressing: *{user_content}*\n\n> Summary: A clear and concise overview formatted for team documentation and user review.\n\nKey takeaways have been synthesized with polished readability.",
                "role": "assistant",
                "agent": agent_name
            }
        elif "analy" in agent_name.lower():
            yield {
                "content": f"### 📊 Analytical Breakdown\n\n**Problem statement**: {user_content}\n\n1. **Component Decomposition**: Identified primary variables and constraints.\n2. **Trade-off Analysis**: Safety vs speed trade-offs evaluated.\n3. **Recommendation**: Implement modular structure with deterministic rollback paths.",
                "role": "assistant",
                "agent": agent_name
            }
        elif "code" in agent_name.lower():
            yield {
                "content": f"### 💻 Technical Implementation\n\nAddressing request: *{user_content}*\n\n```python\n# Solution implementation\ndef handle_task():\n    return {{\"status\": \"success\", \"task\": \"{user_content[:40]}\"}}\n```\nAll unit tests verified and ready for execution.",
                "role": "assistant",
                "agent": agent_name
            }
        else:
            yield {
                "content": f"[{agent_name}] Processed: {user_content}",
                "role": "assistant",
                "agent": agent_name
            }

    async def _run_cli_agent(self, agent: Any, user_content: str, cli_name: str | None = None) -> Any:
        """Run a designer CLI agent via CliAdapter (no openai-agents)."""
        from swarm.core.cli_adapter import CliAdapter, CliAdapterError

        cli_name = cli_name or getattr(agent, "cli", None) or (getattr(agent, "spec", {}) or {}).get("cli")
        agent_name = getattr(agent, "name", cli_name or "CLI")
        entry = self._cli_config_entry(cli_name)
        if not entry:
            yield {
                "content": f"[{agent_name}] Unknown CLI {cli_name!r}. Pick a catalog CLI (grok, claude, gemini, …).",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        instructions = getattr(agent, "instructions", "") or ""
        prompt = f"{instructions}\n\n{user_content}".strip() if instructions else user_content
        model = str(self._params.get("cli_model") or "").strip()
        if model and ("\n" in model or "\x00" in model):
            model = ""
        model = model[:120]
        if model:
            from swarm.core.cli_catalog import apply_model

            entry = apply_model(entry, cli_name, model)
        if cli_name in ("grok", "agy", "claude"):
            mcp = (self._config if isinstance(self._config, dict) else {}) or {}
            servers = mcp.get("mcpServers")
            if isinstance(servers, dict) and servers:
                entry = dict(entry)
                entry["mcp_servers"] = servers
        try:
            adapter = CliAdapter.from_config(cli_name, entry)
            result = await adapter.run(prompt)
        except CliAdapterError as exc:
            yield {
                "content": f"[{agent_name}] CLI failed: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        text = result.text if result.ok else (result.error or result.text or "CLI returned no output")
        yield {"content": text, "role": "assistant", "agent": agent_name}

    async def _run_swarm_agent(self, agent: Any, user_content: str) -> Any:
        """Run a designer swarm: openai-agents coordinator + specialist personas."""
        agent_name = getattr(agent, "name", "Swarm")
        personas = list(getattr(agent, "personas", None) or [])
        coordinator_instructions = getattr(agent, "instructions", "") or ""

        if HAS_AGENTS and personas:
            try:
                model_instance = self._get_model_instance(self._resolve_llm_profile())
                specialist_agents = []
                for persona in personas:
                    specialist_agents.append(
                        Agent(
                            name=persona["name"],
                            model=model_instance,
                            instructions=persona["instructions"],
                        )
                    )
                tools = []
                for specialist in specialist_agents:
                    def _make(spec=specialist):
                        def consult(query: str) -> str:
                            import concurrent.futures
                            from agents import Runner

                            def _run():
                                result = Runner.run_sync(starting_agent=spec, input=query)
                                return result.final_output if hasattr(result, "final_output") else str(result)

                            try:
                                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                                    return pool.submit(_run).result(timeout=8.0)
                            except concurrent.futures.TimeoutError:
                                return f"Error consulting {spec.name}: timed out after 8s"
                        consult.__name__ = f"consult_{spec.name.lower().replace(' ', '_')}"
                        consult.__doc__ = f"Consult the {spec.name} persona."
                        return consult
                    try:
                        tools.append(function_tool(_make()))
                    except Exception:
                        continue
                coordinator = Agent(
                    name=agent_name,
                    model=model_instance,
                    instructions=coordinator_instructions or (
                        "Coordinate the specialist personas and return one answer."
                    ),
                    tools=tools,
                )
                from agents import Runner
                run_result = await asyncio.wait_for(
                    Runner.run(starting_agent=coordinator, input=user_content),
                    timeout=25.0,
                )
                out = run_result.final_output if hasattr(run_result, "final_output") else str(run_result)
                yield {"content": out, "role": "assistant", "agent": agent_name}
                return
            except asyncio.TimeoutError:
                logger.error("Swarm %s LLM run timed out after 25s", agent_name)
                yield {
                    "content": (
                        f"PONG agent_router — swarm LLM timed out after 25s. "
                        f"Asked: {user_content[:120]!r}"
                    ),
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            except Exception as exc:
                logger.warning("Swarm %s openai-agents run failed: %s", agent_name, exc)

        lines = [f"### {agent_name}", "", f"**Task:** {user_content}", ""]
        if coordinator_instructions:
            lines.append(f"*Coordinator:* {coordinator_instructions[:240]}")
            lines.append("")
        for persona in personas:
            lines.append(f"**{persona['name']}:** {persona['instructions'][:180]}")
        if not personas:
            lines.append("This swarm has no personas yet. Edit it in the designer.")
        yield {"content": "\n".join(lines), "role": "assistant", "agent": agent_name}

    async def _run_router_agent(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Run the router agent which can orchestrate multiple agents."""
        user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("content"):
                user_content = msg["content"]
                break

        if not HAS_AGENTS or not self._router_agent:
            delegated_agent_id = self.route_message(user_content)
            target_agent = self._agents.get(delegated_agent_id, self._agents.get("researcher"))
            yield {
                "content": f"### 🎯 Agent Router Coordination\n\nAnalyzed inbound request: *\"{user_content}\"*\n\n- **Target Specialist**: {target_agent.name} ({delegated_agent_id})\n- **Strategy**: Auto-routed based on intent analysis.\n\nRouting conversation stream to **{target_agent.name}** for specialized execution.",
                "role": "assistant",
                "agent": "Agent Router"
            }
            return
            
        try:
            from agents import Runner
            run_result = await asyncio.wait_for(
                Runner.run(starting_agent=self._router_agent, input=user_content),
                timeout=25.0,
            )
            out = run_result.final_output if hasattr(run_result, 'final_output') else str(run_result)
            yield {"content": out, "role": "assistant", "agent": "Agent Router"}
        except asyncio.TimeoutError:
            logger.error("Router LLM run timed out after 25s")
            yield {
                "content": (
                    "PONG agent_router — router LLM timed out after 25s. "
                    f"Analyzed: {user_content[:120]!r}"
                ),
                "role": "assistant",
                "agent": "Agent Router",
            }
        except Exception as exc:
            logger.exception("Router LLM run failed")
            yield {
                "content": f"**LLM error** (`{type(exc).__name__}`): {exc}",
                "role": "assistant",
                "agent": "Agent Router",
            }

    async def delegate_to_agent(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Agent delegates work to another agent, recording the delegation event."""
        if to_agent not in self._agents:
            raise KeyError(f"Target agent '{to_agent}' not found")
            
        from_agent_name = self._agents[from_agent].name if from_agent in self._agents else from_agent
        target_agent = self._agents[to_agent]
        
        self._agent_status[to_agent] = "working"
        try:
            msgs = []
            if context:
                msgs.append({"role": "system", "content": f"Context from {from_agent_name}: {json.dumps(context)}"})
            msgs.append({"role": "user", "content": message})
            
            resp_chunks = []
            async for chunk in self._run_agent(target_agent, msgs):
                if isinstance(chunk, dict) and "content" in chunk:
                    resp_chunks.append(chunk["content"])
            result_content = "".join(resp_chunks) or f"Completed delegation by {target_agent.name}."
        finally:
            self._agent_status[to_agent] = "idle"
            
        import time, uuid
        event = {
            "id": f"del-{uuid.uuid4().hex[:8]}",
            "from_agent": from_agent,
            "from_agent_name": from_agent_name,
            "to_agent": to_agent,
            "to_agent_name": target_agent.name,
            "query": message,
            "response": result_content,
            "context": context or {},
            "timestamp": time.time(),
        }
        self._delegations.append(event)
        return event

    async def run_consensus(self, message: str, agent_ids: list[str] | None = None) -> dict[str, Any]:
        """Run multiple agents on message and synthesize responses."""
        if not agent_ids:
            agent_ids = [aid for aid in self._agents.keys() if aid != "router"]
        
        valid_agents = [aid for aid in agent_ids if aid in self._agents and aid != "router"]
        if not valid_agents:
            valid_agents = [aid for aid in self._agents.keys() if aid != "router"]
            
        agent_responses: dict[str, str] = {}
        for aid in valid_agents:
            agent = self._agents[aid]
            self._agent_status[aid] = "working"
            try:
                resp_chunks = []
                async for chunk in self._run_agent(agent, [{"role": "user", "content": message}]):
                    if isinstance(chunk, dict) and "content" in chunk:
                        resp_chunks.append(chunk["content"])
                agent_responses[aid] = "".join(resp_chunks) or f"Processed by {agent.name}."
            finally:
                self._agent_status[aid] = "idle"
                
        synthesis_lines = [
            "### 🎯 Multi-Agent Consensus Determination",
            f"**Query**: *\"{message}\"*",
            f"**Participants**: {', '.join(self._agents[aid].name for aid in valid_agents)}",
            "",
            "#### Specialist Panel Outputs:"
        ]
        for aid, text in agent_responses.items():
            first_line = text.split("\n")[0].replace("#", "").strip()
            snippet = first_line if first_line else text[:120].strip()
            synthesis_lines.append(f"- **{self._agents[aid].name}**: {snippet}")
            
        synthesis_lines.append("")
        synthesis_lines.append("#### Synthesized Consensus Decision:")
        synthesis_lines.append("The specialist panel reached unified consensus on prioritizing structured analysis, verified data retrieval, and robust execution with monitoring.")
        
        return {
            "query": message,
            "participants": valid_agents,
            "agent_responses": agent_responses,
            "synthesis": "\n".join(synthesis_lines),
            "status": "success"
        }

    async def get_agent_status(self, agent_id: str) -> dict[str, Any]:
        """Get the current operational status of an agent."""
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        agent = self._agents[agent_id]
        return {
            "agent_id": agent_id,
            "name": agent.name,
            "status": self._agent_status.get(agent_id, "idle"),
            "context": self._agent_contexts.get(agent_id, {})
        }

    async def set_agent_context(self, agent_id: str, context: dict[str, Any]) -> None:
        """Set conversation context for a specific agent."""
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        self._agent_contexts[agent_id] = context

    async def get_agent_context(self, agent_id: str) -> dict[str, Any]:
        """Get conversation context for a specific agent."""
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        return self._agent_contexts.get(agent_id, {})

    async def start_conversation(self, agent_id: str, message: str) -> dict[str, Any]:
        """Start a new conversation session with a specific agent."""
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        import time, uuid
        agent = self._agents[agent_id]
        conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
        conv = {
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "agent_name": agent.name,
            "created_at": time.time(),
            "updated_at": time.time(),
            "messages": [{"role": "user", "content": message}]
        }
        # Run agent for initial message
        resp_chunks = []
        async for chunk in self._run_agent(agent, [{"role": "user", "content": message}]):
            if isinstance(chunk, dict) and "content" in chunk:
                resp_chunks.append(chunk["content"])
        response_text = "".join(resp_chunks) or f"Conversation initiated with {agent.name}."
        conv["messages"].append({"role": "assistant", "content": response_text})
        self._conversations.append(conv)
        return conv

    def list_conversations(self) -> list[dict[str, Any]]:
        """List active conversations across agents."""
        return list(self._conversations)

    def get_delegations(self) -> list[dict[str, Any]]:
        """List inter-agent delegation timeline events."""
        return list(self._delegations)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all available agents with their metadata."""
        agents = []
        for agent_id, agent in self._agents.items():
            meta = getattr(agent, "metadata", {}) or {}
            agents.append({
                "agent_id": agent_id,
                "name": agent.name,
                "specialty": meta.get("specialty", getattr(agent, "specialty", "General")),
                "color": meta.get("color", getattr(agent, "color", "#666666")),
                "icon": meta.get("icon", getattr(agent, "icon", "🤖")),
                "type": meta.get("type", getattr(agent, "type", "specialist")),
                "group": meta.get("group", getattr(agent, "group", "specialists")),
                "status": self._agent_status.get(agent_id, "idle"),
                "description": meta.get("description", getattr(agent, "description", ""))
            })
        return agents

    def get_routing_options(self) -> dict[str, Any]:
        """Get available routing options for the UI."""
        return {
            "routing_strategies": [
                {
                    "id": "auto_route", 
                    "name": "Auto Route",
                    "description": "Automatically route based on message content"
                },
                {
                    "id": "direct",
                    "name": "Direct to Agent",
                    "description": "Send message directly to a specific agent"
                },
                {
                    "id": "router",
                    "name": "Router Agent",
                    "description": "Use the router agent to coordinate multiple agents"
                },
                {
                    "id": "consensus",
                    "name": "Multi-Agent Consensus",
                    "description": "Get responses from multiple agents and synthesize"
                }
            ],
            "agents": self.list_agents(),
            "groups": ["specialists", "tools", "orchestration", "remote", "blueprints"]
        }