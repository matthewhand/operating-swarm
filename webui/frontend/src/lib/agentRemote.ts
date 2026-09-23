/**
 * Per-agent remote binding (id + kind). A remote-kind agent chats through a
 * concrete configured remote — never an empty "No remotes" catalog (Issue #745).
 */

import type { RemoteConnection, RemotesListResponse } from './api'
import { configuredRemotes, remoteKindLabel, remoteKinds } from './remotes'
import { STARTER_REMOTE_ID } from './starter-agents'
import type { RemoteEntry } from './remotesCatalog'

export const AGENT_REMOTE_BINDINGS_KEY = 'swarm_agent_remote_bindings'
export const AGENT_REMOTE_BINDINGS_CHANGED_EVENT = 'swarm:agent-remote-bindings-changed'

export interface AgentRemoteBinding {
  id: string
  kind: string
}

type BindingMap = Record<string, AgentRemoteBinding>

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readMap(): BindingMap {
  try {
    const raw = localStorage.getItem(AGENT_REMOTE_BINDINGS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    const rec = asRecord(parsed)
    if (!rec) return {}
    const map: BindingMap = {}
    for (const [agentId, value] of Object.entries(rec)) {
      const binding = parseBinding(value)
      if (binding) map[agentId] = binding
    }
    return map
  } catch {
    return {}
  }
}

function writeMap(map: BindingMap): void {
  try {
    localStorage.setItem(AGENT_REMOTE_BINDINGS_KEY, JSON.stringify(map))
  } catch {
    /* persistence is best-effort */
  }
}

function emitChange(agentId: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent(AGENT_REMOTE_BINDINGS_CHANGED_EVENT, { detail: { agentId } }),
    )
  } catch {
    /* jsdom / detached window */
  }
}

export function parseBinding(value: unknown): AgentRemoteBinding | null {
  const rec = asRecord(value)
  if (!rec) return null
  const id = typeof rec.id === 'string' ? rec.id.trim() : ''
  if (!id) return null
  const kind = typeof rec.kind === 'string' && rec.kind.trim() ? rec.kind.trim() : id
  return { id, kind }
}

export function loadAgentRemoteBinding(agentId: string): AgentRemoteBinding | null {
  if (!agentId) return null
  return readMap()[agentId] ?? null
}

export function saveAgentRemoteBinding(
  agentId: string,
  binding: AgentRemoteBinding | null,
): AgentRemoteBinding | null {
  if (!agentId) return null
  const map = readMap()
  if (!binding?.id) {
    delete map[agentId]
    writeMap(map)
    emitChange(agentId)
    return null
  }
  const next: AgentRemoteBinding = {
    id: binding.id.trim(),
    kind: (binding.kind || binding.id).trim(),
  }
  map[agentId] = next
  writeMap(map)
  emitChange(agentId)
  return next
}

function asConnection(
  remote: Pick<RemoteConnection, 'id'> &
    Partial<RemoteConnection> & { title?: string; kind?: string },
): RemoteConnection {
  const id = remote.id
  const kind = remote.kind || id
  const title = remote.title || remote.label || remoteKindLabel(kind)
  return {
    id,
    kind,
    label: remote.label || title,
    title,
    host_label: remote.host_label || '',
    base_url: remote.base_url || '',
    source: remote.source || 'config',
  }
}

/**
 * Normalize Settings list + rail entries + an optional bound remote into the
 * shape RemoteSelect expects. Bound remotes stay visible even when the
 * configured catalog is empty or stale.
 */
export function remotesListForSelect(
  list?: RemotesListResponse | RemoteConnection[] | null,
  rail?: RemoteEntry[] | null,
  bound?: AgentRemoteBinding | { id: string; kind?: string; title?: string } | null,
): RemotesListResponse {
  const fromList = configuredRemotes(list)
  const seen = new Set(fromList.map((remote) => remote.id))
  const merged = [...fromList]

  for (const entry of rail ?? []) {
    if (!entry?.id || seen.has(entry.id)) continue
    if (!entry.configured && bound?.id !== entry.id) continue
    seen.add(entry.id)
    merged.push(
      asConnection({
        id: entry.id,
        kind: entry.kind,
        title: entry.title,
        label: entry.title,
      }),
    )
  }

  if (bound?.id && !seen.has(bound.id)) {
    merged.unshift(
      asConnection({
        id: bound.id,
        kind: bound.kind || bound.id,
        title: 'title' in bound ? bound.title : undefined,
      }),
    )
  }

  const kinds = remoteKinds(Array.isArray(list) ? undefined : list)
  return {
    object: 'list',
    kinds,
    configured: merged,
    data: merged,
  }
}

/**
 * REQ-904 / #502 — whose provider is being configured?
 *
 * The binding subject is the **agent** and only the agent. A remote id in the
 * URL is an identity (a seat being viewed) and can never be a binding
 * subject: there is no key in this space meaning "the remote bound to
 * itself". The old wiring (`remoteFromUrl || selectedBlueprint`) made
 * `?remote=omb` write a self-binding under `omb`, so a binding written while
 * viewing a remote seat was invisible to the same agent opened by name.
 */
export function resolveAgentBindingSubject(options: {
  remoteFromUrl?: string | null
  selectedBlueprint?: string | null
}): string {
  if ((options.remoteFromUrl || '').trim()) return ''
  return (options.selectedBlueprint || '').trim()
}

/**
 * Resolve the remote id the navbar should show.
 *
 * #502 precedence: a persisted agent binding wins over the URL remote —
 * *viewing is not configuring*. `?remote=X` in the URL sets the view of a
 * remote seat, but must never override the binding of an agent opened by
 * name. Stale ids (persisted or agent `remote_id`) still fall through to an
 * empty repair state.
 */
export function resolveBoundRemoteId(options: {
  remoteFromUrl?: string
  persisted?: AgentRemoteBinding | null
  agentRemoteId?: string
  configuredIds: Iterable<string>
}): string {
  const configured = new Set(
    [...options.configuredIds].map((id) => id.trim()).filter(Boolean),
  )
  const agent = (options.agentRemoteId || '').trim()
  if (agent && configured.has(agent)) return agent
  const persisted = (options.persisted?.id || '').trim()
  if (persisted && configured.has(persisted)) return persisted
  // Identity view only: no agent binding exists, so the URL decides what the
  // user is looking at.
  const url = (options.remoteFromUrl || '').trim()
  if (url && configured.has(url)) return url
  return ''
}

export function isRemoteKindAgent(options: {
  remoteFromUrl?: string
  agentKind?: string
  blueprintId?: string
  selectedKind?: string
  agentType?: string
  remote?: string
  tags?: string[]
}): boolean {
  if (options.remoteFromUrl) return true
  if (options.agentKind === 'remote' || options.selectedKind === 'remote') return true
  if (options.agentType === 'remote') return true
  if (options.remote) return true
  if (options.blueprintId === STARTER_REMOTE_ID) return true
  const id = (options.blueprintId || '').toLowerCase()
  if (id.startsWith('remote:') || id.startsWith('placeholder:remote:') || id.startsWith('remote-')) {
    return true
  }
  return Boolean(options.tags?.includes('remote'))
}
