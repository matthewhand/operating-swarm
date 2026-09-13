"""
WhiskeyTangoFoxtrot: Tracking Free Online Services

A chaotic spy-themed blueprint with a multi-tiered agent hierarchy for tracking and managing free online services using SQLite and web search capabilities.
Uses BlueprintBase and agent-as-tool delegation.
"""

from agents.mcp import MCPServer
import os
from dotenv import load_dotenv; load_dotenv(override=True)

import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, ClassVar

# Ensure src is in path for BlueprintBase import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path: sys.path.insert(0, src_path)

try:
    # Runner/Tool/function_tool probed for optional openai-agents; Agent/Model used at runtime.
    from agents import Agent, Runner, Tool, function_tool  # noqa: F401
    from agents.models.interface import Model
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from swarm.core.blueprint_base import BlueprintBase
    from swarm.core.blueprint_ux import BlueprintUXImproved
except ImportError as e:
    print(f"ERROR: Import failed in WhiskeyTangoFoxtrotBlueprint: {e}. Check dependencies.")
    print(f"sys.path: {sys.path}")
    sys.exit(1)

logger = logging.getLogger(__name__)

# --- Database Path ---
# Defined here for clarity, sourced from env var via BlueprintBase config loading primarily
SQLITE_DB_PATH_STR = os.getenv("SQLITE_DB_PATH", "./wtf_services.db") # Default if not set
SQLITE_DB_PATH = Path(SQLITE_DB_PATH_STR).resolve()

# --- Agent Instructions ---

valory_instructions = """
You are Valory, the top-tier coordinator for Operation Freebie Freedom.
Your mission: Track and manage information about free online services based on user requests.
Delegate tasks to your middle managers:
- Tyril (DB Manager): Use the `Tyril` agent tool for tasks involving storing, retrieving, or updating service info in the database, or managing related files.
- Tray (Web Manager): Use the `Tray` agent tool for tasks involving searching for new services, fetching details from the web, or processing web data.
Synthesize reports from Tyril and Tray into a final response for the user.
Available Agent Tools: Tyril, Tray.
"""

tyril_instructions = """
You are Tyril, middle manager for database and filesystem operations under Valory.
Your mission: Manage the 'services' database and temporary files.
Delegate specific tasks to your minions:
- Larry (Filesystem): Use the `Larry` agent tool for creating, reading, or deleting temporary files related to service data.
- Kriegs (DB Updates): Use the `Kriegs` agent tool for ALL interactions with the 'services' SQLite database (add, update, delete, query records).
You have direct access to the `sqlite` MCP tool for read-only queries if needed, but prefer delegating writes/updates to Kriegs.
Report results or completion status back to Valory.
Available MCP Tools (Direct Use - Read Only Recommended): sqlite.
Available Agent Tools: Larry, Kriegs.
"""

tray_instructions = """
You are Tray, middle manager for web data operations under Valory.
Your mission: Find and process information about free online services from the web.
Delegate specific tasks to your minions:
- Vanna (Web Search/Fetch): Use the `Vanna` agent tool to find service URLs (via brave-search) and fetch content from those URLs (via mcp-npx-fetch).
- Marcher (Data Processing): Use the `Marcher` agent tool to process raw fetched data (using mcp-doc-forge) into a structured format (name, type, url, api_key, usage_limits, documentation_link).
Coordinate the flow: Task Vanna, receive results, task Marcher with Vanna's results, receive structured data.
Report the final structured data back to Valory.
Available Agent Tools: Vanna, Marcher.
"""

larry_instructions = """
You are Larry, filesystem minion under Tyril.
Your mission: Manage temporary files using the `filesystem` MCP tool within the allowed path.
Tasks include storing fetched web content temporarily, reading data for processing, or deleting temp files.
Report success or failure of file operations back to Tyril.
Available MCP Tools: filesystem.
"""

kriegs_instructions = """
You are Kriegs, database minion under Tyril.
Your mission: Perform CRUD (Create, Read, Update, Delete) operations on the 'services' table in the SQLite database using the `sqlite` MCP tool.
The table schema is: (id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL, url TEXT, api_key TEXT, usage_limits TEXT, documentation_link TEXT).
Receive structured data (usually from Tyril, originating from Marcher) and perform the requested database action (INSERT, UPDATE, DELETE, SELECT).
Report the outcome (e.g., "Successfully added Fly.io", "Error updating Grok entry", "Deleted service X", "Found 3 services of type AI") back to Tyril.
Available MCP Tools: sqlite.
"""

