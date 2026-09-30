/**
 * #1196 (shape) + #1783 (traffic) — shared remote health state.
 *
 * `RemoteSessionsPopup` probed health privately and died with its unmount.
 * This store owns the probes once, on a 60s interval (plus a manual refresh),
 * and every consumer — popup, rail rows, chat banner — reads the same map.
 * The CustomEvent mirrors the localStorage-pref pattern so components react
 * without a context provider.
 *
 * #1783: one write per tick, whatever the remote count.
 *
 * `POST /v1/remotes/<id>/health/` takes a single id, and a 60s tick over N
 * remotes is therefore N writes against a DRF write throttle of 1/minute.
 * Measured: ~290k requests to that endpoint in a day, and a `Too many requests
 * — the server is busy` toast every tick. So the poll no longer uses that route
 * at all: it asks `POST /v1/seats/health` — already batch-shaped, already
 * probing `kind: "remote"` through the same `remotes.check_health`, and cached
 * server-side for a minute — with every tracked id in ONE body. The per-id
 * route survives for the deliberate single "test this remote" click in
 * Settings; a poll is not that.
 *
 * The rules below are all load-bearing, and each one exists because of a
 * measured failure:
 *  - `startRemoteHealthPolling` re-probes only when a caller has just ADDED ids
 *    to its own list (#1196). The rail rebuilds its id list on every `remotes`
 *    poll and the chat pane rebuilds one on every remote switch; re-probing per
 *    call turned each rebuild into a fresh volley. An unchanged list costs
 *    nothing, and that invariant is unchanged by batching.
 *  - a tick landing while a request is in flight is DROPPED, not queued. The
 *    next tick is 60s away; queueing is a busy loop, and a busy loop is what
 *    the throttle report was recording.
 *  - a 429 SHUTS THE GATE until the server's own `Retry-After` is up (#1783).
 *    Retrying into a throttle is what produced the toast loop, and a poll is
 *    the one caller that can afford to be quiet.
 *
 * Honesty rules, unchanged in spirit from the per-id version and sharpened by
 * the batch: a verdict is only written when the server actually said something
 * about THAT remote. A failed or throttled batch request says nothing about any
 * remote, so every last verdict stands rather than the rail lighting up every
 * offline dot because the server was busy.
 */
import { probeRemoteHealthBatch, type SeatHealthRow } from './api/seatHealth'
import { createThrottleGate } from './healthThrottle'
import { isThrottleError } from './api'

export type RemoteHealthStatus = 'pending' | 'ok' | 'failed' | 'unconfigured'

export const REMOTE_HEALTH_CHANGED_EVENT = 'swarm:remote-health-changed'
const POLL_INTERVAL_MS = 60_000

/**
 * `check_health` gap codes for the two "nothing was probed" short-circuits,
 * carried through the seat batch row as `gap` (#1783). A remote in one of these
 * states has no instance to reach, so it must never be folded into `failed` —
 * the honest rendering is "not configured", and `isRemoteOffline` deliberately
 * stays false for them.
 */
export const UNCONFIGURED_GAPS = new Set([
  'remote_not_added',
  'remote_base_url_placeholder',
])

/**
 * `MAX_BATCH` in `swarm/core/seat_health.py` truncates the `seats` array
 * without saying so. A rail longer than this is split across requests rather
 * than have its tail silently unprobed for ever — the same trade the seat
 * store makes. At any realistic remote count this is one write per tick.
 */
const BACKEND_MAX_BATCH = 60

const status = new Map<string, RemoteHealthStatus>()
/**
 * Who asked for a poll, and which ids each of them currently wants. Scoped per
 * owner so the rail unmounting cannot silently stop the chat pane's poll (and
 * vice versa) — two surfaces with different lifetimes, one shared interval.
 * The interval runs while at least one owner remains.
 */
const owners = new Map<string, Set<string>>()
/** The default owner, for callers that hold no lifetime of their own. */
const DEFAULT_OWNER = 'default'
let timer: ReturnType<typeof setInterval> | null = null
/** A batch is in flight — a tick landing now is dropped, not queued. */
let inFlight = false
/** #1783: shut until the throttle window frees. See `lib/healthThrottle`. */
const throttle = createThrottleGate()

/**
 * The transport, behind a seam so a test can drive verdicts without a network.
 * (Same reason as the seat store's seam: module-mocking the store's own API
 * module is brittle because store and API module share a basename.)
 */
type RemoteProber = (ids: string[]) => Promise<SeatHealthRow[]>

const defaultProber: RemoteProber = (ids) => probeRemoteHealthBatch(ids)

let prober: RemoteProber = defaultProber

/** Test hook: replace the transport, and get the default back to restore it. */
export function __setRemoteHealthProber(next: RemoteProber | null): void {
  prober = next || defaultProber
}

function emit(): void {
  try {
    window.dispatchEvent(new CustomEvent(REMOTE_HEALTH_CHANGED_EVENT))
  } catch {
    /* non-browser (tests) */
  }
}

/** `every id any owner currently wants`, de-duplicated across owners. */
function trackedIds(): string[] {
  const all = new Set<string>()
  for (const ids of owners.values()) {
    for (const id of ids) all.add(id)
  }
  return Array.from(all)
}

/** One request per `BACKEND_MAX_BATCH` ids. */
function toRequests(ids: string[]): string[][] {
  const parts: string[][] = []
  for (let i = 0; i < ids.length; i += BACKEND_MAX_BATCH) {
    parts.push(ids.slice(i, i + BACKEND_MAX_BATCH))
  }
  return parts
}

