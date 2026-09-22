"""REQ-138 / #531 — quota hop: new session + context seed, no secrets."""

from __future__ import annotations

import json

import pytest

from swarm.core import agent_settings as settings_store
from swarm.core import chat_store
from swarm.core.cli_session_hop import (
    DEFAULT_HOP_MODE,
    apply_api_hop_messages,
    apply_cross_kind_hop_messages,
    apply_injection_to_prompt,
    build_injection_payload,
    hop_backend,
    hop_capability_matrix,
    hop_defaults,
    hop_notice_text,
    is_context_carried_notice,
    is_tool_noise,
    parse_exported_messages,
    prepare_cli_turn,
    redact_injection_text,
    turns_for_injection,
)
from swarm.core.cli_sessions import get_cli_session, put_cli_session


FIXTURE = [
    {"role": "user", "content": "Design a rate limiter"},
    {"role": "assistant", "content": "Use a token bucket."},
    {"role": "tool", "content": "ran wget https://example.com"},
    {"role": "status", "content": "CLI: grok → leftover"},
    {"role": "user", "content": "Add tests. key=sk-testfixtureaaa"},
]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    yield
    settings_store.reset_agent_settings_cache()


def test_redact_strips_secret_shapes():
    text = "token sk-testfixtureaaa and Bearer abc.def and https://u:p@host/x"
    out = redact_injection_text(text)
    assert "sk-testfixtureaaa" not in out
    assert "Bearer abc.def" not in out
    assert "[REDACTED]" in out
    assert "p@" not in out or "[REDACTED]" in out


def test_tool_noise_and_turns_omit_chrome():
    assert is_tool_noise({"role": "tool", "content": "x"})
    assert is_tool_noise({"role": "assistant", "tool_calls": [{"id": "1"}]})
    kept = turns_for_injection(FIXTURE)
    roles = [row["role"] for row in kept]
    assert roles == ["user", "assistant", "user"]
    assert "sk-testfixtureaaa" not in json.dumps(kept)
    assert "[REDACTED]" in kept[-1]["content"]


def test_build_injection_respects_budget_and_header():
    payload = build_injection_payload(
        FIXTURE,
        from_cli="grok",
        to_cli="agy",
        mode="summary",
        token_budget=200,
    )
    assert payload["mode"] == DEFAULT_HOP_MODE
    assert payload["empty"] is False
    assert "Carried context from grok → agy" in payload["text"]
    assert "token bucket" in payload["text"].lower() or "rate limiter" in payload["text"].lower()
    assert "sk-testfixtureaaa" not in payload["text"]
    assert "tool noise omitted" in payload["text"].lower()
    assert payload["tokens"] <= 200 or payload["token_budget"] == 200
    assert payload["omitted"] == ["secrets", "tool_noise"]


def test_hop_notice_is_distinct_from_dropdown_change():
    line = hop_notice_text("grok", "agy", mode="summary", tokens=42)
    assert line == (
        "Started a new agy session (grok → agy). Carried summary context (42 tokens)."
    )
    assert is_context_carried_notice(line)
    assert "CLI: grok → agy" not in line
    empty = hop_notice_text("grok", "agy", mode="summary", tokens=0, empty=True)
    assert empty == (
        "Started a new agy session (grok → agy). No prior context to carry from grok."
    )
    warned = hop_notice_text(
        "grok",
        "agy",
        mode="summary",
        tokens=0,
        empty=True,
        export_warning="Export failed.",
    )
    assert warned == (
        "Started a new agy session (grok → agy). Export failed. Nothing to carry."
    )


def test_capability_matrix_is_honest_summary_inject():
    matrix = hop_capability_matrix()
    assert set(matrix) >= {"grok", "agy", "opencode", "claude"}
    assert matrix["grok"]["export"] == "summary"
    assert matrix["agy"]["export"] == "summary"
    assert matrix["grok"]["hop"] == "new_session_plus_inject"
    defaults = hop_defaults()
    assert defaults["automated_failover"] is False
    assert defaults["always_new_session"] is True
    assert defaults["same_conversation"] is True


