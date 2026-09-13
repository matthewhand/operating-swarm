# Wave 3 QA — Scope B: `src/swarm/` / `webui/` / Django / `skills/` layout

Look-only folder-structure inventory for **#452** (REQ-95). Scope **B** only:
app packages. No file moves, deletes, or product-code edits in this PR.
Refs #452 (no `Fixes`; implementer work waits on CoS).

**As-of:** `origin/main` @ `15bfd714` (Grok rail + Settings sheet + Agent
Router + Herdr + rosters). Prior overlap / chrome maps:

| Doc | What it already answered |
|-----|--------------------------|
| [django-spa-overlap.md](./django-spa-overlap.md) | REQ-22b noun collisions (frozen at `4d554ea5`; six-tab SPA) |
| [qa-wave1-django-spa.md](./qa-wave1-django-spa.md) | Leftover D-items vs today’s Grok chrome |
| [qa-wave2-webui-blueprints.md](./qa-wave2-webui-blueprints.md) | #419 `django_chat` / webui-as-blueprint |
| [webui.md](./webui.md) | REQ-22a SPA internals (not folder ownership) |
| [ADR-001](../ADR-001-primary-ui.md) | Django operator routes + SPA `/` + `/chat` (doc line is stale: `/` is Chat) |

**Method:** static tree of `src/swarm/`, `webui/` (not `node_modules`), both
`manage.py` files, `skills/`, Django `templates/` + `static/` under `src/`,
`urls.py` / `settings.py` / hatch layout, Herdr + SPA serve paths. No Neon.
No host bounce. No `:8001`. No secrets or live LAN URLs. Golden-journey not
run.

**How to read the inventory**

| Column | Meaning |
|--------|---------|
| **Load-bearing** | **Y** = urls / settings / CLI / hatch / tests / Docker would break if removed. **N** = unmounted, unreferenced, or tests-only leftover. **?** = live on one path, dead on another, or cwd/install dependent. |
| **Action** | Proposed **later** (not this PR): `keep` / `move` / `merge` / `delete` / `archive`. |

Scopes **A** (root sprawl), **C** (`docs/`), **D** (deploy/CI) are out of this
file. Tests under `tests/` are cited only when they pin a package’s location.

---

## Verdict

The installable Python product is **one Django app** (`src/swarm`) that also
hosts the CLI, blueprint recipes, Herdr wrapper, and operator HTML. The
day-to-day product chrome is **not** that HTML: it is `webui/frontend` (Grok
rail + Chat + Agent Router), served from a **cwd-relative**
`webui/frontend/dist` that hatch does **not** ship.

That split is load-bearing. A “clean package layout” that moves `webui/` under
`src/swarm/`, or folds SPA into Django templates, or deletes operator HTML
while Herdr / Teams / Settings still hop there, will break live hosts before
it helps.

`django_chat` is already unmounted as a webpage ([wave 2](./qa-wave2-webui-blueprints.md)).
Its leftover **package** still sits inside `blueprints/` and is still
discoverable. That is #419, not a folder move.

---

## 1. Inventory table

### 1.1 Package roots and entrypoints

