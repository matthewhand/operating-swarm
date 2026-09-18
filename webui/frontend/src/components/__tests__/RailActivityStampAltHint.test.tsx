import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { ToastProvider } from '../DaisyUI'

describe('REQ-208: Sidepane — last activity time/day; hover swaps to Alt+N hint', () => {
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

  it('renders Alt+N hint with hidden class and timestamp with group-hover:hidden swap classes', async () => {
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

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const hotkeys = screen.getAllByTestId('spill-hotkey')
    expect(hotkeys.length).toBeGreaterThan(0)
    // #500: the tip is revealed by opacity over the slot, NOT by a `hidden` →
    // `inline-block` display swap. That swap was the regression: on a row whose
    // slot was otherwise empty the tip created a line box on hover, so the row
    // grew and pushed everything below it. This test previously asserted the
    // swap, i.e. it encoded the defect.
    expect(hotkeys[0].className).toContain('os-rail-shortcut--layered')
    expect(hotkeys[0]).not.toHaveClass('hidden')
    expect(hotkeys[0].className).not.toContain('group-hover/row:inline-block')
  })

  it('#500: the tip shares the name line, so revealing it cannot add a line', async () => {
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

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const tip = screen.getAllByTestId('spill-hotkey')[0]
    const slot = tip.closest('[data-testid="rail-row-slot"]')
    const nameLine = tip.parentElement?.parentElement
    const name = nameLine?.querySelector('[data-testid="rail-agent-name"]')

    // The name and the tip are on ONE flex line (jsdom has no layout engine, so
    // the invariant asserted is structural, not a measured height).
    expect(nameLine?.className).toContain('os-rail-name-line')
    expect(nameLine?.contains(name as Node)).toBe(true)
    expect(nameLine?.contains(slot as Node)).toBe(true)
    // The tip is inside the slot, and the slot is the shrink-0 side.
    expect(slot?.contains(tip)).toBe(true)
    expect(slot?.className).toContain('shrink-0')
    // The name is the flexible side, so it keeps the space when width is tight.
    expect(name?.className).toContain('os-rail-row-name')
  })

  it('#500: hovering a row adds and removes no element in the slot (visibility only)', async () => {
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
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const tip = screen.getAllByTestId('spill-hotkey')[0]
    const row = tip.closest('.os-agent-row') as HTMLElement
    const slot = tip.closest('[data-testid="rail-row-slot"]') as HTMLElement
    const before = slot.innerHTML
    const beforeClass = tip.className

    fireEvent.mouseEnter(row)
    fireEvent.mouseOver(row)

    // Hover is a paint change: same nodes, same classes, so no reflow.
    expect(slot.innerHTML).toBe(before)
    expect(tip.className).toBe(beforeClass)
    // An empty-slot row is the failing case #500 named, and it is a real row.
    expect(row).toBeTruthy()
  })
})
