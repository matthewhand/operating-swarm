"""ASCII chrome for the --once TUI dump."""

from swarm.tui.client import RailSeat
from swarm.tui.layout import render_scaffold


def test_render_scaffold_marks_selected_and_placeholder():
    text = render_scaffold(
        [
            RailSeat(id="support", name="Support", kind="api", source="blueprints"),
            RailSeat(id="grok", name="Grok", kind="cli", source="cli-agents"),
        ],
        selected_id="grok",
        base_url="http://127.0.0.1:8000",
    )
    assert "AGENTS" in text
    assert "> Grok" in text
    assert "Support" in text
    assert "Operating Swarm TUI" in text
    assert "placeholder" in text.lower()
    assert "Wave 0" not in text
    assert "Wave 1" not in text
    assert "Open Swarm" not in text
    assert "http://127.0.0.1:8000" in text
    assert "8001" not in text


def test_render_scaffold_groups_seats_under_kind_sections():
    text = render_scaffold(
        [
            RailSeat(id="support", name="Support", kind="api", source="blueprints"),
            RailSeat(id="grok", name="Grok", kind="cli", source="cli-agents"),
            RailSeat(id="team:office", name="Office", kind="team", source="team-rosters"),
            RailSeat(id="night", name="Night", kind="remote", source="remotes"),
        ],
        selected_id="grok",
        base_url="http://127.0.0.1:8000",
    )
    # Rail column is the first cell between box borders.
    rail_cells = [line.split("│")[1].strip() for line in text.splitlines() if "│" in line]
    # Section headers present, ordered CLI / API / Blueprint / Remote.
    positions = {
        name: rail_cells.index(name)
        for name in ("CLI", "API", "Blueprint", "Remote")
    }
    assert positions["CLI"] < positions["API"] < positions["Blueprint"] < positions["Remote"]
    assert "> Grok" in rail_cells
    assert "Support" in rail_cells
    assert "Office" in rail_cells
    assert "Night" in rail_cells
    assert rail_cells.index("Support") > positions["API"]
    assert rail_cells.index("Night") > positions["Remote"]


def test_render_scaffold_empty_rail_is_honest():
    text = render_scaffold([], base_url="http://127.0.0.1:8000")
    assert "none" in text.lower()
    assert "placeholder" in text.lower()
