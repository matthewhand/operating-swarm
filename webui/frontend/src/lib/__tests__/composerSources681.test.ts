/**
 * #681/#682/#683 — the composer picker's provider list and per-provider
 * option sets, built from the same data the seat controls already use.
 *
 * Pure: ChatPage feeds in the query payloads (LLM profiles, discovered CLIs,
 * configured remotes, team rosters) and this module shapes the two-stage
 * workflow's inputs. No hardcoded stubs — an empty payload yields no rows.
 */
import { describe, expect, it } from 'vitest'
import {
  buildComposerProviders,
  composerOptionsForProvider,
  type ComposerApiSource,
  type ComposerCliSource,
  type ComposerRemoteSource,
  type ComposerTeamSource,
} from '../composerSources'

const api: ComposerApiSource = {
  profiles: [
    { id: 'prof-default', label: 'Default profile' },
    { id: 'prof-a', label: 'Profile A' },
  ],
  defaultProfileId: 'prof-default',
}

const clis: ComposerCliSource[] = [
  { name: 'codex', agents: [{ id: 'codex:main', label: 'codex main session' }] },
  { name: 'grok', agents: [] },
]

const remotes: ComposerRemoteSource[] = [
  {
    id: 'openmousbot',
    label: 'openmousbot',
    agents: [
      { id: 'omb:planner', label: 'planner' },
      { id: 'omb:critic', label: 'critic' },
    ],
    defaultAgentId: 'omb:planner',
  },
]

const teams: ComposerTeamSource[] = [
  {
    id: 'demo',
    label: 'demo team',
    members: [{ id: 'team:demo:worker1', label: 'worker1' }],
    defaultMemberId: 'team:demo:worker1',
  },
]

describe('#681 provider list from live sources', () => {
  it('builds one row per provider kind from the payloads', () => {
    const rows = buildComposerProviders({ api, clis, remotes, teams })
    expect(rows.map((r) => r.id)).toEqual([
      'api',
      'cli:codex',
      'cli:grok',
      'remote:openmousbot',
      'team:demo',
    ])
    expect(rows.map((r) => r.kind)).toEqual(['api', 'cli', 'cli', 'remote', 'team'])
  })

  it('empty payloads yield no rows — no stubs', () => {
    expect(buildComposerProviders({})).toEqual([])
  })

  it('carries declared defaults onto the provider rows', () => {
    const rows = buildComposerProviders({ api, clis, remotes, teams })
    const byId = new Map(rows.map((r) => [r.id, r]))
    expect(byId.get('api')?.defaultOptionId).toBe('prof-default')
    expect(byId.get('cli:codex')?.defaultOptionId).toBe('codex:main')
    // A CLI with no session data defaults to itself: the provider IS the
    // agent-dimension choice, so "Use default" still selects it.
    expect(byId.get('cli:grok')?.defaultOptionId).toBe('grok')
    expect(byId.get('remote:openmousbot')?.defaultOptionId).toBe('omb:planner')
    expect(byId.get('team:demo')?.defaultOptionId).toBe('team:demo:worker1')
  })
})

describe('#682/#683 stage-2 option sets per provider', () => {
  it('api provider lists its real profiles', () => {
    const rows = buildComposerProviders({ api })
    expect(composerOptionsForProvider({ api }, rows[0]).map((o) => o.id)).toEqual([
      'prof-default',
      'prof-a',
    ])
  })

  it('cli provider lists only its own configured agents', () => {
    const rows = buildComposerProviders({ clis })
    const codex = rows.find((r) => r.id === 'cli:codex')!
    expect(composerOptionsForProvider({ clis }, codex)).toEqual([
      { id: 'codex:main', label: 'codex main session' },
    ])
  })

  it('remote provider lists its agent bots; team lists its members', () => {
    const rows = buildComposerProviders({ remotes, teams })
    const remote = rows.find((r) => r.id === 'remote:openmousbot')!
    const team = rows.find((r) => r.id === 'team:demo')!
    expect(composerOptionsForProvider({ remotes }, remote)).toHaveLength(2)
    expect(composerOptionsForProvider({ teams }, team)).toEqual([
      { id: 'team:demo:worker1', label: 'worker1' },
    ])
  })

  it('unknown remote/team/cli ids yield no options (api has a single id-independent gateway)', () => {
    const rows = buildComposerProviders({ api, remotes })
    expect(composerOptionsForProvider({ remotes }, { ...rows[0], id: 'remote:nope', kind: 'remote' })).toEqual([])
    expect(composerOptionsForProvider({ api }, rows[0])).toHaveLength(2)
  })
})
