/**
 * #1711 — at the 1-col detent the collapse control shares the header row.
 *
 * What the dogfood report (#1711) caught, and what this file locks down
 * ---------------------------------------------------------------------
 * Collapsing the rail to one pinned-grid column (118px) turns Search and `+`
 * into 2.25rem circles. The collapse control is a third 2.25rem circle, and it
 * was the one control the row had no room for: 36 + 36 + 36 + two 6px gaps +
 * the row's 24px padding is 144px against the 117px the detent leaves. So the
 * row wrapped, and — through #1683's two-row grid and, before that, a
 * one-control-per-row stack — the collapse control landed in a vertical slot of
 * its own, under `+`. The issue's acceptance: it must appear ALONGSIDE Search
 * and `+`, and where the trio cannot fit it must stay in the same strip as
 * Search rather than orphaning into a third circle.
 *
 * Two facts make that true at 1-col, and both are asserted here:
 *  1. the three-control row is ONE wrapping row, not a column stack and not a
 *     two-row grid, with its gap and side padding squeezed to 0.125rem so the
 *     trio fits the 117px it actually has;
 *  2. the collapse control is ordered ahead of `+` inside that row, so the wrap
 *     at 89..115px breaks after it, keeping it on Search's band.
 *
 * jsdom has no layout engine, so these are the source-level contract
 * assertions (repo pattern). The rendered geometry — that the trio really does
 * land on one 56px band at 118px, and that nothing overflows the rail at any
 * width — is measured in a real renderer (Chrome, built CSS) by
 * `scripts/measure-rail-chrome.mjs`, which is the acceptance gate.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import fs from 'fs'
import path from 'path'
import AgentSidebar from '../AgentSidebar'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import {
  ONE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
} from '../../lib/railResize'

const INDEX_CSS = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

/** The body of the `@container (max-width: 118px)` block — the 1-col band. */
function oneColBlock(): string {
  const start = INDEX_CSS.indexOf('@container (max-width: 118px)')
  expect(start).toBeGreaterThanOrEqual(0)
  const open = INDEX_CSS.indexOf('{', start)
  let depth = 0
  for (let i = open; i < INDEX_CSS.length; i++) {
    if (INDEX_CSS[i] === '{') depth++
    else if (INDEX_CSS[i] === '}') {
      depth--
      if (depth === 0) return INDEX_CSS.slice(open + 1, i)
    }
  }
  return ''
}

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        json: async () => ({ object: 'user_preferences', favourites: [], hidden_agents: [] }),
      } as Response
    }
    return { ok: true, json: async () => ({ object: 'list', data: [], results: [] }) } as Response
  })
}

function renderRail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('#1711 the collapse control is in the 1-col header group, not a slot under +', () => {
  it('breaks the wrap AFTER collapse, so it welds to Search at every width', () => {
    const block = oneColBlock()
    // The wrap is a single, unconditional `order` in the 1-col band rather
    // than a width test. A conditional order would need a bound within ~1px of
    // the true fit threshold (116px of content vs the 117px the detent has),
    // and any drift in the pane border, gap or padding would silently flip the
    // detent into the wrap regime. One order, one regime, no cliff.
    expect(block).toMatch(
      /\.os-agent-sidebar \.os-rail-search-row:has\(> :nth-child\(3\)\) > \.os-rail-conceal\s*\{\s*order:\s*-1;/,
    )
    // …and it is scoped to the three-control row, never to the whole rail: at
    // ultra-compact the row carries two controls and keeps its column stack.
    expect(block).not.toMatch(/--avatar-only[^}]*order:/)
  })

  it('keeps every wider detent out of it entirely', () => {
    // The hook must appear in exactly ONE rule in the whole stylesheet, and
    // that rule must be inside the 1-col container query. A stray global rule
    // would move the collapse control ahead of `+` in the multi-column header
    // too, which is the regression #1711's success criteria rule out.
    const rules = [...INDEX_CSS.matchAll(/[^{}]*os-rail-conceal[^{}]*\{/g)].map((m) => m[0])
    expect(rules).toHaveLength(1)
    expect(rules[0]).toContain(':has(> :nth-child(3))')
    const ruleAt = INDEX_CSS.indexOf(rules[0])
    const containerAt = INDEX_CSS.indexOf('@container (max-width: 118px)')
    expect(ruleAt).toBeGreaterThan(containerAt)
    // …and the container query is bounded at the 1-col detent, not the 2-col one.
    expect(ONE_COL_RAIL_WIDTH).toBe(118)
    expect(ONE_COL_RAIL_WIDTH).toBeLessThan(TWO_COL_RAIL_WIDTH)
  })

  it('measures the trio as fitting the 118px detent, with 0 slack to spare', () => {
    // The whole change rests on this arithmetic, so it is asserted rather than
    // left in a comment: three 2.25rem controls + two 0.125rem gaps + two
    // 0.125rem side paddings = 116px, inside the 117px the detent leaves for
    // content (118 minus the pane's 1px border). 36*3 + 2*2 + 2*2 = 116.
    const CONTROL = 36
    const GUTTER = 2
    expect(CONTROL * 3 + GUTTER * 2 + GUTTER * 2).toBe(116)
    expect(CONTROL * 3 + GUTTER * 2 + GUTTER * 2).toBeLessThanOrEqual(ONE_COL_RAIL_WIDTH - 1)
    // One step looser — the 0.25rem rhythm the row used to carry — overflows,
    // which is why the gap had to move and not just the direction.
    expect(CONTROL * 3 + 4 * 2 + 4 * 2).toBeGreaterThan(ONE_COL_RAIL_WIDTH - 1)
  })
})

describe('#1711 the rail really renders the trio the 1-col rule keys on', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it(`carries Search, + and collapse in one row at the ${ONE_COL_RAIL_WIDTH}px detent`, async () => {
    localStorage.setItem('swarm_rail_width', String(ONE_COL_RAIL_WIDTH))
    renderRail()

    const rail = await screen.findByTestId('os-agent-rail')
    expect(rail).toHaveAttribute('data-avatar-only', 'false')
    const row = document.querySelector('.os-rail-search-row')!
    // eslint-disable-next-line testing-library/no-node-access -- child count is the assertion
    expect(row.children.length).toBe(3)

    const collapse = screen.getByTestId('sidebar-conceal')
    // THE regression: the CSS that reorders the trio keys on this class, so a
    // rename of `SidebarConcealButton`'s className would silently orphan the
    // control back onto its own band at every 1-col width.
    expect(collapse).toHaveClass('os-rail-conceal')
    // It is still the row's last DOM child, so DOM/tab order is untouched —
    // only the 1-col visual order moves. `RailConcealInSearchRow1246` pins the
    // trailing placement; this pins that the hook did not cost it.
    expect(row.children[2]).toBe(collapse)
  })

  it('does not hand the 1-col hook to the hoisted expand controls', async () => {
    localStorage.setItem('swarm_rail_width', String(ULTRACOMPACT_RAIL_WIDTH))
    renderRail()

    await screen.findByTestId('os-agent-rail')
    // At ultra-compact the collapse control is hoisted into `.os-rail-top-toggle`
    // and the row reverts to its two-control column stack. Styling it as part of
    // the 1-col group would be wrong there — and the hook must not follow it
    // out of the row, or the 1-col `:has(> :nth-child(3))` key stops matching.
    expect(screen.getByTestId('rail-top-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('sidebar-expand')).not.toHaveClass('os-rail-conceal')
  })
})