| Path | Role | Load-bearing | Proposed action |
|------|------|--------------|-----------------|
| `src/swarm/` | Installable Python package (`hatch` wheel `packages = ["src/swarm"]`). Django app `swarm` + CLI/API kernel + recipes. | Y | keep |
| `src/swarm/__init__.py` | `default_app_config = 'swarm.apps.SwarmConfig'` | Y | keep |
| `src/swarm/settings.py` | Sole `DJANGO_SETTINGS_MODULE=swarm.settings`. `BASE_DIR` = `src/`. `INSTALLED_APPS`: daphne, Django, DRF, channels, `swarm`, `swarm.mcp` (+ optional `mcp_server`). | Y | keep |
| `src/swarm/urls.py` | `ROOT_URLCONF`. HTTP + SPA fallback. No blueprint `include()`. | Y | keep |
| `src/swarm/asgi.py` | HTTP + Channels WS (`swarm.asgi.application`). `swarm-api` → uvicorn this. | Y | keep |
| `src/swarm/wsgi.py` | WSGI twin. | Y | keep |
| `src/swarm/apps.py` | `SwarmConfig.ready()`: logging, XDG config, auth/test guards, resume `/v1/responses`. | Y | keep |
| `src/swarm/routing.py` | WS: `ws/ai-demo/<conversation_id>/` | Y | keep |
| `src/swarm/consumers.py` | `DjangoChatConsumer` (HTMX HTML frames for SPA Chat). | Y | keep |
| `src/swarm/auth.py` / `permissions.py` / `middleware.py` | Token + session + CSP. | Y | keep |
| `src/swarm/admin.py` | Registers `HerdrAgent` only. | Y | keep |
| `src/swarm/serializers.py` | DRF (messages, Herdr). | Y | keep |
| `src/swarm/tool_executor.py` / `types.py` / `util.py` | Agent/tool runtime helpers. | Y | keep |
| `manage.py` (repo root) | Canonical Django CLI. Dotenv from repo root. Docs + `docker-entrypoint.sh` use this. | Y | keep |
| `src/manage.py` | Duplicate; dotenv via `src/` → parent. Used by a few `cd src && python manage.py` scripts. | ? | merge into root `manage.py` later; do not delete until those scripts are updated (Scope D / scripts, not this wave) |
| `webui/` | Thin wrapper: `README.md` + `frontend/`. **No** Python backend. | Y | keep (do not invent `webui/backend/`) |
| `webui/frontend/` | React 18 + Vite + DaisyUI 5 SPA source. | Y | keep |
| `webui/frontend/dist/` | Built assets. Gitignored. Served by Django when cwd is repo root. | Y (runtime) | keep generate-on-build; do not commit |
| `skills/` | Anthropic-format Agent Skills (`SKILL.md`). Default `skills_root()` = `<repo>/skills`. | Y | keep at repo root |
| `src/swarm/manage.py` | Does **not** exist. Coverage omit still lists it. | N | delete the omit line on a tests/CI pass (Scope D) |

`TEMPLATES['DIRS']` points at `<repo>/templates`, which **does not exist**.
Operator HTML is `APP_DIRS` → `src/swarm/templates/`. Hatch wheel includes
`src/swarm/templates/**` and `src/swarm/static/**` and `src/swarm/blueprints/**`.
It does **not** include `webui/` or `skills/`.

### 1.2 `src/swarm/` first-level packages

| Path | Role | Load-bearing | Proposed action |
|------|------|--------------|-----------------|
| `src/swarm/core/` | Kernel: `swarm_cli`, `swarm_api`, discovery, config, skills loader, remotes, chat store, MoA. | Y | keep |
| `src/swarm/core/moa/` | MoA orchestrator / team / backends / CLI. | Y | keep (composition debt is [core.md](./core.md) / wave2 core, not a move) |
| `src/swarm/core/skills.py` | Discovers `<repo>/skills/**/SKILL.md`. | Y | keep; do not relocate without `paths.get_project_root_dir()` |
| `src/swarm/core/paths.py` | Project root = four parents above this file → repo root. | Y | keep |
| `src/swarm/blueprints/` | Discoverable `BlueprintBase` recipes (`blueprint_*.py`). Default `BLUEPRINT_DIRECTORY`. | Y | keep as CLI/API recipes |
| `src/swarm/blueprints/common/` | Shared helpers (not a recipe). | Y | keep |
| `src/swarm/views/` | HTTP pages + `/v1/*` APIs wired by `urls.py`. | Y | keep |
| `src/swarm/templates/` | Django operator HTML (library, teams, settings, sessions, login, Agent Router fallback). | Y | keep until chrome retirement; see §2 |
| `src/swarm/static/` | Operator CSS/JS + vendored Bootstrap/HTMX + `rest_mode/` fossil. | Y | keep live JS; delete/archive fossils later |
| `src/swarm/models/` | ORM: chat, marketplace leftovers, `HerdrAgent`. | Y | keep |
| `src/swarm/migrations/` | Schema including `0012_herdragent`. | Y | keep |
| `src/swarm/herdr/` | Official `herdr` CLI wrapper (REQ-21). Empty `remote` = localhost sockets. | Y | keep (see §4) |
| `src/swarm/mcp/` | Installed Django app `swarm.mcp` (blueprint-as-MCP-tools). | Y | keep |
| `src/swarm/management/commands/runserver.py` | Custom `runserver` (`--disable-auth`). Daphne-first so WS works. | Y | keep |
| `src/swarm/services/` | GitHub marketplace client, job runner, `secure_subprocess` (Herdr uses this). | Y | keep |
| `src/swarm/utils/` | Env / dotenv / logging / redaction. Imported by `settings.py` and both `manage.py`. | Y | keep |
| `src/swarm/extensions/mcp/` | Optional MCP client/tool-provider (not `INSTALLED_APPS`). | ? | keep; do not merge with `swarm.mcp` without an ADR |
| `src/swarm/memory/` | Optional mem0 / langmem / papr backends. | ? | keep (optional extra); do not hoist to top-level |
| `src/swarm/ux/` | CLI ANSI box drawing. | ? | keep (CLI-only) |
| `src/swarm/core/utils/logger.py` | Leftover logger (comment still names `src/swarm/config/utils/logger.py`). | ? | merge into `utils/` later or leave |

