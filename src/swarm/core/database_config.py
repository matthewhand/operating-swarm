"""Django database target resolution and Postgres fail-fast (REQ-123 / #508).

Happy path for durable deploys is **local Postgres in docker compose**.
Cloud operators override with ``DATABASE_URL`` (or ``POSTGRES_*``) pointing
at any Postgres. Neon is test/CI/experiments only — never a default host.

Native pytest, desktop, and tiny demos still fall back to SQLite when
neither ``DATABASE_URL`` nor ``POSTGRES_HOST`` is set.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping, TextIO
from urllib.parse import quote, urlparse, urlunparse

from swarm.core.paths import get_user_data_dir_for_swarm

# sysexits.h EX_CONFIG — systemd RestartPreventExitStatus=78 (Neon runbook).
EX_CONFIG = 78

_QUOTA_MARKERS = (
    "quota",
    "exceeded your compute",
    "compute time",
    "compute units",
    "disabled",
    "cannot connect to compute",
    "endpoint has been disabled",
)

_POSTGRES_ENGINES = frozenset({"postgres", "postgresql", "postgresql_psycopg2"})


def _is_pytest_env(env: Mapping[str, str]) -> bool:
    """True when this process is pytest (isolated sqlite, not operator XDG)."""
    if "PYTEST_VERSION" in env:
        return True
    if env is os.environ and ("pytest" in sys.modules or "PYTEST_VERSION" in os.environ):
        return True
    return False


def _ensure_private_dir(path: Path) -> None:
    """Create ``path`` with user-only permissions (0700)."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _harden_sqlite_file(path: Path) -> None:
    if path.is_file():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def default_sqlite_name() -> str:
    """Native SQLite path: ``<get_user_data_dir_for_swarm()>/db.sqlite3`` (never ``/tmp``)."""
    return str(get_user_data_dir_for_swarm() / "db.sqlite3")


def default_sqlite_test_name() -> str:
    return str(get_user_data_dir_for_swarm() / "test_db.sqlite3")


def _pytest_sqlite_dir() -> Path:
    d = Path(tempfile.gettempdir()) / f"swarm-pytest-{os.getpid()}"
    _ensure_private_dir(d)
    return d


def _env_get(env: Mapping[str, str], key: str) -> str:
    return (env.get(key) or "").strip()


def postgres_selected_without_target(env: Mapping[str, str]) -> bool:
    """``DJANGO_DATABASE=postgres`` but no URL/host — misconfigured."""
    engine = _env_get(env, "DJANGO_DATABASE").lower()
    if engine not in _POSTGRES_ENGINES:
        return False
    return not _env_get(env, "DATABASE_URL") and not _env_get(env, "POSTGRES_HOST")


def resolve_database_url(env: Mapping[str, str] | None = None) -> str | None:
    """Return a Postgres URL when configured, else None (SQLite fallback).

    Precedence: non-empty ``DATABASE_URL``, then ``POSTGRES_HOST`` (+
    ``POSTGRES_*`` parts). ``DJANGO_DATABASE=postgres`` without a host/URL
    is not a URL — callers should treat it as a config error.
    """
    env = os.environ if env is None else env
    explicit = _env_get(env, "DATABASE_URL")
    if explicit:
        return explicit
    host = _env_get(env, "POSTGRES_HOST")
    if not host:
        return None
    user = _env_get(env, "POSTGRES_USER") or "postgres"
    password = env.get("POSTGRES_PASSWORD") or ""
    port = _env_get(env, "POSTGRES_PORT") or "5432"
    dbname = _env_get(env, "POSTGRES_DB") or "swarm"
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"
    return urlunparse(("postgres", netloc, f"/{dbname}", "", "", ""))


def sqlite_name(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    explicit = _env_get(env, "DJANGO_DB_NAME") or _env_get(env, "SQLITE_DB_PATH")
    if explicit:
        return explicit
    if _is_pytest_env(env):
        path = _pytest_sqlite_dir() / "db.sqlite3"
        _harden_sqlite_file(path)
        return str(path)
    path = Path(default_sqlite_name())
    _ensure_private_dir(path.parent)
    _harden_sqlite_file(path)
    return str(path)


def django_databases(env: Mapping[str, str] | None = None) -> dict:
    """Build the Django ``DATABASES`` dict from env (no Neon hostname default)."""
    env = os.environ if env is None else env
    url = resolve_database_url(env)
    if url:
        import dj_database_url

        return {
            "default": dj_database_url.parse(
                url, conn_max_age=600, conn_health_checks=True
            ),
        }
    test_name = _env_get(env, "DJANGO_TEST_DB_NAME")
    if not test_name:
        if _is_pytest_env(env):
            test_name = str(_pytest_sqlite_dir() / "test_db.sqlite3")
        else:
            test_path = Path(default_sqlite_test_name())
            _ensure_private_dir(test_path.parent)
            test_name = str(test_path)
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_name(env),
            "TEST": {
                "NAME": test_name,
                "OPTIONS": {
                    "timeout": 20,
                    "init_command": "PRAGMA journal_mode=WAL;",
                },
            },
        }
    }


