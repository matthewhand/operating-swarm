"""REQ-123 / #508: Compose local Postgres; DATABASE_URL override; Neon test-only."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import yaml

from swarm.core.database_config import (
    EX_CONFIG,
    check_database_or_exit,
    classify_postgres_error,
    django_databases,
    format_fail_fast_message,
    postgres_selected_without_target,
    redact_database_url,
    resolve_database_url,
    sqlite_name,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
ENV_EXAMPLE = REPO / ".env.example"
DATABASE_MD = REPO / "docs" / "DATABASE.md"
NEON_RUNBOOK = REPO / "docs" / "RUNBOOK_NEON_QUOTA_CRASH_LOOP.md"
ORACLE_DOCS = REPO / "docs" / "ORACLE_DEPLOY.md"
ORACLE_UNIT = REPO / "deploy" / "oracle" / "open-swarm-oracle.service"
DOCKERFILE = REPO / "Dockerfile"
PYTEST_WORKFLOW = REPO / ".github" / "workflows" / "python-pytest.yml"
SETTINGS = REPO / "src" / "swarm" / "settings.py"
HELPER = REPO / "src" / "swarm" / "core" / "database_config.py"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_compose_postgres_is_default_happy_path():
    data = _compose()
    pg = data["services"]["postgres"]
    swarm = data["services"]["swarm"]
    assert pg["image"].startswith("postgres:")
    assert "swarm_pgdata" in str(pg["volumes"])
    assert pg.get("healthcheck", {}).get("test")
    assert "neon" not in pg["image"].lower()
    env = swarm["environment"]
    url = env["DATABASE_URL"]
    assert "postgres@postgres:5432" in url or "@postgres:5432" in url
    assert "neon.tech" not in url.lower()
    assert env["POSTGRES_HOST"] == "${POSTGRES_HOST:-postgres}"
    assert swarm["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "swarm_pgdata" in data["volumes"]
    # 5432 must not be published on the host by default.
    assert "ports" not in pg
    text = COMPOSE.read_text(encoding="utf-8")
    assert "neon.tech" not in text.lower()
    assert "REQ-123" in text or "#508" in text


def test_compose_does_not_default_sqlite_file():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "db.sqlite3" not in text
    assert "DJANGO_DB_NAME" not in text


def test_compose_caps_swarm_restarts():
    swarm = _compose()["services"]["swarm"]
    assert str(swarm["restart"]).startswith("on-failure")


def test_env_example_documents_override_and_neon_warning():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "DATABASE_URL=" in text
    assert "POSTGRES_HOST" in text
    assert "test/CI" in text or "test-only" in text.lower() or "experiments only" in text
    assert "day 17" in text
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert "neon.tech" not in stripped.lower()
    assert "your-postgres-password" in text
    assert "SWARM_SKIP_DB_HEALTH" in text


def test_short_docs_and_runbook_keep_neon_optional():
    db = DATABASE_MD.read_text(encoding="utf-8")
    runbook = NEON_RUNBOOK.read_text(encoding="utf-8")
    oracle = ORACLE_DOCS.read_text(encoding="utf-8")
    assert "docker compose" in db.lower()
    assert "DATABASE_URL" in db
    assert "test/CI" in db or "test-only" in db.lower() or "experiments only" in db
    assert "day 17" in db
    assert "pytest" in db.lower()
    assert "SQLite" in db
    assert "neon.tech" not in db
    assert "test/CI/experiments only" in runbook or "test/CI/experiments only" in db
    assert "local Postgres" in runbook
    assert "Do **not** point oracle or Fly at Neon" in oracle
    assert "DJANGO_DB_NAME" in oracle


def test_oracle_unit_stays_sqlite_not_neon():
    text = ORACLE_UNIT.read_text(encoding="utf-8")
    assert "DJANGO_DB_NAME=" in text
    assert "db.sqlite3" in text
    assert "neon.tech" not in text.lower()
    assert "RestartPreventExitStatus=78" in text


def test_dockerfile_fail_fast_and_postgres_migrate_branch():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "check_database_or_exit" in text
    assert "DATABASE_URL" in text
    assert "POSTGRES_HOST" in text
    assert "neon.tech" not in text.lower()


def test_ci_policy_sqlite_pytest_and_local_postgres_migrate():
    text = PYTEST_WORKFLOW.read_text(encoding="utf-8")
    assert "postgres-migrate" in text
    assert "postgres:16" in text
    assert "DATABASE_URL: postgres://swarm:swarm@localhost:5432/swarm" in text
    assert "neon.tech" not in text.lower()
    assert "pytest stays on SQLite" in text or "SQLite" in text


def test_settings_and_helper_have_no_neon_default_host():
    for path in (SETTINGS, HELPER):
        blob = path.read_text(encoding="utf-8").lower()
        assert "neon.tech" not in blob
        assert "neon.tech" not in blob.replace(" ", "")


def test_resolve_database_url_precedence():
    assert resolve_database_url({}) is None
    assert resolve_database_url({"DJANGO_DATABASE": "sqlite"}) is None
    url = resolve_database_url({"DATABASE_URL": "postgres://a:b@h:5432/db"})
    assert url == "postgres://a:b@h:5432/db"
    built = resolve_database_url(
        {
            "POSTGRES_HOST": "db",
            "POSTGRES_USER": "u",
            "POSTGRES_PASSWORD": "p@ss/word",
            "POSTGRES_DB": "swarm",
            "POSTGRES_PORT": "5433",
        }
    )
    assert built is not None
    assert "p%40ss%2Fword" in built
    assert "@db:5433/swarm" in built
    # DATABASE_URL wins over POSTGRES_*.
    assert (
        resolve_database_url(
            {
                "DATABASE_URL": "postgres://x:y@cloud:5432/prod",
                "POSTGRES_HOST": "ignored",
            }
        )
        == "postgres://x:y@cloud:5432/prod"
    )


def test_django_databases_sqlite_and_postgres(tmp_path, monkeypatch):
    from swarm.core.paths import get_user_data_dir_for_swarm

    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path / "xdg-data"))
    sqlite = django_databases({})
    assert sqlite["default"]["ENGINE"] == "django.db.backends.sqlite3"
    expected = get_user_data_dir_for_swarm() / "db.sqlite3"
    assert sqlite["default"]["NAME"] == str(expected)
    assert expected.parent.is_dir()
    assert (expected.parent.stat().st_mode & 0o777) == 0o700
    named = django_databases({"DJANGO_DB_NAME": "/var/data/app.sqlite3"})
    assert named["default"]["NAME"] == "/var/data/app.sqlite3"
    assert sqlite_name({"SQLITE_DB_PATH": "/tmp/alt.sqlite3"}) == "/tmp/alt.sqlite3"
    pg = django_databases({"DATABASE_URL": "postgres://u:p@h:5432/db"})
    assert "postgres" in pg["default"]["ENGINE"]
    assert pg["default"]["NAME"] == "db"
    assert pg["default"]["HOST"] == "h"


def test_sqlite_pytest_env_is_isolated_not_tmp_or_xdg():
    from swarm.core.paths import get_user_data_dir_for_swarm

    db = django_databases({"PYTEST_VERSION": "8.0.0"})
    name = db["default"]["NAME"]
    assert name != "/tmp/db.sqlite3"
    assert str(get_user_data_dir_for_swarm()) not in name
    assert "swarm-pytest-" in name
    test_name = db["default"]["TEST"]["NAME"]
    assert test_name != "/tmp/test_db.sqlite3"
    assert "swarm-pytest-" in test_name


def test_postgres_selected_without_target_is_config_error():
    assert postgres_selected_without_target({"DJANGO_DATABASE": "postgres"})
    assert not postgres_selected_without_target(
        {"DJANGO_DATABASE": "postgres", "POSTGRES_HOST": "db"}
    )


def test_redact_and_quota_classification():
    assert (
        redact_database_url("postgres://user:supersecret@db:5432/app")
        == "postgres://user:***@db:5432/app"
    )
    assert classify_postgres_error(RuntimeError("connection refused")) == "unreachable"
    assert (
        classify_postgres_error(RuntimeError("Your project has exceeded the compute time quota"))
        == "quota"
    )


def test_fail_fast_unreachable_exits_78():
    buf = StringIO()
    codes: list[int] = []

    def boom(_url: str) -> None:
        raise ConnectionError("connection refused")

    check_database_or_exit(
        {"DATABASE_URL": "postgres://user:supersecret@db:5432/app"},
        connect=boom,
        stream=buf,
        exit_fn=codes.append,
        skip_pytest=False,
    )
    assert codes == [EX_CONFIG]
    msg = buf.getvalue()
    assert "unreachable" in msg.lower() or "ERROR: Postgres is configured" in msg
    assert "supersecret" not in msg
    assert "user:***" in msg
    assert "day 17" in msg
    assert str(EX_CONFIG) in msg


def test_fail_fast_quota_message():
    buf = StringIO()
    codes: list[int] = []

    def boom(_url: str) -> None:
        raise RuntimeError("compute time quota exceeded")

    check_database_or_exit(
        {"DATABASE_URL": "postgres://n:pw@ep-foo.us-east-2.aws.neon.tech/neondb"},
        connect=boom,
        stream=buf,
        exit_fn=codes.append,
        skip_pytest=False,
    )
    assert codes == [EX_CONFIG]
    msg = buf.getvalue()
    assert "quota" in msg.lower()
    assert "pw" not in msg
    assert "test/CI" in msg or "experiments only" in msg


def test_fail_fast_missing_target():
    buf = StringIO()
    codes: list[int] = []
    check_database_or_exit(
        {"DJANGO_DATABASE": "postgres"},
        stream=buf,
        exit_fn=codes.append,
        skip_pytest=False,
    )
    assert codes == [EX_CONFIG]
    assert "POSTGRES_HOST" in buf.getvalue()


def test_fail_fast_skips_sqlite():
    buf = StringIO()
    codes: list[int] = []
    check_database_or_exit(
        {},
        connect=lambda _url: (_ for _ in ()).throw(RuntimeError("should not connect")),
        stream=buf,
        exit_fn=codes.append,
        skip_pytest=False,
    )
    assert codes == []
    assert buf.getvalue() == ""


def test_fail_fast_message_contains_runbook_pointer():
    msg = format_fail_fast_message(kind="unreachable", detail="x", url="postgres://u:p@h/db")
    assert "RUNBOOK_NEON_QUOTA_CRASH_LOOP.md" in msg
    assert "DATABASE.md" in msg
    assert "p" not in msg.split("Target:", 1)[1].split("\n", 1)[0] or "***" in msg
