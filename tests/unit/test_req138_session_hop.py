"""REQ-138 / #531 — CLI session hop: a quota hop, not a new chat per task.

The cross-kind plumbing is now read as a *call graph* over the Python source
rather than as a bag of substrings.

What rotted
-----------
``assert "crossKindHopForReconfigure" in chat`` searched the concatenation of
``ChatPage.tsx`` and ``useChatRouting.ts``. The function it names lives in
``lib/cliSessionHop.ts`` and is reached through ``reconfigureHopForSeat``, so
the pin was really asking "is the token spelled this way somewhere in two
files" — and it went red the moment the routing hook was given a wrapper, with
no behaviour change.

The substantive REQ-138 behaviour is not a source property at all; it is
already covered by tests that *run* it:

* ``tests/core/test_cli_session_hop.py`` — 24 tests, including
  ``test_hop_same_conversation_clears_target_session`` (a new session, never a
  resume), ``test_hop_back_is_also_a_new_session``,
  ``test_prepare_cli_turn_forces_new_session_and_seeds_prompt``,
  ``test_apply_cross_kind_hop_injects_seed_for_api_destination`` and its
  remote/blueprint siblings, and ``test_hop_hardcoded_api_follows_remote_destination_issue_1436``.
* ``tests/views/test_cli_session_hop_api.py`` — the endpoint's capability
  matrix, its same-CLI 400, and that a hop seeds the *same* conversation.
* ``webui/frontend/src/lib/__tests__/cliSessionHop.test.ts`` — the spec
  builder, including that api destinations are keyed by the seat record id
  while cli destinations are keyed by adapter name.

What is left here is the wiring itself, expressed as the properties a render
or a call cannot see: that the consumer's turn assembly actually reaches the
cross-kind consumption helper, and that the hop never resumes.
"""

import ast
from pathlib import Path

from helpers.py_ast import (
    calls_within_body,
    defined_names,
    find_function,
    parse_module,
)

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "src" / "swarm" / "core" / "cli_session_hop.py"
API = REPO / "src" / "swarm" / "views" / "cli_session_hop_api.py"
URLS = REPO / "src" / "swarm" / "urls.py"
DOCS = REPO / "docs" / "CLI_FUSION.md"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CHAT_ROUTING = REPO / "webui" / "frontend" / "src" / "features" / "chat" / "useChatRouting.ts"
HOP_TS = REPO / "webui" / "frontend" / "src" / "lib" / "cliSessionHop.ts"
CI = REPO / ".github" / "workflows" / "req138-session-hop.yml"
AGENT = REPO / "src" / "swarm" / "blueprints" / "cli_agent" / "blueprint_cli_agent.py"


def test_hop_is_a_new_session_and_never_a_resume():
    """Structural: the hop function's own body never resumes a prior session.

    The old version asserted ``"never resume" in core.lower()`` and
    ``"always a new session" in core.lower()`` — phrases in a *docstring*. That
    is the family's worst case: the sentence describing the rule is the thing
    being asserted, so rewording the prose fails the suite and doing the
    forbidden thing leaves it green.

    The behaviour is asserted for real by
    ``tests/core/test_cli_session_hop.py`` (a hop clears the target session and
    seeds a fresh one; hopping back is *also* a new session). What this file
    can honestly add is the negative structural check: no code path in the hop
    entry point calls a resume-shaped API.
    """
    module = parse_module(CORE)
    hop = find_function(module, "hop_backend")
    calls = calls_within_body(module, "hop_backend")
    for forbidden in ("resume", "resume_session", "continue_session", "fork_session"):
        assert forbidden not in calls, (
            f"hop_backend calls {forbidden!r}; a hop must start a new session"
        )
    # The stored session id is dropped so a hop-back cannot pick it up again.
    assert any("clear" in name for name in calls), (
        "nothing in hop_backend clears the destination's stored session id, so a "
        "hop-back could resume the session it is supposed to replace"
    )
    assert isinstance(hop, (ast.FunctionDef, ast.AsyncFunctionDef))

    # Negative hygiene, which genuinely is a text property.
    source = CORE.read_text(encoding="utf-8")
    assert "WAVE" not in source
    assert ":8001" not in source


def test_api_and_urls_are_github_only():
    """The hop endpoint is routed, and it never points at a private host."""
    urls = URLS.read_text(encoding="utf-8")
    assert "v1/cli-sessions/hop/" in urls

    api = API.read_text(encoding="utf-8")
    assert "CliSessionHopAPIView" in defined_names(parse_module(API))
    # No host literals at all, so a private gateway cannot be reintroduced.
    assert "localhost" not in api
    assert "http://" not in api
    assert "WAVE" not in api
    assert ":8001" not in api


