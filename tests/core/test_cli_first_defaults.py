"""CLI-first shipped defaults (#151 / #149).

Drives ``build_starter_config`` / ``cli_agents_catalog_payload`` / ``rail_cli_rows``
— the same path ``swarm-cli cli-agents --init`` and ``GET /v1/cli-agents/`` use.
Discovery is PATH/stat only. No LiteLLM catalog edit, no Neon, no secrets.
"""

from __future__ import annotations

from swarm.core import cli_catalog

# Names that must never appear as the CLI-default starting set (#147).
FAKE_CLIS = ("echo", "fake", "dummy", "mock", "testcli", "placeholder")


def _only_grok(exe, path=None):
    return "/usr/bin/grok" if exe == "grok" else None


def _start_set(payload: dict) -> set[str]:
    names = set(payload.get("discovered") or [])
    names.update(payload.get("installed") or [])
    names.update((payload.get("suggestions") or {}).keys())
    for row in payload.get("rail") or []:
        cli = row.get("cli")
        if cli:
            names.add(str(cli))
    return names


def test_shipped_defaults_all_modes_on(monkeypatch):
    """#736 Step 2: gating fully retired — no product-modes key in starter
    configs, and the catalog payload no longer advertises ``modes`` at all
    (legacy clients treat a missing key as all-on)."""
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = cli_catalog.build_starter_config()
    assert "product_modes" not in cfg.get("settings", {})
    payload = cli_catalog.cli_agents_catalog_payload({})
    assert "modes" not in payload
    assert "mode_limitations" not in payload
    rail_ids = {row["id"] for row in payload["rail"]}
    assert "cli_agent" in rail_ids
    assert "api_agent" in rail_ids


def test_shipped_defaults_path_surfaces_only_discovered_clis(monkeypatch):
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = cli_catalog.build_starter_config()
    assert set(cfg["cli_agents"]) == {"grok"}
    assert "pi" not in cfg["cli_agents"]
    payload = cli_catalog.cli_agents_catalog_payload({})
    assert payload["discovered"] == ["grok"]
    assert payload["installed"] == ["grok"]
    assert "pi" not in payload["discovered"]
    assert "pi" not in payload["suggestions"]
    assert "pi" in payload["known"]
    assert payload["rail"][0]["cli"] == "grok"
    assert payload["rail"][0]["installed"] is True
    assert payload["default_cli"] == "grok"


def test_absent_catalog_cli_is_not_invented(monkeypatch):
    monkeypatch.setattr(cli_catalog, "which_cli", lambda exe, path=None: None)
    cfg = cli_catalog.build_starter_config()
    assert cfg["cli_agents"] == {}
    payload = cli_catalog.cli_agents_catalog_payload({})
    assert payload["discovered"] == []
    assert payload["suggestions"] == {}
    assert payload["configured"] == []
    rows = {row["id"]: row for row in payload["rail"]}
    assert rows["cli_agent"]["cli"] == ""
    assert rows["cli_agent"]["installed"] is False
    assert "pi" not in {row.get("cli") for row in payload["rail"]}
    assert "grok" not in {row.get("cli") for row in payload["rail"] if row.get("cli")}
    leaked = _start_set(payload) & set(FAKE_CLIS)
    assert not leaked, leaked


def test_enabling_api_mode_adds_api_agent_rail_row(monkeypatch):
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = {
        "settings": {
            "product_modes": {
                "cli": True,
                "api": True,
                "blueprint": False,
                "team": False,
                "remote": False,
            }
        }
    }
    rows = {row["id"]: row for row in cli_catalog.rail_cli_rows(cfg)}
    assert set(rows) == {"cli_agent", "api_agent"}
    assert rows["api_agent"]["kind"] == "api"
    # #736 Step 2: the stored key is advisory — every seat ships regardless,
    # and the payload carries no ``modes`` advertisement any more.
    payload = cli_catalog.cli_agents_catalog_payload(cfg)
    assert "modes" not in payload
    assert {row["id"] for row in payload["rail"]} == {"cli_agent", "api_agent"}


