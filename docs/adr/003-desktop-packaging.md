# ADR-003: Desktop packaging — local server + pywebview (Windows first)

- **Status:** Proposed (look-only; no installer, no runtime change in this PR)
- **Date:** 2026-09-04
- **Issue:** [#554](https://github.com/matthewhand/open-swarm/issues/554) (REQ-151)
- **Related:** [#529](https://github.com/matthewhand/open-swarm/issues/529) (launch spiel), [ADR-002](./002-config-ownership.md) / [#541](https://github.com/matthewhand/open-swarm/issues/541) (config + desktop paths), [#481](https://github.com/matthewhand/open-swarm/issues/481) (TUI — separate client), [ADR-001](../ADR-001-primary-ui.md) (Django + SPA chrome)
- **Supersedes:** none. Complements ADR-001 (what UI we show) and ADR-002 (where state lives). This ADR picks **how** a Windows user who will not run Docker gets that UI.

**Decision:** Copy **OpenMausBot’s product shape**, not its toolkit.

1. **Shape (same as OpenMausBot):** a local loopback ASGI server owns Django + the built SPA; a desktop window **owns that process** and navigates to `http://127.0.0.1:<port>/`. Desktop is a **pane of glass**. Native CLIs (`grok`, `agy`, `opencode`, Hermes, …) stay installed on the machine.
2. **Windows-first shell (not Electron):** **pywebview + WebView2**, frozen with **PyInstaller onedir** (portable zip / folder first). NSIS / signed GitHub Release is Phase 2.
3. **Do not bundle** Neon, Electron/Chromium, Ollama, or vendor CLIs. Do not write secrets into the repo.

This ADR is **feasibility-first**. It records what `main` (`8f99e136` at writing) already boots, what OpenMausBot actually ships, and then picks one stack. It does **not** add an installer, a `desktop/` tree, or CI publish jobs.

No secrets are documented here. Use `${VAR}` names only.

---

## Issue quote (REQ-151)

**Intent:** Users who won’t run Docker/compose still get a one-click local open-swarm with the WebUI, for Windows especially.

**Success (this Issue — Phase 0 only):**

1. Look-only comparison of packaging options vs OpenMausBot (Electron / Tauri / pywebview / NSIS + embedded server).
2. Recommend **one** option with pros/cons for bundling Django + SPA + optional local LLM proxies.
3. `Fixes` this Issue when the ADR merges. Split implement Issues from the ADR.
4. Phase 1–2 (installer, signed release) are **follow-ups**, not this PR.

**Constraints:** Park behind showoff-critical WebUI unless Matthew prioritizes. No secrets. macOS/Linux later. TUI (#481) is a different client of the same API.

---

## 1. Feasibility (what exists today)

Operating Swarm is already a **local web app**. The missing piece is a Windows-owned process + window, not a new UI.

| Piece | Today (`8f99e136`) | Desktop implication |
|---|---|---|
| HTTP + WebSocket | `swarm.asgi:application` — Django HTTP + Channels WS (`src/swarm/asgi.py`) | Need **ASGI** (uvicorn/daphne), not `runserver` / WSGI |
| Production launcher | `swarm-api` → `src/swarm/core/swarm_api.py` `uvicorn.run("swarm.asgi:application", …)` | Reuse this entry; **rebind host** (see §1.1) |
| Operator + chat UI | Django trailing-slash chrome + SPA `/` + `/chat` ([ADR-001](../ADR-001-primary-ui.md)); `dist/` gitignored, baked by `make frontend` / Docker Node stage | Freeze **prebuilt** `webui/frontend/dist` into the payload |
| DB | `DATABASE_URL` → Postgres; else `DJANGO_DB_NAME` / `SQLITE_DB_PATH`; **default `/tmp/db.sqlite3`** (`src/swarm/settings.py`) | Desktop **must** set a user-profile sqlite path. No Neon. |
| Config | ADR-002 hybrid: secrets in env; topology in XDG `swarm_config.json`; chats/prefs moving to Django | Desktop sets explicit `SWARM_*` / XDG-equivalent under the profile (see §5) |
| Native CLIs | Catalog in `src/swarm/core/cli_catalog.py` (`grok`, `agy`, `opencode`, …); compose **does not** bake them (`docker-compose.yml` header) | Desktop must inherit the **user PATH**. Do not vendor CLIs. |
| Existing “local app” | Pinokio sideload (`pinokio.js` / `pinokio/start.js`) is `docker compose up` → `http://127.0.0.1:8000` | Satisfies Docker users only. Out of scope for #554. |
| Freeze tool | `pyinstaller>=5.13.0` in `pyproject.toml`; used today for **blueprint** `swarm-cli install`, not the server | Already a dep; hard part is Django hidden imports, not installing PyInstaller |
| Icons | `assets/brand/` — “later installable / desktop / Pinokio icons” (`assets/brand/README.md`) | Reuse bee mark; no new UI chrome in this PR |

### 1.1 Boot defaults that are wrong for a desktop publish

These are not blockers for the ADR; they are **Phase 1 must-fix env**, not silent reuse of `swarm-api` defaults.

| Default | File | Why it fails on a Windows box |
|---|---|---|
| `HOST` / `--host` = `0.0.0.0` | `src/swarm/core/swarm_api.py` | Publishes the UI on every interface. Desktop binds **`127.0.0.1` only**. |
| Sqlite `NAME` = `/tmp/db.sqlite3` | `src/swarm/settings.py` | Not a durable Windows profile path; lost on reboot / missing on Win. |
| Prod (`DEBUG=False`) requires `${DJANGO_SECRET_KEY}`, `${DJANGO_ALLOWED_HOSTS}`, and an API token unless `${SWARM_ALLOW_NO_AUTH}` | `src/swarm/settings.py`, `CONFIGURATION.md` | First-run must **materialize** a secret **outside the repo** (see §5.2). |
| Prod Secure cookies | `SWARM_SECURE_COOKIES` default on when `DEBUG=False` | Loopback HTTP needs Secure cookies **off** or the session never sticks. |
| `X_FRAME_OPTIONS` `DENY` | `CONFIGURATION.md` / middleware | Fine: the window **navigates** to loopback. Do **not** iframe Django inside a foreign origin. |

Pinokio already sets `DJANGO_DEBUG=true` and `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1` (`pinokio/start.js`). A published desktop build should stay **`DEBUG=False`** with an explicit loopback allow-list, not ship a debug server.

---

## 2. OpenMausBot evidence (what “OMB-style” actually is)

Upstream: [milind-soni/OpenMausBot](https://github.com/milind-soni/OpenMausBot) (Matthew’s fork: `matthewhand/OpenMausBot`). User-facing remote label in this repo is **OpenMousBot** (REQ-59); the product name is OpenMausBot.

Read from that tree (not cloned into open-swarm):

| Fact | Evidence |
|---|---|
| Electron window + **local harness on loopback** | README: “One small harness server on `127.0.0.1` owns every agent process.” Data in `~/.openmausbot`. |
| Dev URL is IPv4 loopback on purpose | `electron/main.mjs`: `DEV_URL = … "http://127.0.0.1:5199"` — comment warns bare `localhost` can resolve to `::1` and paint a black window. Default packaged server port `8799`. |
| UI + server are **both TypeScript** | `package.json` `build` = `tsc` + `vite build`; `build:server` compiles the harness. `electron-builder.yml`: “compiled harness server (tsc → server/) … run on Electron’s own Node via `ELECTRON_RUN_AS_NODE`.” |
| Windows artifact | `electron-builder.yml` `win.target`: NSIS x64 + zip x64. One-click per-user NSIS. README ships `OpenMausBot-setup.exe`. Signing **not** configured; SmartScreen “unknown publisher” is documented. |
| Auto-update | `electron-updater` + `latest.yml` on public GitHub Releases. Phase 2 for us, not Phase 1. |
| CLIs are **host-native** | README: bots run on `claude` / `codex` / `grok` **installed on the machine** — “no new accounts, no proxy in the middle.” |

**What to copy:** loopback server, window owns lifecycle, host CLIs, user-profile data dir, Windows zip-then-NSIS, no secrets in git.

**What not to copy:** Electron as the runtime. OMB can run the harness **on Electron’s Node**. Operating Swarm’s server is Django / Channels / uvicorn (`src/swarm/asgi.py`, `swarm_api.py`). An Electron shell would still ship a **Python sidecar**. That is Chromium + Node + CPython — two runtimes — for a pane of glass.

Operating Swarm already talks to OpenMausBot as a **remote** (`kind=omb`, HTTP only, no source clone — `docs/REMOTE_HARNESSES.md`, FEATURE_STATUS §11b). Desktop packaging does not replace that remote; it packages *this* product.

---

## 3. Options (Windows publish first)

Score is for **Phase 1 portable Windows artifact** that starts Django+SPA and shows the WebUI. Installer / codesign / auto-update are Phase 2 for every row.

| Option | Window | Server | Extra runtime on disk | PATH / native CLIs | Win publish friction | Fit |
|---|---|---|---|---|---|---|
| **A. Electron + Python sidecar** (literal OMB toolkit) | Chromium | `swarm-api` child | Electron (~150 MB) **+** CPython/Django | Easy to strip PATH; need explicit user-env merge | `electron-builder` NSIS is proven (OMB) | Poor. Duplicates a browser we already have (WebView2) and a language we already ship. |
| **B. Tauri 2 + Python sidecar** | WebView2 | `swarm-api` sidecar | Tiny Rust shell **+** CPython/Django | Sidecar env is controllable | Rust in CI; good later updater | Strong Phase 2 shell. Extra language for Phase 1 with no size win (Python dominates). |
| **C. pywebview + in-process / sibling uvicorn** | WebView2 | Same frozen Python | CPython/Django only | Same process / inherited env | PyInstaller onedir zip; Inno/NSIS later | **Pick for Windows first.** One toolchain we already depend on. |
| **D. NSIS / zip + default browser** | None (Edge/Chrome tab) | Frozen `swarm-api` | CPython/Django only | Good | Fastest zip | Honest fallback if the window slips. Worse lifecycle: closing the tab leaves the server. |
| **E. Pinokio / Docker Compose** | Pinokio / browser | Container `swarm-api` | Docker Engine | CLIs **do not** work unless mapped (`docker-compose.yml`) | Already shipped (`start.js`) | Rejected for #554 audience (“won’t run Docker”). Keep as the container path. |
| **F. PWA / “install this site”** | Browser | User-started server | None | n/a | None | No one-click server. Not a publish artifact. |
| **G. Briefcase / native rewrite** | Native | Would fork the stack | Large | Unclear | High | Rejected. ADR-001 UI stays Django+SPA. |

**Optional local LLM proxies** (Ollama, LiteLLM, a local OpenAI-compatible `:8000/v1`): **do not bundle** in v1. The app already speaks HTTP remotes + LLM profiles ([ADR-002](./002-config-ownership.md), `docs/REMOTE_HARNESSES.md`). Point `${OPENAI_BASE_URL}` / a remote at `http://127.0.0.1:11434/v1` (or whatever the user runs). Shipping a GPU stack inside the desktop zip is a different product.

**PyInstaller vs embeddable CPython:** either can host uvicorn. Prefer **PyInstaller onedir** because it is already a project dependency and produces one folder to zip. One-file mode extracts to `%TEMP%` on every launch — avoid for Django. Hidden-import work is the implement risk (Channels, uvicorn, openai-agents); that is true under Electron/Tauri too.

---

## 4. Decision details

### 4.1 Phase 1 (implement later — not this PR)

A thin `swarm-desktop` entry (name bikeshed OK) that:

1. Resolves a **user-profile home** (see §5) and exports ADR-002 env (`SQLITE_DB_PATH` / `DJANGO_DB_NAME`, `SWARM_CONFIG_PATH` or XDG-equivalent, `SWARM_USER_DATA_DIR`, `SWARM_CHAT_DIR`, `SWARM_ATTACHMENTS_DIR`).
2. Ensures a first-run `${DJANGO_SECRET_KEY}` file **in that profile** (never the git tree).
3. Sets `${HOST}=127.0.0.1`, `${DJANGO_ALLOWED_HOSTS}=127.0.0.1,localhost`, `${DJANGO_CSRF_TRUSTED_ORIGINS}=http://127.0.0.1:<port>,http://localhost:<port>`, `${SWARM_SECURE_COOKIES}=false`, `${DJANGO_DEBUG}=false`.
4. Starts `uvicorn` on `swarm.asgi:application` (same as `swarm-api`), **one worker**, loopback only. Pick a free port if 8000 is taken; persist the chosen port in the profile.
5. Opens a **pywebview** window at `http://127.0.0.1:<port>/` (IPv4, not bare `localhost` — same pitfall OMB documented).
6. On window close: stop uvicorn. Single-instance: second launch focuses the existing window.
7. Ships as a **portable onedir zip** on a GitHub Release draft. No NSIS in Phase 1.

WebView2 is present on current Windows 10/11. If it is missing, fail with a link to Microsoft’s evergreen runtime — do not silently fall back to IE.

### 4.2 Phase 2 (split Issues)

- Inno or NSIS per-user shortcut (OMB-like `*-setup.exe` stable name + versioned artifact).
- Authenticode + SmartScreen notes (OMB ships unsigned today; we can too at first, but document it).
- Optional Tauri **shell swap** if we want a first-class updater without growing pywebview. The frozen `swarm-api` sidecar stays. **Do not start Electron** for the updater.
- macOS / Linux ports of the same shape (WebKit / WebKitGTK).
- Auto-update only after signing policy is explicit (OMB’s `publisherName` trap: set it without a cert and updates die).

### 4.3 What the window is not

- Not a rewrite of the SPA or Django templates (ADR-001 stands; Antigravity WebUI work stays untouched).
- Not a replacement for `swarm-cli` or host CLIs (#554 success 4; #481 TUI is another client).
- Not a sandbox that hides `grok` / `agy` from the user’s login.
- Not a Neon / Fly / Pinokio substitute. Those remain the server/container paths.

---

## 5. Desktop profile vs ADR-002

ADR-002 already says Docker ephemeral needs **RW config + RW data** volumes. Config-root unify (#1434) made discovery and `get_user_config_dir_for_swarm()` the same directory: `$XDG_CONFIG_HOME/swarm` or `~/.config/swarm`. A Windows desktop must **not** rely on Unix `~/.config`.

**Pick for desktop (implement later):** set explicit env at process start so discovery cannot split:

| Concern | Desktop SoT | Notes |
|---|---|---|
| Secrets / flags | Process env loaded from a **profile `.env`** the app may create **once** on first run for `${DJANGO_SECRET_KEY}` (and optional `${API_AUTH_TOKEN}`) | ADR-002: app does not rewrite operator `.env` in general. Desktop first-run is the exception: generate into `%LOCALAPPDATA%\OpenSwarm\swarm\` (or `SWARM_USER_DATA_DIR`), chmod/ACL user-only, then **load** it. Settings UI still never shows plaintext or writes provider keys. |
| Harness topology | `SWARM_CONFIG_PATH` = `{profile}\swarm_config.json` | Same file `swarm-cli` / Settings persist helpers already write. |
| Sibling JSON | Same directory (`team_rosters.json`, …) | ADR-002 table. |
| Sqlite + attachments + chat JSON | `{profile}\data\` (`DJANGO_DB_NAME`, `SWARM_CHAT_DIR`, `SWARM_ATTACHMENTS_DIR`) | Never `/tmp/db.sqlite3`. Never `${DATABASE_URL}` / Neon. |
| SPA prefs | Browser `localStorage` inside WebView2 until #540 | Same as Chrome today; wiping the webview partition wipes favourites unless #540 lands. |

Config-root unify landed in #1434. Desktop freeze must still set `XDG_CONFIG_HOME` (or `SWARM_CONFIG_PATH` for `swarm_config.json`) at process start. Sibling JSON follows `get_user_config_dir_for_swarm()`, not the directory of `SWARM_CONFIG_PATH`, so a Windows profile path has to be that config root — not a second folder.

### 5.2 First-run secret materialization

Published `DEBUG=False` refuses to boot without `${DJANGO_SECRET_KEY}`. Options:

| Approach | Verdict |
|---|---|
| Commit a key | **Forbidden.** |
| Prompt the user to paste a key | Hostile for announce. |
| Generate `secrets.token_urlsafe(50)` into the profile `.env` on first launch | **Pick.** Same class as “ops created the file”; the user is the ops. |
| In-memory only | Session cookies die every launch. Rejected. |

Do not persist provider keys (`${OPENAI_API_KEY}`, `${OMB_API_KEY}`, …) except as `${VAR}` names in `swarm_config.json` (already the remotes rule).

---

## 6. Native tools and local LLM proxies

**CLIs:** `src/swarm/core/cli_catalog.py` invokes `grok`, `agy`, `opencode`, … from `PATH`. Compose already documents that those binaries + their auth dirs are **host-bound** and cannot be baked. Desktop is the **native** path: inherit the user’s environment (Windows: user + machine PATH, not the stripped GUI-app PATH). If a CLI is missing, existing honest empty `models: []` / missing-binary behaviour stands — do not ship a fake grok.

**Remotes:** Hermes / OpenMousBot / Rakazo / nested swarm stay HTTP remotes the user + adds (REQ-59). Packaging this app does not embed those products.

**Local LLM proxies:** optional, already a URL. Document “install Ollama (or LiteLLM) separately; add an LLM profile.” No extraResources GPU blob in v1.

---

## 7. Follow-up implement Issues (parked)

Do not implement in this PR. Suggested filings (titles only):

1. **`swarm-desktop` loopback boot** — env profile from §5; bind `127.0.0.1`; generate first-run `${DJANGO_SECRET_KEY}`; `uvicorn` one worker; migrate sqlite off `/tmp`. Tests: boot without `DATABASE_URL`; refuse `0.0.0.0` in desktop mode.
2. **pywebview window + single-instance** — navigate to IPv4 loopback; shutdown on close; no iframe. Tests: headless skip on CI without WebView2; unit-test URL builder (`127.0.0.1`, never `localhost`).
3. **PyInstaller onedir spec for the server+SPA** — `make frontend` then freeze; hiddenimports for Channels/uvicorn; onedir zip artifact. Tests: smoke `swarm-desktop --help` / import freeze list in CI (Linux can still compile the spec; Windows artifact is a later runner).
4. **Windows PATH merge for GUI-spawned process** — so `grok` / `agy` resolve. Tests: fixture PATH; do not vendor binaries.
5. **Unify XDG helpers** (ADR-002 #3) — required so desktop + `swarm-cli` share one folder on Windows.
6. **Phase 2 NSIS/Inno + GitHub Release** — stable `OpenSwarm-setup.exe` name beside versioned zip; unsigned SmartScreen copy until a cert exists. No `publisherName` in an updater config without a cert.
7. **Docs / announce** — README download button only after an artifact exists. Pair with #529 spiel; do not claim a desktop app in FEATURE_STATUS until the zip boots.

---

## 8. Consequences

- Announce path: a Windows zip that is **the same WebUI** as Docker/Web, without Docker.
- Maintainers: one new Python entry + a spec file; **no** Electron version treadmill; Tauri remains an optional Phase 2 shell.
- Users: install host CLIs themselves (same as OMB / same as native `swarm-api`).
- This PR: documentation only. `Fixes` #554 when merged.

---

## 9. Rejected alternatives (short)

- **Electron first** — correct for a Node harness (OMB). Wrong once the server is Django.
- **Tauri first** — good shell, extra CI language before we can freeze Python.
- **Browser-only zip as the recommended end state** — acceptable **fallback**, not the pick (orphaned uvicorn).
- **Pinokio as the Windows publish** — Docker, and CLIs stay broken without manual maps.
- **Bundling Ollama / a local GPU proxy** — size, licensing, and support; use HTTP profiles instead.
- **Rewriting the UI native** — contradicts ADR-001.
