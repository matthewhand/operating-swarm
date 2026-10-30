# --- REMOVE noisy debug/framework prints unless SWARM_DEBUG=1 ---
import os


def _should_debug():
    # Standardize debug detection: SWARM_DEBUG, SWARM_LOGLEVEL, LOGLEVEL, LOG_LEVEL, DEBUG
    import os
    # Highest precedence: explicit SWARM_DEBUG=1 or true
    debug_env = os.environ.get("SWARM_DEBUG")
    if debug_env is not None:
        return debug_env.lower() in ("1", "true", "yes", "on")
    # Next: SWARM_LOGLEVEL or LOGLEVEL or LOG_LEVEL
    for var in ("SWARM_LOGLEVEL", "LOGLEVEL", "LOG_LEVEL"):
        val = os.environ.get(var)
        if val and val.upper() == "DEBUG":
            return True
    # Next: DEBUG=1 or true
    debug_std = os.environ.get("DEBUG")
    if debug_std is not None:
        return debug_std.lower() in ("1", "true", "yes", "on")
    return False

def _debug_print(*args, **kwargs):
    if _should_debug():
        print(*args, **kwargs)

def _framework_print(*args, **kwargs):
    if _should_debug():
        print(*args, **kwargs)

# --- Content for src/swarm/extensions/blueprint/blueprint_base.py ---
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from agents import set_default_openai_client, set_tracing_disabled
from django.apps import apps  # Import Django apps registry
from openai import AsyncOpenAI

# Disable the openai-agents SDK's tracing exporter by default. It uploads run
# traces to OpenAI's platform (api.openai.com/v1/traces/ingest) using the default
# OpenAI key — which on a CLI-fusion / non-OpenAI gateway is absent or invalid,
# producing a 401 on every agent run AND leaking run data off-box. Opt back in
# with SWARM_ENABLE_AGENT_TRACING=1 (and a valid OPENAI_API_KEY).
if os.environ.get("SWARM_ENABLE_AGENT_TRACING", "").lower() not in ("1", "true", "yes"):
    set_tracing_disabled(True)

# #737: the SDK defaults bare Agent(...) runs to the /responses API — an
# endpoint LiteLLM, Ollama, and most OpenAI-compatible gateways do not
# implement (they serve /v1/chat/completions). Pin the default API to chat
# completions framework-wide; explicit OpenAIResponsesModel users still opt
# back in per-model. SWARM_ENABLE_RESPONSES_API=1 restores SDK default.
try:
    from agents import set_default_openai_api

    if os.environ.get("SWARM_ENABLE_RESPONSES_API", "").lower() not in ("1", "true", "yes"):
        set_default_openai_api("chat_completions")
except Exception:  # pragma: no cover - older SDK without the setter
    pass

# Keep the function import
from swarm.core.approval_mixin import ApprovalMixin
from swarm.core.config_loader import (
    _substitute_env_vars,
    get_resolved_llm_profile,
    list_available_llm_profiles,
)
from swarm.core.config_resolver import ConfigResolver
from swarm.core.memory_mixin import MemoryMixin

__all__ = [
    "BlueprintBase",
    "ApprovalMixin",
    "MemoryMixin",
    "ConfigResolver",
    "Spinner",
    "apply_agent_model_defaults",
    "configure_openai_client_from_env",
]

logger = logging.getLogger(__name__)


def _resolve_framework_chat_model() -> str | None:
    """#737: best-effort model id for bare openai-agents Agents.

    Order: LITELLM_MODEL / DEFAULT_LLM env, then the settings chat route
    (default profile, honouring override_per_task) via llm_task_routing.
    Returns None when nothing is configured — the SDK keeps its own default.
    """
    env_model = os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM")
    if env_model:
        return env_model.strip()
    try:
        from swarm.core.llm_task_routing import (
            load_swarm_config,
            model_id_for_profile,
            resolve_chat_model,
        )

        config = load_swarm_config()
        route = resolve_chat_model(config)
        model = model_id_for_profile(route.profile, config)
        return model or None
    except Exception:
        return None


def apply_agent_model_defaults(agent) -> object:
    """#737: give a bare ``Agent`` the framework's model when it lacks one.

    Support-generated blueprints and persona_swarm construct ``Agent(...)``
    without ``model=``; the SDK then silently falls back to its hardcoded
    ``gpt-4o`` — rejected by non-OpenAI providers. Call this on the agent
    before ``Runner.run`` to pin the resolved chat model (env override
    first). Agents with an explicit model are untouched.
    """
    try:
        if getattr(agent, "model", None):
            return agent
        model = _resolve_framework_chat_model()
        if model:
            agent.model = model
    except Exception:
        logger.debug("apply_agent_model_defaults skipped", exc_info=True)
    return agent
