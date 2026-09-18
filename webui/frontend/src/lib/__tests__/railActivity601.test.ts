/**
 * #601 — the rail's time slot needs data, not just a designated owner.
 *
 * Server stamps `last_message_at` on remote rows and team rosters (the chat
 * store is the source that actually knows). The parsers normalise epoch *or*
 * ISO into the `lastMessageAt` the slot already understands; absence stays
 * absent — no fabricated "now", no "Invalid Date".
 */
import { describe, expect, it } from 'vitest'
import { parseRemote, type RemoteEntry } from '../remotesCatalog'
import { parseTeamRosters } from '../teamRosters'
import { getRowLastMessage } from '../chatTime'

describe('#601 parseRemote last_message_at', () => {
  const base = {
    id: 'trueforge',
    kind: 'trueforge',
    title: 'TrueForge box',
    configured: true,
    agents: [],
  }

  it('normalises an ISO instant', () => {
    const row = parseRemote({ ...base, last_message_at: '2026-09-18T10:00:00+00:00' })
    expect(row?.lastMessageAt).toBe(Date.parse('2026-09-18T10:00:00+00:00'))
  })

  it('normalises an epoch-ms instant', () => {
    const row = parseRemote({ ...base, last_message_at: 1758189600000 })
    expect(row?.lastMessageAt).toBe(1758189600000)
  })

  it('stays absent when the server sends none', () => {
    const row = parseRemote({ ...base }) as RemoteEntry
    expect(row.lastMessageAt).toBeUndefined()
  })
})

describe('#601 parseTeamRosters last_message_at', () => {
  const roster = {
    object: 'team_roster',
    id: 'demo-team',
    name: 'Demo Team',
    members: [],
  }

  it('normalises the instant onto the roster', () => {
    const [team] = parseTeamRosters({ object: 'list', data: [{ ...roster, last_message_at: '2026-09-18T11:00:00+00:00' }] })
    expect(team?.lastMessageAt).toBe(Date.parse('2026-09-18T11:00:00+00:00'))
  })

  it('stays absent when the server sends none', () => {
    const [team] = parseTeamRosters({ object: 'list', data: [roster] })
    expect(team?.lastMessageAt).toBeUndefined()
  })
})

describe('#601 getRowLastMessage accepts camelCase updatedAt', () => {
  it('reads updatedAt when snake_case keys are missing', () => {
    const result = getRowLastMessage('x', [], { updatedAt: 1758189600000 })
    expect(result.timestamp).toBe(1758189600000)
  })
})
