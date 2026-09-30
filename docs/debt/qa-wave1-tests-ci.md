# QA wave 1 — leftover tests/CI debt (look-only)

**Status:** look-only re-read. No product, test, workflow, or existing
`docs/debt/*.md` edits in this change.

**Starting leftover notes:** `docs/debt/tests-ci.md` (REQ-22d, merged as
`#328` / `c2ff95dc`).

**Today’s tree:** `841e953c` (`main` after `#375`).

**Method:** static re-read of `pytest.ini`, `pyproject.toml`,
`.github/workflows/{python-pytest,visual-regression}.yml`,
`tests/e2e_visual/`, `webui/frontend/e2e/`, Vitest `__tests__`,
`scripts/capture_user_journey.py`, checked-in `docs/screenshots/*.png`,
and GitHub Actions conclusions for `visual-regression.yml` /
`python-pytest.yml` on 2026-09-03. No recapture. No host bounce. No
Neon. No secrets. No live LAN URLs.

This file does **not** propose a CI rewrite, a golden-journey patch, a
rebase, a squash, or a fold into `#344`.

---

## How to read the ranks

| Bucket | Meaning |
| --- | --- |
| **must-fix** | Still true on today’s tree; still misleads docs or leaves a hole **outside** the golden-journey HOLD. A later ticket can fix it. Not this PR. |
| **nice** | Still true; already gated, local-only, or cleanup. Do not block a green Python matrix on these. |
| **obsolete** | The leftover note’s *claim* no longer matches today’s files (chrome moved, or a later PR already covered the behavior). |
| **HOLD** | `golden-journey` / `tests/e2e_visual`. Pre-existing. Often FAILURE on otherwise green PRs. Do not “fix” it here. |

Kind tags: **flake** (timing/selector race), **missing coverage** (suite
exists but never runs where it matters), **duplicate suite** (same
behavior asserted twice), **stale lock** (asserts a chrome the product
no longer ships).

---

## HOLD — golden-journey (keep separate)

`.github/workflows/visual-regression.yml` job `golden-journey` is a
**pre-existing HOLD**. It is not a flake of an otherwise current suite.
It is a **stale-lock** browser job that still asserts the pre–Grok-Bot
Home shell.

Observed on 2026-09-03 (GitHub Actions, `visual-regression.yml`):

- Every completed run sampled today concluded **failure**, including
  merges to `main` (`#375`, `#345`, `#365`, `#357`) and open feature
  branches.
- A representative log (`REQ-67` run, same suite as `main`):
  - `test_landing_page_is_styled` — Timeout 10s waiting for
    `.btn-primary` **visible** on `/`. The locator resolves to a
    **hidden** Settings-sheet `Save retention` button
    (`btn btn-primary btn-sm`). Product `/` is now `ChatPage` (Grok
    chrome, `#322`), not the Dashboard catalog.
  - `test_chat_websocket_connects` — Timeout 20s waiting for visible
    exact text `Connected`. Today’s composer puts the badge in an
    `sr-only` `[aria-label="Connection status"]`
    (`webui/frontend/src/pages/ChatPage.tsx`). Playwright
    `chrome.spec.ts` **forbids** a visible `^Connected$` node.
  - `test_dark_mode_toggle` — **SKIPPED**:
    `SPA dark-mode toggle not present on / (Django-canonical shell;
    SPA theme test N/A)`. Selector is still
    `get_by_label("Toggle dark mode")`. Live control is
    `Switch to light/dark theme`.
  - 2 failed, 3 passed, 1 skipped.

The leftover notes already named the two failing predicates as **D-04**
and the skip as **D-05**, and the missing Home/Agents asserts as
**D-11**. Those IDs are **still true**, but they are the HOLD — not a
new gap and not a reason to rewrite CI in a follow-up from this file.

Python unit CI (`.github/workflows/python-pytest.yml`) is a different
job. Recent completed `python-pytest` runs on feature branches were
**success**. Treat a green Python matrix + red `golden-journey` as the
known HOLD pattern.

