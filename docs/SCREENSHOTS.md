# Screenshot Registry

Master registry of every screenshot in the repository. All current captures
live in [`docs/screenshots/`](./screenshots/) and were taken from a live local
dev server by
[`scripts/capture_user_journey.py`](../scripts/capture_user_journey.py) —
headless Chromium, 1280×800 viewport (desktop) or 390×844 dpr2 (mobile),
full-page PNGs.

> **Documentation map:** [USERGUIDE.md](../USERGUIDE.md) is the `swarm-cli`
> reference, [USER_JOURNEY.md](./USER_JOURNEY.md) is the end-to-end story,
> [GUIDED_TOUR.md](./GUIDED_TOUR.md) is the visual tour, and this file is the
> capture registry.

## Current captures (`docs/screenshots/`)

| File | Page / URL | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- | --- |
| `landing.png` | `/` (React SPA dashboard) | Counts **0/45/45** from `/v1/teams`+`/v1/blueprints`+`/v1/models` (aliases + `swarm_*`; **≠** CLI 31 dirs / library 38); Quick Actions **Launch Team / Browse Blueprints / Manage Teams / Settings**; desktop top nav **Agents** + **More** (**Chat · Blueprints · Teams · Sessions · Settings**; rebuild `dist/` then recapture if dock/nav lag) | USER_JOURNEY.md, GUIDED_TOUR.md, README.md | 2026-08-19 | current |
| `spa-chat.png` | `/chat` (React SPA) | **Connected** shell after journey login (session cookie + Channels/ASGI `/ws/`); blueprint selector + empty-state prompts (“Connected and ready”). **Unavailable** Sign-in CTA is for close **4401** / no session; unreachable badge is ASGI/network — not Settings API token (not the frame in this PNG) | GUIDED_TOUR.md | 2026-08-19 | current |
| `spa-teams.png` | `/teams` → **`/teams/launch/`** | Django redirect landing (SPA no longer mounts `/teams`; ADR-001) with sticky capture **“Redirected: /teams → /teams/launch/ …”** banner; Team Launcher underneath with **`fs_introspect`** selected | GUIDED_TOUR.md | 2026-08-19 | current (redirect stem) |
| `spa-blueprints.png` | `/blueprints` → **`/blueprint-library/`** | Django redirect landing (SPA unmounted `/blueprints`; ADR-001) with sticky **“Redirected: …”** banner over Blueprint Library | GUIDED_TOUR.md | 2026-08-19 | current (redirect stem) |
| `spa-settings.png` | `/settings` → **`/settings/`** | Django redirect landing (SPA unmounted `/settings`; ADR-001) with sticky **“Redirected: …”** banner over Settings Dashboard (empty meter **No settings configured** / **0 of 0**) | GUIDED_TOUR.md | 2026-08-19 | current (redirect stem) |
| `spa-agent-creator.png` | `/agent-creator` → **`/agent-creator/`** | Django redirect landing (SPA never remounts creator; ADR-001) with sticky **“Redirected: …”** banner over Agent Creator | GUIDED_TOUR.md | 2026-08-19 | current (redirect stem) |
| `login.png` | `/accounts/login/` (Django) | Sign-in form | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `teams.png` | `/teams/` (Django) | Teams Admin registration form + table | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `teams-launch.png` | `/teams/launch/` (Django) | Team Launcher; **`fs_introspect`** selected (first dropdown option); empty output | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `blueprint-library.png` | `/blueprint-library/` (Django) | `discover_blueprints()` catalog: Available **38**, pagination **Showing 12 of 38** + Show more, MCP badges (ready green checkmarks); **≠** SPA API 45 / `swarm-cli list` 31 | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `my-blueprints.png` | `/blueprint-library/my-blueprints/` (Django) | Custom Created **3** (**Agent A** / **Agent B** / **Agent C**, Aug 18 2026) + create card; Installed **0** (host user-blueprints — not empty) | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `agent-creator.png` | `/agent-creator/` (Django) | Progressive disclosure: **1 Identity** open; **2 Optional Persona** / **3 Optional Tags** collapsed; **Generate Blueprint** / **Validate** | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `settings.png` | `/settings/` (Django) | Settings dashboard; empty meter **No settings configured** / **0 of 0** (not populated local config); category tiles + 0 LLM profiles | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |
| `sessions.png` | `/sessions/` (Django) | Session Explorer empty state: 0 sessions, live toggle, owner-scoped copy (“No sessions for your account yet… only sessions you own”) + POST /v1/responses CTA (captured before mid-run seed) | USER_JOURNEY.md, GUIDED_TOUR.md, SESSION_EXPLORER.md | 2026-08-19 | current |
| `session-detail.png` | `/sessions/resp_journey_seed/` (Django) | Session detail Graph tab: seeded `hybrid_team` fixture (`resp_journey_seed`) with orchestration/agent/auxiliary nodes — real template, synthetic JSON (**not** a live hybrid_team run) | USER_JOURNEY.md, GUIDED_TOUR.md, SESSION_EXPLORER.md | 2026-08-19 | current |
| `profiles.png` | `/profiles/` (Django) | LLM profiles table (provider/model/source/enabled; Settings → LLM profiles active) | USER_JOURNEY.md, GUIDED_TOUR.md | 2026-08-19 | current |

