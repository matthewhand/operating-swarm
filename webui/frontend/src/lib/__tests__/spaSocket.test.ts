/**
 * ADR-017 PR-3 — spaSocket singleton contracts (REQ-925 / #1118).
 *
 * Pinned against a fake WebSocket so no test touches the network:
 * - refcounted subscriptions share one socket + one server session
 * - tagged `spa.frame` envelopes route to the right conversation's listeners
 * - releasing a chat does NOT unsubscribe (sticky sessions — #1118)
 * - reconnect replays `subscribe` for every live conversation
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  activeSpaConversations,
  onSpaStatus,
  resetSpaSocketForTests,
  sendSpaChat,
  spaStatus,
  subscribeSpa,
} from '../spaSocket'

class FakeWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  send = vi.fn((data: string) => {
    this.sent.push(data)
  })
  close = vi.fn(() => {
    this.readyState = 3
    this.onclose?.()
  })

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  deliver(envelope: unknown) {
    this.onmessage?.({ data: JSON.stringify(envelope) })
  }
}

describe('spaSocket singleton', () => {
  beforeEach(() => {
    resetSpaSocketForTests()
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    resetSpaSocketForTests()
    vi.unstubAllGlobals()
  })

  function lastSocket(): FakeWebSocket {
    const ws = FakeWebSocket.instances.at(-1)
    expect(ws).toBeDefined()
    return ws as FakeWebSocket
  }

  it('shares one socket across conversations and routes frames by conversationId', () => {
    const gotA: string[] = []
    const gotB: string[] = []
    subscribeSpa('conv-A', (event) => gotA.push(event.kind))
    subscribeSpa('conv-B', (event) => gotB.push(event.kind))
    const ws = lastSocket()
    ws.open()

    ws.deliver({ kind: 'spa.frame', conversationId: 'conv-A', data: '<div>x</div>' })
    ws.deliver({ kind: 'spa.frame', conversationId: 'conv-B', data: '<div>y</div>' })

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(gotA).toEqual(['unknown'])
    expect(gotB).toEqual(['unknown'])
    expect(activeSpaConversations().sort()).toEqual(['conv-A', 'conv-B'])
  })

  it('refcounts duplicate subscriptions and releases listeners cleanly', () => {
    const l1 = vi.fn()
    const l2 = vi.fn()
    const sub1 = subscribeSpa('conv-1', l1)
    const sub2 = subscribeSpa('conv-1', l2)
    const ws = lastSocket()
    ws.open()

    sub1.release()
    ws.deliver({ kind: 'spa.frame', conversationId: 'conv-1', data: '<div>x</div>' })
    expect(l2).toHaveBeenCalled()
    expect(l1).not.toHaveBeenCalled()

    sub2.release()
    expect(activeSpaConversations()).toEqual([])
  })

  it('release does NOT unsubscribe the server session (sticky, #1118)', () => {
    const sub = subscribeSpa('conv-1', () => {})
    const ws = lastSocket()
    ws.open()
    ws.sent.length = 0

    sub.release()
    expect(ws.sent).toEqual([]) // no unsubscribe frame — session stays live

    // re-mounting adopts the same session with a fresh subscribe
    subscribeSpa('conv-1', () => {})
    expect(ws.sent).toEqual([
      JSON.stringify({ kind: 'subscribe', conversationId: 'conv-1', blueprint: undefined }),
    ])
  })

  it('reconnect replays subscribe for every live conversation', () => {
    subscribeSpa('conv-A', () => {}, 'bp-a')
    subscribeSpa('conv-B', () => {})
    const first = lastSocket()
    first.open()
    first.sent.length = 0

    first.onclose?.()
    expect(spaStatus()).toBe('failed')

    const second = lastSocket()
    second.open()
    expect(second.sent).toEqual([
      JSON.stringify({ kind: 'subscribe', conversationId: 'conv-A', blueprint: 'bp-a' }),
      JSON.stringify({ kind: 'subscribe', conversationId: 'conv-B', blueprint: undefined }),
    ])
  })

  it('sendSpaChat wraps the legacy frame in chat.send', () => {
    subscribeSpa('conv-1', () => {})
    const ws = lastSocket()
    ws.open()
    ws.sent.length = 0

    sendSpaChat('conv-1', JSON.stringify({ message: 'hi', params: { cli: 'omp' } }))
    expect(JSON.parse(ws.sent[0])).toEqual({
      kind: 'chat.send',
      conversationId: 'conv-1',
      message: 'hi',
      params: { cli: 'omp' },
    })
  })

  it('status listeners see connecting → open → failed on drop', () => {
    const statuses: string[] = []
    onSpaStatus((s) => statuses.push(s))
    subscribeSpa('conv-1', () => {})
    const ws = lastSocket()
    expect(statuses).toEqual(['connecting'])
    ws.open()
    expect(statuses.at(-1)).toBe('open')
    ws.onclose?.()
    expect(statuses.at(-1)).toBe('failed')
  })
})
