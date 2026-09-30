# REQ-22d — Tests / CI technical-debt audit

**Status:** audit only. No rewrites in this change.

## Quoted requirement

> REQ-22d technical debt AUDIT ONLY. Do not rewrite. Ranked list in final
> report and/or draft `docs/debt/tests-ci.md`.
>
> Scope: tests/, webui/frontend e2e/playwright,
> scripts/capture_user_journey.py, golden screenshots, pytest-django.
> Look for duplicate coverage, slow tests, tests that require live
> inference, screenshot goldens that freeze the old Home+Agents chrome,
> flaky waits on Connected, unused fixtures.
>
> Each finding: P0/P1/P2, path, why, action. No Neon. Quote this REQ.

Out of scope: Neon quota / `docs/RUNBOOK_NEON_QUOTA_CRASH_LOOP.md` and any
Neon-adjacent CI.

Method: static read of pytest + Playwright + journey capture + checked-in
PNGs against the REQ-5 / REQ-5c chrome that landed in
`91dabd64` (`feat(webui): REQ-5 dark chrome, large home cards,
hide-from-sidebar`). No test rewrites, no recapture.

---

## Ranked findings

| Rank | ID | Pri | Path | One-line why |
| ---: | --- | --- | --- | --- |
| 1 | D-01 | P0 | `docs/screenshots/{landing,spa-chat,teams,settings,blueprint-library}.png` (+ mobile twins) | Goldens freeze pre–REQ-5 chrome (no Agents pane, old Django dropdown nav, rainbow Home tiles) |
| 2 | D-02 | P0 | `docs/SCREENSHOTS.md`, `GUIDED_TOUR.md`, `USER_JOURNEY.md`, `tests/unit/test_screenshot_registry.py` | Caption + string-lock suite claims empty Settings `0 of 0`; on-disk `settings.png` is a populated 36/30/83% meter |
| 3 | D-03 | P0 | `webui/frontend/e2e/chrome.spec.ts`, `.github/workflows/{python-pytest,visual-regression}.yml` | REQ-5 Playwright (large cards + hide-from-sidebar) never runs in CI |
| 4 | D-04 | P1 | `tests/e2e_visual/test_golden_journey.py` | `test_chat_websocket_connects` waits 20s for exact `Connected`; fails on Unavailable; substring-adjacent to “Connected and ready” |
| 5 | D-05 | P1 | `tests/e2e_visual/test_golden_journey.py` (`test_dark_mode_toggle`) | Looks for `aria-label="Toggle dark mode"`; REQ-5 uses “Switch to light/dark theme” → silent skip in visual CI |
| 6 | D-06 | P1 | `scripts/capture_user_journey.py` | spa-chat Connected wait is word-bounded (good) but swallows the Playwright timeout then hard-fails; `--allow-connecting` can still publish a Connecting frame |
| 7 | ~~D-07~~ | ~~P1~~ | **RESOLVED** — `pytest.ini` is now the single source | Dual pytest config where the `pyproject.toml` half was silently ignored. The original diagnosis ("pytest merges them") was wrong — it does not merge, the first file found wins. See §D-07 |
| 8 | D-08 | P1 | `.github/workflows/python-pytest.yml` vs `scripts/run_tests.py` | CI is `uv run pytest` (plugin autoload); `make test` disables autoload and pins plugins — two suites |
| 9 | D-09 | P1 | `tests/conftest.py` | Unused fixtures `mock_openai_client`, `mock_model_instance`, `authenticated_client` |
| 10 | D-10 | P1 | `tests/integration/test_memory_mem0_e2e.py` | Only in-tree test that requires live OpenAI embeddings (`RUN_MEM0_E2E=1` + real `OPENAI_API_KEY`, 300s) |
| 11 | D-11 | P1 | `tests/e2e_visual/conftest.py` vs `scripts/capture_user_journey.py` | Duplicated Django+Playwright server bootstrap (ports 8326 vs 8321); visual suite never asserts Agents / `os-action-card` |
| 12 | D-12 | P2 | `tests/api/conftest.py` + per-file `api_client` | Duplicate `test_user` / `authenticated_async_client` / five local `api_client` fixtures |
| 13 | D-13 | P2 | `webui/frontend/e2e/{smoke,nav,chrome,interaction}.spec.ts` vs Vitest | Theme, nav mount, and Agents hide covered twice; preview e2e never in CI |
| 14 | D-14 | P2 | `tests/unit/test_screenshot_registry.py` | 613-line caption lockfile; recapture after REQ-5 will fail a pile of string asserts before PNGs are honest |
| 15 | D-15 | P2 | `tests/core/test_userguide_captures.py` | Hardcoded `SCRATCH=/tmp/grok-goal-4567a1afab94/implementer`; skips or fails outside that agent scratch |
| 16 | D-16 | P2 | `tests/core/test_documented_cli_journey.py`, `tests/cli/*.py` | Subprocess CLI journey (install+launch+config+wizard); skipped only if `--help` >25s; no `slow` marker |
| 17 | D-17 | P2 | `pyproject.toml` extras | `factory-boy` unused; `pytest-xdist` unused in CI; `pytest-timeout` installed but no global timeout; `slow` marker commented out |
| 18 | D-18 | P2 | `.github/workflows/{python-pytest,visual-regression}.yml` | Frontend built twice per PR; Vitest only in visual job; Playwright e2e in neither |

