/**
 * Provider-namespace isolation at the component surfaces.
 *
 * Every model/provider picker must source its options from the namespace of
 * the selected provider:
 *   - API/blueprint seats → LLM profiles (`apiModelOptionsFromProfiles`)
 *   - CLI seats          → that CLI's own probe only (`cliModelOptionsFor`)
 *   - remote/team        → their own agents/targets
 *
 * A CLI picker must never contain an API profile id (e.g.
 * `litellm/orchestration`); an API picker must never contain a CLI model id.
 * Switching provider kind must switch — never carry — the option source.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { createElement, type ComponentType } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import AgentEditor from '../AgentEditor'
import AgentConfigSidepane from '../AgentConfigSidepane'
import ComposerPickerDialog from '../ComposerPickerDialog'
import NavbarRoutingPicker from '../NavbarRoutingPicker'
import AddAgentWizard from '../AddAgentWizard'
import { ToastProvider } from '../DaisyUI'
import { AGENT_EDITS_KEY } from '../../lib/agentEdits'
import type { ComposerProviderOption } from '../../lib/composerPicker'
import { buildComposerProviders, composerOptionsForProvider } from '../../lib/composerSources'
import { renderRoutingPickerImpl } from '../../features/chat/renderRoutingPicker'
import * as api from '../../lib/api'

const API_PROFILE_ID = 'litellm/orchestration'
const CLI_MODEL_ID = 'codex-only-model'

function openAgentEditorTab(name: string | RegExp) {
  fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name }))
}

function renderEditor(agentId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={() => {}} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  localStorage.removeItem(AGENT_EDITS_KEY)
  vi.unstubAllGlobals()
})

describe('AgentEditor — API seat never lists CLI model ids', () => {
  it('sources the API model control from profiles only', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/llm-profiles/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'llm_profiles',
              profiles: [{ id: 'orchestration', name: 'User chat', model: API_PROFILE_ID }],
              default_llm_profile: 'orchestration',
              task_llm_profiles: {},
            }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/codex/models/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ cli: 'codex', models: [CLI_MODEL_ID] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ clis: ['codex'], native_consensus: {}, catalog: {} }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }),
    )

    renderEditor('codey')
    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    openAgentEditorTab(/Advanced/i)

    const modelSelect = await within(dialog).findByRole('combobox', { name: 'Model override' })
    await waitFor(() => {
      expect(
        within(modelSelect).getByRole('option', { name: API_PROFILE_ID }),
      ).toBeInTheDocument()
    })
    // A CLI model id is a different namespace and must never appear here.
    expect(
      within(modelSelect).queryByRole('option', { name: CLI_MODEL_ID }),
    ).not.toBeInTheDocument()
  })
})

describe('AgentEditor — switching CLI switches the model source (no stale carry-over)', () => {
  it('reloads models for the newly selected CLI and drops the previous CLI\'s models', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/cli-agents/codex/models/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ cli: 'codex', models: ['codex-model-a'] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/grok/models/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ cli: 'grok', models: ['grok-model-x'] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ clis: ['codex', 'grok'], native_consensus: {}, catalog: {} }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }),
    )

    renderEditor('cli_agent')
    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    openAgentEditorTab(/Advanced/i)

    const cliSelect = await within(dialog).findByRole('combobox', { name: 'CLI override' })
    const modelSelect = await within(dialog).findByRole('combobox', { name: 'Model override' })

    await waitFor(() => {
      expect(within(modelSelect).getByRole('option', { name: 'codex-model-a' })).toBeInTheDocument()
    })

    fireEvent.change(cliSelect, { target: { value: 'grok' } })
    await waitFor(() => {
      expect(within(modelSelect).getByRole('option', { name: 'grok-model-x' })).toBeInTheDocument()
    })
    // The previous CLI's model must not survive the switch.
    expect(
      within(modelSelect).queryByRole('option', { name: 'codex-model-a' }),
    ).not.toBeInTheDocument()
  })
})

describe('AgentConfigSidepane — API profile picker lists profiles only', () => {
  it('does not surface CLI model ids as profile options', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          profiles: [{ id: 'profile-1', name: 'Profile One', model: 'gpt-x' }],
          data: [],
        }),
      }),
    )

    render(
      <AgentConfigSidepane
        agentId="codey"
        agentName="Codey"
        agentKind="api"
        onClose={() => {}}
      />,
    )

    const select = await screen.findByTestId('agent-config-profile')
    await waitFor(() => {
      expect(within(select).getByRole('option', { name: /Profile One/ })).toBeInTheDocument()
    })
    expect(
      within(select).queryByRole('option', { name: CLI_MODEL_ID }),
    ).not.toBeInTheDocument()
    expect(
      within(select).queryByRole('option', { name: API_PROFILE_ID }),
    ).not.toBeInTheDocument()
  })
})

const twoStageProviders: ComposerProviderOption[] = [
  { id: 'api', label: 'API gateway', kind: 'api', defaultOptionId: API_PROFILE_ID },
  { id: 'cli:codex', label: 'codex', kind: 'cli' },
]

const apiStage2 = [
  { id: API_PROFILE_ID, label: 'User chat / orchestration' },
  { id: 'anthropic/claude-sonnet-4-6', label: 'Claude Sonnet' },
]
const cliStage2 = [
  { id: CLI_MODEL_ID, label: CLI_MODEL_ID, tag: 'model' as const },
  { id: 'codex-mini', label: 'codex-mini', tag: 'model' as const },
]

const stage2For = (p: ComposerProviderOption) =>
  p.kind === 'api' ? apiStage2 : cliStage2

describe('ComposerPickerDialog — switching provider switches the option source', () => {
  it('api options contain no CLI model ids; cli options contain no api profile ids', () => {
    render(
      <ComposerPickerDialog
        open
        providers={twoStageProviders}
        getProviderOptions={stage2For}
        onPick={() => {}}
        onClose={() => {}}
      />,
    )

    fireEvent.click(screen.getByText('API gateway'))
    expect(screen.getByText('User chat / orchestration')).toBeTruthy()
    expect(screen.queryByText(CLI_MODEL_ID)).toBeNull()

    fireEvent.click(screen.getByTestId('composer-picker-breadcrumb-back'))
    fireEvent.click(screen.getByText('codex'))
    expect(screen.getByText(CLI_MODEL_ID)).toBeTruthy()
    // No stale API profile row survives the kind switch.
    expect(screen.queryByText('User chat / orchestration')).toBeNull()
    expect(screen.queryByText('Claude Sonnet')).toBeNull()
  })
})

describe('NavbarRoutingPicker — two-stage picker namespace isolation', () => {
  it('switching from the API provider to a CLI swaps the option set entirely', async () => {
    render(
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={[{ id: API_PROFILE_ID, label: 'Orchestration', kind: 'api' }]}
        selectedAgent={API_PROFILE_ID}
        models={[]}
        selectedModel=""
        onChange={() => {}}
        twoStage={{ providers: twoStageProviders, getProviderOptions: stage2For }}
      />,
    )

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('API gateway'))
    expect(screen.getByText('User chat / orchestration')).toBeTruthy()
    expect(screen.queryByText(CLI_MODEL_ID)).toBeNull()

    fireEvent.click(screen.getByTestId('composer-picker-breadcrumb-back'))
    fireEvent.click(screen.getByText('codex'))
    expect(screen.getByText(CLI_MODEL_ID)).toBeTruthy()
    expect(screen.queryByText('User chat / orchestration')).toBeNull()
  })
})

describe('renderRoutingPicker — per-kind option sources', () => {
  function captureStub(sink: Array<Record<string, unknown>>): ComponentType<any> {
    const Stub = (props: Record<string, unknown>) => {
      sink.push(props)
      return createElement('div', { 'data-testid': 'nrp-stub' })
    }
    return Stub
  }

  it('the API branch draws agents from profiles and never ships CLI models', () => {
    const sink: Array<Record<string, unknown>> = []
    render(
      createElement(renderRoutingPickerImpl as any, {
        NavbarRoutingPicker: captureStub(sink),
        composerShowProvider: true,
        isApiAgent: true,
        apiModelOptionsFromProfiles: () => [
          { id: API_PROFILE_ID, label: 'User chat / orchestration' },
        ],
        llmProfilesQuery: { data: { profiles: [], default_llm_profile: 'orchestration' } },
        composerProviders: twoStageProviders,
        composerOptionsForProvider: () => [],
        applyApiRoutingChange: () => {},
        selectedModelId: '',
      }),
    )
    const props = sink[0]
    expect(props.seatKind).toBe('api')
    expect(props.agents).toEqual([
      { id: API_PROFILE_ID, label: 'User chat / orchestration', kind: 'api' },
    ])
    expect(props.models).toEqual([])
    expect(JSON.stringify(props.agents)).not.toContain(CLI_MODEL_ID)
  })

  it('the CLI branch draws models from the CLI list and never ships API profile ids', () => {
    const sink: Array<Record<string, unknown>> = []
    render(
      createElement(renderRoutingPickerImpl as any, {
        NavbarRoutingPicker: captureStub(sink),
        composerShowProvider: true,
        isCliAgent: true,
        discoveredClis: ['codex'],
        currentCli: 'codex',
        availableCliModels: [CLI_MODEL_ID],
        persistedDropdown: {},
        cliModelsQuery: { isFetching: false, isPending: false },
        composerProviders: twoStageProviders,
        composerOptionsForProvider: () => [],
        applyCliRoutingChange: () => {},
      }),
    )
    const props = sink[0]
    expect(props.seatKind).toBe('cli')
    expect(props.agents).toEqual([{ id: 'codex', label: 'codex', kind: 'cli' }])
    expect(props.models).toEqual([CLI_MODEL_ID])
    expect(JSON.stringify(props.agents)).not.toContain(API_PROFILE_ID)
  })
})

describe('AddAgentWizard — no model/profile picker leaks across agent kinds', () => {
  it('never renders a model or provider-profile selector on any kind tab', () => {
    vi.spyOn(api, 'fetchBlueprints').mockResolvedValue({ object: 'list', data: [] })
    vi.spyOn(api, 'fetchCustomBlueprints').mockResolvedValue({ object: 'list', data: [] })
    vi.spyOn(api, 'fetchCliAgents').mockResolvedValue({
      clis: [],
      native_consensus: {},
      catalog: {},
      rail: [],
      remote_boxes: [],
    })
    vi.spyOn(api, 'fetchRemotes').mockResolvedValue({
      object: 'list',
      kinds: [{ id: 'omb', label: 'OpenMousBot' }],
      configured: [],
      data: [],
    })
    vi.spyOn(api, 'fetchCompanies').mockResolvedValue({ object: 'list', data: [] })

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <AddAgentWizard isOpen onClose={() => {}} />
      </QueryClientProvider>,
    )

    for (const kind of ['cli', 'api', 'blueprint', 'remote']) {
      fireEvent.click(screen.getByTestId(`kind-option-${kind}`))
      expect(screen.queryByLabelText(/model override/i)).toBeNull()
      expect(screen.queryByLabelText(/profile override/i)).toBeNull()
      expect(screen.queryByLabelText(/^provider and model$/i)).toBeNull()
    }
  })
})

/**
 * #1745 — a System1 categorizer is a *type* axis, so it adds a second kind of
 * isolation: a gate must never leak onto a chat surface, even though it is an
 * `api`-namespace profile and passes the namespace check.
 */
