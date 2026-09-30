"""A stored CLI session id the host no longer has is *recoverable*.

``Error: Session not found`` is not a broken seat: the CLI pruned the session,
the user cleared its state, or the id was copied from another machine. The
right behaviour is to drop the id, run one fresh turn, and say so — not to keep
handing the CLI a session id it will reject on every turn forever.

These tests pin the classifier on the real message shape, the end-to-end
recovery through the blueprint, and — most importantly — that a credential or
model fault is untouched.
"""

from __future__ import annotations

import sys

from swarm.blueprints.cli_agent.blueprint_cli_agent import CliAgentBlueprint
from swarm.core import chat_store
from swarm.core.cli_session_error import (
    MISSING_SESSION_RECOVERY_KEY,
    is_fatal_credential_or_model_error,
    is_fatal_config_error,
    is_missing_session_error,
    is_uncontinued_fatal_init,
    missing_session_notice_text,
    missing_session_recovery_extra,
    should_recover_cli_session,
)
from swarm.core.cli_sessions import get_cli_session, put_cli_session

PY = sys.executable

# The exact copy from a live seat sweep, and the adapter's own ``error`` field.
SWEEP_COPY = "opencode: exited 1: Error: Session not found"
ADAPTER_ERROR = "exited 1: Error: Session not found"


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #


def test_opencode_session_not_found_is_a_recoverable_missing_session():
    """The real message shape, both as reported and as the adapter reports it."""
    assert is_missing_session_error(SWEEP_COPY) is True
    assert is_missing_session_error(ADAPTER_ERROR) is True
    assert is_missing_session_error("[opencode] failed: exited 1: Error: Session not found") is True
    # The other shapes of the same class.
    assert is_missing_session_error("Error: Session not found: ses_abc123") is True
    assert is_missing_session_error("No conversation found with session ID x") is True
    assert is_missing_session_error("Error: unknown session") is True
    assert is_missing_session_error("cannot resume expired session") is True


def test_recovery_needs_an_id_that_was_actually_replayed():
    """No id on the command line means there is nothing to recover.

    A session-shaped message with no id replayed is something else (a provider
    complaining about its own transcript, say). Clearing the store there would
    be a guess that costs a turn.
    """
    assert should_recover_cli_session(ADAPTER_ERROR, session_id="ses_gone") is True
    assert should_recover_cli_session(ADAPTER_ERROR, session_id=None) is False
    assert should_recover_cli_session(ADAPTER_ERROR, session_id="") is False
    assert should_recover_cli_session(ADAPTER_ERROR, session_id="   ") is False


def test_credential_and_model_faults_are_never_a_missing_session():
    """Bad credentials / bad model keep their current behaviour.

    These are real config faults. Clearing the session id and retrying would
    hide one behind a reassuring "started a new session" and cost a turn.
    """
    for text in (
        "exited 1: Error: Unauthorized",
        "Error: 401 invalid api key",
        "Error: please log in to continue",
        "Error: insufficient_quota — add credits",
        "exited 1: Error: model not found: opencode-go/deepseek-v4.1-flash",
        "Error: unknown model: litellm/orchestration",
    ):
        assert is_fatal_credential_or_model_error(text) is True, text
        assert is_missing_session_error(text) is False, text
        assert should_recover_cli_session(text, session_id="ses_gone") is False, text


def test_missing_session_is_still_fatal_config_when_nothing_recovers():
    """The fatal copy is unchanged — pinned by the #499 / REQ-879 suites.

    Recovery happens at the call site (clear + one fresh run). If the fresh run
    also fails, the raw ``Error: Session not found`` must not be persisted as
    an ordinary reply, so the classifier keeps reporting it as fatal.
    """
    assert is_fatal_config_error(SWEEP_COPY) is True
    assert is_fatal_config_error(ADAPTER_ERROR) is True


