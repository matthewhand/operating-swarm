"""
Suggestion Blueprint

Viral docstring update: Operational as of 2025-04-18T10:14:18Z (UTC).
Self-healing, fileops-enabled, swarm-scalable.
"""
# [Swarm Propagation] Next Blueprint: codey
# codey key vars: logger, project_root, src_path
# codey guard: if src_path not in sys.path: sys.path.insert(0, src_path)
# codey debug: logger.debug("Codey agent created: Linus_Corvalds (Coordinator)")
# codey error handling: try/except ImportError with sys.exit(1)

import logging
import os
import shlex
import sys
from datetime import datetime
from typing import Any, ClassVar

import pytz
from typing_extensions import TypedDict

# Ensure src is in path for BlueprintBase import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from agents import Agent, function_tool
    from agents.mcp import MCPServer
    from agents.models.interface import Model

    from swarm.core.blueprint_base import BlueprintBase
except ImportError as e:
     print(f"ERROR: Failed to import 'agents' or 'BlueprintBase'. Is 'openai-agents' installed and src in PYTHONPATH? Details: {e}")
     sys.exit(1)

logger = logging.getLogger(__name__)

# Last swarm update: 2025-04-18T10:15:21Z (UTC)
last_swarm_update = datetime.now(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ (UTC)")
print(f"# Last swarm update: {last_swarm_update}")

# --- Define the desired output structure ---
class SuggestionsOutput(TypedDict):
    """Defines the expected structure for the agent's output."""
    suggestions: list[str]

# Enhanced spinner UX for Suggestion Blueprint with creative suggestion themes
SPINNER_STATES = [
    '💡 Brainstorming ideas...',
    '✨ Generating creative suggestions...',
    '🎯 Refining recommendations...',
    '📝 Compiling suggestion list...',
    '🔍 Evaluating feasibility...',
    '✅ Suggestions ready!',
    '🎉 Delivering personalized recommendations...'
]

# Enhanced spinner class for suggestion generation
class SuggestionSpinner:
    def __init__(self):
        self.states = SPINNER_STATES
        self.current_state = 0
        self.running = False
        self.suggestion_count = 0

    async def start(self):
        self.running = True
        while self.running:
            state = self.states[self.current_state % len(self.states)]
            count = self.suggestion_count + 1
            print(f"\r{state} ({count} suggestions generated)", end='', flush=True)
            self.current_state += 1
            await asyncio.sleep(0.6)

    def add_suggestion(self):
        self.suggestion_count += 1

    def stop(self):
        self.running = False
        print("\r" + " " * 60 + "\r", end='', flush=True)
        print(f"🎉 All {self.suggestion_count} suggestions generated successfully! 💡")

# Patch: Expose underlying fileops functions for direct testing
# PatchedFunctionTool removed - using @function_tool instead

def read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"ERROR: {e}"
def write_file(path: str, content: str) -> str:
    try:
        with open(path, 'w') as f:
            f.write(content)
        return "OK: file written"
    except Exception as e:
        return f"ERROR: {e}"
def list_files(directory: str = '.') -> str:
    try:
        return '\n'.join(os.listdir(directory))
    except Exception as e:
        return f"ERROR: {e}"
def execute_shell_command(command: str) -> str:
    """
    Executes a shell command and returns its stdout and stderr.
    Timeout is configurable via SWARM_COMMAND_TIMEOUT (default: 60s).
    """
    logger.info(f"Executing shell command: {command}")
    try:
        import os
        import subprocess
        timeout = int(os.getenv("SWARM_COMMAND_TIMEOUT", "60"))
        result = subprocess.run(shlex.split(command), shell=False, capture_output=True, text=True, timeout=timeout)
        output = f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        logger.info(f"Command finished. Exit Code: {result.returncode}")
        return output.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {command}")
        return f"Error: Command timed out after {os.getenv('SWARM_COMMAND_TIMEOUT', '60')} seconds."
    except Exception as e:
        logger.error(f"Error executing command '{command}': {e}", exc_info=True)
        return f"Error executing command: {e}"
# Use proper function_tool decorator instead of PatchedFunctionTool
@function_tool
def read_file_tool(file_path: str) -> str:
    """Read the contents of a file."""
    return read_file(file_path)

@function_tool
def write_file_tool(file_path: str, content: str) -> str:
    """Write content to a file."""
    return write_file(file_path, content)

@function_tool
def list_files_tool(directory: str = ".") -> str:
    """List files in a directory."""
    return list_files(directory)

@function_tool
def execute_shell_command_tool(command: str) -> str:
    """Execute a shell command."""
    return execute_shell_command(command)

# --- Define the Blueprint ---
# === OpenAI GPT-4.1 Prompt Engineering Guide ===
# See: https://github.com/openai/openai-cookbook/blob/main/examples/gpt4-1_prompting_guide.ipynb
#
# Agentic System Prompt Example (recommended for structured output/suggestion agents):
SYS_PROMPT_AGENTIC = """
You are an agent - please keep going until the user’s query is completely resolved, before ending your turn and yielding back to the user. Only terminate your turn when you are sure that the problem is solved.
If you are not sure about file content or codebase structure pertaining to the user’s request, use your tools to read files and gather the relevant information: do NOT guess or make up an answer.
You MUST plan extensively before each function call, and reflect extensively on the outcomes of the previous function calls. DO NOT do this entire process by making function calls only, as this can impair your ability to solve the problem and think insightfully.
"""

class SuggestionBlueprint(BlueprintBase):
    """A blueprint defining an agent that generates structured JSON suggestions using output_type."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "SuggestionBlueprint",
        "title": "Suggestion Blueprint (Structured Output)",
        "description": "An agent that provides structured suggestions using Agent(output_type=...).",
        "version": "1.2.0", # Version bump for refactor
        "author": "Open Swarm Team (Refactored)",
        "tags": ["structured output", "json", "suggestions", "output_type"],
        "required_mcp_servers": [],
        "env_vars": [], # OPENAI_API_KEY is implicitly needed by the model
    }

    # Caches
    _model_instance_cache: dict[str, Model] = {}

    def __init__(self, blueprint_id: str = "suggestion", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self.blueprint_id = blueprint_id
        self.config_path = config_path
        self._config = config if config is not None else None
        self._llm_profile_name = None
        self._llm_profile_data = None
        self._markdown_output = None
        # Add other attributes as needed for Suggestion
        # ...

    def create_starting_agent(self, mcp_servers: list[MCPServer]) -> Agent:
        """Create the SuggestionAgent."""
        logger.debug("Creating SuggestionAgent...")
        self._model_instance_cache = {}
        try:
            default_profile_name = self.config.get("llm_profile", "default")
        except RuntimeError:
            # Fallback if config not loaded
            default_profile_name = "default"
        logger.debug(f"Using LLM profile '{default_profile_name}' for SuggestionAgent.")
        model_instance = self._get_model_instance(default_profile_name)
        suggestion_agent_instructions = (
            "You are the SuggestionAgent. Analyze the user's input and generate exactly three relevant, "
            "concise follow-up questions or conversation starters as a JSON object with a single key 'suggestions' "
            "containing a list of strings. You can use fileops tools (read_file, write_file, list_files, execute_shell_command) for any file or shell tasks."
        )
        suggestion_agent = Agent(
            name="SuggestionAgent",
            instructions=suggestion_agent_instructions,
            tools=[read_file_tool, write_file_tool, list_files_tool, execute_shell_command_tool],
            model=model_instance,
            output_type=SuggestionsOutput,
            mcp_servers=mcp_servers
        )
        logger.debug("SuggestionAgent created with output_type enforcement.")
        return suggestion_agent

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Main execution entry point for the Suggestion blueprint."""
        import json
        import os

        logger.info("SuggestionBlueprint run method called.")
        # Deterministic path for tests / SWARM_TEST_MODE — no LLM profile required.
        if os.environ.get("SWARM_TEST_MODE"):
            instruction = messages[-1].get("content", "") if messages else ""
            payload = {
                "suggestions": [
                    f"Can you expand on: {instruction[:80]}?" if instruction else "What should we explore next?",
                    "What are the main risks or trade-offs?",
                    "What would a minimal first step look like?",
                ]
            }
            yield {
                "messages": [
                    {
                        "role": "assistant",
                        "content": json.dumps(payload),
                    }
                ]
            }
            logger.info("SuggestionBlueprint run method finished (TEST_MODE).")
            return

        instruction = messages[-1].get("content", "") if messages else ""
        async for chunk in self._run_non_interactive(instruction, **kwargs):
            yield chunk
        logger.info("SuggestionBlueprint run method finished.")

    async def _run_non_interactive(self, instruction: str, **kwargs) -> Any:
        logger.info(f"Running SuggestionBlueprint non-interactively with instruction: '{instruction[:100]}...'")
        mcp_servers = kwargs.get("mcp_servers", [])
        agent = self.create_starting_agent(mcp_servers=mcp_servers)
        import os

        from agents import Runner
        os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM") or "gpt-3.5-turbo"
        try:
            result = await Runner.run(agent, instruction)
            yield {
                "messages": [
                    {
                        "role": "assistant",
                        "content": str(result)
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error during non-interactive run: {e}", exc_info=True)
            yield {"messages": [{"role": "assistant", "content": f"An error occurred: {e}"}]}

    # --- Model Instantiation Helper --- (Standard helper)
    def _get_model_instance(self, profile_name: str) -> Model:
        """Retrieves or creates an LLM Model instance."""
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")

        # Fallback to simple OpenAI model if config not available
        try:
            profile_data = self.get_llm_profile(profile_name)
        except RuntimeError:
            # Config not loaded, use environment fallback
            import os

            from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
            from swarm.utils.env_utils import openai_client_kwargs
            client_kwargs = openai_client_kwargs()
            if not client_kwargs.get("api_key"):
                raise ValueError("No OPENAI_API_KEY / LITELLM_* key found and config not loaded")
            logger.warning(
                f"Config not available, using fallback OpenAI/LiteLLM model for {profile_name}"
            )
            from openai import AsyncOpenAI
            client = AsyncOpenAI(**client_kwargs)
            model_instance = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client)
            self._model_instance_cache[profile_name] = model_instance
            return model_instance
        if not profile_data: raise ValueError(f"Missing LLM profile '{profile_name}'.")
        provider = profile_data.get("provider", "openai").lower()
        model_name = profile_data.get("model")
        if not model_name: raise ValueError(f"Missing 'model' in profile '{profile_name}'.")
        from swarm.core.llm_provider import is_openai_chat_provider
        if not is_openai_chat_provider(provider):
            raise ValueError(f"Unsupported provider: {provider}")
        # Remove redundant client instantiation; rely on framework-level default client
        # All blueprints now use the default client set at framework init
        logger.debug(f"Instantiating OpenAIChatCompletionsModel(model='{model_name}') for '{profile_name}'.")
        try:
            # Ensure the model selected supports structured output (most recent OpenAI do)
            model_instance = OpenAIChatCompletionsModel(model=model_name)
            self._model_instance_cache[profile_name] = model_instance
            return model_instance
        except Exception as e: raise ValueError(f"Failed to init LLM: {e}") from e

if __name__ == "__main__":
    import asyncio
    import json
    import os
    # Test-mode fallback: output canned JSON without invoking LLM
    if os.environ.get('SWARM_TEST_MODE'):
        example = {
            "suggestions": [
                "What are the potential ethical implications of AI adoption?",
                "How can we ensure transparency in AI decision-making?",
                "What safeguards are necessary for AI deployment in critical systems?"
            ]
        }
        print(json.dumps(example, indent=2))
        import sys; sys.exit(0)
    print("\033[1;36m\n╔══════════════════════════════════════════════════════════════╗\n║   💡 SUGGESTION: SWARM-POWERED IDEA GENERATION DEMO          ║\n╠══════════════════════════════════════════════════════════════╣\n║ This blueprint demonstrates viral swarm propagation,         ║\n║ swarm-powered suggestion logic, and robust import guards.    ║\n║ Try running: python blueprint_suggestion.py                  ║\n╚══════════════════════════════════════════════════════════════╝\033[0m")
    messages = [
        {"role": "user", "content": "Show me how Suggestion leverages swarm propagation for idea generation."}
    ]
    blueprint = SuggestionBlueprint(blueprint_id="demo-1")
    async def run_and_print():
        async for response in blueprint.run(messages):
            print(json.dumps(response, indent=2))
    asyncio.run(run_and_print())
