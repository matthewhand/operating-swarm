import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentSidebar from '../AgentSidebar'

describe('BUG #703: Collapsed rail search icon click opens Search palette', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('clicking the magnifying glass icon in expanded rail opens search palette', () => {
    const onOpenSearch = vi.fn()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open={true} onOpenSearch={onOpenSearch} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const searchIcon = screen.getByTestId('rail-search-icon')
    fireEvent.click(searchIcon)
    expect(onOpenSearch).toHaveBeenCalledTimes(1)
  })

  it('clicking search trigger in collapsed/avatar-only rail opens search palette', () => {
    // Set rail width to avatar-only threshold (e.g. 68px)
    localStorage.setItem('swarm_rail_width', '68')
    const onOpenSearch = vi.fn()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open={true} onOpenSearch={onOpenSearch} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const trigger = screen.getByTestId('rail-search-trigger')
    expect(trigger.tagName).toBe('BUTTON')
    expect(trigger).toHaveAttribute('aria-label', 'Search')
    expect(trigger).not.toHaveAttribute('tabindex', '-1')

    const searchIcon = screen.getByTestId('rail-search-icon')
    fireEvent.click(searchIcon)
    expect(onOpenSearch).toHaveBeenCalledTimes(1)

    // Also verify pressing Enter on the trigger opens search palette
    fireEvent.keyDown(trigger, { key: 'Enter' })
    expect(onOpenSearch).toHaveBeenCalledTimes(2)
  })
})