def test_a_recovered_turn_is_history_not_a_poisoned_init():
    """A turn that recovered answered — it is not an uncontinued init failure."""
    recovered = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello from opencode"},
        {
            "role": "assistant",
            "content": "opencode: exited 1: Error: Session not found",
            MISSING_SESSION_RECOVERY_KEY: True,
        },
    ]
    assert missing_session_recovery_extra(SWEEP_COPY) == {MISSING_SESSION_RECOVERY_KEY: True}
    assert missing_session_recovery_extra("all good") == {}
    assert missing_session_recovery_extra("Error: Unauthorized") == {}
    # Already-marked meta short-circuits: the turn is a recovery, not a miss.
    assert is_missing_session_error(SWEEP_COPY, {MISSING_SESSION_RECOVERY_KEY: True}) is False
    assert is_uncontinued_fatal_init(recovered) is False


def test_notice_text_names_the_lost_session():
    """Honest copy: says what happened, not just "new session"."""
    text = missing_session_notice_text("opencode")
    assert "was gone" in text
    assert "opencode" in text
    # Must not claim a restore that never happened.
    assert "Resumed" not in text
    assert "on host:8000" in missing_session_notice_text("opencode", host="host:8000")
    # A nameless CLI still reads as a sentence.
    assert missing_session_notice_text("").startswith("The previous CLI session was gone")


def test_recovered_notice_is_recognised_as_session_chrome():
    """A restored transcript must treat the line as a notice, not a reply."""
    from swarm.core.chat_transcript import (
        is_cli_session_notice,
        is_new_cli_session_notice,
    )

    text = missing_session_notice_text("opencode")
    assert is_cli_session_notice(text) is True
    assert is_new_cli_session_notice(text) is True
    # A resume notice is not a new-session notice; still unchanged.
    assert is_new_cli_session_notice("Resumed opencode session.") is False


# --------------------------------------------------------------------------- #
# End-to-end recovery through the real blueprint
# --------------------------------------------------------------------------- #

_SCRIPT = """
import sys
if "--session" in sys.argv:
    sys.stderr.write("Error: Session not found\\n")
    raise SystemExit(1)
print("FRESH-OK " + sys.argv[-1])
"""


def _config(script: str, *, parse: str = "text") -> dict:
    return {
        "cli_agents": {
            "opencode": {
                "cmd": [PY, script, "{prompt}"],
                "parse": parse,
                "resume_argv": ["--session", "{session_id}"],
            }
        },
        "cli_fusion": {"default_cli": "opencode"},
    }


def _seed_stored_session(seat: str, session_id: str) -> None:
    """Put a stored session id on a thread that looks like a live one.

    ``active_cli`` matters: a thread only carries a session id because a
    previous turn succeeded, and that turn stamped the active CLI. Without it
    the hop layer reads the record as a switch *away from* ``_default`` and
    drops the id as part of the hop — which would make these tests pass for
    the wrong reason.
    """
    put_cli_session("u1", seat, "opencode", session_id)
    record = chat_store.load("u1", seat) or {}
    chat_store.save(
        "u1",
        seat,
        record.get("messages") or [],
        conversation_id=str(record.get("conversation_id") or ""),
        cli_sessions={"opencode": session_id},
        active_cli="opencode",
    )
    assert get_cli_session("u1", seat, "opencode") == session_id


async def _collect(gen):
    chunks = []
    async for c in gen:
        chunks.append(c)
    return chunks


def _final(chunks) -> str | None:
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


def _notices(chunks) -> list[str]:
    return [str(c.get("content") or "") for c in chunks if c.get("session_notice")]


async def test_stale_session_id_recovers_on_the_same_turn(tmp_path):
    """The seat answers, the dead id is dropped, and the line is honest.

    This is the live-sweep failure: a stored id opencode no longer has, replayed
    via ``resume_argv``. Before the fix the turn surfaced the raw
    ``Error: Session not found`` and the dead id stayed stored.
    """
    script = tmp_path / "cli.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    _seed_stored_session("seat1", "ses_gone")

    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_config(str(script)))
    bp.set_params({"user_key": "u1", "agent": "seat1", "cli": "opencode"})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))

    # The user gets an answer, not the CLI's rejection.
    assert _final(chunks).startswith("FRESH-OK")
    assert "Session not found" not in _final(chunks)
    # …and is told why, rather than being handed a bare "started a new session".
    notices = _notices(chunks)
    assert any("was gone" in n for n in notices), notices
    assert not any(n.startswith("Resumed") for n in notices), notices
    # The dead id is gone, so the *next* turn runs fresh instead of failing
    # the same way forever.
    assert get_cli_session("u1", "seat1", "opencode") is None


