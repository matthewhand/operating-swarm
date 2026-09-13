"""CLI agent adapter layer.

Turns an external, interactive agentic CLI (``claude``, ``gemini``, ``codex``,
``opencode`` ...) into an awaitable subagent that takes a prompt and returns
text. First turn is one-shot; a stored CLI session id (not an OS process
session, not a Django conversation id) can be replayed via ``resume_argv``.
This is the building block the CLI-fusion blueprints compose: each panelist
is a :class:`CliAdapter` driven entirely by configuration.

Design notes
------------
* **No shell.** The command is an argv list executed directly
  (``asyncio.create_subprocess_exec``); the prompt is passed as a discrete
  argument or on stdin, so there is no shell-injection surface. User text is
  still untrusted argv (C-H8): attach ``-p=``, feed stdin, or insert ``--``
  before a flag-shaped positional prompt. Token replacement does not rescan
  the prompt or workdir values.
* **Lifecycle.** Every launch runs in its own OS process *group*
  (``start_new_session=True``) so a hung or runaway agent — and any children it
  spawned — can be killed as a group on timeout, ``aclose``, cancel, or a rail
  **Terminate** (REQ-114). Kill is SIGTERM, then SIGKILL after ``TERM_GRACE``.
  That flag is not a CLI conversation session. CLI session ids (``--resume`` /
  ``--session``) are tracked separately on the chat thread (REQ-52). Chat runs
  register the child pid/pgid so Terminate only signals the swarm-spawned
  group — never an unrelated host process.
* **Config-driven.** Adapters are described as plain dicts (see
  :meth:`CliAdapter.from_config`) so adding a new CLI is a config edit, not code.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import os
import re
import signal
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel substituted in argv / cwd / env templates.
PROMPT_TOKEN = "{prompt}"
WORKDIR_TOKEN = "{workdir}"
# Injected into resume_argv when a stored CLI session id is replayed.
SESSION_TOKEN = "{session_id}"
# Flags that consume the next argv token as the prompt. A bare `-p --help`
# would otherwise treat the user text as a sibling flag; attach as `-p=`.
_PROMPT_VALUE_FLAGS = frozenset({"-p", "--print", "--prompt", "--single"})
# Boolean flags that contradict resume (--session / --resume / exec resume).
_DEFAULT_RESUME_STRIP = ("--no-session", "--continue")

DEFAULT_TIMEOUT = 180.0
# Grace period between SIGTERM and SIGKILL when reaping a timed-out agent.
TERM_GRACE = 5.0
# Auth probes should be quick; cap them well under a normal run timeout.
AUTH_TIMEOUT = 30.0

# Authentication states reported by discovery.
AUTH_AUTHENTICATED = "authenticated"
AUTH_UNAUTHENTICATED = "unauthenticated"
AUTH_UNKNOWN = "unknown"  # no auth_check configured, or the probe was inconclusive
AUTH_NOT_INSTALLED = "not_installed"

# Smoke-probe states: does the configured cmd actually *return* in print mode?
SMOKE_OK = "ok"                          # produced output and exited 0 in time
SMOKE_HANG = "hang"                      # timed out — almost always a wrong/missing
                                         # non-interactive flag (the CLI waited on input)
SMOKE_ERROR = "error"                    # ran but exited non-zero or produced nothing
SMOKE_NOT_INSTALLED = "not_installed"

# A trivial prompt for the smoke probe; cheap, but DOES invoke the model once.
DEFAULT_SMOKE_PROMPT = "Reply with the single word: OK"
# Smoke probes should be quick; cap well under a normal run.
SMOKE_TIMEOUT = 60.0


class CliAdapterError(Exception):
    """Raised for configuration/lookup problems (not runtime CLI failures)."""


@dataclass(frozen=True)
class CliAgentConfig:
    """Declarative description of how to run one agentic CLI one-shot.

    Attributes
    ----------
    name:
        Logical adapter name (e.g. ``"claude"``).
    cmd:
        argv list. Use ``{prompt}`` where the prompt should be injected and
        ``{workdir}`` for the working directory. Prefer ``-p={prompt}``, stdin,
        or a positional ``{prompt}`` after ``--``. A bare ``-p {prompt}`` is
        rewritten to ``-p=`` at launch. When ``prompt_mode == "stdin"``
        the ``{prompt}`` token is optional and the prompt is written to stdin.
    prompt_mode:
        ``"arg"`` (default) substitutes ``{prompt}`` into ``cmd``; ``"stdin"``
        feeds the prompt to the process's standard input.
    parse:
        ``"text"`` returns trimmed stdout. ``"json:<dotpath>"`` parses stdout as
        JSON and extracts the value at the dotted path (e.g. ``json:.result`` or
        ``json:.choices.0.message.content``). On parse failure the raw stdout is
        returned and ``CliResult.parse_error`` is set.
    cwd:
        Working directory template (``{workdir}`` allowed). When None, the
        per-call ``workdir`` is used, else the current directory.
    env:
        Extra environment variables (values may contain ``{prompt}``/``{workdir}``).
        Merged onto the parent environment.
    env_allowlist:
        When None (default), the child inherits the full parent environment —
        convenient, but every panelist then sees every API key. When set to a
        list of names, the child gets only those vars (plus a small essential
        set like ``PATH``/``HOME``) from the parent, isolating each CLI's
        secrets. ``env`` is always applied on top.
    timeout:
        Seconds before the agent (and its process group) is killed.
    mode:
        Informational label describing the safety posture (e.g. ``"readonly"``,
        ``"write"``). Not enforced here — it documents intent and is surfaced in
        results/logs.
    resume_argv:
        Extra argv pieces inserted when a stored CLI session id is replayed.
        Use ``{session_id}`` for the id. ``None`` (default) falls back to the
        catalog policy for ``name``. An empty list means this CLI cannot resume.
        Distinct from OS ``start_new_session=True`` (process-group kill).
    resume_insert:
        Index in the token-substituted argv at which ``resume_argv`` is inserted.
        ``None`` uses the catalog (default ``1`` — after the executable).
    session_id_paths:
        JSON dotted paths to try when capturing a session id from stdout
        (e.g. ``.session_id``). ``None`` uses the catalog plus common defaults.
    """

    name: str
    cmd: list[str]
    prompt_mode: str = "arg"
    parse: str = "text"
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    env_allowlist: list[str] | None = None
    timeout: float = DEFAULT_TIMEOUT
    mode: str = "default"
    auth_check: list[str] | None = None
    # Designate this agent as a CONSENSUS agent: calling it runs a panel instead
    # of a single inference. ``True`` => panel of all available CLIs; a list =>
    # a preferred whitelist (falls back to all-available if none match); a dict
    # ``{"panel": [...], "judge": "<cli>"}`` => explicit. None (default) => normal.
    consensus: bool | list[str] | dict[str, Any] | None = None
    # Swarm ``mcpServers`` to mount into grok/agy/claude when the CLI accepts it.
    mcp_servers: dict[str, Any] | None = None
    resume_argv: list[str] | None = None
    resume_insert: int | None = None
    session_id_paths: list[str] | None = None

    def __post_init__(self) -> None:
        if not self.cmd:
            raise CliAdapterError(f"CLI adapter '{self.name}' has an empty cmd")
        if self.prompt_mode not in ("arg", "stdin"):
            raise CliAdapterError(
                f"CLI adapter '{self.name}': prompt_mode must be 'arg' or 'stdin', "
                f"got {self.prompt_mode!r}"
            )
        if self.prompt_mode == "arg" and not any(PROMPT_TOKEN in part for part in self.cmd):
            raise CliAdapterError(
                f"CLI adapter '{self.name}': prompt_mode 'arg' requires a "
                f"'{PROMPT_TOKEN}' token somewhere in cmd"
            )
        if self.auth_check is not None and (
            not isinstance(self.auth_check, list)
            or not all(isinstance(p, str) for p in self.auth_check)
            or not self.auth_check
        ):
            raise CliAdapterError(
                f"CLI adapter '{self.name}': auth_check must be a non-empty list of strings"
            )
        if self.resume_argv is not None and (
            not isinstance(self.resume_argv, list)
            or not all(isinstance(p, str) for p in self.resume_argv)
        ):
            raise CliAdapterError(
                f"CLI adapter '{self.name}': resume_argv must be a list of strings"
            )
        if self.resume_insert is not None and (
            not isinstance(self.resume_insert, int) or self.resume_insert < 0
        ):
            raise CliAdapterError(
                f"CLI adapter '{self.name}': resume_insert must be an int >= 0"
            )
        if self.session_id_paths is not None and (
            not isinstance(self.session_id_paths, list)
            or not all(isinstance(p, str) for p in self.session_id_paths)
        ):
            raise CliAdapterError(
                f"CLI adapter '{self.name}': session_id_paths must be a list of strings"
            )


@dataclass
class CliResult:
    """Outcome of a single CLI agent invocation."""

    name: str
    ok: bool
    text: str
    returncode: int | None = None
    duration: float = 0.0
    timed_out: bool = False
    parse_error: str | None = None
    error: str | None = None
    stderr: str = ""
    session_id: str | None = None
    # True when the user stopped this run via rail Terminate (REQ-114).
    terminated: bool = False


@dataclass
class SmokeResult:
    """Outcome of a non-interactive smoke probe (see :meth:`CliAdapter.smoke_check`)."""

    name: str
    status: str
    detail: str = ""
    duration: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == SMOKE_OK

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "duration": round(self.duration, 3),
        }


@dataclass
class CliStreamChunk:
    """One event from :meth:`CliAdapter.stream_run`.

    Either an incremental output delta (``delta`` set, ``final=False``) or the
    terminal event (``final=True``) carrying the assembled :class:`CliResult`.
    """

    delta: str = ""
    final: bool = False
    result: CliResult | None = None


def _apply_tokens(value: str, prompt: str, workdir: str) -> str:
    """Replace ``{prompt}`` / ``{workdir}`` in *value* only.

    Replacement values are inserted literally. A user prompt that contains
    ``{workdir}`` (or a workdir that contains ``{prompt}``) must not be
    scanned for further tokens.
    """
    if not value:
        return value
    out: list[str] = []
    i = 0
    n = len(value)
    prompt_len = len(PROMPT_TOKEN)
    workdir_len = len(WORKDIR_TOKEN)
    while i < n:
        if value.startswith(PROMPT_TOKEN, i):
            out.append(prompt)
            i += prompt_len
        elif value.startswith(WORKDIR_TOKEN, i):
            out.append(workdir)
            i += workdir_len
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _looks_like_argv_flag(text: str) -> bool:
    """True when *text* would be parsed as an option if left positional."""
    return bool(text) and text.startswith("-")


def _strip_resume_conflicts(argv: list[str], extra: list[str] | None = None) -> list[str]:
    """Drop flags that cancel resume (``--no-session``, ``--continue``, …)."""
    drop = {flag for flag in _DEFAULT_RESUME_STRIP if flag}
    for flag in extra or []:
        if isinstance(flag, str) and flag:
            drop.add(flag)
    if not drop:
        return list(argv)
    out: list[str] = []
    for part in argv:
        name = part.split("=", 1)[0]
        if name in drop:
            continue
        out.append(part)
    return out


def _protect_prompt_argv(cmd: list[str], prompt: str, workdir: str) -> list[str]:
    """Substitute tokens and keep user text from becoming extra flags.

    * ``-p {prompt}`` (and ``--print`` / ``--prompt`` / ``--single``) become
      ``-p=<prompt>`` so the value cannot be parsed as a sibling flag.
    * A standalone ``{prompt}`` already after ``--`` is left positional.
    * Other positional ``{prompt}`` slots: insert ``--`` before a flag-shaped
      prompt, moving it to the end when later argv still holds options.
    * Innocent positional prompts stay in place so fixture ``python -c``
      cmds keep ``sys.argv[1]``.
    """
    argv: list[str] = []
    deferred: str | None = None
    for part in cmd:
        if part == PROMPT_TOKEN:
            prev = argv[-1] if argv else ""
            if prev in _PROMPT_VALUE_FLAGS:
                argv[-1] = f"{prev}={prompt}"
            elif prev == "--":
                argv.append(prompt)
            elif _looks_like_argv_flag(prompt):
                deferred = prompt
            else:
                argv.append(prompt)
        else:
            argv.append(_apply_tokens(part, prompt, workdir))
    if deferred is not None:
        if argv[-1:] != ["--"]:
            argv.append("--")
        argv.append(deferred)
    return argv


def _extract_json_path(data: Any, dotpath: str) -> Any:
    """Navigate a dotted path into parsed JSON. Supports list indices.

    ``.result`` -> data["result"]; ``.choices.0.message.content`` walks the list.
    Leading dot optional. Raises KeyError/IndexError/TypeError on a bad path.
    """
    cur = data
    for key in dotpath.strip(".").split("."):
        if key == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur[key]
    return cur


_API_ERROR_RESULT = re.compile(r"^\[API Error:\s*(.*)\]\s*$", re.DOTALL | re.IGNORECASE)
_TAKES_VALUE = frozenset({
    "-m", "--model", "-o", "--output-format", "--approval-mode",
    "--resume", "-r", "--session", "--session-id",
    # qwen value flags: their values must not be mistaken for bare model tokens.
    "--auth-type", "--openai-base-url", "--openai-api-key", "--openai-logging-dir",
})


def gateway_error_from_cli_text(text: str | None) -> str | None:
    """Qwen/gemini-style CLIs exit 0 with ``[API Error: ...]`` as the result."""
    if not isinstance(text, str):
        return None
    match = _API_ERROR_RESULT.match(text.strip())
    if not match:
        return None
    return match.group(1).strip() or text.strip()


def gateway_error_from_cli_json(data: Any) -> str | None:
    """Read the last event of a claude/qwen JSON array for a gateway error."""
    if not isinstance(data, list) or not data or not isinstance(data[-1], dict):
        return None
    last = data[-1]
    result = last.get("result")
    found = gateway_error_from_cli_text(result if isinstance(result, str) else None)
    if found:
        return found
    if last.get("is_error") is True:
        if isinstance(result, str) and result.strip():
            return result.strip()
        err = last.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
        return "CLI reported an error"
    return None


def normalize_cli_cmd(name: str, cmd: list[str]) -> list[str]:
    """Restore catalog one-shot flags and turn a stray model token into ``-m``."""
    out = list(cmd)
    if name != "qwen" or not out:
        return out
    if "--output-format" not in out and "-o" not in out:
        out[1:1] = ["--output-format", "json"]
    if "--yolo" not in out and "-y" not in out:
        insert = 1
        for flag in ("--output-format", "-o"):
            if flag in out:
                insert = out.index(flag) + 2
                break
        out.insert(insert, "--yolo")
    i = 1
    while i < len(out):
        tok = out[i]
        if tok.startswith("-") or PROMPT_TOKEN in tok:
            i += 1
            continue
        prev = out[i - 1]
        if prev in _TAKES_VALUE or prev.startswith("-p="):
            i += 1
            continue
        out[i:i + 1] = ["-m", tok]
        i += 2
    return out


class CliAdapter:
    """Runs one configured agentic CLI as an awaitable one-shot subagent."""

    def __init__(self, config: CliAgentConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @classmethod
    def from_config(cls, name: str, raw: dict[str, Any]) -> CliAdapter:
        """Build an adapter from a config dict (see :class:`CliAgentConfig`)."""
        if not isinstance(raw, dict):
            raise CliAdapterError(f"CLI adapter '{name}' config must be a dict")
        cmd = raw.get("cmd")
        if not isinstance(cmd, list) or not all(isinstance(p, str) for p in cmd):
            raise CliAdapterError(f"CLI adapter '{name}': 'cmd' must be a list of strings")
        cfg = CliAgentConfig(
            name=name,
            cmd=normalize_cli_cmd(name, list(cmd)),
            prompt_mode=raw.get("prompt_mode", "arg"),
            parse=raw.get("parse", "text"),
            cwd=raw.get("cwd"),
            env=dict(raw.get("env", {})),
            env_allowlist=raw.get("env_allowlist"),
            # Coerce null/missing timeout to DEFAULT_TIMEOUT — a JSON null in
            # swarm_config used to become timeout=None and crash streaming with
            # TypeError: float + NoneType at ``deadline = start + cfg.timeout``.
            timeout=float(raw.get("timeout") or DEFAULT_TIMEOUT),
            mode=raw.get("mode", "default"),
            auth_check=raw.get("auth_check"),
            consensus=raw.get("consensus"),
            mcp_servers=raw.get("mcp_servers") or raw.get("mcpServers"),
            resume_argv=raw.get("resume_argv"),
            resume_insert=raw.get("resume_insert"),
            session_id_paths=raw.get("session_id_paths"),
        )
        return cls(cfg)

    def session_policy(self) -> dict[str, Any]:
        """Resolved resume policy: config override, else catalog by name."""
        from swarm.core.cli_catalog import session_policy as catalog_policy

        catalog = catalog_policy(self.name) or {}
        resume_argv = self.config.resume_argv
        if resume_argv is None:
            resume_argv = catalog.get("resume_argv")
        insert = self.config.resume_insert
        if insert is None:
            insert = catalog.get("resume_insert", 1)
        paths = self.config.session_id_paths
        if paths is None:
            paths = list(catalog.get("session_id_paths") or [])
        strip = catalog.get("resume_strip") or []
        return {
            "resume_argv": list(resume_argv) if resume_argv else [],
            "resume_insert": int(insert) if insert is not None else 1,
            "session_id_paths": list(paths),
            "can_resume": bool(resume_argv),
            "notes": catalog.get("notes") or "",
            "resume_strip": list(strip) if isinstance(strip, (list, tuple)) else [],
        }

    def can_resume(self) -> bool:
        """True when this adapter knows how to replay a stored CLI session id."""
        return bool(self.session_policy()["can_resume"])

    def is_available(self) -> bool:
        """True when the CLI executable is resolvable on PATH (or absolute)."""
        from swarm.core.cli_catalog import which_cli

        return which_cli(self.config.cmd[0]) is not None

    def _resolved_argv(self, argv: list[str]) -> list[str]:
        """Pin argv[0] to an absolute path so a stripped Daphne PATH still runs."""
        if not argv:
            return argv
        from swarm.core.cli_catalog import which_cli

        resolved = which_cli(argv[0])
        if not resolved:
            return argv
        return [resolved, *argv[1:]]

    def _build_invocation(
        self,
        prompt: str,
        workdir: str,
        session_id: str | None = None,
        resume_session_id: str | None = None,
    ) -> tuple[list[str], bytes | None]:
        """Return (argv, stdin_bytes) for the given prompt.

        First-turn catalog cmds stay one-shot. Resume argv is inserted only
        when ``session_id`` / ``resume_session_id`` is set and this CLI has a
        resume policy. ``resume_session_id`` is an alias of ``session_id``.
        """
        raw_sid = resume_session_id or session_id
        from swarm.core.cli_sessions import sanitize_cli_session_id

        sid = sanitize_cli_session_id(raw_sid)
        argv = _protect_prompt_argv(self.config.cmd, prompt, workdir)
        if sid:
            policy = self.session_policy()
            extra = [
                part.replace(SESSION_TOKEN, sid) for part in policy["resume_argv"]
            ]
            if extra:
                insert = min(int(policy["resume_insert"]), len(argv))
                argv = argv[:insert] + extra + argv[insert:]
            elif self.config.resume_argv is None:
                # No catalog/config policy: append the common --resume flag.
                argv = argv + ["--resume", sid]
            argv = _strip_resume_conflicts(argv, policy.get("resume_strip"))
        stdin_bytes: bytes | None = None
        if self.config.prompt_mode == "stdin":
            stdin_bytes = prompt.encode("utf-8")
        return argv, stdin_bytes

    def _extract_session_id(self, stdout: str) -> str | None:
        """Capture a CLI session id from JSON/JSONL stdout when present."""
        from swarm.core.cli_sessions import extract_session_id

        return extract_session_id(stdout, self.session_policy()["session_id_paths"])

    def _parse_output(self, stdout: str) -> tuple[str, str | None, str | None]:
        """Return (text, parse_error, session_id). parse_error is None on success."""
        session_id = self._extract_session_id(stdout)
        spec = self.config.parse or "text"
        if spec == "text":
            return stdout.strip(), None, session_id
        if spec.startswith("json"):
            dotpath = spec[len("json"):].lstrip(":")
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError as exc:
                return stdout.strip(), f"invalid JSON: {exc}", session_id
            if not dotpath:
                return (
                    data if isinstance(data, str) else json.dumps(data),
                    None,
                    session_id,
                )
            try:
                value = _extract_json_path(data, dotpath)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                return stdout.strip(), f"json path '{dotpath}' not found: {exc}", session_id
            return (value if isinstance(value, str) else json.dumps(value)), None, session_id
        return stdout.strip(), f"unknown parse spec {spec!r}", session_id

    async def run(
        self,
        prompt: str,
        *,
        workdir: str | None = None,
        extra_env: dict[str, str] | None = None,
        session_id: str | None = None,
        run_owner: dict[str, str] | None = None,
    ) -> CliResult:
        """Launch the CLI, await its answer, and parse the result.

        Never raises for runtime failures — a non-zero exit, timeout, or missing
        executable comes back as a :class:`CliResult` with ``ok=False``. The
        one-shot and streaming paths share a single launch/timeout/parse
        implementation: this drains :meth:`stream_run` and returns its terminal
        result (``stream_run`` always emits exactly one ``final`` chunk).
        """
        result: CliResult | None = None
        async for chunk in self.stream_run(
            prompt,
            workdir=workdir,
            extra_env=extra_env,
            session_id=session_id,
            run_owner=run_owner,
        ):
            if chunk.final:
                result = chunk.result
        assert result is not None  # stream_run guarantees a terminal chunk
        return result

    async def stream_run(
        self,
        prompt: str,
        *,
        workdir: str | None = None,
        extra_env: dict[str, str] | None = None,
        session_id: str | None = None,
        run_owner: dict[str, str] | None = None,
    ) -> AsyncIterator[CliStreamChunk]:
        """Like :meth:`run`, but yield stdout incrementally as it arrives.

        Yields :class:`CliStreamChunk` deltas while the CLI produces output, then
        a single terminal chunk (``final=True``) carrying the full
        :class:`CliResult`. The terminal result's ``text`` is parsed per the
        adapter's ``parse`` spec; for ``json:`` adapters the deltas are raw stdout
        (the parsed value only exists once the whole document is read), so callers
        that need clean incremental text should stream only ``parse="text"``
        adapters. Never raises for runtime failures.
        """
        cfg = self.config
        # API/WS callers (cli_agent, fusion, chat WS) must pass a confined
        # workdir. os.getcwd() remains only for local CLI / desktop (#576)
        # when this adapter is invoked without a cwd.
        if workdir:
            effective_workdir = (
                _apply_tokens(cfg.cwd, prompt, workdir) if cfg.cwd else workdir
            )
        else:
            process_cwd = os.getcwd()
            effective_workdir = (
                _apply_tokens(cfg.cwd, prompt, process_cwd)
                if cfg.cwd
                else process_cwd
            )
        argv, stdin_bytes = self._build_invocation(
            prompt, effective_workdir, session_id=session_id
        )
        env = self._build_env(prompt, effective_workdir, extra_env)
        mcp_path = None
        if cfg.mcp_servers:
            from swarm.core.cli_mcp import cleanup_mcp_config_file, inject_mcp_argv

            argv, mcp_path = inject_mcp_argv(
                cfg.name, argv, cfg.mcp_servers, executable=cfg.cmd[0]
            )

        if not self.is_available():
            if mcp_path:
                from swarm.core.cli_mcp import cleanup_mcp_config_file

                cleanup_mcp_config_file(mcp_path)
            yield CliStreamChunk(
                final=True,
                result=CliResult(
                    name=cfg.name, ok=False, text="",
                    error=f"executable not found on PATH: {cfg.cmd[0]!r}",
                ),
            )
            return

        argv = self._resolved_argv(argv)
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_workdir,
                env=env,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            if mcp_path:
                from swarm.core.cli_mcp import cleanup_mcp_config_file

                cleanup_mcp_config_file(mcp_path)
            yield CliStreamChunk(
                final=True,
                result=CliResult(
                    name=cfg.name, ok=False, text="",
                    error=f"failed to launch: {exc}", duration=time.monotonic() - start,
                ),
            )
            return

        run_token = None
        owner = run_owner
        if owner is None:
            from swarm.core.cli_run_registry import current_run_owner

            owner = current_run_owner()
        if owner:
            from swarm.core.cli_run_registry import register_cli_run

            run_token = register_cli_run(
                user_key=str(owner.get("user_key") or "u0"),
                agent_id=str(owner.get("agent_id") or "cli_agent"),
                conversation_id=str(owner.get("conversation_id") or ""),
                pid=proc.pid or 0,
            )

        if stdin_bytes is not None and proc.stdin is not None:
            try:
                proc.stdin.write(stdin_bytes)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        # Drain stderr concurrently so its pipe can never fill and deadlock the
        # process while we are only reading stdout.
        stderr_buf: list[bytes] = []

        async def _drain_stderr() -> None:
            assert proc.stderr is not None
            try:
                while True:
                    blob = await proc.stderr.read(4096)
                    if not blob:
                        break
                    stderr_buf.append(blob)
            except (asyncio.CancelledError, OSError):
                pass

        stderr_task = asyncio.ensure_future(_drain_stderr())

        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        out_parts: list[str] = []
        timed_out = False
        deadline = start + cfg.timeout
        assert proc.stdout is not None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    blob = await asyncio.wait_for(proc.stdout.read(4096), timeout=remaining)
                except asyncio.TimeoutError:
                    timed_out = True
                    break
                if not blob:  # EOF
                    break
                text = decoder.decode(blob)
                if text:
                    out_parts.append(text)
                    yield CliStreamChunk(delta=text)

            tail = decoder.decode(b"", final=True)
            if tail:
                out_parts.append(tail)
                yield CliStreamChunk(delta=tail)

            duration = time.monotonic() - start
            stdout = "".join(out_parts)

            captured_session = self._extract_session_id(stdout)

            if timed_out:
                await self._terminate(proc)
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
                stderr = b"".join(stderr_buf).decode("utf-8", errors="replace")
                yield CliStreamChunk(
                    final=True,
                    result=CliResult(
                        name=cfg.name, ok=False, text=stdout.strip(), returncode=proc.returncode,
                        duration=duration, timed_out=True, stderr=stderr.strip(),
                        error=f"timed out after {cfg.timeout}s",
                        session_id=captured_session,
                    ),
                )
                return

            await proc.wait()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
            stderr = b"".join(stderr_buf).decode("utf-8", errors="replace")

            from swarm.core.cli_run_registry import was_user_terminated

            user_stopped = was_user_terminated(run_token)
            if user_stopped:
                yield CliStreamChunk(
                    final=True,
                    result=CliResult(
                        name=cfg.name, ok=False, text=stdout.strip(), returncode=proc.returncode,
                        duration=duration, stderr=stderr.strip(),
                        error="terminated",
                        session_id=captured_session,
                        terminated=True,
                    ),
                )
                return

            if proc.returncode != 0:
                yield CliStreamChunk(
                    final=True,
                    result=CliResult(
                        name=cfg.name, ok=False, text=stdout.strip(), returncode=proc.returncode,
                        duration=duration, stderr=stderr.strip(),
                        error=f"exited {proc.returncode}: {stderr.strip()[:500]}",
                        session_id=captured_session,
                    ),
                )
                return

            text, parse_error, parsed_session = self._parse_output(stdout)
            gateway_error = gateway_error_from_cli_text(text)
            if gateway_error is None:
                try:
                    gateway_error = gateway_error_from_cli_json(json.loads(stdout))
                except json.JSONDecodeError:
                    gateway_error = None
            yield CliStreamChunk(
                final=True,
                result=CliResult(
                    name=cfg.name,
                    ok=gateway_error is None,
                    text=text,
                    returncode=0,
                    duration=duration,
                    parse_error=parse_error,
                    stderr=stderr.strip(),
                    error=gateway_error,
                    session_id=parsed_session or captured_session,
                ),
            )
        finally:
            # SSE disconnect / aclose / CancelledError — same path as timeout.
            # shield so a cancel during cleanup still lets killpg + wait finish.
            from swarm.core.cli_run_registry import unregister_cli_run

            unregister_cli_run(run_token)
            try:
                await asyncio.shield(self._terminate(proc))
            except asyncio.CancelledError:
                pass
            if not stderr_task.done():
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
            if mcp_path:
                from swarm.core.cli_mcp import cleanup_mcp_config_file

                cleanup_mcp_config_file(mcp_path)

    # Always-passed vars so a locked-down CLI can still run and resolve itself.
    _ESSENTIAL_ENV = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL", "TERM")

    def _build_env(
        self, prompt: str, workdir: str, extra_env: dict[str, str] | None
    ) -> dict[str, str]:
        cfg = self.config
        if cfg.env_allowlist is None:
            env = os.environ.copy()
        else:
            keep = (*self._ESSENTIAL_ENV, *cfg.env_allowlist)
            env = {k: os.environ[k] for k in keep if k in os.environ}
        for key, val in cfg.env.items():
            env[key] = _apply_tokens(val, prompt, workdir)
        if extra_env:
            env.update(extra_env)
        from swarm.core.cli_catalog import host_cli_path

        env["PATH"] = host_cli_path(env.get("PATH", os.environ.get("PATH", "")))
        return env

    async def check_auth(self) -> str:
        """Probe whether this CLI is authenticated.

        Returns one of AUTH_NOT_INSTALLED (executable missing), AUTH_UNKNOWN
        (no ``auth_check`` configured, or the probe errored/timed out),
        AUTH_AUTHENTICATED (``auth_check`` exited 0), or AUTH_UNAUTHENTICATED.
        Never raises.
        """
        cfg = self.config
        if not self.is_available():
            return AUTH_NOT_INSTALLED
        if not cfg.auth_check:
            return AUTH_UNKNOWN
        workdir = os.getcwd()
        argv = self._resolved_argv([_apply_tokens(p, "", workdir) for p in cfg.auth_check])
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env("", workdir, None),
                start_new_session=True,
            )
        except (OSError, ValueError):
            return AUTH_UNKNOWN
        try:
            await asyncio.wait_for(proc.communicate(), timeout=min(cfg.timeout, AUTH_TIMEOUT))
        except asyncio.TimeoutError:
            await self._terminate(proc)
            return AUTH_UNKNOWN
        return AUTH_AUTHENTICATED if proc.returncode == 0 else AUTH_UNAUTHENTICATED

    async def smoke_check(
        self, *, prompt: str = DEFAULT_SMOKE_PROMPT, timeout: float | None = None
    ) -> SmokeResult:
        """Run one trivial one-shot to confirm the cmd *returns* in print mode.

        Unlike :meth:`check_auth` (a cheap exit-code probe), this actually
        invokes the CLI — and therefore the model — once, so it consumes a small
        amount of quota. It exists to catch the most common misconfiguration: a
        missing/wrong non-interactive flag, which makes the CLI block on input
        and hang until the timeout. Returns a :class:`SmokeResult`; never raises.
        """
        if not self.is_available():
            return SmokeResult(self.name, SMOKE_NOT_INSTALLED)
        t = timeout if timeout is not None else min(self.config.timeout, SMOKE_TIMEOUT)
        from swarm.core.cli_catalog import apply_smoke_flags

        smoke_cmd = apply_smoke_flags(self.name, list(self.config.cmd))
        probe = CliAdapter(replace(self.config, cmd=smoke_cmd, timeout=t))
        res = await probe.run(prompt)
        if res.timed_out:
            return SmokeResult(
                self.name, SMOKE_HANG,
                "no output before timeout — check the non-interactive flag",
                res.duration,
            )
        if not res.ok:
            return SmokeResult(self.name, SMOKE_ERROR, (res.error or "")[:200], res.duration)
        if not (res.text or "").strip():
            return SmokeResult(self.name, SMOKE_ERROR, "exited 0 but produced no output", res.duration)
        return SmokeResult(self.name, SMOKE_OK, "", res.duration)

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        """Kill a timed-out process group: SIGTERM, grace, then SIGKILL."""
        if proc.returncode is not None or not proc.pid or proc.pid <= 1:
            return
        try:
            pgid = os.getpgid(proc.pid)
            if pgid <= 1:
                return
        except (ProcessLookupError, OSError):
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, OSError):
                return
            try:
                await asyncio.wait_for(proc.wait(), timeout=TERM_GRACE)
                return
            except asyncio.TimeoutError:
                continue


@dataclass
class CliDiscovery:
    """Autodiscovery status for one configured CLI adapter."""

    name: str
    installed: bool
    executable: str | None
    mode: str
    authenticated: str = AUTH_UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "installed": self.installed,
            "executable": self.executable,
            "mode": self.mode,
            "authenticated": self.authenticated,
        }


class CliAdapterRegistry:
    """Holds the configured CLI adapters and resolves them by name."""

    def __init__(self, adapters: dict[str, CliAdapter] | None = None):
        self._adapters: dict[str, CliAdapter] = adapters or {}

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> CliAdapterRegistry:
        """Build a registry from the top-level swarm config's ``cli_agents`` block."""
        adapters: dict[str, CliAdapter] = {}
        raw_agents = (config or {}).get("cli_agents", {}) or {}
        for name, raw in raw_agents.items():
            try:
                adapters[name] = CliAdapter.from_config(name, raw)
            except CliAdapterError as exc:
                logger.warning("Skipping CLI adapter %r: %s", name, exc)
        return cls(adapters)

    def get(self, name: str) -> CliAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise CliAdapterError(
                f"no CLI adapter named {name!r}; configured: {sorted(self._adapters)}"
            ) from exc

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def available(self) -> list[str]:
        """Names of adapters whose executable is present on this host."""
        return sorted(n for n, a in self._adapters.items() if a.is_available())

    def discover(self) -> list[CliDiscovery]:
        """Report install status for every configured adapter (sorted by name)."""
        out: list[CliDiscovery] = []
        for name in self.names():
            cfg = self._adapters[name].config
            from swarm.core.cli_catalog import which_cli

            exe = cfg.cmd[0]
            resolved = which_cli(exe) or (exe if os.path.sep in exe else None)
            out.append(
                CliDiscovery(
                    name=name,
                    installed=self._adapters[name].is_available(),
                    executable=resolved,
                    mode=cfg.mode,
                )
            )
        return out

    async def discover_auth(self) -> list[CliDiscovery]:
        """Like discover(), but also probe each adapter's authentication state.

        Runs every adapter's ``auth_check`` concurrently. Slower than
        :meth:`discover` (it launches subprocesses), so it is opt-in.
        """
        rows = self.discover()

        async def _fill(row: CliDiscovery) -> CliDiscovery:
            row.authenticated = await self._adapters[row.name].check_auth()
            return row

        return list(await asyncio.gather(*(_fill(r) for r in rows)))

    async def smoke_check_all(
        self, *, names: list[str] | None = None, timeout: float | None = None
    ) -> list[SmokeResult]:
        """Smoke-probe adapters concurrently (all configured, or a subset).

        Each probe runs one trivial one-shot, so this consumes a little quota per
        installed adapter — it is opt-in, not part of plain :meth:`discover`.
        """
        target = names if names is not None else self.names()
        adapters = [self._adapters[n] for n in target if n in self._adapters]
        return list(
            await asyncio.gather(*(a.smoke_check(timeout=timeout) for a in adapters))
        )

    def resolve_panel(self, names: list[str]) -> list[CliAdapter]:
        """Resolve a list of adapter names to adapters (raises on unknown)."""
        return [self.get(n) for n in names]

    def with_overrides(self, overrides: dict[str, dict[str, Any]]) -> CliAdapterRegistry:
        """Return a copy with per-adapter field overrides applied (non-mutating)."""
        merged = dict(self._adapters)
        for name, patch in (overrides or {}).items():
            base = merged.get(name)
            cfg = base.config if base else None
            if cfg is None:
                merged[name] = CliAdapter.from_config(name, patch)
            else:
                merged[name] = CliAdapter(replace(cfg, **patch))
        return CliAdapterRegistry(merged)
