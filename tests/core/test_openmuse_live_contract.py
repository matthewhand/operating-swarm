"""Live-wire contract tests for the OpenMuse remote.

Every shape here was captured from a RUNNING OpenMuse instance
(`GET /api/health` -> 200 {ok, mode, agentConfigured, browserConfigured},
`POST /api/session` -> {token, mode}, `GET /api/agent/tasks/:id` ->
{task, files, browsers, events, artifacts}, errors as {"error": ...}).
These tests exist because the first pass of the impl guessed flat task
payloads and would have polled every live task to its deadline.
"""

from __future__ import annotations

import pytest

# The impl modules resolve their shared helpers through `swarm.core.remotes`,
# so importing an impl module before the kernel is a circular import.
from swarm.core import remotes as _remotes  # noqa: F401

from swarm.core.remote_impls.openmuse import (
    LIVE_QUESTION_STATUSES,
    LIVE_TASK_STATUSES,
    LIVE_TERMINAL_TASK_STATUSES,
    _server_error,
    _task_of,
    _task_state,
    openmuse_pending_question,
    openmuse_task_text,
)
from swarm.core.remote_impls.openmuse import _task_error_text

# --- the exact envelope the live instance returns ---------------------------
LIVE_RUNNING = {
    "task": {
        "id": "468291f6-9551-4c45-998b-1a7000e7a659",
        "kind": "agent",
        "title": "Reply with exactly the word PONG",
        "prompt": "Reply with exactly the word PONG",
        "status": "running",
        "result": "",
        "error": None,
        "plan": [
            {"id": "0", "title": "Understand the outcome", "status": "pending"},
            {"id": "1", "title": "Plan the work", "status": "pending"},
        ],
        "evidence": [],
        "input": {},
        "state": {"connectionId": None},
        "leaseId": "879df37a-1f8f-410c-943f-b2a230a148b4",
        "attempts": 2,
        "artifactIds": [],
        "createdAt": "2026-09-28T01:43:17.169Z",
        "updatedAt": "2026-09-28T01:48:19.904Z",
    },
    "files": [],
    "browsers": [],
    "events": [
        {
            "id": "1171c3fe",
            "date": "2026-09-28T01:43:17.865Z",
            "kind": "status",
            "title": "Started working",
            "detail": "Reply with exactly the word PONG",
            "taskId": "468291f6-9551-4c45-998b-1a7000e7a659",
        }
    ],
    "artifacts": [],
}

LIVE_TIMED_OUT = {
    "task": {**LIVE_RUNNING["task"], "status": "failed", "error": "Model run timed out after five minutes"},
    "files": [],
    "browsers": [],
    "events": [
        {
            "id": "4579384c",
            "date": "2026-09-28T01:48:17.891Z",
            "kind": "error",
            "title": "Task needs attention",
            "detail": "Model run timed out after five minutes",
            "taskId": "468291f6-9551-4c45-998b-1a7000e7a659",
        }
    ],
    "artifacts": [],
}


def test_task_detail_envelope_is_unwrapped_not_read_flat():
    """The live GET returns {task: {...}}; the task fields are one level down."""
    task = _task_of(LIVE_RUNNING)
    assert task["id"] == "468291f6-9551-4c45-998b-1a7000e7a659"
    assert task["status"] == "running"
    # A bare task row still works (some call sites hold the task itself).
    assert _task_of({"id": "t-1", "status": "queued"})["id"] == "t-1"
    assert _task_of("not a dict") == {}


def test_task_state_reads_through_the_envelope():
    assert _task_state(LIVE_RUNNING) == "running"
    assert _task_state(LIVE_TIMED_OUT) == "failed"
    # Flat rows and junk still behave.
    assert _task_state({"status": "succeeded"}) == "succeeded"
    assert _task_state(None) == ""


def test_live_status_enum_matches_the_upstream_taskstatus_type():
    # packages/domain/src/agent.ts TaskStatus, verbatim.
    assert LIVE_TASK_STATUSES == {
        "queued",
        "running",
        "waiting_approval",
        "waiting_input",
        "scheduled",
        "paused",
        "succeeded",
        "failed",
        "cancelled",
    }
    # The server's own `terminal` set in engine/service.ts.
    assert LIVE_TERMINAL_TASK_STATUSES == {"succeeded", "failed", "cancelled"}
    # A working task is never terminal, however long it runs.
    for working in ("queued", "running", "scheduled", "paused"):
        assert working in LIVE_TASK_STATUSES
        assert working not in LIVE_TERMINAL_TASK_STATUSES
    assert LIVE_QUESTION_STATUSES == {"waiting_input", "waiting_approval"}


def test_answer_text_comes_from_the_nested_task_result():
    done = {
        "task": {**LIVE_RUNNING["task"], "status": "succeeded", "result": "PONG"},
        "events": [],
    }
    assert openmuse_task_text(done) == "PONG"
    # While working, `result` is an empty string — never a reply.
    assert openmuse_task_text(LIVE_RUNNING) == ""


