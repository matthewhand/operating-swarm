/**
 * #1041 — the unauthenticated chat load must not flood /v1/preferences/.
 *
 * The regression: AgentSidebar's prefs-save effect depended on
 * resolvedHiddenIds, which reconcileHiddenAgentIds() rebuilds with a fresh
 * array identity every render, and each PATCH response was echoed back via
 * applyPrefsToLocal() → state churn → effect refires. Net effect: ~2.4
 * identical favourites PATCHes per second, blowing the 60/min anon throttle
 * in ~22 seconds of idling on the chat page.
 *
 * Contract: an unauthenticated mount issues ONE preferences GET and ZERO
 * spontaneous PATCHes; a PATCH only ever follows a real local edit.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPage from '../../pages/ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

type Method = 'GET' | 'PATCH'

const calls: { method: Method; url: string }[] = []

function installFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = ((init?.method as Method) || 'GET').toUpperCase()
      calls.push({ method, url })
      if (url.includes('/v1/preferences')) {
        return new Response(
          JSON.stringify({ empty: true }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
}

function mount() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/chat']}>
        <ToastProvider>
          <ChatPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('#1041 preferences flood guard', () => {
  beforeEach(() => {
    calls.length = 0
    __resetUserPrefsCacheForTests()
    installFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('mounts with one GET and no spontaneous PATCHes', async () => {
    mount()
    await waitFor(
      () => {
        expect(screen.getAllByText(/support/i).length).toBeGreaterThan(0)
      },
      { timeout: 5_000 },
    )
    // let every debounced save timer (300ms) and settle effects fire
    await new Promise((r) => setTimeout(r, 1_200))

    const prefs = calls.filter((c) => c.url.includes('/v1/preferences'))
    const gets = prefs.filter((c) => c.method === 'GET').length
    const patches = prefs.filter((c) => c.method === 'PATCH').length
    expect(gets).toBe(1)
    expect(patches).toBe(0)
  })

  it('a real local edit still PATCHes exactly once', async () => {
    const { container } = mount()
    await waitFor(
      () => {
        expect(screen.getAllByText(/support/i).length).toBeGreaterThan(0)
      },
      { timeout: 5_000 },
    )
    // Simulate the sidebar's canonical save path with changed content.
    const { saveUserPrefs } = await import('../../lib/userPrefs')
    await saveUserPrefs({
      favourites: [{ id: 'support', name: 'Support' }],
      hidden_agents: [],
    })
    const patches = calls.filter(
      (c) => c.url.includes('/v1/preferences') && c.method === 'PATCH',
    )
    expect(patches.length).toBe(1)
    void container
  })
})
