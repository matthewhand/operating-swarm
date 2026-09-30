/**
 * The seat doctor, as an operator surface.
 *
 * A repo-wide audit of 93 seats found 53 broken, and almost none of them were
 * code bugs — they were credits to top up, a key to add, a binary to install, a
 * remote pointed at the wrong host. This store holds that answer for the UI.
 *
 * Three rules this file exists to enforce, because breaking any of them makes
 * the operator act on a lie:
 *
 * 1. **It never cries wolf.** `ok` is only ever a *proved turn*. A cheap health
 *    check lands on `unverified`, which is a third state, not a softer `broken`.
 *    And `not_configured` is a setup gap, not a fault: it counts in the
 *    backend's `broken` total (an unconfigured seat cannot do its job) but
 *    `seatDoctorTone` refuses to paint it red. Verdict decides the tone; the
 *    bucket only demotes a `broken` row one step, so `timeout_risk` on an
 *    `unverified` row can never read as a fault either.
 * 2. **It is not the liveness signal.** `lib/seatHealth.ts` owns cheap 60s
 *    liveness and the rail's `⚠ broken` label. Nothing here imports it, and
 *    nothing here writes to it: a 40-second audit must not silently relabel the
 *    rail. (A backend test pins that separation too.)
 * 3. **It is never polled.** There is no interval in this file. A run starts
 *    because a human pressed the button, and a failed run is an `error` state
 *    with a message — never an empty table that reads like good news.
 *
 * Shape follows `lib/seatHealth.ts`: a module-level state object, a listener
 * set, and a CustomEvent so a sibling of the settings sheet can react without a
 * provider.
 */
import { ApiError } from './api/client'
import {
  fetchSeatDoctorReport,
  type SeatDoctorBucketName,
  type SeatDoctorQuery,
  type SeatDoctorReport,
  type SeatDoctorRow,
} from './api/seatDoctor'

export type SeatDoctorStatus = 'idle' | 'running' | 'done' | 'error'

/**
 * How a row is *painted*. Deliberately separate from the backend's verdict:
 * `incomplete` is a `broken` verdict on a bucket that means "not set up yet",
 * and `unknown` is a verdict this UI does not recognise and will not guess at.
 */
export type SeatDoctorTone = 'fault' | 'incomplete' | 'unverified' | 'ok' | 'unknown'

export interface SeatDoctorState {
  status: SeatDoctorStatus
  /** Null until a run succeeds. Kept across a later failure, never faked. */
  report: SeatDoctorReport | null
  error: string
  query: SeatDoctorQuery
  startedAt: number
  /** When the displayed report landed. Zero until the first success. */
  lastSuccessAt: number
}

export const SEAT_DOCTOR_CHANGED_EVENT = 'swarm:seat-doctor-changed'

/**
 * Buckets that describe a seat nobody has finished setting up, not a seat that
 * failed. The backend counts them as broken (correctly — it cannot work); the UI
 * must not paint them like a fault.
 */
export const NOT_A_FAULT_BUCKETS: ReadonlySet<string> = new Set(['not_configured'])

/** One honest sentence per verdict, so the word is never the only signal. */
export const SEAT_DOCTOR_VERDICT_NOTES: Record<string, string> = {
  ok: 'a real turn was proved in this run',
  unverified: 'reachable, but this run did not prove a turn — not a clean bill of health',
  broken: 'this seat did not do its job',
  unknown: 'the server reported a verdict this page does not recognise; it is not guessing',
}

/** `model_invalid` -> `model invalid`. Unknown buckets keep their raw id. */
export const SEAT_DOCTOR_BUCKET_LABELS: Record<string, string> = {
  quota: 'quota',
  auth: 'auth',
  model_invalid: 'model invalid',
  not_installed: 'not installed',
  not_executable: 'not executable',
  not_configured: 'not configured',
  service_down: 'service down',
  unreachable: 'unreachable',
  timeout: 'timeout',
  misconfigured: 'misconfigured',
  timeout_risk: 'timeout risk',
  probe_error: 'probe error',
}

const VERDICTS = new Set(['ok', 'broken', 'unverified'])

