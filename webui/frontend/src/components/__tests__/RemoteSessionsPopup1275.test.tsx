/**
 * #1275 — the server flyout must mirror with the rail's dock side.
 *
 * With the sidepane docked to the right (rail-side preference, #816/#817),
 * the server button popup used to stay left-anchored (`left-0`) and spilled
 * past the viewport edge. The flyout now anchors to the popup's `align` prop:
 * `start` (left-docked rail) keeps the historical left edge; `end`
 * (right-docked rail) mirrors it so the flyout opens leftward.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RemoteSessionsPopup from '../RemoteSessionsPopup'
import AgentSidebar from '../AgentSidebar'
import { sideAwarePopupAlign } from '../../lib/railSide'

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    remotes: [],
    onOpenSettingsRemotes: vi.fn(),
    ...overrides,
  }
}

describe('#1275 server popup mirrors with the rail dock side', () => {
  it('anchors to the left (historical) when the rail is left-docked', () => {
    render(<RemoteSessionsPopup {...baseProps({ align: 'start' })} />)
    const popup = screen.getByTestId('remote-sessions-popup')
    expect(popup.className).toContain('left-0')
    expect(popup.className).not.toContain('right-0')
    expect(popup).toHaveAttribute('data-align', 'start')
  })

  it('mirrors to the right edge (opens leftward) on a right-docked rail', () => {
    render(<RemoteSessionsPopup {...baseProps({ align: 'end' })} />)
    const popup = screen.getByTestId('remote-sessions-popup')
    expect(popup.className).toContain('right-0')
    expect(popup.className).not.toContain('left-0')
    expect(popup).toHaveAttribute('data-align', 'end')
  })

  it('defaults to the left anchor when no align is supplied', () => {
    render(<RemoteSessionsPopup {...baseProps()} />)
    expect(screen.getByTestId('remote-sessions-popup').className).toContain('left-0')
  })
})

describe('#1275 sideAwarePopupAlign dock-aware anchoring rule', () => {
  it('keeps the historical start (left) edge when the rail is on the left', () => {
    expect(sideAwarePopupAlign('left')).toBe('start')
  })

  it('mirrors to the end (right) edge so the flyout opens leftward on the right', () => {
    expect(sideAwarePopupAlign('right')).toBe('end')
  })
})

describe('#1275 AgentSidebar wires the rail side into the server flyout anchor', () => {
  function renderSidebar() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open={true} onOpenSearch={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('left-docked rail opens the server popup with the historical left anchor', () => {
    localStorage.setItem('swarm_rail_side', 'left')
    renderSidebar()
    fireEvent.click(screen.getByTestId('rail-server-icon'))
    const popup = screen.getByTestId('remote-sessions-popup')
    expect(popup).toHaveAttribute('data-align', 'start')
    expect(popup.className).toContain('left-0')
    expect(popup.className).not.toContain('right-0')
  })

  it('right-docked rail mirrors the server popup to the right edge (opens leftward)', () => {
    localStorage.setItem('swarm_rail_side', 'right')
    renderSidebar()
    fireEvent.click(screen.getByTestId('rail-server-icon'))
    const popup = screen.getByTestId('remote-sessions-popup')
    expect(popup).toHaveAttribute('data-align', 'end')
    expect(popup.className).toContain('right-0')
    expect(popup.className).not.toContain('left-0')
  })
})
