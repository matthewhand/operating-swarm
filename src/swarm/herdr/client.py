"""Small ``herdr`` CLI wrapper (REQ-21).

Prefers the official ``herdr`` binary. Does **not** invent a socket protocol
or extra flags — see https://herdr.dev/docs/cli-reference/ and
https://herdr.dev/docs/how-to-work/.

Argv rules
----------
* Default (localhost): ``herdr workspace list`` — no ``--remote``.
* Optional remote: ``herdr --remote <value> workspace list`` (and every other
  command). ``value`` is an operator string such as ``you@gpu-box``,
  ``workbox``, or ``ssh://you@server:2222``. Empty/omitted = localhost.
* ``herdr agent prompt <TARGET> <TEXT>`` is the proven shape
  (``herdr agent prompt w3:p1 HERDR_PING_OK`` → JSON ``type: agent_prompted``).
  TEXT is **one** argv element. Unquoted TEXT is the quoting bug that made
  herdr report ``unknown option: with``.

Blocked / working
-----------------
* If the agent is **blocked**, submit is rejected (``HerdrBlockedError``) and
  ``agent prompt`` is not sent. Herdr itself also returns ``agent_blocked``
  without sending input; we preflight via ``agent get`` and map that CLI error.
* If the agent is already **working**, ``--wait`` may complete when *that*
  in-flight turn finishes — it does not track a newly submitted turn. Documented
  here and in ``docs/HERDR.md``. Do not collide tests with a live WORKING grok
  pane; mock the CLI.

Wait-until
----------
``wait_until(target, status)`` is ``herdr agent wait <TARGET> --until STATUS``
for ``idle`` | ``working`` | ``blocked`` | ``done``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from swarm.services.secure_subprocess import execute_command_safe

logger = logging.getLogger(__name__)

WAIT_UNTIL_STATES = frozenset({"idle", "working", "blocked", "done"})

# Herdr's own default match set (`herdr agent wait --help`): "Without --until,
# matches idle, done, or blocked." A turn that finishes settles in ``done`` — it
# never returns to ``idle`` — so waiting on ``idle`` alone can only expire (#470).
WAIT_UNTIL_STOPPED: tuple[str, ...] = ("idle", "done", "blocked")
_KNOWN_STATES = WAIT_UNTIL_STATES | {"unknown"}
MEMBER_KIND = "herdr"
AGENT_PROMPTED = "agent_prompted"

# Subprocess timeout for short list/read/get calls (seconds). Prompt --wait and
# agent wait use herdr's own --timeout MS and a larger process cap.
_DEFAULT_PROCESS_TIMEOUT = 30


class HerdrError(Exception):
    """Base error for the Herdr CLI wrapper."""


class HerdrCLIError(HerdrError):
    """The ``herdr`` process failed or is not installed."""

    def __init__(self, message: str, *, argv: list[str] | None = None, result: subprocess.CompletedProcess | None = None):
        super().__init__(message)
        self.argv = argv or []
        self.result = result


class HerdrBlockedError(HerdrError):
    """Submit rejected because the Herdr agent is blocked (approval/question UI)."""

    def __init__(self, target: str, message: str = ""):
        super().__init__(message or f"Herdr agent {target!r} is blocked; submit rejected.")
        self.target = target


class HerdrAgentMissingError(HerdrCLIError):
    """The targeted pane/agent no longer exists (#1144).

    The CLI answers ``{"error": {"code": "agent_not_found", ...}}`` —
    carried historically as an opaque CLIError whose message dumped raw JSON
    into the chat. Distinguished so the send path can offer a rebind instead.
    """

    def __init__(self, target: str, message: str = "", *, argv: list[str] | None = None, result: subprocess.CompletedProcess | None = None):
        super().__init__(message or f"Herdr agent {target!r} not found", argv=argv, result=result)
        self.target = target


Runner = Callable[..., subprocess.CompletedProcess]


def _default_runner(
    argv: list[str],
    *,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Run argv via ``execute_command_safe`` (shell=False)."""
    return execute_command_safe(argv, timeout=timeout, capture_output=True, text=True, check=False)


def _looks_like_agent_blocked(payload: Any, stderr: str = "", stdout: str = "") -> bool:
    blob = " ".join(
        part
        for part in (
            stderr or "",
            stdout or "",
            json.dumps(payload) if isinstance(payload, dict | list) else str(payload or ""),
        )
        if part
    ).lower()
    return "agent_blocked" in blob or '"code": "agent_blocked"' in blob


def _looks_like_agent_missing(payload: Any, stderr: str = "", stdout: str = "") -> bool:
    """#1144: the CLI reports ``agent_not_found`` for deleted panes."""
    blob = " ".join(
        part
        for part in (
            stderr or "",
            stdout or "",
            json.dumps(payload) if isinstance(payload, dict | list) else str(payload or ""),
        )
        if part
    ).lower()
    return "agent_not_found" in blob


def extract_prompt_type(payload: Any) -> str | None:
    """Return Herdr JSON ``type`` (live prompt succeeds as ``agent_prompted``)."""
    if isinstance(payload, Mapping):
        raw = payload.get("type")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        result = payload.get("result")
        if isinstance(result, Mapping):
            raw = result.get("type")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _as_records(payload: Any, *keys: str) -> list[Any]:
    """Pull a list of records out of typical herdr JSON wrappers."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for wrap in ("result", "data"):
        inner = payload.get(wrap)
        if inner is not None and inner is not payload:
            found = _as_records(inner, *keys)
            if found:
                return found
    return []


def _record_target(record: Mapping[str, Any], *, pane_first: bool) -> str:
    keys = (
        ("pane_id", "pane", "target", "name", "id", "agent_id")
        if pane_first
        else ("workspace_id", "id", "name", "label", "target")
    )
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return ""


def members_from_agent_list(
    payload: Any,
    *,
    remote: str = "",
    workspace_labels: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Turn ``herdr agent list`` JSON into addable members (kind=herdr).

    ``name`` stays the routing target (pane id like ``w3:p5``) that
    ``herdr agent prompt`` needs; ``display`` becomes the friendly
    ``Agent (Workspace)`` label for the UI (#787). ``workspace_labels`` maps
    workspace ids to their human labels from ``herdr workspace list``.
    """
    labels = workspace_labels or {}
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in _as_records(payload, "agents", "items"):
        if not isinstance(record, Mapping):
            continue
        target = _record_target(record, pane_first=True)
        if not target or target in seen:
            continue
        seen.add(target)
        state = extract_agent_state(record)
        raw_name = record.get("agent") or record.get("name")
        agent_name = raw_name.strip() if isinstance(raw_name, str) else ""
        workspace = str(labels.get(str(record.get("workspace_id", ""))) or "")
        if agent_name and workspace:
            display = f"{agent_name.capitalize()} ({workspace})"
        else:
            display = agent_name.capitalize() if agent_name else ""
        # #728: keep the human label when the CLI id is a pane id, so
        # ambiguity errors can say "w3:p1 (grok)" instead of two ids.
        # Case-insensitive compare: display 'Grok' for target 'grok' adds nothing.
        members.append(
            {
                "kind": MEMBER_KIND,
                "name": target,
                "display": display if display and display.lower() != target.lower() else "",
                "agent": agent_name,
                "workspace": workspace,
                "remote": (remote or "").strip(),
                "source": "agent",
                "state": state,
                "object": "herdr.member",
            }
        )
    return members


def members_from_workspace_list(payload: Any, *, remote: str = "") -> list[dict[str, Any]]:
    """Turn ``herdr workspace list`` JSON into addable members (kind=herdr)."""
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in _as_records(payload, "workspaces", "items"):
        if not isinstance(record, Mapping):
            continue
        target = _record_target(record, pane_first=False)
        if not target or target in seen:
            continue
        seen.add(target)
        raw_label = record.get("name") or record.get("label")
        display = raw_label.strip() if isinstance(raw_label, str) else ""
        members.append(
            {
                "kind": MEMBER_KIND,
                "name": target,
                "display": display if display and display != target else "",
                "remote": (remote or "").strip(),
                "source": "workspace",
                "state": None,
                "object": "herdr.member",
            }
        )
    return members


def extract_state_change_seq(payload: Any) -> int | None:
    """Best-effort ``state_change_seq`` from ``herdr agent get`` JSON.

    Used as a turn-progress marker (#470): the counter advances when a pane
    changes state, so comparing it across a send distinguishes "the agent ran"
    from "nothing happened" without trusting stale pane text.
    """
    if payload is None:
        return None
    if isinstance(payload, list):
        for item in payload:
            found = extract_state_change_seq(item)
            if found is not None:
                return found
        return None
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("state_change_seq")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    for key in ("result", "agent", "data", "pane"):
        if key in payload:
            found = extract_state_change_seq(payload[key])
            if found is not None:
                return found
    return None


def extract_agent_state(payload: Any) -> str | None:
    """Best-effort lifecycle state from ``herdr agent get`` / ``agent list`` JSON."""
    if payload is None:
        return None
    if isinstance(payload, str):
        value = payload.strip().lower()
        return value if value in _KNOWN_STATES else None
    if isinstance(payload, list):
        for item in payload:
            found = extract_agent_state(item)
            if found:
                return found
        return None
    if not isinstance(payload, Mapping):
        return None

    # #1189: the herdr CLI's own field is ``agent_status`` (agent get / agent
    # list JSON) — recognized alongside the looser aliases so best-effort
    # extraction actually sees the live payload's state.
    for key in ("state", "status", "agent_state", "agent_status"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip().lower() in _KNOWN_STATES:
            return raw.strip().lower()

    for key in ("result", "agent", "data", "pane"):
        if key in payload:
            found = extract_agent_state(payload[key])
            if found:
                return found
    return None


def _parse_stdout(stdout: str) -> Any:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return stdout


class HerdrClient:
    """Wrap ``herdr`` as argv lists. Empty ``remote`` means localhost (no flag).

    Optional ``transport`` runs those argv lists on another host (REQ-100 SSH
    hop). When set, ``--remote`` is omitted — the hop *is* the remote.
    """

    def __init__(
        self,
        remote: str = "",
        *,
        herdr_bin: str | None = None,
        runner: Runner | None = None,
        transport: Any = None,
    ) -> None:
        self.remote = (remote or "").strip()
        self.herdr_bin = herdr_bin or os.environ.get("HERDR_BIN") or "herdr"
        self._runner = runner or _default_runner
        self._transport = transport

    @classmethod
    def from_row(cls, row: Any, **kwargs: Any) -> HerdrClient:
        """Build a client from a ``HerdrAgent`` ORM row (or any ``remote`` object)."""
        remote = getattr(row, "remote", "") or ""
        return cls(remote=remote, **kwargs)

    @classmethod
    def from_remote_config(cls, config: Mapping[str, Any] | None = None, **kwargs: Any) -> HerdrClient:
        """Build from persisted ``remotes.herdr``. Missing config is an error.

        Local Herdr omits SSH and ``--remote``. Remote Herdr SSHs to the Herdr
        host, then runs ``herdr`` there (REQ-100). A leftover non-localhost
        HTTP base without SSH fields is a clear error — not a guessed host.
        """
        from swarm.core import remotes as remotes_core
        from swarm.herdr.remote import herdr_client_from_spec

        spec = remotes_core.load_remote("herdr", config if isinstance(config, dict) else None)
        return herdr_client_from_spec(spec, **kwargs)

    def build_argv(self, *parts: str) -> list[str]:
        """``herdr [--remote VALUE] …parts``. Never shell-splits TEXT."""
        argv = [self.herdr_bin]
        if self.remote:
            argv.extend(["--remote", self.remote])
        argv.extend(parts)
        return argv

    def _invoke(
        self,
        argv: list[str],
        *,
        timeout: int | None = _DEFAULT_PROCESS_TIMEOUT,
    ) -> tuple[subprocess.CompletedProcess, Any]:
        logger.debug("herdr argv: %s", argv)
        try:
            if self._transport is not None:
                result = self._transport.run(argv, timeout=timeout)
            else:
                result = self._runner(argv, timeout=timeout)
        except FileNotFoundError as exc:
            raise HerdrCLIError(
                "herdr CLI not found on PATH. Install Herdr or mock the client "
                "in CI (cloud runners must not talk to a live TUI).",
                argv=argv,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise HerdrCLIError(f"herdr timed out: {argv}", argv=argv) from exc

        parsed = _parse_stdout(getattr(result, "stdout", "") or "")
        if result.returncode != 0:
            stderr = getattr(result, "stderr", "") or ""
            stdout = getattr(result, "stdout", "") or ""
            if _looks_like_agent_blocked(parsed, stderr=stderr, stdout=stdout):
                target = ""
                if "prompt" in argv:
                    try:
                        target = argv[argv.index("prompt") + 1]
                    except (ValueError, IndexError):
                        target = ""
                raise HerdrBlockedError(target)
            if _looks_like_agent_missing(parsed, stderr=stderr, stdout=stdout):
                target = ""
                for flag in ("get", "prompt", "read", "wait"):
                    if flag in argv:
                        try:
                            target = argv[argv.index(flag) + 1]
                            break
                        except (ValueError, IndexError):
                            target = ""
                raise HerdrAgentMissingError(target, argv=argv, result=result)
            detail = (stderr or stdout or f"exit {result.returncode}").strip()
            raise HerdrCLIError(detail, argv=argv, result=result)
        return result, parsed

    def workspace_list(self) -> Any:
        """``herdr workspace list``."""
        _, parsed = self._invoke(self.build_argv("workspace", "list"))
        return parsed

    def agent_list(self) -> Any:
        """``herdr agent list``."""
        _, parsed = self._invoke(self.build_argv("agent", "list"))
        return parsed

    def agent_get(self, target: str) -> Any:
        """``herdr agent get <TARGET>`` (used to preflight blocked/working)."""
        if not (target or "").strip():
            raise ValueError("agent target is required")
        _, parsed = self._invoke(self.build_argv("agent", "get", target))
        return parsed

    def agent_read(
        self,
        target: str,
        *,
        source: str | None = None,
        lines: int | None = None,
        fmt: str | None = None,
    ) -> Any:
        """``herdr agent read <TARGET>`` with documented optional flags only."""
        if not (target or "").strip():
            raise ValueError("agent target is required")
        parts: list[str] = ["agent", "read", target]
        if source:
            parts.extend(["--source", source])
        if lines is not None:
            parts.extend(["--lines", str(int(lines))])
        if fmt:
            parts.extend(["--format", fmt])
        _, parsed = self._invoke(self.build_argv(*parts))
        return parsed

    def agent_prompt(
        self,
        target: str,
        text: str,
        *,
        wait: bool = False,
        until: str | Sequence[str] | None = None,
        timeout_ms: int | None = None,
        check_blocked: bool = False,
    ) -> Any:
        """``herdr agent prompt <TARGET> <TEXT>`` — TEXT is one argv element.

        Proven on-host shape: ``herdr agent prompt w3:p1 HERDR_PING_OK`` returns
        JSON ``type: agent_prompted``. Do not shell-split TEXT.

        When ``check_blocked`` is true, ``agent get`` runs first and a blocked
        pane rejects submit. Default is false so the prompt argv matches the
        live one-shot. Herdr itself still returns ``agent_blocked`` without
        sending if the pane is blocked; we map that to ``HerdrBlockedError``.

        ``wait=True`` maps to ``--wait``. If the agent is already working, that
        wait may observe the current turn finishing rather than a new turn.

        ``until`` accepts one state or several; prefer :data:`WAIT_UNTIL_STOPPED`
        so a turn that settles in ``done`` is matched instead of expiring (#470).
        """
        if not (target or "").strip():
            raise ValueError("agent target is required")
        if text is None:
            raise ValueError("prompt text is required")
        # A single state or several (herdr accepts repeated --until). Pass the
        # stopped set to match a turn that ends in ``done`` as well (#470).
        until_states: tuple[str, ...] = ()
        if isinstance(until, str):
            until_states = (until,) if until else ()
        elif until is not None:
            until_states = tuple(str(item) for item in until if item)
        for state in until_states:
            if state not in WAIT_UNTIL_STATES:
                raise ValueError(f"until must be one of {sorted(WAIT_UNTIL_STATES)}")
        if until_states and not wait:
            raise ValueError("--until requires --wait (herdr rejects until without wait)")

        if check_blocked:
            state = extract_agent_state(self.agent_get(target))
            if state == "blocked":
                raise HerdrBlockedError(target)

        parts: list[str] = ["agent", "prompt", target, text]
        if wait:
            parts.append("--wait")
        for state in until_states:
            parts.extend(["--until", state])
        if timeout_ms is not None:
            parts.extend(["--timeout", str(int(timeout_ms))])

        process_timeout = None
        if timeout_ms is not None:
            process_timeout = max(_DEFAULT_PROCESS_TIMEOUT, int(timeout_ms / 1000) + 5)
        elif wait:
            process_timeout = None

        _, parsed = self._invoke(self.build_argv(*parts), timeout=process_timeout)
        return parsed

    def discover_members(self) -> list[dict[str, Any]]:
        """``herdr agent list`` + ``herdr workspace list`` as addable members.

        Each item is ``kind=herdr`` with ``remote`` empty when this client is
        localhost (no ``--remote``). Teams/sidepane persist chosen rows via
        ``POST /v1/herdr-agents/``.
        """
        workspaces = members_from_workspace_list(self.workspace_list(), remote=self.remote)
        labels = {
            item["name"]: item.get("display") or item["name"]
            for item in workspaces
            if item.get("name")
        }
        agents = members_from_agent_list(
            self.agent_list(),
            remote=self.remote,
            workspace_labels=labels,
        )
        seen = {item["name"] for item in agents}
        merged = list(agents)
        for item in workspaces:
            if item["name"] not in seen:
                merged.append(item)
                seen.add(item["name"])
        return merged

    def wait_until(
        self,
        target: str,
        status: str,
        *,
        timeout_ms: int | None = None,
    ) -> Any:
        """``herdr agent wait <TARGET> --until STATUS``.

        STATUS is one of idle | working | blocked | done. Standalone
        ``agent wait`` returns immediately when the current status already
        matches (herdr behavior).
        """
        if not (target or "").strip():
            raise ValueError("agent target is required")
        if status not in WAIT_UNTIL_STATES:
            raise ValueError(f"status must be one of {sorted(WAIT_UNTIL_STATES)}")
        parts: list[str] = ["agent", "wait", target, "--until", status]
        if timeout_ms is not None:
            parts.extend(["--timeout", str(int(timeout_ms))])
        process_timeout = None
        if timeout_ms is not None:
            process_timeout = max(_DEFAULT_PROCESS_TIMEOUT, int(timeout_ms / 1000) + 5)
        _, parsed = self._invoke(self.build_argv(*parts), timeout=process_timeout)
        return parsed

    def herdr_available(self) -> bool:
        """True when the ``herdr`` binary is on PATH (live hosts only)."""
        return shutil.which(self.herdr_bin) is not None