---

## Findings

### D-01 — P0 — Screenshot goldens freeze pre–REQ-5 Home+Agents chrome

**Path:** `docs/screenshots/landing.png`, `spa-chat.png`, `teams.png`,
`settings.png`, `blueprint-library.png`, and the matching
`docs/screenshots/mobile/*` stems. Capture date locked as **2026-08-19**
(`docs/SCREENSHOTS.md`, `docs/GUIDED_TOUR.md`).

**Why:** REQ-5 / REQ-5c (`src/swarm/templates/base.html`,
`webui/frontend/src/App.tsx`, `webui/frontend/src/pages/Dashboard.tsx`)
shipped a shared Home nav + **Agents** sidepane (`#os-agent-sidebar` /
`aria-label="Agent list"`), Chat on the Django primary nav, large
`os-action-card` tiles, and near-black chrome. Checked-in goldens still
show the previous operator shell:

- Django `teams.png` / `blueprint-library.png`: Home · Blueprints
  (dropdown) · Teams · Sessions · Settings (dropdown) · More. **No Chat.**
  **No Agents pane.**
- SPA `landing.png`: four rainbow-colored Quick Action buttons
  (purple / pink / teal / blue), no left Agents list. Current
  `Dashboard.tsx` uses `os-action-card` and Vitest
  (`webui/frontend/src/pages/__tests__/Dashboard.test.tsx`) forbids
  `btn-primary|btn-secondary|btn-accent|btn-info`.
- SPA `spa-chat.png`: Connected composer, **no Agents sidebar**.
  `App.tsx` now mounts `<AgentSidebar>` on `/` and `/chat`.

These PNGs are the tour source of truth. Leaving them in place freezes the
old chrome in USER_JOURNEY / GUIDED_TOUR and will fight any honest
recapture.

**Action:** After a follow-up rewrite ticket (not this audit): rebuild
`webui/frontend/dist`, recapture desktop + mobile via
`scripts/capture_user_journey.py`, then update captions/registry. Do not
keep 2026-08-19 frames as “current”.

---

### D-02 — P0 — Settings golden vs caption/string-lock contradiction

**Path:** `docs/screenshots/settings.png` (331 KB) /
`docs/screenshots/mobile/settings.png` (887 KB);
`docs/SCREENSHOTS.md` row for `settings.png`;
`tests/unit/test_screenshot_registry.py`
(`test_settings_caption_matches_empty_meter_not_populated_local_config`).