async def test_next_turn_after_recovery_starts_fresh(tmp_path):
    """The turn after a recovery must not replay the id the CLI rejected."""
    script = tmp_path / "cli.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    _seed_stored_session("seat2", "ses_gone")

    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_config(str(script)))
    bp.set_params({"user_key": "u1", "agent": "seat2", "cli": "opencode"})
    first = await _collect(bp.run([{"role": "user", "content": "one"}]))
    assert _final(first).startswith("FRESH-OK")

    second = await _collect(bp.run([{"role": "user", "content": "two"}]))
    assert _final(second).startswith("FRESH-OK")
    # No recovery notice the second time — the seat is healthy again.
    assert not any("was gone" in n for n in _notices(second)), _notices(second)


async def test_streaming_turn_recovers_too(tmp_path):
    """The streaming fast path recovers identically.

    It is a separate copy of the retry (bytes are on the wire, so it commits to
    one CLI), and a regression there would leave the WebUI seat broken while the
    non-streaming path looked fine.
    """
    script = tmp_path / "cli.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    _seed_stored_session("seat3", "ses_gone")

    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_config(str(script)))
    bp.set_params({"user_key": "u1", "agent": "seat3", "cli": "opencode"})
    chunks = await _collect(
        bp.run([{"role": "user", "content": "ping"}], stream=True)
    )

    assert _final(chunks).startswith("FRESH-OK")
    assert any("was gone" in n for n in _notices(chunks)), _notices(chunks)
    assert get_cli_session("u1", "seat3", "opencode") is None


async def test_one_retry_only_never_a_loop(tmp_path):
    """A CLI that rejects every run is retried exactly once, not forever.

    Guards the "do not over-retry" rule with an argv-counting CLI: the doomed
    resume plus a single fresh attempt, and no more.
    """
    log = tmp_path / "argv.log"
    always_fails = f"""
import sys
open({str(log)!r}, "a").write(repr(sys.argv[1:]) + "\\n")
sys.stderr.write("Error: Session not found\\n")
raise SystemExit(1)
"""
    script = tmp_path / "cli.py"
    script.write_text(always_fails, encoding="utf-8")
    _seed_stored_session("seat4", "ses_gone")

    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_config(str(script)))
    bp.set_params({"user_key": "u1", "agent": "seat4", "cli": "opencode"})
    await _collect(bp.run([{"role": "user", "content": "ping"}]))

    runs = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert len(runs) == 2, runs
    # First run replayed the dead id; the retry did not.
    assert "ses_gone" in runs[0]
    assert "ses_gone" not in runs[1]


_AUTH_SCRIPT = """
import sys
if "--session" in sys.argv:
    sys.stderr.write("Error: 401 Unauthorized\\n")
    raise SystemExit(1)
sys.stderr.write("Error: 401 Unauthorized\\n")
raise SystemExit(1)
"""


async def test_credential_failure_keeps_the_session_and_does_not_retry(tmp_path):
    """A bad credential must not be papered over by a fresh session.

    Same rejected id, but the CLI is failing on auth. The stored id survives
    (re-auth is a settings fix, and the user still wants that session), the CLI
    is spawned once, and the failure is reported as itself.
    """
    log = tmp_path / "argv.log"
    script = tmp_path / "cli.py"
    script.write_text(
        _AUTH_SCRIPT.replace(
            "import sys\n",
            f"import sys\nopen({str(log)!r}, 'a').write(repr(sys.argv[1:]) + '\\n')\n",
        ),
        encoding="utf-8",
    )
    _seed_stored_session("seat5", "ses_live")

    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_config(str(script)))
    bp.set_params({"user_key": "u1", "agent": "seat5", "cli": "opencode"})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))

    # No recovery, no fresh-session line.
    assert not any("was gone" in n for n in _notices(chunks)), _notices(chunks)
    assert "Unauthorized" in _final(chunks)
    # The stored id is untouched: clearing it would hide a real config fault.
    assert get_cli_session("u1", "seat5", "opencode") == "ses_live"
    # One spawn, not two — the retry is for session misses only.
    runs = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert len(runs) == 1, runs
