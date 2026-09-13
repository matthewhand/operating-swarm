# Auth & trust model

One-page map of how Open Swarm authenticates callers, stamps ownership, and
bounds execution. Operators can reason about **who** can hit which surface and
**what** that principal may see or run.

Canonical code: [`src/swarm/auth.py`](../src/swarm/auth.py),
[`src/swarm/consumers.py`](../src/swarm/consumers.py),
[`src/swarm/core/responses_store.py`](../src/swarm/core/responses_store.py),
[`src/swarm/core/blueprint_sandbox.py`](../src/swarm/core/blueprint_sandbox.py),
workdir helpers under `swarm.core.workdir` / CLI fusion support.

Related: [DEPLOYMENT.md](./DEPLOYMENT.md) · [CONFIGURATION.md](../CONFIGURATION.md) ·
[SESSION_EXPLORER.md](./SESSION_EXPLORER.md) · [websocket_chat.md](./websocket_chat.md) ·
[FEATURE_STATUS.md](../FEATURE_STATUS.md) §10 Security.

---

## Diagram

```text
                    ┌─────────────────────────────────────────────┐
                    │              Client / operator              │
                    └───────────────┬─────────────┬───────────────┘
                                    │             │
              Authorization: Bearer │             │ Django session cookie
              (API_AUTH_TOKEN[S])   │             │ (form login @ /login/)
                                    ▼             ▼
                    ┌───────────────────┐   ┌─────────────────────┐
                    │  REST /v1/*       │   │  WebUI + WS chat    │
                    │  StaticTokenAuth  │   │  @login_required /  │
                    │  → token:<sha24>  │   │  AuthMiddlewareStack│
                    │  (+ session OK)   │   │  → user:<name>      │
                    └─────────┬─────────┘   └──────────┬──────────┘
                              │                        │
                              │  Bearer does NOT       │ anonymous WS
                              │  authenticate WS       │ accept→close 4401
                              ▼                        ▼
                    ┌───────────────────┐   ┌─────────────────────┐
                    │ /v1/responses     │   │ /sessions/ Explorer │
                    │ IDOR: same        │   │ operator bridge:    │
                    │ principal only    │   │ user:* + configured │
                    │ owner_allows()    │   │ token:* (REST stays │
                    │                   │   │ strict)             │
                    └───────────────────┘   └─────────────────────┘

  Workdir: params.workdir/cwd under SWARM_WORKSPACES_DIR
           (ALLOW_UNRESTRICTED_WORKDIR opt-in escape)
  Blueprints: user discovery opt-in; AST sandbox (not OS sandbox)
  Browser: CSRF on login + HTML mutators; prod CSP (script-src/style-src self; no unsafe-inline)
```

---

## 1. API Bearer → `token:` principals (REST)

| Item | Detail |
|---|---|
| Secrets | `API_AUTH_TOKEN` (primary) / legacy `SWARM_API_KEY`; multi-key `API_AUTH_TOKENS` / `SWARM_API_KEYS` (CSV). |
| Wire format | `Authorization: Bearer <token>` or `X-API-Key: <token>`. |
| Auth class | `StaticTokenAuthentication` — constant-time compare against all accepted keys; returns `(AnonymousUser, provided_token)` so `request.auth` is the presenting credential. |
| Permission | When auth is on: `HasValidTokenOrSession` (Bearer **or** Django session). |
| Principal | `token:<first-24-hex-of-sha256(token)>` via `token_principal` / `request_principal`. Each multi-key secret is a **distinct** owner. |
| Enablement | Django setting `ENABLE_API_AUTH` is **derived** from whether any token is configured at startup — not a standalone env toggle. Production (`DEBUG=False`) refuses to boot without a token unless `SWARM_ALLOW_NO_AUTH=true`. |

### REST IDOR on `/v1/responses`

Stored responses carry an `owner` stamp. With `ENABLE_API_AUTH` on:

- `GET` / cancel / `DELETE` call `_assert_owner_access` → `responses_store.owner_allows(record, principal)`.
- Access requires **exact** principal match (`user:…` or `token:…`).
- Legacy/unowned records are **fail-closed** (denied) when auth is on.
- When auth is off (local debug / `SWARM_ALLOW_NO_AUTH`), ownership checks are skipped.

Session users who hit REST with a cookie get `user:<username>` and the same strict IDOR — they do **not** automatically see other users' or token-stamped responses via `/v1/responses/{id}`.

---

## 2. Django session → operator pages & websocket chat

| Surface | Gate |
|---|---|
| Teams admin / export, blueprint library (browse + mutators), settings, Session Explorer, agent/team creator **mutators** | `@login_required` |
| Public without session | Landing SPA, `/teams/launch/`, `/profiles/`, agent-creator **GET**, login form |
| Websocket chat `ws/ai-demo/<conversation_id>/` | Django **session cookie** via `AuthMiddlewareStack` only |

