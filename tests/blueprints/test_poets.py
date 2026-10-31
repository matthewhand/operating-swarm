"""Poets blueprint: hermetic SWARM_TEST_MODE unit and integration coverage."""

from __future__ import annotations

import pytest

from swarm.blueprints.poets.blueprint_poets import PoetsBlueprint
from swarm.core.kind_bases import TeamKindBase


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
    assert issubclass(PoetsBlueprint, TeamKindBase)
    assert PoetsBlueprint.metadata.get("title")
    assert PoetsBlueprint.metadata.get("name") == "poets"
    bp = PoetsBlueprint(blueprint_id="poets")
    assert bp.blueprint_id == "poets"


@pytest.mark.asyncio
async def test_test_mode_produces_poem():
    bp = PoetsBlueprint(blueprint_id="poets")
    chunks = await _collect(bp.run([{"role": "user", "content": "Write a sonnet about the night"}]))
    text = _final_content(chunks)
    assert text is not None
    assert "poem" in text.lower() or "moon" in text.lower() or "night" in text.lower()
