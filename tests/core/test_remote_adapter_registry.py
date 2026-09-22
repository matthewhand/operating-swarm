"""#812 (slice 1) — the RemoteAdapter base + registry, and the first two
strangler migrations (TrueForge, Letta).

``operate()`` routes ``trueforge`` and ``letta`` through the adapter registry
so the if/elif chain stops growing. The adapters forward to the same
implementations the existing suites pin (``test_trueforge_remote.py``,
``test_letta_remote.py``) — behavior unchanged, dispatch polymorphic.
Unregistered kinds keep the legacy chain exactly as-is.
"""

import asyncio

import pytest
from unittest.mock import patch

from swarm.core.remotes import RemoteSpec


def _spec(kind: str, rid: str | None = None) -> RemoteSpec:
    return RemoteSpec(
        id=rid or kind,
        title=rid or kind,
        host_label=kind,
        base_url="http://127.0.0.1:9" if kind != "herdr" else "",
        kind=kind,
    )


class TestRegistry:
    def test_registry_holds_migrated_kinds(self):
        from swarm.remotes.registry import REMOTE_ADAPTER_REGISTRY
        from swarm.remotes.trueforge import TrueForgeAdapter
        from swarm.remotes.letta import LettaAdapter

        assert REMOTE_ADAPTER_REGISTRY["trueforge"] is TrueForgeAdapter
        assert REMOTE_ADAPTER_REGISTRY["letta"] is LettaAdapter

    def test_create_remote_adapter_returns_instance(self):
        from swarm.remotes.registry import create_remote_adapter
        from swarm.remotes.trueforge import TrueForgeAdapter

        adapter = create_remote_adapter(_spec("trueforge"))
        assert isinstance(adapter, TrueForgeAdapter)

    def test_create_remote_adapter_unknown_kind_is_none(self):
        from swarm.remotes.registry import create_remote_adapter

        assert create_remote_adapter(_spec("slack")) is None

    def test_register_decorator_rejects_duplicate_kind(self):
        from swarm.remotes.base import RemoteAdapter
        from swarm.remotes.registry import register_remote_adapter

        with pytest.raises(ValueError, match="already registered"):

            @register_remote_adapter("trueforge")
            class _Dup(RemoteAdapter):
                kind = "trueforge"


class TestBaseContract:
    def test_async_contract_methods_exist_and_raise_not_implemented(self):
        from swarm.remotes.base import RemoteAdapter
        from swarm.remotes.trueforge import TrueForgeAdapter

        adapter = TrueForgeAdapter(_spec("trueforge"))
        # Slice 1 ships the *dispatch seam*; the async protocol surface is
        # declared on the base and fills in per-adapter as httpx migration lands.
        with pytest.raises(NotImplementedError):
            asyncio.run(adapter.check_health())
        with pytest.raises(NotImplementedError):
            asyncio.run(adapter.list_agents())
        with pytest.raises(NotImplementedError):
            asyncio.run(adapter.chat("hi"))
        with pytest.raises(NotImplementedError):
            asyncio.run(adapter.list_routines())

    def test_adapter_carries_spec_and_config(self):
        from swarm.remotes.trueforge import TrueForgeAdapter

        spec = _spec("trueforge")
        adapter = TrueForgeAdapter(spec, config={"a": 1})
        assert adapter.spec is spec
        assert adapter.config == {"a": 1}


class TestTrueForgeAdapter:
    def test_list_forwards_to_legacy_impl(self):
        from swarm.core import remotes
        from swarm.remotes.trueforge import TrueForgeAdapter

        spec = _spec("trueforge")
        with patch.object(remotes, "_trueforge_list", return_value="LIST") as m:
            out = TrueForgeAdapter(spec).list(7.5)
        m.assert_called_once_with(spec, 7.5)
        assert out == "LIST"

    def test_send_forwards_with_session(self):
        from swarm.core import remotes
        from swarm.remotes.trueforge import TrueForgeAdapter

        spec = _spec("trueforge")
        with patch.object(remotes, "_trueforge_send", return_value="SENT") as m:
            out = TrueForgeAdapter(spec).send(
                "hi", 12.0, target="tf1", session_id="sess-9"
            )
        m.assert_called_once_with(spec, "hi", "tf1", 12.0, session_id="sess-9")
        assert out == "SENT"

    def test_routines_forwards(self):
        from swarm.core import remotes
        from swarm.remotes.trueforge import TrueForgeAdapter

        spec = _spec("trueforge")
        with patch.object(remotes, "_trueforge_routines", return_value="ROUTINES") as m:
            out = TrueForgeAdapter(spec).routines(8.0)
        m.assert_called_once_with(spec, 8.0)
        assert out == "ROUTINES"


class TestLettaAdapter:
    def test_list_forwards_with_query(self):
        from swarm.core import remotes
        from swarm.remotes.letta import LettaAdapter

        spec = _spec("letta")
        with patch.object(remotes, "_letta_list", return_value="LIST") as m:
            out = LettaAdapter(spec).list(8.0, query="agents")
        m.assert_called_once_with(spec, 8.0, query="agents")
        assert out == "LIST"

    def test_send_floors_short_timeouts(self):
        from swarm.core import remotes
        from swarm.remotes.letta import LettaAdapter

        spec = _spec("letta")
        with patch.object(remotes, "_letta_send", return_value="SENT") as m, \
                patch.object(remotes, "_LETTA_SEND_TIMEOUT_S", 90.0):
            LettaAdapter(spec).send("hi", 5.0, session_id="s1")
        m.assert_called_once_with(
            spec, "hi", 90.0, session_id="s1", target=""
        )

    def test_send_keeps_long_timeouts(self):
        from swarm.core import remotes
        from swarm.remotes.letta import LettaAdapter

        spec = _spec("letta")
        with patch.object(remotes, "_letta_send", return_value="SENT") as m:
            LettaAdapter(spec).send("hi", 45.0, target="a1")
        m.assert_called_once_with(spec, "hi", 45.0, session_id=None, target="a1")


class TestOperateRouting:
    def test_trueforge_send_routes_through_registry(self):
        from swarm.core import remotes

        spec = _spec("trueforge")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_trueforge_send", return_value="OK") as m:
            out = remotes.operate("trueforge", "send", prompt="hello", timeout=20.0)
        assert out == "OK"  # adapter forwards the impl's result unchanged
        m.assert_called_once()

    def test_letta_list_routes_through_registry(self):
        from swarm.core import remotes

        spec = _spec("letta")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_letta_list", return_value="OK") as m:
            remotes.operate("letta", "list", timeout=8.0)
        m.assert_called_once()

    def test_unregistered_kind_keeps_legacy_chain(self):
        from swarm.core import remotes

        spec = _spec("omb")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_omb_list", return_value="OK") as m:
            remotes.operate("omb", "list", timeout=8.0)
        m.assert_called_once()

    def test_trueforge_routines_route_through_adapter(self):
        from swarm.core import remotes

        spec = _spec("trueforge")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_trueforge_routines", return_value="OK") as m:
            remotes.operate("trueforge", "routines", timeout=8.0)
        m.assert_called_once()
