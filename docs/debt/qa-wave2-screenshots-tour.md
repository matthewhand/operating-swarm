# QA wave 2 — screenshot / tour lock plan (look-only)

**Status:** look-only recapture plan. No PNG binaries. No product, test,
workflow, golden-journey, or existing `docs/debt/*.md` edits in this
change.

**Starting leftover notes:** `docs/debt/qa-wave1-tests-ci.md` on
`cursor/look-only-debt-qa-wave1-tests-ci-fde4` (`#426`). Scope here is
the wave-1 **must-fix leftover** that is still a stale tour lock:
**D-01** (tour PNGs vs Grok rail), **D-02** (settings caption vs
pixels), **D-14** (screenshot registry lockfile). **D-03** is recorded
only (Playwright e2e exists; no workflow runs it).

**Today’s tree:** `dfd72eef` (`main` after `#428`).

**Method:** static re-read of `docs/SCREENSHOTS.md`,
`docs/GUIDED_TOUR.md`, `docs/USER_JOURNEY.md`,
`tests/unit/test_screenshot_registry.py` (619 lines),
`scripts/capture_user_journey.py` `PAGES`, `webui/frontend/src/App.tsx`,
`ChatPage.tsx`, `SettingsSheet.tsx`, `src/swarm/templates/base.html`,
`webui/frontend/e2e/*.spec.ts`, and
`.github/workflows/{python-pytest,visual-regression}.yml`. Visual
inspect of the checked-in 2026-08-19 PNGs (desktop + mobile
`landing` / `spa-chat` / `settings` / `spa-settings` / `teams` /
`blueprint-library` / `login`). No recapture. No host bounce. No
`:8001`. No Neon. No secrets. No live LAN URLs.

This file does **not** recapture goldens, rewrite captions, move
registry tests, add a Playwright CI workflow, rebase, squash, or fold
into `#344` / `#431`.

---

## How to read the ranks

| Bucket | Meaning |
| --- | --- |
| **must-fix** | Still true on today’s tree; tour pixels or caption locks still describe a chrome the product no longer ships. Fix in **one later ticket** (PNGs + captions + registry tests together). Not this PR. |
| **nice** | Still true; same later ticket *may* pick it up if the journey script already visits the stem. Do not block the honesty ticket on these. |
| **obsolete** | The leftover *claim* no longer matches today’s files, or the suggested follow-up (recapture REQ-5 Home cards; delete caption locks first) is the wrong action. |
| **intentional** | Leave alone. Historical / orphan / HOLD / still-true chrome lock. |

Kind tags: **stale lock** (asserts a chrome the product no longer
ships), **caption vs pixels** (docs and PNG contradict each other),
**missing coverage** (suite exists but never runs where it matters).

---

## The one later ticket (do not split)

An honest recapture is **one** ticket that lands together:

1. Retake the listed stems (desktop + mobile) with
   `scripts/capture_user_journey.py` against **today’s** Grok rail +
   current Django operator chrome — not REQ-5 Home cards.
2. Rewrite captions in `GUIDED_TOUR.md`, `USER_JOURNEY.md`,
   `SCREENSHOTS.md` (and the leftover **Connected** lines in
   `FEATURE_STATUS.md` / `docs/websocket_chat.md` / `README.md` alt
   text) to match the **new** pixels.
3. Move the registry string-locks in
   `tests/unit/test_screenshot_registry.py` in the **same** commit
   series so CI does not go red mid-flight and so docs cannot keep
   claiming 2026-08-19 chrome.
4. Update capture-script waits / `PAGES` comments that still hardclaim
   a visible **Connected** pill or a Dashboard `/`.

Do **not** delete the caption locks first and leave the PNGs (that is
the `#431` split on `test_tour_captions_include_spa_desktop_chat_nav`
and `test_spa_chat_checked_in_caption_hardclaims_connected_badge`).
Do **not** rewrite captions onto the old PNGs. Do **not** check in new
PNGs with the old lockfile still requiring `Home · Chat · Blueprints`,
`**Connected**`, `0 of 0`, or `2026-08-19`.

