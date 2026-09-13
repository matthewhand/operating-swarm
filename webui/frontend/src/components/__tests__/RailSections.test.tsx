import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { ToastProvider } from '../DaisyUI'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import {
  NEW_SECTION_PLACEHOLDER,
  RAIL_SECTIONS_STORAGE_KEY,
  UNASSIGNED_SECTION_ID,
} from '../../lib/railSections'

const yesterday = Date.now() - 26 * 60 * 60 * 1000

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
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
          data: [
            {
              id: 'codey',
              object: 'blueprint',
              name: 'Codey',
              description: 'Code assistant',
              last_message_at: yesterday,
              rail: true,
            },
            {
              id: 'stewie',
              object: 'blueprint',
              name: 'Stewie',
              description: 'Helpful agent',
              last_message_at: yesterday,
              rail: true,
            },
            {
              id: 'rakazo',
              object: 'blueprint',
              name: 'Rakazo',
              description: 'Remote helper',
              rail: true,
            },
          ],
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
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open onClose={() => undefined} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function loadedList() {
  const list = await screen.findByRole('navigation', { name: 'Agent list' })
  await waitFor(() => {
    expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
  })
  return list
}

function sectionById(id: string) {
  return screen.getAllByTestId('rail-section').find((node) => node.getAttribute('data-section-id') === id)
}

async function openAgentMenu(name: RegExp) {
  const list = await loadedList()
  const row = await within(list).findByRole('link', { name })
  fireEvent.contextMenu(row)
  return screen.findByRole('menu', { name: /Actions for/ })
}

async function chooseMoveTo(target: string | RegExp) {
  fireEvent.click(await screen.findByTestId('rail-menu-move-to'))
  const submenu = await screen.findByTestId('rail-menu-move-to-submenu')
  const item =
    typeof target === 'string'
      ? within(submenu).getByRole('menuitem', { name: target })
      : within(submenu).getByRole('menuitem', { name: target })
  fireEvent.click(item)
}

