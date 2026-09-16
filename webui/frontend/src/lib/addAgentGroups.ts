/**
 * Add-agent popup grouping (#68): provider / origin / impl rows with counts.
 * Clicking a row filters the agent list; the same id again (or clear) removes it.
 */

import type { CliAgentsInfo, RemoteConnection, RemoteKind } from './api'
import { configuredCliNames, discoveredCliNames } from './cliAgents'
import { remoteKindLabel } from './remotes'

export const OTHER_CLI_PROVIDER = 'other'

export const ORIGIN_CUSTOM = 'custom'
export const ORIGIN_CATALOG = 'catalog'

/** Remote impls the Add-agent Remote tab always lists (issue #68). */
export const ADD_AGENT_REMOTE_GROUP_IDS = [
  'hermes',
  'omb',
  'rakazo',
  'herdr',
  'open-swarm',
] as const

export interface AddAgentGroup {
  id: string
  label: string
  count: number
}

const CLI_PLACEHOLDER_COMMANDS = new Set(['installed', 'not on path', 'not on PATH'])

function uniquePreserve(names: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of names) {
    const name = String(raw).trim()
    if (!name) continue
    const key = name.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(name)
  }
  return out
}

/** First token / basename of a CLI command; empty for rail placeholders. */
export function cliProviderKey(command?: string | null): string {
  const raw = (command || '').trim()
  if (!raw) return ''
  if (CLI_PLACEHOLDER_COMMANDS.has(raw) || /^not on path$/i.test(raw)) return ''
  const first = raw.split(/\s+/)[0] || ''
  const base = first.split(/[/\\]/).pop() || first
  return base.trim().toLowerCase()
}

export function agentCliProvider(agent: {
  provider?: string | null
  command?: string | null
}): string {
  const explicit = (agent.provider || '').trim().toLowerCase()
  if (explicit) return explicit
  return cliProviderKey(agent.command)
}

/**
 * Detected CLI providers: PATH seed + configured, else legacy `clis`
 * when discovery fields are absent (older mocks / clients).
 */
export function detectedCliProviders(info?: CliAgentsInfo | null): string[] {
  if (!info) return []
  const hasDiscoveryFields =
    info.discovered !== undefined ||
    info.installed !== undefined ||
    info.configured !== undefined
  const discovered = discoveredCliNames(info)
  const configured = configuredCliNames(info)
  const fromClis = Array.isArray(info.clis)
    ? info.clis.map((name) => String(name).trim()).filter(Boolean)
    : []
  if (hasDiscoveryFields) return uniquePreserve([...discovered, ...configured])
  return uniquePreserve(fromClis)
}

export function groupCliAgents(
  agents: Array<{ provider?: string | null; command?: string | null }>,
  info?: CliAgentsInfo | null,
): AddAgentGroup[] {
  const providers = detectedCliProviders(info)
  const counts = new Map<string, number>()
  for (const name of providers) counts.set(name.toLowerCase(), 0)

  let other = 0
  const extras = new Map<string, number>()
  for (const agent of agents) {
    const key = agentCliProvider(agent)
    if (!key) {
      other += 1
      continue
    }
    if (counts.has(key)) {
      counts.set(key, (counts.get(key) || 0) + 1)
      continue
    }
    extras.set(key, (extras.get(key) || 0) + 1)
  }

  const groups: AddAgentGroup[] = providers.map((name) => ({
    id: name.toLowerCase(),
    label: name,
    count: counts.get(name.toLowerCase()) || 0,
  }))
  for (const [id, count] of extras) {
    groups.push({ id, label: id, count })
  }
  if (other > 0) {
    groups.push({ id: OTHER_CLI_PROVIDER, label: 'Other', count: other })
  }
  return groups
}

export function filterCliAgents<T extends { provider?: string | null; command?: string | null }>(
  agents: T[],
  providerId: string | null,
): T[] {
  if (!providerId) return agents
  const want = providerId.toLowerCase()
  return agents.filter((agent) => {
    const key = agentCliProvider(agent)
    if (want === OTHER_CLI_PROVIDER) return !key
    return key === want
  })
}

export function groupByOrigin(agents: Array<{ isCustom: boolean }>): AddAgentGroup[] {
  let custom = 0
  let catalog = 0
  for (const agent of agents) {
    if (agent.isCustom) custom += 1
    else catalog += 1
  }
  if (custom === 0 && catalog === 0) return []
  return [
    { id: ORIGIN_CUSTOM, label: 'Custom', count: custom },
    { id: ORIGIN_CATALOG, label: 'Catalog', count: catalog },
  ]
}

export function filterByOrigin<T extends { isCustom: boolean }>(
  agents: T[],
  originId: string | null,
): T[] {
  if (!originId) return agents
  if (originId === ORIGIN_CUSTOM) return agents.filter((agent) => agent.isCustom)
  if (originId === ORIGIN_CATALOG) return agents.filter((agent) => !agent.isCustom)
  return agents
}

export function remoteImplGroupId(remote: { kind?: string; id?: string; impl?: string }): string {
  const raw = (remote.impl || remote.kind || remote.id || '').trim().toLowerCase()
  if (!raw) return ''
  if (
    raw === 'openmousbot' ||
    raw === 'openmausbot' ||
    raw === 'openmous' ||
    raw === 'openmaus'
  ) {
    return 'omb'
  }
  if (raw === 'openswarm' || raw === 'open_swarm' || raw === 'nested' || raw === 'swarm') {
    return 'open-swarm'
  }
  return raw
}

export function remoteImplGroupLabel(
  id: string,
  impls: Array<Pick<RemoteKind, 'id' | 'label'>> = [],
): string {
  if (id === 'open-swarm' || id === 'nested') return 'nested'
  const fromImpls = impls.find((row) => row.id === id)?.label
  if (fromImpls) return fromImpls
  return remoteKindLabel(id)
}

export function groupRemotesByImpl(
  remotes: Array<Pick<RemoteConnection, 'id' | 'kind'> & { impl?: string }>,
  impls: Array<Pick<RemoteKind, 'id' | 'label'>> = [],
): AddAgentGroup[] {
  const counts = new Map<string, number>()
  for (const id of ADD_AGENT_REMOTE_GROUP_IDS) counts.set(id, 0)
  for (const remote of remotes) {
    const id = remoteImplGroupId(remote)
    if (!id) continue
    counts.set(id, (counts.get(id) || 0) + 1)
  }

  const ids: string[] = [...ADD_AGENT_REMOTE_GROUP_IDS]
  for (const id of counts.keys()) {
    if (!ids.includes(id)) ids.push(id)
  }

  return ids
    .filter((id) => ADD_AGENT_REMOTE_GROUP_IDS.includes(id as (typeof ADD_AGENT_REMOTE_GROUP_IDS)[number]) || (counts.get(id) || 0) > 0)
    .map((id) => ({
      id,
      label: remoteImplGroupLabel(id, impls),
      count: counts.get(id) || 0,
    }))
}

export function filterRemotesByImpl<T extends { kind?: string; id?: string; impl?: string }>(
  remotes: T[],
  implId: string | null,
): T[] {
  if (!implId) return remotes
  const want = implId.toLowerCase() === 'nested' ? 'open-swarm' : implId.toLowerCase()
  return remotes.filter((remote) => remoteImplGroupId(remote) === want)
}

export function toggleGroupFilter(current: string | null, clicked: string): string | null {
  return current === clicked ? null : clicked
}
