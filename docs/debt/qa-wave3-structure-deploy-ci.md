# QA wave 3 — SCOPE D deploy & CI layout (look-only)

**Status:** look-only structure audit. No product, deploy, workflow, Makefile,
`pytest.ini`, or compose/Fly/oracle file was changed. This PR **adds this
file only**.

**Issue:** [#452](https://github.com/matthewhand/open-swarm/issues/452)
(REQ-95). `Refs #452` — not Fixes.

**As-of:** `origin/main` @ `344a6986` (includes Pinokio `#375`, ASGI SPA
buffer `#428`, wave1 tests/CI `#426`).

**Method:** static read of `Dockerfile*`, `docker-compose*.yml`,
`docker-entrypoint.sh`, `deploy/`, `fly.toml`, `.github/`, `Makefile`,
`pytest.ini`, and `tests/` **folder names** (plus stray top-level files).
`pinokio.js` / `start.js` were read **only as a deploy surface** (they
exec `docker compose`). No host bounce. No Fly/oracle restart. No Neon.
No secrets. No live LAN URLs. Pre-existing `golden-journey` red is a
**HOLD** — see [qa-wave1-tests-ci.md](./qa-wave1-tests-ci.md); this file
does not re-rank D-01…D-18.

**Out of scope (other REQ-95 clouds):**

- **A** — root `*.md` / `*.js` / `*.patch` / `scripts/` / `pyinstaller_specs`
- **B** — `src/swarm/`, `webui/`, Django vs SPA
- **C** — `docs/` vs root guides

`scripts/run_tests.py` and `scripts/build_frontend.sh` live under **A**
but are named here because Make / CI call them.

---

## How to read the table

| Column | Meaning |
| --- | --- |
| **load-bearing** | **Y** = a live host, CI job, Pinokio menu, or in-tree test *string-locks* this path today. **N** = nothing calls it (safe to archive later). **?** = referenced in comments/docs only, or a no-op flag. |
| **proposed action** | keep / move / merge / delete / archive — **proposal only**. CoS + Matthew pick before any implementer Issue. |

Kind tags used in notes: **orphan** (copied into the image or tree but never
exec’d), **overlap** (two entrypoints start the same ASGI app differently),
**stale path** (script points at a tree that no longer exists), **host-coupled**
(changing it would bounce a live machine).

---

## 1) Inventory

| Path | Role | Load-bearing | Proposed action |
| --- | --- | --- | --- |
| `Dockerfile` | Multi-stage image: Node 22 builds gitignored SPA `dist/`, then `python:3.11-slim` `pip install .`, `CMD` = optional swapfile + `migrate` + `uvicorn swarm.asgi:application`. Locked by `tests/unit/test_plan_a_prod_gates.py` (`uvicorn` present, `manage.py runserver` absent). | **Y** | **keep** at repo root (Fly `[build] dockerfile`, compose `build.context: .`, Hub workflow `file: Dockerfile`). Move only with a coordinated Fly+compose+CI change. |
| `docker-entrypoint.sh` | Orphan shell: adds hardcoded `echocraft` blueprint, copies migrate logic, **`exec python manage.py runserver`**. No `ENTRYPOINT` in `Dockerfile`. No compose `entrypoint:`. Grep across yml/toml/md/sh finds **zero** callers. Not in `.dockerignore`, so it is still copied into the image and then ignored. | **N** | **delete** (later) or **archive** under `docs/archive/`. Do **not** wire it as `ENTRYPOINT` — that would put live containers on `runserver` and fail the Plan A gate. |
| `docker-compose.yml` | Production-ish `swarm` service: build local `open-swarm:local`, publish **`:8000`**, auth **on** (must not hard-set `SWARM_ALLOW_NO_AUTH: "true"` — locked by Plan A + Pinokio tests), `SWARM_RUNTIME=sandbox-home`, XDG config/state bind-mounts, `/health` healthcheck, `SWARM_UVICORN_WORKERS=1`. Uses image `CMD` (no command override). | **Y** | **keep**. Pinokio `start.js` is `docker compose up` against this file. |
| `docker-compose.dev.yml` | Dev overlay: `ports: !override` **`8002:8000`**, bind-mount `.:/app`, `PYTHONPATH=/app/src`, `uvicorn --reload`, `DJANGO_DEBUG=true`. Comments name the oracle host port map (`8000=netbox`, `8001=native open-swarm`). | **Y** | **keep**. `make dev` always passes `-f` this file **last**. |
| `docker-compose.override.example.yml` | Documented catalog of host CLI bind-mounts (claude / grok / gemini / codex / opencode). Users copy to gitignored `docker-compose.override.yml`. | **Y** (as the documented template) | **keep** next to the base compose file. Do not bake CLI mounts into the base file. |
| `docker-compose.override.yml` | Host-coupled CLI map (gitignored). `Makefile` `DEV_OVERRIDE := $(wildcard …)` auto-includes it for `make dev`. Plain `docker compose up` (Pinokio) also auto-merges it when present. | **Y** on hosts that created it; **N** in git | **keep** gitignored. Never commit a real one. |
| `.dockerignore` | Keeps `.env`, `.git`, `.github`, `docs/`, `tests/`, compose files, `fly.toml`, `Makefile`, `webui/frontend/dist` out of the build context. SPA `dist` is copied from the frontend stage instead. | **Y** | **keep**. Does **not** exclude `docker-entrypoint.sh` (harmless until someone exec’s it). |
| `fly.toml` | Fly app `open-swarm`, region `syd`, `[build] dockerfile = 'Dockerfile'`, `PORT=8000`, `SWAPFILE_PATH=/mnt/sqlite_data/swapfile`, volume `sqlite_data`, HTTP check `GET /health` Host `open-swarm.fly.dev`, `min_machines_running = 1`. Locked by `test_fly_toml_http_health_check_enabled`. | **Y** | **keep** at repo root until an implementer also edits `flyctl deploy -c`. Moving it **bounces** Fly. |
| `deploy/oracle/open-swarm-oracle.service` | systemd **user** unit: native `.venv` `uvicorn` on **`127.0.0.1:8001`**, `RestartPreventExitStatus=78`, placeholder `YOURUSER` / `CHANGE_ME_*`. Runbook: `docs/ORACLE_DEPLOY.md`. | **Y** | **keep**. Copied onto the oracle host (`~/.config/systemd/user/`). Editing ExecStart/ports **bounces** `:8001`. |
| `deploy/oracle/nginx-open-swarm.conf` | nginx TLS terminator → `127.0.0.1:8001`, 600s proxy timeouts, bearer passthrough. Placeholders `oracle.example.com`. | **Y** | **keep**. Live copy lives under `/etc/nginx/sites-*`. |
| `deploy/` (dir) | Only `oracle/` today. No `deploy/docker/`, no `deploy/fly/`. | **Y** (as the oracle home) | **keep** the oracle pair. Optional later: add siblings *without* moving Fly/compose until hosts are planned. |
| `.github/workflows/python-pytest.yml` | PR/push `main`: Node 22 `build_frontend.sh` job + Python **3.10/3.11/3.12** `uv run pytest` (`fail-fast: false`). **Not** `make test` / `scripts/run_tests.py`. | **Y** | **keep**. Dual-runner vs Make is wave1 **D-08** — do not “fix” here. |
| `.github/workflows/visual-regression.yml` | PR/push `main`: `npm test` + `npm run build` + `pytest tests/e2e_visual` with `RUN_E2E_VISUAL=1`. | **Y** (job exists) / **HOLD** (suite red) | **keep** the file. Do not rewrite predicates. Cite [qa-wave1-tests-ci.md](./qa-wave1-tests-ci.md) HOLD. |
| `.github/workflows/docker-io-fly-deploy.yml` | Push `main` + `workflow_dispatch`: Buildx push `*/open-swarm:latest` to Docker Hub, then `flyctl deploy -c fly.toml --wait-timeout 300`. Uses `actions/checkout@v3`. Passes unused build-arg `INSTALL_CARGO=true` (Dockerfile has no `ARG INSTALL_CARGO`). | **Y** | **keep**. This is the **live Fly bounce path**. Hub image is **not** what Fly runs (see §2). |
| `.github/workflows/publish.yml` | GitHub Release → PyPI; `workflow_dispatch` → TestPyPI. Trusted publishing + token fallback. | **Y** | **keep**. Unrelated to container hosts. |
| `.github/` (dir) | **Only** those four workflows. No `dependabot.yml`, `CODEOWNERS`, `ISSUE_TEMPLATE`, `PULL_REQUEST_TEMPLATE`. | **Y** | **keep**. Adding templates is out of this wave. |
| `Makefile` | Mixed: `dev` (compose stack on `:8002`), `test` → `scripts/run_tests.py`, `frontend` → `build_frontend.sh`, plus shim/PyInstaller blueprint packaging (`build-shim`, `build-all-executables`, `build-all-pyinstaller`). | **Y** (`dev`/`test`/`frontend`); **?** (legacy `build` / `build-all-pyinstaller`) | **keep** at repo root. Later: split packaging targets or point them at `build_*.py` (scope A). Do not change `dev` port **8002**. |
| `pytest.ini` | **The** pytest config: `testpaths = tests`, always-on `--cov`, `log_cli=true`, `log_file = pytest.log`. Was one of two competing sources. | **Y** | **keep** — it is now the single source of pytest config. The competing `pyproject.toml` `[tool.pytest.ini_options]` was removed, not this file: the wave1 **D-07** unify ticket is done, and it was the *pyproject* half that was dead. Do not re-add a second config source. |
| `tests/conftest.py` | Root pytest-django fixtures. | **Y** | **keep**. Fixture *quality* is wave1 D-09/D-12 — not this file. |
| `tests/swarm_config.json` | Fixture config for collected tests. | **Y** | **keep**. |
| `tests/xdg_isolation.py` | Shared HOME/XDG helper (not a `test_*.py`). | **Y** | **keep** or later **move** to `tests/helpers/`. |
| `tests/test_agent_router.py` | Operator / Agent Router HTTP suite at `tests/` root (`/v1/agents/…`, landed with `#321`). Not under `tests/api/` or `tests/blueprints/`. | **Y** | later **move** → `tests/api/` (or `tests/blueprints/`). |
| `tests/test_asgi_routing.py` | Websocket/ASGI suite living at `tests/` root. | **Y** | later **move** → `tests/asgi/` (or `tests/websocket/`). |
| `tests/test_consumers.py` | Channels consumer suite at `tests/` root. | **Y** | later **move** with the ASGI file. |
| `tests/test_core_filter_messages.py` | Core unit tests at `tests/` root (not under `tests/core/`). | **Y** | later **move** → `tests/core/`. |
| `tests/test_core_truncate_message_history.py` | Same. | **Y** | later **move** → `tests/core/`. |
| `tests/test_core_update_null_content.py` | Same. | **Y** | later **move** → `tests/core/`. |
| `tests/api/` | 19 `test_*.py` — HTTP /v1 + auth. | **Y** | **keep**. |
| `tests/blueprints/` | 30 `test_*.py`. | **Y** | **keep**. Overlaps `tests/unit/blueprints/` (2 files) — later **merge** folders, not test bodies. |
| `tests/cli/` | 9 `test_*.py`. | **Y** | **keep**. |
| `tests/core/` | 55 `test_*.py`. | **Y** | **keep** (receive the three stray `test_core_*.py`). |
| `tests/e2e_visual/` | Golden-journey (`conftest.py`, `test_golden_journey.py`, artifacts gitignored). Opt-in `RUN_E2E_VISUAL=1`. | **Y** / **HOLD** | **keep** path. Do not relocate while the HOLD is red. Quality: [qa-wave1-tests-ci.md](./qa-wave1-tests-ci.md). |
| `tests/herdr/` | 1 `test_*.py` (`test_herdr_client.py`). | **Y** | **keep**. |
| `tests/integration/` | 3 `test_*.py` (includes live mem0 gate — wave1 D-10). | **Y** | **keep**. |
| `tests/mcp/` | 8 `test_*.py`. | **Y** | **keep**. |
| `tests/services/` | 4 `test_*.py`. | **Y** | **keep**. |
| `tests/unit/` | 44 `test_*.py` including Plan A compose/Fly string-locks and Pinokio script locks. | **Y** | **keep**. |
| `tests/unit/blueprints/` | 2 files (`hybrid_moa`, `moa_orchestrator`). | **Y** | later **merge** into `tests/blueprints/` (folder only). |
| `tests/utils/` | 7 `test_*.py`. | **Y** | **keep**. |
| `tests/views/` | 19 `test_*.py`. | **Y** | **keep**. |
| `tests/system/` | **0** pytest files. Nine `test_*.sh` that pipe `/quit` into `python blueprints/<name>/blueprint_*.py` (repo-root `blueprints/` **does not exist**; packages live under `src/swarm/blueprints/`). Includes `test_django_chat.sh` (django_chat retirement is scope B / `#419`). Not referenced by Makefile or workflows. | **N** | **archive** or **delete** later. Do not “fix” the paths in this wave. |
| `pinokio.js` | Pinokio menu (Install / Start / Update / Open App). **Root path is a Pinokio contract** (scope A owns the JS). Deploy fact: Start → `start.js`. | **Y** | **keep** at repo root. Do not move into `deploy/`. |
| `start.js` | `docker compose up` + `SWARM_RUNTIME=sandbox-home` + `ENABLE_WEBUI=true` + `DJANGO_DEBUG=true` + `local.set` `http://127.0.0.1:8000`. Locked by `tests/unit/test_pinokio_scripts.py`. | **Y** | **keep** at repo root. |
| `install.js` / `update.js` | Scope A files. Deploy fact only: `docker compose build` / `git pull` then re-install. | **Y** | **keep** at repo root (not this tidy). |

**Adjacent (not owned by D, cited because CI/Make call them):**
`scripts/run_tests.py` (Make `test`; wave1 D-08),
`scripts/build_frontend.sh` (`python-pytest.yml` `frontend` job + Make
`frontend`), `pyproject.toml` `[tool.pytest.ini_options]` (wave1 D-07).

---

## 2) Entrypoint overlap (compose / dev / override / Fly / Pinokio / oracle)

Every serious start path aims at the same ASGI object
(`swarm.asgi:application`) except the **orphan** `docker-entrypoint.sh`.
They disagree on **who builds the image**, **which port**, **reload**,
**auth/debug**, and **whether host `$HOME` is mounted**.

```text
                    ┌─ Dockerfile CMD ─────────────────────────────┐
                    │  swapfile? → migrate → uvicorn :$PORT        │
                    └──────────────────────────────────────────────┘
                                      ▲
         docker compose up            │           flyctl deploy
         (Pinokio start.js,           │           (fly.toml dockerfile)
          README API quickstart)      │
                │                     │                    │
                ▼                     │                    ▼
     docker-compose.yml ──────────────┘           Fly machine :8000
     host :8000, sandbox-home,                    SWAPFILE_PATH on volume
     auth ON, no --reload                         /health check
                │
                │  + docker-compose.override.yml   (optional, gitignored)
                │       host CLI binaries + auth dirs
                │
                │  + docker-compose.dev.yml        (make dev only)
                ▼
     host :8002, bind-mount source, uvicorn --reload, DJANGO_DEBUG=true

     oracle systemd (no Docker)
     127.0.0.1:8001 uvicorn --workers 1  ← nginx :443
     implied bare-metal (SWARM_RUNTIME unset)
```

| Surface | How the process starts | Host port | Image / venv | Reload | Runtime / auth notes |
| --- | --- | --- | --- | --- | --- |
| `Dockerfile` `CMD` | `uvicorn swarm.asgi:application --host 0.0.0.0 --port $PORT --workers ${SWARM_UVICORN_WORKERS:-1}` after migrate | in-container `$PORT` (default 8000) | image site-packages | no | Swapfile only if `SWAPFILE_PATH` set (Fly). |
| `docker-compose.yml` | **inherits CMD** (no `command:`) | **8000:8000** | `open-swarm:local` build | no | `SWARM_RUNTIME=sandbox-home`; auth required unless `.env` opts out. `$HOME` config+state mounted. |
| `docker-compose.dev.yml` | **overrides** CMD → `migrate --fake-initial` + `uvicorn --reload` | **8002:8000** | same image + bind-mount + `PYTHONPATH=/app/src` | yes | `DJANGO_DEBUG=true`. Explicit `-f` list **skips** auto-merge of override unless `make dev` adds it. |
| `docker-compose.override.yml` | env + volume merge only | (inherits) | (inherits) | (inherits) | Host CLIs. Auto-merged by *unqualified* `docker compose up` (Pinokio). |
| Pinokio `start.js` | `docker compose up` (no `-f`, no `--build`) | **8000** (compose default) | whatever `install.js` built | no | Forces `sandbox-home`, `ENABLE_WEBUI=true`, **`DJANGO_DEBUG=true`**. Opens `http://127.0.0.1:8000`. Will pick up a local override if the sideload clone has one. |
| Pinokio `install.js` | `docker compose build` only | — | builds image | — | Copies `.env.example` → `.env` if missing. |
| Fly `fly.toml` + `docker-io-fly-deploy.yml` | `flyctl deploy` **rebuilds from `Dockerfile`** (not `image =` the Hub tag) | public 443 → 8000 | Fly builder, then volume `/mnt/sqlite_data` | no | Hub job still pushes `:latest` — **that tag is unused by the deploy step**. CI `--wait-timeout 300` vs `fly.toml` `wait_timeout = "20m"`. |
| Oracle unit | `.venv/bin/uvicorn … --host 127.0.0.1 --port 8001 --workers 1` | **8001** localhost | host venv, **no container** | no | CLIs already on PATH. nginx terminates TLS. |
| `docker-entrypoint.sh` | `manage.py runserver` | `$PORT` | would be image, if anyone exec’d it | Django autoreload | **Not in any live path.** Adds `echocraft` from `/app/blueprints` (that tree is not the current package layout). |

**Overlap that matters (proposal, not a rewrite):**

1. **Two “production compose” stories.** Pinokio and the README quickstart
   are unqualified `docker compose up` → base file + optional override.
   `make dev` is a *different* file list and a *different* port, on
   purpose, so it can sit beside oracle `:8001` and netbox `:8000`.
   That split is load-bearing. Do not collapse them.
2. **Hub push ≠ Fly boot.** `docker-io-fly-deploy.yml` builds a
   multi-arch Hub image, then Fly ignores it and builds from the
   Dockerfile again. Later tidy can drop one of those builds — but
   dropping the wrong one **bounces** `open-swarm.fly.dev`.
3. **Three migrate implementations.** Dockerfile `CMD`,
   `docker-compose.dev.yml` `command`, and `docker-entrypoint.sh` each
   copy a migrate block. Only the first two run today. Dedup later
   inside the image — do not add a fourth.
4. **`SWARM_RUNTIME` is compose/Pinokio-only.** Oracle (native) leaves
   it unset (unknown / implied bare-metal per `CONFIGURATION.md`).
   Do not “fix” the unit to send `sandbox-home`.
5. **Pinokio debug vs compose prod defaults.** `start.js` forces
   `DJANGO_DEBUG=true` on top of a compose file that defaults
   `DJANGO_DEBUG=false`. Intentional for sideload; do not “align”
   without a Pinokio ticket (scope A + tests that lock the env).

`DEVELOPMENT.md` “Docker Deployment Details” still describes a
**pre-built image** and mounts of `./blueprints` / `./swarm_config.json`
/ `./db.sqlite3`. That paragraph is **stale** versus today’s compose
file. Honesty edit is **scope C** — do not touch root guides here.

---

## 3) Proposed tidy layout

Goal: one place humans look for “how does this boot?”, without moving
anything that Fly, Pinokio, or the oracle host resolve by **relative
path from the repo root**.

```text
# Stay at repo root (contracts)
Dockerfile                         # Fly + compose + Hub workflow
docker-compose.yml
docker-compose.dev.yml
docker-compose.override.example.yml
fly.toml                           # flyctl deploy -c fly.toml
Makefile
pytest.ini                         # until D-07 merges into pyproject
pinokio.js  start.js  install.js  update.js

deploy/
  oracle/                          # already correct
    open-swarm-oracle.service
    nginx-open-swarm.conf
  # optional later, only after host PRs:
  # docker/   (copies or includes — not a silent move)
  # fly/      (would require fly.toml path change)

.github/workflows/                 # keep four files; no extra nesting
  python-pytest.yml
  visual-regression.yml            # HOLD
  docker-io-fly-deploy.yml
  publish.yml

tests/
  conftest.py
  swarm_config.json
  helpers/xdg_isolation.py         # move from tests/xdg_isolation.py
  asgi/                            # move test_asgi_routing.py, test_consumers.py
  api/                             # also receives test_agent_router.py
  blueprints/  cli/  core/         # core/ absorbs test_core_*.py
  e2e_visual/                      # do not move while HOLD
  herdr/  integration/  mcp/
  services/  unit/  utils/  views/
  # delete or docs/archive/tests-system/ the nine tests/system/*.sh
```

**What “tidy” is *not*:** renaming the compose service (`swarm`),
changing published ports, folding `dev.yml` into the base file, or
moving Pinokio JS under `deploy/` (Pinokio +
`tests/unit/test_pinokio_scripts.py` require those filenames at root).

**Makefile later split (optional):** keep `dev` / `test` / `frontend` /
`help` at root; park `build-*` / `build-all-pyinstaller` next to
`build_all_blueprints.py` (scope A) so deploy readers stop triaging
PyInstaller targets as “how to boot the API”.

---

## 4) Do not do yet

Especially anything that would bounce a live host.

| Do not | Why |
| --- | --- |
| Edit `fly.toml`, rename the Fly app, change `internal_port`, disable `[[http_service.checks]]`, or retarget `flyctl deploy` | **Bounces** `open-swarm.fly.dev`. Health-check path is string-locked. |
| Edit `.github/workflows/docker-io-fly-deploy.yml` (Hub tags, `flyctl` args, secrets names) | Push-to-`main` **deploys**. Even a “drive-by” action-version bump can roll machines. |
| Change oracle unit `ExecStart`, port **8001**, or nginx `proxy_pass` | **Bounces** the native gateway + public HTTPS. Live copies are *on the host*, not auto-synced from git. |
| Change compose published **8000** or `make dev` **8002** | Pinokio Open App is `:8000`. Dev `:8002` exists so it does not steal netbox `:8000` or oracle `:8001`. |
| Set `Dockerfile` `ENTRYPOINT` to `docker-entrypoint.sh` | Switches the container from **uvicorn ASGI** to **`runserver`**. Breaks websockets / Plan A test. Would bounce every compose + Fly boot. |
| Delete or rewrite `docker-entrypoint.sh` in the same PR as a Dockerfile change | Fine later as a *delete-only* docs/debt follow-up. Not bundled with a live CMD edit. |
| `FACTORY_RESET_DATABASE=True` (or equivalent) on Fly/oracle | Dockerfile/entrypoint honor this and **delete** the SQLite file. |
| Merge `pytest.ini` into `pyproject.toml` here | Wave1 **D-07**. A merge changes every local + CI invocation. |
| Point CI at `make test` / `scripts/run_tests.py` here | Wave1 **D-08**. Different plugin autoload. Can disagree with the green Python matrix. |
| Rewrite `visual-regression.yml` or `tests/e2e_visual/` | **HOLD.** Pre-existing red. [qa-wave1-tests-ci.md](./qa-wave1-tests-ci.md) D-04 / D-05 / D-11. |
| Move `pinokio.js` / `start.js` / `install.js` / `update.js` | Pinokio menu `href`s and unit tests require those exact root paths. |
| Relocate `tests/e2e_visual/` | HOLD path is what the visual job runs. |
| Recapture goldens / “fix” screenshot registry | Wave1 D-01/D-02/D-14. Not layout. |
| Touch `src/webui` product code or root markdown guides | Explicitly out of this PR. |
| Commit a real `docker-compose.override.yml` or fill oracle `CHANGE_ME_*` / `YOURUSER` | Secrets / host paths. |
| Fan implementer Issues off #452 | CoS reviews first (REQ-95). |

---

## Suggested later tickets (not this PR)

After CoS + Matthew pick resolutions. One concern per Issue. No Fixes
on this look-only file.

1. **Archive orphan `docker-entrypoint.sh`** (and add it to
   `.dockerignore` if the file is kept for history). Delete-only. No
   Dockerfile `CMD` edit in that ticket.
2. **Decide Hub-vs-Fly:** either Fly `image =` the Hub tag, or stop
   pushing Hub on every `main` commit. Requires a host window.
3. **`tests/` folder tidy:** move the six stray `tests/test_*.py` into
   `core/` / `asgi/` / `api/`; archive `tests/system/*.sh`; optionally merge
   `tests/unit/blueprints/` into `tests/blueprints/`. No assertion
   rewrites.
4. **Unify pytest config + runner** — already ticket-shaped as wave1
   D-07 / D-08. Not a folder move.
5. **Scope C honesty:** refresh `DEVELOPMENT.md` Docker bullets so they
   match today’s compose (local build, XDG mounts, service name
   `swarm`). Not this file.

`golden-journey` stays HOLD. This file does not open a CI rewrite.
