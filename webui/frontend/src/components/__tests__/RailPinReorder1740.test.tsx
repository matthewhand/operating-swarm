/**
 * #1740 — the PIN GRID half of the Alt+Arrow reorder, driven by real keypresses.
 *
 * The first land of #1740 wired Alt+Arrow on section rows only. A pinned tile
 * is a different row class: a different store (`lib/pinnedAgents`), a different
 * order, a different component. So Alt+Down on a focused pin fell through to
 * #1088's window-level sequential navigation and paged away to the next seat —
 * the one place the issue's §1 ("reorder among siblings in the same section,
 * including Pinned") did not hold.
 *
 * Measured here, all on rendered DOM and real storage:
 *
 *   Alt+Down / Alt+Up   swap adjacent tiles in the pin grid, and the stored
 *                       pin order follows
 *   grid edges          a no-op that is ANNOUNCED, never a spill and never
 *                       silent
 *   Alt+Right           files the pin into the adjacent section, which means it
 *                       LEAVES the grid; focus follows it there
 *   Alt+Arrow on a pin  never navigates the pane (#1088 stands down on
 *                       `defaultPrevented` — this is the regression guard)
 *   a plain arrow       still not a reorder (§4)
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { RAIL_ORDER_STORAGE_KEY } from '../../lib/railOrder'
import { RAIL_SECTIONS_STORAGE_KEY, saveRailSections } from '../../lib/railSections'

function blueprint(id: string, name: string) {
  return {
    id,
    object: 'blueprint' as const,
    name,
    description: `${name} seat`,
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    rail: true,
  }
}

const blueprints = [
  blueprint('alpha', 'Alpha'),
  blueprint('bravo', 'Bravo'),
  blueprint('charlie', 'Charlie'),
  blueprint('delta', 'Delta'),
]

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    if (url.includes('/sessions')) return listResponse([])
    if (url.includes('/v1/agents/designs')) return listResponse([])
    if (url.includes('blueprint')) return listResponse(blueprints)
    if (url.includes('team_rosters') || url.includes('team-rosters')) return listResponse([])
    return listResponse([])
  })
}

function listResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ object: 'list', data }),
  } as Response
}

/** The rail's location, so "did the pane navigate?" is observable. */
function LocationProbe() {
  const location = useLocation()
  return <span data-testid="location-probe">{`${location.pathname}${location.search}`}</span>
}

function renderRail() {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function storedPins(): string[] {
  return (JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]') as { id: string }[]).map(
    (pin) => pin.id,
  )
}

function pinGrid(): HTMLElement {
  return screen.getByTestId('agent-fav-grid')
}

/** Pin tile ids in the order the grid RENDERS them. */
function tileIds(): string[] {
  return Array.from(pinGrid().querySelectorAll<HTMLElement>('.os-fav-tile[data-agent-id]')).map(
    (tile) => tile.getAttribute('data-agent-id') || '',
  )
}

function tile(id: string): HTMLElement {
  const found = pinGrid().querySelector<HTMLElement>(`.os-fav-tile[data-agent-id="${id}"]`)
  expect(found, `pin tile ${id}`).not.toBeNull()
  return found as HTMLElement
}

function announcement(): string {
  return screen.getByTestId('rail-reorder-announce').textContent || ''
}

function location(): string {
  return screen.getByTestId('location-probe').textContent || ''
}

/** Real DOM KeyboardEvents on the focused tile, so they BUBBLE to the window. */
function altKey(id: string, key: string): void {
  fireEvent.keyDown(tile(id), { key, altKey: true, bubbles: true, cancelable: true })
}

function plainArrow(id: string, key: string): void {
  fireEvent.keyDown(tile(id), { key, bubbles: true, cancelable: true })
}

