/**
 * REQ-208 / #1088 — the rail row's activity stamp.
 *
 * REQ-208 pinned a hover-swapped Alt+N hint beside the timestamp. #1088
 * removed the Alt+1..9 slot model (native tab-switch collision), so the
 * slot's only tenants now are the unread dot, the role badge, and the
 * activity timestamp. The #500 layout doctrine it established survives:
 * the slot shares the name line and nothing in it can add height.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { ToastProvider } from '../DaisyUI'

describe('REQ-208: sidepane activity stamp (#1088: Alt+N hint retired)', () => {
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
                { id: 'codey', name: 'Codey', role: 'default' },
                { id: 'stewie', name: 'Stewie', role: 'default' },
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

  it('renders no Alt+N hint anywhere in the rail (#1088 removes the slot model)', async () => {
    renderSidebar()
    await ready()
    expect(screen.queryByTestId('spill-hotkey')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/Alt\+\d|⌥\d/)
  })

  it('#500: the timestamp shares the name line and cannot add a line', async () => {
    renderSidebar()
    await ready()
    const slot = document.querySelector('[data-testid="rail-row-slot"]')
    expect(slot).toBeTruthy()
    const nameLine = slot?.parentElement
    expect(nameLine?.className).toContain('os-rail-name-line')
    const name = nameLine?.querySelector('[data-testid="rail-agent-name"]')
    expect(nameLine?.contains(slot as Node)).toBe(true)
    expect(nameLine?.contains(name as Node)).toBe(true)
    expect(slot?.className).toContain('shrink-0')
    expect(name?.className).toContain('os-rail-row-name')
  })

  it('#500: hovering a row adds and removes no element in the slot (visibility only)', async () => {
    renderSidebar()
    await ready()
    const slot = document.querySelector('[data-testid="rail-row-slot"]') as HTMLElement
    const row = slot.closest('.os-agent-row') as HTMLElement
    const before = slot.innerHTML

    fireEvent.mouseEnter(row)
    fireEvent.mouseOver(row)

    expect(slot.innerHTML).toBe(before)
    expect(row).toBeTruthy()
  })

  function renderSidebar() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/']}>
            <AgentSidebar />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
  }

  async function ready() {
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
  }
})
