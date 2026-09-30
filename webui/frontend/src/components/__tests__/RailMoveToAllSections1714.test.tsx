/**
 * #1714 — the right-click "Move to" menu must list EVERY section the rail shows.
 *
 * Driven through the real event: a real `contextMenu` on a real rail row, the
 * real submenu, real `getByRole('menuitem')` queries. No source-substring
 * assertions, and no asserting on handler wiring.
 *
 * The bug this pins: the menu rebuilt its list from `sectionState.sections`
 * while the rail rendered those PLUS the derived OS / Remote / CLI / API /
 * Subagents blocks. Every auto section was therefore missing from the menu,
 * even while being a visible, droppable rail section.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import {
  NEW_SECTION_TARGET,
  RAIL_SECTIONS_STORAGE_KEY,
  UNASSIGNED_SECTION_ID,
  isAutoSectionId,
  railMoveToDestinations,
  type RailSectionBlockLike,
} from '../../lib/railSections'

const yesterday = Date.now() - 26 * 60 * 60 * 1000

interface Blueprint {
  id: string
  name: string
  kind?: string
  cli?: string
  rail?: boolean
}

const ROSTER = {
  data: [
    {
      id: 'crew',
      name: 'Crew',
      description: 'A team',
      members: [
        { id: 'codey', name: 'Codey', kind: 'blueprint', started_at: 1000 },
        { id: 'ada', name: 'Ada', kind: 'blueprint', started_at: 900 },
      ],
    },
  ],
}

function mockFetch(blueprints: Blueprint[], rosters: unknown = { data: [] }) {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/team-rosters') || url.includes('/team_rosters.json')) {
      return { ok: true, status: 200, json: async () => rosters } as Response
    }
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
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
    if (url.includes('/v1/blueprints')) {
      return {
        ok: true,
        json: async () => ({
          object: 'list',
          data: blueprints.map((b) => ({
            object: 'blueprint',
            description: 'd',
            last_message_at: yesterday,
            rail: true,
            ...b,
          })),
        }),
      } as Response
    }
    if (url.includes('/v1/companies')) {
      return { ok: true, json: async () => ({ object: 'list', data: [] }) } as Response
    }
    if (url.includes('/v1/remotes')) {
      return { ok: true, json: async () => ({ object: 'list', data: [], configured: [] }) } as Response
    }
    return { ok: true, json: async () => ({ object: 'list', data: [], results: [] }) } as Response
  })
}

const BLUEPRINTS: Blueprint[] = [
  { id: 'codey', name: 'Codey' },
  { id: 'cliagent', name: 'CliAgent', kind: 'cli', cli: 'grok' },
  { id: 'apibot', name: 'ApiBot' },
]

function renderRail() {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderRailWithTeam() {
  vi.stubGlobal('fetch', mockFetch(BLUEPRINTS, ROSTER))
  return renderRail()
}

/** The section ids the RAIL is showing, read from the rendered DOM. */
function renderedSectionIds(): string[] {
  return screen
    .getAllByTestId('rail-section')
    .map((node) => node.getAttribute('data-section-id') ?? '')
}

async function openMoveTo(rowName: RegExp) {
  const list = await screen.findByRole('navigation', { name: 'Agent list' })
  await waitFor(() => {
    expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
  })
  const row = await within(list).findByRole('link', { name: rowName })
  fireEvent.contextMenu(row)
  await screen.findByRole('menu', { name: /Actions for/ })
  fireEvent.click(await screen.findByTestId('rail-menu-move-to'))
  return screen.findByTestId('rail-menu-move-to-submenu')
}

function moveToEntries(submenu: HTMLElement) {
  return within(submenu)
    .getAllByRole('menuitem')
    .map((node) => ({
      id: node.getAttribute('data-move-to') ?? '',
      label: node.textContent ?? '',
      checked: node.getAttribute('aria-checked') === 'true',
      disabled: node.getAttribute('aria-disabled') === 'true' || (node as HTMLButtonElement).disabled,
    }))
}

