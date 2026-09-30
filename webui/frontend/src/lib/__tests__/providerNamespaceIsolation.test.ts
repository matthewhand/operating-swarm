/**
 * Provider-namespace isolation across every composer provider kind.
 *
 * Each provider's stage-2 option set must come from *its own* namespace and
 * nothing else:
 *   - api      → LLM profiles only (never a CLI model id)
 *   - cli:<x>  → that CLI's own probe/models only (never api profile ids or
 *                another CLI's models)
 *   - remote   → that remote's own agents/herdr panes
 *   - team     → that team's own members
 *
 * Picking a different provider must return a disjoint set — no stale options
 * carried across kinds.
 */
import { describe, expect, it } from 'vitest'
import {
  buildComposerProviders,
  composerOptionsForProvider,
  type ComposerSources,
} from '../composerSources'
import { providerIconKey } from '../providerIcons'

const sources: ComposerSources = {
  api: {
    profiles: [
      { id: 'litellm/orchestration', label: 'User chat / orchestration' },
      { id: 'anthropic/claude-sonnet-4-6', label: 'Claude Sonnet' },
    ],
    defaultProfileId: 'litellm/orchestration',
  },
  clis: [
    { name: 'codex', models: ['gpt-5-codex', 'codex-mini'] },
    { name: 'grok', models: ['grok-4', 'grok-3'] },
  ],
  remotes: [
    {
      id: 'hermes',
      label: 'Hermes',
      agents: [{ id: 'hermes:planner', label: 'planner' }],
      herdrAgents: [{ id: 7, name: 'pane-7' }],
    },
  ],
  teams: [
    {
      id: 'rig-one',
      label: 'Rig One',
      members: [{ id: 'rig-one:worker', label: 'worker' }],
    },
  ],
}

const provider = (id: string) => {
  const row = buildComposerProviders(sources).find((r) => r.id === id)
  if (!row) throw new Error(`missing provider ${id}`)
  return row
}

const ids = (id: string) => composerOptionsForProvider(sources, provider(id)).map((o) => o.id)

describe('provider namespace isolation', () => {
  it('api offers its profiles only — never a CLI model id', () => {
    const apiIds = ids('api')
    expect(apiIds).toEqual(['litellm/orchestration', 'anthropic/claude-sonnet-4-6'])
    expect(apiIds).not.toContain('gpt-5-codex')
    expect(apiIds).not.toContain('grok-4')
  })

  it('a CLI offers its own models only — never api profile ids or another CLI', () => {
    const codex = ids('cli:codex')
    expect(codex).toEqual(['gpt-5-codex', 'codex-mini'])
    expect(codex).not.toContain('litellm/orchestration')
    expect(codex).not.toContain('anthropic/claude-sonnet-4-6')
    expect(codex).not.toContain('grok-4')

    const grok = ids('cli:grok')
    expect(grok).toEqual(['grok-4', 'grok-3'])
    expect(grok).not.toContain('codex-mini')
    expect(grok).not.toContain('litellm/orchestration')
  })

  it('a remote offers its own agents/panes — never api or cli ids', () => {
    const hermes = ids('remote:hermes')
    expect(hermes).toEqual(['hermes:planner', 'pane-7'])
    expect(hermes).not.toContain('litellm/orchestration')
    expect(hermes).not.toContain('gpt-5-codex')
  })

  it('a team offers its own members — never api or cli ids', () => {
    const team = composerOptionsForProvider(sources, {
      id: 'team:rig-one',
      label: 'Rig One',
      kind: 'team',
    })
    expect(team.map((o) => o.id)).toEqual(['rig-one:worker'])
  })

  it('switching provider kind yields a disjoint option set (no stale carry-over)', () => {
    const api = new Set(ids('api'))
    const codex = new Set(ids('cli:codex'))
    const grok = new Set(ids('cli:grok'))
    const remote = new Set(ids('remote:hermes'))

    for (const id of codex) expect(api.has(id)).toBe(false)
    for (const id of grok) expect(api.has(id)).toBe(false)
    for (const id of codex) expect(grok.has(id)).toBe(false)
    for (const id of remote) expect(api.has(id)).toBe(false)
  })

  it('a provider with no matching source yields no options (honest empty)', () => {
    expect(
      composerOptionsForProvider(sources, { id: 'cli:absent', label: 'absent', kind: 'cli' }),
    ).toEqual([])
    expect(
      composerOptionsForProvider(sources, { id: 'remote:absent', label: 'absent', kind: 'remote' }),
    ).toEqual([])
  })
})

describe('provider icon namespace', () => {
  it('a CLI seat never pulls an API provider icon from its model string', () => {
    // The model dimension is API-only; a CLI model string must not resolve to
    // an LLM provider brand on a CLI seat.
    expect(
      providerIconKey({ seatKind: 'cli', providerId: '', modelId: 'claude-3-5-sonnet' }),
    ).toBe('cli')
    expect(providerIconKey({ seatKind: 'cli', providerId: 'codex' })).toBe('cli')
  })
})