# --- PATCH: Suppress OpenAI tracing/telemetry errors if using LiteLLM/custom endpoint ---
import logging

from rich.console import Console

if os.environ.get("LITELLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL"):
    # Silence openai.agents tracing/telemetry errors
    logging.getLogger("openai.agents").setLevel(logging.CRITICAL)
    try:
        import openai.agents.tracing
        openai.agents.tracing.TracingClient = lambda *a, **kw: None
    except Exception:
        pass

# --- Spinner/Status Message Enhancements ---
# To be used by all blueprints for consistent UX
import itertools
import sys
import threading
import time


class Spinner:
    def __init__(self, message_sequence=None, interval=0.3, slow_threshold=10):
        self.message_sequence = message_sequence or ['Generating.', 'Generating..', 'Generating...', 'Running...']
        self.interval = interval
        self.slow_threshold = slow_threshold  # seconds before 'Taking longer than expected'
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = None

    def start(self):
        self._stop_event.clear()
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin)
        self._thread.start()

    def _spin(self):
        for msg in itertools.cycle(self.message_sequence):
            if self._stop_event.is_set():
                break
            elapsed = time.time() - self._start_time
            if elapsed > self.slow_threshold:
                sys.stdout.write('\rGenerating... Taking longer than expected   ')
            else:
                sys.stdout.write(f'\r{msg}   ')
            sys.stdout.flush()
            time.sleep(self.interval)
        sys.stdout.write('\r')
        sys.stdout.flush()

    def stop(self, final_message=''):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        if final_message:
            sys.stdout.write(f'\r{final_message}\n')
            sys.stdout.flush()

# Usage Example (to be called in blueprints):
# spinner = Spinner()
# spinner.start()
# ... do work ...
# spinner.stop('Done!')

def configure_openai_client_from_env():
    """
    Framework-level function: Always instantiate and set the default OpenAI client.
    Prints out the config being used for debug.

    Uses LiteLLM proxy when ``LITELLM_BASE_URL`` / ``OPENAI_BASE_URL`` is set
    (required for load balancing + accounting).
    """
    from swarm.utils.env_utils import get_llm_base_url, openai_client_kwargs

    kwargs = openai_client_kwargs()
    base_url = kwargs.get("base_url") or get_llm_base_url()
    api_key = kwargs.get("api_key")
    if _should_debug():
        _debug_print(
            f"[DEBUG] Using OpenAI client config: base_url={base_url}, api_key={'set' if api_key else 'NOT SET'}"
        )
    if base_url and api_key:
        client = AsyncOpenAI(**kwargs)
        set_default_openai_client(client)
        _framework_print(
            f"[FRAMEWORK] Set default OpenAI client: base_url={base_url}, api_key={'set' if api_key else 'NOT SET'}"
        )
    else:
        _framework_print(
            "[FRAMEWORK] WARNING: base_url or api_key missing, OpenAI client not set! "
            "Set OPENAI_BASE_URL/LITELLM_BASE_URL to the LiteLLM proxy."
        )

configure_openai_client_from_env()

