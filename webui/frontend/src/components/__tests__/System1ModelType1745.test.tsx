/**
 * #1745 — System1 as a first-class model type.
 *
 * Three claims, one file:
 *   1. the type axis exists in the typed payload and the pure helpers;
 *   2. Settings lists a System1 gate under its own heading, badged, and keeps
 *      it out of the chat Default / per-task selects;
 *   3. no chat surface offers a gate — composer picker, AgentEditor's API
 *      override list, or the API model control.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LlmProfile } from '../../lib/api'
import { LlmProfilesPane } from '../settings/panes/LlmProfilesPane'
import LlmProfileAddForm from '../LlmProfileAddForm'
import { ToastProvider } from '../DaisyUI'
import {
  LLM_PROFILE_PROVIDERS,
  MODEL_TYPE_LABELS,
  SYSTEM1_API_KEY_ENV,
  SYSTEM1_BASE_URL_ENV,
  SYSTEM1_PROVIDER_ID,
  buildLlmProfileEntry,
  categorizerProfiles,
  chatProfiles,
  chatSelectableProfiles,
  defaultsForLlmProvider,
  isCategorizerProfile,
  normalizeModelType,
  profileModelType,
} from '../../lib/llmProfiles'
import { apiModelOptionsFromProfiles } from '../../lib/cliAgentContext'
import { buildComposerProviders, composerOptionsForProvider } from '../../lib/composerSources'

const CHAT_MODEL = { id: 'gpt-4o-mini', model: 'gpt-4o-mini' }
const SYSTEM1_MODEL = { id: 'system1-categorizer', model: 'system1-categorizer' }

function profileFixture(): LlmProfile[] {
  return [
    {
      id: 'default',
      object: 'llm_profile',
      source: 'config',
      namespace: 'api',
      owned_by: 'openai',
      model: 'gpt-4o-mini',
      model_type: 'chat',
    },
    {
      id: 'system1-filter',
      object: 'llm_profile',
      source: 'config',
      namespace: 'api',
      owned_by: SYSTEM1_PROVIDER_ID,
      model: SYSTEM1_MODEL.id,
      model_type: 'categorizer',
      base_url: `\${${SYSTEM1_BASE_URL_ENV}}`,
    },
  ]
}

function catalogPayload(overrides: Record<string, unknown> = {}) {
  return {
    object: 'llm_profiles',
    profiles: profileFixture(),
    default_llm_profile: 'default',
    default_is_auto: false,
    override_per_task: true,
    task_llm_profiles: {
      orchestration: 'default',
      auxiliary: 'default',
      delegation: 'default',
    },
    auto_picks: { default: 'default' },
    warnings: [],
    routes: {},
    task_classes: ['orchestration', 'auxiliary', 'delegation'],
    model_types: ['chat', 'categorizer'],
    ...overrides,
  }
}

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <LlmProfilesPane />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function optionValues(select: HTMLElement): string[] {
  return Array.from(select.querySelectorAll('option')).map((row) => (row as HTMLOptionElement).value)
}

describe('#1745 model type helpers', () => {
  it('normalizes System1 spellings to the categorizer type and defaults to chat', () => {
    for (const alias of ['system1', 'System1', 'system-1', 'classifier', 'gate', 'filter', 'categorizer']) {
      expect(normalizeModelType(alias)).toBe('categorizer')
    }
    for (const value of [undefined, null, '', 'chat', 'llm', 'nonsense']) {
      expect(normalizeModelType(value)).toBe('chat')
    }
  })

  it('labels both types in OpenRig-facing copy', () => {
    expect(MODEL_TYPE_LABELS.categorizer).toContain('System1')
    expect(MODEL_TYPE_LABELS.categorizer).toMatch(/categorizer|gate/i)
    expect(MODEL_TYPE_LABELS.chat).toBe('Chat LLM')
  })

  it('infers the type from the row, falling back to the vendor for old servers', () => {
    expect(profileModelType({ model_type: 'categorizer' })).toBe('categorizer')
    expect(profileModelType({ model_type: 'chat' })).toBe('chat')
    // An older server omits model_type; the System1 vendor still means gate.
    expect(profileModelType({ owned_by: SYSTEM1_PROVIDER_ID })).toBe('categorizer')
    expect(profileModelType({ owned_by: 'openai' })).toBe('chat')
    expect(profileModelType(null)).toBe('chat')
    expect(isCategorizerProfile({ owned_by: 'system1' })).toBe(true)
    expect(isCategorizerProfile(undefined)).toBe(false)
  })

  it('offers System1 as a first-class provider with env-name defaults', () => {
    expect(LLM_PROFILE_PROVIDERS).toContain(SYSTEM1_PROVIDER_ID)
    // A named env reference, never a live URL and never a key.
    expect(defaultsForLlmProvider(SYSTEM1_PROVIDER_ID)).toEqual({
      baseUrl: `\${${SYSTEM1_BASE_URL_ENV}}`,
      apiKeyEnv: SYSTEM1_API_KEY_ENV,
    })
    expect(defaultsForLlmProvider('mistral')).toEqual({
      baseUrl: 'https://api.mistral.ai/v1',
      apiKeyEnv: 'MISTRAL_API_KEY',
    })
  })

  it('writes the type and a ${ENV} credential into the persist payload', () => {
    const entry = buildLlmProfileEntry({
      provider: SYSTEM1_PROVIDER_ID,
      model: SYSTEM1_MODEL.id,
      modelType: 'categorizer',
      apiKeyEnv: SYSTEM1_API_KEY_ENV,
      baseUrl: `\${${SYSTEM1_BASE_URL_ENV}}`,
    })
    expect(entry).toEqual({
      provider: SYSTEM1_PROVIDER_ID,
      model: SYSTEM1_MODEL.id,
      model_type: 'categorizer',
      api_key: `\${${SYSTEM1_API_KEY_ENV}}`,
      base_url: `\${${SYSTEM1_BASE_URL_ENV}}`,
    })
    expect(JSON.stringify(entry)).not.toMatch(/sk-/)
    // A chat profile is recorded as chat rather than left untyped.
    expect(
      buildLlmProfileEntry({ provider: 'openai', model: CHAT_MODEL.id }).model_type,
    ).toBe('chat')
  })
})

describe('#1745 LLM profiles pane', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists System1 under its own heading, badged as a gate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => catalogPayload(),
      } as Response),
    )
    renderPane()

    const section = await screen.findByTestId('system1-categorizers')
    expect(section).toHaveTextContent('System1 categorizers')
    expect(section).toHaveTextContent('1 gate model')
    expect(section).toHaveTextContent('filter-in / filter-out seats')

    const row = (screen.getAllByTestId('system1-profile-row')[0])
    expect(row).toHaveTextContent('system1-filter')
    expect((screen.getByTestId('system1-profile-badge'))).toHaveTextContent(
      'System1 (categorizer / gate)',
    )
    // The gate is not in the chat list.
    expect(screen.getByRole('list', { name: 'Configured LLM profiles' })).not.toHaveTextContent(
      'system1-filter',
    )
    expect((screen.getByTestId('chat-profile-badge'))).toHaveTextContent('Chat LLM')
  })

  it('keeps every gate out of Default and the per-task selects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => catalogPayload(),
      } as Response),
    )
    const { container } = renderPane()
    await screen.findByTestId('system1-categorizers')

    // The Default picker and each task-class select are chat surfaces.
    const names = [
      'default-llm-profile',
      'task-llm-orchestration',
      'task-llm-auxiliary',
      'task-llm-delegation',
    ]
    const selects = names.map((name) => {
      const select = container.querySelector<HTMLSelectElement>(`select[name="${name}"]`)
      expect(select, `missing select ${name}`).not.toBeNull()
      return select as HTMLSelectElement
    })
    for (const select of selects) {
      const values = optionValues(select)
      expect(values).toContain('default')
      expect(values).not.toContain('system1-filter')
      expect(values).not.toContain(SYSTEM1_MODEL.id)
    }
  })

  it('warns instead of offering a stored default that is a gate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => catalogPayload({ default_llm_profile: 'system1-filter' }),
      } as Response),
    )
    renderPane()
    const note = await screen.findByTestId('default-is-categorizer')
    expect(note).toHaveTextContent('system1-filter')
    expect(note).toHaveTextContent('cannot be the chat default')
  })

  it('hides the System1 section entirely when no gate is registered', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => catalogPayload({ profiles: [profileFixture()[0]] }),
      } as Response),
    )
    renderPane()
    await screen.findByRole('list', { name: 'Configured LLM profiles' })
    expect(screen.queryByTestId('system1-categorizers')).not.toBeInTheDocument()
  })
})

describe('#1745 add form', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('picking the categorizer type flips the provider and the env names', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => catalogPayload(),
      } as Response),
    )
    render(
      <ToastProvider>
        <LlmProfileAddForm onCancel={vi.fn()} onSaved={vi.fn()} />
      </ToastProvider>,
    )

    const modelType = screen.getByLabelText('Model type') as HTMLSelectElement
    expect(optionValues(modelType)).toEqual(['chat', 'categorizer'])
    expect(screen.getByTestId('llm-profile-model-type-hint')).toHaveTextContent('Emits chat tokens')

    const provider = screen.getByLabelText('Provider') as HTMLSelectElement
    expect(provider.value).toBe('openai')

    fireEvent.change(modelType, { target: { value: 'categorizer' } })
    expect(provider.value).toBe(SYSTEM1_PROVIDER_ID)
    expect((screen.getByLabelText('API key env') as HTMLInputElement).value).toBe(
      SYSTEM1_API_KEY_ENV,
    )
    expect((screen.getByLabelText('Base URL') as HTMLInputElement).value).toBe(
      `\${${SYSTEM1_BASE_URL_ENV}}`,
    )
    expect(screen.getByTestId('llm-profile-model-type-hint')).toHaveTextContent('allow / deny')

    // Back to chat: the System1 vendor must not linger.
    fireEvent.change(modelType, { target: { value: 'chat' } })
    expect(provider.value).toBe('openai')
    expect((screen.getByLabelText('API key env') as HTMLInputElement).value).toBe(
      'OPENAI_API_KEY',
    )
  })

  it('picking the system1 provider marks the type as a categorizer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response),
    )
    render(
      <ToastProvider>
        <LlmProfileAddForm onCancel={vi.fn()} onSaved={vi.fn()} />
      </ToastProvider>,
    )
    const provider = screen.getByLabelText('Provider') as HTMLSelectElement
    fireEvent.change(provider, { target: { value: SYSTEM1_PROVIDER_ID } })
    expect((screen.getByLabelText('Model type') as HTMLSelectElement).value).toBe('categorizer')
  })

  it('saves a System1 gate with its type and no live credential', async () => {
    const patchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ object: 'config_section', section: 'llm', entries: {} }),
    } as Response)
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes('/v1/config/sections/llm') && (init?.method || 'GET').toUpperCase() === 'PATCH') {
        return patchMock(input, init)
      }
      return {
        ok: true,
        status: 200,
        json: async () => catalogPayload(),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <ToastProvider>
        <LlmProfileAddForm onCancel={vi.fn()} onSaved={vi.fn()} />
      </ToastProvider>,
    )
    fireEvent.change(screen.getByLabelText('Model type'), { target: { value: 'categorizer' } })
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'system1-filter' } })
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: SYSTEM1_MODEL.id } })
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => {
      expect(screen.getByText('System1 categorizer saved')).toBeInTheDocument()
    })
    const body = JSON.parse(String(patchMock.mock.calls[0]?.[1]?.body || '{}'))
    expect(body.upsert['system1-filter']).toMatchObject({
      provider: SYSTEM1_PROVIDER_ID,
      model: SYSTEM1_MODEL.id,
      model_type: 'categorizer',
      api_key: `\${${SYSTEM1_API_KEY_ENV}}`,
    })
    expect(JSON.stringify(body)).not.toMatch(/sk-/)
  })
})

describe('#1745 chat surfaces exclude gates', () => {
  it('the API model control lists chat profiles only', () => {
    const options = apiModelOptionsFromProfiles([
      { id: 'chat-model', namespace: 'api', owned_by: 'openai', model_type: 'chat', model: 'gpt-4o-mini' },
      { id: 'system1-filter', namespace: 'api', owned_by: 'system1', model_type: 'categorizer', model: SYSTEM1_MODEL.id },
    ])
    const ids = options.map((row) => row.id)
    expect(ids).toEqual(['chat-model', 'gpt-4o-mini'])
    expect(ids).not.toContain('system1-filter')
    expect(ids).not.toContain(SYSTEM1_MODEL.id)
  })

  it('an older server that omits model_type still hides a system1-vendor row', () => {
    const options = apiModelOptionsFromProfiles([
      { id: 'system1-filter', namespace: 'api', owned_by: 'system1', model: SYSTEM1_MODEL.id },
    ])
    expect(options).toEqual([])
  })

  it('the composer API provider offers no gate rows and no gate default', () => {
    const sources = {
      api: {
        profiles: [
          { id: 'default', label: 'default' },
          {
            id: 'system1-filter',
            label: 'system1-filter',
            modelType: 'categorizer',
            ownedBy: SYSTEM1_PROVIDER_ID,
          },
        ],
        defaultProfileId: 'system1-filter',
      },
    }
    const providers = buildComposerProviders(sources)
    const api = providers.find((row) => row.kind === 'api')
    expect(api).toBeDefined()
    // "Use default" must not resolve to a gate either.
    expect(api?.defaultOptionId).toBe('default')
    const options = composerOptionsForProvider(sources, api!)
    expect(options.map((row) => row.id)).toEqual(['default'])
  })

  it('the pure profile splitters agree with the surfaces', () => {
    const profiles: LlmProfile[] = [
      { id: 'default', object: 'llm_profile', source: 'config', owned_by: 'openai', model_type: 'chat' },
      { id: 'system1-filter', object: 'llm_profile', source: 'config', owned_by: SYSTEM1_PROVIDER_ID, model_type: 'categorizer' },
    ]
    expect(chatProfiles(profiles).map((row) => row.id)).toEqual(['default'])
    expect(categorizerProfiles(profiles).map((row) => row.id)).toEqual(['system1-filter'])
    expect(chatSelectableProfiles(profiles).map((row) => row.id)).toEqual(['default'])
    expect(chatSelectableProfiles(null)).toEqual([])
  })
})
