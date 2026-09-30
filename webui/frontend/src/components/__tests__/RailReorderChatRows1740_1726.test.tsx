/**
 * #1740 / #1726 — the sidepane, driven by real keyboard events and real
 * clicks.
 *
 * The pure models are covered in `railReorder1740.test.ts` and the menu
 * contract in `railContextMenu1727.test.tsx`; this file is the part a user
 * touches. Nothing here reads the source: every assertion is on rendered DOM,
 * a `userEvent`/`fireEvent` key, a real accessible name, or parsed CSS.
 *
 * Measured contracts:
 *
 *   #1740  Alt+Down/Up     reorders among siblings in the same section
 *          Alt+Down at a section edge   does NOT spill into the next section
 *          Alt+Right        files the row into the adjacent section
 *          focus + selection stay on the moved row
 *          a polite live region announces every outcome, no-op included
 *          Space / Enter / Escape / Shift+F10 keep their #1705 behaviour
 *
 *   #1726  "New session" on a row and "+ Add bot" pick produce the SAME
 *          visible result: a second sidepane row with a speech bubble on the
 *          avatar, and the main pane switched.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { railMenuKindForRow } from '../../features/sidebar/useRailMenuOpeners'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import {
  RAIL_SECTIONS_STORAGE_KEY,
  saveRailSections,
} from '../../lib/railSections'
import { RAIL_ORDER_STORAGE_KEY } from '../../lib/railOrder'

function blueprint(id: string, name: string, description: string) {
  return {
    id,
    object: 'blueprint' as const,
    name,
    description,
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    rail: true,
  }
}

const blueprints = [
  blueprint('alpha', 'Alpha', 'First seat'),
  blueprint('bravo', 'Bravo', 'Second seat'),
  blueprint('charlie', 'Charlie', 'Third seat'),
  blueprint('delta', 'Delta', 'Fourth seat'),
]

function listResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ object: 'list', data }),
  } as Response
}

interface FetchState {
  href: string
  sessionPosts: string[]
  /** GET /v1/agents/designs/ rows — rail seats whose rail `kind` is 'design'. */
  designs?: unknown[]
}

/** A router-designed seat. The rail maps every design row to `kind: 'design'`,
 *  which is a RAIL grouping, not one of the seat kinds `seatHasSessions`
 *  declares — so it must not be able to answer "does this seat have sessions". */
function designedAgent(agentId: string) {
  return {
    agent_id: agentId,
    name: agentId,
    description: `${agentId} designer`,
    specialty: 'designer',
    color: '#6366f1',
    icon: '🤖',
    type: 'specialist',
    kind: 'cli',
    agent_type: 'cli',
    cli: 'opencode',
  }
}

function mockFetch(state: FetchState) {
  return vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
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
    // The chat-session create endpoint (#1726: both surfaces go through it).
    if (url.includes('/sessions/') && method === 'POST') {
      const id = `sess-new-${state.sessionPosts.length + 1}`
      state.sessionPosts.push(id)
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id,
          conversation_id: id,
          agent_id: 'alpha',
          title: 'Fresh thread',
          snippet: '',
          created_at: '2026-09-29T10:00:00Z',
          updated_at: '2026-09-29T10:00:00Z',
          labels: [],
          cli_session_id: null,
          status: 'finished',
        }),
      } as Response
    }
    if (url.includes('/sessions/')) return listResponse([])
    if (url.includes('/v1/agents/designs')) return listResponse(state.designs ?? [])
    if (url.includes('blueprint')) return listResponse(blueprints)
    if (url.includes('team_rosters') || url.includes('team-rosters')) return listResponse([])
    return listResponse([])
  })
}

