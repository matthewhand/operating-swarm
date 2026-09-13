import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { ToastProvider } from '../DaisyUI'
import { markAgentUnread, UNREAD_AGENTS_STORAGE_KEY } from '../../lib/unreadAgents'
import { GENERATION_COMPLETE_EVENT } from '../../lib/railOrder'

describe('REQ-210: Unread blue dot (replaces timestamp) + Mark as unread', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/v1/blueprints')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: [
                { id: 'codey', name: 'Codey', role: 'default', rail: true },
                { id: 'stewie', name: 'Stewie', role: 'default', rail: true },
              ],
            }),
          } as Response)
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ results: [], data: [] }),
        } as Response)
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function renderRail(initialRoute = '/chat?blueprint=codey') {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    return render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={[initialRoute]}>
            <Routes>
              <Route path="/chat" element={<AgentSidebar />} />
              <Route path="/" element={<AgentSidebar />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
  }

  it('renders blue dot in place of timestamp for unread agent seat', async () => {
    markAgentUnread('stewie')

    renderRail('/chat?blueprint=codey')

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    // Find unread dots
    const unreadDots = await screen.findAllByTestId('rail-unread-dot')
    expect(unreadDots.length).toBeGreaterThan(0)

    // Verify stewie row has unread dot with group-hover/row:hidden class for Alt swap
    const stewieRow = screen.getByRole('link', { name: /stewie/i })
    const dotInStewie = stewieRow.querySelector('[data-testid="rail-unread-dot"]')
    expect(dotInStewie).toBeInTheDocument()
    expect(dotInStewie?.className).toContain('group-hover/row:hidden')
    expect(dotInStewie?.className).toContain('bg-sky-500')

    // Verify timestamp is replaced (no rail-row-timestamp inside stewie row)
    const timestampInStewie = stewieRow.querySelector('[data-testid="rail-row-timestamp"]')
    expect(timestampInStewie).toBeNull()
  })

  it('context menu provides Mark as unread and restores blue dot', async () => {
    renderRail('/chat?blueprint=codey')

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    // Initially stewie is read
    const stewieRow = screen.getByRole('link', { name: /stewie/i })
    expect(stewieRow.querySelector('[data-testid="rail-unread-dot"]')).toBeNull()

    // Right-click stewie to open context menu
    fireEvent.contextMenu(stewieRow)

    const markUnreadItem = await screen.findByRole('menuitem', { name: /mark as unread/i })
    expect(markUnreadItem).toBeInTheDocument()

    // Click Mark as unread
    act(() => {
      fireEvent.click(markUnreadItem)
    })

    // Verify blue dot is now rendered
    await waitFor(() => {
      expect(stewieRow.querySelector('[data-testid="rail-unread-dot"]')).toBeInTheDocument()
    })

    // Verify stored in localStorage
    expect(localStorage.getItem(UNREAD_AGENTS_STORAGE_KEY)).toContain('stewie')
  })

  it('keeps the unread dot when that seat is the open chat', async () => {
    markAgentUnread('codey')
    renderRail('/chat?blueprint=codey')

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const codeyRow = screen.getByRole('link', { name: /codey/i })
    expect(codeyRow.querySelector('[data-testid="rail-unread-dot"]')).toBeInTheDocument()
    expect(localStorage.getItem(UNREAD_AGENTS_STORAGE_KEY)).toContain('codey')
  })

  it('new inbound activity via generation complete sets unread on unselected agent', async () => {
    renderRail('/chat?blueprint=codey')

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const stewieRow = screen.getByRole('link', { name: /stewie/i })
    expect(stewieRow.querySelector('[data-testid="rail-unread-dot"]')).toBeNull()

    // Dispatch generation complete for stewie while codey is selected
    act(() => {
      window.dispatchEvent(
        new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'stewie' } }),
      )
    })

    await waitFor(() => {
      expect(stewieRow.querySelector('[data-testid="rail-unread-dot"]')).toBeInTheDocument()
    })
  })
})
