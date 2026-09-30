/**
 * Seat health across all three seat kinds (#1658 follow-up).
 *
 * The operator's complaint was "many agents aren't responding", and the UI had
 * no way to say so: a broken seat looked exactly like a working one. This
 * store is the one place that knows, and it follows the existing
 * `remoteHealth.ts` pattern (#1196) — a module-level map, a poll interval, and
 * a CustomEvent so consumers re-render without a context provider.
 *
 * Two tiers, because they answer different questions:
 *   - `probe` asks the backend whether a seat is reachable (a remote's health,
 *     an API seat's tiny provider call, a CLI's `--version`).
 *   - a real turn failing is stronger evidence than any probe, so the chat
 *     path can promote a seat to `broken` via `noteTurnFailure` — and a later
 *     success or probe clears it. Nothing is renamed by hand, so a seat that
 *     recovers gets its real name back on its own.
 *
 * Names are decorated in exactly one place: `seatDisplayName`, which
 * `agentLabel` (the funnel every agent name in the UI flows through) calls.
 *
 * One request per tick, whatever the rail size. `POST /v1/seats/health` takes a
 * `seats` array, so asking it once per seat multiplies traffic by the seat
 * count; and the rail rebuilds its seat list on every poll, so re-probing per
 * call turned each rebuild into a burst. Both are what put 190k requests on
 * this endpoint in a day.
 *
 * #1783: a 429 from that same throttle shuts the poll until the server's
 * `Retry-After` is up. This store is a recurring writer, so retrying into a
 * closed window is how one write per minute became a toast per minute.
 */
import { probeSeatHealthBatch, type SeatHealthRow } from './api/seatHealth'
import { isThrottleError } from './api'
import { createThrottleGate } from './healthThrottle'

export type SeatKind = 'api' | 'cli' | 'remote'
export type SeatHealthState = 'unknown' | 'ok' | 'broken'

/** The minimum a verdict is keyed by — what every read helper takes. */
export interface SeatKey {
  kind: string
  seatId: string
}

export interface SeatRef extends SeatKey {
  kind: SeatKind
  /** CLI seats may be listed under an id that is not the binary name. */
  cli?: string
  baseUrl?: string
  apiKeyEnv?: string
  model?: string
}

export interface SeatHealth {
  state: SeatHealthState
  reason: string
  checkedAt: number
}

export const SEAT_HEALTH_CHANGED_EVENT = 'swarm:seat-health-changed'
export const SEAT_HEALTH_POLL_MS = 60_000
/** Marks a broken seat. Plain text so it is readable, and glyph-agnostic. */
export const BROKEN_SUFFIX = '⚠ broken'

const health = new Map<string, SeatHealth>()
const listeners = new Set<() => void>()
let timer: number | null = null
let tracked: SeatRef[] = []
/** Sorted, de-duplicated `kind:seat_id` list for `tracked`; see `trackSeatHealth`. */
let trackedSignature: string | null = null
/** A batch is in flight — a tick landing now is dropped, not queued. */
let inFlight = false
/**
 * #1783: shut until the throttle window frees. This poll is a recurring writer
 * against a 1/minute DRF write throttle, so a 429 is a signal to go quiet for
 * the server's advertised `Retry-After`, not a hiccup to retry next tick.
 */
const throttle = createThrottleGate()
/** How far into the CLI seats the fork window has walked. */
let cliCursor = 0

/**
 * Two server-side limits this store has to respect, both from
 * `swarm/core/seat_health.py`:
 *
 *  - `MAX_BATCH` truncates the `seats` array without saying so, so a rail
 *    longer than this has to be split across requests rather than have its
 *    tail silently unprobed for ever;
 *  - `CLI_PROBES_PER_BATCH` caps how many *distinct* CLI binaries one request
 *    forks — the rest come back `unknown`/"deferred". A fixed request order
 *    would therefore starve every CLI past the cap for ever, so the CLI seats
 *    are rotated through the front of the request instead.
 */
const BACKEND_MAX_BATCH = 60
const BACKEND_CLI_PROBES = 6

/**
 * The transport, behind a seam so a test can drive verdicts without a network
 * (module-mocking this store's own API module is brittle: the store and the
 * API module deliberately share a basename).
 */
type SeatProber = (seats: SeatRef[]) => Promise<SeatHealthRow[]>

const defaultProber: SeatProber = (seats) =>
  probeSeatHealthBatch(
    seats.map((s) => ({
      kind: s.kind,
      seat_id: s.seatId,
      ...(s.cli ? { cli: s.cli } : {}),
      ...(s.baseUrl ? { base_url: s.baseUrl } : {}),
      ...(s.apiKeyEnv ? { api_key_env: s.apiKeyEnv } : {}),
      ...(s.model ? { model: s.model } : {}),
    })),
  )

