"""#977 regression pins — ``_compacted_context`` must not NameError.

PR #977 (#900 cross-kind handoff) rewired the compacted-context path to seed
pending hops via ``_apply_pending_api_hop(consumer, ...)``, but the module-level
function referenced a ``consumer`` name that does not exist at module scope and
called ``apply_speaker_identity`` without importing it. Every default-model and
blueprint turn whose compact path failed (DB down, no conversation) died with
``NameError`` before anything was sent.
"""

import pytest

from swarm.consumers import _compacted_context


class _StubConsumer:
    """Bare consumer stand-in: no agent identity, so the hop seed is a no-op."""

    active_agent = None
    default_blueprint = ""


@pytest.mark.asyncio
async def test_hop_seed_receives_the_consumer(monkeypatch):
    """The consumer instance itself reaches the hop seed — not a NameError."""
    import swarm.consumers as consumers_module

    seen = {}

    def fake_apply(consumer, conversation_id, messages):
        seen["consumer"] = consumer
        seen["conversation_id"] = conversation_id
        return list(messages)

    async def fake_compact(conversation_id, messages):
        return list(messages)

    monkeypatch.setattr(consumers_module, "_apply_pending_api_hop", fake_apply)
    monkeypatch.setattr(
        "swarm.core.chat_compact.context_for_conversation", fake_compact
    )
    payload = await _compacted_context(
        _StubConsumer(), "conv-pin", [{"role": "user", "content": "hi"}]
    )
    assert seen["consumer"] is not None
    assert seen["conversation_id"] == "conv-pin"
    assert payload == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_compact_failure_falls_back_without_nameerror(monkeypatch):
    """The filtered-transcript fallback imports speaker identity itself."""

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("swarm.core.chat_compact.context_for_conversation", boom)
    payload = await _compacted_context(
        _StubConsumer(), "conv-pin", [{"role": "user", "content": "hello"}]
    )
    assert payload and payload[0]["role"] == "user"
    assert payload[0]["content"] == "hello"
