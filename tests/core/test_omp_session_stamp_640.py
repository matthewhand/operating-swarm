"""#640 — omp session ids must be captured so turn N+1 resumes.

omp (Oh My Pi) prints plain text under ``-p`` (its JSON event stream only
appears with ``--mode json``), so the generic stdout extractor never sees a
session id. But omp *persists every session* it runs:

    ~/.omp/agent/sessions/<encoded-cwd>/<timestamp>_<sessionId>.jsonl

(docs/session.md in can1357/oh-my-pi). The same provider-store contract the
catalog already exploits for qwen/agy. So after a successful production turn
(non-smoke), Open Swarm stamps the newest session file stem as the thread's
omp session id — turn N+1 passes ``--resume <id>`` and the notice becomes
truthful ("Resumed omp session.").
"""

from __future__ import annotations

import time

import pytest

from swarm.core.cli_session_stores import (
    DEFAULT_OMP_SESSIONS_DIR,
    OMP_SESSIONS_STORE,
    latest_omp_session_id,
    list_omp_sessions,
)


def _make_omp_session(root, sid: str, cwd_enc: str = "-home-me-proj", age: float = 0.0):
    bucket = root / cwd_enc
    bucket.mkdir(parents=True, exist_ok=True)
    path = bucket / f"20260919_0800_{sid}.jsonl"
    path.write_text('{"type":"session","id":"%s"}\n' % sid, encoding="utf-8")
    stamp = time.time() - age
    import os

    os.utime(path, (stamp, stamp))
    return path


# ── provider store enumeration ───────────────────────────────────────────────


def test_latest_omp_session_id_returns_newest_stem(tmp_path):
    _make_omp_session(tmp_path, "aaaa1111bbbb2222", age=100.0)
    _make_omp_session(tmp_path, "dddd4444cccc3333", age=1.0)
    got = latest_omp_session_id(str(tmp_path))
    assert got == "dddd4444cccc3333"


def test_latest_omp_session_id_ignores_partials_and_junk(tmp_path):
    _make_omp_session(tmp_path, "deadbeefdeadbeef", age=5.0)
    (tmp_path / "-home-me-proj" / "20260919_0800_partial.jsonl").write_text("{}", encoding="utf-8")
    assert latest_omp_session_id(str(tmp_path)) == "deadbeefdeadbeef"


def test_latest_omp_session_id_missing_store_is_none(tmp_path):
    assert latest_omp_session_id(str(tmp_path / "nope")) is None
    assert latest_omp_session_id("") is None
    assert latest_omp_session_id(None) is None


def test_list_omp_sessions_rows_are_honest(tmp_path):
    _make_omp_session(tmp_path, "aaaa1111bbbb2222", age=42.0)
    rows = list_omp_sessions(str(tmp_path))
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "aaaa1111bbbb2222"
    assert row["source"] == "provider"
    assert row["updated_at"]


# ── catalog wiring ───────────────────────────────────────────────────────────


def test_omp_catalog_declares_session_store():
    from swarm.core import cli_catalog

    assert cli_catalog.list_sessions_store("omp") == OMP_SESSIONS_STORE
    assert cli_catalog.can_list_sessions("omp") is True
    assert cli_catalog.list_sessions_store_dir("omp", None) is not None


def test_store_dispatches_omp_kind(tmp_path):
    from swarm.core.cli_session_stores import list_store_sessions

    _make_omp_session(tmp_path, "aaaa1111bbbb2222")
    rows = list_store_sessions(OMP_SESSIONS_STORE, str(tmp_path))
    assert [r["id"] for r in rows] == ["aaaa1111bbbb2222"]


# ── end-to-end: two turns on one thread resume ───────────────────────────────