The "Used in" column is verified by grepping the docs for
`screenshots/<file>`. USERGUIDE.md embeds no PNG files (CLI reference only)
but points readers at this tour.

## Mobile captures (`docs/screenshots/mobile/`)

Same stems as desktop with `--mobile` (iPhone-14-class: 390×844, dpr 2, touch).

**Parked-dock capture artifact:** `capture_user_journey.py` sets visible fixed
bottom bars (Django `.os-bottom-nav`, SPA `nav.fixed.bottom-0`) to
`position:static` before `full_page=True` so Chromium stitch does not paint the
dock over mid-page content. Live UI keeps those docks **viewport-fixed**;
checked-in mobile PNGs therefore show the tab bar **after scrolled page
content** (end of the PNG), not floating over the viewport. Captions that name
“dock / 5-tab bar” mean that parked strip.

**Bottom nav honesty (as of these PNGs):**

* **SPA** shell (`mobile/landing.png`, `mobile/spa-chat.png`) live dock is
  **Agents** + **More** (**Chat · Blueprints · Teams · Sessions · Settings**
  under More; logo is home). Checked-in PNGs may still show the older four-tab
  dock until recapture. Rebuild `dist/` after pull so `/` serves the current shell.
* **Django** operator pages keep **Agents** + **More** (same destinations;
  logo is home). Checked-in mobile PNGs may still show the older five-tab bar.
* Bare `/teams` `/blueprints` `/settings` `/agent-creator` **redirect** to
  Django; `spa-*` stems are redirect captures (not live SPA pages).
* Desktop and mobile `spa-chat.png` both show the **Connected** composer after
  the journey script logs in as `journey-admin` (blueprint selector + empty-state
  prompts). Capture waits for Connected/Unavailable/Disconnected before
  shooting. When the websocket fails (4401 / ASGI down), ChatPage also renders
  a shrink-safe **Sign in** / **Reconnect** alert (unit-tested; not these PNGs).

