"""REQ-871 — source lock for the swarm-cli blueprint lifecycle.

Spec of record: docs/qa/REQ-871-cli-blueprint-lifecycle.md
Behaviour tests: tests/cli/test_blueprint_lifecycle.py,
tests/cli/test_session_command.py

These assert the *shape* the spec promises, so a later refactor cannot quietly
re-introduce the dead test-mode branch, drop an alias, make ``launch`` fail
instead of falling back to source, or grow a parallel session store.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "src" / "swarm" / "core" / "swarm_cli.py"
PLAN = REPO / "docs" / "qa" / "REQ-871-cli-blueprint-lifecycle.md"


def _cli() -> str:
    return CLI.read_text(encoding="utf-8")


def _compile_helper_body() -> str:
    """``_compile_blueprint_executable`` body, up to the next command."""
    body = _cli().split("def _compile_blueprint_executable", 1)[1]
    return body.split('@app.command(name="compile")', 1)[0]


def test_req871_compile_is_primary_with_both_aliases():
    text = _cli()
    for decorator in ('@app.command(name="compile")', '@app.command(name="install-executable")', '@app.command(name="install")'):
        assert decorator in text


def test_req871_all_three_names_share_one_build_body():
    text = _cli()
    assert text.count("_compile_blueprint_executable(") == 4  # def + 3 call sites


def test_req871_compile_has_exactly_one_test_mode_branch():
    """The second, unreachable branch (debt P2-8) must stay deleted."""
    assert _compile_helper_body().count('os.environ.get("SWARM_TEST_MODE")') == 1


def test_req871_compile_keeps_both_escape_guards():
    body = _compile_helper_body()
    assert "Install path escapes bin directory" in body
    assert "Build path escapes cache directory" in body


def test_req871_launch_falls_back_to_source_without_prompting():
    text = _cli()
    assert "def _source_launch_target" in text
    assert '"installed source"' in text
    assert '"bundled source"' in text
    assert "input(" not in text


def test_req871_delete_exposes_source_binary_and_all():
    text = _cli()
    for flag in ('"--source"', '"--binary"', '"--all"'):
        assert flag in text
    assert "def _remove_blueprint_source" in text
    assert "def _remove_blueprint_binary" in text


def test_req871_list_reports_launcher_kind():
    text = _cli()
    assert "def _launcher_kind" in text
    assert "_launcher_kind(item)" in text


def test_req871_session_subcommand_reads_chat_store_only():
    text = _cli()
    assert 'app.add_typer(session_app, name="session")' in text
    assert '@session_app.command("list")' in text
    assert '@session_app.command("show")' in text
    assert "chat_store.store_dir()" in text


def test_req871_no_parallel_cache_session_store():
    """The TODO's ``~/.cache/swarm/sessions`` store is not a thing we build."""
    text = _cli()
    assert 'cache_root / "sessions"' not in text
    assert '/ "sessions"' not in text


def test_req871_plan_doc_is_shipped():
    assert PLAN.is_file()
    text = PLAN.read_text(encoding="utf-8")
    assert "REQ-871" in text
    assert "test_req871_cli_blueprint_lifecycle.py" in text
