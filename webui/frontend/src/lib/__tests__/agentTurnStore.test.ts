/**
 * #1118 — global per-agent turn registry contracts.
 *
 * The core guarantee: "is agent X mid-turn" is answered from bookends
 * arriving on ANY conversation's session — the mounted chat is irrelevant.
 * Avatar motion sources from here so clicking away can never freeze it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  __foldForTests,
  agentTurnSnapshot,
  isAgentTurnRunning,
  resetAgentTurnStoreForTests,
  startAgentTurnStore,
  subscribeAgentTurns,
} from '../agentTurnStore'

describe('agentTurnStore (#1118)', () => {
  beforeEach(() => {
    resetAgentTurnStoreForTests()
  })

  afterEach(() => {
    resetAgentTurnStoreForTests()
  })

  it('turn_started marks the agent running; turn_finished clears it', () => {
    __foldForTests({ kind: 'turn_started', turnId: 't1', agentId: 'agent-a' })
    expect(isAgentTurnRunning('agent-a')).toBe(true)

    __foldForTests({ kind: 'turn_finished', turnId: 't1', agentId: 'agent-a' })
    expect(isAgentTurnRunning('agent-a')).toBe(false)
  })

  it('bookends from a background conversation still update the store (#1118)', () => {
    // The store never learns which chat is mounted — fold is conversation-
    // blind by design, which IS the fix.
    __foldForTests({ kind: 'turn_started', turnId: 't2', agentId: 'agent-b' })
    expect(isAgentTurnRunning('agent-b')).toBe(true)
    __foldForTests({ kind: 'turn_started', turnId: 't3', agentId: 'agent-c' })
    expect(isAgentTurnRunning('agent-c')).toBe(true)
    __foldForTests({ kind: 'turn_finished', turnId: 't3', agentId: 'agent-c' })
    expect(isAgentTurnRunning('agent-c')).toBe(false)
    expect(isAgentTurnRunning('agent-b')).toBe(true)
  })

  it('snapshot only carries running agents and freezes between emits', () => {
    expect(agentTurnSnapshot()).toEqual({})
    __foldForTests({ kind: 'turn_started', turnId: 't1', agentId: 'agent-a' })
    expect(agentTurnSnapshot()).toEqual({ 'agent-a': true })
    const snap = agentTurnSnapshot()
    __foldForTests({ kind: 'turn_finished', turnId: 't1', agentId: 'agent-a' })
    expect(agentTurnSnapshot()).toEqual({})
    expect(snap).toEqual({ 'agent-a': true }) // old snapshot untouched
  })

  it('notifies subscribers exactly once per state change', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeAgentTurns(listener)
    __foldForTests({ kind: 'turn_started', turnId: 't1', agentId: 'agent-a' })
    expect(listener).toHaveBeenCalledTimes(1)
    // finishing an agent that was never started is a no-op
    __foldForTests({ kind: 'turn_finished', turnId: 't9', agentId: 'ghost' })
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
    __foldForTests({ kind: 'turn_started', turnId: 't2', agentId: 'agent-b' })
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('startAgentTurnStore is idempotent and taps the spa frame stream', async () => {
    const spaSocket = await import('../spaSocket')
    vi.spyOn(spaSocket, 'onSpaFrame')
    startAgentTurnStore()
    startAgentTurnStore()
    expect(spaSocket.onSpaFrame).toHaveBeenCalledTimes(1)
  })
})
