import json
import logging
import os
from pathlib import Path
from typing import Any

from .paths import (  # Import XDG path functions
    get_project_root_dir,
    get_swarm_config_file,
)

logger = logging.getLogger("swarm.config")

DEFAULT_CONFIG_FILENAME = "swarm_config.json"

def _substitute_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        # Always expand env vars in any string
        return os.path.expandvars(value)
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    return value

# Backwards-compatible alias (formerly in swarm.extensions.config.config_loader).
_substitute_env_vars_recursive = _substitute_env_vars

def _hint(msg: str) -> str:
    """Format a concise, actionable hint for CLI surfaces."""
    return f"[hint] {msg}"

def _xdg_config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "swarm" / DEFAULT_CONFIG_FILENAME

def find_config_file(
    specific_path: str | None = None,
    start_dir: Path | None = None,
    default_dir: Path | None = None,
) -> Path | None:
    """
    Locate swarm_config.json using precedence:
      1) User-specified path (explicit ``--config`` always wins)
      2) ``SWARM_CONFIG_PATH`` environment variable
      3) XDG (~/.config/swarm/swarm_config.json)
      4) Upwards search from start_dir
      5) default_dir/swarm_config.json
      6) CWD/swarm_config.json
    Logs actionable hints on common mistakes.
    """
    # 1. User-specified path — an explicit choice must win over the XDG default.
    if specific_path:
        p = Path(specific_path)
        if p.is_file():
            return p.resolve()
        logger.warning(
            f"Specified config path does not exist: {specific_path} | "
            + _hint("Create a default config with: swarm-cli config init --path "
                    f"{specific_path}")
        )
        # Fall through

    # 2. SWARM_CONFIG_PATH env (production / container deploys)
    env_path = os.environ.get("SWARM_CONFIG_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            logger.debug(f"Found config SWARM_CONFIG_PATH: {p}")
            return p.resolve()
        logger.warning(
            f"SWARM_CONFIG_PATH does not exist: {env_path} | "
            + _hint("Point SWARM_CONFIG_PATH at an existing swarm_config.json")
        )

    # 3. XDG config path
    xdg_config = _xdg_config_path()
    if xdg_config.is_file():
        logger.debug(f"Found config XDG: {xdg_config}")
        return xdg_config.resolve()

    # 3. Upwards from start_dir
    if start_dir:
        current = start_dir.resolve()
        while current != current.parent:
            cp = current / DEFAULT_CONFIG_FILENAME
            if cp.is_file():
                logger.debug(f"Found config upwards: {cp}")
                return cp.resolve()
            current = current.parent
        cp = current / DEFAULT_CONFIG_FILENAME
        if cp.is_file():
            logger.debug(f"Found config at root: {cp}")
            return cp.resolve()

    # 4. Default dir
    if default_dir:
        cp = default_dir.resolve() / DEFAULT_CONFIG_FILENAME
        if cp.is_file():
            logger.debug(f"Found config default: {cp}")
            return cp.resolve()

    # 5. CWD
    cwd = Path.cwd()
    if start_dir is None or cwd != start_dir.resolve():
        cp = cwd / DEFAULT_CONFIG_FILENAME
        if cp.is_file():
            logger.debug(f"Found config cwd: {cp}")
            return cp.resolve()

    logger.debug(f"Config '{DEFAULT_CONFIG_FILENAME}' not found.")
    return None

def load_config(config_path: Path) -> dict[str, Any]:
    logger.debug(f"Loading config from {config_path}")
    try:
        with open(config_path) as f:
            config = json.load(f)
        logger.info(f"Loaded config from {config_path}")
        validate_config(config)
        return config
    except FileNotFoundError:
        logger.error(
            f"Config not found: {config_path} | "
            + _hint("Initialize a default config with: swarm-cli config init"
                    f"{' --path ' + str(config_path) if config_path else ''}")
        )
        raise
    except json.JSONDecodeError as e:
        logger.error(
            f"Invalid JSON in {config_path}: {e} | "
            + _hint("Fix the file or recreate it: mv "
                    f"{config_path} {config_path}.bak && swarm-cli config init")
        )
        raise ValueError(f"Invalid JSON: {config_path}") from e
    except Exception as e:
        logger.error(f"Load error {config_path}: {e}", exc_info=True)
        raise

def save_config(config: dict[str, Any], config_path: Path):
    logger.info(f"Saving config to {config_path}")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open('w') as f:
            json.dump(config, f, indent=4)
        logger.debug("Save OK.")
    except Exception as e:
        logger.error(f"Save failed {config_path}: {e}", exc_info=True)
        raise

def validate_config(config: dict[str, Any]):
    logger.debug("Validating config structure...")
    if "llm" not in config or not isinstance(config["llm"], dict):
        raise ValueError(
            "Config 'llm' section missing/malformed. "
            + _hint("Use: swarm-cli config add --section llm --name default --json "
                    "'{\"provider\":\"openai\",\"model\":\"gpt-4o\",\"api_key\":\"${OPENAI_API_KEY}\"}'")
        )
    for name, prof in config.get("llm", {}).items():
        if not isinstance(prof, dict):
            raise ValueError(f"LLM profile '{name}' not dict.")
    logger.debug("Config basic structure OK.")

def get_profile_from_config(config: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profile_data = config.get("llm", {}).get(profile_name)
    if profile_data is None:
        raise ValueError(
            f"LLM profile '{profile_name}' not found. "
            + _hint("List profiles or add one: swarm-cli config list; "
                    "swarm-cli config add --section llm --name default --json '{...}'")
        )
    if not isinstance(profile_data, dict):
        raise ValueError(f"LLM profile '{profile_name}' not dict.")
    return _substitute_env_vars_recursive(profile_data)

def create_default_config(config_path: Path):
    """Creates a default configuration file with valid JSON."""
    default_config = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "${OPENAI_API_KEY}",
                "base_url": None,
                "description": "Default OpenAI profile. Requires OPENAI_API_KEY env var."
            },
            "ollama_example": {
                "provider": "ollama",
                "model": "llama3",
                "api_key": "ollama",  # Usually not needed
                "base_url": "http://localhost:11434",
                "description": "Example for local Ollama Llama 3 model."
            }
        },
        "agents": {},
        "settings": {
            "default_markdown_output": True
        },
        "remotes": {},
    }
    logger.info(f"Creating default configuration file at {config_path}")
    try:
        save_config(default_config, config_path)  # Use save_config to write valid JSON
        logger.debug("Default configuration file created successfully.")
        # Emit a friendly post-create hint to guide the user
        logger.warning(
            _hint("Set your API key: export OPENAI_API_KEY=sk-... "
                  "or save to secrets file: echo 'OPENAI_API_KEY=sk-...' >> ~/.config/swarm/.env")
        )
    except Exception as e:
        logger.error(f"Failed to create default config file at {config_path}: {e}", exc_info=True)
        raise

