"""Issue #88 — AnythingLLM list/search/resume/chat wiring locks."""

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
# The websocket turn path, for the "no per-harness branch" AST lock below.
WS_TURN_PATH = (
    CONSUMERS,
    REPO / "src" / "swarm" / "chat" / "stubs_mixin.py",
    REPO / "src" / "swarm" / "chat" / "helpers.py",
    REPO / "src" / "swarm" / "chat" / "conversations_mixin.py",
    REPO / "src" / "swarm" / "chat" / "advice_mixin.py",
)

HARNESS = "anythingllm"
HARNESS_LABEL = "AnythingLLM"


# The three tests below are the survivors of a four-way hand-copied cluster:
# byte-identical bodies also lived in test_issue90_openwebui.py,
# test_issue91_flowise.py and test_issue92_n8n.py, so each ran four times under
# four harness names while never mentioning the harness it was named for.
# This file is the one the others' comments pointed at, so it keeps the copies.
# See test_issue91_flowise.py for the note on what covers each property.


def test_chat_sends_session_id_for_remote_resume():
    src = "\n".join(x.read_text(encoding="utf-8") for x in (CHAT, CHAT_SEND))
    assert "remoteChatTurnParams" in src
    assert "sessionFromUrl" in src
    assert "fetchRemoteThreadSessions" in src
    assert "os-session-picker" not in src or "SessionPicker" in src


def test_rail_opens_searchable_anythingllm_sessions():
    src = SIDEBAR.read_text(encoding="utf-8")
    # #748/#580: the rail's session affordance is the declared capability
    # (seatHasSessions) plus the menu-payload session rows; remote thread
    # listing lives in RemoteSessionSwitcher + lib/remoteSessions.
    assert "seatHasSessions" in src
    assert "openGroupPicker" in src


def test_operate_api_forwards_session_id():
    src = API.read_text(encoding="utf-8")
    assert "session_id" in src
    assert "query" in src


def test_consumers_route_anythingllm_remote():
    """The WS turn path resolves AnythingLLM through the harness registry.

    Replaces ``"anythingllm" in consumers.py + stubs_mixin.py``.  That string
    was never the route: the consumer turn is harness-agnostic — it iterates
    ``blueprint_instance.run()`` and renders whatever the blueprint streams —
    so the substring was a fossil of the pre-#855 dispatch and could not have
    detected the route being lost.  It *could* be satisfied by a comment, and
    it went red when the string was correctly absent.

    What actually carries a remote turn is the REQ-203 harness registry plus
    the #812 adapter registry, so assert those, and assert the consumer has
    NOT grown a per-harness branch — the real failure the substring was
    pretending to guard.
    """
    from swarm.core.remote_harness import get_harness
    from swarm.core.remotes import RemoteSpec
    from swarm.remotes.base import RemoteAdapter
    from swarm.remotes.registry import create_remote_adapter

    # 1. REQ-203: registered as a harness with health/list/send all bound.
    bound = get_harness(HARNESS)
    assert bound is not None, f"{HARNESS} is not a registered BoundRemoteHarness"
    assert bound.label == HARNESS_LABEL
    for field in ("health_fn", "list_fn", "send_fn"):
        assert callable(getattr(bound, field)), f"{HARNESS}.{field} is not callable"
    # The rail lists sessions, so the server must advertise them.
    assert bound.capabilities.sessions is True
    assert bound.capabilities.list is True
    assert bound.capabilities.send is True
    assert bound.capabilities.health is True

    # 2. #812: the operate seam can build this harness's adapter, and it is a
    #    real implementation rather than the NotImplementedError base stub.
    spec = RemoteSpec(
        id=HARNESS,
        kind=HARNESS,
        title=HARNESS_LABEL,
        host_label=HARNESS_LABEL,
        base_url="https://example.invalid",
    )
    adapter = create_remote_adapter(spec)
    assert isinstance(adapter, RemoteAdapter)
    assert adapter.kind == HARNESS
    for method in ("list", "send"):
        impl = type(adapter).__dict__.get(method)
        assert impl is not None, f"{type(adapter).__name__} does not implement {method}"
        assert impl is not getattr(RemoteAdapter, method), (
            f"{type(adapter).__name__}.{method} is the base-class NotImplementedError stub"
        )

    # 3. Streaming contract the frontend depends on: incremental appends, and
    #    a final message only when nothing streamed.
    assert "streamed_any" in STUBS.read_text(encoding="utf-8")

    # 4. The consumer stays harness-agnostic.  A per-harness branch here is
    #    the anti-pattern the removed substring was standing in for; catch a
    #    re-added one by AST so a comment or docstring cannot satisfy it.
    for path in WS_TURN_PATH:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.lower() == HARNESS
        ]
        assert not hits, (
            f"{path.name} carries a per-{HARNESS} branch at line(s) {hits}; the "
            "websocket turn path must stay harness-agnostic (add an adapter "
            "method or a registry entry instead)."
        )
