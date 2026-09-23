# Screenshot Registry

Master registry of every screenshot in the repository. All current captures
live in [`docs/screenshots/`](./screenshots/) and were taken from a live local
dev server by
[`scripts/capture_user_journey.py`](../scripts/capture_user_journey.py) —
headless Chromium, 1280×800 viewport (desktop) or 390×844 dpr2 (mobile),
full-page PNGs.

> **Documentation map:** [USERGUIDE.md](../USERGUIDE.md) is the `os-cli`
> reference, [USER_JOURNEY.md](./USER_JOURNEY.md) is the end-to-end story,
> [GUIDED_TOUR.md](./GUIDED_TOUR.md) is the visual tour, and this file is the
> capture registry.

## Current captures (`docs/screenshots/`)

| File | Page / URL | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- | --- |
| `flagship-rail.png` | `/` (React SPA ChatPage) | **Flagship (REQ-852 / #465):** the live rail with the Showcase sections profile applied (Settings → Rail → Showcase toggle; #544) — CLI / API / Remote / Fancy section headers over the real seats. Re-capture with `scripts/capture_flagship_465.py` (drives the demo-profile toggle; never seeds synthetic seats) | README.md, GUIDED_TOUR.md | 2026-09-19 | current |
| `landing.png` | `/` (React SPA ChatPage) | Grok-like rail + **Support** chat; kickstart chips; composer. **Not** a count dashboard. `os-cli list` **31** dirs ≠ library **49** / **12 of 49** | USER_JOURNEY.md, GUIDED_TOUR.md, README.md | 2026-09-16 | current |
| `spa-chat.png` | `/chat` (React SPA) | Same ChatPage as `/` after journey login (session cookie + Channels/ASGI `/ws/`). No standing Connected badge. **Unavailable** Sign-in CTA is for close **4401** / no session (not this PNG) | GUIDED_TOUR.md | 2026-09-16 | current |
| `spa-teams.png` | `/teams` → **`/teams/launch/`** | Django redirect landing (SPA no longer mounts `/teams`; ADR-001) with sticky capture **“Redirected: /teams → /teams/launch/ …”** banner; Team Launcher underneath with **`fs_introspect`** selected | GUIDED_TOUR.md | 2026-09-16 | current (redirect stem) |
| `spa-blueprints.png` | `/blueprints` → **`/blueprint-library/`** | Django redirect landing (SPA unmounted `/blueprints`; ADR-001) with sticky **“Redirected: …”** banner over Blueprint Library | GUIDED_TOUR.md | 2026-09-16 | current (redirect stem) |
| `spa-settings.png` | `/settings` → **`/settings/`** | Django redirect landing (SPA unmounted `/settings`; ADR-001) with sticky **“Redirected: …”** banner over Settings Dashboard (meter **40 of 47** / **85%**) | GUIDED_TOUR.md | 2026-09-16 | current (redirect stem) |
| `spa-agent-creator.png` | `/agent-creator` → **`/agent-creator/`** | Django redirect landing (SPA never remounts creator; ADR-001) with sticky **“Redirected: …”** banner over Agent Creator | GUIDED_TOUR.md | 2026-09-16 | current (redirect stem) |
| `login.png` | `/accounts/login/` (Django) | Sign-in form; wordmark **Operating Swarm** + bee mark | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `teams.png` | `/teams/` (Django) | Teams Admin registration form + table | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `teams-launch.png` | `/teams/launch/` (Django) | Team Launcher; **`fs_introspect`** selected (first dropdown option); empty output | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `blueprint-library.png` | `/blueprint-library/` (Django) | `discover_blueprints()` catalog: Available **49**, pagination **Showing 12 of 49** + Show more, MCP badges (ready green checkmarks); **≠** `os-cli list` **31** | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `my-blueprints.png` | `/blueprint-library/my-blueprints/` (Django) | Custom Created **20** (Lib Agent cards + **First Team**) + create card; Installed **0** (not empty) | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `agent-creator.png` | `/agent-creator/` (Django) | Progressive disclosure: **1 Identity** open; **2 Optional Persona** / **3 Optional Tags** collapsed; **Generate Blueprint** / **Validate** | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `settings.png` | `/settings/` (Django) | Settings dashboard for **Operating Swarm (OS)**; meter **40 of 47** / **85%** (product setting groups with defaults — not the old empty **0 of 0** fixture); category tiles | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `sessions.png` | `/sessions/` (Django) | Session Explorer empty state: 0 sessions, live toggle, owner-scoped copy (“No sessions for your account yet… only sessions you own”) + POST /v1/responses CTA (captured before mid-run seed) | USER_JOURNEY.md, GUIDED_TOUR.md, SESSION_EXPLORER.md | 2026-09-16 | current |
| `session-detail.png` | `/sessions/resp_journey_seed/` (Django) | Session detail Graph tab: seeded `hybrid_team` fixture (`resp_journey_seed`) with orchestration/agent/auxiliary nodes — real template, synthetic JSON (**not** a live hybrid_team run) | USER_JOURNEY.md, GUIDED_TOUR.md, SESSION_EXPLORER.md | 2026-09-16 | current |
| `profiles.png` | `/profiles/` (Django) | LLM profiles table (provider/model/source/enabled; Settings → LLM profiles active) | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-09-16 | current |
| `req508-teams-composer/1-essentials.png` | `/chat` Teams composer (#508) | Essentials tab of the redesigned Teams composer popup | none | 2026-09-19 | registry-only |
| `req508-teams-composer/2-roles-pane.png` | `/chat` Teams composer (#508) | Roles pane — CoS/engineer/skeptic slot assignment | none | 2026-09-19 | registry-only |
| `req508-teams-composer/3-tools-pane.png` | `/chat` Teams composer (#508) | Tools pane — tool slot drop zone | none | 2026-09-19 | registry-only |
| `req508-teams-composer/4-catalog-pane.png` | `/chat` Teams composer (#508) | Catalog pane — member picker over the agent catalog | none | 2026-09-19 | registry-only |
| `req508-teams-composer/5-back-to-essentials.png` | `/chat` Teams composer (#508) | Return to Essentials after walking tabs | none | 2026-09-19 | registry-only |
| `req910-plugins/1-rail.png` | `/chat` Rail (REQ-910) | Rail with the Plugins launcher in the sidepane | none | 2026-09-19 | registry-only |
| `req910-plugins/2-plugins-chat-pane.png` | `/chat` Plugins popup (REQ-910) | Plugins popup — chat connector pane | none | 2026-09-19 | registry-only |
| `req910-plugins/3-plugins-tools-pane.png` | `/chat` Plugins popup (REQ-910) | Plugins popup — tools pane | none | 2026-09-19 | registry-only |
| `req910-plugins/4-plugins-skills-pane.png` | `/chat` Plugins popup (REQ-910) | Plugins popup — skills pane | none | 2026-09-19 | registry-only |

The "Used in" column is verified by grepping the docs for
`screenshots/<file>`. USERGUIDE.md embeds no PNG files (CLI reference only)
but points readers at this tour.

## Visual-proof captures (per-REQ folders, `docs/screenshots/`)

PR visual evidence saved next to the QA page it proves. Not embedded in any
doc — each is **registry-only** by design; the PR description referenced it
at merge time.

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `req508-teams-composer/1-essentials.png` | REQ-508 Teams composer — Essentials tab | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/2-roles-pane.png` | REQ-508 Teams composer — Roles pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/3-tools-pane.png` | REQ-508 Teams composer — Tools pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/4-catalog-pane.png` | REQ-508 Teams composer — Catalog pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/5-back-to-essentials.png` | REQ-508 Teams composer — back to Essentials (pane toggle round-trip) | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/1-rail.png` | REQ-910 — rail with Plugins entry | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/2-plugins-chat-pane.png` | REQ-910 Plugins popup — chat (agent) pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/3-plugins-tools-pane.png` | REQ-910 Plugins popup — Add tools pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/4-plugins-skills-pane.png` | REQ-910 Plugins popup — Add skills pane | none (registry-only visual proof) | 2026-09 | registry-only |

## Mobile captures (`docs/screenshots/mobile/`)

Same stems as desktop with `--mobile` (iPhone-14-class: 390×844, dpr 2, touch).

**Parked-dock capture artifact:** `capture_user_journey.py` sets visible fixed
bottom bars (Django `.os-bottom-nav`, SPA `nav.fixed.bottom-0`) to
`position:static` before `full_page=True` so Chromium stitch does not paint the
dock over mid-page content. Live UI keeps those docks **viewport-fixed**;
checked-in mobile PNGs therefore show the tab bar **after scrolled page
content** (end of the PNG), not floating over the viewport. Captions that name
the dock / **Agents + More** bar mean that parked strip.

**Bottom nav honesty (as of these PNGs):**

* **SPA** shell (`mobile/landing.png`, `mobile/spa-chat.png`) is Grok-like
  chat with the rail tucked — **no** five-tab dock on these PNGs. Settings is
  the header gear sheet.
* **Django** operator pages keep **Agents** + **More** (same destinations;
  logo is home). Mobile Django PNGs park that bar at the end of the full-page
  PNG.
* Bare `/teams` `/blueprints` `/settings` `/agent-creator` **redirect** to
  Django; `spa-*` stems are redirect captures (not live SPA pages).
* Desktop and mobile `spa-chat.png` show Support + kickstart chips after the
  journey script logs in as `journey-admin`. Capture waits for a terminal
  websocket state before shooting. When the websocket fails (4401 / ASGI down),
  ChatPage also renders a shrink-safe **Sign in** / **Reconnect** alert
  (unit-tested; not these PNGs).

| File | Page / URL | Mobile-specific notes | Captured | Status |
| --- | --- | --- | --- | --- |
| `mobile/landing.png` | `/` | Grok chrome: Support chat + chips; rail tucked; **no** SPA dock on this PNG. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/spa-chat.png` | `/chat` | Same ChatPage as `/`; Support + chips; rail tucked. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/spa-teams.png` | `/teams` → **`/teams/launch/`** | Redirect landing with sticky **“Redirected: …”** banner; Team Launcher (`fs_introspect` selected); Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/spa-blueprints.png` | `/blueprints` → **`/blueprint-library/`** | Redirect landing with sticky **“Redirected: …”** banner; single-column cards; Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/spa-settings.png` | `/settings` → **`/settings/`** | Redirect landing with sticky **“Redirected: …”** banner; Settings meter **40 of 47**; Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/spa-agent-creator.png` | `/agent-creator` → **`/agent-creator/`** | Redirect landing with sticky **“Redirected: …”** banner; Agent Creator; Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/login.png` | `/accounts/login/` | Full-width login card (no bottom primary bar). Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/teams.png` | `/teams/` | Django **Agents + More**; form wraps. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/teams-launch.png` | `/teams/launch/` | Launcher full-width; **`fs_introspect`** selected (first dropdown option); Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/blueprint-library.png` | `/blueprint-library/` | Paginated cards stack (**12 of 49** discoverable); Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/my-blueprints.png` | `/blueprint-library/my-blueprints/` | Custom Created **20** (Lib Agent / First Team) + create CTA; Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/agent-creator.png` | `/agent-creator/` | **1 Identity** accordion; **Generate Blueprint** / **Validate**; Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/settings.png` | `/settings/` | Meter **40 of 47** / **85%**; tiles wrap; Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/sessions.png` | `/sessions/` | Empty state (0 sessions + live toggle + owner-scoped empty copy); Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/session-detail.png` | `/sessions/resp_journey_seed/` | Seeded `hybrid_team` fixture Graph tab (same honesty as desktop — not a live run); Django **Agents + More**. Embedded in GUIDED_TOUR.md | 2026-09-16 | current |
| `mobile/profiles.png` | `/profiles/` | Profiles table; Django **Agents + More** (profiles nest under Settings). Embedded in GUIDED_TOUR.md | 2026-09-16 | current |

Regenerate with:

```bash
.venv/bin/python scripts/capture_user_journey.py --mobile
```

## Announce / README media (`docs/assets/readme/`)

Decided path for README heroes and the #456 kit. SoT:
[docs/ANNOUNCE.md](./ANNOUNCE.md), [docs/assets/readme/README.md](./assets/readme/README.md).

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `assets/readme/announce-bridge.gif` | REQ-136 / #529 hero (~18s storyboard): Grok-agnostic UI + CLI/API/remote bridge. Spiel captions. Roster: Hermes Remote, OpenMousBot Remote, Antigravity CLI, OpenCode CLI, BA→Engineer→Tester. Wordmark **Operating Swarm**. | README.md, ANNOUNCE.md | 2026-09-16 | storyboard (live recapture later) |

Regenerate the storyboard:

```bash
uv run --with pillow python scripts/render_announce_gif.py
```

## README demo slots (`docs/assets/readme/`) — REQ-97 / #456

Four compact README slots. **Posters now** (SVG). Live GIFs replace the same
stems via [`docs/assets/readme/RECORDING.md`](./assets/readme/RECORDING.md).
No secrets, no house stills, no live LAN IPs. Label **OpenMousBot**, never OMB.

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `assets/readme/cli-agents.gif` | Live SPA recapture (1280×800, `SWARM_TEST_MODE`): Grok-like rail + CLI seats | README.md | 2026-09-16 | current |
| `assets/readme/api-agents.gif` | Live SPA recapture: API / Support thread | README.md | 2026-09-16 | current |
| `assets/readme/remote-agents.gif` | Live SPA recapture: Hermes / OpenMousBot rows in the rail | README.md | 2026-09-16 | current |
| `assets/readme/combined-team.gif` | Live SPA recapture: Demo Bridge / combined roster | README.md | 2026-09-16 | current |
| `assets/readme/cli-agents.svg` | Poster fallback | README.md | 2026-09-06 | poster |
| `assets/readme/api-agents.svg` | Poster fallback | README.md | 2026-09-06 | poster |
| `assets/readme/remote-agents.svg` | Poster fallback | README.md | 2026-09-06 | poster |
| `assets/readme/combined-team.svg` | Poster fallback | README.md | 2026-09-06 | poster |

Reserved live-GIF names `cli.gif` / `api.gif` / `remotes.gif` / `combined.gif`
are still the #456 contract for filmed loops and are not checked in yet.

## Demo animations (`docs/demo/`)

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `demo/cli-agent.gif` | CLI agent: host executable discovery & native session launch (`grok-cli`); window title **operating-swarm** | README.md | 2026-09-16 | current |
| `demo/api-agent.gif` | API agent: OpenAI-compatible `/v1/models` and streaming completions (`litellm-api`) | README.md | 2026-09-16 | current |
| `demo/remote-agent.gif` | Remote agent: external harness catalog & bridge dispatch (**OpenMousBot**, Hermes) | README.md | 2026-09-16 | current |
| `demo/combined-team.gif` | Combined team: unified flow coordinating CLI + API + Remote via handoff (`demo-bridge`) | README.md | 2026-09-16 | current |
| `demo/cli-and-api.gif` | Historical animated terminal loop (~25s loop): `os-cli list`, `launch zeus`, curl `/v1/*`, optional `moa --team` (fake) | README.md | 2026-09-16 | historical |

Four scenes from real `SWARM_TEST_MODE` / curl / `--backend fake` captures under
`docs/demo/captures/` (see `raw_*.txt`). Scene 2 uses documented
`os-cli launch zeus` (after `install-executable zeus`). Scene 4 is
`os-cli moa --backend fake --team --workdir /tmp/moa-demo`.

Regenerate (real captures only) via
[`scripts/render_demo_gif.py`](../scripts/render_demo_gif.py) after updating
`docs/demo/captures/scene{1,2,3,4}.txt` (and `raw_*.txt`) from live commands —
see [Regenerating](#regenerating) below.

## Skills walkthrough (`docs/screenshots/skills/`)

Terminal stills from live CLI proof scripts (via
`webui/frontend/scripts/term-shot.mjs`). Paths in embeds are relative to each
markdown file under `docs/`.

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `skills/01-skills-list.png` | `os-cli skills` listing (name, assets, description) | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
| `skills/02-skills-show.png` | `os-cli skills --show` full `SKILL.md` dump | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
| `skills/03-skill-portable.png` | Same skill across gemini/claude/grok (`prove_skill_across_clis`) | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
| `skills/04-asset-toolcall.png` | Bundled-asset skill staging + execution (`counting-lines`) | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
| `skills/05-consensus.png` | 3-CLI consensus split (REST vs GraphQL) | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
| `skills/06-inference-profile.png` | Intent→backend routing table (`demo_inference_profile`) | examples/inference-profile-routing.md | mixed | current |
| `skills/07-tool-capabilities.png` | Capability→MCP provider resolution demo | examples/tool-capabilities.md | mixed | current |

## Historical SPA Builder (`docs/screenshots/webui/`)

Orphaned `/builder` stills (ADR-001 unmounted the SPA Builder; day-to-day
creation is Django `/agent-creator/`). Dark panels remain embedded in the
historical example doc; light twins are **registry-only** (not embedded).

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `webui/blueprint-tools-badge-dark.png` | Resolved tools (MCP) badge on Builder source card | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/builder-all-panels-dark.png` | Full Builder with all config panels | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/builder-dark.png` | Builder full-page capture (dark) | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/builder-light.png` | Builder full-page light twin | none (registry-only light twin) | mixed | orphaned |
| `webui/inference-profile-dark.png` | Inference profile panel (dark) | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/inference-profile-light.png` | Inference profile panel light twin | none (registry-only light twin) | mixed | orphaned |
| `webui/skills-dark.png` | Skills picker panel (dark) | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/skills-light.png` | Skills picker panel light twin | none (registry-only light twin) | mixed | orphaned |
| `webui/skills-preview-dark.png` | Skills picker with SKILL.md preview | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/tool-capabilities-dark.png` | Tool capabilities / MCP panel (dark) | examples/webui-config-panels.md (historical) | mixed | orphaned |
| `webui/tool-capabilities-light.png` | Tool capabilities panel light twin | none (registry-only light twin) | mixed | orphaned |
| `webui/trait-editor-dark.png` | Per-model trait editor panel | examples/webui-config-panels.md (historical) | mixed | orphaned |

## Other images in the repo

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `assets/images/20250105-Open-Swarm-HTML-Page.png` | Old HTML landing | unused (legacy; outside `docs/screenshots/`) | 2025-01-05 | legacy |
| `docs/screenshots/archive/session-explorer-detail.png` | Older Session detail still (superseded by current `session-detail.png`) | none (intentional archive) | archived | archived |
| `docs/screenshots/archive/session-explorer-list.png` | Superseded list still (replaced by `sessions.png`) | none (intentional archive) | archived | archived |
| `docs/screenshots/archive/a11y-focus-ring.png` | Old a11y focus-ring still | none (intentional archive) | archived | archived |

## Regenerating

### WebUI / journey screenshots

```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
.venv/bin/python scripts/capture_user_journey.py            # desktop
.venv/bin/python scripts/capture_user_journey.py --mobile   # mobile
# optional manifest:
CAPTURE_MANIFEST=/tmp/capture-manifest.json .venv/bin/python scripts/capture_user_journey.py
```

The script starts its own dev server on port 8321
(`DJANGO_DEBUG=true ENABLE_WEBUI=true`), uses an isolated
`SWARM_RESPONSES_DIR` (empty for `sessions.png`), migrates, logs in a
throwaway superuser, captures every page in `PAGES`, mid-run seeds
`resp_journey_seed` before `session-detail.png`, overwrites PNGs, skips
(never fakes) 4xx/5xx, then stops the server. SPA routes need
`webui/frontend/dist/`.

After regenerating, update captions in
[USER_JOURNEY.md](./USER_JOURNEY.md) and [GUIDED_TOUR.md](./GUIDED_TOUR.md) if
pages changed, and refresh this registry's "Captured" dates.

### Demo GIF (`docs/demo/cli-and-api.gif`)

Honesty rule (from the render script): every output line must come from a
real capture under `docs/demo/captures/` — type-animation only; elide with a
single `…` line when trimming a contiguous block. Scene format: `$ ` lines are
typed; other lines are output blocks. `scene*.txt` are picked up in sorted
order (`scene1`…`scene4`).

```bash
# 1) Refresh raw captures (trim into scene{1,2,3,4}.txt afterward)
SWARM_TEST_MODE=1 uv run os-cli list
# prefer documented launch path (install once if needed):
#   uv run os-cli install-executable zeus
SWARM_TEST_MODE=1 uv run os-cli launch zeus --message "Plan a release: tests, changelog, tag"
# or module path still works:
# SWARM_TEST_MODE=1 uv run python -m swarm.blueprints.zeus.zeus_cli \
#     --message "Plan a release: tests, changelog, tag"
SWARM_TEST_MODE=1 DJANGO_DEBUG=true uv run python manage.py runserver 8447 --noreload &
curl -s localhost:8447/v1/models | jq -c '[.data[].id]'
curl -s localhost:8447/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"model":"zeus","stream":true,"messages":[{"role":"user","content":"Plan a release: tests, changelog, tag"}]}'
# optional scene4 — real fake-backend MoA team only (do not invent frames):
mkdir -p /tmp/moa-demo
SWARM_TEST_MODE=1 uv run os-cli moa --backend fake --team --workdir /tmp/moa-demo \
    "Should we ship the release?"

# 2) Render from scene files
uv run python scripts/render_demo_gif.py
# Requires Pillow + DejaVu Sans Mono (fonts-dejavu on Linux).
```

Then set this registry row’s Captured date and Status back to `current`.

## Convention

* The **current** capture of each page lives in `docs/screenshots/` under a
  stable kebab-case filename (matching the `PAGES` slug in the capture
  script).
* When a screenshot is **superseded** but worth keeping for history, move the
  old file to `docs/screenshots/archive/` under the **same filename** before
  regenerating, and note it here with status "archived".
* Every screenshot added to the repo gets a row in this registry.