def load_environment():
    """Load XDG ``~/.config/swarm/.env`` (primary) then project-root ``.env``."""
    from swarm.utils.dotenv_load import load_swarm_dotenv

    project_root = get_project_root_dir()
    try:
        loaded = load_swarm_dotenv(project_root=project_root)
        if loaded:
            logger.debug("dotenv loaded from: %s", ", ".join(loaded))
        else:
            logger.debug("No dotenv files found (XDG or project root).")
    except Exception as e:
        logger.error(
            "Error loading dotenv files: %s",
            e,
            exc_info=logger.level <= logging.DEBUG,
        )

def load_full_configuration(
    blueprint_class_name: str,
    config_path_override: str | Path | None = None,
    profile_override: str | None = None,
    cli_config_overrides: dict[str, Any] | None = None,
    # default_config_path is now primarily for specific overrides or testing;
    # if None, get_swarm_config_file() from paths.py will be used.
    default_config_path_for_tests: Path | None = None,
) -> dict[str, Any]:
    """
    Loads and merges configuration settings from base file, blueprint specifics, profiles, and CLI overrides.
    Uses XDG-compliant config path by default.

    Args:
        blueprint_class_name (str): The name of the blueprint class (e.g., "MyBlueprint").
        config_path_override (Optional[Union[str, Path]]): Path specified via CLI argument.
        profile_override (Optional[str]): Profile specified via CLI argument.
        cli_config_overrides (Optional[Dict[str, Any]]): Overrides provided via CLI argument.
        default_config_path_for_tests (Optional[Path]): Explicit path to a config file,
                                                        primarily for testing or specific scenarios.
                                                        If None, uses XDG default path.

    Returns:
        Dict[str, Any]: The final, merged configuration dictionary.

    Raises:
        ValueError: If the configuration file has JSON errors or cannot be read.
        FileNotFoundError: If a specific config_path_override is given but the file doesn't exist.
    """
    # Determine the configuration file path to use
    # Priority: CLI override > test/specific override > XDG default
    if config_path_override:
        config_path = Path(config_path_override)
        logger.debug(f"Using CLI overridden configuration path: {config_path}")
    elif default_config_path_for_tests:
        config_path = default_config_path_for_tests
        logger.debug(f"Using test/specific default configuration path: {config_path}")
    else:
        config_path = get_swarm_config_file() # Default to XDG config file
        logger.debug(f"Using XDG default configuration path: {config_path}")

    base_config = {}
    if config_path.is_file():
        try:
            with open(config_path, encoding="utf-8") as f:
                base_config = json.load(f)
            logger.debug(f"Successfully loaded base configuration from: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Config Error: Failed to parse JSON in {config_path}: {e}") from e
        except Exception as e:
            raise ValueError(f"Config Error: Failed to read {config_path}: {e}") from e
    else:
        # Only raise FileNotFoundError if a specific override was given and not found.
        # If the XDG default or test default isn't found, it's a warning, not an error.
        if config_path_override:
            raise FileNotFoundError(f"Configuration Error: Specified config file not found: {config_path}")
        else:
            logger.warning(f"Default configuration file not found at {config_path}. Proceeding without base configuration.")

    # 1. Start with base defaults
    final_config = base_config.get("defaults", {}).copy()
    logger.debug(f"Applied base defaults. Keys: {list(final_config.keys())}")

    # 2. Merge base llm and mcpServers sections
    if "llm" in base_config:
        final_config.setdefault("llm", {}).update(base_config["llm"])
        logger.debug("Merged base 'llm'.")
    if "mcpServers" in base_config:
        final_config.setdefault("mcpServers", {}).update(base_config["mcpServers"])
        logger.debug("Merged base 'mcpServers'.")
    if "remotes" in base_config and isinstance(base_config.get("remotes"), dict):
        final_config.setdefault("remotes", {}).update(base_config["remotes"])
        logger.debug("Merged base 'remotes'.")

    # 3. Merge blueprint-specific settings
    blueprint_settings = base_config.get("blueprints", {}).get(blueprint_class_name, {})
    if blueprint_settings:
        final_config.update(blueprint_settings)
        logger.debug(f"Merged BP '{blueprint_class_name}' settings. Keys: {list(blueprint_settings.keys())}")

    # 4. Determine and merge profile settings
    # Priority: CLI > Blueprint Specific > Base Defaults / settings > "default"
    # Honor documented default_model / llm_profile aliases, not only default_profile.
    profile_in_bp_settings = (
        blueprint_settings.get("default_profile")
        or blueprint_settings.get("default_model")
        or blueprint_settings.get("llm_profile")
    )
    settings_block = base_config.get("settings") or {}
    profile_in_base_defaults = (
        base_config.get("defaults", {}).get("default_profile")
        or (settings_block.get("default_llm_profile") if isinstance(settings_block, dict) else None)
        or (settings_block.get("default_llm") if isinstance(settings_block, dict) else None)
    )
    profile_to_use = profile_override or profile_in_bp_settings or profile_in_base_defaults or "default"
    logger.debug(f"Using profile: '{profile_to_use}'")
    profile_settings = base_config.get("profiles", {}).get(profile_to_use, {})
    if profile_settings:
        final_config.update(profile_settings)
        logger.debug(f"Merged profile '{profile_to_use}'. Keys: {list(profile_settings.keys())}")
    elif profile_to_use != "default" and (profile_override or profile_in_bp_settings or profile_in_base_defaults):
        # Runtime named profiles (legacy `profiles` map) and llm profile ids both
        # count; warn whenever the requested name is unknown in either place.
        llm_section = base_config.get("llm") or {}
        llm_known = profile_to_use in llm_section or (
            isinstance(llm_section.get("profiles"), dict)
            and profile_to_use in llm_section["profiles"]
        )
        if not llm_known:
            logger.warning(
                "Profile %r requested but not found in profiles/llm; falling back without profile overlay.",
                profile_to_use,
            )
        else:
            logger.debug(
                "Profile %r is an llm profile id (no legacy profiles overlay).",
                profile_to_use,
            )

    # 5. Merge CLI overrides (highest priority)
    if cli_config_overrides:
        final_config.update(cli_config_overrides)
        logger.debug(f"Merged CLI overrides. Keys: {list(cli_config_overrides.keys())}")

    # Ensure top-level keys exist
    final_config.setdefault("llm", {})
    final_config.setdefault("mcpServers", {})
    final_config.setdefault("remotes", {})

    # 6. Substitute environment variables in the final config
    final_config = _substitute_env_vars(final_config)
    logger.debug("Applied final env var substitution.")

    return final_config


