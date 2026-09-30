/**
 * The seat doctor pane.
 *
 * Rendering contract, in the order the failure matters:
 *  1. the three verdicts are distinct, and `unverified` never gets the error tone;
 *  2. `not_configured` is "not set up", not a fault;
 *  3. a broken seat leads with its remediation;
 *  4. a failed run renders an explicit error and **no table** — an empty table
 *     would read exactly like good news, which is the whole thing to avoid;
 *  5. a run that covered zero seats says so, for the same reason;
 *  6. nothing runs until the operator asks, and no secret value reaches the DOM.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../../DaisyUI'
import { SeatDoctorPane } from '../SeatDoctorPane'
import { __setSeatDoctorFetcher, resetSeatDoctor } from '../../../../lib/seatDoctor'
import type { SeatDoctorReport, SeatDoctorRow } from '../../../../lib/api/seatDoctor'

function row(over: Partial<SeatDoctorRow> = {}): SeatDoctorRow {
  return {
    kind: 'api',
    seat_id: 'gpt-5.6-terra',
    label: 'Terra',
    origin: 'https://api.example.test/v1',
    verdict: 'broken',
    bucket: 'quota',
    detail: '402 Payment Required',
    remediation: 'top up the credit/balance behind api.example.test',
    proves: 'nothing',
    turn_proved: false,
    latency_ms: 120,
    delegates_to: [],
    evidence: {},
    ...over,
  }
}

const ROWS: SeatDoctorRow[] = [
  row({
    seat_id: 'terra',
    label: 'Terra',
    verdict: 'broken',
    bucket: 'quota',
    remediation: 'top up the credit/balance behind api.example.test',
    evidence: { api_key_env: 'OPENAI_API_KEY' },
  }),
  row({
    seat_id: 'ghost',
    label: 'Ghost',
    verdict: 'unverified',
    bucket: '',
    detail: 'binary answers --version',
    remediation: '',
    proves: 'liveness',
  }),
  row({
    seat_id: 'hermes',
    label: 'Hermes',
    verdict: 'ok',
    bucket: '',
    detail: '1-token chat call accepted',
    remediation: '',
    proves: 'turn',
    turn_proved: true,
  }),
  row({
    seat_id: 'trueforge',
    label: 'TrueForge',
    kind: 'remote',
    verdict: 'broken',
    bucket: 'not_configured',
    detail: 'never added as a remote',
    remediation: 'add trueforge in Settings → Remotes, then set its instance url',
    evidence: { api_key_env: '${TRU_EFORGE_TOKEN}' },
  }),
]

function report(results: SeatDoctorRow[]): SeatDoctorReport {
  return {
    object: 'seat_doctor_report',
    deep: false,
    read_only: true,
    totals: { seats: results.length, broken: 0, unverified: 0, ok: 0 },
    buckets: {},
    results,
  }
}

function renderPane() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <SeatDoctorPane />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function rowFor(seatId: string): HTMLElement {
  const found = screen
    .getAllByTestId('seat-doctor-row')
    .find((el) => el.getAttribute('data-seat-id') === seatId)
  if (!found) throw new Error(`no row for ${seatId}`)
  return found
}

/**
 * Press Run and wait for the run to settle — either a report landed, or the run
 * failed loudly. Either way there is a summary or an error, never nothing.
 */
async function runWith(): Promise<void> {
  fireEvent.click(screen.getByTestId('seat-doctor-run'))
  await waitFor(() => {
    const settled =
      screen.queryByTestId('seat-doctor-summary') ??
      screen.queryByTestId('seat-doctor-error')
    if (!settled) throw new Error('the run neither reported nor errored')
  })
}

