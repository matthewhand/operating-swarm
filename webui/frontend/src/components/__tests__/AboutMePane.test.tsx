/**
 * #1323 — Settings → About me operator profile.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI'
import SettingsSheet from '../SettingsSheet'
import { AboutMePane } from '../settings/panes/AboutMePane'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function prefsPayload(profile: { name?: string; timezone?: string; about?: string } = {}) {
  return {
    object: 'user_preferences',
    principal: 'user:ada',
    guest: false,
    empty: false,
    favourites: [],
    hidden_agents: [],
    hostname_override: '',
    operator_profile: {
      name: profile.name ?? '',
      timezone: profile.timezone ?? '',
      about: profile.about ?? '',
    },
  }
}

describe('#1323 About me pane', () => {
  beforeEach(() => {
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    __resetUserPrefsCacheForTests()
  })

  it('loads the saved card and PATCHes operator_profile on save', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo, init?: RequestInit) => {
      const method = init?.method || 'GET'
      if (method === 'PATCH') {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          ok: true,
          status: 200,
          json: async () => prefsPayload(body.operator_profile || {}),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => prefsPayload({ name: 'Ada', timezone: 'UTC', about: 'Be brief.' }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <QueryClientProvider client={client()}>
        <ToastProvider>
          <AboutMePane />
        </ToastProvider>
      </QueryClientProvider>,
    )

    const name = await screen.findByTestId('about-me-name')
    await waitFor(() => expect(name).toHaveValue('Ada'))
    expect(screen.getByTestId('about-me-timezone')).toHaveValue('UTC')
    expect(screen.getByTestId('about-me-notes')).toHaveValue('Be brief.')

    fireEvent.change(screen.getByTestId('about-me-name'), { target: { value: 'Ada Lovelace' } })
    fireEvent.click(screen.getByTestId('about-me-save'))

    await waitFor(() => expect(screen.getByText('About me saved')).toBeInTheDocument())
    const patch = fetchMock.mock.calls.find((call) => call[1]?.method === 'PATCH')
    expect(patch).toBeTruthy()
    const sent = JSON.parse(String(patch?.[1]?.body || '{}'))
    expect(sent.operator_profile).toEqual({
      name: 'Ada Lovelace',
      timezone: 'UTC',
      about: 'Be brief.',
    })
    expect(JSON.stringify(sent)).not.toMatch(/sk-|api_key|password/)
  })

  it('keeps Save disabled when the profile GET fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(
      <QueryClientProvider client={client()}>
        <ToastProvider>
          <AboutMePane />
        </ToastProvider>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('About me unavailable')).toBeInTheDocument()
    expect(screen.getByTestId('about-me-save')).toBeDisabled()
  })

  it('SettingsSheet lists About me and opens the pane', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => prefsPayload(),
      } as Response),
    )
    render(
      <QueryClientProvider client={client()}>
        <ToastProvider>
          <SettingsSheet isOpen={true} onClose={() => {}} initialSection="about-me" />
        </ToastProvider>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('button', { name: 'About me' })).toBeInTheDocument()
    expect(await screen.findByTestId('about-me-pane')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'About me' })).toBeInTheDocument()
  })
})
