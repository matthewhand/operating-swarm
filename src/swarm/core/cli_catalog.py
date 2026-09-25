"""Built-in catalog of known-good CLI adapter configs.

Starting-point ``cli_agents`` configs for popular agentic CLIs. Lets
``swarm-cli cli-agents --suggest`` propose a ready-to-paste config block for any
supported CLI that is installed on the host but not yet in the user's swarm
config. ``LIST_MODELS`` documents each CLI's real non-interactive list-models
argv (see :mod:`swarm.core.cli_models` and ``swarm-cli list-models``).

REQ-157 / #565: the **configured** ``cli_agents`` list stays empty until the
user adds (Settings one-click or ``swarm-cli cli-agents --init --write``).
Startup / ``GET /v1/cli-agents/`` **discovers** binaries on PATH (and known
user-local dirs) and prepopulates the **suggested / addable** set. Discovery
is ``which`` / ``stat`` only — never ``auth_check``, never a login probe,
never a network call.

CLI-first product modes (#151 / #149): shipped defaults turn **CLI on** and
**API / Blueprint / Team / Remote off** until Settings enables them. The rail
and agent picker start from **discovered host CLIs only** — a known catalog
name that is not on PATH (pi absent) stays absent. ``known`` is the full
catalog; ``discovered`` / ``installed`` is the PATH seed; ``configured`` is
opt-in.

Known catalog names (agy is the antigravity CLI): grok, agy, claude, gemini,
codex, opencode, kilocode, pi, omp, qwen.

Remote/headless serving (Issue #180): opencode and kilocode can attach to a
``serve`` endpoint on another box. See :mod:`swarm.core.cli_remote`.

Each entry runs the CLI **one-shot, non-interactive, auto-approve** (full
capability) — the flag that matters is the auto-approve one, without which the
CLI blocks on a permission prompt and is killed on timeout (see
``docs/CLI_FUSION.md``). That is how Open Swarm **simulates always-approve**;
Agent Router Shift+Tab therefore cycles only plan / auto-edit / default.
Exact flags and JSON shapes drift by CLI version, so these are suggestions
to verify with each CLI's ``--help``, not guarantees.

Known per-CLI gotchas are encoded here so the defaults *just run* (verified live
2026-06-16):

* **gemini** refuses to run in an "untrusted" directory — ``--skip-trust`` (or
  ``GEMINI_CLI_TRUST_WORKSPACE=true``) is required for non-interactive use.
* **opencode** has no usable default model in ``run`` mode (its built-in default
  errors as "not supported"), so an explicit ``--model`` is required. The value
  below is account/version-specific — run ``opencode models`` to pick one.
* **omp** (Oh My Pi) needs a durable ``~/.omp/agent/models.yml`` overlay to map
  ``litellm/orchestration`` to the host LiteLLM OpenAI-compatible base (often
  ``http://127.0.0.1:4010/v1``). Env ``OPENAI_BASE_URL`` alone is insufficient.
  Stdin must stay closed in print mode (``CliAdapter`` uses ``DEVNULL``).
* **agy** treats ``-p`` / ``--print`` as a flag that *consumes the next argv
  token as the prompt*. ``agy -p --output-format json 'hi'`` errors with
  ``-p took "--output-format" as its prompt``. Attach the prompt to the flag
  (``-p={prompt}``) and keep ``--output-format`` as a sibling flag.

The gemini default uses the fast flash tier (no ``-m``). To select the pro tier
use ``with_model("gemini", "gemini-3-pro-preview", timeout=600)`` — but note
that on the free ``oauth-personal`` login the pro model is heavily throttled and
can take minutes (or stall) even on a one-word prompt; it is far more usable on a
paid ``GEMINI_API_KEY``. Flash answers in a few seconds.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from swarm.core.kind_bases import CliSlashCommand

# REQ-910 / #641: per-CLI **native slash commands**, declared by the provider
# (ADR-005 ``CliKindBase`` capability) and published verbatim in
# ``GET /v1/cli-agents/`` as ``slash_commands`` so the webui composer derives
# its popup from data — never a hardcoded list in JSX.
#
# Blocking investigation recorded in #641: **omp print mode does not dispatch
# slash commands.** oh-my-pi's own docs (``slash-command-internals.md`` §2)
# dispatch built-ins only in *TUI and ACP/RPC modes*; ``cli-reference.md``
# shows no ``--compress``/compaction launch flag; and the ``omp compress``
# *subcommand* is an unrelated file-to-prompt-register tool. omp therefore
# declares ``/compress`` with ``available=False``: the popup greys it with the
# reason and it is never sent as chat text (the server-side compact flow is
# #636's surface).
CLI_SLASH_COMMANDS: dict[str, tuple[CliSlashCommand, ...]] = {
    "omp": (
        CliSlashCommand(
            name="compress",
            description="Compact this omp session's context",
            available=False,
            unavailable_reason="omp cannot compress in non-interactive (print) mode",
        ),
    ),
}


def cli_slash_commands_payload() -> dict[str, list[dict[str, Any]]]:
    """JSON-safe ``slash_commands`` rows for ``GET /v1/cli-agents/``."""
    return {
        cli: [
            {
                "name": cmd.name,
                "description": cmd.description,
                "available": cmd.available,
                "unavailable_reason": cmd.unavailable_reason,
            }
            for cmd in commands
        ]
        for cli, commands in CLI_SLASH_COMMANDS.items()
    }


# #636: per-CLI provider-native compact hooks, populated as providers verify
# their CLI's real compact command on a CliKindBase subclass. Ships empty —
# an unverified argv template would be the dishonest surface #641 walked back.
CLI_COMPACT_HOOKS: dict[str, str] = {}


def cli_compact_payload() -> dict[str, str]:
    """JSON-safe ``cli_compact`` rows for ``GET /v1/cli-agents/``."""
    return dict(CLI_COMPACT_HOOKS)


def seat_capabilities_payload(extra_bases: list[type] | None = None) -> dict[str, dict]:
    """JSON-safe per-kind seat capabilities for ``GET /v1/cli-agents/`` (#551).

    The published channel: the frontend derives attach/compact/plugins gates
    from this data instead of comparing kind strings. ``extra_bases`` lets a
    test (or a plugin host) prove a subclass override flows through unchanged.
    """
    from swarm.core.kind_bases import (
        ApiKindBase,
        CliKindBase,
        RemoteKindBase,
        TeamKindBase,
        seat_capabilities,
    )

    bases: dict[str, type] = {
        "api": ApiKindBase,
        "cli": CliKindBase,
        "remote": RemoteKindBase,
        "team": TeamKindBase,
    }
    for extra in extra_bases or []:
        kind = str(getattr(extra, "kind", "") or "").strip().lower()
        if kind in bases and extra is not bases[kind]:
            # A subclass overriding axes still publishes under its kind — the
            # payload reflects what a seat of this kind may declare.
            merged = seat_capabilities(bases[kind])
            merged.update(seat_capabilities(extra))
            bases[kind] = extra
    return {
        kind: {
            name: {"enabled": bool(cap["enabled"]), "reason": str(cap["reason"])}
            for name, cap in seat_capabilities(base).items()
        }
        for kind, base in bases.items()
    }

# User-local bins Daphne often misses when started with PATH=/usr/bin:/bin.
_EXTRA_BIN_REL = (
    (".local", "bin"),
    ("bin",),
    (".grok", "bin"),
    (".opencode", "bin"),
    (".npm-global", "bin"),
    (".local", "share", "pnpm"),
    # #1175: hermes's launcher execs `python` from its venv bin; the venv's
    # python symlink resolves into ~/.local/share/uv (mounted ro for CLI
    # discovery). Without this dir on PATH the launcher dies with
    # "venv/bin/python: No such file or directory".
    (".hermes", "hermes-agent", "venv", "bin"),
)


def extra_cli_path_dirs() -> list[str]:
    """User and nvm bin dirs that commonly hold grok/agy/pi/opencode.

    ``SWARM_CLI_PATH_DIRS`` (``os.pathsep``-joined) extends the scan — the
    deployment knob for containerised runs whose host bin mounts differ
    (#716/#717). Configured dirs come first and must exist.
    """
    home = os.path.expanduser("~")
    dirs: list[str] = []
    configured = os.environ.get("SWARM_CLI_PATH_DIRS", "")
    for d in configured.split(os.pathsep):
        if d.strip() and os.path.isdir(d) and d not in dirs:
            dirs.append(d)
    for parts in _EXTRA_BIN_REL:
        path = os.path.join(home, *parts)
        if os.path.isdir(path):
            dirs.append(path)
    nvm = os.path.join(home, ".nvm", "versions", "node")
    if os.path.isdir(nvm):
        for ver in sorted(os.listdir(nvm), reverse=True):
            path = os.path.join(nvm, ver, "bin")
            if os.path.isdir(path):
                dirs.append(path)
    for path in ("/usr/local/bin",):
        if os.path.isdir(path):
            dirs.append(path)
    return dirs


def host_cli_path(current: str | None = None) -> str:
    """``PATH`` with extra user bin dirs prepended (deduped)."""
    current = os.environ.get("PATH", "") if current is None else current
    parts: list[str] = []
    seen: set[str] = set()
    for d in [*extra_cli_path_dirs(), *current.split(os.pathsep)]:
        if d and d not in seen:
            seen.add(d)
            parts.append(d)
    return os.pathsep.join(parts)


def which_cli(exe: str) -> str | None:
    """Resolve ``exe`` on the same PATH runs use (``host_cli_path``)."""
    if not exe:
        return None
    if os.path.sep in exe:
        return exe if os.path.isfile(exe) and os.access(exe, os.X_OK) else None
    path = host_cli_path()
    try:
        return shutil.which(exe, path=path)
    except TypeError:
        return shutil.which(exe)

# name -> adapter config dict (same shape as one `cli_agents` entry).
CATALOG: dict[str, dict[str, Any]] = {
    "grok": {
        # xAI's grok CLI (also installed as `agent`). -p/--single is the
        # non-interactive print mode; --always-approve auto-approves tool use.
        # Attach the prompt (-p={prompt}) so user text cannot become a sibling
        # flag. Inherits the full env (auth is file-based, not a single known var).
        "cmd": ["grok", "--output-format", "json", "--always-approve", "-p={prompt}"],
        "parse": "json:.text",
        "mode": "write",
        "timeout": 240,
    },
    "agy": {
        # Agy print-mode: -p/--print consumes the next argv token as the
        # prompt, so the prompt MUST be attached (-p={prompt}), not a
        # following positional. JSON shape is {response, status, ...}.
        "cmd": [
            "agy",
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "-p={prompt}",
        ],
        "parse": "json:.response",
        "mode": "write",
        "timeout": 240,
    },
    "claude": {
        "cmd": ["claude", "-p={prompt}", "--output-format", "json",
                "--dangerously-skip-permissions"],
        "parse": "json:.result",
        "mode": "write",
        "timeout": 240,
        "env_allowlist": ["ANTHROPIC_API_KEY"],
    },
    "gemini": {
        # --skip-trust: gemini refuses to run in an untrusted dir without it.
        "cmd": ["gemini", "-p={prompt}", "-o", "json", "--yolo", "--skip-trust"],
        "parse": "json:.response",
        "mode": "write",
        "timeout": 240,
        "env_allowlist": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    },
    "codex": {
        # Flags before `--` so a positional prompt cannot swallow them.
        "cmd": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--", "{prompt}"],
        "parse": "text",
        "mode": "write",
        "timeout": 240,
        "env_allowlist": ["OPENAI_API_KEY"],
    },
    "opencode": {
        # --model: opencode's built-in default errors as "not supported"; an
        # explicit model is required. Prefer LAN LiteLLM via host opencode
        # provider (`litellm/orchestration` on .30:8000). Run `opencode models`
        # to pick another available id if needed.
        # --model before `--` so a positional prompt cannot turn it into text.
        "cmd": ["opencode", "run", "--model", "litellm/orchestration", "--", "{prompt}"],
        "parse": "text",
        "mode": "write",
        "timeout": 240,
    },
    "kilocode": {
        # Kilo Code CLI (opencode fork). Binary is ``kilo``. One-shot ``run``
        # with a positional prompt after ``--``. Headless: ``kilo serve``;
        # attach with ``--attach http://host:port`` (see cli_remote).
        "cmd": ["kilo", "run", "--", "{prompt}"],
        "parse": "text",
        "mode": "write",
        "timeout": 240,
    },
    "omp": {
        # Oh My Pi non-interactive print mode. -p/--print does not consume the
        # prompt; the message is positional after `--`. Pin LiteLLM
        # orchestration via ~/.omp/agent/models.yml (provider litellm ->
        # OpenAI-compatible base, often :4010/v1). --auto-approve skips tool
        # prompts. CliAdapter closes stdin (DEVNULL) — required to avoid
        # readPipedInput hang.
        "cmd": [
            "omp",
            "-p",
            "--model",
            "litellm/orchestration",
            "--auto-approve",
            "--",
            "{prompt}",
        ],
        "parse": "text",
        "mode": "write",
        "timeout": 240,
    },
    "pi": {
        # pi -p/--print is non-interactive; prompt is a positional message
        # (not attached to -p). `--` keeps user text from becoming flags.
        # --mode text; --approve trusts project-local files for that run.
        # --no-session is smoke/verify only (see SMOKE_FLAGS) so production
        # runs can resume with --session.
        # No catalog ``--model``: pi's implicit default was a discontinued
        # Aliyun/DashScope coding-plan slug (401). Pin via apply_model from
        # the live ``pi --list-models`` table (provider/id before ``--``).
        "cmd": ["pi", "-p", "--mode", "text", "--approve", "--", "{prompt}"],
        "parse": "text",
        "mode": "write",
        "timeout": 240,
    },
    "qwen": {
        # Qwen Code (gemini-cli fork) one-shot. The positional `query` after
        # `--` does NOT reach the CLI (it reports "No input provided"); use
        # the protected -p=<prompt> form (matches gemini; -p is deprecated
        # but functional). --yolo auto-approves all tools. JSON output is an
        # ARRAY of claude-style events whose FINAL element is the result —
        # parsed via the -1 list index supported by _extract_json_path.
        # timeout None: interactive ws turns run unbounded (stop button kills
        # the process group); set a number in cli_agents to re-arm a limit.
        "cmd": ["qwen", "--output-format", "json", "--yolo", "-p={prompt}"],
        "parse": "json:.-1.result",
        "mode": "write",
        "timeout": None,
    },
}


# CLIs with a BUILT-IN "run N candidates and pick the best" mode (native
# consensus) — the CLI fans out internally in one call, distinct from the
# framework running it N times. Maps cli name -> argv to APPEND, with "{n}"
# substituted for the candidate count.
NATIVE_CONSENSUS: dict[str, list[str]] = {
    "grok": ["--best-of-n", "{n}"],  # verified live: grok runs an N-candidate tournament
}


# How each catalogued CLI names and resumes a session. First-turn ``cmd`` stays
# one-shot; Swarm inserts ``resume_argv`` only when a stored id exists.
# ``{session_id}`` is replaced with the stored id. Distinct from Django/API
# conversation ids and from OS ``start_new_session`` (process-group kill).
#
# List capability (#795): ``works`` = a real provider list (CLI argv or the
# CLI's own session store); ``paste-only`` = resume by id, no verified list;
# ``unsupported`` = no list and no resume. Never invent picker rows.
# Provider list is the SoT for CLI resume — Django Select/New (#469) is not.
#
# antigravity is **not** in CATALOG (not wired). Agy is the catalog name;
# headless resume is ``agy -p --conversation <id>``.
LIST_CAPABILITY_WORKS = "works"
LIST_CAPABILITY_PASTE_ONLY = "paste-only"
LIST_CAPABILITY_UNSUPPORTED = "unsupported"
LIST_CAPABILITIES = frozenset(
    {LIST_CAPABILITY_WORKS, LIST_CAPABILITY_PASTE_ONLY, LIST_CAPABILITY_UNSUPPORTED}
)
# Native transcript export for a quota hop (#531). Catalog CLIs are summary
# inject only until a non-interactive export argv is verified. Fixtures may
# set ``export_argv`` to exercise the transcript path. Never invent export.
EXPORT_CAPABILITY_TRANSCRIPT = "transcript"
EXPORT_CAPABILITY_SUMMARY = "summary"
EXPORT_CAPABILITY_NONE = "none"
EXPORT_CAPABILITIES = frozenset(
    {
        EXPORT_CAPABILITY_TRANSCRIPT,
        EXPORT_CAPABILITY_SUMMARY,
        EXPORT_CAPABILITY_NONE,
    }
)
DEFAULT_EXPORT_NOTES = (
    "No verified non-interactive transcript export. A CLI/API switch starts "
    "a new session and seeds it from the swarm thread (summary inject). "
    "Do not resume the earlier native session — including when switching back."
)
# Agy conversations live as ``<uuid>.db`` under this directory (filename stem
# is the ``--conversation`` id). No official ``agy conversations list`` yet
# (google-antigravity/antigravity-cli#602).
AGY_CONVERSATIONS_STORE = "agy_conversations"
DEFAULT_AGY_CONVERSATIONS_DIR = "~/.gemini/antigravity-cli/conversations"
# Qwen Code persists each session as ``<projects>/<escaped-cwd>/chats/<sid>.jsonl``
# (claude-style JSONL; every event carries sessionId + cwd). The escaped dir
# name is the session's cwd, non-alphanumerics → ``-``.
QWEN_SESSIONS_STORE = "qwen_sessions"
DEFAULT_QWEN_PROJECTS_DIR = "~/.qwen/projects"
# omp (Oh My Pi) persists every session as JSONL under its agent dir; the
# visible `-p` output is plain text, so ids are read from the store (#640).
OMP_SESSIONS_STORE = "omp_sessions"
DEFAULT_OMP_SESSIONS_DIR = "~/.omp/agent/sessions"

SESSION: dict[str, dict[str, Any]] = {
    "grok": {
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 1,
        "session_id_paths": [".sessionId", ".session_id"],
        "list_argv": ["grok", "sessions", "list", "--limit", "50"],
        "list_capability": LIST_CAPABILITY_WORKS,
        "notes": (
            "grok -p --resume <uuid> (also -r). --session-id / -s names a NEW "
            "session; do not use it to resume. JSON often includes sessionId. "
            "List: ``grok sessions list`` (text table: id, dates, status, "
            "summary; cwd + sibling worktrees). JSON/JSONL also accepted."
        ),
    },
    "claude": {
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 1,
        "session_id_paths": [".session_id"],
        "list_capability": LIST_CAPABILITY_PASTE_ONLY,
        "notes": (
            "claude -p --resume <uuid> (also -r). JSON result includes session_id "
            "even when parse is json:.result. A resume may mint a new session_id; "
            "store the latest. --session-id names a new session, not a resume. "
            "List is paste-only: ``claude --resume`` without an id is a TUI picker."
        ),
    },
    "gemini": {
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 1,
        "session_id_paths": [".session_id", ".sessionId"],
        "list_capability": LIST_CAPABILITY_PASTE_ONLY,
        "notes": (
            "gemini -p --resume <uuid> (also -r). --session-id starts a NEW "
            "session and conflicts with --resume. Capture id from JSON when present. "
            "List is paste-only — no verified non-interactive list argv."
        ),
    },
    "codex": {
        "resume_argv": ["resume", "{session_id}"],
        "resume_insert": 2,  # after `codex exec` → `codex exec resume <id> …`
        "session_id_paths": [".thread_id", ".session_id"],
        "list_capability": LIST_CAPABILITY_PASTE_ONLY,
        "notes": (
            "codex exec resume <SESSION_ID> <prompt> (subcommand, not a --flag). "
            "Default catalog parse is text; thread_id appears when --json is used. "
            "Interactive `codex resume` is a TUI — do not use it here. "
            "List is paste-only — no verified non-interactive list argv."
        ),
    },
    "opencode": {
        "resume_argv": ["--session", "{session_id}"],
        "resume_insert": 2,  # after `opencode run` → `opencode run --session <id> …`
        "resume_strip": ["--continue", "-c"],
        "session_id_paths": [".session", ".sessionID", ".id"],
        "list_argv": ["opencode", "session", "list", "--format", "json"],
        "list_capability": LIST_CAPABILITY_WORKS,
        "notes": (
            "opencode run --session <id> (also -s). --continue/-c is last-session "
            "in the cwd, not thread-scoped — do not use it. Capture id when the "
            "CLI emits JSON; the default catalog parse is text. "
            "List: ``opencode session list --format json`` ({id, title, updated})."
        ),
    },
    "kilocode": {
        "resume_argv": ["--session", "{session_id}"],
        "resume_insert": 2,  # after `kilo run` → `kilo run --session <id> …`
        "resume_strip": ["--continue", "-c"],
        "session_id_paths": [".session", ".sessionID", ".id"],
        "list_capability": LIST_CAPABILITY_PASTE_ONLY,
        "notes": (
            "kilo run --session <id> (also -s). --continue/-c is last-session "
            "in the cwd, not thread-scoped — do not use it. "
            "Headless: ``kilo serve``; attach with ``--attach http://host:port``. "
            "List is paste-only until a non-interactive list argv is verified."
        ),
    },
    "omp": {
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 2,  # after `omp -p` → `omp -p --resume <id> …`
        "resume_strip": ["--no-session", "--continue", "-c"],
        "session_id_paths": [".session", ".id"],
        "list_store": OMP_SESSIONS_STORE,
        "list_store_dir": DEFAULT_OMP_SESSIONS_DIR,
        "list_capability": LIST_CAPABILITY_WORKS,
        "notes": (
            "omp -p --resume <id|path> (also -r). --continue/-c is last session — "
            "do not use it here. `-p` prints text, so the session id is read from "
            "omp's own store ~/.omp/agent/sessions/<cwd>/<timestamp>_<id>.jsonl "
            "(newest after each successful turn). Smoke/verify injects --no-session "
            "(ephemeral) and is never stamped."
        ),
    },
    "agy": {
        "resume_argv": ["--conversation", "{session_id}"],
        "resume_insert": 1,
        "session_id_paths": [".conversation_id", ".conversationId"],
        "list_store": AGY_CONVERSATIONS_STORE,
        "list_capability": LIST_CAPABILITY_WORKS,
        "notes": (
            "agy -p --conversation <id>. --continue is most-recent, not "
            "thread-scoped — do not use it here. "
            "No official list argv (antigravity-cli#602). List reads the CLI's "
            "own store ``~/.gemini/antigravity-cli/conversations/<uuid>.db`` "
            "(stem = id, mtime = updated_at; never opens the sqlite)."
        ),
    },
    "pi": {
        "resume_argv": ["--session", "{session_id}"],
        "resume_insert": 2,  # after `pi -p` → `pi -p --session <id> …`
        "resume_strip": ["--no-session", "--continue", "-c"],
        "session_id_paths": [".session", ".id"],
        "list_capability": LIST_CAPABILITY_PASTE_ONLY,
        "notes": (
            "pi -p --session <path|id>. --resume/-r is a TUI picker; "
            "--continue/-c is last session — do not use those here. "
            "Smoke/verify injects --no-session (ephemeral); production cmd does not. "
            "List is paste-only — no verified non-interactive list argv."
        ),
    },
    "qwen": {
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 1,
        "resume_strip": ["--continue", "-c"],
        "session_id_paths": [".session_id"],
        "list_store": QWEN_SESSIONS_STORE,
        "list_store_dir": DEFAULT_QWEN_PROJECTS_DIR,
        "list_capability": LIST_CAPABILITY_WORKS,
        "notes": (
            "qwen --resume <uuid> (also -r). -c/--continue is most-recent and "
            "--session-id names a NEW session — do not use either to resume. "
            "JSON output is an event array; every event carries session_id and "
            "the final result event is authoritative (last match wins). "
            "List works via the provider store: ~/.qwen/projects/<escaped-cwd>/"
            "chats/<sid>.jsonl (id + mtime + first user text + cwd)."
        ),
    },
}

# Flags injected only on smoke/verify probes. Production catalog cmds must
# stay resumable (Pi --no-session would cancel --session).
SMOKE_FLAGS: dict[str, list[str]] = {
    "pi": ["--no-session"],
    "omp": ["--no-session"],
}

for _policy in SESSION.values():
    _policy.setdefault("export_capability", EXPORT_CAPABILITY_SUMMARY)
    _policy.setdefault("export_notes", DEFAULT_EXPORT_NOTES)

# Non-interactive session-list argv / provider store. Never invent rows.
LIST_SESSIONS_TIMEOUT = 15.0
RECENT_SESSION_LIMIT = 10



# #855 slice D — session-cluster helpers moved verbatim to swarm.core.cli.sessions (patch-safe: bodies resolve catalog references through a late-bound handle; names are rebound here so the import surface is unchanged).
from swarm.core.cli import sessions as _cli_sessions  # noqa: E402

_cli_agent_entry = _cli_sessions._cli_agent_entry
list_sessions_argv = _cli_sessions.list_sessions_argv
list_sessions_store = _cli_sessions.list_sessions_store
list_sessions_store_dir = _cli_sessions.list_sessions_store_dir
list_capability = _cli_sessions.list_capability
can_list_sessions = _cli_sessions.can_list_sessions
export_sessions_argv = _cli_sessions.export_sessions_argv
export_capability = _cli_sessions.export_capability
can_export_transcript = _cli_sessions.can_export_transcript
list_sessions_catalog = _cli_sessions.list_sessions_catalog

# Default capability traits (0..1) per known CLI for inference-profile matching
# (see swarm.core.inference_profile). These are sensible starting points the
# USER is expected to tune for their own plans/models via a per-agent ``traits``
# block in config — e.g. someone on a top grok plan may rate it 1.0 intelligence.
# cost = cheapness (1.0 = cheapest). gemini defaults to its fast/cheap flash tier.
CLI_TRAITS: dict[str, dict[str, float]] = {
    "grok":     {"intelligence": 0.90, "speed": 0.60, "cost": 0.55},
    "agy":      {"intelligence": 0.85, "speed": 0.65, "cost": 0.50},
    "claude":   {"intelligence": 0.95, "speed": 0.55, "cost": 0.35},
    "gemini":   {"intelligence": 0.60, "speed": 0.92, "cost": 0.90},
    "codex":    {"intelligence": 0.75, "speed": 0.60, "cost": 0.50},
    "opencode": {"intelligence": 0.55, "speed": 0.65, "cost": 0.75},
    "kilocode": {"intelligence": 0.55, "speed": 0.65, "cost": 0.75},
    "omp":      {"intelligence": 0.60, "speed": 0.70, "cost": 0.80},
    "pi":       {"intelligence": 0.70, "speed": 0.70, "cost": 0.70},
    "qwen":     {"intelligence": 0.62, "speed": 0.85, "cost": 0.85},
}

# First-class sidebar CLIs — always listed like remote FRAMEWORKS (OpenMausBot),
# even when the designer has not created a `kind=cli` record. Other catalog
# CLIs stay available in the backend picker / designer.
# Grok rail verify rows use ``{name}_agent`` ids (grok_agent, agy_agent, …).
SIDEBAR_CLIS: tuple[str, ...] = ("grok", "agy", "opencode", "omp", "pi", "qwen")

CLI_SIDEBAR: dict[str, dict[str, str]] = {
    "grok": {
        "name": "Grok",
        "specialty": "xAI Grok CLI",
        "description": "Host grok CLI in one-shot print mode (--always-approve).",
        "color": "#22c55e",
        "icon": "⚡",
    },
    "agy": {
        "name": "Agy",
        "specialty": "Agy CLI",
        "description": "Host agy CLI in one-shot print mode (auto-approve tools).",
        "color": "#38bdf8",
        "icon": "🛠️",
    },
    "opencode": {
        "name": "OpenCode",
        "specialty": "OpenCode CLI",
        "description": "Host opencode CLI one-shot (run + explicit --model).",
        "color": "#a78bfa",
        "icon": "⌨️",
    },
    "omp": {
        "name": "OMP",
        "specialty": "Oh My Pi CLI",
        "description": "Host omp CLI one-shot (-p + litellm/orchestration).",
        "color": "#f472b6",
        "icon": "◈",
    },
    "pi": {
        "name": "Pi",
        "specialty": "Pi CLI",
        "description": "Host pi CLI in non-interactive print mode (-p).",
        "color": "#fb923c",
        "icon": "π",
    },
    "qwen": {
        "name": "Qwen",
        "specialty": "Qwen Code CLI",
        "description": "Host qwen CLI one-shot (JSON event array, --yolo auto-approve).",
        "color": "#14b8a6",
        "icon": "◈",
    },
}



# #855 slice D — model-cluster helpers moved verbatim to swarm.core.cli.models (patch-safe: bodies resolve catalog references through a late-bound handle; names are rebound here so the import surface is unchanged).
from swarm.core.cli import models as _cli_models  # noqa: E402

cli_traits = _cli_models.cli_traits
has_native_consensus = _cli_models.has_native_consensus
native_consensus_flags = _cli_models.native_consensus_flags
with_native_consensus = _cli_models.with_native_consensus
list_models_argv = _cli_models.list_models_argv
has_list_models = _cli_models.has_list_models
model_traits = _cli_models.model_traits
_model_flag_insert_at = _cli_models._model_flag_insert_at
apply_model = _cli_models.apply_model
with_model = _cli_models.with_model
LIST_MODELS = _cli_models.LIST_MODELS
LIST_MODELS_TIMEOUT = _cli_models.LIST_MODELS_TIMEOUT
MODEL_FLAG = _cli_models.MODEL_FLAG
CLI_MODELS = _cli_models.CLI_MODELS
MODEL_TRAITS = _cli_models.MODEL_TRAITS

def listed_cli_specs() -> list[dict[str, Any]]:
    """Host grok/agy as Agent Router sidebar specs (OpenMausBot-style).

    Always returned so the sidebar does not require a designer POST. A later
    ``kind=cli`` design with the same ``agent_id`` may overlay these.
    """
    specs: list[dict[str, Any]] = []
    for name in SIDEBAR_CLIS:
        if name not in CATALOG:
            continue
        meta = CLI_SIDEBAR.get(name) or {}
        specs.append({
            "agent_id": name,
            "name": meta.get("name") or name.title(),
            "kind": "cli",
            "agent_type": "cli",
            "cli": name,
            "specialty": meta.get("specialty") or f"{name} CLI",
            "description": meta.get("description") or f"Host {name} CLI, one-shot print mode.",
            "color": meta.get("color") or "#6366f1",
            "icon": meta.get("icon") or "⌨️",
            "group": "tools",
            "type": "specialist",
        })
    return specs


def rail_cli_agent_id(cli_name: str) -> str:
    """Grok-rail id: grok → grok_agent."""
    return f"{cli_name}_agent"


def cli_from_rail_id(agent_id: str | None) -> str | None:
    """Map grok_agent / grok / litellm-pi / <prefix>-<cli> → catalog CLI name, or None."""
    raw = str(agent_id or "").strip().lower()
    if not raw:
        return None
    from swarm.core.cli_remote import CLI_ALIASES

    if raw.endswith("_agent"):
        candidate = raw[: -len("_agent")]
        if candidate in CATALOG:
            return candidate
        mapped = CLI_ALIASES.get(candidate)
        if mapped and mapped in CATALOG:
            return mapped
    if raw in CATALOG:
        return raw

    aliased = CLI_ALIASES.get(raw)
    if aliased and aliased in CATALOG:
        return aliased
    for delim in ("-", "_"):
        if delim in raw:
            suffix = raw.rsplit(delim, 1)[-1]
            if suffix in CATALOG:
                return suffix
            mapped = CLI_ALIASES.get(suffix)
            if mapped and mapped in CATALOG:
                return mapped
    return None


# CLI-first product modes (#151) — RETIRED (#736): surfaces are **always on
# if configured**. The Settings toggle was unreliable (#594, #710) and the
# synthetic gating only produced "hidden by product modes" noise. Nothing is
# advertised or filtered any more; legacy configs carrying
# ``settings.product_modes`` still parse (the key is advisory and ignored).
# Full contract archived in docs/archive/product-modes.md (PR #955).
def _discovered_default_cli(discovered: list[str]) -> str:
    """First discovered catalog CLI; never invent a missing executable."""
    found = [name for name in discovered if name in CATALOG]
    for name in SIDEBAR_CLIS:
        if name in found:
            return name
    return found[0] if found else ""


def rail_cli_rows(
    config: dict[str, Any] | None = None,
    *,
    discovered: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Named kind rows for the conversation rail.

    ``cli`` is a PATH-discovered catalog name or empty — never a fake grok/pi
    that is not installed. Host CLIs are picked from the chat CLI dropdown,
    not as four separate rail ids. ``grok_agent``-style ids still map via
    :func:`cli_from_rail_id` for old bookmarks. Both seats always ship
    (#736 always-on-if-configured).
    """
    if discovered is None:
        discovered = discover_host_clis()
    default_cli = _discovered_default_cli(discovered)
    # #736: always-on-if-configured — the former ``modes["cli"]`` /
    # ``modes["api"]`` gates are gone; both rows always ship.
    rows: list[dict[str, Any]] = [
        {
            "id": "cli_agent",
            "object": "cli.agent",
            "name": "cli_agent",
            "cli": default_cli,
            "kind": "cli",
            "description": "Host CLI — pick a discovered catalog CLI in the header.",
            "installed": bool(default_cli),
        },
        {
            "id": "api_agent",
            "object": "cli.agent",
            "name": "api_agent",
            "cli": "",
            "kind": "api",
            "description": "LiteLLM — pick a profile (orchestration, auxiliary, …).",
            "installed": True,
        },
    ]
    return rows


def session_policy(name: str) -> dict[str, Any] | None:
    """How ``name`` names and resumes a CLI session, or None if undocumented."""
    entry = SESSION.get(name)
    return _deepcopy(entry) if entry is not None else None


def smoke_flags(name: str) -> list[str]:
    """Argv injected only on smoke/verify — never on the production catalog cmd."""
    flags = SMOKE_FLAGS.get(name) or []
    return list(flags) if all(isinstance(p, str) for p in flags) else []


def apply_smoke_flags(name: str, cmd: list[str]) -> list[str]:
    """Copy ``cmd`` and insert smoke-only flags before ``--`` when present."""
    extra = [flag for flag in smoke_flags(name) if flag and flag not in cmd]
    if not extra:
        return list(cmd)
    if "--" in cmd:
        index = cmd.index("--")
        return [*cmd[:index], *extra, *cmd[index:]]
    return [*cmd, *extra]


def catalog_names() -> list[str]:
    """Names of every CLI the catalog knows about (sorted)."""
    return sorted(CATALOG)


KNOWN_CLIS: tuple[str, ...] = tuple(catalog_names())


def configured_cli_names(config: dict[str, Any] | None = None) -> list[str]:
    """Names the user (or ``--init --write``) added to ``cli_agents``.

    Empty until add. PATH-discovered binaries are **not** listed here.
    """
    raw = (config or {}).get("cli_agents") or {}
    if not isinstance(raw, dict):
        return []
    return sorted({str(name).strip() for name in raw if str(name).strip()})


def discover_host_clis() -> list[str]:
    """Catalog CLIs whose executable is on PATH or a known user-local dir.

    PATH / ``stat`` only. Does not run the binary, does not probe auth, and
    does not touch the network. Unauthenticated installs still appear.
    """
    return installed_catalog_clis()


def suggested_cli_agents(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Discovered catalog CLIs that are not yet in ``cli_agents`` (one-click add)."""
    return suggest_unconfigured(configured_cli_names(config), installed_only=True)


def cli_agents_catalog_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public ``GET /v1/cli-agents/`` body: configured vs discovered candidates.

    ``known`` / ``clis`` is the full catalog (documentation, not the start set).
    ``configured`` is opt-in (empty until add). ``discovered`` / ``installed``
    are the PATH seed and the CLI-first starting set (#149). ``suggestions`` is
    discovered-minus-configured with a ready catalog entry for one-click add.
    ``modes`` is the always-on advertisement (#736): legacy consumers reading
    the key see every surface enabled.
    Never includes secrets. Never invents a missing executable.
    """
    configured = configured_cli_names(config)
    discovered = discover_host_clis()
    suggestions = suggested_cli_agents(config)
    default_cli = next((name for name in configured if name), "") or _discovered_default_cli(
        discovered
    )
    return {
        "clis": catalog_names(),
        "known": list(KNOWN_CLIS),
        "configured": configured,
        "discovered": discovered,
        "installed": discovered,
        "suggestions": suggestions,
        "default_cli": default_cli,
        # #736: no ``modes`` advertisement — surfaces are always on if
        # configured; the retired key is not sent (legacy clients treat a
        # missing key as all-on).
        "native_consensus": dict(NATIVE_CONSENSUS),
        "catalog": {name: catalog_entry(name) for name in catalog_names()},
        "rail": rail_cli_rows(config, discovered=discovered),
        "list_models": {
            name: list_models_argv(name)
            for name in catalog_names()
            if has_list_models(name)
        },
        "list_sessions": list_sessions_catalog(),
        "slash_commands": cli_slash_commands_payload(),
        "cli_compact": cli_compact_payload(),
        "seat_capabilities": seat_capabilities_payload(),
        "remote": _remote_catalog_payload(),
        "remote_boxes": _remote_boxes_payload(config),
    }


def _remote_catalog_payload() -> dict[str, dict[str, Any]]:
    from swarm.core.cli_remote import remote_catalog

    return remote_catalog()


def _remote_boxes_payload(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    from swarm.core.cli_remote import list_remote_boxes, public_remote_endpoint

    boxes = list_remote_boxes(config)
    rows: list[dict[str, Any]] = []
    for box_id, spec in sorted(boxes.items()):
        public = public_remote_endpoint(spec) or {}
        public["id"] = box_id
        rows.append(public)
    return rows


def installed_catalog_clis() -> list[str]:
    """Catalog CLIs whose executable resolves on this host (sorted)."""
    return [n for n in catalog_names() if which_cli(CATALOG[n]["cmd"][0])]


def _executable_on_path(exe: str) -> bool:
    """True when ``exe`` is an existing path or resolves on PATH."""
    if not exe:
        return False
    if os.path.sep in exe:
        return os.path.isfile(exe) and os.access(exe, os.X_OK)
    return which_cli(exe) is not None


def installed_host_clis(config: dict[str, Any] | None = None) -> list[str]:
    """CLIs available on this host: catalog-on-PATH plus configured-on-PATH.

    The static catalog is only grok/claude/gemini/codex/opencode. A custom
    ``cli_agents`` entry (for example ``antigravity``) is included when its
    ``cmd[0]`` or configured name resolves on PATH.
    """
    found: set[str] = set(installed_catalog_clis())
    raw_agents = (config or {}).get("cli_agents") or {}
    if isinstance(raw_agents, dict):
        for name, entry in raw_agents.items():
            key = str(name).strip()
            if not key:
                continue
            exe = key
            if isinstance(entry, dict):
                cmd = entry.get("cmd") or []
                if isinstance(cmd, (list, tuple)) and cmd:
                    exe = str(cmd[0])
            if _executable_on_path(exe) or (exe != key and _executable_on_path(key)):
                found.add(key)
    return sorted(found)


def build_starter_config(installed: list[str] | None = None) -> dict[str, Any]:
    """A complete, ready-to-run swarm_config for the installed catalog CLIs.

    Wires every composition mode (cli_fusion / cli_orchestrator / cli_map) over
    whatever catalog CLIs are present. The single-agent default and the
    judge/router/reducer/planner roles prefer ``grok`` (then ``claude``, then the
    first available); the panels include *every* installed CLI, so the other
    agents are only engaged for the multi-agent paths. Includes a default ``llm``
    block so the config passes validation. Historically it also carried
    CLI-first ``settings.product_modes`` (#151); that gating is retired (#736)
    so starter configs no longer advertise the key. When nothing is installed,
    returns just the llm + empty ``cli_agents`` — never invents absent CLIs (#149).
    """
    if installed is None:
        installed = installed_catalog_clis()
    agents = {n: catalog_entry(n) for n in installed if n in CATALOG}
    names = sorted(agents)
    cfg: dict[str, Any] = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "${OPENAI_API_KEY}",
            }
        },
        "cli_agents": agents,
    }
    if names:
        primary = next((c for c in ("grok", "claude") if c in names), names[0])
        cfg["cli_fusion"] = {
            "default_cli": primary,
            "default_preset": "all",
            "show_analysis": True,
            "presets": {"all": {"panel": names, "judge": primary}},
        }
        cfg["cli_orchestrator"] = {"router": primary, "panel": names, "judge": primary}
        cfg["cli_map"] = {"planner": primary, "workers": names, "reducer": primary}
    return cfg


def catalog_entry(name: str) -> dict[str, Any] | None:
    """A copy of the catalog config for ``name`` (None if unknown)."""
    entry = CATALOG.get(name)
    return _deepcopy(entry) if entry is not None else None


def executable_for(name: str) -> str | None:
    """The executable (``cmd[0]``) a catalog entry runs, or None if unknown."""
    entry = CATALOG.get(name)
    return entry["cmd"][0] if entry else None


def suggest_unconfigured(
    configured_names: list[str] | None,
    *,
    installed_only: bool = True,
) -> dict[str, dict[str, Any]]:
    """Return ``{name: config}`` for catalog CLIs not already configured.

    Skips any name already present in ``configured_names``. When
    ``installed_only`` (default), also skips CLIs whose executable does not
    resolve on PATH — so suggestions are actionable on *this* host.
    """
    configured = set(configured_names or ())
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in CATALOG.items():
        if name in configured:
            continue
        if installed_only and which_cli(cfg["cmd"][0]) is None:
            continue
        out[name] = _deepcopy(cfg)
    return out


def _deepcopy(cfg: dict[str, Any]) -> dict[str, Any]:
    """Shallow structure with copied list/dict values (configs are 1 level deep)."""
    return {
        k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
        for k, v in cfg.items()
    }
