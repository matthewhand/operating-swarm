"""REQ-44: list-models probes for catalogued CLI adapters.

Fixtures mock stdout (never call a live vendor CLI; no secrets).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from swarm.core import cli_catalog
from swarm.core.cli_models import (
    PROBE_TIMEOUT_S,
    ListModelsResult,
    _remember,
    clear_probe_cache,
    list_models,
    list_models_many,
    parse_models_stdout,
    probe_list_models,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cli_models"
PY = sys.executable

REQUIRED_CLIS = ("grok", "claude", "gemini", "codex", "opencode", "pi")


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


def test_parse_pi_list_models_table_fixture():
    # pi --list-models: whitespace table. First-token-only would list provider
    # names (the Aliyun 401 / two-opaque-ids bug). Join provider/model.
    models = parse_models_stdout(_fixture("pi_list_models.txt"))
    assert models == [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
        "bailian-coding-plan/glm-4.7",
        "github-models/openai/gpt-4.1",
    ]
    assert "anthropic" not in models
    assert "openai" not in models
    assert "default" not in models


def test_parse_pi_table_does_not_invent_default_on_empty():
    raw = (
        "provider             model                   context  max-out  thinking  images\n"
    )
    assert parse_models_stdout(raw) == []


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
        "swarm.core.cli_models._resolve_executable",
        lambda *_a, **_k: "/usr/bin/opencode",
    )
    result = await probe_list_models("opencode", run_exec=fake_run)
    assert result.cli == "opencode"
    assert "opencode/big-pickle" in result.models
    assert result.warning is None


async def test_probe_uses_pi_table_fixture_stdout(monkeypatch):
    stdout = _fixture("pi_list_models.txt")

    async def fake_run(argv, timeout):
        assert argv[0].endswith("pi") or argv[0] == "/usr/bin/pi"
        assert argv[1:] == ["--list-models"]
        return 0, stdout, ""

    monkeypatch.setattr(
        "swarm.core.cli_models._resolve_executable", lambda *_a, **_k: "/usr/bin/pi"
    )
    result = await probe_list_models("pi", run_exec=fake_run)
    assert result.cli == "pi"
    assert result.models[0] == "anthropic/claude-sonnet-4-6"
    assert "openai/gpt-4o" in result.models
    assert "openai" not in result.models
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


def test_missing_cli_falls_back_to_catalog_presets(monkeypatch):
    monkeypatch.setattr("swarm.core.cli_catalog.which_cli", lambda exe: None)
    result = list_models("claude")
    assert result.models == list(cli_catalog.CLI_MODELS["claude"])
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
    # Real sleeper subprocess — must return quickly, honestly empty (#272
    # contract: timeout serves last-good/empty, never fabricated presets).
    monkeypatch.setitem(
        cli_catalog.LIST_MODELS, "grok", [PY, "-c", "import time; time.sleep(30)"]
    )
    t0 = time.monotonic()
    result = list_models("grok", timeout=0.4)
    elapsed = time.monotonic() - t0
    assert result.models == []
    assert "timed out" in (result.warning or "").lower()
    assert elapsed < 8.0  # TERM_GRACE + buffer; must not wait the full 30s


def test_failed_probe_falls_back_no_secrets_in_warning(monkeypatch):
    async def fake_run(argv, timeout):
        return 2, "", "auth failed sk-thisisafakekeybutlongenough"

    monkeypatch.setattr(
        "swarm.core.cli_models._resolve_executable", lambda *_a, **_k: "/usr/bin/claude"
    )
    result = asyncio_run_probe("claude", fake_run)
    # Runtime failure is honest: empty models (not presets), redacted warning.
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


PRESET_CLIS = ("qwen", "omp", "claude", "codex", "gemini", "opencode", "agy", "grok")


def test_catalog_presets_cover_all_dropdown_clis():
    for name in PRESET_CLIS:
        presets = cli_catalog.CLI_MODELS.get(name) or []
        assert presets, f"{name} must list catalog model presets"
    assert cli_catalog.CLI_MODELS["qwen"] == [
        "qwen2.5-coder:32b",
        "qwen2.5-coder:7b",
        "qwen2.5:72b",
    ]
    assert cli_catalog.CLI_MODELS["omp"] == [
        "litellm/orchestration",
        "gemini-2.5-flash",
        "claude-3-5-sonnet",
    ]


def test_qwen_falls_back_to_catalog_presets_without_probe():
    result = list_models("qwen")
    assert result.models == list(cli_catalog.CLI_MODELS["qwen"])
    assert "catalog presets" in (result.warning or "")


def test_omp_falls_back_to_catalog_presets_without_probe():
    result = list_models("omp")
    assert result.models == list(cli_catalog.CLI_MODELS["omp"])
    assert "catalog presets" in (result.warning or "")


async def test_probe_falls_back_to_presets_when_stdout_empty(monkeypatch):
    async def fake_run(argv, timeout):
        return 0, "", ""

    monkeypatch.setattr(
        "swarm.core.cli_models._resolve_executable", lambda *_a, **_k: "/usr/bin/grok"
    )
    result = await probe_list_models("grok", run_exec=fake_run)
    # Empty stdout from an installed CLI is a runtime outcome, not a missing
    # CLI: report honestly empty, never fabricated presets (#272 contract).
    assert result.models == []
    assert "no model ids" in (result.warning or "")


def test_missing_cli_presets_do_not_clobber_last_good():
    """Presets are a display hint: they never evict last-good (#272)."""
    real = ListModelsResult(cli="grok", models=["real-model"])
    clear_probe_cache()
    assert _remember(real).models == ["real-model"]
    missing = ListModelsResult(
        cli="grok",
        models=list(cli_catalog.CLI_MODELS["grok"]),
        warning="grok: CLI not installed (no 'grok' on PATH)",
    )
    served = _remember(missing)
    assert served.models == list(cli_catalog.CLI_MODELS["grok"])
    from swarm.core import cli_models as cm

    with cm._CACHE_LOCK:
        entry = cm._RESULT_CACHE["grok"]
        assert entry.last_good is not None
        assert list(entry.last_good.models) == ["real-model"]


def test_default_probe_timeout_is_bounded():
    assert PROBE_TIMEOUT_S <= 1.5
    assert cli_catalog.LIST_MODELS_TIMEOUT <= 1.5


def test_concurrent_hanging_clis_do_not_stack_timeouts(monkeypatch):
    # Two real sleepers through the shipped _run_exec path. Concurrent + short
    # probe grace must finish in ~one timeout, not two sequential 30s hangs.
    sleeper = [PY, "-c", "import time; time.sleep(30)"]
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", sleeper)
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "claude", list(sleeper))
    clear_probe_cache()
    t0 = time.monotonic()
    rows = list_models_many(["grok", "claude"], timeout=0.4)
    elapsed = time.monotonic() - t0
    assert {row.cli for row in rows} == {"grok", "claude"}
    assert all(row.models == [] for row in rows)
    assert all("timed out" in (row.warning or "").lower() for row in rows)
    assert elapsed < 3.0


