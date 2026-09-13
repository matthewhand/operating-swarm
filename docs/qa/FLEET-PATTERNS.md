# Fleet patterns — shared Success criteria

Issue: #`157`.

Locked 2026-09-10 (Taskmaster + Matthew). **Docs / checklist only** — this
file does not change runtime, catalog, Neon, or CI workflows.

**Intent:** One Success checklist for seats that share the fleet
(open-swarm, OpenMousBot, Rakazo, Chatty, mcp-gateway, CLI-proxy) so each
repo does not reinvent remote prove, same-origin hydrate, health JSON,
herdr host runtime, hide vs archive, or infra-CI judgment.

Operator map (open-swarm Remote axis):
[FEATURE_STATUS.md](../../FEATURE_STATUS.md) §11b Remote harnesses.
Harness verbs: [REMOTE_HARNESSES.md](../REMOTE_HARNESSES.md).

Code PRs that later implement a row here must `Fixes` / `Closes` #157 or a
child Issue. Do not treat this file as a license to ship feature code.

---

## Hard stops (unchanged)

- Issue-first. `*-private` is source of truth.
- No secrets, tokens, `.env` values, or live key material in docs or PRs.
- No LiteLLM catalog change.
- No Neon.
- No `git add -A`.
- No Reachy `POST /wake`.
- Hailo off.

---

## 1. Remote prove

A remote / drive-gate prove is **not** “it worked on localhost.” OMB and
Rakazo drive gates, and open-swarm Remote-axis proves, reuse this list.

