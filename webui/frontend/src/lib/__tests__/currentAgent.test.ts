import { describe, it, expect, beforeEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import {
  CURRENT_AGENT_EVENT,
  CURRENT_AGENT_STORAGE_KEY,
  isApiSeat,
  isScopedSeatId,
  isSwarmOwnedSeat,
  loadCurrentAgent,
  parseCurrentAgent,
  publishCurrentAgent,
  subscribeCurrentAgent,
  useCurrentAgent,
  type CurrentAgent,
} from '../currentAgent'

const API_SEAT: CurrentAgent = { id: 'researcher', kind: 'api' }

beforeEach(() => {
  localStorage.clear()
})

describe('REQ-912/914/917: current-agent signal', () => {
  it('round-trips a published seat through storage', () => {
    expect(loadCurrentAgent()).toBeNull()
    publishCurrentAgent(API_SEAT)
    expect(loadCurrentAgent()).toEqual(API_SEAT)
  })

  it('clears the seat on publish(null), so "unknown" is distinguishable from stale', () => {
    publishCurrentAgent(API_SEAT)
    publishCurrentAgent(null)
    expect(loadCurrentAgent()).toBeNull()
  })

  it('keeps the scope prefix so a team/remote scope is not mistaken for an agent id', () => {
    expect(isScopedSeatId('team:alpha')).toBe(true)
    expect(isScopedSeatId('remote:omb')).toBe(true)
    expect(isScopedSeatId('researcher')).toBe(false)
    expect(isScopedSeatId('')).toBe(false)

    publishCurrentAgent({ id: 'remote:omb', kind: 'remote' })
    expect(loadCurrentAgent()).toEqual({ id: 'remote:omb', kind: 'remote' })
  })

  it('parses junk without throwing', () => {
    expect(parseCurrentAgent(null)).toBeNull()
    expect(parseCurrentAgent(undefined)).toBeNull()
    expect(parseCurrentAgent('')).toBeNull()
    expect(parseCurrentAgent('not json')).toBeNull()
    expect(parseCurrentAgent(42)).toBeNull()
    expect(parseCurrentAgent([])).toBeNull()
    expect(parseCurrentAgent({})).toBeNull()
    expect(parseCurrentAgent({ id: '   ' })).toBeNull()
    expect(parseCurrentAgent({ kind: 'api' })).toBeNull()
  })

  it('accepts a JSON string payload and falls back to id classification for an unknown kind', () => {
    expect(parseCurrentAgent('{"id":"researcher","kind":"api"}')).toEqual(API_SEAT)
    // Unknown/missing kind must not discard a usable seat.
    expect(parseCurrentAgent({ id: 'cli:worker' })).toEqual({ id: 'cli:worker', kind: 'cli' })
    expect(parseCurrentAgent({ id: 'remote:omb', kind: 'nonsense' })).toEqual({
      id: 'remote:omb',
      kind: 'remote',
    })
  })

  it('survives an unreadable storage payload', () => {
    localStorage.setItem(CURRENT_AGENT_STORAGE_KEY, '{not json')
    expect(loadCurrentAgent()).toBeNull()
  })

  it('delivers same-document publishes to subscribers and stops after unsubscribe', () => {
    const seen: Array<CurrentAgent | null> = []
    const off = subscribeCurrentAgent((agent) => seen.push(agent))

    publishCurrentAgent(API_SEAT)
    publishCurrentAgent(null)
    expect(seen).toEqual([API_SEAT, null])

    off()
    publishCurrentAgent({ id: 'cli:worker', kind: 'cli' })
    expect(seen).toHaveLength(2)
  })

  it('delivers other-tab writes via the storage channel', () => {
    const seen: Array<CurrentAgent | null> = []
    subscribeCurrentAgent((agent) => seen.push(agent))

    // A `storage` event only ever fires in *other* documents, so simulate one
    // the way the browser would: the value is already written.
    localStorage.setItem(
      CURRENT_AGENT_STORAGE_KEY,
      JSON.stringify({ id: 'remote:omb', kind: 'remote' }),
    )
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: CURRENT_AGENT_STORAGE_KEY,
          newValue: localStorage.getItem(CURRENT_AGENT_STORAGE_KEY),
        }),
      )
    })

    expect(seen).toEqual([{ id: 'remote:omb', kind: 'remote' }])
  })

  it('ignores storage writes for unrelated keys', () => {
    const handler = vi.fn()
    subscribeCurrentAgent(handler)
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'swarm_theme' }))
    })
    expect(handler).not.toHaveBeenCalled()
  })

  it('dispatches the documented event name with the seat as detail', () => {
    const handler = vi.fn()
    window.addEventListener(CURRENT_AGENT_EVENT, handler)
    publishCurrentAgent(API_SEAT)
    window.removeEventListener(CURRENT_AGENT_EVENT, handler)
    expect(handler).toHaveBeenCalledTimes(1)
    expect((handler.mock.calls[0][0] as CustomEvent).detail).toEqual(API_SEAT)
  })

  it('reads and updates through the hook', () => {
    const { result } = renderHook(() => useCurrentAgent())
    expect(result.current).toBeNull()

    act(() => {
      publishCurrentAgent(API_SEAT)
    })
    expect(result.current).toEqual(API_SEAT)

    act(() => {
      publishCurrentAgent(null)
    })
    expect(result.current).toBeNull()
  })

  it('classifies an API seat strictly and a swarm-owned seat inclusively', () => {
    const cli: CurrentAgent = { id: 'cli:worker', kind: 'cli' }
    const remote: CurrentAgent = { id: 'remote:omb', kind: 'remote' }
    const blueprint: CurrentAgent = { id: 'software_dev', kind: 'blueprint' }

    expect(isApiSeat(API_SEAT)).toBe(true)
    expect(isApiSeat(cli)).toBe(false)
    expect(isApiSeat(remote)).toBe(false)
    expect(isApiSeat(blueprint)).toBe(false)
    expect(isApiSeat(null)).toBe(false)
    expect(isApiSeat(undefined)).toBe(false)

    // The wider reading adds blueprint seats but still excludes cli/remote.
    expect(isSwarmOwnedSeat(API_SEAT)).toBe(true)
    expect(isSwarmOwnedSeat(blueprint)).toBe(true)
    expect(isSwarmOwnedSeat(cli)).toBe(false)
    expect(isSwarmOwnedSeat(remote)).toBe(false)
    expect(isSwarmOwnedSeat(null)).toBe(false)
  })
})
