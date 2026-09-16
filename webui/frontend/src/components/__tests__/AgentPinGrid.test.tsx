import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AgentPinGrid from '../AgentPinGrid'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { endAgentDrag } from '../../lib/pinnedAgents'

const blueprints = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    rail: true,
  },
  {
    id: 'stewie',
    object: 'blueprint' as const,
    name: 'Stewie',
    description: 'Helpful agent',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    rail: true,
  },
]

function mockDataTransfer() {
  const store: Record<string, string> = {}
  const types: string[] = []
  return {
    dropEffect: 'none',
    effectAllowed: 'all',
    types,
    setData(type: string, value: string) {
      store[type] = value
      if (!types.includes(type)) types.push(type)
    },
    getData(type: string) {
      return store[type] ?? ''
    },
    clearData() {
      Object.keys(store).forEach((key) => delete store[key])
      types.length = 0
    },
  }
}

function renderChrome(initialEntry = '/') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AgentPinGrid />
        <AgentSidebar open onClose={() => undefined} />
        <Routes>
          <Route path="/" element={<p>Home</p>} />
          <Route path="/chat" element={<p>Chat for tests</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AgentPinGrid drag-to-pin', () => {
  beforeEach(() => {
    localStorage.clear()
    endAgentDrag()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/preferences')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: true,
              favourites: [],
              hidden_agents: [],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents') || url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [], rail: [] }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: blueprints }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    endAgentDrag()
    localStorage.clear()
  })

  it('has an unlabeled drop grid (no Favourites heading) that accepts a sidepane row', async () => {
    renderChrome()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    expect(codey).toHaveAttribute('draggable', 'true')

    expect(screen.queryByText(/Favourites/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Favourites/i })).not.toBeInTheDocument()
    expect(screen.queryByTestId('agent-pin-grid')).not.toBeInTheDocument()

    const dt = mockDataTransfer()
    fireEvent.dragStart(codey, { dataTransfer: dt })
    const grid = screen.getByTestId('agent-pin-grid')
    fireEvent.dragOver(grid, { dataTransfer: dt })
    fireEvent.drop(grid, { dataTransfer: dt })
    fireEvent.dragEnd(codey, { dataTransfer: dt })

    const tile = await within(grid).findByRole('link', { name: /Codey/ })
    expect(tile).toHaveAttribute('href', '/chat?blueprint=codey')
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])
  })

  it('REQ-171B: pins of each kind use kind-aware hrefs', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([
        { id: 'codey', name: 'Codey' },
        { id: 'team:demo', name: 'Demo' },
        { id: 'remote:omb', name: 'OpenMousBot' },
        { id: 'herdr:w3:p1', name: 'w3:p1' },
      ]),
    )
    renderChrome()

    const grid = screen.getByTestId('agent-pin-grid')
    const codey = await within(grid).findByRole('link', { name: /Codey/ })
    const team = within(grid).getByRole('link', { name: /Demo/ })
    const remote = within(grid).getByRole('link', { name: /OpenMousBot/ })
    const herdr = within(grid).getByRole('link', { name: /w3:p1/ })

    expect(codey).toHaveAttribute('href', '/chat?blueprint=codey')
    expect(team).toHaveAttribute('href', '/chat?team=demo')
    expect(team.getAttribute('href')).not.toMatch(/blueprint=/)
    expect(remote).toHaveAttribute('href', '/chat?remote=omb')
    expect(remote.getAttribute('href')).not.toMatch(/blueprint=/)
    expect(herdr).toHaveAttribute('href', '/teams/#herdr-members')
  })

  it('restores tiles from localStorage and lets the user remove one', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'stewie', name: 'Stewie' }]),
    )
    renderChrome('/chat?blueprint=stewie')

    const grid = screen.getByTestId('agent-pin-grid')
    const tile = await within(grid).findByRole('link', { name: /Stewie/ })
    expect(tile).toHaveAttribute('aria-current', 'page')

    fireEvent.click(screen.getByRole('button', { name: /Remove Stewie/i }))
    await waitFor(() => {
      expect(screen.queryByTestId('agent-pin-grid')).not.toBeInTheDocument()
    })
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([])
    expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
  })
})
