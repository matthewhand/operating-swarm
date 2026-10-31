"""Tests for opt-in memory integration in BlueprintBase (swarm.memory)."""

import asyncio
import logging
import sys

import pytest

from swarm.core.blueprint_base import BlueprintBase
from swarm.memory import MemoryBackend, get_memory_backend

# --- Helpers -----------------------------------------------------------------

class FakeMemoryBackend:
    """In-memory backend implementing the MemoryBackend protocol."""

    def __init__(self, memories=None):
        self.memories = list(memories or [])
        self.search_calls = []
        self.add_calls = []

    def search(self, query, user_id="default"):
        self.search_calls.append((query, user_id))
        return list(self.memories)

    def add(self, messages, user_id="default"):
        self.add_calls.append((messages, user_id))


class EchoBlueprint(BlueprintBase):
    """Minimal concrete blueprint that records the messages run() receives."""

    def __init__(self, *args, **kwargs):
        self.seen_messages = None
        super().__init__(*args, **kwargs)

    async def run(self, messages, **kwargs):
        self.seen_messages = messages
        yield {"messages": [{"role": "assistant", "content": "hello back"}]}

    @property
    def metadata(self):
        return {"title": "Echo", "description": "test blueprint"}


def base_config(extra=None):
    cfg = {
        "llm": {"default": {"provider": "openai", "model": "gpt-mock", "api_key": "test-key"}},
        "settings": {"default_llm_profile": "default", "default_markdown_output": True},
        "blueprints": {},
    }
    cfg.update(extra or {})
    return cfg


def collect(async_gen):
    async def _collect():
        return [chunk async for chunk in async_gen]
    return asyncio.run(_collect())


# --- (a) Strict no-op when memory is not configured ---------------------------

def test_noop_when_memory_unconfigured():
    bp = EchoBlueprint("echo_bp", config=base_config())
    assert bp.memory_backend is None
    # run() must not be wrapped at the instance level
    assert "run" not in bp.__dict__
    messages = [{"role": "user", "content": "hi"}]
    # inject is identity, store is a silent no-op
    assert bp.inject_memory_context(messages) is messages
    bp.store_run_memory(messages, [{"messages": [{"role": "assistant", "content": "x"}]}])
    chunks = collect(bp.run(messages))
    assert bp.seen_messages is messages  # untouched
    assert chunks == [{"messages": [{"role": "assistant", "content": "hello back"}]}]


def test_noop_with_memory_block_missing_backend_key():
    cfg = base_config({"memory": {"user_id": "alice"}})  # no "backend" => disabled
    bp = EchoBlueprint("echo_bp", config=cfg)
    assert bp.memory_backend is None
    assert "run" not in bp.__dict__


# --- (b)+(c) Retrieval injected before run, storage after run ------------------

def test_memory_injected_and_stored_with_top_level_config(monkeypatch):
    fake = FakeMemoryBackend(memories=["User likes green tea"])
    monkeypatch.setattr("swarm.memory.get_memory_backend", lambda cfg, options=None: fake)
    cfg = base_config({"memory": {"backend": "fake", "user_id": "alice"}})
    bp = EchoBlueprint("echo_bp", config=cfg)
    assert bp.memory_backend is fake

    messages = [{"role": "user", "content": "What do I like to drink?"}]
    chunks = collect(bp.run(messages))
    assert chunks == [{"messages": [{"role": "assistant", "content": "hello back"}]}]

    # (b) retrieved memories injected as a leading system message
    assert fake.search_calls == [("What do I like to drink?", "alice")]
    assert bp.seen_messages[0]["role"] == "system"
    assert "User likes green tea" in bp.seen_messages[0]["content"]
    assert bp.seen_messages[1:] == messages

    # (c) post-run storage called with user input + assistant output
    assert len(fake.add_calls) == 1
    stored, user_id = fake.add_calls[0]
    assert user_id == "alice"
    assert {"role": "user", "content": "What do I like to drink?"} in stored
    assert {"role": "assistant", "content": "hello back"} in stored
    # the injected memory system message must not be re-stored
    assert all("Relevant memories" not in m["content"] for m in stored)


