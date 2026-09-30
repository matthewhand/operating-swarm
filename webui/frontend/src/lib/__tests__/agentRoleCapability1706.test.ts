/**
 * #1706 D.14/D.15/D.16 — the FE role-capability decision point.
 *
 * The editor, the picker's option filter and the write guard all read these
 * functions, so they are the only place the FE can disagree with the backend's
 * `validate_role_for_kind`. The parity cases below are deliberately the same
 * matrix the backend test pins, because a divergence between the two is the
 * defect this issue is about — the editor would suppress a role the API
 * accepts, or advertise one the API refuses.
 */
import { describe, expect, it } from 'vitest'
import {
  isChatSeatId,
  ROLE_FIELD_UNAVAILABLE_REASON,
  ROLE_INCAPABLE_SEAT_KINDS,
  roleAllowedOnSeatKind,
  roleEditableForSeat,
  roleSeatKindFor,
} from '../agentRoles'

// The roles the editor can actually offer: the canonical set plus whatever is
// in the custom-role store. An unregistered slug is NOT in this list, because
// `normalizeAgentRole` resolves it to `default` — it is the absence of a role,
// and the backend never sees it either, because the FE only ever sends a value
// it could select.
const NON_DEFAULT_ROLES = [
  'support',
  'gate',
  'skeptic',
  'chief_of_staff',
  'engineer',
  'advisor',
] as const
const ROLE_CAPABLE_KINDS = ['api', 'blueprint', 'cli', 'remote'] as const

describe('#1706 — seat kinds that carry no role', () => {
  it('is exactly team and chat', () => {
    // If a future seat kind joins, this fails loudly instead of the editor
    // silently widening what it hides.
    expect([...ROLE_INCAPABLE_SEAT_KINDS].sort()).toEqual(['chat', 'team'])
  })

  it.each(NON_DEFAULT_ROLES)('rejects %s on every role-incapable seat', (role) => {
    for (const seatKind of ROLE_INCAPABLE_SEAT_KINDS) {
      expect(roleAllowedOnSeatKind(role, seatKind)).toBe(false)
    }
  })

  it('rejects a registered CUSTOM role on a team and a chat', () => {
    // A custom role is a first-class role, so the team/chat rule must cover it
    // too — otherwise the editor would hide the field but the rule would let a
    // custom role through on an api seat the backend calls a team.
    window.localStorage.setItem(
      'swarm_custom_roles',
      JSON.stringify([{ name: 'storefront_liaison', label: 'Liaison', aliases: [], allow_all: false, mechanism: 'none', mechanism_detail: '', css_class: '' }]),
    )
    try {
      for (const seatKind of ROLE_INCAPABLE_SEAT_KINDS) {
        expect(roleAllowedOnSeatKind('storefront_liaison', seatKind)).toBe(false)
      }
      // ...and it is still offered where a role IS allowed, so the rule is
      // about the seat and not about custom roles as a class.
      expect(roleAllowedOnSeatKind('storefront_liaison', 'api')).toBe(true)
    } finally {
      window.localStorage.removeItem('swarm_custom_roles')
    }
  })

  it.each(ROLE_INCAPABLE_SEAT_KINDS)('still allows clearing a role on %s', (seatKind) => {
    // `default` is the absence of a role, so it is valid everywhere —
    // otherwise a stale role could never be removed.
    expect(roleAllowedOnSeatKind('default', seatKind)).toBe(true)
    expect(roleAllowedOnSeatKind('', seatKind)).toBe(true)
    expect(roleAllowedOnSeatKind(null, seatKind)).toBe(true)
  })

  it('keeps #853: support stays API-only', () => {
    expect(roleAllowedOnSeatKind('support', 'api')).toBe(true)
    expect(roleAllowedOnSeatKind('support', 'blueprint')).toBe(true)
    expect(roleAllowedOnSeatKind('support', 'cli')).toBe(false)
    expect(roleAllowedOnSeatKind('support', 'remote')).toBe(false)
  })

  it('leaves ordinary roles unrestricted on role-capable seats', () => {
    for (const seatKind of ROLE_CAPABLE_KINDS) {
      for (const role of NON_DEFAULT_ROLES) {
        if (role === 'support' && (seatKind === 'cli' || seatKind === 'remote')) continue
        expect(roleAllowedOnSeatKind(role, seatKind)).toBe(true)
      }
    }
  })
})

describe('#1706 — classifying the seat a write addresses', () => {
  it.each([
    ['team:alpha', 'team'],
    ['chat:codey:conv-1', 'chat'],
    ['blueprint:chat:codey:conv-1', 'chat'],
    ['codey', 'api'],
    ['api_agent', 'api'],
    ['cli:grok', 'cli'],
    ['remote:herdr', 'remote'],
  ])('classifies %s as %s', (agentId, expected) => {
    expect(roleSeatKindFor(agentId)).toBe(expected)
  })

  it('detects a chat row by the rail prefix', () => {
    expect(isChatSeatId('chat:codey:conv-1')).toBe(true)
    expect(isChatSeatId('codey')).toBe(false)
  })

  it('does not mistake an agent merely named "teamster" for a team', () => {
    expect(roleSeatKindFor('teamster')).toBe('api')
    expect(roleEditableForSeat('teamster').editable).toBe(true)
  })

  it('lets a team/chat id win over a contradicting kind hint', () => {
    // A hint must not be able to relabel a team as an api seat, which would
    // advertise a role the backend then refuses.
    expect(roleSeatKindFor('team:alpha', 'api')).toBe('team')
    expect(roleSeatKindFor('chat:codey:c', 'api')).toBe('chat')
  })

  it('reads cli / remote prefixes rather than defaulting them to api', () => {
    // A wrong default is not inert: it would put a remote seat in the api
    // bucket, where `roleAllowedOnSeatKind` offers the support role the
    // backend refuses (#853).
    expect(roleSeatKindFor('remote:herdr')).toBe('remote')
    expect(roleSeatKindFor('cli:grok')).toBe('cli')
    expect(roleAllowedOnSeatKind('support', roleSeatKindFor('remote:herdr'))).toBe(false)
    expect(roleAllowedOnSeatKind('support', roleSeatKindFor('cli:grok'))).toBe(false)
  })
})

describe('#1706 — what the editor does with the answer', () => {
  it('reports editable with no reason for an ordinary seat', () => {
    expect(roleEditableForSeat('codey', 'api')).toEqual({
      editable: true,
      seatKind: 'api',
      reason: '',
    })
  })

  it('reports a reason for a team and for a chat', () => {
    for (const agentId of ['team:alpha', 'chat:codey:conv-1']) {
      const result = roleEditableForSeat(agentId)
      expect(result.editable).toBe(false)
      expect(result.reason).toBe(ROLE_FIELD_UNAVAILABLE_REASON)
    }
  })
})
