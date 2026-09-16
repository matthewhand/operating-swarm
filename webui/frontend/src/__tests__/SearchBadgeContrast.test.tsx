import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import fs from 'node:fs'
import path from 'node:path'
import AgentSidebar from '../components/AgentSidebar'

describe('REQ-197: Search Ctrl-K badge transparent opacity and contrast', () => {
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

  it('verifies index.css configures transparent background for .os-rail-search__kbd', () => {
    const cssPath = path.resolve(__dirname, '../index.css')
    const css = fs.readFileSync(cssPath, 'utf-8')

    expect(css).toContain('.os-rail-search__kbd')
    expect(css).toContain('background-color: transparent !important;')
    expect(css).toContain('.os-agent-sidebar:hover .os-rail-search__kbd')
    expect(css).not.toContain('.os-rail-search:focus-within .os-rail-search__kbd')
  })

  it('renders search badge without black fill obstructing search field', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open={true} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const searchTrigger = screen.getByRole('button', { name: 'Search' })
    expect(searchTrigger).toBeInTheDocument()
    expect(searchTrigger).toHaveTextContent('Search')

    const kbd = screen.getByText(/Ctrl\+K|⌘K|Alt\+K/i)
    expect(kbd).toBeInTheDocument()
    expect(kbd).toHaveClass('os-rail-search__kbd')
    expect(kbd).toHaveClass('kbd')
  })
})
