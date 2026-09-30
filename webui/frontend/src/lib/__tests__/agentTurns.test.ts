/**
 * ADR-017 PR-2 — the SPA-side turn registry pins.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import * as spaSocket from '../spaSocket'
import {
  activeToolFor,
  activeTurnFor,
  applyTurnFrame,
  getTurnSnapshot,
  isAgentTurnActive,
  recordToolPhaseFrame,
  recordTurnFrame,
  resetTurnRegistry,
  runningTurns,
  stopLabelFor,
  subscribeAgentTurns,
  useActiveToolForAgent,
  useAgentTurns,
  AGENT_TURNS_EVENT,
  TOOL_STATUS_WATCHDOG_MS,
  type ToolPhaseFrame,
  type TurnBookendFrame,
  type TurnSnapshot,
} from '../agentTurns'

const started = (turnId: string, agentId: string) =>
  ({ kind: 'turn_started', turnId, agentId }) as const
const finished = (turnId: string, agentId: string) =>
  ({ kind: 'turn_finished', turnId, agentId }) as const

/**
 * #1684: the shape the live `tool_status` frames actually carry —
 * `{type, id, name, status, agent_id}` and NO `turn_id`
 * (`swarm.tool_executor.emit_tool_status`). Demo replay
 * (`swarm/demo/scenarios.py`) is the same shape.
 */
const toolFrame = (
  id: string,
  name: string,
  status: string,
  agentId?: string,
): ToolPhaseFrame => ({ kind: 'tool_status', id, name, status, agentId })

describe('applyTurnFrame', () => {
  it('registers a running turn from turn_started', () => {
    const snap = applyTurnFrame({}, started('t1', 'jeeves'))
    // #1684: a turn carries its in-flight tool, not just a state.
    expect(snap['t1']).toEqual({
      turnId: 't1',
      agentId: 'jeeves',
      state: 'running',
      activeTool: null,
    })
  })

  it('marks the turn finished, keeping identity', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, finished('t1', 'jeeves'))
    expect(snap['t1']).toEqual({
      turnId: 't1',
      agentId: 'jeeves',
      state: 'finished',
      activeTool: null,
    })
  })

  it('keeps other agents turns untouched by one finish', () => {
    let snap = applyTurnFrame({}, started('t1', 'a'))
    snap = applyTurnFrame(snap, started('t2', 'b'))
    snap = applyTurnFrame(snap, finished('t1', 'a'))
    expect(snap['t2'].state).toBe('running')
  })

  it('ignores turn_finished for an unknown turn', () => {
    const snap: TurnSnapshot = {}
    expect(applyTurnFrame(snap, finished('ghost', 'x'))).toBe(snap)
  })
})

describe('activeTurnFor', () => {
  it('finds the running turn of the requested agent', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, started('t2', 'moa'))
    expect(activeTurnFor(snap, 'moa')?.turnId).toBe('t2')
  })

  it('returns null once that agent only has finished turns', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, finished('t1', 'jeeves'))
    expect(activeTurnFor(snap, 'jeeves')).toBeNull()
  })

  it('is empty before any bookend arrives (bookends are optional protocol)', () => {
    expect(activeTurnFor({}, 'jeeves')).toBeNull()
  })
})

describe('runningTurns', () => {
  it('lists only live turns in insertion order', () => {
    let snap = applyTurnFrame({}, started('t1', 'a'))
    snap = applyTurnFrame(snap, started('t2', 'b'))
    snap = applyTurnFrame(snap, finished('t1', 'a'))
    expect(runningTurns(snap).map((turn) => turn.turnId)).toEqual(['t2'])
  })
})

describe('stopLabelFor', () => {
  it('names the scoped contract when a live turn exists', () => {
    const snap = applyTurnFrame({}, started('t1', 'jeeves'))
    expect(stopLabelFor(activeTurnFor(snap, 'jeeves'))).toContain('other turns keep running')
  })
})