# --- Centralized LLM profile resolution (to eliminate per-blueprint hacks) ---

def _apply_litellm_overrides(profile_data: dict) -> dict:
    """
    Apply LITELLM_* / OPENAI_BASE_URL env var overrides to a profile copy.
    This centralizes the pattern previously duplicated in chatbot, codey, stewie, blueprint_base, etc.
    - If LITELLM_BASE_URL (or OPENAI_BASE_URL) is set, override base_url (for local gateway use).
    - If LITELLM_API_KEY (or OPENAI_API_KEY) is set, override api_key.
    - If LITELLM_MODEL (or DEFAULT_LLM) is set, override model.
    Preserves other profile fields (temperature, max_tokens, etc.).
    Does NOT mutate input.
    """
    import os
    if not isinstance(profile_data, dict):
        profile_data = {}
    resolved = dict(profile_data)
    base = os.getenv("LITELLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    key = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM")
    if base:
        resolved["base_url"] = base
    if key:
        resolved["api_key"] = key
    if model:
        resolved["model"] = model
    return resolved


def raw_llm_profile(full_config: dict, profile_name: str | None) -> dict:
    """Named ``llm`` profile dict *before* LITELLM_MODEL / DEFAULT_LLM steal."""
    if not profile_name:
        return {}
    llm_section = (full_config or {}).get("llm", {}) or {}
    profile = llm_section.get(profile_name)
    if not profile and isinstance(llm_section.get("profiles"), dict):
        profile = llm_section["profiles"].get(profile_name)
    return dict(profile) if isinstance(profile, dict) else {}