describe('#1714 Move to lists every section the rail renders', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch(BLUEPRINTS))
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lists the auto sections the rail shows — the reported bug', async () => {
    renderRail()
    // The rail derives a CLI block because a CLI seat exists.
    await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const railIds = renderedSectionIds()
    expect(railIds).toContain('cli')

    const submenu = await openMoveTo(/Codey/)
    const ids = moveToEntries(submenu).map((entry) => entry.id)
    // Every auto section the RAIL rendered is present in the menu. Before the
    // fix this list began at the first custom section, so `cli` was absent.
    for (const railId of railIds) {
      if (railId === 'subagents') continue
      expect(ids).toContain(railId)
    }
    expect(ids).toContain('cli')
  })

  it('lists every custom section AND Unassigned AND New section together', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [
          { id: 'sec_alpha', name: 'Alpha', collapsed: false },
          { id: 'sec_beta', name: 'Beta', collapsed: false },
        ],
        membership: {},
        unassignedCollapsed: false,
      }),
    )
    renderRail()
    const submenu = await openMoveTo(/Codey/)
    const entries = moveToEntries(submenu)
    const byId = new Map(entries.map((entry) => [entry.id, entry]))
    for (const id of ['cli', 'sec_alpha', 'sec_beta', UNASSIGNED_SECTION_ID, NEW_SECTION_TARGET]) {
      expect(byId.has(id)).toBe(true)
    }
    expect(byId.get('sec_alpha')?.label).toContain('Alpha')
    expect(byId.get('sec_beta')?.label).toContain('Beta')
  })

  it('a section removed from the rail disappears from the menu (#1714 freshness)', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [
          { id: 'sec_alpha', name: 'Alpha' },
          { id: 'sec_beta', name: 'Beta' },
        ],
        membership: {},
        unassignedCollapsed: false,
      }),
    )
    renderRail()
    let submenu = await openMoveTo(/Codey/)
    expect(moveToEntries(submenu).map((e) => e.id)).toContain('sec_beta')

    // Delete "Beta" through its own header menu — the same store the menu reads.
    const betaHeader = screen
      .getAllByTestId('rail-section-header')
      .find((node) => node.getAttribute('data-section-id') === 'sec_beta')!
    fireEvent.contextMenu(within(betaHeader).getByRole('button'))
    const sectionMenu = await screen.findByRole('menu', { name: /Actions for Beta/ })
    fireEvent.click(within(sectionMenu).getByRole('menuitem', { name: 'Delete' }))

    await waitFor(() => {
      expect(renderedSectionIds()).not.toContain('sec_beta')
    })
    submenu = await openMoveTo(/Codey/)
    expect(moveToEntries(submenu).map((e) => e.id)).not.toContain('sec_beta')
  })

  it('the check mark names the section the row is rendered under, not Unassigned', async () => {
    renderRail()
    // CliAgent renders under the derived "CLI" block…
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const cliBlock = screen
      .getAllByTestId('rail-section')
      .find((node) => node.getAttribute('data-section-id') === 'cli')!
    expect(within(cliBlock).getByRole('link', { name: /CliAgent/ })).toBeInTheDocument()

    const submenu = await openMoveTo(/CliAgent/)
    const entries = moveToEntries(submenu)
    const checked = entries.filter((entry) => entry.checked)
    // Before the fix `Unassigned` carried the tick for a row the rail shows
    // under "CLI" — the menu disagreed with the rail it belongs to.
    expect(checked.map((entry) => entry.id)).toEqual(['cli'])
  })

  it('a custom section row ticks its own section and leaves Unassigned alone', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_alpha', name: 'Alpha' }],
        membership: { codey: 'sec_alpha' },
        unassignedCollapsed: false,
      }),
    )
    renderRail()
    const submenu = await openMoveTo(/Codey/)
    const checked = moveToEntries(submenu).filter((entry) => entry.checked)
    expect(checked.map((entry) => entry.id)).toEqual(['sec_alpha'])
  })

  it('choosing a listed section still moves the row (Success 5, no refresh)', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({ sections: [{ id: 'sec_alpha', name: 'Alpha' }], membership: {} }),
    )
    renderRail()
    const submenu = await openMoveTo(/CliAgent/)
    const alpha = within(submenu).getByRole('menuitem', { name: /Alpha/ })
    expect(alpha).not.toBeDisabled()
    fireEvent.click(alpha)
    await waitFor(() => {
      const block = screen
        .getAllByTestId('rail-section')
        .find((node) => node.getAttribute('data-section-id') === 'sec_alpha')!
      expect(within(block).getByRole('link', { name: /CliAgent/ })).toBeInTheDocument()
    })
    // And it is gone from the auto block it used to be harvested into.
    const cliBlock = screen
      .getAllByTestId('rail-section')
      .find((node) => node.getAttribute('data-section-id') === 'cli')
    if (cliBlock) {
      expect(within(cliBlock).queryByRole('link', { name: /CliAgent/ })).not.toBeInTheDocument()
    }
  })

  it('an auto section is listed and ticked but is not a choosable destination', async () => {
    renderRail()
    const submenu = await openMoveTo(/CliAgent/)
    const entries = moveToEntries(submenu)
    const cli = entries.find((entry) => entry.id === 'cli')!
    // Listed (Success 4) and honest about why it cannot be chosen: nothing can
    // be filed into a derived kind block, so offering it as a target would be a
    // click that silently does nothing.
    expect(cli).toBeDefined()
    expect(cli.checked).toBe(true)
    expect(cli.disabled).toBe(true)
    expect(
      within(submenu).getByRole('menuitem', { name: /CLI/ }).getAttribute('title'),
    ).toMatch(/seat kind/i)
  })

  it('Unassigned is offered for a team row, which no auto group claims', async () => {
    // A team row has no seat-kind group (`autoSectionOfRow` returns null for
    // `kind: 'team'`), so Unassigned really is a filing choice for it and must
    // stay clickable — this is the guard against over-disabling.
    const teamRender = renderRailWithTeam()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const teamRow = await within(list).findByRole('link', { name: /Crew/ })
    fireEvent.contextMenu(teamRow)
    await screen.findByRole('menu', { name: /Actions for/ })
    fireEvent.click(await screen.findByTestId('rail-menu-move-to'))
    const submenu = await screen.findByTestId('rail-menu-move-to-submenu')
    const unassigned = moveToEntries(submenu).find(
      (entry) => entry.id === UNASSIGNED_SECTION_ID,
    )!
    expect(unassigned.disabled).toBe(false)
    expect(unassigned.checked).toBe(true)
    teamRender.unmount()
  })

  it('Unassigned is honest-disabled for a row an auto group re-files', async () => {
    renderRail()
    const submenu = await openMoveTo(/CliAgent/)
    const unassigned = moveToEntries(submenu).find(
      (entry) => entry.id === UNASSIGNED_SECTION_ID,
    )!
    // Removing a CLI row's membership only drops it back into the derived CLI
    // block, so the click would do nothing. Offering it is the grey lie.
    expect(unassigned.disabled).toBe(true)
    expect(
      within(submenu).getByRole('menuitem', { name: 'Unassigned' }).getAttribute('title'),
    ).toMatch(/grouped by seat kind/i)
  })
})

