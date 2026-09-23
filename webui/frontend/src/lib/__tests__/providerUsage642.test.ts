/**
 * #642 — provider/type controls lock while agents are registered on them.
 *
 * The counting is data-driven (#551): CLI usage comes from the cli-agents
 * rail payload (`kind === 'cli'`, `cli === <name>`); remote usage comes from
 * the remotes payload's per-remote `agents` rows plus persisted per-agent
 * remote bindings (localStorage `swarm_agent_remote_bindings`). Zero
 * dependents → the control behaves exactly as before.
 */
import { describe, expect, it } from 'vitest'
import { providerDependents, providerUsageLabel } from '../providerUsage'
import type { CliAgentsInfo } from '../api'
import type { RemoteEntry } from '../remotesCatalog'

function railCli(name: string, cli: string): NonNullable<CliAgentsInfo['rail']>[number] {
  return {
    id: name,
    object: 'cli.agent' as const,
    name,
    cli,
    kind: 'cli' as const,
    description: `${name} seat`,
    installed: true,
  }
}

describe('providerDependents — CLI providers', () => {
  const info: CliAgentsInfo = {
    clis: ['grok', 'omp'],
    configured: ['grok', 'omp'],
    native_consensus: {},
    catalog: {},
    rail: [
      railCli('Grok seat', 'grok'),
      railCli('Grok seat 2', 'grok'),
      { ...railCli('API seat', 'orchestration'), kind: 'api' as const },
    ],
  }

  it('counts rail seats whose kind is cli and cli matches', () => {
    expect(providerDependents.cli(info, 'grok')).toBe(2)
  })

  it('returns zero for a CLI no seat uses', () => {
    expect(providerDependents.cli(info, 'omp')).toBe(0)
  })

  it('never counts api-kind rows as CLI dependents', () => {
    expect(providerDependents.cli(info, 'orchestration')).toBe(0)
  })

  it('is robust to missing payloads', () => {
    expect(providerDependents.cli(null, 'grok')).toBe(0)
    expect(providerDependents.cli(undefined, 'grok')).toBe(0)
  })
})

describe('providerDependents — remote instances', () => {
  const railRemote = (id: string, agentIds: string[]): RemoteEntry => ({
    id,
    kind: id,
    title: id,
    configured: true,
    agents: agentIds.map((agentId) => ({ id: agentId, name: agentId })),
  })

  it('counts agents listed on the remote entry and persisted bindings', () => {
    localStorage.setItem(
      'swarm_agent_remote_bindings',
      JSON.stringify({ bee: { id: 'omb', kind: 'omb' }, ada: { id: 'herdr', kind: 'herdr' } }),
    )
    try {
      const catalog = [
        railRemote('omb', ['omb-agent']),
        railRemote('herdr', []),
      ]
      // omb: one catalog row + one persisted binding; herdr: one binding only.
      expect(providerDependents.remote(catalog, 'omb')).toBe(2)
      expect(providerDependents.remote(catalog, 'herdr')).toBe(1)
    } finally {
      localStorage.removeItem('swarm_agent_remote_bindings')
    }
  })

  it('de-duplicates an agent that is both bound and listed', () => {
    localStorage.setItem(
      'swarm_agent_remote_bindings',
      JSON.stringify({ bee: { id: 'omb', kind: 'omb' } }),
    )
    try {
      const catalog = [railRemote('omb', ['bee'])]
      expect(providerDependents.remote(catalog, 'omb')).toBe(1)
    } finally {
      localStorage.removeItem('swarm_agent_remote_bindings')
    }
  })

  it('zero dependents when nothing binds or lists the remote', () => {
    expect(providerDependents.remote([railRemote('rakazo', [])], 'rakazo')).toBe(0)
  })
})

describe('providerUsageLabel', () => {
  it('names the plain tooltip when one agent depends on the type', () => {
    expect(providerUsageLabel(1)).toBe('Agents using this type of provider are still configured')
  })

  it('appends the count when several agents depend on the type', () => {
    expect(providerUsageLabel(3)).toBe(
      'Agents using this type of provider are still configured (3 agents)',
    )
  })

  it('is empty when unused (no tooltip, control stays enabled)', () => {
    expect(providerUsageLabel(0)).toBe('')
  })
})
