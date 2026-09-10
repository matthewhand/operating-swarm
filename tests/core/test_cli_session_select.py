"""REQ-104 — list / switch CLI sessions (design A + honest degrade)."""

from __future__ import annotations

import json
from urllib.parse import quote
import sys

import pytest

from swarm.core import agent_settings as settings_store
from swarm.core import chat_store
from swarm.core.cli_adapter import CliAdapter
from swarm.core.cli_catalog import can_list_sessions, catalog_entry, list_sessions_argv
from swarm.core.cli_session_select import (
    PRIOR_HISTORY_KIND,
    format_prior_history,
    list_cli_sessions,
    parse_grok_sessions_table,
    parse_provider_sessions,
    remember_recent_session,
    select_cli_session,
    switch_notice_text,
)
from swarm.core.cli_sessions import get_cli_session


def _list_config(script: str) -> dict:
    return {
        "cli_agents": {
            "echo": {
                "cmd": [sys.executable, script, "{prompt}"],
                "parse": "json:.result",
                "resume_argv": ["--resume", "{session_id}"],
                "list_argv": [sys.executable, script, "--list"],
            }
        }
    }


def test_catalog_list_defaults_match_capability():
    assert can_list_sessions("grok") is True
    assert list_sessions_argv("grok") == ["grok", "sessions", "list", "--limit", "50"]
    assert can_list_sessions("agy") is True
    assert list_sessions_argv("agy") is None
    assert can_list_sessions("opencode") is True
    for name in ("claude", "gemini", "codex", "pi"):
        assert can_list_sessions(name) is False
        assert list_sessions_argv(name) is None


def test_parse_provider_sessions_sanitizes_and_skips_secrets():
    raw = json.dumps(
        [
            {"id": "sid-ok", "title": "Alpha", "snippet": "hi", "updated_at": "2026-09-05T12:00:00Z"},
            {"id": "sk-secret-key", "title": "nope"},
            {"session_id": "sid-two", "name": "Beta"},
        ]
    )
    rows = parse_provider_sessions(raw)
    assert [r["id"] for r in rows] == ["sid-ok", "sid-two"]
    assert rows[0]["source"] == "provider"


def test_list_fixture_cli_returns_n_sessions(tmp_path):
    script = tmp_path / "list_cli.py"
    script.write_text(
        "import json, sys\n"
        "if '--list' in sys.argv:\n"
        "    print(json.dumps([\n"
        "        {'id': 'sid-1', 'title': 'First', 'snippet': 'hello', 'updated_at': '2026-09-05T10:00:00Z'},\n"
        "        {'id': 'sid-2', 'title': 'Second', 'snippet': 'again', 'updated_at': '2026-09-05T11:00:00Z'},\n"
        "        {'id': 'sid-3', 'title': 'Third', 'snippet': 'more', 'updated_at': '2026-09-05T12:00:00Z'},\n"
        "    ]))\n"
        "    raise SystemExit(0)\n"
        "print(json.dumps({'result': 'ok'}))\n"
    )
    payload = list_cli_sessions(
        "u1",
        "cli_agent",
        "echo",
        config=_list_config(str(script)),
        base_dir=tmp_path,
    )
    assert payload["can_list"] is True
    assert [row["id"] for row in payload["sessions"]] == ["sid-3", "sid-2", "sid-1"]
    assert payload["empty_reason"] is None
    assert payload["activity_sot"] == "provider"


def test_non_listable_cli_degrades_honestly(tmp_path):
    payload = list_cli_sessions("u1", "cli_agent", "claude", config={}, base_dir=tmp_path)
    assert payload["can_list"] is False
    assert payload["list_capability"] == "paste-only"
    assert payload["sessions"] == []
    assert payload["empty_reason"] == "This CLI can't list sessions"
    remember_recent_session(
        "u1",
        "cli_agent",
        "claude",
        "sid-recent",
        title="Touched",
        snippet="last send",
        base_dir=tmp_path,
    )
    again = list_cli_sessions("u1", "cli_agent", "claude", config={}, base_dir=tmp_path)
    assert again["can_list"] is False
    assert [row["id"] for row in again["sessions"]] == ["sid-recent"]
    assert again["activity_sot"] == "swarm"
    assert again["empty_reason"] is None