let prober: SeatProber = defaultProber

/** Test hook: replace the transport, and get the default back to restore it. */
export function __setSeatHealthProber(next: SeatProber | null): void {
  prober = next || defaultProber
}

function key(ref: SeatKey): string {
  return `${ref.kind}:${(ref.seatId || '').trim()}`
}

function emit(): void {
  try {
    window.dispatchEvent(new CustomEvent(SEAT_HEALTH_CHANGED_EVENT))
  } catch {
    /* non-browser (tests) */
  }
  for (const fn of listeners) {
    try {
      fn()
    } catch {
      /* a bad subscriber must not stop the others */
    }
  }
}

function setState(ref: SeatKey, next: SeatHealth): void {
  const k = key(ref)
  const prev = health.get(k)
  if (prev && prev.state === next.state && prev.reason === next.reason) return
  health.set(k, next)
  emit()
}

/** Last known health for a seat. `unknown` until the first probe lands. */
export function seatHealth(ref: SeatKey): SeatHealth {
  return (
    health.get(key(ref)) || {
      state: 'unknown' as SeatHealthState,
      reason: '',
      checkedAt: 0,
    }
  )
}

export function seatIsBroken(ref: SeatKey | null | undefined): boolean {
  if (!ref) return false
  return seatHealth(ref).state === 'broken'
}

export function seatBrokenReason(ref: SeatKey | null | undefined): string {
  if (!ref) return ''
  const row = seatHealth(ref)
  return row.state === 'broken' ? row.reason : ''
}

/**
 * The name an operator actually sees.
 *
 * Unchanged when healthy or unknown — only a seat with an explicit `broken`
 * verdict is decorated, so a transient probe failure can never rename a
 * working agent in the UI.
 */
export function seatDisplayName(
  name: string,
  ref: SeatKey | null | undefined,
): string {
  const base = (name || '').trim()
  if (!base || !ref) return base
  const row = seatHealth(ref)
  if (row.state !== 'broken') return base
  return `${base} ${BROKEN_SUFFIX}`
}

/** Mark a seat broken because a real turn failed. Clears on a later success. */
export function noteTurnFailure(ref: SeatKey, reason: string): void {
  setState(ref, { state: 'broken', reason: (reason || 'turn failed').slice(0, 200), checkedAt: Date.now() })
}

/** Clear a turn-failure verdict once a real turn succeeds. */
export function noteTurnSuccess(ref: SeatKey): void {
  const k = key(ref)
  const prev = health.get(k)
  if (prev && prev.state === 'ok') return
  health.set(k, { state: 'ok', reason: '', checkedAt: Date.now() })
  emit()
}

/** The tracked seats as one comparable string: order-insensitive, deduplicated. */
function seatSetSignature(seats: SeatRef[]): string {
  return Array.from(new Set(seats.map(key))).sort().join('|')
}

/** First occurrence of each seat key wins; a rail can name one seat twice. */
function dedupe(seats: SeatRef[]): SeatRef[] {
  const seen = new Set<string>()
  const out: SeatRef[] = []
  for (const seat of seats) {
    const k = key(seat)
    if (seen.has(k)) continue
    seen.add(k)
    out.push(seat)
  }
  return out
}

/**
 * Put the next `BACKEND_CLI_PROBES` CLI seats at the front of the request, so
 * the fork window walks the whole set over successive ticks.
 */
function rotateClis(seats: SeatRef[]): SeatRef[] {
  const slots: number[] = []
  for (let i = 0; i < seats.length; i += 1) {
    if (seats[i].kind === 'cli') slots.push(i)
  }
  if (slots.length <= BACKEND_CLI_PROBES) return seats
  const shift = cliCursor % slots.length
  cliCursor += BACKEND_CLI_PROBES
  if (shift === 0) return seats
  const out = seats.slice()
  const clis = slots.map((i) => out[i])
  for (let n = 0; n < slots.length; n += 1) {
    out[slots[n]] = clis[(n + shift) % clis.length]
  }
  return out
}

/** One request per `BACKEND_MAX_BATCH` seats. */
function toRequests(seats: SeatRef[]): SeatRef[][] {
  const parts: SeatRef[][] = []
  for (let i = 0; i < seats.length; i += BACKEND_MAX_BATCH) {
    parts.push(seats.slice(i, i + BACKEND_MAX_BATCH))
  }
  return parts
}

