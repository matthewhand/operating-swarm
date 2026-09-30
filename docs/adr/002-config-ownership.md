# ADR-002: Config ownership — `.env` vs XDG `swarm_config.json` vs Django DB

- **Status:** Accepted (implemented for Settings coverage in #776)
- **Date:** 2026-09-04
- **Issue:** [#541](https://github.com/matthewhand/open-swarm/issues/541) (REQ-145); addendum [#776](https://github.com/matthewhand/open-swarm/issues/776)
- **Related:** [#540](https://github.com/matthewhand/open-swarm/issues/540) (REQ-144 prefs), [#508](https://github.com/matthewhand/open-swarm/issues/508) (REQ-123 Postgres compose), [#554](https://github.com/matthewhand/open-swarm/issues/554) / [ADR-003](./003-desktop-packaging.md) (desktop profile paths), [CONFIGURATION.md](../../CONFIGURATION.md)
- **Supersedes:** none. Complements [ADR-001](../ADR-001-primary-ui.md) (UI chrome), not config SoT.

**Decision:** **hybrid** (not pure A, not pure B). Secrets stay env-only.
Non-secret topology and prefs persist in the ownership-table SoT. Precedence
is `force-env > persisted > env-bootstrap > defaults`. Settings must badge
every field that has an env twin. Recovery uses explicit force-env flags.
No sync daemon.

This ADR is **feasibility-first**: it records what the code does on `main`
(`04ccb53a` at writing) and then picks one ownership table. It does **not**
implement sync, migrations, or Settings UI badges.

No secrets are documented here. Use `${VAR}` names only.

---

## Issue quote (REQ-145)

**Intent:** Operators and ephemeral deploys know where truth lives; no silent drift.

**Success (this Issue):**

1. Look-only Cursor cloud (or engineer) produces an **ADR markdown PR** answering the questions with file/path evidence.
2. ADR picks **one** direction (amend strawman or replace); lists migrations / follow-up implement Issues.
3. No code behaviour change in the ADR PR beyond docs (or a tiny inventory script if needed).
4. `Fixes` this Issue when ADR merges.

**Constraints:** Look-only / docs first. No Neon. No secrets in ADR. Park implement behind agreement. Related: #540 prefs, #508 Postgres compose, CONFIGURATION.md.

Owner / CoS notes from the Issue: prefer one clear winner per concern over a bidirectional sync engine. Skeptic PASS if this ADR answers dual-SoT and Docker ephemeral.

Matthew refinement (Issue comment, 2026-09-04): evaluate **A** (env bootstraps; Settings override env), **B** (DB/Settings SoT; env force-override for recovery), or a **hybrid with explicit precedence and UI badges**. Secrets stay env-only. No bidirectional sync daemon.

---

## 1. Feasibility (what exists today)

The strawman is **mostly already true for harness topology writes**, and **already
false for chats and per-user prefs**. The expensive parts of consolidation are
not “pick a new store” — they are:

1. **Stale boot snapshot** vs **live file re-read** (same JSON, two lifetimes).
2. **Default Docker mounts XDG config read-only**, so WebUI persist can fail
   even though the API writes the same path `swarm-cli` uses.
3. **Two XDG directory helpers** that do not always resolve to the same folder.
4. **Chat dual-write** (JSON SoT + Django mirror) and **browser-local prefs**.

A sync engine would paper over (1)–(4). This ADR rejects that.

---

## 2. Evidence: three stores (read vs write; WebUI vs swarm-cli)

### 2.1 Environment / `.env` (ops-owned; app never writes)

| Surface | Read | Write |
|---|---|---|
| Process / systemd env | Wins over files | Operator / orchestrator |
| XDG `~/.config/swarm/.env` | Yes (after process env) | Operator only |
| Project-root `.env` | Yes (lowest file fallback) | Operator only |
| Docker `env_file: .env` | Injected at container start | Host file; app does not rewrite |
| WebUI / Django Settings | **Read** (redacted) | **No** |
| `swarm-cli` | Reads via the same process env after dotenv load | **No** `.env` writer |

**Load path (read):** `src/swarm/utils/dotenv_load.py` — `load_swarm_dotenv()`:

1. Keys already in `os.environ` are never overwritten.
2. Project-root `.env` is loaded with `override=False`.
3. XDG `~/.config/swarm/.env` (or `$XDG_CONFIG_HOME/swarm/.env`) fills keys
   that were **not** already in the process environment (XDG wins over
   project-only keys).

Called from `src/swarm/settings.py`, `src/manage.py`, `src/swarm/wsgi.py`,
`src/swarm/management/commands/runserver.py`. Canonical variable list:
[CONFIGURATION.md § Environment Variables](../../CONFIGURATION.md#environment-variables).

**Substitution (read into JSON):** `${VAR}` in `swarm_config.json` is expanded
by the package reader `config_loader.load_config` (`_substitute_env_vars` /
`os.path.expandvars`). JSON I/O is shared (`read_config_json` /
`write_config_json`). Inside `config_loader.py`, `load_config` /
`save_config` / `validate_config` are defined once; a second copy in that
file used to shadow the first. Django settings and the provider rate limiter
call that reader (#1435). `config_manager.resolve_placeholders` remains for
the CLI helper, and `blueprint_base.py` (`_load_configuration`) still
substitutes when it builds a blueprint profile. `ruff check --select F811
src/` is the CI gate against a later copy shadowing this reader.

**WebUI:** Django `/settings/` and `GET` settings API
(`src/swarm/views/settings_views.py`) collect env-backed flags via
`src/swarm/views/settings_manager.py` and redact secrets. Both endpoints are
`GET` only. `environment_variables()` lists `DJANGO_*` / `SWARM_*` / provider
prefixes with sensitive keys masked. **No view writes `.env`.**

**Docker:** `docker-compose.yml` `env_file: .env` (`required: false`). Explicit
`environment:` keys (including `PORT`) win over the file.

**Verdict:** `.env` / process env is **ops-owned, read-only to the app**.
Feasible to keep as the secrets + deploy-flag SoT. Do not add a Settings
plaintext editor that rewrites `.env`.

---

### 2.2 XDG / `SWARM_CONFIG_PATH` `swarm_config.json` (harness topology)

**Discovery (read),** `src/swarm/core/config_loader.py` `find_config_file()`:

1. Explicit `--config` / `specific_path`
2. `SWARM_CONFIG_PATH` if the file exists
3. XDG: `$XDG_CONFIG_HOME/swarm/swarm_config.json` or `~/.config/swarm/swarm_config.json`
   (`_xdg_config_path()`)
4. Upward search / default dir / cwd `./swarm_config.json`

`swarm-cli config` / `moa-init` / `cli-agents --write` use that helper, then
fall back to `get_user_config_dir_for_swarm() / "swarm_config.json"`
(`src/swarm/core/swarm_cli.py`).

**Boot snapshot (server):** `src/swarm/apps.py` `SwarmConfig.ready()` →
`_load_swarm_config()` loads **once** into `AppConfig.config` from
`SWARM_CONFIG_PATH` or `_xdg_config_path()` only (cwd is *not* loaded here).
Comment in that function: load once so every blueprint sees the same file.

**Blueprint consumers (read snapshot):** `src/swarm/core/blueprint_base.py`
`_load_configuration()` prefers `apps.get_app_config('swarm').config` if
non-empty, else re-discovers the file. That means a **new blueprint instance
after boot keeps the ready() snapshot** unless `AppConfig.config` is empty.

**Live re-read (same file):** remotes and LLM-settings helpers call
`src/swarm/core/remotes.py` `resolve_config_path()` / `load_raw_config()` —
`find_config_file()` then XDG fallback — **on each request**, not the
`AppConfig` dict.

| Writer | Path | Same file as CLI? |
|---|---|---|
| `swarm-cli config init\|add\|remove` | `find_config_file()` else XDG `swarm_config.json` | Yes (canonical CLI writer) |
| `swarm-cli remotes set\|place\|unplace` | `persist_remote` / `persist_agent_team` | Yes |
| `swarm-cli moa-init --write`, `cli-agents --init --write` | same discovery | Yes |
| WebUI SPA Settings `PATCH /v1/llm-profiles/` | `src/swarm/views/llm_profiles_api.py` → `llm_task_routing.persist_llm_settings()` → `load_raw_config()` + `path.write_text` | **Yes** |
| WebUI SPA `POST/PATCH/DELETE /v1/remotes/` | `src/swarm/views/remotes_api.py` → `persist_remote` | **Yes** |
| WebUI / API `PATCH /v1/agent-team/` | `persist_agent_team` | **Yes** |
| Django `/settings/` dashboard | `settings_manager.collect_*` via `load_config()` | **Read only** (no persist) |
| Router designer overlay | `src/swarm/core/remote_teams.py` `persist_remote_overlay()` | Same file **and** mutates `AppConfig.config` in memory |

**Remotes precedence today (already env-wins):** `load_remote()` docstring:
“Defaults ← swarm_config.json remotes ← env (env wins).” Env keys such as
`HERMES_BASE_URL` / `HERMES_API_KEY` overwrite the file at **read** time.
The file is still written when Settings/CLI persist.

**Docker default:** `docker-compose.yml` bind-mounts
`${HOME}/.config/swarm:${HOME}/.config/swarm:ro` — **read-only**. The data
volume `${HOME}/.local/share/swarm` is writable (SQLite + `/v1/responses`).
WebUI persist to XDG **fails with `OSError` / HTTP 500** on an unmodified
compose stack even though the code path is the same as `swarm-cli` on the host.

**Config root (unified, #1434):** `swarm.core.paths.config_root()` is the
only resolver. `SWARM_CONFIG_DIR` overrides it. Windows uses
`%APPDATA%/OpenSwarm/swarm`; other platforms use `$XDG_CONFIG_HOME/swarm`
or `~/.config/swarm`. `_xdg_config_path()`, `get_swarm_config_file()`, and
`get_user_config_dir_for_swarm()` all delegate to that root. Startup
copies a legacy author/platform tree onto the canonical root and logs a
warning, or refuses when the same relative file differs. The copy runs
before dotenv load so the first process reads a migrated `.env`, and it
does not run under pytest. Per-file env
vars (`SWARM_CONFIG_PATH`, `SWARM_ROUTER_DESIGNS`,
`SWARM_AGENT_SETTINGS_PATH`, plus data-dir overlays) are file overlays,
not a second root. Compose mounts that folder; CLI create-if-missing
writes there. No ongoing syncer. Data/cache roots stay on platformdirs
(`#1435`). Settings and `/health` report the resolved root.

**Config loaders:** `config_loader.py` defines `load_config` /
`save_config` / `validate_config` once. A later duplicate block used to
shadow the first copy (same class of bug as REQ-893). `config_manager`
CLI helpers read and write through the shared JSON helpers.
`settings_manager.load_config` and `provider_rate_limit.load_config`
call that package reader.

**Sibling XDG JSON (not `swarm_config.json`, same config dir family):**

| File | Role | Writers |
|---|---|---|
| `agent_settings.json` | Per-agent `new_chat_per_task` / session ids (REQ-65) | `src/swarm/core/agent_settings.py` (API + SPA editor) |
| `team_rosters.json` | REQ-28 composition (not `agent_team.members`) | `src/swarm/core/team_rosters.py` |
| `agent_relationships.json` | REQ-153 peer-mailbox edges (team↔agent / team↔team) | `src/swarm/core/agent_relationships.py` |
| `agent_mailbox_acl.json` | REQ-162 peer-mailbox whitelist / blacklist (per-agent or per-role) | `src/swarm/core/agent_mailbox_acl.py` |
| `teams.json` | `/v1/teams/` LLM-profile **aliases** (not remotes) | `src/swarm/views/utils.py` |
| `router_designs.json` | Designer drafts | `src/swarm/core/router_designs.py` |

These are operator topology / session policy, not Django prefs. They must
share the **same volume** as `swarm_config.json` in Docker.

**Verdict:** WebUI **does** write the same `swarm_config.json` `swarm-cli`
writes, through the remotes / LLM persist helpers — **not** through
`config_manager.save_config` (that module is the older CLI prompt helper).
Django Settings HTML is an inspector, not a writer.

---

### 2.3 Django DB (runtime + catalog; not harness topology)

| Concern | Models / files | WebUI | CLI |
|---|---|---|---|
| Chat transcripts (mirror) | `ChatConversation`, `ChatMessage` (`src/swarm/models/__init__.py`); websocket `src/swarm/consumers.py`; `src/swarm/views/chat_persist_views.py` `_sync_django_and_memory` | Read/write | n/a |
| Chat transcripts (restore SoT) | JSON under `SWARM_CHAT_DIR` / platformdirs data dir — `src/swarm/core/chat_store.py` | Read/write | Settings retention uses this dir |
| Compact summaries | `ConversationSummary` — `src/swarm/core/chat_compact.py` | API | n/a |
| Attachment **bytes** | Files under `SWARM_ATTACHMENTS_DIR` — `src/swarm/core/chat_attachments.py` | Write | n/a |
| Attachment **metadata** | `ChatAttachment` (`src/swarm/migrations/0012_chatattachment.py`) | Write | n/a |
| Herdr members | `HerdrAgent` — `CONFIGURATION.md` §10; `/v1/herdr-agents/` | CRUD | `herdr` CLI wrapper |
| Marketplace catalog | `Blueprint`, `MCPConfig`, `MarketplaceIndex` (`src/swarm/models/core_models.py`) | Marketplace views | n/a |

`MCPConfig` is a **marketplace template** (`config_template`, no secrets).
It is **not** live `mcpServers` in `swarm_config.json`. Do not treat it as a
second MCP SoT.

**DB location:** `src/swarm/settings.py` via `swarm.core.database_config` —
`DATABASE_URL` (or `POSTGRES_HOST` + `POSTGRES_*`) → Postgres; else
`DJANGO_DB_NAME` / `SQLITE_DB_PATH`. Compose happy path is the local
`postgres` service (`postgres://swarm:swarm@postgres:5432/swarm`). Native
pytest / desktop without those env vars still use SQLite (`/tmp/db.sqlite3`
unless a path is set). Neon is test-only — see [DATABASE.md](../DATABASE.md)
and #508. This ADR does not move topology into SQL.

**Per-user UI prefs today:** **not** Django. SPA uses `localStorage`
(`webui/frontend/src/lib/pinnedAgents.ts`, `hiddenAgents.ts`, `theme.ts`,
`settingsPrefs.ts`, `railOrder.ts`, …). #540 is the implement Issue to move
favourites / hidden (and later theme) to a per-user Django preferences API.

**Verdict:** Django already owns auth, Herdr rows, marketplace indexes,
attachment metadata, and a chat **mirror**. It does **not** own remotes, LLM
profiles, MCP servers, or `cli_agents`.

---

## 3. Answers to the Issue questions

### 3.1 After boot, is XDG live SoT or bootstrap?

**Both, by caller — that is the dual-SoT bug.**

| Caller | After `ready()` | Evidence |
|---|---|---|
| `AppConfig.config` / new `BlueprintBase` | **Bootstrap snapshot** (env-substituted at boot) | `apps.py` `_load_swarm_config()` once; `blueprint_base.py` prefers that dict |
| `/v1/remotes/`, `/v1/llm-profiles/`, `load_remote()` | **Live file** (re-read + env overlay) | `load_raw_config()` / `persist_*` |
| `persist_remote_overlay()` only | Writes file **and** patches `AppConfig.config` | `remote_teams.py` — exception, not the remotes/LLM path |

A Settings save of default LLM or a remote **does not** refresh
`AppConfig.config`. Blueprints started after that save can still see boot
values until process restart. Remotes already apply **env over file** on every
read, so a host env URL can disagree with the JSON operators just edited.

**Decision (implement later):** treat the **file** as live SoT for topology.
After every persist, refresh `AppConfig.config` from the same path (or drop
the cache and always re-read). Do not invent a second DB copy.

### 3.2 Does WebUI write the same file `swarm-cli` writes?

**Yes, for remotes + LLM settings + agent-team membership** — same
`resolve_config_path()` / `find_config_file()` / XDG fallback.

**No, for Django `/settings/`** — inspector only.

**Not in default Docker** — XDG mount is `:ro`, so the shared writer hits a
read-only filesystem.

**Not for secrets** — neither surface writes `.env`.

---

## 4. Evaluate A / B / hybrid — pick **hybrid**

Matthew’s two models and the CoS strawman, scored against today’s code and
UI honesty.

| Model | Everyday SoT | Env role | Honesty risk | Recovery |
|---|---|---|---|---|
| **A** — env bootstraps; Settings override env | Persisted Settings/file after first save | Seed empty fields; then lose | High unless every override is badged — ops debug `.env` and the process ignores it | Weak: bad persist needs file/volume surgery |
| **B** — DB/Settings SoT; env force-override | Persisted DB or file | Recovery only | Low if force is explicit and read-only | Strong: tweak env, boot past a broken volume |
| **Hybrid (pick)** | Persisted SoT per §4 table (`swarm_config.json` for topology, Django for prefs/chats) | Secrets always; topology only as **bootstrap** or **explicit force** | Low: badges on every env twin | B’s flag (`SWARM_CONFIG_FORCE_ENV=1` / `SWARM_*_OVERRIDE`) |

**Why not pure A.** Settings already persist remotes and LLM maps to
`swarm_config.json` (`persist_remote`, `persist_llm_settings`). Pure A without
badges is today’s remotes bug in reverse: file written, env still silently
wins (`load_remote`: “env wins”). Pure A *with* badges is the hybrid’s
everyday path — A’s seed + override — but A alone has no recovery story when
the volume is garbage.

**Why not pure B.** Putting topology in Django as the everyday SoT fights
`swarm-cli` and hand-edited JSON ([CONFIGURATION.md](../../CONFIGURATION.md)).
B’s “env can force-override” is the right **recovery** lever, not the everyday
reader. Making env win every boot (current remotes) *is* B-everyday and
misleads operators who just saved Settings.

**Why hybrid.** Takes A’s persist-and-badge honesty and B’s explicit recovery
without a second store or a sync daemon. Secrets never become Settings
plaintext SoT (`${VAR}`, “set / not set” only).

**Precedence (document + enforce in implement Issues):**

1. **Explicit env force-override** — `SWARM_CONFIG_FORCE_ENV=1` (all
   non-secret topology) or per-key `SWARM_*_OVERRIDE` /
   `HERMES_BASE_URL` only when force is on.
2. **Persisted Settings / `swarm_config.json`** (and sibling XDG JSON below).
3. **Env bootstrap defaults** — used only when the persisted key is empty
   (first boot / missing file).
4. **Built-in defaults** (`create_default_config`, remote `default_spec`).

Today remotes skip step 3 and jump to “env always wins.” That is **B everyday**,
which misleads operators who edited Settings. Implement Issue: env wins for
**secrets** always; env wins for **non-secret topology** only when force-override
is set (or the field was never persisted).

### Ownership table (single winner per concern)

| Concern | SoT | Who writes | Who reads | Not a SoT |
|---|---|---|---|---|
| Secrets & deploy flags (`DJANGO_*`, `API_AUTH_TOKEN`, provider keys, `DATABASE_URL`) | **Process env / `.env` / XDG `.env`** | Ops, compose `env_file`, systemd | App (dotenv + `${VAR}`) | Settings plaintext, Django rows, JSON literals |
| Harness topology (`llm`, `settings.*` task map, `mcpServers`, `remotes`, `cli_agents`, `agent_team`, `moa`, `blueprints` defaults) | **`swarm_config.json`** at `SWARM_CONFIG_PATH` or XDG | `swarm-cli` **and** WebUI via the same persist helpers | CLI, APIs, boot snapshot (until refresh) | Django `MCPConfig`, `localStorage` |
| Operator sibling topology (`team_rosters.json`, `teams.json` aliases, `router_designs.json`) | **Same XDG config dir** (own files) | Existing APIs / CLI | WebUI / API | Django; do not merge into chat tables |
| Per-agent session policy (`new_chat_per_task`, CLI/remote session ids) | **`agent_settings.json` today** → **Django prefs in a follow-up** (same #540 registry or a sibling model) | SPA Agent editor / `/v1/agents/…` | Session policy | Do not copy into `swarm_config.json` |
| Per-user UI prefs (favourites, hidden, rail order, theme, hostname override) | **Django per-user prefs (#540)** | SPA after #540 | SPA | `localStorage` after one-time import; not XDG |
| Chats / session transcripts | **JSON chat store today** (documented SoT) → **Django conversation rows as destination SoT** | Chat / WS already dual-write | Restore prefers JSON, then Django | Bidirectional sync engine |
| Attachment bytes | **Files** (`SWARM_ATTACHMENTS_DIR`) | Upload API | Chat | DB BLOBs |
| Attachment metadata, compact summaries, Herdr members, marketplace catalog, auth users | **Django** | Existing views | Existing views | `swarm_config.json` |
| First boot | **Seed-once** | `swarm-cli config init` / empty-volume default | — | Ongoing import loop |

**Non-goals:** bidirectional XDG↔DB sync; silent dual-write of remotes into
SQL; Settings rewriting `.env`; Neon as a config store.

### Why not DB-only topology? (B taken too far)

Feasible but rejected: `swarm-cli` and hand-edited JSON are first-class
([CONFIGURATION.md](../../CONFIGURATION.md)). Remotes/LLM persist already
target the file. Moving topology into Django would create the sync hell this
Issue forbids unless CLI became a DB client. Keep JSON as topology SoT.
B’s recovery flag still applies **to that file**, not only to SQL.

---

## 5. Docker ephemeral: pick **RW config volume + existing data volume**

| Option | Verdict |
|---|---|
| **Volume for config (RW) + volume for DB/files** | **Pick.** Topology and sibling XDG JSON survive `compose down`. Chats/DB already use `~/.local/share/swarm`. |
| DB-only topology | Reject. See §4. |
| Seed-once from image / cwd JSON, no volume | Reject as the **only** strategy. Optional **empty-volume init** (`config init` if file missing) is allowed; not a recurring import. |

**Amend compose (implement Issue, not this PR):** change

`"${HOME}/.config/swarm:${HOME}/.config/swarm:ro"`

to **read-write** (or a dedicated `SWARM_CONFIG_PATH` file mount that is RW).
Keep secrets in `env_file` / orchestrator env, not in the JSON volume as
plaintext. Document: without the config volume, Settings remotes/LLM edits die
with the container; without the data volume, SQLite + chat JSON die.

`docker-compose.dev.yml` only adds a source bind-mount; it inherits the `:ro`
config mount from the base file.

Stale docs: `DEVELOPMENT.md` still describes mounting `./swarm_config.json` —
compose no longer does that ([docs/debt/qa-wave3-structure-root.md](../debt/qa-wave3-structure-root.md)).

---

## 6. UI honesty — Settings copy (implement with ownership)

Every Settings field that has an env twin shows **exactly one** badge.
Copy is for the SPA sheet (`webui/frontend/src/components/SettingsSheet.tsx`
— Remotes / LLM profiles) and, later, the same strings on Django `/settings/`
if that page grows writes. DaisyUI: `badge badge-ghost` / `badge-warning` /
`badge-error`. No secret values in the badge — **names only**.

| Badge (visible text) | When | Control |
|---|---|---|
| `Forced by env FOO (read-only)` | `SWARM_CONFIG_FORCE_ENV=1` or `SWARM_*_OVERRIDE` / forced remote env | Input disabled; Save no-ops that field |
| `From env FOO (not overridden)` | Persisted key empty; effective value is bootstrap env | Editable; first save becomes “Overrides…” |
| `Overrides env FOO` | Persisted value ≠ bootstrap env; file wins | Editable; helper: “`.env` still has FOO; this instance uses Settings.” |
| `From config` | File value, no env twin | Editable |
| `Built-in default` | Neither file nor env | Editable |

Secrets (API keys, tokens): never a plaintext SoT. Show
`Uses ${OPENAI_API_KEY} — set` / `not set`. No override badge that implies
the UI stored the secret.

### Example — Settings → Remotes → Hermes

```
Remotes
  Hermes
  Base URL
    [ https://hermes.lab.example ]     [ Overrides env HERMES_BASE_URL ]
    .env still has HERMES_BASE_URL; this instance uses the URL saved here.
    Clear to Settings to fall back to env bootstrap.

  API key
    [ Uses ${HERMES_API_KEY} — set ]   [ Secret · env-only ]
    Not editable as plaintext. Rotate the env var, then reload.
```

Same pane, recovery boot (`SWARM_CONFIG_FORCE_ENV=1` or
`SWARM_HERMES_BASE_URL_OVERRIDE=1`):

```
  Base URL
    [ https://hermes-rescue.example ]  [ Forced by env HERMES_BASE_URL (read-only) ]
    Persist is ignored until you unset SWARM_CONFIG_FORCE_ENV.
    Saved Settings URL is kept on disk for when force is off.
```

First boot, file empty, compose injected `HERMES_BASE_URL`:

```
  Base URL
    [ https://hermes.lab.example ]     [ From env HERMES_BASE_URL (not overridden) ]
    Save keeps this URL in swarm_config.json (then badge → Overrides…).
    Leave unsaved to keep env as the only source.
```

### Example — Settings → LLM profiles

```
LLM profiles
  Default
    [ gpt-4o-mini ▼ ]                  [ Overrides env DEFAULT_LLM ]
    Chat uses this saved profile. Process env DEFAULT_LLM is ignored
    unless you force-override.

  Override per task                    [ From config ]
    Off: every job uses Default.
```

Force-env recovery:

```
  Default
    [ gpt-4o ▼ ]                       [ Forced by env DEFAULT_LLM (read-only) ]
```

No env twin (auto-pick only):

```
  Default
    [ gpt-4o-mini ▼ (auto) ]           [ Built-in default ]
    Auto-picked Default. Chat uses this until you save another id.
```

### Example — Settings → System (secrets inspector)

```
  OPENAI_API_KEY                       [ Secret · env-only ]
    set
  DJANGO_SECRET_KEY                    [ Secret · env-only ]
    set
  API_AUTH_TOKEN                       [ Secret · env-only ]
    set
```

Django `/settings/` (“Operator dump”) stays a **redacted inspector** until it
either grows the same persist helpers + these badges or keeps linking to SPA
Settings for writes (`SettingsSheet` already links “Operator dump”).

---

## 7. Follow-up implement Issues (parked)

Do not implement in this PR. Suggested filings (titles only):

1. **Refresh `AppConfig.config` after persist (live SoT)** — after
   `persist_remote` / `persist_llm_settings` / `persist_agent_team` / CLI
   writes, reload the same path into `SwarmConfig.config` (or always
   re-read). Tests: PATCH LLM default → new blueprint sees it without
   restart.
2. **Compose: RW XDG config volume** — drop `:ro` (or document a RW
   override). Tests: persist remote inside the container; file visible on
   the host.
3. **Unify XDG helpers** — one `config_root()` plus `SWARM_CONFIG_DIR`,
   Windows vs XDG resolution, and migrate-or-refuse for a legacy tree.
   **Done in #1434** (config root only; data/cache remain #1435). The
   shadowed second copy of `load_config` / `save_config` /
   `validate_config` in `config_loader.py` is removed, and JSON I/O is
   shared with `config_manager`.
4. **[#540](https://github.com/matthewhand/open-swarm/issues/540) Django prefs** —
   favourites / hidden (and later theme, rail order). Seed-once from
   `localStorage` if server empty; then server wins. No XDG copy.
5. **Env force-override + Settings badges** — implement §4 precedence and
   §6 copy. Remotes: stop silent everyday env-wins for non-secret URLs
   unless force flag.
6. **Chat SoT: Django destination** — JSON remains restore SoT today
   (`chat_store.py`). One-way migrate JSON → Django, then Django wins;
   keep files for attachment bytes. No JSON↔SQL loop. Coordinate with
   [#508](https://github.com/matthewhand/open-swarm/issues/508) (local
   Postgres default; Neon test-only).
7. **Fold `agent_settings.json` into the #540 prefs registry** (or a
   documented per-user/per-agent Django model). Until then it stays XDG
   sibling topology, on the same volume.
8. **Docs honesty** — `DEVELOPMENT.md` Docker mount; FEATURE_STATUS
   Settings “write” vs inspector; CONFIGURATION.md pointer to this ADR
   (this PR adds the pointer only).

---

## 8. Consequences

- Operators: secrets in env; topology in one JSON file (plus named sibling
  JSON); chats/prefs moving to Django on purpose, not by drift.
- Ephemeral Docker: mount **config RW + data RW**, or accept loss.
- Implementers: no sync service; refresh the boot cache; badges before
  clever merge.
- This ADR began as documentation only (`Fixes` #541 when merged).
  #776 implements the hybrid write paths and badges (see §9).

---

## 9. Addendum — #776 Full coverage (implemented)

**Decision for #776:** **Full** coverage of non-secret product settings via
Settings. Secrets and deploy flags stay **env-only** (the ADR-002 hybrid,
not a second SoT).

| Partition | Keys | Who writes | Who reads |
|---|---|---|---|
| **WebUI / `swarm_config.json`** | `llm`, `settings.*`, `mcpServers`, `remotes`, `cli_agents`, `agent_team`, plus advanced `cli_fusion` / `cli_map` / `cli_orchestrator` / `moa` / `slashCommands` / `blueprints` / `memory` | Settings + `swarm-cli` via the same persist helpers | CLI, APIs, boot cache (refreshed after persist) |
| **Env-only** | Provider keys, `API_AUTH_TOKEN`, `DJANGO_*`, `HOST`/`PORT`, `DATABASE_URL` | Ops / `.env` | App (`${VAR}`, dotenv) |

Machine-readable inventory: `GET /v1/config-ownership/` and
`swarm.core.config_ownership.inventory()`. Writes:
`PATCH /v1/config/sections/<section>/` (plus existing remotes / LLM
endpoints). Out-of-partition keys and plaintext secrets are **refused**.

**Precedence (enforced):** `SWARM_CONFIG_FORCE_ENV=1` or
`SWARM_<ENV>_OVERRIDE=1` > persisted file > env bootstrap (empty
persisted key) > built-in defaults. Secrets always resolve from env.

**UI honesty:** Settings → LLM profiles and Remotes show ADR-002 §6
badges. System lists advanced sections (write API exists; no dedicated
pane) and env-only secrets (set/not-set inspector only).

**Example file:** [`swarm_config.example.json`](../../swarm_config.example.json)
at repo root. Sibling [#775](https://github.com/matthewhand/open-swarm/issues/775)
may move it; keep the `*.example` name and do not commit live
`swarm_config.json` secrets.

**Not in this addendum:** compose `:ro` → RW (ADR follow-up 2); Django
prefs beyond #540. XDG config-root unify is #1434.
