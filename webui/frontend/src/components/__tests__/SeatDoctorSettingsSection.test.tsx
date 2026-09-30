/**
 * The seat doctor is reachable and discoverable in the settings sheet.
 *
 * A diagnostic nobody can find is the same as no diagnostic. Pinned here: the
 * pane is a first-class settings section (so `/chat?settings=seat-doctor`
 * deep-links into it), it is searchable (#572 — a new section cannot arrive
 * unsearchable), and opening it must NOT start an audit. The last one matters:
 * a mount-time run would put a 40-second audit behind every settings visit.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI'
import SettingsSheet, {
  SETTINGS_SECTIONS,
  SETTINGS_SEARCH_CONTENT,
  isSettingsSection,
  settingsDetailFromQuery,
} from '../SettingsSheet'
import { __setSeatDoctorFetcher, resetSeatDoctor } from '../../lib/seatDoctor'
import type { SeatDoctorQuery, SeatDoctorReport } from '../../lib/api/seatDoctor'

function renderSheet(section = 'seat-doctor') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <SettingsSheet
          isOpen
          onClose={() => {}}
          initialSection={settingsDetailFromQuery(section)?.section ?? null}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('seat doctor in the settings sheet', () => {
  const fetcher = vi.fn((): Promise<SeatDoctorReport> =>
    Promise.resolve({
      object: 'seat_doctor_report',
      deep: false,
      read_only: true,
      totals: { seats: 0, broken: 0, unverified: 0, ok: 0 },
      buckets: {},
      results: [],
    }),
  )

  beforeEach(() => {
    resetSeatDoctor()
    fetcher.mockClear()
    __setSeatDoctorFetcher(fetcher as unknown as (q: SeatDoctorQuery) => Promise<SeatDoctorReport>)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [], profiles: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    cleanup()
    resetSeatDoctor()
    __setSeatDoctorFetcher(null)
    vi.unstubAllGlobals()
  })

  it('is a declared section with searchable content', () => {
    expect(isSettingsSection('seat-doctor')).toBe(true)
    expect(SETTINGS_SECTIONS).toContain('seat-doctor')
    expect(SETTINGS_SEARCH_CONTENT['seat-doctor'].length).toBeGreaterThan(0)
  })

  it('deep-links to the pane without running an audit', async () => {
    renderSheet('seat-doctor')
    const pane = await screen.findByTestId('seat-doctor-pane')
    expect(pane).toHaveAttribute('data-status', 'idle')
    // The whole point: opening the section is free, and nothing is probed.
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('offers it in the nav, and running it from there works', async () => {
    renderSheet('general')
    fireEvent.click(await screen.findByRole('button', { name: 'Seat doctor' }))
    const pane = await screen.findByTestId('seat-doctor-pane')
    expect(pane).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('seat-doctor-run'))
    await screen.findByTestId('seat-doctor-summary')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('settings search finds the section by its own words', async () => {
    renderSheet('general')
    const search = screen.getByLabelText('Search settings')
    fireEvent.change(search, { target: { value: 'seat doctor' } })
    expect(await screen.findByRole('button', { name: 'Seat doctor' })).toBeInTheDocument()
  })
})
