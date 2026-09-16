# REQ-889 — Herdr Send cannot be submitted without a target

> One defect reported against the Remotes operate pane (#453): `Send` was the only
> control in the pane that posted without checking the field it depends on. The
> backend rejects an empty Herdr target by design, so the failure was guaranteed
> and the operator only learned about it after a round trip.

**Status: shipped.** Lock test:
`tests/unit/test_req889_herdr_send_target_guard.py`.
Behaviour tests: `webui/frontend/src/components/__tests__/RemotesSettings.test.tsx`
(the two `#453` cases) plus the two follow-up cases in §6.

> §6 records what browser verification of this guard turned up on the live LAN app:
> the guard held, but the pane it guarded could be showing **another remote's**
> targets. Both halves ship together.

---

## 1. Context

The reported message was exact and unimprovable — it just arrived too late:

```
herdr send: FAIL — target is required (Herdr pane / CLI id, e.g. w3:p1 or grok)
```

`_herdr_send` (`src/swarm/core/remotes.py:3329-3345`) guards on
`if not (target or "").strip()` before it resolves a mode or touches a client, so
the server is not at fault: an empty target can never be a valid Herdr send.
Herdr addresses *panes* (`w3:p1`) or managed CLIs (`grok`); there is no
"single default target" it could fall back to. Interrogate has the same
requirement and already communicated it by disabling its button.

Two things in `RemoteOperatePane` made the failure reachable anyway:

1. **`Send` had no guard.** `Interrogate CLI` carried
   `disabled={!botId.trim()}`; the Send button beside it carried only
   `loading={sendMutation.isPending}`. Nothing in the pane — not the input, not
   the button — indicated that the target was required for Herdr.
2. **The target was empty on arrival, and only an explicit List filled it.**
   `listMutation.onSuccess` sets `botId` from the first row (`if (!botId && bots[0]?.id)`),
   but the mutation was only ever triggered by the operator clicking **List CLIs**.
   So the pane's first Send was an empty-target Send, and the documented
   workaround ("click List CLIs first") was knowledge held outside the UI.

Evidence for the empty-arrival half came from the live pane: `List CLIs` returns
7 real members (`w2:pG`, `w2:pD`, `w3:p1`, …) and fills the field, while a pane
opened straight onto Send posts `target: ""`.

---

## 2. Requirement

**R1.** For kinds whose send requires a target, `Send` must be disabled while the
target field is blank, mirroring `Interrogate CLI` in the same pane.

**R2.** The pane must populate the target from the remote's own list without
requiring a separate click, so the guarded button reaches the enabled state on its
own.

**R3.** The guard is kind-scoped, not global. An empty target is legal for other
remotes (OMB creates a bot when none exists), so `Send` stays enabled for them.

**R4.** A remote whose target list comes back empty leaves `Send` disabled rather
than failing after a round trip.

**R5.** The backend contract is unchanged: `_herdr_send` keeps rejecting an empty
target, and its message stays as the last line of defence.

### Acceptance criteria

- [x] `requiresTarget` is derived from the remote kind (`isHerdrKind`) and gates
      the Send button's `disabled` attribute.
- [x] The pane lists targets once on mount, and the mount-time list is idempotent
      (a ref, not a render-dependent effect).
- [x] The first listed row is adopted as the target when the field is still blank,
      preserving the existing `if (!botId && bots[0]?.id)` behaviour so a target
      the operator already typed or picked is never overwritten.
- [x] A failed list surfaces through the existing `listed` error path; it does not
      throw and does not enable Send.
- [x] An empty target list leaves Send disabled.
- [x] Non-Herdr kinds post exactly as before (empty target allowed).

---

## 3. Deliberate scope

- **Only Herdr is guarded.** `requiresTarget = isHerdr` is written as a named,
  extensible predicate rather than an inline `isHerdr &&` so a second kind with
  the same contract is a one-line change. OMB is *not* included: its send creates a
  bot when none exist, so disabling Send on an empty target would remove a working
  path.
- **The auto-list is one shot per pane mount.** It is a `useRef` guard rather than
  an effect that depends on the mutation identity, which would re-list on every
  render. `List CLIs` remains available for a manual refresh.
- **The pane's own `required` attributes were left alone.** The prompt field is
  `required`; the target field is not, because requiring it would break the OMB
  create-on-send path. The button's `disabled` state is the correct place for a
  kind-specific rule.
- **The issue's underlying request — a second dropdown in the chat header — is
  out of scope here.** That is #436 (implemented by the still-open PR #437). This
  page covers only the dead end reached from Settings → Remotes.

---

## 4. Locked sources

| Behaviour | Source |
|-----------|--------|
| Kind-scoped requirement | `webui/frontend/src/components/RemotesSettings.tsx` (`const requiresTarget = isHerdr`) |
| Mount-time list (idempotent) | `webui/frontend/src/components/RemotesSettings.tsx` (`const autoListedRef = useRef(false)`) |
| Send button guard | `webui/frontend/src/components/RemotesSettings.tsx` (`disabled={requiresTarget && !botId.trim()}`) |
| Interrogate guard it mirrors | `webui/frontend/src/components/RemotesSettings.tsx` (`disabled={!botId.trim()}`) |
| Pane is keyed by remote id (§6) | `webui/frontend/src/components/SettingsSheet.tsx` (`<RemoteOperatePane key={selected.id} …>`) |
| Foreign result is ignored (§6) | `webui/frontend/src/components/RemotesSettings.tsx` (`const belongsHere = …`) |
| Backend rejection (unchanged) | `src/swarm/core/remotes.py` (`_herdr_send`) |
| Backend interrogate rejection | `src/swarm/core/remotes.py` (`_herdr_interrogate`) |

---

## 5. Verification

- `webui/frontend/src/components/__tests__/RemotesSettings.test.tsx` — *"lists
  targets on mount and enables Send without the operator clicking List (#453)"*
  asserts the first member is adopted and Send is enabled; *"keeps Send disabled
  when the target list comes back empty (#453)"* asserts the R4 state. The 10
  pre-existing pane cases (health, list, send, interrogate, sessions, routines)
  still pass unchanged.
- Three pre-existing tests had mocks that captured **any** `POST /v1/remotes/…`
  as a remote *create*. The mount-time list is a second such POST, so those
  matchers now exclude `/operate/` and keep asserting the create payload they were
  written for (`RemotesSettings.test.tsx` gained a `beforeEach` stub for the same
  reason).
- `tests/unit/test_req889_herdr_send_target_guard.py` pins the three source facts
  above so the guard cannot be silently dropped.
- Python suites that read this component as source text
  (`test_req131_omb_list_timeout.py`, `test_issue302_operate_timeouts.py`,
  `test_req149_scrollable_lists.py`, `test_issue305_anythingllm_sessions.py`) pass
  unchanged.
- Full frontend suite: same 11 pre-existing failures as the parent commit, with
  the two new `#453` cases added and passing; `tsc --noEmit` and `eslint` both
  unchanged (28 errors / 32 errors respectively, all pre-existing).

---

## 6. Follow-up: the pane kept the previous remote's targets

**Status: shipped** in the same PR. Verified in a real browser, not by reading code.

The closing ask was to confirm the guard "in the browser on the LAN app". Playwright
(headless Chromium) against `http://10.0.0.36:8002/` did confirm the guard — Send is
disabled with a blank target, enables once a target exists, and a re-list does not
clobber a target the operator picked — but the pane it guarded was not the pane it
claimed to be.

### Observed (live, 2026-09-17)

| Step | Pane heading | Target field | Rows shown |
|---|---|---|---|
| Open Settings → Remotes (default selection `omb`) | OpenMousBot | `3a383904-…` | 20 OMB bots |
| Switch **Remote** → `herdr` | **Herdr** | `3a383904-…` (unchanged) | **the same 20 OMB bots** |
| Switch back to `omb`, then `herdr` again | Herdr | unchanged | unchanged |

So the Herdr pane was showing OpenMousBot's bots, and — because R2 adopts the first
listed row — it auto-filled its target with an **OMB bot UUID**. The server's own
Herdr list (`op=list`, captured in the same page load) returned 7 members named
`w2:pG`, `w2:pD`, `w3:p1`, `w4:p1`, `w2`, `w3`, `w4`; none of them reached the UI.

This is worse than the empty-target dead end it replaced: the guard's precondition
was satisfied with a target no Herdr pane can accept, so the first Send would fail
against Herdr instead of against its own validation.

### Root cause

`SettingsSheet` rendered `{selected ? <RemoteOperatePane remote={selected} /> : null}`.
Same element type at the same position → React **reuses the instance** across a
Remote switch, so `listed`, `botId`, and the adopted target survived it. The
mount-time list in R2 is `useRef`-guarded and mount-only, so it never ran for the
newly selected remote either.

### Fix

1. `SettingsSheet.tsx` keys the pane by remote id — `key={selected.id}` — so a
   switch remounts it, which clears the previous remote's state and re-runs the
   mount list for the one now selected (the R2 behaviour, applied per remote).
2. `RemotesSettings.tsx` gains `belongsHere`, and every mutation's success handler
   ignores a result whose `remote` is not this pane's. Defence in depth: a target
   list from one remote is never a valid target for another, so a late or
   mismatched response cannot be adopted again.

### Tests (both fail against the unfixed pane)

- `RemotesSettings.test.tsx` — *"ignores a target list that belongs to another
  remote (#453)"*: a list result carrying `remote: 'omb'` must not populate the
  Herdr pane; Send stays disabled.
- `SettingsSheet.test.tsx` — *"reloads the pane when the Remote picker changes, so
  one remote never keeps another's targets (#453)"*: with `omb` and `herdr` both
  configured, switching the picker must load the new remote's own targets
  (`w2:pG`) and drop the old remote's rows.

Both were run with only the source fix stashed: they fail there and pass with it,
which is what makes them regressions rather than restatements.
