/**
 * #532 / REQ-919 — role wire-up store: edges persist per provider+role,
 * self-heal on junk, and announce changes so editors and pills stay in sync.
 */
import { describe, expect, it, beforeEach } from 'vitest'
import {
  ROLE_CONSUMERS_CHANGED_EVENT,
  ROLE_CONSUMERS_KEY,
  loadAllRoleConsumerEdges,
  loadConsumerEdges,
  loadProviderEdges,
  loadRoleConsumers,
  providersWithConsumers,
  saveRoleConsumers,
  toggleRoleConsumer,
} from '../roleConsumers'

describe('roleConsumers (#532)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('round-trips a wire-up and reads it back from both sides', () => {
    expect(saveRoleConsumers('charles', 'suggestions', ['codey', 'stewie'])).toEqual([
      'codey',
      'stewie',
    ])
    expect(loadRoleConsumers('charles', 'suggestions')).toEqual(['codey', 'stewie'])
    expect(loadRoleConsumers('charles', 'skeptic')).toEqual([])
    expect(loadRoleConsumers('nobody', 'suggestions')).toEqual([])
    expect(loadProviderEdges('charles')).toEqual([
      { providerId: 'charles', role: 'suggestions', consumerId: 'codey' },
      { providerId: 'charles', role: 'suggestions', consumerId: 'stewie' },
    ])
    expect(loadConsumerEdges('codey')).toEqual([
      { providerId: 'charles', role: 'suggestions', consumerId: 'codey' },
    ])
    expect(providersWithConsumers()).toEqual(['charles'])
  })

  it('toggles without duplicating and unwires at zero consumers', () => {
    toggleRoleConsumer('charles', 'skeptic', 'codey')
    toggleRoleConsumer('charles', 'skeptic', 'codey')
    expect(toggleRoleConsumer('charles', 'skeptic', 'codey')).toEqual(['codey'])
    expect(toggleRoleConsumer('charles', 'skeptic', 'codey')).toEqual([])
    expect(window.localStorage.getItem(ROLE_CONSUMERS_KEY)).toBeNull()
  })

  it('rejects self-wiring and junk on both write and read', () => {
    expect(saveRoleConsumers('charles', 'suggestions', ['charles', '', '  '])).toEqual([])
    expect(loadRoleConsumers('', 'suggestions')).toEqual([])
    expect(loadRoleConsumers('charles', '')).toEqual([])
    window.localStorage.setItem(
      ROLE_CONSUMERS_KEY,
      JSON.stringify({ charles: { suggestions: ['charles', 'codey', 42, null] }, junk: 'nope' }),
    )
    expect(loadRoleConsumers('charles', 'suggestions')).toEqual(['codey'])
    expect(loadAllRoleConsumerEdges()).toEqual([
      { providerId: 'charles', role: 'suggestions', consumerId: 'codey' },
    ])
  })

  it('fires a change event on save', () => {
    let fired = 0
    const listener = () => {
      fired += 1
    }
    window.addEventListener(ROLE_CONSUMERS_CHANGED_EVENT, listener)
    try {
      saveRoleConsumers('a', 'advisor', ['b'])
      expect(fired).toBe(1)
    } finally {
      window.removeEventListener(ROLE_CONSUMERS_CHANGED_EVENT, listener)
    }
  })
})