def test_answer_text_falls_back_to_a_result_runevent_detail():
    """RunEvent prose lives in `detail`, and a finished run emits kind:result."""
    detail = {
        "task": {**LIVE_RUNNING["task"], "status": "succeeded", "result": ""},
        "events": [
            {"kind": "status", "title": "Started working", "detail": "working"},
            {"kind": "result", "title": "Done", "detail": "Deployed build 482 to staging."},
        ],
    }
    assert openmuse_task_text(detail) == "Deployed build 482 to staging."


def test_answer_text_reads_a_step_event_and_last_update_when_result_is_empty():
    """Live regression: a task that answered "OK" with `result` still empty.

    Captured from a running instance — `task.result` was "", the only copies of
    the reply were `state.lastUpdate` and a `kind:"step"` "Agent update" event.
    The previous filter only accepted kinds matching _EVENT_TEXT_HINTS, so
    "step" was skipped and the seat reported an empty turn: a working remote
    read as broken.
    """
    live = {
        "task": {
            **LIVE_RUNNING["task"],
            "status": "succeeded",
            "result": "",
            "state": {"lastUpdate": "OK", "connectionId": None},
        },
        "events": [
            {"kind": "status", "title": "Started working", "detail": "Reply with OK"},
            {"kind": "step", "title": "Agent update", "detail": "OK"},
            {"kind": "step", "title": "Finish only when the outcome is achieved", "detail": ""},
        ],
    }
    assert openmuse_task_text(live) == "OK"

    # Same answer with no state at all: the step event still carries it.
    no_state = {**live, "task": {**live["task"], "state": {}}}
    assert openmuse_task_text(no_state) == "OK"


def test_a_real_result_event_still_wins_over_a_step_event():
    live = {
        "task": {**LIVE_RUNNING["task"], "status": "succeeded", "result": "", "state": {}},
        "events": [
            {"kind": "step", "title": "Agent update", "detail": "interim chatter"},
            {"kind": "result", "title": "Work completed", "detail": "The final answer."},
        ],
    }
    assert openmuse_task_text(live) == "The final answer."


def test_progress_only_step_events_are_not_mistaken_for_an_answer():
    # Empty-detail progress steps must not become the reply.
    progress = {
        "task": {**LIVE_RUNNING["task"], "status": "succeeded", "result": "", "state": {}},
        "events": [
            {"kind": "status", "title": "Started working", "detail": "working"},
            {"kind": "step", "title": "Plan the work", "detail": ""},
        ],
    }
    assert openmuse_task_text(progress) == ""


def test_failure_reason_comes_from_task_error_then_the_error_event():
    assert _task_error_text(LIVE_TIMED_OUT) == "Model run timed out after five minutes"
    # No task.error, but the run emitted an error event.
    event_only = {
        "task": {**LIVE_RUNNING["task"], "status": "failed", "error": None},
        "events": LIVE_TIMED_OUT["events"],
    }
    assert _task_error_text(event_only) == "Model run timed out after five minutes"
    assert _task_error_text(LIVE_RUNNING) == ""


def test_pending_question_is_read_off_the_nested_task():
    waiting = {
        "task": {**LIVE_RUNNING["task"], "status": "waiting_input", "question": "Which environment?"},
        "events": [],
    }
    found = openmuse_pending_question(waiting, task_id="468291f6")
    assert found is not None
    assert found["question"]["ask"] == "Which environment?"
    # The envelope's own id wins over the caller's hint.
    assert found["task_id"] == "468291f6-9551-4c45-998b-1a7000e7a659"
    # A finished task has no question even though it has a result.
    assert (
        openmuse_pending_question(
            {"task": {**LIVE_RUNNING["task"], "status": "succeeded", "question": None}},
            task_id="t-9",
        )
        is None
    )


def test_error_envelope_is_hono_error_not_fastapi_detail():
    # Captured live: 422 {"error": "Invalid input: expected string, received undefined"}
    assert _server_error({"error": "This task is not waiting for input"}) == (
        "This task is not waiting for input"
    )
    assert _server_error({"error": "Only failed tasks can be retried"}) == (
        "Only failed tasks can be retried"
    )
    # Captured live: 401 {"error": "Sign in to OpenMuse"}
    assert _server_error({"error": "Sign in to OpenMuse"}) == "Sign in to OpenMuse"
    # Other builds/surfaces still tolerated.
    assert _server_error({"detail": "Not Found"}) == "Not Found"
    assert _server_error({"message": "boom"}) == "boom"
    assert _server_error({}) == ""
    assert _server_error("plain text") == "plain text"


def test_health_route_is_the_unauthenticated_api_health():
    """`/api/health` is the only route that answers without a session token.

    The agent routes 404 on the verified build, so they cannot be the probe.
    """
    from swarm.core.remotes import default_spec

    spec = default_spec("openmuse")
    assert spec.health_path == "/api/health"
    assert spec.version_path == "/api/health"


@pytest.mark.parametrize(
    "status,expect_terminal",
    [
        ("queued", False),
        ("running", False),
        ("waiting_input", False),
        ("waiting_approval", False),
        ("scheduled", False),
        ("paused", False),
        ("succeeded", True),
        ("failed", True),
        ("cancelled", True),
    ],
)
def test_every_live_status_has_an_unambiguous_disposition(status, expect_terminal):
    """No live status may be polled to the deadline, or read as done early."""
    assert (status in LIVE_TERMINAL_TASK_STATUSES) is expect_terminal
