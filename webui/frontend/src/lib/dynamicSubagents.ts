/**
 * Dynamic Subagents Registration & Events
 *
 * Handles runtime dynamic subagents spawned during task execution or fan-out.
 * Persists registered subagents and dispatches DYNAMIC_SUBAGENT_SPAWNED_EVENT
 * so AgentSidebar, ChatPage, and other components reactively display them as
 * first-class citizens.
 */

export const DYNAMIC_SUBAGENTS_STORAGE_KEY = 'swarm_dynamic_subagents'
export const DYNAMIC_SUBAGENT_SPAWNED_EVENT = 'swarm:dynamic-subagent-spawned'

export interface DynamicSubagent {
  id: string
  name: string
  parentAgentId?: string
  role?: string
  status?: 'running' | 'completed' | 'failed' | 'idle' | string
  task?: string
  summary?: string
  avatar_path?: string
  timestamp?: number
  [key: string]: unknown
}

export interface DynamicSubagentSpawnedDetail {
  subagent?: DynamicSubagent
  subagents?: DynamicSubagent[]
  id?: string
  name?: string
  parentAgentId?: string
  role?: string
  status?: string
}

export function parseDynamicSubagents(raw: string | null): DynamicSubagent[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is DynamicSubagent =>
        Boolean(
          item &&
            typeof item === 'object' &&
            typeof item.id === 'string' &&
            item.id.length > 0,
        ),
    )
  } catch {
    return []
  }
}

export function loadDynamicSubagents(): DynamicSubagent[] {
  try {
    return parseDynamicSubagents(localStorage.getItem(DYNAMIC_SUBAGENTS_STORAGE_KEY))
  } catch {
    return []
  }
}

export function saveDynamicSubagents(subagents: DynamicSubagent[]): DynamicSubagent[] {
  try {
    localStorage.setItem(DYNAMIC_SUBAGENTS_STORAGE_KEY, JSON.stringify(subagents))
  } catch {
    /* storage quota / unavailable */
  }
  return subagents
}

export function registerDynamicSubagent(agent: DynamicSubagent): DynamicSubagent[] {
  if (!agent || !agent.id) return loadDynamicSubagents()
  const current = loadDynamicSubagents()
  const existingIndex = current.findIndex((item) => item.id === agent.id)
  let updated: DynamicSubagent[]
  if (existingIndex >= 0) {
    const merged = { ...current[existingIndex], ...agent }
    updated = [...current]
    updated[existingIndex] = merged
  } else {
    const newEntry: DynamicSubagent = {
      timestamp: Date.now(),
      status: 'running',
      ...agent,
    }
    updated = [...current, newEntry]
  }
  saveDynamicSubagents(updated)

  try {
    const saved = updated.find((item) => item.id === agent.id) || agent
    window.dispatchEvent(
      new CustomEvent<DynamicSubagentSpawnedDetail>(DYNAMIC_SUBAGENT_SPAWNED_EVENT, {
        detail: {
          subagent: saved,
          subagents: updated,
          id: saved.id,
          name: saved.name,
          parentAgentId: saved.parentAgentId,
          role: saved.role,
          status: saved.status,
        },
      }),
    )
  } catch {
    /* non-browser environment */
  }

  return updated
}

export function updateDynamicSubagentStatus(
  id: string,
  status: string,
  summary?: string,
): DynamicSubagent[] {
  if (!id) return loadDynamicSubagents()
  const current = loadDynamicSubagents()
  const target = current.find((item) => item.id === id)
  if (!target) return current
  return registerDynamicSubagent({
    ...target,
    status,
    ...(summary ? { summary } : {}),
  })
}

export function removeDynamicSubagent(id: string): DynamicSubagent[] {
  const current = loadDynamicSubagents()
  const filtered = current.filter((item) => item.id !== id)
  saveDynamicSubagents(filtered)
  try {
    window.dispatchEvent(
      new CustomEvent<DynamicSubagentSpawnedDetail>(DYNAMIC_SUBAGENT_SPAWNED_EVENT, {
        detail: {
          subagents: filtered,
          id,
        },
      }),
    )
  } catch {
    /* non-browser */
  }
  return filtered
}

export function clearDynamicSubagents(): void {
  try {
    localStorage.removeItem(DYNAMIC_SUBAGENTS_STORAGE_KEY)
  } catch {
    /* ignore */
  }
  try {
    window.dispatchEvent(
      new CustomEvent<DynamicSubagentSpawnedDetail>(DYNAMIC_SUBAGENT_SPAWNED_EVENT, {
        detail: { subagents: [] },
      }),
    )
  } catch {
    /* ignore */
  }
}

export function getDynamicSubagent(id: string): DynamicSubagent | undefined {
  return loadDynamicSubagents().find((item) => item.id === id)
}
