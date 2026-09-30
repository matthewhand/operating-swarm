"""Issue #1690 — a CLI seat must RESUME its host session on the follow-up turn.

The resume machinery exists end to end (catalog ``resume_argv``, the adapter's
argv injection, the per-thread ``cli_sessions`` store). What was missing is the
proof that the loop is *closed*: turn 1 mints a host session id, that id is
stored, and turn 2 replays it. If the hop layer drops the id, or the store never
persists it, the seat silently starts a brand-new host session every turn while
the UI still implies continuity.

These tests drive two real turns through :class:`CliAgentBlueprint` with a fake
host CLI that mints a fresh id per run and echoes the id it was resumed with, so
"did turn 2 reuse turn 1's id" is observable rather than inferred. The argv
prefix comes from the real catalog ``cmd``, so ``resume_insert`` lands exactly
where production lands it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from swarm.blueprints.cli_agent.blueprint_cli_agent import CliAgentBlueprint
from swarm.core import chat_store, cli_catalog
from swarm.core.cli_sessions import get_cli_session

# A fake host CLI. It behaves like the real ones: a resume flag names an
# existing session, otherwise a brand new one is minted. Every invocation is
# appended to ``$FAKE_CLI_LOG`` so a test can assert on the exact argv.
_FAKE_CLI = '''\
import json, os, sys

RESUME_FLAGS = ("--session", "--conversation", "--resume", "--continue", "resume")
argv = sys.argv[1:]
with open(os.environ["FAKE_CLI_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")

resumed = ""
for i, arg in enumerate(argv):
    if arg in RESUME_FLAGS and i + 1 < len(argv):
        resumed = argv[i + 1]
        break

state_path = os.environ["FAKE_CLI_STATE"]
try:
    with open(state_path, encoding="utf-8") as fh:
        minted = int(fh.read().strip() or "0")
except (OSError, ValueError):
    minted = 0

if not resumed:
    minted += 1
    with open(state_path, "w", encoding="utf-8") as fh:
        fh.write(str(minted))
    sid = "host-sess-%d" % minted
    verdict = "FRESH"
else:
    sid = resumed
    verdict = "RESUMED"

# One id under every key the catalog and its default paths look at, so the
# extraction works for any CLI in the matrix regardless of its parse spec.
body = verdict + " " + sid
blob = {
    "session_id": sid, "sessionId": sid, "session": sid, "id": sid,
    "conversation_id": sid, "conversationId": sid, "thread_id": sid,
    "text": body, "response": body, "result": body, "message": body,
    "content": body, "output": body, "answer": body, "status": "ok",
}
print(json.dumps(blob))
'''

# The CLIs the issue names, in the order the issue lists them.
ISSUE_CLIS = ["agy", "codex", "grok", "opencode"]
# Everything else in the catalog, so a regression in one CLI is not masked.
MATRIX = ISSUE_CLIS + ["claude", "gemini", "qwen", "omp", "pi"]


def _seat(tmp_path: Path, cli: str):
    """Build a blueprint whose only CLI is a fake host binary named ``cli``.

    The catalog ``cmd`` is reused verbatim except for argv[0], so the argv the
    fake sees is the argv production would build.
    """
    log = tmp_path / "argv.log"
    state = tmp_path / "state"
    script = tmp_path / f"{cli}.py"
    script.write_text(f"#!{sys.executable}\n" + _FAKE_CLI, encoding="utf-8")
    script.chmod(0o755)
    catalog = cli_catalog.CATALOG[cli]
    cmd = [str(script), *catalog["cmd"][1:]]
    raw = {"cmd": cmd, "parse": catalog.get("parse", "text")}
    if catalog.get("prompt_mode"):
        raw["prompt_mode"] = catalog["prompt_mode"]
    config = {
        "cli_agents": {cli: raw},
        "cli_fusion": {"default_cli": cli},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=config)
    # The fake CLI needs its two scratch paths. Names only, no secrets.
    env = {"FAKE_CLI_LOG": str(log), "FAKE_CLI_STATE": str(state)}
    return bp, log, env


async def _collect(gen) -> list[dict]:
    return [chunk async for chunk in gen]


def _text(chunks) -> str:
    text = ""
    for chunk in chunks:
        msgs = chunk.get("messages") if isinstance(chunk, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = str(msgs[0]["content"])
    return text


def _sid(text: str) -> str:
    match = re.search(r"host-sess-\d+", text or "")
    assert match, f"no session id in the CLI reply: {text!r}"
    return match.group(0)


def _notices(chunks) -> list[str]:
    return [str(c.get("content") or "") for c in chunks if c.get("session_notice")]


def _runs(log: Path) -> list[list[str]]:
    if not log.is_file():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line
    ]


async def _turn(
    bp: CliAgentBlueprint,
    seat: str,
    cli: str,
    text: str,
    *,
    stream: bool = False,
    cid: str = "",
    user_key: str = "u1690",
):
    params: dict = {"user_key": user_key, "agent": seat, "cli": cli}
    if cid:
        params["conversation_id"] = cid
    bp.set_params(params)
    return await _collect(bp.run([{"role": "user", "content": text}], stream=stream))


def _resume_argv_for(cli: str) -> list[str]:
    return list((cli_catalog.session_policy(cli) or {}).get("resume_argv") or [])


@pytest.mark.parametrize("cli", MATRIX)
async def test_followup_turn_replays_the_stored_session_id(tmp_path, monkeypatch, cli):
    """THE bug: turn 2 must carry turn 1's host session id on its argv.

    Before the fix the second spawn omits the resume flag, the CLI mints a
    second id, and the seat has silently thrown away the whole conversation.
    """
    bp, log, env = _seat(tmp_path, cli)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    seat = f"seat-{cli}"

    first = await _turn(bp, seat, cli, "remember: the pin is 7")
    second = await _turn(bp, seat, cli, "what was the pin?")

    runs = _runs(log)
    first_id = _sid(_text(first))
    second_id = _sid(_text(second))
    assert second_id == first_id, (
        f"{cli}: turn 1 minted {first_id}, turn 2 minted {second_id} — the seat "
        f"started a new host session instead of resuming. argv: {runs}"
    )
    assert f"RESUMED {first_id}" in _text(second), _text(second)
    assert len(runs) == 2, f"{cli}: expected 2 spawns, got {len(runs)}: {runs}"

    # The resume argv really reached the process, in the catalog's shape.
    resume_argv = _resume_argv_for(cli)
    assert resume_argv, f"{cli} declares no resume_argv — needs a real policy"
    for token in [*resume_argv[:-1], first_id]:
        assert token in runs[1], f"{cli}: {token!r} missing from {runs[1]}"
    # Turn 1 had nothing to resume and must not have pretended otherwise.
    for token in resume_argv[:-1]:
        assert token not in runs[0], f"{cli}: turn 1 already injected {token!r}"


@pytest.mark.parametrize("cli", MATRIX)
async def test_followup_turn_keeps_the_id_it_replayed(tmp_path, monkeypatch, cli):
    """A resume must not be one-shot: the id stays on the thread afterwards."""
    bp, _, env = _seat(tmp_path, cli)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    seat = f"keep-{cli}"

    await _turn(bp, seat, cli, "one")
    stored = get_cli_session("u1690", seat, cli)
    assert stored, f"{cli}: turn 1 stored no session id"
    await _turn(bp, seat, cli, "two")
    assert get_cli_session("u1690", seat, cli) == stored


@pytest.mark.parametrize("cli", ISSUE_CLIS)
async def test_streaming_followup_turn_replays_the_stored_session_id(
    tmp_path, monkeypatch, cli
):
    """The streaming fast path is a separate copy of the resume logic.

    Once bytes are on the wire it commits to one CLI, so it re-implements
    read → resume → stamp by hand. A regression there leaves the seat broken
    while the non-streaming path looks fine.
    """
    bp, log, env = _seat(tmp_path, cli)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    seat = f"stream-{cli}"

    first = await _turn(bp, seat, cli, "remember: the pin is 7", stream=True)
    second = await _turn(bp, seat, cli, "what was the pin?", stream=True)

    first_id = _sid(_text(first))
    second_id = _sid(_text(second))
    assert second_id == first_id, (
        f"{cli}: streaming — turn 1 minted {first_id}, turn 2 minted "
        f"{second_id}. argv: {_runs(log)}"
    )
    assert get_cli_session("u1690", seat, cli) == first_id


async def test_turn_announces_the_resume_instead_of_a_new_session(tmp_path, monkeypatch):
    """The user-facing line must match what actually happened."""
    bp, _, env = _seat(tmp_path, "agy")
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    first = await _turn(bp, "seat-notice", "agy", "one")
    second = await _turn(bp, "seat-notice", "agy", "two")

    assert any("Started a new agy session" in n for n in _notices(first)), _notices(first)
    assert any("Resumed agy session" in n for n in _notices(second)), _notices(second)
    assert not any("Started a new" in n for n in _notices(second)), _notices(second)
    # A plain resume is not a context hop — no fake "carried context" chrome.
    assert not any("Carried context" in n for n in _notices(second)), _notices(second)


async def test_kilocode_is_honest_about_never_resuming(tmp_path, monkeypatch):
    """kilo 1.0.0 has no session flag (#1658). The seat must say so, not fake it.

    A stored id for a CLI with no resume argv is dead weight: it is never
    replayed. This pins the honest behaviour — no invented flag on the argv, no
    "Resumed" claim — so a future change cannot quietly make it pretend.
    """
    assert cli_catalog.session_policy("kilocode")["resume_unsupported_reason"]
    bp, log, env = _seat(tmp_path, "kilocode")
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    first = await _turn(bp, "seat-kilo", "kilocode", "one")
    second = await _turn(bp, "seat-kilo", "kilocode", "two")

    runs = _runs(log)
    assert len(runs) == 2, runs
    for run in runs:
        assert "--resume" not in run, f"invented a resume flag for kilo: {run}"
        assert "--session" not in run, f"invented a session flag for kilo: {run}"
    assert not any("Resumed" in n for n in _notices(second)), _notices(second)
    assert any("Started a new kilocode session" in n for n in _notices(second))
    # The seat answered both turns even though it cannot resume.
    assert _text(first) and _text(second)


async def test_an_unstamped_thread_does_not_fire_a_bogus_hop():
    """Root-cause guard: an unset ``active_cli`` is not a CLI switch.

    ``chat_store.normalize_agent_id("")`` returns ``_default``, so a thread
    whose ``active_cli`` was never written reads as "we were on ``_default`` and
    are now switching to opencode". That spurious hop forces ``resume_id=None``
    and drops the stored id — a fresh host session every turn, with a hop notice
    the user never asked for.
    """
    from swarm.core.cli_session_hop import maybe_implicit_hop

    chat_store.save(
        "u1690",
        "seat-hop",
        [{"role": "user", "content": "hi"}],
        conversation_id="",
        cli_sessions={"opencode": "host-sess-1"},
        active_cli="",
    )
    record = chat_store.load("u1690", "seat-hop") or {}
    assert record.get("cli_sessions") == {"opencode": "host-sess-1"}
    assert not record.get("active_cli"), record.get("active_cli")

    hop = maybe_implicit_hop(
        "u1690", "seat-hop", "opencode", [{"role": "user", "content": "hi"}]
    )
    assert hop is None, f"an unstamped thread fired a hop: {hop}"
    # …and the id it already had is still there to resume.
    assert get_cli_session("u1690", "seat-hop", "opencode") == "host-sess-1"


# --------------------------------------------------------------------------- #
# The production shape: a real user, a minted conversation, and the transcript
# write the consumer performs between turns.
# --------------------------------------------------------------------------- #

def _cid(cli: str) -> str:
    """A non-default conversation id, one per CLI.

    ``ChatConversation.conversation_id`` is globally unique, so a shared id
    across the parameterised runs would collide on the owner check.
    """
    return f"chat-minted-1690-{cli}"


@pytest.mark.django_db
@pytest.mark.parametrize("cli", ISSUE_CLIS)
async def test_minted_conversation_resumes_across_turns(monkeypatch, tmp_path, cli):
    """A real seat thread: minted ``conversation_id``, real user, real persist.

    Every WebUI conversation other than the default one is stored in its own
    ``<agent>__<conversation_id>.json`` file (``chat_repository._session_id_for``)
    while the CLI id was being written to the agent's default file. The next
    turn reads the conversation's own file, finds no ``cli_sessions`` key, and
    starts a fresh host session — the loop never closes.
    """
    from asgiref.sync import sync_to_async
    from django.contrib.auth import get_user_model

    from swarm.core.chat_repository import append_message

    bp, log, env = _seat(tmp_path, cli)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    user = await sync_to_async(get_user_model().objects.create_user)(
        username=f"issue1690-{cli}", password="pw"
    )
    user_key = chat_store.user_key_for(user)
    seat = f"seat-django-{cli}"
    cid = _cid(cli)
    assert cid != chat_store.conversation_id_for(user, seat)

    first = await _turn(bp, seat, cli, "remember: the pin is 7", cid=cid, user_key=user_key)
    first_id = _sid(_text(first))
    # The consumer stores each turn as one ChatMessage row; that is what
    # refreshes the JSON cache between turns.
    await sync_to_async(append_message)(
        user, seat, cid, {"role": "user", "content": "remember: the pin is 7"}
    )
    await sync_to_async(append_message)(
        user, seat, cid, {"role": "assistant", "content": _text(first)}
    )

    # The invariant, stated on the file itself: the id and the stamp that
    # explains it live on the conversation's own record.
    thread_file = (
        chat_store.store_dir() / "active" / user_key / f"{seat}__{cid}.json"
    )
    assert thread_file.is_file(), sorted(p.name for p in thread_file.parent.glob("*.json"))
    record = json.loads(thread_file.read_text(encoding="utf-8"))
    assert record.get("cli_sessions") == {cli: first_id}, record.get("cli_sessions")
    assert record.get("active_cli") == cli, record.get("active_cli")

    second = await _turn(bp, seat, cli, "what was the pin?", cid=cid, user_key=user_key)

    runs = _runs(log)
    second_id = _sid(_text(second))
    assert second_id == first_id, (
        f"{cli}: minted conversation — turn 1 minted {first_id}, turn 2 minted "
        f"{second_id}. argv: {runs}"
    )
    assert f"RESUMED {first_id}" in _text(second), _text(second)
    assert get_cli_session(user_key, seat, cli, conversation_id=cid) == first_id


# `transaction=True` is REQUIRED here, not a style choice. This is an ASYNC
# test, and its database work does not land on the connection pytest-django's
# plain `django_db` atomic block wraps, so the writes COMMIT FOR REAL and were
# never rolled back. The casualties were durable and outlived the test:
# `create_user` left a `User`, and the two `update_settings(...)` calls below
# each emit a `settings.patched` activity event, leaving two `ActivityEventRow`s
# for `agent/seat-stem`.
#
# Those rows then broke an unrelated, much later test in the same session:
# `tests/core/test_org_policy_1317.py::
# test_unavailable_company_model_falls_back_and_records_activity` asserts
# `ActivityEventRow.objects.get()` -- i.e. exactly one row, the one this test
# is about -- and raised
# `MultipleObjectsReturned: get() returned more than one ActivityEventRow --
# it returned 3!`. It passes in isolation, so it read as an order-dependent
# flake in an unrelated file; the real defect was the leak on this side.
#
# `transaction=True` selects pytest-django's `TransactionTestCase` semantics:
# real commits, plus a `flush` at teardown, so everything this test writes is
# actually removed and the next test starts clean. Verified with the pair:
#   pytest tests/core/test_issue1690_cli_resume_loop.py::\
# test_thread_stem_tracks_the_thread_layer_it_mirrors \
#          tests/core/test_org_policy_1317.py::\
# test_unavailable_company_model_falls_back_and_records_activity
# -> 1 failed (2 leaked rows) before, 2 passed after.
@pytest.mark.django_db(transaction=True)
async def test_thread_stem_tracks_the_thread_layer_it_mirrors(monkeypatch, tmp_path):
    """``thread_session_id`` must agree with ``_session_id_for``.

    The two live in different modules on purpose (one is the thread layer, one
    is the CLI id store) but they must name the same file, or the id is written
    somewhere the transcript is not. If the thread layer ever changes its rule,
    this fails instead of the seat silently losing resume again.
    """
    from asgiref.sync import sync_to_async
    from django.contrib.auth import get_user_model

    from swarm.core.agent_settings import (
        KEY_NEW_CHAT_PER_TASK,
        is_new_chat_per_task,
        reset_agent_settings_cache,
        update_settings,
    )
    from swarm.core.chat_repository import _session_id_for
    from swarm.core.cli_sessions import thread_session_id

    user = await sync_to_async(get_user_model().objects.create_user)(
        username="issue1690-stem", password="pw"
    )
    user_key = chat_store.user_key_for(user)
    seat = "seat-stem"
    # Keep the settings store off the developer's real agent_settings.json.
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    reset_agent_settings_cache()
    default_cid = chat_store.conversation_id_for(user, seat)
    minted_cid = "chat-minted-1690-stem"

    assert thread_session_id(user_key, seat, default_cid) == _session_id_for(
        user, seat, default_cid
    ) == ""
    assert thread_session_id(user_key, seat, minted_cid) == _session_id_for(
        user, seat, minted_cid
    ) == minted_cid
    # No conversation id at all is the default file.
    assert thread_session_id(user_key, seat, "") == _session_id_for(user, seat, "") == ""

    # New-chat-per-task files EVERY conversation under its own stem, including
    # the owner's default one.
    monkey = update_settings(seat, {KEY_NEW_CHAT_PER_TASK: True})
    try:
        reset_agent_settings_cache()
        assert is_new_chat_per_task(seat) is True, monkey
        assert thread_session_id(user_key, seat, default_cid) == _session_id_for(
            user, seat, default_cid
        ) == default_cid
    finally:
        update_settings(seat, {KEY_NEW_CHAT_PER_TASK: False})
        reset_agent_settings_cache()

    # An existing record wins over the prediction, so a layout already on disk
    # is never second-guessed.
    chat_store.save(
        user_key,
        seat,
        [{"role": "user", "content": "hi"}],
        conversation_id=minted_cid,
        session_id="some-other-stem",
    )
    assert thread_session_id(user_key, seat, minted_cid) == "some-other-stem"


# --- regression guard for the isolation defect fixed above ------------------
# This one is a real behavioural assertion, not a marker check: it runs AFTER
# `test_thread_stem_tracks_the_thread_layer_it_mirrors` in the same session and
# asserts that nothing that test wrote is still in the database. If the
# `transaction=True` is ever reverted to a plain `django_db`, the async test's
# writes commit for real, these rows reappear, and THIS fails -- naming the
# defect at its actual boundary rather than at a decorator.
#
# It is the same fact that broke an unrelated file: those two
# `ActivityEventRow`s turned
# `test_org_policy_1317.py::test_unavailable_company_model_falls_back_and_records_activity`
# into a `MultipleObjectsReturned` that only appeared in a full-suite run.
@pytest.mark.django_db
def test_the_stem_test_leaves_no_durable_rows_behind():
    from django.contrib.auth import get_user_model

    from swarm.models.activity import ActivityEventRow

    leaked_events = list(
        ActivityEventRow.objects.filter(entity_id="seat-stem").values_list(
            "action", "entity_id"
        )
    )
    assert leaked_events == [], (
        "the async test above committed activity rows that outlived it: "
        f"{leaked_events!r}"
    )

    leaked_users = list(
        get_user_model()
        .objects.filter(username="issue1690-stem")
        .values_list("username", flat=True)
    )
    assert leaked_users == [], (
        f"the async test above committed a User that outlived it: {leaked_users!r}"
    )

