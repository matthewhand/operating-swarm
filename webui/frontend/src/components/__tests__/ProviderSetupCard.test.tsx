/**
 * #894 — in-chat interactive provider setup card.
 *
 * Contracts:
 * - The `swarm-provider-setup` fence is split out of the prose and renders
 *   the interactive card; malformed/foreign fences degrade to plain text.
 * - The card offers cloud + local presets, prefilled base URL / model /
 *   env-var hint, and updates its fields on preset switch.
 * - "Test connection" probes without persisting and surfaces ok/error.
 * - "Save & upgrade Admin bot" persists the profile and flips the card to
 *   its Answered state (✓ Connected · model), disabling inputs.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProviderSetupCard from '../ProviderSetupCard'
import { parseProviderSetupFence, PROVIDER_PRESETS } from '../../lib/providerSetupCard'
import { ToastProvider } from '../DaisyUI'

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return {
    ...actual,
    testLlmProfile: vi.fn(async () => ({ ok: true, latency_ms: 142, error_class: null })),
    upsertLlmProfile: vi.fn(async () => ({ object: 'llm_profiles' as const, default: 'openai', profiles: [] })),
  }
})

function renderCard(spec = { type: 'provider_setup' as const, defaultProvider: 'openai' }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ProviderSetupCard spec={spec} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#894 — provider setup card parsing', () => {
  it('parses the fence into a card and strips it from the prose', () => {
    const text = 'Let’s wire you up.\n\n```swarm-provider-setup\n{"type": "provider_setup", "default_provider": "ollama"}\n```\n\nPick a provider below.'
    const { prose, card } = parseProviderSetupFence(text)
    expect(card).toEqual({ type: 'provider_setup', defaultProvider: 'ollama' })
    expect(prose).toContain('Let’s wire you up.')
    expect(prose).toContain('Pick a provider below.')
    expect(prose).not.toContain('swarm-provider-setup')
  })

  it('malformed or foreign fences degrade to plain text', () => {
    expect(parseProviderSetupFence('```swarm-provider-setup\n{not json}\n```').card).toBeNull()
    expect(
      parseProviderSetupFence('```swarm-provider-setup\n{"type": "other"}\n```').card,
    ).toBeNull()
    const untouched = parseProviderSetupFence('```swarm-provider-setup\n{"type": "other"}\n```')
    expect(untouched.prose).toContain('swarm-provider-setup')
  })

  it('ships cloud and local presets with env hints', () => {
    const cloud = PROVIDER_PRESETS.filter((row) => row.group === 'cloud').map((row) => row.id)
    const local = PROVIDER_PRESETS.filter((row) => row.group === 'local').map((row) => row.id)
    expect(cloud).toContain('openai')
    expect(cloud).toContain('anthropic')
    expect(local).toContain('ollama')
    expect(local).toContain('lmstudio')
    const ollama = PROVIDER_PRESETS.find((row) => row.id === 'ollama')
    expect(ollama?.baseUrl).toContain('11434')
    expect(ollama?.needsKey).toBe(false)
  })
})

describe('#894 — provider setup card interaction', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders presets and prefilled fields; preset switch updates them', () => {
    renderCard()
    expect(screen.getByRole('radio', { name: 'OpenAI' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText(/OpenAI API key/i)).toBeInTheDocument()
    expect(screen.getByText(/Stored as OPENAI_API_KEY/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: 'Ollama' }))
    expect((screen.getByLabelText(/Base URL/i) as HTMLInputElement).value).toContain('11434')
    expect((screen.getByLabelText(/Default model/i) as HTMLInputElement).value).toBe('llama3.1:8b')
    expect(screen.getByText(/Not required for Ollama/)).toBeInTheDocument()
  })

  it('test connection probes without persisting and reports success', async () => {
    const { testLlmProfile } = await import('../../lib/api')
    renderCard()
    fireEvent.click(screen.getByTestId('provider-setup-test'))
    await waitFor(() => {
      expect(screen.getByTestId('provider-setup-probe-ok')).toHaveTextContent(/Connected · 142ms/)
    })
    expect(testLlmProfile).toHaveBeenCalledTimes(1)
    expect(vi.mocked(await import('../../lib/api')).upsertLlmProfile).not.toHaveBeenCalled()
  })

  it('save persists the profile and flips the card to Answered', async () => {
    const { upsertLlmProfile } = await import('../../lib/api')
    renderCard()
    fireEvent.change(screen.getByLabelText(/OpenAI API key/i), { target: { value: 'sk-test' } })
    fireEvent.click(screen.getByTestId('provider-setup-save'))
    await waitFor(() => {
      expect(screen.getByTestId('provider-setup-configured')).toHaveTextContent(
        /✓ Connected to OpenAI · gpt-4o/,
      )
    })
    expect(upsertLlmProfile).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'openai', model: 'gpt-4o', api_key: 'sk-test', set_default: true }),
    )
    // The Answered state replaces the whole form — no editable fields remain.
    expect(screen.queryByLabelText(/Base URL/i)).toBeNull()
    expect(screen.queryByTestId('provider-setup-save')).toBeNull()
  })

  it('a failed probe surfaces the error hint and save still works after retry', async () => {
    const api = await import('../../lib/api')
    vi.mocked(api.testLlmProfile).mockResolvedValueOnce({
      ok: false,
      latency_ms: 30,
      error_class: 'auth',
      hint: 'Key rejected by provider.',
    })
    renderCard()
    fireEvent.click(screen.getByTestId('provider-setup-test'))
    await waitFor(() => {
      expect(screen.getByTestId('provider-setup-probe-error')).toHaveTextContent(/Key rejected/)
    })
    fireEvent.click(screen.getByTestId('provider-setup-save'))
    await waitFor(() => {
      expect(screen.getByTestId('provider-setup-configured')).toBeInTheDocument()
    })
  })
})
