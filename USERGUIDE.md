# Open Swarm User Guide: `swarm-cli`

This guide is the task-oriented reference for the `swarm-cli` command-line
tool: managing blueprints and configuration in your Open Swarm environment.
It assumes you have installed `open-swarm` (from source: `uv sync
--all-extras`; from PyPI: `pip install open-swarm`). Every command documented
here is verified against `swarm-cli --help`.

> **Documentation map:** this file is the `swarm-cli` reference;
> [docs/USER_JOURNEY.md](./docs/USER_JOURNEY.md) is the end-to-end story
> (install → CLI → web UI → API) with real transcripts;
> [docs/GUIDED_TOUR.md](./docs/GUIDED_TOUR.md) is the **screenshot tour** of the
> web UI (Playwright PNGs under `docs/screenshots/`);
> [docs/SCREENSHOTS.md](./docs/SCREENSHOTS.md) is the capture registry.
>
> **Blueprints are CLI/API only.** They do not ship a webpage or a second chat
> shell. The Grok-like SPA (`/` + `/chat`) is the product web UI.
>
> **Web UI note:** day-to-day **operator UI** is the **Django** shell
> (trailing-slash routes: `/blueprint-library/`, `/teams/launch/`,
> `/sessions/`, `/settings/`, … — [ADR-001](./docs/ADR-001-primary-ui.md)).
> Most browse/admin pages (`/blueprint-library/`, `/teams/`, `/sessions/`,
> `/settings/`) and creator mutators require a Django login session; Team
> launcher (`/teams/launch/`) and Agent Creator GET stay public. The React
> SPA keeps `/` (dashboard) and `/chat` (SPA Chat); bare paths redirect to
> Django — `/teams` → `/teams/launch/`, `/blueprints` → `/blueprint-library/`,
> `/settings` → `/settings/`, `/agent-creator` → `/agent-creator/`.
> Session vs Bearer, websocket **4401**, and Explorer bridge:
> **[docs/AUTH.md](./docs/AUTH.md)**.
> **`/v1/teams` / Django `/teams/`** register **LLM-profile aliases**
> (prefer **Profiles**: `id`/`description`/`llm_profile`). A **Team** is
> API/CLI/remote members that see/talk via handoff (`/v1/agent-team/`) —
> see [docs/GLOSSARY.md](./docs/GLOSSARY.md). Regenerate tour images with
> `scripts/capture_user_journey.py`.

---

## Overview

<!-- from-scratch: list.txt -->
```text
swarm-cli list
```

`swarm-cli` ships these commands (verify with `swarm-cli --help`):

| Command | Purpose |
| --- | --- |
| `list` | List installed executables, bundled blueprints, and user blueprint sources |
| `install-executable <name>` / `install <name>` | Build a standalone executable for a blueprint (PyInstaller) |
| `launch <name> [options]` | Run an installed blueprint executable (pre/listen/post hooks optional) |
| `uninstall <name>` | Remove a compiled blueprint executable from the user bin directory |
| `add` / `delete` | Add or remove a blueprint from the user blueprint library |
| `config` | Manage LLM profiles and MCP servers (`list` \| `add` \| `remove`) |
| `cli-agents` / `agents` | Autodiscover configured agentic CLIs (`--check-auth`, `--init`, `--smoke`, `--suggest`, `--list-models`, …) |
| `list-models` | Probe a catalogued CLI for the models it actually offers (`{cli, models: [...]}`) |
| `skills` | List reusable `SKILL.md` capabilities (apply via `cli_agent` `skill=` param) |
| `tui` | Interactive terminal UI — AGENTS rail + chat over the same REST/SSE API as the WebUI ([ADR-012](./docs/adr/012-swarm-cli-tui.md)) |
| `wizard` | Scaffold a new team blueprint (supports `--non-interactive`) |
| `moa` | Mixture of Agents (`--backend fake\|grok\|acpx`; `--act` / `--act-write`, or `--team --workdir` + `--team-tasks` for scripted consensus→team — not a live Runner) |
| `moa-init` | Install/merge default `moa` panel config/presets (`--write`, `--show-openwebui`; team mode is CLI/model-path, not a preset key) |

