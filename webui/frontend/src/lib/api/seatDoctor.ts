/**
 * GET /v1/seats/doctor — the seat audit, over HTTP.
 *
 * This is the same report `python -m django seat_doctor --json` prints, so the
 * operator does not have to leave the browser to learn which seat needs a credit
 * topped up.
 *
 * It is NOT the same signal as `./seatHealth` (`POST /v1/seats/health`), and the
 * two must never be merged:
 *
 *   - the batch probe is cheap liveness, polled on a 60s interval, and its
 *     `broken` verdict is all the rail's `⚠ broken` label is allowed to claim;
 *   - the doctor is a bounded, evidence-backed audit whose `ok` verdict is
 *     *stricter* — a cheap health check only ever reaches `unverified`, because
 *     only a proved turn counts as working.
 *
 * The run is user-initiated by construction: there is no interval here and
 * nothing in the frontend starts one. See `lib/seatDoctor.ts` for the store.
 */
import { apiGet } from './client'

/**
 * The buckets the backend can name. A bucket is derived from the *shape* of a
 * probe failure, never from a per-seat table, so a new probe shape can add one.
 */
export const SEAT_DOCTOR_BUCKETS = [
  'quota',
  'auth',
  'model_invalid',
  'not_installed',
  'not_executable',
  'not_configured',
  'service_down',
  'unreachable',
  'timeout',
  'misconfigured',
  'timeout_risk',
  'probe_error',
] as const

export type SeatDoctorBucket = (typeof SEAT_DOCTOR_BUCKETS)[number]

/**
 * Wire-typed as `string`-friendly on purpose: a bucket or verdict the server
 * grows later must reach the UI as "unrecognised", not crash the pane. The UI
 * never guesses a meaning for one — it renders it as unknown.
 */
export type SeatDoctorBucketName = SeatDoctorBucket | (string & {})

/** `ok` requires a proved turn. Anything less is `unverified`, never `ok`. */
export type SeatDoctorVerdict = 'ok' | 'broken' | 'unverified'

/** What a probe actually established. */
export type SeatDoctorProves = 'turn' | 'liveness' | 'nothing'

export interface SeatDoctorRow {
  kind: string
  seat_id: string
  label: string
  origin: string
  verdict: SeatDoctorVerdict | (string & {})
  bucket: SeatDoctorBucketName
  detail: string
  /** The operator action. This is the whole point of the report. */
  remediation: string
  proves: SeatDoctorProves | (string & {})
  turn_proved: boolean
  latency_ms: number
  delegates_to: string[]
  /**
   * Server-side redacted. The UI never dumps this into the DOM: an
   * allowlist plus `envVarName()` in `lib/seatDoctor.ts` is the only way a
   * value reaches the screen, and that only ever yields an env var *name*.
   */
  evidence: Record<string, unknown>
}

export interface SeatDoctorTotals {
  seats: number
  broken: number
  unverified: number
  ok: number
}

export interface SeatDoctorReport {
  object: string
  deep: boolean
  read_only: boolean
  totals: SeatDoctorTotals
  /** bucket -> count, highest first. */
  buckets: Record<string, number>
  results: SeatDoctorRow[]
}

export interface SeatDoctorQuery {
  /** Repeatable `kind` filter; empty means every kind. */
  kinds?: string[]
  /** Spend a real round trip per seat. Slower, more evidence. */
  deep?: boolean
  limit?: number
}

export const SEAT_DOCTOR_PATH = '/v1/seats/doctor'

/** Build the query string deterministically so the GET pacer can coalesce. */
export function seatDoctorPath(query: SeatDoctorQuery = {}): string {
  const params = new URLSearchParams()
  for (const kind of query.kinds ?? []) {
    const trimmed = (kind || '').trim()
    if (trimmed) params.append('kind', trimmed)
  }
  if (query.deep) params.append('deep', '1')
  if (typeof query.limit === 'number' && Number.isFinite(query.limit)) {
    params.append('limit', String(Math.trunc(query.limit)))
  }
  const qs = params.toString()
  return qs ? `${SEAT_DOCTOR_PATH}?${qs}` : SEAT_DOCTOR_PATH
}

/**
 * Run one audit. Rejects on a transport/HTTP error, so the caller can say so
 * out loud — an audit that failed must never look like an audit that passed.
 */
export function fetchSeatDoctorReport(
  query: SeatDoctorQuery = {},
): Promise<SeatDoctorReport> {
  return apiGet<SeatDoctorReport>(seatDoctorPath(query))
}