class BlueprintBase(ApprovalMixin, MemoryMixin, ConfigResolver, ABC):
    """
    Abstract base class for all Swarm blueprints.

    Defines the core interface for blueprint initialization and execution.
    Composed of ApprovalMixin, MemoryMixin, and ConfigResolver.
    """
    enable_terminal_commands: bool = False  # By default, terminal command execution is disabled
    approval_required: bool = False
    console = Console()
    session_logger = None
    metadata: dict[str, Any] = {
        "title": "Blueprint",
        "description": "",
        "abbreviation": None,
    }

    @property
    def abbreviation(self) -> str | None:
        """Short identifier or abbreviation for this blueprint, if declared in metadata."""
        md = getattr(self, "metadata", None)
        if isinstance(md, dict):
            return md.get("abbreviation")
        return getattr(self, "_abbreviation", None)

    def __init__(self, blueprint_id: str, config=None, config_path=None, **kwargs):
        self.blueprint_id = blueprint_id
        self.config_path = config_path
        self._config = config if config is not None else None
        self._llm_profile_name = None
        self._llm_profile_data = None
        self._markdown_output = None
        self._load_configuration()  # Ensure config is loaded during init
        # --- Optional memory integration (strict no-op unless configured) ---
        self._memory_backend = None
        self._memory_settings = {}
        self._init_memory_backend()
        # Add any additional initialization logic here

    def display_splash_screen(self, animated: bool = False):
        """Default splash screen. Subclasses can override for custom CLI/API branding."""
        console = Console()
        console.print(f"[bold cyan]Welcome to {self.__class__.__name__}![/]", style="bold")



    @property
    def slash_commands(self):
        from swarm.core.slash_commands import slash_registry
        return slash_registry

    def get_navbar_items(self=None) -> list[dict]:
        """Returns metadata for navbar items contributed by this blueprint."""
        return []

    @property
    def splash(self) -> str:
        """
        Plain text splash/description for API, docs, etc.
        """
        title = self.metadata.get('title', 'Blueprint')
        desc = self.metadata.get('description', '')
        return f"{title}: {desc}"

    def get_cli_splash(self, color='cyan', emoji='🤖') -> str:
        """
        CLI splash with ANSI/emoji, only for terminal output.
        """
        from swarm.core.output_utils import ansi_box
        # Map legacy color names to the ANSI codes used by core ansi_box.
        color_codes = {
            'cyan': '96', 'green': '92', 'yellow': '93', 'magenta': '95',
            'blue': '94', 'red': '91', 'white': '97', 'grey': '90',
        }
        title = self.metadata.get('title', 'Blueprint')
        desc = self.metadata.get('description', '')
        return ansi_box(title, desc, color=color_codes.get(color, '96'), emoji=emoji)

    def make_agent(self, name, instructions, tools, mcp_servers=None, memory_type=None, memory_config=None, inference_profile=None, role=None, **kwargs):
        """Factory for creating an Agent with the correct model instance from framework config.

        ``inference_profile`` (optional) is a *suggestion* of the kind of inference
        wanted (e.g. ``{"intelligence": 1.0}`` or ``{"speed": 0.9, "cost": 0.9}``).
        It is scored against the tagged profiles in swarm_config.json's ``llm``
        section and only takes effect when no explicit profile name or env override
        (LITELLM_MODEL/DEFAULT_LLM) is set. Equivalent to declaring
        ``metadata['inference_profile']`` on the blueprint.
        """
        from agents import Agent  # Ensure Agent is always in scope
        if inference_profile is not None:
            self._inference_profile = inference_profile
            # Bust any cached resolution so the suggestion is honored.
            if hasattr(self, '_resolved_llm_profile'):
                del self._resolved_llm_profile
        model_instance = self._get_model_instance(self._resolve_llm_profile())

        # Resolve memory settings
        memory_type = memory_type or self.config.get("settings", {}).get("default_memory_type")
        memory_config = memory_config or self.config.get("settings", {}).get("default_memory_config")
        memory_instance = self._get_memory_instance(memory_type, memory_config)

        from swarm.core.agent_roles import attach_role, normalize_agent_role

        role = normalize_agent_role(kwargs.pop("role", None) or role)
        mailbox_ctx = getattr(self, "_mailbox_context", None)
        # REQ-79: unused tools must not crash Agent() — None becomes [].
        tools = list(tools or [])
        if mailbox_ctx is not None:
            extra = mailbox_ctx.tool_objects()
            tools = tools + extra
        lifecycle_ctx = getattr(self, "_lifecycle_context", None)
        if lifecycle_ctx is not None:
            extra = lifecycle_ctx.tool_objects()
            tools = tools + extra
        topology_ctx = getattr(self, "_topology_context", None)
        if topology_ctx is not None:
            extra = topology_ctx.tool_objects()
            tools = tools + extra

        # Optional sandbox harness integration: attach sandbox execution tools
        # if requested (REQ-860 / REQ-863: Settings provider drives the backend;
        # #719: the per-agent ``sandbox`` param overrides settings for this
        # agent alone — opt-in when settings are none, opt-out when enabled).
        sandbox_opt = kwargs.pop("sandbox", None)
        params_for_sandbox = dict(getattr(self, "_params", None) or {})
        if sandbox_opt is None:
            from swarm.core.sandbox.opt_in import effective_sandbox_config

            effective = effective_sandbox_config(self._config, params_for_sandbox)
            if effective is not None:
                sandbox_opt = dict(effective)
        if sandbox_opt:
            try:
                from swarm.core.sandbox import SandboxManager
                if isinstance(sandbox_opt, dict):
                    sb_mgr = SandboxManager.from_config(sandbox_opt)
                elif isinstance(sandbox_opt, SandboxManager):
                    sb_mgr = sandbox_opt
                else:
                    # Legacy boolean: jailed local backend, not unrestricted host.
                    sb_mgr = SandboxManager.from_config({"backend_type": "local"})
                if sb_mgr.tools_enabled():
                    tools = tools + sb_mgr.as_function_tools()
            except Exception as e:
                logger.warning("Failed to attach sandbox tools to agent '%s': %s", name, e)

        if isinstance(instructions, str):
            from swarm.core.operator_profile import instructions_with_about_me

            instructions = instructions_with_about_me(instructions)

        agent = Agent(
            name=name,
            model=model_instance,
            instructions=instructions,
            tools=tools,
            mcp_servers=mcp_servers or [],
            **kwargs
        )
        attach_role(agent, role)

        # Attach memory if any
        if memory_instance:
            # We add it as a custom attribute if the SDK agent doesn't have it
            agent.memory = memory_instance

        # #1684: the turn-phase `tool_status` producer. Attached HERE, at the one
        # factory every seat converges on, because the `ApiKindBase.run`
        # chokepoint is bypassed by the three API seats that shadow `run` —
        # including ChatbotBlueprint, which is what `api_agent` (the default
        # chat seat) resolves to. A frame the SPA never receives is a badge that
        # never appears, so the producer has to sit on the path that actually
        # runs; see `kind_bases.ApiKindBase.__init_subclass__`.
        #
        # `attach_turn_phase_hooks` is idempotent, so this cannot stack a second
        # `ToolPhaseHooks` on an agent that already carries one, and it raises
        # nothing: a status frame must never be able to fail agent creation.
        try:
            from swarm.core.turn_phase import attach_turn_phase_hooks

            attach_turn_phase_hooks(agent)
        except Exception:
            logger.debug("turn-phase hook attach skipped", exc_info=True)

        return agent

    def start_session_logger(self, blueprint_name: str, global_instructions: str = None, project_instructions: str = None):
        from swarm.core.session_logger import SessionLogger
        self.session_logger = SessionLogger(blueprint_name=blueprint_name)
        self.session_logger.log_instructions(global_instructions, project_instructions)

    def log_message(self, role: str, content: str):
        if self.session_logger:
            self.session_logger.log_message(role, content)

    def log_tool_call(self, tool_name: str, result: str):
        if self.session_logger:
            self.session_logger.log_tool_call(tool_name, result)

    def close_session_logger(self):
        if self.session_logger:
            self.session_logger.close()
            self.session_logger = None

    def print_help(self):
        """
        Print CLI usage/help for this blueprint. Subclasses can override for custom help.
        """
        blueprint_name = getattr(self, 'blueprint_id', self.__class__.__name__)
        print(f"\nUsage: {blueprint_name} [options] <prompt>\n")
        print("Options:")
        print("  -m, --model <model>         Model to use for completions")
        print("  -q, --quiet                 Non-interactive mode (only prints final output)")
        print("  -o, --output <file>         Output file")
        print("  --project-doc <file>        Include a markdown file as context")
        print("  --full-context              Load all project files as context")
        print("  --approval <policy>         Set approval policy for agent actions (suggest, auto-edit, full-auto)")
        print("  --version                   Show version and exit")
        print("  -h, --help                  Show this help message and exit\n")
        print("Examples:")
        print(f"  {blueprint_name} \"Refactor all utils into a single module.\"")
        print(f"  {blueprint_name} --full-context \"Analyze and fix all TODOs across the codebase.\"")
        print(f"  {blueprint_name} --approval full-auto \"Upgrade all dependencies, update changelog, and implement pending TODOs.\"")
        print(f"  {blueprint_name} --full-context --approval suggest \"Review all TODO comments and provide implementation suggestions.\"")
        print(f"  {blueprint_name} \"Generate documentation for functions with TODO comments.\"")

    @abstractmethod
    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """
        The main execution method for the blueprint.
        """
        import os
        import pprint
        logger.debug("ENVIRONMENT DUMP BEFORE MODEL CALL:")
        pprint.pprint(dict(os.environ))
        raise NotImplementedError("Subclasses must implement the 'run' method.")
        yield {}