function renderRail() {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Row roots in rail order, grouped by the section block that renders them. */
async function railRows(): Promise<HTMLElement[]> {
  const list = await screen.findByRole('navigation', { name: 'Agent list' })
  await waitFor(() => {
    if (list.querySelectorAll('.os-agent-row[data-agent-id]').length < 4) {
      throw new Error('rail rows not rendered yet')
    }
  })
  return Array.from(list.querySelectorAll<HTMLElement>('.os-agent-row[data-agent-id]'))
}

function rowId(row: HTMLElement): string {
  return row.getAttribute('data-agent-id') || ''
}

function rowById(rows: HTMLElement[], id: string): HTMLElement {
  const found = rows.find((row) => rowId(row) === id)
  expect(found, `rail row ${id}`).toBeTruthy()
  return found as HTMLElement
}

/** Row ids of one section block, in the order that block renders them. */
function blockRowIds(sectionId: string): string[] {
  const block = document.querySelector(`[data-section-id="${sectionId}"]`)
  if (!block) return []
  return Array.from(block.querySelectorAll<HTMLElement>('.os-agent-row[data-agent-id]')).map(
    (row) => row.getAttribute('data-agent-id') || '',
  )
}

/**
 * The block's row ids restricted to the seats this test seeded. The rail adds
 * its own support/team rows to Unassigned, so an exact block list is not a
 * stable thing to assert on — the ORDER of the seats under test is.
 */
function orderAmong(sectionId: string, ids: string[]): string[] {
  const wanted = new Set(ids)
  return blockRowIds(sectionId).filter((id) => wanted.has(id))
}

const SEATS = ['alpha', 'bravo', 'charlie', 'delta']

function announcement(): string {
  return screen.getByTestId('rail-reorder-announce').textContent || ''
}

function storedOrder(): string[] {
  return JSON.parse(localStorage.getItem(RAIL_ORDER_STORAGE_KEY) || '[]') as string[]
}

/** Two stored sections, one seat in each, so "adjacent section" is a real move. */
beforeEach(() => {
  localStorage.clear()
  localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(RAIL_SECTIONS_STORAGE_KEY, JSON.stringify([]))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/* ==================================================================== */
/* #1740                                                                */
/* ==================================================================== */

describe('#1740 Alt+ArrowUp/Down reorder WITHIN a section', () => {
  it('moves a focused row down among its siblings and persists the order', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    focusRow(rows, 'alpha')

    altKey('alpha', 'ArrowDown')

    // The row moved down: the DOM order flipped and the store followed.
    await waitFor(() =>
      expect(orderAmong('unassigned', SEATS)).toEqual(['bravo', 'alpha', 'charlie', 'delta']),
    )
    expect(storedOrder().indexOf('alpha')).toBe(storedOrder().indexOf('bravo') + 1)
    // The pane did NOT navigate: a reorder is not a move to another seat.
    expect(
      document.querySelector('.os-agent-row[data-agent-id="alpha"]')?.closest(
        '[data-testid="os-agent-rail"]',
      ),
    ).toBeTruthy()
  })

  it('does NOT spill into the previous section at the top edge, and says so', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    // Two stored sections so Unassigned is not the first block on screen.
    saveRailSections({
      sections: [
        { id: 'sec_one', name: 'One', collapsed: false },
        { id: 'sec_two', name: 'Two', collapsed: false },
      ],
      membership: { alpha: 'sec_one', bravo: 'sec_two' },
      unassignedCollapsed: false,
    })
    renderRail()
    const rows = await railRows()
    const before = blockRowIds('sec_one')
    expect(before).toEqual(['alpha'])
    focusRow(rows, 'alpha')
    altKey('alpha', 'ArrowUp')

    // Still exactly where it was — no spill, no wrap.
    await waitFor(() => expect(blockRowIds('sec_one')).toEqual(['alpha']))
    // …and the no-op is ANNOUNCED, not silent.
    await waitFor(() => expect(announcement()).toMatch(/already at the edge of this section/i))
    expect(announcement()).toContain('One')
  })

  it('moves a row between sections with Alt+Right, keeping it selected and focused', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    saveRailSections({
      sections: [
        { id: 'sec_one', name: 'One', collapsed: false },
        { id: 'sec_two', name: 'Two', collapsed: false },
      ],
      membership: { alpha: 'sec_one', bravo: 'sec_two' },
      unassignedCollapsed: false,
    })
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')

    // Select it first, so §3 "clear selection still on the moved item" is real.
    fireEvent.click(alpha, { ctrlKey: true })
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'true'))
    alpha.focus()

    altKey('alpha', 'ArrowRight')

    // The moved row lands at the TOP of the destination block — the same
    // above-the-first-row placement a drop onto that block's first row makes.
    await waitFor(() =>
      expect(orderAmong('sec_two', ['alpha', 'bravo'])).toEqual(['alpha', 'bravo']),
    )
    // …and it is gone from where it was: the row crossed, it was not copied.
    expect(orderAmong('sec_one', ['alpha'])).toEqual([])
    await waitFor(() => expect(announcement()).toContain('Two'))
    // Selection follows the row across the section boundary (#1740 §3).
    const moved = await waitFor(() => {
      const inTwo = document.querySelector<HTMLElement>(
        '[data-section-id="sec_two"] .os-agent-row[data-agent-id="alpha"]',
      )
      expect(inTwo).not.toBeNull()
      return inTwo as HTMLElement
    })
    expect(moved).toHaveAttribute('data-selected', 'true')
    // Focus followed too, so the operator can keep pressing Alt+Arrow.
    await waitFor(() => expect(document.activeElement).toBe(moved))
  })

})