def test_known_vs_discovered_vs_configured(monkeypatch):
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    empty = cli_catalog.cli_agents_catalog_payload({})
    assert set(empty["known"]) == set(cli_catalog.catalog_names())
    assert empty["configured"] == []
    assert empty["discovered"] == ["grok"]
    added = cli_catalog.cli_agents_catalog_payload(
        {"cli_agents": {"grok": cli_catalog.catalog_entry("grok")}}
    )
    assert added["configured"] == ["grok"]
    assert "grok" not in added["suggestions"]
    assert added["discovered"] == ["grok"]


def test_catalog_and_discovered_exclude_fake_clis(monkeypatch):
    """Issue #147: starting set is discovered host CLIs — no fake/echo CLIs."""
    assert set(cli_catalog.catalog_names()).isdisjoint(FAKE_CLIS)
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    payload = cli_catalog.cli_agents_catalog_payload({})
    surfaced = _start_set(payload)
    leaked = surfaced & set(FAKE_CLIS)
    assert not leaked, leaked
    assert payload["discovered"] == ["grok"]
    assert "pi" not in payload["discovered"]
    # known/clis/catalog may list real catalog names (docs, not the start set)
    assert "pi" in payload["known"]


def test_cli_fusion_default_cli_honoured_when_configured(monkeypatch):
    """Regression: cli_fusion.default_cli beats the alphabetical
    configured-first fallback when the named CLI is configured."""
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = {
        "cli_agents": {
            "agy": cli_catalog.catalog_entry("agy"),
            "opencode": cli_catalog.catalog_entry("opencode"),
        },
        "cli_fusion": {"default_cli": "opencode", "presets": {}},
    }
    payload = cli_catalog.cli_agents_catalog_payload(cfg)
    assert payload["configured"] == ["agy", "opencode"]
    assert payload["default_cli"] == "opencode"


def test_cli_fusion_default_cli_honoured_when_discovered(monkeypatch):
    """The configured default is honoured for a discovered-only CLI too."""

    def fake_which(exe, path=None):
        return f"/usr/bin/{exe}" if exe in {"agy", "opencode"} else None

    monkeypatch.setattr(cli_catalog, "which_cli", fake_which)
    payload = cli_catalog.cli_agents_catalog_payload(
        {"cli_fusion": {"default_cli": "opencode"}}
    )
    assert payload["discovered"] == ["agy", "opencode"]
    assert payload["default_cli"] == "opencode"


def test_cli_fusion_default_cli_ignored_when_absent(monkeypatch):
    """A default naming an absent CLI is ignored — never invented; falls back
    to the configured-first/discovered default."""
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = {
        "cli_agents": {
            "agy": cli_catalog.catalog_entry("agy"),
            "opencode": cli_catalog.catalog_entry("opencode"),
        },
        "cli_fusion": {"default_cli": "pi"},
    }
    payload = cli_catalog.cli_agents_catalog_payload(cfg)
    assert "pi" not in payload["discovered"]
    assert "pi" not in payload["configured"]
    assert payload["default_cli"] == "agy"


def test_cli_fusion_default_cli_unset_falls_back_unchanged(monkeypatch):
    """No cli_fusion block: configured-first, then discovered — untouched."""
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = {
        "cli_agents": {
            "opencode": cli_catalog.catalog_entry("opencode"),
            "agy": cli_catalog.catalog_entry("agy"),
        }
    }
    payload = cli_catalog.cli_agents_catalog_payload(cfg)
    assert payload["default_cli"] == "agy"
    # Nothing configured: discovered fallback (SIDEBAR_CLIS order).
    monkeypatch.setattr(cli_catalog, "which_cli", lambda exe, path=None: "/x")
    empty = cli_catalog.cli_agents_catalog_payload({})
    assert empty["default_cli"] == "grok"


def test_rail_cli_rows_unaffected_by_cli_fusion_default(monkeypatch):
    """The rail CLI seed stays the discovered default; cli_fusion only
    retargets the payload's default_cli."""
    monkeypatch.setattr(cli_catalog, "which_cli", _only_grok)
    cfg = {
        "cli_agents": {"opencode": cli_catalog.catalog_entry("opencode")},
        "cli_fusion": {"default_cli": "opencode"},
    }
    payload = cli_catalog.cli_agents_catalog_payload(cfg)
    assert payload["default_cli"] == "opencode"
    rows = {row["id"]: row for row in payload["rail"]}
    assert rows["cli_agent"]["cli"] == "grok"
