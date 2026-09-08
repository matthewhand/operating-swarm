"""Provider session stores — ids + display metadata only."""

from __future__ import annotations

import json

from swarm.core.cli_session_stores import (
    list_agy_conversations,
    list_qwen_sessions,
    list_store_sessions,
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
    from swarm.core.cli_session_stores import read_qwen_transcript
    res = read_qwen_transcript(_write_qwen_transcript_fixture(tmp_path), "sid-9")
    assert res is not None
    assert res["cwd"] == "/home/dev/proj"
    assert res["git_branch"] == "feat/x"
    assert res["turns"] == [
        {"role": "user", "content": "run the tests"},
        {"role": "assistant", "content": "Running now."},
    ]


def test_qwen_transcript_reader_missing_is_none(tmp_path):
    from swarm.core.cli_session_stores import read_qwen_transcript
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
