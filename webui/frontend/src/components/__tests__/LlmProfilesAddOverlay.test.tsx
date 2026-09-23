import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'

function catalogPayload(ids: string[]) {
  return {
    object: 'llm_profiles',
    profiles: ids.map((id) => ({
      id,
      object: 'llm_profile',
      source: 'config',
      owned_by: 'openai',
    })),
    default_llm_profile: ids[0] || '',
    default_is_auto: !ids[0],
    override_per_task: false,
    task_llm_profiles: {},
    auto_picks: ids[0] ? { default: ids[0] } : {},
    warnings: [],
    routes: {},
    task_classes: ['orchestration', 'auxiliary', 'delegation'],
  }
}

function renderSheet() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet isOpen={true} onClose={vi.fn()} initialSection="llm-profiles" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('LLM profiles add overlay', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses opaque overlay chrome and keeps advanced collapsed on add', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => catalogPayload(['gpt-4o-mini']),
      } as Response),
    )
    renderSheet()
    expect(await screen.findByRole('heading', { name: 'LLM profiles' })).toBeInTheDocument()

    const sheet = screen.getByRole('dialog', { hidden: true })
    const chrome = within(sheet).getByTestId('os-overlay-chrome')
    expect(chrome).toHaveClass('bg-base-100')
    expect(chrome).toHaveClass('border')
    expect(chrome).toHaveClass('shadow-xl')
    expect(chrome.className).toMatch(/overflow/)
    expect(chrome.className).toMatch(/max-h/)

    fireEvent.click(screen.getByRole('button', { name: 'Add LLM profile' }))
    const overlay = await screen.findByTestId('llm-profile-add-overlay')
    expect(overlay).toHaveClass('bg-base-100')
    expect(overlay).toHaveClass('border')
    expect(overlay).toHaveClass('shadow-xl')
    expect(overlay.className).toMatch(/overflow-y-auto/)
    expect(overlay.className).toMatch(/max-h/)

    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByLabelText('Provider')).toBeInTheDocument()
    expect(screen.getByLabelText('Model')).toBeInTheDocument()
    expect(screen.getByLabelText('API key env')).toBeInTheDocument()
    expect(screen.getByLabelText('Base URL')).toBeInTheDocument()
    expect(screen.queryByLabelText('Temperature')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Max tokens')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Timeout (sec)')).not.toBeInTheDocument()
    expect(screen.queryByTestId('llm-profile-add-advanced')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByTestId('llm-profile-add-advanced')).toBeInTheDocument()
    expect(screen.getByLabelText('Temperature')).toBeInTheDocument()
  })

  it('persists a saved profile and round-trips it after remount', async () => {
    const stored = catalogPayload(['gpt-4o-mini'])
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/v1/config/sections/llm') && method === 'PATCH') {
        const body = JSON.parse(String(init?.body || '{}')) as {
          upsert?: Record<string, { provider?: string }>
        }
        const name = Object.keys(body.upsert || {})[0]
        if (name && !stored.profiles.some((row) => row.id === name)) {
          stored.profiles.push({
            id: name,
            object: 'llm_profile',
            source: 'config',
            owned_by: body.upsert?.[name]?.provider || 'openai',
          })
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'config_section', section: 'llm', entries: body.upsert }),
        } as Response
      }
      if (url.includes('/v1/llm-profiles')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ ...stored, profiles: [...stored.profiles] }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    const first = renderSheet()
    fireEvent.click(await screen.findByRole('button', { name: 'Add LLM profile' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'local-groq' } })
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'groq' } })
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'llama-3.1-8b' } })
    fireEvent.change(screen.getByLabelText('API key env'), { target: { value: 'GROQ_API_KEY' } })
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.groq.com/openai/v1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => {
      expect(screen.getByText('LLM profile saved')).toBeInTheDocument()
    })
    expect(
      await screen.findByRole('list', { name: 'Configured LLM profiles' }),
    ).toHaveTextContent('local-groq')

    const patchCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/v1/config/sections/llm') && call[1]?.method === 'PATCH',
    )
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      upsert: {
        'local-groq': {
          provider: 'groq',
          model: 'llama-3.1-8b',
          api_key: '${GROQ_API_KEY}',
          base_url: 'https://api.groq.com/openai/v1',
        },
      },
    })

    first.unmount()
    renderSheet()
    expect(
      await screen.findByRole('list', { name: 'Configured LLM profiles' }),
    ).toHaveTextContent('local-groq')
  })

  it('shows testing → ok with latency and hydrates the model combobox', async () => {
    let release: ((value: Response) => void) | undefined
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/v1/llm-profiles/test') && method === 'POST') {
        return pending
      }
      return {
        ok: true,
        status: 200,
        json: async () => catalogPayload(['gpt-4o-mini']),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderSheet()
    fireEvent.click(await screen.findByRole('button', { name: 'Add LLM profile' }))
    const testBtn = screen.getByRole('button', { name: 'Test connection' })
    expect(testBtn).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'http://198.51.100.30:4000/v1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    const status = await screen.findByTestId('llm-profile-probe-status')
    expect(status).toHaveAttribute('data-state', 'testing')
    expect(status).toHaveTextContent('Testing')

    release?.({
      ok: true,
      status: 200,
      json: async () => ({
        object: 'llm_profile_probe',
        ok: true,
        latency_ms: 42,
        error_class: null,
        state: 'ok',
        models: ['orchestration', 'auxiliary'],
      }),
    } as Response)

    await waitFor(() => {
      expect(status).toHaveAttribute('data-state', 'ok')
    })
    expect(status).toHaveTextContent('42ms')
    expect(status).toHaveClass('text-success')

    const options = screen.getByTestId('llm-profile-model-options')
    expect(options.querySelector('option[value="orchestration"]')).not.toBeNull()
    expect(options.querySelector('option[value="auxiliary"]')).not.toBeNull()
    const modelInput = screen.getByLabelText('Model')
    expect(modelInput).toHaveAttribute('list', options.id)
  })

  it('shows classified error hints on auth / timeout failures', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/v1/llm-profiles/test') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as { model?: string }
        if (body.model === 'dead') {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              ok: false,
              latency_ms: 8,
              error_class: 'timeout',
              hint: 'is the host up?',
              state: 'error',
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: false,
            latency_ms: 5,
            error_class: 'auth',
            hint: 'check key',
            state: 'error',
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => catalogPayload(['gpt-4o-mini']),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderSheet()
    fireEvent.click(await screen.findByRole('button', { name: 'Add LLM profile' }))
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.openai.com/v1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    const status = await screen.findByTestId('llm-profile-probe-status')
    await waitFor(() => {
      expect(status).toHaveAttribute('data-state', 'error')
    })
    expect(status).toHaveTextContent('check key')
    expect(status).toHaveClass('text-error')

    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'dead' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => {
      expect(status).toHaveTextContent('is the host up?')
    })
  })

  it('warns when the provider is reachable but the model is missing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/v1/llm-profiles/test') && (init?.method || 'GET').toUpperCase() === 'POST') {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              ok: true,
              latency_ms: 11,
              error_class: 'model_missing',
              hint: 'reachable, but that model is not on the provider',
              state: 'warn',
              models: ['orchestration'],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => catalogPayload(['gpt-4o-mini']),
        } as Response
      }),
    )

    renderSheet()
    fireEvent.click(await screen.findByRole('button', { name: 'Add LLM profile' }))
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'http://198.51.100.30:4000/v1' },
    })
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    const status = await screen.findByTestId('llm-profile-probe-status')
    await waitFor(() => {
      expect(status).toHaveAttribute('data-state', 'warn')
    })
    expect(status).toHaveTextContent(/not on the provider/)
    expect(status).toHaveClass('text-warning')
    expect(
      screen.getByTestId('llm-profile-model-options').querySelector('option[value="orchestration"]'),
    ).not.toBeNull()
  })
})
