# Issue #136 — Kind-chat end-to-end (private SoT)

Issue: #`136`.

**Intent:** Prove the claimed agent kinds can chat end-to-end so Grok seats
can retire onto open-swarm.

Gating tests: `tests/api/test_issue136_kind_chat_e2e.py` (Bearer / session
CSRF cycle / guest FAIL / kind matrix / honest errors).
Helper: `swarm.core.agent_kind.resolve_chat_blueprint_id` (`api_agent` →
`chatbot`, same recipe the websocket consumer already used).

No secrets, tokens, `.env` values, Neon, LiteLLM catalog edits, or Qwen/Comfy
contention. Cheap local backends only (`SWARM_TEST_MODE`, Python echo CLI,
deterministic `support` / `software_dev` grammar).

---

## Success checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Authenticated SPA or API path not blocked by CSRF for legitimate clients | **PASS** | Session cookie + `GET /login/` `csrftoken` + `X-CSRFToken` → 200 (`test_session_csrf_cycle_completes_a_turn`). Bearer / `X-API-Key` REST is CSRF-exempt (`test_bearer_without_csrf_cookie_completes_a_turn`, `test_bearer_plus_session_cookie_does_not_need_csrf`). Documented in [AUTH.md](../AUTH.md) §7. |
| 2a | CLI agent turn | **PASS** | `POST /v1/chat/completions` `model=cli_agent` `params.cli=echo` (local `python -c` echo). Reply contains `CLI-ECHO:`. |
| 2b | API agent turn | **PASS** | `model=api_agent` now resolves to the `chatbot` recipe (WS already did this; REST did not). `SWARM_TEST_MODE` reply `You said: …`. |
| 2c | Blueprint agent turn (`support`) | **PASS** | Deterministic Support path (`SWARM_TEST_MODE`) — “create a team” reply. Also streamed SSE + `[DONE]`. |
| 2d | Team / `software_dev` (CoS + engineer as-tool) | **PASS** | `status` names seats; `quote` extracts Intent/Success; engineer `implement` stays **BLOCKED** without feasibility (handoff/as-tool gate, no LLM). |
| 3 | Send → streamed or final reply; no crash; honest error if unavailable | **PASS** | Final JSON `chat.completion` per kind. SSE path asserts `text/event-stream` + `[DONE]`. Unknown model → **404** naming the id. Empty `cli_agents` → named “No CLI agents are configured” (HTTP 200 with honest body, not a fake success essay). |
| 4 | Tests / recorded checklist in the private repo | **PASS** | This file + `tests/api/test_issue136_kind_chat_e2e.py` + `tests/core/test_agent_kind.py` (`resolve_chat_blueprint_id`). |

Run (no paid providers):

```bash
uv run pytest tests/api/test_issue136_kind_chat_e2e.py tests/core/test_agent_kind.py tests/unit/test_issue136_csrf_bearer.py -q
```

Checked-in transcript: [docs/qa/evidence/issue-136-kind-turns.md](./evidence/issue-136-kind-turns.md).

---

## Live ubuntu-gtx `:8000` look-only vs this branch

openswarm-agy notes below were taken on **live tip of `main`**, not this PR.
This table is verified **on this branch’s tests**, not by claiming the live host.

| Live observation (tip of `main`) | This branch |
|---|---|
| GET `/` and `/accounts/login/` set `csrftoken` | `test_login_and_accounts_login_prime_csrftoken` — `/login/` and `/accounts/login/` set the cookie. Landing `/` is not required to prime. |
| POST no cookie → 403 CSRF cookie not set | On **this** tip the routed view is `csrf_exempt`. Guest/no-cookie with auth on → **403 credentials** (`test_guest_without_credentials_is_denied`), not CSRF. Live CSRF-without-cookie is LAN preview minting a session (`test_session_without_csrf_is_denied`). |
| Cookie without `X-CSRFToken` → 403 CSRF token missing | Still **403 CSRF** (`test_session_without_csrf_is_denied`). Login ≠ CSRF bypass. |
| Cookie jar + `X-CSRFToken` + Referer (even anon) → CSRF clears; 404 if model wrong | Login session + `csrftoken` + `X-CSRFToken` + Referer/Origin → **200** Support turn (`test_session_csrf_cycle_completes_a_turn`). Unknown model → **404** naming the id. SPA contract: `credentials: 'include'` + `getCookie('csrftoken')` → `X-CSRFToken`. |
| Bearer/fake token alone without cookie → 403 CSRF cookie not set | **Fixed.** Valid Bearer, no cookies → **200** (`test_bearer_without_csrf_cookie_completes_a_turn`). Fake Bearer, no cookies → auth failure, **not** `CSRF cookie not set`. `urls.py` wraps both chat-completions `as_view()` with `csrf_exempt`. |
| `/v1/models` has `cli_agent`, `support`, `software_dev`, `skeptic`; no `api_agent` | **Fixed.** `GET /v1/models` lists `api_agent` (recipe `chatbot`) plus those ids (`test_models_list_includes_api_agent_rail_id`). |
| Login form needs `csrfmiddlewaretoken`; WS anon → 4401 unless DEBUG+LAN | Unchanged and correct. Login CSRF is existing hardening. WS 4401 is AUTH.md (Bearer does **not** auth websockets). Not a Success item to weaken. |

