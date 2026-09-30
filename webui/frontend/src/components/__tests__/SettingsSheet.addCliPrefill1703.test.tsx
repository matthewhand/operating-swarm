/**
 * #1703 — the host-CLI tip's "Add provider" deep link, all the way through the
 * real SettingsSheet. The tip hands `addCliName`; the sheet must route to
 * Settings → CLI agents and open the add form already filled for that CLI, so
 * the operator's next click is Save rather than a hunt for the right form.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

const CATALOG = {
  clis: ['claude', 'codex', 'opencode'],
  known: ['claude', 'codex', 'opencode'],
  configured: [],
  discovered: ['opencode'],
  installed: ['opencode'],
  paths: { opencode: '/usr/local/bin/opencode' },
  suggestions: { opencode: { cmd: ['opencode', '-p', '{prompt}'] } },
  native_consensus: {},
  catalog: { opencode: { cmd: ['opencode', '-p', '{prompt}'] } },
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      const json = (body: unknown) =>
        ({ ok: true, status: 200, json: async () => body }) as Response
      if (url.includes('/v1/config/sections/cli_agents')) {
        return json({ object: 'config_section', data: {} })
      }
      if (url.includes('/v1/cli-agents')) return json(CATALOG)
      if (url.includes('/v1/rate-limits')) {
        return json({ object: 'provider_rate_limits', data: [] })
      }
      if (url.includes('/v1/preferences')) {
        return json({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
          hostname_override: '',
          values: {},
        })
      }
      return json({ object: 'blueprint_list', data: [] })
    }),
  )
}

function renderSheet(props: { initialAddCliName?: string | null; initialSection?: string | null }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet
          isOpen
          onClose={() => {}}
          initialAddCliName={props.initialAddCliName ?? null}
          initialSection={(props.initialSection ?? null) as never}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  __resetUserPrefsCacheForTests()
})

describe('SettingsSheet #1703 add-CLI prefill', () => {
  it('routes to CLI agents and prefills the add form for the detected CLI', async () => {
    stubFetch()
    renderSheet({ initialAddCliName: 'opencode' })

    const nameInput = (await screen.findByLabelText(/^Name/i)) as HTMLInputElement
    await waitFor(() => {
      expect(nameInput.value).toBe('opencode')
    })
    expect((screen.getByLabelText(/Command/i) as HTMLInputElement).value).toBe(
      'opencode -p {prompt}',
    )
    expect(screen.getByRole('button', { name: 'Save CLI agent' })).toBeInTheDocument()
  })

  it('still honours an explicit section alongside the prefill', async () => {
    stubFetch()
    renderSheet({ initialAddCliName: 'opencode', initialSection: 'remotes' })
    // remotes wins the routing decision, so the add form is not the landing view.
    await waitFor(() => {
      expect(screen.queryByLabelText(/^Name/i)).not.toBeInTheDocument()
    })
  })

  it('does not open the add form when the tip hands no CLI', async () => {
    stubFetch()
    // The plain "Settings → CLI agents" deep link, with no detected name.
    renderSheet({ initialSection: 'cli-agents' })
    await waitFor(() => {
      expect(screen.getByTestId('cli-row-opencode')).toBeInTheDocument()
    })
    expect(screen.queryByLabelText(/^Name/i)).not.toBeInTheDocument()
  })
})
