/**
 * REQ-69: ordered per-agent inference seats (LLM / CLI / remote).
 *
 * Empty list means Settings default. Scale-out round-robins; sequential
 * failover is a server concern (config errors only, not 429).
 */

export type InferenceKind = 'llm' | 'cli' | 'remote'

export interface InferenceSeat {
  id: string
  kind: InferenceKind
  label?: string
}

const RR_PREFIX = 'swarm_inference_rr:'

export function seatKey(seat: InferenceSeat): string {
  return `${seat.kind}:${seat.id}`
}

export function parseSeatKey(raw: string): InferenceSeat | null {
  const text = String(raw || '').trim()
  if (!text) return null
  const match = /^(llm|cli|remote):(.+)$/i.exec(text)
  if (match) {
    const kind = match[1].toLowerCase() as InferenceKind
    const id = match[2].trim()
    if (!id) return null
    return { id, kind, label: id }
  }
  return { id: text, kind: 'llm', label: text }
}

export function normalizeInferenceList(raw: unknown): InferenceSeat[] {
  if (!Array.isArray(raw)) return []
  const out: InferenceSeat[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    let seat: InferenceSeat | null = null
    if (typeof item === 'string') seat = parseSeatKey(item)
    else if (item && typeof item === 'object') {
      const rec = item as Record<string, unknown>
      const id = typeof rec.id === 'string' ? rec.id.trim() : ''
      const kind = rec.kind
      if (!id) continue
      if (kind === 'llm' || kind === 'cli' || kind === 'remote') {
        seat = { id, kind, label: typeof rec.label === 'string' ? rec.label : id }
      } else {
        seat = parseSeatKey(id)
      }
    }
    if (!seat) continue
    const key = seatKey(seat)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(seat)
  }
  return out
}

/** Serializes anything the normalizer accepts (seats or raw string keys). */
export function serializeInferenceList(seats: InferenceSeat[] | string[]): string[] {
  return normalizeInferenceList(seats).map(seatKey)
}

/** Round-robin index for scale-out (new chat per task). Session-scoped. */
export function nextInferenceIndex(agentId: string, n: number): number {
  if (n <= 0 || !agentId) return 0
  let i = 0
  try {
    i = Number(sessionStorage.getItem(RR_PREFIX + agentId)) || 0
    sessionStorage.setItem(RR_PREFIX + agentId, String(i + 1))
  } catch {
    /* jsdom / private mode */
  }
  return ((i % n) + n) % n
}

export function pickScaleOut(seats: InferenceSeat[], index: number): InferenceSeat | null {
  const list = normalizeInferenceList(seats)
  if (!list.length) return null
  const i = ((index % list.length) + list.length) % list.length
  return list[i]
}
