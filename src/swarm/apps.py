import logging
import logging.config
import os  # Import os

from django.apps import AppConfig

# Import Django settings and logging config
from django.conf import settings

from swarm.core.serving_process import detect_process_role

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

        # #800 follow-up: install the 429-report dedup filter on the throttle
        # logger. Must run AFTER dictConfig (which rewrites handlers), and
        # early, so the very first 429 of a process is already counted.
        try:
            from swarm.core.request_logging import install as install_throttle_log_filter

            install_throttle_log_filter()
        except Exception as e:
            logger.warning(
                f"Throttle log dedup filter not installed: {e}. "
                "429 reports will be emitted per rejection as before.",
                exc_info=True,
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

        # Record which install profile booted. The base install is barebones
        # and heavyweight integrations live behind extras, so a boot log that
        # says which extras are live turns a later "why is social_django
        # missing" into a one-line answer. Never raises: reporting must not
        # be able to block startup.
        try:
            from swarm.core.build_info import summary_line

            logger.info("Install profile: %s", summary_line())
        except Exception:
            logger.debug("Could not report install profile", exc_info=True)

        # Blueprint discovery / URL registration happen where needed (e.g. list_models),
        # not at AppConfig.ready().

        # Ensure necessary environment variables for Django are set if not already
        if not os.environ.get("DJANGO_SETTINGS_MODULE"):
             os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
             logger.warning(
                "DJANGO_SETTINGS_MODULE not set, setting default 'swarm.settings'"
            )

        # #1434: copy a legacy tree (or refuse on conflict). Dotenv load already
        # migrated when it ran, so this pass is idempotent and still covers
        # SWARM_SKIP_DOTENV. Pytest must not touch the operator's real tree.
        try:
            from swarm.core.paths import (
                ConfigRootConflict,
                migrate_legacy_config_root,
                startup_should_migrate_config,
            )

            if startup_should_migrate_config():
                migrate_legacy_config_root()
        except ConfigRootConflict:
            raise
        except OSError:
            logger.error(
                "Config root migration failed; refusing to start on a partial tree",
                exc_info=True,
            )
            raise
        except Exception:
            logger.error(
                "Config root migration failed; this process is using the canonical root only",
                exc_info=True,
            )

        # Load the swarm config ONCE and cache it on the AppConfig so every
        # blueprint reads the same file. BlueprintBase._load_configuration already
        # prefers ``apps.get_app_config('swarm').config`` — populating it here from
        # the canonical config root is what makes the server honor swarm_config.json
        # (like swarm-cli does). We load ONLY SWARM_CONFIG_PATH or that root;
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

        # #1342: refuse SWARM_ALLOW_ANONYMOUS / SWARM_DEMO_MODE in non-debug
        # production — they hand any stranger a full logged-in session.
        self._check_public_anonymous()

        self._check_database()

        # Serving hooks (auth warning, worker check, async resume, schedule
        # engine). Policy lives in serving_process (SWARM_PROCESS_ROLE and
        # argv basenames). One log lists what ran and what was skipped.
        self._start_serving_hooks()

        logger.info("Swarm app initialization checks completed.")

    @staticmethod
    def _check_public_anonymous() -> None:
        """#1342: refuse anonymous preview (a full unauthenticated session) on a
        public host, unless the operator sets ``SWARM_ALLOW_PUBLIC_ANONYMOUS=1``.

        Same shape as the ``SWARM_TEST_MODE`` guard in ``ready()``:
        ``ImproperlyConfigured`` is re-raised, anything else is logged so a
        surprise in flag parsing can never block startup.
        """
        try:
            from swarm.middleware import assert_public_anonymous_allowed
            assert_public_anonymous_allowed()
        except Exception as e:
            from django.core.exceptions import ImproperlyConfigured
            if isinstance(e, ImproperlyConfigured):
                raise
            logger.warning("Public-anonymous guard check failed: %s", e)

    @staticmethod
    def _check_database() -> None:
        """Fail fast (exit 78) when Postgres is configured but unusable.

        Skipped under pytest and when SWARM_SKIP_DB_HEALTH is set. SQLite is
        a no-op. See swarm.core.database_config and docs/DATABASE.md.
        """
        from swarm.core.database_config import check_database_or_exit

        check_database_or_exit()

    @staticmethod
    def _log_startup_hooks(outcomes: list[tuple[str, str]]) -> None:
        """One startup line: which serving hooks ran, which did not, and why."""
        started = [name for name, status in outcomes if status == "started"]
        skipped: list[str] = []
        for name, status in outcomes:
            if status == "started":
                continue
            detail = status.removeprefix("skipped: ")
            skipped.append(f"{name} ({detail})")
        logger.info(
            "Startup hooks started: %s; skipped: %s; why: %s",
            ", ".join(started) or "none",
            ", ".join(skipped) or "none",
            detect_process_role().reason,
        )

    @staticmethod
    def _start_serving_hooks() -> None:
        """Run serving-process hooks and log a single started/skipped summary."""
        outcomes: list[tuple[str, str]] = [
            ("api_auth_warning", SwarmConfig._warn_if_api_auth_disabled()),
        ]
        try:
            worker_status = SwarmConfig._check_uvicorn_workers()
        except ValueError as exc:
            outcomes.append(("uvicorn_workers", f"failed: {exc}"))
            outcomes.append(("async_resume", "skipped: uvicorn worker check failed"))
            outcomes.append(("schedule_engine", "skipped: uvicorn worker check failed"))
            SwarmConfig._log_startup_hooks(outcomes)
            raise
        outcomes.append(("uvicorn_workers", worker_status))
        outcomes.append(("async_resume", SwarmConfig._maybe_resume_async_tasks()))
        outcomes.append(("schedule_engine", SwarmConfig._maybe_start_schedule_engine()))
        SwarmConfig._log_startup_hooks(outcomes)

    @staticmethod
    def _warn_if_api_auth_disabled() -> str:
        """Surface the DEBUG / missing-token footgun when the process is serving."""
        role = detect_process_role()
        if not role.warn_auth:
            return f"skipped: {role.reason}"
        if bool(getattr(settings, "ENABLE_API_AUTH", False)):
            return "skipped: ENABLE_API_AUTH is on"
        logger.warning(
            "API authentication is OFF (ENABLE_API_AUTH=false — typically DEBUG "
            "without API_AUTH_TOKEN / SWARM_API_KEY). Fine for local development; "
            "do not expose this process on a network without setting an API token."
        )
        return "started"

    @staticmethod
    def _check_uvicorn_workers() -> str:
        """Refuse/warn multi-worker async when serving (process-local inflight)."""
        role = detect_process_role()
        if not role.check_workers and not os.environ.get("SWARM_UVICORN_WORKERS"):
            return f"skipped: {role.reason}"
        try:
            from swarm.core.concurrency import resolved_uvicorn_workers

            resolved_uvicorn_workers()
        except ValueError as e:
            logger.error("Multi-worker async contract: %s", e)
            raise
        except Exception as e:
            logger.debug("uvicorn workers check skipped: %s", e)
            return f"skipped: {e}"
        return "started"

    @staticmethod
    def _maybe_resume_async_tasks() -> str:
        if os.environ.get("SWARM_TEST_MODE"):
            return "skipped: SWARM_TEST_MODE"
        role = detect_process_role()
        if not role.serving:
            return f"skipped: {role.reason}"
        try:
            import threading

            from swarm.views.responses_views import resume_pending_responses

            threading.Thread(target=resume_pending_responses, daemon=True).start()
        except Exception as e:  # never let resume break startup
            logger.warning("Could not schedule async-task resume: %s", e)
            return f"skipped: {e}"
        return "started"

    @staticmethod
    def _maybe_start_schedule_engine() -> str:
        """Tick routines + test schedules in this process (not distributed)."""
        if os.environ.get("SWARM_TEST_MODE"):
            return "skipped: SWARM_TEST_MODE"
        if os.environ.get("SWARM_DISABLE_SCHEDULE_ENGINE"):
            return "skipped: SWARM_DISABLE_SCHEDULE_ENGINE"
        role = detect_process_role()
        if not role.serving:
            return f"skipped: {role.reason}"
        try:
            from swarm.core.schedule_engine import start_loop

            start_loop()
        except Exception as e:  # never let the ticker break startup
            logger.warning("Could not start schedule engine: %s", e)
            return f"skipped: {e}"
        return "started"

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