def is_postgres_configured(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return bool(resolve_database_url(env)) or postgres_selected_without_target(env)


def redact_database_url(url: str) -> str:
    """Mask userinfo in a database URL for logs."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "<unparseable DATABASE_URL>"
    if parsed.password is None and parsed.username is None:
        return url
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or ""
    netloc = f"{user}:***@{host}{port}" if user else f"***@{host}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def classify_postgres_error(exc: BaseException) -> str:
    """Return ``quota`` or ``unreachable`` from a connection failure."""
    blob = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in blob for marker in _QUOTA_MARKERS):
        return "quota"
    return "unreachable"


def format_fail_fast_message(
    *,
    kind: str,
    detail: str,
    url: str | None = None,
) -> str:
    """Operator-facing message; no secrets. Aligns with the Neon quota runbook."""
    redacted = redact_database_url(url) if url else "(no DATABASE_URL / POSTGRES_HOST)"
    if kind == "missing-target":
        headline = (
            "ERROR: DJANGO_DATABASE selects Postgres, but neither DATABASE_URL "
            "nor POSTGRES_HOST is set."
        )
    elif kind == "quota":
        headline = (
            "ERROR: Postgres is configured but the server rejected the connection "
            "(quota / compute exhausted — common on always-on Neon free tier)."
        )
    else:
        headline = (
            "ERROR: Postgres is configured (DATABASE_URL / POSTGRES_*) "
            "but is unreachable."
        )
    return (
        f"{headline}\n"
        f"  Target: {redacted}\n"
        f"  Detail: {detail}\n"
        "\n"
        "  Durable default is local Postgres in docker compose "
        "(`docker compose up` starts the `postgres` service).\n"
        "  Cloud operators: set DATABASE_URL to any reachable Postgres.\n"
        "  Neon is test/CI/experiments only — never the implied default.\n"
        "  Neon free-tier always-on typically burns the quota by ~day 17.\n"
        "  See docs/DATABASE.md and docs/RUNBOOK_NEON_QUOTA_CRASH_LOOP.md.\n"
        "\n"
        f"Exiting with code {EX_CONFIG} (EX_CONFIG) so systemd can stop "
        "crash-looping (RestartPreventExitStatus=78).\n"
    )


def _connect_postgres(url: str) -> None:
    import psycopg2

    dsn = url
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://") :]
    conn = psycopg2.connect(dsn, connect_timeout=5)
    conn.close()


def should_skip_db_health(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    if _env_get(env, "SWARM_SKIP_DB_HEALTH") in {"1", "true", "yes"}:
        return True
    if "pytest" in sys.modules or "PYTEST_VERSION" in env:
        return True
    return False


def check_database_or_exit(
    env: Mapping[str, str] | None = None,
    *,
    connect: Callable[[str], None] | None = None,
    stream: TextIO | None = None,
    exit_fn: Callable[[int], None] | None = None,
    skip_pytest: bool = True,
) -> None:
    """If Postgres is configured, connect or exit 78 with a clear message.

    SQLite (no URL/host) is a no-op. Pytest is skipped unless ``skip_pytest``
    is false (unit tests inject ``connect``).
    """
    env = os.environ if env is None else env
    stream = sys.stderr if stream is None else stream
    exit_fn = sys.exit if exit_fn is None else exit_fn
    if skip_pytest and should_skip_db_health(env):
        return
    if postgres_selected_without_target(env):
        stream.write(
            format_fail_fast_message(
                kind="missing-target",
                detail="Set DATABASE_URL or POSTGRES_HOST.",
            )
        )
        stream.flush()
        exit_fn(EX_CONFIG)
        return
    url = resolve_database_url(env)
    if not url:
        return
    connect_fn = connect or _connect_postgres
    try:
        connect_fn(url)
    except Exception as exc:
        kind = classify_postgres_error(exc)
        stream.write(
            format_fail_fast_message(
                kind=kind,
                detail=f"{type(exc).__name__}: {exc}",
                url=url,
            )
        )
        stream.flush()
        exit_fn(EX_CONFIG)
