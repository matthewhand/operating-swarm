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


# ---------------------------------------------------------------------------
# Slice 2: the remaining nine kinds join the registry; operate()'s if/elif
# chain dies. Dispatch is data-driven — patching the registry changes the
# outcome, and no legacy impl name survives inside operate()'s source.
# ---------------------------------------------------------------------------

SLICE2_KINDS = (
    "herdr",
    "hermes",
    "anythingllm",
    "openwebui",
    "flowise",
    "n8n",
    "omb",
    "rakazo",
    "swarm",
)


class TestSlice2Registry:
    def test_registry_covers_every_declared_kind(self):
        from swarm.core import remotes as remotes_mod
        from swarm.remotes.registry import REMOTE_ADAPTER_REGISTRY

        assert set(REMOTE_ADAPTER_REGISTRY) == set(remotes_mod.REMOTE_KIND_IDS)

    @pytest.mark.parametrize("kind", SLICE2_KINDS)
    def test_each_kind_builds_its_adapter(self, kind):
        from swarm.remotes.registry import create_remote_adapter

        adapter = create_remote_adapter(_spec(kind))
        assert adapter is not None
        assert adapter.kind == kind


class TestSlice2Forwarding:
    def test_herdr_list_forwards_config(self):
        from swarm.core import remotes
        from swarm.remotes.herdr import HerdrAdapter

        spec = _spec("herdr")
        with patch.object(remotes, "_herdr_list", return_value="L") as m:
            HerdrAdapter(spec, config={"c": 1}).list(6.0, query="p")
        m.assert_called_once_with(spec, 6.0, {"c": 1})

    def test_herdr_send_forwards_target_and_config(self):
        from swarm.core import remotes
        from swarm.remotes.herdr import HerdrAdapter

        spec = _spec("herdr")
        with patch.object(remotes, "_herdr_send", return_value="S") as m:
            HerdrAdapter(spec, config={"c": 1}).send("hi", 7.0, target="w3:p1")
        m.assert_called_once_with(spec, "hi", "w3:p1", 7.0, {"c": 1})

    def test_herdr_interrogate_forwards(self):
        from swarm.core import remotes
        from swarm.remotes.herdr import HerdrAdapter

        spec = _spec("herdr")
        with patch.object(remotes, "_herdr_interrogate", return_value="I") as m:
            HerdrAdapter(spec, config=None).interrogate("w3:p1", 8.0, {"c": 1})
        m.assert_called_once_with(spec, "w3:p1", 8.0, {"c": 1})

    def test_hermes_list_ignores_query(self):
        from swarm.core import remotes
        from swarm.remotes.hermes import HermesAdapter

        spec = _spec("hermes")
        with patch.object(remotes, "_hermes_list", return_value="L") as m:
            HermesAdapter(spec).list(8.0, query="x")
        m.assert_called_once_with(spec, 8.0)

    def test_hermes_send_forwards_session(self):
        from swarm.core import remotes
        from swarm.remotes.hermes import HermesAdapter

        spec = _spec("hermes")
        with patch.object(remotes, "_hermes_send", return_value="S") as m:
            HermesAdapter(spec).send("hi", 20.0, session_id="s1")
        m.assert_called_once_with(spec, "hi", 20.0, session_id="s1")

    def test_anythingllm_send_floors_short_timeouts(self):
        from swarm.core import remotes
        from swarm.remotes.anythingllm import AnythingLLMAdapter

        spec = _spec("anythingllm")
        with patch.object(remotes, "_anythingllm_send", return_value="S") as m, \
                patch.object(remotes, "_ANYTHINGLLM_SEND_TIMEOUT_S", 90.0):
            AnythingLLMAdapter(spec).send("hi", 5.0, session_id="s", target="t")
        m.assert_called_once_with(spec, "hi", 90.0, session_id="s", target="t")

    def test_openwebui_forwards_to_openwebui_remote(self):
        from swarm.remotes.openwebui import OpenWebUIAdapter

        spec = _spec("openwebui")
        with patch("swarm.core.openwebui_remote.openwebui_list", return_value="L") as ml, \
                patch("swarm.core.openwebui_remote.openwebui_send", return_value="S") as ms, \
                patch("swarm.core.openwebui_remote.send_timeout", return_value=55.0) as mt:
            OpenWebUIAdapter(spec).list(8.0, query="chats")
            OpenWebUIAdapter(spec).send("hi", 12.0, session_id="s1", target="t")
        ml.assert_called_once_with(spec, 8.0, query="chats")
        mt.assert_called_once_with(12.0)
        ms.assert_called_once_with(spec, "hi", 55.0, session_id="s1", target="t")

    @pytest.mark.parametrize(
        "kind,module,cls,impl_list,impl_send",
        [
            ("flowise", "swarm.remotes.flowise", "FlowiseAdapter", "_flowise_list", "_flowise_send"),
            ("n8n", "swarm.remotes.n8n", "N8nAdapter", "_n8n_list", "_n8n_send"),
        ],
    )
    def test_flowise_n8n_forward_with_query_and_floor(self, kind, module, cls, impl_list, impl_send):
        import importlib

        from swarm.core import remotes

        mod = importlib.import_module(module)
        adapter_cls = getattr(mod, cls)
        spec = _spec(kind)
        with patch.object(remotes, impl_list, return_value="L") as ml, \
                patch.object(remotes, impl_send, return_value="S") as ms, \
                patch.object(remotes, f"_{kind.upper()}_SEND_TIMEOUT_S", 90.0):
            adapter_cls(spec).list(8.0, query="flows")
            adapter_cls(spec).send("hi", 5.0, session_id="s1", target="t")
        ml.assert_called_once_with(spec, 8.0, query="flows")
        expected_timeout = 90.0  # legacy floor: 5.0 < 30 → kind default
        ms.assert_called_once_with(spec, "hi", expected_timeout, session_id="s1", target="t")

    @pytest.mark.parametrize(
        "kind,module,cls",
        [("omb", "swarm.remotes.omb", "OmbAdapter"), ("rakazo", "swarm.remotes.rakazo", "RakazoAdapter"), ("swarm", "swarm.remotes.swarm", "SwarmAdapter")],
    )
    def test_omb_rakazo_swarm_forward_positionally(self, kind, module, cls):
        import importlib

        from swarm.core import remotes

        mod = importlib.import_module(module)
        adapter_cls = getattr(mod, cls)
        spec = _spec(kind)
        with patch.object(remotes, f"_{kind}_list", return_value="L") as ml, \
                patch.object(remotes, f"_{kind}_send", return_value="S") as ms:
            adapter_cls(spec).list(8.0, query="q")
            adapter_cls(spec).send("hi", 9.0, target="t", session_id="s1")
        ml.assert_called_once_with(spec, 8.0)
        ms.assert_called_once_with(spec, "hi", "t", 9.0)


