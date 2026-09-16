/** #215: per-seat context-window usage (estimate until a real tokenizer). */

import { apiGet } from './api'

export const CONTEXT_USAGE_TYPE = 'context_usage'
export const CONTEXT_USAGE_EVENT = 'swarm:context-usage'
export const USAGE_SPARK_LIMIT = 24

export interface ContextUsageBreakdown {
  messages: number
  summaries: number
  system: number
  tools: number
}

export interface ContextUsage {
  type: typeof CONTEXT_USAGE_TYPE
  conversation_id: string
  agent_id: string
  tokens: number
  window: number | null
  pct: number | null
  estimate: boolean
  breakdown: ContextUsageBreakdown
}

const EMPTY_BREAKDOWN: ContextUsageBreakdown = {
  messages: 0,
  summaries: 0,
  system: 0,
  tools: 0,
}

function asNonNegInt(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 0
}

function asWindow(value: unknown): number | null {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null
}

export function parseContextUsage(value: unknown): ContextUsage | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  if (String(row.type) !== CONTEXT_USAGE_TYPE) return null
  if (row.tokens == null) return null
  const tokens = asNonNegInt(row.tokens)
  const breakdownRaw =
    row.breakdown && typeof row.breakdown === 'object'
      ? (row.breakdown as Record<string, unknown>)
      : {}
  const breakdown: ContextUsageBreakdown = {
    messages: asNonNegInt(breakdownRaw.messages),
    summaries: asNonNegInt(breakdownRaw.summaries),
    system: asNonNegInt(breakdownRaw.system),
    tools: asNonNegInt(breakdownRaw.tools),
  }
  return {
    type: CONTEXT_USAGE_TYPE,
    conversation_id: String(row.conversation_id || ''),
    agent_id: String(row.agent_id || ''),
    tokens,
    window: asWindow(row.window),
    pct: row.pct == null ? null : asNonNegInt(row.pct),
    estimate: row.estimate !== false,
    breakdown: { ...EMPTY_BREAKDOWN, ...breakdown },
  }
}

/** Compact badge copy: "~12.3k tokens, window unknown" / "~12.3k / 128k". */
export function formatUsageTokens(n: number): string {
  const abs = Math.max(0, n)
  if (abs < 1000) return String(Math.round(abs))
  const k = abs / 1000
  if (abs < 100_000) {
    const fixed = k.toFixed(1)
    return `${fixed.endsWith('.0') ? String(Math.round(k)) : fixed}k`
  }
  return `${Math.round(k)}k`
}

export function formatContextUsageLabel(usage: Pick<ContextUsage, 'tokens' | 'window'>): string {
  const used = `~${formatUsageTokens(usage.tokens)}`
  if (usage.window != null && usage.window > 0) {
    return `${used} / ${formatUsageTokens(usage.window)}`
  }
  return `${used} tokens, window unknown`
}

function sparkKey(conversationId: string): string {
  return `swarm_context_usage_spark:${conversationId}`
}

export function readUsageSpark(conversationId: string): number[] {
  const cid = conversationId.trim()
  if (!cid) return []
  try {
    const raw = window.sessionStorage.getItem(sparkKey(cid))
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((n) => (typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.round(n)) : null))
      .filter((n): n is number => n != null)
      .slice(-USAGE_SPARK_LIMIT)
  } catch {
    return []
  }
}

export function recordUsageSpark(conversationId: string, tokens: number): number[] {
  const cid = conversationId.trim()
  if (!cid) return []
  const next = [...readUsageSpark(cid), Math.max(0, Math.round(tokens))].slice(-USAGE_SPARK_LIMIT)
  try {
    window.sessionStorage.setItem(sparkKey(cid), JSON.stringify(next))
  } catch {
    /* private mode / quota */
  }
  return next
}

export function publishContextUsage(usage: ContextUsage): void {
  recordUsageSpark(usage.conversation_id, usage.tokens)
  try {
    window.dispatchEvent(new CustomEvent(CONTEXT_USAGE_EVENT, { detail: usage }))
  } catch {
    /* jsdom / SSR */
  }
}

export async function fetchContextUsage(opts: {
  agentId: string
  conversationId: string
  modelId?: string | null
}): Promise<ContextUsage> {
  const agent = opts.agentId.trim() || '_default'
  const conversationId = opts.conversationId.trim()
  const params = new URLSearchParams({
    agent,
    conversation_id: conversationId,
  })
  const model = (opts.modelId || '').trim()
  if (model) params.set('model', model)
  const data = await apiGet<unknown>(`/chat/context-usage/?${params.toString()}`)
  const parsed = parseContextUsage(data)
  if (!parsed) {
    throw new Error('Context usage returned no payload')
  }
  return parsed
}
