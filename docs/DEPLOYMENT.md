# Deploying a CLI-wrapping OpenAI-compatible server

A runbook for standing up Open Swarm so it exposes an **OpenAI-compatible API**
(`/v1/chat/completions`, `/v1/responses`, `/v1/models`, OpenAPI at `/api/schema/`)
that wraps your installed agentic CLIs (grok, claude, gemini, codex, opencode).

For the full auth & trust map (Bearer vs Django session, websocket 4401,
Session Explorer operator bridge, workdir confinement, blueprint AST sandbox,
CSRF / prod CSP), see **[AUTH.md](./AUTH.md)**.

## 0. Prerequisites — the CLIs must be installed *where the server runs*

The fusion blueprints shell out to the CLIs as subprocesses, so each CLI you
want to use must be **installed and authenticated on the same host/container as
the server** (not just on your laptop). In Docker, that means baking the CLIs
into the image (or mounting them) and providing their auth.

Auth, per CLI:

| CLI | Auth |
|---|---|
| `gemini` | `GEMINI_API_KEY` / `GOOGLE_API_KEY`, or `gemini` oauth login |
| `claude` | `ANTHROPIC_API_KEY`, or `claude` login |
| `grok` (a.k.a. `agent`) | file-based login via the `grok` CLI (no single env var) |
| `codex` | `OPENAI_API_KEY` |
| `opencode` | per its own config (`opencode models`) |

## 1. Update

```bash
git checkout main && git pull --ff-only
```

## 2. Configure

```bash
cp .env.example .env   # set DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, API_AUTH_TOKEN
                       # (production refuses to start without all three)

# If the browser UI is served from a non-localhost origin (LAN IP, reverse
# proxy hostname), add that exact origin to DJANGO_CSRF_TRUSTED_ORIGINS —
# scheme + host + port, comma-separated. Defaults are only
# http://localhost:8000 and http://127.0.0.1:8000 (greenfield swarm-api).
# When running Open Swarm on an alternate port (such as :8002), ensure trusted
# origins match that port, e.g.:
#   DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8002,https://swarm.example.com
# Also include the host in DJANGO_ALLOWED_HOSTS (hostname only, no scheme).

# which CLIs are installed AND authenticated on this host?
swarm-cli cli-agents --check-auth

# generate a swarm_config.json wiring cli_agent/cli_fusion/cli_map/cli_orchestrator
# over the installed CLIs (writes to ~/.config/swarm/swarm_config.json):
swarm-cli cli-agents --init --write
```

Then open the written `swarm_config.json` and confirm the **judge / router /
planner** roles (in the `cli_fusion` / `cli_orchestrator` / `cli_map` blocks)
point only at CLIs that showed as authenticated — `--init` prefers `grok` then
`claude` by default; change them to match your host.

