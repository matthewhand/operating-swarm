"""#1316 — an agent cannot silently create a twin routine.

``create_routine`` must reject a routine whose normalized
``{name, instruction, trigger}`` already exists for the same agent, while
still allowing genuinely distinct routines and explicit ``allow_duplicate``
copies.
"""

import pytest

from swarm.core import routines as store


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _payload(**overrides):
    payload = {
        "name": "Ship notes",
        "instruction": "Summarize the merged pull request.",
        "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
    }
    payload.update(overrides)
    return payload


def test_identical_routine_is_blocked(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    first = store.create_routine("codey", _payload())

    with pytest.raises(store.DuplicateRoutineError) as excinfo:
        store.create_routine("codey", _payload())

    assert excinfo.value.existing_id == first["id"]
    assert excinfo.value.existing["id"] == first["id"]
    # No twin was written.
    rows = store.list_routines("codey")
    assert len(rows) == 1
    assert rows[0]["id"] == first["id"]


def test_case_and_whitespace_variants_are_duplicates(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    first = store.create_routine("codey", _payload())

    variants = [
        _payload(name="  ship   NOTES  "),
        _payload(instruction="summarize the   merged pull request."),
        _payload(name="SHIP NOTES", instruction="Summarize the merged pull request. "),
    ]
    for variant in variants:
        with pytest.raises(store.DuplicateRoutineError) as excinfo:
            store.create_routine("codey", variant)
        assert excinfo.value.existing_id == first["id"]
    assert len(store.list_routines("codey")) == 1


def test_distinct_instruction_or_trigger_is_allowed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_routine("codey", _payload())
    store.create_routine("codey", _payload(instruction="Write a release post instead."))
    store.create_routine(
        "codey",
        _payload(trigger={"kind": "github_pr_merged", "owner_repo": "other/repo"}),
    )
    # Same fingerprint only within one agent: another agent may own a copy.
    store.create_routine("other", _payload())
    assert len(store.list_routines("codey")) == 3
    assert len(store.list_routines("other")) == 1


def test_allow_duplicate_creates_a_deliberate_copy(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    first = store.create_routine("codey", _payload())

    twin = store.create_routine("codey", {**_payload(), "allow_duplicate": True})
    assert twin["id"] != first["id"]
    assert len(store.list_routines("codey")) == 2

    # Stringy truthy values are honoured too.
    again = store.create_routine("codey", {**_payload(), "allow_duplicate": "true"})
    assert again["id"] not in {first["id"], twin["id"]}
    assert len(store.list_routines("codey")) == 3


def test_blocked_duplicate_is_stable_and_recoverable(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    first = store.create_routine("codey", _payload())

    # Idempotency edge: repeated blocked attempts report the same existing row
    # and never mutate the store.
    for _ in range(3):
        with pytest.raises(store.DuplicateRoutineError) as excinfo:
            store.create_routine("codey", _payload())
        assert excinfo.value.existing_id == first["id"]
    assert len(store.list_routines("codey")) == 1

    # Once the original is deleted, the same payload can be created again.
    assert store.delete_routine("codey", first["id"]) is True
    recreated = store.create_routine("codey", _payload())
    assert recreated["id"] != first["id"]
    assert len(store.list_routines("codey")) == 1
