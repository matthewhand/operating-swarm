/**
 * #532 — role wire-up persistence: which agents *consume* a role provider.
 *
 * A role (suggestions, skeptic, gate, advisor, ...) is a badge on the
 * provider agent, but it only does work once other agents are wired to use
 * it. That edge — consumer → provider for a given role — is stored here,
 * keyed by provider agent id: `swarm_role_consumers[providerId] = consumers`.
 *
 * The store is self-healing: unknown ids drop out on read, and an empty
 * consumer list deletes the key so `providersWithConsumers` stays honest.
 */

export const ROLE_CONSUMERS_KEY = 'swarm_role_consumers'
export const ROLE_CONSUMERS_CHANGED_EVENT = 'swarm:role-consumers-changed'

/** A provider may host several roles; an edge is one consumer using one role of one provider. */
export interface RoleConsumerEdge {
  providerId: string
  role: string
  consumerId: string
}

function readMap(): Record<string, Record<string, string[]>> {
  try {
    const raw = window.localStorage.getItem(ROLE_CONSUMERS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (parsed == null || typeof parsed !== 'object') return {}
    const out: Record<string, Record<string, string[]>> = {}
    for (const [provider, roles] of Object.entries(parsed as Record<string, unknown>)) {
      if (roles == null || typeof roles !== 'object') continue
      const roleMap: Record<string, string[]> = {}
      for (const [role, consumers] of Object.entries(roles as Record<string, unknown>)) {
        if (!Array.isArray(consumers)) continue
        const ids = consumers
          .map((id) => (typeof id === 'string' ? id.trim() : ''))
          .filter((id) => id.length > 0 && id !== provider)
        if (ids.length > 0) roleMap[role] = Array.from(new Set(ids))
      }
      if (Object.keys(roleMap).length > 0) out[provider] = roleMap
    }
    return out
  } catch {
    return {}
  }
}

function writeMap(map: Record<string, Record<string, string[]>>): void {
  try {
    if (Object.keys(map).length === 0) {
      window.localStorage.removeItem(ROLE_CONSUMERS_KEY)
    } else {
      window.localStorage.setItem(ROLE_CONSUMERS_KEY, JSON.stringify(map))
    }
  } catch {
    /* storage unavailable — wire-up stays session-only */
  }
  window.dispatchEvent(new CustomEvent(ROLE_CONSUMERS_CHANGED_EVENT))
}

/** All consumer ids wired to `providerId` for `role`, ordered, deduped, self-free. */
export function loadRoleConsumers(providerId: string, role: string): string[] {
  const key = String(providerId || '').trim()
  const roleKey = String(role || '').trim()
  if (!key || !roleKey) return []
  return readMap()[key]?.[roleKey] ?? []
}

/** Every edge in the store — the provider side renders these as pills. */
export function loadAllRoleConsumerEdges(): RoleConsumerEdge[] {
  const map = readMap()
  const edges: RoleConsumerEdge[] = []
  for (const [providerId, roles] of Object.entries(map)) {
    for (const [role, consumers] of Object.entries(roles)) {
      for (const consumerId of consumers) edges.push({ providerId, role, consumerId })
    }
  }
  return edges
}

/** Edges where `agentId` is the role provider — its chat shows these as pills. */
export function loadProviderEdges(agentId: string): RoleConsumerEdge[] {
  return loadAllRoleConsumerEdges().filter((edge) => edge.providerId === agentId)
}

/** Edges where `agentId` consumes a role — the editor shows these as wiring. */
export function loadConsumerEdges(agentId: string): RoleConsumerEdge[] {
  return loadAllRoleConsumerEdges().filter((edge) => edge.consumerId === agentId)
}

/** Agent ids across the catalog that have any consumer wired to them. */
export function providersWithConsumers(): string[] {
  return Object.keys(readMap())
}

/** Replace the consumer list for one (provider, role) edge. Empty list unwires. */
export function saveRoleConsumers(providerId: string, role: string, consumers: readonly string[]): string[] {
  const key = String(providerId || '').trim()
  const roleKey = String(role || '').trim()
  const map = readMap()
  if (!key || !roleKey) return []
  const ids = Array.from(
    new Set(
      consumers
        .map((id) => String(id ?? '').trim())
        .filter((id) => id.length > 0 && id !== key),
    ),
  )
  if (ids.length === 0) {
    const roles = { ...(map[key] ?? {}) }
    delete roles[roleKey]
    if (Object.keys(roles).length === 0) delete map[key]
    else map[key] = roles
  } else {
    map[key] = { ...(map[key] ?? {}), [roleKey]: ids }
  }
  writeMap(map)
  return loadRoleConsumers(key, roleKey)
}

/** Toggle one consumer on a (provider, role) edge. Returns the new list. */
export function toggleRoleConsumer(providerId: string, role: string, consumerId: string): string[] {
  const current = loadRoleConsumers(providerId, role)
  const wanted = String(consumerId || '').trim()
  if (!wanted || wanted === String(providerId || '').trim()) return current
  const next = current.includes(wanted)
    ? current.filter((id) => id !== wanted)
    : [...current, wanted]
  return saveRoleConsumers(providerId, role, next)
}
