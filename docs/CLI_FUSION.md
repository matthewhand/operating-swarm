# CLI Fusion — your installed agentic CLIs, behind one OpenAI endpoint

Most agentic CLIs (`claude`, `gemini`, `codex`, `opencode`, `omp`, …) are powerful but
**not** OpenAI-compatible, and each only orchestrates its own model's subagents.
Open Swarm's CLI-fusion blueprints turn whatever CLIs you already have installed
into composable, API-addressable subagents:

- **`cli_agent`** — expose a *single* CLI over `/v1/chat/completions`.
- **`cli_fusion`** — fan a prompt to a *panel* of CLIs in parallel, have a
  *judge* compare their answers, *synthesize* a single best answer, and
  optionally iterate a bounded **master plan** (the judge decides the next step).

Inspired by [OpenRouter Fusion](https://openrouter.ai/docs/guides/features/plugins/fusion),
except the panelists are *your local toolbox*, not a fixed hosted set — and they
can use any tools their own CLI provides (MCP servers, file access, web, …).

Any OpenAI client (Open WebUI, Cursor, the OpenAI SDK, a shell script) talks to
them with no changes — just point at the Open Swarm API and pick the model name.

---

## Quick start (60 seconds)

```bash
pip install open-swarm

# Optional: write every discovered CLI into swarm_config (explicit accept).
# Fresh install stays empty until you add from Settings suggestions or here:
swarm-cli cli-agents --init --write

export OPENAI_API_KEY=sk-...          # for the llm block
swarm-cli cli-agents                  # configured list + PATH suggestions (no auth)
swarm-cli cli-agents --smoke          # confirm they answer non-interactively
```

**Opt-in catalog (REQ-157 / #565).** `cli_agents` starts **empty**. On startup
(and `GET /v1/cli-agents/`) Open Swarm **discovers** known CLIs on PATH /
user-local bins **without an auth check**: `grok`, `agy` (antigravity),
`claude`, `gemini`, `codex`, `opencode`, `omp`, `pi`. Those appear as **Suggested**
one-click add in Settings (same shape as remotes). Adding persists; removing
clears the configured list (the binary may still be rediscovered as a
candidate). The chat CLI dropdown lists configured names only.

`--init --write` is the explicit "accept all discovered" path: it writes
`cli_agents` + `cli_fusion` + `cli_orchestrator` + `cli_map`. Then start the
API (`swarm-api` / `docker compose up`) and call any mode by `model` name. To
wire it by hand instead:

1. Add a `cli_agents` block (and optionally `cli_fusion`) to your
   `~/.config/swarm/swarm_config.json` — see [the example](#full-example) below.
2. Make sure the CLIs are installed and **logged in** on the host (each CLI
   authenticates itself; Open Swarm does not proxy their credentials).
3. Call the API:

```bash
# Single CLI:
curl -sf http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${API_AUTH_TOKEN}" -H "Content-Type: application/json" \
  -d '{"model":"cli_agent","messages":[{"role":"user","content":"Explain this repo"}],
       "params":{"cli":"claude"}}' | jq -r '.choices[0].message.content'

# Fusion panel:
curl -sf http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${API_AUTH_TOKEN}" -H "Content-Type: application/json" \
  -d '{"model":"cli_fusion","messages":[{"role":"user","content":"Design a rate limiter"}],
       "params":{"preset":"general-high","show_analysis":true}}' | jq -r '.choices[0].message.content'
```

`params` is the standard Open Swarm per-request field; OpenAI SDKs send it via
`extra_body={"params": {...}}`.

### Autodiscovery

See which of your **configured** CLIs are installed, and which catalog CLIs
were **discovered** on PATH (no auth probe unless you pass `--check-auth`):

```bash
swarm-cli cli-agents               # configured status + PATH suggestions (fast, no auth)
swarm-cli cli-agents --check-auth  # also probe each configured CLI's auth_check
swarm-cli cli-agents --suggest     # print the same suggestion block (also on by default)
swarm-cli cli-agents --smoke       # run one trivial one-shot per configured CLI
swarm-cli cli-agents --json        # includes configured, discovered, suggestions
swarm-cli cli-agents --list-models # live {cli, models: [...]} per catalog CLI (REQ-44)
swarm-cli cli-agents --list-models --cli grok
swarm-cli list-models grok         # same probe; omit the name to probe every catalog CLI
swarm-cli cli-agents --config ./swarm_config.json
```

`--json` emits one JSON object on stdout (logs stay on stderr, so `| jq` is
clean): `{"agents": [...], "configured": [...], "discovered": [...],
"suggestions": {...}}`, plus `"smoke"` when `--smoke` is set. Discovery never
runs `auth_check` unless you pass `--check-auth`. Use it to wire Settings /
automation.

`--smoke` is the counterpart to `--check-auth`: auth tells you the CLI is logged
in; smoke tells you its configured `cmd` actually **returns** in non-interactive
mode instead of hanging on a prompt. Each probe runs one trivial one-shot
(`status` of `ok` / `hang` / `error` / `not_installed`) — a `hang` almost always
means a missing or wrong non-interactive/auto-approve flag. Unlike auth, the
smoke probe invokes the model once per CLI, so it costs a little quota; it's
opt-in for that reason.

`--suggest` checks a built-in catalog of known-good adapter configs against your
host and prints a ready-to-paste `cli_agents` block for every supported CLI
(`claude`, `gemini`, `codex`, `opencode`, `omp`) that is installed but not yet in your
config — so getting started is "install the CLI, run `--suggest`, paste". The
suggested flags track each CLI's non-interactive + auto-approve mode; verify them
against the CLI's own `--help`, since flags drift by version.

```
AGENT            STATUS     MODE       EXECUTABLE
claude           installed  write      /home/you/.local/bin/claude
codex            missing    write      -
gemini           installed  write      /home/you/.nvm/.../gemini
3/4 configured CLI agents installed on this host.
```

---

## Config: `cli_agents`

Each entry declares how to run one CLI **one-shot**. The command is an argv list
executed directly (no shell), so the prompt is never interpolated into a shell
string.

| Key | Type | Meaning |
|---|---|---|
| `cmd` | list[str] | argv. Put `{prompt}` where the prompt goes; `{workdir}` for the working dir. |
| `prompt_mode` | `"arg"` \| `"stdin"` | `arg` (default) substitutes `{prompt}` into `cmd`; `stdin` pipes it to stdin. |
| `parse` | `"text"` \| `"json:<dotpath>"` | `text` (default) = trimmed stdout. `json:.result` parses JSON and extracts a dotted path (list indices allowed, e.g. `json:.choices.0.message.content`). |
| `cwd` | str | Working directory template (`{workdir}` allowed). Defaults to the per-request `workdir` or the server CWD. |
| `env` | dict | Extra env vars merged onto the child's environment. |
| `env_allowlist` | list[str] \| null | **null (default):** child inherits the full environment (convenient, but every panelist sees every API key). **Set it:** child gets only these vars plus essentials (`PATH`, `HOME`, …) — isolates each CLI's secrets. |
| `timeout` | number | Seconds before the CLI (and its whole process group) is killed. Default 180. |
| `mode` | str | Free-text label documenting safety posture (`"readonly"`, `"write"`). Advisory. |
| `auth_check` | list[str] | Optional argv probe for `swarm-cli cli-agents --check-auth`. Exit 0 ⇒ authenticated. Should be cheap and not consume quota (capped at 30s). |
| `consensus` | bool \| list[str] \| dict | Designate this agent as a **consensus agent** — calling it runs a panel, not a single call. `true` ⇒ all available CLIs; a list ⇒ a preferred whitelist (falls back to all-available if it matches nothing); `{"panel":[…],"judge":"…"}` ⇒ explicit. See [Consensus modes](BLUEPRINT_LIBRARY.md#consensus-modes-a-second-axis--partly-built-partly-roadmap). |
| `resume_argv` | list[str] \| null | Extra argv inserted when a stored CLI session id exists. Use `{session_id}`. `null` uses the catalog policy for this name; `[]` means this CLI cannot resume. |
| `resume_insert` | int \| null | Index in argv at which `resume_argv` is inserted (catalog default `1`; `codex` uses `2` so it becomes `codex exec resume <id>`). |
| `session_id_paths` | list[str] \| null | JSON dotted paths to capture a session id from stdout (e.g. `.session_id`). |

> ⚠️ **Exact flags and JSON shapes vary by CLI version.** The snippets below are
> starting points — run the CLI's `--help` and confirm its non-interactive flag,
> its auto-approve flag, and (if using `json:` parse) the actual key in its JSON
> output. When in doubt, use `parse: "text"`.

### Non-interactive mode is the whole game

The adapter runs each CLI with stdin closed and a timeout. The flag that makes or
breaks a run is the **auto-approve** one: in non-interactive mode an agentic CLI
will otherwise stop mid-task to ask "may I write this file / run this command?",
and since there's no one to answer, it blocks until the timeout kills it. So to
get a panelist that actually *does work*, pin down two flags from its `--help`:

1. its **print/exec/run** flag (one-shot, non-interactive), and
2. its **auto-approve / skip-permissions** flag (so it never waits on a prompt).

| CLI | Print/exec | Auto-approve (full-capability) | Structured output → `parse` |
|---|---|---|---|
| `grok` | `-p` / `--single` (also installed as `agent`) | `--always-approve` | `--output-format json` → `json:.text` |
| `claude` | `-p` | `--dangerously-skip-permissions` | `--output-format json` → `json:.result` |
| `gemini` | `-p` | `--yolo` | `-o json` → `json:.response` |
| `codex` | `exec` | `--dangerously-bypass-approvals-and-sandbox` (or `--full-auto`) | text |
| `opencode` | `run` | (none needed — `run` acts without an approval gate) | text |
| `omp` | `-p` / `--print` | `--auto-approve` | text |

### CLI session resume (REQ-52)

Catalog CLIs **own** their sessions. Open Swarm stores each CLI session id next
to the chat thread (`cli_sessions` on the per-agent JSON record) and, on the
next send to that CLI, inserts the resume argv so the CLI restores its own
context. This is not a Django/API conversation id and not OS
`start_new_session` (process-group kill). First-turn catalog cmds stay one-shot;
resume argv is added only when a stored id exists. Missing or expired ids start
a new session; we store the new id. If a CLI cannot resume, the UI says we
started a new session — never a fake “restored”.

| CLI | Resume argv (when an id is stored) | How the id is named | Capture |
|---|---|---|---|
| `grok` | `--resume {session_id}` (`-r`) | UUID. `--session-id` / `-s` names a **new** session | JSON `sessionId` / `session_id` |
| `claude` | `--resume {session_id}` (`-r`) | UUID. `--session-id` names a **new** session | JSON `session_id` (sibling of `result`) |
| `gemini` | `--resume {session_id}` (`-r`) | UUID. `--session-id` starts a **new** session | JSON `session_id` / `sessionId` when present |
| `codex` | `codex exec resume {session_id} …` (subcommand) | UUID / thread id | JSON `thread_id` when `--json`; default catalog parse is text |
| `opencode` | `opencode run --session {session_id}` (`-s`) | `ses_…`. `--continue` is last-cwd, not thread-scoped | JSON when the CLI emits it; default parse is text |
| `omp` | `omp -p --resume {session_id}` (`-r`) | session id/path; `--continue` is last-session — do not use | default parse is text |
| `agy` | `--conversation {session_id}` | UUID. `--continue` is most-recent, not thread-scoped | JSON `conversation_id` |
| `pi` | `pi -p --session {session_id}` | path or id. `--continue` is last session | JSON when present; smoke/verify uses `--no-session` |

`antigravity` is not in the catalog. Agy is the catalog name; headless resume is
`agy -p --conversation <id>` (JSON often includes `conversation_id`).

Per-adapter config can override `resume_argv`, `resume_insert`, and
`session_id_paths`. An empty `resume_argv` means the CLI cannot resume.

### CLI Select session (REQ-104 / #795)

From a CLI rail row, **Select session** browses that CLI’s existing sessions and
switches the mounted chat onto one of them. This is not “resume whatever id we
last stored” (REQ-52); it is an explicit hop between the CLI’s own sessions and
open-swarm. **Provider list is the source of truth** for CLI resume — Django
Select/New (#469) stays for swarm-backed threads and does not replace it.

**Design (A) — used:** selecting a session (or **Start new session**) **mints a
new Django/chat-store conversation** bound to that CLI session id. The previous
swarm thread is not deleted (still on disk / history). Old compressions stay on
the old conversation and are not copied. Design **(B)** (wipe/rebuild the same
Django conversation) is not used — wipe is not clean enough, and orphans keep
user data reachable.

**Prior-history pill:** if the current chat already has turns and the selected
CLI session differs, those turns collapse into an expandable **Prior history**
pill (same System/Agent family as Support preload / #685). The CLI session
loads under that pill. Same session + same content → no double-collapse. The
pill is a **UI archive** (`kind: prior_history`); `render_prompt` skips it so
prior foreign history is never prepended as CLI turns.

**Listing (#795):** each catalogued CLI that supports list+resume shows
**provider-owned** sessions (ids + display metadata only — no secret-shaped
payloads), including sessions never started in open-swarm. Selecting one binds
`cli_session` and the next send uses that CLI’s resume argv. `can_list` is true
when a catalog/config `list_argv` or provider `list_store` is set. Empty copy
is “This CLI can’t list sessions” or “No sessions found” — never fake rows.
Paste-id always works. Recents are the last 5–10 swarm-touch ids with a
relative activity stamp (`2m ago` / `Yesterday`). **Activity SoT:** provider
`updated_at` when `can_list`; else last swarm-touch. Config
`cli_agents.<name>.list_argv` / `list_store` / `list_store_dir` can override
(or disable) the catalog.

| CLI | List API | Resume API | Status |
|---|---|---|---|
| `grok` | `grok sessions list [--limit N]` (text table: id, created, updated, status, summary; cwd + sibling worktrees). JSON/JSONL also parsed. | `--resume {id}` (`-r`) | **works** |
| `agy` | Provider store `~/.gemini/antigravity-cli/conversations/<uuid>.db` (filename stem = `--conversation` id, mtime = `updated_at`; sqlite never opened). No official `agy conversations list` yet ([antigravity-cli#602](https://github.com/google-antigravity/antigravity-cli/issues/602)). | `--conversation {id}` | **works** |
| `opencode` | `opencode session list --format json` (`id`, `title`, `updated`) | `--session {id}` (`-s`) | **works** |
| `omp` | *(none verified)* | `--resume {id}` (`-r`) | **paste-only** |
| `claude` | none — `claude --resume` without an id is a TUI picker | `--resume {id}` (`-r`) | **paste-only** |
| `gemini` | none verified | `--resume {id}` (`-r`) | **paste-only** |
| `codex` | none verified (`codex resume` is a TUI) | `codex exec resume {id}` | **paste-only** |
| `pi` | none — `--resume` is a TUI picker | `--session {id}` | **paste-only** |
| Fixture / configured `list_argv` | JSON / JSONL of `{id,title,snippet,updated_at}` (or `session_id` / `thread_id` / `conversation_id`) | per adapter `resume_argv` | **works** |

Status meanings: **works** = picker lists provider sessions; **paste-only** =
resume by pasted id + swarm recents; **unsupported** = no list and no resume
(none in the catalog today). Antigravity is not a separate catalog entry.

### Cross-tool session hop (REQ-138 / #531)

Quota death mid-task is a **switch**, not a restart. Changing the CLI (or API)
dropdown — still in the **same** swarm chat/task pane — always starts a **new**
session on the target tool and **seeds** it with prior context. Switching
**back** to Grok (or any earlier CLI) is also a new session; open-swarm does
**not** resume or patch the earlier native session. The switch is **manual**
(the user changes the dropdown). There is no automated quota failover.

This is not Select session (#468 / #795): that *attaches* a provider session
id so the next send uses `--resume`. Hop *leaves* the current backend.

**What is injected**

| Mode | Default token budget | What the new CLI/API sees |
|---|---|---|
| `summary` (default; also called condensed) | 4000 | Newest user/assistant/system turns that fit, plus a carried-context header |
| `full` | 16000 | Same filter, larger budget |

Omitted from every blob: **secrets** (key-shaped tokens, `Bearer`, URI
passwords) and **tool noise** (tool roles, `tool_calls`, status/info chrome,
prior-history pills). Limits live in Settings → CLI agents → **When switching
CLI**, or `mode` / `token_budget` on `POST /v1/cli-sessions/hop/`.

**CLI vs API**

- **CLI:** next send is one-shot with no resume argv. The first prompt is
  `[Carried context from {from} → {to} — {mode}…]` plus the latest user turn.
- **API:** same conversation; `previous_response_id` is not continued across
  the hop. The carried blob is prepended as a system message when a pending
  hop exists.

**Export / import capability**

Prefer a native transcript export when a CLI has `export_argv` (fixtures).
Catalog CLIs today have **no verified non-interactive export**, so import
falls back to the swarm thread (the pane of glass) and the UI says so.
Select session → **Continue on…** hops a listed provider session onto another
CLI the same way: new target session + seed; honest error + summary fallback
when the source cannot export.

| CLI | List | Resume | Native export | Hop inject |
|---|---|---|---|---|
| `grok` | works | `--resume` | none verified | summary (swarm thread) |
| `agy` | works (store stems; sqlite never opened) | `--conversation` | none (store not read) | summary |
| `opencode` | works | `--session` | none verified | summary |
| `omp` | paste-only | `--resume` | none verified | summary |
| `claude` / `gemini` / `codex` / `pi` | paste-only | resume argv | none | summary |
| Fixture `export_argv` | — | — | **transcript** | native turns, then seed |

**Status line:** `Carried summary context from grok → agy (847 tokens).` —
distinct from the #362 dropdown line `CLI: grok → agy`. Empty thread:
`Started a new agy session. No prior context to carry from grok.`

`GET /v1/cli-sessions/hop/` is the machine-readable matrix. Config
`cli_agents.<name>.export_argv` / `export_capability` can enable a fixture
transcript path (`{session_id}` substituted).

### Example adapters

```jsonc
"cli_agents": {
  "claude": {
    "cmd": ["claude", "-p={prompt}", "--output-format", "json",
            "--dangerously-skip-permissions"],
    "parse": "json:.result",
    "mode": "write",
    "timeout": 240
  },
  "gemini": {
    "cmd": ["gemini", "-p={prompt}", "-o", "json", "--yolo", "--skip-trust"],
    "parse": "json:.response",
    "mode": "write"
  },
  "codex": {
    "cmd": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--", "{prompt}"],
    "parse": "text",
    "mode": "write"
  },
  "opencode": {
    "cmd": ["opencode", "run", "--model", "litellm/orchestration", "--", "{prompt}"],
    "parse": "text",
    "mode": "write"
  },
  "omp": {
    "cmd": ["omp", "-p", "--model", "litellm/orchestration", "--auto-approve", "--", "{prompt}"],
    "parse": "text",
    "mode": "write"
  }
}
```

### Known per-CLI gotchas (baked into the defaults)

These bite the moment you run a CLI non-interactively; the catalog and the
examples above already include the fixes (verified live 2026-06-16):

| CLI | Gotcha | Fix (already applied) |
|---|---|---|
| `gemini` | refuses to run in an "untrusted" directory | `--skip-trust` (or `GEMINI_CLI_TRUST_WORKSPACE=true`) |
| `opencode` | built-in default model errors as "not supported" | explicit `--model` (e.g. `litellm/orchestration`) — run `opencode models` to pick one available to your account |
| `omp` | custom LiteLLM slug not in built-ins; stdin hang without DEVNULL | durable `~/.omp/agent/models.yml` mapping `litellm/orchestration`; catalog cmd pins `--model` + `--auto-approve` |
| `claude` | none for read/answer; writes need the auto-approve flag | `--dangerously-skip-permissions` (already in the write config) |

The `--model` value for `opencode` is account/version-specific — it's the one
place you'll likely need to adjust. Everything else runs as shipped.

### List-models probe (REQ-44)

Each catalogued CLI has a **non-interactive** list-models argv (the CLI's own
flag, not a hardcoded vendor list). Swarm runs it with stdin closed and a
timeout; missing CLI, unknown name, failed probe, or timeout → `{cli, models: []}`
plus a warning — never a crash, never a hang.

| CLI | Probe (from `--help` / docs) |
|---|---|
| `grok` | `grok models` |
| `claude` | `claude models` |
| `gemini` | `gemini --list-models` |
| `codex` | `codex debug models` |
| `opencode` | `opencode models` |

```bash
swarm-cli list-models grok
# {"cli": "grok", "models": ["grok-4", "..."]}

curl -sf http://localhost:8000/v1/cli-agents/grok/models
# same {cli, models} shape

curl -sf http://localhost:8000/v1/cli-agents/models
# [ {cli, models}, ... ] for every catalogued CLI
```

`GET /v1/cli-agents/` and `GET /v1/config-options/` also expose the argv table
(`list_models`) so Settings / #358 can auto-pick without guessing flags. The
catalog GET does **not** run the probe. Live probes
(`GET /v1/cli-agents/<cli>/models` and MCP `--help`) resolve the binary with
`which_cli` on `host_cli_path` — the same PATH CLI runs use — so a
Daphne-stripped `PATH=/usr/bin:/bin` still finds `~/.local/bin/grok`. Empty or
failed probes return `{models: [], warning}` (HTTP 200). Chat does not invent a
`default` option from that.

The catalog GET body includes host discovery the SPA already reads:
`installed` / `configured` / `discovered` / `rail`. Tests must use that payload,
not a stub that omits those keys.

**Per-CLI model flag.** When a request (or an inference profile) pins a specific
model, the catalog rewrites the CLI's command using that CLI's model flag:

| CLI | Model flag |
|---|---|
| `gemini` | `-m` |
| `claude` | `--model` |
| `opencode` | `--model` |
| `omp` | `--model` |
| `agy` | `--model` |
| `grok` | `-m` |

`cli_catalog.apply_model` replaces an already-pinned model in place (rather than
duplicating the flag) and is a no-op for CLIs with no known model flag or no
`cmd`; new flags sit **before** `-p` / `{prompt}`. `with_model` returns a
catalog entry pinned to a model (with an optional larger `timeout` for slower
"pro" tiers). Chat send `params.model` (or Agent Router `cli_model`) reaches
`apply_overrides` → `apply_model` for CLIs in `MODEL_FLAG`. The API Model
control lists LLM/profile ids from `/v1/llm-profiles/`; `/v1/models` stays an
honest OpenAI blueprint envelope.

These panelists run at **full capability** — they can read, write, and run
commands. The one real hazard of fanning several write-capable agents out in
parallel is that they stomp each other's edits in a shared tree; `cli_fusion`
solves that by giving each panelist its own working copy — see
[Workdir isolation](#workdir-isolation).

---

## Config: `cli_fusion`

| Key | Type | Meaning |
|---|---|---|
| `default_cli` | str | Which adapter the `cli_agent` blueprint uses when the request doesn't name one. |
| `presets` | dict | Named panels. Each preset: `{ "panel": [names], "judge": name }`. |
| `default_preset` | str | Preset used by `cli_fusion` when the request doesn't specify a panel/preset. |
| `max_rounds` | int | Master-plan rounds (default 1, hard-capped at 5). |
| `max_concurrency` | int | Max CLI subprocesses launched at once per round (default 8). |
| `isolate_workdir` | bool \| null | Give each panelist its own working copy so parallel writes don't collide. **null (default):** auto — isolate when the request's `workdir` is a git repo and the panel has >1 member. **true:** always isolate. **false:** never (all panelists share one workdir). See [Workdir isolation](#workdir-isolation). |
| `show_analysis` | bool | Append the judge's consensus/contradictions/gaps footer to the answer. |

```jsonc
"cli_fusion": {
  "default_cli": "claude",
  "default_preset": "general-high",
  "max_rounds": 1,
  "isolate_workdir": true,
  "show_analysis": false,
  "presets": {
    "general-high":   { "panel": ["claude", "gemini", "codex"], "judge": "claude" },
    "general-budget": { "panel": ["gemini"],                    "judge": "gemini" }
  }
}
```

### Per-request `params`

| Param | Applies to | Meaning |
|---|---|---|
| `cli` | cli_agent | Which adapter to run (the failover primary). |
| `fallback` | cli_agent | Explicit ordered list of adapters to try if the primary fails. |
| `failover` | cli_agent | Auto-failover to other installed adapters when the primary fails (default `true`; set `false` for strict single-CLI — never silently switch models). |
| `panel` | cli_fusion | Explicit list of adapter names (overrides preset). |
| `preset` | cli_fusion | Named preset to use. |
| `judge` | cli_fusion | Judge adapter (overrides preset's). |
| `max_rounds` | cli_fusion | Override master-plan rounds (capped at 5). |
| `isolate` | cli_fusion | Override `isolate_workdir` for this request (`true`/`false`). |
| `show_analysis` | cli_fusion | Override the analysis footer. |
| `timeout` | both | Override every adapter's timeout for this request. |
| `workdir` | both | Working directory for the CLI(s). Confined under `SWARM_WORKSPACES_DIR` / XDG `workspaces/` (relative paths OK; absolute outside the root rejected unless `ALLOW_UNRESTRICTED_WORKDIR=true`). |

---

## How fusion works

```
prompt ─► panel: N CLIs run in PARALLEL (asyncio.gather), each one-shot
            │
            ▼
        judge CLI: compares (not concatenates) the answers → structured JSON
            { consensus, contradictions, gaps, unique_insights, answer, done, next_step }
            │
            ▼
        synthesize: judge's "answer" (or longest panel answer if no judge)
            │
       done? ──no──► feed answer + next_step back as the next round's prompt
            │
           yes ─► final answer (the only chunk marked final)
```

- **No judge configured?** Fusion still works — it falls back to the longest
  successful panel answer.
- **Master plan:** when `max_rounds > 1` and the judge returns `"done": false`,
  its `"next_step"` becomes the next round's instruction. The loop stops on
  `done`, at `max_rounds`, or if every panelist fails.
- **Progress** (per-round panel/judge status) streams as a side-channel chunk
  (`{"type":"fusion_progress"}`) that vanilla OpenAI clients ignore, so it never
  pollutes the synthesized answer.

---

## Decompose & distribute — `cli_map`

The complement to consensus. `cli_fusion` sends the *same* question to a panel;
`cli_map` splits *one task* into independent subtasks, distributes them across
worker CLIs in parallel (round-robin), and reduces the results into one answer —
divide-and-conquer for scale.

```jsonc
"cli_map": {
  "planner": "claude",
  "workers": ["claude", "gemini", "opencode"],
  "reducer": "claude",
  "max_items": 6
}
```

A **planner** CLI decomposes the prompt into a JSON subtask list (or pass
`params.items` to skip planning), workers run the subtasks concurrently, and a
**reducer** combines them (falling back to a labeled concatenation if no reducer
is configured). Falls back to `cli_fusion` config when the `cli_map` block is
omitted.

## Granular consensus — `cli_orchestrator`

`cli_fusion` fans out on *every* request. `cli_orchestrator` makes consensus
*granular*: a cheap **router** CLI runs a single inference, answers directly, and
escalates to a consensus panel **only** when it judges the question high-stakes
(correctness-critical, security/production-impacting, contested). Single
inference by default, consensus on demand.

```jsonc
"cli_orchestrator": {
  "router": "claude",
  "panel": ["claude", "gemini", "opencode"],
  "judge": "claude"
}
```

```bash
curl -sf localhost:8000/v1/chat/completions -H "Authorization: Bearer $TOKEN" \
  -d '{"model":"cli_orchestrator","messages":[{"role":"user","content":"Is this migration safe?"}]}'
```

Falls back to `cli_fusion.default_cli` (router) and `default_preset` (panel/judge)
when the `cli_orchestrator` block is omitted. The shared loop lives in
`swarm.core.consensus.run_consensus()`, so the same panel→judge→synthesize
primitive backs both blueprints (and can be wrapped as an agent tool).

## Skills — reusable capabilities, portable across CLIs

A **skill** is a directory with a `SKILL.md` (YAML frontmatter `name` +
`description`, then markdown instructions, optionally bundled scripts), following
Anthropic's [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
open standard — so a skill authored here also loads in Claude Code / the Skills
API. Skills live under the repo's `skills/` directory.

```bash
swarm-cli skills                      # list discoverable skills + asset counts
swarm-cli skills --show counting-lines  # print one skill's full SKILL.md
swarm-cli skills --json               # machine-readable
```

Apply a skill to **any** CLI with the `cli_agent` `skill=` param — it prepends
the skill's instructions and stages any bundled assets into the workdir so a
write-mode CLI can execute them:

```bash
curl -sf localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "cli_agent",
  "messages": [{"role":"user","content":"Added retry-with-backoff to the upload client."}],
  "extra_body": {"params": {"cli": "grok", "skill": "conventional-commit"}}
}'
```

The same skill works on grok, claude, or gemini (verified live, 3/3). Bundled
examples: `conventional-commit`, `reviewing-code`, `writing-changelog`,
`counting-lines` (ships an executable `count.py`), `support-session-ownership`
(Support session ownership). See the illustrated
[walkthrough](SKILLS_AND_CONSENSUS_WALKTHROUGH.md).

## Inference profiles — say what you want, not which model

A blueprint can declare *what kind of thinking it wants* instead of naming a CLI,
along three 0–1 axes — `intelligence`, `speed`, `cost` (cheapness) — as priority
weights. Each CLI carries 0–1 **capability** traits (defaults in
`cli_catalog.CLI_TRAITS`, override per-agent in config), and the best match is
chosen by a weighted dot product. This keeps blueprints portable: "I want smart"
runs on whatever *you* labelled smart.

```jsonc
// tag your backends (per cli_agents entry) — e.g. rate your top plan highly
"cli_agents": {
  "claude": { "cmd": [...], "traits": {"intelligence": 1.0, "speed": 0.5, "cost": 0.3} },
  "gemini": { "cmd": [...], "traits": {"intelligence": 0.6, "speed": 0.95, "cost": 0.95} }
}
```

```bash
# request-level: ask for traits, not a model
curl ... -d '{"model":"cli_agent","messages":[...],
  "extra_body":{"params":{"profile":{"intelligence":0.9,"speed":0.2,"cost":0.1}}}}'
```

A blueprint declares it once in metadata (`inference_profile = {...}`).
Precedence: explicit `cli` param > `profile` > `default_cli` > first available.
Live routing: deep-reasoning → claude, fast&cheap → gemini (see
[docs/examples/inference-profile-routing.md](examples/inference-profile-routing.md)).

## Failover & graceful degradation

Not every CLI is installed and working on every host, so the blueprints assume
some will fail and route around them:

- **`cli_agent` fails over.** It tries the primary CLI, and on failure (not
  installed, not authenticated, non-zero exit, or hang→timeout) moves to the next
  candidate. The chain is the primary plus either an explicit `params.fallback`
  list or — by default — every other *installed* adapter. Each failover is
  surfaced as a progress event. Set `params.failover: false` for strict
  single-CLI behaviour that never silently switches models. (Streaming commits to
  the first installed candidate — no mid-stream failover, since sent bytes can't
  be unsent.)
- **`cli_fusion` degrades.** A broken or missing panelist never sinks the round:
  failures are dropped (and reported), and the judge synthesizes consensus from
  the survivors. Only when *every* panelist fails does the round error out. So a
  panel of `[claude, gemini, codex]` on a host missing `codex` still returns a
  two-CLI consensus.

## Streaming

`cli_agent` streams the CLI's stdout **incrementally** when the request sets
`"stream": true` and the adapter uses `parse: "text"` — each delta is forwarded
as a `chat.completion.chunk`, so an OpenAI streaming client sees output as the
CLI produces it instead of waiting for the whole run. `json:`-parse adapters
can't stream (the value only exists once the full document is read), so they
fall back to a single one-shot chunk. Non-streaming requests are unchanged: one
full answer. `cli_fusion` does not stream panelists — the judge needs each
panelist's complete answer before it can compare them.

## Workdir isolation

Panelists run at full capability, so a panel of N write-capable agents fanned out
over the *same* `workdir` will stomp each other's edits. `cli_fusion` defuses this
by giving each panelist its own working copy for the duration of a round:

- **git repo (the common case):** each panelist gets a throwaway
  `git worktree` checked out at `HEAD`, so it sees the full repo cheaply and its
  edits never touch the source tree or the other panelists. The worktrees are
  removed (`--force`, discarding scratch edits) when the round ends.
- **non-repo `workdir` (or none):** each panelist gets a fresh empty temp
  directory as scratch space.

Controlled by `cli_fusion.isolate_workdir` (config) or the per-request `isolate`
param. The default (`null`) auto-isolates when `workdir` is a git repo and the
panel has more than one member; set it `true` to always isolate or `false` to
share one workdir. The **judge** always runs in the base `workdir` (it only reads
and compares the panel's text answers). Fusion synthesizes a single *text* answer
— it does not merge the panelists' divergent trees, so the isolated edits are
treated as scratch work, not a deliverable.

## Safety

CLI agents can read files, run commands, and reach the network. Treat them as
untrusted, side-effecting processes:

- **Workdir isolation.** Keep `isolate_workdir` on (the default auto-isolates git
  repos) so parallel write-capable panelists can't corrupt the source tree or
  collide — see above.
- **Timeouts always.** Interactive CLIs hang waiting for input if you get the
  non-interactive or auto-approve flag wrong. Every adapter has a `timeout`; on
  expiry the whole process group is killed (SIGTERM → SIGKILL).
- **Secret isolation.** By default every panelist inherits the full environment.
  Set `env_allowlist` per adapter so each CLI sees only the keys it needs.
- **Recursion guard.** If a panelist CLI is itself pointed back at this Open
  Swarm endpoint with `model: "cli_fusion"`, the `SWARM_CLI_FUSION_DEPTH` env var
  (injected into children) makes nested fusion degrade to a single agent — no
  fan-out explosion.
- **Cost.** A panel of N agents over R rounds is ~N×R completions. Keep
  `max_rounds` small and panels focused; use `general-budget` for cheap runs.

---

## Full example

A complete, copy-pasteable config lives at
[`docs/examples/cli_fusion.swarm_config.json`](examples/cli_fusion.swarm_config.json).
