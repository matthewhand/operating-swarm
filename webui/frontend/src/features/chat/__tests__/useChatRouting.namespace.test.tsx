/**
 * `useChatRouting.applyCliRoutingChange` owns the CLI dropdown memory. Every
 * CLI switch must write the model slot (clearing it when the switch carries
 * no model), so the previous CLI's model can never be merged into the new
 * CLI's model list — a foreign-namespace id the new CLI does not expose.
 */
import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useChatRouting } from '../useChatRouting'
import { loadAgentDropdownChoice, saveLocalAgentDropdown } from '../../../lib/agentSettings'
import type { RoutingPathChange } from '../../../components/NavbarRoutingPicker'
import { hopCliSession } from '../../../lib/cliSessionHop'

vi.mock('../../../lib/cliSessionHop', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/cliSessionHop')>(
    '../../../lib/cliSessionHop',
  )
  return {
    ...actual,
    hopCliSession: vi.fn().mockResolvedValue({ status: '' }),
  }
})

function renderRouting() {
  const setSearchParams = vi.fn()
  const hook = renderHook(() =>
    useChatRouting({
      threadKey: 'cli_agent',
      setThreads: vi.fn(),
      teamFromUrl: '',
      remoteFromUrl: '',
      selectedBlueprint: 'cli_agent',
      conversationIdRef: { current: null },
      isRemoteAgent: false,
      isRemoteBackedTeam: false,
      isCliAgent: true,
      activeChatAgentId: 'cli_agent',
      currentCli: 'grok',
      activeRemoteId: '',
      dropdownAgentId: 'cli_agent',
      setSearchParams,
      addToast: vi.fn(),
    }),
  )
  return { ...hook, setSearchParams }
}

function agentChange(agent: string, previousAgent: string, previousModel: string): RoutingPathChange {
  return {
    changed: 'agent',
    agent,
    model: '',
    modelBase: '',
    effort: null,
    previous: { agent: previousAgent, model: previousModel, modelBase: previousModel, effort: null },
  }
}

describe('useChatRouting — CLI switch clears the previous CLI model memory', () => {
  it('drops a stale model when the new CLI carries none', () => {
    saveLocalAgentDropdown('cli_agent', { cli: 'grok', model: 'grok-4' })
    expect(loadAgentDropdownChoice('cli_agent')).toMatchObject({ cli: 'grok', model: 'grok-4' })

    const { result } = renderRouting()
    act(() => {
      result.current.applyCliRoutingChange(agentChange('codex', 'grok', 'grok-4'))
    })

    const stored = loadAgentDropdownChoice('cli_agent')
    expect(stored.cli).toBe('codex')
    // The old CLI's model must not survive into the new CLI's picker.
    expect(stored.model).toBeUndefined()
  })

  it('keeps an explicitly carried model on the switch', () => {
    saveLocalAgentDropdown('cli_agent', { cli: 'grok', model: 'grok-4' })
    const { result } = renderRouting()
    const change = agentChange('codex', 'grok', 'grok-4')
    change.model = 'gpt-5-codex'
    act(() => {
      result.current.applyCliRoutingChange(change)
    })
    expect(loadAgentDropdownChoice('cli_agent')).toMatchObject({
      cli: 'codex',
      model: 'gpt-5-codex',
    })
  })
})

describe('useChatRouting — provider reconfigure on the current CLI', () => {
  it('does not post a hop when the profile stays on the same CLI', () => {
    vi.mocked(hopCliSession).mockClear()
    const setThreads = vi.fn()
    const { result } = renderHook(() =>
      useChatRouting({
        threadKey: 'cli_agent',
        setThreads,
        teamFromUrl: '',
        remoteFromUrl: '',
        selectedBlueprint: 'cli_agent',
        conversationIdRef: { current: 'thread-1' },
        isRemoteAgent: false,
        isRemoteBackedTeam: false,
        isCliAgent: true,
        activeChatAgentId: 'cli_agent',
        currentCli: 'grok',
        activeRemoteId: '',
        dropdownAgentId: 'cli_agent',
        setSearchParams: vi.fn(),
        addToast: vi.fn(),
      }),
    )
    act(() => {
      result.current.reconfigureProviderForSeat('claude-work')
    })
    expect(hopCliSession).not.toHaveBeenCalled()
    expect(setThreads).toHaveBeenCalledTimes(1)
    const updater = setThreads.mock.calls[0][0] as (
      prev: Record<string, { text: string }[]>,
    ) => Record<string, { text: string }[]>
    const next = updater({})
    expect(next.cli_agent[0].text).toContain("Provider profile 'claude-work' noted")
    expect(next.cli_agent[0].text).toContain('CLI agent')
  })
})
