/**
 * #1373: parse Support NL-create routine cards.
 * Persist uses the existing routines API (`createRoutine`).
 */

export const SUPPORT_ROUTINE_FENCE = 'swarm-nl-routine'
export const SUPPORT_INTERACTIVE_FIXTURE = 'SUPPORT_INTERACTIVE_CREATE_1373'
export const ADD_ROUTINE_LABEL = 'Add routine'

const FENCE_RE = /```swarm-nl-routine\s*\n([\s\S]*?)```/i

export interface SupportNlRoutineTrigger {
  kind: string
  seconds?: number
  expression?: string
  owner_repo?: string
  event?: string
  actor?: string
  run_at?: string
  sender?: string
  pattern?: string
  event_type?: string
}

export interface SupportNlRoutineCard {
  id: string
  kind: 'routine'
  title: string
  agentId: string
  instruction: string
  trigger: SupportNlRoutineTrigger
  triggerLabel: string
  persisted: boolean
  usable: boolean
  chatHref: string
  source?: string
  fixture?: string
}

export function parseSupportNlRoutineFence(text: string): {
  prose: string
  card: SupportNlRoutineCard | null
} {
  const source = String(text ?? '')
  const match = source.match(FENCE_RE)
  if (!match) {
    return { prose: source, card: null }
  }
  const card = parseSupportNlRoutineJson(match[1] || '')
  const prose = `${source.slice(0, match.index)}${source.slice((match.index || 0) + match[0].length)}`
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return { prose, card }
}

export function parseSupportNlRoutineJson(raw: string): SupportNlRoutineCard | null {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    const title = String(data.title || '').trim()
    const agentId = String(data.agentId || data.agent_id || '').trim()
    if (!title || !agentId) return null
    const trigger =
      data.trigger && typeof data.trigger === 'object'
        ? (data.trigger as SupportNlRoutineTrigger)
        : { kind: 'cron', expression: '0 9 * * *' }
    const persisted = data.persisted === true
    return {
      id: String(data.id || '').trim(),
      kind: 'routine',
      title,
      agentId,
      instruction: String(data.instruction || title),
      trigger,
      triggerLabel: String(data.triggerLabel || data.trigger_label || trigger.kind || 'Scheduled'),
      persisted,
      usable: persisted || data.usable === true,
      chatHref: String(data.chatHref || `/chat?blueprint=${encodeURIComponent(agentId)}`),
      source: data.source ? String(data.source) : undefined,
      fixture: data.fixture ? String(data.fixture) : undefined,
    }
  } catch {
    return null
  }
}