Anonymous websocket connects are **accept-then-close** with code **4401** (`WS_AUTH_REQUIRED_CODE`) and reason `authentication required`, so the SPA can show a Sign-in CTA instead of an opaque failure. `receive()` also re-checks session auth so a frame that races the close cannot append to a transcript or invoke a blueprint/LLM.

**Dev LAN exception (REQ-13):** when `DJANGO_DEBUG=true`, loopback and RFC1918/link-local clients are auto-logged as `swarm-anon-preview` (HTTP middleware + the same mint on the websocket if no cookie yet). Pytest does not get this implicit path. Force on with `SWARM_ALLOW_ANONYMOUS=1`; force off with `SWARM_ALLOW_ANONYMOUS=0`. Production stays 4401 / login-required.

Login: `/login/` and `/accounts/login/` → `custom_login`. POST is **not** CSRF-exempt; `next` is open-redirect hardened (rooted relative paths only).

### UI preferences (REQ-144 / REQ-168) — guest vs logged-in

`GET`/`PATCH` `/v1/preferences/` stores **Favourites** (ordered `{id,name}` list), **Hidden Bots** (agent ids), and **hostname override** (display / system-name label) in a first-party `UserPreference` row (JSON bag + registry; no `django-dynamic-preferences` package). SQLite/Postgres; no Neon; no secrets in the bag.

| Caller | Identity | Cross-browser |
|---|---|---|
| Form-login session (incl. LAN `swarm-anon-preview`) | `user:<username>` + FK to that User | Same account → same favourites/hidden/hostname |
| REST Bearer / `X-API-Key` | `token:<sha256-prefix>` (no User row) | Same token → same bag |
| Unauthenticated guest | `session:<django-session-key>` | Same browser session only. A new browser without that cookie starts empty, then may **import-once** from `localStorage` if the server bag is still empty. Cross-device sync requires login. |

SPA rail chrome loads prefs on session start and PATCHes on pin/hide/hostname change (debounced). After the first successful server write, **server wins** over a stale local cache. Extra knobs (theme, …) can join the same `values` JSON later without a new table.

---

## 3. Bearer does **not** auth websockets

The Settings-page / `.env` API token authenticates **HTTP REST** only.

- Presenting `Authorization: Bearer …` on the websocket upgrade does nothing useful for `DjangoChatConsumer`.
- Chat needs a form-login session cookie on the same origin.
- See [websocket_chat.md](./websocket_chat.md) for Connected vs 4401 vs unreachable badges.

---

## 4. Session Explorer operator bridge

UI: `/sessions/`, `/sessions/<id>/`, `/api/sessions/` — all `@login_required`.

With `ENABLE_API_AUTH` on, `explorer_owner_allows` lets a logged-in Django operator see:

1. Rows owned by their `user:<username>` principal, **and**
2. Rows stamped with any **currently configured** API-token principal (`token:<sha256-prefix>`), so curl/Bearer-created sessions are visible in the browser.

Foreign `user:…` owners and unowned legacy rows stay hidden in the Explorer.  
**REST `/v1/responses` IDOR is unchanged** — still same-principal only. The bridge is observability for operators, not a privilege escalation on the API.

When API auth is off, the Explorer aligns with open REST (does not fail-closed-hide everything).

---

## 5. Workdir confinement

Per-request `params.workdir` / `params.cwd` (`cli_agent`, hybrid MoA, MoA orchestrator, CLI fusion consumers, WS chat) and `swarm-cli moa --workdir` / `--cwd`:

