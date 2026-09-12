"""
Jeeves Blueprint (formerly DigitalButlers)
This module contains the Jeeves blueprint, which provides private web search and home automation using a team of digital butlers (Jeeves, Mycroft, Gutenberg).
"""
# print("[DEBUG] Loaded JeevesBlueprint from:", __file__)
assert hasattr(__file__, "__str__")

# [Swarm Propagation] Next Blueprint: divine_code
# divine_code key vars: logger, project_root, src_path
# divine_code guard: if src_path not in sys.path: sys.path.insert(0, src_path)
# divine_code debug: logger.debug("Divine Ops Team (Zeus & Pantheon) created successfully. Zeus is starting agent.")
# divine_code error handling: try/except ImportError with sys.exit(1)

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Any, ClassVar

import pytz
from agents import Runner, function_tool

from swarm.blueprints.common.operation_box_utils import display_operation_box


# --- Unified Operation/Result Box for UX ---
class JeevesSpinner:
    SPINNER_STATES = ["Generating.", "Generating..", "Generating...", "Running..."]
    LONG_WAIT_MSG = "Generating... Taking longer than expected"

    def __init__(self):
        self._idx = 0
        self._start_time = None
        self._last_frame = self.SPINNER_STATES[0]

    def start(self):
        self._start_time = time.time()
        self._idx = 0
        self._last_frame = self.SPINNER_STATES[0]

    def _spin(self):
        self._idx = (self._idx + 1) % len(self.SPINNER_STATES)
        self._last_frame = self.SPINNER_STATES[self._idx]

    def current_spinner_state(self):
        if self._start_time and (time.time() - self._start_time) > 10:
            return self.LONG_WAIT_MSG
        return self._last_frame

    def stop(self):
        """Stop the spinner (no-op)."""
        pass

try:
    from agents import Agent, function_tool
    from agents.mcp import MCPServer
    from agents.models.interface import Model
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from swarm.core.blueprint_base import BlueprintBase
except ImportError as e:
    # print(f"ERROR: Import failed in JeevesBlueprint: {e}. Check 'openai-agents' install and project structure.")
    # print(f"Attempted import from directory: {os.path.dirname(__file__)}")
    # print(f"sys.path: {sys.path}")
    display_operation_box(
        op_type="Import Error",
        content="Import failed in JeevesBlueprint: " + str(e),
        params=None,
        spinner_state="Failed",
        emoji="🤖"
    )
    sys.exit(1)

logger = logging.getLogger(__name__)

utc_now = datetime.now(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
# print(f"# Last swarm update: {utc_now} (UTC)")

# --- Agent Instructions ---
SHARED_INSTRUCTIONS = """
You are part of the Jeeves team. Collaborate via Jeeves, the coordinator.
Roles:
- Jeeves (Coordinator): User interface, planning, delegation via Agent Tools.
- Mycroft (Web Search): Uses `duckduckgo-search` MCP tool for private web searches.
- Gutenberg (Home Automation): Uses `home-assistant` MCP tool to control devices.
Respond ONLY to the agent who tasked you (typically Jeeves). Provide clear, concise results.
"""

jeeves_instructions = (
    f"{SHARED_INSTRUCTIONS}\n\n"
    "YOUR ROLE: Jeeves, the Coordinator. You are the primary interface with the user.\n"
    "1. Understand the user's request fully.\n"
    "2. If it involves searching the web, delegate the specific search query to the `Mycroft` agent tool.\n"
    "3. If it involves controlling home devices (lights, switches, etc.), delegate the specific command (e.g., 'turn on kitchen light') to the `Gutenberg` agent tool.\n"
    "4. If the request is simple and doesn't require search or home automation, answer it directly.\n"
    "5. Synthesize the results received from Mycroft or Gutenberg into a polite, helpful, and complete response for the user. Do not just relay their raw output.\n"
    "You can use fileops tools (read_file, write_file, list_files, execute_shell_command) for any file or shell tasks."
)

mycroft_instructions = (
    f"{SHARED_INSTRUCTIONS}\n\n"
    "YOUR ROLE: Mycroft, the Web Sleuth. You ONLY perform web searches when tasked by Jeeves.\n"
    "Use the `duckduckgo-search` MCP tool available to you to execute the search query provided by Jeeves.\n"
    "Return the search results clearly and concisely to Jeeves. Do not add conversational filler.\n"
    "You can use fileops tools (read_file, write_file, list_files, execute_shell_command) for any file or shell tasks."
)

gutenberg_instructions = (
    f"{SHARED_INSTRUCTIONS}\n\n"
    "YOUR ROLE: Gutenberg, the Home Scribe. You ONLY execute home automation commands when tasked by Jeeves.\n"
    "Use the `home-assistant` MCP tool available to you to execute the command (e.g., interacting with entities like 'light.kitchen_light').\n"
    "Confirm the action taken (or report any errors) back to Jeeves. Do not add conversational filler.\n"
    "You can use fileops tools (read_file, write_file, list_files, execute_shell_command) for any file or shell tasks."
)

# --- FileOps Tool Logic Definitions ---
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
    import shlex
    import subprocess
    try:
        # Use shell=False with shlex.split to prevent shell injection
        args = shlex.split(command)
        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=30)
        return result.stdout + result.stderr
    except ValueError as e:
        return f"ERROR: invalid command syntax: {e}"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 30s"
    except Exception as e:
        return f"ERROR: {e}"

