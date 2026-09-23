/**
 * #507 — Hide/Unhide is broken across surfaces.
 *
 * Repro cases from the issue (written BEFORE the fix; all four fail on the
 * unfixed tree):
 *   1. Store split: hiding via agent-store (Agent Router) must move the
 *      mounted rail's row, and unhide must bring it back — no remount.
 *   2. Same-tab cross-surface: a plain write to the canonical store (what the
 *      Search palette / Hidden-Bots popup does) must update the rail WITHOUT
 *      any synthetic `storage` dispatch (real browsers never fire `storage`
 *      in the tab that wrote).
 *   3. CLI/API policy: Hide on a CLI or API seat must actually hide (old
 *      behaviour: silent no-op) and be reversible from the canonical store.
 *   4. Canonical adoption: a pre-mount canonical list is authoritative.
 */
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest'
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import {
  HIDDEN_AGENTS_STORAGE_KEY,
  loadHiddenAgentIds,
  saveHiddenAgentIds,
  unhideAgentId,
} from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import type * as AgentStoreModule from '../../lib/agent-store'

let useAgentStore: typeof AgentStoreModule.useAgentStore

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
  blueprint('codey', 'Codey', 'Code assistant'),
  blueprint('stewie', 'Stewie', 'Helpful agent'),
  blueprint('gate', 'Gate', 'Role: gate'),
  blueprint('skeptic', 'Skeptic', 'Role: skeptic'),
]

const rosters = [
  {
    id: 'research',
    object: 'team_roster' as const,
    name: 'Research',
    members: [{ id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' }],
    wires: { handoff: true, as_tool: true },
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
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    if (url.includes('team_rosters') || url.includes('team-rosters')) {
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: rosters }) } as Response
    }
    if (url.includes('/v1/cli-agents') && !url.includes('/runs')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          clis: ['grok'],
          native_consensus: {},
          catalog: {},
          rail: [
            { id: 'cli_agent', object: 'cli.agent', name: 'cli_agent', cli: 'grok', kind: 'cli', description: 'Host CLI', installed: true },
            { id: 'api_agent', object: 'cli.agent', name: 'api_agent', cli: '', kind: 'api', description: 'LiteLLM', installed: true },
          ],
        }),
      } as Response
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
    if (url.includes('/v1/agents/designs')) {
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
    }
    if (url.includes('/v1/remotes')) {
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
    }
    if (url.includes('/v1/herdr-agents')) {
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
    }
    return { ok: true, status: 200, json: async () => ({ object: 'list', data: blueprints }) } as Response
  })
}

function renderSidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function storedHidden(): string[] {
  return JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')
}

async function railList() {
  return screen.findByRole('navigation', { name: 'Agent list' })
}

beforeAll(async () => {
  // Import AFTER jsdom exists but with a clean localStorage, mirroring app boot.
  localStorage.clear()
  ;({ useAgentStore } = await import('../../lib/agent-store'))
})

describe('#507 hide/unhide across surfaces', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('store split: agent-store hide moves the mounted rail row; unhide restores it (no remount)', async () => {
    renderSidebar()
    const list = await railList()
    await within(list).findByRole('link', { name: /Codey/ })

    // Hide from the Agent Router surface (writes the store, bridges canonical).
    useAgentStore.getState().hideAgent('codey')
    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toContain('codey')

    // Unhide from the same surface — the row must return, no reload/remount.
    useAgentStore.getState().unhideAgent('codey')
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    })
    expect(useAgentStore.getState().hiddenAgentIds).not.toContain('codey')
  })

  it('same-tab canonical write updates the rail without any synthetic storage event', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['stewie']))
    renderSidebar()
    const list = await railList()
    await within(list).findByRole('link', { name: /Codey/ })
    expect(within(list).queryByRole('link', { name: /Stewie/ })).not.toBeInTheDocument()

    // What the Hidden-Bots search popup effectively does — a bare write.
    // Deliberately NOT dispatching `storage`: browsers never fire it same-tab.
    saveHiddenAgentIds([])
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Stewie/ })).toBeInTheDocument()
    })
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
  })

  it('CLI/API policy: Hide on a CLI seat actually hides and is reversible; API seat likewise', async () => {
    renderSidebar()
    const list = await railList()
    const cli = await within(list).findByRole('link', { name: /cli_agent/ })
    fireEvent.contextMenu(cli)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Hide from sidebar$/i }))
    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /cli_agent/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toContain('cli_agent')

    // Unhide from the canonical store (Search palette path).
    unhideAgentId('cli_agent', loadHiddenAgentIds())
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /cli_agent/ })).toBeInTheDocument()
    })

    const api = await within(list).findByRole('link', { name: /api_agent/ })
    fireEvent.contextMenu(api)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Hide from sidebar$/i }))
    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /api_agent/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toContain('api_agent')
  })

  it('canonical adoption: a pre-mount canonical list is authoritative for the rail', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['codey']))
    renderSidebar()
    const list = await railList()
    await within(list).findByRole('link', { name: /Stewie/ })
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
  })
})