**Why:** Registry + tour + the 613-line lockfile all require
**“No settings configured” / “0 of 0”** and ban “populated local
configuration”. The on-disk desktop PNG is a **populated** Settings
Dashboard: **36** total / **30** configured / **83%** complete, Django
Framework table expanded (`DEBUG=True`, redacted `SECRET_KEY`,
`ALLOWED_HOSTS=localhost,127.0.0.1`). That is also pre–REQ-5 chrome
(tiny Export/Refresh buttons, purple-accent header — the gradient
`#667eea` / `#764ba2` is gone from `operator.css` and asserted absent in
`tests/unit/test_req5_chrome_shell.py`).

So the “honesty” suite currently locks **captions that do not match the
PNG**, and the PNG does not match **current** Settings
(`os-action-card` grid in `src/swarm/templates/settings_dashboard.html`).

**Action:** Recapture Settings against isolated
`SWARM_USER_DATA_DIR` (capture script already isolates this). Rewrite
captions to the new frame. Split registry tests so they assert PNG
facts (OCR or structured manifest) rather than only markdown strings.

---

### D-03 — P0 — REQ-5 Playwright e2e is not in CI

**Path:** `webui/frontend/e2e/chrome.spec.ts` (`dashboard shows four
large chrome action cards`, `right-click hide from sidebar…`);
`webui/frontend/package.json` script `test:e2e`;
`.github/workflows/python-pytest.yml` (frontend job: `build_frontend.sh`
only); `.github/workflows/visual-regression.yml` (`npm test` = Vitest,
then Python `tests/e2e_visual`).

**Why:** The only browser test that asserts REQ-5 Home cards
(`os-action-card`, height > 120) and Agents hide/unhide
(`localStorage.swarm_hidden_agents`) is Playwright `chrome.spec.ts`.
No workflow runs `npm run test:e2e`. Visual CI exercises computed CSS
and a `Connected` badge, not the Agents pane. A green PR can ship a
broken Home+Agents shell.

**Action:** Add `npm run test:e2e` (with `npx playwright install
chromium`) to visual-regression or a dedicated SPA e2e job. Keep it
off the Python 3.10/3.11/3.12 matrix.

---

### D-04 — P1 — Flaky exact wait on Connected

**Path:** `tests/e2e_visual/test_golden_journey.py` →
`test_chat_websocket_connects`.

**Why:**

```python
badge = page.get_by_text("Connected", exact=True)
badge.wait_for(state="visible", timeout=20_000)
```

- 20s hard wait; no `Unavailable` / `Disconnected` terminal states
  (unlike `scripts/capture_user_journey.py`’s word-bounded
  `Connected|Unavailable|Disconnected`).
- Empty-state copy is **“Connected and ready”**
  (`webui/frontend/src/pages/ChatPage.tsx`). `exact=True` avoids a
  substring match today, but any extra “Connected” node (or a
  Connecting… stall under CI load) flakes the visual job.
- Comment in `capture_user_journey.py` already records that **8s was
  flaky** and raised the capture wait to 20s — same pressure, weaker
  predicate in the pytest suite.

**Action:** Reuse the capture-script predicate
(`[aria-label="Connection status"]` + word-bounded terminal states).
Fail with the badge text in the message; do not treat Connecting… as
Connected.

---

### D-05 — P1 — Visual dark-mode test silently skips after REQ-5

**Path:** `tests/e2e_visual/test_golden_journey.py` →
`test_dark_mode_toggle`.

**Why:** Selector is `get_by_label("Toggle dark mode")`. REQ-5 SPA
toggle is `Switch to light theme` / `Switch to dark theme`
(`webui/frontend/src/App.tsx`). When count is 0 the test
**`pytest.skip`s** (“Django-canonical shell; SPA theme test N/A”)
instead of failing. Visual CI stays green without exercising theme CSS.
The correct selector already lives in
`webui/frontend/e2e/interaction.spec.ts`, which CI does not run
(see D-03 / D-13).

**Action:** Point the visual test at the REQ-5 accessible name, or
delete it and rely on Playwright e2e once that job exists.

---

### D-06 — P1 — Journey capture Connected wait still leaky

**Path:** `scripts/capture_user_journey.py` (`SPA_CHAT_STATUS_TIMEOUT_MS`,
`_spa_chat_status_is_terminal`, `capture()` spa-chat branch).

