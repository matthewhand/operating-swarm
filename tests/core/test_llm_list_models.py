"""REQ-43 consumes REQ-44 {cli, models} — no --help scrape."""

from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path

from swarm.core import cli_catalog, llm_list_models
from swarm.core.llm_task_routing import (
    TASK_CLASS_AUXILIARY,
    TASK_CLASS_DELEGATION,
    TASK_CLASS_ORCHESTRATION,
    auto_pick_task_models,
    collect_catalog,
    discover_and_collect,
    settings_public_payload,
)

FIXTURES = Path(__file__).parent / "fixtures" / "llm_list_models"
V1_MODELS = FIXTURES / "v1_models.json"
OPENCODE = FIXTURES / "opencode.json"
GEMINI = FIXTURES / "gemini.json"
CONSUMER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "swarm"
    / "core"
    / "llm_list_models.py"
)


def test_consumer_does_not_scrape_help_or_spawn_clis():
    tree = ast.parse(CONSUMER.read_text(encoding="utf-8"))
    imported = []
    help_argv = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append((node.module or "").split(".")[0])
        elif isinstance(node, ast.Constant) and node.value == "--help":
            help_argv.append(node)
    assert "subprocess" not in imported
    assert "asyncio" not in imported
    assert help_argv == []


def test_v1_models_fixture_maps_to_three_distinct_classes():
    payload = json.loads(V1_MODELS.read_text(encoding="utf-8"))
    rows = llm_list_models.normalize_list_models_payload(payload)
    assert rows[0]["cli"]
    ids = rows[0]["models"]
    assert "sk-" not in json.dumps(payload)
    result = auto_pick_task_models(ids)
    assert result.picks[TASK_CLASS_AUXILIARY] == "gpt-4o-mini"
    assert result.picks[TASK_CLASS_ORCHESTRATION] == "gpt-5.6-terra"
    assert result.picks[TASK_CLASS_DELEGATION] == "o3"
    assert len(set(result.picks.values())) == 3


def test_req44_cli_payloads_are_consumed_as_catalog():
    rows = llm_list_models.load_list_models_fixtures([OPENCODE, GEMINI])
    clis = {row["cli"] for row in rows}
    assert clis == {"opencode", "gemini"}
    catalog, _, source, warnings = discover_and_collect(
        {"cli_agents": {"opencode": {}, "gemini": {}}},
        discovery_payloads=rows,
    )
    ids = {entry.id for entry in catalog}
    assert "opencode/big-pickle" in ids
    assert "gemini-3-pro-preview" in ids
    assert source in {llm_list_models.SOURCE_STUB, llm_list_models.SOURCE_REQ44}
    assert not any("sk-" in (w or "") for w in warnings)
    result = auto_pick_task_models(
        [entry for entry in catalog if entry.source == "list_models"],
        vendors={
            "opencode/big-pickle": "opencode",
            "opencode": "opencode",
            "opencode/pro": "opencode",
            "gemini-3-flash-preview": "gemini",
            "gemini-2.5-pro": "gemini",
            "gemini-3-pro-preview": "gemini",
        },
    )
    assert len(set(result.picks.values())) == 3


def test_req44_helper_wins_over_stub():
    def fake_helper(name: str):
        return {
            "cli": name,
            "models": ["gpt-4o-mini", "gpt-5.6-terra", "o3"],
        }

    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"openai": {"cmd": ["openai"]}}},
        helper=fake_helper,
        probe=True,
        v1_models={"object": "list", "data": [{"id": "should-not-win"}]},
    )
    assert source == llm_list_models.SOURCE_REQ44
    assert rows[0]["models"] == ["gpt-4o-mini", "gpt-5.6-terra", "o3"]
    assert "should-not-win" not in rows[0]["models"]
    assert not any("sk-" in w for w in warnings)


def test_missing_helper_stubs_on_v1_models_and_does_not_crash():
    payload = json.loads(V1_MODELS.read_text(encoding="utf-8"))
    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"grok": {}}},
        helper=False,
        v1_models=payload,
    )
    assert source == llm_list_models.SOURCE_STUB
    assert rows[0]["models"] == ["gpt-4o-mini", "gpt-5.6-terra", "o3"]
    catalog = collect_catalog({"cli_agents": {"grok": {}}}, discovery_payloads=rows)
    ids = {entry.id for entry in catalog}
    assert "gpt-5.6-terra" in ids
    assert "grok" in ids


def test_empty_list_models_payload_warns_no_crash():
    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"unknown-cli": {}}},
        helper=False,
    )
    assert source == llm_list_models.SOURCE_STUB
    assert warnings
    assert rows[0]["models"] == []
    catalog, _, _, _ = discover_and_collect(
        {"cli_agents": {"unknown-cli": {}}},
        discovery_payloads=rows,
    )
    assert any(entry.id == "unknown-cli" for entry in catalog)


