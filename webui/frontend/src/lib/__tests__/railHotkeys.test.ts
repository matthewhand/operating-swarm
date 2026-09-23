import { describe, expect, it } from 'vitest'
import { chatHrefForRowId } from '../agentNotifications'
import {
  computeRailHotkeyTargets,
  herdrChatHref,
  type RailRow,
} from '../railHotkeys'

describe('computeRailHotkeyTargets (REQ-172)', () => {
  const mockRows: RailRow[] = [
    { kind: 'agent', id: 'agent-1', agent: { id: 'agent-1', name: 'Agent 1' } },
    { kind: 'agent', id: 'agent-2', agent: { id: 'agent-2', name: 'Agent 2' } },
    { kind: 'team', id: 'team-alpha', team: { id: 'alpha', name: 'Team Alpha' } },
    { kind: 'remote', id: 'remote-omb', remote: { id: 'omb', label: 'OpenMousBot' } },
    { kind: 'agent', id: 'agent-5', agent: { id: 'agent-5', name: 'Agent 5' } },
    { kind: 'agent', id: 'agent-6', agent: { id: 'agent-6', name: 'Agent 6' } },
    { kind: 'agent', id: 'agent-7', agent: { id: 'agent-7', name: 'Agent 7' } },
    { kind: 'agent', id: 'agent-8', agent: { id: 'agent-8', name: 'Agent 8' } },
    { kind: 'agent', id: 'agent-9', agent: { id: 'agent-9', name: 'Agent 9' } },
    { kind: 'agent', id: 'agent-10', agent: { id: 'agent-10', name: 'Agent 10' } },
  ]

  it('case 0 favourites: Alt+1–9 target top nine unpinned rows', () => {
    const targets = computeRailHotkeyTargets({
      visiblePins: [],
      orderedRows: mockRows,
    })

    expect(targets).toHaveLength(9)
    expect(targets[0].id).toBe('agent-1')
    expect(targets[0].href).toBe('/chat?blueprint=agent-1')
    expect(targets[1].id).toBe('agent-2')
    expect(targets[2].id).toBe('team-alpha')
    expect(targets[2].href).toBe('/chat?team=alpha')
    expect(targets[3].id).toBe('remote-omb')
    expect(targets[3].href).toBe('/chat?remote=omb')
    expect(targets[8].id).toBe('agent-9')
  })

  it('case 3 favourites: Alt+1–3 target pins, Alt+4–9 target top six unpinned', () => {
    const pins = [
      { id: 'pin-1', name: 'Pin 1' },
      { id: 'pin-2', name: 'Pin 2' },
      { id: 'pin-3', name: 'Pin 3' },
    ]

    const targets = computeRailHotkeyTargets({
      visiblePins: pins,
      orderedRows: mockRows,
    })

    expect(targets).toHaveLength(9)
    // First 3 are pins
    expect(targets[0].id).toBe('pin-1')
    expect(targets[0].kind).toBe('pin')
    expect(targets[1].id).toBe('pin-2')
    expect(targets[2].id).toBe('pin-3')

    // Next 6 are from unpinned rows
    expect(targets[3].id).toBe('agent-1')
    expect(targets[3].kind).toBe('agent')
    expect(targets[4].id).toBe('agent-2')
    expect(targets[5].id).toBe('team-alpha')
    expect(targets[6].id).toBe('remote-omb')
    expect(targets[7].id).toBe('agent-5')
    expect(targets[8].id).toBe('agent-6')
  })

  it('case 10 favourites: unpinned rows unused, only first 9 pins bound', () => {
    const pins = Array.from({ length: 10 }, (_, i) => ({
      id: `pin-${i + 1}`,
      name: `Pin ${i + 1}`,
    }))

    const targets = computeRailHotkeyTargets({
      visiblePins: pins,
      orderedRows: mockRows,
    })

    expect(targets).toHaveLength(9)
    expect(targets[0].id).toBe('pin-1')
    expect(targets[8].id).toBe('pin-9')
    // No unpinned rows included
    expect(targets.some((t) => t.kind !== 'pin')).toBe(false)
  })

  it('REQ-171B: pins of each kind use kind-aware hrefs (not always ?blueprint=)', () => {
    const targets = computeRailHotkeyTargets({
      visiblePins: [
        { id: 'codey', name: 'Codey' },
        { id: 'team:demo', name: 'Demo' },
        { id: 'remote:omb', name: 'OpenMousBot' },
        { id: 'herdr:w3:p1', name: 'w3:p1', kind: 'herdr' },
      ],
      orderedRows: [],
    })

    expect(targets).toHaveLength(4)
    expect(targets[0]).toMatchObject({
      id: 'codey',
      kind: 'pin',
      href: '/chat?blueprint=codey',
    })
    expect(targets[1]).toMatchObject({
      id: 'team:demo',
      kind: 'pin',
      href: '/chat?team=demo',
    })
    expect(targets[1].href).not.toMatch(/blueprint=/)
    expect(targets[2]).toMatchObject({
      id: 'remote:omb',
      kind: 'pin',
      href: '/chat?remote=omb',
    })
    expect(targets[2].href).not.toMatch(/blueprint=/)
    // #543: herdr seats chat like every other kind — the pin targets the
    // agent's own conversation, not the settings-adjacent members page.
    expect(targets[3]).toMatchObject({
      id: 'herdr:w3:p1',
      kind: 'pin',
      href: '/chat?remote=herdr&session=w3%3Ap1',
      isHerdr: true,
    })
  })

  it('handles fewer than 9 total items gracefully', () => {
    const pins = [{ id: 'pin-1', name: 'Pin 1' }]
    const rows: RailRow[] = [
      { kind: 'agent', id: 'agent-1', agent: { id: 'agent-1', name: 'Agent 1' } },
    ]

    const targets = computeRailHotkeyTargets({
      visiblePins: pins,
      orderedRows: rows,
    })

    expect(targets).toHaveLength(2)
    expect(targets[0].id).toBe('pin-1')
    expect(targets[1].id).toBe('agent-1')
  })
})

describe('#543 herdrChatHref — herdr seats are URL-addressable', () => {
  it('builds a chat URL whose session IS the agent target', () => {
    expect(herdrChatHref('herdr:p1')).toBe('/chat?remote=herdr&session=p1')
    expect(herdrChatHref('p1')).toBe('/chat?remote=herdr&session=p1')
  })

  it('encodes agent names that share an id shape with URL params', () => {
    // Two agents with the same name on different remotes stay distinguishable
    // through the agent list's remote field; the name itself must survive the
    // URL round-trip.
    expect(herdrChatHref('herdr:w3:p1')).toBe('/chat?remote=herdr&session=w3%3Ap1')
  })

  it('chatHrefForRowId maps herdr seats to their chat URL (not /teams)', () => {
    expect(chatHrefForRowId('herdr:p1')).toBe('/chat?remote=herdr&session=p1')
  })
})
