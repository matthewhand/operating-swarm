"""Provider session stores — ids + display metadata + transcript readers."""

from __future__ import annotations

import json
import sqlite3

from swarm.core.cli_session_stores import (
    PROVIDER_TRANSCRIPT_READERS,
    list_agy_conversations,
    list_qwen_sessions,
    list_store_sessions,
    read_agy_transcript,
    read_grok_transcript,
    read_opencode_transcript,
    read_provider_transcript,
    read_qwen_transcript,
)
from swarm.core.cli_catalog import list_sessions_store, list_sessions_store_dir


def test_agy_store_uses_stem_and_mtime_never_opens_db(tmp_path):
    sid = "d1d8a55b-cc27-4dd4-bc62-2f73015960d2"
    path = tmp_path / f"{sid}.db"
    path.write_bytes(b"SQLite format 3 not a real db")
    (tmp_path / f"{sid}.db-wal").write_bytes(b"wal")
    rows = list_agy_conversations(tmp_path)
    assert [r["id"] for r in rows] == [sid]
    assert rows[0]["title"] == sid
    assert rows[0]["source"] == "provider"
    assert rows[0]["updated_at"].endswith("Z")


def test_agy_store_skips_secrets_and_non_db(tmp_path):
    (tmp_path / "sk-live-secret-key.db").write_bytes(b"x")
    (tmp_path / "readme.txt").write_text("hi")
    assert list_agy_conversations(tmp_path) == []


def test_unknown_store_kind_is_empty():
    assert list_store_sessions("not-a-store", "/tmp") == []


def test_missing_dir_is_empty(tmp_path):
    assert list_agy_conversations(tmp_path / "nope") == []
    assert list_agy_conversations(None) == []


