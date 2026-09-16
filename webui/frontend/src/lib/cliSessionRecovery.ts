/**
 * REQ-879 / #274 — detect a poisoned CLI/config session so Chat can offer recovery
 * instead of rehydrating a terminal failure as if the service were permanently down.
 */

export const CLI_SESSION_RECOVERY_MESSAGE =
  'This session encountered an agent configuration error.'

const FATAL_CONFIG_NEEDLES = [
  'no cli agents are configured',
  'no cli is configured',
  'no cli backend is configured',
  'unconfigured harness',
  'endpoint not configured',
]

const RESUME_FAILURE_NEEDLES = [
  'no conversation',
  'conversation found',
  'session not found',
  'unknown session',
  'invalid session',
  'expired session',
  'cannot resume',
  'failed to resume',
  'no such session',
  'unable to resume',
  'resume failed',
]

export interface FatalConfigMessageLike {
  role?: string
  text?: string
  content?: string
  fatalConfigError?: boolean
  fatal_config_error?: boolean
  streaming?: boolean
}

export function isFatalConfigErrorText(text: string): boolean {
  const blob = (text || '').toLowerCase()
  if (!blob) return false
  if (FATAL_CONFIG_NEEDLES.some((needle) => blob.includes(needle))) return true
  if (RESUME_FAILURE_NEEDLES.some((needle) => blob.includes(needle))) return true
  return blob.includes('not configured') && (blob.includes('cli') || blob.includes('harness'))
}

export function isFatalConfigErrorMessage(message: FatalConfigMessageLike): boolean {
  if (message.fatalConfigError === true || message.fatal_config_error === true) return true
  return isFatalConfigErrorText(message.text || message.content || '')
}

/** Last user/assistant turn is a terminal CLI/config failure (ignore status chrome). */
export function lastTurnNeedsRecovery(messages: FatalConfigMessageLike[]): boolean {
  const last = [...messages]
    .reverse()
    .find((row) => (row.role === 'user' || row.role === 'assistant') && row.streaming !== true)
  if (!last || last.role !== 'assistant') return false
  return isFatalConfigErrorMessage(last)
}
