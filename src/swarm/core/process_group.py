"""POSIX process-group helpers with a Windows-safe fallback (#1438).

Spawn and tree-kill live in :mod:`swarm.core.proc` (POSIX ``killpg``, Windows
``taskkill /T /F``). This module keeps those names and the Windows liveness
check. Liveness cannot use ``os.waitpid`` (``WNOHANG`` is ignored, so the
call blocks) or ``os.kill(pid, 0)`` (that value is ``CTRL_C_EVENT``).
``GetExitCodeProcess`` is also the wrong probe: exit code 259 is
``STILL_ACTIVE`` and a real exit code, so a finished child stays "running".
"""

from __future__ import annotations

import threading

from swarm.core.proc import PROCESS_GROUP_ERRORS
from swarm.core.proc import group_id as get_pgid
from swarm.core.proc import kill_tree as kill_pg
from swarm.core.proc import termination_signals as terminate_signals

__all__ = [
    "PROCESS_GROUP_ERRORS",
    "get_pgid",
    "kill_pg",
    "nt_pid_alive",
    "terminate_signals",
]

# WaitForSingleObject needs SYNCHRONIZE. PROCESS_QUERY_LIMITED_INFORMATION
# can read an exit code, but cannot wait, and 259 is ambiguous.
_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102

_KERNEL32 = None
_KERNEL_LOCK = threading.Lock()


def nt_pid_alive(pid: int) -> bool:
    """Whether *pid* is running, without signalling it.

    Windows only. A rail status poll must not block in ``os.waitpid`` or send
    ``CTRL_C_EVENT`` via ``os.kill(pid, 0)``.
    """
    if not pid or int(pid) <= 0:
        return False
    return _nt_pid_running(int(pid))


def _configure_kernel32(kernel):
    """Bind Win32 prototypes once.

    ``ctypes.WinDLL`` caches ``kernel32``. Rebinding ``argtypes`` on every
    status poll races another thread's call and can truncate a ``HANDLE``.
    """
    from ctypes import wintypes

    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _kernel32():
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    with _KERNEL_LOCK:
        if _KERNEL32 is None:
            import ctypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            _configure_kernel32(kernel)
            _KERNEL32 = kernel
    return _KERNEL32


def _nt_pid_running(pid: int, kernel=None) -> bool:
    """True when a zero-timeout wait on *pid* times out.

    ``kernel`` is the WinDLL stand-in tests pass in. Production loads kernel32.
    ``WAIT_OBJECT_0`` means the process has exited, including when its exit
    code is 259 (``STILL_ACTIVE``). ``WAIT_TIMEOUT`` means it is still running.
    """
    if kernel is None:
        kernel = _kernel32()
    handle = kernel.OpenProcess(_SYNCHRONIZE, False, int(pid))
    if not handle:
        return False
    try:
        waited = kernel.WaitForSingleObject(handle, 0)
        return int(waited) == _WAIT_TIMEOUT
    finally:
        kernel.CloseHandle(handle)