**Out of that ticket:** adding `npm run test:e2e` to a workflow
(D-03). Rewriting `tests/e2e_visual` / `visual-regression.yml`
(wave-1 HOLD). Weakening still-true remotes / **OMB** / row-fill
chrome tests (see [Still-true chrome tests](#still-true-chrome-tests-do-not-weaken)).

---

## Pixel facts (checked-in 2026-08-19 frames)

Inspected on disk. Registry marks every row **current**.

| Stem | On-disk pixels | Product today |
| --- | --- | --- |
| `landing.png` (1280×998) | SPA **Dashboard** catalog: 0 / 45 / 45, rainbow Quick Actions (Launch Team / Browse Blueprints / Manage Teams / Settings), desktop top nav **Home · Chat · Blueprints · Teams · Sessions · Settings** | `/` is `ChatPage` + Grok left rail (`App.tsx`). `chrome.spec.ts` forbids `Primary` nav and `/^Home$/` / `/^Chat$/` links. `Dashboard` is not mounted. |
| `mobile/landing.png` | Same catalog; SPA five-tab dock **Home · Chat · Blueprints · Teams · Sessions** (Home active), parked at PNG end | SPA has no `MobileTab` / `nav.fixed.bottom-0` (`App.tsx`). `FEATURE_STATUS.md` already says **no mobile five-tab dock**. |
| `spa-chat.png` (1280×800) | Top nav + visible **Connected** pill + “Connected and ready” empty-state + blueprint selector. **No** left rail. | Grok rail + agent name header + Compact composer. Connection status is `sr-only`. Healthy `status === 'open'` sets `statusLabel` to `''` (`ChatPage.tsx`). `chrome.spec.ts` asserts `getByText(/^Connected$/)` count **0**. |
| `mobile/spa-chat.png` | Same Connected composer; dock **Chat** active | Same: no dock, no standing Connected. |
| `settings.png` (1280×2846, 331050 bytes) | Django Settings Dashboard: **36** total / **30** configured / **83%** complete; Django Framework expanded; `DEBUG=True`. Nav is **Home · Blueprints▾ · Teams · Sessions · Settings▾ · More** (no Chat, no Agents pane). | Captions + `test_settings_caption_matches_empty_meter_not_populated_local_config` require **No settings configured** / **0 of 0**. Django chrome today is Home · **Chat** · Blueprints · Teams · Sessions · Settings **plus** `#os-agent-sidebar` (`base.html`). SPA Settings is a DaisyUI `modal-end` sheet (`SettingsSheet.tsx`), not this page. |
| `spa-settings.png` | Same populated **36 / 30 / 83%** meter under a sticky **Redirected: /settings → /settings/** banner | Registry / tour claim empty meter **0 of 0** under that banner. |
| `teams.png` / `blueprint-library.png` | Django dropdown chrome, **no Chat**, **no Agents** pane. Library shows Available **38**, **Showing 12 of 38**, MCP: OK. | `base.html` primary IA is Home · Chat · Blueprints · Teams · Sessions · Settings (no Blueprints/Settings dropdowns) + Agents aside. |

`login.png` is a chrome-less Sign-in card (no primary nav). Skills /
`webui/` / `archive/` stills are not journey goldens.

---

## Stems to retake

`PAGES` in `scripts/capture_user_journey.py` is 16 stems × desktop +
mobile = **32** journey PNGs. Recapture **today’s** chrome. Do not
aim at REQ-5 large Home cards.

### Must-fix retakes (D-01 / D-02)

| Stem | Why retake | After recapture, captions must say |
| --- | --- | --- |
| `landing` + `mobile/landing` | `/` is Chat + Grok rail, not a Dashboard catalog. PNG still sells rainbow Quick Actions + six-link top nav. `README.md` embeds `landing.png` as “Operating Swarm dashboard”. | Left rail (`aria-label="Agent list"`) + selected-agent chat. No Home catalog. No top-nav phrase. No five-tab dock. |
| `spa-chat` + `mobile/spa-chat` | Visible **Connected** pill + top nav + no rail. Product forbids a visible `^Connected$` node. Healthy WS is silent (`statusLabel === ''`). | Rail + composer. No standing Connected badge. Empty state is “Message {agent}”, not “Connected and ready”. |
| `settings` + `mobile/settings` | Pixels are 36/30/83%; captions lock 0 of 0. Nav in the PNG is pre-Chat Django. | **Whatever the isolated capture server actually paints** (see Settings meter). Also current Django chrome (Chat in nav + Agents pane). |
| `spa-settings` + `mobile/spa-settings` | Same populated meter under Redirected banner; captions claim 0 of 0. | Keep the Redirected banner (still honest). Meter + chrome must match the new `settings` twin, not “empty 0 of 0”. |

`landing` and `spa-chat` may be near-duplicates after `#322` (`/` and
`/chat` both mount `ChatPage`). That is fine: keep both stems if
`PAGES` still lists them; say so in the caption. Do not invent a
Dashboard frame.

### Must-fix retakes (same ticket — Django operator chrome)

These stems are still “a real Django page”, but the **chrome around
them** is stale vs `base.html` (Chat link + Agents sidebar +
no-dropdown primary). A journey regen already visits every `PAGES`
row; retake them in the same run.

| Stem | Why in the same run |
| --- | --- |
| `teams`, `teams-launch`, `blueprint-library`, `my-blueprints`, `agent-creator`, `sessions`, `session-detail`, `profiles` | 2026-08-19 frames freeze Home · Blueprints▾ · Teams · Sessions · Settings▾ · More. Current operator chrome is Home · Chat · Blueprints · Teams · Sessions · Settings + `#os-agent-sidebar`. |
| `spa-teams`, `spa-blueprints`, `spa-agent-creator` | Redirect stems. Keep the injected **Redirected:** banner. Underneath must match the new canonical twins. |

Mobile twins of every stem above ride the same `--mobile` run.

### Nice (same script; not the lie)

| Stem | Why nice |
| --- | --- |
| `login` + `mobile/login` | Chrome-less Sign-in card. Still a plausible login form. Retake if the full `PAGES` run is already happening; do not block the ticket on login pixels. |

### Intentional — do not retake in this ticket

| Path | Why leave |
| --- | --- |
| `docs/screenshots/skills/*.png` | CLI term-shots; not Grok chrome. |
| `docs/screenshots/webui/*.png` | Orphaned Builder; already `orphaned` / registry-only. |
| `docs/screenshots/archive/*` | Intentional archive. |
| `docs/demo/cli-and-api.gif` | CLI demo; not the tour lock. |
| `assets/images/20250105-Open-Swarm-HTML-Page.png` | Legacy unused. |
| New Settings-**sheet** overlay PNG | Nice later. SPA Settings is a `modal-end` sheet over chat, not a `PAGES` URL. Do not pretend `/settings` is the sheet. |

Do **not** add a Playwright `toHaveScreenshot` golden in this later
ticket. Pixel freeze stays the docs PNG set.

---

## Captions to rewrite

Rewrite **after** (or in the same PR as) the new PNGs. Follow pixels,
not the old lockfile.

### Must-fix caption surfaces

| File | What is stale | Rewrite to |
| --- | --- | --- |
| `docs/GUIDED_TOUR.md` §2 “Dashboard & SPA” | “Lightweight React dashboard”, **0 / 45 / 45**, Quick Actions, **Home · Chat · Blueprints · Teams · Sessions · Settings**, SPA five-tab dock, **Connected** shell / “Connected and ready”. Date **2026-08-19**. | `/` + `/chat` are Grok rail + chat. Settings is the gear sheet, not a nav eject. No standing Connected. Drop the catalog story. |
| `docs/GUIDED_TOUR.md` §3 chrome intro | “SPA desktop top nav: Home · Chat · …” and “SPA mobile dock is Home · Chat · …” | SPA has **no** product top nav and **no** five-tab dock. Django **does** still have that primary IA + a mobile `os-bottom-nav` (Home · Chat · Blueprints · Teams · Sessions). Keep parked-dock honesty for **Django** mobile twins only. |
| `docs/GUIDED_TOUR.md` Settings + `spa-settings` | Empty meter **0 of 0** | Match recaptured meter + current Django chrome. |
| `docs/USER_JOURNEY.md` | Date **2026-08-19**; `/` is a lightweight SPA dashboard; top nav phrase; **Connected** after login; Settings **0 of 0**. | Same as tour. Keep redirect + `fs_introspect` + seeded `resp_journey_seed` honesty if those pixels still hold. |
| `docs/SCREENSHOTS.md` | Every journey row dated **2026-08-19** and marked **current**. `landing` / `spa-chat` / settings / mobile dock / **Connected** copy. | New date. `landing` row must stop saying “React SPA dashboard” + Quick Actions + Home·Chat·… `spa-chat` must stop hardclaiming a visible **Connected** pill. Settings rows must stop claiming 0 of 0 unless the new PNG is actually empty. |
| `README.md` | `<img … landing.png alt="Operating Swarm dashboard">` | Alt text = Grok rail + chat (or whatever the new frame is). |
| `FEATURE_STATUS.md` API/ws row | “Journey `spa-chat.png` shows **Connected** after login” | Grok-chrome row already says “no standing Connected”. Align this leftover. |
| `docs/websocket_chat.md` | “checked-in desktop/mobile frames (2026-08-19) show **Connected**” | Badge table can stay as protocol language. Drop the claim that the **PNG** shows a visible Connected pill. |

### Captions that may move because pixels will move

Follow the new frames; do not pre-write numbers.

- **0/45/45** landing counts (`test_tour_docs_bridge_cli_list_vs_library_vs_landing_counts`). `/` will no longer show those tiles. Keep a CLI 31 / library / API bridge **somewhere** if those three surfaces still differ; do not hang it on a Dashboard PNG that is gone.
- **12 of 38**, “ready green checkmarks”, Custom Created **3** (Agent A/B/C). Capture isolates `SWARM_USER_DATA_DIR`, so my-blueprints may come back **empty**. Library totals may drift. Captions follow pixels.
- **`fs_introspect` selected**, seeded `resp_journey_seed` / not-a-live-`hybrid_team`-run, Redirected banner — keep if the new PNGs still show them.

### Nice caption leftovers (not the P0 lie)

- `CHANGELOG.md` 2026-08-19 / Connected / 0 of 0 entries are **historical**. Leave them.
- `GUIDED_TOUR.md` start-the-app blurb (“Build the React SPA (dashboard + /chat)”) — nice wording pass.
- `base.html` comment “Primary IA matches SPA Home” / “match SPA five-tab dock” — Django template comments, not tour captions. Out of this ticket unless an operator-docs pass wants them.

### Do not caption-rewrite onto old pixels

A caption-only PR that says “Grok rail” while `landing.png` still
shows rainbow Quick Actions is a new lie. Same for flipping Settings
copy to “36 / 30 / 83%” without a coordinated registry move — that
path is honest about **today’s** settings PNG, but it still freezes
pre-Chat Django nav. Prefer one regen.

---

## Registry tests that must move with the PNGs

`tests/unit/test_screenshot_registry.py` is still a caption lockfile
(wave-1 D-14). `#431` deletes two of these locks without retaking
PNGs. **Do not land that split.** Move the tests in the same later
ticket as the PNGs + captions.

### Must move (will fail an honest recapture if left as-is)

| Test | Today’s lock | Move to |
| --- | --- | --- |
| `test_tour_captions_include_spa_desktop_chat_nav` | Requires `Home · Chat · Blueprints · Teams · Sessions · Settings` in GUIDED_TOUR / USER_JOURNEY / SCREENSHOTS | Grok rail + chat (Agent list / no product top nav). Django operator captions may still name Home · Chat · … **for Django**. |
| `test_spa_chat_checked_in_caption_hardclaims_connected_badge` | Requires `**Connected**` in those three docs; bans `Connecting…` | Silent healthy WS. Ban a standing visible Connected pill. Do not keep requiring `**Connected**` just because the capture script can still read a node. |
| `test_settings_caption_matches_empty_meter_not_populated_local_config` | Requires “No settings configured” + `0 of 0`; bans “populated local configuration” | Match the recaptured meter. If the isolated server still paints 36/30/83% (or any non-zero), lock **that**, not 0 of 0. |
| `test_user_journey_screenshot_date_is_current_regeneration` | Requires `2026-08-19` in USER_JOURNEY | New date, or drop the date literal (prefer “last regenerated” without a frozen day). |
| `test_tour_docs_bridge_cli_list_vs_library_vs_landing_counts` | Requires `0/45/45` (or `0 / 45 / 45`) as a landing fact | Stop treating Dashboard tiles as `/`. Keep a three-surface count bridge only if captions still need it. |
| `test_docs_admit_parked_mobile_dock_artifact` | Parked-dock language for SPA + Django | SPA dock is gone. Keep parked-dock honesty for **Django** `os-bottom-nav` mobile twins. |
| `test_capture_script_waits_for_connected_or_unavailable` | Script must wait on `aria-label="Connection status"` text matching `\bConnected\b` | Healthy open status is `''`. A regen today fails spa-chat (`badge not terminal … '(empty)'`) unless `--allow-connecting`. Wait on rail + composer (or a non-empty *unhealthy* label). Do not republish a Connecting… frame as Connected. |
| `test_capture_script_parks_django_and_spa_mobile_bottom_navs` | Requires parking `nav.fixed.bottom-0` / `Mobile primary` | SPA park is a no-op (`App.tsx` has no that nav). Keep Django `.os-bottom-nav` parking. |
| `test_feature_status_mobile_dock_omits_settings` | Accepts `"mobile five-tab dock"` **or** `"Settings is desktop top-nav"` | Product text is already “no mobile five-tab dock”. Do not re-require the old “Settings is desktop top-nav” fork. |
| `test_my_blueprints_caption_matches_three_custom_agents` | Agent A/B/C + Custom Created **3** | Follow new pixels (likely empty under isolated XDG). |
| `test_blueprint_library_caption_matches_ready_mcp_badges` | “ready green checkmarks” | Follow new pixels; keep the spinner ban if badges are still ready. |

### Keep (still honest; not the stale-chrome lie)

| Test | Why keep |
| --- | --- |
| `test_guided_tour_and_journey_embeds_exist_on_disk` | Embed ↔ file existence. |
| `test_capture_pages_covered_by_registry` / `test_capture_pages_png_files_exist_desktop_and_mobile` | `PAGES` ↔ files. |
| `test_registry_does_not_claim_spa_dual_product_for_redirects` | Redirect honesty. |
| `test_capture_script_injects_redirect_banner_for_spa_stems` / `test_tour_captions_claim_sticky_banner_in_checked_in_spa_pngs` | Redirected banner. |
| `test_capture_pages_spa_only_root_and_chat` | ADR-001 `/` + `/chat` only. |
| `test_session_detail_*` / launcher `fs_introspect` | Seed vs launcher distinct. |
| `test_spa_app_mobile_dock_omits_settings_tab` | Already asserts Grok gear sheet, no `MobileTab`. Still true. |
| `test_every_non_archive_png_listed_in_registry` and skills/webui row tests | Registry completeness. |
| `test_agent_creator_caption_names_identity_progressive_disclosure` | Move only if the new creator PNG changes. |

### Capture-script comments that travel with the ticket

`PAGES` still names `landing` “Landing page (React SPA dashboard)” and
`settings` “Settings dashboard (Django)”. `SPA_ROUTE_STEMS` is still
`landing` + `spa-chat` — keep the two URLs; fix the dashboard wording.
`SERVER_ENV` sets `DJANGO_DEBUG=true`, so a “fresh empty meter” is
**not** a realistic capture outcome.

---

## Settings meter (D-02) — do not chase 0 of 0

Wave 1 already recorded: captions require **0 of 0**;
`docs/screenshots/settings.png` is a populated **36 / 30 / 83%**
meter (Django Framework open, `DEBUG=True`). Re-inspected: same
bytes (331050), same meter, same contradiction on
`spa-settings.png` and the tour/registry text.

The later ticket should **not** try to manufacture an empty meter:

- Capture always sets `DJANGO_DEBUG=true` (dev server +
  `SECRET_KEY` relax). `DEBUG=True` is a configured setting.
- `settings_views.py` counts raw collection “configured” rows; a
  throwaway journey DB with those env vars will not paint 0 of 0.

Honest path: recapture on the isolated journey server, then lock
**those** numbers (and the current Django chrome). If someone later
wants a true empty-meter fixture, that is a different capture-env
change — not a caption lie.

SPA Settings (gear → `SettingsSheet`) is a different surface. Do not
relabel `settings.png` as the DaisyUI sheet.

---

## D-03 — Playwright e2e exists; no workflow runs it

**Record only. Do not add a CI workflow from this file.**

Six specs under `webui/frontend/e2e/`:

- `chrome.spec.ts` — Grok left rail + chat; forbids top-nav Home/Chat
  and a visible `^Connected$`
- `nav.spec.ts`
- `smoke.spec.ts`
- `interaction.spec.ts`
- `settings-sheet.spec.ts`
- `teams-sidepane.spec.ts`

`webui/frontend/package.json` has `"test:e2e": "playwright test"`.

`.github/workflows/python-pytest.yml` runs `./scripts/build_frontend.sh`
and `uv run pytest`. It does not run `npm run test:e2e`.

`.github/workflows/visual-regression.yml` runs `npm test` (Vitest) +
`npm run build`, then `uv run pytest tests/e2e_visual` (golden-journey
HOLD). It installs Playwright Chromium for **that** Python suite. It
does not run `npm run test:e2e`.

Wave-1 leftover wording “REQ-5 large-card suite” is **obsolete**. The
**gap** (preview e2e never leaves the laptop) is **still true**. A
later CI-shape ticket may add it; this wave does not open that
rewrite.

Vitest **does** run in the visual job. Rail / Hidden / Compact /
settings-sheet behavior is not “untested”; it is unit-tested. D-03 is
missing **browser** CI, not missing unit coverage.

---

## Still-true chrome tests (do not weaken)

`#431` (REQ-73) drops stale *tour* caption locks **and** proposes
dropping remotes / **OMB** / row-fill asserts. Those product locks
are **still true** on `dfd72eef`. The later screenshot ticket must
not ride along and weaken them.

| Still true on main | Path |
| --- | --- |
| Remotes menu labels **Hermes**, **OMB**, **Rakazo** | `SettingsSheet.tsx` `REMOTE_PANES`; `SettingsSheet.test.tsx` still requires those buttons |
| Computer-control stub names a placed **OMB or Rakazo** remote | `ComputerControlStub.tsx`; `ComputerControlStub.test.tsx`; `ChatPage.test.tsx` |
| Rail row-fill classes `os-agent-row--support` / `os-agent-row--cos` | `AgentSidebar.tsx` still paints them; `AgentSidebar.test.tsx` still matches them |

Do **not** delete those asserts to go green. Do **not** add
`not.toHaveClass` ahead of a product PR that removes the fill. Tour
registry moves are unrelated.

`#431` deleting `test_tour_captions_include_spa_desktop_chat_nav` and
`test_spa_chat_checked_in_caption_hardclaims_connected_badge` **without**
new PNGs + new captions is the wrong split for D-01 / D-14. Those two
tests belong in the one later recapture ticket, rewritten to the new
frames — not dropped onto the old goldens.

---

## Ranked leftover IDs against today

### Must-fix

| ID | Bucket | Still-true? | Severity | Kind | Path | Today |
| --- | --- | --- | --- | --- | --- | --- |
| D-01 | must-fix | **still true** (worse) | P0 | stale lock | `docs/screenshots/{landing,spa-chat}.png` + mobile twins; README embed | 2026-08-19 Dashboard + top nav + Connected composer. Product is Grok rail + silent healthy WS (`#322`). |
| D-02 | must-fix | **still true** | P0 | caption vs pixels | `settings.png` / `spa-settings.png` + mobile; tour + registry | Pixels 36/30/83% + `DEBUG=True`. Captions lock 0 of 0. Django nav in the PNG is also pre-Chat. |
| D-14 | must-fix | **still true** (worse) | P1 | stale lock | `tests/unit/test_screenshot_registry.py` | Still locks `2026-08-19`, `0 of 0`, `0/45/45`, `12 of 38`, `**Connected**`, `Home · Chat · Blueprints · Teams · Sessions · Settings`, Custom Created **3**. An honest recapture fails this file until it moves **with** the PNGs. |
| D-03 | must-fix (gap) / obsolete (wording) | gap **still true** | P0 | missing coverage | `webui/frontend/e2e/*.spec.ts`; both workflows | Six Playwright specs; `test:e2e` script; **no** workflow runs it. Not a license to add a workflow here. |

### Nice

| ID | Bucket | Still-true? | Severity | Kind | Path | Today |
| --- | --- | --- | --- | --- | --- | --- |
| D-06 | nice | **still true** | P1 | stale lock (capture path) | `scripts/capture_user_journey.py` | Connected wait swallows `wait_for_function`, then hard-fails. On today’s chrome the badge text is **empty** when healthy, so a regen fails closed (good) or `--allow-connecting` can still publish a Connecting… frame (bad). Fix in the same recapture ticket as D-01. |
| W2-01 | nice | new | P2 | stale lock | `FEATURE_STATUS.md` API/ws row; `docs/websocket_chat.md` journey paragraph | Leftover “spa-chat.png shows Connected” after the Grok-chrome row already says no standing Connected. Same caption pass. |
| W2-02 | nice | new | P2 | stale lock | Django operator `PAGES` stems + mobile twins | Pre-Chat dropdown nav, no Agents pane. Same journey run as D-01; not a second ticket. |
| W2-03 | nice | new | P2 | missing coverage | Settings **sheet** has no journey PNG | Optional later stem. Do not overload `settings.png`. |

### Obsolete

| ID | Bucket | Why obsolete |
| --- | --- | --- |
| Wave-1 follow-up “Recapture on REQ-5 chrome” | obsolete | Product chrome is Grok-Bot (`#322`), not REQ-5 Home+Agents catalog. Recapture **today’s** rail+chat. |
| D-03 wording “REQ-5 large-card Playwright” | obsolete | `chrome.spec.ts` first test is “Grok chrome is left rail + chat…”. Gap remains (no CI). |
| Caption-lock delete as a standalone REQ-73 fix | obsolete-as-action | `#431` dropping nav / Connected **registry** tests without moving PNGs leaves the goldens claiming the old chrome. Move with pixels. |
| “Four Home cards / Primary nav” as a *Playwright* lock | obsolete | `#322` already rewrote e2e. The leftover lock is the **PNG + caption + registry** trio. |

### Intentional

| Item | Why leave |
| --- | --- |
| `golden-journey` / D-04 / D-05 / D-11 | Wave-1 **HOLD**. Still FAILURE on `main`. Not this recapture ticket. Do not rewrite `tests/e2e_visual` or `visual-regression.yml` here. |
| Skills / `webui/` / archive PNGs | Historical or CLI. Already marked orphaned/archived. |
| Remotes / OMB / row-fill Vitest locks | Still true on the product. See above. |
| Dual pytest config (D-07 / D-08) and other wave-1 nice IDs | Out of screenshot/tour scope. |
| Adding Playwright e2e to CI | D-03 gap is real; adding a workflow is a different ticket. |

---

## Inventory snapshot (`dfd72eef`)

| Surface | Count / fact |
| --- | --- |
| Journey `PAGES` stems | 16 (desktop + mobile = 32 PNGs) |
| Checked-in journey date | **2026-08-19** (registry + tour + USER_JOURNEY + date test) |
| Registry tests | 32 functions in `test_screenshot_registry.py` |
| Playwright specs | 6 under `webui/frontend/e2e/` |
| Workflows that run `npm run test:e2e` | **none** |
| Workflows that run Vitest | `visual-regression.yml` only |
| Pixel goldens in Playwright | **none** (`toHaveScreenshot` unused) |
| `Dashboard` mounted in `App.tsx` | **no** (`/` and `/chat` → `ChatPage`) |
| Visible Connected on ChatPage | **no** (`sr-only`; healthy label `''`) |
| SPA mobile five-tab dock | **no** |
| Django primary + Agents aside | **yes** (`base.html`) |
| Settings sheet remotes | Hermes / **OMB** / Rakazo labels still shipped |

---

## Suggested later ticket (not this PR)

**One honesty ticket:** regen journey PNGs (desktop + mobile) on
current Grok + Django chrome → rewrite tour/registry/README captions
to those pixels → move the D-14 locks listed above → fix the
spa-chat Connected wait so a healthy silent WS can publish a frame
that captions will not call **Connected**.

Do not add a workflow. Do not touch `:8001`. Do not rebase `#431` /
`#344`. Do not drop remotes / OMB / row-fill tests. Do not check in
PNG binaries in *this* look-only PR (there are none).

`golden-journey` stays HOLD until a dedicated ticket owns those six
tests. That ticket is not this file.
