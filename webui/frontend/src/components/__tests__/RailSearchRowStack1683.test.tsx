/**
 * #1683 — the rail's search row must fit the controls it actually has.
 *
 * The row holds up to three controls: the Search pill, Add agent, and the
 * pane-collapse control. Below the one-column pinned-grid detent (118px) they
 * do not fit side by side — 36 + 36 + 36 + two 6px gaps + the row's 24px
 * padding is 144px — so the row wraps. A one-control-per-row stack puts the
 * collapse control on a THIRD row, under Add, from every width between 89px
 * (the first above the avatar-only line) and 118px.
 *
 * #1683 first answered that with a two-row grid (search spanning the top row,
 * Add + collapse sharing the second). #1711 then found the consequence: the
 * collapse control still never shared a row with Search, so at the 1-col
 * detent — the width the issue is actually about — the pane's only way back
 * was a circle parked in a band of its own. The wrap is now one wrapping row
 * that keeps collapse welded to Search, so the premise below is unchanged but
 * the fix is not the grid: see `RailOneColCollapseInline1711.test.tsx` for
 * that contract, and the note on each assertion here.
 *
 * jsdom has no layout engine, so this file pins the two halves of the fix:
 *  1. the CSS contract — below 118px a row carrying three children lays out as
 *     a wrapping row, never a per-control column stack, and the two-control
 *     ultra-compact stack is untouched;
 *  2. the premise that contract rests on — the real component renders three
 *     children above the avatar-only line and two at/below it.
 *
 * The rendered geometry is measured in a real renderer (Chrome, built CSS) by
 * `scripts/measure-rail-chrome.mjs`, which is the acceptance gate.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import fs from 'fs'
import path from 'path'
import AgentSidebar from '../AgentSidebar'
import { ADD_BOT_MENU_TRIGGER_TESTID } from '../AddBotMenu'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { ONE_COL_RAIL_WIDTH, TWO_COL_RAIL_WIDTH, ULTRACOMPACT_RAIL_WIDTH } from '../../lib/railResize'

const INDEX_CSS = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

function ruleBody(selector: string): string {
  const start = INDEX_CSS.indexOf(`\n${selector} {`)
  expect(start).toBeGreaterThanOrEqual(0)
  const open = INDEX_CSS.indexOf('{', start)
  return INDEX_CSS.slice(open + 1, INDEX_CSS.indexOf('}', open))
}

function containerBlock(predicate: string): string {
  const start = INDEX_CSS.indexOf(`@container (${predicate})`)
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
    return {
      ok: true,
      json: async () => ({ object: 'list', data: [], results: [] }),
    } as Response
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

describe('#1683 search row: three controls wrap as a group below the one-column detent', () => {
  it('never stacks one control per row at the 1-col band', () => {
    const block = containerBlock('max-width: 118px')
    // #1711 replaced #1683's two-row grid with ONE wrapping row: the trio
    // keeps the horizontal band it has at every wider detent, and the wrap
    // (89..115px, mid-drag only) costs a second line for `+`, never a third
    // slot for the collapse control.
    expect(block).toMatch(
      /\.os-agent-sidebar \.os-rail-search-row:has\(> :nth-child\(3\)\)\s*\{[^}]*?flex-direction:\s*row;/,
    )
    expect(block).toMatch(/flex-wrap:\s*wrap;/)
    // The superseded #1683 grid must not creep back: it is the layout that
    // left the collapse control off the search row.
    expect(block).not.toMatch(/grid-template-columns:/)
  })

  it('spends the row\'s whole width on the trio, not on a column stack', () => {
    const block = containerBlock('max-width: 118px')
    const rule = block.match(
      /\.os-agent-sidebar \.os-rail-search-row:has\(> :nth-child\(3\)\)\s*\{([^}]*)\}/,
    )
    expect(rule).toBeTruthy()
    // 3 x 2.25rem + 2 gaps + 2 side paddings must land inside the 117px the
    // 118px detent leaves for content. 0.25rem each (the old rhythm) is
    // 108 + 8 + 8 = 124px and wraps at the detent itself; 0.125rem is 116px.
    expect(rule![1]).toMatch(/gap:\s*0\.125rem;/)
    expect(rule![1]).toMatch(/padding-left:\s*0\.125rem;/)
    expect(rule![1]).toMatch(/padding-right:\s*0\.125rem;/)
    // 3 * 36 + 2 * 2 + 2 * 2 = 116 <= 117 (118 minus the pane's 1px border).
    expect(3 * 36 + 2 * 2 + 2 * 2).toBeLessThanOrEqual(ONE_COL_RAIL_WIDTH - 1)
  })

  it('leaves the ultra-compact column stack exactly as it was', () => {
    const avatarOnly = ruleBody('.os-agent-sidebar--avatar-only .os-rail-search-row')
    expect(avatarOnly).toMatch(/flex-direction:\s*column;/)
    expect(avatarOnly).not.toMatch(/display:\s*grid/)
    // …and the shared container rule still stacks by default, so a hypothetical
    // fourth child degrades to a column rather than to a squeezed row.
    const block = containerBlock('max-width: 118px')
    expect(block).toMatch(/\.os-agent-sidebar \.os-rail-search-row\s*\{[^}]*?flex-direction:\s*column;/)
  })

  it('keeps the bound on the one-column detent, below two columns', () => {
    expect(ONE_COL_RAIL_WIDTH).toBe(118)
    expect(ONE_COL_RAIL_WIDTH).toBeLessThan(TWO_COL_RAIL_WIDTH)
    expect(INDEX_CSS).toContain('@container (max-width: 118px)')
  })
})

describe('#1683 the row really does carry a third control only above the avatar-only line', () => {
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

  async function searchRowChildren(): Promise<number> {
    const rail = await screen.findByTestId('os-agent-rail')
    // The `:has(> :nth-child(3))` contract is about the row's child count, so
    // the count has to come from the row element itself.
    // eslint-disable-next-line testing-library/no-node-access -- child count is the assertion
    const row = rail.querySelector('.os-rail-search-row')
    expect(row).toBeTruthy()
    // eslint-disable-next-line testing-library/no-node-access -- same reason
    return row!.children.length
  }

  for (const width of [ONE_COL_RAIL_WIDTH, 110, 96]) {
    it(`renders search + add + collapse (3 children) at ${width}px`, async () => {
      localStorage.setItem('swarm_rail_width', String(width))
      renderRail()
      const rail = await screen.findByTestId('os-agent-rail')
      expect(rail).toHaveAttribute('data-avatar-only', 'false')
      expect(screen.getByTestId('rail-search-trigger')).toBeInTheDocument()
      // #1674 turned the `+` into a menu; its trigger is the Add control, and
      // that is the element the `:has(> :nth-child(3))` rule counts.
      expect(screen.getByTestId(ADD_BOT_MENU_TRIGGER_TESTID)).toBeInTheDocument()
      expect(await searchRowChildren()).toBe(3)
    })
  }

  it(`renders search + add only (2 children) at the ultra-compact ${ULTRACOMPACT_RAIL_WIDTH}px`, async () => {
    localStorage.setItem('swarm_rail_width', String(ULTRACOMPACT_RAIL_WIDTH))
    renderRail()
    const rail = await screen.findByTestId('os-agent-rail')
    expect(rail).toHaveAttribute('data-avatar-only', 'true')
    // The collapse control is hoisted out of the row, which is why the
    // `:has(> :nth-child(3))` layout must not (and does not) apply here.
    expect(screen.getByTestId('rail-top-toggle')).toBeInTheDocument()
    expect(screen.queryByTestId('sidebar-conceal')).not.toBeInTheDocument()
    expect(await searchRowChildren()).toBe(2)
  })
})