class TestSlice2Operate:
    def test_herdr_list_routes_through_adapter_despite_empty_base_url(self):
        from swarm.core import remotes

        spec = _spec("herdr")
        assert not spec.base_url  # herdr is CLI/SSH — no base_url
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_herdr_list", return_value="OK") as m:
            remotes.operate("herdr", "list", timeout=6.0)
        m.assert_called_once()

    def test_omb_list_routes_through_adapter(self):
        from swarm.core import remotes

        spec = _spec("omb")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_omb_list", return_value="OK") as m:
            remotes.operate("omb", "list", timeout=8.0)
        m.assert_called_once()

    def test_registered_http_kind_with_empty_base_url_still_errors(self):
        from swarm.core import remotes

        spec = _spec("omb")
        spec.base_url = ""
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True):
            out = remotes.operate("omb", "list", timeout=8.0)
        assert out.detail == "base_url is empty"

    def test_interrogate_stays_herdr_only(self):
        from swarm.core import remotes

        spec = _spec("omb")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True):
            out = remotes.operate("omb", "interrogate", target="x", timeout=8.0)
        assert out.ok is False
        assert "interrogate is Herdr-only" in out.detail

    def test_unknown_kind_falls_to_terminal_fallback(self):
        from swarm.core import remotes

        spec = _spec("omb")
        spec.id = "mystery"
        spec.kind = ""
        spec.base_url = "http://127.0.0.1:9"
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True):
            out = remotes.operate("mystery", "list", timeout=8.0)
        assert out.ok is False
        assert "not implemented here" in out.detail

    def test_dispatch_is_registry_driven(self):
        """Open/closed pin: swapping the registry entry swaps the outcome."""
        from swarm.core import remotes
        from swarm.remotes.base import RemoteAdapter
        from swarm.remotes import registry

        spec = _spec("omb")

        class _Stub(RemoteAdapter):
            kind = "omb"

            def list(self, timeout, query=""):
                return "STUBBED"

        original = registry.REMOTE_ADAPTER_REGISTRY["omb"]
        registry.REMOTE_ADAPTER_REGISTRY["omb"] = _Stub
        try:
            with patch.object(remotes, "load_remote", return_value=spec), \
                    patch.object(remotes, "is_configured", return_value=True):
                out = remotes.operate("omb", "list", timeout=8.0)
            assert out == "STUBBED"
        finally:
            registry.REMOTE_ADAPTER_REGISTRY["omb"] = original


