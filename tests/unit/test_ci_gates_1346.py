"""#1346 — local CI gates cover the three holes left by the first runner.

Actions still cannot start until the spending limit is restored. What a
checkout can reproduce is the rest of the gate sequence: the other Python
matrix leg, a real Postgres migrate (including the social_django tables), and
the barebones import on the other image architecture.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    path = REPO / "scripts" / "ci_gates.py"
    spec = importlib.util.spec_from_file_location("ci_gates_1346", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass() looks the class up in sys.modules while the body executes.
    sys.modules["ci_gates_1346"] = module
    spec.loader.exec_module(module)
    return module


ci = _load()


def test_default_selection_includes_the_gaps_and_skips_frontend():
    selected = ci.select_gates()
    assert selected == [
        "lock",
        "migration-graph",
        "sanitization",
        "tests",
        "py313",
        "barebones",
        "deploy-profile",
        "barebones-foreign",
        "postgres-migrate",
    ]


def test_quick_skips_only_the_full_suite():
    selected = ci.select_gates(quick=True)
    assert "tests" not in selected
    assert selected[0] == "lock"
    assert selected[1] == "migration-graph"
    assert "py313" in selected
    assert "postgres-migrate" in selected
    assert "barebones-foreign" in selected


def test_migration_graph_follows_the_lock_and_does_not_rewrite_it():
    # `uv run` updates uv.lock unless --frozen. That must not happen before
    # `uv lock --check`, or a drifted lock is rewritten and the lock gate passes.
    assert ci.ORDER.index("lock") < ci.ORDER.index("migration-graph")
    argv = ci.GATES["migration-graph"].commands[0]
    assert argv[:4] == ("uv", "run", "--frozen", "pytest")
    assert "tests/core/test_swarm_migration_graph.py" in argv
    quick = ci.select_gates(quick=True)
    assert quick.index("migration-graph") == quick.index("lock") + 1
    lock_at = ci.ORDER.index("lock")
    assert ci.ORDER.index("migration-graph") > lock_at
    # main() does not stop on a failed gate, so a later unfrozen `uv run`
    # would still rewrite uv.lock after `uv lock --check` has failed.
    for name, gate in ci.GATES.items():
        for command in gate.commands:
            if command[:2] == ("uv", "run"):
                assert "--frozen" in command, name
    source = (REPO / "scripts" / "ci_gates.py").read_text(encoding="utf-8")
    unfrozen = re.findall(
        r"""["']uv["']\s*,\s*["']run["']\s*,\s*["'](?!--frozen)[^"']*["']""",
        source,
    )
    assert unfrozen == []


def test_only_keeps_the_requested_order_and_rejects_unknown_names():
    assert ci.select_gates(only="postgres-migrate,lock") == ["postgres-migrate", "lock"]
    with pytest.raises(ValueError, match="unknown gate"):
        ci.select_gates(only="neon")


def test_with_frontend_appends_the_vitest_gate():
    selected = ci.select_gates(with_frontend=True, quick=True)
    assert selected[-1] == "frontend"


def test_matrix_leg_is_the_interpreter_the_venv_is_not():
    assert ci.matrix_leg("3.12") == "3.13"
    assert ci.matrix_leg("3.13") == "3.12"
    assert ci.matrix_leg("3.14") == "3.13"


def test_foreign_target_is_the_other_image_arch():
    arm = ci.foreign_target("x86_64")
    assert arm.arch == "aarch64"
    assert arm.linker == "ld-linux-aarch64.so.1"
    amd = ci.foreign_target("aarch64")
    assert amd.arch == "x86_64"
    assert amd.qemu_names[0] == "qemu-x86_64-static"
    with pytest.raises(ValueError, match="unsupported machine"):
        ci.foreign_target("riscv64")


def test_sysroot_requires_linker_libc_libz_and_libgcc(tmp_path: Path):
    target = ci.foreign_target("x86_64")
    lib = tmp_path / "lib"
    lib.mkdir()
    for name in (target.linker, "libc.so.6", "libz.so.1", "libgcc_s.so.1"):
        (lib / name).write_text("x", encoding="utf-8")
    assert ci.sysroot_satisfies(tmp_path, target.linker)
    (lib / "libz.so.1").unlink()
    assert not ci.sysroot_satisfies(tmp_path, target.linker)


def test_prereq_message_names_qemu_and_libz():
    message = ci.foreign_prereq_message(ci.foreign_target("x86_64"))
    assert "qemu-aarch64-static" in message
    assert "libz.so.1" in message
    assert "QEMU_LD_PREFIX" in message


