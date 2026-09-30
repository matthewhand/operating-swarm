/**
 * Per-agent memory client (#1391).
 *
 * Consumes GET/POST /v1/agents/<id>/memories/ and DELETE
 * /v1/agents/<id>/memories/<memory_id>/ from #1390. Pack-tier
 * conventions (profile, log) travel in a template; episode and note
 * stay local.
 */
import { apiDelete, apiGet, apiPost } from './api'
import { agentIdFromBlueprint } from './agentChat'

export const MEMORY_KIND_PROFILE = 'profile'
export const MEMORY_KIND_LOG = 'log'
export const MEMORY_KIND_EPISODE = 'episode'
export const MEMORY_KIND_NOTE = 'note'

export const MEMORY_TIER_PACK = 'pack'
export const MEMORY_TIER_LOCAL = 'local'

export type AgentMemoryKind = 'profile' | 'log' | 'episode' | 'note'
export type AgentMemoryTier = 'pack' | 'local'
export type MemoryListFilter = 'all' | AgentMemoryTier | AgentMemoryKind

export const PACK_KINDS = new Set<AgentMemoryKind>([MEMORY_KIND_PROFILE, MEMORY_KIND_LOG])
export const LOCAL_KINDS = new Set<AgentMemoryKind>([MEMORY_KIND_EPISODE, MEMORY_KIND_NOTE])
export const CONVENTION_KINDS = [MEMORY_KIND_PROFILE, MEMORY_KIND_LOG] as const
export const ALL_MEMORY_KINDS = [
  MEMORY_KIND_PROFILE,
  MEMORY_KIND_LOG,
  MEMORY_KIND_EPISODE,
  MEMORY_KIND_NOTE,
] as const

export const KIND_LABELS: Record<AgentMemoryKind, string> = {
  profile: 'Profile',
  log: 'Log',
  episode: 'Episode',
  note: 'Note',
}

export const TIER_LABELS: Record<AgentMemoryTier, string> = {
  pack: 'Pack',
  local: 'Local',
}

export interface AgentMemory {
  object?: 'agent_memory'
  id: string
  agent_id: string
  kind: AgentMemoryKind
  tier: AgentMemoryTier
  title: string
  body: string
  created_at: string
}

export interface AgentMemoryList {
  object: 'agent_memory_list'
  agent_id: string
  memories: AgentMemory[]
}

export interface AgentMemoryPackFragment {
  object: 'agent_memory_pack'
  schema?: number
  memories: Array<{ kind: string; title: string; body: string }>
}

export interface AgentMemoryWrite {
  kind: AgentMemoryKind
  title?: string
  body?: string
}

export type MemoryExportSkipReason = 'episode_skipped' | 'note_skipped'

export interface MemoryExportExclusion {
  memory: AgentMemory
  reason: MemoryExportSkipReason
}

export interface MemoryExportPreview {
  included: AgentMemory[]
  excluded: MemoryExportExclusion[]
  includedCount: number
  excludedCount: number
}

export const SKIP_REASON_LABELS: Record<MemoryExportSkipReason, string> = {
  episode_skipped: 'Episode skipped — stays local, not packed into a template.',
  note_skipped: 'Note skipped — stays local, not packed into a template.',
}

const KIND_ALIASES: Record<string, AgentMemoryKind> = {
  profile: MEMORY_KIND_PROFILE,
  persona: MEMORY_KIND_PROFILE,
  identity: MEMORY_KIND_PROFILE,
  log: MEMORY_KIND_LOG,
  journal: MEMORY_KIND_LOG,
  episode: MEMORY_KIND_EPISODE,
  episodic: MEMORY_KIND_EPISODE,
  note: MEMORY_KIND_NOTE,
  scratch: MEMORY_KIND_NOTE,
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function memoriesPath(agentId: string): string {
  const agent = agentIdFromBlueprint(agentId)
  return `/v1/agents/${encodeURIComponent(agent)}/memories/`
}

export function memoryPath(agentId: string, memoryId: string): string {
  return `${memoriesPath(agentId)}${encodeURIComponent(memoryId)}/`
}

export function memoryPackPath(agentId: string): string {
  return `${memoriesPath(agentId)}pack/`
}

export function normalizeMemoryKind(value: unknown): AgentMemoryKind | null {
  const text = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')
  return KIND_ALIASES[text] ?? null
}

export function kindTier(kind: AgentMemoryKind): AgentMemoryTier {
  return PACK_KINDS.has(kind) ? MEMORY_TIER_PACK : MEMORY_TIER_LOCAL
}

export function isConventionKind(kind: string): boolean {
  return PACK_KINDS.has(kind as AgentMemoryKind)
}

export function parseAgentMemory(raw: unknown, fallbackAgentId = ''): AgentMemory | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const kind = normalizeMemoryKind(rec.kind)
  if (!kind) return null
  const id = String(rec.id || '').trim()
  const title = String(rec.title || '').trim()
  const body = String(rec.body ?? rec.content ?? rec.text ?? '')
  if (!id || (!title && !body.trim())) return null
  const agent = String(rec.agent_id || fallbackAgentId).trim()
  const created = String(rec.created_at || '').trim()
  // Kind is the source of truth. A declared tier that disagrees would
  // otherwise land the same row in both the pack and local sections.
  const tier = kindTier(kind)
  return {
    object: 'agent_memory',
    id,
    agent_id: agent,
    kind,
    tier,
    title,
    body,
    created_at: created,
  }
}

