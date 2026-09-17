"""REQ-868: unconfigured CLI chat errors point at in-app Manage CLI."""

from pathlib import Path

from swarm.blueprints.common.cli_fusion_support import (
    MANAGE_CLI_HREF,
    UNCONFIGURED_CLI_AGENTS_MESSAGE,
    unconfigured_cli_message,
)

REPO = Path(__file__).resolve().parents[2]
BLUEPRINTS = REPO / "src" / "swarm" / "blueprints"


def test_unified_message_points_at_manage_cli():
    assert UNCONFIGURED_CLI_AGENTS_MESSAGE == (
        "No CLI agents are configured. Configure your installed CLIs in "
        "[Manage CLI](/chat?settings=cli-agents) (Settings → CLI Agents)."
    )
    assert MANAGE_CLI_HREF == "/chat?settings=cli-agents"
    assert "docs/CLI_FUSION.md" not in UNCONFIGURED_CLI_AGENTS_MESSAGE


def test_unconfigured_cli_message_keeps_lead():
    text = unconfigured_cli_message("No router CLI is configured")
    assert text.startswith("No router CLI is configured.")
    assert "[Manage CLI](/chat?settings=cli-agents)" in text
    assert "Settings → CLI Agents" in text
    assert unconfigured_cli_message("") == UNCONFIGURED_CLI_AGENTS_MESSAGE
    assert unconfigured_cli_message(None) == UNCONFIGURED_CLI_AGENTS_MESSAGE


def test_blueprint_runtime_errors_do_not_cite_cli_fusion_docs():
    hits = []
    for path in BLUEPRINTS.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "docs/CLI_FUSION.md" in text:
            hits.append(str(path.relative_to(REPO)))
    assert hits == []