**Why:** The wait is the right shape (word-bounded; 20s). Two leftover
hazards:

1. `wait_for_function` exceptions are **swallowed** (`except Exception:
   pass`) before a second badge read; failure mode is a delayed skip,
   not a crisp timeout.
2. `--allow-connecting` writes a PNG while the badge is still
   Connecting…; docs/tests (`test_spa_chat_checked_in_caption_hardclaims_connected_badge`)
   then hardclaim **Connected**. A soft-accept recapture can reintroduce
   the honesty bug the 20s wait was meant to close.

**Action:** Do not swallow the wait; drop or tightly gate
`--allow-connecting` so it cannot overwrite `docs/screenshots/spa-chat.png`.

---

### D-07 — P1 — Dual pytest config — **RESOLVED**

**Path:** `pytest.ini` (kept). `pyproject.toml` `[tool.pytest.ini_options]` (removed).

**Original diagnosis, and why it was wrong:** this entry previously read
*"Both files set `DJANGO_SETTINGS_MODULE`, `testpaths`, `asyncio_mode`, and
warning filters. Pytest merges them."* **Pytest does not merge.** For a given
rootdir it takes the **first** config file it finds, in the order `pytest.ini`,
`pyproject.toml`, `tox.ini`, `setup.cfg`, and ignores the rest. So the situation
was never a benign "merge" — it was **one file entirely inert**, and pytest said
so on every single run:

```
configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)
```

That warning went unread, which is how a P1 item sat unfixed while the audit that
wrote it documented a merge that does not happen. Assuming a merge is what made
the keys look redundant enough to leave alone.

**What was actually dead** — the entire `pyproject.toml` block, including:

- `SWARM_SKIP_DOTENV=true` — the #1335 guard that stops `settings.py` loading the
  operator's real `~/.config/swarm/.env` (API_AUTH_TOKEN, DATABASE_URL) into the
  run. It only ever worked because `tests/conftest.py` *also* sets it by
  `os.environ.setdefault`. Two mechanisms, one live; the redundancy is what hid
  the rot.
- `DJANGO_ALLOW_ASYNC_UNSAFE=true` — set nowhere else. Genuinely absent from
  every bare `uv run pytest`, including CI.
- the `Marks applied to fixtures have no effect` filter for pytest 9.

**Fix:** migrated those keys into `pytest.ini`, deleted the dead block, corrected
`CONTRIBUTING.md`, and added
`tests/core/test_pytest_config_single_source.py`, which asserts the *resolved*
config via `request.config` and the live process env — not file text, so it
cannot be satisfied by a config file nothing reads.

**Also folded in:** the commented-out `timeout = 30` hang guard is now
`timeout = 600`. It was parked with "enable if we observe hangs in CI"; we do
observe them, and only one workflow job passed `--timeout=180`, so a hang in the
main job had no ceiling. 600s is a hang guard, not a perf budget — the full suite
runs in ~570s *total*.

**Not fixed here (still open, lower priority):** `pytest.ini` forces `--cov` and
`--cov-fail-under=0` while `[tool.coverage.report] fail_under = 70` in
`pyproject.toml` is overridden by that CLI flag on every pytest run. The two
gates can therefore never both bite. `log_cli`/`log_file = pytest.log` noise is
also untouched.

- `pytest.ini` `addopts = -ra --cov=src/swarm --cov-report=term-missing
  --cov-fail-under=0` — every invocation pays coverage; fail-under is
  **0**.
- `[tool.coverage.report] fail_under = 70` in pyproject — a second,
  conflicting gate if someone runs coverage separately.
- `log_cli = true` + `log_cli_level = INFO` + `log_file = pytest.log`
  — INFO logs for the full ~600-test suite. Known suite-slowness
  source; `pytest.log` is easy to leave dirty in the workspace.
- `CONTRIBUTING.md` says “Pytest is configured in `pyproject.toml`”
  and never mentions `pytest.ini`.
- `pytest.ini` comments out a `slow` marker; there is still no way to
  run `-m "not slow"`.

