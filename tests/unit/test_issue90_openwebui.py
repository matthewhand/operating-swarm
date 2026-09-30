"""Issue #90 — Open WebUI list/search/resume/chat wiring locks."""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CHAT_SEND = REPO / "webui" / "frontend" / "src" / "features" / "chat" / "useChatSend.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
# #855 slice 2: per-harness dispatch moved verbatim into the stubs mixin.
STUBS = REPO / "src" / "swarm" / "chat" / "stubs_mixin.py"
API = REPO / "src" / "swarm" / "views" / "remotes_api.py"
ADAPTER = REPO / "src" / "swarm" / "core" / "openwebui_remote.py"
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"
HARNESS = REPO / "src" / "swarm" / "core" / "remote_harness.py"
# The websocket turn path, for the "no per-harness branch" AST lock below.
WS_TURN_PATH = (
    CONSUMERS,
    REPO / "src" / "swarm" / "chat" / "stubs_mixin.py",
    REPO / "src" / "swarm" / "chat" / "helpers.py",
    REPO / "src" / "swarm" / "chat" / "conversations_mixin.py",
    REPO / "src" / "swarm" / "chat" / "advice_mixin.py",
)

HARNESS_ID = "openwebui"
HARNESS_LABEL = "Open WebUI"


# Three tests used to live here with bodies matching
# tests/unit/test_issue88_anythingllm.py (this file's chat variant asserted
# `"SessionPicker" in src` where #88 asserted the equivalent
# `"os-session-picker" not in src or "SessionPicker" in src`, so the first was a
# near-duplicate; the other two were exact). Survivors and their stronger
# replacements are documented in test_issue91_flowise.py.
#
# The per-harness test below is NOT a duplicate: it reads the module-level
# HARNESS_ID, so it exercises a different value here than in the other three.


def test_consumers_route_openwebui_remote():
    """The WS turn path resolves Open WebUI through the harness registry.

    Replaces ``"openwebui" in consumers.py + stubs_mixin.py``.  That string
    was never the route — the consumer turn is harness-agnostic and renders
    whatever ``blueprint_instance.run()`` streams — so it could not detect
    the route being lost, and a comment would have satisfied it.  What
    actually carries a remote turn is the REQ-203 harness registry plus the
    #812 adapter registry, so assert those, and assert the consumer has NOT
    grown a per-harness branch.
    """
    from swarm.core.remote_harness import get_harness
    from swarm.core.remotes import RemoteSpec
    from swarm.remotes.base import RemoteAdapter
    from swarm.remotes.registry import create_remote_adapter

    # 1. REQ-203: registered as a harness with health/list/send all bound.
    bound = get_harness(HARNESS_ID)
    assert bound is not None, f"{HARNESS_ID} is not a registered BoundRemoteHarness"
    assert bound.label == HARNESS_LABEL
    for field in ("health_fn", "list_fn", "send_fn"):
        assert callable(getattr(bound, field)), f"{HARNESS_ID}.{field} is not callable"
    assert bound.capabilities.sessions is True
    assert bound.capabilities.list is True
    assert bound.capabilities.send is True
    assert bound.capabilities.health is True

    # 2. #812: the operate seam can build this harness's adapter, and it is a
    #    real implementation rather than the NotImplementedError base stub.
    spec = RemoteSpec(
        id=HARNESS_ID,
        kind=HARNESS_ID,
        title=HARNESS_LABEL,
        host_label=HARNESS_LABEL,
        base_url="https://example.invalid",
    )
    adapter = create_remote_adapter(spec)
    assert isinstance(adapter, RemoteAdapter)
    assert adapter.kind == HARNESS_ID
    for method in ("list", "send"):
        impl = type(adapter).__dict__.get(method)
        assert impl is not None, f"{type(adapter).__name__} does not implement {method}"
        assert impl is not getattr(RemoteAdapter, method), (
            f"{type(adapter).__name__}.{method} is the base-class NotImplementedError stub"
        )

    # 3. Streaming contract the frontend depends on.
    assert "streamed_any" in STUBS.read_text(encoding="utf-8")

    # 4. The consumer stays harness-agnostic; catch a re-added per-harness
    #    branch by AST so a comment or docstring cannot satisfy it.
    for path in WS_TURN_PATH:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.lower() == HARNESS_ID
        ]
        assert not hits, (
            f"{path.name} carries a per-{HARNESS_ID} branch at line(s) {hits}; the "
            "websocket turn path must stay harness-agnostic (add an adapter "
            "method or a registry entry instead)."
        )


def test_adapter_is_external_open_webui_not_os_webui():
    src = ADAPTER.read_text(encoding="utf-8")
    assert "os-webui" in src.lower() or "own WebUI" in src
    assert "never replace" in src.lower() or "must never replace" in src
    remotes = REMOTES.read_text(encoding="utf-8")
    assert '"openwebui"' in remotes
    assert "OPENWEBUI_BASE_URL" in remotes
    assert "os-webui" in remotes
    harness = HARNESS.read_text(encoding="utf-8")
    assert "openwebui" in harness
    assert "sessions=rid in" in harness.replace(" ", "") or '"openwebui"' in harness
