import json
import logging
import os
import re
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

# ``os.path.expandvars`` leaves an unknown reference untouched, so a surviving
# ``${NAME}`` means NAME was never set. Braced form only: an unbraced ``$NAME``
# can legitimately appear inside a literal secret and would false-positive.
_UNRESOLVED_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def unresolved_env_placeholders(value: Any) -> list[str]:
    """Env var names referenced as ``${NAME}`` that substitution left behind.

    Walks strings, dict values and list/tuple items and returns a sorted,
    de-duplicated list of names. Used to refuse a literal ``"${NAME}"`` before
    it reaches a provider client as a bogus URL, key or model id.
    """
    names: set[str] = set()

    def _walk(item: Any) -> None:
        if isinstance(item, str):
            names.update(_UNRESOLVED_ENV_RE.findall(item))
        elif isinstance(item, dict):
            for child in item.values():
                _walk(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                _walk(child)

    _walk(value)
    return sorted(names)


def drop_unresolved_env_values(
    profile: dict, keys: tuple[str, ...] = ("api_key", "base_url")
) -> tuple[dict, list[str]]:
    """Strip profile values that are still ``${NAME}`` placeholders.

    Returns ``(cleaned_profile, missing_env_vars)``. Dropping the value (rather
    than passing the literal through) matters: a literal ``"${LITELLM_BASE_URL}"``
    is a *valid* string to the OpenAI SDK, so it becomes a request target and
    fails much later as an opaque URL/auth error that never names the variable.
    Dropping ``api_key`` also restores the SDK's own ``OPENAI_API_KEY`` lookup.
    """
    unresolved = {
        key: profile[key]
        for key in keys
        if isinstance(profile.get(key), str) and unresolved_env_placeholders(profile[key])
    }
    if not unresolved:
        return profile, []
    missing = sorted({n for value in unresolved.values() for n in unresolved_env_placeholders(value)})
    cleaned = {k: v for k, v in profile.items() if k not in unresolved}
    return cleaned, missing


def _hint(msg: str) -> str:
    """Format a concise, actionable hint for CLI surfaces."""
    return f"[hint] {msg}"

def _xdg_config_path() -> Path:
    """Canonical XDG ``swarm_config.json`` — same directory as create-if-missing."""
    return get_swarm_config_file(DEFAULT_CONFIG_FILENAME)

def find_config_file(
    specific_path: str | None = None,
    start_dir: Path | None = None,
    default_dir: Path | None = None,
) -> Path | None:
    """
    Locate swarm_config.json using precedence:
      1) User-specified path (explicit ``--config`` always wins)
      2) ``SWARM_CONFIG_PATH`` environment variable
      3) Canonical config root (``config_root() / swarm_config.json``)
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
            + _hint("Create a default config with: os-cli config init --config "
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

def read_config_json(config_path: str | Path) -> dict[str, Any]:
    """Read a swarm config file as JSON. No validation and no env substitution.

    Shared by :func:`load_config` (strict) and ``config_manager.load_config``
    (CLI helper that ``sys.exit``s). Lenient boot paths that must accept a
    ``cli_agents``-only file keep their own readers.
    """
    path = Path(config_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be an object: {path}")
    return data


def write_config_json(
    config: dict[str, Any],
    config_path: str | Path,
    *,
    mkdir: bool = True,
) -> None:
    """Write a swarm config dict as indented JSON."""
    path = Path(config_path)
    if mkdir:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load, validate, and env-substitute ``swarm_config.json``.

    This is the single module-level implementation. A second copy used to
    sit at the bottom of this file and silently shadowed these helpers
    (#1435 / same class of bug as REQ-893).

    An omitted path uses :func:`find_config_file`. When that discovery
    finds nothing, return ``{}`` so no-arg consumers share one empty
    result. An explicit path that is missing or invalid still raises.
    """
    if config_path is None:
        found = find_config_file()
        if found is None:
            return {}
        path = found
    else:
        path = Path(config_path)
    logger.debug(f"Loading config from {path}")
    try:
        config = read_config_json(path)
        logger.info(f"Loaded config from {path}")
        validate_config(config)
        return _substitute_env_vars(config)
    except FileNotFoundError:
        logger.error(
            f"Config not found: {path} | "
            + _hint("Initialize a default config with: os-cli config init"
                    f"{' --config ' + str(path) if path else ''}")
        )
        raise
    except json.JSONDecodeError as e:
        logger.error(
            f"Invalid JSON in {path}: {e} | "
            + _hint("Fix the file or recreate it: mv "
                    f"{path} {path}.bak && os-cli config init")
        )
        raise ValueError(f"Invalid JSON: {path}") from e
    except Exception as e:
        logger.error(f"Load error {path}: {e}", exc_info=True)
        raise


def save_config(config: dict[str, Any], config_path: str | Path):
    logger.info(f"Saving config to {config_path}")
    path = Path(config_path)
    try:
        write_config_json(config, path, mkdir=True)
        logger.debug("Save OK.")
    except Exception as e:
        logger.error(f"Save failed {path}: {e}", exc_info=True)
        raise


def validate_config(config: dict[str, Any]):
    logger.debug("Validating config structure...")
    if "llm" not in config or not isinstance(config.get("llm"), dict):
        raise ValueError(
            "Config 'llm' section missing/malformed. "
            + _hint("Use: os-cli config add --section llm --name default --json "
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
            + _hint("List profiles or add one: os-cli config list; "
                    "os-cli config add --section llm --name default --json '{...}'")
        )
    if not isinstance(profile_data, dict):
        raise ValueError(f"LLM profile '{profile_name}' not dict.")
    return _substitute_env_vars(profile_data)


def create_default_config(config_path: str | Path):
    """Write the CLI ``config init`` default (llm + settings + remotes)."""
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
    path = Path(config_path)
    logger.info(f"Creating default configuration file at {path}")
    try:
        save_config(default, path)
        logger.debug("Default configuration file created successfully.")
        logger.warning(
            _hint("Set OPENAI_API_KEY or run config add for profiles. "
                  "Secrets belong in the user-config .env next to swarm_config.json")
        )
    except Exception as e:
        logger.error(f"Failed to create default config file at {path}: {e}", exc_info=True)
        raise


def load_environment():
    """Load the user-config ``.env`` (primary) then project-root ``.env``."""
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
    # if None, find_config_file() discovery is used.
    default_config_path_for_tests: Path | None = None,
) -> dict[str, Any]:
    """
    Loads and merges configuration settings from base file, blueprint specifics, profiles, and CLI overrides.
    Discovers the base file the same way the rest of the app does (see
    :func:`find_config_file`) unless a path is given explicitly.

    Args:
        blueprint_class_name (str): The name of the blueprint class (e.g., "MyBlueprint").
        config_path_override (Optional[Union[str, Path]]): Path specified via CLI argument.
        profile_override (Optional[str]): Profile specified via CLI argument.
        cli_config_overrides (Optional[Dict[str, Any]]): Overrides provided via CLI argument.
        default_config_path_for_tests (Optional[Path]): Explicit path to a config file,
                                                        primarily for testing or specific scenarios.
                                                        If None, uses :func:`find_config_file`
                                                        discovery.

    Returns:
        Dict[str, Any]: The final, merged configuration dictionary.

    Raises:
        ValueError: If the configuration file has JSON errors or cannot be read.
        FileNotFoundError: If a specific config_path_override is given but the file doesn't exist.
    """
    # Determine the configuration file path to use
    # Priority: CLI override > test/specific override > discovery
    if config_path_override:
        config_path = Path(config_path_override)
        logger.debug(f"Using CLI overridden configuration path: {config_path}")
    elif default_config_path_for_tests:
        config_path = default_config_path_for_tests
        logger.debug(f"Using test/specific default configuration path: {config_path}")
    else:
        # Discovery (explicit > SWARM_CONFIG_PATH > XDG swarm_config.json >
        # upwards > CWD), matching find_config_file's documented precedence.
        # This used to be get_swarm_config_file(), which named a config.yaml that
        # nothing writes — so this branch silently loaded an empty base config for
        # every caller without an override (requirements.load_active_config, and
        # through it the MCP provider's mcpServers).
        config_path = find_config_file() or get_swarm_config_file()
        logger.debug(f"Using discovered configuration path: {config_path}")

    base_config = {}
    if config_path.is_file():
        try:
            base_config = read_config_json(config_path)
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
    Providers in ``PROVIDER_DEFAULTS`` (Mistral) keep their own URL, key, and
    model. Gateway env must not send those calls at the LiteLLM proxy.
    Preserves other profile fields (temperature, max_tokens, etc.).
    Does NOT mutate input.
    """
    import os

    from swarm.core.llm_provider import provider_owns_endpoint

    if not isinstance(profile_data, dict):
        profile_data = {}
    resolved = dict(profile_data)
    owns_endpoint = provider_owns_endpoint(resolved.get("provider"))
    base = os.getenv("LITELLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    key = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM")
    if base and not owns_endpoint:
        resolved["base_url"] = base
    if key and not owns_endpoint:
        resolved["api_key"] = key
    if model and not owns_endpoint:
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

    # Vendor defaults (Mistral's official base URL / key env) before gateway
    # overrides, so a missing URL is the vendor endpoint rather than the proxy.
    from swarm.core.llm_provider import apply_provider_defaults

    profile = apply_provider_defaults(profile)

    # Apply overrides
    resolved = _apply_litellm_overrides(profile)

    # Env overrides above substitute the real values when present, so a value
    # still braced here points at a variable that is not set. Never hand that
    # literal to a provider client — name the variable and drop the value.
    resolved, missing_env = drop_unresolved_env_values(resolved)
    if missing_env:
        names = ", ".join(missing_env)
        logger.warning(
            "LLM profile %r references %s, but %s not set; ignoring those values. "
            "Set %s in the environment (e.g. .env or the user-config .env), or "
            "replace the placeholder in swarm_config.json.",
            name,
            names,
            "that variable is" if len(missing_env) == 1 else "those variables are",
            names,
        )

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


# Reexports for server config compat (from .server_config)
from .server_config import load_server_config, save_server_config  # noqa: E402,F401
