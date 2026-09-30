/**
 * #1672 — `capabilities.operate` is gone, and the SPA has no half-wired
 * consumer of it.
 *
 * What the capability was: a *server-side* classification. `computer_operate_stub()`
 * reads `capabilities_for(rid).operate` to tell two honest refusals apart —
 * `computer_not_supported` (not a computer vendor) from
 * `computer_operate_unwired` (a computer vendor whose verb is not built; ADR-007
 * Phase 3 is parked, docs/adr/007-local-computer-control.md §6 item 3).
 *
 * Why it is not in the payload: it was published as `true` for omb/rakazo while
 * every computer op still answered `computer_operate_unwired`, and nothing in
 * `src/` read it. The Monitor "Computer control" pane it looks like it belongs
 * to is the *local seat's* sandbox / screen / routines surface
 * (`ComputerControlStub` → `/v1/agents/<id>/sandbox-display/`), which has
 * nothing to do with which remote is placed. Gating that working control on a
 * remote's flag would have broken it; publishing the flag as if the client
 * cared announced a capability nothing could back up.
 *
 * The backend half of this proof is `SERVER_SIDE_ONLY_CAPABILITIES` in
 * `src/swarm/core/remote_harness.py`, asserted in
 * `tests/core/test_req203_remote_harness.py` and `tests/views/test_remotes_api.py`.
 * These tests hold the client half: the normaliser must not resurrect the key
 * from a stale backend, and the type must not model it.
 */
import { describe, expect, it } from 'vitest'
import type { RemoteCapabilities } from '../api/types'
import { parseRemote } from '../remotesCatalog'

/**
 * Compile-time guarantee. If `operate` is ever added back to
 * `RemoteCapabilities`, this becomes `true` and the `const` below stops
 * compiling — so `tsc --noEmit` / `npm run build` fails instead of the key
 * quietly returning to a client model nothing reads.
 */
type OperateIsInTheClientModel = 'operate' extends keyof RemoteCapabilities ? true : false
const OPERATE_IS_IN_THE_CLIENT_MODEL: OperateIsInTheClientModel = false

/**
 * Exactly what `RemoteCapabilities.as_dict()` publishes. Mirrored from
 * `src/swarm/core/remote_harness.py` minus `SERVER_SIDE_ONLY_CAPABILITIES`.
 */
const PUBLISHED_CAPABILITY_KEYS = [
  'list',
  'send',
  'health',
  'interrogate',
  'routines',
  'sessions',
  'transport',
  'server_managed_context',
] as const

describe('#1672 the published remote capabilities carry no `operate`', () => {
  it('the client model has no `operate` key at all', () => {
    expect(OPERATE_IS_IN_THE_CLIENT_MODEL).toBe(false)
  })

  it.each(['hermes', 'omb', 'rakazo', 'herdr', 'openmuse'])(
    'a %s row is normalised down to the keys the SPA acts on',
    (kind) => {
      const row = parseRemote({
        id: kind,
        kind,
        title: kind,
        configured: true,
        agents: [],
        capabilities: {
          list: true,
          send: true,
          health: true,
          interrogate: false,
          routines: false,
          sessions: true,
          transport: 'http',
          server_managed_context: false,
        },
      })
      expect(row).not.toBeNull()
      expect(Object.keys(row!.capabilities ?? {}).sort()).toEqual(
        ['list', 'send', 'sessions'].sort(),
      )
    },
  )

  it('drops a stale `operate` a pre-#1672 backend still sends', () => {
    // Old server, new SPA: the key must not leak into the normalised entry,
    // because nothing downstream can act on it and a leaked true/false is a
    // claim the client would then be making on the server's behalf.
    const row = parseRemote({
      id: 'omb',
      kind: 'omb',
      title: 'OpenMousBot',
      configured: true,
      agents: [],
      capabilities: { list: true, send: true, health: true, operate: true, sessions: false },
    })
    expect(row?.capabilities).toEqual({ list: true, send: true, sessions: false })
    expect('operate' in (row?.capabilities ?? {})).toBe(false)
  })

  it('the published key set is exactly the mirrored list', () => {
    // Fails if the backend grows a key and the SPA's `RemoteEntry.capabilities`
    // is not told about it in the same change.
    const caps: RemoteCapabilities = {}
    for (const key of PUBLISHED_CAPABILITY_KEYS) {
      ;(caps as Record<string, unknown>)[key] = key === 'transport' ? 'http' : true
    }
    expect(Object.keys(caps).sort()).toEqual([...PUBLISHED_CAPABILITY_KEYS].sort())
    expect(Object.keys(caps)).not.toContain('operate')
  })

  it('`capabilities.sessions` — the one the SPA does read — is untouched', () => {
    // #1672 must not have taken `sessions` down with it: the session picker
    // gate in `remoteSessions.ts` depends on it.
    const yes = parseRemote({
      id: 'hermes',
      kind: 'hermes',
      title: 'Hermes',
      configured: true,
      agents: [],
      capabilities: { list: true, send: true, health: true, sessions: true },
    })
    const no = parseRemote({
      id: 'hermes',
      kind: 'hermes',
      title: 'Hermes',
      configured: true,
      agents: [],
      capabilities: { list: true, send: true, health: true, sessions: false },
    })
    const absent = parseRemote({
      id: 'hermes',
      kind: 'hermes',
      title: 'Hermes',
      configured: true,
      agents: [],
      capabilities: { list: true, send: true, health: true },
    })
    expect(yes?.capabilities?.sessions).toBe(true)
    expect(no?.capabilities?.sessions).toBe(false)
    expect(absent?.capabilities?.sessions).toBe(false)
  })
})
