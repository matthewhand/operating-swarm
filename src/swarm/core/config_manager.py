# src/swarm/extensions/config/config_manager.py

import json
import logging
import shutil
import sys
from typing import Any

from swarm.settings import DEBUG
from swarm.utils.redact import redact_sensitive_data


def prompt_user(prompt: str) -> str:
    """Prompt the user for input via CLI and return the response."""
    return input(prompt + " ")

# Initialize logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
if not logger.handlers:
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s - %(message)s")
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

CONFIG_BACKUP_SUFFIX = ".backup"

def resolve_placeholders(config):
    # Recursively resolve placeholders in the config dict (env vars, etc.)
    import os
    import re
    pattern = re.compile(r'\$\{([^}]+)\}')
    def _resolve(val):
        if isinstance(val, str):
            def replacer(match):
                var = match.group(1)
                return os.environ.get(var, match.group(0))
            return pattern.sub(replacer, val)
        elif isinstance(val, dict):
            return {k: _resolve(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [_resolve(v) for v in val]
        return val
    return _resolve(config)

def backup_configuration(config_path: str) -> None:
    """
    Create a backup of the existing configuration file.

    Args:
        config_path (str): Path to the configuration file.
    """
    backup_path = config_path + CONFIG_BACKUP_SUFFIX
    try:
        shutil.copy(config_path, backup_path)
        logger.info(f"Configuration backup created at '{backup_path}'")
        print(f"Backup of configuration created at '{backup_path}'")
    except Exception as e:
        logger.error(f"Failed to create configuration backup: {e}")
        print(f"Failed to create backup: {e}")
        sys.exit(1)

def load_config(config_path: str) -> dict[str, Any]:
    """
    Load the server configuration from a JSON file and resolve placeholders.

    Args:
        config_path (str): Path to the configuration file.

    Returns:
        Dict[str, Any]: The resolved configuration.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file contains invalid JSON or unresolved placeholders.
    """
    try:
        with open(config_path) as file:
            config = json.load(file)
            logger.debug("Raw configuration loaded: %s", redact_sensitive_data(config))
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}")
        print(f"Configuration file not found at {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file {config_path}: {e}")
        print(f"Invalid JSON in configuration file {config_path}: {e}")
        sys.exit(1)

    # Resolve placeholders recursively
    try:
        resolved_config = resolve_placeholders(config)
        logger.debug(
            "Configuration after resolving placeholders: %s",
            redact_sensitive_data(resolved_config),
        )
    except Exception as e:
        logger.error(f"Failed to resolve placeholders in configuration: {e}")
        print(f"Failed to resolve placeholders in configuration: {e}")
        sys.exit(1)

    return resolved_config

def save_config(config_path: str, config: dict[str, Any]) -> None:
    """
    Save the updated configuration to the config file.

    Args:
        config_path (str): Path to the configuration file.
        config (Dict[str, Any]): Configuration dictionary to save.

    Raises:
        SystemExit: If saving the configuration fails.
    """
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        logger.info(f"Configuration saved to '{config_path}'")
        print(f"Configuration saved to '{config_path}'")
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        print(f"Failed to save configuration: {e}")
        sys.exit(1)

def add_llm(config_path: str) -> None:
    """
    Add a new LLM to the configuration.

    Args:
        config_path (str): Path to the configuration file.
    """
    config = load_config(config_path)
    print("Starting the process to add a new LLM.")

    while True:
        llm_name = prompt_user("Enter the name of the new LLM (or type 'done' to finish)").strip()
        print(f"User entered LLM name: {llm_name}")
        if llm_name.lower() == 'done':
            print("Finished adding LLMs.")
            break
        if not llm_name:
            print("LLM name cannot be empty.")
            continue

        if llm_name in config.get("llm", {}):
            print(f"LLM '{llm_name}' already exists.")
            continue

        llm = {}
        llm["provider"] = prompt_user("Enter the provider type (e.g., 'openai', 'ollama')").strip()
        llm["model"] = prompt_user("Enter the model name (e.g., 'gpt-4')").strip()
        llm["base_url"] = prompt_user("Enter the base URL for the API").strip()
        llm_api_key_input = prompt_user("Enter the environment variable for the API key (e.g., 'OPENAI_API_KEY') or leave empty if not required").strip()
        if llm_api_key_input:
            llm["api_key"] = f"${{{llm_api_key_input}}}"
        else:
            llm["api_key"] = ""
        try:
            temperature_input = prompt_user("Enter the temperature (e.g., 0.7)").strip()
            llm["temperature"] = float(temperature_input)
        except ValueError:
            print("Invalid temperature value. Using default 0.7.")
            llm["temperature"] = 0.7

        config.setdefault("llm", {})[llm_name] = llm
        logger.info(f"Added LLM '{llm_name}' to configuration.")
        print(f"LLM '{llm_name}' added.")

    backup_configuration(config_path)
    save_config(config_path, config)
    print("LLM configuration process completed.")

def remove_llm(config_path: str, llm_name: str) -> None:
    """
    Remove an existing LLM from the configuration.

    Args:
        config_path (str): Path to the configuration file.
        llm_name (str): Name of the LLM to remove.
    """
    config = load_config(config_path)

    if llm_name not in config.get("llm", {}):
        print(f"LLM '{llm_name}' does not exist.")
        return

    confirm = prompt_user(f"Are you sure you want to remove LLM '{llm_name}'? (yes/no)").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Operation cancelled.")
        return

    del config["llm"][llm_name]
    backup_configuration(config_path)
    save_config(config_path, config)
    print(f"LLM '{llm_name}' has been removed.")
    logger.info(f"Removed LLM '{llm_name}' from configuration.")

def add_mcp_server(config_path: str) -> None:
    """
    Add a new MCP server to the configuration.

    Args:
        config_path (str): Path to the configuration file.
    """
    config = load_config(config_path)
    print("Starting the process to add a new MCP server.")

    while True:
        server_name = prompt_user("Enter the name of the new MCP server (or type 'done' to finish)").strip()
        print(f"User entered MCP server name: {server_name}")
        if server_name.lower() == 'done':
            print("Finished adding MCP servers.")
            break
        if not server_name:
            print("Server name cannot be empty.")
            continue

        if server_name in config.get("mcpServers", {}):
            print(f"MCP server '{server_name}' already exists.")
            continue

        server = {}
        server["command"] = prompt_user("Enter the command to run the MCP server (e.g., 'npx', 'uvx')").strip()
        args_input = prompt_user("Enter the arguments as a JSON array (e.g., [\"-y\", \"server-name\"])").strip()
        try:
            server["args"] = json.loads(args_input)
            if not isinstance(server["args"], list):
                raise ValueError
        except ValueError:
            print("Invalid arguments format. Using an empty list.")
            server["args"] = []

        env_vars = {}
        add_env = prompt_user("Do you want to add environment variables? (yes/no)").strip().lower()
        while add_env in ['yes', 'y']:
            env_var = prompt_user("Enter the environment variable name").strip()
            env_value = prompt_user(f"Enter the value or placeholder for '{env_var}' (e.g., '${{{env_var}_KEY}}')").strip()
            if env_var and env_value:
                env_vars[env_var] = env_value
            add_env = prompt_user("Add another environment variable? (yes/no)").strip().lower()

        server["env"] = env_vars

        config.setdefault("mcpServers", {})[server_name] = server
        logger.info(f"Added MCP server '{server_name}' to configuration.")
        print(f"MCP server '{server_name}' added.")

    backup_configuration(config_path)
    save_config(config_path, config)
    print("MCP server configuration process completed.")

def remove_mcp_server(config_path: str, server_name: str) -> None:
    """
    Remove an existing MCP server from the configuration.

    Args:
        config_path (str): Path to the configuration file.
        server_name (str): Name of the MCP server to remove.
    """
    config = load_config(config_path)

    if server_name not in config.get("mcpServers", {}):
        print(f"MCP server '{server_name}' does not exist.")
        return

    confirm = prompt_user(f"Are you sure you want to remove MCP server '{server_name}'? (yes/no)").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Operation cancelled.")
        return

    del config["mcpServers"][server_name]
    backup_configuration(config_path)
    save_config(config_path, config)
    print(f"MCP server '{server_name}' has been removed.")
    logger.info(f"Removed MCP server '{server_name}' from configuration.")
