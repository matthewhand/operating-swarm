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
  {
    name: 'codex',
    // #711: session-resumable rows (REQ-104 payload), tagged `session`.
    sessions: [{ id: 'codex:main', label: 'codex main session' }],
  },
  { name: 'grok', models: ['grok-4', 'grok-3'] },
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
      'custom_blueprint',
    ])
    expect(rows.map((r) => r.kind)).toEqual(['api', 'cli', 'cli', 'remote', 'blueprint'])
  })

  it('empty payloads yield no rows — no stubs', () => {
    expect(buildComposerProviders({})).toEqual([])
  })

  it('carries declared defaults onto the provider rows', () => {
    const rows = buildComposerProviders({ api, clis, remotes, teams })
    const byId = new Map(rows.map((r) => [r.id, r]))
    expect(byId.get('api')?.defaultOptionId).toBe('prof-default')
    // #711: accepting "Use default" for a CLI always selects the CLI itself —
    // never a session id (sessions are a stage-2 explicit pick).
    expect(byId.get('cli:codex')?.defaultOptionId).toBe('codex')
    expect(byId.get('cli:grok')?.defaultOptionId).toBe('grok')
    expect(byId.get('remote:openmousbot')?.defaultOptionId).toBe('omb:planner')
    expect(byId.get('custom_blueprint')?.defaultOptionId).toBe('demo')
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

  it('cli provider lists resumable sessions tagged session, then models (#711)', () => {
    const rows = buildComposerProviders({ clis })
    const codex = rows.find((r) => r.id === 'cli:codex')!
    expect(composerOptionsForProvider({ clis }, codex)).toEqual([
      { id: 'codex:main', label: 'codex main session', tag: 'session' },
    ])
    const grok = rows.find((r) => r.id === 'cli:grok')!
    expect(composerOptionsForProvider({ clis }, grok)).toEqual([
      { id: 'grok-4', label: 'grok-4', tag: 'model' },
      { id: 'grok-3', label: 'grok-3', tag: 'model' },
    ])
  })

  it('a CLI with neither sessions nor models yields no options — honest empty (#711)', () => {
    const rows = buildComposerProviders({ clis: [{ name: 'bare' }] })
    const bare = rows.find((r) => r.id === 'cli:bare')!
    expect(composerOptionsForProvider({ clis: [{ name: 'bare' }] }, bare)).toEqual([])
  })

  it('remote provider lists its agent bots; team lists its members', () => {
    const rows = buildComposerProviders({ remotes })
    const remote = rows.find((r) => r.id === 'remote:openmousbot')!
    expect(composerOptionsForProvider({ remotes }, remote)).toHaveLength(2)
    const teamProvider = { id: 'team:demo', label: 'demo team', kind: 'team' as const }
    expect(composerOptionsForProvider({ teams }, teamProvider)).toEqual([
      { id: 'team:demo:worker1', label: 'worker1' },
    ])
  })

  it('#832: custom blueprint provider lists defined blueprints and teams', () => {
    const blueprints = [{ id: 'codey', label: 'Codey', description: 'Coding bot' }]
    const rows = buildComposerProviders({ blueprints, teams })
    const bpRow = rows.find((r) => r.id === 'custom_blueprint')!
    expect(bpRow).toBeDefined()
    expect(bpRow.kind).toBe('blueprint')
    expect(bpRow.label).toBe('Custom Blueprint')
    expect(bpRow.description).toBe('1 blueprint, 1 team')
    expect(bpRow.defaultOptionId).toBe('codey')

    const options = composerOptionsForProvider({ blueprints, teams }, bpRow)
    expect(options).toEqual([
      { id: 'codey', label: 'Codey', description: 'Coding bot', tag: 'blueprint', kind: 'blueprint' },
      { id: 'demo', label: 'demo team', tag: 'team', kind: 'team' },
    ])
  })

  it('#832: omits custom_blueprint provider row when neither blueprints nor teams exist', () => {
    const rows = buildComposerProviders({ api, clis, remotes })
    expect(rows.find((r) => r.id === 'custom_blueprint')).toBeUndefined()
  })

  it('unknown remote/team/cli ids yield no options (api has a single id-independent gateway)', () => {
    const rows = buildComposerProviders({ api, remotes })
    expect(composerOptionsForProvider({ remotes }, { ...rows[0], id: 'remote:nope', kind: 'remote' })).toEqual([])
    expect(composerOptionsForProvider({ api }, rows[0])).toHaveLength(2)
  })
})