vanna_instructions = """
You are Vanna, web search and fetch minion under Tray.
Your mission: Find URLs for specified services and fetch content from those URLs.
1. Use the `brave-search` MCP tool to find the official website or documentation URL for a service name provided by Tray.
2. Use the `mcp-npx-fetch` MCP tool to retrieve the content (HTML or text) from the URL found.
Report the fetched content (or any errors like URL not found/fetch failed) back to Tray.
Available MCP Tools: brave-search, mcp-npx-fetch.
"""

marcher_instructions = """
You are Marcher, data processing minion under Tray.
Your mission: Process raw web content (fetched by Vanna) into structured data using the `mcp-doc-forge` MCP tool.
Receive raw text/HTML content and the original service name/type from Tray.
Use `mcp-doc-forge` (likely its text extraction or summarization functions) to extract: name, type, url, api_key (if mentioned), usage_limits, documentation_link.
Report the structured data (as JSON or a clear key-value format) back to Tray.
Available MCP Tools: mcp-doc-forge.
"""

# --- Define the Blueprint ---
class WhiskeyTangoFoxtrotBlueprint(BlueprintBase):
    """Tracks free online services with a hierarchical spy-inspired agent team using SQLite and web search."""
    metadata: ClassVar[dict[str, Any]] = {
        "name": "WhiskeyTangoFoxtrotBlueprint",
        "title": "WhiskeyTangoFoxtrot Service Tracker",
        "description": "Tracks free online services with SQLite and web search using a multi-tiered agent hierarchy.",
        "version": "1.2.0", # Refactored version
        "author": "Open Swarm Team (Refactored)",
        "tags": ["web scraping", "database", "sqlite", "multi-agent", "hierarchy", "mcp"],
        "required_mcp_servers": ["sqlite", "brave-search", "mcp-npx-fetch", "mcp-doc-forge", "filesystem"],
        "env_vars": ["BRAVE_API_KEY", "SQLITE_DB_PATH", "ALLOWED_PATH"], # Actual required vars
        # Capability-based tool needs (see swarm.core.tool_capabilities): this
        # scraper wants real browser automation — auto-provisioned from the
        # non-auth official microsoft/playwright-mcp.
        "tool_requirements": {"browser": "mandatory", "web_search": "optional"},
    }

    # Caches
    _openai_client_cache: dict[str, AsyncOpenAI] = {}
    _model_instance_cache: dict[str, Model] = {}

    def __init__(self, blueprint_id: str = "whiskeytangofoxtrot", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id=blueprint_id, config=config, config_path=config_path, **kwargs)
        self.blueprint_id = blueprint_id
        self.config_path = config_path
        self._config = config if config is not None else None
        self._llm_profile_name = None
        self._llm_profile_data = None
        self._markdown_output = None
        # Add other attributes as needed for WhiskeyTangoFoxtrot
        # ...

    def initialize_db(self) -> None:
        """Initializes the SQLite database schema if not present."""
        db_path = SQLITE_DB_PATH
        logger.info(f"Ensuring database schema exists at: {db_path}")
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='services';")
            if not cursor.fetchone():
                logger.info("Initializing 'services' table in SQLite database.")
                cursor.execute("""
                    CREATE TABLE services (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        type TEXT NOT NULL,
                        url TEXT,
                        api_key TEXT,
                        usage_limits TEXT,
                        documentation_link TEXT,
                        last_checked TEXT
                    );
                """)
                conn.commit()
                logger.info("'services' table created.")
            else:
                 logger.debug("'services' table already exists.")
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"SQLite error during DB initialization: {e}", exc_info=True)
            # Depending on severity, you might want to raise this
            # raise RuntimeError(f"Failed to initialize database: {e}") from e
        except Exception as e:
             logger.error(f"Unexpected error during DB initialization: {e}", exc_info=True)
             # raise RuntimeError(f"Failed to initialize database: {e}") from e


    # --- Model Instantiation Helper --- (Standard helper)
    def _get_model_instance(self, profile_name: str) -> Model:
        """Retrieves or creates an LLM Model instance."""
        # ... (Implementation is the same as previous refactors) ...
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")
        profile_data = self.get_llm_profile(profile_name)
        if not profile_data: raise ValueError(f"Missing LLM profile '{profile_name}'.")
        provider = profile_data.get("provider", "openai").lower()
        model_name = profile_data.get("model")
        if not model_name: raise ValueError(f"Missing 'model' in profile '{profile_name}'.")
        from swarm.core.llm_provider import is_openai_chat_provider
        if not is_openai_chat_provider(provider):
            raise ValueError(f"Unsupported provider: {provider}")
        client_cache_key = f"{provider}_{profile_data.get('base_url')}"
        if client_cache_key not in self._openai_client_cache:
             client_kwargs = { "api_key": profile_data.get("api_key"), "base_url": profile_data.get("base_url") }
             filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}
             log_kwargs = {k:v for k,v in filtered_kwargs.items() if k != 'api_key'}
             logger.debug(f"Creating new AsyncOpenAI client for '{profile_name}': {log_kwargs}")
             try: self._openai_client_cache[client_cache_key] = AsyncOpenAI(**filtered_kwargs)
             except Exception as e: raise ValueError(f"Failed to init client: {e}") from e
        client = self._openai_client_cache[client_cache_key]
        logger.debug(f"Instantiating OpenAIChatCompletionsModel(model='{model_name}') for '{profile_name}'.")
        try:
            model_instance = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
            self._model_instance_cache[profile_name] = model_instance
            return model_instance
        except Exception as e: raise ValueError(f"Failed to init LLM: {e}") from e


    def render_prompt(self, template_name: str, context: dict) -> str:
        return f"User request: {context.get('user_request', '')}\nHistory: {context.get('history', '')}\nAvailable tools: {', '.join(context.get('available_tools', []))}"


    async def run(self, messages: list[dict], **kwargs):
        """Main execution entry point for the WhiskeyTangoFoxtrot blueprint."""
        logger.info("WhiskeyTangoFoxtrotBlueprint run method called.")
        instruction = messages[-1].get("content", "") if messages else ""
        # --- Test Mode: yield a canned answer immediately, never spawn the
        # multi-tier agent loop (which hangs without a live LLM). ---
        if os.environ.get("SWARM_TEST_MODE"):
            yield {"messages": [{"role": "assistant", "content": f"[TEST-MODE] WhiskeyTangoFoxtrot tracking free services. You said: '{instruction}'"}]}
            return
        from agents import Runner
        ux = BlueprintUXImproved(style="serious")
        spinner_idx = 0
        start_time = time.time()
        spinner_yield_interval = 1.0  # seconds
        last_spinner_time = start_time
        yielded_spinner = False
        result_chunks = []
        try:
            runner_gen = Runner.run(self.create_starting_agent([]), instruction)
            while True:
                now = time.time()
                try:
                    chunk = next(runner_gen)
                    result_chunks.append(chunk)
                    # If chunk is a final result, wrap and yield
                    if chunk and isinstance(chunk, dict) and "messages" in chunk:
                        content = chunk["messages"][0]["content"] if chunk["messages"] else ""
                        summary = ux.summary("Operation", len(result_chunks), {"instruction": instruction[:40]})
                        box = ux.ansi_emoji_box(
                            title="WhiskeyTangoFoxtrot Result",
                            content=content,
                            summary=summary,
                            params={"instruction": instruction[:40]},
                            result_count=len(result_chunks),
                            op_type="run",
                            status="success"
                        )
                        yield {"messages": [{"role": "assistant", "content": box}]}
                    else:
                        yield chunk
                    yielded_spinner = False
                except StopIteration:
                    break
                except Exception:
                    if now - last_spinner_time >= spinner_yield_interval:
                        taking_long = (now - start_time > 10)
                        spinner_msg = ux.spinner(spinner_idx, taking_long=taking_long)
                        yield {"messages": [{"role": "assistant", "content": spinner_msg}]}
                        spinner_idx += 1
                        last_spinner_time = now
                        yielded_spinner = True
            if not result_chunks and not yielded_spinner:
                yield {"messages": [{"role": "assistant", "content": ux.spinner(0)}]}
        except Exception as e:
            logger.error(f"Error during WhiskeyTangoFoxtrot run: {e}", exc_info=True)
            yield {"messages": [{"role": "assistant", "content": f"An error occurred: {e}"}]}
        return


    def create_starting_agent(self, mcp_servers: list[MCPServer]) -> Agent:
        """Creates the WTF agent hierarchy and returns Valory (Coordinator)."""
        # Ensure config is loaded (defensive fix for tests/patching)
        if self._config is None:
            self._load_configuration()
        self.initialize_db() # Ensure DB is ready

        logger.debug("Creating WhiskeyTangoFoxtrot agent team...")
        self._model_instance_cache = {}
        self._openai_client_cache = {}

        default_profile_name = self.config.get("llm_profile", "default")
        logger.debug(f"Using LLM profile '{default_profile_name}' for WTF agents.")
        model_instance = self._get_model_instance(default_profile_name)

        # Helper to filter started MCP servers
        def get_agent_mcps(names: list[str]) -> list[MCPServer]:
            started_names = {s.name for s in mcp_servers}
            required_found = [name for name in names if name in started_names]
            if len(required_found) != len(names):
                missing = set(names) - started_names
                logger.warning(f"Agent needing {names} is missing started MCP(s): {', '.join(missing)}")
            return [s for s in mcp_servers if s.name in required_found]

        # Instantiate all agents first
        agents: dict[str, Agent] = {}

        agents["Larry"] = Agent(name="Larry", model=model_instance, instructions=larry_instructions, tools=[], mcp_servers=get_agent_mcps(["filesystem"]))
        agents["Kriegs"] = Agent(name="Kriegs", model=model_instance, instructions=kriegs_instructions, tools=[], mcp_servers=get_agent_mcps(["sqlite"]))
        agents["Vanna"] = Agent(name="Vanna", model=model_instance, instructions=vanna_instructions, tools=[], mcp_servers=get_agent_mcps(["brave-search", "mcp-npx-fetch"]))
        agents["Marcher"] = Agent(name="Marcher", model=model_instance, instructions=marcher_instructions, tools=[], mcp_servers=get_agent_mcps(["mcp-doc-forge"]))

        agents["Tyril"] = Agent(
            name="Tyril", model=model_instance, instructions=tyril_instructions,
            tools=[ # Tools for delegating to minions
                agents["Larry"].as_tool(tool_name="Larry", tool_description="Delegate filesystem tasks (temp files)."),
                agents["Kriegs"].as_tool(tool_name="Kriegs", tool_description="Delegate SQLite database operations (CRUD).")
            ],
            mcp_servers=get_agent_mcps(["sqlite"]) # Tyril might read DB directly
        )
        agents["Tray"] = Agent(
            name="Tray", model=model_instance, instructions=tray_instructions,
            tools=[ # Tools for delegating to minions
                 agents["Vanna"].as_tool(tool_name="Vanna", tool_description="Delegate web search/fetch tasks."),
                 agents["Marcher"].as_tool(tool_name="Marcher", tool_description="Delegate processing/structuring of fetched web data.")
            ],
            mcp_servers=[] # Tray coordinates web minions
        )

        agents["Valory"] = Agent(
            name="Valory", model=model_instance, instructions=valory_instructions,
            tools=[ # Tools for delegating to middle managers
                agents["Tyril"].as_tool(tool_name="Tyril", tool_description="Delegate database and filesystem management tasks."),
                agents["Tray"].as_tool(tool_name="Tray", tool_description="Delegate web data fetching and processing tasks.")
            ],
            mcp_servers=[] # Coordinator doesn't directly use MCPs
        )

        logger.debug("WhiskeyTangoFoxtrot agents created. Starting with Valory.")
        return agents["Valory"]

# Standard Python entry point
if __name__ == "__main__":
    import asyncio
    import json
    messages = [
        {"role": "user", "content": "WTF is going on?"}
    ]
    blueprint = WhiskeyTangoFoxtrotBlueprint(blueprint_id="demo-1")
    async def run_and_print():
        async for response in blueprint.run(messages):
            print(json.dumps(response, indent=2))
    asyncio.run(run_and_print())
