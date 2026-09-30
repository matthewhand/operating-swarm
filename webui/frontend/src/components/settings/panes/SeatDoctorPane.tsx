/**
 * Seat doctor — the operator-facing surface for `GET /v1/seats/doctor`.
 *
 * Plain on purpose. This is a diagnostic table, not a dashboard: a seat name, a
 * verdict, a bucket, and the fix.
 *
 * Three properties the component is built around, in order of importance:
 *
 * 1. **It never cries wolf.** `unverified` is a third state, not a softer
 *    `broken`, and it is never painted with the error token. A `not_configured`
 *    row counts in the broken total (the backend is right: an unconfigured seat
 *    cannot work) but reads as "incomplete", not "on fire". A verdict this page
 *    does not recognise renders as unknown rather than being folded into ok.
 * 2. **A failed run says so.** The table renders from a real report or not at
 *    all. A transport error, a 500, and a body that is not a report each get an
 *    explicit error block — the absence of that block is the only thing that
 *    means "all clear", and there is no path that produces an empty table on
 *    failure. A completed run covering zero seats is *also* called out, because
 *    "0 rows" otherwise reads exactly like good news.
 * 3. **The fix is the headline.** `remediation` is the largest text in a row;
 *    `detail` (the evidence it came from) is quieter.
 *
 * It is not the rail's `⚠ broken`. That label is cheap liveness from
 * `lib/seatHealth.ts`, polled every 60s. This is a bounded audit that requires a
 * *user* press, and the two never write into each other.
 */
import { useEffect, useId, useMemo, useState } from 'react'
import { AlertCircle, Loader2, RefreshCw, Stethoscope, Wrench } from 'lucide-react'
import { Alert, Button } from '../../DaisyUI'
import {
  NOT_A_FAULT_BUCKETS,
  SEAT_DOCTOR_CHANGED_EVENT,
  SEAT_DOCTOR_TONE_GLYPHS,
  SEAT_DOCTOR_VERDICT_NOTES,
  envVarNames,
  runSeatDoctor,
  seatDoctorState,
  seatDoctorTone,
  seatDoctorVerdict,
  sortSeatDoctorRows,
  subscribeSeatDoctor,
  summariseSeatDoctor,
  type SeatDoctorState,
} from '../../../lib/seatDoctor'
import type { SeatDoctorRow } from '../../../lib/api/seatDoctor'

/** Filter options. `all` is the default — a filter must never hide a fault. */
const FILTERS = [
  { id: 'all', label: 'All seats' },
  { id: 'fault', label: 'Faults' },
  { id: 'incomplete', label: 'Not set up' },
  { id: 'unverified', label: 'Unverified' },
  { id: 'ok', label: 'Proved' },
] as const

type FilterId = (typeof FILTERS)[number]['id']

const KIND_OPTIONS = ['api', 'cli', 'remote'] as const

function clock(at: number): string {
  if (!at) return ''
  try {
    return new Date(at).toLocaleTimeString()
  } catch {
    return ''
  }
}