def test_cli_agent_consumes_pending_hop():
    """The CLI seat reads the seeded hop rather than starting cold.

    ``prepare_cli_turn`` / ``context_carried_chunk`` used to be substring
    pins. They are now AST facts: the blueprint module actually calls the
    helper, and the helper's module actually defines the function.
    """
    agent = parse_module(AGENT)
    calls = calls_within_body(agent, "_prepare_cli_turn")
    assert any("prepare_cli_turn" in name for name in calls), (
        "the CLI blueprint no longer reaches prepare_cli_turn, so a hop's seeded "
        "context is dropped on the floor"
    )
    fusion = parse_module(
        REPO / "src" / "swarm" / "blueprints" / "common" / "cli_fusion_support.py"
    )
    assert "context_carried_chunk" in defined_names(fusion), (
        "the carried-context marker is gone, so a hop's context carry is invisible"
    )
    assert "is_context_carried_notice" in defined_names(parse_module(CORE))


def test_spa_calls_hop_on_cli_dropdown_switch():
    """The routing hook imports the hop, so a switch carries context.

    Read as the import + call, not as a token. The old pin was
    ``assert "hopCliSession" in chat``; the wrapper indirection
    (``reconfigureProviderForSeat`` → ``reconfigureHopForSeat`` →
    ``crossKindHopForReconfigure``) is what broke it, and the wrapper is the
    *better* shape: the spec builder is now unit-tested independently in
    ``lib/__tests__/cliSessionHop.test.ts``.
    """
    routing = (CHAT_ROUTING).read_text(encoding="utf-8")
    assert "from '../../lib/cliSessionHop'" in routing, (
        "useChatRouting no longer imports the hop module, so a seat switch cannot carry context"
    )
    assert "hopCliSession" in routing
    assert "reconfigureProviderForSeat" in routing

    # The chat surface still routes sends through the same hook.
    assert "useChatRouting" in CHAT.read_text(encoding="utf-8")

    hop = HOP_TS.read_text(encoding="utf-8")
    assert "CLI_SESSION_HOPPED_EVENT" in hop
    # The user-visible status line names the carry, which is the only thing
    # that tells the user their context followed them.
    assert "Carried" in hop
    assert "WAVE" not in hop
    assert ":8001" not in hop


def test_docs_and_own_diff_ci():
    """The design note and the manual gate both still exist."""
    docs = DOCS.read_text(encoding="utf-8")
    assert "REQ-138" in docs or "#531" in docs
    assert "summary" in docs.lower()

    ci = CI.read_text(encoding="utf-8")
    assert "req138" in ci.lower() or "REQ-138" in ci
    assert "pytest" in ci
    assert "vitest" in ci


def test_cross_kind_hop_plumbing_is_wired():
    """#900: cross-kind hops carry from_kind/to_kind/to_agent/from_agent.

    Checked as a call graph, which is the only way to say "this consumer
    actually reaches this helper" without a live socket:

    * the destination-kind-aware consumption helper exists and takes ``to_kind``;
    * the hop entry point accepts ``to_kind`` / ``to_agent`` / ``from_agent``;
    * the API view forwards them;
    * the consumer's turn assembly calls the consumption helper, reached through
      the ``swarm.chat.helpers`` mixin.
    """
    core = parse_module(CORE)

    # The consumption helper takes the destination kind — the whole point of
    # #900. A rename of the parameter breaks this, correctly.
    consume = find_function(core, "apply_cross_kind_hop_messages")
    params = {a.arg for a in consume.args.args} | {a.arg for a in consume.args.kwonlyargs}
    assert "to_kind" in params, (
        f"apply_cross_kind_hop_messages no longer takes to_kind (has {sorted(params)})"
    )

    hop = find_function(core, "hop_backend")
    hop_params = {a.arg for a in hop.args.args} | {a.arg for a in hop.args.kwonlyargs}
    for field in ("to_kind", "from_agent"):
        assert field in hop_params, (
            f"hop_backend no longer accepts {field!r}, so a cross-kind hop "
            "cannot address the destination seat"
        )
    assert "to_label" in hop_params

    # The API view forwards the cross-kind fields out of the request body.
    api_source = API.read_text(encoding="utf-8")
    for field in ("to_kind", "to_agent", "from_agent"):
        assert f'"{field}"' in api_source, (
            f"the hop API no longer reads {field!r} from the request body"
        )

    # The consumer's turn assembly reaches the consumption helper through the
    # chat mixin (moved verbatim in #855 slice 2).
    helpers = parse_module(REPO / "src" / "swarm" / "chat" / "helpers.py")
    assert "apply_cross_kind_hop_messages" in calls_within_body(
        helpers, "_apply_pending_api_hop"
    ), (
        "the API/remote pending-hop path no longer calls "
        "apply_cross_kind_hop_messages, so a cross-kind hop is silently dropped"
    )
    consumers = parse_module(REPO / "src" / "swarm" / "consumers.py")
    assert "_apply_pending_api_hop" in defined_names(consumers), (
        "the consumer no longer re-exports the pending-hop helper the turn "
        "assembly depends on"
    )
