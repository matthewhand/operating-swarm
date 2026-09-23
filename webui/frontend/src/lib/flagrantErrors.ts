/**
 * #746 — flagrant runtime/transport error detection.
 *
 * When a turn dies (remote FAIL, CLI crash, unreachable transport, fatal
 * config error) the failure text must be recognisable so the renderer can
 * present it out-of-band — an error element anchored outside the message
 * flow — instead of appending it to the conversation as if it were chat
 * content that later turns should treat as context.
 */

/** Remote operate failures: `{remote} {op}: FAIL — {detail}`. */
const REMOTE_FAIL = /\b(?:send|list|health)\s*:\s*FAIL\s*[\u2014-]/i

/** Unreachable / transport-level copy produced by remotes.py and urllib. */
const TRANSPORT_NEEDLES = [
  'connection refused',
  'errno 111',
  'name or service not known',
  'getaddrinfo failed',
  'timed out',
  'not added — the sidebar seat is a catalog placeholder',
]

/** #274/#499: fatal config needles (same family as cliSessionRecovery). */
const FATAL_CONFIG_NEEDLES = [
  'no cli agents are configured',
  'no cli is configured',
  'no cli backend is configured',
  'unconfigured harness',
  'endpoint not configured',
]

export type FlagrantErrorKind = 'remote' | 'fatal-config'

/**
 * True when the text is a flagrant runtime/transport failure — never ordinary
 * conversation content. Deliberately conservative: it must never fire on a
 * message that merely contains words like "fail".
 */
export function isFlagrantErrorText(text: string | null | undefined): boolean {
  return flagrantErrorKind(text) !== undefined
}

/** Which renderer family this flagrant error belongs to (undefined = not one). */
export function flagrantErrorKind(
  text: string | null | undefined,
): FlagrantErrorKind | undefined {
  const blob = (text ?? '').toLowerCase()
  if (!blob) return undefined
  if (FATAL_CONFIG_NEEDLES.some((needle) => blob.includes(needle))) {
    return 'fatal-config'
  }
  if (REMOTE_FAIL.test(blob)) return 'remote'
  if (TRANSPORT_NEEDLES.some((needle) => blob.includes(needle))) return 'remote'
  return undefined
}