---

## What later PRs already covered (do not re-open as missing tests)

Leftover notes were written against REQ-5 chrome (`91dabd64`,
`#307`). Product chrome and several feature tests moved after that
tree. These are **already covered** by later PRs; they are not leftover
holes.

| Later PR | What it added that CI *does* run | What it did **not** fix |
| --- | --- | --- |
| `#322` Grok-Bot chrome | Rewrote `e2e/chrome.spec.ts`, `nav.spec.ts`, `smoke.spec.ts` to left-rail + chat. Unmounted `Dashboard` from `App.tsx` (`/` → `ChatPage`). Vitest `App.routes.test.tsx`. | Did not add `npm run test:e2e` to any workflow. Did not recapture PNGs. Did not update `tests/e2e_visual`. |
| `#320` settings sheet | `SettingsSheet.test.tsx`, `e2e/settings-sheet.spec.ts` | Playwright file still not in CI. |
| `#331` teams in AGENTS | `e2e/teams-sidepane.spec.ts`, Vitest roster helpers | Same: preview e2e not in CI. |
| `#334` hover-edit | `chrome.spec.ts` Blueprint sheet case; `AgentSidebar` Vitest | Playwright still local-only. |
| `#335` / `#342` Hidden seed + drag | `chrome.spec.ts` + `AgentSidebar.test.tsx` + `hiddenAgents.test.ts` | Duplicate hide contract (Vitest + Playwright). Playwright not in CI. |
| `#341` REQ-27b | `ComputerControlStub.test.tsx` + `chrome.spec.ts` modal case | Playwright not in CI. |
| `#345` REQ-28 | `tests/core/test_{agent_roles,team_isolation,team_rosters}.py`, `tests/views/test_team_rosters_api.py`, Vitest `agentRoles` / `teamRoster` | Extra local `api_client` in `test_team_rosters_api.py` (worsens D-12). |
| `#365` REQ-37 | `tests/core/test_chat_compact.py`, Vitest `chatCompact.test.ts`, `ChatPage` compact cases, `chrome.spec.ts` Compact menu | Playwright Compact case still local-only. |
| `#357` REQ-36 | `tests/blueprints/test_software_dev.py` | n/a for leftover D-ids. |
| `#375` REQ-47 | `tests/unit/test_pinokio_scripts.py` | n/a. |
| `#328` itself | This leftover ranking only | No test or workflow change (by design). |

Vitest **does** run in the visual job (`npm test` before
`npm run build` in `visual-regression.yml`). That is why later SPA
behavior (rail, Hidden, Compact, settings sheet) is not “untested” —
it is unit-tested. The hole is **browser e2e never leaving the laptop**.

`Dashboard.test.tsx` still locks four `os-action-card` Home tiles.
`Dashboard` is **not mounted** (`App.tsx` routes `/` and `/chat` to
`ChatPage` only). That leftover Vitest is a **duplicate / stale lock**,
not missing coverage of current Home.

---

## Ranked leftover IDs (D-01 … D-18) against today

### Must-fix (still true; not the HOLD)

