"""Match a visitor prompt to a canned scenario and emit stream frames."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from swarm.demo.scenarios import (
    DEMO_SCENARIOS,
    FALLBACK_SCENARIO,
    DemoScenario,
    demo_suggestion_chips,
)

_CHUNK_SIZE = 48


@dataclass(frozen=True)
class DemoFrame:
    kind: str  # status | chunk | json
    text: str = ""
    payload: dict | None = None


def _norm(value: str) -> str:
    return " ".join((value or "").lower().split())


def match_scenario(prompt: str) -> DemoScenario:
    """Exact chip/prompt wins; otherwise keyword score; else fallback."""
    needle = _norm(prompt)
    if not needle:
        return FALLBACK_SCENARIO
    for row in DEMO_SCENARIOS:
        if needle == _norm(row.chip) or needle == _norm(row.prompt):
            return row
    best: DemoScenario | None = None
    best_score = 0
    for row in DEMO_SCENARIOS:
        score = sum(1 for kw in row.keywords if kw in needle)
        if score > best_score:
            best = row
            best_score = score
    if best_score == 0 or best is None:
        return FALLBACK_SCENARIO
    return best


def _chunks(text: str) -> Iterator[str]:
    body = text or ""
    if not body:
        return
    start = 0
    while start < len(body):
        end = min(len(body), start + _CHUNK_SIZE)
        if end < len(body):
            space = body.rfind(" ", start, end)
            if space > start:
                end = space + 1
        piece = body[start:end]
        if piece:
            yield piece
        start = end


def iter_demo_frames(prompt: str) -> Iterator[DemoFrame]:
    scenario = match_scenario(prompt)
    for line in scenario.status_lines:
        yield DemoFrame(kind="status", text=line)
    for event in scenario.events:
        yield DemoFrame(kind="json", payload=dict(event))
    for piece in _chunks(scenario.body):
        yield DemoFrame(kind="chunk", text=piece)


def demo_body_for(prompt: str) -> str:
    return match_scenario(prompt).body


def demo_chips_payload() -> dict:
    return {"type": "suggestions", "suggestions": demo_suggestion_chips()}