describe('global registry and subscription (#1118)', () => {
  beforeEach(() => {
    resetTurnRegistry()
  })

  afterEach(() => {
    resetTurnRegistry()
  })

  it('records turn_started and turn_finished into the registry and drives isAgentTurnActive', () => {
    expect(isAgentTurnActive('jeeves')).toBe(false)
    recordTurnFrame(started('t1', 'jeeves'))
    expect(isAgentTurnActive('jeeves')).toBe(true)
    expect(getTurnSnapshot()['t1']).toEqual({
      turnId: 't1',
      agentId: 'jeeves',
      state: 'running',
      activeTool: null,
    })

    recordTurnFrame(finished('t1', 'jeeves'))
    expect(isAgentTurnActive('jeeves')).toBe(false)
    expect(getTurnSnapshot()['t1']?.state).toBe('finished')
  })

  it('supports single-argument applyTurnFrame to update the global registry', () => {
    expect(isAgentTurnActive('codey')).toBe(false)
    applyTurnFrame(started('t2', 'codey'))
    expect(isAgentTurnActive('codey')).toBe(true)
    applyTurnFrame(finished('t2', 'codey'))
    expect(isAgentTurnActive('codey')).toBe(false)
  })

  it('resolves isAgentTurnActive with or without scoped prefix', () => {
    recordTurnFrame(started('t1', 'jeeves'))
    expect(isAgentTurnActive('jeeves')).toBe(true)
    expect(isAgentTurnActive('agent:jeeves')).toBe(true)
    expect(isAgentTurnActive('blueprint:jeeves')).toBe(true)
    expect(isAgentTurnActive('other')).toBe(false)
  })

  it('notifies listeners when a turn starts and finishes', () => {
    const history: TurnSnapshot[] = []
    const unsub = subscribeAgentTurns((snap) => {
      history.push(snap)
    })

    recordTurnFrame(started('t1', 'jeeves'))
    expect(history.length).toBe(1)
    expect(history[0]['t1']?.state).toBe('running')

    recordTurnFrame(finished('t1', 'jeeves'))
    expect(history.length).toBe(2)
    expect(history[1]['t1']?.state).toBe('finished')

    unsub()
    recordTurnFrame(started('t2', 'moa'))
    expect(history.length).toBe(2)
  })

  it('dispatches AGENT_TURNS_EVENT window event on update', () => {
    const events: TurnSnapshot[] = []
    const onEvent = (e: Event) => {
      events.push((e as CustomEvent<TurnSnapshot>).detail)
    }
    window.addEventListener(AGENT_TURNS_EVENT, onEvent)

    recordTurnFrame(started('t1', 'jeeves'))
    expect(events.length).toBe(1)
    expect(events[0]['t1']?.state).toBe('running')

    window.removeEventListener(AGENT_TURNS_EVENT, onEvent)
  })
})

describe('whole-SPA tap feeds background turns (#1118)', () => {
  beforeEach(() => {
    resetTurnRegistry()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    resetTurnRegistry()
  })

  it('useAgentTurns taps the conversation-blind mux so a background bookend animates (#1118)', () => {
    const spy = vi.spyOn(spaSocket, 'onSpaFrame')
    const { unmount } = renderHook(() => useAgentTurns())
    expect(spy).toHaveBeenCalled()

    const handler = spy.mock.calls[0][0] as (
      event: { kind: string; turnId: string; agentId: string },
      conversationId: string,
    ) => void

    // A bookend from a chat that is NOT mounted (background/sticky session).
    act(() => {
      handler(started('bg-1', 'stewie'), 'background-conversation')
    })
    expect(isAgentTurnActive('stewie')).toBe(true)

    act(() => {
      handler(finished('bg-1', 'stewie'), 'background-conversation')
    })
    expect(isAgentTurnActive('stewie')).toBe(false)

    unmount()
  })
})

/**
 * #1684 — the turn phase. `docs/UI_DESIGN.md` §3: the avatar's eye-dots mean
 * "waiting on a model response"; the Running badge means "a tool call is in
 * flight". Two states, two sources, never one flag.
 */