| ID | Bucket | Still-true? | Severity | Kind | Path | Today |
| --- | --- | --- | --- | --- | --- | --- |
| D-01 | must-fix | **still true** (worse) | P0 | stale lock | `docs/screenshots/{landing,spa-chat,teams,settings,blueprint-library}.png` + `docs/screenshots/mobile/*` | On-disk frames are still the **2026-08-19** tour. `landing.png` is rainbow Quick Actions + top nav Home·Chat·…, no Agents rail. `spa-chat.png` is Connected composer + top nav, no left rail. `teams.png` is Django dropdown chrome (Home · Blueprints▾ · Teams · Sessions · Settings▾ · More), no Chat, no Agents pane. Product SPA is Grok left-rail + chat (`App.tsx`). Captions in `SCREENSHOTS.md` / `GUIDED_TOUR.md` / `USER_JOURNEY.md` still mark these stems **current**. |
| D-02 | must-fix | **still true** | P0 | stale lock | `docs/screenshots/settings.png` (331050 bytes), `docs/screenshots/mobile/settings.png`; `tests/unit/test_screenshot_registry.py` `test_settings_caption_matches_empty_meter_not_populated_local_config` | Registry + tour still require **“No settings configured” / “0 of 0”**. Desktop PNG is still the populated **36 / 30 / 83%** Settings Dashboard (Django Framework expanded, `DEBUG=True`). Caption and pixels still contradict. |
| D-03 | must-fix | **still true** as “Playwright e2e never in CI”; **obsolete** as “REQ-5 large-card suite” | P0 | missing coverage | `webui/frontend/e2e/*.spec.ts`; `.github/workflows/{python-pytest,visual-regression}.yml` | Six Playwright files exist (`chrome`, `nav`, `smoke`, `interaction`, `settings-sheet`, `teams-sidepane`). `package.json` has `test:e2e`. **No workflow runs it.** `#322+` rewrote `chrome.spec.ts` to Grok rail (not four Home cards). The *gap* is unchanged; the *description* in leftover notes is stale. Do not treat this as a license to rewrite CI in a follow-up from this file — just record that preview e2e is laptop-only. |
| D-07 | must-fix | **RESOLVED** | — | — | Closed. The wave1 diagnosis ("duplicate suite (config)") understated it and its stated mechanism was wrong: pytest does **not** merge the two files, it takes the first and ignores the rest, so the whole `pyproject.toml` block was inert — including the #1335 `SWARM_SKIP_DOTENV` guard (which only worked via `tests/conftest.py`) and `DJANGO_ALLOW_ASYNC_UNSAFE` (which was absent everywhere). Every run printed `WARNING: ignoring pytest config in pyproject.toml!`. Migrated to `pytest.ini`, deleted the dead block, fixed `CONTRIBUTING.md`, added `tests/core/test_pytest_config_single_source.py`, and enabled the parked `timeout` hang guard at 600s. Detail in `docs/debt/tests-ci.md` §D-07. |
| D-08 | must-fix | **still true** | P1 | duplicate suite (runner) | `scripts/run_tests.py`; `Makefile` `test`; `.github/workflows/python-pytest.yml` | `make test` still sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and pins plugins. CI is still `uv run pytest` with autoload + always-on cov. Matrix still 3.10 / 3.11 / 3.12, `fail-fast: false`, no xdist. |
| D-14 | must-fix | **still true** (worse) | P2→P1 | stale lock | `tests/unit/test_screenshot_registry.py` (619 lines) | Still a caption lockfile: `2026-08-19`, `0 of 0`, `0/45/45`, `12 of 38`, `**Connected**`, `fs_introspect`, “ready green checkmarks”, Custom Created **3**, bans `Connecting…`. Also still locks SPA desktop nav phrase **Home · Chat · Blueprints · Teams · Sessions · Settings** (`test_tour_captions_include_spa_desktop_chat_nav`) after `#322` removed that nav from `App.tsx`. An honest recapture still requires a coordinated docs+lockfile edit. |

### Nice (still true; gated or cleanup)

