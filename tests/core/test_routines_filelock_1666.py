"""#1666 — the routines store is a whole-file read-modify-write, so every
mutator has to serialise on the sibling ``FileLock`` or two writers each
commit the snapshot they read and drop the other's rows.

Mirrors the ``filelock`` pattern established in ``agent_memory`` (a sibling
``.lock``, ``Timeout`` surfaced as ``OSError``) and the contention tests in
``test_activity_log_1314``.

What the seat-budget accounting change already provided, and why it was not
enough: ``_settlement_lock`` is a ``threading.RLock``, so it orders nothing
across processes, and it only ever wrapped ``append_history`` /
``settle_routine_tokens`` — the operator PATCH path never took it, so the tick's
run row and the operator's PATCH were two unlocked read-modify-writes of the
same row list. The store's file lock is what orders them, and it is taken for
the read *and* the write, with the rows reloaded from disk rather than built on
the process cache.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from filelock import FileLock

from swarm.core import routines as store


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _path(tmp_path) -> Path:
    return tmp_path / "agent_routines.json"


def _create(agent: str, name: str) -> dict:
    return store.create_routine(agent, {"name": name})


def _stagger_reads(monkeypatch, delay: float) -> None:
    """Widen the read->write window so interleaving is the rule, not luck.

    Without the guard every writer reads the same snapshot and then all of
    them write, so the test fails deterministically instead of racing.
    """
    real_read = store._read_store

    def staggered_read() -> dict:
        data = real_read()
        time.sleep(delay)
        return data

    monkeypatch.setattr(store, "_read_store", staggered_read)


def _held(path, seconds: float = 5):
    """A separate interpreter holding the store lock, so the OS lock is real."""
    holder = textwrap.dedent(
        """
        import sys, time
        from filelock import FileLock
        lock = FileLock(sys.argv[1])
        lock.acquire()
        print("held", flush=True)
        time.sleep(float(sys.argv[2]))
        lock.release()
        """
    )
    child = subprocess.Popen(
        [sys.executable, "-c", holder, str(path), str(seconds)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "held"
    return child


def test_stale_cache_does_not_clobber_disk(tmp_path, monkeypatch):
    """A cached snapshot must never be the base of a write."""
    _isolate(tmp_path, monkeypatch)
    _create("codey", "kept")
    store._cache = {"schema": store.SCHEMA, "agents": {}}
    _create("codey", "added")
    store.reset_routines_cache()
    assert {row["name"] for row in store.list_routines("codey")} == {"kept", "added"}


def test_a_write_keeps_a_row_another_process_edited(tmp_path, monkeypatch):
    """The same lost update, without needing two writers to interleave.

    A second process (or an operator's editor) wrote the file behind this
    process's back. The next PATCH must be based on what is on disk, or the
    other writer's ``description`` is dropped without a trace.
    """
    path = _path(tmp_path)
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine("codey", {"name": "Hourly recap"})
    assert store.get_routine("codey", created["id"])["description"] == ""

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    on_disk["agents"]["codey"][0]["description"] = "written by the other process"
    path.write_text(json.dumps(on_disk), encoding="utf-8")

    store.update_routine("codey", created["id"], {"name": "Renamed"})

    row = store.get_routine("codey", created["id"])
    assert row["name"] == "Renamed"
    assert row["description"] == "written by the other process"


def test_a_listing_sees_another_process_write(tmp_path, monkeypatch):
    """The cache is stamped on the file, so it cannot pin a stale store."""
    path = _path(tmp_path)
    _isolate(tmp_path, monkeypatch)
    created = _create("codey", "kept")
    assert len(store.list_routines("codey")) == 1

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    on_disk["agents"]["scout"] = [
        {
            "id": "r-other",
            "name": "Added elsewhere",
            "instruction": "Do it.",
            "active": True,
            "trigger": {"kind": "interval", "seconds": 60},
        }
    ]
    path.write_text(json.dumps(on_disk), encoding="utf-8")

    assert {row["id"] for row in store.list_all_routines()} == {created["id"], "r-other"}


def test_an_unreadable_store_is_not_overwritten(tmp_path, monkeypatch):
    """A failed read must not publish an empty store over every routine."""
    path = _path(tmp_path)
    _isolate(tmp_path, monkeypatch)
    created = _create("codey", "kept")
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(OSError):
        store.update_routine("codey", created["id"], {"name": "Renamed"})

    # The rows are still on disk, untouched, for an operator to recover.
    assert path.read_text(encoding="utf-8") == "{ not json"
    store.reset_routines_cache()
    assert store.list_routines("codey") == []


def test_concurrent_creates_keep_every_row(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: _create("codey", f"row-{i}"), range(8)))
    store.reset_routines_cache()
    assert {row["name"] for row in store.list_routines("codey")} == {
        f"row-{i}" for i in range(8)
    }


def test_concurrent_creates_keep_every_row_when_reads_stagger(tmp_path, monkeypatch):
    """The same assertion with the read->write window forced wide open.

    ``_store_lock`` alone would not be enough here: the process cache is
    dropped inside the guard so each writer re-reads what the previous
    writer committed.
    """
    _isolate(tmp_path, monkeypatch)
    _stagger_reads(monkeypatch, 0.05)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: _create("codey", f"row-{i}"), range(8)))
    store.reset_routines_cache()
    assert {row["name"] for row in store.list_routines("codey")} == {
        f"row-{i}" for i in range(8)
    }


def test_concurrent_writes_across_agents_keep_every_row(tmp_path, monkeypatch):
    """One agent's clobber must not take another agent's rows with it."""
    _isolate(tmp_path, monkeypatch)
    _stagger_reads(monkeypatch, 0.05)
    agents = ["codey", "codex", "support", "research"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda pair: _create(pair[0], f"row-{pair[1]}"),
                [(agent, i) for agent in agents for i in range(2)],
            )
        )
    store.reset_routines_cache()
    for agent in agents:
        assert {row["name"] for row in store.list_routines(agent)} == {
            f"row-{i}" for i in range(2)
        }


def test_concurrent_create_and_delete_keep_every_survivor(tmp_path, monkeypatch):
    """A delete re-reading a stale snapshot resurrects deleted rows."""
    _isolate(tmp_path, monkeypatch)
    doomed = [_create("codey", f"doomed-{i}") for i in range(3)]
    _create("codey", "keeper")
    _stagger_reads(monkeypatch, 0.05)

    def remove(routine_id: str) -> None:
        assert store.delete_routine("codey", routine_id) is True

    def add(i: int) -> None:
        _create("codey", f"fresh-{i}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(remove, row["id"]) for row in doomed]
        futures += [pool.submit(add, i) for i in range(3)]
        for future in futures:
            future.result()

    store.reset_routines_cache()
    names = {row["name"] for row in store.list_routines("codey")}
    assert names == {"keeper", "fresh-0", "fresh-1", "fresh-2"}


def test_concurrent_history_appends_keep_every_run_row(tmp_path, monkeypatch):
    """``append_history`` shares the store, so it takes the same guard."""
    _isolate(tmp_path, monkeypatch)
    routine = _create("codey", "nightly")
    routine_id = routine["id"]
    _stagger_reads(monkeypatch, 0.05)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(
            pool.map(
                lambda i: store.append_history(
                    "codey", routine_id, source="test", event=f"run-{i}"
                ),
                range(6),
            )
        )

    store.reset_routines_cache()
    stored = store.get_routine("codey", routine_id)
    assert stored is not None
    assert {row["event"] for row in stored["history"]} == {f"run-{i}" for i in range(6)}


def test_a_fire_and_an_operator_patch_lose_nothing(tmp_path, monkeypatch):
    """The filed case in one process: a tick run and a PATCH on one routine."""
    path = _path(tmp_path)
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Hourly recap",
            "instruction": "Recap the hour.",
            "trigger": {"kind": "interval", "seconds": 3600},
        },
    )
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def fire() -> None:
        try:
            barrier.wait(timeout=10)
            for index in range(15):
                store.append_history(
                    "codey", created["id"], source="schedule", summary=f"tick {index}"
                )
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    def patch() -> None:
        try:
            barrier.wait(timeout=10)
            for index in range(15):
                store.update_routine(
                    "codey", created["id"], {"name": f"Nightly {index}"}
                )
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    workers = [threading.Thread(target=fire), threading.Thread(target=patch)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=120)

    assert errors == []
    row = store.get_routine("codey", created["id"])
    assert len(row["history"]) == 15
    assert row["name"] == "Nightly 14"
    assert len(json.loads(path.read_text(encoding="utf-8"))["agents"]["codey"][0]["history"]) == 15


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork-based writers need POSIX")
def test_two_processes_writing_one_store_lose_nothing(tmp_path, monkeypatch):
    """Separate processes, one store: the race ``_settlement_lock`` cannot see."""
    path = _path(tmp_path)
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Hourly recap",
            "instruction": "Recap the hour.",
            "trigger": {"kind": "interval", "seconds": 3600},
        },
    )
    per_child, children = 12, 2

    pids = []
    for child in range(children):
        pid = os.fork()
        if pid == 0:  # pragma: no cover - the child only speaks through the file
            try:
                for index in range(per_child):
                    store.append_history(
                        "codey",
                        created["id"],
                        source="schedule",
                        summary=f"child {child} run {index}",
                    )
            finally:
                os._exit(0)
        pids.append(pid)
    for pid in pids:
        assert os.waitpid(pid, 0)[1] == 0

    store.reset_routines_cache()
    assert len(store.get_routine("codey", created["id"])["history"]) == per_child * children
    assert len(json.loads(path.read_text(encoding="utf-8"))["agents"]["codey"][0]["history"]) == per_child * children


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork-based writers need POSIX")
def test_a_process_write_survives_a_stale_reader_in_the_parent(tmp_path, monkeypatch):
    """A parent's cached store must not hide what its children wrote."""
    _isolate(tmp_path, monkeypatch)
    created = _create("codey", "kept")
    assert len(store.list_routines("codey")) == 1  # warm this process's cache

    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child only speaks through the file
        try:
            store.update_routine("codey", created["id"], {"description": "from the child"})
        finally:
            os._exit(0)
    assert os.waitpid(pid, 0)[1] == 0

    assert store.get_routine("codey", created["id"])["description"] == "from the child"


def test_a_nested_store_write_does_not_self_deadlock(tmp_path, monkeypatch):
    """Re-entry is counted, so an inner write cannot block on its own thread."""
    _isolate(tmp_path, monkeypatch)
    created = _create("codey", "kept")

    def outer(data):
        # A mutator that has to persist twice is the re-entrancy hazard: a
        # second FileLock instance for the same file would block on a lock this
        # thread already holds.
        store._mutate_store(lambda _inner: ("inner", False))
        return data, True

    assert store._mutate_store(outer) is not None
    assert [row["id"] for row in store.list_routines("codey")] == [created["id"]]


def test_write_reports_busy_when_lock_is_held(tmp_path, monkeypatch):
    """A store that cannot be locked is reported, not written blind."""
    _isolate(tmp_path, monkeypatch)
    _create("codey", "kept")
    path = store.routines_path()
    monkeypatch.setattr(store, "_LOCK_TIMEOUT_SECONDS", 0.2)
    held = FileLock(store.routines_lock_path(path), timeout=5)
    held.acquire()
    try:
        with pytest.raises(OSError, match="Could not lock agent routines"):
            _create("codey", "blocked")
    finally:
        held.release()
    store.reset_routines_cache()
    assert [row["name"] for row in store.list_routines("codey")] == ["kept"]


def test_another_process_holding_the_lock_blocks_the_write(tmp_path, monkeypatch):
    """The guard is a real cross-process lock, not a thread lock.

    The holder is a separate interpreter so this exercises the OS-level
    advisory lock rather than the in-process ``RLock``. It only needs
    ``filelock``, so it never touches Django settings or the config root.
    """
    _isolate(tmp_path, monkeypatch)
    _create("codey", "kept")
    path = store.routines_path()
    lock_path = store.routines_lock_path(path)
    monkeypatch.setattr(store, "_LOCK_TIMEOUT_SECONDS", 0.5)

    child = _held(lock_path)
    try:
        with pytest.raises(OSError, match="Could not lock agent routines"):
            _create("codey", "blocked")
    finally:
        child.kill()
        child.wait(timeout=30)

    store.reset_routines_cache()
    assert [row["name"] for row in store.list_routines("codey")] == ["kept"]


def test_the_operator_patch_waits_for_the_store_lock(tmp_path, monkeypatch):
    """The PATCH is ordered by the *file* lock, not by the settlement lock.

    ``_settlement_lock`` is process-local and the PATCH never took it, so
    before #1666 this write sailed straight through an external writer's
    critical section. Now it waits, and completes once the lock is free.
    """
    _isolate(tmp_path, monkeypatch)
    created = _create("codey", "kept")
    path = store.routines_path()
    outcome: dict[str, object] = {}

    def writer() -> None:
        try:
            outcome["value"] = store.update_routine(
                "codey", created["id"], {"description": "written after the lock"}
            )
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            outcome["error"] = exc

    with FileLock(str(store.routines_lock_path(path)), timeout=5):
        worker = threading.Thread(target=writer)
        worker.start()
        worker.join(timeout=1.0)
        blocked = worker.is_alive()
    worker.join(timeout=30)

    assert blocked is True, "the write did not wait for the store lock"
    assert "error" not in outcome
    assert outcome["value"]["description"] == "written after the lock"


def test_the_run_row_waits_for_the_store_lock_too(tmp_path, monkeypatch):
    """Both writers take the same lock, which is what orders them."""
    _isolate(tmp_path, monkeypatch)
    created = _create("codey", "kept")
    path = store.routines_path()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            store.append_history("codey", created["id"], source="test")
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    with FileLock(str(store.routines_lock_path(path)), timeout=5):
        worker = threading.Thread(target=writer)
        worker.start()
        worker.join(timeout=1.0)
        blocked = worker.is_alive()
    worker.join(timeout=30)

    assert blocked is True
    assert errors == []
    assert len(store.get_routine("codey", created["id"])["history"]) == 1


def test_lock_is_released_after_a_failed_write(tmp_path, monkeypatch):
    """A raising mutator must not leave the store locked or the cache pinned."""
    _isolate(tmp_path, monkeypatch)
    _create("codey", "nightly")
    with pytest.raises(ValueError):
        store.update_routine("codey", store.list_routines("codey")[0]["id"], {"nope": 1})
    updated = store.update_routine("codey", store.list_routines("codey")[0]["id"], {"name": "renamed"})
    assert updated["name"] == "renamed"


def test_duplicate_detection_is_atomic_with_the_create(tmp_path, monkeypatch):
    """Two identical creates racing must not both land."""
    _isolate(tmp_path, monkeypatch)
    payload = {
        "name": "Ship notes",
        "instruction": "Summarize the merged pull request.",
        "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
    }
    _stagger_reads(monkeypatch, 0.05)
    errors: list[BaseException] = []

    def add() -> None:
        try:
            store.create_routine("codey", payload)
        except store.DuplicateRoutineError:
            pass
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=add) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    store.reset_routines_cache()
    assert len(store.list_routines("codey")) == 1
