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

/** #499: Settings section that can actually resolve a needle class. */
const FATAL_CONFIG_TARGETS: Record<string, { section: 'cli-agents' | 'remotes' }> = {
  'no cli agents are configured': { section: 'cli-agents' },
  'no cli is configured': { section: 'cli-agents' },
  'no cli backend is configured': { section: 'cli-agents' },
  'unconfigured harness': { section: 'remotes' },
  'endpoint not configured': { section: 'remotes' },
}

/** #499: where the configuration lives, when the failure names one. */
export interface ConfigTarget {
  section: 'cli-agents' | 'remotes'
}

/** Maps terminal copy to the Settings section that resolves it (#499). */
export function configTargetFromText(text: string): ConfigTarget | undefined {
  const blob = (text || '').toLowerCase()
  if (!blob) return undefined
  for (const [needle, target] of Object.entries(FATAL_CONFIG_TARGETS)) {
    if (blob.includes(needle)) return target
  }
  return undefined
}

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
  /** #499: server-stamped Settings target riding on the persisted flag. */
  configTarget?: ConfigTarget
  config_target?: ConfigTarget
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

/**
 * #499: the Settings target for the banner's primary action, from the same
 * last assistant turn the recovery check reads. Prefers the server-stamped
 * target (new records) and falls back to classifying the text (legacy rows).
 * Undefined for resume failures and unknown copy — the banner stays unchanged.
 */
export function lastRecoveryTarget(
  messages: FatalConfigMessageLike[],
): ConfigTarget | undefined {
  const last = [...messages]
    .reverse()
    .find((row) => (row.role === 'user' || row.role === 'assistant') && row.streaming !== true)
  if (!last || last.role !== 'assistant') return undefined
  if (!isFatalConfigErrorMessage(last)) return undefined
  const stamped = last.configTarget ?? last.config_target
  if (stamped && stamped.section) return stamped
  return configTargetFromText(last.text || last.content || '')
}