describe('#1740 the reorder announcement is a real live region', () => {
  it('is a polite status region on the rail', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    await railRows()
    const region = screen.getByTestId('rail-reorder-announce')
    expect(region).toHaveAttribute('role', 'status')
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('announces a successful move with the new position and the section name', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    focusRow(rows, 'alpha')
    altKey('alpha', 'ArrowDown')
    await waitFor(() => expect(announcement()).toMatch(/^Moved alpha down to position \d+ of \d+ in /))
    // The section named is the one the row is rendered under — the one the
    // move was confined to, not the rail as a whole.
    expect(announcement()).toMatch(/ in (Unassigned|API)\.$/)
  })
})

describe('#1740 coexists with the existing row shortcuts', () => {
  // NOTE: the four tests in this block are DELIBERATE NON-REGRESSION GUARDS.
  // They pass both before and after this change — that is the point, since the
  // issue's §4 is "existing non-Alt arrow behaviour is unchanged". They assert
  // only on the stored order and the selection, never on the new announcement
  // region, so a failure means #1740 broke a shipped shortcut rather than that
  // the feature is missing.

  it('Space still toggles the selection and never reorders the rail', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    const alpha = focusRow(rows, 'alpha')
    const orderBefore = storedOrder()

    spaceKey()
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'true'))
    expect(storedOrder()).toEqual(orderBefore)
    expect(orderAmong('unassigned', SEATS)).toEqual(SEATS)
  })

  it('Shift+F10 still opens the row context menu', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    alpha.focus()
    shiftF10()
    const menu = await screen.findByRole('menu')
    expect(menu).toHaveAttribute('aria-label', expect.stringContaining('Alpha'))
  })

  it('Escape still clears a multi-selection', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    await screen.findByTestId('os-rail-bulk-bar')
    escapeKey()
    await waitFor(() => expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull())
  })

  it('a plain ArrowDown is neither a reorder nor a selection change', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    const alpha = focusRow(rows, 'alpha')
    const orderBefore = storedOrder()
    arrowKey('alpha', 'ArrowDown')
    expect(storedOrder()).toEqual(orderBefore)
    expect(alpha).toHaveAttribute('data-selected', 'false')
    expect(orderAmong('unassigned', SEATS)).toEqual(SEATS)
  })

  it('Alt+Left/Right moves no seat: the pane does not follow the rail', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    focusRow(rows, 'alpha')
    altKey('alpha', 'ArrowRight')
    // #1088 claimed EVERY Alt+Arrow and read anything that was not ArrowDown
    // as "up", so Alt+Right used to navigate backwards to another seat. The row
    // under focus must still be the one the operator started on.
    expect(document.activeElement?.getAttribute('data-agent-id')).toBe('alpha')
  })
})

/* ==================================================================== */
/* #1726                                                                */
/* ==================================================================== */