/**
 * The verdict for one remote seat row, or `null` when the row says nothing
 * about it.
 *
 * `unknown` is the ABSENCE of an answer, not a verdict: it is what a capped-out
 * CLI seat, an unrecognised kind, a probe that raised, and a deliberately
 * skipped seat all report. A remote that was never configured is the one
 * `unknown` case with a positive claim behind it, and it says so with a `gap`
 * code — so it becomes `unconfigured`, and every other `unknown` leaves the
 * last verdict alone. Marking a whole remote fleet offline because our own
 * probe crashed is the exact lie the `⚠ broken` badge must not tell.
 */
function verdictFor(row: SeatHealthRow): RemoteHealthStatus | null {
  const id = (row?.seat_id || '').trim()
  if (!id) return null
  if (row.state === 'ok') return 'ok'
  if (row.state === 'broken') return 'failed'
  const gap = (row.gap || '').trim()
  if (UNCONFIGURED_GAPS.has(gap)) return 'unconfigured'
  return null
}

function applyRows(rows: SeatHealthRow[]): void {
  let changed = false
  for (const row of Array.isArray(rows) ? rows : []) {
    let next: RemoteHealthStatus | null = null
    try {
      next = verdictFor(row)
    } catch {
      /* one unusable row must not cost the batch its other verdicts */
    }
    if (!next) continue
    const id = (row?.seat_id || '').trim()
    if (status.get(id) === next) continue
    status.set(id, next)
    changed = true
  }
  if (changed) emit()
}

/**
 * Send one batch for `ids`, in as few writes as the backend cap allows.
 *
 * The ONLY place this store talks to the network. A tick that lands while a
 * batch is in flight, or while the throttle gate is shut, costs nothing: both
 * are dropped, never queued, and the ids are simply picked up by the next tick
 * (or the one after `Retry-After`).
 */
function send(ids: string[]): void {
  if (ids.length === 0) return
  if (throttle.paused()) return
  if (inFlight) return
  inFlight = true
  const parts = toRequests(ids)
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
      // their verdicts, and a 429 on one of them is recorded, not thrown away.
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
      for (const batch of batches) applyRows(batch.rows)
    })
    .catch(() => {
      // A failed status poll is not proof any remote is down. Every last
      // verdict is left alone rather than announcing an offline fleet.
    })
    .finally(() => {
      inFlight = false
    })
}

/**
 * One poll tick: the whole tracked set, in one write. The source is the owners'
 * lists rather than `status`, so a remote the operator can see is polled
 * whether or not its last verdict ever landed.
 */
function probeTracked(): void {
  send(trackedIds())
}

export function remoteHealthStatus(remoteId: string): RemoteHealthStatus {
  return status.get(remoteId) ?? 'pending'
}

export function isRemoteOffline(remoteId: string): boolean {
  return remoteHealthStatus(remoteId) === 'failed'
}

/** True when the seat has no instance to talk to — "not configured", not "down". */
export function isRemoteUnconfigured(remoteId: string): boolean {
  return remoteHealthStatus(remoteId) === 'unconfigured'
}

export function remoteHealthSnapshot(): Record<string, RemoteHealthStatus> {
  return Object.fromEntries(status)
}

/**
 * Probe the given remotes now, whatever the poll is doing. No-op while a batch
 * is in flight or while the throttle gate is shut (#1783: no dig-while-429).
 * This is the explicit "refresh" path and deliberately does NOT change what
 * the poll tracks.
 */
export function refreshRemoteHealth(remoteIds: string[]): void {
  const ids = Array.from(new Set((remoteIds || []).filter(Boolean)))
  send(ids)
}

/**
 * Publish the remotes an owner wants, and keep polling them.
 *
 * Whether to re-probe is decided by what changed in that owner's LIST, not by
 * the caller's array identity: only ids this owner has just ADDED are probed.
 * A fresh owner — its first call, or a remount after a stop — probes once,
 * because that is a new subscription rather than a rail rebuild.
 *
 * The immediate verdict for a newly added id is one write for the WHOLE
 * tracked set, not a write for the new id: the batch is the unit of traffic
 * here, and a second write would be the amplification this replaced.
 */
export function startRemoteHealthPolling(
  remoteIds: string[],
  owner: string = DEFAULT_OWNER,
): void {
  const ids = Array.from(new Set((remoteIds || []).filter(Boolean)))
  const previous = owners.get(owner)
  const added = previous ? ids.filter((id) => !previous.has(id)) : ids
  owners.set(owner, new Set(ids))
  if (timer == null && typeof window !== 'undefined') {
    timer = setInterval(probeTracked, POLL_INTERVAL_MS)
  }
  // A new remote, or a new subscription, gets an immediate verdict; a rebuild
  // carrying the same ids spends no traffic at all.
  if (added.length > 0) probeTracked()
}

/**
 * Release one owner's demand. The shared interval stops only when the LAST
 * owner lets go, so one surface unmounting cannot starve another.
 */
export function stopRemoteHealthPolling(owner: string = DEFAULT_OWNER): void {
  owners.delete(owner)
  if (owners.size === 0 && timer != null) {
    clearInterval(timer)
    timer = null
  }
}

/** Test-only: the store is a singleton, so suites need a clean slate. */
export function __resetRemoteHealthForTests(): void {
  owners.clear()
  if (timer != null) {
    clearInterval(timer)
    timer = null
  }
  status.clear()
  inFlight = false
  throttle.noteSuccess()
}
