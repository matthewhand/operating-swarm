# ADR-015: Identity and provider binding are separate axes

**Status:** Accepted (REQ-904 / #502)

## Context

A user reported: *I have an agent named **Herdr** and I set its remote
inference to **OpenMousBot**. That means "Herdr uses OpenMousBot" — but the UI
switched me to the OpenMousBot agent, navigated away from Herdr, and discarded
my session.*

The binding store's own header (`lib/agentRemote.ts`) already documented the
right concept — "per-agent remote binding" — but the wiring fused two
independent axes into one control:

| Axis | Question it answers | Owner | Mutating it may… |
|---|---|---|---|
| **Identity** | *Which agent am I talking to?* (a named agent, a team, a remote seat) | the route/URL + session selection | change the thread, the session, the seat |
| **Provider binding** | *Which backend does **this** agent use?* | a persisted property of that agent | **nothing else** — same agent, same thread, same session |

## Decision

1. **Two axes, never fused.** Identity lives in the route/URL and session
   selection. A provider binding is `{ownerAgentId, remoteId, kind}` persisted
   per agent.
2. **The binding subject is the agent, and only the agent.**
   `resolveAgentBindingSubject()` is the single owner of this rule. A remote
   id in the URL is an identity being viewed and can never become a binding
   subject — a remote is never "bound to itself".
3. **Provider changes are inert.** `applyRemoteRoutingChange()` is the single
   decision point for the navbar's remote picker. A provider pick writes the
   binding and nothing else: no `?remote=`, no `session` delete, no
   navigation. Only an identity pick (while `?remote=` is in the URL) may
   navigate and reset the session — that existing behaviour is preserved and
   pinned by test.
4. **Viewing is not configuring.** In `resolveBoundRemoteId()`, a persisted
   agent binding outranks the URL remote. The URL decides what a *remote
   seat's* view shows only when no agent binding exists.
5. **One store, one key space.** `AGENT_REMOTE_BINDINGS_KEY` is keyed by agent
   id only.

The canonical illustration, settled: *"toggle the remote on Herdr"* means
Herdr's backend is now OpenMousBot — Herdr stays selected, Herdr's thread and
session survive, and the URL does not change.

## Enforcement

- `resolveAgentBindingSubject` — one helper, every surface (no second
  implementation of "whose binding is this?").
- `applyRemoteRoutingChange` — one helper for the picker's identity/provider
  decision; provider-inertness is asserted affirmatively (`deleteSession:
  false`), so a consumer cannot default into the old fusion.
- Invariant tests pin each rule: `agentRemoteDoctrine502.test.ts` (subject +
  precedence + round-trip), `remoteRouting502.test.ts` (inert provider axis,
  preserved identity axis), `ChatPage.remoteDoctrine502.test.tsx` (the
  Herdr/OpenMousBot scenario end to end).

## Consequences

- Copy that says "Remote" while meaning "the agent I am talking to" is now
  wrong by definition and can be fixed incrementally without touching data
  flow (out of scope here, per the issue).
- Server-side `agent_dropdowns` hydration (`userPrefs.ts`) already keys by
  agent id and therefore aligns with this ADR unchanged.
