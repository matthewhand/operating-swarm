/**
 * #580 — the rail menu and the navbar must agree on which seats offer
 * sessions, from one declared predicate (#551 doctrine).
 *
 * The bug: the rail offered Select/New session on `api || cli || isCli`
 * while the navbar mounted a switcher only for `isCliAgent && currentCli` —
 * an API seat's promise had no header affordance.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { railMenuItems } from '../railContextMenu'
import { seatHasSessions, seatOffersSessionMenu } from '../seatCapabilities'

// #856 slice J: the navbar session switchers moved verbatim into the
// ChatHeader module — the navbar-agreement pins read their real home.
const chatHeaderSrc = () =>
  readFileSync(join(process.cwd(), 'src/features/chat/ChatHeader.tsx'), 'utf8')
const sidebarSrc = () =>
  readFileSync(join(process.cwd(), 'src/components/AgentSidebar.tsx'), 'utf8')

describe('seatHasSessions (the one declared predicate)', () => {
  it('declares sessions for api and cli kinds', () => {
    expect(seatHasSessions({ kind: 'api' })).toBe(true)
    expect(seatHasSessions({ kind: 'cli' })).toBe(true)
    expect(seatHasSessions({ kind: 'cli', isCli: true })).toBe(true)
  })

  it('declares sessions for cli rows carrying isCli without kind', () => {
    expect(seatHasSessions({ kind: null, isCli: true })).toBe(true)
    expect(seatHasSessions({ kind: '', isCli: true })).toBe(true)
  })

  it('denies team, remote, herdr and unknown kinds', () => {
    expect(seatHasSessions({ kind: 'team' })).toBe(false)
    expect(seatHasSessions({ kind: 'remote' })).toBe(false)
    expect(seatHasSessions({ kind: 'herdr' })).toBe(false)
    expect(seatHasSessions({ kind: 'blueprint' })).toBe(false)
    expect(seatHasSessions({ kind: null })).toBe(false)
    expect(seatHasSessions({})).toBe(false)
  })

  it('seatOffersSessionMenu mirrors the navbar predicate exactly', () => {
    for (const kind of ['api', 'cli', 'team', 'remote', 'herdr', 'blueprint', null]) {
      expect(seatOffersSessionMenu({ kind })).toBe(seatHasSessions({ kind }))
    }
  })
})

describe('rail menu agreement', () => {
  const base = { pinned: false, hidden: false, unread: false }

  /** Drive railMenuItems exactly as AgentSidebar does: the session flags
   * come from the shared predicate, nothing else. */
  function menuFor(kind: 'api' | 'cli' | 'team' | 'remote') {
    const seat = { kind }
    return railMenuItems({
      ...base,
      kind,
      hasSelectSession: seatHasSessions(seat),
      hasNewSession: seatHasSessions(seat),
    })
  }

  it('api seats get Select session and New session', () => {
    const ids = menuFor('api').map((item) => item.id)
    expect(ids).toContain('select-session')
    expect(ids).toContain('new-session')
  })

  it('cli seats keep both items', () => {
    const ids = menuFor('cli').map((item) => item.id)
    expect(ids).toContain('select-session')
    expect(ids).toContain('new-session')
  })

  it('team and remote seats get neither', () => {
    for (const kind of ['team', 'remote'] as const) {
      const ids = menuFor(kind).map((item) => item.id)
      expect(ids).not.toContain('select-session')
      expect(ids).not.toContain('new-session')
    }
  })

  it('the rail consumes the shared predicate, not an inline kind list (#551)', () => {
    expect(sidebarSrc()).toContain('hasSelectSession: seatHasSessions(menu)')
    expect(sidebarSrc()).toContain('hasNewSession: seatHasSessions(menu)')
    // The drifted inline expression is gone.
    expect(sidebarSrc()).not.toContain(
      "menu.kind === 'api' || menu.kind === 'cli' || Boolean(menu.isCli)",
    )
  })
})

describe('navbar agreement', () => {
  it('the navbar mounts the API session switcher under the declared capability', () => {
    const src = chatHeaderSrc()
    expect(src).toContain('ApiSessionSwitcher')
    // Gated by isApiAgent — the navbar's declared-kind gate (#736: the
    // former productModes AND-layer is retired), not a fabricated
    // currentCli resolution.
    expect(src).toMatch(/isApiAgent \? \([^]*?ApiSessionSwitcher/)
  })

  it('neither surface derives the gate from a possibly-fabricated currentCli (#566)', () => {
    const src = chatHeaderSrc()
    const anchor = src.indexOf('ApiSessionSwitcher')
    const gate = src.slice(src.lastIndexOf('{is', anchor), anchor)
    expect(gate).not.toMatch(/currentCli/)
  })

  it('the CLI switcher is untouched', () => {
    expect(chatHeaderSrc()).toContain('isCliAgent && currentCli ? (')
    expect(chatHeaderSrc()).toContain('<CliSessionSwitcher')
  })
})