pytest-django specifics in the same pile:

- `tests/conftest.py` documents that overriding `django_db_setup` caused
  teardown flakes; `DJANGO_DEBUG` must be set **before** pytest-django
  imports `swarm.settings` (also mirrored in `src/swarm/settings.py`
  via `TESTING = 'pytest' in sys.modules`).
- `src/swarm/settings.py` `TESTING` forces DEBUG; production cookie/CSP
  defaults are **untestable** under the live settings module
  (`tests/unit/test_production_security_defaults.py` reimplements the
  block instead of importing settings).
- `pyproject.toml` filters `Marks applied to fixtures have no effect`
  (`PytestRemovedIn9Warning`) instead of removing fixture marks.

**Action:** Single config source (prefer pyproject). Make coverage
opt-in (`--cov` only in CI). Turn `log_cli` off by default. Add a real
`slow` marker. Stop filtering the fixture-mark warning; delete the marks.

---

### D-08 — P1 — `make test` vs CI pytest are different processes

**Path:** `scripts/run_tests.py`; `.github/workflows/python-pytest.yml`
(`uv run pytest`); `Makefile` `test` target.

**Why:** `run_tests.py` sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and
explicitly loads `django`, `asyncio`, `pytest_mock`, optional
`pytest_cov`. CI does **not** use that wrapper, so third-party plugins
autoload and `--cov` from `pytest.ini` always runs. Local `make test`
and GitHub can disagree on collection, warnings, and duration.

Also: CI matrix is Python **3.10 / 3.11 / 3.12** with `fail-fast:
false` — three full cov+log_cli suites per PR, no xdist
(D-17).

**Action:** One entrypoint. Either CI calls `scripts/run_tests.py` or
the wrapper is deleted and docs/Makefile match `uv run pytest`.

---

### D-09 — P1 — Unused root fixtures

**Path:** `tests/conftest.py`.

**Why:** Grep across `tests/` (definitions only at the fixture):

| Fixture | Used by tests? |
| --- | --- |
| `mock_openai_client` | **No** |
| `mock_model_instance` | **No** (also `pytest.skip`s if openai-agents import fails) |
| `authenticated_client` | **No** |
| `authenticated_async_client` | Shadowed by `tests/api/conftest.py` (that copy is used) |
| `mock_load_config` | Yes — `tests/views/test_blueprint_library_views.py` |
| `test_user` / `api_client` | Yes, but also redeclared locally (D-12) |

Dead fixtures still import `AsyncOpenAI` / `OpenAIChatCompletionsModel`
and request `db` for unused auth helpers — extra pytest-django setup
on any accidental request.

**Action:** Delete the three unused fixtures; keep auth helpers in
`tests/api/conftest.py` only.

---

### D-10 — P1 — Live-inference test in the default tree

**Path:** `tests/integration/test_memory_mem0_e2e.py`.

**Why:** Module docstring + `skipif`: requires `RUN_MEM0_E2E=1` **and**
a real `OPENAI_API_KEY`. mem0 local qdrant is on-disk; LLM + embedder
hit OpenAI. Timeout **300s**. Last recorded run (2026-06-11) got **401**
on a revoked key. Default CI skips it (good), but it is still collected
as `integration` with no `slow` marker, and it is the only test that
needs live inference.

Other “e2e” names are mocked or fake-backend:

- `tests/api/test_auth_operator_golden_path.py` — `AsyncMock` / no
  worker; CHANGELOG wording “proves live AsyncOpenAI streaming” is the
  **generated code path**, not a network call.
- `tests/api/test_moa_http_e2e.py` — `fake_responses` panel.
- `tests/integration/test_hybrid_moa_persona.py` — `moa_backend="fake"`.
- `tests/test_asgi_routing.py` — `mock_openai_streaming()`.

**Action:** Move mem0 live proof behind an explicit `live_inference`
marker (and document it). Do not add more key-gated tests to the
default path.

---

### D-11 — P1 — Visual suite duplicates capture bootstrap, misses REQ-5 chrome