class TestChainRemoval:
    def test_operate_source_has_no_per_kind_impl_calls(self):
        import inspect

        from swarm.core import remotes

        source = inspect.getsource(remotes.operate)
        for legacy in (
            "_herdr_list",
            "_herdr_send",
            "_herdr_interrogate",
            "_hermes_list",
            "_hermes_send",
            "_anythingllm_list",
            "_anythingllm_send",
            "_letta_list",
            "_letta_send",
            "openwebui_list",
            "openwebui_send",
            "_flowise_list",
            "_flowise_send",
            "_n8n_list",
            "_n8n_send",
            "_omb_list",
            "_omb_send",
            "_rakazo_list",
            "_rakazo_send",
            "_swarm_list",
            "_swarm_send",
            "_trueforge_list",
            "_trueforge_send",
        ):
            assert legacy not in source, f"operate() still calls {legacy} directly"


# ---------------------------------------------------------------------------
# Slice 3: the blueprint consumes adapters polymorphically. The four streaming
# kinds expose iter_chat() + empty_reply_hint() on the adapter; the blueprint's
# per-kind if/elif branch and the per-kind empty-reply strings are gone.
# ---------------------------------------------------------------------------


def create_adapter_for_test(kind: str, spec):
    """Resolve the real adapter for *kind* (the blueprint test path)."""
    from swarm.remotes import registry

    return registry.REMOTE_ADAPTER_REGISTRY[kind](spec)


async def _collect(gen):
    return [c async for c in gen]


