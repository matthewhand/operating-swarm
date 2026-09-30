# Auth & trust model

One-page map of how Operating Swarm authenticates callers, stamps ownership, and
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

## 8. OAuth sign-in (GitHub / Google)

Optional, and layered on top of §2 — it does **not** replace `custom_login` or `API_AUTH_TOKEN`. It needs the `oauth` extra (`pip install '.[oauth]'`, or `.[deploy]`, which also brings `wsgi`; the container image installs `.[deploy]`). Without the extra `social_django` is absent from `INSTALLED_APPS`, `/oauth/` is not routed, and `/login/` falls back to password-only without complaining.

Both providers are wired — `social_core.backends.github.GithubOAuth2` and `social_core.backends.google.GoogleOAuth2`, registered in the `if SOCIAL_AUTH_AVAILABLE:` block of [`src/swarm/settings.py`](../src/swarm/settings.py). **GitHub is the simpler path**: one OAuth App, no console project, and no `email_verified` check on top of the allowlist.

### 8.1 GitHub setup

GitHub → Settings → Developer settings → OAuth Apps → **New OAuth App**:

| Field | Value |
|---|---|
| Application name | anything (shown on the consent screen) |
| Homepage URL | `https://<your-host>` |
| Authorization callback URL | `https://<your-host>/oauth/complete/github/` |

The `<backend>` path segment is the social-core backend name, and it is **not** the setting name uppercased. GitHub is `github`; Google is `google-oauth2` (its setting prefix `SOCIAL_AUTH_GOOGLE_OAUTH2` is spelled differently from the slug on purpose — a slug-derived lookup yields `SOCIAL_AUTH_GOOGLE-OAUTH2_KEY`, which does not exist, so the Google button could never render). `social_django.urls` is mounted at `/oauth/` in [`src/swarm/urls.py`](../src/swarm/urls.py); its views are `login/<backend>/` (begin) and `complete/<backend>/` (callback). The trailing slash is part of the registered URL.

### 8.2 Google setup

Google Cloud Console → the project → **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID** → *Web application*:

| Field | Value |
|---|---|
| Authorized redirect URIs | `https://<your-host>/oauth/complete/google-oauth2/` |
| Authorized JavaScript origins | `https://<your-host>` (only if the SPA ever talks to Google directly) |

Add the test users / Workspace restrictions here too — Google refuses an unlisted account *before* the request reaches our pipeline, so it looks like an allowlist rejection but is not one.

### 8.3 The environment variables

Read from the process environment only, never committed (`_social_auth_credentials_from_env`, [`src/swarm/settings.py`](../src/swarm/settings.py)); the gate is [`src/swarm/oauth_pipeline.py`](../src/swarm/oauth_pipeline.py). For the four credentials both the `SWARM_OAUTH_*` name and the bare `SOCIAL_AUTH_*` name are accepted — the `SWARM_OAUTH_*` prefix is the documented one. The three allowlist knobs are **`SWARM_OAUTH_*` only**; see §8.6.

| Variable | Purpose |
|---|---|
| `SWARM_OAUTH_GITHUB_KEY` | GitHub OAuth App **Client ID** → `SOCIAL_AUTH_GITHUB_KEY`. |
| `SWARM_OAUTH_GITHUB_SECRET` | GitHub OAuth App **Client secret** → `SOCIAL_AUTH_GITHUB_SECRET`. |
| `SWARM_OAUTH_GOOGLE_KEY` | Google OAuth **Client ID** → `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY`. |
| `SWARM_OAUTH_GOOGLE_SECRET` | Google OAuth **Client secret** → `SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET`. |
| `SWARM_OAUTH_ALLOWED_EMAILS` | Exact addresses permitted to sign in, comma-separated (`allowed_emails()`). |
| `SWARM_OAUTH_ALLOWED_DOMAINS` | Email **domains** permitted to sign in, comma-separated — `example.com`, not `@example.com` (`allowed_domains()`). |
| `SWARM_OAUTH_ALLOW_ANY` | Truthy value disables the allowlist check entirely. **Dev only.** |

> **Fail closed.** With none of `SWARM_OAUTH_ALLOWED_EMAILS` / `SWARM_OAUTH_ALLOWED_DOMAINS` / `SWARM_OAUTH_ALLOW_ANY` set, **every** social sign-in is refused — and the login page renders no provider button at all, because `web_views._oauth_providers()` returns `[]`. Unconfigured therefore looks identical to not-installed until you check the variables.

