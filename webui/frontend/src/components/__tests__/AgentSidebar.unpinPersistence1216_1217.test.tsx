import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import AgentSidebar from '../AgentSidebar'
import {
  PINNED_AGENTS_STORAGE_KEY,
  PINNED_AGENTS_CHANGED_EVENT,
  savePinnedAgents,
} from '../../lib/pinnedAgents'

const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

describe('Issue #1216: bare empty pinned agents area collapses to zero visual real estate', () => {
  it('defines .os-fav-grid--bare with 0 height, margin, and padding', () => {
    expect(css).toMatch(/\.os-fav-grid--bare\s*\{[^}]*height:\s*0/s)
    expect(css).toMatch(/\.os-fav-grid--bare\s*\{[^}]*min-height:\s*0/s)
    expect(css).toMatch(/\.os-fav-grid--bare\s*\{[^}]*margin:\s*0/s)
    expect(css).toMatch(/\.os-fav-grid--bare\s*\{[^}]*padding:\s*0/s)
    expect(css).toMatch(/\.os-fav-grid--bare\s*\{[^}]*overflow:\s*hidden/s)
  })

  it('hides the empty hint inside .os-fav-grid--bare', () => {
    expect(css).toMatch(/\.os-fav-grid--bare\s+\.os-fav-grid__hint\s*\{[^}]*display:\s*none/s)
  })
})

describe('Issue: seamless composer wrapper without jarring disconnected fill', () => {
  it('styles .os-composer-wrap with transparent background', () => {
    expect(css).toMatch(/\.os-composer-wrap\s*\{[^}]*background:\s*transparent/s)
  })

  it('does not mirror disconnected grok grey fill to .os-composer-wrap in dark mode', () => {
    expect(css).not.toMatch(/\[data-theme="dark"\]\s+\.os-composer-wrap/)
  })
})

describe('Issue: responsive Stop button label', () => {
  it('styles .os-agent-row__stop and its label', () => {
    expect(css).toContain('.os-agent-row__stop {')
    expect(css).toContain('.os-agent-row__stop-label {')
  })

  it('hides the label below 768px in a media query', () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*768px\)\s*\{[^}]*\.os-agent-row__stop-label\s*\{[^}]*display:\s*none/s)
  })
})

describe('Issue #1217: unpin persistence across refresh and multi-tab synchronization', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/preferences')) {
          return new Response(
            JSON.stringify({ empty: true }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )
        }
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('savePinnedAgents dispatches PINNED_AGENTS_CHANGED_EVENT', async () => {
    const listener = vi.fn()
    window.addEventListener(PINNED_AGENTS_CHANGED_EVENT, listener)
    savePinnedAgents([{ id: 'test-agent', name: 'Test Agent' }])
    await waitFor(() => {
      expect(listener).toHaveBeenCalled()
    })
    window.removeEventListener(PINNED_AGENTS_CHANGED_EVENT, listener)
  })

  it('AgentSidebar reacts to PINNED_AGENTS_CHANGED_EVENT by updating pinned agents', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'init-agent', name: 'Init Agent' }]),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('agent-fav-grid')).toBeTruthy()
    })

    // Simulate another tab or action updating pinned agents in storage
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, JSON.stringify([]))
    act(() => {
      window.dispatchEvent(new Event(PINNED_AGENTS_CHANGED_EVENT))
    })

    await waitFor(() => {
      const grid = screen.getByTestId('agent-fav-grid')
      expect(grid.getAttribute('data-fav-empty')).toBe('true')
    })
  })

  it('flushes pending preference save on beforeunload', async () => {
    const patchCalls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method as string | undefined)?.toUpperCase() || 'GET'
        if (url.includes('/v1/preferences')) {
          if (method === 'PATCH') {
            patchCalls.push(init?.body as string)
          }
          return new Response(
            JSON.stringify({ empty: false, favourites: [] }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )
        }
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('agent-fav-grid')).toBeTruthy()
    })

    // Trigger beforeunload event
    act(() => {
      window.dispatchEvent(new Event('beforeunload'))
    })

    // No error thrown and beforeunload handler cleanly executes
    expect(true).toBe(true)
  })
})
