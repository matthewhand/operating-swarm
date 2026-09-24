"""#1081 Phase 1 — headless Pi RPC driver (prototype).

Speaks the JSONL stdio protocol of ``pi --mode rpc``
(``@earendil-works/pi-coding-agent``) so a future ``PiAgentKind`` seat can
outsource the inference/tool loop to the Pi harness. Prototype status:
nothing routes to this yet and nothing can select it — see
``docs/adr/pi-harness-evaluation.md`` for the phased gate (Belay ToolGate
must cover Pi tool execution before any production use).

Protocol notes that shape this code (rpc.md, verified 2026-09-23):

- Strict LF framing on raw bytes. Do NOT use ``readline`` on text mode: it
  also splits on U+2028/U+2029, which are legal inside JSON strings.
- A ``prompt`` command's ``response`` (success) only means *accepted* —
  the run completes at the ``agent_settled`` event.
- ``message_update`` records carry ``assistantMessageEvent``; ``text_delta``
  events stream assistant text.
- Correlate commands to responses via the optional ``id`` we supply.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PiRpcError",
    "PiRpcProcessError",
    "PiSession",
    "chunk_events_from_records",
    "default_pi_command",
]

_DEFAULT_PROMPT_TIMEOUT_S = 600.0


class PiRpcError(RuntimeError):
    """A Pi RPC command failed or the protocol was violated."""


class PiRpcProcessError(PiRpcError):
    """The ``pi`` subprocess could not be started or died unexpectedly."""


def default_pi_command() -> list[str]:
    """Resolve the Pi CLI command, honouring ``SWARM_PI_BIN``.

    Kept dependency-free on purpose: the driver must import cleanly (and its
    tests must run hermetically) on hosts without Node/Pi installed.
    """
    override = os.environ.get("SWARM_PI_BIN", "").strip()
    if override:
        return override.split()
    found = shutil.which("pi")
    return [found] if found else []


@dataclass
class _PendingCall:
    event: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None


class PiSession:
    """One long-lived ``pi --mode rpc`` child process.

    A reader thread turns stdout into protocol records: responses resolve
    their pending call, session events fan out to ``on_event`` subscribers.
    """

    def __init__(
        self,
        command: list[str] | None = None,
        cwd: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        cmd = command if command is not None else default_pi_command()
        if not cmd:
            raise PiRpcProcessError(
                "Pi CLI not found. Install @earendil-works/pi-coding-agent "
                "(npm i -g @earendil-works/pi-coding-agent) or set SWARM_PI_BIN."
            )
        cmd = [*cmd, "--mode", "rpc", "--no-session"]
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:  # pragma: no cover - surfaced via message
            raise PiRpcProcessError(f"Failed to spawn Pi RPC process: {exc}") from exc
        self._on_event = on_event
        self._lock = threading.Lock()
        self._pending: dict[str, _PendingCall] = {}
        self._next_id = 0
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # -- protocol plumbing -------------------------------------------------

    def _read_loop(self) -> None:  # pragma: no cover - thread body
        assert self._proc.stdout is not None
        while True:
            # Strict LF framing on bytes (see module docstring).
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.strip(b"\r\n")
            if not line:
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue  # diagnostics belong on stderr, never parsed
            if not isinstance(record, dict):
                continue
            self._dispatch(record)

    def _dispatch(self, record: dict[str, Any]) -> None:
        if record.get("type") == "response":
            rid = record.get("id")
            with self._lock:
                pending = self._pending.pop(str(rid), None) if rid is not None else None
            if pending is not None:
                pending.response = record
                pending.event.set()
            return
        if self._on_event is not None:
            try:
                self._on_event(record)
            except Exception:  # noqa: BLE001 - subscriber bugs must not kill the reader
                pass

    def _call(self, command: dict[str, Any], timeout: float) -> dict[str, Any]:
        if self._proc.stdin is None or self._proc.poll() is not None:
            raise PiRpcProcessError("Pi RPC process is not running")
        rid = f"swarm-{self._next_id}"
        self._next_id += 1
        payload = {"id": rid, **command}
        pending = _PendingCall()
        with self._lock:
            self._pending[rid] = pending
        try:
            self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as exc:
            with self._lock:
                self._pending.pop(rid, None)
            raise PiRpcProcessError(f"Failed to write to Pi RPC stdin: {exc}") from exc
        if not pending.event.wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise PiRpcError(f"Pi RPC command timed out after {timeout}s: {command.get('type')}")
        response = pending.response or {}
        if not response.get("success", False):
            raise PiRpcError(
                f"Pi RPC command '{command.get('type')}' failed: {response.get('error', 'unknown')}"
            )
        return response

    # -- public surface ----------------------------------------------------

    def prompt(self, message: str, timeout: float = _DEFAULT_PROMPT_TIMEOUT_S) -> None:
        """Accept a prompt. Returns once *accepted* — stream events after."""
        self._call({"type": "prompt", "message": message}, timeout)

    def abort(self, timeout: float = 15.0) -> None:
        self._call({"type": "abort"}, timeout)

    def get_state(self, timeout: float = 15.0) -> dict[str, Any]:
        return self._call({"type": "get_state"}, timeout).get("data") or {}

    def set_model(self, provider: str, model_id: str, timeout: float = 15.0) -> None:
        self._call({"type": "set_model", "provider": provider, "id": model_id}, timeout)

    def compact(self, timeout: float = 120.0) -> None:
        self._call({"type": "compact"}, timeout)

    def close(self) -> None:
        """Close stdin for an orderly Pi shutdown, then reap the child."""
        if self._proc.stdin is not None and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - stubborn child
            self._proc.kill()
            self._proc.wait(timeout=5)


def chunk_events_from_records(records: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Map Pi session events onto Swarm's chunk vocabulary.

    One mapping table, in one place (ADR: "duplicated event models" risk):
    ``message_update``/``text_delta`` → ``{"type": "text", "text": …}``,
    ``agent_end`` → ``{"type": "end"}``. Unknown events are dropped here —
    richer mapping (tool events, compaction) lands with Phase 4, not before.
    """
    for record in records:
        if record.get("type") == "message_update":
            update = record.get("assistantMessageEvent") or {}
            if update.get("type") == "text_delta":
                text = update.get("delta", "")
                if text:
                    yield {"type": "text", "text": text}
        elif record.get("type") == "agent_end":
            yield {"type": "end"}