- Resolve under `SWARM_WORKSPACES_DIR` (default XDG `…/swarm/workspaces`).
- Relative paths are fine; **absolute paths outside the root are rejected**.
- Escape hatch: `ALLOW_UNRESTRICTED_WORKDIR=true` — for local CLI power users only; **keep off on API servers**.
- Unset write workdirs mint a **marked** per-run temp (`run-<12 hex>` + `.swarm-auto-run`) under that root. The API/WS path never uses the Django process CWD (`CliAdapter.stream_run` receives that confined path; it does not fall back to `os.getcwd()` on this path).
- Explicit **Folder** (`params.folder` / agent settings, REQ-167 / #588) is used as process cwd when set. It is **not** remapped under the workspaces root.
- `cleanup_run_workdir` / `prune_stale_run_workdirs` delete only directories that contain `.swarm-auto-run`. A user dir named `workspaces/run-deadbeefcafe` **without** the marker is kept.

`software_dev` / `software_dev_team` file tools are a separate workdir: they
default to the **API-host filesystem** (`params.workdir` or
`SWARM_SOFTWARE_DEV_WORKDIR`). dev-worker-max `:8002` cannot read or write a
tree that only exists on dev-worker-gpu (for example `~/chatty-commander`)
unless `params.remote_workdir` or a remote-shaped `params.workdir`
(`user@host:path` / `ssh://…`) plus SSH is configured. Identity is an
env-var name for a key path — never a private key. See
[ISSUE-148-software-dev-remote-workdir.md](./qa/ISSUE-148-software-dev-remote-workdir.md).

---

## 6. User blueprint discovery + AST sandbox

| Control | Default | Meaning |
|---|---|---|
| `SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY` | **off** | Creator saves write under the user blueprints dir; **discovery / `exec_module` of that tree is opt-in**. |
| `SWARM_BLUEPRINT_PATHS` | unset | Extra roots (os.pathsep-separated) always eligible for scan; bundled names win on collision. |
| `SWARM_USER_BLUEPRINT_SANDBOX` | **on** | AST + banned-snippet gate (`blueprint_sandbox.py`) before loading user/community roots and on creator validate/save. |

Important trust bound: this is a **static AST filter**, **not an OS sandbox**. It blocks obvious escapes (`subprocess`, write-mode `open` / `Path.open`, selected network clients, reflection helpers, …). Bundled blueprints under `src/swarm/blueprints` are trusted and skip the gate. Running third-party blueprint code remains a code-execution trust decision.

---

## 7. CSRF, cookies, headers (prod CSP)

| Control | Behavior |
|---|---|
| CSRF | Required on `custom_login` POST, HTML mutators (blueprint library, etc.), and **session-cookie** POSTs to `/v1/chat/completions` (DRF `SessionAuthentication` still checks CSRF even when the view is `@csrf_exempt`). SPA cycle: `GET /login/` or `/accounts/login/` primes `csrftoken`; send `credentials: 'include'` + `X-CSRFToken` from that cookie (`api.ts` `ensureCsrfCookie` / `buildHeaders`). Token-auth REST (`Authorization: Bearer` / `X-API-Key`) is CSRF-exempt **without** a cookie jar — both `/v1/chat/completions` routes wrap `as_view()` with `csrf_exempt` so ASGI/Daphne keeps the flag (live tip-of-main Bearer-without-cookie was 403 CSRF). Guest/anon without Bearer or session stays **403** when `ENABLE_API_AUTH` is on (do not weaken). Issue #136 / `tests/api/test_issue136_kind_chat_e2e.py`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Must include scheme+host(+port) for every UI origin (LAN/proxy too). |
| Secure cookies | When `DEBUG=False`, `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` default on; opt out with `SWARM_SECURE_COOKIES=false` for HTTP staging. |
| Always-on headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options` (default `DENY`; prod may override via `DJANGO_X_FRAME_OPTIONS`). |
| **CSP** | When `DEBUG=False`, `ContentSecurityPolicyMiddleware` sets `Content-Security-Policy` from `CONTENT_SECURITY_POLICY` (opt out with `SWARM_CSP=false`). Policy is self-centric: `default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, `font-src 'self'`, `img-src 'self' data: blob:`, `script-src 'self'`, `style-src 'self'`, `connect-src 'self' ws: wss:` (websocket chat). **No CDN hosts. No `'unsafe-inline'`.** Operator UI assets (Bootstrap, Prism, Font Awesome, marked) are vendored under `src/swarm/static/contrib/` and loaded via `{% static %}`. |

### Inline extraction (complete for operator templates)

Django operator page logic lives under `static/js/` (`{% static %}` + `data-action` / `data-*` delegation; `json_script` data islands where needed). **Inline `onclick=` / `oninput=` handlers are gone** → `script-src 'self'`. **Inline `<style>` blocks and `style=""` attributes are gone** from `src/swarm/templates/` (classes in `static/css/operator.css`; progress width via `data-pct="N"` CSS rules; visibility via `.os-hide`). HTMX's default indicator `<style>` inject is disabled (`static/js/htmx_csp.js`); equivalent rules live in `operator.css`. Prefer classes/external CSS over adding `'unsafe-*'` directives.

**Pages on external JS:** `settings_dashboard`, `teams_launch`, `session_explorer`, `teams_admin`, `agent_creator`, `team_creator`, `blueprint_library` (+ `blueprint_card`), `my_blueprints`, `blueprint_creator`, and `session_detail`. High-traffic actions use `data-action` (creators, settings quick actions, library search/show-more/GitHub, creator reset).

---

## Quick operator checklist

1. Production: set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `API_AUTH_TOKEN` (or multi-key vars).
2. Point OpenAI clients at `/v1` with `Authorization: Bearer $API_AUTH_TOKEN` (CSRF cookie not required). Kind turns: `cli_agent`, `api_agent` (→ `chatbot` recipe), `support`, `software_dev`.
3. Sign in at `/login/` for WebUI, Session Explorer, and websocket chat (session ≠ API token). Browser POSTs to `/v1/chat/completions` also need the CSRF token cycle.
4. Keep `ALLOW_UNRESTRICTED_WORKDIR` and `SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY` off unless you intentionally widen trust.
5. Expect prod CSP (`script-src 'self'`; `style-src 'self'`); rely on CSRF + frame/nosniff + auth gates above. Use `SWARM_CSP=false` only to disable the header.
