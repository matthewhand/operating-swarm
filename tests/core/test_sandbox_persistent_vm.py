"""#1329 — persistent per-bot local VM dirs, LRU cap, and identity context."""

from __future__ import annotations

import os

import pytest

from swarm.core.sandbox import SandboxManager, vm_registry
from swarm.core.sandbox.vm_registry import (
    DEFAULT_VM_CAP,
    bind_bot_context,
    current_bot_context,
    enforce_cap,
    reset_bot_context,
    resolve_bot_vm_dir,
    vm_root,
)


@pytest.fixture(autouse=True)
def _isolate_vm_root(tmp_path, monkeypatch):
    monkeypatch.setenv(vm_registry.ENV_SANDBOX_VMS_DIR, str(tmp_path / "vms"))


def test_default_cap_is_eight():
    assert DEFAULT_VM_CAP == 8


def test_dir_is_stable_across_manager_rebuild():
    """A local bot keeps its work dir (and files) across a manager rebuild."""
    token = bind_bot_context(owner_key="u7", bot_id="notes_bot", conversation_id="c1")
    try:
        first = SandboxManager.from_config({"provider": "local"})
        first.write_file("notes.txt", "persisted across restart")
        first_dir = first.config.work_dir
    finally:
        reset_bot_context(token)

    # "Restart": a brand new manager for the same owner/bot resolves the same dir.
    token = bind_bot_context(owner_key="u7", bot_id="notes_bot", conversation_id="c2")
    try:
        second = SandboxManager.from_config({"provider": "local"})
        assert second.config.work_dir == first_dir
        assert second.read_file("notes.txt") == "persisted across restart"
    finally:
        reset_bot_context(token)


def test_explicit_work_dir_still_wins_over_vm():
    token = bind_bot_context(owner_key="u7", bot_id="notes_bot")
    try:
        manager = SandboxManager.from_config(
            {"provider": "local", "work_dir": "/tmp/swarm-explicit-workdir"}
        )
        assert manager.config.work_dir == "/tmp/swarm-explicit-workdir"
    finally:
        reset_bot_context(token)


def test_without_context_local_manager_keeps_legacy_cwd():
    assert current_bot_context() is None
    manager = SandboxManager.from_config({"provider": "local"})
    assert manager.config.work_dir == os.getcwd()


def test_cap_evicts_least_recently_used():
    root = vm_root()
    dirs = []
    for i in range(9):
        d = resolve_bot_vm_dir("u1", f"bot{i}", enforce=False)
        dirs.append(d)
        # Deterministic age: bot0 oldest … bot8 newest.
        stamp = root / ".stamps" / "u1" / f"bot{i}"
        os.utime(d, (1000 + i, 1000 + i))
        if stamp.exists():
            os.utime(stamp, (1000 + i, 1000 + i))

    removed = enforce_cap(8, owner_key="u1", active=dirs[-1])

    assert len(removed) == 1
    assert removed[0].name == "bot0"
    remaining = sorted(p.name for p in (root / "u1").iterdir() if p.is_dir())
    assert len(remaining) == 8
    assert "bot0" not in remaining


def test_active_vm_is_never_evicted():
    root = vm_root()
    dirs = []
    for i in range(9):
        d = resolve_bot_vm_dir("u2", f"bot{i}", enforce=False)
        dirs.append(d)
        stamp = root / ".stamps" / "u2" / f"bot{i}"
        os.utime(d, (1000 + i, 1000 + i))
        if stamp.exists():
            os.utime(stamp, (1000 + i, 1000 + i))

    # The oldest dir is the one actively executing: it must survive; bot1 goes.
    removed = enforce_cap(8, owner_key="u2", active=dirs[0])

    assert dirs[0].name not in {p.name for p in removed}
    assert dirs[0].is_dir()
    assert len(list((root / "u2").iterdir())) == 8


def test_cap_is_per_owner():
    for i in range(8):
        resolve_bot_vm_dir("uA", f"bot{i}", enforce=False)
        resolve_bot_vm_dir("uB", f"bot{i}", enforce=False)

    enforce_cap(8)  # global sweep: both owners already at cap → nothing evicted

    assert len(list((vm_root() / "uA").iterdir())) == 8
    assert len(list((vm_root() / "uB").iterdir())) == 8


def test_resolve_bot_vm_dir_sanitizes_traversal():
    root = vm_root().resolve()
    path = resolve_bot_vm_dir("../../evil", "../..\\escape")
    assert path.resolve().is_relative_to(root)
    # The literal parent directories are never created above the root.
    assert not (vm_root().parent / "evil").exists()


def test_bind_context_token_reset_has_no_leak():
    assert current_bot_context() is None
    token = bind_bot_context(owner_key="u1", bot_id="botA")
    assert current_bot_context().bot_id == "botA"
    try:
        raise RuntimeError("turn cancelled")
    except RuntimeError:
        pass
    finally:
        reset_bot_context(token)
    assert current_bot_context() is None
