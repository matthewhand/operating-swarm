/**
 * #1349 / #1350 / #1351 / #1355 — ultra-compact rail batch.
 *
 * #1349: in ultra-compact (avatar-only) mode the expand control is the
 *        top-most element of the pane, above the stacked search row, and
 *        reads the same in either dock.
 * #1350: ultra-compact shrank ~5–10% (96 → 88px) without clipping icons; the
 *        snap detents follow.
 * #1351: each bottom mini-icon carries a subtle bordered badge/pill built
 *        from theme tokens (legible light + dark).
 * #1355: the expand/collapse width change animates, and the animation is off
 *        under `prefers-reduced-motion: reduce`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import fs from 'fs'
import path from 'path'
import AgentSidebar from '../AgentSidebar'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import {
  AVATAR_ONLY_THRESHOLD,
  ULTRACOMPACT_RAIL_WIDTH,
  RAIL_SNAP_POINTS,
  isAvatarOnlyWidth,
} from '../../lib/railResize'

const INDEX_CSS = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
const SIDEBAR_SRC = fs.readFileSync(path.resolve(__dirname, '../AgentSidebar.tsx'), 'utf8')

/** The pre-#1350 ultra-compact width, the baseline for the shrink check. */
const ULTRACOMPACT_WIDTH_BEFORE = 96

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        json: async () => ({
          object: 'user_preferences',
          favourites: [],
          hidden_agents: [],
        }),
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

describe('#1349 the ultra-compact control sits at the top of the pane', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem('swarm_rail_width', String(ULTRACOMPACT_RAIL_WIDTH))
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  for (const side of ['left', 'right'] as const) {
    it(`is the top-most content element in the ${side} dock`, async () => {
      localStorage.setItem('swarm_rail_side', side)
      renderRail()
      const rail = await screen.findByTestId('os-agent-rail')
      expect(rail).toHaveAttribute('data-avatar-only', 'true')
      expect(rail).toHaveClass(`os-agent-sidebar--${side}`)
      expect(rail).not.toHaveAttribute('data-collapsed', 'true')

      const toggle = screen.getByTestId('rail-top-toggle')
      expect(rail.contains(toggle)).toBe(true)
      expect(toggle).toHaveAttribute('data-rail-side', side)

      // The expand affordance lives in the top control, not the search row.
      expect(within(toggle).getByTestId('sidebar-expand')).toBeInTheDocument()
      expect(screen.queryByTestId('sidebar-conceal')).not.toBeInTheDocument()

      // And the control precedes the search row in document order — the
      // stacked search/add buttons can no longer push it to the pane bottom.
      const searchRow = screen
        .getByTestId('rail-search-trigger')
        .closest('.os-rail-search-row') as HTMLElement
      expect(searchRow).toBeTruthy()
      // bit 4 = Node.DOCUMENT_POSITION_FOLLOWING.
      expect(toggle.compareDocumentPosition(searchRow) & 4).toBeTruthy()
    })
  }
})

describe('#1350 ultra-compact shaves ~5–10% without clipping', () => {
  it('keeps the shrink within the 5–10% window', () => {
    const ratio = (ULTRACOMPACT_WIDTH_BEFORE - ULTRACOMPACT_RAIL_WIDTH) / ULTRACOMPACT_WIDTH_BEFORE
    expect(ratio).toBeGreaterThanOrEqual(0.05)
    expect(ratio).toBeLessThanOrEqual(0.1)
  })

  it('moves the detent and the avatar-only threshold with the new width', () => {
    expect(ULTRACOMPACT_RAIL_WIDTH).toBe(AVATAR_ONLY_THRESHOLD)
    expect(RAIL_SNAP_POINTS).toContain(ULTRACOMPACT_RAIL_WIDTH)
    expect(isAvatarOnlyWidth(ULTRACOMPACT_RAIL_WIDTH)).toBe(true)
    expect(isAvatarOnlyWidth(ULTRACOMPACT_RAIL_WIDTH + 1)).toBe(false)
  })

  it('renders the rail at the shaved ultra-compact width', async () => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem('swarm_rail_width', String(ULTRACOMPACT_RAIL_WIDTH))
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
    try {
      renderRail()
      const rail = await screen.findByTestId('os-agent-rail')
      expect(rail.style.width).toBe(`${ULTRACOMPACT_RAIL_WIDTH}px`)
    } finally {
      cleanup()
      vi.unstubAllGlobals()
      localStorage.clear()
    }
  })
})

describe('#1351 bottom mini-icons carry a theme-token badge/pill', () => {
  it('tags every bottom mini-icon with the badge hook', () => {
    const badges = SIDEBAR_SRC.match(/os-rail-icon-badge/g) ?? []
    // Teams, Plugins, Routines + the Server icon.
    expect(badges.length).toBeGreaterThanOrEqual(4)
  })

  it('#1650: avatar-only badges are bare glyphs — no border, no pill tint', () => {
    const match = INDEX_CSS.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-rail-icon-badge\s*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    const rule = match![1]
    expect(rule).toMatch(/border:\s*0/)
    expect(rule).toMatch(/background:\s*transparent/)
    expect(rule).not.toMatch(/border:\s*1px solid/)
    expect(rule).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    // Hover affordance stays, but as a token tint, never a border.
    const hover = INDEX_CSS.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-rail-icon-badge:hover[\s\S]*?\{([^}]+)\}/,
    )
    expect(hover).toBeTruthy()
    expect(hover![1]).toMatch(/background:/)
    expect(hover![1]).not.toMatch(/border-color:/)
  })

  it('applies the badge class to the rendered footer chrome in avatar-only mode', async () => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem('swarm_rail_width', String(ULTRACOMPACT_RAIL_WIDTH))
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
    try {
      renderRail()
      await screen.findByTestId('os-agent-rail')
      for (const testid of ['os-teams-button', 'os-plugins-button', 'os-calendar-button', 'rail-server-icon']) {
        expect(screen.getByTestId(testid).className).toContain('os-rail-icon-badge')
      }
    } finally {
      cleanup()
      vi.unstubAllGlobals()
      localStorage.clear()
    }
  })
})

describe('#1355 expand/collapse slide animation', () => {
  it('animates the rail width on desktop rails', () => {
    expect(INDEX_CSS).toMatch(
      /\.os-agent-sidebar--animated\s*\{[^}]*transition:\s*width\s+220ms/,
    )
  })

  it('disables the slide under prefers-reduced-motion: reduce', () => {
    expect(INDEX_CSS).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.os-agent-sidebar--animated\s*\{\s*transition:\s*none/,
    )
  })

  it('stamps the animating class on the in-flow rail but not the mobile drawer', async () => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
    try {
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const { unmount } = render(
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={['/chat']}>
            <AgentSidebar open />
          </MemoryRouter>
        </QueryClientProvider>,
      )
      const rail = await screen.findByTestId('os-agent-rail')
      expect(rail.className).toContain('os-agent-sidebar--animated')
      unmount()
      cleanup()

      render(
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={['/chat']}>
            <AgentSidebar open narrow />
          </MemoryRouter>
        </QueryClientProvider>,
      )
      const drawerRail = await screen.findByTestId('os-agent-rail')
      expect(drawerRail.className).not.toContain('os-agent-sidebar--animated')
    } finally {
      cleanup()
      vi.unstubAllGlobals()
      localStorage.clear()
    }
  })
})
