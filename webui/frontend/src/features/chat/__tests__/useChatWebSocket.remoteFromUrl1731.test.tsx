/**
 * #1731 — is the `remoteFromUrl` dependency in `useChatWebSocket`'s effect array
 * actually LOAD-BEARING, or is it decoration?
 *
 * The issue asked for this explicitly: "a test that passes with and without the
 * fix is decoration." The preceding guard file
 * (`useChatWebSocket.blueprint1731.test.tsx`) pins WHAT blueprint the hook
 * picks for each shape — all of which passes either way, by design.
 *
 * This file isolates the dependency itself: the ONLY thing that changes is
 * `remoteFromUrl`, with `conversationId`, `runtimeBlueprint`, `teamFromUrl` and
 * `connectAttempt` all held constant. That is the exact case the dep array
 * exists to handle, because setup reads `remoteFromUrl` SYNCHRONOUSLY:
 *
 *   const blueprint = teamFromUrl ? undefined
 *     : remoteFromUrl ? 'remote_harness'
 *     : runtimeBlueprint || undefined
 *
 * A ref would be useless there (there is no deferred callback to read it in),
 * so a dependency is the only correct mechanism — but only if it is present.
 * If the effect does not re-run, the previously-registered `remote_harness`
 * blueprint is left in `registry.blueprints` and the NEW remote's conversation
 * is never subscribed at all, because `subscribeSpa` sends its `subscribe`
 * envelope only on the first subscription for a conversation id.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import type { ChatWsEvent } from '../../../lib/chatWs'
import type { SpaStatus, SpaSubscription } from '../../../lib/spaSocket'

const subscriptions: Array<{ conversationId: string; blueprint: string | undefined }> = []

vi.mock('../../../lib/spaSocket', () => ({
  spaStatus: () => 'open' as SpaStatus,
  spaLastCloseCode: () => null,
  onSpaStatus: (): SpaSubscription => ({ release: () => {} }),
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

/** Mount with every option pinned, so ONE prop can be varied in isolation. */
function mountRemote(remoteFromUrl: string) {
  return renderHook(
    (props: { remoteFromUrl: string }) =>
      useChatWebSocket({
        connectAttempt: 0,
        conversationId: 'conv-1',
        runtimeBlueprint: 'cli_agent',
        teamFromUrl: '',
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
    { initialProps: { remoteFromUrl } },
  )
}

beforeEach(() => {
  subscriptions.length = 0
})

describe('#1731 remoteFromUrl is load-bearing', () => {
  it('a ?remote= change alone re-runs setup and re-subscribes', () => {
    // Entering a remote seat: no other dep changes.
    const { rerender } = mountRemote('')
    expect(subscriptions).toHaveLength(1)
    expect(subscriptions[0].blueprint).toBe('cli_agent')

    // `?remote=a` — remoteFromUrl is the ONLY value that moved.
    rerender({ remoteFromUrl: 'hermes' })

    // This is the assertion that fails when remoteFromUrl is not a dependency:
    // the effect never re-runs, so no subscription carries the remote
    // blueprint and the operator sits on a socket bound to the local runtime
    // blueprint while looking at a remote seat.
    expect(subscriptions).toHaveLength(2)
    expect(subscriptions[1]).toEqual({ conversationId: 'conv-1', blueprint: 'remote_harness' })
  })

  it('switching between two remotes keeps the remote blueprint on both', () => {
    const { rerender } = mountRemote('hermes')
    expect(subscriptions[0].blueprint).toBe('remote_harness')

    rerender({ remoteFromUrl: 'hermes-2' })

    expect(subscriptions).toHaveLength(2)
    expect(subscriptions[1].blueprint).toBe('remote_harness')
  })

  it('leaving a remote seat returns to the runtime blueprint', () => {
    const { rerender } = mountRemote('hermes')
    expect(subscriptions[0].blueprint).toBe('remote_harness')

    rerender({ remoteFromUrl: '' })

    // Back on a local seat the stale 'remote_harness' must not persist: a local
    // agent asking to be served by the remote harness blueprint is its own bug.
    expect(subscriptions).toHaveLength(2)
    expect(subscriptions[1].blueprint).toBe('cli_agent')
  })
})