class TestSlice3AdapterStream:
    @pytest.mark.parametrize(
        "module,cls,impl",
        [
            ("swarm.remotes.letta", "LettaAdapter", "iter_letta_chat"),
            ("swarm.remotes.anythingllm", "AnythingLLMAdapter", "iter_anythingllm_chat"),
            ("swarm.remotes.flowise", "FlowiseAdapter", "iter_flowise_chat"),
        ],
    )
    def test_iter_chat_forwards(self, module, cls, impl):
        import importlib

        from swarm.core import remotes

        mod = importlib.import_module(module)
        adapter_cls = getattr(mod, cls)
        spec = _spec("letta")
        with patch.object(remotes, impl, return_value=iter([])) as m:
            list(adapter_cls(spec).iter_chat("hi", session_id="s1", target="t1"))
        m.assert_called_once_with(spec, "hi", session_id="s1", target="t1")

    def test_openwebui_iter_chat_forwards_to_openwebui_remote(self):
        from swarm.remotes.openwebui import OpenWebUIAdapter

        spec = _spec("openwebui")
        with patch(
            "swarm.core.openwebui_remote.iter_openwebui_chat", return_value=iter([])
        ) as m:
            list(OpenWebUIAdapter(spec).iter_chat("hi", session_id="s1", target="t1"))
        m.assert_called_once_with(spec, "hi", session_id="s1", target="t1")

    @pytest.mark.parametrize(
        "module,cls,who,thing",
        [
            ("swarm.remotes.letta", "LettaAdapter", "Letta", "agent session"),
            ("swarm.remotes.anythingllm", "AnythingLLMAdapter", "AnythingLLM", "workspace or thread session"),
            ("swarm.remotes.flowise", "FlowiseAdapter", "Flowise", "chatflow session"),
            ("swarm.remotes.openwebui", "OpenWebUIAdapter", "Open WebUI", "chat session"),
        ],
    )
    def test_empty_reply_hint_names_the_session_kind(self, module, cls, who, thing):
        import importlib

        mod = importlib.import_module(module)
        hint = getattr(mod, cls)(_spec("letta")).empty_reply_hint()
        assert who in hint
        assert thing in hint

    def test_base_declares_iter_chat(self):
        from swarm.remotes.base import RemoteAdapter

        adapter = RemoteAdapter(_spec("omb"))
        with pytest.raises(NotImplementedError):
            next(adapter.iter_chat("hi"))

    def test_registry_resolves_streaming_kinds(self):
        from swarm.remotes.registry import create_remote_adapter

        for kind in ("letta", "anythingllm", "flowise", "openwebui"):
            adapter = create_remote_adapter(_spec(kind))
            assert adapter is not None and hasattr(adapter, "iter_chat")


class TestSlice3BlueprintPolymorphic:
    @pytest.fixture
    def bp(self):
        from swarm.blueprints.remote_harness.blueprint_remote_harness import (
            RemoteHarnessBlueprint,
        )

        return RemoteHarnessBlueprint(config={"llm": {}})

    async def _stream(self, bp, kind):
        from swarm.remotes import registry
        from swarm.remotes.base import RemoteAdapter

        real_cls = registry.REMOTE_ADAPTER_REGISTRY[kind]
        stub_kind = kind

        class _StubStream(real_cls if real_cls else RemoteAdapter):
            kind = stub_kind

            def iter_chat(self, prompt, *, session_id=None, target=""):
                yield ("Hel", False, None)
                yield ("lo", True, None)

        bp.set_params(
            {"op": "send", "name": kind, "prompt": "hi", "session_id": "docs:t1"}
        )
        with patch(
            "swarm.blueprints.remote_harness.blueprint_remote_harness.remotes_core.kind_of_instance",
            return_value=kind,
        ), patch(
            "swarm.blueprints.remote_harness.blueprint_remote_harness.remotes_core.load_remote",
            return_value=_spec(kind),
        ), patch.object(
            registry, "REMOTE_ADAPTER_REGISTRY", {kind: _StubStream}
        ):
            chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
        texts = []
        for chunk in chunks:
            msgs = chunk.get("messages") if isinstance(chunk, dict) else None
            if msgs and msgs[0].get("content"):
                texts.append(msgs[0]["content"])
        return texts, chunks

    @pytest.mark.parametrize("kind", ["letta", "anythingllm", "flowise", "openwebui"])
    async def test_blueprint_streams_via_adapter(self, bp, kind):
        texts, chunks = await self._stream(bp, kind)
        assert "Hel" in texts
        assert texts[-1] == "Hello"
        assert chunks[-1].get("final") is True

    def test_blueprint_source_has_no_per_kind_stream_branch(self):
        import inspect

        from swarm.blueprints.remote_harness import blueprint_remote_harness as brh

        source = inspect.getsource(brh)
        for legacy in (
            "iter_letta_chat",
            "iter_openwebui_chat",
            "iter_flowise_chat",
            "iter_anythingllm_chat",
            'if stream_kind == "letta"',
            'elif stream_kind == "openwebui"',
        ):
            assert legacy not in source, f"blueprint still branches on {legacy}"