def test_select_updates_stored_id_and_mints_new_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {"role": "status", "content": "Started a new echo session."},
        ],
        conversation_id="agt-1-cli_agent",
        base_dir=tmp_path,
    )
    first = select_cli_session(
        "u1",
        "cli_agent",
        "echo",
        session_id="sid-2",
        from_conversation_id="agt-1-cli_agent",
        imported_messages=[{"role": "user", "content": "from cli"}, {"role": "assistant", "content": "cli reply"}],
        title="Second",
        snippet="again",
        base_dir=tmp_path,
    )
    assert first["same_session"] is False
    assert first["conversation_id"] != "agt-1-cli_agent"
    assert first["conversation_id"].startswith("cli-cli_agent-")
    assert first["cli_session_id"] == "sid-2"
    assert first["collapsed_prior"] is True
    assert first["import"] == "full"
    assert "Restored" not in first["status"]
    assert first["status"] == "Switched to echo session sid-2."
    assert get_cli_session("u1", "cli_agent", "echo", base_dir=tmp_path) == "sid-2"
    assert settings_store.stored_cli_session_id("cli_agent") == "sid-2"

    kinds = [m.get("kind") for m in first["messages"]]
    assert PRIOR_HISTORY_KIND in kinds
    pill = next(m for m in first["messages"] if m.get("kind") == PRIOR_HISTORY_KIND)
    assert "old question" in pill["content"]
    assert "old answer" in pill["content"]
    assert any(m.get("content") == "from cli" for m in first["messages"])
    assert not any(m.get("role") in ("status", "info") for m in first["turns"])
    assert any(e.get("content") == first["status"] for e in first["ui_events"])
    assert any(e.get("kind") == PRIOR_HISTORY_KIND for e in first["ui_events"])

    old = chat_store.load("u1", "cli_agent", conversation_id="agt-1-cli_agent", base_dir=tmp_path)
    assert old is not None
    assert any(m.get("content") == "old question" for m in old["messages"])

    new = chat_store.load(
        "u1",
        "cli_agent",
        conversation_id=first["conversation_id"],
        session_id=first["conversation_id"],
        base_dir=tmp_path,
    )
    assert new is not None
    assert new["conversation_id"] == first["conversation_id"]
    assert not any(m.get("role") in ("status", "info") for m in new["messages"])
    assert any(e.get("content") == first["status"] for e in new["ui_events"])
    assert any(e.get("kind") == PRIOR_HISTORY_KIND for e in new["ui_events"])


def test_select_same_session_does_not_double_collapse(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [{"role": "user", "content": "hi"}],
        conversation_id="cur",
        cli_sessions={"echo": "sid-1"},
        base_dir=tmp_path,
    )
    again = select_cli_session(
        "u1",
        "cli_agent",
        "echo",
        session_id="sid-1",
        from_conversation_id="cur",
        base_dir=tmp_path,
    )
    assert again["same_session"] is True
    assert again["collapsed_prior"] is False
    assert again["conversation_id"] == "cur"


def test_start_new_clears_id_and_collapses_prior(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [{"role": "user", "content": "keep me"}, {"role": "assistant", "content": "ok"}],
        conversation_id="old",
        cli_sessions={"echo": "sid-1"},
        base_dir=tmp_path,
    )
    result = select_cli_session(
        "u1",
        "cli_agent",
        "echo",
        start_new=True,
        from_conversation_id="old",
        base_dir=tmp_path,
    )
    assert result["cli_session_id"] is None
    assert result["collapsed_prior"] is True
    assert result["status"] == "Started a new echo session."
    assert "Restored" not in result["status"]
    assert get_cli_session("u1", "cli_agent", "echo", base_dir=tmp_path) is None
    assert settings_store.stored_cli_session_id("cli_agent") is None
    assert any(m.get("kind") == PRIOR_HISTORY_KIND for m in result["messages"])
    assert not any(m.get("role") in ("status", "info") for m in result["turns"])
    assert any(e.get("content") == result["status"] for e in result["ui_events"])


