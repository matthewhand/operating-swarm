import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, ClassVar

from dotenv import load_dotenv

load_dotenv(override=True)


# Set logging to WARNING by default unless SWARM_DEBUG=1
if not os.environ.get("SWARM_DEBUG"):
    logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.DEBUG)


# Ensure src is in path for BlueprintBase import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


try:
    from agents import Agent, function_tool
    # Patch: If MCPServer import fails, define a dummy MCPServer for demo/test
    try:
        from agents.mcp import MCPServer
    except ImportError:
        class MCPServer:
            pass
    MCPServer2 = MCPServer
    from agents.models.interface import Model
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from swarm.core.blueprint_base import BlueprintBase
except ImportError as e:
    print(f"ERROR: Import failed in ChatbotBlueprint: {e}. Check dependencies.")
    print(f"sys.path: {sys.path}")
    sys.exit(1)

logger = logging.getLogger(__name__)


# --- Define the Blueprint ---
class ChatbotBlueprint(BlueprintBase):
    def __init__(self, blueprint_id: str, config_path: Path | None = None, **kwargs):
        super().__init__(blueprint_id, config_path=config_path, **kwargs)
        class DummyLLM:
            def chat_completion_stream(self, **_):
                class DummyStream:
                    def __aiter__(self):
                        return self
                    async def __anext__(self):
                        raise StopAsyncIteration
                return DummyStream()
        self.llm = DummyLLM()

        # Remove redundant client instantiation; rely on framework-level default client
        # (No need to re-instantiate AsyncOpenAI or set_default_openai_client)
        # All blueprints now use the default client set at framework init

    """A simple conversational chatbot agent."""
    metadata: ClassVar[dict[str, Any]] = {
        "name": "chatbot",
        "title": "Simple Chatbot",
        "description": "A basic conversational agent that responds to user input.",
        "version": "1.1.0", # Refactored version
        "author": "Open Swarm Team (Refactored)",
        "tags": ["chatbot", "conversation", "simple"],
        "required_mcp_servers": [],
        "env_vars": [],
        "navbar_items": [{"id": "token_counter", "kind": "token_counter", "label": "Tokens"}],
    }

    def get_navbar_items(self=None) -> list[dict]:
        """Returns metadata for navbar items contributed by this blueprint."""
        return [{"id": "token_counter", "kind": "token_counter", "label": "Tokens"}]

    # Caches
    _openai_client_cache: dict[str, AsyncOpenAI] = {}
    _model_instance_cache: dict[str, Model] = {}

    # Patch: Expose underlying fileops functions for direct testing
    class PatchedFunctionTool:
        def __init__(self, func, name):
            self.func = func
            self.name = name

    def read_file(self, path: str) -> str:
        try:
            with open(path) as f:
                return f.read()
        except Exception as e:
            return f"ERROR: {e}"

    def write_file(self, path: str, content: str) -> str:
        try:
            with open(path, 'w') as f:
                f.write(content)
            return "OK: file written"
        except Exception as e:
            return f"ERROR: {e}"

    def list_files(self, directory: str = '.') -> str:
        try:
            return '\n'.join(os.listdir(directory))
        except Exception as e:
            return f"ERROR: {e}"

    def execute_shell_command(self, command: str) -> str:
        import shlex
        import subprocess
        try:
            result = subprocess.run(shlex.split(command), shell=False, capture_output=True, text=True, timeout=30)
            return result.stdout + result.stderr
        except (ValueError, subprocess.TimeoutExpired) as e:
            return f"ERROR: {e}"
        except Exception as e:
            return f"ERROR: {e}"
    # Use proper function_tool decorator instead of PatchedFunctionTool
    @function_tool
    def read_file_tool(self, file_path: str) -> str:
        """Read the contents of a file."""
        return self.read_file(file_path)

    @function_tool
    def write_file_tool(self, file_path: str, content: str) -> str:
        """Write content to a file."""
        return self.write_file(file_path, content)

    @function_tool
    def list_files_tool(self, directory: str = ".") -> str:
        """List files in a directory."""
        return self.list_files(directory)

    @function_tool
    def execute_shell_command_tool(self, command: str) -> str:
        """Execute a shell command."""
        return self.execute_shell_command(command)

    # --- Model Instantiation Helper --- (Standard helper)
    def _get_model_instance(self, profile_name: str) -> Model:
        """Retrieves or creates an LLM Model instance for chatbot / api_agent.

        Tip profiles keep provider: litellm. Accept that via
        is_openai_chat_provider (aliases included) and speak Chat Completions
        through the OpenAI SDK. Prefer the *named* profile model so
        DEFAULT_LLM/LITELLM_MODEL=auxiliary cannot steal orchestration.
        """
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")
        profile_data = dict(self.get_llm_profile(profile_name) or {})
        import os
        from swarm.core.config_loader import named_profile_model
        from swarm.core.llm_provider import is_openai_chat_provider, openai_sdk_provider
        model_name = named_profile_model(self.config, profile_name, profile_data)
        if not model_name:
            model_name = os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM")
        profile_data["model"] = model_name
        if os.getenv("LITELLM_BASE_URL"):
            profile_data["base_url"] = os.getenv("LITELLM_BASE_URL")
        if os.getenv("LITELLM_API_KEY"):
            profile_data["api_key"] = os.getenv("LITELLM_API_KEY")
        provider = profile_data.get("provider", "openai")
        if not is_openai_chat_provider(provider):
            raise ValueError(f"Unsupported provider: {provider}")
        if not model_name:
            raise ValueError(f"Missing 'model' in profile '{profile_name}'.")

        sdk_provider = openai_sdk_provider(provider)
        client_cache_key = f"{sdk_provider}_{profile_data.get('base_url')}"
        if client_cache_key not in self._openai_client_cache:
             client_kwargs = { "api_key": profile_data.get("api_key"), "base_url": profile_data.get("base_url") }
             filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}
             log_kwargs = {k:v for k,v in filtered_kwargs.items() if k != 'api_key'}
             logger.debug(f"Creating new AsyncOpenAI client for '{profile_name}': {log_kwargs}")
             try:
                self._openai_client_cache[client_cache_key] = AsyncOpenAI(**filtered_kwargs)
             except Exception as e:
                raise ValueError(f"Failed to init client: {e}") from e
        client = self._openai_client_cache[client_cache_key]
        logger.debug(f"Instantiating OpenAIChatCompletionsModel(model='{model_name}') for '{profile_name}'.")
        try:
            model_instance = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
            self._model_instance_cache[profile_name] = model_instance
            return model_instance
        except Exception as e:
            raise ValueError(f"Failed to init LLM: {e}") from e

    def create_starting_agent(self, mcp_servers: list[MCPServer]) -> Agent:
        """Creates the single Chatbot agent."""
        logger.debug("Creating Chatbot agent...")
        self._model_instance_cache = {}
        self._openai_client_cache = {}

        # Honor settings.default_llm_profile (orchestration on tip), not a
        # hardcoded top-level "default" that still has provider=litellm + model=auxiliary.
        default_profile_name = self.llm_profile_name
        logger.debug(f"Using LLM profile '{default_profile_name}' for Chatbot/api_agent.")
        model_instance = self._get_model_instance(default_profile_name)

        if self.enable_terminal_commands:
            chatbot_instructions = """
You are a helpful and friendly chatbot. Respond directly to the user's input in a conversational manner.

You have access to the following tools for file operations and shell commands:
- read_file
- write_file
- list_files
- execute_shell_command
Use them responsibly when the user asks for file or system operations.
"""
        else:
            chatbot_instructions = (
                "You are a helpful and friendly chatbot. "
                "Respond directly to the user's input in a conversational manner. "
                "Do not call tools."
            )

        chatbot_agent = Agent(
            name="Chatbot",
            model=model_instance,
            instructions=chatbot_instructions,
            tools=(
                [self.read_file_tool, self.write_file_tool, self.list_files_tool, self.execute_shell_command_tool]
                if self.enable_terminal_commands
                else []
            ),
            mcp_servers=mcp_servers # Pass along, though likely unused
        )

        logger.debug("Chatbot agent created.")
        return chatbot_agent

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Main execution entry point for the Chatbot blueprint."""
        logger.info("ChatbotBlueprint run method called.")
        raw = messages[-1].get("content", "") if messages else ""
        instruction = raw.strip() if isinstance(raw, str) else raw
        if not instruction:
            yield {"messages": [{"role": "assistant", "content": "Hello! How can I help you?"}], "final": True}
            return
        if os.environ.get('SWARM_TEST_MODE'):
            user_text = instruction if isinstance(instruction, str) else (
                next((m.get("content", "") for m in reversed(instruction) if m.get("role") == "user"), "")
                if isinstance(instruction, list) else str(instruction)
            )
            yield {"messages": [{"role": "assistant", "content": f"You said: {user_text}"}], "final": True}
            return
        # REST / CSRF / ASGI: skip CLI spinner sleeps (they also trip
        # SynchronousOnlyOperation when Rich/stdout runs on the event loop).
        if sys.stdout.isatty() and os.environ.get("SWARM_DEBUG"):
            from swarm.core.output_utils import print_search_progress_box
            spinner_states = [
                "Listening to user... 👂",
                "Consulting knowledge base... 📚",
                "Formulating response... 💭",
                "Typing reply... ⌨️"
            ]
            total_steps = len(spinner_states)
            params = {"instruction": instruction}
            summary = f"Chatbot agent run for: '{instruction}'"
            for i, spinner_state in enumerate(spinner_states, 1):
                print_search_progress_box(
                    op_type="Chatbot Agent Run",
                    results=[instruction, f"Chatbot agent is running your request... (Step {i})"],
                    params=params,
                    result_type="chatbot",
                    summary=summary,
                    progress_line=f"Step {i}/{total_steps}",
                    spinner_state=spinner_state,
                    operation_type="Chatbot Run",
                    search_mode=None,
                    total_lines=total_steps,
                    emoji='🤖',
                    border='╔'
                )
                await asyncio.sleep(0.09)
        async for chunk in self._run_non_interactive(instruction, **kwargs):
            yield chunk
        logger.info("ChatbotBlueprint run method finished.")

    async def _run_non_interactive(self, instruction: str, **kwargs) -> Any:
        mcp_servers = kwargs.get("mcp_servers", [])
        agent = self.create_starting_agent(mcp_servers=mcp_servers)

        from agents import Runner
        try:
            timeout = float(os.getenv("SWARM_CHATBOT_RUN_TIMEOUT", "20"))
        except (TypeError, ValueError):
            timeout = 20.0
        try:
            result = await asyncio.wait_for(Runner.run(agent, instruction), timeout=timeout)
            response = getattr(result, 'final_output', str(result))
            yield {"messages": [{"role": "assistant", "content": response}], "final": True}
        except asyncio.TimeoutError:
            logger.error("Chatbot/api_agent LLM run timed out after %.1fs", timeout)
            yield {
                "messages": [{
                    "role": "assistant",
                    "content": (
                        f"PONG {self.blueprint_id} — LLM timed out after {timeout:.0f}s. "
                        f"Asked: {str(instruction)[:120]!r}"
                    ),
                }],
                "final": True,
            }
        except Exception as e:
            logger.error(f"Error during non-interactive run: {e}", exc_info=True)
            yield {"messages": [{"role": "assistant", "content": f"An error occurred: {e}\nAgent-based LLM not available."}], "final": True}

# Standard Python entry point
if __name__ == "__main__":
    # --- AUTO-PYTHONPATH PATCH FOR AGENTS ---
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
    src_path = os.path.join(project_root, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    if '--instruction' in sys.argv:
        instruction = sys.argv[sys.argv.index('--instruction') + 1]
    else:
        print("Interactive mode not supported in this script.")
        sys.exit(1)

    blueprint = ChatbotBlueprint(blueprint_id="chatbot")
    async def runner():
        async for chunk in blueprint._run_non_interactive(instruction):
            msg = chunk["messages"][0]["content"]
            if not msg.startswith("An error occurred:"):
                print(msg)
    asyncio.run(runner())
