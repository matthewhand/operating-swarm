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

/** #1374 — sibling turns may run in parallel; Running cards are offered. */
export const PARALLEL_FAN_OUT = 'parallel_fan_out' as const

export interface ParallelFanOutCapability {
  enabled: boolean
  reason: string
}

/**
 * #1374 Phase A — does this seat advertise parallel fan-out?
 *
 * Reads the published `seat_capabilities[kind].parallel_fan_out` row
 * (ADR-016). An absent payload never widens the seat: older backends that
 * do not publish the axis stay off, even for API/team kinds.
 */
/**
 * Which published kind row gates Running cards for the seat on screen.
 * A remote-backed team stays on the remote row (fan-out off): the turn
 * belongs to the remote provider, same as the composer menu's kind key.
 */
export function parallelFanOutKindFor(input: {
  teamId?: string | null
  isCli?: boolean
  isRemote?: boolean
  isRemoteBackedTeam?: boolean
}): 'team' | 'cli' | 'remote' | 'api' {
  if (input.teamId) return input.isRemoteBackedTeam ? 'remote' : 'team'
  if (input.isCli) return 'cli'
  if (input.isRemote || input.isRemoteBackedTeam) return 'remote'
  return 'api'
}

export function seatOffersParallelFanOut(input: {
  kind?: string | null
  declared?: Record<string, { enabled?: boolean; reason?: string } | undefined> | null
}): ParallelFanOutCapability {
  const entry = input.declared?.[PARALLEL_FAN_OUT]
  if (entry && typeof entry.enabled === 'boolean') {
    return { enabled: entry.enabled, reason: String(entry.reason || '') }
  }
  const kind = String(input.kind || '').trim().toLowerCase()
  return {
    enabled: false,
    reason: kind
      ? `Parallel fan-out is not declared for ${kind} seats`
      : 'Parallel fan-out is not declared for this seat kind',
  }
}

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

/** One navbar picker's resolved capability (#1202). */
export interface NavbarPickerCapability {
  enabled: boolean
  reason: string
}

export interface NavbarSeatCapabilities {
  agents: NavbarPickerCapability
  sessions: NavbarPickerCapability
}

export interface NavbarSeatCapabilityInput {
  kind?: string | null
  /** CLI rows from the cli-agents endpoint may carry the CLI on `isCli`. */
  isCli?: boolean
  /** `RemoteConnection.capabilities.sessions` — declared by the remote row. */
  remoteSessions?: boolean | null
  /**
   * The published `seat_capabilities[kind]` payload. A future backend that
   * declares an `agents` / `sessions` axis outranks the matrix below
   * (ADR-016 resolution order); today the vocabulary has neither, so the
   * declared matrix is the fallback.
   */
  declared?: Record<string, { enabled?: boolean; reason?: string } | undefined> | null
  providerName?: string
}

function declaredAxis(
  declared: NavbarSeatCapabilityInput['declared'],
  axis: 'agents' | 'sessions',
): NavbarPickerCapability | null {
  const entry = declared?.[axis]
  if (entry && typeof entry.enabled === 'boolean') {
    return { enabled: entry.enabled, reason: String(entry.reason || '') }
  }
  return null
}

/**
 * #1202 — the ONE declared capability predicate the navbar Agent / Session
 * pickers consume. Not re-derived from `isCliAgent` per surface: a seat
 * advertises `agents` / `sessions` (or the kind's declared fallback does).
 *
 * Matrix: API/blueprint supports both; CLI supports Sessions but not Agents
 * (a single host owns its own agent); Remote supports Agents and Sessions only
 * when the remote row declares `capabilities.sessions`; Team supports both.
 */
export function navbarSeatCapabilities(
  input: NavbarSeatCapabilityInput,
): NavbarSeatCapabilities {
  const kind = String(input.kind || '').trim().toLowerCase()
  const isCli = input.isCli === true || kind === 'cli'
  const isRemote = kind === 'remote' || kind === 'herdr'
  const isTeam = kind === 'team'
  const isApi = kind === 'api' || kind === 'blueprint'
  const provider = String(input.providerName || '').trim() || 'this provider'

  const declaredAgents = declaredAxis(input.declared, 'agents')
  const declaredSessions = declaredAxis(input.declared, 'sessions')

  const agents: NavbarPickerCapability =
    declaredAgents ??
    (isCli
      ? { enabled: false, reason: `Agent selection is not supported by ${provider}` }
      : { enabled: true, reason: '' })

  let sessions: NavbarPickerCapability
  if (declaredSessions) {
    sessions = declaredSessions
  } else if (isRemote) {
    sessions =
      input.remoteSessions === true
        ? { enabled: true, reason: '' }
        : {
            enabled: false,
            reason: `${provider} is stateless and does not support persistent sessions`,
          }
  } else if (isApi || isTeam || isCli) {
    sessions = { enabled: true, reason: '' }
  } else {
    sessions = {
      enabled: false,
      reason: `Session selection is not supported by ${provider}`,
    }
  }

  return { agents, sessions }
}
