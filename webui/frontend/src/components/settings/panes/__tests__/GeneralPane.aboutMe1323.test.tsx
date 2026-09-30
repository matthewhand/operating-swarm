/**
 * #1323 — General pane About me textarea saves, reloads, and clears.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../../DaisyUI'
import { GeneralPane } from '../GeneralPane'
import { __resetUserPrefsCacheForTests } from '../../../../lib/userPrefs'

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function prefsPayload(aboutMe = '') {
  return {
    object: 'user_preferences',
    principal: 'user:ada',
    guest: false,
    empty: false,
    favourites: [],
    hidden_agents: [],
    hostname_override: '',
    about_me: aboutMe,
  }
}

function renderPane() {
  return render(
    <QueryClientProvider client={client()}>
      <ToastProvider>
        <GeneralPane
          autoCompressPct={80}
          onAutoCompressPct={() => {}}
          contextStrategy="compress"
          onContextStrategy={() => {}}
          cullTriggerPct={90}
          onCullTriggerPct={() => {}}
          cullFractionPct={50}
          onCullFractionPct={() => {}}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1323 General About me', () => {
  beforeEach(() => {
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    __resetUserPrefsCacheForTests()
  })

  it('loads the saved note, PATCHes about_me, and clears it', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo, init?: RequestInit) => {
      const method = init?.method || 'GET'
      if (method === 'PATCH') {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          ok: true,
          status: 200,
          json: async () => prefsPayload(body.about_me || ''),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => prefsPayload('Works nights.'),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPane()

    const input = await screen.findByTestId('about-me-instructions-input')
    await waitFor(() => expect(input).toHaveValue('Works nights.'))

    fireEvent.change(input, { target: { value: 'Prefers terse answers.' } })
    fireEvent.click(screen.getByTestId('about-me-instructions-save'))
    await waitFor(() => expect(screen.getByText('About me saved')).toBeInTheDocument())

    const save = fetchMock.mock.calls.find((call) => {
      const body = JSON.parse(String(call[1]?.body || '{}'))
      return call[1]?.method === 'PATCH' && body.about_me === 'Prefers terse answers.'
    })
    expect(save).toBeTruthy()

    fireEvent.click(screen.getByTestId('about-me-instructions-clear'))
    await waitFor(() => expect(screen.getByText('About me cleared')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByTestId('about-me-instructions-input')).toHaveValue(''))
    const cleared = fetchMock.mock.calls.find((call) => {
      const body = JSON.parse(String(call[1]?.body || '{}'))
      return call[1]?.method === 'PATCH' && body.about_me === ''
    })
    expect(cleared).toBeTruthy()
  })

  it('does not save secret-looking notes', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => prefsPayload(''),
    }) as Response)
    vi.stubGlobal('fetch', fetchMock)

    renderPane()
    const input = await screen.findByTestId('about-me-instructions-input')
    await waitFor(() => expect(screen.getByTestId('about-me-instructions-save')).toBeEnabled())
    fireEvent.change(input, { target: { value: 'password=hunter2' } })
    fireEvent.click(screen.getByTestId('about-me-instructions-save'))
    await waitFor(() => expect(screen.getByText('About me not saved')).toBeInTheDocument())
    const leaked = fetchMock.mock.calls.some((call) => {
      if (call[1]?.method !== 'PATCH') return false
      return String(call[1]?.body || '').includes('hunter2')
    })
    expect(leaked).toBe(false)
  })
})
