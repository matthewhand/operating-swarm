/**
 * #1684 — the dispatcher folds a `tool_status` frame into the turn registry
 * beside the existing `attachToolToThread`.
 *
 * The frame the server builds carries `{type, id, name, status, agent_id}` and
 * NO `turn_id` (`swarm.tool_executor.emit_tool_status`), and demo replay
 * (`swarm/demo/scenarios.py`) is the same shape — so this asserts the wiring
 * on the real parsed frame, not a hand-built one.
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import type { MutableRefObject } from 'react'
import { useChatWsDispatcher } from '../useChatWsDispatcher'
import { parseChatWsMessage } from '../../../lib/chatWs'
import {
  activeToolFor,
  getTurnSnapshot,
  recordTurnFrame,
  resetTurnRegistry,
} from '../../../lib/agentTurns'

vi.mock('../../../lib/railOrder', () => ({ notifyGenerationComplete: vi.fn() }))

function dispatch() {
  const attachToolToThread = vi.fn()
  const setAgentTurns = vi.fn()
  const notifyCtxRef = {
    current: { agentId: 'jeeves', agentName: 'Jeeves', agentKind: 'api', blueprintId: 'jeeves' },
  } as MutableRefObject<{
    agentId: string | null
    agentName: string
    agentKind: string
    blueprintId: string
  }>
  const view = renderHook(() =>
    useChatWsDispatcher({
      activeChatAgentId: 'jeeves',
      attachQuestionToThread: vi.fn(),
      attachToolToThread,
      sendToolDecision: vi.fn(),
      threadKey: 'jeeves',
      useSuggestions: false,
      seatUnread: false,
      pinnedToBottomRef: { current: true },
      setContextUsage: vi.fn(),
      setAgentTurns: setAgentTurns as never,
      setFanOutLegs: vi.fn(),
      setAuxTasks: vi.fn(),
      setSuggestionChips: vi.fn(),
      setThreads: vi.fn(),
      setUnreadIds: vi.fn(),
      selectedBlueprint: 'jeeves',
      userKeyCounterRef: { current: 0 },
      notifyCtxRef,
    }),
  )
  return { view, attachToolToThread, setAgentTurns }
}

/** The exact payload the live producer emits — note: no `turn_id`. */
const toolStatusFrame = (status: string, id = 'c1', name = 'read_file') =>
  parseChatWsMessage(
    JSON.stringify({ type: 'tool_status', id, name, status, agent_id: 'jeeves' }),
  )

describe('#1684 tool_status dispatcher wiring', () => {
  beforeEach(() => {
    resetTurnRegistry()
  })

  afterEach(() => {
    resetTurnRegistry()
  })

  it('records the phase and still attaches the tool to the thread', () => {
    const { view, attachToolToThread, setAgentTurns } = dispatch()
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'jeeves' })

    act(() => {
      view.result.current(toolStatusFrame('running'))
    })

    // The pre-existing transcript behaviour is untouched …
    expect(attachToolToThread).toHaveBeenCalledWith({
      id: 'c1',
      name: 'read_file',
      status: 'running',
      agentId: 'jeeves',
      needsApproval: false,
    })
    // … and the badge's source now exists too.
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).toEqual({
      toolId: 'c1',
      name: 'read_file',
    })
    // The page-level snapshot is folded in step with the global registry, so
    // the rail's merged view never shows a stale turn.
    expect(setAgentTurns).toHaveBeenCalled()
  })

  it('clears the phase on the terminal frame', () => {
    const { view } = dispatch()
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'jeeves' })
    act(() => {
      view.result.current(toolStatusFrame('running'))
    })
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).not.toBeNull()

    act(() => {
      view.result.current(toolStatusFrame('done'))
    })
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).toBeNull()
  })

  it('drops an unattributable frame instead of inventing a turn (no turnId, unknown agent)', () => {
    const { view } = dispatch()
    act(() => {
      view.result.current(
        parseChatWsMessage(
          JSON.stringify({ type: 'tool_status', id: 'x', name: 'bash', status: 'running' }),
        ),
      )
    })
    expect(getTurnSnapshot()).toEqual({})
  })

  it('a demo-mode canned frame (no turnId, done status) is a harmless no-op', () => {
    const { view, attachToolToThread } = dispatch()
    // swarm/demo/scenarios.py:113 — a `done` handoff with no turn ever started.
    act(() => {
      view.result.current(
        parseChatWsMessage(
          JSON.stringify({
            type: 'tool_status',
            id: 'demo-sdlc-handoff',
            name: 'handoff',
            status: 'done',
            agent_id: 'sdlc_handoff',
          }),
        ),
      )
    })
    expect(attachToolToThread).toHaveBeenCalled()
    expect(getTurnSnapshot()).toEqual({})
  })
})
