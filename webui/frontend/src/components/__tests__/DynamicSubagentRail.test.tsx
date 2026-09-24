import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import {
  clearDynamicSubagents,
  loadDynamicSubagents,
  registerDynamicSubagent,
  updateDynamicSubagentStatus,
  DYNAMIC_SUBAGENT_SPAWNED_EVENT,
} from '../../lib/dynamicSubagents'

const baseBlueprints = [
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
    role: 'engineer',
    rail: true,
  },
  {
    id: 'support_agent',
    object: 'blueprint' as const,
    name: 'Support Agent',
    description: 'Help Desk',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    role: 'support',
    rail: true,
  },
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
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    if (url.includes('blueprints')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: baseBlueprints }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ object: 'list', data: [] }),
    } as Response
  })
}

describe('Dynamic Subagents Rail Integration (AgentSidebar first-class citizen)', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    // #1098 upkeep: jsdom's 1024px default is the #1084 laptop tier, which
    // collapses section headers. These pins target rail-row behavior, not
    // responsive layout — run at the desktop viewport.
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
    window.localStorage.clear()
    clearDynamicSubagents()
    vi.stubGlobal('fetch', mockFetch())
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
  })

  afterEach(() => {
    window.localStorage.clear()
    clearDynamicSubagents()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function renderSidebar(blueprints = baseBlueprints) {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open={true} blueprints={blueprints} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('registers dynamic subagent and verifies it persists in storage and dispatches event', () => {
    const listener = vi.fn()
    window.addEventListener(DYNAMIC_SUBAGENT_SPAWNED_EVENT, listener)

    const list = registerDynamicSubagent({
      id: 'sub-review',
      name: 'Code Reviewer',
      parentAgentId: 'codey',
      role: 'engineer',
      status: 'completed',
      summary: 'Reviewed changes and checked coverage',
    })

    expect(list).toHaveLength(1)
    expect(list[0].id).toBe('sub-review')
    expect(list[0].name).toBe('Code Reviewer')
    expect(loadDynamicSubagents()).toHaveLength(1)
    expect(loadDynamicSubagents()[0].name).toBe('Code Reviewer')
    expect(listener).toHaveBeenCalledTimes(1)

    window.removeEventListener(DYNAMIC_SUBAGENT_SPAWNED_EVENT, listener)
  })

  it('renders dynamically spawned subagent on the sidepane rail as a first-class citizen', async () => {
    registerDynamicSubagent({
      id: 'sub-review',
      name: 'Code Reviewer',
      parentAgentId: 'codey',
      role: 'engineer',
      status: 'completed',
      summary: 'Static analysis and test verifications',
    })

    renderSidebar()

    // Subagents section header is present
    expect(await screen.findByText('Subagents')).toBeInTheDocument()

    // Subagent item is visible as a first-class citizen on the rail
    const subagentRow = screen.getByText('Code Reviewer')
    expect(subagentRow).toBeInTheDocument()

    // Has rail ID and list item container
    const railItem = document.querySelector('[data-rail-id="sub-review"]')
    expect(railItem).toBeInTheDocument()
    expect(within(railItem as HTMLElement).getByText('Code Reviewer')).toBeInTheDocument()
    // Role badge overlay
    expect(within(railItem as HTMLElement).getByText('Engineer')).toBeInTheDocument()
  })

  it('reactively displays dynamically spawned subagents when spawned event fires while mounted', async () => {
    renderSidebar()

    // Initially no Subagents section
    expect(screen.queryByText('Subagents')).not.toBeInTheDocument()
    expect(screen.queryByText('Live Assistant')).not.toBeInTheDocument()

    // Dynamically spawn subagent during runtime
    await act(async () => {
      registerDynamicSubagent({
        id: 'sub-live',
        name: 'Live Assistant',
        role: 'support',
        status: 'running',
        summary: 'Handling interactive query',
      })
    })

    // Now Subagents section and item appear reactively!
    expect(await screen.findByText('Subagents')).toBeInTheDocument()
    expect(screen.getByText('Live Assistant')).toBeInTheDocument()
    expect(document.querySelector('[data-rail-id="sub-live"]')).toBeInTheDocument()
  })

  it('supports multiple dynamic subagents and toggling the Subagents section', async () => {
    registerDynamicSubagent({
      id: 'sub-1',
      name: 'Alpha Worker',
      role: 'engineer',
      status: 'completed',
    })
    registerDynamicSubagent({
      id: 'sub-2',
      name: 'Beta Tester',
      role: 'skeptic',
      status: 'running',
    })

    renderSidebar()

    const subagentsHeader = await screen.findByText('Subagents')
    expect(subagentsHeader).toBeInTheDocument()
    expect(screen.getByText('Alpha Worker')).toBeInTheDocument()
    expect(screen.getByText('Beta Tester')).toBeInTheDocument()

    // Toggle collapse on Subagents section header
    fireEvent.click(subagentsHeader)

    // When collapsed, rows in the section are hidden
    expect(screen.queryByText('Alpha Worker')).not.toBeInTheDocument()
    expect(screen.queryByText('Beta Tester')).not.toBeInTheDocument()

    // Click again to expand
    fireEvent.click(subagentsHeader)
    expect(screen.getByText('Alpha Worker')).toBeInTheDocument()
    expect(screen.getByText('Beta Tester')).toBeInTheDocument()
  })

  it('updates dynamic subagent status reactively', async () => {
    registerDynamicSubagent({
      id: 'sub-status',
      name: 'Status Agent',
      role: 'engineer',
      status: 'running',
      summary: 'Task in progress',
    })

    renderSidebar()
    expect(await screen.findByText('Status Agent')).toBeInTheDocument()

    await act(async () => {
      updateDynamicSubagentStatus('sub-status', 'completed', 'Task finished successfully')
    })

    const updated = loadDynamicSubagents().find((s) => s.id === 'sub-status')
    expect(updated?.status).toBe('completed')
    expect(updated?.summary).toBe('Task finished successfully')
  })
})

// #843: subagent spawn timestamps must survive the SidebarAgent mapping —
// the rail's time slot reads last_message_at, which used to be dropped here,
// leaving subagent rows as the only seats without an activity time.
describe('Dynamic Subagent activity timestamps (#843)', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    window.localStorage.clear()
    clearDynamicSubagents()
    vi.stubGlobal('fetch', mockFetch())
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
  })

  afterEach(() => {
    window.localStorage.clear()
    clearDynamicSubagents()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders the spawn timestamp on the subagent rail row', async () => {
    registerDynamicSubagent({
      id: 'sub-timed',
      name: 'Timed Worker',
      parentAgentId: 'codey',
      role: 'engineer',
      status: 'completed',
      timestamp: Date.now(),
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open={true} blueprints={baseBlueprints} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(
      () => {
        const row = document.querySelector('[data-rail-id="sub-timed"]')
        expect(row).not.toBeNull()
        expect(within(row as HTMLElement).getByText('Just now')).toBeInTheDocument()
      },
      { timeout: 5000 },
    )
  })
})
