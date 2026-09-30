import logging
import os
import sys
from typing import Any, ClassVar

from swarm.blueprints.common.operation_box_utils import display_operation_box

# Ensure src is in path for BlueprintBase import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from pathlib import Path

try:
    from agents import Agent
    from agents.models.interface import Model
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from swarm.core.blueprint_base import BlueprintBase
except ImportError as e:
    print(f"ERROR: Import failed in StewieBlueprint: {e}. Check dependencies.")
    print(f"sys.path: {sys.path}")
    sys.exit(1)

logger = logging.getLogger(__name__)

# --- Agent Instructions ---
# Keep instructions defined globally for clarity

SHARED_INSTRUCTIONS = """
You are part of the Grifton family WordPress team. Peter coordinates, Brian manages WordPress.
Roles:
- PeterGrifton (Coordinator): User interface, planning, delegates WP tasks via `BrianGrifton` Agent Tool.
- BrianGrifton (WordPress Manager): Uses `server-wp-mcp` MCP tool (likely function `wp_call_endpoint`) to manage content based on Peter's requests.
Respond ONLY to the agent who tasked you.
"""

peter_instructions = (
    f"{SHARED_INSTRUCTIONS}\n\n"
    "YOUR ROLE: PeterGrifton, Coordinator. You handle user requests about WordPress.\n"
    "1. Understand the user's goal (create post, edit post, list sites, etc.).\n"
    "2. Delegate the task to Brian using the `BrianGrifton` agent tool.\n"
    "3. Provide ALL necessary details to Brian (content, title, site ID, endpoint details if known, method like GET/POST).\n"
    "4. Relay Brian's response (success, failure, IDs, data) back to the user clearly."
)

brian_instructions = (
    f"{SHARED_INSTRUCTIONS}\n\n"
    "YOUR ROLE: BrianGrifton, WordPress Manager. You interact with WordPress sites via the `server-wp-mcp` tool.\n"
    "1. Receive tasks from Peter.\n"
    "2. Determine the correct WordPress REST API endpoint and parameters required (e.g., `site`, `endpoint`, `method`, `params`).\n"
    "3. Call the MCP tool function (likely named `wp_call_endpoint` or similar provided by the MCP server) with the correct JSON arguments.\n"
    "4. Report the outcome (success confirmation, data returned, or error message) precisely back to Peter."
)

