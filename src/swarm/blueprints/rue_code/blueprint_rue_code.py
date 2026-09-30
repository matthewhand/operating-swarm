"""
RueCode Blueprint

Viral docstring update: Operational as of 2025-04-18T10:14:18Z (UTC).
Self-healing, fileops-enabled, swarm-scalable.

.. warning::

   **This seat does not answer.** The fileops / shell / cost tools below are
   real ``function_tool``s, but they are never handed to a model, so there is
   no model turn behind this seat. It used to reply with a hardcoded
   "Code Results / Semantic Results" table instead, which reads as an analysis
   of your repo and is not one. :meth:`RueCodeBlueprint.run` now returns the
   shared honest refusal and marks the seat broken via ``seat_health``. Wire an
   ``Agent`` to the tools above to make it real.
"""
import logging
import os
import shlex
import subprocess
import time
from pathlib import Path

from swarm.blueprints.common import unavailable_seat as unavailable
from swarm.blueprints.common.operation_box_utils import display_operation_box
from swarm.core.blueprint_ux import BlueprintUX
from swarm.core.config_loader import load_full_configuration

#: Why this seat cannot answer, and what to use instead.
NO_MODEL_WIRING_REASON = (
    "this recipe's fileops / shell / cost tools are never handed to a model, so "
    "there is no agent behind it to produce a turn"
)
NO_MODEL_WIRING_REMEDY = (
    "use `cli_agent` or `cli_map` for file-backed work, `codey` for code "
    "generation, or attach these tools to an `Agent` to make this seat real"
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Last swarm update: {{ datetime.now(pytz.utc).strftime('%Y-%m-%dT%H:%M:%SZ') }}
# Patch: Expose underlying fileops functions for direct testing
from agents import function_tool


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
    Security Note: Ensure commands are properly sanitized or restricted.
    Timeout is configurable via SWARM_COMMAND_TIMEOUT (default: 60s).
    """
    logger.info(f"Executing shell command: {command}")
    try:
        import os
        timeout = int(os.getenv("SWARM_COMMAND_TIMEOUT", "60"))
        result = subprocess.run(
            shlex.split(command),
            shell=False,
            check=False, # Don't raise exception on non-zero exit code
            capture_output=True,
            text=True,
            timeout=timeout
        )
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
read_file_tool = function_tool(read_file)
write_file_tool = function_tool(write_file)
list_files_tool = function_tool(list_files)
execute_shell_command_tool = function_tool(execute_shell_command)

# Attempt to import BlueprintBase, handle potential ImportError during early setup/testing
try:
    from swarm.core.blueprint_base import BlueprintBase
except ImportError as e:
    logger.error(f"Import failed: {e}. Check 'openai-agents' install and project structure.")
    # *** REMOVED sys.exit(1) ***
    # Define a dummy class if import fails, allowing module to load for inspection/debugging
    class BlueprintBase:
        metadata = {}
        def __init__(self, *args, **kwargs): pass
        async def run(self, *args, **kwargs): yield {}

# --- Tool Definitions ---

def execute_shell_command(command: str) -> str:
    """
    Executes a shell command and returns its stdout and stderr.
    Security Note: Ensure commands are properly sanitized or restricted.
    """
    logger.info(f"Executing shell command: {command}")
    try:
        result = subprocess.run(
            shlex.split(command),
            shell=False,
            check=False, # Don't raise exception on non-zero exit code
            capture_output=True,
            text=True,
            timeout=60 # Add a timeout
        )
        output = f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        logger.info(f"Command finished. Exit Code: {result.returncode}")
        return output.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {command}")
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        logger.error(f"Error executing command '{command}': {e}", exc_info=True)
        return f"Error executing command: {e}"

def read_file(file_path: str) -> str:
    """Reads the content of a specified file."""
    logger.info(f"📄 Reading file: {file_path}")
    try:
        if ".." in file_path:
            logger.warning(f"Attempted path traversal detected in read_file: {file_path}")
            return "\033[91m❌ Error: Invalid file path (potential traversal).\033[0m"
        path = Path(file_path)
        if not path.is_file():
            logger.warning(f"File not found: {file_path}")
            return f"\033[91m❌ Error: File not found at {file_path}\033[0m"
        content = path.read_text(encoding='utf-8')
        logger.info(f"Successfully read {len(content)} characters from {file_path}")
        max_len = 10000
        if len(content) > max_len:
            logger.warning(f"File {file_path} truncated to {max_len} characters.")
            return f"\033[93m⚠️ {content[:max_len]}\n... [File Truncated]\033[0m"
        return f"\033[92m✅ File read successfully!\033[0m\n\033[94m{content}\033[0m"
    except Exception as e:
        logger.error(f"Error reading file '{file_path}': {e}", exc_info=True)
        return f"\033[91m❌ Error reading file: {e}\033[0m"

def write_file(file_path: str, content: str) -> str:
    """Writes content to a specified file, creating directories if needed."""
    logger.info(f"✏️ Writing to file: {file_path}")
    try:
        if ".." in file_path:
            logger.warning(f"Attempted path traversal detected in write_file: {file_path}")
            return "\033[91m❌ Error: Invalid file path (potential traversal).\033[0m"
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        logger.info(f"Successfully wrote {len(content)} characters to {file_path}")
        return f"\033[92m✅ Successfully wrote to {file_path}\033[0m"
    except Exception as e:
        logger.error(f"Error writing file '{file_path}': {e}", exc_info=True)
        return f"\033[91m❌ Error writing file: {e}\033[0m"

def list_files(directory_path: str = ".") -> str:
    """Lists files and directories in a specified path."""
    logger.info(f"Listing files in directory: {directory_path}")
    try:
        # Basic path traversal check
        if ".." in directory_path:
             logger.warning(f"Attempted path traversal detected in list_files: {directory_path}")
             return "Error: Invalid directory path (potential traversal)."
        # Consider restricting base path

        path = Path(directory_path)
        if not path.is_dir():
            return f"Error: Directory not found at {directory_path}"

        entries = []
        for entry in path.iterdir():
            entry_type = "d" if entry.is_dir() else "f"
            entries.append(f"{entry_type} {entry.name}")

        logger.info(f"Found {len(entries)} entries in {directory_path}")
        return "\n".join(entries) if entries else "Directory is empty."
    except Exception as e:
        logger.error(f"Error listing files in '{directory_path}': {e}", exc_info=True)
        return f"Error listing files: {e}"

# --- FileOps Tool Logic Definitions ---
def read_file_fileops(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"ERROR: {e}"
def write_file_fileops(path: str, content: str) -> str:
    try:
        with open(path, 'w') as f:
            f.write(content)
        return "OK: file written"
    except Exception as e:
        return f"ERROR: {e}"
def list_files_fileops(directory: str = '.') -> str:
    try:
        return '\n'.join(os.listdir(directory))
    except Exception as e:
        return f"ERROR: {e}"
def execute_shell_command_fileops(command: str) -> str:
    import subprocess
    try:
        result = subprocess.run(shlex.split(command), shell=False, capture_output=True, text=True)
        return result.stdout + result.stderr
    except Exception as e:
        return f"ERROR: {e}"

# --- LLM Cost Estimation Tool ---
def calculate_llm_cost(model: str, prompt_tokens: int, completion_tokens: int = 0, config: dict = None) -> float:
    """
    Calculate the estimated cost (USD) for an LLM API call based on model and token usage.
    Pricing is pulled from swarm_config.json if available, else defaults.
    """
    # Default prices (per 1K tokens)
    default_price = {'prompt': 0.002, 'completion': 0.004}
    price = None
    model_key = model.lower()
    if config:
        llm_config = config.get('llm', {})
        for key, val in llm_config.items():
            m = val.get('model', '').lower()
            if m == model_key or key.lower() == model_key:
                # Support both single cost (same for prompt/completion) or dict
                if isinstance(val.get('cost'), dict):
                    price = val['cost']
                elif 'cost' in val:
                    price = {'prompt': float(val['cost']), 'completion': float(val['cost'])}
                break
    if price is None:
        price = default_price
    cost = (prompt_tokens / 1000.0) * price['prompt'] + (completion_tokens / 1000.0) * price['completion']
    return round(cost, 6)

def llm_cost_tool(model: str, prompt_tokens: int, completion_tokens: int = 0, config: dict = None) -> str:
    try:
        cost = calculate_llm_cost(model, prompt_tokens, completion_tokens, config)
        return f"Estimated cost for {model}: ${cost} (prompt: {prompt_tokens}, completion: {completion_tokens} tokens)"
    except Exception as e:
        return f"Error: {e}"

llm_cost_tool_fn = function_tool(llm_cost_tool, strict_mode=False)  # config:dict param needs relaxed schema

# --- RueCodeBlueprint Definition ---
# === OpenAI GPT-4.1 Prompt Engineering Guide ===
# See: https://github.com/openai/openai-cookbook/blob/main/examples/gpt4-1_prompting_guide.ipynb
#
# Agentic System Prompt Example (recommended for code generation/repair agents):
SYS_PROMPT_AGENTIC = """
You are an agent - please keep going until the user’s query is completely resolved, before ending your turn and yielding back to the user. Only terminate your turn when you are sure that the problem is solved.
If you are not sure about file content or codebase structure pertaining to the user’s request, use your tools to read files and gather the relevant information: do NOT guess or make up an answer.
You MUST plan extensively before each function call, and reflect extensively on the outcomes of the previous function calls. DO NOT do this entire process by making function calls only, as this can impair your ability to solve the problem and think insightfully.
"""

class RueSpinner:
    FRAMES = ["Generating.", "Generating..", "Generating...", "Running..."]
    LONG_WAIT_MSG = "Generating... Taking longer than expected"
    INTERVAL = 0.12
    SLOW_THRESHOLD = 10

    def __init__(self):
        self._idx = 0
        self._start_time = None
        self._last_frame = self.FRAMES[0]

    def start(self):
        self._start_time = time.time()
        self._idx = 0
        self._last_frame = self.FRAMES[0]

    def _spin(self):
        self._idx = (self._idx + 1) % len(self.FRAMES)
        self._last_frame = self.FRAMES[self._idx]

    def current_spinner_state(self):
        if self._start_time and (time.time() - self._start_time) > self.SLOW_THRESHOLD:
            return self.LONG_WAIT_MSG
        return self._last_frame

class RueCodeBlueprint(BlueprintBase):
    """
    A blueprint designed for code generation, execution, and file system interaction.
    Uses Jinja2 for templating prompts and provides tools for shell commands and file operations.
    """
    metadata = {
        **unavailable.placeholder_metadata(),
        "name": "RueCode",
        "title": "Rue Code (tool seat — not wired to a model)",
        "description": (
            "Fileops / shell / cost tools, not yet attached to an agent. This "
            "seat does not answer; use cli_agent or codey for real turns."
        ),
        "author": "Matthew Hand",
        "version": "0.1.0",
        "tags": ["code", "execution", "filesystem", "developer", "placeholder"],
        "llm_profile": "default_dev"  # Example: Suggests a profile suitable for coding
    }

    def __init__(self, blueprint_id: str = "rue_code", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self.blueprint_id = blueprint_id
        self.config_path = config_path
        self._config = config if config is not None else None
        self._llm_profile_name = None
        self._llm_profile_data = None
        self._markdown_output = None
        # Use standardized config loader
        if self._config is None:
            self._config = load_full_configuration(
                blueprint_class_name=self.__class__.__name__,
                config_path_override=config_path,
                profile_override=None,
                cli_config_overrides=None
            )
        # Minimal LLM stub for demo
        class DummyLLM:
            def chat_completion_stream(self, messages, **_):
                class DummyStream:
                    def __aiter__(self): return self
                    async def __anext__(self):
                        raise StopAsyncIteration
                return DummyStream()
        self.llm = DummyLLM()
        # Use silly style for RueCode
        self.ux = BlueprintUX(style="silly")
        self.spinner = RueSpinner()

    def render_prompt(self, template_name: str, context: dict) -> str:
        # Minimal fallback: just format the user request directly for now
        # (No Jinja2 dependency, just a stub for demo)
        return f"User request: {context.get('user_request', '')}\nHistory: {context.get('history', '')}\nAvailable tools: {', '.join(context.get('available_tools', []))}"

    def code_vs_semantic(self, label, results):
        """Format code or semantic results for display."""
        return f"{label.title()} Results:\n" + "\n".join(f"- {r}" for r in results)

    def summary(self, label, count, params):
        return f"{label} ({count} results) for: {params}"

    async def run(self, messages: list[dict[str, str]], **kwargs):
        # **kwargs: the API layer passes options like stream=; accept and ignore.
        #
        # The fileops and shell tools above are real `function_tool`s, but nothing
        # ever handed them to a model: this recipe carried a `DummyLLM` and
        # returned a hardcoded "Code Results / Semantic Results" table built from
        # two literal strings. The agent sweep scored that 1.9s table as a reply,
        # which is worse than an error — it looks like analysis of *your* repo and
        # is fiction. There is no prompt this seat can honestly answer, so it says
        # so instead of generating one.
        logger.info("RueCodeBlueprint run method called.")
        last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), None)
        if not last_user_message:
            display_operation_box(
                title="RueCode Error",
                content="I need a user message to proceed.",
                emoji="📝"
            )
            yield {"messages": [{"role": "assistant", "content": self.ux.box("Error", "I need a user message to proceed.")}]}
            return
        yield unavailable.cannot_answer_chunk(
            self.blueprint_id or "rue_code",
            why=NO_MODEL_WIRING_REASON,
            remedy=NO_MODEL_WIRING_REMEDY,
            backends=["rue_code"],
        )
        logger.info("RueCodeBlueprint run finished (no model wiring).")

if __name__ == "__main__":
    import asyncio
    print("\033[1;36m\n╔══════════════════════════════════════════════════════════════╗\n║   📝 RUE CODE: SWARM TEMPLATING & EXECUTION DEMO             ║\n╠══════════════════════════════════════════════════════════════╣\n║ This blueprint demonstrates viral doc propagation,           ║\n║ code templating, and swarm-powered execution.                ║\n║ Try running: python blueprint_rue_code.py                    ║\n╚══════════════════════════════════════════════════════════════╝\033[0m")
    messages = [
        {"role": "user", "content": "Show me how Rue Code does templating and swarm execution."}
    ]
    blueprint = RueCodeBlueprint(blueprint_id="demo-1")
    async def run_and_print():
        spinner = RueSpinner()
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
            title="RueCode Output",
            content="\n".join(all_results),
            style="bold green",
            result_count=len(all_results),
            params={"prompt": messages[0]["content"]},
            op_type="rue_code"
        )
    asyncio.run(run_and_print())
