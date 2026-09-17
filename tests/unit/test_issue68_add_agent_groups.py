"""Issue #68: Add Agent popup groups by provider with counts; click filters."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WIZARD_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AddAgentWizard.tsx"
GROUPS_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "addAgentGroups.ts"


def test_wizard_has_blueprint_kind_and_group_filter_surface():
    content = WIZARD_TSX.read_text(encoding="utf-8")
    assert "export type AgentKind = 'cli' | 'api' | 'remote' | 'blueprint'" in content
    assert 'data-testid="kind-option-blueprint"' in content
    assert "manage-agent-groups" in content
    assert "clear-group-filter" in content
    assert "toggleGroupFilter" in content
    assert "groupCliAgents" in content
    assert "groupByOrigin" in content
    assert "groupRemotesByImpl" in content
    assert "Operating Swarm" not in content


def test_group_helper_covers_cli_api_remote_blueprint_ids():
    content = GROUPS_TS.read_text(encoding="utf-8")
    assert "detectedCliProviders" in content
    assert "ORIGIN_CUSTOM" in content
    assert "ORIGIN_CATALOG" in content
    assert "'hermes'" in content
    assert "'omb'" in content
    assert "'rakazo'" in content
    assert "'herdr'" in content
    assert "'open-swarm'" in content
    assert "nested" in content
    assert "OMB" not in content
    assert "Operating Swarm" not in content