function relative(at: number, now: number): string {
  if (!at) return ''
  const seconds = Math.max(0, Math.round((now - at) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  return `${minutes}m ago`
}

/**
 * The env var *name* a row points at, never its value. See `envVarName()` in
 * `lib/seatDoctor.ts` — a value that is not a plausible identifier is dropped
 * rather than printed, so a secret cannot reach the DOM through this path.
 */
function credentialChips(row: SeatDoctorRow): string[] {
  if (seatDoctorTone(row) === 'ok') return []
  return envVarNames(row)
}

function VerdictChip({ row }: { row: SeatDoctorRow }) {
  const tone = seatDoctorTone(row)
  const verdict = seatDoctorVerdict(row)
  const note = SEAT_DOCTOR_VERDICT_NOTES[verdict] ?? SEAT_DOCTOR_VERDICT_NOTES.unknown
  const label = tone === 'incomplete' ? `${verdict} · not set up` : verdict
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <span
        className="os-seat-doctor-verdict"
        data-tone={tone}
        data-testid="seat-doctor-verdict"
      >
        <span className="os-seat-doctor-verdict__glyph" aria-hidden="true">
          {SEAT_DOCTOR_TONE_GLYPHS[tone]}
        </span>
        {label}
      </span>
      <span className="text-[0.65rem] leading-tight text-base-content/60">{note}</span>
    </span>
  )
}

function SeatDoctorRowView({ row }: { row: SeatDoctorRow }) {
  const tone = seatDoctorTone(row)
  const envs = credentialChips(row)
  const seatName = row.label || row.seat_id || '(unnamed seat)'
  return (
    <tr
      className="os-seat-doctor-row align-top"
      data-testid="seat-doctor-row"
      data-tone={tone}
      data-verdict={seatDoctorVerdict(row)}
      data-bucket={row.bucket || ''}
      data-seat-id={row.seat_id}
    >
      <td>
        <div className="text-sm font-semibold">{seatName}</div>
        <div className="font-mono text-[0.65rem] text-base-content/60">
          {row.kind} · {row.seat_id}
        </div>
        {row.origin ? (
          <div className="font-mono text-[0.65rem] text-base-content/50">{row.origin}</div>
        ) : null}
        {envs.length > 0 ? (
          <div className="mt-0.5 text-[0.65rem] text-base-content/60">
            env name only:{' '}
            {envs.map((name) => (
              <code key={name} className="mr-1 font-mono">
                ${name}
              </code>
            ))}
          </div>
        ) : null}
      </td>
      <td>
        <VerdictChip row={row} />
      </td>
      <td>
        <span
          className="badge badge-ghost badge-sm"
          data-testid="seat-doctor-bucket"
          data-fault={String(
            tone === 'fault' && !!row.bucket && !NOT_A_FAULT_BUCKETS.has(row.bucket),
          )}
        >
          {row.bucket ? row.bucket.replace(/_/g, ' ') : '—'}
        </span>
        {row.latency_ms > 0 ? (
          <div className="mt-0.5 font-mono text-[0.65rem] text-base-content/50">
            {row.latency_ms}ms
          </div>
        ) : null}
      </td>
      <td>
        {/*
          The remediation is the whole reason this report exists, so it is the
          largest text in the row. `detail` is the evidence behind it and stays
          quiet; an empty remediation is stated as such rather than left blank.
        */}
        <div className="os-seat-doctor-fix" data-testid="seat-doctor-remediation">
          {row.remediation || 'No fix named by this run.'}
        </div>
        {row.detail ? <div className="os-seat-doctor-detail">{row.detail}</div> : null}
      </td>
    </tr>
  )
}

export function SeatDoctorPane() {
  const headingId = useId()
  const [state, setState] = useState<SeatDoctorState>(() => seatDoctorState())
  const [filter, setFilter] = useState<FilterId>('all')
  const [kinds, setKinds] = useState<string[]>([])
  const [deep, setDeep] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  // Store subscription, not a local copy: the report outlives this pane, so
  // unmounting mid-run loses nothing and the run itself is never cancelled.
  useEffect(() => {
    // `seatDoctorState()` hands back a stable object reference, so the identity
    // check is a real "nothing changed" check. Without it every store event —
    // including a no-op emit from a sibling — would re-render this pane.
    const sync = () => {
      setState((prev) => (prev === seatDoctorState() ? prev : seatDoctorState()))
    }
    sync()
    window.addEventListener(SEAT_DOCTOR_CHANGED_EVENT, sync)
    const off = subscribeSeatDoctor(sync)
    return () => {
      window.removeEventListener(SEAT_DOCTOR_CHANGED_EVENT, sync)
      off()
    }
  }, [])

  // An honest "this is not hung" tick while a run is in flight. It counts
  // seconds off a local clock; it never re-issues the request. The effect only
  // exists while running, so an idle pane schedules nothing at all.
  useEffect(() => {
    if (state.status !== 'running') return
    const started = state.startedAt
    const tick = () => setElapsed(Math.max(0, Math.round((Date.now() - started) / 1000)))
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [state.status, state.startedAt])

  const rows = useMemo(() => (state.report?.results ?? []).filter(Boolean), [state.report])
  const summary = useMemo(() => summariseSeatDoctor(rows), [rows])
  const sorted = useMemo(() => sortSeatDoctorRows(rows), [rows])
  const visible = useMemo(
    () => (filter === 'all' ? sorted : sorted.filter((row) => seatDoctorTone(row) === filter)),
    [filter, sorted],
  )

  const running = state.status === 'running'
  const toggleKind = (kind: string) =>
    setKinds((prev) =>
      prev.includes(kind) ? prev.filter((k) => k !== kind) : [...prev, kind],
    )

  return (
    <section
      id="os-seat-doctor"
      aria-labelledby={headingId}
      className="space-y-4"
      data-testid="seat-doctor-pane"
      data-status={state.status}
    >
      <div>
        <h4 id={headingId} className="flex items-center gap-2 text-lg font-semibold">
          <Stethoscope className="h-5 w-5" aria-hidden="true" />
          Seat doctor
        </h4>
        <p className="mt-1 text-sm text-base-content/70">
          Read-only audit of every API, CLI and remote seat. It is not the rail&apos;s
          {' '}<code className="font-mono">⚠ broken</code> label — that one is cheap liveness polled
          every 60s. This is stricter: a seat is only <strong>ok</strong> when this run proved a
          real turn, so a reachable binary or a passing health check stays{' '}
          <strong>unverified</strong> and is never reported as healthy. Unverified is not broken.
        </p>
        <p className="mt-1 text-sm text-base-content/70">
          Nothing is written and nothing is polled — the run happens when you press the button,
          and it takes tens of seconds because every seat is probed with short timeouts.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Button
          type="button"
          size="sm"
          onClick={() => void runSeatDoctor({ kinds, deep })}
          loading={running}
          disabled={running}
          data-testid="seat-doctor-run"
        >
          <RefreshCw className="mr-1 h-4 w-4" aria-hidden="true" />
          {running ? 'Running…' : 'Run diagnosis'}
        </Button>

        <fieldset className="flex items-center gap-3">
          <legend className="sr-only">Filter by seat kind</legend>
          {KIND_OPTIONS.map((kind) => (
            <label key={kind} className="flex cursor-pointer items-center gap-1 text-xs">
              <input
                type="checkbox"
                className="checkbox checkbox-xs"
                checked={kinds.includes(kind)}
                onChange={() => toggleKind(kind)}
                data-testid={`seat-doctor-kind-${kind}`}
              />
              {kind}
            </label>
          ))}
        </fieldset>

        <label className="flex cursor-pointer items-center gap-1 text-xs">
          <input
            type="checkbox"
            className="checkbox checkbox-xs"
            checked={deep}
            onChange={() => setDeep((prev) => !prev)}
            data-testid="seat-doctor-deep"
          />
          deep (slower, proves turns for more seats)
        </label>
      </div>

      {/*
        Never an empty table on failure. `status === 'error'` always renders this
        block, and the table below is gated on a real report, so "no error shown"
        is the only thing that reads as all clear.
      */}
      {state.status === 'error' ? (
        <div className="space-y-2" data-testid="seat-doctor-error">
          <Alert type="error" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm">
              <strong>Seat doctor run failed.</strong> No verdict is available from this attempt, so
              nothing below is being claimed about your seats: {state.error}
            </span>
          </Alert>
          {state.report ? (
            <p className="text-xs text-base-content/60">
              The rows below are the last successful run ({clock(state.lastSuccessAt)}), not this
              one.
            </p>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void runSeatDoctor(state.query)}
            data-testid="seat-doctor-retry"
          >
            Try again
          </Button>
        </div>
      ) : null}

      {running ? (
        <div data-testid="seat-doctor-running">
          <Alert type="info" icon={<Loader2 className="h-5 w-5 animate-spin" />}>
            <span className="text-sm">
              Probing every seat with short timeouts. This is expected to take tens of seconds
              {elapsed > 0 ? ` (${elapsed}s so far)` : ''} — it is not a poll, and it will not run
              again on its own.
            </span>
          </Alert>
        </div>
      ) : null}

      {state.status === 'idle' ? (
        <div data-testid="seat-doctor-idle">
          <Alert type="info" icon={<Stethoscope className="h-5 w-5" />}>
            <span className="text-sm">
              No run yet. Nothing is known about your seats until you press Run diagnosis — that is
              deliberate, because a report nobody asked for is a report nobody reads.
            </span>
          </Alert>
        </div>
      ) : null}

      {state.report && state.status !== 'running' ? (
        <>
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
            data-testid="seat-doctor-summary"
          >
            <span>
              <span className="font-semibold">{summary.seats}</span> seats covered
            </span>
            <span data-testid="seat-doctor-total-broken">
              <span className="font-semibold">{summary.broken}</span> broken
              {summary.incomplete > 0 ? (
                <span className="text-base-content/60">
                  {' '}
                  ({summary.incomplete} not set up, {summary.broken - summary.incomplete} faulty)
                </span>
              ) : null}
            </span>
            <span data-testid="seat-doctor-total-unverified">
              <span className="font-semibold">{summary.unverified}</span> unverified
            </span>
            <span data-testid="seat-doctor-total-ok">
              <span className="font-semibold">{summary.ok}</span> proved working
            </span>
            {summary.unknown > 0 ? (
              <span data-testid="seat-doctor-total-unknown" className="text-base-content/60">
                <span className="font-semibold">{summary.unknown}</span> unrecognised verdict
              </span>
            ) : null}
            <span className="text-base-content/50">
              run {relative(state.lastSuccessAt, Date.now())}
              {state.report.deep ? ' · deep' : ''}
              {state.report.read_only ? ' · read-only' : ''}
            </span>
          </div>

          {summary.buckets.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5" aria-label="Buckets in this run" data-testid="seat-doctor-buckets">
              {summary.buckets.map((bucket) => (
                <li key={bucket.bucket}>
                  <span className="badge badge-ghost badge-sm font-mono">
                    {bucket.label} · {bucket.count}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          {/*
            A completed run that covered nothing is a finding about the roster,
            not a clean bill of health. Without this block, "0 rows" renders
            identically to "everything is fine" — the exact failure this page
            must not have.
          */}
          {summary.seats === 0 ? (
            <div data-testid="seat-doctor-empty">
              <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
                <span className="text-sm">
                  The run completed but covered <strong>0 seats</strong>. That is not an all-clear —
                  the roster could not be enumerated, so no verdict is available for anything.
                </span>
              </Alert>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-base-content/60">Show:</span>
                {FILTERS.map((option) => (
                  <Button
                    key={option.id}
                    type="button"
                    variant={filter === option.id ? 'primary' : 'ghost'}
                    size="xs"
                    onClick={() => setFilter(option.id)}
                    data-testid={`seat-doctor-filter-${option.id}`}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>

              <div className="overflow-x-auto">
                <table className="os-seat-doctor-table" data-testid="seat-doctor-table">
                  <caption className="sr-only">
                    Seat doctor findings. Columns: seat, verdict, bucket, fix.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Seat</th>
                      <th scope="col">Verdict</th>
                      <th scope="col">Bucket</th>
                      <th scope="col">Fix</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((row, index) => (
                      <SeatDoctorRowView key={`${row.kind}:${row.seat_id}:${index}`} row={row} />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      ) : null}

      <p className="flex items-start gap-1.5 text-xs text-base-content/50">
        <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>
          Credential references are shown as the variable <em>name</em> only. Values are never sent
          to this page, and an evidence field that is not a plain variable name is dropped rather
          than printed.
        </span>
      </p>
    </section>
  )
}

export default SeatDoctorPane
