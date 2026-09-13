# REQ-847 — Stale hidden prefs reconciled against the live rail (#170)

> Hide ids (`agent:` / `team:` / `remote:`) that match **no live rail row** and
> no pinned id are dropped each session, so old server prefs can't keep teams,
> agents, or remotes hidden forever. The next prefs PATCH self-heals the server
> bag. Retro-fitted requirement + source-lock for the shipped fix.

**As-of:** branch `fix/149-cli-first-discovered-defaults` (dirty; feature shipped
in-session under #170).

**Issue:** [#170](https://github.com/matthewhand/open-swarm/issues/170)

## Requirement

1. `reconcileHiddenAgentIds(hidden, liveIds, pinnedIds)` keeps a hide id only
   when it matches a live row id **or** a pinned id.
2. Pinned ids stay hideable even when their row is a non-catalog pin.
3. Reconciliation is **skipped until every rail feed settles** (blueprints,
   rosters/teams, remotes, cli, herdr) so a mid-load moment can neither flash
   rows visible nor persist a trimmed hide list back to `/v1/preferences/`.
4. The existing seed/hydrate paths (`loadOrSeedHiddenAgentIds`) are unchanged.

## Acceptance criteria

- [x] `reconcileHiddenAgentIds` filters with `live.has(id) || pinned.has(id)`.
- [x] `AgentSidebar` computes `railDataPending` across all five feeds and gates
      `resolvedHiddenIds` on it.
- [x] `resolvedHiddenIds` feeds the debounced prefs PATCH (self-heal).

## Locked sources

| File | Role |
|------|------|
| `webui/frontend/src/lib/hiddenAgents.ts` | `reconcileHiddenAgentIds` |
| `webui/frontend/src/components/AgentSidebar.tsx` | rail feed gate + wiring |
| `webui/frontend/src/lib/__tests__/hiddenAgents.test.ts` | Behaviour spec of record (vitest) |

## Test map

- `tests/unit/test_req847_hidden_reconciliation.py` — source-lock (this REQ).
- `webui/frontend/src/lib/__tests__/hiddenAgents.test.ts` (vitest) — reconcile behaviour.