def named_profile_model(
    full_config: dict,
    profile_name: str | None,
    resolved: dict | None = None,
) -> str | None:
    """Model for a named profile.

    Env ``LITELLM_MODEL`` / ``DEFAULT_LLM`` (applied by
    ``_apply_litellm_overrides``) must not steal ``orchestration`` when tip
    ``default_llm_profile=orchestration``. Gateway URL/key overrides stay.
    """
    raw = raw_llm_profile(full_config, profile_name)
    for source in (raw, resolved or {}):
        model = source.get("model") if isinstance(source, dict) else None
        if isinstance(model, str) and model.strip():
            return model.strip()
    return None


def get_resolved_llm_profile(
    full_config: dict,
    profile_name: str | None = None,
    *,
    allow_missing: bool = False,
) -> dict | None:
    """
    Centralized resolver for an LLM profile from the (loaded+substituted) full_config.
    Handles both 'llm': {name: {...}} and legacy 'llm': {'profiles': {name: ...}}.
    Applies env LITELLM overrides automatically for consistent custom gateway usage.
    Returns None (with warning) for 'none' or missing when allow_missing=True.
    Raises clear actionable errors otherwise.
    """
    import logging
    logger = logging.getLogger("swarm.config")

    llm_section = (full_config or {}).get("llm", {}) or {}
    name = profile_name or "default"

    if name and str(name).lower() in ("none", ""):
        logger.info("LLM profile 'none' requested; operating without LLM profile.")
        return None

    # Try direct key or profiles dict
    profile = llm_section.get(name)
    if not profile and "profiles" in llm_section:
        profile = llm_section["profiles"].get(name)

    if not profile:
        if allow_missing:
            logger.warning(f"LLM profile '{name}' not found (allow_missing). Available: {list(llm_section.keys())}")
            return None
        avail = list(llm_section.keys())
        raise ValueError(f"LLM profile '{name}' not found in config. Available: {avail}. Hint: add it or use --profile default")

    # Check provider before applying overrides (overrides don't supply provider)
    if "provider" not in profile:
        raise ValueError(f"'provider' missing in LLM profile '{name}'. Add a 'provider' key (e.g. 'openai').")

    # Apply overrides
    resolved = _apply_litellm_overrides(profile)

    return resolved


