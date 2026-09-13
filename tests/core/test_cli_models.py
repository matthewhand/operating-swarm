"""REQ-44: list-models probes for catalogued CLI adapters.

Fixtures mock stdout (never call a live vendor CLI; no secrets).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from swarm.core import cli_catalog
from swarm.core.cli_models import (
    ListModelsResult,
    list_models,
    parse_models_stdout,
    probe_list_models,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cli_models"
PY = sys.executable

REQUIRED_CLIS = ("grok", "claude", "gemini", "codex", "opencode")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_every_catalog_cli_documents_a_list_models_probe():
    names = set(cli_catalog.catalog_names())
    assert set(REQUIRED_CLIS) <= names
    for name in REQUIRED_CLIS:
        argv = cli_catalog.list_models_argv(name)
        assert argv, f"{name} must document a list-models argv"
        assert argv[0] == cli_catalog.executable_for(name)
        assert argv[0] != "antigravity"  # not wired into CATALOG


def test_list_models_argv_is_a_copy():
    argv = cli_catalog.list_models_argv("opencode")
    argv.append("--mutated")
    assert "--mutated" not in cli_catalog.LIST_MODELS["opencode"]


def test_parse_opencode_line_fixture():
    # opencode models: one provider/model id per line.
    models = parse_models_stdout(_fixture("opencode_models.txt"))
    assert models == [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5",
        "openai/gpt-5.6-terra",
        "opencode/big-pickle",
    ]


def test_parse_gemini_json_fixture():
    # gemini --list-models: JSON array of {modelId, name, ...}.
    models = parse_models_stdout(_fixture("gemini_list_models.json"))
    assert models == [
        "auto",
        "gemini-3-flash-preview",
        "gemini-3-pro-preview",
    ]


def test_parse_codex_models_wrapper_and_slug():
    raw = '{"models": [{"slug": "gpt-5.6-terra"}, {"slug": "gpt-5.4-mini"}]}'
    assert parse_models_stdout(raw) == ["gpt-5.6-terra", "gpt-5.4-mini"]


def test_parse_agy_models_fixture():
    # agy models: tab-separated ``id<TAB>label`` lines; parser takes the first
    # token. The "Fetching available models..." spinner banner goes to stderr
    # and must never appear on stdout; if a banner ever leaks, the header
    # filter drops it instead of listing it as a model.
    raw = (
        "gemini-3.8-flash-high\tGemini 3.8 Flash (High)\n"
        "gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"
        "claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n"
        "Fetching available models...\n"
    )
    assert parse_models_stdout(raw) == [
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
        "claude-sonnet-4-6",
    ]


def test_parse_drops_secrets_and_headers():
    raw = (
        "ID NAME\n"
        "sk-thisisafakekeybutlongenough leftover\n"
        "claude-sonnet-4-6 Sonnet\n"
        "OPENAI_API_KEY=sk-otherfakekeyvalue\n"
    )
    assert parse_models_stdout(raw) == ["claude-sonnet-4-6"]


async def test_probe_uses_opencode_fixture_stdout(monkeypatch):
    stdout = _fixture("opencode_models.txt")

    async def fake_run(argv, timeout):
        assert argv[0].endswith("opencode") or argv[0] == "/usr/bin/opencode"
        assert argv[1:] == ["models"]
        return 0, stdout, ""

    monkeypatch.setattr(
        "swarm.core.cli_models._resolve_executable", lambda *_a, **_k: "/usr/bin/opencode"
    )
    result = await probe_list_models("opencode", run_exec=fake_run)
    assert result.cli == "opencode"
    assert "opencode/big-pickle" in result.models
    assert result.warning is None


async def test_probe_uses_gemini_fixture_stdout(monkeypatch):
    stdout = _fixture("gemini_list_models.json")

    async def fake_run(argv, timeout):
        assert argv[-1] == "--list-models"
        return 0, stdout, ""

    monkeypatch.setattr(
        "swarm.core.cli_models._resolve_executable", lambda *_a, **_k: "/usr/bin/gemini"
    )
    result = await probe_list_models("gemini", run_exec=fake_run)
    assert result.as_dict() == {
        "cli": "gemini",
        "models": ["auto", "gemini-3-flash-preview", "gemini-3-pro-preview"],
    }


def test_unknown_cli_warns_empty_list():
    result = list_models("nope-not-real")
    assert result == ListModelsResult(
        cli="nope-not-real",
        models=[],
        warning="unknown CLI 'nope-not-real'; no list-models probe in the catalog",
    )
    assert result.as_dict()["models"] == []
    assert "unknown CLI" in result.as_dict()["warning"]


def test_missing_cli_warns_empty_list(monkeypatch):
    monkeypatch.setattr("swarm.core.cli_catalog.which_cli", lambda exe: None)
    result = list_models("claude")
    assert result.models == []
    assert "not installed" in (result.warning or "")


def test_stripped_path_probe_finds_user_local_grok(tmp_path, monkeypatch):
    """Daphne-stripped PATH still resolves ~/.local/bin/grok (C-H5)."""
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    grok = local_bin / "grok"
    grok.write_text("#!/bin/sh\n")
    grok.chmod(0o755)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(empty))

    from swarm.core.cli_models import _resolve_executable

    assert _resolve_executable("grok") == str(grok)

    async def fake_run(argv, timeout):
        assert argv[0] == str(grok)
        assert argv[1:] == ["models"]
        return 0, "grok-4.5\n", ""

    import asyncio

    result = asyncio.run(probe_list_models("grok", run_exec=fake_run))
    assert result.models == ["grok-4.5"]
    assert result.warning is None


def test_timeout_does_not_hang(monkeypatch):
    # Real sleeper subprocess — must return quickly with empty + warning.
    monkeypatch.setitem(
        cli_catalog.LIST_MODELS, "grok", [PY, "-c", "import time; time.sleep(30)"]
    )
    t0 = time.monotonic()
    result = list_models("grok", timeout=0.4)
    elapsed = time.monotonic() - t0
    assert result.models == []
    assert "timed out" in (result.warning or "").lower()
    assert elapsed < 8.0  # TERM_GRACE + buffer; must not wait the full 30s


def test_failed_probe_empty_list_no_secrets_in_warning(monkeypatch):
    async def fake_run(argv, timeout):
        return 2, "", "auth failed sk-thisisafakekeybutlongenough"

    monkeypatch.setattr(
        "swarm.core.cli_models._resolve_executable", lambda *_a, **_k: "/usr/bin/claude"
    )
    result = asyncio_run_probe("claude", fake_run)
    assert result.models == []
    assert "sk-thisisafakekeybutlongenough" not in (result.warning or "")
    assert "[REDACTED]" in (result.warning or "")
    assert "failed" in (result.warning or "").lower()


def asyncio_run_probe(name, fake_run):
    import asyncio

    return asyncio.run(probe_list_models(name, run_exec=fake_run))


def test_result_omits_warning_key_when_ok():
    assert ListModelsResult(cli="grok", models=["grok-4"]).as_dict() == {
        "cli": "grok",
        "models": ["grok-4"],
    }
