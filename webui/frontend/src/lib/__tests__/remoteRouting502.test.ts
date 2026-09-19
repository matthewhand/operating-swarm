/**
 * REQ-904 / #502 — provider changes are **inert**; identity changes are not.
 *
 * `applyRemoteRoutingChange` is the single place the navbar's remote picker
 * decision lives, so the two axes cannot be re-fused by a future edit:
 *   - a provider pick (changed === 'agent', no remote seat in the URL)
 *     persists the agent's binding and touches NOTHING else — no `?remote=`
 *     write, no `session` delete, no navigation;
 *   - a session pick (changed === 'model') may set `session`;
 *   - while viewing a remote *seat* (?remote= in the URL) the pick is an
 *     identity change — the existing navigate-and-reset behaviour is
 *     preserved and pinned.
 */
import { describe, expect, it } from 'vitest'
import { applyRemoteRoutingChange } from '../remoteRouting'

const CATALOG = [
  { id: 'omb', kind: 'omb' },
  { id: 'trueforge', kind: 'trueforge' },
]

describe('#502 applyRemoteRoutingChange — provider axis is inert', () => {
  it('a provider pick writes the binding and no URL keys', () => {
    const result = applyRemoteRoutingChange({
      next: { agent: 'trueforge', changed: 'agent' },
      bindingAgentId: 'remote:herdr',
      configured: CATALOG,
    })
    expect(result.binding).toEqual({ id: 'trueforge', kind: 'trueforge' })
    expect(result.setRemote).toBeUndefined()
    expect(result.setSession).toBeUndefined()
    expect(result.deleteSession).toBe(false)
  })

  it('clearing the provider clears the binding and no URL keys', () => {
    const result = applyRemoteRoutingChange({
      next: { agent: '', changed: 'agent' },
      bindingAgentId: 'remote:herdr',
      configured: CATALOG,
    })
    expect(result.binding).toBeNull()
    expect(result.setRemote).toBeUndefined()
    expect(result.deleteSession).toBe(false)
  })

  it('a session pick sets only the session key', () => {
    const result = applyRemoteRoutingChange({
      next: { agent: 'omb', changed: 'model', model: 'bot-7' },
      bindingAgentId: 'remote:herdr',
      configured: CATALOG,
    })
    expect(result.setSession).toBe('bot-7')
    expect(result.setRemote).toBeUndefined()
    expect(result.deleteSession).toBe(false)
  })

  it('never writes a binding when the URL carries a remote seat (no self-binding)', () => {
    const result = applyRemoteRoutingChange({
      next: { agent: 'trueforge', changed: 'agent' },
      bindingAgentId: '',
      remoteFromUrl: 'omb',
      configured: CATALOG,
    })
    expect(result.binding).toBeUndefined()
  })
})

describe('#502 applyRemoteRoutingChange — identity axis preserved', () => {
  it('viewing a remote seat: the pick navigates and resets the session (pinned)', () => {
    const result = applyRemoteRoutingChange({
      next: { agent: 'trueforge', changed: 'agent' },
      bindingAgentId: '',
      remoteFromUrl: 'omb',
      configured: CATALOG,
    })
    expect(result.setRemote).toBe('trueforge')
    expect(result.deleteSession).toBe(true)
  })

  it('viewing a remote seat: a session pick sets the session', () => {
    const result = applyRemoteRoutingChange({
      next: { agent: 'omb', changed: 'model', model: 'bot-9' },
      bindingAgentId: '',
      remoteFromUrl: 'omb',
      configured: CATALOG,
    })
    expect(result.setRemote).toBe('omb')
    expect(result.setSession).toBe('bot-9')
  })
})