def test_hop_same_conversation_clears_target_session(tmp_path):
    chat_store.save(
        "u1",
        "cli_agent",
        FIXTURE,
        conversation_id="thread-1",
        cli_sessions={"grok": "sid-grok-old", "agy": "sid-agy-old"},
        active_cli="grok",
        base_dir=tmp_path,
    )
    put_cli_session("u1", "cli_agent", "agy", "sid-agy-old", base_dir=tmp_path)
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="agy",
        conversation_id="thread-1",
        mode="summary",
        base_dir=tmp_path,
    )
    assert result["object"] == "cli_session_hop"
    assert result["conversation_id"] == "thread-1"
    assert result["cli_session_id"] is None
    assert result["empty"] is False
    assert "Carried summary context" in result["status"]
    assert get_cli_session("u1", "cli_agent", "agy", base_dir=tmp_path) is None
    loaded = chat_store.load("u1", "cli_agent", conversation_id="thread-1", base_dir=tmp_path)
    assert loaded["active_cli"] == "agy"
    assert loaded["cli_hop"]["pending"] is True
    assert loaded["cli_hop"]["to_cli"] == "agy"
    assert "sid-agy-old" not in json.dumps(loaded.get("cli_sessions") or {})
    assert any(
        e.get("kind") == "context_carried" for e in loaded.get("ui_events") or []
    )


def test_hop_back_is_also_a_new_session(tmp_path):
    chat_store.save(
        "u1",
        "cli_agent",
        FIXTURE,
        conversation_id="thread-1",
        cli_sessions={"grok": "sid-grok-old"},
        active_cli="agy",
        base_dir=tmp_path,
    )
    put_cli_session("u1", "cli_agent", "grok", "sid-grok-old", base_dir=tmp_path)
    hop_backend(
        "u1",
        "cli_agent",
        from_cli="agy",
        to_cli="grok",
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    assert get_cli_session("u1", "cli_agent", "grok", base_dir=tmp_path) is None


def test_export_fallback_is_honest(tmp_path):
    chat_store.save(
        "u1",
        "cli_agent",
        FIXTURE,
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="agy",
        conversation_id="thread-1",
        import_session_id="sid-outside",
        base_dir=tmp_path,
    )
    assert result["import"] == "swarm"
    assert result["export_warning"]
    assert "cannot export" in result["export_warning"]
    assert "token bucket" in result["injection"]["text"].lower() or "rate limiter" in result[
        "injection"
    ]["text"].lower()


def test_fixture_export_argv_imports_native_transcript(tmp_path):
    exported = [
        {"role": "user", "content": "Native grok turn"},
        {"role": "assistant", "content": "Native grok answer"},
    ]

    def run_export(command, _timeout):
        assert "{session_id}" not in " ".join(command)
        assert "sid-export" in command
        return 0, json.dumps(exported), ""

    cfg = {"cli_agents": {"grok": {"export_argv": ["fake-grok", "export", "{session_id}"]}}}
    chat_store.save("u1", "cli_agent", FIXTURE, conversation_id="thread-1", base_dir=tmp_path)
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="agy",
        conversation_id="thread-1",
        import_session_id="sid-export",
        config=cfg,
        run_export=run_export,
        base_dir=tmp_path,
    )
    assert result["import"] == "transcript"
    assert result["export_warning"] is None
    assert "Native grok turn" in result["injection"]["text"]
    assert "rate limiter" not in result["injection"]["text"].lower()


def test_prepare_cli_turn_forces_new_session_and_seeds_prompt(tmp_path):
    chat_store.save(
        "u1",
        "cli_agent",
        FIXTURE,
        conversation_id="thread-1",
        cli_sessions={"agy": "sid-agy-old"},
        active_cli="grok",
        base_dir=tmp_path,
    )
    hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="agy",
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    prepared = prepare_cli_turn(
        "u1",
        "cli_agent",
        "agy",
        FIXTURE + [{"role": "user", "content": "continue the limiter"}],
        "FULL PROMPT SHOULD NOT WIN",
        "continue the limiter",
        conversation_id="thread-1",
        stored_session_id="sid-agy-old",
        can_resume=True,
        base_dir=tmp_path,
    )
    assert prepared["resume_id"] is None
    assert "continue the limiter" in prepared["prompt"]
    assert "Carried context from grok → agy" in prepared["prompt"]
    assert "sk-testfixtureaaa" not in prepared["prompt"]
    assert "FULL PROMPT SHOULD NOT WIN" not in prepared["prompt"]


def test_same_cli_without_import_is_rejected():
    with pytest.raises(ValueError, match="must differ"):
        hop_backend("u1", "cli_agent", from_cli="grok", to_cli="grok")


def test_apply_injection_and_api_messages(tmp_path):
    assert apply_injection_to_prompt("SEED", "go") == "SEED\n\nUSER: go"
    chat_store.save(
        "u1",
        "api_agent",
        FIXTURE,
        conversation_id="api-1",
        base_dir=tmp_path,
    )
    hop_backend(
        "u1",
        "api_agent",
        from_cli="openai",
        to_cli="api",
        conversation_id="api-1",
        kind="api",
        base_dir=tmp_path,
    )
    messages = apply_api_hop_messages(
        "u1",
        "api_agent",
        [{"role": "user", "content": "next"}],
        conversation_id="api-1",
        to_cli="api",
        base_dir=tmp_path,
    )
    assert messages[0]["role"] == "system"
    assert "Carried context" in messages[0]["content"]
    assert messages[-1]["content"] == "next"