Do **not** treat ubuntu-gtx `:8000` @ `69b7b677` as Success for this PR.

---

## Auth contract (verified)

```text
Guest / no cookie / no Bearer
  → 403  "Authentication credentials were not provided"
         (when ENABLE_API_AUTH is on)

Session cookie, no CSRF token
  → 403  CSRF Failed: …     (login ≠ CSRF bypass)

Session cookie + csrftoken cookie + X-CSRFToken
  → 200  turn completes

Authorization: Bearer <API_AUTH_TOKEN>
  → 200  CSRF cookie not required
         (still 200 if a leftover session cookie is also present)

Invalid Bearer
  → 401/403  Invalid API Key / credentials not provided
             (does not disable CSRF or open the API)
```

SPA already primes `csrftoken` via `ensureCsrfCookie()` (`GET /login/`) and
sends `X-CSRFToken` from `webui/frontend/src/lib/api.ts`.

Token clients (curl, TUI, Grok-retire REST) use:

```text
Authorization: Bearer $API_AUTH_TOKEN
POST /v1/chat/completions
```

Do not put the token in Issues, PRs, commits, or CI logs.

---

## Deviations (honest)

1. **Guest / anonymous remains FAIL** when `ENABLE_API_AUTH` is on. That is
   product policy, not a waiver. Live DEBUG LAN auto-login
   (`swarm-anon-preview`) mints a session without a CSRF cookie, so a bare
   `POST /v1/chat/completions` (no Bearer, no `X-CSRFToken`) returns
   `403 CSRF Failed: CSRF cookie not set.` — the same class as
   `test_session_without_csrf_is_denied`. Fix for operators: send Bearer, or
   complete the session CSRF cycle. We did **not** weaken CSRF for anonymous
   callers.

2. **`api_agent` is not a discoverable blueprint package.** It is the rail /
   starter API seat. Runtime recipe is `chatbot`. REST POST and GET `/v1/models`
   now advertise `api_agent` (live `:8000` previously listed `cli_agent` /
   `support` / `software_dev` but not `api_agent`). Websocket already mapped
   the rail id to `chatbot`.

3. **True paid-provider inference is not exercised.** Tests use
   `SWARM_TEST_MODE`, a local Python echo CLI, and `software_dev` /
   `support` deterministic grammars. If a live model is unavailable, the
   product must keep returning a named error (404 / “No CLI agents are
   configured” / Support fallback), never a garbage success. That contract
   is locked here; a live Grok/Qwen turn is out of scope (no paid burn, no
   Qwen-while-Comfy).

4. **Remote kind is not a Success item** for this Issue (CLI / API /
   Blueprint / Team). Remotes stay on their own harness Issues.

5. **Private CI may be fake-red** on unrelated jobs. Own-diff workflow
   `.github/workflows/issue136-kind-chat-e2e.yml` gates only these tests.

---

## CSRF root cause (verified, not just the live hunch)

Live look-only on ubuntu-gtx `:8000` (non-binding, verified in tests):
`GET /` and `GET /accounts/login/` set `csrftoken`. POST with no cookie →
403 CSRF cookie not set. Cookie without `X-CSRFToken` → 403 token missing.
Cookie + `X-CSRFToken` + Referer clears CSRF (then 404 if the model id is
wrong). Bearer alone without a cookie was observed 403 CSRF on that tip —
the routed `as_view()` must carry `csrf_exempt` for ASGI/Daphne, not only
the dispatch decorator. `urls.py` now wraps both `/v1/chat/completions`
paths with `csrf_exempt(...)`.

`ChatCompletionsView.dispatch` is also `@csrf_exempt`, which skips Django
`CsrfViewMiddleware` when the flag is on the callback. DRF
`SessionAuthentication.enforce_csrf` still runs for an authenticated
session and passes `callback=None`, so the view decorator does **not**
exempt cookie clients.

That is why live `ubuntu-gtx` `POST /v1/chat/completions` without a CSRF
cookie returned `403 CSRF Failed: CSRF cookie not set.` when LAN debug
preview had already authenticated the caller.

`CustomSessionAuthentication.enforce_csrf` now skips CSRF **only** when the
request presents a **valid** configured static token. Session-only POSTs
still require the CSRF cycle. Guests still fail closed.

## Related — Issue #150 (live CoS Runner)

This checklist locks the **deterministic** `software_dev` seat/action path
(`SWARM_TEST_MODE` + `params.seat`/`action`). Workdir-only / freeform
turns that must reach `Runner.run` so CoS can `consult_engineer` are
Issue #150 — see [ISSUE-150-software-dev-runner.md](./ISSUE-150-software-dev-runner.md).
Tip quirk: `bool(self._params)` used to skip Runner whenever any param
(including `workdir`) was set; Chatty Commander #854 omitted `workdir` as
a workaround. That workaround is no longer required.
