import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { ToastProvider } from '../DaisyUI'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { notifyCliRunState, resetCliRunState } from '../../lib/cliRunState'

const blueprints = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    rail: true,
  },
]

function mockFetch(options?: { cliRunning?: boolean }) {
  return vi.fn().mockImplementation(async (input: RequestInfo, _init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/v1/cli-agents/runs/terminate')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'cli_run_terminate',
          agent: 'cli_agent',
          status: 'terminated',
          running: false,
        }),
      } as Response
    }
    if (url.includes('/v1/cli-agents/runs')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'cli_run_status',
          agent: 'cli_agent',
          running: Boolean(options?.cliRunning),
          count: options?.cliRunning ? 1 : 0,
        }),
      } as Response
    }
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
    if (url.includes('team_rosters') || url.includes('team-rosters')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 'research',
              object: 'team_roster',
              name: 'Research',
              members: [{ id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' }],
              wires: { handoff: true, as_tool: true },
            },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/cli-agents')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          clis: ['grok'],
          native_consensus: {},
          catalog: {},
          rail: [
            {
              id: 'cli_agent',
              object: 'cli.agent',
              name: 'cli_agent',
              cli: 'grok',
              kind: 'cli',
              description: 'Host CLI',
              installed: true,
            },
            {
              id: 'api_agent',
              object: 'cli.agent',
              name: 'api_agent',
              cli: '',
              kind: 'api',
              description: 'LiteLLM',
              installed: true,
            },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/remotes')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 'omb',
              kind: 'omb',
              title: 'OpenMousBot',
              source: 'user',
              configured: true,
              base_url: 'http://localhost:9',
              agents: [{ id: 'cos', name: 'Pat' }],
            },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/herdr-agents')) {
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
    }
    if (url.includes('/v1/cli-sessions')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'cli_session_list',
          agent_id: 'cli_agent',
          cli: 'grok',
          can_list: false,
          sessions: [],
          recent: [],
          empty_reason: "This CLI can't list sessions",
          activity_sot: 'swarm',
        }),
      } as Response
    }
    return { ok: true, status: 200, json: async () => ({ object: 'list', data: blueprints }) } as Response
  })
}

function renderSidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open onClose={() => undefined} />
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  )
}

describe('REQ-114 rail Terminate', () => {
  beforeEach(() => {
    resetCliRunState()
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetCliRunState()
    localStorage.clear()
  })

  it('disables Terminate on an idle CLI row and keeps the row', async () => {
    vi.stubGlobal('fetch', mockFetch({ cliRunning: false }))
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /cli_agent/ }))
    const stop = await screen.findByRole('menuitem', { name: /^Terminate$/i })
    expect(stop).toBeDisabled()
    expect(stop).toHaveAttribute('title', 'Nothing running')
    expect(within(list).getByRole('link', { name: /cli_agent/ })).toBeInTheDocument()
  })

  it('omits Terminate on API, team, and remote rows', async () => {
    vi.stubGlobal('fetch', mockFetch())
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })

    fireEvent.contextMenu(await within(list).findByRole('link', { name: /api_agent/ }))
    expect(screen.queryByRole('menuitem', { name: /^Terminate$/i })).not.toBeInTheDocument()

    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Codey/ }))
    expect(screen.queryByRole('menuitem', { name: /^Terminate$/i })).not.toBeInTheDocument()

    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Research \(team\)/ }))
    expect(screen.queryByRole('menuitem', { name: /^Terminate$/i })).not.toBeInTheDocument()

    fireEvent.contextMenu(await within(list).findByRole('link', { name: /OpenMousBot \(remote\)/ }))
    expect(screen.queryByRole('menuitem', { name: /^Terminate$/i })).not.toBeInTheDocument()
  })

  it('terminates a running CLI process, toasts, and leaves the agent row', async () => {
    const fetchMock = mockFetch({ cliRunning: true })
    vi.stubGlobal('fetch', fetchMock)
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    notifyCliRunState('cli_agent', true)
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /cli_agent/ }))
    const stop = await screen.findByRole('menuitem', { name: /^Terminate$/i })
    expect(stop).toBeEnabled()
    fireEvent.click(stop)
    await waitFor(() => {
      const posted = fetchMock.mock.calls.some(
        (call: unknown[]) => {
          const [input, init] = call as [RequestInfo, RequestInit | undefined]
          const url = String(input)
          return (
            url.includes('/v1/cli-agents/runs/terminate') &&
            (init?.method || 'GET').toUpperCase() === 'POST'
          )
        },
      )
      expect(posted).toBe(true)
    })
    expect(await screen.findByText('Process stopped.')).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /cli_agent/ })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /^Delete$/i })).not.toBeInTheDocument()
  })
})
