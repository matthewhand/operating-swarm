/**
 * #1705 — the rail's Ctrl/Shift multi-select: a real selection with a visible
 * outcome.
 *
 * Driven entirely through rendered output and real DOM events (modifier
 * clicks, Space, Escape, focus), never through handler wiring or source text.
 * The measured contract:
 *
 *   1. click a row            → still opens the seat (unchanged)
 *   2. Ctrl/Cmd+click         → toggles that row in / out
 *   3. Shift+click            → contiguous range from the anchor
 *   4. Space on a focused row → toggles (keyboard equivalent of Ctrl+click)
 *   5. Escape                 → clears
 *   6. bulk chrome appears ONLY at two or more selected seats
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { RAIL_SECTIONS_STORAGE_KEY } from '../../lib/railSections'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { declarations, ruleBodies } from '../../lib/__tests__/helpers/cssRules'

const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

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

/** The rail's selectable rows, in the order the user sees them. */
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

/** Ids of the rows between two of them, inclusive — the span a range covers. */
function spanIds(rows: HTMLElement[], from: HTMLElement, to: HTMLElement): string[] {
  const a = rows.indexOf(from)
  const b = rows.indexOf(to)
  expect(a).toBeGreaterThanOrEqual(0)
  expect(b).toBeGreaterThanOrEqual(0)
  const [lo, hi] = a <= b ? [a, b] : [b, a]
  return rows.slice(lo, hi + 1).map(rowId)
}

function selectedIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll<HTMLElement>('[data-selected="true"]')).map(rowId)
}

beforeEach(() => {
  localStorage.clear()
  // No favourites: the selection order under test is the section row order.
  localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(RAIL_SECTIONS_STORAGE_KEY, '[]')
  vi.stubGlobal('fetch', mockFetch())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('#1705 Ctrl/Cmd+click toggles one rail row', () => {
  it('selects and deselects without opening the seat, and stays hidden at one', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')

    fireEvent.click(alpha, { ctrlKey: true })
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'true'))
    expect(within(alpha).getByTestId('rail-selected-check')).toBeInTheDocument()
    // One selected seat is still just an open: the rail does not jump to a
    // bulk toolbar the user did not ask for.
    expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull()
    expect(within(alpha).getByTestId('rail-agent-name')).toHaveTextContent('Alpha')
    // A modifier click must not have navigated: the seat's own label is intact
    // and the rail is still mounted.
    expect(alpha.closest('[data-testid="os-agent-rail"]')).toBeTruthy()

    fireEvent.click(alpha, { ctrlKey: true })
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'false'))
    expect(screen.queryByTestId('rail-selected-check')).toBeNull()
  })

  it('Cmd+click is the same gesture on mac keyboards', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { metaKey: true })
    fireEvent.click(bravo, { metaKey: true })
    await waitFor(() =>
      expect(selectedIds(alpha.closest('nav') as HTMLElement)).toEqual(['alpha', 'bravo']),
    )
  })
})

describe('#1705 Shift+click selects the contiguous range from the anchor', () => {
  it('takes every row between the anchor and the target, in rail order', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const charlie = rowById(rows, 'charlie')
    const delta = rowById(rows, 'delta')
    const nav = alpha.closest('nav') as HTMLElement
    // Whatever else the rail seeds, the range must cover the three rows the
    // user sees between the anchor and the target — the middle one included.
    const expected = spanIds(rows, alpha, charlie)
    expect(expected).toHaveLength(3)
    expect(expected).toContain('alpha')
    expect(expected).toContain('charlie')
    expect(delta).toHaveAttribute('data-selected', 'false')

    fireEvent.click(alpha, { ctrlKey: true })
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'true'))
    fireEvent.click(charlie, { shiftKey: true })
    await waitFor(() => expect(selectedIds(nav).sort()).toEqual([...expected].sort()))
  })

  it('re-derives from the same anchor when the range runs backwards', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    const charlie = rowById(rows, 'charlie')
    const nav = alpha.closest('nav') as HTMLElement

    fireEvent.click(charlie, { ctrlKey: true })
    await waitFor(() => expect(charlie).toHaveAttribute('data-selected', 'true'))
    fireEvent.click(bravo, { shiftKey: true })
    await waitFor(() =>
      expect(selectedIds(nav).sort()).toEqual(spanIds(rows, bravo, charlie).sort()),
    )
    expect(alpha).toHaveAttribute('data-selected', 'false')
  })

  it('Shift+click with no anchor yet degrades to a single toggle', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    fireEvent.click(alpha, { shiftKey: true })
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'true'))
    expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull()
  })
})

