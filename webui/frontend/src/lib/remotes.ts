/**
 * Opt-in remotes catalog (REQ-59).
 *
 * Settings and remote dropdowns list only configured remotes. Kind labels
 * use OpenMousBot for the ``omb`` id — never the letters OMB in UI copy.
 */

import type { RemoteConnection, RemoteKind, RemotesListResponse } from './api'

export const ADD_REMOTE_VALUE = '__add_remote__'

export const FALLBACK_REMOTE_KINDS: RemoteKind[] = [
  { id: 'hermes', label: 'Hermes' },
  { id: 'anythingllm', label: 'AnythingLLM' },
  { id: 'letta', label: 'Letta' },
  { id: 'omb', label: 'OpenMousBot' },
  { id: 'rakazo', label: 'Rakazo' },
  { id: 'herdr', label: 'Herdr' },
  { id: 'open-swarm', label: 'open-swarm' },
  { id: 'trueforge', label: 'TrueForge' },
]

const FALLBACK_LABELS: Record<string, string> = Object.fromEntries(
  FALLBACK_REMOTE_KINDS.map((kind) => [kind.id, kind.label]),
)

export function remoteKindLabel(id: string, kinds: RemoteKind[] = FALLBACK_REMOTE_KINDS): string {
  const rid = (id || '').trim().toLowerCase()
  const aliases: Record<string, string> = {
    openmausbot: 'omb',
    openmaus: 'omb',
    openmousbot: 'omb',
    openswarm: 'open-swarm',
    open_swarm: 'open-swarm',
  }
  const resolved = aliases[rid] || rid
  const fromKinds = kinds.find((kind) => kind.id === resolved)?.label
  if (fromKinds) return fromKinds
  return FALLBACK_LABELS[resolved] || resolved
}

export function remoteKinds(response?: RemotesListResponse | null): RemoteKind[] {
  const listed = response?.kinds
  if (Array.isArray(listed) && listed.length > 0) {
    return listed.map((kind) => ({
      id: kind.id,
      label: kind.label || remoteKindLabel(kind.id),
    }))
  }
  return FALLBACK_REMOTE_KINDS
}

/**
 * Only remotes the user (or env) has added. Defaults / unused kinds stay out.
 */
export function configuredRemotes(
  response?: RemotesListResponse | RemoteConnection[] | null,
): RemoteConnection[] {
  if (!response) return []
  if (Array.isArray(response)) {
    return response.filter((remote) => Boolean(remote?.id))
  }
  if (Array.isArray(response.configured)) {
    return response.configured
  }
  return (response.data ?? []).filter((remote) => remote.source && remote.source !== 'default')
}

/** Empty catalog vs remotes-exist-but-unbound. Never "No remotes" while remotes exist. */
export function remoteSelectPlaceholder(configuredCount: number, selectedId = ''): string {
  if (configuredCount === 0) return 'No remotes'
  if (!selectedId) return 'Pick a remote'
  return 'Remote'
}

/** Add-agent Remote tab: impls under kind=remote, never a parallel Herdr kind. */
export function addAgentRemoteImpls(
  response?: RemotesListResponse | null,
): RemoteKind[] {
  const listed = remoteKinds(response)
  const seen = new Set(listed.map((kind) => kind.id))
  const merged = [...listed]
  for (const fallback of FALLBACK_REMOTE_KINDS) {
    if (!seen.has(fallback.id)) {
      merged.push(fallback)
      seen.add(fallback.id)
    }
  }
  return merged.map((kind) => ({
    ...kind,
    kind: 'remote',
    impl: kind.impl || kind.id,
  }))
}

export function unusedRemoteKinds(
  response?: RemotesListResponse | null,
): RemoteKind[] {
  const used = new Set(configuredRemotes(response).map((remote) => remote.id))
  return remoteKinds(response).filter((kind) => kind.id === 'trueforge' || !used.has(kind.id))
}

export function remoteOptionLabel(remote: RemoteConnection, kinds?: RemoteKind[]): string {
  return remote.label || remoteKindLabel(remote.kind || remote.id, kinds)
}

export function isHerdrKind(id: string | undefined): boolean {
  return (id || '').trim().toLowerCase() === 'herdr'
}

export function herdrLocationLabel(remote: Pick<RemoteConnection, 'herdr_mode' | 'transport' | 'ssh_host' | 'ssh_user' | 'ssh_port' | 'base_url'>): string {
  const mode = remote.herdr_mode || remote.transport
  if (mode === 'ssh' && remote.ssh_host && remote.ssh_user) {
    const port = remote.ssh_port && remote.ssh_port !== 22 ? `:${remote.ssh_port}` : ''
    return `SSH ${remote.ssh_user}@${remote.ssh_host}${port}`
  }
  if (mode === 'ssh') return 'Remote Herdr (SSH — host/user missing)'
  return remote.base_url || 'Local Herdr (no SSH)'
}
