/**
 * #1731 — `useChatWebSocket` reads `remoteFromUrl` at setup time to choose the
 * subscription's blueprint, and nothing pinned that.
 *
 * The setup is synchronous:
 *
 *   const blueprint = teamFromUrl ? undefined
 *     : remoteFromUrl ? 'remote_harness'
 *     : runtimeBlueprint || undefined
 *
 * so a ref would be useless there and a dependency is the correct fix (a
 * deferred callback could read a ref; setup cannot). The issue is that the
 * dependency was unverified — and while writing the coverage, the *load-bearing*
 * question was checked rather than assumed: the mock below records the
 * `blueprint` argument `subscribeSpa` actually receives, so these tests observe
 * the value rather than the source array.
 *
 * These are DELIBERATE NON-REGRESSION GUARDS. They are expected to pass both
 * before and after any further change: they pin behaviour that is already
 * correct, and their job is to make a future refactor of the dep array red.
 * The fail-before/pass-after proof for the *fix* this work delivered is in
 * `useChatWebSocket.remoteFromUrl1731.test.tsx`; the one assertion here that is
 * not a guard is noted inline.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import type { ChatWsEvent } from '../../../lib/chatWs'
import type { SpaStatus, SpaStatusListener, SpaSubscription } from '../../../lib/spaSocket'

/** Every `subscribeSpa` call, with the blueprint argument the hook passed. */
const subscriptions: Array<{ conversationId: string; blueprint: string | undefined }> = []

const statusListeners = new Set<SpaStatusListener>()

// The whole socket surface is faked. The real module holds a module-level
// singleton, which is precisely the shared state this hook must not rebuild on
// every seat switch, so statuses are delivered by hand rather than by a socket.
vi.mock('../../../lib/spaSocket', () => ({
  spaStatus: () => 'open' as SpaStatus,
  spaLastCloseCode: () => null,
  onSpaStatus: (listener: SpaStatusListener): SpaSubscription => {
    statusListeners.add(listener)
    return {
      release: () => {
        statusListeners.delete(listener)
      },
    }
  },
  // #1731: the blueprint argument is RECORDED, not discarded. Without this the
  // remote path is unobservable — the hook can pass anything and the test
  // cannot tell.
  subscribeSpa: (
    conversationId: string,
    _listener: (event: ChatWsEvent) => void,
    blueprint?: string,
  ): SpaSubscription => {
    subscriptions.push({ conversationId, blueprint })
    return { release: () => {} }
  },
  sendSpaChat: () => {},
}))

const { useChatWebSocket } = await import('../useChatWebSocket')

function mount(overrides: Record<string, unknown> = {}) {
  return renderHook(
    (props: Record<string, unknown>) =>
      useChatWebSocket({
        connectAttempt: 0,
        conversationId: 'conv-1',
        runtimeBlueprint: '',
        teamFromUrl: '',
        remoteFromUrl: '',
        threadKey: 't1',
        wsRef: { current: null },
        handleWsEventRef: { current: () => {} },
        notifyCtxRef: { current: { agentId: null, agentName: '' } },
        setStatus: vi.fn(),
        setAuthRejected: vi.fn(),
        setAwaitingAssistant: vi.fn(),
        setThreads: vi.fn(),
        setConnectAttempt: vi.fn(),
        ...props,
      } as never),
    { initialProps: overrides },
  )
}

beforeEach(() => {
  subscriptions.length = 0
  statusListeners.clear()
})

afterEach(() => {
  subscriptions.length = 0
  statusListeners.clear()
})

describe('#1731 useChatWebSocket blueprint selection', () => {
  it('subscribes a remote seat with the remote_harness blueprint', () => {
    mount({ remoteFromUrl: 'hermes', conversationId: 'remote-hermes' })

    expect(subscriptions).toHaveLength(1)
    // The recorded argument, asserted by value. This is the whole point of the
    // issue: the argument was previously thrown away by the mock.
    expect(subscriptions[0].blueprint).toBe('remote_harness')
    expect(subscriptions[0].conversationId).toBe('remote-hermes')
  })

  it('a ?remote= change re-subscribes with remote_harness', () => {
    const { rerender } = mount({ remoteFromUrl: 'hermes', conversationId: 'remote-hermes' })
    rerender({ remoteFromUrl: 'hermes-2', conversationId: 'remote-hermes-2' } as never)

    expect(subscriptions.map((s) => s.conversationId)).toEqual([
      'remote-hermes',
      'remote-hermes-2',
    ])
    // Both subscriptions carry the remote blueprint — a remote seat never
    // falls back to the runtime blueprint just because the id changed.
    expect(subscriptions.every((s) => s.blueprint === 'remote_harness')).toBe(true)
  })

  it('a team seat still suppresses the blueprint entirely', () => {
    mount({ teamFromUrl: 'team-9', conversationId: 'team-9' })

    expect(subscriptions).toHaveLength(1)
    // undefined, not 'remote_harness' and not the runtime blueprint: a team
    // seat subscribes with no blueprint at all.
    expect(subscriptions[0].blueprint).toBeUndefined()
  })

  it('a team seat suppresses the blueprint even when a remote is also set', () => {
    mount({ teamFromUrl: 'team-9', remoteFromUrl: 'hermes', conversationId: 'team-9' })

    expect(subscriptions[0].blueprint).toBeUndefined()
  })

  it('a plain runtime blueprint is still honoured', () => {
    mount({ runtimeBlueprint: 'cli_agent', conversationId: 'conv-1' })

    expect(subscriptions[0].blueprint).toBe('cli_agent')
  })

  it('an empty runtime blueprint subscribes with no blueprint', () => {
    mount({ runtimeBlueprint: '', conversationId: 'conv-1' })

    expect(subscriptions[0].blueprint).toBeUndefined()
  })
})