Run `swarm-cli --help` or `swarm-cli <command> --help` for the authoritative
usage text.

---

## File Locations (XDG Compliance)

`swarm-cli` follows the XDG Base Directory Specification (via
`platformdirs`), keeping your home directory clean. Linux paths shown;
macOS/Windows vary per `platformdirs` conventions.

*   **Configuration File (`swarm_config.json`):**
    *   **Location:** searched upward from the current directory first, then
        `~/.config/swarm/swarm_config.json` (or `$XDG_CONFIG_HOME/swarm/`).
        Override with `SWARM_CONFIG_PATH`.
    *   **Purpose:** stores LLM profiles and MCP server definitions.
    *   **Creation:** create it yourself (see
        [Managing Configuration](#managing-configuration) below) — it is not
        auto-created.
*   **User Blueprint Sources:**
    *   **Location:** `~/.local/share/swarm/blueprints/` (or
        `$XDG_DATA_HOME/swarm/blueprints/`; override the data dir with
        `SWARM_USER_DATA_DIR`).
    *   **Purpose:** blueprint source folders you add manually; `install` and
        `list` pick them up from here.
*   **Installed CLI Binaries (Executables):**
    *   **Location:** `~/.local/share/swarm/bin/`
    *   **Purpose:** standalone executables created by `swarm-cli install`.
    *   **Note:** add this directory to your `PATH` to run installed
        blueprints directly by name.
*   **Build Cache (PyInstaller):**
    *   **Location:** `~/.cache/swarm/`
    *   **Purpose:** temporary files generated during `swarm-cli install`.

---

## Managing Blueprints

### Listing Blueprints (`swarm-cli list`)

Shows three groups: installed executables, blueprints bundled with the
package, and user blueprint sources.

```bash
swarm-cli list                # all three groups
swarm-cli list --installed    # -i: only installed executables
swarm-cli list --available    # -a: only blueprint source directories
```

Example output (fresh environment):

```text
--- Installed Blueprint Executables (in /home/user/.local/share/swarm/bin) ---
(No installed blueprint executables found in /home/user/.local/share/swarm/bin)
Try 'swarm-cli install-executable <blueprint_name>' or see 'swarm-cli list --available'.

--- Bundled Blueprints (available from package) ---
- jeeves (entry: blueprint_jeeves.py)
- codey (entry: blueprint_codey.py)
- suggestion (entry: suggestion_cli.py)
...

--- User Blueprint Sources (in /home/user/.local/share/swarm/blueprints) ---
(No user blueprint sources found in /home/user/.local/share/swarm/blueprints)
You can add blueprints by copying their source folders to this directory.
```

### Adding Your Own Blueprints (`swarm-cli add` or manual copy)

Prefer the CLI when you have a blueprint source path:

```bash
swarm-cli add ./my_blueprints/cool_agent --name cool_agent
swarm-cli list --available    # it now appears as a user blueprint source
```

Or copy the folder yourself into the user blueprints directory:

```bash
mkdir -p ~/.local/share/swarm/blueprints
cp -r ./my_blueprints/cool_agent ~/.local/share/swarm/blueprints/cool_agent
swarm-cli list --available
```

### Installing Blueprints as Commands (`swarm-cli install`)

Builds a standalone executable (PyInstaller) from a user blueprint source or
a bundled blueprint, and places it in `~/.local/share/swarm/bin/`.
`install` and `install-executable` are the same command.

```bash
swarm-cli install jeeves
# Installing blueprint 'jeeves' as executable...
#   Source: .../src/swarm/blueprints/jeeves
#   Entry Point: blueprint_jeeves.py
#   Output Executable: /home/user/.local/share/swarm/bin/jeeves
```

*   **After installation:** (with `~/.local/share/swarm/bin/` in your `PATH`)
    ```bash
    jeeves --message "Now I'm a command!"
    ```
*   **Fast test-mode install:** with `SWARM_TEST_MODE=1`, `install` writes a
    quick shell shim instead of compiling a PyInstaller binary, and launched
    blueprints emit deterministic canned output — useful for trying the CLI
    without an API key (see
    [docs/USER_JOURNEY.md](./docs/USER_JOURNEY.md#try-a-blueprint-without-an-api-key-swarm_test_mode)).

### Terminal TUI (`swarm-cli tui`) — interactive front door

Open Swarm’s own terminal client of the **same HTTP API** as the WebUI
([REQ-111](https://github.com/matthewhand/open-swarm/issues/481) /
[ADR-012](./docs/adr/012-swarm-cli-tui.md)): a Herdr-like left **AGENTS rail**
(kind sections CLI / API / Blueprint / Remote from the same five catalogs the
SPA sidebar reads) and a live chat pane. Selecting a seat hydrates that
agent’s real thread (`GET /chat/thread/`); Blueprint seats send and stream
replies over REST SSE (`/v1/chat/completions`, Bearer); `n` starts a new
session and `s` lists / resumes. Not Herdr’s SSH TUI and not an in-process
blueprint runtime (`swarm-cli launch` stays a separate door).

Keys: `j` / `k` (or arrows) move, `Enter` selects, type + `Enter` sends,
`n` new session, `s` session list + a digit resumes, `/` filters the rail
(name/id, Esc clears), `q` quits. API down,
auth failure, or a login-gated hydrate are named errors — nothing is
invented. CLI-tool / team / remote / Herdr rows honestly disable the
composer (their send is the SPA websocket path; TUI v1 has no cookie jar).

```bash
# Textual is an optional [tui] extra (included by `uv sync --all-extras`).
# Requires a running swarm-api (greenfield http://127.0.0.1:8000; fleet often :8002 when LiteLLM owns :8000 — not :8001)
# and, when API auth is on, API_AUTH_TOKEN / SWARM_API_KEY (env values only).
swarm-cli tui

# Non-TTY / CI: the Wave 0 ASCII dump + JSON still work
swarm-cli tui --once
swarm-cli tui --once --base-url http://127.0.0.1:8000 --json   # or :8002 on fleets where LiteLLM owns :8000
```

`launch` / `install` stay available (dual entry).

### Launching Blueprints (`swarm-cli launch`)

Runs a **previously installed** blueprint executable from
`~/.local/share/swarm/bin/`. If the executable is missing, `launch` exits
with an error telling you to `swarm-cli install-executable <name>` first.

*   **Single message run:**
    ```bash
    swarm-cli launch jeeves --message "What time is it?"
    ```
*   **Interactive mode:** (omit `--message`; behavior depends on the
    blueprint)
    ```bash
    swarm-cli launch jeeves
    ```
*   **Hooks — chain other installed blueprints around the main run:**
    ```bash
    swarm-cli launch codey \
      --pre lint_team \
      --listen observer \
      --post verifier \
      --message "Refactor the parser"
    ```
    *   `--pre` / `-p`: comma-separated blueprint names to run **before** the
        main task
    *   `--listen` / `-L`: comma-separated blueprint names to invoke **on the
        same inputs**
    *   `--post` / `-o`: comma-separated blueprint names to run **after** the
        main task

    Hook blueprints must also be installed executables; missing ones are
    skipped with a warning.

These are the only `launch` options. To select a different LLM profile, set
`DEFAULT_LLM` in the environment (see below); blueprint-specific flags can be
passed when running the blueprint executable (or its module entry point)
directly, e.g. `python -m swarm.blueprints.jeeves.jeeves_cli --help`.

### Removing Blueprints (`swarm-cli delete` / `uninstall`)

```bash
swarm-cli uninstall jeeves                 # remove compiled executable from user bin
swarm-cli delete cool_agent                # remove from user blueprint library
# optional manual cleanup of leftover files:
# rm ~/.local/share/swarm/bin/jeeves
# rm -r ~/.local/share/swarm/blueprints/cool_agent
```

---

## Managing Configuration

`swarm_config.json` holds your LLM profiles and MCP server definitions.
Copy [`swarm_config.example.json`](./swarm_config.example.json) or run
`swarm-cli config init`. Manage entries with `swarm-cli config` (or edit
the JSON file by hand). A checkout-local `swarm_config.json` is gitignored.

```bash
swarm-cli config list --section llm
swarm-cli config add --section llm --name default --json \
  '{"provider":"openai","model":"gpt-4o-mini","api_key":"${OPENAI_API_KEY}"}'
swarm-cli config remove --section llm --name default
```

The loader honors `SWARM_CONFIG_PATH`, then XDG
(`~/.config/swarm/swarm_config.json`), then CWD / upward search.

### Example configuration

```json
{
    "llm": {
        "default": {
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
            "description": "Default OpenAI profile. Requires OPENAI_API_KEY env var."
        },
        "ollama_example": {
            "provider": "ollama",
            "model": "llama3",
            "api_key": "ollama",
            "base_url": "http://localhost:11434",
            "description": "Example for local Ollama Llama 3 model."
        }
    },
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "${ALLOWED_PATH}"],
            "env": { "ALLOWED_PATH": "${ALLOWED_PATH}" }
        }
    },
    "settings": {
        "default_markdown_output": true
    }
}
```

**Important:** placeholders like `${OPENAI_API_KEY}` are substituted from the
environment at load time. You **must** set the corresponding environment
variables — `export` them or put them in a `.env` file in your working
directory.

### Local OpenAI-compatible gateway (role model slugs)

Some local gateways (LiteLLM, LM Studio, custom proxies) expose OpenAI-style
`/v1` and advertise role-oriented **model ids**. One common layout — verified
against a local OpenAI-compatible `/v1/models` listing — is:

| Gateway model id (`model`) | Typical use |
| --- | --- |
| `orchestration` | planning / coordination |
| `delegation` | mid-tier worker / handoff work |
| `auxiliary` | fast / cheap polish, tests, simple steps |

Point named LLM **profiles** at that host with env vars (no secrets in JSON).
`provider: "openai"` means “OpenAI-compatible client”, not the OpenAI cloud.
`base_url` must include `/v1`.

```bash
# .env or shell — endpoint only; use any non-empty placeholder if the gateway is keyless
export LITELLM_BASE_URL=http://127.0.0.1:8000/v1   # LAN LiteLLM; stock LiteLLM docs often use :4000
export LITELLM_API_KEY=sk-local-placeholder
# Leave LITELLM_MODEL unset: a global model override defeats per-profile routing.
export DEFAULT_LLM=orchestration
```

```json
{
    "llm": {
        "orchestration": {
            "provider": "openai",
            "model": "orchestration",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
            "intelligence": 0.95,
            "description": "Gateway slug orchestration — planning / coordination."
        },
        "delegation": {
            "provider": "openai",
            "model": "delegation",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
            "intelligence": 0.7,
            "cost": 0.4,
            "description": "Gateway slug delegation — mid-tier worker steps."
        },
        "auxiliary": {
            "provider": "openai",
            "model": "auxiliary",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
            "speed": 0.9,
            "cost": 0.9,
            "description": "Gateway slug auxiliary — fast / cheap steps."
        }
    },
    "settings": {
        "default_llm_profile": "orchestration"
    }
}
```

Or register the same profiles with the CLI:

```bash
swarm-cli config add --section llm --name orchestration --json \
  '{"provider":"openai","model":"orchestration","base_url":"${LITELLM_BASE_URL}","api_key":"${LITELLM_API_KEY}","intelligence":0.95}'
swarm-cli config add --section llm --name delegation --json \
  '{"provider":"openai","model":"delegation","base_url":"${LITELLM_BASE_URL}","api_key":"${LITELLM_API_KEY}","intelligence":0.7,"cost":0.4}'
swarm-cli config add --section llm --name auxiliary --json \
  '{"provider":"openai","model":"auxiliary","base_url":"${LITELLM_BASE_URL}","api_key":"${LITELLM_API_KEY}","speed":0.9,"cost":0.9}'
```

In the SPA, **Settings → LLM profiles** is the picker (not the Django operator dump). Default is any connected CLI / API / remote id — `gpt-5.6-terra` is fine. If you never pick, swarm auto-assigns auxiliary (cheap/fast), orchestration (mid/chat), and delegation (smart/expensive) from the connected catalog (REQ-44 `{cli, models}` when that helper is present; otherwise `/v1/models` + fixtures — no CLI `--help` scrape). **Override per task** off keeps every job on Default; on maps task classes `orchestration` / `auxiliary` / `delegation` via `settings.task_llm_profiles` (same keys as live LiteLLM role model ids — often identity-mapped to profiles of those names). Code summary (#356) uses the **auxiliary** mapping; design/coding uses **delegation**. Missing ids warn and fall back to Default.

**Honest notes:**

* Profile **names** are config keys; the gateway **slug** is the `model` field.
  Matching names (`orchestration` → `orchestration`) is convenient but optional.
* The `intelligence` / `speed` / `cost` tags are optional capability axes. Only
  tagged profiles participate in `inference_profile` scoring (used by blueprints
  such as `hybrid_team`). Untagged profiles are still selectable via
  `DEFAULT_LLM` / `settings.default_llm_profile` / an explicit profile name.
* `hybrid_team` step **roles** are `orchestration` / `agent` / `auxiliary` (not
  `delegation`). If you want that blueprint’s mid-tier (`agent`) role to hit the
  gateway’s `delegation` slug, keep a tagged profile whose `model` is
  `delegation` (as above) so scoring can pick it; the profile key may be
  `delegation` or anything else.
* Change the host by editing `LITELLM_BASE_URL` only — do not hard-code keys in
  `swarm_config.json`.

Quickstart custom-endpoint steps:
[docs/QUICKSTART.md §3](./docs/QUICKSTART.md#3-configure-your-llm-provider).
Full schema: [CONFIGURATION.md](./CONFIGURATION.md).

### Selecting an LLM profile

Choose which profile a run uses via the `DEFAULT_LLM` environment variable
(defaults to `default`):

```bash
export DEFAULT_LLM=ollama_example          # from the example above
# or, with the local gateway profiles:
# export DEFAULT_LLM=orchestration
swarm-cli launch codey --message "Test Llama3 performance"
```

See [CONFIGURATION.md](./CONFIGURATION.md) for the full configuration guide
(server environment variables, API auth, etc.).

---

## Discovering CLI Agents (`swarm-cli cli-agents`)

Autodiscover which agentic CLIs from your `cli_agents` config are installed on
this host (and optionally authenticated). Alias: `swarm-cli agents`.

```bash
swarm-cli cli-agents                     # install status (fast)
swarm-cli cli-agents --check-auth        # also run each CLI's auth_check
swarm-cli cli-agents --suggest           # propose config for installed-but-unconfigured CLIs
swarm-cli cli-agents --smoke             # one trivial one-shot per installed CLI (uses quota)
swarm-cli cli-agents --json              # machine-readable (combine with the flags above)
swarm-cli cli-agents --list-models       # live {cli, models} for each catalog CLI
swarm-cli list-models grok               # one CLI; omit the name to probe all
swarm-cli cli-agents --config ./swarm_config.json

# Generate a starter swarm_config wiring cli_agents + fusion/orchestrator/map
# over CLIs found on this host (claude/gemini/codex/opencode catalog):
swarm-cli cli-agents --init              # print JSON to stdout
swarm-cli cli-agents --init --write      # write to XDG config (backs up existing)
```

`--smoke` invokes each CLI's model once; prefer `--check-auth` for a cheap
login probe. Full adapter schema and fusion modes:
[docs/CLI_FUSION.md](./docs/CLI_FUSION.md).

---

## Team wizard (`swarm-cli wizard`)

Scaffold a new **Blueprint** (multi-agent workflow source) under your
blueprints tree — unrelated to `/v1/teams` LLM-profile aliases. Interactive by
default; use `--non-interactive` in scripts/CI.

```bash
swarm-cli wizard
swarm-cli wizard --non-interactive \
  --name my_team \
  --role "planner:Break work into steps" \
  --role "implementer:Apply changes" \
  --output-dir ./src/swarm/blueprints
```

`--no-shortcut` skips installing a CLI launcher symlink. Full flags:
`swarm-cli wizard --help`. Also covered in
[docs/QUICKSTART.md](./docs/QUICKSTART.md).

---

## Skills (`swarm-cli skills`)

List reusable `SKILL.md` capabilities under the project's `skills/` directory
(or `--dir`). Applying a skill is not a separate CLI write path — pass
`skill=<name>` or `skills=[...]` on `cli_agent` **or** a Blueprint-backed API
seat (today's stored `api` kind). Chat shows those references as chips; click
opens a skill card. Discovery and #652 kinds: [docs/SKILLS.md](./docs/SKILLS.md).

```bash
swarm-cli skills                         # name, asset count, description
swarm-cli skills --show counting-lines   # full SKILL.md instructions
swarm-cli skills --json
swarm-cli skills --dir /path/to/skills
```

Bundled examples: `conventional-commit`, `reviewing-code`, `writing-changelog`,
`counting-lines`. Details and screenshots:
[docs/CLI_FUSION.md](./docs/CLI_FUSION.md#skills--reusable-capabilities-portable-across-clis),
[docs/SKILLS_AND_CONSENSUS_WALKTHROUGH.md](./docs/SKILLS_AND_CONSENSUS_WALKTHROUGH.md).

---

## Mixture of Agents (`swarm-cli moa`)

Read-only multi-seat opinions → orchestrator determination. **Participants
never write.** After consensus you choose one of:

| Mode | Flags | What runs |
| --- | --- | --- |
| Consensus only | (default) | Determination; optional `--cwd` for panel read context |
| Orchestrator write | `--act` / `--act-write` | Single orchestrator-owned write |
| Consensus → team | `--team --workdir` (+ optional `--team-tasks`) | **Scripted** specialists (`WorkspaceTools`) under `--workdir` — **not** a live openai-agents `Runner` |

`--team` and `--act` are mutually exclusive. `--workdir` is only valid with
`--team` (specialist write workspace; created if missing). `--cwd` is panel
read context only and is **not** a substitute for `--workdir`.

```bash
# Demo / CI — default backend is fake
swarm-cli moa "How should we rate-limit the API?" --json

# Explicit fake multi-seat
swarm-cli moa "Pick a cache" --backend fake --participants a,b \
  --fake-responses 'a=Use redis.||b=Use redis with TTL.'

# Live Grok consensus (local grok CLI; Codex not required)
swarm-cli moa "Summarize risks in auth/" --backend grok \
  --participants analyst,critic --cwd .

# Optional acpx multi-vendor panel
swarm-cli moa "Review the design" --backend acpx \
  --participants claude,gemini --cwd .

# Orchestrator-only write after determination
swarm-cli moa "Document the decision" --backend fake --act \
  --act-write ./moa_decision.md

# Consensus then scripted team (no openai-agents)
swarm-cli moa "Ship rate limiting?" --backend fake --team \
  --workdir /tmp/moa-team \
  --team-tasks 'implementer:Apply|tester:Verify|docs:ADR' \
  --json -v
```

`--team-tasks` is pipe-separated `purpose[:instruction][@rel/path]`. Purposes:
`implementer`, `tester`, `docs`, `researcher`. Default tasks (when you omit a
custom string) are implementer + tester + docs; default paths are `decision.md`,
`test_notes.md`, `docs/ADR.md`, `research_notes.md`. Participant `--permission`
is `approve-reads` or `deny-all` only (never `approve-all`).

Without `--team`/`--act`, `--json` reports `mode=consensus_only`. With
`--act`, `mode=consensus_then_act` (human output includes an Act section).
With `--team`, `mode=consensus_then_team`. Exit codes: `0` success; `1`
runtime / soft team failure (unusable panel or specialist `ok=False` —
payload still printed); `2` usage/validation; `5` write denied.

Full model, backends, Python API, and honesty notes:
[docs/MOA.md](./docs/MOA.md). Walkthroughs with captured runs:
[docs/examples/moa-consensus-vs-team/](./docs/examples/moa-consensus-vs-team/),
[docs/examples/moa-orchestrator/](./docs/examples/moa-orchestrator/).

### MoA config init (`swarm-cli moa-init`)

Install or merge the default `moa` panel block (backend, participants, named
presets). **Presets are panel-only** (`backend` / `participants` /
`fake_responses`) — team mode is **not** a preset key; use
`swarm-cli moa --team --workdir …` or API models `hybrid_moa` /
`moa_orchestrator`.

```bash
swarm-cli moa-init                       # dry-run print default moa block
swarm-cli moa-init --write               # merge into XDG / discovered config
swarm-cli moa-init --config ./swarm_config.json --write
swarm-cli moa-init --write --overwrite   # replace existing moa block entirely
swarm-cli moa-init --backend fake -p analyst,critic   # dry-run with overrides
swarm-cli moa-init --show-openwebui      # Open WebUI connection JSON; exit
```

Example config: [docs/examples/moa.swarm_config.json](./docs/examples/moa.swarm_config.json).
Open WebUI wiring: [docs/OPENWEBUI_MOA.md](./docs/OPENWEBUI_MOA.md).

**Web UI:** this guide stays CLI-first (no PNG embeds). For the Django
operator shell screenshot tour see
[docs/GUIDED_TOUR.md](./docs/GUIDED_TOUR.md) and
[docs/SCREENSHOTS.md](./docs/SCREENSHOTS.md); for MoA over Open WebUI see
[docs/OPENWEBUI_MOA.md](./docs/OPENWEBUI_MOA.md); skills screenshots live in
[docs/SKILLS_AND_CONSENSUS_WALKTHROUGH.md](./docs/SKILLS_AND_CONSENSUS_WALKTHROUGH.md).

---

## Troubleshooting

*   **Command Not Found (`swarm-cli` or installed blueprint):**
    *   Ensure the install completed (`uv sync --all-extras` from source, or
        `pip install open-swarm`); with `uv`, prefix commands with `uv run`.
    *   Verify Python's user script directory (e.g. `~/.local/bin`) is in
        your `PATH`.
    *   For installed blueprints, check that `~/.local/share/swarm/bin/` is
        also in your `PATH`.
*   **`Blueprint executable not found` from `swarm-cli launch`:** `launch`
    only runs installed executables — run
    `swarm-cli install <name>` first, and check spelling against
    `swarm-cli list`.
*   **Configuration Errors:**
    *   Verify your `swarm_config.json` exists (working directory or
        `~/.config/swarm/`) and is valid JSON.
    *   Ensure environment variables referenced in the config (like
        `OPENAI_API_KEY`) are set in your current shell session.
*   **Permissions:** ensure you have read/write permission for the XDG
    directories (`~/.config/swarm`, `~/.local/share/swarm`,
    `~/.cache/swarm`).
*   **`swarm-cli moa` usage errors (exit 2):** `--team` requires
    `--workdir`; `--workdir` without `--team` is rejected; `--team` and
    `--act` cannot be combined. Use `--cwd` only for panel read context.
*   **`swarm-cli moa --team` soft-fail (exit 1, payload printed):** unusable
    panel skips specialists; or a specialist returns `ok=False`. Inspect
    `--json` / `-v` or the stderr soft-fail line. See
    [docs/TROUBLESHOOTING.md §8](./docs/TROUBLESHOOTING.md#8-moa--swarm-cli-moa-common-failures).
*   **CLI agents missing / unauthenticated:** run
    `swarm-cli cli-agents --check-auth` (or `--init --write` for a starter
    config). Each CLI authenticates itself; Open Swarm does not proxy their
    credentials. See [docs/CLI_FUSION.md](./docs/CLI_FUSION.md).