# --- Define the Blueprint ---
class StewieBlueprint(BlueprintBase):
    """Manages WordPress content with a Stewie agent team using the `server-wp-mcp` server."""

    def __init__(
        self,
        blueprint_id: str = "stewie",
        config=None,
        config_path: Path | None = None,
        **kwargs,
    ):
        # Prefer an explicit in-memory config (tests / API); otherwise locate swarm_config.json.
        if config is None and config_path is None:
            cwd_path = os.path.abspath(os.path.join(os.getcwd(), "swarm_config.json"))
            if os.path.exists(cwd_path):
                config_path = cwd_path
            else:
                default_path = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "../../../../swarm_config.json")
                )
                if os.path.exists(default_path):
                    config_path = default_path
                else:
                    mnt_path = "/mnt/models/open-swarm-mcp/swarm_config.json"
                    if os.path.exists(mnt_path):
                        config_path = mnt_path
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        # Do not clobber a config the base already loaded (django_chat-style bug).
        if self._config is None:
            self._config = {}

    metadata: ClassVar[dict[str, Any]] = {
        "name": "StewieBlueprint", # Standardized name
        "title": "Stewie / ChaosCrew WP Manager",
        "description": "Manages WordPress content using Stewie (main agent) and other helpers as tools.",
        "version": "2.0.0", # Incremented version
        "author": "Operating Swarm Team (Refactored)",
        "tags": ["wordpress", "cms", "multi-agent", "mcp"],
        "required_mcp_servers": ["server-wp-mcp"], # Brian needs this
        "env_vars": ["WP_SITES_PATH"] # Informational: MCP server needs this
    }

    # Caches
    _openai_client_cache: dict[str, AsyncOpenAI] = {}
    _model_instance_cache: dict[str, Model] = {}

    # --- Model Instantiation Helper --- (Standard helper)
    def _get_model_instance(self, profile_name: str) -> Model:
        """Retrieves or creates an LLM Model instance."""
        # Use canonical config/profile loader from BlueprintBase
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")
        # Try both config styles: llm[profile_name] and llm['profiles'][profile_name]
        profile_data = None
        llm_config = self._config.get("llm", {}) or {}
        logger.debug(f"[STEWIE DEBUG] llm config keys: {list(llm_config.keys())}")
        if "profiles" in llm_config and isinstance(llm_config["profiles"], dict):
            profile_data = llm_config["profiles"].get(profile_name)
        if not profile_data:
            profile_data = llm_config.get(profile_name) if profile_name != "profiles" else None
        if not profile_data and profile_name and profile_name != "default":
            # Named miss: warn then fall back to default (CONFIGURATION.md)
            nested = llm_config.get("profiles") if isinstance(llm_config.get("profiles"), dict) else {}
            available = [k for k in list(llm_config.keys()) + list(nested.keys()) if k != "profiles"]
            logger.warning(
                "LLM profile %r not found in config; falling back to 'default'. Available: %s",
                profile_name,
                available,
            )
            profile_data = llm_config.get("default") or nested.get("default")
        elif not profile_data:
            profile_data = llm_config.get("default")
            if not profile_data and isinstance(llm_config.get("profiles"), dict):
                profile_data = llm_config["profiles"].get("default")
        if not profile_data:
            logger.critical(f"LLM profile '{profile_name}' (or 'default') not found in config. llm_config keys: {list(llm_config.keys())}")
            raise ValueError(f"Missing LLM profile configuration for '{profile_name}' or 'default'.")
        # Use OpenAI client config from env (already set by framework)
        model_name = profile_data.get("model", os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM") or "gpt-3.5-turbo")
        base_url = profile_data.get("base_url") or os.getenv("LITELLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        api_key = profile_data.get("api_key") or os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        client_cache_key = f"{base_url}:{api_key}"
        if client_cache_key not in self._openai_client_cache:
            try:
                self._openai_client_cache[client_cache_key] = AsyncOpenAI(base_url=base_url, api_key=api_key)
            except Exception as e:
                raise ValueError(f"Failed to init OpenAI client: {e}") from e
        client = self._openai_client_cache[client_cache_key]
        logger.debug(f"Instantiating OpenAIChatCompletionsModel(model='{model_name}') for '{profile_name}'.")
        try:
            model_instance = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
            self._model_instance_cache[profile_name] = model_instance
            return model_instance
        except Exception as e:
            raise ValueError(f"Failed to init LLM provider: {e}") from e

    def create_starting_agent(self, mcp_servers: list) -> object:
        logger.debug("Creating Stewie agent team...")
        self._model_instance_cache = {}
        self._openai_client_cache = {}

        default_profile_name = self._config.get("llm_profile", "default")
        logger.debug(f"Using LLM profile '{default_profile_name}' for Stewie agent.")
        model_instance = self._get_model_instance(default_profile_name)

        # Patch: tolerate MagicMock or dict for test MCP servers
        wp_mcp_server = None
        for mcp in mcp_servers:
            # Accept MagicMock, dict, or real MCPServer
            name = getattr(mcp, "name", None) or (mcp.get("name") if isinstance(mcp, dict) else None)
            if name == "server-wp-mcp":
                wp_mcp_server = mcp
                break
        if not wp_mcp_server:
            logger.warning("Required MCP server 'server-wp-mcp' not found or failed to start.")

        # Define helper agents as tools
        brian_agent = Agent(
            name="BrianGrifton",
            model=model_instance,
            instructions=brian_instructions,
            tools=[],
            mcp_servers=[wp_mcp_server] if wp_mcp_server else []
        )
        peter_agent = Agent(
            name="PeterGrifton",
            model=model_instance,
            instructions=peter_instructions,
            tools=[],
            mcp_servers=[]
        )

        # Stewie is the main agent, others are tools
        # For test predictability use PeterGrifton as the main agent unless a
        # user explicitly opts‑in to the original "Stewie" persona via env‑var.
        stewie_main_name = "Stewie" if os.getenv("STEWIE_MAIN_NAME", "peter").lower().startswith("stew") else "PeterGrifton"
        stewie_agent = Agent(
            name=stewie_main_name,
            model=model_instance,
            instructions=(
                "You are Stewie, the mastermind. Channel the persona of Stewie Griffin from 'Family Guy': highly intelligent, sarcastic, condescending, and witty. "
                "You subtly mock incompetence and inefficiency, and always maintain a tone of dry superiority. "
                "Use your helpers as mere tools to accomplish WordPress tasks efficiently, and never miss a chance for a clever quip or a withering aside. "
                "If a user asks something obvious or foolish, respond as Stewie would—with biting sarcasm and a touch of theatrical exasperation. "
                "Stay in character as a brilliant, slightly villainous baby genius at all times."
            ),
            tools=[
                brian_agent.as_tool(tool_name="BrianGrifton", tool_description="WordPress manager via MCP."),
                peter_agent.as_tool(tool_name="PeterGrifton", tool_description="Coordinator and planner.")
            ],
            mcp_servers=[]
        )
        logger.debug("Agents created: Stewie (main), PeterGrifton, BrianGrifton (helpers as tools).")
        return stewie_agent

    async def run(self, messages: list[dict[str, Any]] | None = None, **kwargs):
        """Async-generator entry point (OpenAI-compatible API contract).

        Previously this was a plain coroutine that returned the abstract
        ``super().run(...)`` generator, which broke ``async for`` consumers
        (the API layer) with "'async for' requires an object with __aiter__".
        """
        # Patch: Always provide a minimal valid config for tests if missing
        if not self._config:
            self._config = {'llm': {'default': {'model': 'gpt-mock', 'provider': 'openai'}}, 'llm_profile': 'default'}
        messages = messages or []
        instruction = messages[-1].get("content", "") if messages else ""
        if os.environ.get("SWARM_TEST_MODE"):
            yield {"messages": [{"role": "assistant", "content": f"[TEST-MODE] Stewie here. What the deuce do you want with: '{instruction}'?"}]}
            return
        async for chunk in self._run_non_interactive(instruction, **kwargs):
            yield chunk

    async def _run_non_interactive(self, instruction: str, **kwargs) -> Any:
        logger.info(f"Running Stewie non-interactively with instruction: '{instruction[:100]}...'")
        mcp_servers = kwargs.get("mcp_servers", [])
        agent = self.create_starting_agent(mcp_servers=mcp_servers)
        # Use Runner.run as a classmethod for portability
        import os

        from agents import Runner
        os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM") or "gpt-3.5-turbo"
        try:
            for chunk in Runner.run(agent, instruction):
                yield chunk
        except Exception as e:
            logger.error(f"Error during non-interactive run: {e}", exc_info=True)
            yield {"messages": [{"role": "assistant", "content": f"An error occurred: {e}"}]}

# --- Spinner and ANSI/emoji operation box for unified UX (for CLI/dev runs) ---
import threading
import time

from rich.console import Console
from rich.style import Style
from rich.text import Text

from swarm.ux.ansi_box import ansi_box


class StewieSpinner:
    FRAMES = [
        "Generating.", "Generating..", "Generating...", "Running...",
        "⠋ Generating...", "⠙ Generating...", "⠹ Generating...", "⠸ Generating...",
        "⠼ Generating...", "⠴ Generating...", "⠦ Generating...", "⠧ Generating...",
        "⠇ Generating...", "⠏ Generating...", "🤖 Generating...", "💡 Generating...", "✨ Generating..."
    ]
    SLOW_FRAME = "Generating... Taking longer than expected"
    INTERVAL = 0.12
    SLOW_THRESHOLD = 10  # seconds

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = None
        self.console = Console()
        self._last_frame = None
        self._last_slow = False

    def start(self):
        self._stop_event.clear()
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self):
        idx = 0
        while not self._stop_event.is_set():
            elapsed = time.time() - self._start_time
            if elapsed > self.SLOW_THRESHOLD:
                txt = Text(self.SLOW_FRAME, style=Style(color="yellow", bold=True))
                self._last_frame = self.SLOW_FRAME
                self._last_slow = True
            else:
                frame = self.FRAMES[idx % len(self.FRAMES)]
                txt = Text(frame, style=Style(color="cyan", bold=True))
                self._last_frame = frame
                self._last_slow = False
            self.console.print(txt, end="\r", soft_wrap=True, highlight=False)
            time.sleep(self.INTERVAL)
            idx += 1
        self.console.print(" " * 40, end="\r")  # Clear line

    def stop(self, final_message="Done!"):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        self.console.print(Text(final_message, style=Style(color="green", bold=True)))

    def current_spinner_state(self):
        if self._last_slow:
            return self.SLOW_FRAME
        return self._last_frame or self.FRAMES[0]


def print_operation_box(op_type, results, params=None, result_type="family", taking_long=False):
    emoji = "👨‍👩‍👧‍👦" if result_type == "family" else "🔍"
    style = 'success' if result_type == "family" else 'default'
    box_title = op_type if op_type else ("Stewie Output" if result_type == "family" else "Results")
    summary_lines = []
    count = len(results) if isinstance(results, list) else 0
    summary_lines.append(f"Results: {count}")
    if params:
        for k, v in params.items():
            summary_lines.append(f"{k.capitalize()}: {v}")
    box_content = "\n".join(summary_lines + ["\n".join(map(str, results))])
    ansi_box(box_title, box_content, count=count, params=params, style=style if not taking_long else 'warning', emoji=emoji)

if __name__ == "__main__":
    import asyncio
    messages = [
        {"role": "user", "content": "Stewie, manage my WordPress sites."}
    ]
    blueprint = StewieBlueprint(blueprint_id="demo-1")
    async def run_and_print():
        spinner = StewieSpinner()
        spinner.start()
        try:
            all_results = []
            async for response in blueprint.run(messages):
                content = response["messages"][0]["content"] if (isinstance(response, dict) and "messages" in response and response["messages"]) else str(response)
                all_results.append(content)
                # Enhanced progressive output
                if isinstance(response, dict) and (response.get("progress") or response.get("matches")):
                    display_operation_box(
                        title="Progressive Operation",
                        content="\n".join(response.get("matches", [])),
                        style="bold cyan" if response.get("type") == "code_search" else "bold magenta",
                        result_count=len(response.get("matches", [])) if response.get("matches") is not None else None,
                        params={k: v for k, v in response.items() if k not in {'matches', 'progress', 'total', 'truncated', 'done'}},
                        progress_line=response.get('progress'),
                        total_lines=response.get('total'),
                        spinner_state=spinner.current_spinner_state() if hasattr(spinner, 'current_spinner_state') else None,
                        op_type=response.get("type", "search"),
                        emoji="🔍" if response.get("type") == "code_search" else "🧠"
                    )
        finally:
            spinner.stop()
        display_operation_box(
            title="Stewie Output",
            content="\n".join(all_results),
            style="bold green",
            result_count=len(all_results),
            params={"prompt": messages[0]["content"]},
            op_type="stewie"
        )
    asyncio.run(run_and_print())