Each allowlist knob accepts either a Django setting or the env var, and a blank value never masks a populated env var (declaring `SWARM_OAUTH_ALLOWED_DOMAINS=""` in a settings module would otherwise silently discard the operator's value). `SWARM_OAUTH_ALLOW_ANY` uses the codebase-wide `TRUTHY` set — `1` / `true` / `t` / `yes` / `y` / `on`, case-insensitively — and every negative or unrecognised spelling (`false`, `off`, `no`, `0`, empty, unset) leaves the check **on**. Writing `SWARM_OAUTH_ALLOW_ANY=false` does not opt out.

On top of the allowlist, a Google sign-in is refused unless the provider reports `email_verified` (`require_verified_email`): a Workspace tenant admits super-admin-provisioned, alias, and external-collaborator accounts, so a domain allowlist is materially weaker on Google. GitHub needs no such check — the `user:email` scope makes `GithubOAuth2.user_data` replace the address with GitHub's confirmed primary.

### 8.4 Verifying it worked

| Check | Where | Means |
|---|---|---|
| `GET /v1/system/build/` | `BuildInfoView` → `swarm.core.build_info` | `extras` contains `oauth`. Subject to the same gate as the rest of `/v1` (`Authorization: Bearer $API_AUTH_TOKEN`, or a session cookie) when `ENABLE_API_AUTH` is on. |
| Boot log `Install profile: os-core <version> +oauth+wsgi` | `AppConfig.ready()` → `summary_line()` | The `deploy` profile is live on **the machine you are looking at**, extras sorted. `os-core <version> (core only)` means the extra never got installed. |
| A provider button on `/login/` | `web_views._oauth_providers()` | All three conditions held: extra installed **and** `/oauth/` URLs mounted, key **and** secret present, and an allowlist configured. |

**Button missing?** The install-profile line is the first thing to check, because it splits the two causes: no `oauth` in the profile means the extra is absent and you need `pip install '.[oauth]'` plus a rebuild; `oauth` present with no button means a missing variable. A mounted-and-fully-configured install that still fails at the provider is the TLS-proxy case — `SECURE_PROXY_SSL_HEADER` in `settings.py` is what keeps `redirect_uri` on `https://` behind Fly/nginx, and both providers reject a `redirect_uri` whose scheme or host disagrees with the registered callback.

### 8.5 Rotating a secret

The variables are read from the process environment at settings-import time, so a rotation is a secret write plus a restart — no image push, no rebuild.

```bash
flyctl secrets set SWARM_OAUTH_GITHUB_SECRET='<new-client-secret>'
flyctl machine restart
```

`flyctl secrets set` already bounces the app's machines; the explicit restart covers a secret written against an already-running machine on an older CLI. Mirror the change wherever the secret is stored (a `.env` for `docker compose up -d`, a systemd `EnvironmentFile`, your platform's secret manager). Rotating a *client* secret does not require re-registering the callback URL, so the URLs in §8.1 / §8.2 stay put.

### 8.6 The allowlist is mandatory on a public host

This host fronts the project's LLM keys. On a public domain an open OAuth login is not a convenience feature — it is an open signup for those keys, to anyone who can reach GitHub or Google. So `swarm.oauth_pipeline` owns the allowlist check itself rather than delegating to social-core's `SOCIAL_AUTH_ALLOWED_DOMAINS`, whose exact semantics are version-specific and whose *absence* means allow rather than deny. Owning it also makes "unconfigured means deny" directly testable (`tests/core/test_oauth.py`).

Three consequences that matter when you debug a refusal:

- Setting `SOCIAL_AUTH_ALLOWED_DOMAINS` here is a **silent no-op that refuses every login** — the check never reads it. Use `SWARM_OAUTH_ALLOWED_DOMAINS`.
- The pipeline steps run **before** `social_user` / `create_user`, and a refusal *raises* rather than returning `None`, so a rejected sign-in leaves no user row behind and lands on `/accounts/login/` with an explanation instead of a 500.
- An already-authenticated user is **re-checked on every callback**, not waved through on the assumption they were checked at account creation. Deleting an address from the allowlist therefore takes effect on the next sign-in attempt rather than leaving a live session's owner permanently approved.

---

## Quick operator checklist

1. Production: set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `API_AUTH_TOKEN` (or multi-key vars).
2. Point OpenAI clients at `/v1` with `Authorization: Bearer $API_AUTH_TOKEN` (CSRF cookie not required). Kind turns: `cli_agent`, `api_agent` (→ `chatbot` recipe), `support`, `software_dev`.
3. Sign in at `/login/` for WebUI, Session Explorer, and websocket chat (session ≠ API token). Browser POSTs to `/v1/chat/completions` also need the CSRF token cycle.
4. Keep `ALLOW_UNRESTRICTED_WORKDIR` and `SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY` off unless you intentionally widen trust.
5. Expect prod CSP (`script-src 'self'`; `style-src 'self'`); rely on CSRF + frame/nosniff + auth gates above. Use `SWARM_CSP=false` only to disable the header.
6. Turning on OAuth sign-in? Install the `oauth`/`deploy` extra, register the `https://<your-host>/oauth/complete/<backend>/` callback, and set an allowlist — with no allowlist every social sign-in is refused. See §8.