def test_cache_skips_second_shipped_probe(monkeypatch, tmp_path):
    count = tmp_path / "count"
    count.write_text("0")
    script = tmp_path / "probe.py"
    script.write_text(
        "from pathlib import Path\n"
        f"p = Path({str(count)!r})\n"
        "p.write_text(str(int(p.read_text() or '0') + 1))\n"
        "print('cached-model')\n"
    )
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", [PY, str(script)])
    clear_probe_cache()
    first = list_models_many(["grok"])
    second = list_models_many(["grok"])
    assert first[0].models == ["cached-model"]
    assert second[0].models == ["cached-model"]
    assert first[0].warning is None
    assert count.read_text().strip() == "1"


def test_expired_cache_returns_immediately_without_waiting(monkeypatch, tmp_path):
    script = tmp_path / "probe.py"
    script.write_text("print('stale-model')\n")
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", [PY, str(script)])
    clear_probe_cache()
    first = list_models_many(["grok"])
    assert first[0].models == ["stale-model"]
    from swarm.core import cli_models as cm

    with cm._CACHE_LOCK:
        cm._RESULT_CACHE["grok"].ts = time.monotonic() - cm.PROBE_CACHE_TTL_S - 1
    monkeypatch.setitem(
        cli_catalog.LIST_MODELS, "grok", [PY, "-c", "import time; time.sleep(30)"]
    )
    t0 = time.monotonic()
    second = list_models_many(["grok"])
    elapsed = time.monotonic() - t0
    assert second[0].models == ["stale-model"]
    assert elapsed < 0.5


def test_failed_refresh_keeps_last_good_models(monkeypatch, tmp_path):
    mode = tmp_path / "mode"
    mode.write_text("ok")
    script = tmp_path / "probe.py"
    script.write_text(
        "from pathlib import Path\n"
        f"mode = Path({str(mode)!r}).read_text().strip()\n"
        "if mode == 'ok':\n"
        "    print('keep-me')\n"
        "else:\n"
        "    raise SystemExit('auth expired')\n"
    )
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", [PY, str(script)])
    clear_probe_cache()
    ok = list_models_many(["grok"])
    assert ok[0].models == ["keep-me"]
    mode.write_text("fail")
    from swarm.core import cli_models as cm

    cm._refresh_names(["grok"], timeout=2.0)
    served = list_models_many(["grok"])
    assert served[0].models == ["keep-me"]
    assert "failed" in (served[0].warning or "").lower()

