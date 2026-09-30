/**
 * #1699 / #1700 — the reader for the catalog's admission + readiness fields.
 *
 * Two properties matter more than the field plumbing:
 *
 * 1. **Fail open in one place.** A backend older than the gate sends none of
 *    these fields, and a missing field must read as "listed and ready". If it
 *    read as anything else, a rollback would silently empty every picker.
 * 2. **The picker is the consumer.** `pickerSeatRows` is what #1699's "not
 *    listed in the agent picker" and #1700's "not a silent chat target" mean in
 *    the UI, so these tests assert on what the picker is handed, not on the
 *    field names.
 */

import { describe, expect, it } from 'vitest'
import type { Blueprint } from '../api'
import {
  parseManageLinks,
  parseSeatOffer,
  pickerSeatRows,
  selectableSeats,
  seatOffersById,
  withheldSeatIds,
} from '../blueprintSeats'

/** A catalog row as the server sends it, with only the fields under test. */
function row(partial: Record<string, unknown>): Blueprint {
  return {
    id: '',
    object: 'blueprint',
    name: '',
    description: '',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: null,
    compiled: null,
    ...partial,
  } as Blueprint
}

const readyRow = row({ id: 'support', name: 'Support', description: 'Onboarder' })

const withheldRemote = row({
  id: 'remote_harness',
  name: 'Remote harness',
  description: 'Talks to Hermes',
  seat_kind: 'remote',
  seat_source: 'discovery',
  seat_listed: false,
  chat_ready: false,
  unavailable_reason: 'No remote is configured.',
  manage_links: [{ href: '/chat?settings=remotes', label: 'Add a remote' }],
})

const unrunnableApi = row({
  id: 'poets',
  name: 'Poets',
  description: 'Two voices',
  seat_kind: 'api',
  seat_source: 'discovery',
  seat_listed: true,
  chat_ready: false,
  unavailable_reason: 'No LLM provider is configured.',
  manage_links: [{ href: '/chat?settings=llm-profiles', label: 'Set up an API provider' }],
})

describe('parseSeatOffer — fail open', () => {
  it('a row from a backend older than the gate is listed and ready', () => {
    const offer = parseSeatOffer(readyRow)
    expect(offer.listed).toBe(true)
    expect(offer.ready).toBe(true)
    expect(offer.reason).toBe('')
    expect(offer.manageLinks).toEqual([])
  })

  it('an explicit false is honoured on every field', () => {
    const offer = parseSeatOffer(withheldRemote)
    expect(offer.listed).toBe(false)
    expect(offer.ready).toBe(false)
    expect(offer.kind).toBe('remote')
    expect(offer.source).toBe('discovery')
    expect(offer.reason).toBe('No remote is configured.')
    expect(offer.manageLinks).toEqual([
      { href: '/chat?settings=remotes', label: 'Add a remote' },
    ])
  })

  it('a value of true is not turned back into "unknown"', () => {
    const offer = parseSeatOffer(row({ ...readyRow, seat_listed: true, chat_ready: true }))
    expect(offer.listed).toBe(true)
    expect(offer.ready).toBe(true)
  })

  it('an unrecognised kind degrades to "other" rather than a guess', () => {
    // The SPA must never re-derive the kind from the id — that would be a second
    // copy of agent_kind.classify_agent_kind and the two would drift.
    expect(parseSeatOffer(row({ ...readyRow, seat_kind: 'quantum' })).kind).toBe('other')
    expect(parseSeatOffer(readyRow).kind).toBe('other')
  })
})

describe('parseManageLinks — a link is only useful with both halves', () => {
  it('drops a link with no href or no label', () => {
    expect(
      parseManageLinks([
        { href: '/chat?settings=remotes' },
        { label: 'Add a remote' },
        { href: '  ', label: 'x' },
        null,
        'nope',
      ]),
    ).toEqual([])
  })

  it('trims and keeps a well-formed link', () => {
    expect(parseManageLinks([{ href: ' /chat?settings=remotes ', label: ' Add a remote ' }])).toEqual([
      { href: '/chat?settings=remotes', label: 'Add a remote' },
    ])
  })

  it('a non-array is not an error', () => {
    expect(parseManageLinks(undefined)).toEqual([])
    expect(parseManageLinks({})).toEqual([])
  })
})

describe('#1699 — the picker never offers a withheld seat', () => {
  it('withheldSeatIds names exactly the rows the server withheld', () => {
    const rows = [readyRow, withheldRemote, unrunnableApi]
    expect(withheldSeatIds(rows)).toEqual(['remote_harness'])
  })

  it('a user-created row is never withheld even when the server says so', () => {
    // Belt and braces on the server rule: a mislabelled `seat_source` must not
    // cost an operator the seat they installed.
    const mine = row({ ...withheldRemote, id: 'my-seat', seat_source: 'user' })
    expect(withheldSeatIds([mine])).toEqual([])
    expect(selectableSeats([mine]).map((r) => r.id)).toEqual(['my-seat'])
  })

  it('selectableSeats drops the withheld row and keeps the rest', () => {
    const ids = selectableSeats([readyRow, withheldRemote, unrunnableApi]).map((r) => r.id)
    expect(ids).toEqual(['support', 'poets'])
  })

  it('an empty catalog is an empty list, not a crash', () => {
    expect(selectableSeats([])).toEqual([])
    expect(selectableSeats(null)).toEqual([])
    expect(withheldSeatIds(undefined)).toEqual([])
    expect(seatOffersById(undefined).size).toBe(0)
  })
})

describe('#1700 — an unrunnable seat is marked, not silently offered', () => {
  it('pickerSeatRows keeps the row and appends the reason plus its repair label', () => {
    const rows = pickerSeatRows([unrunnableApi])
    expect(rows).toHaveLength(1)
    expect(rows[0].id).toBe('poets')
    expect(rows[0].description).toContain('Two voices')
    expect(rows[0].description).toContain('No LLM provider is configured.')
    expect(rows[0].description).toContain('Set up an API provider')
  })

  it('a ready row is passed through byte-for-byte', () => {
    const rows = pickerSeatRows([readyRow])
    expect(rows[0]).toBe(readyRow)
  })

  it('a withheld row is dropped rather than annotated', () => {
    expect(pickerSeatRows([withheldRemote])).toEqual([])
  })

  it('a not-ready row with no reason is not decorated with an empty dash', () => {
    const rows = pickerSeatRows([
      row({ ...unrunnableApi, unavailable_reason: '', manage_links: [] }),
    ])
    expect(rows[0].description).toBe('Two voices')
  })

  it('a not-ready row with a reason but no link still states the reason', () => {
    const rows = pickerSeatRows([row({ ...unrunnableApi, manage_links: [] })])
    expect(rows[0].description).toContain('No LLM provider is configured.')
    expect(rows[0].description).not.toContain('→')
  })

  it('a row with no description gains one rather than an empty prefix', () => {
    const { description: _existing, ...noDescription } = unrunnableApi
    const rows = pickerSeatRows([row(noDescription)])
    expect(rows[0].description).toBe(
      'No LLM provider is configured. → Set up an API provider',
    )
  })
})