def test_old_compressions_are_not_copied(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [
            {"role": "user", "content": "summarized turn"},
            {"role": "assistant", "content": "long answer"},
        ],
        conversation_id="compacted",
        base_dir=tmp_path,
    )
    result = select_cli_session(
        "u1",
        "cli_agent",
        "echo",
        session_id="sid-new",
        from_conversation_id="compacted",
        base_dir=tmp_path,
    )
    assert result["conversation_id"] != "compacted"
    # New thread has the pill + status only — no copied summary rows.
    roles = [m.get("role") for m in result["messages"]]
    assert "assistant" not in roles
    assert any(m.get("kind") == PRIOR_HISTORY_KIND for m in result["messages"])


def test_select_imports_qwen_provider_transcript_and_folder(tmp_path, monkeypatch):
    import swarm.core.cli_session_stores as stores
    from swarm.core.cli_session_select import select_cli_session
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    monkeypatch.setattr(
        stores,
        "read_provider_transcript",
        lambda cli, sid, store_dir=None: {
            "turns": [
                {"role": "user", "content": "run the tests"},
                {"role": "assistant", "content": "Running now."},
            ],
            "cwd": "/home/dev/proj",
            "git_branch": "feat/x",
        },
    )
    # NOTE: select imports the reader from the stores module namespace,
    # so patching stores.read_provider_transcript takes effect.
    res = select_cli_session(
        "u9",
        "cli_agent",
        "qwen",
        session_id="sid-9",
        title="tests",
        base_dir=tmp_path,
    )
    assert res["same_session"] is False
    assert res["import"] == "full"
    assert res["folder"] == "/home/dev/proj"
    assert res["git_branch"] == "feat/x"
    assert any(m.get("content") == "run the tests" for m in res["messages"])
    assert any(m.get("content") == "Running now." for m in res["messages"])