describe('#1745 System1 categorizers never appear on a chat surface', () => {
  const CATEGORIZER_ID = 'system1-filter'
  const CATEGORIZER_MODEL = 'system1-categorizer'

  function profilesPayload() {
    return {
      object: 'llm_profiles',
      profiles: [
        {
          id: 'orchestration',
          name: 'User chat',
          source: 'config',
          namespace: 'api',
          owned_by: 'openai',
          model: API_PROFILE_ID,
          model_type: 'chat',
        },
        {
          id: CATEGORIZER_ID,
          name: CATEGORIZER_ID,
          source: 'config',
          namespace: 'api',
          owned_by: 'system1',
          model: CATEGORIZER_MODEL,
          model_type: 'categorizer',
        },
      ],
      default_llm_profile: 'orchestration',
      task_llm_profiles: {},
      model_types: ['chat', 'categorizer'],
    }
  }

  it('the AgentEditor API override list omits the gate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/llm-profiles/')) {
          return { ok: true, status: 200, json: async () => profilesPayload() } as Response
        }
        if (url.includes('/v1/cli-agents/codex/models/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ cli: 'codex', models: [CLI_MODEL_ID] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ clis: ['codex'], native_consensus: {}, catalog: {} }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
      }),
    )

    renderEditor('codey')
    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    openAgentEditorTab(/Advanced/i)

    const modelSelect = await within(dialog).findByRole('combobox', { name: 'Model override' })
    const options = Array.from(modelSelect.querySelectorAll('option')).map(
      (row) => (row as HTMLOptionElement).value,
    )
    expect(options).toContain(API_PROFILE_ID)
    expect(options).not.toContain(CATEGORIZER_ID)
    expect(options).not.toContain(CATEGORIZER_MODEL)
  })

  it('the composer picker stage-2 rows omit the gate and the "Use default" row', () => {
    const sources = {
      api: {
        profiles: [
          { id: 'orchestration', label: 'User chat' },
          {
            id: CATEGORIZER_ID,
            label: CATEGORIZER_ID,
            modelType: 'categorizer',
            ownedBy: 'system1',
          },
        ],
        defaultProfileId: CATEGORIZER_ID,
      },
    }
    const apiProvider: ComposerProviderOption = { id: 'api', label: 'API gateway', kind: 'api' }
    const rows = composerOptionsForProvider(sources, apiProvider)
    expect(rows.map((row) => row.id)).toEqual(['orchestration'])
    // The default row would otherwise apply the gate to a chat turn.
    const providers = buildComposerProviders(sources)
    expect(providers.find((row) => row.kind === 'api')?.defaultOptionId).toBe('orchestration')
  })
})