async function pinGridWith(pinIds: string[]): Promise<void> {
  localStorage.setItem(
    PINNED_AGENTS_STORAGE_KEY,
    JSON.stringify(pinIds.map((id) => ({ id, name: id }))),
  )
  renderRail()
  await waitFor(() => expect(tileIds()).toEqual(pinIds))
  // The pin grid renders from the stored pins, which is faster than the agent
  // list. Keying a gesture before the list lands would measure a half-loaded
  // rail (no section rows to spill into), so every fixture waits for one.
  await waitFor(() =>
    expect(document.querySelectorAll('.os-agent-row[data-agent-id]').length).toBeGreaterThan(0),
  )
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(RAIL_SECTIONS_STORAGE_KEY, JSON.stringify([]))
  vi.stubGlobal('fetch', mockFetch())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('#1740 Alt+Up/Down reorder WITHIN the pin grid', () => {
  it('Alt+Down swaps a pin with the tile below it, in the DOM and in storage', async () => {
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    tile('alpha').focus()
    expect(document.activeElement).toBe(tile('alpha'))

    altKey('alpha', 'ArrowDown')

    await waitFor(() => expect(tileIds()).toEqual(['bravo', 'alpha', 'charlie']))
    expect(storedPins()).toEqual(['bravo', 'alpha', 'charlie'])
    // Focus stayed on the tile the operator was on, so the key can be pressed
    // again without re-finding it.
    await waitFor(() => expect(document.activeElement).toBe(tile('alpha')))
    await waitFor(() => expect(announcement()).toMatch(/^Moved alpha down to position \d+ of \d+ in /))
    // …and it names the scope, the same as a section row does.
    expect(announcement()).toMatch(/ in Pinned\.$/)
  })

  it('Alt+Up swaps a pin with the tile above it', async () => {
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    tile('charlie').focus()

    altKey('charlie', 'ArrowUp')

    await waitFor(() => expect(tileIds()).toEqual(['alpha', 'charlie', 'bravo']))
    expect(storedPins()).toEqual(['alpha', 'charlie', 'bravo'])
    expect(announcement()).toMatch(/^Moved charlie up to position \d+ of \d+ in Pinned\.$/)
  })

  it('never spills out of the grid: the section rows below are untouched', async () => {
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    const rowsBefore = Array.from(
      document.querySelectorAll('.os-agent-row[data-agent-id]'),
    ).map((row) => row.getAttribute('data-agent-id'))
    tile('charlie').focus()

    altKey('charlie', 'ArrowDown') // last tile: an edge, below the grid

    await waitFor(() => expect(announcement()).toMatch(/already at the edge/i))
    expect(
      Array.from(document.querySelectorAll('.os-agent-row[data-agent-id]')).map((row) =>
        row.getAttribute('data-agent-id'),
      ),
    ).toEqual(rowsBefore)
  })
})

describe('#1740 the pin grid edges are a no-op that announces itself', () => {
  it('Alt+Up on the FIRST pin is refused, loudly', async () => {
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    tile('alpha').focus()

    altKey('alpha', 'ArrowUp')

    await waitFor(() => expect(announcement()).toContain('already at the edge of this section'))
    expect(announcement()).toContain('Pinned')
    expect(tileIds()).toEqual(['alpha', 'bravo', 'charlie'])
    expect(storedPins()).toEqual(['alpha', 'bravo', 'charlie'])
  })

  it('Alt+Down on the LAST pin is refused, loudly', async () => {
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    tile('charlie').focus()

    altKey('charlie', 'ArrowDown')

    await waitFor(() => expect(announcement()).toContain('already at the edge of this section'))
    expect(tileIds()).toEqual(['alpha', 'bravo', 'charlie'])
    expect(storedPins()).toEqual(['alpha', 'bravo', 'charlie'])
  })

  it('a single pinned tile is an edge in both directions', async () => {
    await pinGridWith(['alpha'])
    tile('alpha').focus()

    altKey('alpha', 'ArrowUp')
    await waitFor(() => expect(announcement()).toContain('already at the edge of this section'))
    altKey('alpha', 'ArrowDown')
    await waitFor(() => expect(announcement()).toContain('already at the edge of this section'))
    expect(storedPins()).toEqual(['alpha'])
  })
})

describe('#1740 Alt+Right files a pin into the adjacent section, and it leaves the grid', () => {
  it('unpins into that section, with focus following the seat', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([
        { id: 'alpha', name: 'Alpha' },
        { id: 'bravo', name: 'Bravo' },
        { id: 'charlie', name: 'Charlie' },
      ]),
    )
    // A stored (custom) section is a real filing choice, and the first one the
    // rail offers the pin: the auto seat-kind groups are grouping, not choice.
    saveRailSections({
      sections: [{ id: 'sec_one', name: 'One', collapsed: false }],
      membership: { delta: 'sec_one' },
      unassignedCollapsed: false,
    })
    renderRail()
    await waitFor(() => expect(tileIds()).toEqual(['alpha', 'bravo', 'charlie']))
    // The seat already filed in `sec_one` has to be on screen before the
    // gesture fires, so "lands at the top of the destination" is measurable.
    await waitFor(() =>
      expect(
        document.querySelector('[data-section-id="sec_one"] .os-agent-row[data-agent-id="delta"]'),
      ).not.toBeNull(),
    )
    tile('bravo').focus()

    altKey('bravo', 'ArrowRight')

    // Gone from the grid — a pin that stayed would be rendered nowhere
    // (`excludePinnedFromList` strips pinned ids from the section rows).
    await waitFor(() => expect(tileIds()).toEqual(['alpha', 'charlie']))
    expect(storedPins()).toEqual(['alpha', 'charlie'])
    // …and filed at the TOP of the destination, above the seat already there.
    const filed = await waitFor(() => {
      const row = document.querySelector<HTMLElement>(
        '[data-section-id="sec_one"] .os-agent-row[data-agent-id="bravo"]',
      )
      expect(row).not.toBeNull()
      return row as HTMLElement
    }
    )
    const rowsInOne = Array.from(
      document.querySelectorAll<HTMLElement>('[data-section-id="sec_one"] .os-agent-row[data-agent-id]'),
    ).map((row) => row.getAttribute('data-agent-id'))
    expect(rowsInOne).toEqual(['bravo', 'delta'])
    expect(storedOrderIndex('bravo')).toBe(storedOrderIndex('delta') - 1)
    await waitFor(() => expect(announcement()).toContain('One'))
    // Focus followed the seat, so Alt+Arrow can keep being pressed.
    await waitFor(() => expect(document.activeElement).toBe(filed))
  })

  it('Alt+Left is the grid\'s own edge: there is no section above the pins', async () => {
    saveRailSections({
      sections: [{ id: 'sec_one', name: 'One', collapsed: false }],
      membership: { delta: 'sec_one' },
      unassignedCollapsed: false,
    })
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    tile('alpha').focus()

    altKey('alpha', 'ArrowLeft')

    await waitFor(() => expect(announcement()).toContain('already at the edge of this section'))
    expect(announcement()).toContain('Pinned')
    expect(tileIds()).toEqual(['alpha', 'bravo', 'charlie'])
    expect(storedPins()).toEqual(['alpha', 'bravo', 'charlie'])
  })
})

