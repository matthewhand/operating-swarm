"""REQ-157 / #565 — CLI agents empty until add; PATH discovery seeds suggestions.

Discovery is PATH / known-location ``which`` only. No auth_check, no login,
no network, no :8001, no secrets, no Wave labels.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from swarm.apps import SwarmConfig
from swarm.blueprints.common.cli_fusion_support import build_registry
from swarm.core import cli_catalog

REPO = Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "req157-cli-agents.yml"
CATALOG = REPO / "src" / "swarm" / "core" / "cli_catalog.py"
VIEW = REPO / "src" / "swarm" / "views" / "api_views.py"
PANE = REPO / "webui" / "frontend" / "src" / "components" / "CliAgentsSettingsPane.tsx"
CONTEXT = REPO / "webui" / "frontend" / "src" / "lib" / "cliAgentContext.ts"
SUPPORT = REPO / "src" / "swarm" / "blueprints" / "common" / "cli_fusion_support.py"
APPS = REPO / "src" / "swarm" / "apps.py"


def test_known_clis_are_documented():
    names = set(cli_catalog.catalog_names())
    # omp (#193) and qwen joined the shipped catalog after REQ-157 froze the
    # original seven; keep the tuple-order contract for all of them.
    assert names == {
        "agy",
        "claude",
        "codex",
        "gemini",
        "grok",
        "kilocode",
        "omp",
        "opencode",
        "pi",
        "qwen",
    }
    assert tuple(cli_catalog.KNOWN_CLIS) == tuple(cli_catalog.catalog_names())
    assert cli_catalog.executable_for("agy") == "agy"


def test_configured_list_empty_until_add_then_remove_rediscover(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_catalog.shutil, "which", lambda exe, path=None: f"/bin/{exe}")
    empty = {}
    assert cli_catalog.configured_cli_names(empty) == []
    assert cli_catalog.configured_cli_names({"cli_agents": {}}) == []
    payload = cli_catalog.cli_agents_catalog_payload(empty)
    assert payload["configured"] == []
    assert "grok" in payload["discovered"]
    assert "grok" in payload["suggestions"]
    assert payload["installed"] == payload["discovered"]
    assert "sk-" not in str(payload)
    assert ":8001" not in str(payload)

    added = {"cli_agents": {"grok": cli_catalog.catalog_entry("grok")}}
    after_add = cli_catalog.cli_agents_catalog_payload(added)
    assert after_add["configured"] == ["grok"]
    assert "grok" not in after_add["suggestions"]
    assert "grok" in after_add["discovered"]

    after_remove = cli_catalog.cli_agents_catalog_payload({"cli_agents": {}})
    assert after_remove["configured"] == []
    assert "grok" in after_remove["suggestions"]


def test_discovery_uses_path_only_no_auth_or_network(monkeypatch):
    def fake_which(exe, path=None):
        return "/usr/bin/codex" if exe == "codex" else None

    monkeypatch.setattr(cli_catalog.shutil, "which", fake_which)
    forbidden = MagicMock(side_effect=AssertionError("discovery must not spawn or auth"))
    monkeypatch.setattr(cli_catalog, "NATIVE_CONSENSUS", cli_catalog.NATIVE_CONSENSUS)
    import subprocess
    import urllib.request

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    found = cli_catalog.discover_host_clis()
    assert found == ["codex"]
    assert cli_catalog.suggested_cli_agents({}) == {
        "codex": cli_catalog.catalog_entry("codex"),
    }
    forbidden.assert_not_called()


def test_empty_path_yields_no_suggestions(monkeypatch):
    monkeypatch.setattr(cli_catalog.shutil, "which", lambda exe, path=None: None)
    assert cli_catalog.discover_host_clis() == []
    assert cli_catalog.suggested_cli_agents({}) == {}
    payload = cli_catalog.cli_agents_catalog_payload({})
    assert payload["discovered"] == []
    assert payload["suggestions"] == {}
    assert payload["configured"] == []


def test_runtime_registry_does_not_auto_wire_path_clis(monkeypatch):
    monkeypatch.setattr(cli_catalog, "installed_catalog_clis", lambda: ["grok", "agy"])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    registry = build_registry({"cli_agents": {}})
    assert registry.names() == []


def test_startup_discovery_helper_is_path_only(monkeypatch):
    monkeypatch.setattr(cli_catalog, "discover_host_clis", lambda: ["pi"])
    assert SwarmConfig._discover_host_clis() == ["pi"]


def test_source_locks_opt_in_and_github_only():
    catalog = CATALOG.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    pane = PANE.read_text(encoding="utf-8")
    context = CONTEXT.read_text(encoding="utf-8")
    support = SUPPORT.read_text(encoding="utf-8")
    apps = APPS.read_text(encoding="utf-8")
    ci = CI.read_text(encoding="utf-8")

    assert "discover_host_clis" in catalog
    assert "cli_agents_catalog_payload" in catalog
    assert "Never ``auth_check``" in catalog or "never ``auth_check``" in catalog
    assert "cli_agents_catalog_payload" in view
    assert "No CLI agents configured yet" in pane
    assert 'aria-label="CLI agents"' in pane
    assert "Show unavailable" in pane
    assert "os-cli-settings-btn" in pane
    assert "info?.configured" in context
    assert "info?.clis" not in context
    assert "installed_catalog_clis" not in support
    assert "discovered_clis" in apps
    assert "_discover_host_clis" in apps
    assert "req157" in ci.lower() or "REQ-157" in ci
    assert "vitest" in ci
    assert "pytest" in ci
    for blob in (catalog, view, pane, context, support, apps, ci):
        assert ":8001" not in blob
        assert "WAVE" not in blob
        assert "sk-" not in blob
        assert "ghp_" not in blob
