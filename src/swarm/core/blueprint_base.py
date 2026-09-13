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

# Keep the function import
from swarm.core.config_loader import (
    _substitute_env_vars,
    get_resolved_llm_profile,
    list_available_llm_profiles,
)

logger = logging.getLogger(__name__)
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

class BlueprintBase(ABC):
    """
    Abstract base class for all Swarm blueprints.

    Defines the core interface for blueprint initialization and execution.
    """
    enable_terminal_commands: bool = False  # By default, terminal command execution is disabled
    approval_required: bool = False
    console = Console()
    session_logger = None

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

    def _load_configuration(self) -> None:
        """Load blueprint configuration from Django AppConfig, path, or discovery.

        Always applies env-var substitution and profile/markdown settings after a
        config source is selected — including when ``config=`` was pre-supplied.
        """
        try:
            if self._config is None:
                # 1. Django AppConfig (primary source in server mode)
                try:
                    app_cfg = apps.get_app_config('swarm')
                    if getattr(app_cfg, 'config', None):
                        self._config = app_cfg.config
                except Exception:
                    pass

                # 2. Explicit path provided at construction time
                if self._config is None and self.config_path is not None:
                    p = Path(self.config_path)
                    if p.exists():
                        with open(p) as f:
                            self._config = json.load(f)
                    else:
                        logger.warning("Config path %s does not exist.", self.config_path)

                # 3. Standard discovery: SWARM_CONFIG_PATH → XDG → CWD → …
                #    Lenient JSON load (no strict llm validation) so CLI-only
                #    configs work the same as AppConfig.
                if self._config is None:
                    from swarm.core.config_loader import find_config_file
                    found = find_config_file()
                    if found:
                        try:
                            with open(found) as f:
                                self._config = json.load(f)
                            if os.environ.get("SWARM_CONFIG_DEBUG"):
                                logger.info("Loaded config from %s", found)
                        except (OSError, json.JSONDecodeError) as e:
                            logger.warning("Failed to load config %s: %s", found, e)
                            self._config = {}
                    else:
                        self._config = {}

                # 4. Env-var bootstrap: bare OPENAI_API_KEY with no config file
                if not self._config and os.environ.get("OPENAI_API_KEY"):
                    self._config = {
                        "llm": {"default": {
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "api_key": os.environ["OPENAI_API_KEY"],
                        }},
                        "settings": {"default_llm_profile": "default"},
                        "mcpServers": {},
                    }
                    logger.info("No config file found; bootstrapped from OPENAI_API_KEY.")

            if self._config is None:
                self._config = {}

            # Always substitute + apply, even when config was pre-supplied.
            self._config = _substitute_env_vars(self._config)
            self._apply_config_settings()
        except Exception as e:
            logger.error(
                "Unexpected error loading config for blueprint '%s': %s",
                self.blueprint_id, e, exc_info=True,
            )
            self._config = self._config if isinstance(self._config, dict) else {}
            try:
                self._apply_config_settings()
            except Exception:
                pass

    def _apply_config_settings(self) -> None:
        """Apply LLM profile name, profile data, and markdown setting from loaded config."""
        if not isinstance(self._config, dict):
            self._config = {}
        settings = self._config.get("settings", {})
        llm = self._config.get("llm", {})

        if "llm_profile" in self._config:
            self._llm_profile_name = self._config["llm_profile"]

        profiles = llm.get("profiles", llm)
        # When profile name is still unresolved, leave data empty — property
        # resolution via _resolve_llm_profile will fill it on access.
        name = self._llm_profile_name
        self._llm_profile_data = profiles.get(name, {}) if name else {}

        bp_settings = self._config.get("blueprints", {}).get(self.blueprint_id, {})
        # Accept both keys used in the wild (tests/docs: output_markdown).
        if "output_markdown" in bp_settings:
            self._markdown_output = bool(bp_settings["output_markdown"])
        elif "markdown_output" in bp_settings:
            self._markdown_output = bool(bp_settings["markdown_output"])
        else:
            self._markdown_output = settings.get("default_markdown_output", True)

    def _load_and_process_config(self):
        """Compatibility alias — delegates to :meth:`_load_configuration`."""
        self._load_configuration()

    def _llm_candidates(self) -> dict[str, Any]:
        """Profiles in the config 'llm' section that declare capability axes.

        Only profiles tagging at least one of intelligence/speed/cost are treated
        as scorable candidates, so untagged profiles (e.g. 'default', 'reason')
        never win a match merely by defaulting to a neutral 0.5 on every axis.
        """
        from swarm.core.inference_profile import TRAITS
        cfg = self._config if isinstance(self._config, dict) else {}
        llm_section = cfg.get("llm", {}) or {}
        candidates: dict[str, Any] = {}
        for prof_name, prof in llm_section.items():
            if isinstance(prof, dict) and any(t in prof for t in TRAITS):
                candidates[prof_name] = {t: prof[t] for t in TRAITS if t in prof}
        return candidates

    def _desired_inference_profile(self) -> dict[str, Any] | None:
        """The inference-profile *suggestion* for this blueprint, if any.

        A value set programmatically (e.g. via make_agent(inference_profile=...))
        takes precedence over a static metadata['inference_profile']. Returns
        None when the blueprint expresses no preference (the resolver then falls
        through to its normal default).
        """
        ip = getattr(self, "_inference_profile", None)
        if isinstance(ip, dict) and ip:
            return ip
        md = getattr(self, "metadata", None)
        if isinstance(md, dict) and isinstance(md.get("inference_profile"), dict) and md["inference_profile"]:
            return md["inference_profile"]
        return None

    def _select_profile_by_inference(self):
        """Score the blueprint's inference_profile suggestion against the tagged
        config profiles and return the best-matching profile name, or None.

        This is a *suggestion*: it only ever fills in a profile when no explicit
        name/env override was chosen, and it declines (returns None) when the
        suggestion names no known axis or no candidate is tagged.
        """
        desired = self._desired_inference_profile()
        if not desired:
            return None
        from swarm.core.inference_profile import rank, resolve
        candidates = self._llm_candidates()
        chosen = resolve(desired, candidates)
        if not chosen:
            logger.debug(
                "[inference_profile] no scorable match for desired=%s among %d candidate(s); "
                "falling through to default", desired, len(candidates),
            )
            return None
        ranking = rank(desired, candidates)
        logger.info(
            "[inference_profile] blueprint '%s' requested %s -> selected '%s' (top: %s)",
            getattr(self, "blueprint_id", None) or type(self).__name__,
            desired, chosen, [(n, round(s, 3)) for n, s in ranking[:3]],
        )
        return chosen

    @staticmethod
    def _blueprint_section_profile_name(bp_cfg: dict | None) -> str | None:
        """Per-blueprint profile key: llm_profile, default_model, or default_profile."""
        if not isinstance(bp_cfg, dict):
            return None
        for key in ("llm_profile", "default_model", "default_profile"):
            value = bp_cfg.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _settings_default_profile_name(cfg: dict | None) -> str | None:
        """Documented settings.default_llm_profile, with legacy settings.default_llm."""
        settings = (cfg or {}).get("settings") or {}
        if not isinstance(settings, dict):
            return None
        for key in ("default_llm_profile", "default_llm"):
            value = settings.get(key)
            if value:
                return str(value)
        return None

    def _llm_profile_exists(self, profile_name: str) -> bool:
        llm = (self._config or {}).get("llm") or {}
        if not isinstance(llm, dict):
            return False
        if profile_name in llm and profile_name != "profiles":
            entry = llm.get(profile_name)
            if isinstance(entry, dict):
                return True
        profiles = llm.get("profiles")
        return isinstance(profiles, dict) and profile_name in profiles

    def _fallback_llm_profile_name(self, requested: str, *, source: str) -> str:
        """Warn and fall back when an explicitly requested profile is missing."""
        import logging
        logger = logging.getLogger(__name__)
        fallback = self._settings_default_profile_name(self._config) or "default"
        if fallback == requested or not self._llm_profile_exists(fallback):
            fallback = "default"
        logger.warning(
            "LLM profile %r from %s not found in config; falling back to %r. Available: %s",
            requested,
            source,
            fallback,
            list_available_llm_profiles(self._config or {}),
        )
        return fallback

    def _resolve_llm_profile(self):
        """Resolve the LLM profile for this blueprint using the following order:
        1. If self._llm_profile_name is set, use it.
        2. Top-level config llm_profile / default_model.
        3. Per-blueprint llm_profile / default_model / default_profile.
        4. settings.default_llm_profile (or legacy settings.default_llm).
        5. Global swarm_config blueprints.<name> profile keys (when local config
           has no blueprints/settings hit).
        6. settings default from that global config.
        7. Env var DEFAULT_LLM.
        7b. inference_profile scoring: if the blueprint declares a desired
            inference_profile (metadata or make_agent param), pick the closest
            tagged profile via inference_profile.resolve(). This is the primary
            path for blueprints that only declare *intent*; explicit names and
            env overrides above still win.
        8. Otherwise, use 'default'.

        Explicitly requested names that are missing from ``llm`` warn and fall
        back to settings.default_llm_profile (else ``default``), matching
        CONFIGURATION.md — never silently ignore ``default_model``.
        """
        # Use cached value if already resolved
        if getattr(self, '_resolved_llm_profile', None):
            return self._resolved_llm_profile
        name = getattr(self, 'blueprint_id', None) or getattr(self, '__class__', type(self)).__name__
        profile = None
        profile_source = None
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("[DEBUG _resolve_llm_profile] blueprint_id/name: %s", name)
        if isinstance(self._config, dict):
            logger.debug(
                "[DEBUG _resolve_llm_profile] config keys: %s",
                list(self._config.keys()),
            )

        # 1. Explicit override
        if getattr(self, '_llm_profile_name', None):
            profile = self._llm_profile_name
            profile_source = "programmatic override"
            logger.debug(f"[DEBUG _resolve_llm_profile] Using programmatic override: {profile}")
        # 2. Blueprint config (top-level) — llm_profile or documented default_model
        elif self._config:
            top = self._config.get('llm_profile') or self._config.get('default_model')
            if top:
                profile = str(top)
                profile_source = "top-level llm_profile/default_model"
                logger.debug(f"[DEBUG _resolve_llm_profile] Using top-level profile: {profile}")

        # 3. Per-blueprint section (do not elif-skip settings when blueprints
        #    exists but has no profile key — that was the silent-default bug).
        if not profile and self._config and self._config.get('blueprints'):
            logger.debug(f"[DEBUG _resolve_llm_profile] Checking per-blueprint config for: {name}")
            bp_cfg = self._config['blueprints'].get(name) or self._config['blueprints'].get(name.replace('Blueprint', ''))
            logger.debug(f"[DEBUG _resolve_llm_profile] bp_cfg: {bp_cfg}")
            bp_profile = self._blueprint_section_profile_name(bp_cfg if isinstance(bp_cfg, dict) else None)
            if bp_profile:
                profile = bp_profile
                profile_source = "blueprints[].llm_profile/default_model"
                logger.debug(f"[DEBUG _resolve_llm_profile] Using per-blueprint profile: {profile}")

        # 4. settings.default_llm_profile / legacy default_llm
        if not profile:
            settings_profile = self._settings_default_profile_name(self._config)
            if settings_profile:
                profile = settings_profile
                profile_source = "settings.default_llm_profile"
                logger.debug(f"[DEBUG _resolve_llm_profile] Using settings default: {profile}")

        # 5–6. Global file lookup only when local config did not name a profile
        if not profile:
            global_config = None
            try:
                import json
                from pathlib import Path
                config_paths = [Path.cwd() / 'swarm_config.json', Path.home() / '.config/swarm/swarm_config.json']
                for path in config_paths:
                    if path.exists():
                        with open(path) as f:
                            global_config = json.load(f)
                        break
            except Exception:
                global_config = None
            if global_config and 'blueprints' in global_config:
                bp_cfg = global_config['blueprints'].get(name) or global_config['blueprints'].get(name.replace('Blueprint', ''))
                bp_profile = self._blueprint_section_profile_name(bp_cfg if isinstance(bp_cfg, dict) else None)
                if bp_profile:
                    profile = bp_profile
                    profile_source = "global blueprints[].llm_profile/default_model"
            if not profile:
                settings_profile = self._settings_default_profile_name(global_config)
                if settings_profile:
                    profile = settings_profile
                    profile_source = "global settings.default_llm_profile"

        # 7. Env var DEFAULT_LLM
        if not profile:
            import os
            profile = os.environ.get('DEFAULT_LLM')
            if profile:
                profile_source = "DEFAULT_LLM env"
        # 7b. inference_profile scoring (suggestion) — primary path for blueprints
        #     that declare only intent; runs below explicit names/env overrides.
        if not profile:
            profile = self._select_profile_by_inference()
            if profile:
                profile_source = "inference_profile"
        # 8. Otherwise, use 'default'
        if not profile:
            profile = 'default'
            profile_source = "builtin default"

        # Explicit requests must not silently ignore unknown names.
        if (
            profile_source
            and profile_source not in ("inference_profile", "builtin default")
            and not self._llm_profile_exists(str(profile))
        ):
            profile = self._fallback_llm_profile_name(str(profile), source=profile_source)

        logger.debug(f"[DEBUG _resolve_llm_profile] Final resolved profile: {profile}")
        self._resolved_llm_profile = profile
        return profile

    @property
    def config(self) -> dict[str, Any]:
        """Returns the loaded and processed Swarm configuration."""
        if self._config is None:
            raise RuntimeError("Configuration accessed before initialization or after failure.")
        return self._config

    @property
    def llm_profile(self) -> dict[str, Any]:
        """
        Returns the LLM profile dict for this blueprint (centralized resolution + litellm overrides).
        Raises a clear actionable error if missing.
        """
        profile_name = self._resolve_llm_profile()
        try:
            resolved = get_resolved_llm_profile(self._config or {}, profile_name, allow_missing=False)
            if resolved is None:
                avail = list_available_llm_profiles(self._config or {})
                raise ValueError(f"LLM profile '{profile_name}' resolved to none. Available: {avail}")
            return resolved
        except Exception as e:
            avail = list_available_llm_profiles(self._config or {})
            raise ValueError(
                f"LLM profile '{profile_name}' error: {e}. "
                f"Available: {avail}. Hint: use --profile default or ensure swarm_config.json has valid llm entry + api_key (or LITELLM_* envs)."
            ) from e

    @property
    def llm_profile_name(self) -> str:
        """Returns the name of the LLM profile being used."""
        return self._resolve_llm_profile()

    @llm_profile_name.setter
    def llm_profile_name(self, value: str):
        self._llm_profile_name = value
        if hasattr(self, '_resolved_llm_profile'):
            del self._resolved_llm_profile

    @property
    def slash_commands(self):
        from swarm.core.slash_commands import slash_registry
        return slash_registry

    def get_navbar_items(self=None) -> list[dict]:
        """Returns metadata for navbar items contributed by this blueprint."""
        return []

    def get_llm_profile(self, profile_name: str) -> dict:
        """Returns the resolved LLM profile dict (with LITELLM_* overrides applied).

        Uses centralized resolver in config_loader for consistency across the app.
        When a non-empty name is requested and missing/unusable, logs a warning and
        returns ``{}`` (optional lookup). Prefer the ``llm_profile`` property for
        fail-loud resolution of the active profile.
        """
        if not profile_name:
            return {}
        try:
            resolved = get_resolved_llm_profile(self.config, profile_name, allow_missing=True)
            if resolved is None:
                # get_resolved_llm_profile already warned for missing names.
                return {}
            return resolved
        except Exception as e:
            logger.warning(
                "LLM profile %r lookup failed: %s; returning {}. Available: %s",
                profile_name,
                e,
                list_available_llm_profiles(self.config or {}),
            )
            return {}

    @property
    def should_output_markdown(self) -> bool:
        """
        Determines if markdown output should be used for this blueprint.
        Priority: blueprint config > global config > False
        """
        settings = self._config.get("settings", {}) if self._config else {}
        bp_settings = self._config.get("blueprints", {}).get(self.blueprint_id, {}) if self._config else {}
        if "output_markdown" in bp_settings:
            return bool(bp_settings["output_markdown"])
        if "default_markdown_output" in settings:
            return bool(settings["default_markdown_output"])
        return False

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

    def _get_model_instance(self, profile_name: str):
        """Retrieves or creates an LLM Model instance, respecting LITELLM_MODEL/DEFAULT_LLM if set."""
        if not hasattr(self, '_model_instance_cache'):
            self._model_instance_cache = {}
        if not hasattr(self, '_openai_client_cache'):
            self._openai_client_cache = {}
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")
        profile_data = self.get_llm_profile(profile_name)
        import os
        # --- PATCH: API mode selection ---
        # Default to 'completions' mode unless 'responses' is explicitly specified in swarm_config.json for this blueprint
        api_mode = profile_data.get("api_mode") or self.config.get("api_mode") or "completions"
        # Allow env override for debugging if needed
        api_mode = os.getenv("SWARM_LLM_API_MODE", api_mode)
        model_name = os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM") or profile_data.get("model")
        provider = profile_data.get("provider", "openai")
        # OpenAI-compatible gateways (LiteLLM, Ollama, …) keep the OpenAI client.
        from swarm.core.llm_provider import is_openai_chat_provider
        if is_openai_chat_provider(provider):
            provider = "openai"
        client_kwargs = { "api_key": profile_data.get("api_key"), "base_url": profile_data.get("base_url") }
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}
        log_kwargs = {k:v for k,v in filtered_kwargs.items() if k != 'api_key'}
        logger.debug(f"Creating new AsyncOpenAI client for '{profile_name}' with {log_kwargs} and api_mode={api_mode}")
        client_cache_key = f"{provider}_{profile_data.get('base_url')}_{api_mode}"
        if client_cache_key not in self._openai_client_cache:
            from openai import AsyncOpenAI
            self._openai_client_cache[client_cache_key] = AsyncOpenAI(**filtered_kwargs)
        client = self._openai_client_cache[client_cache_key]
        # --- PATCH: Use correct model class based on api_mode ---
        if api_mode == "responses":
            from agents.models.openai_responses import OpenAIResponsesModel
            model_instance = OpenAIResponsesModel(model=model_name, openai_client=client)
        else:
            from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
            model_instance = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
        self._model_instance_cache[profile_name] = model_instance
        return model_instance

    def _get_memory_instance(self, memory_type: str, memory_config: dict = None):
        """Helper to get a memory backend instance."""
        if not memory_type or memory_type.lower() == 'none':
            return None
        from swarm.memory import get_memory_backend
        return get_memory_backend(memory_type, memory_config)

    # --- Memory integration (opt-in via config; strict no-op otherwise) ---

    @property
    def memory_backend(self):
        """The configured memory backend for this blueprint, or None."""
        return getattr(self, "_memory_backend", None)

    def _resolve_memory_settings(self) -> dict | None:
        """Resolve the opt-in 'memory' config block for this blueprint.

        Checks config["blueprints"][blueprint_id]["memory"] first, then the
        top-level config["memory"] block. Returns None when not configured.
        """
        cfg = self._config if isinstance(self._config, dict) else {}
        blueprints_section = cfg.get("blueprints", {})
        bp_cfg = blueprints_section.get(self.blueprint_id, {}) if isinstance(blueprints_section, dict) else {}
        mem_cfg = bp_cfg.get("memory") if isinstance(bp_cfg, dict) else None
        if mem_cfg is None:
            mem_cfg = cfg.get("memory")
        return mem_cfg if isinstance(mem_cfg, dict) else None

    def _init_memory_backend(self) -> None:
        """Resolve the optional memory backend from config and, when present,
        wrap run() so memories are retrieved before and stored after each run.

        Strictly a no-op when no "memory" block (with a "backend" key) is
        configured, or when the backend package is unavailable.
        """
        try:
            mem_cfg = self._resolve_memory_settings()
            if not mem_cfg or not mem_cfg.get("backend"):
                return
            from swarm.memory import get_memory_backend
            backend = get_memory_backend(mem_cfg)
            if backend is None:
                return
            self._memory_settings = mem_cfg
            self._memory_backend = backend
            self._wrap_run_with_memory()
            logger.debug(f"Memory backend '{mem_cfg.get('backend')}' enabled for blueprint '{self.blueprint_id}'.")
        except Exception as e:
            logger.warning(f"Failed to initialize memory backend for '{self.blueprint_id}': {e}")

    def _memory_user_id(self, user_id: str = None) -> str:
        return user_id or getattr(self, "_memory_settings", {}).get("user_id") or "default"

    def inject_memory_context(self, messages: list, user_id: str = None) -> list:
        """Prepend a system message with memories relevant to the latest user message.

        Returns ``messages`` unchanged when no backend is configured, no user
        message is present, or no relevant memories are found.
        """
        backend = self.memory_backend
        if backend is None or not messages:
            return messages
        query = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user" and msg.get("content"):
                query = str(msg["content"])
                break
        if not query:
            return messages
        try:
            memories = backend.search(query, user_id=self._memory_user_id(user_id)) or []
        except Exception as e:
            logger.warning(f"Memory search failed for '{self.blueprint_id}': {e}")
            return messages
        memories = [str(m).strip() for m in memories if str(m).strip()]
        if not memories:
            return messages
        memory_text = "\n".join(f"- {m}" for m in memories)
        memory_message = {
            "role": "system",
            "content": f"Relevant memories from previous conversations:\n{memory_text}",
        }
        return [memory_message, *list(messages)]

    def store_run_memory(self, messages: list, run_chunks: list = None, user_id: str = None) -> None:
        """Persist the conversation (input messages plus assistant output) after a run.

        No-op when no memory backend is configured; storage errors are logged,
        never raised.
        """
        backend = self.memory_backend
        if backend is None:
            return
        conversation = [
            m for m in (messages or [])
            if isinstance(m, dict) and m.get("role") and m.get("content")
        ]
        for chunk in run_chunks or []:
            if not isinstance(chunk, dict):
                continue
            chunk_messages = chunk.get("messages") or []
            if isinstance(chunk_messages, dict):
                chunk_messages = [chunk_messages]
            for m in chunk_messages:
                if isinstance(m, dict) and m.get("content"):
                    conversation.append({"role": m.get("role", "assistant"), "content": m["content"]})
        if not conversation:
            return
        try:
            backend.add(conversation, user_id=self._memory_user_id(user_id))
        except Exception as e:
            logger.warning(f"Memory add failed for '{self.blueprint_id}': {e}")

    def _wrap_run_with_memory(self) -> None:
        """Wrap this instance's run() so memory retrieval/storage happen around each run.

        Only invoked when a memory backend is configured, so unconfigured
        blueprints keep their original run() untouched.
        """
        if getattr(self, "_memory_run_wrapped", False):
            return
        original_run = self.run

        async def run_with_memory(messages, **kwargs):
            user_id = kwargs.get("user_id")
            augmented = self.inject_memory_context(messages, user_id=user_id)
            collected = []
            async for chunk in original_run(augmented, **kwargs):
                collected.append(chunk)
                yield chunk
            self.store_run_memory(messages, collected, user_id=user_id)

        self.run = run_with_memory
        self._memory_run_wrapped = True

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

        return agent

    def request_approval(self, action_type, action_summary, action_details=None):
        """
        Prompt user for approval before executing an action.
        Returns True if approved, False if rejected, or edited action if supported.
        """
        try:
            from swarm.core.blueprint_ux import BlueprintUX
            ux = BlueprintUX(style="serious")
            box = ux.box(f"Approve {action_type}?", action_summary, summary="Details:", params=action_details)
            self.console.print(box)
        except Exception:
            print(f"Approve {action_type}?\n{action_summary}\nDetails: {action_details}")
        while True:
            resp = input("Approve this action? [y]es/[n]o/[e]dit/[s]kip: ").strip().lower()
            if resp in ("y", "yes"): return True
            if resp in ("n", "no"): return False
            if resp in ("s", "skip"): return False
            if resp in ("e", "edit"):
                if action_details:
                    print("Edit not yet implemented; skipping.")
                    return False
                else:
                    print("No editable content; skipping.")
                    return False

    def execute_tool_with_approval(self, tool_func, action_type, action_summary, action_details=None, *args, **kwargs):
        if getattr(self, 'approval_required', False):
            approved = self.request_approval(action_type, action_summary, action_details)
            if not approved:
                try:
                    self.console.print(f"[yellow]Skipped {action_type}[/yellow]")
                except Exception:
                    print(f"Skipped {action_type}")
                return None
        return tool_func(*args, **kwargs)

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

