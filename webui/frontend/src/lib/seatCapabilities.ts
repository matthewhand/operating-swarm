/**
 * #580 / #551 doctrine: a seat's session capability is **declared once** and
 * consumed by every surface that offers session affordances.
 *
 * The rail's context menu and the navbar's session switcher used two
 * independent expressions (`kind === 'api' || kind === 'cli' || isCli` vs
 * `isCliAgent && currentCli`), so an API seat was promised "Select session" /
 * "New session" by the rail while the navbar rendered no session control at
 * all. They cannot drift again when both consume `seatHasSessions`.
 *
 * Note the deliberate *absence* of `preferredChatCli`-style fallbacks: gating
 * an affordance on a value that may be **fabricated** for a seat that declares
 * none (see #566) is not a safe predicate.
 */

/** Seat kinds that own swarm-side sessions today. */
const SESSION_CAPABLE_KINDS = new Set(['api', 'cli'])

/**
 * Can this seat have sessions at all? Declared by its kind — not re-derived
 * per surface, not inferred from a resolvable CLI string.
 */
export function seatHasSessions(seat: {
  kind?: string | null
  isCli?: boolean
}): boolean {
  const kind = String(seat.kind || '').trim().toLowerCase()
  if (SESSION_CAPABLE_KINDS.has(kind)) return true
  // CLI rows from the cli-agents endpoint may carry the CLI on `isCli`
  // rather than `kind`.
  if (seat.isCli) return true
  return false
}

/**
 * Should the rail context menu offer Select session / New session for this
 * seat? Same declaration as the navbar consumes — one source of truth.
 */
export function seatOffersSessionMenu(seat: {
  kind?: string | null
  isCli?: boolean
}): boolean {
  return seatHasSessions(seat)
}