**Path:** `tests/e2e_visual/conftest.py`;
`tests/e2e_visual/test_golden_journey.py`;
`scripts/capture_user_journey.py`.

**Why:** Both start `manage.py runserver --noreload`, migrate, create a
throwaway superuser, and drive Chromium. Ports 8326 vs 8321. Visual
tests still guard **old** regression classes (Tailwind 2kB CSS,
`card-bordered`, zero-text navbar, Daisy theme) and do **not** assert:

- Agents sidebar present on Django `/teams/` or SPA `/` `/chat`
- `os-action-card` size/class on Home or Settings
- Chat link on Django primary nav

So visual CI can pass on a styled **old** shell.

**Action:** Share one server/auth fixture. Add two cheap asserts for
Agents + `os-action-card`. Keep pixel goldens out of pytest (PNGs stay
docs).

---

### D-12 — P2 — Duplicate pytest-django fixtures

**Path:** `tests/conftest.py` (`test_user`, `api_client`);
`tests/api/conftest.py` (`test_user`, `authenticated_async_client`);
local `api_client` in `tests/views/test_{teams_api,library_api,chat_views,api_views}.py`
and `tests/api/test_moa_http_e2e.py`.

**Why:** Same `username='testuser'` constructed two ways
(`update_or_create` vs `get_or_create`). Five files ignore the root
`api_client(db)` and build a bare `APIClient()` (some without requesting
`db`). Fixture-resolution depends on directory conftest order — a
pytest-django footgun when a test is moved.

`tests/core/conftest.py` and `tests/blueprints/conftest.py` both define
the same autouse `clear_litellm_env`.

**Action:** One `api_client` / `test_user` in root or `tests/api/`.
Delete local copies. Merge the LiteLLM env fixture once.

---

### D-13 — P2 — SPA Playwright vs Vitest overlap; preview e2e absent from CI

**Path:** `webui/frontend/e2e/smoke.spec.ts`, `nav.spec.ts`,
`interaction.spec.ts`, `chrome.spec.ts`;
`webui/frontend/src/pages/__tests__/Dashboard.test.tsx`;
`webui/frontend/src/components/__tests__/AgentSidebar.test.tsx`;
`webui/frontend/src/pages/__tests__/ChatPage.test.tsx`.

**Why:**

| Behavior | Vitest | Playwright e2e | Python visual |
| --- | --- | --- | --- |
| Four Home cards / not rainbow | Dashboard.test.tsx | chrome.spec.ts | no |
| Agents hide/unhide | AgentSidebar.test.tsx | chrome.spec.ts | no |
| Theme persist | — | interaction.spec.ts | broken skip (D-05) |
| `#root` + Primary nav | — | smoke + nav | landing styled |
| Connected badge | ChatPage.test.tsx (mock WS) | no | exact Connected (D-04) |

Playwright e2e is `vite preview` on :4173 **without Django** (API
stubs in chrome.spec only). It cannot see the Django Agents pane or
WS Connected. That is fine if it runs; it does not (D-03).

**Action:** Keep Vitest as the fast REQ-5 contract. Run Playwright e2e
once in CI. Do not add a third copy of hide-from-sidebar.

---

### D-14 — P2 — Screenshot registry is a caption lockfile

**Path:** `tests/unit/test_screenshot_registry.py` (613 lines, 35 tests).

**Why:** Useful as an embed/existence gate. Harmful as a freeze layer:
it asserts exact nav phrases, `2026-08-19`, `0/45/45`, `12 of 38`,
`**Connected**`, `fs_introspect`, “ready green checkmarks”, Custom
Created **3**, and forbids `Connecting…`. A single honest recapture
(D-01) will require a large coordinated edit of docs **and** this file,
which discourages updating goldens.

**Action:** Keep file-existence + “every PNG has a registry row”. Move
pixel/caption facts to a capture manifest JSON. Drop date literals.

---

### D-15 — P2 — USERGUIDE scratch-path test

**Path:** `tests/core/test_userguide_captures.py`.

