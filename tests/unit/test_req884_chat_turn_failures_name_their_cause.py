"""REQ-884 — source lock for chat-turn failures naming their cause.

Spec of record: docs/qa/REQ-884-chat-turn-failures-name-their-cause.md
Behaviour tests: tests/unit/test_consumer_turn_error_frame.py,
tests/unit/test_llm_profile_unresolved_env.py

These pin the *shape* the spec promises, so a later refactor cannot quietly
un-guard the turn dispatch (aborting the socket instead of sending an error
frame) or let an unresolved ``${NAME}`` reach a provider client again.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
# #855: the module-level helpers (incl. _credential_hint) moved verbatim to
# swarm/chat/helpers.py; their defs pin against the new home.
CHAT_HELPERS = REPO / "src" / "swarm" / "chat" / "helpers.py"
CONFIG_LOADER = REPO / "src" / "swarm" / "core" / "config_loader.py"
SPEC = REPO / "docs" / "qa" / "REQ-884-chat-turn-failures-name-their-cause.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _turn_dispatch() -> str:
    """Turn execution region: ``_run_serialised_chat_turn`` plus the
    ``_run_chat_turn_body`` it delegates to (ADR-017 PR-1 split the dispatch
    out of the serialised wrapper; the guard contract is unchanged)."""
    body = _text(CONSUMERS).split("async def _run_serialised_chat_turn", 1)[1]
    return body.split("\n    async def _emit_teammate_task_cards", 1)[0]


def test_req884_turn_dispatch_sends_an_error_frame_instead_of_escaping():
    dispatch = _turn_dispatch()
    assert "Guard the dispatch itself" in dispatch
    assert "except Exception as e:" in dispatch
    assert "logger.exception" in dispatch
    assert "self.send_error_message(" in dispatch


def test_req884_error_partial_uses_the_shared_safe_message_helper():
    dispatch = _turn_dispatch()
    assert "client_safe_error_message(" in dispatch
    # The public text names a provider/credential fault instead of repeating the
    # connection-level message the SPA was already showing.
    assert "model provider is unusable" in dispatch


def test_req884_error_frame_names_a_missing_credential():
    """The hint is optional-by-design and must not invent a cause."""
    dispatch = _turn_dispatch()
    assert "_credential_hint()" in dispatch
    assert "hint = _credential_hint()" in dispatch
    assert "if hint:" in dispatch
    text = _text(CONSUMERS) + _text(CHAT_HELPERS)
    assert "def _credential_hint() -> str:" in text
    assert "llm_credential_hint" in text


def test_req884_diagnosis_stays_quiet_when_it_cannot_prove_a_problem():
    diagnostics = (REPO / "src" / "swarm" / "core" / "llm_diagnostics.py").read_text(
        encoding="utf-8"
    )
    assert "if not profile:" in diagnostics
    assert "or add an api_key to this LLM profile" in diagnostics


def test_req884_a_failed_error_send_cannot_itself_escape():
    dispatch = _turn_dispatch()
    assert "turn error partial send failed" in dispatch
    # Up to two handlers: the dispatch guard and the nested send guard.
    assert dispatch.count("except Exception") >= 2


def test_req884_error_frames_are_not_model_context():
    """send_error_message documents this; keep the guarantee visible."""
    text = _text(CONSUMERS)
    assert "deliberately NOT appended to ``self.messages``" in text


def test_req884_placeholder_helpers_exist():
    text = _text(CONFIG_LOADER)
    assert "def unresolved_env_placeholders(value" in text
    assert "def drop_unresolved_env_values(" in text


def test_req884_resolver_drops_placeholders_after_env_overrides():
    resolver = _text(CONFIG_LOADER).split("def get_resolved_llm_profile", 1)[1]
    overrides_at = resolver.index("_apply_litellm_overrides(profile)")
    drop_at = resolver.index("drop_unresolved_env_values(resolved)")
    assert overrides_at < drop_at, "a set LITELLM_* value must still win"


def test_req884_unknown_variables_are_still_left_alone_by_substitution():
    """The guard is in the resolver, not in expandvars (a pinned contract)."""
    text = _text(CONFIG_LOADER)
    assert "os.path.expandvars(value)" in text
    assert "_UNRESOLVED_ENV_RE = re.compile(" in text


def _drop_body() -> str:
    body = _text(CONFIG_LOADER).split("def drop_unresolved_env_values", 1)[1]
    return body.split("\ndef ", 1)[0]


def test_req884_scope_keeps_only_api_key_and_base_url():
    """A placeholder ``model`` is left alone on purpose (see the spec)."""
    body = _drop_body()
    assert '("api_key", "base_url")' in body
    assert '"model"' not in body


def test_req884_spec_doc_is_shipped():
    assert SPEC.is_file()
    text = _text(SPEC)
    assert "REQ-884" in text
    assert "test_req884_chat_turn_failures_name_their_cause.py" in text