### 1.3 Blueprints (recipes vs leftover Django mini-apps)

Discovery walks `BLUEPRINT_DIRECTORY` for `blueprint_*.py`. `urls_module` /
`url_prefix` are **never consumed** except declared on `django_chat`.

| Path | Role | Load-bearing | Proposed action |
|------|------|--------------|-----------------|
| `src/swarm/blueprints/chatbot`, `dynamic_team` | Thin LLM / alias recipes. | Y | keep |
| `src/swarm/blueprints/cli_*` (agent, ensemble, fusion, map, orchestrator, pipeline, planner, recurse, roundtable) | CLI-fusion strategy recipes. | Y | keep (core.md wrap later; do not move) |
| `src/swarm/blueprints/hybrid_*`, `moa`, `moa_orchestrator` | Multi-agent / MoA recipes. | Y | keep |
| `src/swarm/blueprints/software_dev`, `gate`, `skeptic` | Roles/workflows (#420). CLI/API only. | Y | keep |
| `src/swarm/blueprints/codey`, `suggestion` | Also hatch console scripts. | Y | keep |
| `src/swarm/blueprints/geese`, `chucks_angels`, `jeeves`, `poets`, `stewie`, `persona_council` | Bundled recipes. | Y | keep |
| `src/swarm/blueprints/fs_introspect`, `remote_harness`, `harness_fleet`, `rue_code` | Filesystem / remote / harness recipes. | Y | keep |
| `src/swarm/blueprints/agent_router`, `support` | Router / Support briefing recipes (SPA `/agents` + rail). | Y | keep |
| `src/swarm/blueprints/gawd`, `zeus`, `whiskeytango_foxtrot` | Recipes **plus leftover `apps.py`**. No templates/urls/views. Not in `INSTALLED_APPS`. | Y (recipe) / N (`apps.py`) | keep recipe; **delete** leftover `apps.py` later (core.md P2-10; **not** #419) |
| `src/swarm/blueprints/django_chat/` | Unmounted webpage + import-time `django.setup()` + still-discoverable id. | Y (discovery) / N (HTTP) | **delete** package in #419 (prefer); do not move |
| `src/swarm/blueprints/django_chat/templates/django_chat/django_chat_webpage.html` | Alpine/HTMX model dropdown. App not installed → `APP_DIRS` cannot see it. | N | delete with #419 |
| `src/swarm/blueprints/django_chat/{urls,views,apps}.py` | Mini-app; `name = "blueprints.django_chat"` (wrong vs `swarm.blueprints…`). | N | delete with #419 |
| `src/swarm/blueprints/README.md` | Still lists django_chat as “Django-integrated chat”. | ? | delete/edit that row with #419 (W-03) |

No other blueprint ships `templates/` or a webpage. Messenger stub dir is
already gone (wave 2 W-16).

### 1.4 Django views / templates / static

| Path | Role | Load-bearing | Proposed action |
|------|------|--------------|-----------------|
| `src/swarm/views/web_views.py` | `/` (SPA or Django `index.html`), `/chat` SPA, Teams launcher/admin, profiles, `team_rosters.json`. SPA paths are **cwd-relative** `webui/frontend/dist`. | Y | keep |
| `src/swarm/views/webui.py` | Legacy `/webui/` → `/`. | Y | keep (bookmark compat) |
| `src/swarm/views/chat_views.py` | `/v1/chat/completions`, `/health`. | Y | keep |
| `src/swarm/views/chat_persist_views.py` | `/chat/thread/`, `/chat/compact/`, retention POSTs. | Y | keep |
| `src/swarm/views/settings_views.py` + `settings_manager.py` | `/settings/` dump + `/settings/api/` + env. | Y | keep (sheet ≠ dump; [wave 1 Q-03](./qa-wave1-django-spa.md)) |
| `src/swarm/views/teams_api.py` | `/v1/teams/` LLM-profile **aliases**. | Y | keep (do not merge with rosters) |
| `src/swarm/views/team_rosters_api.py` | `/v1/team-rosters/` composition. | Y | keep |
| `src/swarm/views/herdr_api.py` | `/v1/herdr-agents/` + discover. | Y | keep |
| `src/swarm/views/remotes_api.py` | Hermes / OMB / Rakazo remotes. | Y | keep |
| `src/swarm/views/api_views.py` | Blueprints, models, CLI agents, config-options (includes **skills**), marketplace, support. | Y | keep |
| `src/swarm/views/definition_views.py` | `/v1/definitions/` (Settings sheet Blueprint editor). | Y | keep |
| `src/swarm/views/agent_router_views.py` + `agent_router_page.py` | `/v1/agents/*` + `/agents` (SPA `dist` or `agent_router.html`). | Y | keep |
| `src/swarm/views/blueprint_library_views.py` | `/blueprint-library/` HTML + avatars. | Y | keep |
| `src/swarm/views/library_api.py` | `/v1/library/` SPA-parity REST. | Y | keep |
| `src/swarm/views/agent_creator_views.py` | `/agent-creator/`, `/team-creator/` (stamps `tags: ["swarm", "webui"]` — wave 2 W-09). | Y | keep pages; wrap tag later |
| `src/swarm/views/session_explorer.py` | `/sessions/` over `/v1/responses`. | Y | keep |
| `src/swarm/views/llm_profiles_api.py` | `/v1/llm-profiles/`. | Y | keep |
| `src/swarm/views/responses_views.py` | OpenAI Responses API. | Y | keep |
| `src/swarm/views/system_views.py` | `/v1/system/` local-store facts (REQ-56). | Y | keep |
| `src/swarm/views/core_views.py` | Dead: renders missing `swarm/index.html` / `swarm/login.html`. Not in `urls.py`. | N | delete (wave 1 Q-17) |
| `src/swarm/templates/base.html` | Operator shell: Home · Chat · Blueprints · Teams · Sessions · Settings + dock. Comment still claims it “matches SPA”. | Y | keep until retirement; comment is stale |
| `src/swarm/templates/index.html` | Home **only if** `dist/` missing. | ? | keep as fallback **or** shrink to “build the frontend” stub |
| `src/swarm/templates/agent_router.html` | `/agents` fallback if `dist/` missing. | ? | keep as fallback |
| `src/swarm/templates/teams_launch.html` + `static/js/teams_launch.js` | Public blueprint launcher. `ENABLE_WEBUI` gated. | Y | keep |
| `src/swarm/templates/teams_admin.html` + `teams_admin.js` | Alias CRUD + `#herdr-members`. Login + `ENABLE_WEBUI`. | Y | keep (Herdr UI lives here) |
| `src/swarm/templates/settings_dashboard.html` + `settings_dashboard.js` | Operator dump + REQ-14 retention + Herdr. | Y | keep |
| `src/swarm/templates/blueprint_library.html` + `my_blueprints.html` + `blueprint_*.html` + JS | Catalog / creator / source. | Y | keep |
| `src/swarm/templates/agent_creator.html` / `team_creator.html` | Hidden factories (no nav href). | Y | keep or hide behind library Create |
| `src/swarm/templates/session_*.html` + JS | Session Explorer. | Y | keep |
| `src/swarm/templates/profiles.html` | LLM profile table. | Y | keep or fold into Settings later |
| `src/swarm/templates/account/login.html` | Login mini-shell. | Y | keep |
| `src/swarm/templates/account/signup.html` | No URL; title still “django_chat”. | N | delete (W-08 / Q-16) |
| `src/swarm/templates/websocket_partials/*` | WS HTML frames parsed by SPA `chatWs.ts`. | Y | keep until JSON frames exist |
| `src/swarm/static/js/chrome_theme.js` / `agent_sidebar.js` | Django port of theme + AGENTS rail. | Y | keep (shared keys `swarm_theme`, `swarm_hidden_agents`) |
| `src/swarm/static/js/dropdown.js` | Unreferenced; redirects to `/django_chat/<bp>/new/`. | N | delete (W-07 / Q-18) |
| `src/swarm/static/css/dropdown.css` | Still linked from `base.html`. | ? | delete with JS if unused |
| `src/swarm/static/js/htmx.min.js` + `htmx_csp.js` | Loaded on every operator page; no `hx-` on those pages. | ? | keep for WS partials / later delete from operator chrome |
| `src/swarm/static/contrib/` | Bootstrap, Font Awesome, Prism, marked, Tabler. | Y | keep while operator HTML lives |
| `src/swarm/static/css/operator.css` / `rest_mode_style.css` | Operator + shared `os-action-card`. | Y | keep |
| `src/swarm/static/rest_mode/` (~84 files) | Pre-ADR chat/settings fossil. Tests still use some JS for XSS. | N (chrome) / Y (tests) | archive or keep-for-tests; **do not** wire into `base.html` |
| `src/swarm/static/team_rosters.json` | Sidepane seed (also `webui/frontend/public/team_rosters.json`). | Y | keep; do not invent a third copy |
| `src/swarm/static/htmx/` | Extra vendored HTMX tree. | ? | merge with `static/js/htmx.min.js` or leave |

### 1.5 `webui/` (SPA + glue)

There is **no** `webui/backend/`. Django that serves the SPA lives under
`src/swarm/views/{web_views,webui}.py` and `urls.py`.

| Path | Role | Load-bearing | Proposed action |
|------|------|--------------|-----------------|
| `webui/README.md` | Dev: Vite `:3000` → Django `:8000`. Stale: still describes `/` as dashboard + lists missing `tailwind.config.js`. | ? | archive/edit on a docs pass (Scope C adjacent) |
| `webui/frontend/package.json` | `open-swarm-webui`. Node `>=22.12`. | Y | keep |
| `webui/frontend/package-lock.json` | Canonical. `npm ci` in `scripts/build_frontend.sh`, Docker, CI. | Y | keep |
| `webui/frontend/pnpm-lock.yaml` | Divergent leftover. | N | delete (webui.md P2-3) |
| `webui/frontend/vite.config.ts` | Dev proxy → `127.0.0.1:8000`. `preview.proxy = {}` for Playwright. | Y | keep |
| `webui/frontend/src/App.tsx` | Routes: `/` + `/chat` → `ChatPage`; `/agents` → `AgentRouterPage`; `*` → `/`. Settings sheet + Search over Chat. | Y | keep |
| `webui/frontend/src/pages/ChatPage.tsx` | Product Chat. | Y | keep |
| `webui/frontend/src/pages/AgentRouterPage.tsx` | Own chrome; uses **folder** `components/AgentSidebar/`. | Y | keep |
| `webui/frontend/src/pages/Dashboard.tsx` | **Unrouted.** Tests still import it. | N | delete (or archive) after unlocking tests |
| `webui/frontend/src/components/AgentSidebar.tsx` | Live Grok rail (~1130 lines). Used by `App.tsx`. Lists Herdr via `/v1/herdr-agents/`. | Y | keep |
| `webui/frontend/src/components/AgentSidebar/` | Second sidebar implementation for Agent Router. | Y | merge with the rail component later; **do not** delete one while `/agents` uses the other |
| `webui/frontend/src/components/AgentAvatar.tsx` vs `AgentSidebar/AgentAvatar.tsx` | Two avatars. | Y (both used) | merge |
| `webui/frontend/src/components/SettingsSheet.tsx` | REQ-19 DaisyUI end-sheet (not Django `/settings/`). | Y | keep |
| `webui/frontend/src/components/SearchPalette.tsx` | In-chrome launcher (Django hops). | Y | keep |
| `webui/frontend/src/experimental/CommandPalette.tsx` | Default-ON third catalog. | ? | promote or delete (webui.md P1-6/P1-7) |
| `webui/frontend/src/components/DaisyUI/*` | 13 wrappers; live pages use a subset. | ? | delete unused museum later |
| `webui/frontend/src/lib/api.ts` | Live: blueprints, Herdr, CLI agents, … Plus leftover Builder CRUD. | Y | keep live exports; delete unused |
| `webui/frontend/src/lib/agentRoles.ts` | Rail / Chat / Settings roles. | Y | keep |
| `webui/frontend/src/lib/agent-roles.ts` | Agent Router / AgentChat roles (parallel module). | Y | merge with `agentRoles.ts` later |
| `webui/frontend/src/lib/{supportAgent,supportAgents,support-briefing}.ts` | Support-agent helpers (split names). | Y | merge |
| `webui/frontend/src/lib/{highlightPython,highlight-python}.ts` | Highlight (wrapper + impl). | Y | merge |
| `webui/frontend/src/lib/{skills,inferenceProfile,toolCapabilities}.ts` | ADR-001 Builder leftovers; tests-only. | N | delete |
| `webui/frontend/src/lib/teamRoster.ts` + `teamRosters.ts` | Composition roster client (`kind` includes `herdr`). | Y | keep |
| `webui/frontend/public/team_rosters.json` | Vite-dev + Django candidate. | Y | keep |
| `webui/frontend/e2e/` | Playwright chrome locks. | Y | keep (do not treat as sacred IA if chrome ADR changes) |
| `webui/frontend/src/lib/chatWs.ts` | Talks to `routing.py` `ws/ai-demo/…`. | Y | keep |

Vite proxies `/v1`, `/teams`, `/settings`, `/sessions`, `/blueprint-library`,
`/ws`, … to Django `:8000`. **Not** proxied: `/chat/thread/` and
`/chat/compact/` (would collide with SPA `/chat`). Production Django matches
those exact paths; `npm run dev` can lie.

`ENABLE_WEBUI` gates Django **Teams launcher/admin**, not whether `dist/` is
served.

### 1.6 `skills/`

| Path | Role | Load-bearing | Proposed action |
|------|------|--------------|-----------------|
| `skills/conventional-commit/SKILL.md` | Bundled skill. | Y | keep |
| `skills/reviewing-code/SKILL.md` | Bundled skill. | Y | keep |
| `skills/writing-changelog/SKILL.md` | Bundled skill. | Y | keep |
| `skills/counting-lines/SKILL.md` + `count.py` | Bundled skill + asset (`stage_assets`). | Y | keep |
| `src/swarm/core/skills.py` | Loader (`discover_skills` / `apply_skill`). | Y | keep |
| `GET /v1/config-options/` | Serializes the catalog (deleted SPA Builder still consumes via unused `api.ts`). | Y (API) | keep API; SPA client is remount bait |
| `webui/frontend/src/lib/skills.ts` | `buildSkillRequest()` → `cli_agent` + `params.skill`. Tests only. | N | delete with Builder leftovers |

These are **open-swarm agent skills** (Anthropic `SKILL.md` format), not Cursor
skills. Hatch wheel does not ship `skills/`; a pip-only install must keep a
repo-root (or `--dir`) catalog. Moving the tree under `src/swarm/skills/`
without changing `skills_root()` **breaks** `swarm-cli skills` and
`tests/core/test_skills.py`.

---

## 2. SPA vs Django leftover ownership

Product decision in code (ahead of ADR-001 text):

| Surface | Owner | Stack | Routes |
|---------|-------|-------|--------|
| **Grok chrome (day-to-day)** | SPA | React 18 + DaisyUI 5 | `/`, `/chat`, `/chat/*` |
| **Agent Router** | SPA (Django fallback HTML) | React; `agent_router.html` if no `dist/` | `/agents`, `/agents/*` |
| **Operator back-office** | Django | Bootstrap 5 + `operator.css` + vanilla JS | `/teams/`, `/teams/launch/`, `/blueprint-library/`, `/agent-creator/`, `/team-creator/`, `/settings/`, `/sessions/`, `/profiles/` |
| **Auth / admin** | Django | contrib | `/login/`, `/accounts/login/`, `/admin/` |
| **Transport** | Django | DRF + Channels | `/v1/*`, `/chat/thread/`, `/chat/compact/`, `ws/ai-demo/<id>/` |
| **Legacy bookmark** | Django redirect | `WebUIView` | `/webui/` → `/` |
| **Unmounted blueprint webpage** | nobody | leftover files | advertised `/django_chat/` — SPA catch-all → product Chat if `dist/` exists |

```
                    ┌─────────────────────────────────────────┐
  browser  `/`      │  webui/frontend (Grok rail + Chat)      │
  `/chat`           │  SettingsSheet / SearchPalette overlays │
  `/agents`         └───────────────┬─────────────────────────┘
                                    │ fetch / WS (cwd-relative dist)
                                    ▼
  Django `src/swarm`  ┌──────────────────────────────────────┐
                      │ urls.py + views/ + consumers.py      │
                      │ /v1/*  /ws  /chat/thread  Herdr API  │
                      └───────────────┬──────────────────────┘
                                      │ full-page <a href>
                                      ▼
  leftover operator   ┌──────────────────────────────────────┐
                      │ templates/ + static/js (Bootstrap)   │
                      │ Teams / Library / Settings dump      │
                      │ Herdr members UI lives HERE          │
                      └──────────────────────────────────────┘
```

**Who owns which noun (do not “simplify” by merging stores):**

| Noun | SPA owns | Django leftover owns | Must not collapse |
|------|----------|----------------------|-------------------|
| Chat UI | `ChatPage` | deleted `chat.html`; WS **partials** still Django | Partials until JSON frames |
| Settings | `SettingsSheet` (browser prefs) | `/settings/` operator dump + REQ-14 **server** retention | Two products (wave 1 Q-03) |
| Team | Rail rosters `/v1/team-rosters/` + `?team=` | `/teams/` aliases; `/teams/launch/` run-a-blueprint; `/team-creator/` codegen | Four meanings (wave 1 Q-01) |
| Herdr | Rail list + href `/teams/#herdr-members` | ORM + `/v1/herdr-agents/` + Teams/Settings JS | API + model stay; UI hop is leftover |
| Blueprints | Rail `/v1/blueprints` + Chat `?blueprint=` | Library HTML + `/v1/library/` | Catalog id ≠ webpage |
| Agents (Router) | `AgentRouterPage` + `/v1/agents/` | `agent_router.html` fallback | Prefer SPA |
| Home | Chat (`/`) | `src/swarm/templates/index.html` if no `dist/` | Fallback is a second product |
| Theme | `data-theme` + `swarm_theme` | `data-bs-theme` / `data-os-theme` + same key | Shared **storage**, not DOM |
| Skills | unused `lib/skills.ts` | `/v1/config-options/` + `core/skills.py` + repo `skills/` | CLI/API, not chrome |

**ADR-001 vs tree:** the ADR still says SPA retains `/` **dashboard** + `/chat`.
Code mounts Chat at both. FEATURE_STATUS is closer. A later docs PR should
amend the ADR; do not “restore” `Dashboard.tsx` to satisfy the ADR.

**#419 vs operator chrome:** retiring `django_chat` does **not** retire
`templates/` or `webui/`. Those are the product / leftover operator UIs.
Wave 2 I-01…I-07 stay.

---

## 3. Proposed package boundaries (later, after CoS picks)

Target shape — **logical** ownership, not a move plan for this week:

```
repo root
├── manage.py                 # only Django CLI entry
├── skills/                   # Agent Skills catalog (discovered, not imported)
├── webui/frontend/           # Grok chrome source; build → dist/ (not in wheel)
└── src/swarm/                # the pip package
    ├── settings.py / urls.py / asgi.py
    ├── core/                 # CLI + API kernel (no HTML)
    ├── blueprints/           # CLI/API recipes only (no apps.py / templates)
    ├── herdr/                # herdr argv wrapper
    ├── views/                # HTTP + /v1  (serves dist/; operator HTML until retired)
    ├── models/ + migrations/
    ├── templates/ + static/  # operator leftover (explicitly “not Grok chrome”)
    ├── mcp/                  # installed Django MCP app
    └── extensions/ + memory/ + services/ + utils/
```

| Should live | Where | Why |
|-------------|-------|-----|
| Grok rail, Chat, Agent Router, Settings sheet | `webui/frontend/src/` | Node toolchain; DaisyUI; already the product chrome |
| SPA build output | `webui/frontend/dist/` (gitignored) | Docker `COPY` + `web_views._get_frontend_path()` |
| Django that **serves** SPA | `src/swarm/views/web_views.py` + `urls.py` | ASGI buffer / auth / fallback |
| Operator HTML/JS | stay under `src/swarm/templates` + `static` | `APP_DIRS` + `STATICFILES_DIRS`; Herdr/Teams/Settings hops |
| Blueprint recipes | `src/swarm/blueprints/<id>/` | `BLUEPRINT_DIRECTORY` + discovery |
| Blueprint **webpages** | nowhere | #419: CLI/API only |
| Herdr wrapper + ORM + `/v1/herdr-agents/` | `src/swarm/herdr` + `models/herdr.py` + `views/herdr_api.py` | Live-host binary; CI mocks |
| Agent Skills | repo-root `skills/` + `core/skills.py` | `get_project_root_dir() / "skills"`; hatch does not ship them |
| MCP Django app vs MCP client | `swarm.mcp` vs `extensions/mcp` | Different jobs; do not merge on a tidy pass |
| Alias Teams vs roster Teams | `src/swarm/views/teams_api.py` vs `views/team_rosters_api.py` | Two contracts |

**Reasonable later tidy (still not this PR):**

1. Delete `src/manage.py` after scripts call root `manage.py`.
2. Delete dead Django: `core_views.py`, `signup.html`, `dropdown.js`.
3. Delete `django_chat/` via #419 (not a move).
4. Delete leftover blueprint `apps.py` (gawd / zeus / whiskeytango).
5. Delete SPA Builder leftovers + unrouted `Dashboard.tsx` + extra lockfile.
6. Merge dual SPA modules (`AgentSidebar` ×2, `agentRoles` / `agent-roles`, avatars).
7. Point `TEMPLATES['DIRS']` at a real dir or drop the missing `<repo>/templates`.
8. Resolve SPA `dist/` via `settings.BASE_DIR.parent` instead of cwd (only with
   a dedicated serve-path ticket — see §4).

**Do not** create `src/open_swarm/` or split `swarm` into `swarm_core` +
`swarm_web` until hatch, `DJANGO_SETTINGS_MODULE`, Docker `PYTHONPATH`, and
blueprint discovery are redesigned together.

---

## 4. Do not do yet (risks)

These look like “structure cleanup” and will break live hosts or #419/#452
intent if an implementer starts from this file.

### 4.1 Herdr (REQ-21) — not a preview leftover

| Do not | Why |
|--------|-----|
| Move or rename `src/swarm/herdr/` | `HerdrClient` wraps the **official** `herdr` binary. `herdr_available()` is “live hosts only.” Cloud CI **mocks** it. |
| Delete `models/herdr.py` / migration `0012` / `/v1/herdr-agents/` | Persisted `kind=herdr` members. SQLite default; no Neon. |
| “Fix” rail Herdr links to stay in SPA | They intentionally hop to Django `/teams/#herdr-members`. Changing the hash or retiring that fragment without a roster editor loses the only add/remove UI. |
| Bake `198.51.100.30`, Fly, or `--remote` defaults | Same-host empty `remote` is the contract ([docs/HERDR.md](../HERDR.md)). |
| Call live `herdr` from CI or this cloud | Tests mock. Do not target a WORKING pane. |
| Confuse Herdr with Hermes / OMB / Rakazo | Those are `views/remotes_api.py` + `harness_fleet` `"kind": "hermes webui"` (wave 2 I-07). |

### 4.2 Live preview / `:8001` / cwd serve

| Do not | Why |
|--------|-----|
| Touch `:8001` or LAN preview hosts | Out of scope (#452). No `:8001` constants in `src/swarm` or `webui/`. |
| Relocate `webui/` under `src/swarm/webui/` | `Path("webui/frontend/dist")` is **cwd-relative** in `web_views.py` and `urls.py`. Docker copies `/app/webui/frontend/dist`. Vite, `make frontend`, and Playwright assume today’s path. |
| Run `manage.py` from `src/` as the new normal | SPA `dist/` resolve fails; `/` falls back to a different Home. |
| Auto-`npm build` on `/chat` | `spa_chat()` deliberately does not call `_ensure_frontend_built()` (tests). |
| Enable `vite preview` proxies | `preview.proxy = {}` keeps Playwright hermetic. |
| Point Herdr or remotes at a preview URL | Live `.30` notes in HERDR.md are **documentation**, not code defaults. |

### 4.3 Django / SPA / django_chat

| Do not | Why |
|--------|-----|
| Remount `Dashboard`, TeamsPage, SettingsPage, Builder | ADR-001 + #419. `Dashboard.tsx` on disk is not a route. |
| Remount `django_chat` or add `kind=webui` | Webpage is already unmounted. Catch-all `/django_chat/` is product Chat. |
| Delete `templates/` + `static/` in the same PR as `django_chat` | Operator leftover is still the Teams / Settings / Herdr / Library UI. |
| Delete `ChatConversation` / WS partials / REQ-14 with #419 | Wave 2 I-01. Blueprint only **reads** conversations. |
| Merge `/v1/teams` into `/v1/team-rosters` because both say Team | Alias ≠ composition. |
| Fold Settings sheet into `/settings/` (or the reverse) without an ADR | Two stores (localStorage vs server retention). |
| Move `skills/` into `src/swarm/` or `.cursor/skills/` | Breaks discovery + tests; these are not Cursor skills. |
| Merge `extensions/mcp` into `swarm.mcp` | Installed app vs optional client. |
| Fan implementer clouds off #452 | CoS reviews this look-only file first. #419 stays a separate delete ticket. |

### 4.4 Safe later vs unsafe now

**Safer later deletes (still not this PR):** `core_views.py`, `signup.html`,
`dropdown.js`, `pnpm-lock.yaml`, SPA Builder libs, leftover blueprint
`apps.py`, `django_chat/` **via #419**.

**Unsafe “tidies”:** any move of `webui/`, `skills/`, `herdr/`, `blueprints/`,
or `manage.py`; rewriting SPA fallback exclusions; changing
`DJANGO_SETTINGS_MODULE`; installing `django_chat` “to make the tree honest.”

---

## Out of scope (this PR / this file)

- No product, test, CI, Docker, or existing `docs/debt/*.md` edits.
- No Scope A root markdown / Pinokio / `scripts/` inventory.
- No Scope C docs-guide honesty pass (except citing stale ADR/FEATURE_STATUS).
- No Scope D deploy/CI file moves.
- No Neon. No host bounce. No secrets. No `:8001`.
- No `Fixes #452` / `Fixes #419`. Implementer work waits on CoS + Matthew.
