"""Behavioral tests for the CLI-blueprint audit + progress helpers
(``swarm.blueprints.common.audit`` / ``progress``) and the Chuck's Angels blueprint.

Previously this file mostly asserted that ``print`` / ``print_search_progress_box``
were *called* with the same arguments the test had just passed in — tautological
checks that re-verified the test's own inputs and would pass even if the helper
did nothing. They now assert on the REAL rendered output (via ``capsys``), so a
regression in the formatting or pass-through logic actually fails the test.
"""

from swarm.blueprints.common.audit import AuditLogger
from swarm.blueprints.common.progress import ProgressRenderer


class TestAuditLogger:
    """AuditLogger.log() formats with *args and only emits when enabled."""

    def test_disabled_logger_emits_nothing(self, capsys):
        AuditLogger(enabled=False).log("should not appear")
        assert capsys.readouterr().out == ""

    def test_enabled_logger_emits_message(self, capsys):
        AuditLogger(enabled=True).log("hello world")
        assert "hello world" in capsys.readouterr().out

    def test_enabled_logger_applies_positional_format_args(self, capsys):
        AuditLogger(enabled=True).log("Test {} {}", "message", "with")
        assert "Test message with" in capsys.readouterr().out

    def test_enabled_flag_reflects_constructor(self):
        assert AuditLogger(enabled=True).enabled is True
        assert AuditLogger(enabled=False).enabled is False


class TestProgressRenderer:
    """ProgressRenderer renders through the real print_search_progress_box."""

    def test_init_defaults(self):
        r = ProgressRenderer()
        assert r.default_emoji == "✨"
        assert r.default_border == "╔"
        assert r.default_spinner_states == [
            "Generating.", "Generating..", "Generating...", "Running..."
        ]

    def test_init_custom(self):
        custom = ["Loading", "Processing", "Done"]
        r = ProgressRenderer(default_emoji="🚀", default_border="═", default_spinner_states=custom)
        assert r.default_emoji == "🚀"
        assert r.default_border == "═"
        assert r.default_spinner_states == custom

    def test_render_emits_summary(self, capsys):
        ProgressRenderer().render_progress_box(
            op_type="test_op", results=["alpha", "beta"], summary="My Summary"
        )
        out = capsys.readouterr().out
        assert out.strip(), "render_progress_box produced no output"
        assert "My Summary" in out

    def test_render_defaults_spinner_when_none(self, capsys):
        # spinner_state=None must fall back to the first default frame.
        ProgressRenderer().render_progress_box(
            op_type="op", results=[], summary="needle-none", spinner_state=None
        )
        out = capsys.readouterr().out
        assert "needle-none" in out
        assert "Generating." in out

    def test_render_resolves_float_spinner_state(self, capsys):
        # a numeric spinner_state is resolved via get_spinner_state() into a frame.
        ProgressRenderer().render_progress_box(
            op_type="op", results=[], summary="needle-float", spinner_state=0.0
        )
        out = capsys.readouterr().out
        assert "needle-float" in out
        assert ("Generating" in out) or ("Running" in out)


class TestChucksAngelsBlueprint:
    """The Chuck's Angels blueprint produces deterministic, themed output."""

    def test_init(self):
        from swarm.blueprints.chucks_angels.blueprint_chucks_angels import (
            ChucksAngelsBlueprint,
        )
        blueprint = ChucksAngelsBlueprint(blueprint_id="test_angels")
        assert blueprint.blueprint_id == "test_angels"
        assert blueprint.metadata["name"] == "chucks_angels"
        assert blueprint.metadata["title"] == "Chuck's Angels"
        assert blueprint.metadata["version"] == "0.1.1"
        assert "Chuck Norris" in blueprint.metadata["description"]

    async def test_run_echoes_user_message(self):
        from swarm.blueprints.chucks_angels.blueprint_chucks_angels import (
            ChucksAngelsBlueprint,
        )
        blueprint = ChucksAngelsBlueprint(blueprint_id="test_angels")
        messages = [
            {"role": "user", "content": "Test message"},
            {"role": "assistant", "content": "Response"},
        ]
        results = [r async for r in blueprint.run(messages)]
        assert len(results) == 2
        assert results[0]["role"] == "assistant"
        assert "Chuck's Angels" in results[0]["content"]
        assert "Test message" in results[0]["content"]
        assert "Roundhouse kick" in results[1]["content"]

    async def test_run_handles_no_user_message(self):
        from swarm.blueprints.chucks_angels.blueprint_chucks_angels import (
            ChucksAngelsBlueprint,
        )
        blueprint = ChucksAngelsBlueprint(blueprint_id="test_angels")
        results = [r async for r in blueprint.run([{"role": "assistant", "content": "Response"}])]
        assert len(results) == 2
        assert "No user message found" in results[0]["content"]