- [ ] **Health URL** from a **non-localhost** client (LAN or documented
      remote host). `127.0.0.1` / `localhost` alone is not the prove.
      Open-swarm probe: `POST /v1/remotes/<id>/health/` or
      `swarm-cli remotes health` — see [REMOTE_HARNESSES.md](../REMOTE_HARNESSES.md#health).
- [ ] **UI** from a **non-localhost** browser (or the product’s published
      UI URL). Django-served SPA / operator chrome, not a bare Vite
      origin — see §2.
- [ ] **URL-bar shot** (scheme + host + port visible) **or** a written
      **headless deviation** (why no shot, which command, which host).
      A cropped pane without the URL bar is not the shot.
- [ ] Gate text in the consuming Issue / PR **links this file** (or quotes
      these three bullets) instead of inventing a second remote-prove list.

**Not a remote prove:** `vite` / `vite preview` without an API proxy
(§2). Playwright on `:4173` with `preview.proxy = {}` is a hermetic SPA
e2e, not a hydrate / remote-drive prove
([vite.config.ts](../../webui/frontend/vite.config.ts)).

### SSH / shell-safe argv (pointer — does not block §1–6)

On an SSH hop (Herdr remote, nested-host CLI, any `ssh user@host -- …`
drive), **never space-join args into a shell string**. Pass an **argv
list** (`subprocess` `shell=False`) or quote each token if a shell is
unavoidable (`shlex.quote`). A stub that receives `list[str]` can PASS
while live OpenSSH FAILS on the joined string (spaces split, flags
appear as extra options).

Evidence: private
[#148](https://github.com/matthewhand/open-swarm/issues/148)
FAIL — stub list vs OpenSSH space-join.

This note is **not** a Success checkbox. Do not fail fleet §1–6 for it.
Fix quoting on the SSH / Herdr Issue (or a child); keep `Fixes #157`
on this checklist PR.

---

## 2. SPA ↔ API same-origin / CSRF-prime

**Rule:** `vite` or `vite preview` **without** a same-origin proxy to the
API is **not** a hydrate prove target.

Lesson: private [#139](https://github.com/matthewhand/open-swarm/issues/139).
CSRF cycle: [AUTH.md §7](../AUTH.md#7-csrf-cookies-headers-prod-csp).
Hydrate honesty: [REQ-171A](../requirements/REQ-171A.md) / kind-chat
[Issue #136](./ISSUE-136-kind-chat-e2e.md).

- [ ] Browser session POSTs use the **same origin** as the API (Django
      serves the SPA, or Vite **dev** proxy is on and the page origin is
      the proxied host).
- [ ] Session cookie path primes CSRF: `GET /login/` or
      `/accounts/login/` sets `csrftoken`; SPA sends
      `credentials: 'include'` + `X-CSRFToken`
      (`ensureCsrfCookie` / `buildHeaders` in
      [api.ts](../../webui/frontend/src/lib/api.ts)).
- [ ] Bearer / `X-API-Key` REST is CSRF-exempt **without** a cookie jar.
      Guest / anon without Bearer or session stays **403** when auth is
      on — do not weaken CSRF to make a cross-origin preview “work.”
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` includes scheme+host(+port) for every
      UI origin (LAN / proxy too).
- [ ] Do **not** record “hydrate FAIL” against `vite preview` with empty
      `preview.proxy`. That origin cannot complete the cookie + CSRF
      cycle. Prove hydrate on the Django origin (or Vite **with** proxy).

Chat websockets also need a form-login session cookie on the same origin
([AUTH.md §3](../AUTH.md#3-bearer-does-not-auth-websockets)). Bearer does
not authenticate WS.

---

## 3. Health contract (sketch)

Harnesses open-swarm will drive should expose a **tiny JSON** health
body so fleet seats can share one probe. This is a sketch, not a
breaking rename of today’s routes.

**Target shape**

```json
{"ok": true, "runtime": true, "static": true}
```

| Field | Meaning |
|-------|---------|
| `ok` | Process answered; liveness. Prefer boolean. |
| `runtime` | Runtime / worker is up (boolean, or a short runtime name such as Rakazo `"pi"`). |
| `static` | Static / UI (or OMB `static` mode) is serving. Boolean or short flag. |

**Today (honest map — do not pretend these already match)**

| Harness | Probe | Body today |
|---------|-------|------------|
| Rakazo | `GET /health` (public) | `{"ok": true, "runtime": "pi", …}` |
| OpenMousBot | `GET /api/health` | `{"app": "openmausbot", …}` — include a `static` flag when aligning |
| Hermes | `GET /health` | `{"status": "ok"}` |
| Nested open-swarm | `GET /health` | `{"status": "ok"}` |
| Herdr | **Not HTTP** | `herdr workspace list` (local or SSH) |

Auth-gated 401/403 on a **live** port still counts as **UP** for
open-swarm `check_health` (endpoint is alive). DOWN is a report, not a
crash-loop. New harnesses should add `ok` + `runtime` / `static` rather
than a third schema. Implementation is a **child Issue**, not this file.

---

## 4. herdr as preferred host runtime

Once a **local prove** has landed, prefer **[Herdr](../HERDR.md)** as the
host runtime for **engineer / skeptic CLI sessions** over one-off
freebuff / tmux panes.

- [ ] Eng / skeptic CLI work that needs a durable host pane goes through
      Herdr (`herdr agent prompt` / wait-until idle), not a disposable
      tmux/freebuff session invented for that pulse.
- [ ] Local Herdr = this host (no SSH). Remote Herdr is **SSH-shaped**
      (SSH to the Herdr host, then its CLIs) — not an HTTP remote like
      OMB / Hermes / Rakazo. See [GLOSSARY — Herdr](../GLOSSARY.md#herdr-member-kindherdr).
- [ ] **Pointer only.** Do **not** change the LiteLLM catalog, Neon, or
      baked LAN hosts to “enable” this preference.
- [ ] Cloud / Actions CI still **mocks** `herdr`. Missing SSH config is
      an error, not a guessed host.

`swarm-cli tui` is open-swarm’s own API client (Herdr-*like* chrome). It
is not a substitute for the Herdr hop and does not replace this pointer.

---

## 5. Hide / sidebar (prefer OMB Hide)

Prefer the **OpenMousBot Hide** pattern before inventing a new sidebar
hide on Rakazo or open-swarm.

| Verb | Meaning | Not |
|------|---------|-----|
| **Hide** | Persist a flag; row leaves the main list; **Hidden** section (or Hidden Bots) can Unhide. | Soft-delete, trash, or “gone from the product.” |
| **Archive** | Soft-delete the seat (recoverable, then purge). | Hide. Separate lifecycle. |

- [ ] Hide = persist flag + Hidden section. No hide-all requirement.
- [ ] Archive stays a different verb ([AGENT_LIFECYCLE.md](../AGENT_LIFECYCLE.md)
      — `archived` / restore / ~30 day purge). Do not overload Hide as
      archive.
- [ ] Open-swarm already ships this shape: right-click **Hide from
      sidebar**, Hidden Bots, persist
      `localStorage.swarm_hidden_agents` + `GET/PATCH /v1/preferences/`
      ([FEATURE_STATUS.md](../../FEATURE_STATUS.md) Web UI — Agent
      sidepane hide). Reuse it; do not add a second hide model.
- [ ] Rakazo / other fleet UIs: copy OMB Hide (flag + Hidden section)
      rather than a new “remove from rail” invention.

---

## 6. Infra CI is not a Success fail

**Empty-runner / fake-red GitHub Actions ≠ Success fail.**

Class: Chatty `#853` / `#849`; open-swarm
[#152](https://github.com/matthewhand/open-swarm/issues/152).
Same judgment already noted on kind-chat
([Issue #136](./ISSUE-136-kind-chat-e2e.md) — “Private CI may be
fake-red on unrelated jobs”).

- [ ] **Skeptic PASS** on the Issue Success items is the merge gate.
- [ ] An Actions job that never ran (empty runner), used a broken
      shared runner, or went red on an **unrelated** workflow is a
      **documented deviation**, not a Success fail.
- [ ] Document the deviation in the PR / QA note (which job, why it is
      not this Issue’s contract, which own-diff or local command did
      pass).
- [ ] Own-diff workflows that lock **this** change still matter. A
      collection `ImportError` on tip of `main` is still a must-fix
      ([FEATURE_STATUS.md](../../FEATURE_STATUS.md) — Test suite health).
- [ ] Do not block merge solely because a fleet-wide or leftover
      workflow is red for reasons outside the Issue.

---

## How seats reuse this file

| Seat | Use |
|------|-----|
| **open-swarm** | Remote-axis prove + hydrate prove + herdr pointer. Link from §11b. |
| **OMB / Rakazo** | Drive gates = §1 remote prove + §3 health. Hide = §5. |
| **Chatty / mcp-gateway / CLI-proxy** | Same-origin / CSRF (§2) and infra CI (§6) before inventing a local rule. |

New fleet Issues should checkbox against these six items (or mark N/A
with a reason) instead of rewriting them.