describe('tool phase reducer (#1684)', () => {
  beforeEach(() => {
    resetTurnRegistry()
  })

  afterEach(() => {
    vi.useRealTimers()
    resetTurnRegistry()
  })

  it('sets activeTool on `running`, resolved by agentId because the frame carries no turnId', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('call-1', 'read_file', 'running', 'jeeves'))
    expect(snap['t1'].activeTool).toEqual({ toolId: 'call-1', name: 'read_file' })
    expect(activeToolFor(snap, 'jeeves')).toEqual({ toolId: 'call-1', name: 'read_file' })
  })

  it('clears on done | error | denied', () => {
    for (const status of ['done', 'error', 'denied']) {
      let snap = applyTurnFrame({}, started(`t-${status}`, 'jeeves'))
      snap = applyTurnFrame(snap, toolFrame(`c-${status}`, 'read_file', 'running', 'jeeves'))
      snap = applyTurnFrame(snap, toolFrame(`c-${status}`, 'read_file', status, 'jeeves'))
      expect(snap[`t-${status}`].activeTool).toBeNull()
    }
  })

  it('does NOT clear on `allowed` — the call is approved and about to execute', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'bash', 'running', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'bash', 'allowed', 'jeeves'))
    expect(snap['t1'].activeTool).toEqual({ toolId: 'c1', name: 'bash' })
  })

  it('correlates the terminal frame by id, so one call finishing cannot retire a parallel one', () => {
    // The SDK fans a batch out through asyncio.gather, so two `read_file`
    // calls genuinely overlap (turn_phase.py:29-35).
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('a', 'read_file', 'running', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('b', 'read_file', 'running', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('a', 'read_file', 'done', 'jeeves'))
    // `b` is still running: the badge must survive `a`'s terminal frame.
    expect(snap['t1'].activeTool).toEqual({ toolId: 'b', name: 'read_file' })
    snap = applyTurnFrame(snap, toolFrame('b', 'read_file', 'done', 'jeeves'))
    expect(snap['t1'].activeTool).toBeNull()
  })

  it('scopes the tool to its own agent — one busy agent cannot badge another', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, started('t2', 'moa'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'read_file', 'running', 'moa'))
    expect(activeToolFor(snap, 'moa')).toEqual({ toolId: 'c1', name: 'read_file' })
    expect(activeToolFor(snap, 'jeeves')).toBeNull()
    expect(snap['t1'].activeTool).toBeNull()
  })

  it('resolves a scoped agentId exactly as isAgentTurnActive does', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'read_file', 'running', 'jeeves'))
    expect(activeToolFor(snap, 'agent:jeeves')).toEqual({ toolId: 'c1', name: 'read_file' })
    expect(activeToolFor(snap, 'blueprint:jeeves')).toEqual({ toolId: 'c1', name: 'read_file' })
    expect(activeToolFor(snap, 'agent:moa')).toBeNull()
    expect(activeToolFor(snap, null)).toBeNull()
  })

  it('never invents a turn for an unattributable frame (no phantom turn to finish)', () => {
    // No turn has started yet — e.g. a frame for another conversation.
    const snap = applyTurnFrame({}, toolFrame('c1', 'read_file', 'running', 'ghost'))
    expect(snap).toEqual({})
    expect(isAgentTurnActive('ghost', snap)).toBe(false)
  })

  it('ignores a terminal frame for a different tool than the one in flight', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'read_file', 'running', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('other', 'bash', 'done', 'jeeves'))
    expect(snap['t1'].activeTool).toEqual({ toolId: 'c1', name: 'read_file' })
  })

  it('never-stuck layer 2: turn_finished clears an in-flight tool unconditionally', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'read_file', 'running', 'jeeves'))
    // The socket died before the tool's own terminal frame came back.
    snap = applyTurnFrame(snap, finished('t1', 'jeeves'))
    expect(snap['t1'].activeTool).toBeNull()
    expect(activeToolFor(snap, 'jeeves')).toBeNull()
  })

  it('a re-delivered turn_started does not wipe the tool in flight', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, toolFrame('c1', 'read_file', 'running', 'jeeves'))
    snap = applyTurnFrame(snap, started('t1', 'jeeves'))
    expect(snap['t1'].activeTool).toEqual({ toolId: 'c1', name: 'read_file' })
  })
})