def test_memory_enabled_via_per_blueprint_config(monkeypatch):
    fake = FakeMemoryBackend()
    monkeypatch.setattr("swarm.memory.get_memory_backend", lambda cfg, options=None: fake)
    cfg = base_config()
    cfg["blueprints"] = {"echo_bp": {"memory": {"backend": "fake"}}}
    bp = EchoBlueprint("echo_bp", config=cfg)
    assert bp.memory_backend is fake
    # default user id used when none configured
    collect(bp.run([{"role": "user", "content": "hello"}]))
    assert fake.search_calls == [("hello", "default")]
    assert fake.add_calls and fake.add_calls[0][1] == "default"


def test_no_injection_when_search_returns_nothing(monkeypatch):
    fake = FakeMemoryBackend(memories=[])
    monkeypatch.setattr("swarm.memory.get_memory_backend", lambda cfg, options=None: fake)
    cfg = base_config({"memory": {"backend": "fake"}})
    bp = EchoBlueprint("echo_bp", config=cfg)
    messages = [{"role": "user", "content": "hello"}]
    collect(bp.run(messages))
    assert bp.seen_messages == messages  # no system message prepended


def test_backend_errors_do_not_break_run(monkeypatch):
    class ExplodingBackend:
        def search(self, query, user_id="default"):
            raise RuntimeError("search boom")

        def add(self, messages, user_id="default"):
            raise RuntimeError("add boom")

    monkeypatch.setattr(
        "swarm.memory.get_memory_backend", lambda cfg, options=None: ExplodingBackend()
    )
    cfg = base_config({"memory": {"backend": "fake"}})
    bp = EchoBlueprint("echo_bp", config=cfg)
    messages = [{"role": "user", "content": "hello"}]
    chunks = collect(bp.run(messages))  # must not raise
    assert chunks == [{"messages": [{"role": "assistant", "content": "hello back"}]}]
    assert bp.seen_messages == messages


# --- (d) Graceful fallback when mem0 is not installed --------------------------

def test_factory_graceful_when_mem0_missing(monkeypatch, caplog):
    # Setting the sys.modules entry to None makes `import mem0` raise ImportError.
    monkeypatch.setitem(sys.modules, "mem0", None)
    # The app configures the parent 'swarm' logger with propagate=False, which
    # keeps records from reaching caplog's root handler — re-enable for capture.
    monkeypatch.setattr(logging.getLogger("swarm"), "propagate", True)
    with caplog.at_level(logging.WARNING, logger="swarm.memory"):
        backend = get_memory_backend({"backend": "mem0"})
    assert backend is None
    assert any("mem0" in rec.getMessage() for rec in caplog.records)


def test_blueprint_graceful_when_mem0_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "mem0", None)
    cfg = base_config({"memory": {"backend": "mem0"}})
    bp = EchoBlueprint("echo_bp", config=cfg)  # must not raise
    assert bp.memory_backend is None
    assert "run" not in bp.__dict__  # run untouched
    messages = [{"role": "user", "content": "hi"}]
    chunks = collect(bp.run(messages))
    assert chunks == [{"messages": [{"role": "assistant", "content": "hello back"}]}]


# --- Factory / protocol details ------------------------------------------------

def test_factory_returns_none_when_disabled_or_unknown():
    assert get_memory_backend(None) is None
    assert get_memory_backend({}) is None
    assert get_memory_backend({"backend": ""}) is None
    assert get_memory_backend({"backend": "none"}) is None
    assert get_memory_backend({"backend": "totally-unknown"}) is None
    # legacy (name, options) call style still supported
    assert get_memory_backend("none", {}) is None
    assert get_memory_backend("unknown-backend", {"k": "v"}) is None


def test_placeholder_backends_disabled_and_raise():
    from swarm.memory.langmem_memory import LangmemMemory
    from swarm.memory.letta_memory import LettaMemory
    from swarm.memory.papr_memory import PaprMemory

    assert get_memory_backend({"backend": "langmem"}) is None
    assert get_memory_backend({"backend": "letta"}) is None
    assert get_memory_backend({"backend": "papr"}) is None
    with pytest.raises(NotImplementedError):
        LangmemMemory({})
    with pytest.raises(NotImplementedError):
        LettaMemory({})
    with pytest.raises(NotImplementedError):
        PaprMemory({})


def test_fake_backend_satisfies_protocol():
    assert isinstance(FakeMemoryBackend(), MemoryBackend)