| ID | Bucket | Still-true? | Severity | Kind | Path | Today |
| --- | --- | --- | --- | --- | --- | --- |
| D-06 | nice | **still true** | P1 | flake (capture path) | `scripts/capture_user_journey.py` | Word-bounded Connected wait still swallows `wait_for_function` (`except Exception: pass`). `--allow-connecting` still exists and can still write a Connecting… `spa-chat.png` that D-14 will then hard-claim as Connected. Not CI; only recapture. |
| D-09 | nice | **still true** | P1 | unused | `tests/conftest.py` | `mock_openai_client`, `mock_model_instance`, `authenticated_client` still defined only. No test requests them. |
| D-10 | nice | **still true** | P1 | missing coverage (opt-in live) | `tests/integration/test_memory_mem0_e2e.py` | Still the only in-tree test that needs live OpenAI (`RUN_MEM0_E2E=1` + real `OPENAI_API_KEY`, 300s). Default CI still skips (good). Still no `live_inference` / `slow` marker. Last recorded run in the docstring is still 2026-06-11 / 401. Do not add more key-gated tests. |
| D-12 | nice | **still true** (worse) | P2 | duplicate suite | `tests/conftest.py`, `tests/api/conftest.py`, local `api_client` | Root `test_user` is `update_or_create`; API conftest is `get_or_create`. Local `api_client()` now in **eight** files (original five plus `test_herdr_api.py`, `test_remotes_api.py`, `test_team_rosters_api.py` from later PRs). `clear_litellm_env` still duplicated in `tests/core/conftest.py` and `tests/blueprints/conftest.py`. |
| D-13 | nice | **partially obsolete** | P2 | duplicate suite | `webui/frontend/e2e/*` vs Vitest | Theme persist is still Playwright-only (`interaction.spec.ts`) and still absent from CI. Hide/unhide is still Vitest **and** `chrome.spec.ts` (do not add a third copy). Home-card / Primary-nav overlap in the leftover table is **obsolete**: `nav.spec.ts` / `smoke.spec.ts` now assert Agent list + composer; `chrome.spec.ts` asserts **no** Primary nav. `Dashboard.test.tsx` vs `chrome.spec.ts` is no longer the same contract. |
| D-15 | nice | **still true** | P2 | unused / scratch | `tests/core/test_userguide_captures.py` | Default `SCRATCH=/tmp/grok-goal-4567a1afab94/implementer`. Still skips when that tree is empty. `tests/core/conftest.py` still bundles it with the slow-CLI skip. |
| D-16 | nice | **still true** | P2 | flake / slow | `tests/core/test_documented_cli_journey.py`, `tests/cli/*.py`, `tests/xdg_isolation.py` | Still subprocess CLI with 30–60s timeouts. Still no `slow` marker. Still session `--help` >25s skip only. Full Python matrix still pays this on three versions. |
| D-17 | nice | **still true** | P2 | unused tooling | `pyproject.toml` extras | `factory-boy` still unused (no `factory.Factory` / `DjangoModelFactory`). `pytest-xdist` still not passed in CI. `pytest-timeout` still installed; global `timeout =` still commented; only `test_auth_hardening.py` (60s) and mem0 e2e (300s) mark timeouts. |
| D-18 | nice | **still true** | P2 | duplicate suite (CI shape) | `python-pytest.yml` `frontend` job; `visual-regression.yml` | SPA still built twice per PR. Vitest still only in the visual job. Playwright e2e still in neither. Recorded as leftover **shape**, not as a rewrite ticket. |
| W1-01 | nice | **new leftover** (post-`#322`) | P2 | stale lock / unused | `webui/frontend/src/pages/Dashboard.tsx`, `…/__tests__/Dashboard.test.tsx` | Component + Vitest still lock four Home cards. `App.tsx` never mounts `Dashboard`. Covered as “already unmounted,” not as missing Home coverage. |

### Obsolete (leftover *claim* is no longer the tree)

| ID | Bucket | Still-true? | Severity then | Why obsolete |
| --- | --- | --- | --- | --- |
| D-03 (wording) | obsolete | claim obsolete; gap remains (see must-fix) | P0 | Leftover text: “REQ-5 Playwright (large cards + hide-from-sidebar)”. Today `chrome.spec.ts` first test is “Grok chrome is left rail + chat, not a top-nav product shell”. Hide/unhide remains, but the sacred Home-card contract moved to unmounted `Dashboard.test.tsx`. |
| D-11 (as a *new* must-fix) | HOLD / obsolete-as-action | predicate still true | P1 | Visual suite still duplicates capture bootstrap (ports 8326 vs 8321) and still does not assert Agents / `os-action-card`. That is now **why the HOLD fails**, not a separate “add two cheap asserts” ticket. Do not rewrite this job from this file. |
| Follow-up #1 in leftover notes (“Recapture on REQ-5 chrome”) | obsolete | — | — | Product chrome is Grok-Bot (`#322`), not REQ-5 Home+Agents catalog. If a later honesty ticket recaptures, recapture **today’s** rail+chat, not REQ-5 cards. |
| D-13 table rows “Four Home cards / Primary nav” as Playwright locks | obsolete | — | P2 | `#322` deleted those Playwright locks. Vitest `Dashboard.test.tsx` is the leftover Home-card lock. |

