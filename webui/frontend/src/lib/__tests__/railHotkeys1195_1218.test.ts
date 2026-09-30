/**
 * #1218 / #1195 — the Alt+Up / Alt+Down sequential rail navigation contract
 * after the alt-N rework.
 *
 * 1. #1195: every target — herdr pins included — navigates via its computed
 *    href (SPA `navigate`), never via `window.location.assign` hard reloads.
 *    #543 doctrine: `?remote=herdr&session=<name>` IS the herdr conversation.
 * 2. #1218: a focused popup owns Alt+Arrow for its own list — the rail's
 *    global handler must yield when the event originates inside an overlay.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { activeRailNavIndex, computeRailNavSequence, stepRailNav } from '../railHotkeys'

const SIDEBAR = join(__dirname, '..', '..', 'components', 'AgentSidebar.tsx')

describe('#1195 herdr targets chat via href, not a hard reload', () => {
  const pins = [{ id: 'herdr:w3:p1', name: 'w3:p1', kind: 'herdr' }]
  const rows = [
    { kind: 'agent' as const, id: 'agy', agent: { id: 'agy', name: 'Agy' } },
    { kind: 'remote' as const, id: 'remote:herdr', remote: { id: 'herdr', label: 'Herdr' } },
  ]
  const seq = computeRailNavSequence({ visiblePins: pins, orderedRows: rows })

  it('the herdr pin is in the sequence with its chat href', () => {
    expect(seq[0]).toMatchObject({
      id: 'herdr:w3:p1',
      isHerdr: true,
      href: '/chat?remote=herdr&session=w3%3Ap1',
    })
  })

  it('is the active anchor when its conversation is open', () => {
    expect(activeRailNavIndex(seq, '?remote=herdr&session=w3:p1')).toBe(0)
  })

  it('steps from the herdr pin into the next row', () => {
    expect(stepRailNav(seq, 0, 1)?.id).toBe('agy')
  })

  it('the sidebar handler has no /teams/#herdr-members override left', () => {
    const src = readFileSync(SIDEBAR, 'utf8')
      .split('\n')
      .map((line) => line.replace(/\/\/.*$/, ''))
      .join('\n')
    expect(src.includes('herdr-members')).toBe(false)
    expect(src.includes('window.location.assign')).toBe(false)
  })
})

describe('#1218 popups own Alt+Arrow while focused', () => {
  it('the rail handler yields when the event originates inside an overlay', () => {
    const src = readFileSync(SIDEBAR, 'utf8')
    expect(src).toMatch(
      /closest\('\.os-search-palette, dialog\[open\], \[role="dialog"\]'\)/,
    )
  })

  it('popups keep their plain-arrow list navigation intact', () => {
    // The palette's own keydown branch (unmodified by this change).
    const palette = readFileSync(
      join(__dirname, '..', '..', 'components', 'SearchPalette.tsx'),
      'utf8',
    )
    expect(palette).toMatch(/event\.key === 'ArrowDown'/)
  })
})
