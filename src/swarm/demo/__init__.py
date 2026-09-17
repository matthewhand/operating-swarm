"""Public demo mode (REQ-882 / #279): mocked inference, no paid LLMs."""

from swarm.demo.engine import (
    DemoFrame,
    demo_body_for,
    demo_chips_payload,
    iter_demo_frames,
    match_scenario,
)
from swarm.demo.mode import demo_stream_delay_s, is_demo_mode
from swarm.demo.scenarios import (
    DEMO_SCENARIOS,
    FALLBACK_SCENARIO,
    demo_suggestion_chips,
)

__all__ = [
    "DEMO_SCENARIOS",
    "FALLBACK_SCENARIO",
    "DemoFrame",
    "demo_body_for",
    "demo_chips_payload",
    "demo_stream_delay_s",
    "demo_suggestion_chips",
    "is_demo_mode",
    "iter_demo_frames",
    "match_scenario",
]