def test_pick_cpython_url_prefers_the_newest_default_gnu_build():
    rows = [
        {
            "key": "cpython-3.12.1-linux-aarch64-gnu",
            "version": "3.12.1",
            "url": "https://example.invalid/old",
            "os": "linux",
            "variant": "default",
            "implementation": "cpython",
            "arch": "aarch64",
            "libc": "gnu",
        },
        {
            "key": "cpython-3.12.14-linux-aarch64-gnu",
            "version": "3.12.14",
            "url": "https://example.invalid/new",
            "os": "linux",
            "variant": "default",
            "implementation": "cpython",
            "arch": "aarch64",
            "libc": "gnu",
        },
        {
            "key": "cpython-3.12.14+freethreaded-linux-aarch64-gnu",
            "version": "3.12.14",
            "url": "https://example.invalid/free",
            "os": "linux",
            "variant": "default",
            "implementation": "cpython",
            "arch": "aarch64",
            "libc": "gnu",
        },
        {
            "key": "cpython-3.12.9-linux-aarch64-gnu",
            "version": "3.12.9",
            "url": "https://example.invalid/nine",
            "os": "linux",
            "variant": "default",
            "implementation": "cpython",
            "arch": "aarch64",
            "libc": "gnu",
        },
        {
            "key": "cpython-3.12.14-linux-x86_64-gnu",
            "version": "3.12.14",
            "url": "https://example.invalid/amd64",
            "os": "linux",
            "variant": "default",
            "implementation": "cpython",
            "arch": "x86_64",
            "libc": "gnu",
        },
    ]
    # String order ranks 3.12.9 above 3.12.14. The download must not.
    assert ci.pick_cpython_url(rows, "aarch64") == "https://example.invalid/new"


def test_migrate_env_replaces_any_external_database():
    base = {
        "PATH": "/usr/bin",
        "DATABASE_URL": "postgres://user:secret@ep-neon.example/db",
        "POSTGRES_HOST": "ep-neon.example",
        "DJANGO_DB_NAME": "/tmp/db.sqlite3",
    }
    dsn = ci.ephemeral_dsn(54321)
    env = ci.migrate_subprocess_env(base, dsn)
    assert env["DATABASE_URL"] == "postgres://swarm:swarm@127.0.0.1:54321/swarm"
    assert "POSTGRES_HOST" not in env
    assert "DJANGO_DB_NAME" not in env
    assert env["SWARM_SKIP_DOTENV"] == "1"
    assert env["DJANGO_DEBUG"] == "true"
    assert env["PATH"] == "/usr/bin"


def test_migrate_env_refuses_a_non_loopback_target():
    with pytest.raises(RuntimeError, match="refusing to migrate"):
        ci.migrate_subprocess_env({}, "postgres://swarm:swarm@ep-neon.example/db")


def test_docker_argv_matches_the_actions_service():
    argv = ci.docker_run_argv("os-ci-gate-pg-1")
    assert argv[0] == "docker"
    assert "postgres:16" in argv
    assert "POSTGRES_USER=swarm" in argv
    assert "POSTGRES_PASSWORD=swarm" in argv
    assert "POSTGRES_DB=swarm" in argv
    assert "127.0.0.1::5432" in argv


def test_barebones_env_drops_a_live_database_url():
    env = ci.barebones_env(
        {"DATABASE_URL": "postgres://swarm@ep-neon.example/db", "POSTGRES_HOST": "ep-neon.example"}
    )
    assert "DATABASE_URL" not in env
    assert "POSTGRES_HOST" not in env
    assert env["SWARM_SKIP_DOTENV"] == "1"
    assert env["DJANGO_SECRET_KEY"] == "ci-only-not-a-secret"


def test_social_tables_are_the_1330_migration_targets():
    assert "social_auth_usersocialauth" in ci.SOCIAL_TABLES
    assert "social_auth_partial" in ci.SOCIAL_TABLES
    for name in ci.SOCIAL_TABLES:
        assert name in ci.SOCIAL_CHECK


def test_postgres_candidates_prefer_the_ci_major(monkeypatch):
    monkeypatch.delenv("OS_CI_POSTGRES_BIN", raising=False)
    debian = [
        path
        for path in ci.postgres_bin_candidates()
        if path.parts[:4] == ("/", "usr", "lib", "postgresql")
    ]
    assert [path.parent.name for path in debian] == ["16", "17", "15"]


def test_quick_py313_runs_sanitization_only(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(ci, "project_python_mm", lambda: "3.12")
    monkeypatch.setattr(ci, "ensure_matrix_venv", lambda _version: Path("/tmp/py313/bin/python"))

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return 0, "PASS (0s)"

    monkeypatch.setattr(ci, "_run", fake_run)
    rc, detail = ci.run_py313(quick=True)
    assert rc == 0
    assert len(calls) == 1
    assert any("test_tracked_files_sanitization.py" in part for part in calls[0])
    assert "full suite skipped (--quick)" in detail


def test_deploy_profile_uses_the_dockerfile_extra(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(ci.subprocess, "run", fake_run)
    ci.ensure_profile(tmp_path / "deploy", ".[deploy]")
    assert "--clear" in calls[0]
    assert calls[1][-1] == ".[deploy]"


def test_foreign_python_download_identifies_itself():
    # releases.astral.sh returns 403 to urllib's default User-Agent.
    request = ci.download_request("https://example.invalid/python.tar.gz")
    assert request.get_header("User-agent") == "os-ci-gates"


def test_doc_states_the_billing_limit_is_still_unfixed():
    doc = ci.__doc__ or ""
    assert "admin billing" in doc
    assert "3.13" in doc
    assert "Postgres" in doc
    assert "social_django" in doc
    assert "linux/amd64" in doc
    assert "NOT checked" not in doc