@pytest.mark.asyncio
async def test_omp_second_turn_resumes_via_store_stamp(tmp_path, monkeypatch):
    """Fixture omp prints text only (no JSON), writes its own session file.

    Turn 1: no stored id → honest 'Started a new omp session.'; the store
    stamp records the fixture's session id. Turn 2: '--resume <id>' reaches
    the CLI and the notice is 'Resumed omp session.'
    """
    import sys

    from swarm.blueprints.cli_agent.blueprint_cli_agent import CliAgentBlueprint
    from swarm.core.cli_sessions import get_cli_session
    from tests.blueprints.test_cli_agent import (
        _collect,
        _final_content,
        _session_notices,
    )

    omp_store = tmp_path / "omp-home" / "sessions"
    monkeypatch.setenv("SWARM_OMP_SESSIONS_DIR", str(omp_store))
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chat"))

    script = tmp_path / "omp_fixture.py"
    script.write_text(
        "import json, sys, os, time\n"
        "args = sys.argv[1:]\n"
        "resume = args[args.index('--resume') + 1] if '--resume' in args else None\n"
        "sid = resume or 'feed1234feed1234'\n"
        "store = os.environ['SWARM_OMP_SESSIONS_DIR']\n"
        "bucket = os.path.join(store, '-home-me-proj')\n"
        "os.makedirs(bucket, exist_ok=True)\n"
        "with open(os.path.join(bucket, '20260919_0800_' + sid + '.jsonl'), 'w') as f:\n"
        "    f.write(json.dumps({'type': 'session', 'id': sid}) + '\\n')\n"
        "print('plain text answer resume=' + str(resume))\n",
        encoding="utf-8",
    )
    cfg = {
        "cli_agents": {
            "omp": {
                "cmd": [sys.executable, str(script), "{prompt}"],
                "parse": "text",
                "resume_argv": ["--resume", "{session_id}"],
                "resume_insert": 2,
            }
        },
        "cli_fusion": {"default_cli": "omp"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"user_key": "u1", "agent": "cli_agent", "cli": "omp", "failover": False})
    first = await _collect(bp.run([{"role": "user", "content": "hello"}]))
    assert _final_content(first) == "plain text answer resume=None"
    assert _session_notices(first) == ["Started a new omp session."]
    assert get_cli_session("u1", "cli_agent", "omp") == "feed1234feed1234"

    bp.set_params({"user_key": "u1", "agent": "cli_agent", "cli": "omp", "failover": False})
    second = await _collect(
        bp.run(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "plain text answer resume=None"},
                {"role": "user", "content": "again"},
            ]
        )
    )
    assert _final_content(second) == "plain text answer resume=feed1234feed1234"
    assert _session_notices(second) == ["Resumed omp session."]
    assert all("Started a new" not in n for n in _session_notices(second))


@pytest.mark.asyncio
async def test_omp_smoke_run_never_stamps_store(tmp_path, monkeypatch):
    """Smoke/verify runs carry --no-session in the cmd: nothing stamped."""
    import sys

    from swarm.blueprints.cli_agent.blueprint_cli_agent import CliAgentBlueprint
    from swarm.core.cli_sessions import get_cli_session
    from tests.blueprints.test_cli_agent import _collect, _final_content

    omp_store = tmp_path / "omp-home" / "sessions"
    monkeypatch.setenv("SWARM_OMP_SESSIONS_DIR", str(omp_store))
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chat"))

    script = tmp_path / "omp_smoke.py"
    script.write_text(
        "import os, sys\n"
        "bucket = os.path.join(os.environ['SWARM_OMP_SESSIONS_DIR'], '-home-me-proj')\n"
        "os.makedirs(bucket, exist_ok=True)\n"
        "open(os.path.join(bucket, '20260919_0800_cafe1234cafe1234.jsonl'), 'w').write('{}\\n')\n"
        "print('smoke ok')\n",
        encoding="utf-8",
    )
    cfg = {
        "cli_agents": {
            "omp": {
                # Smoke/verify shape: --no-session is IN the cmd (ephemeral).
                "cmd": [sys.executable, str(script), "--no-session", "{prompt}"],
                "parse": "text",
            }
        },
        "cli_fusion": {"default_cli": "omp"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params(
        {
            "user_key": "u1",
            "agent": "cli_agent",
            "cli": "omp",
            "failover": False,
        }
    )
    chunks = await _collect(bp.run([{"role": "user", "content": "smoke"}]))
    assert _final_content(chunks) == "smoke ok"
    assert get_cli_session("u1", "cli_agent", "omp") in (None, "")


def test_default_omp_sessions_dir_is_agent_bucket():
    assert DEFAULT_OMP_SESSIONS_DIR == "~/.omp/agent/sessions"


# ── real-world id shape (#640 skeptic fix) ──────────────────────────────────


def test_latest_omp_session_id_accepts_hyphenated_uuid(tmp_path):
    """Real omp ids are hyphenated UUIDs — they must not be filtered out."""
    real = "01a0b694-440e-740c-aa3a-cfa4e89c4847"
    _make_omp_session(tmp_path, real, age=1.0)
    assert latest_omp_session_id(str(tmp_path)) == real


def test_latest_omp_session_id_still_ignores_junk_stems(tmp_path):
    _make_omp_session(tmp_path, "01a0b694-440e-740c-aa3a-cfa4e89c4847", age=9.0)
    bucket = tmp_path / "-home-me-proj"
    (bucket / "20260919_0800_not-an-id.jsonl").write_text("{}", encoding="utf-8")
    (bucket / "20260919_0800_partial.jsonl").write_text("{}", encoding="utf-8")
    (bucket / "README.txt").write_text("x", encoding="utf-8")
    assert (
        latest_omp_session_id(str(tmp_path))
        == "01a0b694-440e-740c-aa3a-cfa4e89c4847"
    )
