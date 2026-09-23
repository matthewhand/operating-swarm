import logging
import logging.config
import os  # Import os

from django.apps import AppConfig

# Import Django settings and logging config
from django.conf import settings

logger = logging.getLogger(__name__)

class SwarmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'swarm'
    verbose_name = "Swarm Application"

    def ready(self):
        # Configure logging using the settings dictionary
        # This ensures settings are fully loaded before configuring logging
        try:
            logging.config.dictConfig(settings.LOGGING)
            logger.info("Logging configured successfully via SwarmConfig.ready().")
        except Exception as e:
            # Fallback to basic config if dictConfig fails
            logging.basicConfig(level=logging.INFO)
            logger.critical(
                f"Failed to configure logging using dictConfig: {e}. Using basicConfig.",
                exc_info=True
            )


        # The blueprint discovery and URL registration should ideally happen
        # when blueprints are actually needed or instantiated, often handled
        # by the blueprint loading mechanism itself or specific view logic.
        # Avoid doing heavy discovery or URL manipulation directly in AppConfig.ready
        # unless absolutely necessary and carefully managed, as it can lead to
        # import loops or run before the full Django environment is set up.

        # Example: Trigger necessary setup if needed, but avoid blueprint
        # instantiation here.
        logger.info("Swarm AppConfig ready.")

        # Blueprint discovery / URL registration happen where needed (e.g. list_models),
        # not at AppConfig.ready().

        # Ensure necessary environment variables for Django are set if not already
        if not os.environ.get("DJANGO_SETTINGS_MODULE"):
             os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
             logger.warning(
                "DJANGO_SETTINGS_MODULE not set, setting default 'swarm.settings'"
            )

        # Load the swarm config ONCE and cache it on the AppConfig so every
        # blueprint reads the same file. BlueprintBase._load_configuration already
        # prefers ``apps.get_app_config('swarm').config`` — populating it here from
        # the XDG path is what makes the server honor ~/.config/swarm/swarm_config.json
        # (like swarm-cli does). We load ONLY SWARM_CONFIG_PATH or the XDG path;
        # if neither exists we leave config empty and BlueprintBase's own
        # working-directory fallback still picks up a ./swarm_config.json — so cwd
        # behavior is unchanged, we only *add* XDG.
        self.config = self._load_swarm_config()

        # REQ-157: PATH-only CLI discovery. Seeds the addable/suggested set.
        # Never writes cli_agents. Never auth-checks or talks to the network.
        self.discovered_clis = self._discover_host_clis()

        # Refuse SWARM_TEST_MODE in non-debug production (silent canned answers).
        try:
            from swarm.utils.env_utils import assert_test_mode_allowed
            assert_test_mode_allowed()
        except Exception as e:
            # Re-raise ImproperlyConfigured; log unexpected errors.
            from django.core.exceptions import ImproperlyConfigured
            if isinstance(e, ImproperlyConfigured):
                raise
            logger.warning("Test-mode guard check failed: %s", e)

        self._warn_if_api_auth_disabled()
        self._check_database()

        # Resume async /v1/responses tasks left in-flight by a restart — server
        # processes only (not migrate/test), guarded against the runserver
        # reloader's parent process to avoid double-resume.
        self._check_uvicorn_workers()
        self._maybe_resume_async_tasks()
        self._maybe_start_schedule_engine()

        logger.info("Swarm app initialization checks completed.")

    @staticmethod
    def _check_database() -> None:
        """Fail fast (exit 78) when Postgres is configured but unusable.

        Skipped under pytest and when SWARM_SKIP_DB_HEALTH is set. SQLite is
        a no-op. See swarm.core.database_config and docs/DATABASE.md.
        """
        from swarm.core.database_config import check_database_or_exit

        check_database_or_exit()

    @staticmethod
    def _warn_if_api_auth_disabled() -> None:
        """Surface the DEBUG / missing-token footgun when the process is serving."""
        import sys

        argv = " ".join(sys.argv)
        serving = any(
            s in argv for s in ("uvicorn", "swarm-api", "gunicorn", "daphne", "runserver")
        )
        if not serving:
            return
        if bool(getattr(settings, "ENABLE_API_AUTH", False)):
            return
        logger.warning(
            "API authentication is OFF (ENABLE_API_AUTH=false — typically DEBUG "
            "without API_AUTH_TOKEN / SWARM_API_KEY). Fine for local development; "
            "do not expose this process on a network without setting an API token."
        )

    @staticmethod
    def _check_uvicorn_workers() -> None:
        """Refuse/warn multi-worker async when serving (process-local inflight)."""
        import sys

        argv = " ".join(sys.argv)
        if not any(s in argv for s in ("uvicorn", "swarm-api", "gunicorn", "daphne")):
            # Still validate env when set so unit tests can exercise the helper.
            if not os.environ.get("SWARM_UVICORN_WORKERS"):
                return
        try:
            from swarm.core.concurrency import resolved_uvicorn_workers

            resolved_uvicorn_workers()
        except ValueError as e:
            logger.error("Multi-worker async contract: %s", e)
            raise
        except Exception as e:
            logger.debug("uvicorn workers check skipped: %s", e)

    @staticmethod
    def _maybe_resume_async_tasks() -> None:
        import sys

        if os.environ.get("SWARM_TEST_MODE"):
            return
        argv = " ".join(sys.argv)
        if "runserver" in argv:
            serving = ("--noreload" in argv) or os.environ.get("RUN_MAIN") == "true"
        else:
            serving = any(s in argv for s in ("swarm-api", "daphne", "uvicorn", "gunicorn"))
        if not serving:
            return
        try:
            import threading

            from swarm.views.responses_views import resume_pending_responses

            threading.Thread(target=resume_pending_responses, daemon=True).start()
        except Exception as e:  # never let resume break startup
            logger.warning("Could not schedule async-task resume: %s", e)

    @staticmethod
    def _maybe_start_schedule_engine() -> None:
        """Tick routines + test schedules in this process (not distributed)."""
        import sys

        if os.environ.get("SWARM_TEST_MODE") or os.environ.get("SWARM_DISABLE_SCHEDULE_ENGINE"):
            return
        argv = " ".join(sys.argv)
        if "runserver" in argv:
            serving = ("--noreload" in argv) or os.environ.get("RUN_MAIN") == "true"
        else:
            serving = any(s in argv for s in ("swarm-api", "daphne", "uvicorn", "gunicorn"))
        if not serving:
            return
        try:
            from swarm.core.schedule_engine import start_loop

            start_loop()
        except Exception as e:  # never let the ticker break startup
            logger.warning("Could not start schedule engine: %s", e)

    @staticmethod
    def _load_swarm_config() -> dict:
        """Resolve + load swarm_config.json (XDG-aware), env-substituted. Never raises.

        Loads the JSON leniently (no ``llm``-section requirement) — a CLI-fusion
        gateway config is often ``cli_agents``-only, and the validation in
        ``config_loader.load_config`` would otherwise reject it and lose the config.
        """
        import json
        from pathlib import Path

        from swarm.core import config_loader

        try:
            env_path = os.environ.get("SWARM_CONFIG_PATH")
            if env_path and Path(env_path).is_file():
                path = Path(env_path)
            else:
                # XDG only here; ./swarm_config.json is handled by BlueprintBase's
                # own cwd fallback so we don't change cwd behavior (or break tests
                # that simulate "no config files").
                xdg = config_loader._xdg_config_path()
                path = xdg if xdg.is_file() else None
            if not path:
                logger.info("No XDG/SWARM_CONFIG_PATH swarm_config.json; deferring to cwd fallback.")
                return {}
            raw = json.loads(Path(path).read_text())
            cfg = config_loader._substitute_env_vars(raw)
            logger.info("Swarm config loaded from %s", path)
            return cfg if isinstance(cfg, dict) else {}
        except Exception as e:
            logger.warning("Failed to load swarm config (%s); using empty config.", e)
            return {}

    @staticmethod
    def _discover_host_clis() -> list:
        """Detect catalog CLIs on PATH / known locations. No auth, no network."""
        try:
            from swarm.core.cli_catalog import discover_host_clis

            found = discover_host_clis()
            logger.info(
                "Discovered host CLIs (no auth): %s",
                ", ".join(found) or "none",
            )
            return found
        except Exception as e:
            logger.warning("CLI host discovery skipped: %s", e)
            return []

