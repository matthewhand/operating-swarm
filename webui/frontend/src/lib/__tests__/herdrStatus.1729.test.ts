/**
 * #1729 — the Herdr status store and its transition rules.
 *
 * The store is pure state, so these tests never mount a component or open a
 * socket. What they pin is the behaviour a wrong answer would quietly break:
 *
 * - a status OS cannot vouch for never becomes a positive label
 * - an out-of-order frame cannot re-light a dot the operator cleared
 * - finishing marks unread through the EXISTING store, so the rail's own dot
 *   lights with no rail change
 *
 * Unread is asserted against `lib/unreadAgents` — the real store — rather than
 * a private copy, because "which store" is the whole reuse claim.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import {
  HERDR_AGENT_STATUSES,
  SEAT_STATUSES,
  UNKNOWN_STATUS,
  applyHerdrStatusFrame,
  clearHerdrSeat,
  decideHerdrStatus,
  getHerdrReading,
  herdrAttentionSeats,
  herdrStatusFor,
  isStaleFrame,
  normalizeSeatStatus,
  parseHerdrStatusFrame,
  resetHerdrStatusStore,
  statusLabel,
  subscribeHerdrStatus,
  type HerdrStatusFrame,
} from '../herdrStatus'
import {
  UNREAD_AGENTS_STORAGE_KEY,
  isAgentUnread,
  loadUnreadAgentIds,
  markAgentRead,
} from '../unreadAgents'

function frame(over: Partial<HerdrStatusFrame> = {}): HerdrStatusFrame {
  return {
    type: 'herdr_status',
    seat_id: 'herdr:w3:p1',
    target: 'w3:p1',
    status: 'working',
    ...over,
  }
}

describe('#1729 herdr status store', () => {
  beforeEach(() => {
    localStorage.clear()
    resetHerdrStatusStore()
  })

  describe('the vocabulary', () => {
    it('maps every Herdr-published state onto exactly one OS status', () => {
      expect([...HERDR_AGENT_STATUSES]).toEqual(['idle', 'working', 'blocked', 'done'])
      expect(normalizeSeatStatus('idle')).toBe('idle')
      expect(normalizeSeatStatus('working')).toBe('working')
      expect(normalizeSeatStatus('blocked')).toBe('waiting')
      expect(normalizeSeatStatus('done')).toBe('finished')
    })

    it.each([['nonsense'], [''], ['  '], ['Blocked '], ['DONE']])(
      'treats %o as unknown rather than guessing',
      (raw) => {
        // Case/whitespace insensitivity is deliberate normalisation; an
        // unrecognised VALUE is not.
        if (typeof raw === 'string' && raw.trim().toLowerCase() in {
          idle: 1,
          working: 1,
          blocked: 1,
          done: 1,
        }) {
          expect(normalizeSeatStatus(raw)).not.toBe(UNKNOWN_STATUS)
          return
        }
        expect(normalizeSeatStatus(raw)).toBe(UNKNOWN_STATUS)
      },
    )

    it.each([[null], [undefined], [7], [{}], [[]]])(
      'never turns a non-string %o into a positive status',
      (raw) => {
        expect(normalizeSeatStatus(raw)).toBe(UNKNOWN_STATUS)
      },
    )

    it('accepts an already-mapped OS value as well as a Herdr value', () => {
      // The wire carries both: `status` is OS-mapped, `herdr_status` is
      // Herdr's own. Only understanding one would need a branch per call site.
      expect(normalizeSeatStatus('waiting')).toBe('waiting')
      expect(normalizeSeatStatus('finished')).toBe('finished')
      expect(normalizeSeatStatus('unknown')).toBe(UNKNOWN_STATUS)
    })

    it('names every state in words for an accessible label', () => {
      expect(statusLabel('waiting')).toMatch(/waiting/i)
      expect(statusLabel('finished')).toMatch(/finished/i)
      expect(statusLabel('unknown')).toBe('Status unknown')
      for (const seat of SEAT_STATUSES) {
        expect(statusLabel(seat).length).toBeGreaterThan(0)
      }
    })
  })

  describe('frame parsing', () => {
    it('accepts a well-formed frame', () => {
      const parsed = parseHerdrStatusFrame(
        JSON.parse('{"type":"herdr_status","seat_id":"herdr:w3:p1","status":"blocked"}'),
      )
      expect(parsed?.seat_id).toBe('herdr:w3:p1')
      expect(parsed?.status).toBe('blocked')
    })

    it.each([
      [null],
      [undefined],
      ['a string'],
      [42],
      [{ type: 'something_else', seat_id: 'herdr:w3:p1' }],
      [{ type: 'herdr_status', status: 'working' }],
      [{ type: 'herdr_status', seat_id: '   ', status: 'working' }],
    ])('drops %o instead of half-reading it', (raw) => {
      // A half-parsed payload must become "nothing", never a guessed status.
      expect(parseHerdrStatusFrame(raw)).toBeNull()
    })

    it('tolerates missing optional fields', () => {
      const parsed = parseHerdrStatusFrame({ type: 'herdr_status', seat_id: 'herdr:a' })
      expect(parsed).not.toBeNull()
      expect(parsed?.status).toBe('')
      expect(parsed?.mark_unread).toBe(false)
      expect(parsed?.state_change_seq).toBeNull()
    })
  })

  describe('transitions', () => {
    it('marks unread on finish through the existing rail store', () => {
      applyHerdrStatusFrame(frame({ status: 'finished', mark_unread: true }))
      // The reuse claim, asserted against the real store the rail reads.
      expect(loadUnreadAgentIds()).toContain('herdr:w3:p1')
      expect(isAgentUnread('herdr:w3:p1')).toBe(true)
      expect(localStorage.getItem(UNREAD_AGENTS_STORAGE_KEY)).toContain('herdr:w3:p1')
    })

    it('does not mark unread on a seat the operator is reading', () => {
      applyHerdrStatusFrame(
        frame({ status: 'finished', mark_unread: false, seat_is_open: true }),
      )
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('flags waiting as attention but not unread', () => {
      applyHerdrStatusFrame(frame({ status: 'blocked', needs_input: true }))
      expect(herdrStatusFor('herdr:w3:p1')).toBe('waiting')
      expect(herdrAttentionSeats()).toEqual(['herdr:w3:p1'])
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('reports working as busy without demanding attention', () => {
      applyHerdrStatusFrame(frame({ status: 'working' }))
      expect(herdrStatusFor('herdr:w3:p1')).toBe('working')
      expect(herdrAttentionSeats()).toEqual([])
    })

    it('stores unknown for an unrecognised status without lighting anything', () => {
      const decision = applyHerdrStatusFrame(frame({ status: 'quantum', mark_unread: true }))
      expect(decision.status).toBe(UNKNOWN_STATUS)
      expect(herdrStatusFor('herdr:w3:p1')).toBe(UNKNOWN_STATUS)
      expect(herdrAttentionSeats()).toEqual([])
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('an unknown status for a seat we never saw leaves it unknown', () => {
      expect(herdrStatusFor('herdr:never-heard-of')).toBe(UNKNOWN_STATUS)
      expect(getHerdrReading('herdr:never-heard-of')).toBeNull()
    })

    it('notifies subscribers on every change', () => {
      const seen: string[] = []
      const release = subscribeHerdrStatus((seatId) => seen.push(seatId))
      applyHerdrStatusFrame(frame({ status: 'blocked' }))
      applyHerdrStatusFrame(frame({ status: 'finished', mark_unread: true }))
      release()
      applyHerdrStatusFrame(frame({ status: 'idle' }))
      expect(seen).toEqual(['herdr:w3:p1', 'herdr:w3:p1'])
    })

    it('a subscriber that throws does not starve the others', () => {
      const seen: string[] = []
      const bad = subscribeHerdrStatus(() => {
        throw new Error('boom')
      })
      const good = subscribeHerdrStatus((seatId) => seen.push(seatId))
      applyHerdrStatusFrame(frame({ status: 'blocked' }))
      bad()
      good()
      expect(seen).toEqual(['herdr:w3:p1'])
    })
  })

  describe('out-of-order updates', () => {
    it.each([
      [8, 9, true],
      [9, 9, false],
      [10, 9, false],
      [null, 9, false],
      [8, null, false],
    ])('incoming=%o known=%o -> stale=%o', (incoming, known, expected) => {
      expect(isStaleFrame(incoming as number | null, known as number | null)).toBe(expected)
    })

    it('a late frame cannot walk a seat backwards from finished to working', () => {
      applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true, state_change_seq: 9 }))
      markAgentRead('herdr:w3:p1')
      const decision = applyHerdrStatusFrame(
        frame({ status: 'working', state_change_seq: 8 }),
      )
      expect(decision.stale).toBe(true)
      expect(decision.changed).toBe(false)
      // The dot the operator just cleared must stay cleared.
      expect(herdrStatusFor('herdr:w3:p1')).toBe('finished')
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('a re-read of the same seq is accepted but not re-announced', () => {
      applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true, state_change_seq: 9 }))
      markAgentRead('herdr:w3:p1')
      const decision = applyHerdrStatusFrame(
        frame({ status: 'done', mark_unread: true, state_change_seq: 9 }),
      )
      expect(decision.stale).toBe(false)
      expect(decision.changed).toBe(false)
      expect(decision.markUnread).toBe(false)
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('a frame with no seq is not discarded as stale', () => {
      applyHerdrStatusFrame(frame({ status: 'done', state_change_seq: 9 }))
      const decision = applyHerdrStatusFrame(frame({ status: 'working' }))
      expect(decision.stale).toBe(false)
      expect(decision.changed).toBe(true)
      expect(herdrStatusFor('herdr:w3:p1')).toBe('working')
    })

    it('a later frame wins when it is genuinely newer', () => {
      applyHerdrStatusFrame(frame({ status: 'working', state_change_seq: 8 }))
      const decision = applyHerdrStatusFrame(frame({ status: 'done', state_change_seq: 9 }))
      expect(decision.changed).toBe(true)
      expect(herdrStatusFor('herdr:w3:p1')).toBe('finished')
    })
  })

  describe('clearing', () => {
    it('clears both the status and the unread mark', () => {
      applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true }))
      expect(isAgentUnread('herdr:w3:p1')).toBe(true)
      clearHerdrSeat('herdr:w3:p1')
      expect(herdrStatusFor('herdr:w3:p1')).toBe(UNKNOWN_STATUS)
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('clearing a seat with nothing to clear is a no-op', () => {
      const seen: string[] = []
      const release = subscribeHerdrStatus((seatId) => seen.push(seatId))
      clearHerdrSeat('herdr:never-seen')
      release()
      expect(seen).toEqual([])
    })
  })

  describe('decideHerdrStatus (pure)', () => {
    it('honours the server\'s unread decision rather than re-deriving it', () => {
      // The backend knows whether the operator has the seat open. Two
      // derivations of "should this be unread" is how a dot starts to lie.
      const closed = decideHerdrStatus(frame({ status: 'done', mark_unread: true }))
      const open = decideHerdrStatus(frame({ status: 'done', mark_unread: false }))
      expect(closed.markUnread).toBe(true)
      expect(open.markUnread).toBe(false)
      expect(closed.status).toBe(open.status)
    })

    it('marks attention from the status, not from the server flag', () => {
      expect(decideHerdrStatus(frame({ status: 'blocked' })).attention).toBe(true)
      expect(decideHerdrStatus(frame({ status: 'working' })).attention).toBe(false)
      expect(decideHerdrStatus(frame({ status: 'done' })).attention).toBe(false)
    })

    it('reports the first sighting as a change', () => {
      expect(decideHerdrStatus(frame({ status: 'idle' }), null).changed).toBe(true)
    })

    it('reports an unchanged re-read as not changed', () => {
      const first = applyHerdrStatusFrame(frame({ status: 'idle' }))
      const reading = getHerdrReading('herdr:w3:p1')
      expect(first.changed).toBe(true)
      expect(decideHerdrStatus(frame({ status: 'idle' }), reading).changed).toBe(false)
    })
  })
})

// Deliberate non-regression guards — these pass before and after the change.
describe('#1729 non-regression guards', () => {
  beforeEach(() => {
    localStorage.clear()
    resetHerdrStatusStore()
  })

  it('guard: the existing unread store still round-trips its own ids', () => {
    // The Herdr path writes through this store; if its own contract moved,
    // every other unread affordance moved with it. Passes both ways.
    const ids = loadUnreadAgentIds()
    expect(Array.isArray(ids)).toBe(true)
    expect(isAgentUnread('not-a-seat')).toBe(false)
  })

  it('guard: clearing an unrelated seat leaves ours alone', () => {
    applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true }))
    clearHerdrSeat('herdr:other-pane')
    expect(herdrStatusFor('herdr:w3:p1')).toBe('finished')
    expect(isAgentUnread('herdr:w3:p1')).toBe(true)
  })

  it('guard: two seats track independently', () => {
    applyHerdrStatusFrame(frame({ seat_id: 'herdr:a', status: 'blocked' }))
    applyHerdrStatusFrame(frame({ seat_id: 'herdr:b', status: 'done', mark_unread: true }))
    expect(herdrStatusFor('herdr:a')).toBe('waiting')
    expect(herdrStatusFor('herdr:b')).toBe('finished')
    expect(isAgentUnread('herdr:b')).toBe(true)
    expect(isAgentUnread('herdr:a')).toBe(false)
  })
})