export function parseMemories(raw: unknown, fallbackAgentId = ''): AgentMemory[] {
  const rec = asRecord(raw)
  const items = Array.isArray(raw)
    ? raw
    : Array.isArray(rec?.memories)
      ? rec.memories
      : Array.isArray(rec?.data)
        ? rec.data
        : []
  const rows: AgentMemory[] = []
  for (const item of items) {
    const parsed = parseAgentMemory(item, fallbackAgentId)
    if (parsed) rows.push(parsed)
  }
  return rows
}

export function filterMemories(
  memories: readonly AgentMemory[],
  filter: MemoryListFilter = 'all',
): AgentMemory[] {
  if (filter === 'all') return [...memories]
  if (filter === MEMORY_TIER_PACK || filter === MEMORY_TIER_LOCAL) {
    return memories.filter((row) => kindTier(row.kind) === filter)
  }
  return memories.filter((row) => row.kind === filter)
}

export function groupMemoriesByTier(memories: readonly AgentMemory[]): {
  pack: AgentMemory[]
  local: AgentMemory[]
} {
  return {
    pack: filterMemories(memories, MEMORY_TIER_PACK),
    local: filterMemories(memories, MEMORY_TIER_LOCAL),
  }
}

export function skipReasonFor(kind: string): MemoryExportSkipReason | null {
  if (kind === MEMORY_KIND_EPISODE) return 'episode_skipped'
  if (kind === MEMORY_KIND_NOTE) return 'note_skipped'
  return null
}

/** Included vs excluded rows for a template pack preview. */
export function previewMemoryExport(memories: readonly AgentMemory[]): MemoryExportPreview {
  const included: AgentMemory[] = []
  const excluded: MemoryExportExclusion[] = []
  for (const memory of memories) {
    const reason = skipReasonFor(memory.kind)
    if (reason) {
      excluded.push({ memory, reason })
      continue
    }
    if (PACK_KINDS.has(memory.kind)) {
      included.push(memory)
    }
  }
  return {
    included,
    excluded,
    includedCount: included.length,
    excludedCount: excluded.length,
  }
}

export async function fetchAgentMemories(
  agentId: string,
  opts?: { kind?: string; tier?: string },
): Promise<AgentMemory[]> {
  const params = new URLSearchParams()
  if (opts?.kind) params.set('kind', opts.kind)
  if (opts?.tier) params.set('tier', opts.tier)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const data = await apiGet<AgentMemoryList>(`${memoriesPath(agentId)}${suffix}`)
  return parseMemories(data, agentIdFromBlueprint(agentId))
}

export async function createAgentMemory(
  agentId: string,
  body: AgentMemoryWrite,
): Promise<AgentMemory> {
  const created = await apiPost<AgentMemory>(memoriesPath(agentId), {
    kind: body.kind,
    title: body.title ?? '',
    body: body.body ?? '',
  })
  const parsed = parseAgentMemory(created, agentIdFromBlueprint(agentId))
  if (!parsed) {
    throw new Error('Memory response was not a convention row.')
  }
  return parsed
}

export async function deleteAgentMemory(agentId: string, memoryId: string): Promise<void> {
  await apiDelete(memoryPath(agentId, memoryId))
}

export async function fetchMemoryPack(agentId: string): Promise<AgentMemoryPackFragment> {
  return apiGet<AgentMemoryPackFragment>(memoryPackPath(agentId))
}