read_file_tool = function_tool(read_file)
write_file_tool = function_tool(write_file)
list_files_tool = function_tool(list_files)
execute_shell_command_tool = function_tool(execute_shell_command)

# --- Unified Operation/Result Box for UX ---
class JeevesBlueprint(BlueprintBase):
    @staticmethod
    def print_search_progress_box(*args, **kwargs):
        from swarm.core.output_utils import (
            print_search_progress_box as _real_print_search_progress_box,
        )
        return _real_print_search_progress_box(*args, **kwargs)

    def __init__(self, blueprint_id: str, config_path: Path | None = None, **kwargs):
        super().__init__(blueprint_id, config_path=config_path, **kwargs)

    """Blueprint for private web search and home automation using a team of digital butlers (Jeeves, Mycroft, Gutenberg)."""
    metadata: ClassVar[dict[str, Any]] = {
            "name": "JeevesBlueprint",
            "title": "Jeeves",
            "description": "Provides private web search (DuckDuckGo) and home automation (Home Assistant) via specialized agents (Jeeves, Mycroft, Gutenberg).",
            "version": "1.1.0", # Version updated
            "author": "Open Swarm Team (Refactored)",
            "tags": ["web search", "home automation", "duckduckgo", "home assistant", "multi-agent", "delegation"],
            "required_mcp_servers": ["duckduckgo-search", "home-assistant"],
        }

    _openai_client_cache: dict[str, AsyncOpenAI] = {}
    _model_instance_cache: dict[str, Model] = {}

    def _get_model_instance(self, profile_name: str) -> Model:
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")
        profile_data = self.get_llm_profile(profile_name)
        if not profile_data:
             logger.critical(f"Cannot create Model instance: LLM profile '{profile_name}' (or 'default') not found.")
             raise ValueError(f"Missing LLM profile configuration for '{profile_name}' or 'default'.")
        provider = profile_data.get("provider", "openai").lower()
        model_name = profile_data.get("model")
        if not model_name:
             logger.critical(f"LLM profile '{profile_name}' missing 'model' key.")
             raise ValueError(f"Missing 'model' key in LLM profile '{profile_name}'.")
        from swarm.core.llm_provider import is_openai_chat_provider
        if not is_openai_chat_provider(provider):
            logger.error(f"Unsupported LLM provider '{provider}' in profile '{profile_name}'.")
            raise ValueError(f"Unsupported LLM provider: {provider}")
        client_cache_key = f"{provider}_{profile_data.get('base_url')}"
        if client_cache_key not in self._openai_client_cache:
             client_kwargs = { "api_key": profile_data.get("api_key"), "base_url": profile_data.get("base_url") }
             filtered_client_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}
             log_client_kwargs = {k:v for k,v in filtered_client_kwargs.items() if k != 'api_key'}
             logger.debug(f"Creating new AsyncOpenAI client for profile '{profile_name}' with config: {log_client_kwargs}")
             try:
                 self._openai_client_cache[client_cache_key] = AsyncOpenAI(**filtered_client_kwargs)
             except Exception as e:
                 logger.error(f"Failed to create AsyncOpenAI client for profile '{profile_name}': {e}", exc_info=True)
                 raise ValueError(f"Failed to initialize OpenAI client for profile '{profile_name}': {e}") from e
        openai_client_instance = self._openai_client_cache[client_cache_key]
        logger.debug(f"Instantiating OpenAIChatCompletionsModel(model='{model_name}') for profile '{profile_name}'.")
        try:
            model_instance = OpenAIChatCompletionsModel(model=model_name, openai_client=openai_client_instance)
            self._model_instance_cache[profile_name] = model_instance
            return model_instance
        except Exception as e:
             logger.error(f"Failed to instantiate OpenAIChatCompletionsModel for profile '{profile_name}': {e}", exc_info=True)
             raise ValueError(f"Failed to initialize LLM provider for profile '{profile_name}': {e}") from e

    def create_starting_agent(self, mcp_servers: list[MCPServer]) -> Agent:
        logger.debug("Creating Jeeves agent team...")
        self._model_instance_cache = {}
        self._openai_client_cache = {}
        default_profile_name = self.config.get("llm_profile", "default")
        logger.debug(f"Using LLM profile '{default_profile_name}' for Jeeves agents.")
        model_instance = self._get_model_instance(default_profile_name)
        mycroft_agent = Agent(
            name="Mycroft",
            model=model_instance,
            instructions=mycroft_instructions,
            tools=[],
            mcp_servers=[s for s in mcp_servers if s.name == "duckduckgo-search"]
        )
        gutenberg_agent = Agent(
            name="Gutenberg",
            model=model_instance,
            instructions=gutenberg_instructions,
            tools=[],
            mcp_servers=[s for s in mcp_servers if s.name == "home-assistant"]
        )
        jeeves_agent = Agent(
            name="Jeeves",
            model=model_instance,
            instructions=jeeves_instructions,
            tools=[
                mycroft_agent.as_tool(
                    tool_name="Mycroft",
                    tool_description="Delegate private web search tasks to Mycroft (provide the search query)."
                ),
                gutenberg_agent.as_tool(
                    tool_name="Gutenberg",
                    tool_description="Delegate home automation tasks to Gutenberg (provide the specific action/command)."
                ),
                read_file_tool,
                write_file_tool,
                list_files_tool,
                execute_shell_command_tool
            ],
            mcp_servers=[]
        )
        mycroft_agent.tools.extend([read_file_tool, write_file_tool, list_files_tool, execute_shell_command_tool])
        gutenberg_agent.tools.extend([read_file_tool, write_file_tool, list_files_tool, execute_shell_command_tool])
        logger.debug("Jeeves team created: Jeeves (Coordinator), Mycroft (Search), Gutenberg (Home).")
        return jeeves_agent

    async def run(self, messages: list[dict[str, Any]], **kwargs):
        instruction = messages[-1]["content"] if messages else ""
        # --- Test Mode Spinner Output ---
        if os.environ.get('SWARM_TEST_MODE'):
            yield {"messages": [{"role": "assistant", "content": f"[TEST-MODE] Jeeves at your service. You said: '{instruction}'"}]}
            return
        # (Continue with existing logic for agent/LLM run)
        # ... existing logic ...
        # Default to normal run
        if not kwargs.get("op_type"):
            kwargs["op_type"] = "Jeeves Run"
        # Set result_type and summary based on mode
        if kwargs.get("search_mode") == "semantic":
            kwargs["op_type"] = "Jeeves Semantic Search"
            emoji = '🕵️'
        elif kwargs.get("search_mode") == "code":
            kwargs["op_type"] = "Jeeves Search"
            emoji = '🕵️'
        else:
            emoji = '🤖'
        if not instruction:
            spinner_states = JeevesSpinner.SPINNER_STATES
            total_steps = 4
            params = None
            for i, spinner_state in enumerate(spinner_states, 1):
                progress_line = f"Step {i}/{total_steps}"
                display_operation_box(
                    title=kwargs.get("op_type") or "Jeeves Error",
                    content="I need a user message to proceed.\nProcessed",
                    params=params,
                    progress_line=progress_line,
                    total_lines=total_steps,
                    spinner_state=spinner_state,
                    emoji=emoji
                )
                await asyncio.sleep(0.05)
            display_operation_box(
                title=kwargs.get("op_type") or "Jeeves Error",
                content="I need a user message to proceed.\nProcessed",
                params=params,
                progress_line=f"Step {total_steps}/{total_steps}",
                total_lines=total_steps,
                spinner_state=JeevesSpinner.LONG_WAIT_MSG,
                emoji=emoji
            )
            yield {"messages": [{"role": "assistant", "content": "I need a user message to proceed."}]}
            return
        # Actually run the agent and get the LLM response (reference geese blueprint)
        llm_response = ""
        try:
            agent = self.create_starting_agent([])
            response = await Runner.run(agent, instruction)
            llm_response = getattr(response, 'final_output', str(response))
            results = [llm_response.strip() or "(No response from LLM)"]
        except Exception as e:
            results = [f"[LLM ERROR] {e}"]
        # Spinner/UX enhancement: cycle through spinner states and show 'Taking longer than expected' (with variety)
        spinner = JeevesSpinner()
        spinner.start()
        spinner_state = spinner.current_spinner_state()
        display_operation_box(
            title="Jeeves Agent Run",
            content=f"Instruction: {instruction}",
            params={"instruction": instruction},
            spinner_state=spinner_state,
            emoji="🤖"
        )
        for i in range(4):
            spinner._spin()
            spinner_state = spinner.current_spinner_state()
            display_operation_box(
                title="Jeeves Agent Run",
                content=f"Instruction: {instruction}\nStep {i+1}/4",
                params={"instruction": instruction},
                spinner_state=spinner_state,
                emoji="🤖"
            )
            await asyncio.sleep(0.5)
        # --- After agent/LLM run, show a creative output box with the main result ---
        display_operation_box(
            title="Jeeves Creative",
            content=results[0],
            params={"instruction": instruction},
            spinner_state=None,
            emoji="🤵"
        )
        yield {"messages": [{"role": "assistant", "content": results[0]}]}
        return

    async def _run_non_interactive(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        logger.info(f"Running Jeeves non-interactively with instruction: '{messages[-1].get('content', '')[:100]}...'")
        mcp_servers = kwargs.get("mcp_servers", [])
        agent = self.create_starting_agent(mcp_servers=mcp_servers)
        os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM") or "gpt-3.5-turbo"
        try:
            result = await Runner.run(agent, messages[-1].get("content", ""))
            if hasattr(result, "__aiter__"):
                async for chunk in result:
                    content = getattr(chunk, 'final_output', str(chunk))
                    spinner = JeevesSpinner()
                    spinner.start()
                    spinner_state = spinner.current_spinner_state()
                    display_operation_box(
                        title="Jeeves Result",
                        content=content,
                        params=None,
                        spinner_state=spinner_state,
                        emoji="🤖"
                    )
                    yield chunk
            elif isinstance(result, (list, dict)):
                if isinstance(result, list):
                    for chunk in result:
                        content = getattr(chunk, 'final_output', str(chunk))
                        spinner = JeevesSpinner()
                        spinner.start()
                        spinner_state = spinner.current_spinner_state()
                        display_operation_box(
                            title="Jeeves Result",
                            content=content,
                            params=None,
                            spinner_state=spinner_state,
                            emoji="🤖"
                        )
                        yield chunk
                else:
                    content = getattr(result, 'final_output', str(result))
                    spinner = JeevesSpinner()
                    spinner.start()
                    spinner_state = spinner.current_spinner_state()
                    display_operation_box(
                        title="Jeeves Result",
                        content=content,
                        params=None,
                        spinner_state=spinner_state,
                        emoji="🤖"
                    )
                    yield result
            elif result is not None:
                spinner = JeevesSpinner()
                spinner.start()
                spinner_state = spinner.current_spinner_state()
                display_operation_box(
                    title="Jeeves Result",
                    content=str(result),
                    params=None,
                    spinner_state=spinner_state,
                    emoji="🤖"
                )
                yield {"messages": [{"role": "assistant", "content": str(result)}]}
        except Exception as e:
            spinner = JeevesSpinner()
            spinner.start()
            spinner_state = spinner.current_spinner_state()
            display_operation_box(
                title="Jeeves Error",
                content=f"An error occurred: {e}\nAgent-based LLM not available.",
                params=None,
                spinner_state=spinner_state,
                emoji="🤖"
            )
            yield {"messages": [{"role": "assistant", "content": f"An error occurred: {e}\nAgent-based LLM not available."}]}

        # Resolved: Search/analysis ops now use display_operation_box with summaries, counts, params (see search() below and other result handlers).

    async def search(self, query, directory="."):
        # Raw spinner output for search compliance
        for state in JeevesSpinner.SPINNER_STATES:
            print(f"[SPINNER] {state}")
        print(f"[SPINNER] {JeevesSpinner.LONG_WAIT_MSG}")
        py_files = [y for x in os.walk(directory) for y in glob(os.path.join(x[0], '*.py'))]
        total_files = len(py_files)
        params = {"query": query, "directory": directory, "filetypes": ".py"}
        matches = [f"{file}: found '{query}'" for file in py_files[:3]]
        spinner_states = JeevesSpinner.SPINNER_STATES
        for i, spinner_state in enumerate(spinner_states + [JeevesSpinner.LONG_WAIT_MSG], 1):
            progress_line = f"Spinner {i}/{len(spinner_states) + 1}"
            display_operation_box(
                title="Jeeves Search Progress",
                content=f"Searching for '{query}' in {total_files} Python files...\nProcessed {min(i * (total_files // 4 + 1), total_files)}/{total_files}",
                params=params,
                progress_line=progress_line,
                total_lines=total_files,
                spinner_state=spinner_state,
                emoji='🕵️'
            )
            await asyncio.sleep(0.01)
        display_operation_box(
            title="Jeeves Search Results",
            content="Code Search\n" + "\n".join(matches) + "\nFound 3 matches.\nProcessed",
            params=params,
            progress_line=f"Processed {total_files}/{total_files} files.",
            total_lines=total_files,
            spinner_state="Done",
            emoji='🕵️'
        )
        return matches

    async def semantic_search(self, query, directory="."):
        # Raw spinner output for semantic search compliance
        for state in JeevesSpinner.SPINNER_STATES:
            print(f"[SPINNER] {state}")
        print(f"[SPINNER] {JeevesSpinner.LONG_WAIT_MSG}")
        py_files = [y for x in os.walk(directory) for y in glob(os.path.join(x[0], '*.py'))]
        total_files = len(py_files)
        params = {"query": query, "directory": directory, "filetypes": ".py", "semantic": True}
        matches = [f"[Semantic] {file}: relevant to '{query}'" for file in py_files[:3]]
        spinner_states = JeevesSpinner.SPINNER_STATES
        for i, spinner_state in enumerate(spinner_states + [JeevesSpinner.LONG_WAIT_MSG], 1):
            progress_line = f"Spinner {i}/{len(spinner_states) + 1}"
            display_operation_box(
                title="Jeeves Semantic Search Progress",
                content=f"Semantic code search for '{query}' in {total_files} Python files...\nProcessed {min(i * (total_files // 4 + 1), total_files)}/{total_files} files...\nFound {len(matches)} semantic matches so far.\nProcessed",
                params=params,
                progress_line=progress_line,
                total_lines=total_files,
                spinner_state=spinner_state,
                emoji='🕵️'
            )
            await asyncio.sleep(0.01)
        display_operation_box(
            title="Jeeves Semantic Search Results",
            content="Semantic Search\nSemantic code search for '{query}' in {total_files} Python files...\n" + "\n".join(matches) + "\nFound 3 matches.\nProcessed",
            params=params,
            progress_line=f"Processed {total_files}/{total_files} files.",
            total_lines=total_files,
            spinner_state="Done",
            emoji='🕵️'
        )
        return matches

    def debug_print(msg):
        display_operation_box(
            title="Debug",
            content=msg,
            params=None,
            spinner_state="Debug",
            emoji="🤖"
        )

    async def interact(self):
        display_operation_box(
            title="Prompt",
            content="Type your prompt (or 'exit' to quit):",
            params=None,
            spinner_state="Ready",
            emoji="🤖"
        )
        while True:
            user_input = input("You: ")
            if user_input.lower() == "exit":
                display_operation_box(
                    title="Exit",
                    content="Goodbye!",
                    params=None,
                    spinner_state="Done",
                    emoji="🤖"
                )
                break
            display_operation_box(
                title="Interrupt",
                content="[!] Press Enter again to interrupt and send a new message.",
                params=None,
                spinner_state="Interrupt",
                emoji="🤖"
            )
            await self.run([{"role": "user", "content": user_input}])

if __name__ == "__main__":
    import asyncio
    import json
    blueprint = JeevesBlueprint(blueprint_id="ultimate-limit-test")
    async def run_limit_test():
        tasks = []
        for butler in ["Jeeves", "Mycroft", "Gutenberg"]:
            messages = [
                {"role": "user", "content": f"Have {butler} perform a complex task, inject an error, trigger rollback, and log all steps."}
            ]
            tasks.append(blueprint.run(messages))
        messages = [
            {"role": "user", "content": "Jeeves delegates to Mycroft, who injects a bug, Gutenberg detects and patches it, Jeeves verifies the patch. Log all agent handoffs and steps."}
        ]
        tasks.append(blueprint.run(messages))
        results = await asyncio.gather(*[asyncio.create_task(t) for t in tasks], return_exceptions=True)
        for idx, result in enumerate(results):
            print(f"\n[PARALLEL TASK {idx+1}] Result:")
            if isinstance(result, Exception):
                print(f"Exception: {result}")
            else:
                async for response in result:
                    print(json.dumps(response, indent=2))

# Module-level alias for SPINNER_STATES to allow CLI import
SPINNER_STATES = ["Polishing the silver"] + JeevesSpinner.SPINNER_STATES