describe('#1714 railMoveToDestinations — the enumeration itself', () => {
  const block = (id: string, name: string, custom: boolean): RailSectionBlockLike => ({
    id,
    name,
    custom,
  })

  it('is a superset check: every block appears exactly once, in rail order', () => {
    const blocks = [block('cli', 'CLI', false), block('sec_a', 'A', true), block('remote', 'Remote', false)]
    const out = railMoveToDestinations({
      blocks,
      currentSectionId: UNASSIGNED_SECTION_ID,
      autoGroup: 'cli',
    })
    expect(out.map((d) => d.id)).toEqual(['cli', 'sec_a', 'remote', UNASSIGNED_SECTION_ID])
  })

  it('only custom sections are selectable; auto sections are not destinations', () => {
    const out = railMoveToDestinations({
      blocks: [block('cli', 'CLI', false), block('sec_a', 'A', true)],
      currentSectionId: UNASSIGNED_SECTION_ID,
      autoGroup: null,
    })
    expect(out.find((d) => d.id === 'sec_a')?.selectable).toBe(true)
    for (const auto of out.filter((d) => isAutoSectionId(d.id))) {
      expect(auto.selectable).toBe(false)
      expect(auto.reason).toMatch(/seat kind/i)
    }
  })

  it('Unassigned is a destination unless an auto group would re-file the row', () => {
    const noGroup = railMoveToDestinations({
      blocks: [block('sec_a', 'A', true)],
      currentSectionId: UNASSIGNED_SECTION_ID,
      autoGroup: null,
    })
    expect(noGroup.find((d) => d.id === UNASSIGNED_SECTION_ID)?.selectable).toBe(true)

    const grouped = railMoveToDestinations({
      blocks: [block('sec_a', 'A', true)],
      currentSectionId: UNASSIGNED_SECTION_ID,
      autoGroup: 'cli',
    })
    const unassigned = grouped.find((d) => d.id === UNASSIGNED_SECTION_ID)!
    expect(unassigned.selectable).toBe(false)
    expect(unassigned.reason).toMatch(/grouped by seat kind/i)
  })

  it('keeps Unassigned listed even when the rail hid the empty block (#688)', () => {
    const out = railMoveToDestinations({
      blocks: [block('sec_a', 'A', true)],
      currentSectionId: 'sec_a',
      autoGroup: null,
    })
    expect(out.map((d) => d.id)).toContain(UNASSIGNED_SECTION_ID)
  })

  it('the auto group wins the check mark over the filed section', () => {
    const out = railMoveToDestinations({
      blocks: [block('cli', 'CLI', false), block('sec_a', 'A', true)],
      currentSectionId: 'sec_a',
      autoGroup: 'cli',
    })
    expect(out.find((d) => d.checked)?.id).toBe('cli')
  })

  it('with no auto group the filed section is the checked one', () => {
    const out = railMoveToDestinations({
      blocks: [block('sec_a', 'A', true), block('sec_b', 'B', true)],
      currentSectionId: 'sec_b',
      autoGroup: null,
    })
    expect(out.find((d) => d.checked)?.id).toBe('sec_b')
  })
})
