/**
 * `useChatDerived` builds the two-stage composer picker's sources and the
 * seat's selected model id. Two namespace invariants live here:
 *
 *   1. the CLI probe payload belongs to the *current* CLI only — an unrelated
 *      CLI must not inherit its models;
 *   2. API seats read their model memory from the `api` slot only — a stale
 *      CLI model id in the `model` slot must never surface on an API seat.
 */
import { describe, expect, it } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useChatDerived, type UseChatDerivedOptions } from '../useChatDerived'
import {
  buildComposerProviders,
  composerOptionsForProvider,
} from '../../../lib/composerSources'

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
}

const base: UseChatDerivedOptions = {
  searchParams: new URLSearchParams(),
  isCliAgent: true,
  currentCli: 'codex',
  currentCliModel: 'gpt-5-codex',
  persistedDropdown: {},
  llmProfilesQuery: {
    data: {
      profiles: [{ id: 'litellm/orchestration', name: 'User chat' }],
      default_llm_profile: 'litellm/orchestration',
      default_llm_ready: true,
    },
  },
  llmDefaultProfile: 'litellm/orchestration',
  input: '',
  queuedRows: [],
  queuedHoldIds: [],
  isApiAgent: false,
  defaultLlmTipDismissed: true,
  messages: [],
  replyTarget: null,
  selectedAgentName: 'Codex',
  status: 'open',
  authRejected: false,
  selectedBlueprint: 'cli_agent',
  discoveredClis: ['codex', 'grok'],
  cliModelsQuery: { data: { models: ['gpt-5-codex'] } },
  configuredRemoteRows: [],
  activeRemoteId: '',
  remoteNavbarAgents: [],
  remoteAgentsQuery: { isPending: false },
  herdrAgentsQuery: { data: { data: [] }, isPending: false },
  teamsQuery: { data: [] },
  blueprints: [],
  contextMaxRef: { current: null },
}

function renderDerived(overrides: Partial<UseChatDerivedOptions> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useChatDerived({ ...base, ...overrides }), {
    wrapper: wrapper(client),
  })
}

describe('useChatDerived composer sources — CLI model scoping', () => {
  it('attaches probed models only to the current CLI', () => {
    const { result } = renderDerived()
    const clis = result.current.composerSources.clis ?? []
    const codex = clis.find((c) => c.name === 'codex')!
    const grok = clis.find((c) => c.name === 'grok')!
    expect(codex.models).toEqual(['gpt-5-codex'])
    // The other CLI has no probe yet — honest empty, never codex's models.
    expect(grok.models).toBeUndefined()
  })

  it("api options are profiles only; cli options are that CLI's models only", () => {
    const { result } = renderDerived()
    const sources = result.current.composerSources
    const providers = buildComposerProviders(sources)
    const api = providers.find((p) => p.kind === 'api')!
    const codex = providers.find((p) => p.id === 'cli:codex')!

    expect(composerOptionsForProvider(sources, api).map((o) => o.id)).toEqual([
      'litellm/orchestration',
    ])
    expect(composerOptionsForProvider(sources, codex).map((o) => o.id)).toEqual([
      'gpt-5-codex',
    ])
    expect(
      composerOptionsForProvider(sources, api).map((o) => o.id),
    ).not.toContain('gpt-5-codex')
    expect(
      composerOptionsForProvider(sources, codex).map((o) => o.id),
    ).not.toContain('litellm/orchestration')
  })
})

describe('#1372 useChatDerived composer placeholder', () => {
  it('is Message <selected agent display name>', () => {
    const { result } = renderDerived({ selectedAgentName: 'Ada Lovelace' })
    expect(result.current.composerPlaceholder).toBe('Message Ada Lovelace')
  })

  it('falls back when the display name is empty and never interpolates undefined/null', () => {
    const { result } = renderDerived({ selectedAgentName: '' })
    expect(result.current.composerPlaceholder).toBe('Message …')
    expect(result.current.composerPlaceholder).not.toMatch(/undefined|null/)
  })

  it('keeps Reply… while a reply is armed', () => {
    const { result } = renderDerived({
      selectedAgentName: 'Ada Lovelace',
      replyTarget: { id: 'm1' },
    })
    expect(result.current.composerPlaceholder).toBe('Reply…')
  })

  it('updates when the selected agent is renamed', () => {
    const { result, rerender } = renderHook(
      (name: string) =>
        useChatDerived({
          ...base,
          selectedAgentName: name,
        }),
      {
        wrapper: wrapper(new QueryClient({ defaultOptions: { queries: { retry: false } } })),
        initialProps: 'Ada Lovelace',
      },
    )
    expect(result.current.composerPlaceholder).toBe('Message Ada Lovelace')
    rerender('Charles Babbage')
    expect(result.current.composerPlaceholder).toBe('Message Charles Babbage')
  })
})

describe('useChatDerived selectedModelId — API seat never reads the CLI slot', () => {
  it('ignores a stale CLI model id in the model slot', () => {
    const { result } = renderDerived({
      isCliAgent: false,
      isApiAgent: true,
      currentCli: '',
      currentCliModel: '',
      persistedDropdown: { model: 'gpt-5-codex' },
    })
    expect(result.current.selectedModelId).toBe('')
  })

  it('prefers the api slot and the ?model= param for API seats', () => {
    const fromApiSlot = renderDerived({
      isCliAgent: false,
      isApiAgent: true,
      currentCli: '',
      currentCliModel: '',
      persistedDropdown: { api: 'litellm/orchestration', model: 'gpt-5-codex' },
    })
    expect(fromApiSlot.result.current.selectedModelId).toBe('litellm/orchestration')

    const fromParam = renderDerived({
      isCliAgent: false,
      isApiAgent: true,
      currentCli: '',
      currentCliModel: '',
      searchParams: new URLSearchParams('model=anthropic/claude-sonnet-4-6'),
      persistedDropdown: { api: 'litellm/orchestration', model: 'gpt-5-codex' },
    })
    expect(fromParam.result.current.selectedModelId).toBe('anthropic/claude-sonnet-4-6')
  })
})