def _write_qwen_session(root, project, sid, first_prompt="fix the login bug"):
    chats = root / project / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "type": "user",
            "sessionId": sid,
            "timestamp": "2026-09-06T21:09:58.449Z",
            "cwd": "/home/x/project",
            "message": {"role": "user", "parts": [{"text": first_prompt}]},
        },
        {
            "type": "assistant",
            "sessionId": sid,
            "message": {"role": "model", "parts": [{"text": "Done."}]},
        },
    ]
    (chats / f"{sid}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


QWEN_JSONL = """{"uuid":"a","type":"system","cwd":"/home/dev/proj","gitBranch":"feat/x","systemPayload":{}}
{"uuid":"b","type":"user","cwd":"/home/dev/proj","message":{"role":"user","parts":[{"text":"run the tests"}]}}
{"uuid":"c","type":"assistant","cwd":"/home/dev/proj","message":{"role":"model","parts":[{"text":"On it.","thought":true},{"text":"Running now."}]}}
{"uuid":"d","type":"tool_result","message":{}}
"""


def _write_qwen_transcript_fixture(tmp_path, sid="sid-9"):
    chats = tmp_path / "-home-dev-proj" / "chats"
    chats.mkdir(parents=True)
    (chats / f"{sid}.jsonl").write_text(QWEN_JSONL)
    return tmp_path


def test_qwen_transcript_reader_returns_turns_cwd_branch(tmp_path):
    res = read_qwen_transcript(_write_qwen_transcript_fixture(tmp_path), "sid-9")
    assert res is not None
    assert res["cwd"] == "/home/dev/proj"
    assert res["git_branch"] == "feat/x"
    assert res["turns"] == [
        {"role": "user", "content": "run the tests"},
        {"role": "assistant", "content": "Running now."},
    ]


def test_qwen_transcript_reader_missing_is_none(tmp_path):
    assert read_qwen_transcript(tmp_path, "nope") is None


def test_qwen_store_lists_sessions_with_folder_and_title(tmp_path):
    sid = "db59c49d-827d-4785-a168-35e7b7b427e0"
    _write_qwen_session(tmp_path, "-home-x-my-proj", sid, first_prompt="is open-swarm up?")
    rows = list_qwen_sessions(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == sid
    assert row["source"] == "provider"
    assert row["folder"] == "-home-x-my-proj"
    assert row["title"] == "is open-swarm up?"
    assert row["updated_at"].endswith("Z")


def test_qwen_store_skips_secret_ids_and_orders_by_mtime(tmp_path):
    old = "11111111-2222-4333-8444-555555555555"
    new = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    _write_qwen_session(tmp_path, "-p1", old)
    _write_qwen_session(tmp_path, "-p2", new)
    # Make the second file newer.
    import os, time

    future = time.time() + 60
    os.utime(tmp_path / "-p2" / "chats" / f"{new}.jsonl", (future, future))
    rows = list_qwen_sessions(tmp_path)
    assert [r["id"] for r in rows] == [new, old]


def test_qwen_store_dispatches_via_catalog():
    assert list_sessions_store("qwen", None) == "qwen_sessions"
    assert (list_sessions_store_dir("qwen", None) or "").endswith(".qwen/projects")
    assert list_store_sessions("qwen_sessions", "/nonexistent-dir") == []


def test_provider_transcript_registry_is_pluggable():
    assert set(PROVIDER_TRANSCRIPT_READERS) >= {"qwen", "agy", "grok", "opencode"}
    assert read_provider_transcript("pi", "sid-1") is None
    assert read_provider_transcript("kilo", "sid-1") is None
    assert read_provider_transcript("qwen", None) is None


def _write_grok_session(root, sid, cwd="/home/dev/proj"):
    from urllib.parse import quote

    folder = root / quote(cwd, safe="")
    sess = folder / sid
    sess.mkdir(parents=True)
    lines = [
        {"type": "system", "content": "You are grok."},
        {
            "type": "user",
            "content": [{"type": "text", "text": "ignore me"}],
            "synthetic_reason": "system_reminder",
        },
        {
            "type": "user",
            "content": [{"type": "text", "text": "say hello from grok"}],
            "prompt_index": 0,
        },
        {
            "type": "assistant",
            "content": "hello from grok",
            "tool_calls": [{"id": "c1", "name": "noop", "arguments": "{}"}],
        },
        {"type": "assistant", "content": "", "tool_calls": [{"id": "c2", "name": "x"}]},
        {"type": "tool_result", "content": "ok"},
    ]
    (sess / "chat_history.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )
    return root


def test_grok_transcript_reader_returns_turns(tmp_path):
    sid = "01a0849e-006a-70f1-ba75-603ac2aeb6d1"
    res = read_grok_transcript(_write_grok_session(tmp_path, sid), sid)
    assert res is not None
    assert res["cwd"] == "/home/dev/proj"
    assert res["turns"] == [
        {"role": "user", "content": "say hello from grok"},
        {"role": "assistant", "content": "hello from grok"},
    ]


def test_read_provider_transcript_dispatches_grok(tmp_path, monkeypatch):
    sid = "01a0849e-006a-70f1-ba75-603ac2aeb6d1"
    _write_grok_session(tmp_path, sid)
    monkeypatch.setenv("SWARM_GROK_SESSIONS_DIR", str(tmp_path))
    res = read_provider_transcript("grok", sid)
    assert res is not None
    assert res["turns"][0]["content"] == "say hello from grok"


def _write_opencode_db(tmp_path, sid="ses_test123abcXYZ"):
    db = tmp_path / "opencode.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE session (
          id TEXT PRIMARY KEY,
          project_id TEXT,
          directory TEXT,
          title TEXT,
          time_created INTEGER,
          time_updated INTEGER
        );
        CREATE TABLE message (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          time_created INTEGER,
          time_updated INTEGER,
          data TEXT
        );
        CREATE TABLE part (
          id TEXT PRIMARY KEY,
          message_id TEXT,
          session_id TEXT,
          time_created INTEGER,
          time_updated INTEGER,
          data TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO session(id, project_id, directory, title, time_created, time_updated) "
        "VALUES (?,?,?,?,?,?)",
        (sid, "global", "/home/dev/oc", "hi", 1, 2),
    )
    con.execute(
        "INSERT INTO message(id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?)",
        ("msg_u1", sid, 10, 10, json.dumps({"role": "user"})),
    )
    con.execute(
        "INSERT INTO message(id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?)",
        ("msg_a1", sid, 20, 20, json.dumps({"role": "assistant", "path": {"cwd": "/home/dev/oc"}})),
    )
    con.execute(
        "INSERT INTO part(id, message_id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?,?)",
        ("prt_1", "msg_u1", sid, 11, 11, json.dumps({"type": "text", "text": "ping opencode", "synthetic": False})),
    )
    con.execute(
        "INSERT INTO part(id, message_id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?,?)",
        ("prt_2", "msg_a1", sid, 21, 21, json.dumps({"type": "reasoning", "text": "thinking"})),
    )
    con.execute(
        "INSERT INTO part(id, message_id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?,?)",
        ("prt_3", "msg_a1", sid, 22, 22, json.dumps({"type": "text", "text": "pong from opencode"})),
    )
    con.commit()
    con.close()
    return tmp_path, sid


def test_opencode_transcript_reader_from_db(tmp_path):
    root, sid = _write_opencode_db(tmp_path)
    res = read_opencode_transcript(root, sid)
    assert res is not None
    assert res["cwd"] == "/home/dev/oc"
    assert res["turns"] == [
        {"role": "user", "content": "ping opencode"},
        {"role": "assistant", "content": "pong from opencode"},
    ]


def _write_agy_db(tmp_path, sid="a960100c-b1a8-4520-8cfb-fafea20cf206"):
    """Minimal steps table with protobuf-ish printable payloads."""
    db = tmp_path / f"{sid}.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload BLOB, step_format INTEGER)"
    )
    con.execute(
        "CREATE TABLE trajectory_metadata_blob (id TEXT, data BLOB)"
    )
    user_prompt = "Audit the scripts and report two findings."
    # Duplicate prompt like real agy payloads.
    user_blob = user_prompt.encode() + b"\x00\x01" + user_prompt.encode()
    assist_blob = json.dumps(
        {"Message": "Finding one.\nFinding two.", "Recipient": "user", "toolAction": "notify"}
    ).encode()
    meta = b"pad file:///home/dev/agy-proj more"
    con.execute(
        "INSERT INTO trajectory_metadata_blob(id, data) VALUES (?, ?)",
        ("main", meta),
    )
    con.execute(
        "INSERT INTO steps(idx, step_type, step_payload, step_format) VALUES (?,?,?,?)",
        (0, 14, user_blob, 0),
    )
    con.execute(
        "INSERT INTO steps(idx, step_type, step_payload, step_format) VALUES (?,?,?,?)",
        (1, 8, b'{"AbsolutePath":"/x","toolAction":"Viewing"}', 0),
    )
    con.execute(
        "INSERT INTO steps(idx, step_type, step_payload, step_format) VALUES (?,?,?,?)",
        (2, 132, assist_blob, 0),
    )
    con.commit()
    con.close()
    return tmp_path, sid


def test_agy_transcript_reader_extracts_user_and_final(tmp_path):
    root, sid = _write_agy_db(tmp_path)
    res = read_agy_transcript(root, sid)
    assert res is not None
    assert res["cwd"] == "/home/dev/agy-proj"
    assert res["turns"][0] == {
        "role": "user",
        "content": "Audit the scripts and report two findings.",
    }
    assert res["turns"][1]["role"] == "assistant"
    assert "Finding one" in res["turns"][1]["content"]