describe('REQ-209 sidepane agent sections', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('keeps the pin grid above Unassigned and shows activity stamps on rows', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'stewie', name: 'Stewie' }]),
    )
    renderRail()
    const rail = await screen.findByTestId('os-agent-rail')
    const list = await loadedList()
    const grid = screen.getByTestId('agent-fav-grid')
    const unassigned = sectionById(UNASSIGNED_SECTION_ID)
    expect(unassigned).toBeTruthy()
    expect(within(unassigned!).getByTestId('rail-section-name')).toHaveTextContent('Unassigned')
    expect(grid.compareDocumentPosition(unassigned!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(within(grid).getByRole('link', { name: 'Stewie' })).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Stewie/ })).not.toBeInTheDocument()
    expect(rail.querySelector('[data-testid="agent-fav-grid"]')).toBe(grid)
    const stamps = within(list).getAllByTestId('rail-row-timestamp')
    expect(stamps.length).toBeGreaterThan(0)
    expect(stamps[0].textContent).toMatch(/Yesterday|Today|AM|PM/)
  })

  it('right-click Move to → New section creates a section, places the agent, and focuses the title', async () => {
    renderRail()
    await openAgentMenu(/Rakazo/)
    await chooseMoveTo(NEW_SECTION_PLACEHOLDER)
    const rename = await screen.findByTestId('rail-section-rename')
    expect(rename).toHaveFocus()
    fireEvent.change(rename, { target: { value: 'stuff' } })
    fireEvent.blur(rename)
    await waitFor(() => {
      expect(screen.queryByTestId('rail-section-rename')).not.toBeInTheDocument()
    })
    const custom = screen
      .getAllByTestId('rail-section')
      .find((node) => node.getAttribute('data-section-custom') === 'true')
    expect(custom).toBeTruthy()
    expect(within(custom!).getByTestId('rail-section-name')).toHaveTextContent('stuff')
    expect(within(custom!).getByRole('link', { name: /Rakazo/ })).toBeInTheDocument()
    const unassigned = sectionById(UNASSIGNED_SECTION_ID)!
    expect(within(unassigned).queryByRole('link', { name: /Rakazo/ })).not.toBeInTheDocument()
    expect(within(unassigned).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    const stored = JSON.parse(localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY) || '{}')
    expect(stored.sections[0].name).toBe('stuff')
    expect(stored.membership.rakazo).toBe(stored.sections[0].id)
  })

  it('Move to existing / Unassigned persists across remount', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_stuff', name: 'stuff', collapsed: false }],
        membership: { rakazo: 'sec_stuff' },
        unassignedCollapsed: false,
      }),
    )
    const first = renderRail()
    await loadedList()
    expect(within(sectionById('sec_stuff')!).getByRole('link', { name: /Rakazo/ })).toBeInTheDocument()
    await openAgentMenu(/Codey/)
    await chooseMoveTo('stuff')
    await waitFor(() => {
      expect(within(sectionById('sec_stuff')!).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    })
    first.unmount()
    renderRail()
    const list = await loadedList()
    expect(within(sectionById('sec_stuff')!).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    await openAgentMenu(/Codey/)
    fireEvent.click(await screen.findByTestId('rail-menu-move-to'))
    const submenu = await screen.findByTestId('rail-menu-move-to-submenu')
    expect(within(submenu).getByRole('menuitem', { name: 'stuff' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    fireEvent.click(within(submenu).getByRole('menuitem', { name: 'Unassigned' }))
    await waitFor(() => {
      expect(within(sectionById(UNASSIGNED_SECTION_ID)!).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    })
    expect(within(list).getAllByTestId('spill-hotkey').length).toBeGreaterThan(0)
  })

  it('#173: right-clicking the rail background creates an empty section and focuses its title', async () => {
    renderRail()
    const list = await loadedList()
    fireEvent.contextMenu(list)
    const menu = await screen.findByRole('menu', { name: 'Actions for Side pane' })
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'New section' }))
    const rename = await screen.findByTestId('rail-section-rename')
    expect(rename).toHaveFocus()
    expect(rename).toHaveValue('')
    fireEvent.change(rename, { target: { value: 'locked comms' } })
    fireEvent.blur(rename)
    await waitFor(() => {
      expect(screen.queryByTestId('rail-section-rename')).not.toBeInTheDocument()
    })
    const custom = screen
      .getAllByTestId('rail-section')
      .find((node) => node.getAttribute('data-section-custom') === 'true')
    expect(custom).toBeTruthy()
    expect(within(custom!).getByTestId('rail-section-name')).toHaveTextContent('locked comms')
    // Empty until an agent is dragged in — the drop hint is the move path.
    expect(within(custom!).getByTestId('rail-section-empty')).toHaveTextContent('Drag agents here')
    expect(within(sectionById(UNASSIGNED_SECTION_ID)!).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
  })

  it('collapses like Hidden Bots (name + count, hover toggle) and persists', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_stuff', name: 'stuff', collapsed: false }],
        membership: { rakazo: 'sec_stuff' },
        unassignedCollapsed: false,
      }),
    )
    const first = renderRail()
    await loadedList()
    const stuff = sectionById('sec_stuff')!
    expect(within(stuff).getByTestId('rail-section-count')).toHaveTextContent('1')
    expect(within(stuff).getByTestId('rail-section-toggle')).toBeInTheDocument()
    fireEvent.click(within(stuff).getByRole('button', { name: /Collapse stuff/ }))
    await waitFor(() => {
      expect(sectionById('sec_stuff')).toHaveAttribute('data-collapsed', 'true')
    })
    expect(within(sectionById('sec_stuff')!).queryByRole('link', { name: /Rakazo/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY) || '{}').sections[0].collapsed).toBe(
      true,
    )
    first.unmount()
    renderRail()
    await loadedList()
    expect(sectionById('sec_stuff')).toHaveAttribute('data-collapsed', 'true')
    expect(within(sectionById('sec_stuff')!).getByTestId('rail-section-count')).toHaveTextContent('1')
  })

  it('empty custom section shows Drag agents here; section menu rename / move / delete', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [
          { id: 'sec_a', name: 'alpha', collapsed: false },
          { id: 'sec_b', name: 'beta', collapsed: false },
        ],
        membership: {},
        unassignedCollapsed: false,
      }),
    )
    renderRail()
    await loadedList()
    const alpha = sectionById('sec_a')!
    expect(within(alpha).getByTestId('rail-section-empty')).toHaveTextContent('Drag agents here')
    fireEvent.contextMenu(within(alpha).getByTestId('rail-section-header'))
    const menu = await screen.findByRole('menu', { name: 'Actions for alpha' })
    expect(within(menu).getByRole('menuitem', { name: 'Rename' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Move up' })).toBeDisabled()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Move down' }))
    await waitFor(() => {
      const ids = screen.getAllByTestId('rail-section').map((node) => node.getAttribute('data-section-id'))
      expect(ids.slice(0, 2)).toEqual(['sec_b', 'sec_a'])
    })
    fireEvent.contextMenu(within(sectionById('sec_a')!).getByTestId('rail-section-header'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    const rename = await screen.findByTestId('rail-section-rename')
    fireEvent.change(rename, { target: { value: 'renamed' } })
    fireEvent.blur(rename)
    await waitFor(() => {
      expect(within(sectionById('sec_a')!).getByTestId('rail-section-name')).toHaveTextContent('renamed')
    })
    fireEvent.contextMenu(within(sectionById('sec_a')!).getByTestId('rail-section-header'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    await waitFor(() => {
      expect(sectionById('sec_a')).toBeUndefined()
    })
    expect(sectionById(UNASSIGNED_SECTION_ID)).toBeTruthy()
  })
})
