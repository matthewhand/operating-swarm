"""#1658 follow-up — an OpenMuse seat must offer a selectable target.

The navbar agent picker (`remoteAgentsFromOperate` -> `ombBotsFromOperate`)
reads `agents` / `bots` from the list payload. A list that carries only
`sessions` left the seat with nothing to pick, so send had no target and the
OpenMuse seat was unusable in the composer even though it was healthy.

Contract pinned here:
  * no task index  -> exactly one honest target, "New OpenMuse task"
  * a task index   -> one target per real task, by id, so picking one resumes
  * the sentinel resolves to "no resume key" on send (it never polls for a
    task the instance has never heard of)
  * a real task id is still resumed, and the remote's own name is still refused
"""

from __future__ import annotations

# Import the kernel first: the impl modules resolve their shared helpers through
# `swarm.core.remotes`, so importing an impl module before the kernel is a
# circular import. (Same ordering the other openmuse test files use.)
from swarm.core import remotes as _remotes  # noqa: F401

from swarm.core.remote_impls.openmuse import (
    NEW_TASK_ID,
    NEW_TASK_LABEL,
    _openmuse_agents,
    _resolve_task_id,
)


class _Spec:
    id = "openmuse"
    name = "openmuse"
    agent = ""


def test_no_task_index_offers_exactly_one_honest_target():
    agents = _openmuse_agents([])
    assert agents == [{"id": NEW_TASK_ID, "name": NEW_TASK_LABEL}]


def test_real_tasks_are_offered_by_id_so_picking_one_resumes_it():
    agents = _openmuse_agents(
        [
            {"id": "task-a", "title": "Ship the release"},
            {"id": "task-b", "title": ""},
        ]
    )
    assert [a["id"] for a in agents] == ["task-a", "task-b"]
    # A task with no title still gets a usable label.
    assert agents[1]["name"] == "OpenMuse task"
    # And picking it is a real resume, not a create.
    assert _resolve_task_id(_Spec(), "task-a", None) == ("task-a", "")


def test_the_sentinel_means_no_resume_key():
    task_id, err = _resolve_task_id(_Spec(), NEW_TASK_ID, None)
    assert (task_id, err) == ("", "")
    # Same when it arrives as the session id.
    assert _resolve_task_id(_Spec(), "", NEW_TASK_ID) == ("", "")


def test_no_target_at_all_still_creates_a_task():
    assert _resolve_task_id(_Spec(), "", None) == ("", "")


def test_the_remote_own_name_is_still_refused():
    # TrueForge #1159 parity: never ask OpenMuse for a task named after the
    # seat. The guard is per-instance — a named instance refuses its own id.
    assert _resolve_task_id(_Spec(), "openmuse", None) == ("", "self")

    class _PublicSpec:
        id = "openmuse_public"
        name = "openmuse_public"
        agent = ""

    assert _resolve_task_id(_PublicSpec(), "openmuse_public", None) == ("", "self")
    # Stricter still: the canonical kind names are refused on every instance, so
    # no seat can ever be talked into polling for a task called "openmuse".
    assert _resolve_task_id(_PublicSpec(), "openmuse", None) == ("", "self")
    assert _resolve_task_id(_PublicSpec(), "open-muse", None) == ("", "self")
    # A real task id is untouched.
    assert _resolve_task_id(_PublicSpec(), "7bb3ac61-8085-4ca8-b038-3fd7e1bc3253", None) == (
        "7bb3ac61-8085-4ca8-b038-3fd7e1bc3253",
        "",
    )


def test_a_malformed_id_is_still_refused():
    assert _resolve_task_id(_Spec(), "has space", None)[1] == "bad-id"
    assert _resolve_task_id(_Spec(), "x" * 200, None)[1] == "bad-id"