# ---------------------------------------------------------------------------
# Slice 4: health dispatch joins the registry. Adapters own their health —
# Herdr's CLI/SSH probe and Letta's alternate health paths move out of the
# generic prober, which becomes kind-blind. Default adapter health forwards
# to the shared prober, so HTTP kinds are unchanged.
# ---------------------------------------------------------------------------


class TestSlice4Health:
    def test_check_health_routes_through_registry(self):
        from swarm.core import remotes
        from swarm.core.remotes import HealthResult
        from swarm.remotes import registry
        from swarm.remotes.base import RemoteAdapter

        sentinel = HealthResult(remote="omb", ok=True, state="UP", detail="stubbed")

        class _Stub(RemoteAdapter):
            kind = "omb"

            def health(self, timeout, config=None):
                return sentinel

        original = registry.REMOTE_ADAPTER_REGISTRY["omb"]
        registry.REMOTE_ADAPTER_REGISTRY["omb"] = _Stub
        try:
            with patch.object(remotes, "is_configured", return_value=True):
                out = remotes.check_health(
                    "omb", config={"llm": {}, "remotes": {}}, timeout=1.0
                )
        finally:
            registry.REMOTE_ADAPTER_REGISTRY["omb"] = original
        assert out is sentinel

    def test_herdr_adapter_health_forwards_to_cli_probe(self):
        from swarm.core import remotes
        from swarm.core.remotes import HealthResult
        from swarm.remotes.herdr import HerdrAdapter

        spec = _spec("herdr")
        sentinel = HealthResult(remote="herdr", ok=True, state="UP", detail="cli")
        with patch.object(remotes, "_herdr_health", return_value=sentinel) as m:
            out = HerdrAdapter(spec, config={"c": 1}).health(3.0, {"c": 1})
        m.assert_called_once_with(spec, 3.0, {"c": 1})
        assert out is sentinel

    def test_herdr_adapter_falls_back_to_generic_prober(self):
        from swarm.core import remotes
        from swarm.remotes.herdr import HerdrAdapter

        spec = _spec("herdr")
        with patch.object(remotes, "_herdr_health", return_value=None), \
                patch.object(remotes, "_check_health_spec", return_value="PROBED") as m:
            out = HerdrAdapter(spec, config=None).health(3.0, None)
        m.assert_called_once_with(spec, 3.0, None, extra_health_paths=[])
        assert out == "PROBED"

    def test_base_health_forwards_to_generic_prober(self):
        from swarm.core import remotes
        from swarm.remotes.base import RemoteAdapter

        spec = _spec("omb")
        with patch.object(remotes, "_check_health_spec", return_value="PROBED") as m:
            out = RemoteAdapter(spec, config={"c": 1}).health(2.5, {"c": 1})
        m.assert_called_once_with(spec, 2.5, {"c": 1}, extra_health_paths=[])
        assert out == "PROBED"

    def test_letta_extra_health_paths(self):
        from swarm.remotes.letta import LettaAdapter

        assert LettaAdapter(_spec("letta")).extra_health_paths() == [
            "/v1/health",
            "/v1/health/",
            "/health",
        ]

    def test_base_extra_health_paths_empty(self):
        from swarm.remotes.base import RemoteAdapter

        assert RemoteAdapter(_spec("omb")).extra_health_paths() == []

    def test_generic_prober_is_kind_blind(self):
        import inspect

        from swarm.core import remotes

        source = inspect.getsource(remotes._check_health_spec)
        assert '"herdr"' not in source and "'herdr'" not in source
        assert '"letta"' not in source and "'letta'" not in source

    def test_check_health_herdr_still_probes_cli_first(self):
        from swarm.core import remotes
        from swarm.core.remotes import HealthResult

        spec = _spec("herdr")
        sentinel = HealthResult(remote="herdr", ok=True, state="UP", detail="cli")
        with patch.object(remotes, "load_remote", return_value=spec), \
                patch.object(remotes, "is_configured", return_value=True), \
                patch.object(remotes, "_herdr_health", return_value=sentinel) as m:
            out = remotes.check_health("herdr", timeout=3.0)
        m.assert_called_once()
        assert out is sentinel