def test_rejects_secret_shaped_paste(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    try:
        select_cli_session(
            "u1",
            "cli_agent",
            "echo",
            session_id="sk-live-secret-key",
            base_dir=tmp_path,
        )
    except ValueError as exc:
        assert "session id" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_switch_notice_never_says_restored():
    assert "restored" not in switch_notice_text("echo", "sid-1", start_new=False).lower()
    assert "restored" not in switch_notice_text("echo", None, start_new=True).lower()


def test_format_prior_history_skips_empty():
    text = format_prior_history(
        [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
            {"role": "status", "content": "Started a new echo session."},
        ]
    )
    assert "**User:** q" in text
    assert "**Assistant:** a" in text
    assert "Started a new echo session." not in text



GROK_TABLE = """
Label: main
SESSION ID                            CREATED    UPDATED    STATUS     SUMMARY
aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee 2026-09-01 2026-09-05 local      External grok chat
bbbbbbbb-cccc-4ddd-8eee-ffffffffffff 2026-08-20 2026-08-22 remote     Older sibling
sk-secret-key-should-never-appear    2026-09-01 2026-09-05 local      nope
"""


def test_parse_grok_sessions_table_ids_and_metadata_only():
    rows = parse_grok_sessions_table(GROK_TABLE)
    assert [r["id"] for r in rows] == [
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
    ]
    assert rows[0]["title"] == "External grok chat"
    assert rows[0]["source"] == "provider"
    assert rows[0]["updated_at"] == "2026-09-05T00:00:00Z"
    assert parse_grok_sessions_table("No sessions found.") == []


def test_grok_list_then_select_resumes_external_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()

    def run_list(argv, timeout):
        assert "sessions" in argv and "list" in argv
        return 0, GROK_TABLE, ""

    payload = list_cli_sessions(
        "u1",
        "cli_agent",
        "grok",
        config={},
        run_list=run_list,
        base_dir=tmp_path,
    )
    assert payload["can_list"] is True
    assert payload["list_capability"] == "works"
    assert payload["activity_sot"] == "provider"
    sid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    assert [row["id"] for row in payload["sessions"]][0] == sid

    selected = select_cli_session(
        "u1",
        "cli_agent",
        "grok",
        session_id=sid,
        title="External grok chat",
        base_dir=tmp_path,
    )
    assert selected["cli_session_id"] == sid
    assert get_cli_session("u1", "cli_agent", "grok", base_dir=tmp_path) == sid

    adapter = CliAdapter.from_config("grok", catalog_entry("grok"))
    argv, _ = adapter._build_invocation("continue please", "/tmp", session_id=sid)
    assert argv[0] == "grok"
    assert "--resume" in argv
    assert argv[argv.index("--resume") + 1] == sid


def test_grok_list_does_not_invent_rows_on_garbage(tmp_path):
    def run_list(argv, timeout):
        return 0, "not a session table and not json", ""

    payload = list_cli_sessions(
        "u1", "cli_agent", "grok", run_list=run_list, base_dir=tmp_path
    )
    assert payload["can_list"] is True
    assert payload["sessions"] == []
    assert payload["warning"] == "Session list had no parseable ids"
    assert payload["empty_reason"] == "No sessions found"


def test_opencode_json_list_normalizes_unix_ms(tmp_path):
    raw = json.dumps(
        [
            {
                "id": "ses_external1",
                "title": "Outside OpenCode",
                "updated": 1_725_552_000_000,
                "directory": "/tmp/proj",
            }
        ]
    )

    def run_list(argv, timeout):
        assert argv[-2:] == ["--format", "json"] or "--format" in argv
        return 0, raw, ""

    payload = list_cli_sessions(
        "u1", "cli_agent", "opencode", run_list=run_list, base_dir=tmp_path
    )
    assert payload["can_list"] is True
    assert payload["sessions"][0]["id"] == "ses_external1"
    assert payload["sessions"][0]["title"] == "Outside OpenCode"
    assert payload["sessions"][0]["updated_at"].endswith("Z")
    assert payload["sessions"][0]["source"] == "provider"

    adapter = CliAdapter.from_config("opencode", catalog_entry("opencode"))
    argv, _ = adapter._build_invocation("hi", "/tmp", session_id="ses_external1")
    assert "--session" in argv
    assert argv[argv.index("--session") + 1] == "ses_external1"


def test_agy_store_lists_external_conversation_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    conv = tmp_path / "conversations"
    conv.mkdir()
    sid = "3b4a1d20-3968-4ed2-90b3-00eea3060b02"
    (conv / f"{sid}.db").write_bytes(b"SQLite format 3")
    (conv / "sk-secret-key.db").write_bytes(b"nope")
    (conv / "notes.txt").write_text("ignore")
    config = {"cli_agents": {"agy": {"list_store_dir": str(conv)}}}
    payload = list_cli_sessions(
        "u1", "cli_agent", "agy", config=config, base_dir=tmp_path
    )
    assert payload["can_list"] is True
    assert payload["list_capability"] == "works"
    assert payload["activity_sot"] == "provider"
    assert [row["id"] for row in payload["sessions"]] == [sid]
    assert payload["sessions"][0]["source"] == "provider"

    selected = select_cli_session(
        "u1", "cli_agent", "agy", session_id=sid, base_dir=tmp_path
    )
    assert selected["cli_session_id"] == sid
    adapter = CliAdapter.from_config("agy", catalog_entry("agy"))
    argv, _ = adapter._build_invocation("next", "/tmp", session_id=sid)
    assert "--conversation" in argv
    assert argv[argv.index("--conversation") + 1] == sid


def test_agy_missing_store_dir_is_empty_not_fake(tmp_path):
    config = {"cli_agents": {"agy": {"list_store_dir": str(tmp_path / "missing")}}}
    payload = list_cli_sessions(
        "u1", "cli_agent", "agy", config=config, base_dir=tmp_path
    )
    assert payload["can_list"] is True
    assert payload["sessions"] == []
    assert payload["empty_reason"] == "No sessions found"


def test_parse_provider_sessions_accepts_conversation_id():
    raw = json.dumps(
        [{"conversationId": "3b4a1d20-3968-4ed2-90b3-00eea3060b02", "name": "Cloud Run"}]
    )
    rows = parse_provider_sessions(raw, cli_name="agy")
    assert rows[0]["id"] == "3b4a1d20-3968-4ed2-90b3-00eea3060b02"
    assert rows[0]["title"] == "Cloud Run"


def test_list_uses_folder_as_cwd(tmp_path, monkeypatch):
    from swarm.core.agent_folder import AgentFolderError

    captured: dict[str, str | None] = {}

    def fake_run(argv, timeout, cwd=None):
        captured["cwd"] = cwd
        return 0, json.dumps([{"id": "sid-1", "title": "One"}]), ""

    monkeypatch.setattr(
        "swarm.core.cli_session_select._default_run_list", fake_run
    )
    folder = tmp_path / "ws"
    folder.mkdir()
    payload = list_cli_sessions(
        "u1",
        "cli_agent",
        "echo",
        config=_list_config(str(tmp_path / "unused.py")),
        base_dir=tmp_path,
        folder=str(folder),
    )
    assert captured["cwd"] == str(folder.resolve())
    assert payload["sessions"][0]["id"] == "sid-1"

    with pytest.raises(AgentFolderError, match="does not exist"):
        list_cli_sessions(
            "u1",
            "cli_agent",
            "echo",
            config=_list_config(str(tmp_path / "unused.py")),
            base_dir=tmp_path,
            folder=str(tmp_path / "missing"),
        )


def test_select_rejects_bad_folder(tmp_path):
    from swarm.core.agent_folder import AgentFolderError

    with pytest.raises(AgentFolderError, match="does not exist"):
        select_cli_session(
            "u1",
            "cli_agent",
            "echo",
            start_new=True,
            folder=str(tmp_path / "missing"),
            base_dir=tmp_path,
        )


def test_select_explicit_sid_empty_chat_forces_reimport(tmp_path, monkeypatch):
    """#139: bound sid + empty/notice-only chat must not same_session import=none."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    # Notice-only: status chrome is not a visible model turn.
    chat_store.save(
        "u1",
        "cli_agent",
        [{"role": "status", "content": "Started a new echo session. No prior context."}],
        conversation_id="cur",
        cli_sessions={"echo": "sid-1"},
        base_dir=tmp_path,
    )

    import swarm.core.cli_session_stores as stores

    def fake_read(cli, sid):
        assert cli == "echo" and sid == "sid-1"
        return {
            "turns": [
                {"role": "user", "content": "hello from provider"},
                {"role": "assistant", "content": "provider reply"},
            ]
        }

    monkeypatch.setattr(stores, "read_provider_transcript", fake_read)
    again = select_cli_session(
        "u1",
        "cli_agent",
        "echo",
        session_id="sid-1",
        from_conversation_id="cur",
        base_dir=tmp_path,
    )
    assert again["same_session"] is False
    assert again["import"] == "full"
    texts = [str(m.get("content") or "") for m in again.get("messages") or []]
    assert any("hello from provider" in t for t in texts)
    assert any("provider reply" in t for t in texts)


def test_select_forwards_folder_into_resolve(tmp_path, monkeypatch):
    """#139: row.folder from SPA must reach resolve_session_cwd on select."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    folder = tmp_path / "ws"
    folder.mkdir()
    captured: dict = {}

    import swarm.core.agent_folder as agent_folder

    real = agent_folder.resolve_session_cwd

    def wrap(*, agent_id, raw):
        captured["agent_id"] = agent_id
        captured["raw"] = raw
        return real(agent_id=agent_id, raw=raw)

    monkeypatch.setattr(agent_folder, "resolve_session_cwd", wrap)
    res = select_cli_session(
        "u1",
        "cli_agent",
        "echo",
        session_id="sid-folder",
        folder=str(folder),
        base_dir=tmp_path,
    )
    assert res["same_session"] is False
    assert captured.get("raw") == str(folder)



def test_select_imports_grok_provider_transcript_real_reader(tmp_path, monkeypatch):
    """Non-qwen reader path: grok chat_history.jsonl -> select import=full."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()

    sid = "01a0849e-006a-70f1-ba75-603ac2aeb6d1"
    store = tmp_path / "grok-sessions"
    sess = store / quote("/home/dev/proj", safe="") / sid
    sess.mkdir(parents=True)
    lines = [
        {"type": "user", "content": [{"type": "text", "text": "hydrate me"}], "prompt_index": 0},
        {"type": "assistant", "content": "hydrated from grok"},
    ]
    (sess / "chat_history.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SWARM_GROK_SESSIONS_DIR", str(store))

    res = select_cli_session(
        "u-grok",
        "cli_agent",
        "grok",
        session_id=sid,
        title="hydrate",
        base_dir=tmp_path,
    )
    assert res["same_session"] is False
    assert res["import"] == "full"
    assert res["folder"] == "/home/dev/proj"
    texts = [str(m.get("content") or "") for m in res.get("messages") or []]
    assert any("hydrate me" in t for t in texts)
    assert any("hydrated from grok" in t for t in texts)