describe('#1740 the pin grid coexists with #1088 and with plain arrows', () => {
  it('Alt+Down on a pin no longer navigates the pane (#1088 stands down)', async () => {
    // The regression this pins: with no pin handler, the window handler read
    // Alt+Down and paged to the next rail target, so the operator lost the
    // tile they were on. The tile now `preventDefault`s, which that handler
    // honours.
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    expect(location()).toBe('/chat')
    tile('alpha').focus()

    altKey('alpha', 'ArrowDown')

    await waitFor(() => expect(tileIds()).toEqual(['bravo', 'alpha', 'charlie']))
    expect(location()).toBe('/chat')
  })

  it('a plain ArrowDown on a pin is not a reorder (§4)', async () => {
    await pinGridWith(['alpha', 'bravo', 'charlie'])
    tile('alpha').focus()

    plainArrow('alpha', 'ArrowDown')

    expect(tileIds()).toEqual(['alpha', 'bravo', 'charlie'])
    expect(storedPins()).toEqual(['alpha', 'bravo', 'charlie'])
  })

  it('the pin grid still announces in the rail\'s polite live region', async () => {
    await pinGridWith(['alpha', 'bravo'])
    const region = screen.getByTestId('rail-reorder-announce')
    expect(region).toHaveAttribute('role', 'status')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(within(region).queryByText(/Moved/)).toBeNull()
    tile('bravo').focus()
    altKey('bravo', 'ArrowUp')
    await waitFor(() => expect(within(region).getByText(/Moved bravo up to position 1 of 2 in Pinned\./)).toBeTruthy())
  })

  it('Shift+F10 on a pin still opens its context menu (the reorder is composed, not replacing)', async () => {
    await pinGridWith(['alpha', 'bravo'])
    tile('bravo').focus()

    fireEvent.keyDown(tile('bravo'), {
      key: 'F10',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })

    const menu = await screen.findByRole('menu')
    expect(menu).toHaveAttribute('aria-label', expect.stringContaining('Bravo'))
  })
})

function storedOrder(): string[] {
  return JSON.parse(localStorage.getItem(RAIL_ORDER_STORAGE_KEY) || '[]') as string[]
}

function storedOrderIndex(id: string): number {
  return storedOrder().indexOf(id)
}
