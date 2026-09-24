/**
 * #1088 — Alt+Up / Alt+Down sequential rail navigation (Herdr parity).
 *
 * Replaces REQ-172's Alt+1..9 slot model, which collided with native browser
 * tab switching (Alt+1..8 on Linux/Windows). The navigable sequence is the
 * rail's visual order: visible pins first, then every row in the uncollapsed
 * sections — no 9-slot cap, no spill. Movement clamps at the boundaries.
 */
import { describe, expect, it } from 'vitest'
import { chatHrefForRowId } from '../agentNotifications'
import {
  activeRailNavIndex,
  computeRailNavSequence,
  herdrChatHref,
  stepRailNav,
  type RailRow,
} from '../railHotkeys'

const mockRows: RailRow[] = [
  { kind: 'agent', id: 'agent-1', agent: { id: 'agent-1', name: 'Agent 1' } },
  { kind: 'agent', id: 'agent-2', agent: { id: 'agent-2', name: 'Agent 2' } },
  { kind: 'team', id: 'team-alpha', team: { id: 'alpha', name: 'Team Alpha' } },
  { kind: 'remote', id: 'remote-omb', remote: { id: 'omb', label: 'OpenMousBot' } },
  { kind: 'agent', id: 'agent-5', agent: { id: 'agent-5', name: 'Agent 5' } },
]

describe('#1088 computeRailNavSequence — rail visual order', () => {
  it('lists visible pins first, then all rows in order — no 9-slot cap', () => {
    const pins = [
      { id: 'pin-1', name: 'Pin 1' },
      { id: 'pin-2', name: 'Pin 2' },
    ]
    const seq = computeRailNavSequence({ visiblePins: pins, orderedRows: mockRows })
    expect(seq.map((t) => t.id)).toEqual([
      'pin-1',
      'pin-2',
      'agent-1',
      'agent-2',
      'team-alpha',
      'remote-omb',
      'agent-5',
    ])
    // more than 9 entries is fine now
    const manyRows = Array.from({ length: 12 }, (_, i) => ({
      kind: 'agent' as const,
      id: `agent-${i + 1}`,
      agent: { id: `agent-${i + 1}`, name: `Agent ${i + 1}` },
    }))
    const big = computeRailNavSequence({ visiblePins: [], orderedRows: manyRows })
    expect(big).toHaveLength(12)
  })

  it('kind-aware hrefs survive the model change (REQ-171B / #543)', () => {
    const seq = computeRailNavSequence({
      visiblePins: [
        { id: 'codey', name: 'Codey' },
        { id: 'team:demo', name: 'Demo' },
        { id: 'remote:omb', name: 'OpenMousBot' },
        { id: 'herdr:w3:p1', name: 'w3:p1', kind: 'herdr' },
      ],
      orderedRows: mockRows,
    })
    expect(seq[0]).toMatchObject({ id: 'codey', href: '/chat?blueprint=codey' })
    expect(seq[1]).toMatchObject({ id: 'team:demo', href: '/chat?team=demo' })
    expect(seq[2]).toMatchObject({ id: 'remote:omb', href: '/chat?remote=omb' })
    expect(seq[3]).toMatchObject({
      id: 'herdr:w3:p1',
      href: '/chat?remote=herdr&session=w3%3Ap1',
      isHerdr: true,
    })
    expect(seq[4]).toMatchObject({ id: 'agent-1', href: '/chat?blueprint=agent-1' })
    expect(seq[6]).toMatchObject({ id: 'team-alpha', href: '/chat?team=alpha' })
    expect(seq[8]).toMatchObject({ id: 'agent-5', href: '/chat?blueprint=agent-5' })
  })
})

describe('#1088 activeRailNavIndex — resolve the current row from the URL', () => {
  const seq = computeRailNavSequence({
    visiblePins: [{ id: 'pin-1', name: 'Pin 1' }],
    orderedRows: mockRows,
  })

  it('matches ?blueprint= rows', () => {
    expect(activeRailNavIndex(seq, '?blueprint=agent-2')).toBe(2)
  })
  it('matches ?team= and ?remote= rows', () => {
    expect(activeRailNavIndex(seq, '?team=alpha')).toBe(3)
    expect(activeRailNavIndex(seq, '?remote=omb')).toBe(4)
  })
  it('matches herdr sessions and pins', () => {
    const withHerdr = computeRailNavSequence({
      visiblePins: [{ id: 'herdr:p1', name: 'p1', kind: 'herdr' }],
      orderedRows: [],
    })
    expect(activeRailNavIndex(withHerdr, '?remote=herdr&session=p1')).toBe(0)
  })
  it('returns -1 when nothing matches (no navigation anchor)', () => {
    expect(activeRailNavIndex(seq, '?blueprint=unknown-agent')).toBe(-1)
  })
})

describe('#1088 stepRailNav — sequential movement with boundary clamping', () => {
  const seq = computeRailNavSequence({
    visiblePins: [{ id: 'pin-1', name: 'Pin 1' }],
    orderedRows: mockRows,
  })

  it('Alt+Down advances through pins into unpinned rows and across sections', () => {
    expect(stepRailNav(seq, 0, 1)?.id).toBe('agent-1')
    expect(stepRailNav(seq, 1, 1)?.id).toBe('agent-2')
    expect(stepRailNav(seq, 2, 1)?.id).toBe('team-alpha')
    expect(stepRailNav(seq, 3, 1)?.id).toBe('remote-omb')
  })
  it('Alt+Up walks back the same path', () => {
    expect(stepRailNav(seq, 1, -1)?.id).toBe('pin-1')
    expect(stepRailNav(seq, 4, -1)?.id).toBe('team-alpha')
  })
  it('clamps at the boundaries instead of wrapping or escaping', () => {
    expect(stepRailNav(seq, 0, -1)?.id).toBe('pin-1')
    expect(stepRailNav(seq, seq.length - 1, 1)?.id).toBe('agent-5')
  })
  it('an unanchored current index (-1) starts from the top on Alt+Down', () => {
    expect(stepRailNav(seq, -1, 1)?.id).toBe('pin-1')
    expect(stepRailNav(seq, -1, -1)?.id).toBe('pin-1')
  })
})

describe('#543 herdrChatHref — herdr seats are URL-addressable (unchanged)', () => {
  it('builds a chat URL whose session IS the agent target', () => {
    expect(herdrChatHref('herdr:p1')).toBe('/chat?remote=herdr&session=p1')
    expect(herdrChatHref('p1')).toBe('/chat?remote=herdr&session=p1')
  })

  it('encodes agent names that share an id shape with URL params', () => {
    expect(herdrChatHref('herdr:w3:p1')).toBe('/chat?remote=herdr&session=w3%3Ap1')
  })

  it('chatHrefForRowId maps herdr seats to their chat URL (not /teams)', () => {
    expect(chatHrefForRowId('herdr:p1')).toBe('/chat?remote=herdr&session=p1')
  })
})