describe('#1705 keyboard parity', () => {
  it('Space on a focused row toggles it and Enter still reaches the row', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    alpha.focus()
    expect(document.activeElement).toBe(alpha)
    // Rows are natively tabbable (link/button), so Tab/Shift+Tab walks them.
    expect(alpha.tabIndex).toBeGreaterThanOrEqual(0)
    expect(bravo.tabIndex).toBeGreaterThanOrEqual(0)

    fireEvent.keyDown(alpha, { key: ' ' })
    await waitFor(() => expect(alpha).toHaveAttribute('data-selected', 'true'))
    fireEvent.keyDown(bravo, { key: ' ' })
    await waitFor(() => expect(bravo).toHaveAttribute('data-selected', 'true'))
    expect(screen.getByTestId('os-rail-bulk-bar')).toHaveAttribute('data-selected-count', '2')

    // A modified Space is left to the browser (find-as-you-type, shortcuts):
    // it must NOT be read as a selection gesture.
    fireEvent.keyDown(bravo, { key: ' ', ctrlKey: true })
    expect(bravo).toHaveAttribute('data-selected', 'true')
  })

  it('Escape clears the whole selection from anywhere in the rail', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    await waitFor(() => expect(screen.getByTestId('os-rail-bulk-bar')).toBeInTheDocument())

    fireEvent.keyDown(document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull())
    expect(alpha).toHaveAttribute('data-selected', 'false')
    expect(bravo).toHaveAttribute('data-selected', 'false')
  })

  it('leaves Escape alone while the operator is typing in a field', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    await waitFor(() => expect(screen.getByTestId('os-rail-bulk-bar')).toBeInTheDocument())

    const hostname = screen.getByLabelText('Hostname')
    fireEvent.keyDown(hostname, { key: 'Escape' })
    expect(screen.getByTestId('os-rail-bulk-bar')).toBeInTheDocument()
  })
})

describe('#1705 bulk chrome appears only at two or more', () => {
  it('names the count, offers the actions, and is never a hover reveal', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    const charlie = rowById(rows, 'charlie')
    fireEvent.click(alpha, { ctrlKey: true })
    await waitFor(() => expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull())

    fireEvent.click(bravo, { ctrlKey: true })
    const bar = await screen.findByTestId('os-rail-bulk-bar')
    expect(bar).toHaveAttribute('data-selected-count', '2')
    expect(within(bar).getByTestId('os-rail-bulk-count')).toHaveTextContent('2 selected')
    expect(within(bar).getByRole('button', { name: 'Hide 2 selected' })).toBeInTheDocument()
    // Unpin is honest about a selection with nothing pinned in it.
    expect(within(bar).getByRole('button', { name: 'Unpin selected' })).toBeDisabled()

    fireEvent.click(charlie, { ctrlKey: true })
    await waitFor(() =>
      expect(screen.getByTestId('os-rail-bulk-bar')).toHaveAttribute('data-selected-count', '3'),
    )
  })

  it('Clear empties the selection and takes the bar with it', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    const bar = await screen.findByTestId('os-rail-bulk-bar')
    fireEvent.click(within(bar).getByRole('button', { name: 'Clear selection' }))
    await waitFor(() => expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull())
    expect(alpha).toHaveAttribute('data-selected', 'false')
    expect(bravo).toHaveAttribute('data-selected', 'false')
  })

  it('the count is a live region, so the selection is announced', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    const bar = await screen.findByTestId('os-rail-bulk-bar')
    expect(within(bar).getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(bar).toHaveAccessibleName('Bulk actions for 2 selected agents')
  })
})

describe('#1705 bulk Hide writes the hidden-agents store for the whole selection', () => {
  it('persists every selected id and clears the selection', async () => {
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    const charlie = rowById(rows, 'charlie')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    fireEvent.click(charlie, { ctrlKey: true })
    const bar = await screen.findByTestId('os-rail-bulk-bar')
    fireEvent.click(within(bar).getByRole('button', { name: 'Hide 3 selected' }))

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')
      expect(stored).toEqual(expect.arrayContaining(['alpha', 'bravo', 'charlie']))
    })
    await waitFor(() => expect(screen.queryByTestId('os-rail-bulk-bar')).toBeNull())
    // The hidden rows leave the list, which is the point of the action.
    await waitFor(() => expect(screen.queryByText('Alpha')).toBeNull())
    expect(screen.queryByText('Bravo')).toBeNull()
    expect(screen.queryByText('Charlie')).toBeNull()
  })

  it('leaves the already-hidden set intact', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['delta']))
    renderRail()
    const rows = await railRows()
    const alpha = rowById(rows, 'alpha')
    const bravo = rowById(rows, 'bravo')
    fireEvent.click(alpha, { ctrlKey: true })
    fireEvent.click(bravo, { ctrlKey: true })
    const bar = await screen.findByTestId('os-rail-bulk-bar')
    fireEvent.click(within(bar).getByRole('button', { name: 'Hide 2 selected' }))
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')
      expect(stored).toEqual(expect.arrayContaining(['alpha', 'bravo', 'delta']))
    })
  })
})

describe('#1705 the selected state is legible without relying on colour', () => {
  it('paints an outline AND a glyph on the row (never a role hue)', () => {
    const selected = declarations(ruleBodies(css, ".os-agent-row[data-selected='true']")[0] ?? '')
    // An outline, not a background-only state: it composites over hover/active.
    expect(selected['outline']).toMatch(/2px solid var\(--color-primary\)/)
    expect(selected['background']).toMatch(/color-mix/)
    // Role colour stays on `.os-agent-role-badge` (AGENTS.md) — a row must not
    // grow a fill, a left border or a background outline in a role hue.
    expect(selected['border-left']).toBeUndefined()
    expect(selected['background']).not.toMatch(/--color-primary[^)]*\)/)
  })

  it('gives the row a real focus-visible ring', () => {
    const focus = declarations(ruleBodies(css, '.os-agent-row:focus-visible')[0] ?? '')
    expect(focus['outline']).toMatch(/2px solid var\(--color-primary\)/)
  })

  it('gives every bulk action a focus-visible ring too', () => {
    const focus = declarations(ruleBodies(css, '.os-rail-bulk-bar__btn:focus-visible')[0] ?? '')
    expect(focus['outline']).toMatch(/2px solid var\(--color-primary\)/)
  })
})