| File | Page / URL | Mobile-specific notes | Captured | Status |
| --- | --- | --- | --- | --- |
| `mobile/landing.png` | `/` | Stat cards stack (**0/45/45**, same API bridge as desktop landing); Quick Actions **Launch Team / Browse Blueprints / Manage Teams / Settings**; SPA dock Chat · Blueprints · Teams · Sessions (Home/Chat are SPA; rest Django hrefs — ADR-001); dock **parked** at end of full-page PNG. Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/spa-chat.png` | `/chat` | **Connected** + blueprint selector + empty-state prompts; SPA dock with **Chat** active (**parked** at PNG end). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/spa-teams.png` | `/teams` → **`/teams/launch/`** | Redirect landing with sticky **“Redirected: …”** banner; Team Launcher (`fs_introspect` selected); Django **5-tab** bar (Teams active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/spa-blueprints.png` | `/blueprints` → **`/blueprint-library/`** | Redirect landing with sticky **“Redirected: …”** banner; single-column cards; Django **5-tab** (Blueprints active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/spa-settings.png` | `/settings` → **`/settings/`** | Redirect landing with sticky **“Redirected: …”** banner; Settings empty meter **0 of 0**; Django **5-tab** (Settings active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/spa-agent-creator.png` | `/agent-creator` → **`/agent-creator/`** | Redirect landing with sticky **“Redirected: …”** banner; Agent Creator; Django **5-tab** (Blueprints active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/login.png` | `/accounts/login/` | Full-width login card (no bottom primary bar). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/teams.png` | `/teams/` | Django **5-tab** bar (Teams active); form wraps. Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/teams-launch.png` | `/teams/launch/` | Launcher full-width; **`fs_introspect`** selected (first dropdown option); Django **5-tab** (Teams active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/blueprint-library.png` | `/blueprint-library/` | Paginated cards stack (**12 of 38** discoverable); Django **5-tab** (Blueprints active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/my-blueprints.png` | `/blueprint-library/my-blueprints/` | Custom Created **3** stack (**Agent A** / **B** / **C**) + create CTA; Django **5-tab** (Blueprints active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/agent-creator.png` | `/agent-creator/` | **1 Identity** accordion; **Generate Blueprint** / **Validate**; Django **5-tab** (Blueprints active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/settings.png` | `/settings/` | Empty meter **No settings configured** / **0 of 0**; tiles wrap; Django **5-tab** (Settings active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/sessions.png` | `/sessions/` | Empty state (0 sessions + live toggle + owner-scoped empty copy); Django **5-tab** (Sessions active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/session-detail.png` | `/sessions/resp_journey_seed/` | Seeded `hybrid_team` fixture Graph tab (same honesty as desktop — not a live run); Django **5-tab** (Sessions active). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |
| `mobile/profiles.png` | `/profiles/` | Profiles table; Django **5-tab** (Settings active — profiles nest under Settings). Embedded in GUIDED_TOUR.md | 2026-08-19 | current |

Regenerate with:

```bash
.venv/bin/python scripts/capture_user_journey.py --mobile
```

## Announce / README media (`docs/assets/readme/`)

Decided path for README heroes and the #456 kit. SoT:
[docs/ANNOUNCE.md](./ANNOUNCE.md), [docs/assets/readme/README.md](./assets/readme/README.md).

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `assets/readme/announce-bridge.gif` | REQ-136 / #529 hero (~18s storyboard): Grok-agnostic UI + CLI/API/remote bridge. Spiel captions. Roster: Hermes Remote, OpenMousBot Remote, Antigravity CLI, OpenCode CLI, BA→Engineer→Tester | README.md, ANNOUNCE.md | 2026-09-06 | storyboard (live recapture later) |

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
| `assets/readme/cli-agents.svg` | Poster: Grok-like rail + **Grok CLI** chat (opencode / agy rows) | README.md | 2026-09-06 | poster (GIF pending) |
| `assets/readme/api-agents.svg` | Poster: **LiteLLM API** owned thread / OpenAI-compat door | README.md | 2026-09-06 | poster (GIF pending) |
| `assets/readme/remote-agents.svg` | Poster: **OpenMousBot** remote (Hermes / Rakazo rows) | README.md | 2026-09-06 | poster (GIF pending) |
| `assets/readme/combined-team.svg` | Poster: **Demo Bridge** — CLI + API + remote handoff | README.md | 2026-09-06 | poster (GIF pending) |

Reserved live-GIF names `cli.gif` / `api.gif` / `remotes.gif` / `combined.gif`
are still the #456 contract for filmed loops and are not checked in yet.

## Demo animations (`docs/demo/`)

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `demo/cli-agent.gif` | CLI agent: host executable discovery & native session launch (`grok-cli`) | README.md | 2026-09-06 | current |
| `demo/api-agent.gif` | API agent: OpenAI-compatible `/v1/models` and streaming completions (`litellm-api`) | README.md | 2026-09-06 | current |
| `demo/remote-agent.gif` | Remote agent: external harness catalog & bridge dispatch (**OpenMousBot**, Hermes) | README.md | 2026-09-06 | current |
| `demo/combined-team.gif` | Combined team: unified flow coordinating CLI + API + Remote via handoff (`demo-bridge`) | README.md | 2026-09-06 | current |
| `demo/cli-and-api.gif` | Historical animated terminal loop (~25s loop): `swarm-cli list`, `launch zeus`, curl `/v1/*`, optional `moa --team` (fake) | README.md | 2026-08-18 | historical |

Four scenes from real `SWARM_TEST_MODE` / curl / `--backend fake` captures under
`docs/demo/captures/` (see `raw_*.txt`). Scene 2 uses documented
`swarm-cli launch zeus` (after `install-executable zeus`). Scene 4 is
`swarm-cli moa --backend fake --team --workdir /tmp/moa-demo`.

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
| `skills/01-skills-list.png` | `swarm-cli skills` listing (name, assets, description) | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
| `skills/02-skills-show.png` | `swarm-cli skills --show` full `SKILL.md` dump | SKILLS_AND_CONSENSUS_WALKTHROUGH.md | mixed | current |
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
SWARM_TEST_MODE=1 uv run swarm-cli list
# prefer documented launch path (install once if needed):
#   uv run swarm-cli install-executable zeus
SWARM_TEST_MODE=1 uv run swarm-cli launch zeus --message "Plan a release: tests, changelog, tag"
# or module path still works:
# SWARM_TEST_MODE=1 uv run python -m swarm.blueprints.zeus.zeus_cli \
#     --message "Plan a release: tests, changelog, tag"
SWARM_TEST_MODE=1 DJANGO_DEBUG=true uv run python manage.py runserver 8447 --noreload &
curl -s localhost:8447/v1/models | jq -c '[.data[].id]'
curl -s localhost:8447/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"model":"zeus","stream":true,"messages":[{"role":"user","content":"Plan a release: tests, changelog, tag"}]}'
# optional scene4 — real fake-backend MoA team only (do not invent frames):
mkdir -p /tmp/moa-demo
SWARM_TEST_MODE=1 uv run swarm-cli moa --backend fake --team --workdir /tmp/moa-demo \
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