/** Short glyphs, so the three states differ without relying on colour alone. */
export const SEAT_DOCTOR_TONE_GLYPHS: Record<SeatDoctorTone, string> = {
  fault: '✕',
  incomplete: '◌',
  unverified: '?',
  ok: '✓',
  unknown: '·',
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function normaliseVerdict(value: unknown): 'ok' | 'broken' | 'unverified' | 'unknown' {
  const raw = text(value).trim().toLowerCase()
  return VERDICTS.has(raw) ? (raw as 'ok' | 'broken' | 'unverified') : 'unknown'
}

function normaliseBucket(value: unknown): string {
  return text(value).trim().toLowerCase()
}

/** The verdict word to print. Never invented for an unrecognised value. */
export function seatDoctorVerdict(row: Pick<SeatDoctorRow, 'verdict'>): string {
  return normaliseVerdict(row.verdict)
}

/**
 * How a row reads. The verdict decides; `not_configured` is the single bucket
 * allowed to demote a `broken` row from "fault" to "incomplete", because nothing
 * is *wrong* there — the seat was simply never set up.
 */
export function seatDoctorTone(
  row: Pick<SeatDoctorRow, 'verdict' | 'bucket'>,
): SeatDoctorTone {
  const verdict = normaliseVerdict(row.verdict)
  if (verdict === 'ok') return 'ok'
  if (verdict === 'unverified') return 'unverified'
  if (verdict === 'broken') {
    return NOT_A_FAULT_BUCKETS.has(normaliseBucket(row.bucket)) ? 'incomplete' : 'fault'
  }
  return 'unknown'
}

/** Faults first, then setup gaps, then unverified, then working. */
const TONE_ORDER: Record<SeatDoctorTone, number> = {
  fault: 0,
  incomplete: 1,
  unverified: 2,
  unknown: 3,
  ok: 4,
}

export function seatDoctorBucketLabel(bucket: SeatDoctorBucketName | ''): string {
  const key = normaliseBucket(bucket)
  if (!key) return '—'
  return SEAT_DOCTOR_BUCKET_LABELS[key] ?? key.replace(/_/g, ' ')
}

// --- env var names, never values -------------------------------------------

const ENV_EVIDENCE_KEYS = ['api_key_env', 'cookie_env', 'missing_env'] as const
/** Shell-portable variable name. Anything else is not a name. */
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/

/**
 * The variable *name* out of a server value, or `''`.
 *
 * The backend already redacts, but "already redacted" is not a reason to trust
 * a second consumer: `${VAR}` and `VAR` are names, `VAR=secret` yields the name
 * before the `=`, and anything that is not a plausible identifier is dropped
 * rather than printed. A secret can therefore never reach the DOM through this
 * path, whatever the server sent.
 */
export function envVarName(raw: unknown): string {
  const trimmed = text(raw).trim()
  if (!trimmed) return ''
  const braced = trimmed.match(/^\$\{([^{}]+)\}$/)
  if (braced) {
    const inner = braced[1].trim()
    return ENV_NAME.test(inner) ? inner : ''
  }
  const assigned = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=/)
  if (assigned) return assigned[1]
  return ENV_NAME.test(trimmed) ? trimmed : ''
}

/** Env var *names* an `auth`-shaped row points at. Never their values. */
export function envVarNames(row: Pick<SeatDoctorRow, 'evidence'>): string[] {
  const evidence = row.evidence
  if (!evidence || typeof evidence !== 'object' || Array.isArray(evidence)) return []
  const record = evidence as Record<string, unknown>
  const names: string[] = []
  for (const key of ENV_EVIDENCE_KEYS) {
    const name = envVarName(record[key])
    if (name && !names.includes(name)) names.push(name)
  }
  return names
}

// --- summary ----------------------------------------------------------------

export interface SeatDoctorSummary {
  seats: number
  broken: number
  unverified: number
  ok: number
  /** A verdict this UI does not recognise. Counted, never merged into ok. */
  unknown: number
  /** `not_configured` rows inside `broken`. Still counted as broken. */
  incomplete: number
  /** Highest count first, then alphabetical, so the list is stable. */
  buckets: Array<{ bucket: string; label: string; count: number }>
}

/**
 * Counted from the rows, not from the server's `totals`. The rows are the whole
 * report, so recomputing cannot disagree with the table — and a `totals` block
 * that disagreed would be exactly the kind of quiet lie this page must not tell.
 */
