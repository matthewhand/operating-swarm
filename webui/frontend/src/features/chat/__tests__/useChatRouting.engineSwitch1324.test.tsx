/**
 * #1324 — a hop that reports capability loss must toast a warning and
 * still land the switch (never block).
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useChatRouting } from '../useChatRouting'
import type { RoutingPathChange } from '../../../components/NavbarRoutingPicker'

const hopCliSession = vi.fn()

vi.mock('../../../lib/cliSessionHop', () => ({
  crossKindHopForReconfigure: vi.fn(),
  hopCliSession: (...args: unknown[]) => hopCliSession(...args),
}))

afterEach(() => {
  hopCliSession.mockReset()
})

function agentChange(agent: string, previousAgent: string): RoutingPathChange {
  return {
    changed: 'agent',
    agent,
    model: '',
    modelBase: '',
    effort: null,
    previous: { agent: previousAgent, model: '', modelBase: '', effort: null },
  }
}

describe('#1324 useChatRouting engine-switch warning toast', () => {
  it('toasts capability_warning without blocking the hop status line', async () => {
    hopCliSession.mockResolvedValue({
      status: 'Started a new claude session (grok → claude). Carried summary context (12 tokens). Switching from grok to claude loses session list.',
      capability_warning: 'Switching from grok to claude loses session list.',
    })
    const addToast = vi.fn()
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
        addToast,
      }),
    )

    act(() => {
      result.current.applyCliRoutingChange(agentChange('claude', 'grok'))
    })

    await vi.waitFor(() => {
      expect(addToast).toHaveBeenCalledWith({
        type: 'warning',
        title: 'Engine switch',
        message: 'Switching from grok to claude loses session list.',
      })
    })
    expect(setThreads).toHaveBeenCalled()
  })

  it('does not toast when the hop reports no capability loss', async () => {
    hopCliSession.mockResolvedValue({
      status: 'Started a new agy session (grok → agy). Carried summary context (12 tokens).',
      capability_warning: null,
    })
    const addToast = vi.fn()
    const { result } = renderHook(() =>
      useChatRouting({
        threadKey: 'cli_agent',
        setThreads: vi.fn(),
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
        addToast,
      }),
    )

    act(() => {
      result.current.applyCliRoutingChange(agentChange('agy', 'grok'))
    })

    await vi.waitFor(() => expect(hopCliSession).toHaveBeenCalled())
    expect(addToast).not.toHaveBeenCalled()
  })

  it('toasts an acknowledged loss before the hop runs, and does not toast twice', async () => {
    const order: string[] = []
    hopCliSession.mockImplementation(() => {
      order.push('hop')
      return Promise.resolve({
        status: 'Started a new claude session (grok → claude). Switching from grok to claude loses session list.',
        capability_warning: 'Switching from grok to claude loses session list.',
      })
    })
    const addToast = vi.fn(() => {
      order.push('toast')
    })
    const setSearchParams = vi.fn()
    const { result } = renderHook(() =>
      useChatRouting({
        threadKey: 'cli_agent',
        setThreads: vi.fn(),
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
        setSearchParams,
        addToast,
      }),
    )

    act(() => {
      result.current.applyCliRoutingChange({
        ...agentChange('claude', 'grok'),
        capabilityWarning: 'Switching from grok to claude loses session list.',
      })
    })

    await vi.waitFor(() => expect(hopCliSession).toHaveBeenCalled())
    expect(order[0]).toBe('toast')
    expect(order.filter((step) => step === 'toast')).toEqual(['toast'])
    expect(setSearchParams).toHaveBeenCalled()
    expect(addToast).toHaveBeenCalledTimes(1)

    addToast.mockClear()
    act(() => {
      result.current.applyCliRoutingChange({
        ...agentChange('claude', 'grok'),
        capabilityWarning: 'Switching from grok to claude loses session list.',
      })
    })
    await vi.waitFor(() => expect(hopCliSession).toHaveBeenCalledTimes(2))
    expect(addToast).toHaveBeenCalledTimes(1)
  })
})
