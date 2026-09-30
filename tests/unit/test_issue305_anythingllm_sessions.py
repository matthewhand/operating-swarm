"""Issue #305 — AnythingLLM Settings operate uses listed workspace:thread ids."""

import ast
from pathlib import Path

from swarm.blueprints.remote_harness.blueprint_remote_harness import RemoteHarnessBlueprint

CONSUMERS = Path(__file__).resolve().parents[2] / "src" / "swarm" / "consumers.py"
SETTINGS = (
    Path(__file__).resolve().parents[2]
    / "webui"
    / "frontend"
    / "src"
    / "components"
    / "RemotesSettings.tsx"
)
VIEWS = Path(__file__).resolve().parents[2] / "src" / "swarm" / "views" / "remotes_api.py"
# #855 slice 2: per-harness dispatch moved verbatim into the stubs mixin.
STUBS = Path(__file__).resolve().parents[2] / "src" / "swarm" / "chat" / "stubs_mixin.py"


def test_settings_parser_reads_sessions_key():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "'sessions' in raw" in text
    assert "session_id" in text


def test_operate_view_forwards_session_id():
    text = VIEWS.read_text(encoding="utf-8")
    assert "session_id" in text


def test_consumers_remap_anythingllm():
    """The remote-id -> kind remap still resolves anythingllm, and feeds a real route.

    Replaces ``'"anythingllm"' in consumers.py``.  The consumer holds no
    per-harness table at all: the websocket turn is harness-agnostic (it
    iterates ``blueprint_instance.run()``), so that substring never described
    a remap, could be satisfied by a comment, and went red precisely because
    the string is correctly gone.

    The remap every remote send actually depends on is
    ``remotes.kind_of_instance`` — the remote_harness blueprint calls it
    before each operate — so assert it resolves the id and the alias forms,
    and that the kind it resolves to has both a registered harness and a
    buildable adapter.  A remap into a kind with no route is exactly the
    regression the old assertion could not see.
    """
    from swarm.core.remote_harness import get_harness
    from swarm.core.remotes import _KIND_ALIASES, RemoteSpec, kind_of_instance
    from swarm.remotes.registry import create_remote_adapter

    # 1. The catalogued id, a named-instance form, and the alias forms all
    #    remap to the same kind.  ``_KIND_ALIASES`` is the table
    #    ``kind_of_instance`` consults first, so a dropped entry there is a
    #    dropped remap — not just an unused constant.
    assert kind_of_instance("anythingllm") == "anythingllm"
    assert kind_of_instance("anythingllm-2") == "anythingllm"
    for alias in ("anything-llm", "anything_llm"):
        assert kind_of_instance(alias) == "anythingllm", (
            f"alias {alias!r} no longer remaps to the anythingllm kind"
        )
        assert _KIND_ALIASES.get(alias) == "anythingllm"

    # 2. The remapped kind resolves to a harness with list/send bound — the
    #    "list workspaces/threads as sessions and send into an existing
    #    thread" contract #305 is about.
    bound = get_harness(kind_of_instance("anythingllm"))
    assert bound is not None, "the remapped kind has no registered harness"
    assert bound.label == "AnythingLLM"
    assert callable(bound.list_fn) and callable(bound.send_fn)
    assert bound.capabilities.sessions is True

    # 3. ...and to an adapter the operate seam can actually build.
    adapter = create_remote_adapter(
        RemoteSpec(
            id="anythingllm",
            kind="anythingllm",
            title="AnythingLLM",
            host_label="AnythingLLM",
            base_url="https://example.invalid",
        )
    )
    assert adapter is not None and adapter.kind == "anythingllm"
    assert type(adapter).__dict__.get("send") is not None

    # 4. No per-harness branch in the websocket turn path (AST, so neither a
    #    comment nor a docstring can satisfy it).
    for path in (CONSUMERS, STUBS):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.lower() == "anythingllm"
        ]
        assert not hits, (
            f"{path.name} carries a per-anythingllm branch at line(s) {hits}; "
            "the websocket turn path must stay harness-agnostic."
        )


def test_placed_anythingllm_and_herdr_get_consult_tools():
    bp = RemoteHarnessBlueprint(
        config={"llm": {}, "agent_team": {"members": ["anythingllm", "herdr"]}}
    )
    agents = bp._build_agents()
    assert "anythingllm" in agents
    assert "herdr" in agents
    names = []
    for tool in getattr(agents["coordinator"], "tools", []) or []:
        names.append(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
    joined = " ".join(str(n) for n in names)
    assert "consult_anythingllm" in joined
    assert "consult_herdr" in joined
