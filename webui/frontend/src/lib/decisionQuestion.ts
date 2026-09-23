/**
 * Parse an agent-emitted ```question fence into a user-answerable card.
 * Distinct from one-way System pills (config intel; not replyable).
 */

export interface DecisionQuestion {
  id: string
  ask: string
  choices: string[]
  other: string
}

const FENCE_RE = /```question\s*\n([\s\S]*?)```/i

export function questionFromPayload(raw: {
  id?: unknown
  ask?: unknown
  choices?: unknown
  other?: unknown
}): DecisionQuestion | null {
  const ask = String(raw.ask || '').trim()
  if (!ask || !Array.isArray(raw.choices)) return null
  const choices = raw.choices
    .map((item) => String(item || '').trim())
    .filter((item) => item.length > 0)
  if (!choices.length) return null
  return {
    id: String(raw.id || 'q').trim() || 'q',
    ask,
    choices,
    other: String(raw.other || 'Other').trim() || 'Other',
  }
}

export function parseDecisionQuestion(text: string): DecisionQuestion | null {
  if (!text) return null
  const match = text.match(FENCE_RE)
  if (!match) return null
  try {
    const raw = JSON.parse(match[1]) as {
      id?: unknown
      ask?: unknown
      choices?: unknown
      other?: unknown
    }
    return questionFromPayload(raw)
  } catch {
    return null
  }
}

export function stripDecisionQuestion(text: string): string {
  if (!text) return ''
  return text.replace(FENCE_RE, '').trim()
}
