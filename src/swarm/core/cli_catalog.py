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

Known catalog names (agy is the antigravity CLI): grok, agy, claude, gemini,
codex, opencode, pi, omp, qwen.

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

# User-local bins Daphne often misses when started with PATH=/usr/bin:/bin.
_EXTRA_BIN_REL = (
    (".local", "bin"),
    ("bin",),
    (".grok", "bin"),
    (".npm-global", "bin"),
    (".local", "share", "pnpm"),
)


def extra_cli_path_dirs() -> list[str]:
    """User and nvm bin dirs that commonly hold grok/agy/pi/opencode."""
    home = os.path.expanduser("~")
    dirs: list[str] = []
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
    "omp": {
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 2,  # after `omp -p` → `omp -p --resume <id> …`
        "resume_strip": ["--no-session", "--continue", "-c"],
        "session_id_paths": [".session", ".id"],
        "list_capability": LIST_CAPABILITY_PASTE_ONLY,
        "notes": (
            "omp -p --resume <id|path> (also -r). --continue/-c is last session — "
            "do not use it here. Smoke/verify injects --no-session (ephemeral); "
            "production cmd does not. List is paste-only — no verified "
            "non-interactive list argv."
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


def _cli_agent_entry(name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """``cli_agents.<name>`` dict from config, or empty."""
    raw_agents = (config or {}).get("cli_agents") or {}
    if not isinstance(raw_agents, dict):
        return {}
    entry = raw_agents.get(name)
    return entry if isinstance(entry, dict) else {}


def list_sessions_argv(name: str, config: dict[str, Any] | None = None) -> list[str] | None:
    """Copy of a non-interactive list-sessions argv, or None if this CLI cannot list.

    Config ``cli_agents.<name>.list_argv`` wins over the catalog (fixtures).
    An empty list in config disables a catalogued argv (honest paste-only).
    """
    entry = _cli_agent_entry(name, config)
    if "list_argv" in entry:
        argv = entry.get("list_argv")
        if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
            return list(argv)
        return None
    policy = session_policy(name) or {}
    argv = policy.get("list_argv")
    if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
        return list(argv)
    return None


def list_sessions_store(name: str, config: dict[str, Any] | None = None) -> str | None:
    """Provider-store kind (e.g. ``agy_conversations``), or None.

    Config ``cli_agents.<name>.list_store`` wins. Empty string disables the
    catalogued store. When ``list_argv`` is set, the argv is preferred.
    """
    if list_sessions_argv(name, config) is not None:
        return None
    entry = _cli_agent_entry(name, config)
    if "list_store" in entry:
        raw = entry.get("list_store")
        kind = str(raw or "").strip()
        return kind or None
    policy = session_policy(name) or {}
    raw = policy.get("list_store")
    kind = str(raw or "").strip()
    return kind or None


def list_sessions_store_dir(name: str, config: dict[str, Any] | None = None) -> str | None:
    """Expanded directory for a provider session store, or None."""
    if list_sessions_store(name, config) is None:
        return None
    entry = _cli_agent_entry(name, config)
    raw = entry.get("list_store_dir")
    if raw is None:
        policy = session_policy(name) or {}
        raw = policy.get("list_store_dir")
    if raw:
        return os.path.expanduser(str(raw))
    env = os.environ.get("SWARM_AGY_CONVERSATIONS_DIR", "").strip()
    if env:
        return os.path.expanduser(env)
    if list_sessions_store(name, config) == AGY_CONVERSATIONS_STORE:
        return os.path.expanduser(DEFAULT_AGY_CONVERSATIONS_DIR)
    return None


def list_capability(name: str, config: dict[str, Any] | None = None) -> str:
    """``works`` | ``paste-only`` | ``unsupported`` for this CLI's session list."""
    entry = _cli_agent_entry(name, config)
    override = entry.get("list_capability")
    if isinstance(override, str) and override in LIST_CAPABILITIES:
        return override
    if can_list_sessions(name, config):
        return LIST_CAPABILITY_WORKS
    policy = session_policy(name) or {}
    if policy.get("resume_argv"):
        return LIST_CAPABILITY_PASTE_ONLY
    documented = policy.get("list_capability")
    if isinstance(documented, str) and documented in LIST_CAPABILITIES:
        return documented
    return LIST_CAPABILITY_UNSUPPORTED


def can_list_sessions(name: str, config: dict[str, Any] | None = None) -> bool:
    """True when a real list argv or provider store is configured."""
    return list_sessions_argv(name, config) is not None or list_sessions_store(name, config) is not None


def export_sessions_argv(name: str, config: dict[str, Any] | None = None) -> list[str] | None:
    """Non-interactive transcript-export argv, or None.

    Config ``cli_agents.<name>.export_argv`` wins. An empty list disables a
    catalogued argv. Catalog CLIs ship no export argv (honest summary inject).
    ``{session_id}`` is replaced by the caller when invoking.
    """
    entry = _cli_agent_entry(name, config)
    if "export_argv" in entry:
        argv = entry.get("export_argv")
        if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
            return list(argv)
        return None
    policy = session_policy(name) or {}
    argv = policy.get("export_argv")
    if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
        return list(argv)
    return None


def export_capability(name: str, config: dict[str, Any] | None = None) -> str:
    """``transcript`` | ``summary`` | ``none`` for hop import from this CLI."""
    entry = _cli_agent_entry(name, config)
    override = entry.get("export_capability")
    if isinstance(override, str) and override in EXPORT_CAPABILITIES:
        return override
    if export_sessions_argv(name, config) is not None:
        return EXPORT_CAPABILITY_TRANSCRIPT
    policy = session_policy(name) or {}
    documented = policy.get("export_capability")
    if isinstance(documented, str) and documented in EXPORT_CAPABILITIES:
        return documented
    if session_policy(name) or _cli_agent_entry(name, config):
        return EXPORT_CAPABILITY_SUMMARY
    return EXPORT_CAPABILITY_NONE


def can_export_transcript(name: str, config: dict[str, Any] | None = None) -> bool:
    """True when a real export argv is configured (fixture or verified CLI)."""
    return export_sessions_argv(name, config) is not None


def list_sessions_catalog() -> dict[str, dict[str, Any]]:
    """Machine-readable list/resume/export table for every catalogued CLI."""
    out: dict[str, dict[str, Any]] = {}
    for name in catalog_names():
        policy = session_policy(name) or {}
        out[name] = {
            "capability": list_capability(name),
            "list_argv": list_sessions_argv(name),
            "list_store": list_sessions_store(name),
            "resume_argv": list(policy["resume_argv"]) if policy.get("resume_argv") else None,
            "export_capability": export_capability(name),
            "export_argv": export_sessions_argv(name),
        }
    return out


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


def cli_traits(name: str) -> dict[str, float] | None:
    """Default capability traits for a known CLI, or None if unknown."""
    t = CLI_TRAITS.get(name)
    return dict(t) if t is not None else None


def has_native_consensus(name: str) -> bool:
    """True when this CLI has a built-in consensus/heavy mode the catalog knows."""
    return name in NATIVE_CONSENSUS


def native_consensus_flags(name: str, n: int = 2) -> list[str] | None:
    """argv to append to enable ``name``'s built-in consensus for N candidates, or None."""
    tmpl = NATIVE_CONSENSUS.get(name)
    if not tmpl:
        return None
    count = str(max(2, int(n)))
    return [count if part == "{n}" else part for part in tmpl]


def with_native_consensus(name: str, n: int = 2) -> dict[str, Any] | None:
    """A catalog entry for ``name`` with its built-in consensus mode enabled.

    Returns None if the CLI is unknown or has no native consensus flag.
    """
    entry = catalog_entry(name)
    flags = native_consensus_flags(name, n)
    if entry is None or flags is None:
        return None
    entry["cmd"] = list(entry["cmd"]) + flags
    return entry


# Non-interactive argv that lists models each catalog CLI can actually run.
# Sourced from each CLI's ``--help`` / official docs (not a vendor marketing
# list). Probe via :mod:`swarm.core.cli_models` — never prompts, always times
# out. antigravity is omitted until it is wired into ``CATALOG``.
#
#   grok      ``grok models``           (xAI CLI reference)
#   claude    ``claude models``         (same shape as grok/opencode; older
#                                       builds fail the probe → empty+warning)
#   gemini    ``gemini --list-models``  (JSON; early-exit, no REPL)
#   codex     ``codex debug models``    (raw catalog JSON)
#   opencode  ``opencode models``       (already documented in this catalog)
#   agy       ``agy models``            (tab-separated id<TAB>label lines; a
#                                       spinner banner goes to stderr, stdout
#                                       parses as plain lines)
# qwen: deliberately absent — its current build rejects ``--list-models``
# ("Unknown arguments") and has no models subcommand, so there is nothing
# honest to probe; dropdown falls back to the empty + warning path.
LIST_MODELS: dict[str, list[str]] = {
    "grok": ["grok", "models"],
    "claude": ["claude", "models"],
    "gemini": ["gemini", "--list-models"],
    "codex": ["codex", "debug", "models"],
    "opencode": ["opencode", "models"],
    "agy": ["agy", "models"],
}

# List-models probes must stay cheap and never hang a Settings / #358 caller.
LIST_MODELS_TIMEOUT = 15.0


def list_models_argv(name: str) -> list[str] | None:
    """Copy of the list-models argv for ``name``, or None if unknown."""
    argv = LIST_MODELS.get(name)
    return list(argv) if argv is not None else None


def has_list_models(name: str) -> bool:
    """True when the catalog documents a list-models probe for ``name``."""
    return name in LIST_MODELS


# Flag each CLI uses to pin a specific model, so callers can request a
# particular tier (e.g. gemini's pro vs. flash). Only flags verified against the
# installed CLI version belong here; omit a CLI rather than guess.
MODEL_FLAG: dict[str, str] = {
    "gemini": "-m",        # verified live (gemini 0.45): -m gemini-3-pro-preview
    "claude": "--model",   # claude -p --model <name>
    "opencode": "--model", # opencode run --model <name>
    "omp": "--model",      # omp -p --model <provider/id>
    "agy": "--model",      # agy --model <name>
    "grok": "-m",          # grok -m/--model <id> (verified: grok-4.6, grok-4.5)
    "qwen": "-m",          # qwen -m/--model <id> (verified live: gateway slug auxiliary)
}

# Suggested model ids for the Agent Router CLI-model dropdown. The UI always
# offers a custom string on top of these; they are starting points, not a
# live catalog from the host CLI.
CLI_MODELS: dict[str, list[str]] = {
    "grok": ["grok-4.6", "grok-4.5"],
    "agy": [
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
        "gemini-3.1-pro-high",
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
        "gpt-oss-120b-medium",
    ],
    "gemini": ["gemini-3-flash-preview", "gemini-3-pro-preview"],
    "claude": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
    "opencode": ["litellm/orchestration"],
    "omp": ["litellm/orchestration"],
}


# Default capability traits (0..1) per known MODEL, keyed by model id. These
# refine the per-provider CLI_TRAITS default: a provider runs many models (e.g.
# gemini flash vs pro) with very different intelligence/speed/cost. Illustrative
# starting points — users override per-model via config. cost = cheapness.
MODEL_TRAITS: dict[str, dict[str, float]] = {
    "gemini-3-pro-preview":   {"intelligence": 0.92, "speed": 0.35, "cost": 0.30},
    "gemini-3-flash-preview": {"intelligence": 0.62, "speed": 0.95, "cost": 0.92},
    "claude-opus-4-8":        {"intelligence": 0.98, "speed": 0.45, "cost": 0.20},
    "claude-sonnet-4-6":      {"intelligence": 0.90, "speed": 0.70, "cost": 0.55},
    "claude-haiku-4-5":       {"intelligence": 0.70, "speed": 0.92, "cost": 0.85},
}


def model_traits(model: str) -> dict[str, float] | None:
    """Default capability traits for a known model id, or None if unknown."""
    t = MODEL_TRAITS.get(model)
    return dict(t) if t is not None else None


_PROMPT_FLAG_TOKENS = frozenset({"-p", "--print", "--prompt", "--single"})


def _model_flag_insert_at(cmd: list[str]) -> int:
    """Index to insert a model flag — before ``-p`` / ``{prompt}``, never after."""
    if "--" in cmd:
        return cmd.index("--")
    for i, part in enumerate(cmd):
        if part in _PROMPT_FLAG_TOKENS:
            return i
        if part.startswith(("-p=", "--print=", "--prompt=", "--single=")):
            return i
        if "{prompt}" in part:
            return i
    return len(cmd)


def apply_model(entry: dict[str, Any], name: str, model: str) -> dict[str, Any]:
    """Return a copy of ``entry`` with ``name``'s model flag set to ``model``.

    Replaces an already-pinned model (e.g. opencode's default) rather than
    duplicating it; a no-op for CLIs with no known model flag. New flags sit
    before ``-p`` / ``{prompt}`` so the prompt cannot swallow them.
    """
    entry = _deepcopy(entry)
    flag = MODEL_FLAG.get(name)
    if flag is None:
        return entry
    cmd = list(entry.get("cmd") or [])
    if not cmd:
        return entry  # no command to pin a model on; don't fabricate a flag-only cmd
    if flag in cmd:
        i = cmd.index(flag)
        nxt = cmd[i + 1] if i + 1 < len(cmd) else None
        if nxt is not None and nxt != "--":
            cmd[i + 1] = model
        elif nxt == "--":
            cmd.insert(i + 1, model)
        else:
            cmd.append(model)
    else:
        insert_at = _model_flag_insert_at(cmd)
        cmd[insert_at:insert_at] = [flag, model]
    entry["cmd"] = cmd
    return entry


def with_model(name: str, model: str, *, timeout: int | None = None) -> dict[str, Any] | None:
    """A catalog entry for ``name`` pinned to a specific ``model``.

    Pro/heavy tiers (notably ``gemini-3-pro-preview``) think for much longer than
    the flash default, so pass a larger ``timeout`` when selecting one. Returns
    None for an unknown CLI; returns the entry unchanged if the catalog has no
    known model flag for it.
    """
    base = catalog_entry(name)
    if base is None:
        return None
    entry = apply_model(base, name, model)
    if timeout is not None:
        entry["timeout"] = timeout
    return entry


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
    """Map grok_agent / grok → catalog CLI name, or None."""
    raw = str(agent_id or "").strip().lower()
    if not raw:
        return None
    if raw.endswith("_agent"):
        raw = raw[: -len("_agent")]
    if raw in CATALOG:
        return raw
    return None


def rail_cli_rows() -> list[dict[str, Any]]:
    """Named kind rows for the conversation rail: ``cli_agent`` + ``api_agent``.

    Host CLIs (grok/agy/opencode/pi) are picked from the chat CLI dropdown, not
    as four separate rail ids. ``grok_agent``-style ids still map via
    :func:`cli_from_rail_id` for old bookmarks.
    """
    default_cli = next(
        (name for name in SIDEBAR_CLIS if name in CATALOG and which_cli(CATALOG[name]["cmd"][0])),
        SIDEBAR_CLIS[0] if SIDEBAR_CLIS else "grok",
    )
    installed = any(
        name in CATALOG and which_cli(CATALOG[name]["cmd"][0]) for name in SIDEBAR_CLIS
    )
    return [
        {
            "id": "cli_agent",
            "object": "cli.agent",
            "name": "cli_agent",
            "cli": default_cli,
            "kind": "cli",
            "description": "Host CLI — pick grok, agy, opencode, or pi in the header.",
            "installed": installed,
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

    ``configured`` is opt-in (empty until add). ``discovered`` / ``installed``
    are the PATH seed. ``suggestions`` is discovered-minus-configured with a
    ready catalog entry for one-click add. Never includes secrets.
    """
    configured = configured_cli_names(config)
    discovered = discover_host_clis()
    suggestions = suggested_cli_agents(config)
    return {
        "clis": catalog_names(),
        "known": list(KNOWN_CLIS),
        "configured": configured,
        "discovered": discovered,
        "installed": discovered,
        "suggestions": suggestions,
        "default_cli": next((name for name in configured if name), ""),
        "native_consensus": dict(NATIVE_CONSENSUS),
        "catalog": {name: catalog_entry(name) for name in catalog_names()},
        "rail": rail_cli_rows(),
        "list_models": {
            name: list_models_argv(name)
            for name in catalog_names()
            if has_list_models(name)
        },
        "list_sessions": list_sessions_catalog(),
    }


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
    block so the config passes validation. When nothing is installed, returns
    just the llm + an empty ``cli_agents`` block.
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