def test_parse_exported_messages_skips_junk():
    raw = json.dumps(
        {
            "messages": [
                {"role": "user", "content": "ok"},
                {"role": "tool", "content": "nope"},
                {"role": "assistant", "content": "sk-testfixturebbb"},
            ]
        }
    )
    rows = parse_exported_messages(raw)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert "sk-testfixturebbb" not in rows[1]["content"]


@pytest.mark.django_db
def test_hop_empty_json_uses_db_mirror_without_export(tmp_path):
    """#901: with an empty JSON thread, hop reads the Django mirror instantly."""
    from django.contrib.auth import get_user_model as _gum

    from swarm.core.agent_sessions import mirror_thread_to_db

    user = _gum().objects.create_user(username="hop-db-fallback-user", password="pw")
    uk = chat_store.user_key_for(user)
    mirror_thread_to_db(
        user,
        "thread-mirror",
        [
            {"role": "user", "content": "Mirrored question"},
            {"role": "assistant", "content": "Mirrored answer"},
        ],
        agent_id="cli_agent",
    )
    result = hop_backend(
        uk,
        "cli_agent",
        from_cli="grok",
        to_cli="agy",
        conversation_id="thread-mirror",
        base_dir=tmp_path,
        user=user,
    )
    # #900: the mirror-sourced import is labelled honestly (the frontend
    # union already carries "db_mirror").
    assert result["import"] == "db_mirror"
    assert result["export_warning"] is None  # no export attempted at all
    assert "Mirrored question" in result["injection"]["text"]
    assert "Mirrored answer" in result["injection"]["text"]


# ---------------------------------------------------------------------------
# #900 — cross-kind context handoff: cli ↔ api ↔ remote
# ---------------------------------------------------------------------------


def test_hop_accepts_cross_kind_destination(tmp_path):
    chat_store.save("u1", "cli_agent", FIXTURE, conversation_id="thread-1", base_dir=tmp_path)
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="auxiliary",
        to_kind="api",
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    assert result["kind"] == "api"
    assert result["to_cli"] == "auxiliary"
    assert "token bucket" in result["injection"]["text"].lower()


def test_hop_accepts_remote_destination(tmp_path):
    chat_store.save("u1", "cli_agent", FIXTURE, conversation_id="thread-1", base_dir=tmp_path)
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="omb",
        to_kind="remote",
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    assert result["kind"] == "remote"
    assert result["injection"]["empty"] is False


def test_apply_cross_kind_hop_injects_seed_for_api_destination(tmp_path):
    chat_store.save("u1", "cli_agent", FIXTURE, conversation_id="thread-1", base_dir=tmp_path)
    hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="auxiliary",
        to_kind="api",
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    messages = [{"role": "user", "content": "next question"}]
    out = apply_cross_kind_hop_messages(
        "u1",
        "cli_agent",
        messages,
        to_kind="api",
        to_id="auxiliary",
        base_dir=tmp_path,
    )
    assert out[0]["role"] == "system"
    assert "token bucket" in out[0]["content"].lower()
    assert out[-1] == {"role": "user", "content": "next question"}


def test_apply_cross_kind_hop_injects_seed_for_remote_destination(tmp_path):
    chat_store.save("u1", "cli_agent", FIXTURE, conversation_id="thread-1", base_dir=tmp_path)
    hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="omb",
        to_kind="remote",
        conversation_id="thread-1",
        base_dir=tmp_path,
    )
    # Remote destination: the seed merges into the latest user turn (the
    # remote analogue of apply_injection_to_prompt), because server-managed
    # remotes only see the last user turn.
    out = apply_cross_kind_hop_messages(
        "u1",
        "cli_agent",
        [{"role": "user", "content": "hello remote"}],
        to_kind="remote",
        to_id="omb",
        base_dir=tmp_path,
    )
    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert "token bucket" in out[0]["content"].lower()
    assert out[0]["content"].endswith("hello remote")


def test_apply_cross_kind_hop_noop_without_pending_hop(tmp_path):
    messages = [{"role": "user", "content": "plain turn"}]
    out = apply_cross_kind_hop_messages(
        "u1",
        "cli_agent",
        messages,
        to_kind="api",
        to_id="auxiliary",
        base_dir=tmp_path,
    )
    assert out == messages


def test_hop_defaults_declare_cross_kinds():
    defaults = hop_defaults()
    assert set(defaults["kinds"]) == {"cli", "api", "remote"}