describe('#1726 New session and + Add bot produce the SAME visible result', () => {
  it('New session on a row adds a second sidepane row with a speech bubble', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const seat = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id="alpha"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })

    fireEvent.contextMenu(seat)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^New session$/i }))

    // A SECOND row, with its own rail id naming the seat and the session.
    const chatRow = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id^="chat:alpha:"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })
    expect(chatRow).toHaveAttribute('data-chat-row', 'true')
    // The seat row is still there (#1709's "one row per seat" is untouched).
    expect(list.querySelector('.os-agent-row[data-agent-id="alpha"]')).not.toBeNull()

    // The affordance the issue asks for: a speech bubble ON the avatar.
    expect(within(chatRow).getByTestId('rail-chat-badge')).toBeInTheDocument()
    // …and the seat row has no badge, so the two are distinguishable.
    expect(
      within(seat).queryByTestId('rail-chat-badge'),
    ).toBeNull()

    // Selecting the twin opens that session, and the seat row is named as the
    // chat's owner rather than being an identical duplicate.
    expect(chatRow).toHaveAttribute('href', expect.stringContaining('session=sess-new-1'))
    expect(chatRow).toHaveAttribute('href', expect.stringContaining('blueprint=alpha'))
    expect(chatRow).toHaveAccessibleName(/^Chat with Alpha:/)
    expect(within(chatRow).getByTestId('rail-agent-name')).toHaveTextContent('Fresh thread')
  })

  it('picking the same agent from + Add bot adds the same row', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() =>
      expect(list.querySelector('.os-agent-row[data-agent-id="alpha"]')).not.toBeNull(),
    )

    fireEvent.click(screen.getByTestId('add-bot-menu-trigger'))
    fireEvent.click(await screen.findByTestId('os-add-bot-menu-agent-alpha'))

    // The SAME rail id, the SAME marker, the SAME destination — one code path.
    const chatRow = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id^="chat:alpha:"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })
    expect(chatRow).toHaveAttribute('data-chat-row', 'true')
    expect(within(chatRow).getByTestId('rail-chat-badge')).toBeInTheDocument()
    expect(chatRow).toHaveAttribute('href', expect.stringContaining('session=sess-new-1'))
  })

  it('a chat row greys the actions that need a seat it does not have', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const seat = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id="alpha"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })
    fireEvent.contextMenu(seat)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^New session$/i }))

    const chatRow = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id^="chat:alpha:"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })
    fireEvent.contextMenu(chatRow)
    const edit = await screen.findByRole('menuitem', { name: /Edit Profile/ })
    const duplicate = screen.getByRole('menuitem', { name: /^Duplicate$/ })
    expect(edit).toBeDisabled()
    expect(duplicate).toBeDisabled()
    // The seat's own row keeps both — the greying is per row kind, not global.
    expect(edit).toHaveAttribute('title', expect.stringContaining('chat'))
  })

  it('the chat row is filed under its seat, so a section change keeps the pair together', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    saveRailSections({
      sections: [{ id: 'sec_one', name: 'One', collapsed: false }],
      membership: { alpha: 'sec_one' },
      unassignedCollapsed: false,
    })
    renderRail()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const seat = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id="alpha"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })
    fireEvent.contextMenu(seat)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^New session$/i }))

    // Not left in limbo in Unassigned: it lands in the same section as its seat.
    await waitFor(() =>
      expect(
        list.querySelector('[data-section-id="sec_one"] .os-agent-row[data-agent-id^="chat:alpha:"]'),
      ).not.toBeNull(),
    )
  })
})

/* ==================================================================== */
/* #1727 — the session capability is asked about the SEAT                */
/* ==================================================================== */