function applyRow(row: SeatHealthRow): void {
  const ref = { kind: row?.kind ?? '', seatId: row?.seat_id ?? '' }
  if (!ref.kind || !ref.seatId) return
  if (row.state === 'unknown') {
    // `unknown` is the ABSENCE of an answer, not a verdict: the backend reports
    // a capped-out CLI, an unrecognised kind and a deliberately skipped seat
    // that way. A real turn failing is stronger evidence than any probe, and a
    // probe saying "I don't know" is not evidence at all — so this must never
    // overwrite what is already known.
    return
  }
  setState(ref, {
    state: row.state,
    reason: row.reason || '',
    checkedAt: row.checked_at || Date.now(),
  })
}

/**
 * One poll tick: the whole tracked set in as few requests as the backend's
 * batch cap allows. This is the single place that talks to the network, and it
 * is batch-shaped on purpose — the endpoint takes a `seats` array, and asking
 * it once per seat is a 20x traffic amplification over a 20-seat rail.
 *
 * A tick that lands while a batch is in flight is dropped rather than queued:
 * the next one is 60s away, and queueing is exactly the busy loop this
 * replaced.
 */
function probeTracked(): void {
  if (inFlight) return
  // #1783: no dig-while-429. A shut gate costs zero requests, and every last
  // verdict below still stands, so the rail keeps saying what it last knew.
  if (throttle.paused()) return
  const parts = toRequests(rotateClis(dedupe(tracked)))
  if (parts.length === 0) return
  inFlight = true
  Promise.all(
    parts.map((part) => {
      let pending: Promise<SeatHealthRow[]>
      try {
        pending = Promise.resolve(prober(part))
      } catch {
        // A transport that throws synchronously must not wedge the interval.
        return Promise.resolve({ throttled: false, rows: [] as SeatHealthRow[] })
      }
      // Per-request isolation: one failed request must not cost the others
      // their verdicts. A 429 additionally shuts the gate, so the next tick
      // waits out the window instead of feeding the throttle that just spoke.
      return pending.then(
        (rows) => ({ throttled: false, rows: Array.isArray(rows) ? rows : [] }),
        (err: unknown) => {
          const throttled = isThrottleError(err)
          if (throttled) throttle.note(err)
          return { throttled, rows: [] as SeatHealthRow[] }
        },
      )
    }),
  )
    .then((batches) => {
      // A split batch is the only way two parts race here, and a success must
      // not un-shut a gate the other part just closed.
      if (batches.every((b) => !b.throttled)) throttle.noteSuccess()
      for (const batch of batches) {
        for (const row of batch.rows) {
          try {
            applyRow(row)
          } catch {
            /* one unusable row must not cost the batch its other verdicts */
          }
        }
      }
    })
    .catch(() => {
      // A failed status poll is not proof the seat is broken. Every last
      // verdict is left alone rather than renaming a working agent.
    })
    .finally(() => {
      inFlight = false
    })
}

/**
 * Publish the seats the rail is showing, and keep polling them.
 *
 * Whether to re-probe is decided by the SET of seat keys — a sorted, deduplicated
 * `kind:seat_id` list — not by the caller's array identity. The rail rebuilds
 * this list on every `remotes` / agent poll, and re-probing per call turned each
 * rebuild into a burst of one request per seat. A pure reorder, or a fresh array
 * with identical contents, now costs nothing; a genuinely new seat still gets an
 * immediate verdict (unless the throttle gate is shut, #1783 — then it gets the
 * next tick), which is the whole point of the feature.
 */
export function trackSeatHealth(seats: SeatRef[]): void {
  const next = dedupe((seats || []).filter((s) => s && s.kind && s.seatId))
  const signature = seatSetSignature(next)
  if (trackedSignature !== null && signature === trackedSignature) {
    // Same seats, new array. Keep the newest refs for the payload, spend no
    // traffic.
    tracked = next
    return
  }
  tracked = next
  trackedSignature = signature
  emit()
  if (next.length === 0) {
    // Nothing to poll: never leave an interval running over an empty set.
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    return
  }
  if (timer === null && typeof window !== 'undefined') {
    timer = window.setInterval(probeTracked, SEAT_HEALTH_POLL_MS)
  }
  probeTracked()
}

export function stopTrackingSeatHealth(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
  tracked = []
  // Cleared so the next `trackSeatHealth` is a fresh subscription and probes
  // once, even for the same seats — that is a remount, not a rail rebuild.
  trackedSignature = null
  inFlight = false
  throttle.noteSuccess()
}

/** Re-probe immediately (a manual refresh, or right after a seat switch). */
export function refreshSeatHealth(): void {
  probeTracked()
}

/** Subscribe to health changes; returns an unsubscribe function. */
export function subscribeSeatHealth(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

/** Test hook: drop all state and stop polling. */
export function resetSeatHealth(): void {
  stopTrackingSeatHealth()
  health.clear()
  cliCursor = 0
  emit()
}