def list_available_llm_profiles(full_config: dict) -> list[str]:
    """List available LLM profile names for help/error messages."""
    llm_section = (full_config or {}).get("llm", {}) or {}
    keys = list(llm_section.keys())
    if "profiles" in llm_section and isinstance(llm_section["profiles"], dict):
        keys.extend(list(llm_section["profiles"].keys()))
    # dedup preserve order
    seen = set()
    return [k for k in keys if not (k in seen or seen.add(k))]


# --- Additional unification helpers (find/load/save/validate etc.) for central config management ---
# These consolidate logic previously duplicated in extensions/config/.

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_CONFIG_FILENAME = "swarm_config.json"


def load_config(config_path: Path) -> dict[str, Any]:
    logger.debug(f"Loading config from {config_path}")
    try:
        with open(config_path) as f:
            config = json.load(f)
        validate_config(config)
        return _substitute_env_vars(config)
    except FileNotFoundError:
        logger.error(f"Config not found: {config_path} | " + _hint("swarm-cli config init"))
        raise
    except Exception as e:
        logger.error(f"Load error {config_path}: {e}", exc_info=True)
        raise


def save_config(config: dict[str, Any], config_path: Path):
    logger.info(f"Saving config to {config_path}")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open('w') as f:
        json.dump(config, f, indent=4)


def validate_config(config: dict[str, Any]):
    if "llm" not in config or not isinstance(config.get("llm"), dict):
        raise ValueError("Config 'llm' section missing/malformed. " + _hint("swarm-cli config add --section llm ..."))
    logger.debug("Config structure OK.")


def get_profile_from_config(config: dict[str, Any], profile_name: str) -> dict[str, Any]:
    prof = config.get("llm", {}).get(profile_name)
    if not prof:
        raise ValueError(f"LLM profile '{profile_name}' not found. " + _hint("swarm-cli config list"))
    return _substitute_env_vars(prof)


def create_default_config(config_path: Path):
    default = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "${OPENAI_API_KEY}",
                "base_url": None,
            }
        },
        "settings": {"default_markdown_output": True},
        "remotes": {},
    }
    save_config(default, config_path)
    logger.warning(_hint("Set OPENAI_API_KEY or run config add for profiles."))


# Reexports for server config compat (from .server_config)
from .server_config import load_server_config, save_server_config  # noqa: E402,F401
