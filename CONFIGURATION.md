# Swarm Configuration Guide

Ownership of `.env` vs XDG `swarm_config.json` vs Django (what is live SoT
after boot, what WebUI writes, Docker volumes) is decided in
**[ADR-002](docs/adr/002-config-ownership.md)** (REQ-145 / #541; #776 Full
coverage addendum). Settings owns every **non-secret** product key in
`swarm_config.json`. Secrets and bind/deploy flags stay env-only. Inventory:
`GET /v1/config-ownership/`. Example file:
[`swarm_config.example.json`](./swarm_config.example.json) (sibling #775 may
move it). A future Windows desktop zip (not shipped) must set these paths
explicitly — [ADR-003](docs/adr/003-desktop-packaging.md) (REQ-151 / #554).

## Quickstart: Configuring Swarm

Swarm supports both interactive and manual configuration. The recommended way to set up and manage your config is via the `swarm-cli`, which provides commands to initialize, edit, and validate your configuration interactively. However, you can also hand-edit the config JSON if you prefer full control or need to automate deployment.

- **CLI (`swarm-cli config`):**
  - `swarm-cli config list [--section llm|mcpServers|remotes]` — view profiles / MCP servers / remotes.
  - `swarm-cli config init [--force]` — write a default `swarm_config.json` (refuses to overwrite unless `--force`). The committed template is [`swarm_config.example.json`](./swarm_config.example.json).
  - `swarm-cli config add --section llm|mcpServers|remotes --name <name> --json '<...>'` — add a profile, MCP server, or remote entry.
  - `swarm-cli config remove --section … --name …` — remove an entry.
  - There is **no** `swarm-cli configure`, `list-config`, or `set` command; use `config` as above or edit JSON.
- **Remote harnesses (`swarm-cli remotes`):** persist + probe + operate Hermes / OMB / Rakazo. See [docs/REMOTE_HARNESSES.md](docs/REMOTE_HARNESSES.md). Local computer-control adaptation (browser vs Docker sandbox vs host via placed remotes; SaaS deferred) is [ADR-007](docs/adr/007-local-computer-control.md) (REQ-189 / #645).
- **Manual:**
  - Edit `~/.config/swarm/swarm_config.json` directly (or wherever your config is located).

---

## 1. Config File Location and Discovery

**Recommended location:** `~/.config/swarm/swarm_config.json` (XDG Base Directory
Spec — overridable with `XDG_CONFIG_HOME`).

The repository ships [`swarm_config.example.json`](./swarm_config.example.json)
as the copy-paste template (no secrets, no operator LAN hosts). A checkout-local
`swarm_config.json` is gitignored — copy the example, or run
`swarm-cli config init` to write the XDG file.

Config is resolved in this order:

1. `SWARM_CONFIG_PATH` (explicit absolute path) — wins if set and the file exists.
2. **XDG**: `~/.config/swarm/swarm_config.json` (or `$XDG_CONFIG_HOME/swarm/…`).
3. `./swarm_config.json` in the current working directory.

So dropping a config at `~/.config/swarm/swarm_config.json` is enough — both
`swarm-cli` and the API server (`swarm-api` / uvicorn ASGI) pick it up
with no environment variable. Set `SWARM_CONFIG_PATH` only when you want to point
at a non-standard path explicitly. (`swarm-cli` additionally does an upward
directory search for a project-local `swarm_config.json`.)

- **If missing:** Swarm generates a default config using `OPENAI_API_KEY` and the official OpenAI endpoint (with a warning).

> Paths and all environment variables (`SWARM_CONFIG_PATH`, `SWARM_RESPONSES_DIR`,
> server/auth/feature flags, provider keys) are consolidated in one place:
> **[Environment Variables](#environment-variables)** below. Auth & trust model
> (Bearer vs session, WS, Explorer bridge, workdir, blueprint sandbox):
> **[docs/AUTH.md](./docs/AUTH.md)**.

---

## 2. Example Config Structure

```json
{
  "llm": {
    "gpt-4o": {
      "provider": "openai",
      "model": "gpt-4o",
      "api_key": "${OPENAI_API_KEY}",
      "base_url": "https://api.openai.com/v1",
      "pricing": { "prompt": 0.000005, "completion": 0.000015, "unit": "per_token" }
    },
    "o3-mini": {
      "provider": "openrouter",
      "model": "openrouter/o3-mini",
      "api_key": "${OPENROUTER_API_KEY}",
      "base_url": "https://openrouter.ai/api/v1",
      "pricing": { "prompt": 0.000001, "completion": 0.000002, "unit": "per_token" }
    },
    "envvars_only": {
      "provider": "${LLM_PROVIDER}",
      "model": "${LLM_MODEL}",
      "api_key": "${LLM_API_KEY}",
      "base_url": "${LLM_BASE_URL}",
      "pricing": {
        "prompt": "${LLM_PROMPT_COST}",
        "completion": "${LLM_COMPLETION_COST}",
        "unit": "${LLM_COST_UNIT}"
      }
    }
  },
  "settings": {
    "default_llm_profile": "gpt-4o",
    "override_per_task": false,
    "task_llm_profiles": {
      "orchestration": "gpt-4o",
      "auxiliary": "gpt-4o-mini",
      "delegation": "o3"
    }
  },
  "blueprints": {
    "rue_code": { "default_model": "o3-mini" },
    "geese": { "default_model": "gpt-4o" }
  },
  "mcpServers": {
    "main": {
      "url": "http://localhost:8001",
      "api_key": "${MCP_API_KEY}",
      "description": "Primary local MCP server"
    },
    "cloud": {
      "url": "https://mcp.example.com",
      "api_key": "${MCP_CLOUD_KEY}",
      "description": "Cloud backup MCP server"
    }
  }
}
```

---

## 3. Key Features

- **Model Profiles by Name:** Each key under `llm` matches a model (e.g., `gpt-4o`, `o3-mini`).
- **Cost Tracking:** `pricing` section per model, used for cost estimation/reporting.
- **Environment Variables:** Use `${ENVVAR}` for any value.
- **Per-Blueprint Model Overrides:** `blueprints` section allows each blueprint to specify a `default_model`.
- **Agent/Task Overrides:** Blueprints themselves can choose models per agent/task.
- **MCP Servers:** The `mcpServers` section defines available MCP servers, their endpoints, and credentials.
- **Remote harnesses:** The `remotes` section stores `base_url` + auth for Hermes, OpenMausBot, Rakazo, and nested open-swarm (`swarm`). CLI `swarm-cli remotes set|health|operate|team|place|unplace`; REST `/v1/remotes/` and `/v1/agent-team/`. `agent_team.members` is the handoff Team roster (not `/v1/teams/` Profiles). Nested swarm default is the stub `http://127.0.0.1:9`; v1 refuses this process listen URL. Do **not** point remotes at Fly open-litellm. LAN LLM for this swarm is `http://10.0.0.30:8000/v1`. Full map: [docs/REMOTE_HARNESSES.md](docs/REMOTE_HARNESSES.md).
- **CLI Agent Fusion:** A `cli_agents` section wraps your installed agentic CLIs (grok/agy/claude/gemini/codex/opencode/pi) as subagents, with `cli_fusion` / `cli_map` / `cli_orchestrator` blocks composing them. The section starts **empty** until you add (Settings one-click or `swarm-cli cli-agents --init --write`). Startup / `GET /v1/cli-agents/` discovers those binaries on PATH without an auth check and lists them as suggestions. Calling the API with `model: "cli_fusion"` (consensus across CLIs) or `model: "cli_map"` (many agents, each one CLI) runs them. Full reference in **[docs/CLI_FUSION.md](docs/CLI_FUSION.md)** and the deploy runbook **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.
- **Per-task override (REQ-43):** `settings.override_per_task` plus `settings.task_llm_profiles` map task classes (`orchestration` / `auxiliary` / `delegation`) to any connected model id. Those names are roles, not required slugs. SPA Settings auto-picks three models when the user never opens the picker. Live CLI catalogs come from sibling REQ-44 (`{cli, models}`) when that helper is merged; until then auto-pick stubs on `/v1/models` + fixtures and does not scrape CLI `--help`. Off = everything uses Default.
- **Fallbacks:**
  - If a **named** model/profile is requested and missing, the system logs a **warning** and falls back to `settings.default_llm_profile` (else `default`). This is never silent.
  - Unspecified profile (no name requested) quietly uses the documented default chain — that quiet path is intentional.
  - If config is missing, a default config is generated (uses OpenAI endpoint).

---

## 4. How Loading Works

1. **Locate and load** `swarm_config.json` (prefer XDG, fallback to cwd/project).
2. **Substitute environment variables** for any `${...}` values.
3. **Select the active LLM profile** from `settings.default_llm_profile`, unless overridden by a blueprint (`llm_profile` / `default_model`) or CLI/`DEFAULT_LLM`.
4. **Blueprints:**
    - Use their own `default_model` / `llm_profile` if set in config.
    - May specify a model per agent/task within their own logic.
5. **If a requested model/profile is missing:**
    - Resolution (`_resolve_llm_profile` / runtime): **warning** + fall back to `settings.default_llm_profile` or `default`.
    - Active profile property (`BlueprintBase.llm_profile`): **raises** a clear error (fail-loud for callers that need a real profile).
    - Optional lookup (`get_llm_profile(name)`): **warning** + empty dict `{}`.

---

## 5. CLI vs Manual Configuration

- The `swarm-cli` is the recommended tool for config tasks:
  - `swarm-cli config init` / `config list` / `config add` / `config remove` (LLM profiles and MCP servers)
  - `swarm-cli moa-init` (merge default Mixture-of-Agents config block)
  - `swarm-cli cli-agents --init [--write]` (wire CLI fusion/MoA over installed CLIs)
- Manual editing of `swarm_config.json` is fully supported for power users and automation.

---

## 6. Security & Redaction

Operator-facing auth/trust (API Bearer, Django session, websockets, Session
Explorer bridge, workdir confinement, user-blueprint AST sandbox, CSRF / prod
CSP) is documented in **[docs/AUTH.md](./docs/AUTH.md)**.

- All sensitive config values (API keys, tokens) are redacted in logs.
- Never log full secrets.

`swarm.utils.redact.redact_sensitive_data` walks dicts/lists recursively and
masks any value whose **key** matches a sensitive name (e.g. `api_key`,
`password`, `token`, `secret`). Details:

- **Case-insensitive** key matching (`API_KEY`, `Password` are caught).
- **Type-agnostic** — a sensitive value is masked even if it isn't a string
  (ints, bools, or a nested dict/list stored under a secret key are masked
  wholesale, never passed through).
- By default the value is replaced with `[REDACTED]`. Pass `reveal_chars=N` to
  keep the first/last `N` characters for debugging (`abc…hij`); values too short
  to reveal safely are fully masked.

---

## 7. Troubleshooting

- **Missing config:** Default file is generated, warning printed.
- **Missing / typo model profile:** Warning printed, then fallback to `settings.default_llm_profile` or `default` (check logs for `LLM profile '…' not found`). The `llm_profile` property raises instead of returning empty data.
- **Missing API key:** Error raised if not found after env substitution.
- **Cost not shown:** Add `pricing` section to the model profile.

---

## 8. Extending & Testing

- Add new models/providers by updating the `llm` section.
- Use envvars for secrets and endpoints.
- Add/override MCP servers as needed.
- Tests should cover config loading, env substitution, fallback logic, and cost reporting.

---

## 9. Memory (experimental)

Blueprints can opt in to persistent, cross-conversation memory. **mem0 is the default and currently the only working backend.** Install its dependency via the `memory` extra:

```sh
pip install open-swarm[memory]   # or: uv sync --extra memory
```

### Config Shape

Add a `memory` block either per blueprint (under `blueprints.<id>`, checked first) or at the top level of the config (applies to all blueprints):

```json
{
  "blueprints": {
    "my_blueprint": {
      "memory": {
        "backend": "mem0",
        "user_id": "alice",
        "limit": 5,
        "config": { "vector_store": { "provider": "qdrant" } }
      }
    }
  }
}
```

Keys (all optional except `backend`):

| Key       | Description |
|-----------|-------------|
| `backend` | `"mem0"` is the only implemented backend. Empty/`"none"` disables memory; unknown names log a warning and disable. **Required** — without it the block is ignored. |
| `user_id` | Default user id for memory search/storage when a run doesn't pass one (default: `"default"`). |
| `limit`   | Max memory snippets returned per search (default: `5`). |
| `config`  | Dict passed verbatim to `mem0.Memory.from_config(...)` (vector store, LLM, etc. — see mem0 docs). Omit to use mem0's defaults. |

**Custom OpenAI-compatible endpoint (e.g. LiteLLM):** mem0 accepts a base-URL
override per component via the `config` block (forwarded verbatim):

```json
"memory": {
  "backend": "mem0",
  "config": {
    "llm":      {"provider": "openai", "config": {"model": "gpt-4o-mini", "openai_base_url": "${LITELLM_BASE_URL}", "api_key": "${LITELLM_API_KEY}"}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small", "openai_base_url": "${LITELLM_BASE_URL}", "api_key": "${LITELLM_API_KEY}"}}
  }
}
```

Note: the endpoint must also proxy an **embeddings** model — mem0 needs one
for its vector store, not just a chat model.

### Behavior

- **Pre-run retrieval:** before each `run()`, the latest user message is used to search memory; any hits are prepended as a single system message (`"Relevant memories from previous conversations: ..."`).
- **Post-run storage:** after the run, the input messages plus the assistant's output are stored under `user_id`. The injected memory system message is not re-stored.
- **Strict no-op when unconfigured:** with no `memory` block (or no `backend` key), `run()` is untouched and behavior is byte-for-byte identical to before.
- **Graceful degradation:** if `backend: "mem0"` is set but the `mem0ai` package is not installed, a warning is logged and the blueprint continues without memory — nothing raises.
- **Error isolation:** memory search/storage failures are logged as warnings and never break a run.

### Status

This integration is covered by unit tests using fake in-memory backends; it has **not yet been validated end-to-end against a live mem0 instance**. The `langmem` and `papr` backends are placeholders: selecting them in config logs a warning and disables memory, and instantiating their classes directly raises `NotImplementedError`.

---

## Environment Variables

The canonical reference. [`.env.example`](./.env.example) is the copy-paste
template; this table explains what each variable does. Secrets belong in the
environment / `.env`, never in `swarm_config.json` (reference them with
`${VAR}`).

### Config & state paths

| Variable | Purpose | Default |
|---|---|---|
| `SWARM_CONFIG_PATH` | Explicit path to `swarm_config.json` (wins over discovery). | unset → XDG-first discovery (see [§1](#1-config-file-location-and-discovery)) |
| `SWARM_CONFIG_FORCE_ENV` | Recovery: env wins over persisted non-secret topology (Settings fields become read-only). | unset (off) |
| `SWARM_<ENV>_OVERRIDE` | Per-key force-env (e.g. `SWARM_DEFAULT_LLM_OVERRIDE=1`, `SWARM_HERMES_BASE_URL_OVERRIDE=1`). | unset |
| `XDG_CONFIG_HOME` | Base for the config dir (`…/swarm/swarm_config.json`, `teams.json` aliases, `team_rosters.json` composition). | `~/.config` |
| `SWARM_RESPONSES_DIR` | Where `/v1/responses` stores records for `previous_response_id` chaining and `GET`/`DELETE`. | `$XDG_DATA_HOME/swarm/responses` (i.e. `~/.local/share/swarm/responses`) |
| `SWARM_RESPONSES_SYNC_TIMEOUT` | Default seconds a `/v1/responses` request waits inline before auto-escalating to a queued handle (per-request override: `max_wait_seconds`). Unset = fully-blocking sync. | unset |
| `SWARM_RESPONSES_MAX_AGE_DAYS` | Optional retention for `swarm.core.responses_store.prune_expired()` (terminal records only; skips `queued`/`in_progress`). **Not applied automatically** — call the helper or cron it. Unset / ≤0 = prune no-op when age omitted. | unset |
| `SWARM_CHAT_DIR` | Per-agent SPA chat JSON store (`active/<user>/<agent>.json` + `trash/`). Used to restore Chat after reload / agent switch. Retention UI is Settings-only. | `$SWARM_USER_DATA_DIR/chats` (platformdirs if unset) |
| `SWARM_ATTACHMENTS_DIR` | Composer file-attach bytes (REQ-38). Metadata is Django `ChatAttachment`; paths are `{user_key}/{uuid}` only. | `$SWARM_USER_DATA_DIR/attachments` |
| `SWARM_CHAT_MAX_AGE_DAYS` | Auto-**move to trash** (never hard-delete) inactive agent chats older than this many days when Settings loads. `0` disables. Empty trash is a manual Settings action. | `90` |
| `SWARM_ARCHIVED_AGENT_RETENTION_DAYS` | Days an Support/CoS-archived rail seat stays recoverable before `manage.py purge_archived_agents --apply` hard-deletes it (REQ-154). Unstamped rows are skipped unless `--include-unstamped`. **Chats are not deleted by this job** — they still follow `SWARM_CHAT_MAX_AGE_DAYS`. `<=0` = treat archived rows as immediately due. | `30` |
| `SWARM_RUNTIME_MODE` | Where **this app** is running (SPA runtime banner). `bare-metal` (dedicated harness, no container), `sandbox-home` (compose with `$HOME` / `SWARM_SANDBOX_ROOT` mapped), `sandbox-isolated` (compose without that tree). Missing / unrecognized → **unknown** (never fake a green sandbox). This is **not** the browser-control or computer-control provider ([ADR-007](docs/adr/007-local-computer-control.md)). Compose: `docker-compose.yml` defaults `sandbox-home`; `docker-compose.dev.yml` also defaults sandbox-home. | unset → unknown |
| `SWARM_CHROME_CDP` | Optional Chrome DevTools URL for Playwright **attach** (`Browser (this machine)`). Launch is used when unset. | unset |
| `XDG_DATA_HOME` | Base for state data (responses store). | `~/.local/share` |
| `SWARM_WORKSPACES_DIR` / `WORKSPACES_DIR` | Root for per-request `params.workdir` / `params.cwd` and `swarm-cli moa --workdir` / `--cwd`. Relative paths resolve here; absolute paths outside this root are rejected unless unrestricted (below). | `$XDG_DATA_HOME/…/swarm/workspaces` (via `SWARM_USER_DATA_DIR` / platformdirs) |
| `ALLOW_UNRESTRICTED_WORKDIR` | When `true`/`1`/`yes`, allow absolute workdirs outside `SWARM_WORKSPACES_DIR` (local CLI power users writing under `/tmp/…` or a repo checkout). Keep **off** for API servers. | `false` |
| `SWARM_SOFTWARE_DEV_WORKDIR` | Default **local** workdir for `software_dev` file tools when `params.workdir` / `cwd` is unset. This is the **API-host filesystem** — a path that only exists on another host is invisible. | `$PWD/.software_dev_ws` |
| `SWARM_SOFTWARE_DEV_REMOTE_WORKDIR` | Optional SSH remote tree (`user@host:path` or `ssh://user@host/path`). Same as `params.remote_workdir`. | unset (local FS) |
| `SWARM_SOFTWARE_DEV_SSH_HOST` / `_SSH_USER` / `_SSH_PORT` | SSH target when the remote path is bare (or to override a URL). Refuses to guess a host. | unset |
| `SWARM_SOFTWARE_DEV_SSH_IDENTITY` | Value is a key **file path** (not key material). `params.ssh_identity_env` names this variable. Never paste a private key. | unset |
| `SWARM_BLUEPRINT_PATHS` | Extra blueprint roots scanned **in addition** to the bundled set (os.pathsep-separated). The user data blueprints dir is included **only when** `SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY=true` (default off). Bundled blueprints win on name collision. | unset |

### Server, security & auth

| Variable | Purpose | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret. **Required in production** (server refuses to start without it). | dev only: fixed insecure fallback |
| `DJANGO_DEBUG` | Debug mode (verbose errors, DEBUG logging, relaxed auth). Keep **off** in prod. | `false` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts (whitespace-trimmed, empties dropped). **Required in production.** In debug, `*` is prepended so LAN Host / websocket Origin work. | dev: `*,localhost,127.0.0.1` |
| `SWARM_ALLOW_ANONYMOUS` | Auth-free preview user. Unset: auto-on for DEBUG + LAN/loopback (HTTP session + websocket). `1` force on (any IP); `0` force off. Never implicit in pytest or production. | unset (debug LAN) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins for CSRF on mutating routes (whitespace-trimmed, empties dropped). Must include scheme + host + port. Add LAN/proxy origins (e.g. `http://10.0.0.30:8000`) when the UI is not on localhost. | `http://localhost:8000,http://127.0.0.1:8000` |
| `API_AUTH_TOKEN` | Bearer token OpenAI clients present to the API. Primary when set. **Required in production** (`DEBUG=False`) unless `SWARM_ALLOW_NO_AUTH=true` — server refuses to start without any token. | none |
| `SWARM_API_KEY` | Legacy alias for `API_AUTH_TOKEN` (used if the latter is unset). | none |
| `API_AUTH_TOKENS` / `SWARM_API_KEYS` | Optional comma-separated list of additional (or sole) accepted Bearer secrets. Merged with the single-token vars; each key maps to a distinct ownership principal (`token:<sha256-prefix>`). When API auth is on, Session Explorer also shows those token-owned sessions to a logged-in Django operator (REST IDOR stays same-principal). | none |
| `ENABLE_API_AUTH` | **Django setting** (not an env toggle): auto-on when any API auth token is set at startup. Require auth on `/v1/*` (including `/v1/models` and `/v1/blueprints`). Also enables the Session Explorer operator bridge for token-owned rows. | on iff token(s) set |
| `SWARM_SECURE_COOKIES` | When `DEBUG=False`, force `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE`. Default **on** in production; set `false` for HTTP-only staging. (No effect when `DEBUG=True` — cookies stay non-Secure for local HTTP.) | prod: true |
| `DJANGO_X_FRAME_OPTIONS` | Env override for `X_FRAME_OPTIONS`, read **only** when `DEBUG=False`. `XFrameOptionsMiddleware` is always installed; Django’s default is already `DENY` in debug and prod. | `DENY` |
| `SWARM_CSP` | When `DEBUG=False`, enable `Content-Security-Policy` via `ContentSecurityPolicyMiddleware` (`script-src 'self'`; `style-src 'self'` — operator CSS in `static/css/operator.css`, no `'unsafe-inline'`; vendored Bootstrap/Prism/FA; no CDN). Set `false` to omit the header. | prod: on |
| `SWARM_ALLOW_NO_AUTH` | Allow booting in production **without** a token (warns) — for when an external OAuth proxy / API gateway already gates access. | `false` |
| `ALLOW_TESTUSER_AUTOLOGIN` | Dev-only auto-login (debug only, random password). | `false` |
| `HOST` / `PORT` | Bind address/port for the server. | `0.0.0.0` / `8000` |
| `SWARM_UVICORN_WORKERS` | uvicorn worker count. Prefer **1** — inflight limits are process-local; cancel is filesystem-shared when workers share `SWARM_RESPONSES_DIR`. | `1` |
| `SWARM_ENFORCE_SINGLE_WORKER` | When true (default), refuse `SWARM_UVICORN_WORKERS` &gt; 1 at app startup. | `true` |
| `SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY` | When true, scan user blueprint dirs (exec_module). Default off so creator saves are write-only. | `false` |
| `SWARM_USER_BLUEPRINT_SANDBOX` | AST safety gate before `exec_module` for user/community blueprint roots (and creator save validation). Set `false` only to opt out. | `true` |

### Database (REQ-123 / #508)

Durable default is **local Postgres in docker compose**. Cloud operators
point at any Postgres with `DATABASE_URL`. **Neon is test/CI/experiments
only** (free-tier always-on ~day 17). Short guide:
[docs/DATABASE.md](docs/DATABASE.md).

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Wins. Postgres DSN (`postgres://` / `postgresql://`). Compose sets `postgres://swarm:swarm@postgres:5432/swarm` (local placeholder, not a secret). | compose: local `postgres` service; else unset → SQLite |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Discrete knobs when `DATABASE_URL` is empty. | compose: `postgres` / `5432` / `swarm` / `swarm` / `swarm` |
| `DJANGO_DATABASE` | If `postgres` / `postgresql` without URL/host, startup **fails fast** (exit 78). `sqlite` is documentary. | unset |
| `DJANGO_DB_NAME` / `SQLITE_DB_PATH` | SQLite file when Postgres is not configured (pytest, desktop, tiny native demos). | `/tmp/db.sqlite3` |
| `SWARM_SKIP_DB_HEALTH` | Skip the startup Postgres connect check. Emergency only. | unset (check on) |

Unreachable Postgres or a Neon quota/compute error **exits 78** with a
clear, redacted message — see
[docs/RUNBOOK_NEON_QUOTA_CRASH_LOOP.md](docs/RUNBOOK_NEON_QUOTA_CRASH_LOOP.md).

### Feature flags

| Variable | Purpose | Default |
|---|---|---|
| `ENABLE_WEBUI` | Serve the web UI (`/` prefers SPA when built; canonical operator UI is Django trailing-slash pages — bare `/teams`→`/teams/launch/`, `/blueprints`→`/blueprint-library/`, etc.). Teams admin / blueprint library / sessions / settings need a login session; login POST is CSRF-protected. | on |
| `SWARM_RUNTIME` | REQ-45 isolation mode announced to the app: `bare-metal` (no container), `sandbox-home` (compose with `$HOME` / `SWARM_SANDBOX_ROOT` mapped), `sandbox-isolated` (compose, no home map). Base `docker-compose.yml` defaults to `sandbox-home`. Missing = unknown, not a fake green. | compose: `sandbox-home`; else unset |
| `ENABLE_ADMIN` | Mount the Django admin. | off |
| `ENABLE_GITHUB_MARKETPLACE` | GitHub-topics blueprint discovery (`/marketplace/github/…`). Upstream GitHub failures return **429/502**, not an empty 200. Client `org`/`topic` must match `GITHUB_MARKETPLACE_ORG_ALLOWLIST` / `GITHUB_MARKETPLACE_TOPICS` when those lists are non-empty (else **400**); empty org allowlist means unscoped open search. | off |
| `ENABLE_MCP_SERVER` | Aspirational MCP-server mode — warns loudly; see [docs/mcp_server_mode.md](./docs/mcp_server_mode.md). | off |

### Behavior & diagnostics

| Variable | Purpose | Default |
|---|---|---|
| `SWARM_TEST_MODE` | Deterministic, network-free blueprint output (testing). | off |
| `DJANGO_LOG_LEVEL` / `LOGLEVEL` | Log verbosity. | `INFO` |
| `STATEFUL_CHAT_ID_PATH` | `\|\|`-separated JMESPath expressions used to extract the chat/session id from an incoming request payload (first non-empty match wins). | `metadata.channelInfo.channelId`, `metadata.userInfo.userId`, … |
| `SWARM_TRUNCATION_MODE` | Context truncation strategy when trimming message history to fit the token budget: `pairs` (sophisticated — keeps assistant/tool call pairs intact) or `simple` (most-recent only). Unknown values fall back to `simple`. | `pairs` |

### Speech (REQ-77)

Composer microphone and assistant read-aloud default to the **OS/browser**
implementation (`SpeechRecognition` / `speechSynthesis`). Settings → Speech
can opt each of STT and TTS into a custom OpenAI-compatible endpoint
(`/v1/audio/transcriptions`, `/v1/audio/speech`). Fields: base URL, model id,
**api-key env name only**. Empty custom URL never guesses a host. Persist stores
`${STT_API_KEY}` / `${TTS_API_KEY}` placeholders — never a live token.

| Variable | Purpose | Default |
|---|---|---|
| `STT_API_KEY` | Value for the custom transcription env name (if you opt in). | unset |
| `TTS_API_KEY` | Value for the custom speech env name (if you opt in). | unset |
| `SPEECH_STT_BASE_URL` / `SPEECH_TTS_BASE_URL` | Optional env override for a custom audio base URL. Empty = no host. | unset |
| `SPEECH_STT_SOURCE` / `SPEECH_TTS_SOURCE` | `system` (default) or `custom`. Custom is unused until a base URL is set. | `system` |

`GET/PATCH /v1/speech/`, `POST /v1/speech/transcribe/`, `POST /v1/speech/speak/`.
Missing/DOWN is an honest info line. Tests stub system APIs and HTTP.

### Provider credentials & integrations

Model/provider keys and service endpoints — `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`,
`LITELLM_*`, `OLLAMA_BASE_URL`, plus MCP/tool keys (`BRAVE_API_KEY`,
`GITHUB_TOKEN`, `QDRANT_*`, …) — are listed with inline guidance in
[`.env.example`](./.env.example). Reference them in `swarm_config.json` via
`${VAR}`.

> **Note for CLI agents:** wrapped CLIs (`claude`, `gemini`, `grok`, …) carry
> **their own** authentication — Open Swarm never reads or stores it. These
> provider keys are only for `llm` profiles and MCP tool servers.

---

## 10. Herdr members (REQ-21)

Persisted Herdr connections (`kind=herdr`) live in the Django database
(Compose Postgres, or SQLite when `DATABASE_URL` is unset). Do **not**
point this feature at Neon. Empty `remote` means
localhost — `herdr` with no `--remote` (unix sockets under `~/.config/herdr/`).
When `remote` is set, every call is `herdr --remote <value> …`.

CRUD: `/v1/herdr-agents/`. Discover live panes: `/v1/herdr-agents/discover/`
(`herdr agent list` + `herdr workspace list`). Operator UI: `/settings/` and
`/teams/#herdr-members`. Wrapper: `swarm.herdr.HerdrClient`. Full notes:
[docs/HERDR.md](docs/HERDR.md) (not Hermes/OMB/Rakazo; cloud CI must mock `herdr`).

**REQ-64 remotes kind + REQ-100 SSH shape:** add `herdr` in Settings. This is
**not** an HTTP remote like OpenMousBot / Hermes / Rakazo.

* Local: `swarm-cli remotes set herdr --herdr-mode local` (localhost URL only
  when you choose that). Open Swarm talks to Herdr on this host; no SSH.
* Remote: `swarm-cli remotes set herdr --herdr-mode ssh --ssh-host <host>
  --ssh-user <user> --ssh-identity-env HERDR_SSH_IDENTITY`. Health / list /
  send / interrogate go over SSH to that Herdr host, then to Herdr’s CLIs.
  Identity is an env-var *name* (path), never a private key.

Missing SSH config is a clear error — not a silent other-host. Tests stub SSH
(and leftover localhost HTTP). No tokens or guessed hosts in the repo.

---

For more, see the main [README.md](./README.md) or run `swarm-cli --help`.
