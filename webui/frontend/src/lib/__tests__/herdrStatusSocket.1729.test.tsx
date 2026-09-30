/**
 * #1729 — the Herdr status socket client.
 *
 * Herdr seat status rides a dedicated push-only socket, NOT the SPA multiplex.
 * The multiplex is a strict per-conversation transport whose contract is that
 * every frame is a reply to something the client asked for; a status frame
 * there would interleave frames nobody requested. These tests pin the client
 * half of the separation, plus the socket lifecycle (one connection, clean
 * teardown, bounded reconnect).
 */

import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  herdrStatusSocketState,
  onHerdrStatusState,
  resetHerdrStatusSocketForTests,
  subscribeHerdrStatusFeed,
} from '../herdrStatusSocket'
import { useHerdrStatusFeed } from '../useHerdrStatusFeed'
import { herdrStatusFor, resetHerdrStatusStore } from '../herdrStatus'
import { isAgentUnread } from '../unreadAgents'

class FakeWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  send = vi.fn((data: string) => {
    this.sent.push(data)
  })
  close = vi.fn((code?: number) => {
    this.readyState = 3
    this.onclose?.({ code: code ?? 1000 })
  })

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  deliver(payload: unknown) {
    act(() => {
      this.onmessage?.({ data: JSON.stringify(payload) })
    })
  }
}

function Probe() {
  useHerdrStatusFeed()
  return null
}

describe('#1729 herdr status socket', () => {
  beforeEach(() => {
    localStorage.clear()
    resetHerdrStatusStore()
    resetHerdrStatusSocketForTests()
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    cleanup()
    resetHerdrStatusSocketForTests()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  function lastSocket(): FakeWebSocket {
    const ws = FakeWebSocket.instances.at(-1)
    expect(ws).toBeDefined()
    return ws as FakeWebSocket
  }

  it('connects to the dedicated status socket, not the chat mux', () => {
    render(<Probe />)
    // The separation, asserted: no chat socket is opened for a status feed.
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(lastSocket().url).toContain('/ws/herdr-status/')
    expect(lastSocket().url).not.toContain('/ws/spa/')
  })

  it('reports the socket lifecycle to subscribers', () => {
    const states: string[] = []
    const subscription = onHerdrStatusState((state) => states.push(state))
    render(<Probe />)
    expect(states).toContain('connecting')
    lastSocket().open()
    expect(states).toContain('open')
    subscription.release()
  })

  it('folds a status event into the store and marks unread on finish', () => {
    render(<Probe />)
    lastSocket().deliver({
      type: 'herdr_status',
      seat_id: 'herdr:w3:p1',
      target: 'w3:p1',
      status: 'done',
      herdr_status: 'done',
      mark_unread: true,
    })
    expect(herdrStatusFor('herdr:w3:p1')).toBe('finished')
    // The reuse claim, end to end: the existing rail store is what lights.
    expect(isAgentUnread('herdr:w3:p1')).toBe(true)
  })

  it('flags a waiting agent for attention without marking it unread', () => {
    render(<Probe />)
    lastSocket().deliver({
      type: 'herdr_status',
      seat_id: 'herdr:w3:p1',
      status: 'waiting',
      herdr_status: 'blocked',
      needs_input: true,
    })
    expect(herdrStatusFor('herdr:w3:p1')).toBe('waiting')
    expect(isAgentUnread('herdr:w3:p1')).toBe(false)
  })

  it('accepts a frame carrying only the OS status', () => {
    render(<Probe />)
    lastSocket().deliver({ type: 'herdr_status', seat_id: 'herdr:a', status: 'finished' })
    expect(herdrStatusFor('herdr:a')).toBe('finished')
  })

  it('drops a malformed or non-JSON frame without touching the store', () => {
    render(<Probe />)
    for (const payload of [
      { type: 'something_else', seat_id: 'herdr:x' },
      { type: 'herdr_status' },
      null,
    ]) {
      lastSocket().deliver(payload)
    }
    act(() => {
      lastSocket().onmessage?.({ data: 'not json at all' })
    })
    expect(herdrStatusFor('herdr:x')).toBe('unknown')
  })

  it('stops folding once the feed unmounts', () => {
    render(<Probe />)
    const socket = lastSocket()
    cleanup()
    socket.deliver({ type: 'herdr_status', seat_id: 'herdr:w3:p1', status: 'done' })
    // A leaked subscription would keep mutating a store nothing renders.
    expect(herdrStatusFor('herdr:w3:p1')).toBe('unknown')
  })

  it('shares one socket across subscribers', () => {
    const first = subscribeHerdrStatusFeed(() => {})
    const second = subscribeHerdrStatusFeed(() => {})
    const socket = lastSocket()
    socket.open()
    // N mounted surfaces must not mean N sockets.
    expect(FakeWebSocket.instances).toHaveLength(1)
    first.release()
    // Still a live subscriber, so the socket stays up.
    expect(herdrStatusSocketState()).toBe('open')
    expect(socket.close).not.toHaveBeenCalled()
    second.release()
    expect(herdrStatusSocketState()).toBe('closed')
  })

  it('closes the socket when the last subscriber releases', () => {
    const subscription = subscribeHerdrStatusFeed(() => {})
    const socket = lastSocket()
    socket.open()
    subscription.release()
    expect(socket.close).toHaveBeenCalled()
    expect(herdrStatusSocketState()).toBe('closed')
  })

  it('releases twice without throwing', () => {
    const subscription = subscribeHerdrStatusFeed(() => {})
    subscription.release()
    expect(() => subscription.release()).not.toThrow()
  })

  it('a listener that throws does not starve the others', () => {
    const seen: string[] = []
    const bad = subscribeHerdrStatusFeed(() => {
      throw new Error('boom')
    })
    const good = subscribeHerdrStatusFeed((frame) => seen.push(frame.seat_id))
    lastSocket().deliver({ type: 'herdr_status', seat_id: 'herdr:a', status: 'idle' })
    expect(seen).toEqual(['herdr:a'])
    bad.release()
    good.release()
  })

  it('reconnects on an unexpected drop', () => {
    vi.useFakeTimers()
    const subscription = subscribeHerdrStatusFeed(() => {})
    const first = lastSocket()
    first.open()
    act(() => {
      first.onclose?.({ code: 1006 })
    })
    expect(herdrStatusSocketState()).toBe('failed')
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(FakeWebSocket.instances.length).toBeGreaterThan(1)
    subscription.release()
  })

  it('does not reconnect after an auth rejection', () => {
    vi.useFakeTimers()
    const subscription = subscribeHerdrStatusFeed(() => {})
    const socket = lastSocket()
    socket.open()
    act(() => {
      socket.onclose?.({ code: 4401 })
    })
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    // Hammering a rejected socket is not helpful; the Sign-in CTA drives it.
    expect(FakeWebSocket.instances).toHaveLength(1)
    subscription.release()
  })

  it('does not reconnect after a deliberate release', () => {
    vi.useFakeTimers()
    const subscription = subscribeHerdrStatusFeed(() => {})
    const socket = lastSocket()
    socket.open()
    subscription.release()
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('a constructor that throws fails fast instead of throwing at the caller', () => {
    class Exploding {
      constructor() {
        throw new Error('blocked by the sandbox')
      }
      static OPEN = 1
      static CONNECTING = 0
    }
    vi.stubGlobal('WebSocket', Exploding)
    const subscription = subscribeHerdrStatusFeed(() => {})
    expect(herdrStatusSocketState()).toBe('failed')
    subscription.release()
  })
})