describe('tool phase never-stuck layer 3: the client watchdog (#1684)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetTurnRegistry()
  })

  afterEach(() => {
    vi.useRealTimers()
    resetTurnRegistry()
  })

  it('expires a badge whose terminal frame never arrived', () => {
    recordTurnFrame(started('t1', 'jeeves'))
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'jeeves'))
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).not.toBeNull()

    vi.advanceTimersByTime(TOOL_STATUS_WATCHDOG_MS - 1)
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).not.toBeNull()

    vi.advanceTimersByTime(1)
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).toBeNull()
  })

  it('is disarmed by a terminal frame — the timer must not outlive its badge', () => {
    recordTurnFrame(started('t1', 'jeeves'))
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'jeeves'))
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'done', 'jeeves'))
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).toBeNull()

    // Nothing to clear, and no stray timer firing a notification later.
    const history: TurnSnapshot[] = []
    const unsub = subscribeAgentTurns((snap) => history.push(snap))
    vi.advanceTimersByTime(TOOL_STATUS_WATCHDOG_MS * 2)
    expect(history).toEqual([])
    unsub()
  })

  it('re-arms per tool, so a second call gets a fresh budget', () => {
    recordTurnFrame(started('t1', 'jeeves'))
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'jeeves'))
    vi.advanceTimersByTime(TOOL_STATUS_WATCHDOG_MS - 10)
    // A new tool starts on the same turn: the badge is now c2's, and c2 has
    // the full bound rather than inheriting c1's almost-expired one.
    recordToolPhaseFrame(toolFrame('c2', 'bash', 'running', 'jeeves'))
    vi.advanceTimersByTime(20)
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).toEqual({
      toolId: 'c2',
      name: 'bash',
    })
  })

  it('resetTurnRegistry disarms every watchdog', () => {
    recordTurnFrame(started('t1', 'jeeves'))
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'jeeves'))
    resetTurnRegistry()
    expect(activeToolFor(getTurnSnapshot(), 'jeeves')).toBeNull()
    expect(() => vi.advanceTimersByTime(TOOL_STATUS_WATCHDOG_MS)).not.toThrow()
  })
})

describe('tool phase through the global registry and the whole-SPA tap (#1684)', () => {
  beforeEach(() => {
    resetTurnRegistry()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    resetTurnRegistry()
  })

  it('records a background conversation tool phase from the conversation-blind tap', () => {
    const spy = vi.spyOn(spaSocket, 'onSpaFrame')
    const { unmount } = renderHook(() => useActiveToolForAgent('stewie'))
    const handler = spy.mock.calls[0][0] as (
      event: TurnBookendFrame | ToolPhaseFrame,
      conversationId: string,
    ) => void

    // A tool frame from a chat that is NOT mounted (sticky background session).
    // This is the whole reason the phase lives in the registry.
    act(() => {
      handler(started('bg-1', 'stewie'), 'background-conversation')
      handler(toolFrame('c1', 'read_file', 'running', 'stewie'), 'background-conversation')
    })
    expect(activeToolFor(getTurnSnapshot(), 'stewie')).toEqual({
      toolId: 'c1',
      name: 'read_file',
    })

    act(() => {
      handler(toolFrame('c1', 'read_file', 'done', 'stewie'), 'background-conversation')
    })
    expect(activeToolFor(getTurnSnapshot(), 'stewie')).toBeNull()

    unmount()
  })

  it('notifies subscribers when the phase changes, and not when it does not', () => {
    const history: TurnSnapshot[] = []
    const unsub = subscribeAgentTurns((snap) => history.push(snap))
    recordTurnFrame(started('t1', 'jeeves'))
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'jeeves'))
    expect(history.length).toBe(2)

    // A duplicate `running` for the same tool changes nothing, so subscribers
    // (the rail, the composer) are not re-rendered for a no-op frame.
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'jeeves'))
    expect(history.length).toBe(2)

    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'done', 'jeeves'))
    expect(history.length).toBe(3)
    unsub()
  })
})