export function summariseSeatDoctor(rows: readonly SeatDoctorRow[]): SeatDoctorSummary {
  const counts: Record<string, number> = {}
  const summary: SeatDoctorSummary = {
    seats: rows.length,
    broken: 0,
    unverified: 0,
    ok: 0,
    unknown: 0,
    incomplete: 0,
    buckets: [],
  }
  for (const row of rows) {
    const verdict = normaliseVerdict(row.verdict)
    if (verdict === 'broken') {
      summary.broken += 1
      if (seatDoctorTone(row) === 'incomplete') summary.incomplete += 1
    } else if (verdict === 'unverified') summary.unverified += 1
    else if (verdict === 'ok') summary.ok += 1
    else summary.unknown += 1

    const bucket = normaliseBucket(row.bucket)
    if (bucket) counts[bucket] = (counts[bucket] ?? 0) + 1
  }
  summary.buckets = Object.entries(counts)
    .map(([bucket, count]) => ({ bucket, label: seatDoctorBucketLabel(bucket), count }))
    .sort((a, b) => b.count - a.count || a.bucket.localeCompare(b.bucket))
  return summary
}

/** Faults first. A diagnostic that leads with the healthy rows buries the point. */
export function sortSeatDoctorRows(rows: readonly SeatDoctorRow[]): SeatDoctorRow[] {
  return [...rows].sort(
    (a, b) =>
      TONE_ORDER[seatDoctorTone(a)] - TONE_ORDER[seatDoctorTone(b)] ||
      (a.label || a.seat_id).localeCompare(b.label || b.seat_id),
  )
}

// --- store ------------------------------------------------------------------

type SeatDoctorFetcher = (query: SeatDoctorQuery) => Promise<SeatDoctorReport>

const defaultFetcher: SeatDoctorFetcher = (query) => fetchSeatDoctorReport(query)

let fetcher: SeatDoctorFetcher = defaultFetcher
let inflight: Promise<SeatDoctorReport | null> | null = null
let state: SeatDoctorState = {
  status: 'idle',
  report: null,
  error: '',
  query: {},
  startedAt: 0,
  lastSuccessAt: 0,
}

const listeners = new Set<() => void>()

function emit(): void {
  try {
    window.dispatchEvent(new CustomEvent(SEAT_DOCTOR_CHANGED_EVENT))
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

function patch(next: Partial<SeatDoctorState>): void {
  state = { ...state, ...next }
  emit()
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.message || 'the request failed'} (HTTP ${error.status})`
  }
  if (error instanceof Error && error.message.trim()) return error.message
  return 'the request failed without a message'
}

/** Current state. A stable object reference, so `useState` will not loop. */
export function seatDoctorState(): SeatDoctorState {
  return state
}

export function subscribeSeatDoctor(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

/**
 * Run one audit, now. Human-initiated only: nothing in this module schedules
 * itself, and a second press while a run is in flight joins that run rather than
 * starting a second 40-second audit.
 *
 * Resolves to the report, or `null` when the run failed. A failure is recorded
 * as an `error` with a message and the *previous* report is kept, so the pane
 * can say "this run failed" above real rows instead of showing nothing.
 */
export function runSeatDoctor(query: SeatDoctorQuery = {}): Promise<SeatDoctorReport | null> {
  if (inflight) return inflight
  patch({ status: 'running', error: '', query, startedAt: Date.now() })
  const run = fetcher(query)
    .then((report) => {
      // A body that is not a report is a failure. Rendering it as zero rows
      // would be the one lie this page cannot make.
      if (!report || typeof report !== 'object' || !Array.isArray(report.results)) {
        throw new Error('the server did not return a seat doctor report')
      }
      patch({ status: 'done', report, error: '', lastSuccessAt: Date.now() })
      return report
    })
    .catch((error: unknown) => {
      patch({ status: 'error', error: errorMessage(error) })
      return null
    })
    .finally(() => {
      inflight = null
    })
  inflight = run
  return run
}

/** Test hook: replace the transport, and get the default back to restore it. */
export function __setSeatDoctorFetcher(next: SeatDoctorFetcher | null): void {
  fetcher = next || defaultFetcher
}

/** Test hook: drop all state. */
export function resetSeatDoctor(): void {
  inflight = null
  state = { status: 'idle', report: null, error: '', query: {}, startedAt: 0, lastSuccessAt: 0 }
  emit()
}