describe('SeatDoctorPane', () => {
  beforeEach(() => {
    resetSeatDoctor()
    __setSeatDoctorFetcher(() => Promise.resolve(report(ROWS)))
  })

  afterEach(() => {
    // Unmount first: `resetSeatDoctor()` emits, and an emit that reaches a
    // still-mounted pane is a state update outside act(). Vitest runs this
    // hook before the auto-cleanup one, so the order has to be explicit.
    cleanup()
    resetSeatDoctor()
    __setSeatDoctorFetcher(null)
    vi.useRealTimers()
  })

  it('reports nothing at all until the operator asks — no run on mount', () => {
    renderPane()
    expect(screen.getByTestId('seat-doctor-pane')).toHaveAttribute('data-status', 'idle')
    expect(screen.getByTestId('seat-doctor-idle')).toBeInTheDocument()
    expect(screen.queryByTestId('seat-doctor-table')).not.toBeInTheDocument()
  })

  it('renders the three verdicts as three distinct states', async () => {
    renderPane()
    await runWith()

    const terra = rowFor('terra')
    const ghost = rowFor('ghost')
    const hermes = rowFor('hermes')

    expect(terra).toHaveAttribute('data-verdict', 'broken')
    expect(terra).toHaveAttribute('data-tone', 'fault')
    expect(ghost).toHaveAttribute('data-verdict', 'unverified')
    expect(ghost).toHaveAttribute('data-tone', 'unverified')
    expect(hermes).toHaveAttribute('data-verdict', 'ok')
    expect(hermes).toHaveAttribute('data-tone', 'ok')

    // The chip carries the tone, so the distinction is not colour-only.
    for (const [rowEl, tone] of [
      [terra, 'fault'],
      [ghost, 'unverified'],
      [hermes, 'ok'],
    ] as const) {
      expect(within(rowEl).getByTestId('seat-doctor-verdict')).toHaveAttribute(
        'data-tone',
        tone,
      )
    }

    // Faults lead; a diagnostic that opens on the healthy rows buries the point.
    expect(screen.getAllByTestId('seat-doctor-row').map((el) => el.getAttribute('data-seat-id'))).toEqual([
      'terra',
      'trueforge',
      'ghost',
      'hermes',
    ])
  })

  /**
   * The false-alarm case. `unverified` must not read as a fault, in tone, in
   * wording, or in the totals — an operator who sees red on every CLI seat stops
   * believing the page.
   */
  it('never paints unverified as broken', async () => {
    renderPane()
    await runWith()

    const ghost = rowFor('ghost')
    expect(ghost).toHaveAttribute('data-tone', 'unverified')
    expect(within(ghost).getByTestId('seat-doctor-verdict').textContent).toMatch(/unverified/)
    expect(within(ghost).getByTestId('seat-doctor-verdict').textContent).not.toMatch(
      /broken/i,
    )
    // The note says what is and is not known.
    expect(ghost.textContent).toMatch(/did not prove a turn/)
    // And the summary keeps the two counts apart.
    expect(within(screen.getByTestId('seat-doctor-total-unverified')).getByText('1')).toBeInTheDocument()
    expect(within(screen.getByTestId('seat-doctor-total-ok')).getByText('1')).toBeInTheDocument()
  })

  it('renders not_configured as "not set up", not as a fault', async () => {
    renderPane()
    await runWith()

    const ghost = rowFor('trueforge')
    expect(ghost).toHaveAttribute('data-verdict', 'broken')
    expect(ghost).toHaveAttribute('data-tone', 'incomplete')
    expect(ghost).not.toHaveAttribute('data-tone', 'fault')
    expect(within(ghost).getByTestId('seat-doctor-verdict').textContent).toMatch(
      /not set up/i,
    )
    // Still counted as broken — the backend is right that it cannot work — but
    // reported separately from the seats that are actually misbehaving.
    expect(screen.getByTestId('seat-doctor-total-broken').textContent).toMatch(/2 broken/)
    expect(screen.getByTestId('seat-doctor-total-broken').textContent).toMatch(
      /1 not set up, 1 faulty/,
    )
  })

  it('leads a broken row with its remediation', async () => {
    renderPane()
    await runWith()

    const terra = rowFor('terra')
    expect(within(terra).getByTestId('seat-doctor-remediation')).toHaveTextContent(
      'top up the credit/balance behind api.example.test',
    )
    const trueforge = rowFor('trueforge')
    expect(within(trueforge).getByTestId('seat-doctor-remediation')).toHaveTextContent(
      'add trueforge in Settings → Remotes, then set its instance url',
    )
  })

  /**
   * The failure this page is most likely to get wrong, and one the backend has
   * already been bitten by twice. An error must be loud, and it must not leave
   * an empty table behind it.
   */
  it('renders an explicit error and no table when the run fails', async () => {
    __setSeatDoctorFetcher(() => Promise.reject(new Error('connection refused')))
    renderPane()
    await runWith()

    const error = screen.getByTestId('seat-doctor-error')
    expect(error).toHaveTextContent(/Seat doctor run failed/i)
    expect(error).toHaveTextContent(/connection refused/)
    expect(error).toHaveTextContent(/nothing below is being claimed/i)
    expect(screen.queryByTestId('seat-doctor-table')).not.toBeInTheDocument()
    expect(screen.queryAllByTestId('seat-doctor-row')).toHaveLength(0)
    // No summary either — a zero there would read as "0 broken".
    expect(screen.queryByTestId('seat-doctor-summary')).not.toBeInTheDocument()
    expect(screen.getByTestId('seat-doctor-retry')).toBeInTheDocument()
  })

  it('re-runs on demand, and labels stale rows when that re-run fails', async () => {
    renderPane()
    await runWith()
    expect(screen.getByTestId('seat-doctor-table')).toBeInTheDocument()

    __setSeatDoctorFetcher(() => Promise.reject(new Error('gateway timeout')))
    await runWith()
    expect(screen.getByTestId('seat-doctor-error')).toHaveTextContent(/gateway timeout/)
    expect(screen.getByTestId('seat-doctor-error')).toHaveTextContent(
      /last successful run/i,
    )
    // The old rows are still there, and they are still attributed to that run.
    expect(screen.getAllByTestId('seat-doctor-row')).toHaveLength(4)
    // And the operator can try again from the error itself.
    expect(screen.getByTestId('seat-doctor-retry')).toBeInTheDocument()
  })

  it('a completed run that covered 0 seats is called out, not shown as a clean table', async () => {
    __setSeatDoctorFetcher(() => Promise.resolve(report([])))
    renderPane()
    await runWith()

    expect(screen.getByTestId('seat-doctor-empty')).toHaveTextContent(/covered/i)
    expect(screen.getByTestId('seat-doctor-empty')).toHaveTextContent(/0 seats/i)
    expect(screen.getByTestId('seat-doctor-empty')).toHaveTextContent(/not an all-clear/i)
    expect(screen.queryByTestId('seat-doctor-table')).not.toBeInTheDocument()
  })

  it('shows a running state with an honest time warning, and no table meanwhile', async () => {
    let resolve: (value: SeatDoctorReport) => void = () => {}
    __setSeatDoctorFetcher(
      () => new Promise<SeatDoctorReport>((res) => {
        resolve = res
      }),
    )
    renderPane()

    fireEvent.click(screen.getByTestId('seat-doctor-run'))
    const running = await screen.findByTestId('seat-doctor-running')
    expect(running).toHaveTextContent(/tens of seconds/i)
    expect(running).toHaveTextContent(/will not run again/i)
    expect(screen.queryByTestId('seat-doctor-table')).not.toBeInTheDocument()
    expect(screen.getByTestId('seat-doctor-run')).toBeDisabled()

    // Still no table while the audit is in flight, however long it takes.
    expect(screen.queryByTestId('seat-doctor-table')).not.toBeInTheDocument()
    expect(screen.queryByTestId('seat-doctor-error')).not.toBeInTheDocument()

    await act(async () => {
      resolve(report(ROWS))
    })
    await screen.findByTestId('seat-doctor-table')
    expect(screen.queryByTestId('seat-doctor-running')).toBeNull()
  })

  it('filters to faults without hiding that the other rows exist', async () => {
    renderPane()
    await runWith()

    fireEvent.click(screen.getByTestId('seat-doctor-filter-fault'))
    expect(screen.getAllByTestId('seat-doctor-row').map((el) => el.getAttribute('data-seat-id'))).toEqual([
      'terra',
    ])

    fireEvent.click(screen.getByTestId('seat-doctor-filter-unverified'))
    expect(screen.getAllByTestId('seat-doctor-row').map((el) => el.getAttribute('data-seat-id'))).toEqual([
      'ghost',
    ])

    fireEvent.click(screen.getByTestId('seat-doctor-filter-all'))
    expect(screen.getAllByTestId('seat-doctor-row')).toHaveLength(4)
  })

  it('passes the kind filter and deep flag through to the audit', async () => {
    const fetcher = vi.fn(() => Promise.resolve(report([])))
    __setSeatDoctorFetcher(fetcher)
    renderPane()

    fireEvent.click(screen.getByTestId('seat-doctor-kind-remote'))
    fireEvent.click(screen.getByTestId('seat-doctor-deep'))
    await runWith()

    expect(fetcher).toHaveBeenCalledWith({ kinds: ['remote'], deep: true })
  })

  it('shows a credential as its variable name only, and never a value', async () => {
    renderPane()
    await runWith()

    const trueforge = rowFor('trueforge')
    expect(trueforge.textContent).toMatch(/\$TRU_EFORGE_TOKEN/)
    expect(document.body.innerHTML).not.toMatch(/sk-[A-Za-z0-9]/)

    // A value that is not a plain variable name is dropped, not printed.
    __setSeatDoctorFetcher(() =>
      Promise.resolve(
        report([
          row({
            seat_id: 'leaky',
            label: 'Leaky',
            evidence: { api_key_env: 'sk-ant-api03-REALVALUE' },
          }),
        ]),
      ),
    )
    await runWith()
    await screen.findByTestId('seat-doctor-table')
    expect(document.body.innerHTML).not.toContain('sk-ant-api03-REALVALUE')
  })

  it('an unrecognised verdict is surfaced, not folded into ok', async () => {
    __setSeatDoctorFetcher(() =>
      Promise.resolve(report([row({ seat_id: 'weird', label: 'Weird', verdict: 'sideways' })])),
    )
    renderPane()
    await runWith()

    const weird = rowFor('weird')
    expect(weird).toHaveAttribute('data-tone', 'unknown')
    expect(weird).toHaveTextContent(/does not recognise/i)
    expect(screen.getByTestId('seat-doctor-total-unknown')).toHaveTextContent('1')
    expect(within(screen.getByTestId('seat-doctor-total-ok')).queryByText('1')).toBeNull()
  })
})
