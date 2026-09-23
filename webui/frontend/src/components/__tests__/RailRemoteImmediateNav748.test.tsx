/**
 * #748 — clicking a session-capable remote row (Letta/Slack/AnythingLLM/Open
 * WebUI) must behave like every other rail row: navigate to chat immediately,
 * defaulting to the most recent session. The old async list → attached popup
 * flow stalled the row behind a network round trip and an extra click.
 *
 * The session *switcher* affordance remains available in the chat header —
 * the rail row is a launch surface, not a session browser.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentSidebar from '../AgentSidebar'

const LETTA_REMOTE = {
  id: 'letta',
  kind: 'letta',
  title: 'Letta',
  base_url: 'http://127.0.0.1:8283',
  configured: true,
  capabilities: { sessions: true },
  agents: [],
}

let lastLocation = ''
function LocationProbe() {
  const location = useLocation()
  lastLocation = location.pathname + location.search
  return null
}

function renderSidebar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open={true} onOpenSearch={vi.fn()} />
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function lettaRow(): HTMLElement {
  // eslint-disable-next-line testing-library/no-node-access -- the row is only addressable by its data attributes
  const row = screen.getByText('Letta').closest('[data-kind="remote"]')
  expect(row).not.toBeNull()
  return row as HTMLElement
}

describe('#748 remote rows navigate immediately', () => {
  beforeEach(() => {
    localStorage.clear()
    lastLocation = ''
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [LETTA_REMOTE] }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('navigates straight to the remote chat on click — no picker stall', async () => {
    renderSidebar()
    await screen.findByText('Letta')
    fireEvent.click(lettaRow())
    await waitFor(() => {
      expect(lastLocation).toContain('remote=letta')
    })
  })

  it('does not open the sessions popup for the plain row click', async () => {
    renderSidebar()
    await screen.findByText('Letta')
    fireEvent.click(lettaRow())
    await waitFor(() => {
      expect(lastLocation).toContain('remote=letta')
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByTestId('remote-sessions-popup')).not.toBeInTheDocument()
  })
})
