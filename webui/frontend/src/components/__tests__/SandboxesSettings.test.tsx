import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'

const SETTINGS_PAYLOAD = {
  provider: 'none',
  enable_sandbox_tools: false,
  timeout_seconds: 30,
  work_dir: '/tmp',
  daytona_api_key_env: '',
  daytona_api_url: '',
  dangerous_confirmed: false,
  providers: [
    { id: 'none', label: 'None', description: 'No execution tools.' },
    {
      id: 'bare_metal',
      label: 'Bare metal host',
      description: 'Direct host execution.',
      dangerous: true,
      requires: ['confirm_dangerous'],
    },
    { id: 'daytona', label: 'Daytona', description: 'Cloud microVMs.' },
  ],
  secrets: { daytona_api_key_env: null, daytona_api_url: null },
}

function fetchRoute(url: string, init?: RequestInit): Response {
  const target = String(url)
  if (target.includes('/v1/settings/sandbox/test')) {
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, provider: 'bare_metal', detail: 'ok: python 3.13.11' }),
    } as unknown as Response
  }
  if (init?.method === 'PUT') {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        ...SETTINGS_PAYLOAD,
        provider: 'bare_metal',
        dangerous_confirmed: true,
      }),
    } as unknown as Response
  }
  return {
    ok: true,
    status: 200,
    json: async () => SETTINGS_PAYLOAD,
  } as unknown as Response
}

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet isOpen={true} onClose={vi.fn()} initialSection="sandboxes" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('Sandboxes settings pane', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders provider radios with the dangerous badge and default marker', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchRoute))
    renderPane()

    const none = await screen.findByTestId('sandbox-provider-none')
    expect(none).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('sandbox-provider-bare_metal')).toBeInTheDocument()
    expect(screen.getByTestId('sandbox-dangerous-badge')).toHaveTextContent('dangerous')
    expect(screen.getByTestId('settings-sandboxes-pane')).toBeInTheDocument()
  })

  it('selects a provider, saves with dangerous confirmation, and shows probe result', async () => {
    const fetchMock = vi.fn(fetchRoute)
    vi.stubGlobal('fetch', fetchMock)
    renderPane()

    const bareMetal = await screen.findByTestId('sandbox-provider-bare_metal')
    fireEvent.click(bareMetal)

    const save = screen.getByTestId('sandbox-save')
    await waitFor(() => expect(save).not.toBeDisabled())
    fireEvent.click(save)

    await waitFor(() =>
      expect(screen.getByTestId('sandbox-save-ok')).toBeInTheDocument(),
    )
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(putCall).toBeTruthy()
    const body = JSON.parse(String(putCall?.[1]?.body))
    expect(body.provider).toBe('bare_metal')
    expect(body.confirm_dangerous).toBe(true)

    fireEvent.click(screen.getByTestId('sandbox-test'))
    const result = await screen.findByTestId('sandbox-probe-result')
    expect(result).toHaveTextContent('OK')
  })

  it('shows Daytona-only options only for the daytona provider', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchRoute))
    renderPane()

    await screen.findByTestId('sandbox-provider-none')
    expect(screen.queryByTestId('daytona-options')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('sandbox-provider-daytona'))
    expect(await screen.findByTestId('daytona-options')).toBeInTheDocument()
  })
})
