import { describe, expect, it } from 'vitest'
import type { CliAgentsInfo } from '../api'
import {
  ADD_AGENT_REMOTE_GROUP_IDS,
  OTHER_CLI_PROVIDER,
  agentCliProvider,
  cliProviderKey,
  detectedCliProviders,
  filterByOrigin,
  filterCliAgents,
  filterRemotesByImpl,
  groupByOrigin,
  groupCliAgents,
  groupRemotesByImpl,
  remoteImplGroupId,
  remoteImplGroupLabel,
  toggleGroupFilter,
} from '../addAgentGroups'

const catalog: CliAgentsInfo = {
  clis: ['agy', 'claude', 'codex', 'gemini', 'grok'],
  discovered: ['grok', 'claude'],
  installed: ['grok', 'claude'],
  configured: ['grok'],
  native_consensus: {},
  catalog: {},
}

describe('addAgentGroups (#68)', () => {
  it('extracts a CLI provider from a command, ignoring rail placeholders', () => {
    expect(cliProviderKey('grok -p {prompt}')).toBe('grok')
    expect(cliProviderKey('/usr/bin/claude')).toBe('claude')
    expect(cliProviderKey('installed')).toBe('')
    expect(cliProviderKey('not on PATH')).toBe('')
    expect(agentCliProvider({ provider: 'agy', command: 'ignored' })).toBe('agy')
  })

  it('lists detected CLI providers from discovered/configured, not the full clis catalog', () => {
    expect(detectedCliProviders(catalog)).toEqual(['grok', 'claude'])
    expect(detectedCliProviders({ clis: ['grok'], native_consensus: {}, catalog: {} })).toEqual([
      'grok',
    ])
    expect(
      detectedCliProviders({
        clis: ['agy', 'claude', 'grok'],
        discovered: [],
        installed: [],
        configured: [],
        native_consensus: {},
        catalog: {},
      }),
    ).toEqual([])
  })

  it('groups CLI agents by detected provider with counts and extra assigned CLIs', () => {
    const groups = groupCliAgents(
      [
        { command: 'grok' },
        { command: 'grok -p hi' },
        { command: 'claude' },
        { command: 'custom-tool' },
        { command: 'installed' },
      ],
      catalog,
    )
    expect(groups).toEqual([
      { id: 'grok', label: 'grok', count: 2 },
      { id: 'claude', label: 'claude', count: 1 },
      { id: 'custom-tool', label: 'custom-tool', count: 1 },
      { id: OTHER_CLI_PROVIDER, label: 'Other', count: 1 },
    ])
  })

  it('filters CLI agents by provider and clears when the same id is clicked again', () => {
    const agents = [{ command: 'grok' }, { command: 'claude' }, { command: 'installed' }]
    expect(filterCliAgents(agents, 'grok').map((row) => row.command)).toEqual(['grok'])
    expect(filterCliAgents(agents, OTHER_CLI_PROVIDER).map((row) => row.command)).toEqual([
      'installed',
    ])
    expect(filterCliAgents(agents, null)).toHaveLength(3)
    expect(toggleGroupFilter(null, 'grok')).toBe('grok')
    expect(toggleGroupFilter('grok', 'grok')).toBeNull()
    expect(toggleGroupFilter('grok', 'claude')).toBe('claude')
  })

  it('groups API/Blueprint agents as custom vs catalog with counts', () => {
    const agents = [
      { id: 'c1', isCustom: true },
      { id: 'c2', isCustom: true },
      { id: 'k1', isCustom: false },
    ]
    expect(groupByOrigin(agents)).toEqual([
      { id: 'custom', label: 'Custom', count: 2 },
      { id: 'catalog', label: 'Catalog', count: 1 },
    ])
    expect(filterByOrigin(agents, 'custom').map((row) => row.id)).toEqual(['c1', 'c2'])
    expect(filterByOrigin(agents, 'catalog').map((row) => row.id)).toEqual(['k1'])
    expect(filterByOrigin(agents, null)).toHaveLength(3)
    expect(groupByOrigin([])).toEqual([])
  })

  it('groups remotes by implementation with Hermes/OpenMousBot/Rakazo/Herdr/nested counts', () => {
    const groups = groupRemotesByImpl(
      [
        { id: 'h1', kind: 'hermes', title: 'Hermes', base_url: 'http://h' },
        { id: 'o1', kind: 'omb', title: 'OpenMousBot', base_url: 'http://o' },
        { id: 'o2', kind: 'openmousbot', title: 'Bot 2', base_url: 'http://o2' },
        { id: 'n1', kind: 'open-swarm', title: 'Nested', base_url: 'http://n' },
      ],
      [
        { id: 'hermes', label: 'Hermes' },
        { id: 'omb', label: 'OpenMousBot' },
        { id: 'rakazo', label: 'Rakazo' },
        { id: 'herdr', label: 'Herdr' },
        { id: 'open-swarm', label: 'open-swarm' },
      ],
    )
    expect(ADD_AGENT_REMOTE_GROUP_IDS).toEqual([
      'hermes',
      'omb',
      'rakazo',
      'herdr',
      'open-swarm',
    ])
    expect(groups.map((row) => [row.id, row.label, row.count])).toEqual([
      ['hermes', 'Hermes', 1],
      ['omb', 'OpenMousBot', 2],
      ['rakazo', 'Rakazo', 0],
      ['herdr', 'Herdr', 0],
      ['open-swarm', 'nested', 1],
    ])
    expect(groups.find((row) => row.id === 'omb')?.label).not.toMatch(/\bOMB\b/)
    expect(remoteImplGroupId({ kind: 'nested' })).toBe('open-swarm')
    expect(remoteImplGroupLabel('open-swarm')).toBe('nested')
    expect(filterRemotesByImpl([{ id: 'h1', kind: 'hermes' }, { id: 'o1', kind: 'omb' }], 'omb')).toEqual([
      { id: 'o1', kind: 'omb' },
    ])
  })
})
