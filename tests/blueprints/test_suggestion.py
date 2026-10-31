"""Suggestion blueprint: hermetic SWARM_TEST_MODE unit and integration coverage."""

from __future__ import annotations

import json
import pytest

from swarm.blueprints.suggestion.blueprint_suggestion import SuggestionBlueprint
from swarm.core.blueprint_base import BlueprintBase


async def _collect(gen):
    return [c async for c in gen]


def _final_content(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


@pytest.fixture(autouse=True)
def _test_mode(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-test-key")


def test_metadata_and_subclass():
    assert issubclass(SuggestionBlueprint, BlueprintBase)
    assert SuggestionBlueprint.metadata.get("title")
    assert SuggestionBlueprint.metadata.get("name") == "suggestion"
    bp = SuggestionBlueprint(blueprint_id="suggestion")
    assert bp.blueprint_id == "suggestion"


@pytest.mark.asyncio
async def test_test_mode_produces_structured_suggestions():
    bp = SuggestionBlueprint(blueprint_id="suggestion")
    chunks = await _collect(bp.run([{"role": "user", "content": "How do I optimize database queries?"}]))
    text = _final_content(chunks)
    assert text is not None
    data = json.loads(text)
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)
    assert len(data["suggestions"]) > 0
