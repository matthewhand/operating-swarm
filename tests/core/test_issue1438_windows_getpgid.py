"""#1438 — Windows CLI cancel must kill the child tree, not swallow AttributeError.

POSIX spawn is ``start_new_session`` and kill is ``os.killpg``.
Windows spawn is ``CREATE_NEW_PROCESS_GROUP`` and kill is ``taskkill /T /F``.
Platform is mocked on hosts that cannot run the other OS. The native Windows
tree-kill test runs in the windows-proc job (windows-latest). Ubuntu jobs skip it.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from swarm.core.cli_adapter import CliAdapter
from swarm.core.cli_models import _terminate as models_terminate
from swarm.core.cli_run_registry import (
    is_cli_run_running,
    register_cli_run,
    reset_cli_run_registry,
    terminate_cli_runs,
    terminate_process_group,
)
from swarm.core.proc import (
    CREATE_NEW_PROCESS_GROUP,
    group_id,
    kill_tree,
    spawn_kwargs,
    termination_signals,
)
from swarm.core.process_group import (
    _configure_kernel32,
    _nt_pid_running,
    get_pgid,
    kill_pg,
    nt_pid_alive,
    terminate_signals,
)

PY = sys.executable
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_cli_run_registry()
    yield
    reset_cli_run_registry()


@pytest.fixture
def no_posix_pgroup(monkeypatch):
    """Hide Unix process-group APIs the way Windows does."""
    monkeypatch.delattr(os, "getpgid", raising=False)
    monkeypatch.delattr(os, "killpg", raising=False)


class _FakeProc:
    def __init__(self, pid: int = 5150) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.wait_calls = 0

    def wait(self):
        async def _wait():
            self.wait_calls += 1
            self.returncode = -9
            return self.returncode

        return _wait()


class _Done:
    def __init__(self, code: int = 0, err: bytes = b"") -> None:
        self.returncode = code
        self.stderr = err


def _fake_taskkill(calls: list[list[str]], code: int = 0):
    def _run(argv, check=False, capture_output=True, **_kwargs):  # noqa: ARG001
        calls.append(list(argv))
        return _Done(code)

    return _run


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    if pid <= 1:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return True
        time.sleep(0.05)
    return False


def test_posix_spawn_kwargs_start_new_session(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert spawn_kwargs() == {"start_new_session": True}


def test_posix_kill_tree_uses_killpg_not_os_kill(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    killed: list[tuple[int, int]] = []
    os_kills: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "getpgid", lambda _pid: 77, raising=False)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append((int(pgid), int(sig))), raising=False)
    monkeypatch.setattr(os, "kill", lambda pid, sig: os_kills.append((int(pid), int(sig))))
    kill_tree(77, signal.SIGTERM)
    assert killed == [(77, int(signal.SIGTERM))]
    assert os_kills == []


def test_posix_kill_tree_reaps_grandchild(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX killpg tree-kill runs on the Linux CI job")
    grand_path = tmp_path / "grand.pid"
    code = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(grand_path)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(120)\n"
    )
    parent = subprocess.Popen(
        [PY, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **spawn_kwargs(),
    )
    gpid = 0
    try:
        assert os.getpgid(parent.pid) == parent.pid
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not gpid:
            if grand_path.exists():
                raw = grand_path.read_text(encoding="utf-8").strip()
                if raw.isdigit():
                    gpid = int(raw)
                    break
            time.sleep(0.05)
        assert gpid > 1
        kill_tree(parent.pid, signal.SIGKILL)
        # Our own child stays a zombie until wait; os.kill(pid, 0) still succeeds then.
        parent.wait(timeout=5)
        assert parent.returncode is not None
        assert _wait_dead(gpid)
    finally:
        if parent.poll() is None:
            try:
                os.killpg(os.getpgid(parent.pid), signal.SIGKILL)
            except OSError:
                parent.kill()
        parent.wait(timeout=5)
        if gpid > 1:
            with contextlib.suppress(OSError):
                os.kill(gpid, signal.SIGKILL)


def test_windows_spawn_uses_new_process_group(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(subprocess, "CREATE_NEW_PROCESS_GROUP", raising=False)
    kwargs = spawn_kwargs()
    assert kwargs == {"creationflags": CREATE_NEW_PROCESS_GROUP}
    assert kwargs["creationflags"] == 0x00000200
    assert "start_new_session" not in kwargs


def test_windows_kill_tree_taskkill_does_not_touch_posix(monkeypatch):
    """The old fix deleted getpgid and called os.kill. Cancel must taskkill the tree."""
    monkeypatch.setattr(sys, "platform", "win32")

    def _boom(*_args, **_kwargs):
        raise AssertionError("POSIX process-group API used on the Windows path")

    monkeypatch.setattr(os, "getpgid", _boom, raising=False)
    monkeypatch.setattr(os, "killpg", _boom, raising=False)
    monkeypatch.setattr(os, "kill", _boom)
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_taskkill(calls))
    kill_tree(4242, signal.SIGTERM)
    assert calls == [["taskkill", "/T", "/F", "/PID", "4242"]]


def test_windows_taskkill_already_gone_is_not_an_error(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", _fake_taskkill([], code=128))
    kill_tree(4242)


def test_windows_taskkill_failure_raises(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", _fake_taskkill([], code=1))
    with pytest.raises(OSError):
        kill_tree(4242)


def test_windows_taskkill_timeout_raises(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    def _hang(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="taskkill", timeout=10)

    monkeypatch.setattr(subprocess, "run", _hang)
    with pytest.raises(OSError, match="timed out"):
        kill_tree(4242)


def test_refuses_pid_le_1():
    with pytest.raises(ProcessLookupError):
        kill_tree(1)


def test_windows_signals_are_one_taskkill(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert termination_signals() == (int(signal.SIGTERM),)


def test_terminate_signals_omits_missing_sigkill(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delattr(signal, "SIGKILL", raising=False)
    assert terminate_signals() == (int(signal.SIGTERM),)


def test_windows_group_id_without_getpgid(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(os, "getpgid", raising=False)
    pid = os.getpid()
    assert group_id(pid) == pid
    assert get_pgid(pid) == pid
    token = register_cli_run(user_key="u0", agent_id="cli_agent", pid=pid)
    assert token


def test_facade_kill_pg_is_taskkill_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_taskkill(calls))
    kill_pg(99, signal.SIGTERM)
    assert calls == [["taskkill", "/T", "/F", "/PID", "99"]]


def test_registry_terminate_on_windows_taskkill_tree(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("swarm.core.cli_run_registry.TERM_GRACE", 0.0)
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_taskkill(calls))
    host_spawn = (
        {"creationflags": CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    child = subprocess.Popen(
        [PY, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **host_spawn,
    )
    try:
        token = register_cli_run(user_key="u0", agent_id="cli_agent", pid=child.pid)
        assert token
        assert terminate_cli_runs("u0", "cli_agent") == "terminated"
        assert calls == [["taskkill", "/T", "/F", "/PID", str(child.pid)]]
        assert terminate_process_group(child.pid, child.pid) is True
        assert calls[-1] == ["taskkill", "/T", "/F", "/PID", str(child.pid)]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.asyncio
async def test_adapter_cancel_on_windows_taskkill_tree(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_taskkill(calls))
    proc = _FakeProc(pid=6100)
    await CliAdapter._terminate(proc)
    assert calls == [["taskkill", "/T", "/F", "/PID", "6100"]]
    assert proc.returncode is not None


class _FakeKernel:
    """Stand-in for kernel32 OpenProcess / WaitForSingleObject / CloseHandle.

    Values are wait results: ``0x102`` still running, ``0`` exited (even when
    the exit code would be 259 / ``STILL_ACTIVE``), ``0xFFFFFFFF`` wait failed.
    A pid that is absent fails ``OpenProcess``.
    """

    def __init__(self, waits: dict[int, int]):
        self.waits = waits
        self.closed: list[int] = []
        self.opened: list[int] = []

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x00100000
        assert inherit is False
        self.opened.append(pid)
        if pid not in self.waits:
            return 0
        return pid

    def WaitForSingleObject(self, handle, timeout):
        assert timeout == 0
        return self.waits[int(handle)]

    def CloseHandle(self, handle):
        self.closed.append(int(handle))
        return 1


def test_nt_pid_running_uses_wait_and_closes_handle():
    # 7 has exited (WAIT_OBJECT_0), including a child whose code is 259.
    # 8 is WAIT_FAILED. 99 does not open.
    kernel = _FakeKernel({42: 0x102, 7: 0, 8: 0xFFFFFFFF})
    assert _nt_pid_running(42, kernel=kernel) is True
    assert _nt_pid_running(7, kernel=kernel) is False
    assert _nt_pid_running(8, kernel=kernel) is False
    assert kernel.closed == [42, 7, 8]
    assert _nt_pid_running(99, kernel=kernel) is False
    assert 99 not in kernel.closed


def test_nt_pid_running_closes_handle_when_wait_raises():
    class _Boom(_FakeKernel):
        def WaitForSingleObject(self, _handle, _timeout):
            raise OSError("wait failed")

    kernel = _Boom({4: 0x102})
    with pytest.raises(OSError, match="wait failed"):
        _nt_pid_running(4, kernel=kernel)
    assert kernel.closed == [4]


def test_configure_kernel32_binds_wait_prototypes():
    from ctypes import wintypes

    class _Slot:
        def __init__(self):
            self.argtypes = None
            self.restype = None

    class _Bare:
        def __init__(self):
            self.OpenProcess = _Slot()
            self.WaitForSingleObject = _Slot()
            self.CloseHandle = _Slot()

    kernel = _Bare()
    assert _configure_kernel32(kernel) is kernel
    assert kernel.OpenProcess.argtypes == (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    assert kernel.OpenProcess.restype is wintypes.HANDLE
    assert kernel.WaitForSingleObject.argtypes == (wintypes.HANDLE, wintypes.DWORD)
    assert kernel.WaitForSingleObject.restype is wintypes.DWORD
    assert kernel.CloseHandle.argtypes == (wintypes.HANDLE,)
    assert kernel.CloseHandle.restype is wintypes.BOOL
    _configure_kernel32(kernel)
    assert kernel.WaitForSingleObject.restype is wintypes.DWORD


def test_nt_pid_alive_follows_wait_and_skips_non_positive(monkeypatch):
    monkeypatch.setattr(
        "swarm.core.process_group._nt_pid_running",
        lambda pid, _kernel=None: pid == 7,
    )
    assert nt_pid_alive(7) is True
    assert nt_pid_alive(8) is False
    assert nt_pid_alive(9) is False
    assert nt_pid_alive(0) is False
    assert nt_pid_alive(-1) is False


def test_windows_status_poll_does_not_block_or_signal(monkeypatch, no_posix_pgroup):
    """Rail list/terminate must not waitpid or os.kill(pid, 0) on Windows.

    Once register succeeds without getpgid, list_cli_runs probes liveness.
    os.waitpid ignores WNOHANG on Windows (blocks). os.kill(pid, 0) is
    CTRL_C_EVENT. Either hides the run or never reaches Terminate.
    """
    assert no_posix_pgroup is None
    assert not hasattr(os, "getpgid")
    # Windows is `sys.platform`, not merely a missing getpgid. Leaving the
    # platform as linux makes group_id call the deleted os.getpgid.
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("swarm.core.cli_run_registry.TERM_GRACE", 0.0)
    alive = {"on": True}
    calls: list[tuple] = []

    def waitpid(pid, opt):
        calls.append(("waitpid", pid, opt))
        return (0, 0)

    def kill(pid, sig):
        calls.append(("kill", pid, sig))
        alive["on"] = False

    monkeypatch.setattr(os, "waitpid", waitpid)
    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(
        "swarm.core.cli_run_registry.nt_pid_alive",
        lambda _pid: alive["on"],
    )

    pid = 424242
    assert register_cli_run(
        user_key="u0",
        agent_id="cli_agent",
        pid=pid,
        pgid=pid,
    )
    assert is_cli_run_running("u0", "cli_agent") is True
    assert calls == []

    taskkills: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_taskkill(taskkills))
    assert terminate_cli_runs("u0", "cli_agent") == "terminated"
    assert taskkills == [["taskkill", "/T", "/F", "/PID", str(pid)]]
    assert not any(item[0] == "waitpid" for item in calls)
    assert not any(item[0] == "kill" and item[2] == 0 for item in calls)


@pytest.mark.asyncio
async def test_models_terminate_on_windows_taskkill_tree(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_taskkill(calls))
    proc = _FakeProc(pid=6101)
    await models_terminate(proc, grace=0.1)
    assert calls == [["taskkill", "/T", "/F", "/PID", "6101"]]
    assert proc.returncode is not None


@pytest.mark.asyncio
async def test_adapter_terminate_on_posix_uses_killpg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "getpgid", lambda pid: int(pid), raising=False)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append((int(pgid), int(sig))), raising=False)
    proc = _FakeProc(pid=6102)
    await CliAdapter._terminate(proc)
    assert killed == [(6102, int(signal.SIGTERM))]


def test_spawn_sites_delegate_to_helper():
    for rel, minimum in (
        ("src/swarm/core/cli_adapter.py", 2),
        ("src/swarm/core/cli_models.py", 1),
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "start_new_session" not in text, rel
        assert text.count("spawn_kwargs()") >= minimum, rel


def test_no_direct_posix_process_calls_outside_helper():
    path = ROOT / "scripts" / "lint_no_direct_pgroup.py"
    spec = importlib.util.spec_from_file_location("lint_no_direct_pgroup", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hits = module.violations(ROOT)
    assert hits == []


@pytest.mark.skipif(sys.platform != "win32", reason="native taskkill tree-kill")
def test_native_windows_cancel_kills_child_tree(tmp_path):
    grand_path = tmp_path / "grand.pid"
    code = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(grand_path)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(120)\n"
    )
    parent = subprocess.Popen(
        [PY, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **spawn_kwargs(),
    )
    gpid = 0
    try:
        assert spawn_kwargs()["creationflags"] == int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP)
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not gpid:
            if grand_path.exists():
                raw = grand_path.read_text(encoding="utf-8").strip()
                if raw.isdigit():
                    gpid = int(raw)
                    break
            time.sleep(0.05)
        assert gpid > 1
        kill_tree(parent.pid)
        parent.wait(timeout=5)
        assert parent.returncode is not None
        assert _wait_dead(gpid)
    finally:
        if parent.poll() is None:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(parent.pid)],
                check=False,
                capture_output=True,
            )
            parent.wait(timeout=5)
        else:
            parent.wait(timeout=5)
