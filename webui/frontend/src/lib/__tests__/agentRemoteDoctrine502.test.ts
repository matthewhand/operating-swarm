/**
 * REQ-904 / #502 — the two-axis doctrine, as invariant tests.
 *
 * Axis 1 **Identity**: which agent am I talking to? Owned by the route/URL +
 * session selection. Changing it may navigate and reset the session.
 * Axis 2 **Provider binding**: which backend does *this* agent use? A
 * persisted property of that agent — `saveAgentRemoteBinding(agentId, …)`,
 * never keyed by the provider's own id, never read from the URL. Changing it
 * must be **inert**: same agent, same thread, same session, same URL.
 *
 * Canonical illustration: agent *Herdr* bound to remote *OpenMousBot* means
 * "Herdr uses OpenMousBot" — never "switch me to OpenMousBot".
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  AGENT_REMOTE_BINDINGS_KEY,
  loadAgentRemoteBinding,
  resolveAgentBindingSubject,
  resolveBoundRemoteId,
  saveAgentRemoteBinding,
} from '../agentRemote'

describe('#502 resolveAgentBindingSubject — the binding key is the agent, never the provider', () => {
  beforeEach(() => {
    localStorage.removeItem(AGENT_REMOTE_BINDINGS_KEY)
  })
  afterEach(() => {
    localStorage.removeItem(AGENT_REMOTE_BINDINGS_KEY)
  })

  it('a named agent binds under its own id', () => {
    expect(resolveAgentBindingSubject({ selectedBlueprint: 'herdr' })).toBe('herdr')
  })

  it('viewing a remote seat never makes the provider its own binding subject', () => {
    // The core defect: `?remote=omb` used to make bindingAgentId === 'omb' —
    // the remote bound to itself. There must be no key in that space.
    expect(resolveAgentBindingSubject({ remoteFromUrl: 'omb' })).toBe('')
    expect(
      resolveAgentBindingSubject({ remoteFromUrl: 'omb', selectedBlueprint: 'herdr' }),
    ).toBe('')
  })

  it('a remote-kind *agent* opened by name still binds under its agent id', () => {
    // `remote:herdr` is an identity (a remote seat the user owns), and it is
    // still an agent — it may have its own provider binding.
    expect(resolveAgentBindingSubject({ selectedBlueprint: 'remote:herdr' })).toBe('remote:herdr')
  })
})

describe('#502 resolveBoundRemoteId — viewing is not configuring', () => {
  it('a persisted agent binding wins over the URL remote', () => {
    expect(
      resolveBoundRemoteId({
        remoteFromUrl: 'omb',
        persisted: { id: 'trueforge', kind: 'trueforge' },
        configuredIds: ['omb', 'trueforge'],
      }),
    ).toBe('trueforge')
  })

  it('the URL remote still resolves when no binding exists (view of a remote seat)', () => {
    expect(
      resolveBoundRemoteId({
        remoteFromUrl: 'omb',
        persisted: null,
        configuredIds: ['omb'],
      }),
    ).toBe('omb')
  })

  it('stale persisted ids still fall through to empty (repair state preserved)', () => {
    expect(
      resolveBoundRemoteId({
        persisted: { id: 'gone', kind: 'hermes' },
        configuredIds: ['omb'],
      }),
    ).toBe('')
  })
})

describe('#502 round-trip — the key-space bug that fails today', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_REMOTE_BINDINGS_KEY)
  })

  it('save while viewing a remote seat under a named agent → read back by agent id', () => {
    // The reported symptom: "I set it and it didn't stick." The old wiring
    // wrote under the remote id when ?remote= was present, so the agent's own
    // read could never find it. One key space: the agent id.
    saveAgentRemoteBinding('herdr', { id: 'omb', kind: 'omb' })
    expect(loadAgentRemoteBinding('herdr')).toEqual({ id: 'omb', kind: 'omb' })
    // And the write must never have created a self-binding under the provider.
    expect(loadAgentRemoteBinding('omb')).toBeNull()
  })
})
