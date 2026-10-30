"""Configuration resolver mixin for blueprints and seats."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from django.apps import apps

from swarm.core.config_loader import (
    _substitute_env_vars,
    get_resolved_llm_profile,
    list_available_llm_profiles,
)

logger = logging.getLogger(__name__)


class ConfigResolver:
    """Provides configuration loading, profile resolution, and LLM instantiation."""

    _config: dict[str, Any] | None = None
    config_path: str | Path | None = None
    _llm_profile_name: str | None = None
    _llm_profile_data: dict[str, Any] | None = None
    _markdown_output: bool | None = None

    def _load_configuration(self) -> None:
        """Load blueprint configuration from Django AppConfig, path, or discovery.

        Always applies env-var substitution and profile/markdown settings after a
        config source is selected — including when ``config=`` was pre-supplied.
        """
        bp_id = getattr(self, "blueprint_id", "")
        try:
            if self._config is None:
                # 1. Django AppConfig (primary source in server mode)
                try:
                    app_cfg = apps.get_app_config("swarm")
                    if getattr(app_cfg, "config", None):
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
                        "llm": {
                            "default": {
                                "provider": "openai",
                                "model": "gpt-4o-mini",
                                "api_key": os.environ["OPENAI_API_KEY"],
                            }
                        },
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
                bp_id,
                e,
                exc_info=True,
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
            candidate = self._config["llm_profile"]
            from swarm.core.model_namespace import model_valid_for_provider

            if model_valid_for_provider("api", "", candidate, config=self._config):
                self._llm_profile_name = candidate
            else:
                logger.warning(
                    "Ignoring config llm_profile %r not valid for an API seat", candidate
                )

        profiles = llm.get("profiles", llm)
        # When profile name is still unresolved, leave data empty — property
        # resolution via _resolve_llm_profile will fill it on access.
        name = self._llm_profile_name
        self._llm_profile_data = profiles.get(name, {}) if name else {}

        bp_id = getattr(self, "blueprint_id", "")
        bp_settings = self._config.get("blueprints", {}).get(bp_id, {})
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
        if (
            isinstance(md, dict)
            and isinstance(md.get("inference_profile"), dict)
            and md["inference_profile"]
        ):
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
                "falling through to default",
                desired,
                len(candidates),
            )
            return None
        ranking = rank(desired, candidates)
        logger.info(
            "[inference_profile] blueprint '%s' requested %s -> selected '%s' (top: %s)",
            getattr(self, "blueprint_id", None) or type(self).__name__,
            desired,
            chosen,
            [(n, round(s, 3)) for n, s in ranking[:3]],
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
        if getattr(self, "_resolved_llm_profile", None):
            return self._resolved_llm_profile
        name = getattr(self, "blueprint_id", None) or getattr(
            self, "__class__", type(self)
        ).__name__
        profile = None
        profile_source = None
        logger.debug("[DEBUG _resolve_llm_profile] blueprint_id/name: %s", name)
        if isinstance(self._config, dict):
            logger.debug(
                "[DEBUG _resolve_llm_profile] config keys: %s",
                list(self._config.keys()),
            )

        # 1. Explicit override
        if getattr(self, "_llm_profile_name", None):
            profile = self._llm_profile_name
            profile_source = "programmatic override"
            logger.debug(
                f"[DEBUG _resolve_llm_profile] Using programmatic override: {profile}"
            )
        # 2. Blueprint config (top-level) — llm_profile or documented default_model
        elif self._config:
            top = self._config.get("llm_profile") or self._config.get("default_model")
            if top:
                profile = str(top)
                profile_source = "top-level llm_profile/default_model"
                logger.debug(
                    f"[DEBUG _resolve_llm_profile] Using top-level profile: {profile}"
                )

        # 3. Per-blueprint section (do not elif-skip settings when blueprints
        #    exists but has no profile key — that was the silent-default bug).
        if not profile and self._config and self._config.get("blueprints"):
            logger.debug(
                f"[DEBUG _resolve_llm_profile] Checking per-blueprint config for: {name}"
            )
            bp_cfg = self._config["blueprints"].get(name) or self._config[
                "blueprints"
            ].get(name.replace("Blueprint", ""))
            bp_profile = self._blueprint_section_profile_name(
                bp_cfg if isinstance(bp_cfg, dict) else None
            )
            if bp_profile:
                profile = bp_profile
                profile_source = "blueprints[].llm_profile/default_model"
                logger.debug(
                    f"[DEBUG _resolve_llm_profile] Using per-blueprint profile: {profile}"
                )

        # 4. settings.default_llm_profile / legacy default_llm
        if not profile:
            settings_profile = self._settings_default_profile_name(self._config)
            if settings_profile:
                profile = settings_profile
                profile_source = "settings.default_llm_profile"
                logger.debug(
                    f"[DEBUG _resolve_llm_profile] Using settings default: {profile}"
                )

        # 5–6. Global file lookup only when local config did not name a profile
        if not profile:
            global_config = None
            try:
                from swarm.core.paths import get_swarm_config_file

                # Same root as discovery / CLI create-if-missing (#1434). A
                # hardcoded home config path ignores $XDG_CONFIG_HOME.
                config_paths = [
                    Path.cwd() / "swarm_config.json",
                    get_swarm_config_file(),
                ]
                for path in config_paths:
                    if path.exists():
                        with open(path) as f:
                            global_config = json.load(f)
                        break
            except Exception:
                global_config = None
            if global_config and "blueprints" in global_config:
                bp_cfg = global_config["blueprints"].get(name) or global_config[
                    "blueprints"
                ].get(name.replace("Blueprint", ""))
                bp_profile = self._blueprint_section_profile_name(
                    bp_cfg if isinstance(bp_cfg, dict) else None
                )
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
            profile = os.environ.get("DEFAULT_LLM")
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
            profile = "default"
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
            raise RuntimeError(
                "Configuration accessed before initialization or after failure."
            )
        return self._config

    @property
    def llm_profile(self) -> dict[str, Any]:
        """Returns the LLM profile dict for this blueprint (centralized resolution + litellm overrides).

        Raises a clear actionable error if missing.
        """
        profile_name = self._resolve_llm_profile()
        try:
            resolved = get_resolved_llm_profile(
                self._config or {}, profile_name, allow_missing=False
            )
            if resolved is None:
                avail = list_available_llm_profiles(self._config or {})
                raise ValueError(
                    f"LLM profile '{profile_name}' resolved to none. Available: {avail}"
                )
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
        if hasattr(self, "_resolved_llm_profile"):
            del self._resolved_llm_profile

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
            resolved = get_resolved_llm_profile(
                self.config, profile_name, allow_missing=True
            )
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
        """Determines if markdown output should be used for this blueprint.

        Priority: blueprint config > global config > False
        """
        settings = self._config.get("settings", {}) if self._config else {}
        bp_id = getattr(self, "blueprint_id", "")
        bp_settings = (
            self._config.get("blueprints", {}).get(bp_id, {})
            if self._config
            else {}
        )
        if "output_markdown" in bp_settings:
            return bool(bp_settings["output_markdown"])
        if "default_markdown_output" in settings:
            return bool(settings["default_markdown_output"])
        return False

    def _get_model_instance(self, profile_name: str):
        """Retrieves or creates an LLM Model instance, respecting LITELLM_MODEL/DEFAULT_LLM if set."""
        if not hasattr(self, "_model_instance_cache"):
            self._model_instance_cache = {}
        if not hasattr(self, "_openai_client_cache"):
            self._openai_client_cache = {}
        if profile_name in self._model_instance_cache:
            logger.debug(f"Using cached Model instance for profile '{profile_name}'.")
            return self._model_instance_cache[profile_name]
        logger.debug(f"Creating new Model instance for profile '{profile_name}'.")
        profile_data = self.get_llm_profile(profile_name)

        # Default to 'completions' mode unless 'responses' is explicitly specified in swarm_config.json for this blueprint
        api_mode = (
            profile_data.get("api_mode")
            or self.config.get("api_mode")
            or "completions"
        )
        api_mode = os.getenv("SWARM_LLM_API_MODE", api_mode)
        model_name = (
            os.getenv("LITELLM_MODEL")
            or os.getenv("DEFAULT_LLM")
            or profile_data.get("model")
        )
        provider = profile_data.get("provider", "openai")
        from swarm.core.llm_provider import is_openai_chat_provider

        if is_openai_chat_provider(provider):
            provider = "openai"
        client_kwargs = {
            "api_key": profile_data.get("api_key"),
            "base_url": profile_data.get("base_url"),
        }
        from swarm.utils.env_utils import llm_http_timeout

        client_kwargs["timeout"] = llm_http_timeout()
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}
        log_kwargs = {k: v for k, v in filtered_kwargs.items() if k != "api_key"}
        logger.debug(
            f"Creating new AsyncOpenAI client for '{profile_name}' with {log_kwargs} and api_mode={api_mode}"
        )
        client_cache_key = f"{provider}_{profile_data.get('base_url')}_{api_mode}"
        if client_cache_key not in self._openai_client_cache:
            from openai import AsyncOpenAI

            self._openai_client_cache[client_cache_key] = AsyncOpenAI(
                **filtered_kwargs
            )
        client = self._openai_client_cache[client_cache_key]
        if api_mode == "responses":
            from agents.models.openai_responses import OpenAIResponsesModel

            model_instance = OpenAIResponsesModel(
                model=model_name, openai_client=client
            )
        else:
            from agents.models.openai_chatcompletions import (
                OpenAIChatCompletionsModel,
            )

            model_instance = OpenAIChatCompletionsModel(
                model=model_name, openai_client=client
            )
        self._model_instance_cache[profile_name] = model_instance
        return model_instance
