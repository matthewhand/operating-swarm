/**
 * #1411 — a reaction_turn frame becomes a visible reaction-only row.
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { MutableRefObject } from 'react'
import { useChatWsDispatcher } from '../useChatWsDispatcher'
import type { ChatMessage } from '../chatMessages'
import { parseChatWsMessage } from '../../../lib/chatWs'

vi.mock('../../../lib/railOrder', () => ({
  notifyGenerationComplete: vi.fn(),
}))

function dispatch(initial: ChatMessage[] = []) {
  const threads: { current: Record<string, ChatMessage[]> } = { current: { jeeves: initial } }
  const setThreads = (updater: unknown) => {
    const prev = threads.current
    threads.current =
      typeof updater === 'function'
        ? (updater as (value: Record<string, ChatMessage[]>) => Record<string, ChatMessage[]>)(prev)
        : (updater as Record<string, ChatMessage[]>)
  }
  const notifyCtxRef = {
    current: { agentId: 'jeeves', agentName: 'Jeeves', agentKind: 'api', blueprintId: 'jeeves' },
  } as MutableRefObject<{
    agentId: string | null
    agentName: string
    agentKind: string
    blueprintId: string
  }>
  const hook = renderHook(() =>
    useChatWsDispatcher({
      activeChatAgentId: 'jeeves',
      attachQuestionToThread: vi.fn(),
      attachToolToThread: vi.fn(),
      sendToolDecision: vi.fn(),
      threadKey: 'jeeves',
      useSuggestions: false,
      seatUnread: false,
      pinnedToBottomRef: { current: true },
      setContextUsage: vi.fn(),
      setAgentTurns: vi.fn(),
      setFanOutLegs: vi.fn(),
      setAuxTasks: vi.fn(),
      setSuggestionChips: vi.fn(),
      setThreads: setThreads as never,
      setUnreadIds: vi.fn(),
      selectedBlueprint: 'jeeves',
      userKeyCounterRef: { current: 0 },
      notifyCtxRef,
    }),
  )
  return { hook, threads }
}

describe('#1411 reaction_turn dispatcher', () => {
  it('appends a reaction-only assistant row with no text', () => {
    const { hook, threads } = dispatch()
    const event = parseChatWsMessage(
      JSON.stringify({
        type: 'reaction_turn',
        id: 'message-response-abc',
        emoji: '👍',
        reaction_only: true,
        reactions: [{ emoji: '👍', count: 1, agentReacted: true }],
      }),
    )
    act(() => {
      hook.result.current(event)
    })
    const row = threads.current.jeeves[0]
    expect(row.key).toBe('message-response-abc')
    expect(row.role).toBe('assistant')
    expect(row.text).toBe('')
    expect(row.reactionOnly).toBe(true)
    expect(row.streaming).toBe(false)
    expect(row.reactions?.[0]?.emoji).toBe('👍')
  })

  it('replaces an in-flight row instead of duplicating it', () => {
    const { hook, threads } = dispatch([
      { key: 'message-response-abc', role: 'assistant', text: '…', streaming: true },
    ])
    const event = parseChatWsMessage(
      JSON.stringify({
        type: 'reaction_turn',
        id: 'message-response-abc',
        emoji: '👀',
        reaction_only: true,
        reactions: [{ emoji: '👀', count: 1, agentReacted: true }],
      }),
    )
    act(() => {
      hook.result.current(event)
    })
    expect(threads.current.jeeves).toHaveLength(1)
    expect(threads.current.jeeves[0].text).toBe('')
    expect(threads.current.jeeves[0].reactionOnly).toBe(true)
    expect(threads.current.jeeves[0].reactions?.[0]?.emoji).toBe('👀')
  })
})