The server and `swarm-cli` both find this XDG file automatically — no extra
step. Set `SWARM_CONFIG_PATH` only to point at a non-standard path. See
[CONFIGURATION.md §1](../CONFIGURATION.md#1-config-file-location-and-discovery)
for the full resolution rules.

## 3. Run

```bash
swarm-api                 # ASGI server on :8000 greenfield (also powers websocket chat)
# or:
docker compose up -d
# Fleet bare uvicorn (example): uvicorn swarm.asgi:application --port 8002
# — when LiteLLM already owns host :8000.
```

**SPA (`/` + `/chat`, ADR-001):** `webui/frontend/dist/` is gitignored. After
`git pull` on a source checkout, run **`make frontend`** (wraps
`./scripts/build_frontend.sh`) once so `/` serves the React dashboard; without
`dist/`, Django falls back to the template index. The **Dockerfile** multi-stage
build bakes that `dist/` into the image, so `docker compose` / Fly deploys serve
the SPA without a host-side Node install. CI (`python-pytest.yml` `frontend`
job) runs the same script on PRs.

Point any OpenAI client at the **Open Swarm** base (`http://<host>:8000/v1`
greenfield, or `http://<host>:8002/v1` when LiteLLM already owns `:8000`) with
`Authorization: Bearer $API_AUTH_TOKEN`. Do not confuse swarm `/v1` with LiteLLM
`/v1` on the same host.

For multiple clients with separate ownership principals, set
`API_AUTH_TOKENS=key-a,key-b` (or `SWARM_API_KEYS`) — comma-separated secrets
accepted alongside the single `API_AUTH_TOKEN` / `SWARM_API_KEY`. Each Bearer
maps to its own `token:<sha256-prefix>` principal for response ownership.
With API auth on, the Django Session Explorer (`/sessions/`, login required)
is an operator bridge: a logged-in web user also sees sessions stamped with
those configured token principals (curl/API creates); foreign `user:…`
owners stay hidden. REST `/v1/responses` IDOR remains strict same-principal.

Websocket chat on the same ASGI process needs a Django **session cookie**
(form login). The API Bearer token does **not** authenticate websockets;
anonymous sockets accept-then-close with code **4401**. Details and diagram:
[AUTH.md](./AUTH.md).

> **Single worker preferred for inflight limits.** Async `/v1/responses`
> inflight limits are **process-local**; cooperative cancel is shared via the
> filesystem when workers share `SWARM_RESPONSES_DIR`. Compose/Dockerfile default
> `SWARM_UVICORN_WORKERS=1`. Setting workers > 1 is refused by default
> (`SWARM_ENFORCE_SINGLE_WORKER=true`); only override if you accept per-worker
> inflight accounting. Oracle systemd unit already uses `--workers 1`.

> **Persist Responses state.** `/v1/responses` is stateful: stored responses (for
> `previous_response_id` chaining and `GET`/`DELETE`) live under
> `SWARM_RESPONSES_DIR` (default `~/.local/share/swarm/responses`). In Docker,
> mount a volume there — or set `SWARM_RESPONSES_DIR` to a mounted path — or
> chained responses won't survive a container restart.

## 4. Prove it works

```bash
H="-H 'Authorization: Bearer $API_AUTH_TOKEN' -H 'Content-Type: application/json'"

curl -sf http://localhost:8000/v1/models | jq .          # lists cli_fusion, cli_map, …
curl -sf http://localhost:8000/api/schema/ | head        # OpenAPI spec (200)

# one agent, consensus across your CLIs:
curl -sf http://localhost:8000/v1/chat/completions -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"cli_fusion","messages":[{"role":"user","content":"In one word, capital of France?"}]}' | jq .

# many agents, each one CLI:
curl -sf http://localhost:8000/v1/chat/completions -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"cli_map","messages":[{"role":"user","content":"In one word, capital of France?"}]}' | jq .

# Responses API:
curl -sf http://localhost:8000/v1/responses -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"cli_fusion","input":"In one word, capital of France?"}' | jq .
```

PASS = HTTP 200 and a non-empty answer naming Paris.

## Which blueprint?

| You want | `model:` |
|---|---|
| One agent, consensus across many CLIs | `cli_fusion` |
| Many agents, each using one CLI | `cli_map` |
| Cheap router that escalates hard questions to a panel | `cli_orchestrator` |
| A single named CLI, no consensus | `cli_agent` |

See [CLI_FUSION.md](CLI_FUSION.md) for the full config reference (panels, judges,
presets, per-request `params`, failover, workdir isolation, native best-of-N).

## Common gotchas

- **`All CLI panelists failed` / empty answers** → the CLI isn't installed or not
  authenticated *in the server's environment*. Re-run `swarm-cli cli-agents
  --check-auth` on the host.
- **Server refuses to start** → in production (`DJANGO_DEBUG` not true) you must
  set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `API_AUTH_TOKEN`.
  Production also **forces secure cookies** (`SESSION_COOKIE_SECURE` /
  `CSRF_COOKIE_SECURE`; opt out with `SWARM_SECURE_COOKIES=false` for HTTP staging).
  `X-Content-Type-Options: nosniff` and `X-Frame-Options` (default `DENY`) are
  Django defaults from always-on `SecurityMiddleware` / `XFrameOptionsMiddleware`
  in **both** debug and production — the prod settings block only reasserts them
  (and honors `DJANGO_X_FRAME_OPTIONS`). Production also sets a minimal
  Content-Security-Policy (`script-src 'self'`; `style-src 'self'`; no CDN;
  no `'unsafe-inline'`). Opt out with `SWARM_CSP=false`. See
  [AUTH.md](./AUTH.md) §7.
- **401/403** → missing/wrong `Authorization: Bearer $API_AUTH_TOKEN`.
- **SPA chat “Unavailable — sign in required” / WS close 4401** → no Django
  session cookie. Sign in via `/login/` (alias `/accounts/login/`; CSRF
  required on POST). Settings API tokens do **not** open the websocket
  (Bearer ≠ session — [AUTH.md](./AUTH.md) §3). Unreachable/ASGI-down is a
  different badge from 4401.
- **gemini slow / stalls** → the free `oauth-personal` tier throttles the pro
  model heavily; the flash default answers in seconds. Use a paid `GEMINI_API_KEY`
  for the pro tier.

