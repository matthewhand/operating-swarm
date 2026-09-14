# Open Swarm Roadmap

Open Swarm is an agent framework — a derivative of OpenAI's experimental
[Swarm](https://github.com/openai/swarm) concept, since migrated to the
[openai-agents SDK](https://github.com/openai/openai-agents-python) — providing
blueprints (reusable multi-agent workflows), a Django REST API
(OpenAI-compatible `/v1/chat/completions`), CLI launchers, MCP integration, and
a web UI.

This roadmap is the single source of truth for project status. It supersedes
the older phase-based `TODO.md`. Per-feature evidence lives in the live
[FEATURE_STATUS.md](./FEATURE_STATUS.md) board (re-verify a row before acting
if it looks wrong; the 2026-06-10 audit is in
[docs/archive/FEATURE_STATUS_2026-06-10.md](./docs/archive/FEATURE_STATUS_2026-06-10.md)).

- [x] **v1 product cut (vocabulary / surface honesty)** — narrow terms to match
  shipped code: [docs/GLOSSARY.md](./docs/GLOSSARY.md) (Blueprint vs `/v1/teams`
  LLM-profile alias, Persona/MoA, CLI Fusion, Session, Operator UI vs SPA Chat)
  + [docs/ADR-001-primary-ui.md](./docs/ADR-001-primary-ui.md) (Django operator
  chrome; SPA keeps `/` + `/chat` only — do not remount Builder).

## Status legend

| Mark | Meaning |
|------|---------|
| `[x]` | Done and shipped |
| `[ ]` | Not done / planned — partially-done parents stay unchecked, with checked sub-items showing progress |

Last updated: 2026-06-19 (v0.5.1 on PyPI; CLI Agent Fusion + async + persona councils + recursion shipped).

---

## 0. Current release — v0.5.1 (on PyPI)

The first tagged FOSS releases shipped: **v0.3.0 → v0.4.x → v0.5.0 → v0.5.1** are
live on PyPI (`pip install open-swarm`). Highlights since the 2026-06-11 snapshot:

- [x] **CLI Agent Fusion line** shipped & tagged (was §3.5b/§3.6 "publish pending"):
  `cli_agent`, `cli_fusion`, `cli_orchestrator`, `cli_map`, plus MAF-class
  `cli_pipeline`/`cli_roundtable`/`cli_planner`, and recursive `cli_recurse`.
- [x] **Canonical `swarm_*` names** for the orchestration patterns (`swarm_ensemble`,
  `swarm_recurse`, …); `cli_*` kept as aliases. `cli_fusion`→`cli_ensemble`.
- [x] **Async tasking** — `/v1/responses` + `/v1/chat/completions` `background:true`
  (queued→poll→cancel, restart-durable), `system_fingerprint` provenance.
- [x] **Persona councils** (`persona_council`) — diverse-lens consensus.
- [x] **Community-blueprint discovery foundation** — external roots + `SWARM_BLUEPRINT_PATHS`.
- [x] **Docker** — API-only base compose + opt-in CLI mapping override.
- [x] **First tagged release + PyPI publish** (was §3.6 open).
- [x] **Memory configuration documented** in CONFIGURATION.md §9 (mem0 default) (was §3.2 open).

Still open (see below + new items): MCP-server dependency,
letta/langmem backends, deeper blueprint ecosystem curation (coverage/metadata),
and **CLI command-registration cruft** (many `swarm-cli` aliases declared but
"not found or not callable" — only `list`/`wizard`/`install` work cleanly).

---

## 1. Done / Shipped

- [x] Core blueprint system (`src/swarm/core/`, `BlueprintBase`, discovery, config)
- [x] Django REST API with OpenAI-compatible endpoints (`/v1/models`, `/v1/chat/completions`)
- [x] Django templates/HTMx web UI — **this is the live, supported production UI**
  - ⚠️ Correction (2026-06-11): the websocket chat *consumer* exists but is **unroutable** — `settings.py` references `swarm.asgi.application` which does not exist, and `channels` is not in `INSTALLED_APPS`. See §2 ASGI item.
- [x] CLI entry points all working: `swarm-cli`, `swarm-api`, `codey`, `suggestion`
- [x] Test suite green: 857 passed / 2 skipped / 0 failed
- [x] Security hardening sprint (June 2026): command/SQL injection, open redirect, hardcoded passwords
- [x] **FOSS cleanup wave (2026-06-10):**
  - [x] `node_modules` (8,356 files / 69 MB) and `.letta/` untracked from git
  - [x] Packaging repaired: `uv sync`/`uv lock` work; phantom `langmem`/`papr` pins removed; `mem0` → `mem0ai`; entry-point typo; real URLs
  - [x] README rewritten as honest FOSS-product doc (only verified features documented)
  - [x] Dead code removed: 8 orphaned blueprints + `repl/`, `agent/`, `llm/`, `cli/`, duplicate builders
  - [x] Consolidation: 5 spinners → 1, 2 config loaders → 1, ANSI boxes → 1; deprecation shims fully sunset (§2.1)
  - [x] Production-safe defaults: `SECRET_KEY` required outside debug, `DEBUG` off by default, `ALLOWED_HOSTS` required in prod
  - [x] Auth bypass elimination: `testuser`/`testpass` auto-login removed (now `ALLOW_TESTUSER_AUTOLOGIN` + debug only, random password); API auth required to boot in production; `runserver` auth-on by default; CSRF restored on mutating endpoints; `.env.example` fully documented
  - [x] Security branches merged: open-redirect validation, `secure_subprocess` wrapper, CSRF agent/team creator
  - [x] Frontend repaired: lockfile in sync (`npm ci` works), type-check green (36 TS errors fixed), build green
  - [x] React SPA wired to real APIs: BlueprintsPage on `/v1/blueprints/`, dashboard on live counts, zero mock data remains
  - [x] Memory wired into the agent loop (opt-in `MemoryBackend` protocol, mem0 backend, graceful degradation, 11 tests)
  - [x] Bug fixes found en route: Django-4 `re_path` import (broke 59 tests when frontend built), SPA fallback `TypeError` on every non-root route, Pagination duplicate key / undefined `totalPages`
  - [x] Docs: ROADMAP.md, FEATURE_STATUS.md (58 evidence rows), USER_JOURNEY.md (7 Playwright screenshots + regeneration script), CHANGELOG entry
  - [x] Tests: 616 → 713 (archive salvage ports, auth-hardening guards, shim identity locks, memory integration)

---

## 2. Nearly Done — finish-first list

- [ ] **Remote branch hygiene (needs repo-owner action on GitHub)**
  - [x] Triage all 84 unmerged branches (44 superseded/duplicate → delete; ~28 still merge-worthy; 12 stale-diverged)
  - [x] Merge top 3 security branches
  - [x] Delete superseded/duplicate branches on origin (all done — origin now has only main)
  - [x] Merge the remaining merge-worthy branches — 16 merged (test-coverage set + GitHubClient/models-package refactor); session-poisoning sys.modules mocks in three of them rewritten
  - [x] Review `refactor-wip` (368 commits): verdict — nothing worth salvaging (2 nice-to-haves documented in the review: GitHub CLI discovery, compile_blueprint command); safe to archive/delete on origin
  - [x] Push the local cleanup-wave commits to origin (squashed; granular log in docs/archive/)
- [x] **Login routing** (found while capturing USER_JOURNEY screenshots)
  - [x] `custom_login` view exists (`src/swarm/views/web_views.py`) but has **no URL pattern** — `/accounts/login/` 404s; routed `accounts/login/` (name `login`, Django default) and `login/` (name `custom_login`, matches `settings.LOGIN_URL`); locked by `tests/views/test_login_routing.py`
  - [x] `/webui/` route 500s (`TemplateDoesNotExist: webui/index.html`) — `WebUIView` now redirects to `/` (kept for backward compat; the old `webui/index.html` template no longer exists)
- [x] **Finish archive salvage**: async API tests ported (`tests/api/`, 22 tests)
- [x] **Blueprint test collection**: in-tree `test_basic.py` files moved to `tests/blueprints/` and fixed (flock, chucks_angels, digitalbutlers — now collected and green)
- [x] **Naming/metadata debt**
  - [x] stewie module renamed `blueprint_family_ties.py` → `blueprint_stewie.py` (rename also FIXED discovery — stewie was invisible to the blueprint scanner); `family_ties/` forwarder deleted
  - [x] `blueprint_audit_status.json` deleted (fake metadata, zero consumers)

- [x] **ASGI routing for websocket chat** — `swarm/asgi.py` + `routing.py` created; daphne/channels registered (they were declared core deps all along, never wired); 9 full-stack tests; live-verified 101 upgrade with session auth, 403 anonymous/bad-origin (`docs/websocket_chat.md`)

- [x] **Non-streaming `/v1/chat/completions` test-mode bug FIXED** — chunk normalizer consumes the whole generator and returns the final message (was: first spinner chunk). Per-blueprint API smoke matrix added (`tests/api/test_blueprint_api_smoke.py`): 13 blueprints verified answering on BOTH streaming and non-streaming surfaces (was: only zeus). Former xfail RESOLVED: `whiskeytango_foxtrot` now yields a canned `[TEST-MODE]` answer early in run() instead of hanging — all 14 blueprints pass the smoke matrix.

### 2.1 Deprecation shim sunset

Consolidation shims deleted. Canonical imports:
`swarm.core.spinner`, `swarm.core.config_loader`, `swarm.ux.ansi_box` /
`swarm.core.output_utils.ansi_box`, `swarm.core.swarm_api`. Locked gone by
`tests/unit/test_deprecation_shims.py`.

- [x] Migrate remaining internal callers off shim paths (`views/settings_manager.py` → core config_loader; also fixed a broken `extensions.blueprint.discovery` import in `core_views.py`)
- [x] Remove `swarm.extensions.blueprint` (`__init__` / `spinner` / `slash_commands`) — deleted; use `swarm.core.*`
- [x] Remove remaining shims (`extensions/config/config_loader`, `blueprints/common/spinner`, `ux/spinner`, `utils/ansi_box`, `extensions/launchers/swarm_api`)

---

## 3. Far From Done — documented as roadmap, not current state

### 3.1 React/DaisyUI SPA (`webui/frontend`)

Status: **ADR-001 accepted** — Django trailing-slash UI is canonical; SPA mounts
**only** `/` (dashboard) + `/chat`. Leftover Teams/Blueprints/Settings/Builder/
AgentCreator SPA pages were **deleted** (no quarantine remount bait). Do **not**
remount them; SPA↔Django parity is **rejected** as a v1 goal.

- [x] SPA scope cut to Dashboard + Chat (ADR-001)
  - [x] Component library (13 DaisyUI/React components)
  - [x] Vite + TypeScript + Tailwind/DaisyUI build setup; lockfile in sync
  - [x] Dashboard on live blueprint/model/team counts; fabricated stats removed
  - [x] ChatPage (blueprint selector, WS via ASGI; session-cookie auth; 4401 when anonymous)
  - [x] Leftover SPA operator pages deleted; e2e/a11y/shots = `/` + `/chat` only
  - [x] Bare `/teams` `/blueprints` `/settings` `/agent-creator` redirect to Django
  - [x] **JSON Teams API** — `/v1/teams/` LLM-profile aliases (see GLOSSARY) — Django UI owns CRUD chrome
  - [x] Resolved npm audit advisories: vite 5 → 8 (PR #84), 0 vulnerabilities
  - [ ] ChatPage polish (reconnect, markdown composer) — see §4.6
  - [x] **REQ-163 Phase 0** — virtualized chat ADR ([ADR-004](./docs/adr/004-virtualized-chat-history.md)): pick `@tanstack/react-virtual` ≥ 3.14; fallback MIT Virtuoso; Query stays the data layer
  - [ ] **REQ-163 Phase 1** — virtualize ChatPage `displayItems` (no API pagination)
  - [ ] **REQ-163 Phase 2** — cursor-paginate `GET /chat/thread/` + `useInfiniteQuery` load-older
  - [x] **REQ-194 Phase 0** — 3D robot avatar ADRs ([ADR-008](./docs/adr/008-3d-robot-avatar-theme.md), [Reachy report](./docs/reports/reachy-3d-avatar-inspiration.md)): MiniPose playback, lazy header WebGL, one Rail key; disabled picker stub
  - [ ] **REQ-194 Phase 1** — `robot3d` + one licensed mesh (idle/working); chat never blocked
  - [ ] **REQ-194 Phase 2** — ≥2 body × ≥2 head on one MiniPose rig
  - [ ] **REQ-194 Phase 3** — map chat/WS status to idle/listen/working/error
  - [ ] ~~Replace Django template pages page-by-page~~ — **superseded by ADR-001**

### 3.2 Memory integration (mem0 / letta / langmem)

- [ ] Memory production-ready
  - [x] Backends scaffolded as optional extras (`mem0ai` resolves and installs)
  - [x] Wired into the agent loop: opt-in per-blueprint `memory` config block; retrieval injected pre-run, conversation stored post-run; no-op when unconfigured
  - [x] End-to-end validation against a real mem0 instance: opt-in `tests/integration/test_memory_mem0_e2e.py` (skips unless `RUN_MEM0_E2E=1` + `OPENAI_API_KEY`; local qdrant + sqlite under tmp_path). 2026-06-11 real run: mem0ai 2.0.4 initialized and the store cycle reached OpenAI embeddings, but the repo `.env` key is revoked (401) — full green pass pending a valid key
  - [ ] letta/langmem backends (placeholder modules raising clear errors today)
  - [x] Decide on a default backend and document configuration in CONFIGURATION.md — **DONE** (mem0 default, CONFIGURATION.md §9)

### 3.3 MCP server mode (`ENABLE_MCP_SERVER`)

- [ ] Functional MCP server hosting blueprints as tools
  - [x] URL routing behind the flag
  - [x] `provider.py` executes blueprints with passing tests (stale TODO docstring corrected)
  - [ ] Declare the `django-mcp-server` dependency (imports as `mcp_server`; not in `pyproject.toml` — the mount is dead on a clean install; see `docs/mcp_server_mode.md`)
  - [ ] Auth story for MCP clients (token-based)

### 3.4 Marketplace/Wagtail (`ENABLE_WAGTAIL`) and SAML IdP (`ENABLE_SAML_IDP`) — REMOVED

- [x] **DECISION MADE (2026-06-11): drop both — executed 2026-06-11.** Removed `swarm/marketplace/` (Wagtail app), Wagtail/SAML blocks in settings.py + urls.py, wagtail/taggit/modelcluster pins from pyproject, the Wagtail-backed `MarketplaceBlueprintsView`/`MarketplaceMCPConfigsView` + routes, SAML env getters and `tests/unit/test_settings_saml.py`, and the wagtail/saml docs
  - [x] GitHub-topics discovery kept: service moved to `swarm/services/github_topics_service.py`; `Marketplace*GitHub*` endpoints and `ENABLE_GITHUB_MARKETPLACE` flag unchanged (`docs/github_marketplace.md`)
  - [x] Stewie blueprint reviewed: no Wagtail coupling; works as a normal blueprint (`blueprint_stewie.py`; nested Django leftovers later deleted)

### 3.5 Blueprint ecosystem rationalization (17 remaining blueprints)

- [x] Delete the 8 orphaned blueprints (done 2026-06-10)
- [ ] Curate a flagship set — candidates: `codey`, `geese`, `jeeves`, `zeus`, `suggestion`, `rue_code`, `poets`, `stewie`
- [ ] Test coverage for retained blueprints (most still lack collected tests; see §2 blueprint-test-collection item)
- [ ] Demote or archive non-flagship blueprints to an examples/contrib area
- [ ] Restore or formally drop legacy CLI commands old docs reference (`wizard`, `config`, `add`)

### 3.4b CLI command-registration cruft (NEW — found 2026-06-19)

`swarm-cli` discovery emits a wall of `Warning: Execute function for alias 'X'
not found or not callable. Skipping.` on every invocation (config, add, delete,
edit-config, validate-env, validate-envvars, …). Only `list`, `wizard`, and
`install` resolve cleanly; `swarm-cli config` errors `invalid choice`.

- [x] Prune the dead alias registrations — deleted orphan argparse trees
  (`extensions/cli`, `core/cli`) that emitted those warnings; shipped entry is
  Typer `swarm.core.swarm_cli:app` (no alias warnings)
- [x] Silence the per-invocation warnings for unregistered aliases (tree gone)
- [x] Reconcile docs to the commands that actually work (USERGUIDE / QUICKSTART
  already match Typer; DEVELOPMENT.md entry-point note updated)

### 3.5b CLI Agent Fusion (v0.4.0 feature line)

Turns the agentic CLIs an operator already has installed (`claude`, `gemini`,
`codex`, `opencode`, …) into one-shot, OpenAI-API-addressable subagents, composed
four ways: single (`cli_agent`), consensus panel (`cli_fusion`), granular
consensus (`cli_orchestrator`), and decompose-and-distribute (`cli_map`). Full
design in [docs/CLI_FUSION.md](./docs/CLI_FUSION.md). Built as a PR series in the
commit log; version bumped to 0.4.0.

- [x] CLI Agent Fusion built for v0.4.0 (code complete; tag + PyPI publish pending)
  - [x] Foundation: `CliAdapter` one-shot layer + `cli_agent`/`cli_fusion` blueprints
  - [x] Install + auth autodiscovery: `swarm-cli cli-agents` (`--check-auth`/`--smoke`/`--suggest`/`--json`)
  - [x] Full-capability panelists (auto-approve) + per-panelist workdir isolation (git worktree / temp dir)
  - [x] Built-in adapter catalog with per-CLI gotchas baked in (gemini `--skip-trust`, opencode `--model`)
  - [x] Incremental streaming (`cli_agent`) + failover/graceful degradation
  - [x] Reusable `swarm.core.consensus` service (consensus-first synthesis) + `swarm.core.cli_tools` agent-tool layer (`as_tool()`)
  - [x] `cli_orchestrator` (granular consensus) + `cli_map` (decompose → distribute → reduce) blueprints
  - [x] End-to-end API coverage; verified live over claude+gemini+opencode
  - [ ] Tag `v0.4.0` + PyPI publish (manual release step — owner action)

### 3.6 Release engineering

- [x] First tagged FOSS release on PyPI — **DONE**: v0.3.0 → v0.5.1 all published
  - [x] Fix publish workflow: old workflows deleted (one published to REAL PyPI on every main push with timestamp versions!); new `publish.yml` is release/tag-driven with manual dispatch, version from pyproject
  - [x] CI tests Python 3.10/3.11/3.12 via uv, with `uv lock --check` guarding against phantom pins
  - [x] CONTRIBUTING.md added (honest: references only scripts that exist; lint scoped to touched files)
  - [x] License headers / NOTICE decision: **NOTICE file instead of per-file headers** (decided 2026-06-11). `NOTICE` covers the MIT grant, OpenAI Swarm/openai-agents attribution, and vendored static assets (marked.js, Tabler Icons, Font Awesome webfonts); linked from README's License section
  - [x] Cut the actual first release (tag, release notes from CHANGELOG) — through v0.5.1
- [ ] **Windows desktop package (REQ-151)** — Phase 0 ADR accepted when
  [docs/adr/003-desktop-packaging.md](./docs/adr/003-desktop-packaging.md)
  merges: OpenMausBot-style **local loopback server + owned window**,
  implemented as **pywebview + PyInstaller onedir** (not Electron).
  Phase 1 portable zip and Phase 2 NSIS/signing are split Issues — no
  installer in the ADR PR. TUI (#481 / ADR-012) is a separate API client —
  Wave 0 scaffold is `swarm-cli tui --once`; Waves 1–N are child Issues.

### 3.7 Sandboxed Tool Execution & Isolation (LangChain / Host / Container)

Provides tool-level sandboxed execution (Python REPL, Bash subprocesses, workspace file I/O) complementing the core `openai-agents` loop ([docs/architecture/LANGCHAIN_SANDBOX_HARNESS.md](./docs/architecture/LANGCHAIN_SANDBOX_HARNESS.md)).

- [x] **MVP Bare-Metal Host Harness (`src/swarm/core/sandbox/`)**
  - [x] `SandboxBackend` protocol with `LocalSubprocessSandbox`, `LangChainSandboxHarness`, `MockSandbox`, and `SandboxManager`.
  - [x] Bare-metal host execution within designated workspace directories with automatic environment sanitization (scrubs API keys, secrets, DB credentials).
  - [x] Direct bridge to OpenAI Agents via `SandboxManager.as_function_tools()`.
  - [x] Unit test suite covering backends, env scrubbing, timeout handling, and fallback behavior (`tests/core/test_langchain_sandbox.py`).
- [ ] **Phase 2: Containerized & MicroVM Sandboxes (Roadmap)**
  - [ ] `DockerSandbox`: Ephemeral container per session (`docker run --rm -v ...`) with CPU/memory limits and optional network egress restriction (`--network none`).
  - [ ] `E2BSandbox`: Integration with E2B cloud sandboxes (Firecracker microVMs) for multi-tenant and cloud deployments.
  - [ ] LangChain Docker/Container tool harmonization via `LangChainSandboxHarness`.


---

## 4. Critique findings — multi-agent audit (2026-06-19)

A read-only fan-out audited the web UI, end-to-end workflows, code/repo
structure, and cruft. Findings below are prioritized; each cites `file:line`.
Bright spots confirmed: the `/v1/responses` async engine, the `swarm-cli
cli-agents --init/--check-auth/--suggest` flow, the OpenAPI-served REST surface,
USERGUIDE.md accuracy, and the `cli_*` family's test coverage.

### 4.1 Security (do first)
- [x] **XSS / secret leak:** settings dashboard now uses `json_script` +
  `redact_settings_groups` (`settings_dashboard.html`, `settings_views.py`).
- [x] **Unauthed web save + unsandboxed exec:** creator saves are
  `@login_required`; AST sandbox + banned-snippet gate
  (`blueprint_sandbox.py`, `agent_creator_views.py`); user discovery opt-in
  via `SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY` (default off).

### 4.2 Broken-but-shipped (erodes trust)
- [x] **`django_chat` LLM stub** — `run()` now calls the configured OpenAI-compatible
  profile (no more “Would respond to…” box). Still Django-context heavy.
- [x] **Web create→run save path** — `save_custom_agent` / `save_team_swarm` /
  library `blueprint_creator` write under `get_user_blueprints_dir()` (plus JSON
  catalog for My Blueprints). Discovery remains opt-in
  (`SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY`).
- [x] **Agent Creator Pro clickware** — `/agent-creator-pro/` soft-redirects to
  `/agent-creator/` (nav link removed); view/template/JS/CSS deleted.
- [x] **My Blueprints runner wired:** posts `/v1/chat/completions` with blueprint
  id + CTAs to `/chat?blueprint=` and `/teams/launch/` (replaces Simulate-run
  demo). Settings Validate + env Export labeled “(not available)”; path-check
  buttons removed; Team Creator Validate still marked demo.
- [x] **SPA `loading` button spinner (DaisyUI 5)** — `Button.tsx` renders
  `loading loading-spinner` + `aria-busy`; covered by `Button.test.tsx` /
  `A11y.test.tsx`. Dead `active`/`disabled` variant aliases remain low priority.

### 4.3 Docs-vs-reality (breaks onboarding)
- [x] **Docs + CLI `config` group** — QUICKSTART/CONFIGURATION use real
  `swarm-cli config list|add|remove|init`. Orphaned `extensions/launchers`
  `.env` helper usage text now points at shipped `--section/--json` form.
- [x] **`install` wording** — QUICKSTART §2 now says PyInstaller compile (not
  “downloads”).
- [x] **swarm-cli dead-alias warnings** — see 4.4 (orphaned `extensions/cli` deleted).

### 4.4 Dead code / parallel trees
- [x] **`extensions/` vs `core/` parallel CLI trees** — deleted orphan argparse
  `extensions/cli` + unused `core/cli`; deleted non-shipped
  `extensions.launchers.swarm_cli` / `swarm_wrapper` / `swarm_api`; `swarm-cli`
  and `swarm-api` both point at `swarm.core.*` in pyproject.
  Live helpers relocated: `prompt_user` → `core.config_manager`,
  `AsyncInputHandler` → `core.async_input`.
- [x] **`extensions/cli/main.py` orphaned** — deleted with the argparse tree
  (supersedes §3.4b).
- [x] **Dead view+template:** `blueprint_webpage` + `simple_blueprint_page.html`
  (+ `chat.html`) removed 0.5.2 — see FEATURE_STATUS / CHANGELOG.
- [x] **Orphaned `templates/rest_mode/*`** — deleted unrouted `slackbot.html` /
  `message_ui.html` + components (static `rest_mode/js` kept for XSS regression
  coverage). `chat.html` already removed.
- [x] **`stewie` ships a broken nested Django app** — deleted dead `settings`/`views`/`serializers`/`models`/`urls`/`apps` (nonexistent `blueprints.chc`); kept `blueprint_stewie.py`

### 4.5 Structure
- [ ] **God-modules:** `blueprints/codey/blueprint_codey.py` (1021 lines),
  `core/blueprint_base.py` (919 lines, 35 methods — memory/approval/config all
  inlined). Extract `MemoryMixin`/`ApprovalMixin`/`ConfigResolver`; pull
  `CodeySpinner`/`DummyTool` into shared infra.
- [x] **`ansi_box` duplication** — `utils/ansi_box.py` is a DeprecationWarning
  shim re-exporting `ux/ansi_box` (callers moved to `ux` / `output_utils`).
- [ ] **Blueprint metadata inconsistent** — `name`≠dirname in 9 blueprints;
  3 declaration styles (`ClassVar`, bare, `@property`); absent in `gawd`/`geese`/
  `zeus`; no machine-readable `category`. Define a schema + discovery-time
  validator (CI-enforced). (`whinge_surf` husk removed.)
- [ ] **`urls.py` REST inconsistency** — hand-duplicated slash/no-slash route
  pairs, mixed CBV/FBV, 4 auth styles. Adopt a DRF router for `v1/*` resources.
- [ ] **9 `cli_*` deliberation blueprints overlap** — a strategy family as 9
  top-level blueprints. Consider one blueprint + `strategy` param, or a shared base.

### 4.6 UX / SPA (medium)
- [x] **Toast a11y** — DaisyUI `ToastItem` now `role="status"` + `aria-live`
  (assertive for error/warning). Orphan Builder panels / AuthContext deleted.
- [ ] **Modal triple focus/dismiss** — native `<dialog>` + `focus-trap-react` +
  manual backdrop math (`Modal.tsx:84-105`); pick one.
- [ ] **ChatPage gaps** — single-line composer remains; markdown bubbles +
  auto-reconnect/backoff (skip 4401) landed.
- [x] **BuilderPage / AgentCreatorPage / Teams / Blueprints / Settings SPA** —
  deleted (ADR-001); `App.tsx` mounts `/` + `/chat` only. Orphan Builder panel
  components + unused AuthContext deleted too; canonical creator is Django
  `/agent-creator/`.
- [x] **Django operator UI offline + CSP** — Bootstrap 5.3.3, Prism, Font Awesome
  vendored under `src/swarm/static/contrib/`; `base.html` + rest_mode marked use
  `{% static %}` / relative imports (no CDN). Prod (`DEBUG=False`) sets a minimal
  CSP (`ContentSecurityPolicyMiddleware`; `script-src 'self'`, `style-src 'self'`
  documented in AUTH.md §7 — template `style=""` extracted to `operator.css`).
  Remaining legacy polish: `profiles.html` DaisyUI-on-Bootstrap mismatch;
  richer `title`/`head` blocks — decide retire-vs-migrate.
- [ ] **Django legacy surface polish** — `profiles.html` DaisyUI classes on a
  Bootstrap base (unstyled); `base.html` head/title block gaps.

### 4.7 API + tests
- [x] **`/v1/responses` trailing-slash twins** — `…/responses/`, detail, and cancel
  now resolve (same pattern as `/v1/blueprints` / `/v1/teams`).
- [x] **Blueprint source/tools + cli-agents/config-options slash twins** —
  `/v1/blueprints/<id>/source/` + `/tools/` no longer 404; `/v1/cli-agents` and
  `/v1/config-options` accept no-slash too (`tests/api/test_blueprint_source.py`,
  `test_blueprint_tools.py`). Broader DRF-router cleanup still open in §4.5.
- [x] **Silent model fallback** — unknown `default_model` / named profile silently
  used `default` or `{}`. Now honors `blueprints[].default_model` /
  `settings.default_llm_profile`, warns on miss (Stewie + `get_llm_profile` +
  resolve path); `llm_profile` property stays fail-loud
  (`tests/core/test_fallback_to_default_model.py`, stewie / blueprint_base tests).
- [x] **`/v1/teams/` honesty** — documented as LLM-profile alias registry
  (`id`/`description`/`llm_profile`), not a multi-agent team builder (OpenAPI +
  module docstring + FEATURE_STATUS).
- [x] **Stewie coverage** — dedicated `tests/blueprints/test_stewie.py` + gap smoke;
  `whinge_surf` empty husk removed (was not discoverable).
