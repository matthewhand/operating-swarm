/**
 * #1202 — the ONE declared predicate behind the navbar Agent / Session
 * pickers. CLI supports Sessions but not Agents; API/blueprint supports both;
 * Remote supports Agents, Sessions only when the remote row declares it;
 * Team supports both. A declared axis outranks the kind matrix (ADR-016).
 */
import { describe, expect, it } from 'vitest'
import { navbarSeatCapabilities } from '../seatCapabilities'

describe('#1202 navbarSeatCapabilities', () => {
  it('CLI host supports Sessions but not Agents', () => {
    const caps = navbarSeatCapabilities({ kind: 'cli', isCli: true, providerName: 'grok' })
    expect(caps.agents.enabled).toBe(false)
    expect(caps.agents.reason).toBe('Agent selection is not supported by grok')
    expect(caps.sessions.enabled).toBe(true)
    expect(caps.sessions.reason).toBe('')
  })

  it('API blueprint supports both', () => {
    const caps = navbarSeatCapabilities({ kind: 'api', providerName: 'codey' })
    expect(caps.agents.enabled).toBe(true)
    expect(caps.sessions.enabled).toBe(true)
  })

  it('remote supports Agents; Sessions only when the row declares capabilities.sessions', () => {
    const stateless = navbarSeatCapabilities({ kind: 'remote', providerName: 'Rakazo' })
    expect(stateless.agents.enabled).toBe(true)
    expect(stateless.sessions.enabled).toBe(false)
    expect(stateless.sessions.reason).toBe(
      'Rakazo is stateless and does not support persistent sessions',
    )

    const stateful = navbarSeatCapabilities({
      kind: 'remote',
      remoteSessions: true,
      providerName: 'TrueForge',
    })
    expect(stateful.agents.enabled).toBe(true)
    expect(stateful.sessions.enabled).toBe(true)
  })

  it('hermes: a declared session-capable remote enables Sessions with no reason', () => {
    const caps = navbarSeatCapabilities({
      kind: 'remote',
      remoteSessions: true,
      providerName: 'Hermes Agent (dev-worker-gpu)',
    })
    expect(caps.sessions).toEqual({ enabled: true, reason: '' })
    expect(caps.agents.enabled).toBe(true)
  })

  it('Team supports both', () => {
    const caps = navbarSeatCapabilities({ kind: 'team', providerName: 'Demo Team' })
    expect(caps.agents.enabled).toBe(true)
    expect(caps.sessions.enabled).toBe(true)
  })

  it('a declared axis outranks the kind-derived matrix', () => {
    const caps = navbarSeatCapabilities({
      kind: 'api',
      declared: { sessions: { enabled: false, reason: 'declared off' } },
    })
    expect(caps.sessions).toEqual({ enabled: false, reason: 'declared off' })
    expect(caps.agents.enabled).toBe(true)
  })
})