**Why:** Default `SCRATCH=/tmp/grok-goal-4567a1afab94/implementer`.
Skips when that tree is empty; only meaningful in one Cloud Agent
scratch. `tests/core/conftest.py` also bundles it with the slow-CLI
skip for `test_documented_cli_journey`.

**Action:** Delete or gate behind an explicit env that CI never sets.

---

### D-16 — P2 — Slow CLI subprocess tests, no `slow` marker

**Path:** `tests/core/test_documented_cli_journey.py`;
`tests/cli/test_config_init_command.py`, `test_moa_init_command.py`,
`test_launchers.py`; `tests/xdg_isolation.py`;
`tests/core/conftest.py` (`_cli_startup_ms` > 25s skip).

**Why:** Each call is `python -m swarm.core.swarm_cli` with a 30–60s
timeout. The documented journey runs list → install-executable →
launch → config add/list → wizard. The only speed escape hatch is a
session-level `--help` probe. `pytest.ini` still comments “Add markers
… slow”. Full CI pays this cost on three Python versions (D-08).

**Action:** Mark `@pytest.mark.slow`. Default CI: `-m "not slow"`.
Nightly or a single-version job runs the journey.

---

### D-17 — P2 — Unused / idle test tooling

**Path:** `pyproject.toml` `[project.optional-dependencies] test|dev`.

**Why:**

- `factory-boy` — no `factory.Factory` / `DjangoModelFactory` in
  `tests/`.
- `pytest-xdist` — not passed in CI (`-n`).
- `pytest-timeout` — installed; **no** global `timeout =` (commented
  in pytest.ini). Only
  `tests/unit/test_auth_hardening.py` (60s) and mem0 e2e (300s) mark
  timeouts.
- `pytest-env` listed in `test` extra; `run_tests.py` exists specifically
  to avoid needing it.

**Action:** Drop unused extras or start using them (xdist on unit-only
job; global timeout 30s).

---

### D-18 — P2 — CI frontend work duplicated, SPA e2e missing

**Path:** `.github/workflows/python-pytest.yml` job `frontend`;
`.github/workflows/visual-regression.yml`.

**Why:** Every PR builds the SPA twice (`build_frontend.sh` / `npm ci &&
npm run build`). Vitest runs only in visual-regression. Playwright e2e
runs nowhere. Python unit matrix does not need a frontend build except
for tests that read `dist/` (they generally skip or fail-fast only in
e2e_visual).

**Action:** One frontend job: install → `npm test` → `npm run test:e2e`
→ `npm run build` → upload `dist` or trigger visual pytest. Keep the
Python matrix keyless and browser-free.

---

## Cross-cutting notes (not separate ranks)

- **pytest-django import order:** `swarm.settings` sets `TESTING` from
  `sys.modules` before conftest. That is load-bearing; any runner that
  imports Django first without `DJANGO_DEBUG` will demand
  `DJANGO_SECRET_KEY` / `ALLOWED_HOSTS`. Document it next to the single
  pytest config (D-07).
- **`tests/e2e_visual` is opt-in** (`RUN_E2E_VISUAL=1`) so a local
  `uv run pytest` skips it — good. CI visual job is the only place those
  six tests run; they must stay honest after REQ-5 (D-04, D-05, D-11).
- **No Playwright `toHaveScreenshot` goldens** in
  `webui/frontend/e2e/`. Pixel freeze is entirely the docs PNG set
  (D-01), not a Playwright snapshot dir.
- **XSS view tests** (`tests/views/test_*xss*.py`) are static source
  checks, not live browsers — complementary, not duplicate of e2e.

---

## Suggested follow-up order (rewrite tickets, not this PR)

1. Recapture journey PNGs on REQ-5 chrome; fix Settings captions (D-01, D-02, D-14).
2. Put `npm run test:e2e` in CI; fix visual Connected + theme selectors (D-03, D-04, D-05).
3. Unify pytest config + CI entrypoint; delete unused fixtures (D-07, D-08, D-09, D-12).
4. Mark slow/live tests; stop paying cov+log_cli on every local run (D-10, D-16, D-17, D-18).
