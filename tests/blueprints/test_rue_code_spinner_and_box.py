"""Spinner and operation-box UX tests for the RueCode blueprint.

Ported from archive/local-main-2025-04 and adapted to current main:
- RueCodeBlueprint is constructed with an explicit config dict because
  the no-config fallback path calls load_full_configuration() with a
  keyword argument it no longer accepts on main.
"""
import pytest

from swarm.blueprints.common.operation_box_utils import display_operation_box
from swarm.blueprints.common.unavailable_seat import NO_MODEL_TURN_LEAD
from swarm.blueprints.rue_code.blueprint_rue_code import RueCodeBlueprint, RueSpinner

TEST_CONFIG = {
    "llm": {"default": {"provider": "openai", "model": "gpt-mock"}},
    "settings": {"default_llm_profile": "default", "default_markdown_output": True},
    "blueprints": {},
    "llm_profile": "default",
    "mcpServers": {},
}


def test_rue_spinner_states():
    spinner = RueSpinner()
    spinner.start()
    states = []
    for _ in range(6):
        spinner._spin()
        states.append(spinner.current_spinner_state())
    assert states[:3] == ["Generating..", "Generating...", "Running..."]
    spinner._start_time -= 11
    assert spinner.current_spinner_state() == spinner.LONG_WAIT_MSG


def test_rue_operation_box_output(capsys):
    spinner = RueSpinner()
    spinner.start()
    display_operation_box(
        title="Rue Test",
        content="Testing operation box",
        spinner_state=spinner.current_spinner_state(),
        emoji="📝"
    )
    captured = capsys.readouterr()
    assert "Rue Test" in captured.out
    assert "Testing operation box" in captured.out
    assert "📝" in captured.out


@pytest.mark.asyncio
async def test_rue_run_refuses_instead_of_fabricating_results(monkeypatch, capsys):
    """The turn must not invent "Code Results" for a repo it never read.

    These fileops / shell tools are real ``function_tool``s but nothing ever
    hands them to a model, so the old response — a table built from the literals
    ``def foo(): ...`` and ``def bar(): ...`` — was fiction presented as an
    analysis of the user's codebase. The #1357 sweep scored it as a 1.9s reply.
    """
    blueprint = RueCodeBlueprint(blueprint_id="test_rue", config=TEST_CONFIG)
    monkeypatch.setattr(blueprint, "render_prompt", lambda *_a, **_k: "prompt")
    out = []
    async for msg in blueprint.run([{"role": "user", "content": "test"}]):
        out.append(msg)
    content = ""
    for chunk in out:
        if isinstance(chunk, dict) and chunk.get("messages"):
            content = str(chunk["messages"][-1].get("content") or "")
    assert content.startswith(NO_MODEL_TURN_LEAD)
    for fabricated in ("def foo()", "def bar()", "Code Results", "Semantic Results"):
        assert fabricated not in content
    # The operation box is still there for the empty-turn error path below.
    capsys.readouterr()


# Edge case: empty user message
@pytest.mark.asyncio
async def test_rue_run_empty(capsys):
    blueprint = RueCodeBlueprint(blueprint_id="test_rue", config=TEST_CONFIG)
    out = []
    async for msg in blueprint.run([{"role": "assistant", "content": "no user"}]):
        out.append(msg)
    captured = capsys.readouterr()
    assert "RueCode Error" in captured.out
    assert out
