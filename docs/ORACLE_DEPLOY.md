# Operating Swarm Oracle — authenticated, durable, public-HTTPS deployment

A runbook to stand up an Operating Swarm gateway that an external client (e.g. Grok
via mcp-gateway) can reach over **public HTTPS with a bearer token**, durable
across reboots.

> **The one hard constraint — read first.** Operating Swarm's CLI blueprints
> (`cli_agent`, `cli_fusion`, `cli_*`) **shell out to host-installed CLIs**
> (`gemini`, `claude`, `grok`, `opencode`), each with its **own** auth (gemini
> OAuth, grok file-login, claude key/login). Those don't containerize or
> transfer cleanly — **the gateway must run on a host where the CLIs are
> installed and authenticated.** So "cloud" here means *a VM you control and can
> log into to authenticate the CLIs*, not a stateless container image. Non-CLI
> blueprints (chatbot, etc.) just need an `llm` profile and have no such
> constraint.

Artifacts referenced below live in [`deploy/oracle/`](../deploy/oracle/):
`open-swarm-oracle.service`, `nginx-open-swarm.conf` (service unit / nginx
filenames stay `open-swarm-*` until those artifacts are renamed).

## 0. Prerequisites (on the cloud host)
- A VM you can SSH into, plus a **domain** (`oracle.example.com`) pointed at its IP.
- Python 3.11+, `uv`, `node` (for gemini), and the CLIs you want
  (`claude`, `gemini`, `grok`, …) **installed and authenticated** as the run user.
- nginx + certbot for TLS.

## 1. App + config
```bash
git clone https://github.com/matthewhand/operating-swarm.git ~/operating-swarm
cd ~/operating-swarm && uv sync --all-extras
# Bring your CLI-agent config (or generate it):
mkdir -p ~/.config/swarm
os-cli cli-agents --init --write     # autodiscovers installed+authed CLIs
# (or copy an existing ~/.config/swarm/swarm_config.json over)
```

## 2. Auth token
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # save this
```

## 3. systemd service (durable, bound to localhost)
```bash
mkdir -p ~/.config/systemd/user
cp ~/operating-swarm/deploy/oracle/open-swarm-oracle.service ~/.config/systemd/user/
# edit it: set YOURUSER, the node path (match `which gemini`), DJANGO_ALLOWED_HOSTS
# (include your domain), and API_AUTH_TOKEN=<the token from step 2>.
systemctl --user daemon-reload
systemctl --user enable --now open-swarm-oracle.service
loginctl enable-linger "$USER"          # survive logout/reboot
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/v1/models   # 200
```
The unit binds **127.0.0.1:8001** — only nginx (next step) faces the internet.

## 4. Public HTTPS (nginx + Let's Encrypt)
```bash
sudo cp ~/operating-swarm/deploy/oracle/nginx-open-swarm.conf /etc/nginx/sites-available/open-swarm
# edit server_name -> your domain
sudo ln -s /etc/nginx/sites-available/open-swarm /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d oracle.example.com     # fills in the ssl_* lines, adds HTTP->HTTPS
```

## 5. Verify (with auth)
```bash
T=<your token>
B=https://oracle.example.com/v1
curl -s -o /dev/null -w "no-auth: %{http_code}\n"  -X POST $B/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"cli_agent","messages":[{"role":"user","content":"hi"}]}'   # 403
curl -s -o /dev/null -w "authed: %{http_code}\n"   -X POST $B/v1/chat/completions \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"model":"cli_agent","messages":[{"role":"user","content":"hi"}],"params":{"cli":"grok"}}'              # 200
```

## 6. Async tasking (what Grok uses)
```bash
# fire
curl -s https://oracle.example.com/v1/responses -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"model":"cli_fusion","input":"<long task>","background":true,"params":{"preset":"tri"}}'
# -> {"id":"resp_...","status":"queued"}
# poll
curl -s https://oracle.example.com/v1/responses/resp_... -H "Authorization: Bearer $T"
# -> {"status":"completed","output_text":"...","execution_ms":...,"system_fingerprint":"..."}
```
`chat/completions` also supports `"background": true` (returns a `poll_url`).

## 7. Wire into mcp-gateway
Add Operating Swarm as a backend pointing at the OpenAPI spec, with the bearer token:
`https://oracle.example.com/api/schema/` (spec) and base URL
`https://oracle.example.com/v1`, header `Authorization: Bearer <token>`.
After the proxy reloads the spec, the generated tools expose `params`, `name`,
etc. (every write endpoint's body is documented).

## Notes
- **Database:** this unit defaults to **SQLite** via `DJANGO_DB_NAME` (see
  `deploy/oracle/open-swarm-oracle.service`). That is intentional and is
  **not** Neon. To use any Postgres, set `DATABASE_URL` (or `POSTGRES_*`)
  on the unit — compose’s happy path is local Postgres
  ([DATABASE.md](./DATABASE.md)). Do **not** point oracle or Fly at Neon
  as the primary path (test/CI only; free-tier ~day 17).
- Keep `DJANGO_DEBUG=true` only if you accept verbose error pages on the LAN side;
  for stricter prod, set `DJANGO_DEBUG=false` and also set `DJANGO_SECRET_KEY` +
  `DJANGO_ALLOWED_HOSTS` (the server refuses to boot without them in prod), and
  use `--insecure`-free serving via `os-api`/daphne if you serve the web UI.
- Persist `SWARM_RESPONSES_DIR` (async task state) on durable storage so queued
  tasks survive restarts (the worker resumes in-progress tasks on boot).
- The responses store has **no automatic TTL**. Disk can grow with completed
  sessions; periodically call `swarm.core.responses_store.prune_expired`
  (optional `SWARM_RESPONSES_MAX_AGE_DAYS`, or pass `max_age_days=…`). Prune
  never deletes `queued` / `in_progress` records.
- For an internal layer that already gates access (e.g. cloud OAuth proxy), you
  may run without a token by setting `SWARM_ALLOW_NO_AUTH=true` instead.