### HOLD IDs (still true; do not treat as this wave’s fix list)

| ID | Still-true? | Severity | Kind | Path | Today |
| --- | --- | --- | --- | --- | --- |
| D-04 | **still true** (worse) | P1 | stale lock (was flake) | `tests/e2e_visual/test_golden_journey.py` `test_chat_websocket_connects` | Exact visible `Connected`, 20s. Product badge is `sr-only`. Consistent FAILURE on `main` today, not an intermittent race. |
| D-05 | **still true** | P1 | stale lock (silent skip) | same file, `test_dark_mode_toggle` | Still `Toggle dark mode` → skip. Confirmed in today’s visual logs. |
| D-11 | **still true** (worse) | P1 | stale lock + duplicate bootstrap | `tests/e2e_visual/conftest.py` + `test_golden_journey.py` vs `scripts/capture_user_journey.py` | `.btn-primary` on `/` now hits a hidden retention button. Suite can still pass CSS-size / navbar-text checks on a shell that is not the product Home. |

---

## Inventory snapshot (`841e953c`)

| Surface | Count / fact |
| --- | --- |
| Pytest files `tests/**/test_*.py` | 204 |
| Vitest files under `webui/frontend/src` | 38 |
| Playwright specs `webui/frontend/e2e/*.spec.ts` | 6 |
| Workflows that run `uv run pytest` (unit matrix) | `python-pytest.yml` |
| Workflows that run `npm test` (Vitest) | `visual-regression.yml` only |
| Workflows that run `npm run test:e2e` | **none** |
| `tests/e2e_visual` gate | `RUN_E2E_VISUAL=1` (CI visual job only) |
| Pixel goldens in Playwright | **none** (`toHaveScreenshot` still unused). Pixel freeze is still the docs PNG set. |
| Live-inference tests in default path | mem0 e2e only; skipped without env. |

XSS view tests remain static source checks, not a third browser suite.

---

## Cross-cutting (unchanged, not new ranks)

- **pytest-django import order** (`DJANGO_DEBUG` before `swarm.settings`,
  `TESTING = 'pytest' in sys.modules`) is still load-bearing. Still
  documented only next to the dual config (D-07).
- **No Neon / oracle / LAN** work is implied by any row above.
- **`#344`** (open Grok-Bot chrome product PR) is out of scope. Do not
  fold this look-only file into it.
- Suggested leftover follow-up order that said “put `npm run test:e2e`
  in CI; fix visual Connected + theme” is a **CI rewrite**. This wave
  records the gap and **does not** open that rewrite.

---

## Suggested later tickets (not this PR)

Honesty and local-suite cleanup only. No workflow file in the first
honesty ticket.

1. Recapture journey PNGs against **current** Grok chrome + isolated
   Settings empty meter; then rewrite captions/registry (D-01, D-02,
   D-14). Drop date literals.
2. Delete or park unmounted `Dashboard` Vitest once product agrees Home
   is not a catalog (W1-01). Do not add another Home-card e2e.
3. Single pytest config source; make `--cov` / `log_cli` opt-in; one
   runner for `make test` and docs (D-07, D-08). Delete unused fixtures
   (D-09, D-12).
4. Mark `slow` / `live_inference`; leave mem0 opt-in (D-10, D-16).

`golden-journey` stays HOLD until a dedicated ticket owns those six
tests. That ticket is not this file.
