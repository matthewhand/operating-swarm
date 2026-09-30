/**
 * #1374 — stopping a sibling Running card must not drop this thread's
 * awaiting flag. Stopping the seat on screen still clears it.
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useChatTurnOps, type UseChatTurnOpsOptions } from '../useChatTurnOps'

function options(setAwaitingAssistant: (value: boolean) => void): UseChatTurnOpsOptions {
  return {
    selectedBlueprint: 'codey',
    setSearchParams: vi.fn(),
    messages: [],
    submitUserText: vi.fn(),
    conversationId: 'c1',
    threadKey: 'codey',
    threads: { codey: [] },
    setThreads: vi.fn(),
    wsRef: { current: { readyState: 1, send: vi.fn() } as unknown as WebSocket },
    lastUserTextRef: { current: '' },
    conversationIdRef: { current: 'c1' },
    messagesEditable: false,
    setAwaitingAssistant,
    setEditingKey: vi.fn(),
    addToast: vi.fn(),
  }
}

describe('#1374 sibling stop preserves this thread awaiting', () => {
  it('does not clear awaiting when the card asks to preserve it', () => {
    const setAwaitingAssistant = vi.fn<(value: boolean) => void>()
    const send = vi.fn()
    const { result } = renderHook(() =>
      useChatTurnOps({
        ...options(setAwaitingAssistant),
        wsRef: { current: { readyState: 1, send } as unknown as WebSocket },
      }),
    )
    act(() => {
      result.current.interruptRunningTurn('stewie', 't2', { preserveAwaiting: true })
    })
    expect(setAwaitingAssistant).not.toHaveBeenCalled()
    expect(send).toHaveBeenCalledWith('{"type":"cancel_turn","agent":"stewie","turn_id":"t2"}')
  })

  it('still clears awaiting for this seat and for a bare cancel', () => {
    const setAwaitingAssistant = vi.fn<(value: boolean) => void>()
    const send = vi.fn()
    const { result } = renderHook(() =>
      useChatTurnOps({
        ...options(setAwaitingAssistant),
        wsRef: { current: { readyState: 1, send } as unknown as WebSocket },
      }),
    )
    act(() => {
      result.current.interruptRunningTurn('codey', 't1')
    })
    expect(setAwaitingAssistant).toHaveBeenCalledWith(false)
    expect(send).toHaveBeenCalledWith('{"type":"cancel_turn","agent":"codey","turn_id":"t1"}')

    setAwaitingAssistant.mockClear()
    act(() => {
      result.current.interruptRunningTurn()
    })
    expect(setAwaitingAssistant).toHaveBeenCalledWith(false)
  })
})