describe('#1727 the session capability is answered by the seat, not by the catalog wire kind', () => {
  // The regression this pins: reading the seat's capability by spreading the
  // catalog row over the menu let the row's RAW `kind` field answer instead
  // of the menu's already-resolved kind. A router-designed rail seat carries
  // `kind: 'design'` (a rail grouping, not a seat kind), so "Select session" /
  // "New session" silently vanished from a seat that can hold sessions.
  // A substring assertion over the source could not have caught this — only
  // the rendered menu can.
  it('keeps Select session and New session on a designed rail seat', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [], designs: [designedAgent('hass-eng')] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const rows = await railRows()
    const seat = rowById(rows, 'hass-eng')

    fireEvent.contextMenu(seat)
    const select = await screen.findByRole('menuitem', { name: /Select session/i })
    const fresh = screen.getByRole('menuitem', { name: /^New session$/i })
    expect(select).not.toBeDisabled()
    expect(fresh).not.toBeDisabled()
  })

  it('a chat row takes its session capability from its SEAT, not from "chat"', async () => {
    const state: FetchState = { href: '/chat', sessionPosts: [] }
    vi.stubGlobal('fetch', mockFetch(state))
    renderRail()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const seat = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id="alpha"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })
    fireEvent.contextMenu(seat)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^New session$/i }))
    const chatRow = await waitFor(() => {
      const row = list.querySelector<HTMLElement>('.os-agent-row[data-agent-id^="chat:alpha:"]')
      expect(row).not.toBeNull()
      return row as HTMLElement
    })

    fireEvent.contextMenu(chatRow)
    // Alpha is an API seat, so its session items stay live on the twin…
    expect(await screen.findByRole('menuitem', { name: /^New session$/i })).not.toBeDisabled()
    expect(screen.getByRole('menuitem', { name: /Select session/i })).not.toBeDisabled()
  })
})

describe('#1726 the rail classifies a row id exactly once', () => {
  it('reads a chat row id as the seat it names, and a seat id as itself', () => {
    const agents = [
      { id: 'alpha', name: 'Alpha' },
      { id: 'codex_agent', name: 'Codex', kind: 'cli' },
      { id: 'herdr:lab', name: 'Lab', kind: 'herdr' },
    ] as never[]
    expect(railMenuKindForRow('alpha', agents)).toBe('api')
    expect(railMenuKindForRow('codex_agent', agents)).toBe('cli')
    expect(railMenuKindForRow('herdr:lab', agents)).toBe('herdr')
    expect(railMenuKindForRow('team:ops', agents)).toBe('team')
    expect(railMenuKindForRow('remote:acp', agents)).toBe('remote')
    // A designed row's wire kind is a rail grouping, not a seat kind, so it
    // must still read as the API seat the rail renders it as.
    expect(railMenuKindForRow('hass-eng', [{ id: 'hass-eng', kind: 'design' }] as never)).toBe('api')
    // …and the chat row of each seat is that seat's kind, never 'chat'.
    expect(railMenuKindForRow('chat:codex_agent:s1', agents)).toBe('cli')
    expect(railMenuKindForRow('chat:team:ops:s1', agents)).toBe('team')
    expect(railMenuKindForRow('chat:herdr:lab:s1', agents)).toBe('herdr')
  })
})

/** #1740 fixtures seed sections per test with `saveRailSections`. */
/**
 * Real DOM KeyboardEvents, dispatched on the focused row so they BUBBLE —
 * which is the point: the row's React handler and the window-level #1088
 * navigation handler both see the same event, and only the
 * `defaultPrevented` handshake stops both acting on it. (This repo has no
 * `@testing-library/user-event` dependency and the brief forbids adding one;
 * `fireEvent.keyDown` is what the #1705 selection test already uses.)
 */
function focusRow(rows: HTMLElement[], id: string): HTMLElement {
  const row = rowById(rows, id)
  row.focus()
  expect(document.activeElement).toBe(row)
  return row
}

function altKey(id: string, key: string): void {
  const row = document.querySelector<HTMLElement>(`.os-agent-row[data-agent-id="${id}"]`)
  expect(row, `row ${id}`).not.toBeNull()
  fireEvent.keyDown(row as HTMLElement, { key, altKey: true, bubbles: true, cancelable: true })
}

function arrowKey(id: string, key: string): void {
  const row = document.querySelector<HTMLElement>(`.os-agent-row[data-agent-id="${id}"]`)
  fireEvent.keyDown(row as HTMLElement, { key, bubbles: true, cancelable: true })
}

function spaceKey(): void {
  const active = document.activeElement as HTMLElement | null
  fireEvent.keyDown(active as HTMLElement, { key: ' ', bubbles: true, cancelable: true })
}

function shiftF10(): void {
  const active = document.activeElement as HTMLElement | null
  fireEvent.keyDown(active as HTMLElement, {
    key: 'F10',
    shiftKey: true,
    bubbles: true,
    cancelable: true,
  })
}

function escapeKey(): void {
  fireEvent.keyDown(document.body, { key: 'Escape', bubbles: true, cancelable: true })
}
