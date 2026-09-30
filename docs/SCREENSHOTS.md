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
| `#1311-mine-presets.png` | `/__proof__/library-1311?step=mine` | #1311 Blueprints pane on Mine: personal-library copy and Add Support/Researcher/Reviewer to rail | none | 2026-09-27 | registry-only |
| `#1311-team-publish.png` | `/__proof__/library-1311?step=team` | #1311 Team scope with the Engineering roster selected and Publish enabled | none | 2026-09-27 | registry-only |
| `#1311-preset-on-rail.png` | `/__proof__/library-1311?step=preset` | #1311 “Support is on the rail.” after Add Support to rail | none | 2026-09-27 | registry-only |
| `#1311-import-missing.png` | `/__proof__/library-1311?step=import` | #1311 Organisation import notice listing missing blueprint, MCP server, and skill | none | 2026-09-27 | registry-only |
| `#1445-chat-anythingllm-header.png` | `/chat?remote=anythingllm` | #1445 chat header on a valid AnythingLLM seat; path stamped in-frame | none | 2026-09-27 | registry-only |
| `#1445-settings-deeplink-header-cleared.png` | `/chat?remote=anythingllm&settings=true` | #1445 Settings deep link clears the AnythingLLM header; chat stays mounted | none | 2026-09-27 | registry-only |
| `#1445-settings-closed-header-restored.png` | `/chat?remote=anythingllm` (Settings closed) | #1445 closing Settings restores the AnythingLLM header | none | 2026-09-27 | registry-only |
| `#1445-agents-no-chat-header.png` | `/agents` | #1445 Agent Router has its own header and no chat navbar | none | 2026-09-27 | registry-only |
| `#1447-computer-routines-no-agent-tab.png` | `/__proof__/ia-1447?surface=computer` | #1447 live ChatHeader + Computer Control — Routines + Test schedule only; Agent tab gone | none | 2026-09-27 | registry-only |
| `#1447-avatar-agent-config-sidepane.png` | `/__proof__/ia-1447?surface=config` | #1447 live ChatHeader avatar opens AgentConfigSidepane (pencil stays the full editor) | none | 2026-09-27 | registry-only |
| `reactions-1411-dark-turn.png` | `/__proof__/reactions-1411?theme=dark&view=turn` | #1411 reaction-only thumbs-up visible at rest on a dark chat bubble | none | 2026-09-27 | registry-only |
| `reactions-1411-light-turn.png` | `/__proof__/reactions-1411?theme=light&view=turn` | #1411 same reaction-only turn with light `--os-reaction-*` tokens | none | 2026-09-27 | registry-only |
| `reactions-1411-dark-hydrated.png` | `/__proof__/reactions-1411?theme=dark&view=hydrated` | #1411 reaction-only turn still visible after thread reload | none | 2026-09-27 | registry-only |
| `reactions-1411-dark-picker.png` | `/__proof__/reactions-1411?theme=dark&view=picker&palette=speech` | #1411 speech palette picker open | none | 2026-09-27 | registry-only |
| `reactions-1411-light-picker.png` | `/__proof__/reactions-1411?theme=light&view=picker&palette=speech` | #1411 speech palette picker in light theme | none | 2026-09-27 | registry-only |
| `reactions-1411-dark-irc-picker.png` | `/__proof__/reactions-1411?theme=dark&view=picker&palette=irc` | #1411 IRC palette omits speech-only emoji | none | 2026-09-27 | registry-only |
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
| `#1402-issue-comment.png` | `/chat?blueprint=codey#1402-issue-comment` | GitHub trigger chips: Comment / Anyone / Issue / acme/widgets | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1402-issue-assigned.png` | `/chat?blueprint=codey#1402-issue-assigned` | GitHub trigger chips: Assigned / Specific user mona / Issue / acme/widgets | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1402-pr-comment.png` | `/chat?blueprint=codey#1402-pr-comment` | GitHub trigger chips: Comment / Anyone / Pull request / acme/widgets | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1402-missing-repo.png` | `/chat?blueprint=codey#1402-missing-repo` | GitHub event chips with empty repo; Save blocked | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1395/1395-list-pending-fill-vs-enabled.png` | `/__proof__/routines-1395` | #1395 routines list: Pending fill vs Enabled vs Paused | none | 2026-09-27 | registry-only |
| `1395/1395-export-fill-in-preview.png` | `/__proof__/routines-1395` | #1395 export select with required fill-in preview (Channel, GitHub owner/repo) | none | 2026-09-27 | registry-only |
| `1395/1395-enable-incomplete-error.png` | `/__proof__/routines-1395` | #1395 fill-then-enable blocked with a clear incomplete error | none | 2026-09-27 | registry-only |
| `1395/1395-enabled-after-fill.png` | `/__proof__/routines-1395` | #1395 list after fill-then-enable: imported row Enabled, leftover row still Pending fill | none | 2026-09-27 | registry-only |
| `1391-agent-memory-panel.png` | `/chat?blueprint=codey` | #1391 Edit agent Memory tab — All/Pack/Local filters, pack vs local rows, add/remove conventions | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1391-memory-export-wizard.png` | `/chat?blueprint=codey` | #1391 template export preview — included 2 / excluded 2, episode skipped, note skipped | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1403-dialog-issue-default-on.png` | `/__proof__/routines-1403?surface=dialog&state=issue-on` | #1403 RoutineEditorDialog Tools checkbox — Open Pull Request default-ON for `issues.opened` | none | 2026-09-27 | registry-only |
| `#1403-dialog-interval-default-off.png` | `/__proof__/routines-1403?surface=dialog&state=interval-off` | #1403 RoutineEditorDialog Tools checkbox — Open Pull Request default-OFF for interval | none | 2026-09-27 | registry-only |
| `#1403-pane-issue-default-on.png` | `/__proof__/routines-1403?surface=pane&state=issue-on` | #1403 ComputerRoutinesPane Tools checkbox — Open Pull Request default-ON for `issues.opened` | none | 2026-09-27 | registry-only |
| `#1403-pane-removed-persists.png` | `/__proof__/routines-1403?surface=pane&state=removed` | #1403 ComputerRoutinesPane Tools checkbox — Open Pull Request removed and persisted | none | 2026-09-27 | registry-only |
| `#1406-dialog-picker.png` | `/__proof__/routines-1406?surface=dialog&state=picker` | #1406 RoutineEditorDialog — + Add Tool or MCP picker of catalog tools | none | 2026-09-27 | registry-only |
| `#1406-dialog-added-remove.png` | `/__proof__/routines-1406?surface=dialog&state=added` | #1406 RoutineEditorDialog — extra tools added with Remove | none | 2026-09-27 | registry-only |
| `#1406-pane-added-remove.png` | `/__proof__/routines-1406?surface=pane&state=pane-added` | #1406 ComputerRoutinesPane — extra tools added with Remove | none | 2026-09-27 | registry-only |
| `#1406-dialog-disabled-reason.png` | `/__proof__/routines-1406?surface=dialog&state=disabled` | #1406 picker — Brave Search disabled with BRAVE_API_KEY reason | none | 2026-09-27 | registry-only |
| `#1410-dialog-pr-suggest.png` | `/__proof__/routines-1410?surface=dialog&state=pr` | #1410 RoutineEditorDialog — instructions mention a PR, suggest Open Pull Request | none | 2026-09-27 | registry-only |
| `#1410-dialog-memory-suggest.png` | `/__proof__/routines-1410?surface=dialog&state=memory` | #1410 RoutineEditorDialog — instructions mention MEMORIES, suggest Memories | none | 2026-09-27 | registry-only |
| `#1410-dialog-present-quiet.png` | `/__proof__/routines-1410?surface=dialog&state=present` | #1410 RoutineEditorDialog — Open PR already present, no nag | none | 2026-09-27 | registry-only |
| `#1410-dialog-dismissed.png` | `/__proof__/routines-1410?surface=dialog&state=dismissed` | #1410 RoutineEditorDialog — Open PR suggestion dismissed for this draft | none | 2026-09-27 | registry-only |
| `#1410-pane-pr-suggest.png` | `/__proof__/routines-1410?surface=pane&state=pane-pr` | #1410 ComputerRoutinesPane — instructions mention a PR, suggest Open Pull Request | none | 2026-09-27 | registry-only |
| `req1397-plugins-pack/1-pack-status-enabled-missing.png` | `/chat` Plugins popup Pack tab (#1397) | Plugin-id status: enabled + missing; path banner in-frame; no tokens | none | 2026-09-27 | registry-only |
| `req1397-plugins-pack/2-pack-import-ids.png` | `/chat` Plugins popup Pack tab (#1397) | Import pack textarea with plugin ids only; path banner in-frame | none | 2026-09-27 | registry-only |
| `req1397-plugins-pack/3-settings-plugin-pack.png` | Settings → Plugins (#1397) | Same pack/import/status pane on the current agent; no tokens | none | 2026-09-27 | registry-only |
| `req1399-templates/1-gallery.png` | `/chat` Templates overlay (#1399) | Gallery cards + Storefront Bee detail | none | 2026-09-27 | registry-only |
| `req1399-templates/2-installer.png` | `/chat` Templates overlay (#1399) | Validate + install onto seat | none | 2026-09-27 | registry-only |
| `req1399-templates/3-validation.png` | `/chat` Templates overlay (#1399) | Secret-free validation status | none | 2026-09-27 | registry-only |
| `1393/#1393-skills-editor.png` | `/chat?blueprint=codey#1393-skills-editor` | #1393 skills editor: list/create, **When to use** description | none | 2026-09-27 | registry-only |
| `1393/#1393-pack-picker-invalid.png` | `/chat?blueprint=codey#1393-pack-picker-invalid` | #1393 export multi-select + gettingStarted picker; Export disabled when gettingStarted is not chosen | none | 2026-09-27 | registry-only |
| `1393/#1393-first-chat-getting-started.png` | `/chat?blueprint=codey#1393-first-chat` | #1393 first empty chat after import: getting-started skill + when-to-use chip | none | 2026-09-27 | registry-only |

The "Used in" column is verified by grepping the docs for
`screenshots/<file>`. USERGUIDE.md embeds no PNG files (CLI reference only)
but points readers at this tour.

## Visual-proof captures (per-REQ folders, `docs/screenshots/`)

PR visual evidence saved next to the QA page it proves. Not embedded in any
doc — each is **registry-only** by design; the PR description referenced it
at merge time.

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `#1445-chat-anythingllm-header.png` | #1445 AnythingLLM header on `/chat?remote=anythingllm` | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1445-settings-deeplink-header-cleared.png` | #1445 `/chat?settings=true` clears the AnythingLLM header | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1445-settings-closed-header-restored.png` | #1445 closing Settings restores the AnythingLLM header | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1445-agents-no-chat-header.png` | #1445 `/agents` has no chat header | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1447-computer-routines-no-agent-tab.png` | #1447 live ChatHeader + Computer Control — Routines + Test schedule only; no Agent tab | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1447-avatar-agent-config-sidepane.png` | #1447 live ChatHeader avatar opens AgentConfigSidepane | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `req508-teams-composer/1-essentials.png` | REQ-508 Teams composer — Essentials tab | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/2-roles-pane.png` | REQ-508 Teams composer — Roles pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/3-tools-pane.png` | REQ-508 Teams composer — Tools pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/4-catalog-pane.png` | REQ-508 Teams composer — Catalog pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req508-teams-composer/5-back-to-essentials.png` | REQ-508 Teams composer — back to Essentials (pane toggle round-trip) | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/1-rail.png` | REQ-910 — rail with Plugins entry | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/2-plugins-chat-pane.png` | REQ-910 Plugins popup — chat (agent) pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/3-plugins-tools-pane.png` | REQ-910 Plugins popup — Add tools pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `req910-plugins/4-plugins-skills-pane.png` | REQ-910 Plugins popup — Add skills pane | none (registry-only visual proof) | 2026-09 | registry-only |
| `#1402-issue-comment.png` | `/chat?blueprint=codey#1402-issue-comment` — GitHub trigger chips: Comment / Anyone / Issue / acme/widgets | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1402-issue-assigned.png` | `/chat?blueprint=codey#1402-issue-assigned` — GitHub trigger chips: Assigned / Specific user mona / Issue / acme/widgets | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1402-pr-comment.png` | `/chat?blueprint=codey#1402-pr-comment` — GitHub trigger chips: Comment / Anyone / Pull request / acme/widgets | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1402-missing-repo.png` | `/chat?blueprint=codey#1402-missing-repo` — GitHub event chips with empty repo; Save blocked | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1395/1395-list-pending-fill-vs-enabled.png` | #1395 routines list — Pending fill vs Enabled vs Paused | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1395/1395-export-fill-in-preview.png` | #1395 export select — required fill-in preview (Channel, GitHub owner/repo) | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1395/1395-enable-incomplete-error.png` | #1395 fill-then-enable — clear error when required slots are incomplete | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1395/1395-enabled-after-fill.png` | #1395 list after a complete fill — imported row Enabled, pending-fill row unchanged | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1391-agent-memory-panel.png` | #1391 Agent Memory panel at `/chat?blueprint=codey` — Memory tab, All/Pack/Local filters, pack vs local list, add/remove conventions | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1391-memory-export-wizard.png` | #1391 Memory export wizard at `/chat?blueprint=codey` — included 2 / excluded 2, episode skipped, note skipped | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1395/1395-export-select.png` | #1395 routines pack — export multi-select on `/chat?blueprint=codey` | none (registry-only visual proof) | 2026-09 | registry-only |
| `1395/1395-import-fill-ins.png` | #1395 routines pack — post-import fill-ins (pending enable) | none (registry-only visual proof) | 2026-09 | registry-only |
| `#1403-dialog-issue-default-on.png` | #1403 dialog — Open PR default-ON (issue trigger) | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1403-dialog-interval-default-off.png` | #1403 dialog — Open PR default-OFF (interval) | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1403-pane-issue-default-on.png` | #1403 computer pane — Open PR default-ON (issue trigger) | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1403-pane-removed-persists.png` | #1403 computer pane — Open PR removed persists | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `req1405-routine-builder/#1405-armed-inactive.png` | #1405 builder — Inactive/Active (armed) toggle, unique `/chat?os-proof=1405-armed-inactive` chrome | none (registry-only visual proof) | 2026-09 | registry-only |
| `req1405-routine-builder/#1405-save-draft.png` | #1405 builder — Save draft while Inactive, unique `/chat?os-proof=1405-save-draft` chrome | none (registry-only visual proof) | 2026-09 | registry-only |
| `req1405-routine-builder/#1405-test-dry-run.png` | #1405 builder — Test dry-run preview (no live send), unique `/chat?os-proof=1405-test-dry-run` chrome | none (registry-only visual proof) | 2026-09 | registry-only |
| `req1405-routine-builder/#1405-model-picker.png` | #1405 builder — model picker next to Agent Instructions, unique `/chat?os-proof=1405-model-picker` chrome | none (registry-only visual proof) | 2026-09 | registry-only |
| `1389-profile/1389-identity-edit.png` | #1389 Edit-agent Identity tab — name, description, title, avatar shape/color | none (registry-only visual proof) | 2026-09 | registry-only |
| `1389-profile/1389-rail-profile.png` | #1389 left rail after profile save (no reload) | none (registry-only visual proof) | 2026-09 | registry-only |
| `1389-profile/1389-header-profile.png` | #1389 chat header name + title after profile save | none (registry-only visual proof) | 2026-09 | registry-only |
| `1389-profile/1389-pack-preview.png` | #1389 Identity export/import `pack.profile` preview | none (registry-only visual proof) | 2026-09 | registry-only |
| `#1406-dialog-picker.png` | #1406 dialog — + Add Tool or MCP picker | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1406-dialog-added-remove.png` | #1406 dialog — extra tools added + Remove | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1406-pane-added-remove.png` | #1406 computer pane — extra tools added + Remove | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1406-dialog-disabled-reason.png` | #1406 picker — disabled Brave Search reason | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1410-dialog-pr-suggest.png` | #1410 dialog — mention PR suggests Open Pull Request | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1410-dialog-memory-suggest.png` | #1410 dialog — mention MEMORIES suggests Memories | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1410-dialog-present-quiet.png` | #1410 dialog — tool already present, no nag | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1410-dialog-dismissed.png` | #1410 dialog — dismissed suggestion stays gone | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `#1410-pane-pr-suggest.png` | #1410 computer pane — mention PR suggests Open Pull Request | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `issue-1324/1-before-switch.png` | #1324 proof harness `/__proof__/engine-switch-1324` — path-in-frame, current engine grok, switch armed | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `issue-1324/2-warning-before-apply.png` | #1324 picker warning names session list; engine still grok until acknowledgment | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `issue-1324/2-toast-names-loss.png` | #1324 Engine switch toast after Switch anyway; current engine is claude (switch not blocked) | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `req1397-plugins-pack/1-pack-status-enabled-missing.png` | #1397 Pack tab — enabled/missing status, path in-frame | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `req1397-plugins-pack/2-pack-import-ids.png` | #1397 Pack tab — import plugin ids, path in-frame | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `req1397-plugins-pack/3-settings-plugin-pack.png` | #1397 Settings Plugins pack pane, path in-frame | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `req1399-templates/1-gallery.png` | #1399 template gallery overlay | none (registry-only visual proof) | 2026-09 | registry-only |
| `req1399-templates/2-installer.png` | #1399 template installer onto a seat | none (registry-only visual proof) | 2026-09 | registry-only |
| `req1399-templates/3-validation.png` | #1399 validate secret-free pack | none (registry-only visual proof) | 2026-09 | registry-only |
| `1393/#1393-skills-editor.png` | #1393 agent editor skills list/create; description labeled When to use | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1393/#1393-pack-picker-invalid.png` | #1393 pack export picker; Export disabled until gettingStarted names a selected skill | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1393/#1393-first-chat-getting-started.png` | #1393 first chat surfaces getting-started skill + when-to-use chip | none (registry-only visual proof) | 2026-09-27 | registry-only |
| `1674/#1674-add-bot-menu-open-dark.png` | `/__proof__/add-bot-1674` | #1674 rail Add-bot menu open — the Add-agent control is now a searchable menu of seats and groups, not a bare wizard button | none (registry-only visual proof) | 2026-09-28 | registry-only |
| `1676/#1676-agent-pill-centered-dark.png` | `/__proof__/agent-pill-1676` | #1676 foreground agent's avatar + name ride a centered floating pill under the header band; the rail toggle keeps the left lead slot | none (registry-only visual proof) | 2026-09-28 | registry-only |
| `1676/#1676-agent-pill-edit-pane-dark.png` | `/__proof__/agent-pill-1676?pane=edit` | #1676 one right-side edit-agent pane opened from the pill surface | none (registry-only visual proof) | 2026-09-28 | registry-only |
| `1697/#1697-agent-selector-sidepane-dark.png` | `/__proof__/agent-selector-1697` | #1697 agent selector sidepane (dark) | none (registry-only visual proof) | 2026-09-28 | registry-only |
| `1697/#1697-agent-selector-sidepane-light.png` | `/__proof__/agent-selector-1697` | #1697 agent selector sidepane (light twin) | none (registry-only visual proof) | 2026-09-28 | registry-only |
| `1704/#1704-before-folder-text-row-dark.png` | `/__proof__/folder-pill-1704?theme=dark&folder=unset` (pre-fix bundle) | #1704 BEFORE — "Select folder" is a text row inside the stacked label column: 3 label rows, pill 61.83px | none (registry-only visual proof) | 2026-09-29 | registry-only |
| `1704/#1704-after-folder-icon-revealed-dark.png` | `/__proof__/folder-pill-1704?theme=dark&folder=unset` | #1704 AFTER, hover — folder icon right-aligned beside the pencil, one row: 2 label rows, pill 49.19px | none (registry-only visual proof) | 2026-09-29 | registry-only |
| `1704/#1704-after-folder-icon-at-rest-dark.png` | `/__proof__/folder-pill-1704?theme=dark&folder=unset` (no hover) | #1704 AFTER at rest — same 49.19px pill; the reveal is opacity, so hovering costs no height | none (registry-only visual proof) | 2026-09-29 | registry-only |
| `1704/#1704-after-folder-bound-dark.png` | `/__proof__/folder-pill-1704?theme=dark&folder=bound` | #1704 control — a bound folder is the path as the bottom label and the unset icon is gone, so the two never stack | none (registry-only visual proof) | 2026-09-29 | registry-only |

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

## UI fix proof stills — issue dogfood (unembedded)

Acceptance captures taken by the per-issue capture harnesses under
`webui/frontend/scripts/` (`capture_*.mjs`, `shot-*.mjs`) and by
`scripts/capture_1709_add_chat_select.mjs`. They are measurement evidence for
one issue at one commit, not documentation of a current page, so every row below
is registry-only: nothing embeds them, and this table is their only index.

| File | What it shows | Used in | Captured | Status |
| --- | --- | --- | --- | --- |
| `#1703-host-cli-tip-dark.png` | #1703 host-CLI-detected tip at the top of chat, dark | none (registry-only) | 2026-09-28 | registry-only |
| `#1703-host-cli-tip-light.png` | #1703 host-CLI-detected tip, light twin | none (registry-only) | 2026-09-28 | registry-only |
| `1709/#1709-after-new-chat-selected-dark.png` | #1709 rail after Add chat, new conversation selected | none (registry-only) | 2026-09-28 | registry-only |
| `1709/#1709-before-prior-selection-dark.png` | #1709 rail before Add chat, prior selection still active | none (registry-only) | 2026-09-28 | registry-only |
| `1711/#1711-after-collapse-with-search-plus-dark.png` | #1711 one-column rail header: Search, collapse and + on one band | none (registry-only) | 2026-09-28 | registry-only |
| `1711/#1711-before-collapse-under-plus-dark.png` | #1711 one-column rail header before the fix: collapse orphaned under + | none (registry-only) | 2026-09-28 | registry-only |
| `1717-organic-blobs.png` | #1717 organic blob/circle/pill silhouettes across avatar states | none (registry-only) | 2026-09-28 | registry-only |
| `dogfood-1715/bound-multiline-dark.png` | #1715 floating badge label, bounded to two lines | none (registry-only) | 2026-09-28 | registry-only |
| `dogfood-1715/unset-single-label-dark.png` | #1715 unset-role single label, vertically centred in the pill | none (registry-only) | 2026-09-28 | registry-only |

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
