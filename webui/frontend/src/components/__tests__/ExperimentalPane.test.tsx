import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI'
import SettingsSheet from '../SettingsSheet'
import { ExperimentalPane } from '../settings/panes/ExperimentalPane'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function prefsPayload(values: Record<string, unknown> = {}, empty = false) {
  return {
    object: 'user_preferences',
    principal: 'session:test',
    guest: true,
    empty,
    favourites: [],
    hidden_agents: [],
    hostname_override: '',
    values,
  }
}

function stubFetch(prefs: Record<string, unknown> = {}) {
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/v1/preferences/')) return jsonResponse(prefsPayload(prefs))
    return jsonResponse({ object: 'list', data: [] })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ExperimentalPane />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1230 Experimental settings pane', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  it('renders a toggle card per catalogue feature, MVP-off by default', () => {
    renderPane()
    expect(screen.getByTestId('experimental-pane')).toBeInTheDocument()
    const openai = screen.getByTestId('experimental-toggle-openai_agents')
    expect(openai).not.toBeChecked()
    expect(screen.getByTestId('experimental-toggle-daytona')).not.toBeChecked()
    expect(screen.getByTestId('experimental-toggle-robot3d')).not.toBeChecked()
    // The pre-existing chat-message-actions experiment ships on for review.
    expect(screen.getByTestId('experimental-toggle-chat_message_actions')).toBeChecked()
  })

  it('persists a toggle to localStorage and the prefs values bag', async () => {
    const fetchMock = stubFetch()
    renderPane()
    const toggle = screen.getByTestId('experimental-toggle-daytona')
    fireEvent.click(toggle)

    expect(localStorage.getItem('swarm_experimental_daytona')).toBe('on')
    expect(toggle).toBeChecked()

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        (call) =>
          String(call[0]).includes('/v1/preferences/') &&
          (call[1] as RequestInit | undefined)?.method === 'PATCH',
      )
      expect(patch).toBeTruthy()
      const body = JSON.parse(String((patch?.[1] as RequestInit).body || '{}'))
      expect(body.values.experimental_flags.daytona).toBe(true)
    })
  })

  it('round-trips the composer rewrite experiment through its real storage key', () => {
    stubFetch()
    renderPane()
    const toggle = screen.getByTestId('experimental-toggle-prompt_rewrite')
    expect(toggle).not.toBeChecked()
    fireEvent.click(toggle)
    expect(localStorage.getItem('swarm_composer_rewrite_enabled')).toBe('true')
    expect(toggle).toBeChecked()
  })

  it('hydrates enabled flags from the server prefs bag', async () => {
    stubFetch({ experimental_flags: { robot3d: true } })
    renderPane()
    await waitFor(() => {
      expect(screen.getByTestId('experimental-toggle-robot3d')).toBeChecked()
    })
    expect(localStorage.getItem('swarm_experimental_robot3d')).toBe('on')
  })
})

describe('#1230 Experimental tab in SettingsSheet', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  it('renders the Experimental nav entry and opens the pane', async () => {
    stubFetch()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <SettingsSheet isOpen onClose={vi.fn()} initialSection="experimental" />
        </ToastProvider>
      </QueryClientProvider>,
    )
    expect(screen.getByTestId('experimental-pane')).toBeInTheDocument()
    const navButton = screen.getByRole('button', { name: 'Experimental' })
    fireEvent.click(navButton)
    expect(screen.getByTestId('experimental-pane')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Experimental' })).toBeInTheDocument()
  })
})