def test_skip_copy_is_calm_and_has_no_ticket_jargon():
    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {},
        helper=lambda name: {"cli": name, "models": ["x"]},
        probe=True,
    )
    assert rows == []
    assert source == llm_list_models.SOURCE_REQ44
    assert warnings == [llm_list_models.SKIPPED_NO_CLI_COPY]
    blob = " ".join(warnings)
    assert "REQ-" not in blob
    assert "#" not in blob
    assert "cli_agents" not in blob


def test_probe_runs_for_installed_clis_when_cli_agents_empty():
    def fake_helper(name: str):
        return {"cli": name, "models": ["grok-4"]}

    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {},
        helper=fake_helper,
        probe=True,
        installed=["grok"],
    )
    assert source == llm_list_models.SOURCE_REQ44
    assert rows[0]["cli"] == "grok"
    assert rows[0]["models"] == ["grok-4"]
    assert not any("REQ-" in w or "#" in w for w in warnings)


def test_sanitize_ui_warning_strips_req_and_issue_numbers():
    raw = "No connected cli_agents; skipped REQ-44 list-models probe."
    cleaned = llm_list_models.sanitize_ui_warning(raw)
    assert "REQ-" not in cleaned
    assert "#" not in cleaned
    assert llm_list_models.sanitize_ui_warnings([raw, "Issue #536 status"]) == [
        llm_list_models.sanitize_ui_warning(raw),
        "status",
    ]


def test_discover_uses_shipped_probe_path(monkeypatch, tmp_path: Path):
    script = tmp_path / "probe.py"
    script.write_text("print('shipped-model')\n")
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", [sys.executable, str(script)])
    llm_list_models.clear_discovery_cache()
    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"grok": {}}},
        probe=True,
    )
    assert source == llm_list_models.SOURCE_REQ44
    assert rows[0]["cli"] == "grok"
    assert rows[0]["models"] == ["shipped-model"]
    assert not any("sk-" in (w or "") for w in warnings)


def test_discover_second_call_does_not_reprobe(monkeypatch, tmp_path: Path):
    count = tmp_path / "count"
    count.write_text("0")
    script = tmp_path / "probe.py"
    script.write_text(
        "from pathlib import Path\n"
        f"p = Path({str(count)!r})\n"
        "p.write_text(str(int(p.read_text() or '0') + 1))\n"
        "print('once-model')\n"
    )
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", [sys.executable, str(script)])
    llm_list_models.clear_discovery_cache()
    first, source, _ = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"grok": {}}},
        probe=True,
    )
    second, _, _ = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"grok": {}}},
        probe=True,
    )
    assert source == llm_list_models.SOURCE_REQ44
    assert first[0]["models"] == ["once-model"]
    assert second[0]["models"] == ["once-model"]
    assert count.read_text().strip() == "1"


def test_discover_probes_configured_clis_concurrently(monkeypatch):
    sleeper = [sys.executable, "-c", "import time; time.sleep(0.55); print('m')"]
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "grok", sleeper)
    monkeypatch.setitem(cli_catalog.LIST_MODELS, "claude", list(sleeper))
    llm_list_models.clear_discovery_cache()
    t0 = time.monotonic()
    rows, source, _ = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"grok": {}, "claude": {}}},
        probe=True,
    )
    elapsed = time.monotonic() - t0
    assert source == llm_list_models.SOURCE_REQ44
    assert {row["cli"] for row in rows} == {"grok", "claude"}
    assert all(row["models"] == ["m"] for row in rows)
    # Sequential would be ~1.1s+; concurrent stays under one sleep plus overhead.
    assert elapsed < 1.0


def test_discover_hanging_cli_is_bounded(monkeypatch):
    monkeypatch.setitem(
        cli_catalog.LIST_MODELS,
        "grok",
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    llm_list_models.clear_discovery_cache()
    t0 = time.monotonic()
    rows, source, warnings = llm_list_models.discover_cli_model_lists(
        {"cli_agents": {"grok": {}}},
        probe=True,
    )
    elapsed = time.monotonic() - t0
    assert source == llm_list_models.SOURCE_REQ44
    assert rows[0]["models"] == []
    assert any("timed out" in (w or "").lower() for w in warnings)
    assert elapsed < 3.0


def test_settings_payload_records_stub_source(tmp_path: Path):
    payload = settings_public_payload(
        {
            "llm": {},
            "cli_agents": {"opencode": {}},
            "v1_models": json.loads(V1_MODELS.read_text(encoding="utf-8")),
        }
    )
    assert payload["list_models_source"] == llm_list_models.SOURCE_STUB
    ids = [row["id"] for row in payload["profiles"]]
    assert "gpt-5.6-terra" in ids
    blob = json.dumps(payload)
    assert "sk-" not in blob
    assert "api_key" not in blob
    assert "--help" not in blob
    assert "REQ-" not in blob
    assert not any("REQ-" in (w or "") or "#" in (w or "") for w in payload["warnings"])
