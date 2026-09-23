import { useEffect, useState } from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useSearchParams } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import SearchPalette, { OPEN_SEARCH_EVENT, type SearchPaletteOptions } from '../SearchPalette'
import { HIDDEN_AGENTS_STORAGE_KEY, loadHiddenAgentIds, unhideAgentId } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { HOSTNAME_STORAGE_KEY, dispatchHostnameChanged } from '../../lib/hostname'
import {
  GENERATION_COMPLETE_EVENT,
  RAIL_ORDER_STORAGE_KEY,
} from '../../lib/railOrder'
import {
  BUMP_COMPLETED_KEY,
  BUMP_SCOPE_KEY,
  HOSTNAME_OVERRIDE_KEY,
} from '../../lib/settingsPrefs'
import { RAIL_SECTIONS_STORAGE_KEY } from '../../lib/railSections'
import { DELETED_RAIL_IDS_KEY } from '../../lib/deletedRailIds'
import { saveAgentSessions, type AgentSession } from '../../lib/scaleOutSessions'
import { publishChatConnection, resetChatConnection } from '../../lib/chatConnection'
import { notifyCliRunState, resetCliRunState } from '../../lib/cliRunState'
import {
  NEEDS_APPROVAL_LABEL,
  notifyApprovalWait,
  resetAgentAttention,
} from '../../lib/agentAttention'

function blueprint(
  id: string,
  name: string,
  description: string,
  role?: string,
  avatar_path?: string,
) {
  const actualRole = role && !role.startsWith('/') ? role : undefined
  const actualAvatar = avatar_path || (role && role.startsWith('/') ? role : undefined)
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
    ...(actualRole ? { role: actualRole } : {}),
    ...(actualAvatar ? { avatar_path: actualAvatar } : {}),
    rail: true,
  }
}

const blueprints = [
  blueprint('codey', 'Codey', 'Code assistant', '/avatars/codey_avatar.png'),
  blueprint('stewie', 'Stewie', 'Helpful agent'),
  blueprint('gate', 'Gate', 'Role: gate'),
  blueprint('skeptic', 'Skeptic', 'Role: skeptic'),
  blueprint('cos', 'Pat', 'Talks to any team.', 'chief_of_staff'),
]

const rosters = [
  {
    id: 'office',
    object: 'team_roster' as const,
    name: 'Office',
    members: [
      { id: 'research', kind: 'team', team_id: 'research', role: 'default', source: 'team:research' },
    ],
    wires: { handoff: true, as_tool: true },
  },
  {
    id: 'research',
    object: 'team_roster' as const,
    name: 'Research',
    members: [{ id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' }],
    wires: { handoff: true, as_tool: true },
  },
]

function mockDataTransfer() {
  const store = new Map<string, string>()
  return {
    setData: (type: string, value: string) => {
      store.set(type, value)
    },
    getData: (type: string) => store.get(type) || '',
    effectAllowed: 'copyMove' as const,
    dropEffect: 'move' as const,
    types: [] as string[],
  }
}

function dragTo(source: Element, target: Element) {
  const dataTransfer = mockDataTransfer()
  // #761: zero-height jsdom rects resolve to 'above' (insert-before), the
  // historical behavior this suite pins.
  fireEvent.dragStart(source, { dataTransfer })
  fireEvent.dragEnter(target, { dataTransfer })
  fireEvent.dragOver(target, { dataTransfer })
  fireEvent.drop(target, { dataTransfer })
  fireEvent.dragEnd(source, { dataTransfer })
}

function mockFetch(extraBlueprints = blueprints, extraRosters = rosters) {
  return vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    const method = String(init?.method || 'GET').toUpperCase()
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
        json: async () => ({ object: 'list', data: extraRosters }),
      } as Response
    }
    if (url.includes('/v1/cli-sessions')) {
      if (method === 'POST' || url.includes('/select')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'cli_session_select',
            agent_id: 'cli_agent',
            cli: 'grok',
            conversation_id: 'cli-fresh-1',
            cli_session_id: null,
            messages: [],
            status: 'Started a new grok session.',
            collapsed_prior: false,
            import: 'none',
          }),
        } as Response
      }
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
    if (url.includes('/v1/cli-agents')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          clis: ['grok', 'agy', 'opencode', 'pi'],
          native_consensus: {},
          catalog: {},
          rail: [
            { id: 'cli_agent', object: 'cli.agent', name: 'cli_agent', cli: 'grok', kind: 'cli', description: 'Host CLI', installed: true },
            { id: 'api_agent', object: 'cli.agent', name: 'api_agent', cli: '', kind: 'api', description: 'LiteLLM', installed: true },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/agents/designs')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          data: [
            {
              agent_id: 'waveshare-opencode',
              name: 'Waveshare OpenCode',
              kind: 'cli',
              cli: 'opencode',
              specialty: 'opencode CLI',
              description: 'Waveshare rover driver',
            },
          ],
        }),
      } as Response
    }
    if (url.includes('api.github.com')) {
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }
    if (url.includes('/sessions')) {
      if (method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_session',
            id: 'sess-new-1',
            conversation_id: 'sess-new-1',
            agent_id: 'codey',
            title: 'New session',
            snippet: '',
            created_at: '2026-09-05T00:00:00Z',
            updated_at: '2026-09-05T00:00:00Z',
            labels: [],
            cli_session_id: null,
            empty: true,
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'agent_session_list',
          agent_id: 'codey',
          sessions: [
            {
              id: 'agt-1-codey',
              conversation_id: 'agt-1-codey',
              agent_id: 'codey',
              title: 'Session 1',
              snippet: 'hello from session one',
              created_at: '2026-09-05T00:00:00Z',
              updated_at: '2026-09-05T00:10:00Z',
              labels: [],
              cli_session_id: null,
              status: 'finished',
            },
            {
              id: 'sess-notes',
              conversation_id: 'sess-notes',
              agent_id: 'codey',
              title: 'Notes',
              snippet: 'later notes',
              created_at: '2026-09-05T00:20:00Z',
              updated_at: '2026-09-05T00:30:00Z',
              labels: [],
              cli_session_id: null,
              status: 'finished',
            },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/herdr-agents')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 1,
              object: 'herdr.agent',
              kind: 'herdr',
              name: 'w3:p1',
              remote: '',
              created_at: '2026-09-03T00:00:00Z',
              updated_at: '2026-09-03T00:00:00Z',
            },
          ],
        }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ object: 'list', data: extraBlueprints }),
    } as Response
  })
}

function SearchProbe() {
  const [params] = useSearchParams()
  return <span data-testid="os-test-search">{params.toString()}</span>
}

/** Hidden Agents opens the Search palette (REQ-190), not an in-rail dialog. */
function HiddenSearchHost() {
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<SearchPaletteOptions | undefined>()
  useEffect(() => {
    const onOpen = (event: Event) => {
      setOptions((event as CustomEvent<SearchPaletteOptions>).detail)
      setOpen(true)
    }
    window.addEventListener(OPEN_SEARCH_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_SEARCH_EVENT, onOpen)
  }, [])
  return (
    <SearchPalette
      open={open}
      options={options}
      onClose={() => {
        setOpen(false)
        setOptions(undefined)
      }}
    />
  )
}

/** Empty `[]` is a user preference (no re-seed). Missing key = first load. */
function rememberEmptyFavourites() {
  localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
}

function renderSidebar(initialEntry = '/chat', onOpenSearch = () => undefined) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={onOpenSearch} />
        <HiddenSearchHost />
        <SearchProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function storedHidden(): string[] {
  return JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')
}

function hiddenBotsButton(count: number) {
  return screen.getByRole('button', { name: `Hidden Agents ${count} (${count} hidden)` })
}

async function unhideFromSearch(label: string, agentId: string) {
  const dialog = await screen.findByRole('dialog', { name: 'Search' })
  const byName = within(dialog).queryByRole('button', {
    name: new RegExp(`^Unhide ${label}$`, 'i'),
  })
  const btn = byName || within(dialog).queryByTestId(`unhide-${agentId}`)
  if (btn) {
    fireEvent.click(btn)
    return
  }
  // Team roster ids stay hidden in localStorage but are not Search bot rows.
  unhideAgentId(agentId, loadHiddenAgentIds())
  window.dispatchEvent(new Event('storage'))
}

function railRow(id: string): Element | null {
  return document.querySelector(`[data-rail-id="${id}"]`)
}

/**
 * `data-rail-id` sits on the row for team/remote rows and on the wrapping
 * `<li>` for section rows, so the active class may be one level down.
 */
function isRowActive(id: string): boolean {
  const node = railRow(id)
  if (!node) return false
  if (node.classList.contains('os-agent-row--active')) return true
  return Boolean(node.querySelector('.os-agent-row--active'))
}

/**
 * #542: pins are where the active state actually broke. `pinActive` compared
 * against `selectedId`, which team/remote scopes blanked out to `''` — so no
 * pin could ever light up once the pane was on a team or a remote.
 */
function pinTile(id: string): Element | null {
  return document.querySelector(`.os-fav-tile[data-agent-id="${id}"]`)
}

function isPinActive(id: string): boolean {
  return Boolean(pinTile(id)?.classList.contains('os-fav-tile--active'))
}

function storedRailOrder(): string[] {
  return JSON.parse(localStorage.getItem(RAIL_ORDER_STORAGE_KEY) || '[]')
}

function railIds(list: HTMLElement): string[] {
  return [...list.querySelectorAll('[data-rail-id]')].map(
    (node) => node.getAttribute('data-rail-id') || '',
  )
}

describe('AgentSidebar Grok rail', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lists Support first and does not filter the catalog from the rail Search field', async () => {
    const onOpenSearch = vi.fn()
    renderSidebar('/chat', onOpenSearch)

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    const links = within(list).getAllByRole('link')
    expect(links[0]).toBe(support)
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Stewie/ })).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Gate/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Skeptic/ })).not.toBeInTheDocument()

    const search = screen.getByRole('button', { name: 'Search' })
    expect(search).toHaveClass('os-rail-search')
    expect(search).toHaveTextContent('Search')
    const kbd = search.querySelector('.os-rail-search__kbd')
    expect(kbd?.textContent === '⌘K' || kbd?.textContent === 'Ctrl+K').toBe(true)
    fireEvent.focus(search)
    fireEvent.click(search)
    expect(onOpenSearch).toHaveBeenCalled()
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Stewie/ })).toBeInTheDocument()
  })

  it('designed router agents appear in the rail and link to standard chat', async () => {
    renderSidebar('/chat')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Waveshare OpenCode/ })
    expect(row).toHaveAttribute('href', '/chat?blueprint=waveshare-opencode')
    expect(row).not.toHaveAttribute('href', expect.stringContaining('/agents?agent='))
  })

  it('prevents regression of "Focused / 96 hidden agents": clicking designed agent does not route to /agents or hide agents', async () => {
    renderSidebar('/chat')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Waveshare OpenCode/ })
    // Must stay on standard chat href
    expect(row).toHaveAttribute('href', '/chat?blueprint=waveshare-opencode')
    expect(row.getAttribute('href')).not.toMatch(/^\/agents\?/)
  })

  it('REQ-170: catalog recipes without rail stay off the AGENTS rail', async () => {
    const catalogOnly = [
      blueprint('support', 'Support', 'Onboarding', 'support'),
      {
        ...blueprint('poets', 'Poets', 'Poet swarm'),
        rail: false,
      },
      {
        ...blueprint('chucks_angels', "Chuck's Angels", 'Demo'),
        rail: false,
      },
      {
        ...blueprint('django_chat', 'Django Chat', 'Retired webui leftover'),
        rail: false,
      },
      {
        ...blueprint('moa', 'mixture_of_agents', 'MoA'),
        rail: false,
      },
      {
        ...blueprint('cli_fusion', 'cli_fusion', 'CLI fusion'),
        rail: false,
      },
      {
        ...blueprint('codey', 'Codey', 'Code assistant'),
        rail: false,
      },
    ]
    vi.stubGlobal('fetch', mockFetch(catalogOnly))
    renderSidebar('/chat')

    const rail = await screen.findByTestId('os-agent-rail')
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    expect(await within(list).findByRole('link', { name: /Support/ })).toBeInTheDocument()
    expect(await within(list).findByRole('link', { name: /cli_agent/ })).toBeInTheDocument()
    for (const name of ['Poets', "Chuck's Angels", 'Django Chat', 'mixture_of_agents', 'cli_fusion', 'Codey']) {
      expect(within(rail).queryByRole('link', { name: new RegExp(name, 'i') })).not.toBeInTheDocument()
    }
  })

  it('REQ-170: a leftover pin of a catalog-only id does not re-enter the list', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'poets', name: 'Poets' }]),
    )
    const catalogOnly = [
      blueprint('support', 'Support', 'Onboarding', 'support'),
      { ...blueprint('poets', 'Poets', 'Poet swarm'), rail: false },
    ]
    vi.stubGlobal('fetch', mockFetch(catalogOnly))
    renderSidebar('/chat')

    const rail = await screen.findByTestId('os-agent-rail')
    expect(await within(rail).findByRole('link', { name: /Support/ })).toBeInTheDocument()
    await waitFor(() => {
      expect(within(rail).queryByRole('link', { name: /Poets/i })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: 'Poets' })).not.toBeInTheDocument()
  })

  it('paints the same custom face on the Codey rail tile as the header would', async () => {
    renderSidebar('/chat?blueprint=codey')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const face = codey.querySelector('[data-agent-avatar]')
    expect(face).toHaveAttribute('data-agent-avatar', 'custom')
    expect(codey.querySelector('img')).toHaveAttribute('src', '/avatars/codey_avatar.png')
    const support = within(list).getByRole('link', { name: /Support/ })
    expect(support.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'default',
    )
  })

  it('lists cli_agent then api_agent after Support', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /cli_agent/ })
    expect(within(list).getByRole('link', { name: /cli_agent/ })).toHaveAttribute(
      'href',
      '/chat?blueprint=cli_agent',
    )
    expect(within(list).getByRole('link', { name: /api_agent/ })).toHaveAttribute(
      'href',
      '/chat?blueprint=api_agent',
    )
    const ids = railIds(list)
    expect(ids.indexOf('support')).toBeLessThan(ids.indexOf('cli_agent'))
    expect(ids.indexOf('cli_agent')).toBeLessThan(ids.indexOf('api_agent'))
  })

  it('offers Select session on a CLI rail row and on Codey (Django)', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /cli_agent/ }))
    expect(await screen.findByRole('menuitem', { name: 'Select session' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /^New session$/i })).toBeInTheDocument()

    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Codey/ }))
    expect(screen.getByRole('menuitem', { name: 'Select session' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /^New session$/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Hide from sidebar/i })).toBeInTheDocument()
  })

  it('opens the CLI session picker overlay from Select session without unmounting chat', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /cli_agent/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Select session' }))
    const picker = await screen.findByTestId('os-cli-session-picker')
    expect(picker).toBeInTheDocument()
    expect(within(picker).getByTestId('cli-session-empty')).toHaveTextContent(
      "This CLI can't list sessions",
    )
    expect(within(picker).getByTestId('cli-session-start-new')).toBeInTheDocument()
    expect(list).toBeInTheDocument()
  })

  it('CLI New session posts start_new so the next send uses a fresh id', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /cli_agent/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /^New session$/i }))
    await waitFor(() => {
      expect(screen.getByTestId('os-test-search')).toHaveTextContent('session=cli-fresh-1')
    })
    const posted = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(
      (call: unknown[]) => {
        const [input, init] = call as [RequestInfo, RequestInit | undefined]
        const url = String(input)
        const body = typeof init?.body === 'string' ? init.body : ''
        return url.includes('/v1/cli-sessions/select') && body.includes('"start_new":true')
      },
    )
    expect(posted).toBe(true)
  })

  // #507: the old force-visible exemption (#321/#621) is gone — Hide and
  // Unhide are inverses for every rail kind, and the Hidden count is truthful.
  it('hides cli_agent and api_agent when their ids are in the hidden store', async () => {
    localStorage.setItem(
      HIDDEN_AGENTS_STORAGE_KEY,
      JSON.stringify(['cli_agent', 'api_agent', 'codey']),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Support/ })
    expect(within(list).queryByRole('link', { name: /cli_agent/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /api_agent/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(hiddenBotsButton(3)).toBeInTheDocument()
  })

  it('seeds Hidden with gate and skeptic on first load; Support stays visible', async () => {
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    expect(within(list).getAllByRole('link')[0]).toBe(support)
    expect(support.className).not.toMatch(/os-agent-row--support/)
    expect(support.className).not.toMatch(/os-agent-role-/)
    expect(support.querySelector('.os-agent-role-badge')).toHaveTextContent('Support')
    expect(within(list).queryByRole('link', { name: /Gate/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Skeptic/ })).not.toBeInTheDocument()

    await waitFor(() => {
      expect(storedHidden()).toEqual(['gate', 'skeptic'])
    })
    fireEvent.click(hiddenBotsButton(2))
    const dialog = await screen.findByRole('dialog', { name: 'Search' })
    expect(await within(dialog).findByText('Gate')).toBeInTheDocument()
    expect(within(dialog).getByText('Skeptic')).toBeInTheDocument()
    await unhideFromSearch('Gate', 'gate')
    await waitFor(() => {
      expect(storedHidden()).toEqual(['skeptic'])
    })
    expect(within(list).getByRole('link', { name: /Gate/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Support/ })).toBeInTheDocument()
  })

  it('does not re-seed when the user already customized hidden agents', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['codey']))
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    })
    expect(within(list).getByRole('link', { name: /Support/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Gate/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Skeptic/ })).toBeInTheDocument()
    expect(storedHidden()).toEqual(['codey'])
  })

  it('hides from the list via context menu and unhides from the end-of-list popup', async () => {
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })

    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /Hide from sidebar/i }))

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    })
    expect(within(list).getByRole('link', { name: /Stewie/ })).toBeInTheDocument()
    expect(storedHidden()).toEqual(['gate', 'skeptic', 'codey'])
    expect(screen.queryByRole('menuitem', { name: /Hide all/i })).not.toBeInTheDocument()

    fireEvent.click(hiddenBotsButton(3))
    await unhideFromSearch('Codey', 'codey')
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic'])
    expect(hiddenBotsButton(2)).toBeInTheDocument()
  })

  it('opens the agent-scoped editor from the context menu', async () => {
    const opened: Array<{ agentId?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent).detail || {})
    }
    window.addEventListener('swarm:open-agent-editor', onOpen)
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Edit Profile$/i }))
    expect(opened).toEqual([{ agentId: 'codey', agentName: 'Codey' }])
    window.removeEventListener('swarm:open-agent-editor', onOpen)
  })

  it('REQ-98: context menu lists Notifications Off by default', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    fireEvent.contextMenu(codey)
    expect(await screen.findByRole('menuitem', { name: /Notifications: Off/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Notifications: On/i })).not.toBeInTheDocument()
  })

  it('pins from the context menu onto the unlabeled favourite grid', async () => {
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))

    const grid = screen.getByLabelText('Pinned agents')
    const tile = within(grid).getByRole('link', { name: 'Codey' })
    expect(tile).toBeInTheDocument()
    expect(tile.querySelector('.os-agent-avatar--lg')).toBeTruthy()
    expect(tile.querySelector('.os-fav-tile__name')).toHaveTextContent('Codey')
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])
  })

  it('offers Select session and New session on an API agent, not on a team row', async () => {
    renderSidebar('/chat?blueprint=codey')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    fireEvent.contextMenu(codey)
    expect(await screen.findByRole('menuitem', { name: /Select session/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /^New session$/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /Select session/i }))
    const dialog = await screen.findByRole('dialog', { name: 'Codey sessions' })
    expect(within(dialog).getByRole('option', { name: /Notes/ })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /^New session$/i })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('option', { name: /Notes/ }))
    expect(screen.getByTestId('os-test-search')).toHaveTextContent('session=sess-notes')
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Codey/ })).toHaveAttribute(
        'href',
        expect.stringContaining('session=sess-notes'),
      )
    })

    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Office \(team\)/ }))
    expect(screen.queryByRole('menuitem', { name: /Select session/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /^New session$/i })).not.toBeInTheDocument()
  })

  it('creates an empty Django session from New session and keeps chat mounted', async () => {
    renderSidebar('/chat?blueprint=codey')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Codey/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /^New session$/i }))
    await waitFor(() => {
      expect(screen.getByTestId('os-test-search')).toHaveTextContent('session=sess-new-1')
    })
  })

  it('#182: rail footer shows Teams directly above Plugins', async () => {
    renderSidebar('/chat')

    await screen.findByRole('navigation', { name: 'Agent list' })
    const teams = screen.getByTestId('os-teams-button')
    const plugins = screen.getByTestId('os-plugins-button')
    expect(teams).toHaveAttribute('aria-label', 'Teams')
    expect(plugins).toHaveAttribute('aria-label', 'Plugins')
    // DOM order: Teams precedes Plugins within the footer stack.
    expect(teams.compareDocumentPosition(plugins) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('exposes Plugins and an editable hostname after the conversation list', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    expect(screen.getByRole('button', { name: /Plugins/i })).toBeInTheDocument()
    const hostname = screen.getByLabelText('Hostname')
    fireEvent.change(hostname, { target: { value: 'lab-box' } })
    fireEvent.blur(hostname)
    expect(localStorage.getItem(HOSTNAME_STORAGE_KEY)).toBe('lab-box')
    expect(localStorage.getItem(HOSTNAME_OVERRIDE_KEY)).toBe('lab-box')
  })

  it('syncs hostname live without reload when HOSTNAME_CHANGED_EVENT is dispatched (REQ-188B-2)', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const input = screen.getByLabelText('Hostname') as HTMLInputElement
    expect(input.value).toBe('localhost')

    act(() => {
      dispatchHostnameChanged('remote.box.net')
    })
    expect(input.value).toBe('remote.box.net')
  })

  it('renders a server icon left of hostname and clicking it opens remote sessions popup (REQ-118)', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const serverBtn = screen.getByTestId('rail-server-icon')
    expect(serverBtn).toBeInTheDocument()
    expect(serverBtn).toHaveAttribute('aria-label', 'Remote sessions')

    expect(screen.queryByTestId('remote-sessions-popup')).toBeNull()
    fireEvent.click(serverBtn)
    expect(screen.getByTestId('remote-sessions-popup')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('remote-sessions-popup')).toBeNull()
  })

  it('places XOR update/info chrome immediately right of the system name (REQ-78)', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const server = screen.getByTestId('rail-server-icon')
    const hostname = screen.getByLabelText('Hostname')
    const chrome = screen.getByTestId('rail-update-chrome')
    const row = hostname.closest('.os-rail-hostname-row')
    expect(row).toBeTruthy()
    expect(row?.contains(server)).toBe(true)
    expect(row?.contains(chrome)).toBe(true)
    expect(server.compareDocumentPosition(hostname) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(hostname.compareDocumentPosition(chrome) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(chrome).toHaveAttribute('data-kind', 'idle')
    expect(chrome.querySelectorAll('svg')).toHaveLength(1)
    expect(screen.queryAllByTestId('rail-update-chrome')).toHaveLength(1)
  })

  it('#400 rail hostname is never a loopback IP', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const hostname = screen.getByLabelText('Hostname') as HTMLInputElement
    expect(hostname.value).not.toBe('127.0.0.1')
    expect(hostname.value).not.toBe('::1')
  })

  it('#401 rail names keep a title with the full label', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    const nameEl = within(support).getByTestId('rail-agent-name')
    expect(nameEl).toHaveTextContent('Support')
    expect(nameEl).toHaveAttribute('title', 'Support')
  })

  it('#404 agent list scroller has footer clearance padding (idle: pb-4; #729 expands to pb-16 mid-drag)', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    // #729 supersedes the constant pb-16: the 4rem drag-era clearance is
    // reserved only while a drag is in progress; idle rows reclaim the height.
    expect(screen.getByTestId('rail-agent-scroller').className).toMatch(/pb-4/)
    expect(screen.getByTestId('rail-agent-scroller').className).not.toMatch(/pb-16/)
  })

  it('paints a red dot on rail-server-icon when local WS is disconnected (REQ-195)', async () => {
    resetChatConnection()
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const serverBtn = screen.getByTestId('rail-server-icon')
    expect(serverBtn).toBeInTheDocument()
    expect(screen.queryByTestId('local-server-status-dot')).not.toBeInTheDocument()

    act(() => {
      publishChatConnection('closed')
    })
    expect(screen.getByTestId('local-server-status-dot')).toBeInTheDocument()

    act(() => {
      publishChatConnection('open')
    })
    expect(screen.queryByTestId('local-server-status-dot')).not.toBeInTheDocument()
    resetChatConnection()
  })

  it('leaves the Hidden Agents area blank until something is hidden', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const zone = screen.getByRole('region', { name: 'Hidden Agents' })
    expect(zone).toHaveAttribute('data-empty', 'true')
    expect(zone).not.toHaveTextContent(/drop here to hide/i)
    expect(zone).toHaveTextContent('')
    expect(screen.queryByRole('button', { name: /Hidden Agents/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Hide all/i })).not.toBeInTheDocument()
  })

  it('reveals a light empty drop target on drag-over and hides on drop', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const zone = screen.getByRole('region', { name: 'Hidden Agents' })
    expect(zone).toHaveAttribute('data-empty', 'true')
    expect(screen.queryByText(/drop here to hide/i)).not.toBeInTheDocument()

    fireEvent.dragStart(codey, { dataTransfer: mockDataTransfer() })
    fireEvent.dragOver(zone, { dataTransfer: mockDataTransfer() })
    expect(zone).toHaveAttribute('data-drag-over', 'true')
    expect(zone).toHaveClass('os-hidden-bots--active')
    expect(screen.queryByText(/drop here to hide/i)).not.toBeInTheDocument()

    dragTo(codey, zone)

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['codey'])
    expect(hiddenBotsButton(1)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Hidden Agents' })).toHaveAttribute('data-empty', 'false')
  })

  it('shows Hidden Agents count and swaps to a chevron on hover', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const trigger = await screen.findByTestId('os-hidden-bots-button')
    expect(trigger).toHaveAccessibleName(/Hidden Agents 2/)
    expect(within(trigger).getByText('Hidden Agents')).toBeInTheDocument()
    expect(within(trigger).getByTestId('os-hidden-bots-count')).toHaveTextContent('2')
    fireEvent.mouseEnter(trigger)
    // #557: the hover affordance is now the lucide chevron rather than a literal
    // '>' character, so assert the icon (and that the count yields to it) instead
    // of coupling the test to a text glyph.
    const tail = within(trigger).getByTestId('os-hidden-bots-tail')
    expect(tail.querySelector('svg.lucide-chevron-right')).toBeTruthy()
    expect(tail).not.toHaveTextContent('>')
    fireEvent.mouseLeave(trigger)
    expect(within(trigger).getByTestId('os-hidden-bots-count')).toHaveTextContent('2')
  })

  it('drags a support agent onto Hidden and persists the id', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    const zone = screen.getByRole('region', { name: 'Hidden Agents' })

    fireEvent.dragStart(support, { dataTransfer: mockDataTransfer() })
    expect(support).toHaveClass('os-agent-row--dragging')
    fireEvent.dragOver(zone, { dataTransfer: mockDataTransfer() })
    expect(zone).toHaveAttribute('data-drag-over', 'true')

    dragTo(support, zone)

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Support/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic', 'support'])
    expect(hiddenBotsButton(3)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Hide all/i })).not.toBeInTheDocument()
  })

  it('drags a default agent onto Hidden; Unhide restores; no Hide-all', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const zone = screen.getByRole('region', { name: 'Hidden Agents' })

    dragTo(codey, zone)

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic', 'codey'])
    expect(screen.queryByRole('button', { name: /Hide all/i })).not.toBeInTheDocument()

    fireEvent.click(hiddenBotsButton(3))
    await unhideFromSearch('Codey', 'codey')
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic'])
    expect(hiddenBotsButton(2)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Hide all/i })).not.toBeInTheDocument()
  })

  it('hides role agents (gate, skeptic) via the empty Hidden Agents drop slot', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const zone = screen.getByRole('region', { name: 'Hidden Agents' })

    dragTo(await within(list).findByRole('link', { name: /Gate/ }), zone)
    dragTo(await within(list).findByRole('link', { name: /Skeptic/ }), zone)

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Gate/ })).not.toBeInTheDocument()
      expect(within(list).queryByRole('link', { name: /Skeptic/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic'])
    expect(hiddenBotsButton(2)).toBeInTheDocument()
  })

  it('no-ops when a row is dropped onto itself', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    dragTo(codey, codey)
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(storedHidden()).toEqual(['gate', 'skeptic'])
  })

  it('hides a pinned favourite from the grid but keeps the pin for Unhide', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    const grid = screen.getByLabelText('Pinned agents')
    const tile = within(grid).getByRole('link', { name: 'Codey' })
    expect(tile).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()

    dragTo(tile, screen.getByRole('region', { name: 'Hidden Agents' }))

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    })
    expect(within(grid).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])
    expect(storedHidden()).toEqual(['gate', 'skeptic', 'codey'])
  })

  it('restores a favourite pin after hide then unhide, including after remount', async () => {
    const first = renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Codey/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    const grid = screen.getByLabelText('Pinned agents')
    expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()

    fireEvent.contextMenu(within(grid).getByRole('link', { name: 'Codey' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Hide from sidebar/i }))
    await waitFor(() => {
      expect(within(grid).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
    })
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])

    first.unmount()
    renderSidebar()
    const listAfter = await screen.findByRole('navigation', { name: 'Agent list' })
    const gridAfter = screen.getByLabelText('Pinned agents')
    const unhideTrigger = await screen.findByRole('button', {
      name: 'Hidden Agents 3 (3 hidden)',
    })
    expect(within(gridAfter).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
    expect(within(listAfter).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()

    fireEvent.click(unhideTrigger)
    await unhideFromSearch('Codey', 'codey')
    await waitFor(() => {
      expect(within(gridAfter).getByRole('link', { name: 'Codey' })).toBeInTheDocument()
    })
    expect(within(listAfter).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])
  })

  it('does not pin on unhide when the agent was never favourited', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(await within(list).findByRole('link', { name: /Codey/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Hide from sidebar/i }))
    fireEvent.click(hiddenBotsButton(3))
    await unhideFromSearch('Codey', 'codey')
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    })
    expect(within(screen.getByLabelText('Pinned agents')).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
  })

  it('lists persisted Herdr members (kind=herdr) so Teams/sidepane can pick them', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const herdr = await within(list).findByRole('link', { name: /w3:p1/ })
    // #543: the herdr row LINKS TO ITS CHAT — the agent name rides the
    // remote-harness session param — instead of the settings-adjacent members
    // page. A herdr seat is a talk-to target like every other kind.
    expect(herdr).toHaveAttribute('href', '/chat?remote=herdr&session=w3%3Ap1')
    expect(herdr).toHaveTextContent(/Herdr · localhost/)
  })

  it('keeps the rail role badge as non-interactive text inside the row link (#332)', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    const opened: Array<Record<string, unknown>> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent).detail || {})
    }
    window.addEventListener('swarm:open-settings', onOpen)
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const gate = await within(list).findByRole('link', { name: /Gate/ })
    const badge = gate.querySelector('.os-agent-role-badge')
    expect(badge).not.toBeNull()
    expect(badge).toHaveAttribute('data-definition-id', 'gate')
    expect(badge).not.toHaveAttribute('role', 'button')
    expect(badge).not.toHaveAttribute('tabindex')
    expect(within(list).queryByRole('button', { name: 'Open gate settings' })).not.toBeInTheDocument()
    fireEvent.click(badge!)
    expect(opened).toEqual([])
    window.removeEventListener('swarm:open-settings', onOpen)
  })

  it('has no hover-edit pencil on role rows; Edit Profile on the context menu opens the agent editor', async () => {
    // REQ-26 first-load seed hides gate/skeptic; show all roles for this check.
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    const opened: Array<{ agentId?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent).detail || {})
    }
    window.addEventListener('swarm:open-agent-editor', onOpen)
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    expect(screen.queryByRole('button', { name: 'Edit Support' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit Gate' })).not.toBeInTheDocument()
    expect(document.querySelector('.os-agent-edit')).not.toBeInTheDocument()
    expect(within(list).queryByRole('menuitem', { name: /Hide all/i })).not.toBeInTheDocument()

    fireEvent.contextMenu(support)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Edit Profile$/i }))
    expect(opened).toEqual([{ agentId: 'support', agentName: 'Support' }])
    window.removeEventListener('swarm:open-agent-editor', onOpen)
  })

  it('persists a native drag reorder and leaves favourite tiles alone', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const stewie = await within(list).findByRole('link', { name: /Stewie/ })
    const support = await within(list).findByRole('link', { name: /Support/ })
    const codey = within(list).getByRole('link', { name: /Codey/ })

    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    const grid = screen.getByLabelText('Pinned agents')
    expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()

    expect(railIds(list)[0]).toBe('support')
    dragTo(stewie, support)

    await waitFor(() => {
      expect(railIds(list)[0]).toBe('stewie')
    })
    expect(storedRailOrder()[0]).toBe('stewie')
    expect(within(list).getByRole('link', { name: /Support/ })).toBeInTheDocument()
    expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])
    expect(within(grid).getAllByRole('link').map((link) => link.getAttribute('aria-label'))).toEqual([
      'Codey',
    ])
  })

  it('reloads a persisted rail order without scrambling favourite tiles', async () => {
    localStorage.setItem(RAIL_ORDER_STORAGE_KEY, JSON.stringify(['stewie', 'support', 'codey']))
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'codey', name: 'Codey' }]),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() => {
      expect(railIds(list)[0]).toBe('stewie')
    })
    const grid = screen.getByLabelText('Pinned agents')
    expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()
    expect(within(grid).getAllByRole('link')).toHaveLength(1)
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
  })

  it('moves a just-completed fixture to index 0 when bump is on', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Stewie/ })
    expect(railIds(list)[0]).toBe('support')

    fireEvent(window, new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'stewie' } }))

    await waitFor(() => {
      expect(railIds(list)[0]).toBe('stewie')
    })
    expect(storedRailOrder()[0]).toBe('stewie')
  })

  it('#552: a sectioned agent is NOT bumped by default — Only Unassigned', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_stuff', name: 'stuff', collapsed: false }],
        membership: { stewie: 'sec_stuff' },
        unassignedCollapsed: false,
      }),
    )
    localStorage.setItem(BUMP_COMPLETED_KEY, '1')
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Stewie/ })

    const before = railIds(list)
    fireEvent(window, new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'stewie' } }))

    // Its own position and its section-mates' positions are unchanged.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(railIds(list)).toEqual(before)
    expect(storedRailOrder()).toEqual([])
  })

  it('#552: All sections restores the old behaviour for sectioned agents', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_stuff', name: 'stuff', collapsed: false }],
        membership: { stewie: 'sec_stuff' },
        unassignedCollapsed: false,
      }),
    )
    localStorage.setItem(BUMP_COMPLETED_KEY, '1')
    localStorage.setItem(BUMP_SCOPE_KEY, 'all')
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Stewie/ })

    fireEvent(window, new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'stewie' } }))

    await waitFor(() => {
      expect(storedRailOrder()[0]).toBe('stewie')
    })
  })

  it('#552: the scope is still subordinate to the master toggle', async () => {
    localStorage.setItem(BUMP_COMPLETED_KEY, '0')
    localStorage.setItem(BUMP_SCOPE_KEY, 'all')
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Stewie/ })

    fireEvent(window, new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'stewie' } }))

    expect(railIds(list)[0]).toBe('support')
    expect(storedRailOrder()).toEqual([])
  })

  it('does not bump a completed fixture when the toggle is off', async () => {
    localStorage.setItem(BUMP_COMPLETED_KEY, '0')
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Stewie/ })
    expect(railIds(list)[0]).toBe('support')

    fireEvent(window, new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'stewie' } }))

    expect(railIds(list)[0]).toBe('support')
    expect(storedRailOrder()).toEqual([])
  })

  it('#564: a pinned agent dropped inside a section is unpinned AND assigned to it', async () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_stuff', name: 'stuff', collapsed: false }],
        membership: {}, // empty: this is exactly the gap that swallowed the drop
        unassignedCollapsed: false,
      }),
    )
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'stewie', name: 'Stewie' }]),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    // Wait for the rows before looking for sections — the rail paints its
    // loading state first.
    await within(list).findByRole('link', { name: /Codey/ })

    const tile = within(screen.getByLabelText('Pinned agents')).getByRole('link', {
      name: 'Stewie',
    })
    const section = screen
      .getAllByTestId('rail-section')
      .find((node) => node.getAttribute('data-section-id') === 'sec_stuff')!

    // Drop on the section BLOCK, not its header and not its empty hint — the
    // padding is where a real drag lands and where the container's
    // dropUnfavourite used to take over (unpin only, never assign).
    dragTo(tile, section)

    const stored = JSON.parse(localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY) || '{}')
    expect(stored.membership.stewie).toBe('sec_stuff')
    // And it really did leave the pinned grid.
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([])
    expect(
      within(screen.getAllByTestId('rail-section').find(
        (node) => node.getAttribute('data-section-id') === 'sec_stuff',
      )!).getByRole('link', { name: /Stewie/ }),
    ).toBeInTheDocument()
  })

  it('REQ-128: does not duplicate favourite agents into the list when generation finishes', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'codey', name: 'Codey' }]),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const grid = screen.getByLabelText('Pinned agents')
    expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()

    // Fire generation complete for the pinned favourite agent
    fireEvent(window, new CustomEvent(GENERATION_COMPLETE_EVENT, { detail: { agentId: 'codey' } }))

    // Favourites stay unchanged in the pin grid, not duplicated into the list
    expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(storedRailOrder()).not.toContain('codey')
  })

  it('REQ-164 / REQ-109: displays + button beside Search input (not in favourites grid) and opens Add agent wizard', async () => {
    renderSidebar()
    const addBtn = await screen.findByRole('button', { name: 'Add agent' })
    expect(addBtn).toBeInTheDocument()
    expect(addBtn).toHaveAttribute('data-testid', 'add-agent-button')
    expect(addBtn.closest('.os-rail-search-row')).toBeInTheDocument()

    // Favourites row/grid must not contain the add button
    const favGrid = screen.getByTestId('agent-fav-grid')
    expect(within(favGrid).queryByTestId('add-agent-button')).toBeNull()

    // Click + button to open wizard
    fireEvent.click(addBtn)

    expect(await screen.findByTestId('add-agent-wizard')).toBeInTheDocument()
    expect(screen.getByText('Add Agent')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-cli')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-api')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-remote')).toBeInTheDocument()
  })

  it('keeps a scale-out agent as one stacked row and opens a session picker', async () => {
    const running: AgentSession[] = [1, 2, 3, 4].map((n) => ({
      id: `run-${n}`,
      agentId: 'codey',
      title: `Task ${n}`,
      snippet: `work ${n}`,
      status: 'running',
      startedAt: n * 200,
      updatedAt: n * 200,
    }))
    saveAgentSessions('codey', [
      ...running,
      {
        id: 'fin-1',
        agentId: 'codey',
        title: 'Old job',
        snippet: 'finished fixture',
        status: 'finished',
        startedAt: 50,
        updatedAt: 50,
      },
    ])
    renderSidebar('/chat?blueprint=codey')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('button', { name: /Codey, 5 sessions/i })
    const rows = list.querySelectorAll('[data-agent-id="codey"]')
    expect(rows).toHaveLength(1)
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(codey).toHaveAttribute('data-scale-out', 'true')

    const faces = within(codey).getAllByTestId('os-stacked-avatar')
    expect(faces).toHaveLength(3)
    expect(within(codey).getByTestId('os-stacked-remainder')).toHaveTextContent('+1')
    const delays = faces.map((face) => face.style.animationDelay)
    expect(new Set(delays).size).toBe(3)
    for (const face of faces) {
      expect(face).toHaveClass('os-stacked-avatar--pulse')
    }

    fireEvent.click(codey)
    const dialog = await screen.findByRole('dialog', { name: 'Codey sessions' })
    const options = within(dialog).getAllByRole('option')
    expect(options).toHaveLength(5)
    expect(within(dialog).getByText('finished fixture', { exact: false })).toBeInTheDocument()

    fireEvent.change(screen.getByRole('combobox', { name: /Filter Codey sessions/i }), {
      target: { value: 'Task 2' },
    })
    expect(within(dialog).getAllByRole('option')).toHaveLength(1)
    fireEvent.click(within(dialog).getByRole('option', { name: /Task 2/i }))
    expect(screen.queryByRole('dialog', { name: 'Codey sessions' })).not.toBeInTheDocument()
    expect(screen.getByTestId('os-test-search').textContent).toContain('session=run-2')
    expect(screen.getByTestId('os-test-search').textContent).toContain('blueprint=codey')
  })

  it('shows a distinct CoS badge and nested team rows with a Team badge', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const cos = await within(list).findByRole('link', { name: /Pat/ })
    expect(cos).not.toHaveClass('os-agent-role-chief_of_staff')
    expect(cos).not.toHaveClass('os-agent-row--cos')
    expect(cos.className).not.toMatch(/os-agent-role-/)
    const cosBadge = within(cos).getByText('CoS')
    expect(cosBadge).toHaveAttribute('data-role', 'chief_of_staff')
    expect(cosBadge).toHaveClass('os-agent-role-badge')
    expect(cosBadge).toHaveClass('os-agent-role-chief_of_staff')

    const office = within(list).getByRole('link', { name: /Office/ })
    expect(office).toHaveAttribute('data-kind', 'team')
    // #525: team membership is not a role, so a team row carries no badge.
    expect(within(office).queryByText('Team')).not.toBeInTheDocument()

    const research = within(list).getByRole('link', { name: /Research/ })
    expect(research).toHaveAttribute('data-kind', 'team')
    expect(research.closest('ul')).toHaveClass('os-agent-team-nest')
  })

  it('REQ-67: role chrome is the badge only — no row fill/border', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    renderSidebar('/chat?blueprint=codey')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    const gate = within(list).getByRole('link', { name: /Gate/ })
    const skeptic = within(list).getByRole('link', { name: /Skeptic/ })
    const cos = within(list).getByRole('link', { name: /Pat/ })
    const codey = within(list).getByRole('link', { name: /Codey/ })

    for (const row of [support, gate, skeptic, cos, codey]) {
      expect(row).toHaveClass('os-agent-row')
      expect(row.className).not.toMatch(/os-agent-row--(support|gate|skeptic|cos|chief_of_staff)/)
      expect(row.className).not.toMatch(/os-agent-role-/)
      const dot = row.querySelector('.os-agent-dot')
      if (dot) expect(dot).not.toHaveAttribute('data-role')
    }

    expect(support.querySelector('.os-agent-role-badge')).toHaveAttribute('data-role', 'support')
    expect(gate.querySelector('.os-agent-role-badge')).toHaveAttribute('data-role', 'gate')
    expect(skeptic.querySelector('.os-agent-role-badge')).toHaveAttribute('data-role', 'skeptic')
    expect(cos.querySelector('.os-agent-role-badge')).toHaveAttribute('data-role', 'chief_of_staff')
    expect(codey.querySelector('.os-agent-role-badge')).toBeNull()

    expect(codey).toHaveClass('os-agent-row--active')
    expect(support).not.toHaveClass('os-agent-row--active')
    expect(support.closest('.os-agent-row-wrap')?.className).not.toMatch(/os-agent-role-/)
  })

  it('nested team row keeps ?team= and does not clobber with ?blueprint= (REQ-28 / #345)', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const research = await within(list).findByRole('link', { name: /Research \(team\)/ })
    expect(research).toHaveAttribute('href', '/chat?team=research')
    expect(research.getAttribute('href')).not.toMatch(/blueprint=/)
    const office = within(list).getByRole('link', { name: /Office \(team\)/ })
    expect(office).toHaveAttribute('href', '/chat?team=office')
  })

  it('Plugins overlay is a search palette over the rail (#805)', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.click(screen.getByRole('button', { name: /Plugins/i }))
    const dialog = screen.getByRole('dialog', { name: 'Plugins' })
    expect(dialog).toHaveClass('os-search-palette')
    expect(within(dialog).getByRole('combobox', { name: 'Filter tools' })).toBeInTheDocument()
    expect(await within(dialog).findByRole('switch', { name: /Web Search Off/i })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close plugins' }))
    expect(screen.queryByRole('dialog', { name: 'Plugins' })).not.toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
  })
})

describe('AgentSidebar special roles', () => {
  const roster = [
    {
      id: 'codey',
      object: 'blueprint' as const,
      name: 'Codey',
      description: 'Code',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: null,
      rail: true,
    },
    {
      id: 'skeptic',
      object: 'blueprint' as const,
      name: 'Skeptic',
      description: 'Retry stub',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'skeptic',
      rail: true,
    },
    {
      id: 'gate',
      object: 'blueprint' as const,
      name: 'Gate',
      description: 'Approve stub',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'gate',
      rail: true,
    },
    {
      id: 'support',
      object: 'blueprint' as const,
      name: 'Support',
      description: 'Onboarding. First team.',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'support',
      rail: true,
    },
  ]

  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: roster }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lists Support first with a role=support look, not a diamond', async () => {
    renderSidebar('/chat?blueprint=support')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() => {
      expect(within(list).getAllByRole('link').length).toBeGreaterThan(0)
    })
    const links = within(list).getAllByRole('link')
    expect(links[0]).toHaveTextContent('Support')
    expect(links[0].querySelector('[data-role="support"]')).not.toBeNull()
  })
})

describe('AgentSidebar teams', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'demo-team',
                  object: 'team_roster',
                  name: 'Demo Team',
                  description: 'Example multi-agent roster',
                  members: [
                    { id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' },
                  ],
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
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
    localStorage.clear()
  })

  it('mixes a visually distinct team row with agent rows', async () => {
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Demo Team \(team\)/ })
    expect(team).toHaveAttribute('href', '/chat?team=demo-team')
    expect(team.className).toMatch(/os-team-item/)
    // #525: the 'Team' role-styled pill is gone from sidepane rows.
    expect(within(team).queryByText('Team')).not.toBeInTheDocument()
    expect(within(team).queryByText('Remote')).not.toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Stewie/ })).toBeInTheDocument()
  })

  it('lists Demo Harness Kinds with Mode A names on the rail team row', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'demo-harness-kinds',
                  object: 'team_roster',
                  name: 'Demo Harness Kinds',
                  members: [
                    { id: 'grok-cli', name: 'Grok CLI', kind: 'cli', role: 'default' },
                    { id: 'litellm-api', name: 'LiteLLM API', kind: 'api', role: 'default' },
                  ],
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents')) {
          return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: blueprints }),
        } as Response
      }),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Demo Harness Kinds \(team\)/ })
    expect(team).toHaveAttribute('href', '/chat?team=demo-harness-kinds')
    expect(within(team).queryByText('Team')).not.toBeInTheDocument()
  })

  it('shows one declared persona face plus a remainder on a team row (REQ-81, #438)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'squad',
                  object: 'team_roster',
                  name: 'Squad',
                  blueprint_id: 'software_dev',
                  persona_count: 3,
                  personas: [
                    { name: 'Researcher' },
                    { name: 'Writer' },
                    { name: 'Reviewer' },
                  ],
                  members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              ...blueprints,
              {
                id: 'software_dev',
                object: 'blueprint',
                name: 'Software-dev team',
                description: 'CoS / engineer / skeptic',
                abbreviation: null,
                required_mcp_servers: [],
                tags: [],
                installed: true,
                compiled: true,
                persona_count: 3,
                personas: [
                  { name: 'Researcher' },
                  { name: 'Writer' },
                  { name: 'Reviewer' },
                ],
              },
            ],
          }),
        } as Response
      }),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Squad \(team\)/ })
    expect(team).toHaveAttribute('data-persona-count', '3')
    expect(team).toHaveAttribute('data-roster', 'declared')
    const rosterEl = within(team).getByTestId('declared-roster')
    expect(rosterEl).toHaveAttribute('data-persona-count', '3')
    // #438: one face (the chat target) plus the remainder, not three fanned
    // faces. `aria-label` also names the remainder, so it is not a bare glyph.
    expect(rosterEl).toHaveAttribute('data-stack-count', '1')
    expect(rosterEl).toHaveAttribute('data-remainder', '2')
    expect(rosterEl).toHaveAttribute('aria-label', 'Squad declared members, +2')
    expect(within(team).getByTestId('team-remainder')).toHaveTextContent('+2')
    // The declared roster keeps every persona name reachable, just not drawn.
    expect(rosterEl).toHaveTextContent('Researcher, Writer, Reviewer')
  })

  it('#525: a team row renders no Team badge and no definition-pane button', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Demo Team \(team\)/ })

    expect(within(team).queryByText('Team')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Open Demo Team team settings' }),
    ).not.toBeInTheDocument()
    // Team membership is still declared on the row itself (semantics kept).
    expect(team).toHaveAttribute('data-kind', 'team')
    expect(team).toHaveAttribute('aria-label', 'Demo Team (team)')
  })

  it('selects a team like an agent via ?team=', async () => {
    renderSidebar('/chat?team=demo-team')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Demo Team \(team\)/ })
    expect(team).toHaveAttribute('aria-current', 'page')
    expect(within(list).getByRole('link', { name: /Codey/ })).not.toHaveAttribute(
      'aria-current',
    )
  })

  it('REQ-24 #342: hides a team roster row as team:<id> and Unhide restores it', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Demo Team \(team\)/ })
    const zone = screen.getByRole('region', { name: 'Hidden Agents' })
    dragTo(team, zone)

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Demo Team \(team\)/ })).not.toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic', 'team:demo-team'])

    fireEvent.click(hiddenBotsButton(3))
    await unhideFromSearch('Demo Team', 'team:demo-team')
    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /Demo Team \(team\)/ })).toBeInTheDocument()
    })
    expect(storedHidden()).toEqual(['gate', 'skeptic'])
  })
})

describe('AgentSidebar favourites grid (REQ-94)', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('seeds Support as the first-load favourite when prefs are missing', async () => {
    localStorage.removeItem(PINNED_AGENTS_STORAGE_KEY)
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const grid = screen.getByTestId('agent-fav-grid')
    const supportTile = await within(grid).findByRole('link', { name: 'Support' })
    expect(supportTile.querySelector('.os-fav-tile__badge')).toHaveAttribute('data-role', 'support')
    expect(within(list).queryByRole('link', { name: /Support/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'support', name: 'Support' },
    ])
  })

  it('keeps an empty favourites grid bare with a quiet + until a drag starts', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const grid = screen.getByTestId('agent-fav-grid')
    expect(grid).toHaveClass('os-fav-grid--bare')
    expect(grid).toHaveAttribute('data-fav-empty', 'true')
    expect(screen.getByTestId('fav-empty-hint')).toHaveTextContent('+')
    expect(within(grid).queryByRole('link')).not.toBeInTheDocument()

    const dt = mockDataTransfer()
    fireEvent.dragStart(codey, { dataTransfer: dt })
    expect(grid).not.toHaveClass('os-fav-grid--bare')
    expect(screen.getByTestId('fav-empty-hint')).toHaveTextContent('drop')
    fireEvent.dragEnd(codey, { dataTransfer: dt })
  })

  it('drops a row onto the 2-up grid as a named large avatar and removes it from the list', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const stewie = within(list).getByRole('link', { name: /Stewie/ })
    const grid = screen.getByTestId('agent-fav-grid')
    expect(grid).toHaveAttribute('data-fav-layout', '2-up')
    expect(screen.queryByText(/Favourites/i)).not.toBeInTheDocument()

    dragTo(codey, grid)
    const first = await within(grid).findByRole('link', { name: 'Codey' })
    expect(first.querySelector('.os-agent-avatar--lg')).toBeTruthy()
    expect(first.querySelector('.os-fav-tile__name')).toHaveTextContent('Codey')
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()

    dragTo(stewie, grid)
    const tiles = within(grid).getAllByRole('link')
    expect(tiles.map((link) => link.getAttribute('aria-label'))).toEqual(['Codey', 'Stewie'])
    expect(tiles[1].querySelector('.os-fav-tile__name')).toHaveTextContent('Stewie')
    expect(within(list).queryByRole('link', { name: /Stewie/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
      { id: 'stewie', name: 'Stewie' },
    ])
  })

  it('keeps named tiles and list exclusion after remount', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([
        { id: 'codey', name: 'Codey' },
        { id: 'stewie', name: 'Stewie' },
      ]),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const grid = screen.getByTestId('agent-fav-grid')
    const tiles = await within(grid).findAllByRole('link')
    expect(tiles.map((link) => link.getAttribute('aria-label'))).toEqual(['Codey', 'Stewie'])
    expect(tiles[0].querySelector('.os-agent-avatar--lg')).toBeTruthy()
    expect(tiles[0].querySelector('.os-fav-tile__name')).toHaveTextContent('Codey')
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Stewie/ })).not.toBeInTheDocument()
  })

  it('overlays a role badge inside a favourite tile when the agent has a role', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const support = await within(list).findByRole('link', { name: /Support/ })
    const codey = within(list).getByRole('link', { name: /Codey/ })
    const grid = screen.getByTestId('agent-fav-grid')
    dragTo(support, grid)
    dragTo(codey, grid)

    const supportTile = await within(grid).findByRole('link', { name: 'Support' })
    const badge = supportTile.querySelector('.os-fav-tile__badge')
    expect(badge).toBeTruthy()
    expect(badge).toHaveClass('os-agent-role-badge')
    expect(badge).toHaveAttribute('data-role', 'support')
    expect(badge).toHaveTextContent('Support')
    expect(support.contains(badge)).toBe(false)

    const codeyTile = within(grid).getByRole('link', { name: 'Codey' })
    expect(codeyTile.querySelector('.os-fav-tile__badge')).toBeNull()
    expect(codeyTile.querySelector('.os-agent-role-badge')).toBeNull()
  })

  it('keeps favourite tiles ghost until hover or selected', async () => {
    renderSidebar('/chat?blueprint=codey')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const stewie = within(list).getByRole('link', { name: /Stewie/ })
    const grid = screen.getByTestId('agent-fav-grid')
    dragTo(codey, grid)
    dragTo(stewie, grid)

    const codeyTile = await within(grid).findByRole('link', { name: 'Codey' })
    const stewieTile = within(grid).getByRole('link', { name: 'Stewie' })
    expect(codeyTile).toHaveClass('os-fav-tile--active')
    expect(stewieTile).not.toHaveClass('os-fav-tile--active')
    expect(stewieTile.className).toMatch(/\bos-fav-tile\b/)
    expect(getComputedStyle(stewieTile).backgroundColor).toMatch(/rgba?\(0,\s*0,\s*0,\s*0\)|transparent/)
  })

  it('unfavourites when a tile is dropped onto the agents list (no duplicate)', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const grid = screen.getByTestId('agent-fav-grid')
    dragTo(codey, grid)

    const tile = await within(grid).findByRole('link', { name: 'Codey' })
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()

    const drop = screen.getByTestId('agent-list-drop')
    dragTo(tile, drop)

    await waitFor(() => {
      expect(within(grid).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
    })
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(within(list).getAllByRole('link', { name: /Codey/ })).toHaveLength(1)
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([])
  })

  it('unfavourites when a tile is dropped onto a list row', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const grid = screen.getByTestId('agent-fav-grid')
    dragTo(codey, grid)
    const tile = await within(grid).findByRole('link', { name: 'Codey' })
    const stewie = within(list).getByRole('link', { name: /Stewie/ })
    dragTo(tile, stewie)

    await waitFor(() => {
      expect(within(grid).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
    })
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([])
  })

  it('reorders favourite tiles within the grid and persists', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const stewie = within(list).getByRole('link', { name: /Stewie/ })
    const grid = screen.getByTestId('agent-fav-grid')
    dragTo(codey, grid)
    dragTo(stewie, grid)

    let tiles = within(grid).getAllByRole('link')
    expect(tiles.map((link) => link.getAttribute('aria-label'))).toEqual(['Codey', 'Stewie'])

    dragTo(tiles[1], tiles[0])
    await waitFor(() => {
      expect(
        within(grid)
          .getAllByRole('link')
          .map((link) => link.getAttribute('aria-label')),
      ).toEqual(['Stewie', 'Codey'])
    })
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'stewie', name: 'Stewie' },
      { id: 'codey', name: 'Codey' },
    ])
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Stewie/ })).not.toBeInTheDocument()
  })
})

describe('AgentSidebar favourite kind hrefs (REQ-171B #608)', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
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
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'demo',
                  object: 'team_roster',
                  name: 'Demo',
                  description: 'Example roster',
                  members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'omb',
                  title: 'OpenMousBot',
                  configured: true,
                  agents: [],
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 1,
                  object: 'herdr.agent',
                  kind: 'herdr',
                  name: 'w3:p1',
                  remote: '',
                  created_at: '2026-09-03T00:00:00Z',
                  updated_at: '2026-09-03T00:00:00Z',
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
              clis: [],
              native_consensus: {},
              catalog: {},
              rail: [],
            }),
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
    localStorage.clear()
  })

  it('pins blueprint / team / remote / herdr and uses kind-aware hrefs', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    const team = await within(list).findByRole('link', { name: /Demo \(team\)/ })
    const remote = await within(list).findByRole('link', { name: /OpenMousBot \(remote\)/ })
    const herdr = await within(list).findByRole('link', { name: /w3:p1/ })
    const grid = screen.getByTestId('agent-fav-grid')

    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    fireEvent.contextMenu(team)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    fireEvent.contextMenu(remote)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    fireEvent.contextMenu(herdr)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))

    const codeyTile = await within(grid).findByRole('link', { name: 'Codey' })
    const teamTile = within(grid).getByRole('link', { name: 'Demo' })
    const remoteTile = within(grid).getByRole('link', { name: 'OpenMousBot' })
    const herdrTile = within(grid).getByRole('link', { name: 'w3:p1' })

    expect(codeyTile).toHaveAttribute('href', '/chat?blueprint=codey')
    expect(teamTile).toHaveAttribute('href', '/chat?team=demo')
    expect(teamTile.getAttribute('href')).not.toMatch(/blueprint=/)
    // Issue #432 fix: 1-member team falls back to the single member's face rather than blank
    expect(teamTile.querySelector('[data-agent-id="codey"]')).toBeInTheDocument()
    expect(remoteTile).toHaveAttribute('href', '/chat?remote=omb')
    expect(remoteTile.getAttribute('href')).not.toMatch(/blueprint=/)
    expect(herdrTile).toHaveAttribute('href', '/teams/#herdr-members')

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: '2', altKey: true, bubbles: true, cancelable: true }),
      )
    })
    expect(screen.getByTestId('os-test-search')).toHaveTextContent('team=demo')
    expect(screen.getByTestId('os-test-search')).not.toHaveTextContent('blueprint=')

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: '3', altKey: true, bubbles: true, cancelable: true }),
      )
    })
    expect(screen.getByTestId('os-test-search')).toHaveTextContent('remote=omb')
    expect(screen.getByTestId('os-test-search')).not.toHaveTextContent('blueprint=')
  })

  it('#542 highlights the pinned team when the pane is on that team', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([
        { id: 'team:demo', name: 'Demo' },
        { id: 'remote:omb', name: 'OpenMousBot' },
        { id: 'codey', name: 'Codey' },
      ]),
    )
    renderSidebar('/chat?team=demo')
    await screen.findByTestId('agent-fav-grid')
    await waitFor(() => expect(pinTile('team:demo')).toBeTruthy())
    expect(isPinActive('team:demo')).toBe(true)
    expect(isPinActive('remote:omb')).toBe(false)
    expect(isPinActive('codey')).toBe(false)
  })

  it('#542 highlights the pinned remote when the pane is on that remote', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([
        { id: 'team:demo', name: 'Demo' },
        { id: 'remote:omb', name: 'OpenMousBot' },
        { id: 'codey', name: 'Codey' },
      ]),
    )
    renderSidebar('/chat?remote=omb')
    await screen.findByTestId('agent-fav-grid')
    await waitFor(() => expect(pinTile('remote:omb')).toBeTruthy())
    expect(isPinActive('remote:omb')).toBe(true)
    expect(isPinActive('team:demo')).toBe(false)
  })
})

describe('AgentSidebar Django prefs (REQ-144)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('applies server favourites and hidden ids over localStorage', async () => {
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, JSON.stringify([{ id: 'old', name: 'Old' }]))
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['stale']))
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
              principal: 'user:alice',
              guest: false,
              empty: false,
              favourites: [{ id: 'codey', name: 'Codey' }],
              hidden_agents: ['stewie'],
            }),
          } as Response
        }
        return mockFetch()(url)
      }),
    )

    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const grid = await screen.findByTestId('agent-fav-grid')
    await waitFor(() => {
      expect(within(grid).getByRole('link', { name: 'Codey' })).toBeInTheDocument()
    })
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Stewie/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      { id: 'codey', name: 'Codey' },
    ])
    expect(JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')).toEqual(['stewie'])
  })
})

describe('AgentSidebar pin unpin + plugins (REQ-5c #322)', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('unpins from the context menu and clears swarm_pinned_agents', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    fireEvent.contextMenu(codey)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Pin$/i }))
    const grid = screen.getByLabelText('Pinned agents')
    const tile = within(grid).getByRole('link', { name: 'Codey' })
    expect(tile).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Codey/ })).not.toBeInTheDocument()

    fireEvent.contextMenu(tile)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Unpin$/i }))
    await waitFor(() => {
      expect(within(grid).queryByRole('link', { name: 'Codey' })).not.toBeInTheDocument()
    })
    expect(within(list).getByRole('link', { name: /Codey/ })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]')).toEqual([])
  })

  it('opens the Plugins search popup and closes it', async () => {
    renderSidebar()
    await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.click(screen.getByRole('button', { name: /Plugins/i }))
    const dialog = await screen.findByRole('dialog', { name: 'Plugins' })
    expect(within(dialog).getByRole('combobox', { name: 'Filter tools' })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close plugins' }))
    expect(screen.queryByRole('dialog', { name: 'Plugins' })).not.toBeInTheDocument()
  })
})

const SCALE_MEMBERS = [
  { id: 'cos', name: 'Pat', kind: 'agent', role: 'chief_of_staff', started_at: '2026-09-03T00:00:00Z', status: 'running' },
  { id: 'ada', name: 'Ada', kind: 'agent', started_at: '2026-09-03T00:00:01Z', status: 'finished' },
  { id: 'bea', name: 'Bea', kind: 'agent', started_at: '2026-09-03T00:00:02Z', status: 'running' },
  { id: 'cyd', name: 'Cyd', kind: 'agent', started_at: '2026-09-03T00:00:03Z', status: 'running' },
  { id: 'dee', name: 'Dee', kind: 'agent', started_at: '2026-09-03T00:00:04Z', status: 'running' },
]

const STACK_REMOTES = {
  object: 'list',
  data: [
    {
      id: 'omb',
      title: 'OMB',
      configured: true,
      agents: [
        { id: 'omb-cos', name: 'CoS', started_at: '2026-09-03T00:00:00Z', role: 'chief_of_staff' },
        { id: 'w1', name: 'Worker 1', started_at: '2026-09-03T00:00:01Z' },
        { id: 'w2', name: 'Worker 2', started_at: '2026-09-03T00:00:02Z' },
        { id: 'w3', name: 'Worker 3', started_at: '2026-09-03T00:00:03Z' },
        { id: 'w4', name: 'Worker 4', started_at: '2026-09-03T00:00:04Z' },
      ],
    },
    {
      id: 'hermes',
      title: 'Hermes',
      configured: true,
      agents: [{ id: 'hermes-1', name: 'Hermes', started_at: '2026-09-03T00:00:00Z' }],
    },
    {
      id: 'empty-box',
      title: 'Empty Box',
      configured: true,
      agents: [],
    },
    {
      id: 'rakazo',
      title: 'Rakazo',
      configured: true,
      agents: [
        { id: 'r1', name: 'Rakazo A', started_at: '2026-09-03T00:00:00Z' },
        { id: 'r2', name: 'Rakazo B', started_at: '2026-09-03T00:00:01Z' },
      ],
    },
    {
      id: 'lab-swarm',
      kind: 'open-swarm',
      title: 'Lab swarm',
      configured: true,
      agents: [
        { id: 'ns-cos', name: 'CoS', started_at: '2026-09-03T00:00:00Z' },
        { id: 'ns-w', name: 'Nested worker', started_at: '2026-09-03T00:00:01Z' },
      ],
    },
  ],
}

describe('AgentSidebar stacked avatars (REQ-68)', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
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
        if (url.includes('/v1/remotes')) {
          return {
            ok: true,
            status: 200,
            json: async () => STACK_REMOTES,
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
                  id: 'scale-out',
                  object: 'team_roster',
                  name: 'Scale Out',
                  description: 'Five workers',
                  members: SCALE_MEMBERS,
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
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
    localStorage.clear()
  })

  it('#438: a 5-member team row shows one chat face and +4, not a fan of 3 faces', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Scale Out \(team\)/ })
    // #438 supersedes REQ-891's sidepane stack: one face for the member you are
    // talking to, plus a +N for the rest. The old assertion here pinned
    // "at most 3 faces with no +N remainder" and three `.os-avatar-stack__face`
    // nodes with staggered pulse delays — the fan this ticket removes.
    expect(team).toHaveAttribute('data-stack-count', '1')
    expect(team).toHaveAttribute('data-remainder', '4')
    expect(team.querySelector('.os-avatar-stack__face')).toBeNull()
    expect(within(team).getByTestId('team-chat-face')).toBeInTheDocument()
    expect(within(team).getByTestId('team-remainder')).toHaveTextContent('+4')
  })

  it('#438: the team row face is the chat target, not an arbitrary first face', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Scale Out \(team\)/ })
    // `defaultSessionForTeam` owns "chief_of_staff_id, else CoS-role, else first"
    // — the rail reads that rule rather than re-deriving a member to show.
    const face = within(team).getByTestId('team-chat-face')
    expect(face).toHaveAttribute('data-remainder', '4')
    expect(face.querySelector('[data-agent-avatar]')).toBeInTheDocument()
  })

  it('keeps a single-agent remote as one normal avatar (no mini stack)', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const hermes = await within(list).findByRole('link', { name: /Hermes \(remote\)/ })
    expect(hermes).toHaveAttribute('data-stack-count', '1')
    expect(hermes).toHaveAttribute('data-remainder', '0')
    expect(within(hermes).queryByLabelText('Hermes members')).not.toBeInTheDocument()
    expect(within(hermes).queryByText(/^\+\d+$/)).not.toBeInTheDocument()
    expect(hermes.querySelector('[data-agent-avatar]')).toBeInTheDocument()
    expect(hermes.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
  })

  it('labels OpenMousBot (not OMB) and stacks CoS + workers; left-click opens directly, right-click Select Agent opens picker', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const omb = await within(list).findByRole('link', { name: /OpenMousBot \(remote\)/ })
    expect(omb).toHaveTextContent('OpenMousBot')
    expect(omb).not.toHaveTextContent(/\bOMB\b/)
    // #438: one face + a +N for the remaining members (this asserted a 3-face
    // fan with no remainder before — the fan REQ-891 asked for and #438 removes).
    expect(omb).toHaveAttribute('data-stack-count', '1')
    expect(omb).toHaveAttribute('data-remainder', '4')
    expect(within(omb).getByTestId('team-remainder')).toHaveTextContent('+4')
    expect(within(list).getByRole('link', { name: /Rakazo \(remote\)/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Lab swarm \(remote\)/ })).toBeInTheDocument()

    // REQ-130: primary click opens chat immediately with no intermediate picker
    fireEvent.click(omb)
    expect(screen.queryByRole('dialog', { name: 'OpenMousBot sessions' })).not.toBeInTheDocument()

    // REQ-130: right-click menu provides Select Agent to open the member picker
    fireEvent.contextMenu(omb)
    const selectAgent = await screen.findByRole('menuitem', { name: 'Select Agent' })
    fireEvent.click(selectAgent)

    const dialog = await screen.findByRole('dialog', { name: 'OpenMousBot sessions' })
    expect(within(dialog).getAllByRole('option')).toHaveLength(5)
    expect(dialog).toHaveTextContent('OpenMousBot')
    expect(dialog).not.toHaveTextContent(/\bOMB\b/)
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Filter sessions' }), {
      target: { value: 'Worker 1' },
    })
    expect(within(dialog).getAllByRole('option')).toHaveLength(1)
    fireEvent.click(within(dialog).getByRole('option', { name: /Worker 1/ }))
    expect(screen.queryByRole('dialog', { name: 'OpenMousBot sessions' })).not.toBeInTheDocument()
  })

  it('omits Select Agent on a one-bot remote (Hermes is implicit)', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const hermes = await within(list).findByRole('link', { name: /Hermes \(remote\)/ })
    fireEvent.contextMenu(hermes)
    const menu = await screen.findByRole('menu', { name: 'Actions for Hermes' })
    expect(within(menu).queryByRole('menuitem', { name: 'Select Agent' })).not.toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Hide from sidebar' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: /sessions/i })).not.toBeInTheDocument()
  })

  it('omits Select Agent on a remote with no listed bots', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const empty = await within(list).findByRole('link', { name: /Empty Box \(remote\)/ })
    fireEvent.contextMenu(empty)
    const menu = await screen.findByRole('menu', { name: 'Actions for Empty Box' })
    expect(within(menu).queryByRole('menuitem', { name: 'Select Agent' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: /sessions/i })).not.toBeInTheDocument()
  })

  it('shows Select Agent for a two-bot remote and lists both names', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const rakazo = await within(list).findByRole('link', { name: /Rakazo \(remote\)/ })
    fireEvent.contextMenu(rakazo)
    const selectAgent = await screen.findByRole('menuitem', { name: 'Select Agent' })
    fireEvent.click(selectAgent)
    const dialog = await screen.findByRole('dialog', { name: 'Rakazo sessions' })
    const options = within(dialog).getAllByRole('option')
    expect(options).toHaveLength(2)
    expect(dialog).toHaveTextContent('Rakazo A')
    expect(dialog).toHaveTextContent('Rakazo B')
  })

  it('opens the team picker filtered to that roster via Select Agent, and opens CoS directly on click', async () => {
    renderSidebar('/chat?team=scale-out')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Scale Out \(team\)/ })

    // REQ-130: primary click navigates directly to CoS chat context
    fireEvent.click(team)
    expect(screen.queryByRole('dialog', { name: 'Scale Out sessions' })).not.toBeInTheDocument()
    expect(screen.getByTestId('os-test-search')).toHaveTextContent('team=scale-out&session=cos')

    // REQ-130: right-click context menu opens member picker via Select Agent
    fireEvent.contextMenu(team)
    const selectAgent = await screen.findByRole('menuitem', { name: 'Select Agent' })
    fireEvent.click(selectAgent)

    const dialog = await screen.findByRole('dialog', { name: 'Scale Out sessions' })
    expect(within(dialog).getAllByRole('option')).toHaveLength(5)
    expect(within(dialog).getByRole('option', { name: /Pat/ })).toHaveAttribute(
      'data-session-id',
      'scale-out:cos',
    )
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Filter sessions' }), {
      target: { value: 'cyd' },
    })
    expect(within(dialog).getAllByRole('option')).toHaveLength(1)
    fireEvent.click(within(dialog).getByRole('option', { name: /Cyd/ }))
    expect(screen.queryByRole('dialog', { name: 'Scale Out sessions' })).not.toBeInTheDocument()
  })
})

describe('AgentSidebar special roles', () => {
  const roster = [
    {
      id: 'codey',
      object: 'blueprint' as const,
      name: 'Codey',
      description: 'Code',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: null,
      rail: true,
    },
    {
      id: 'skeptic',
      object: 'blueprint' as const,
      name: 'Skeptic',
      description: 'Retry stub',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'skeptic',
      rail: true,
    },
    {
      id: 'gate',
      object: 'blueprint' as const,
      name: 'Gate',
      description: 'Approve stub',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'gate',
      rail: true,
    },
    {
      id: 'support',
      object: 'blueprint' as const,
      name: 'Support',
      description: 'Onboarding. First team.',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'support',
      rail: true,
    },
  ]

  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([]))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = typeof input === 'string' ? input : (input as Request).url
        if (url.includes('herdr')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: roster }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lists Support first with a role=support look, not a diamond', async () => {
    renderSidebar('/chat?blueprint=support')
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await waitFor(() => {
      expect(within(list).getAllByRole('link').length).toBeGreaterThan(0)
    })
    const links = within(list).getAllByRole('link')
    expect(links[0]).toHaveTextContent('Support')
    expect(links[0]).toHaveAttribute('data-role', 'support')
    expect(links[0].querySelector('.os-agent-dot')).toBeNull()
    expect(links[0].querySelector('.os-agent-role-badge')).not.toBeNull()
    expect(within(list).getByRole('link', { name: /Gate/ })).toHaveAttribute('data-role', 'gate')
    expect(within(list).getByRole('link', { name: /Skeptic/ })).toHaveAttribute(
      'data-role',
      'skeptic',
    )
  })
})

describe('AgentSidebar REQ-129 — Hidden Agents row chrome', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders "Hidden Agents" label with count and swaps count to a chevron on hover', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['gate', 'skeptic']))
    renderSidebar()
    const btn = await screen.findByTestId('os-hidden-bots-button')
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveClass('os-hidden-bots-row')
    expect(within(btn).getByText('Hidden Agents')).toBeInTheDocument()

    // Resting state: count is visible
    const countEl = within(btn).getByTestId('os-hidden-bots-count')
    expect(countEl).toHaveTextContent('2')

    // Hover state: swaps the count for the chevron icon (#557 — was a literal '>')
    fireEvent.mouseEnter(btn)
    const tail = within(btn).getByTestId('os-hidden-bots-tail')
    expect(tail.querySelector('svg.lucide-chevron-right')).toBeTruthy()
    expect(tail).not.toHaveTextContent('>')

    // Leave hover state: restores count
    fireEvent.mouseLeave(btn)
    expect(within(btn).getByTestId('os-hidden-bots-count')).toHaveTextContent('2')
  })
})

describe('AgentSidebar REQ-116 — Resizable left rail', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders resizer handle on desktop and sets avatar-only state when narrow', async () => {
    renderSidebar('/chat?narrow=false')
    const resizer = await screen.findByTestId('rail-resize-handle')
    expect(resizer).toBeInTheDocument()
    expect(resizer).toHaveAttribute('role', 'separator')

    const rail = screen.getByTestId('os-agent-rail')
    expect(rail).toHaveAttribute('data-avatar-only', 'false')

    // Simulate resizing with keyboard ArrowLeft to shrink past threshold
    fireEvent.keyDown(resizer, { key: 'Home' }) // jumps to MIN_RAIL_WIDTH (68px)
    expect(rail).toHaveAttribute('data-avatar-only', 'true')
    expect(rail).toHaveClass('os-agent-sidebar--avatar-only')

    // Simulate expanding back
    fireEvent.keyDown(resizer, { key: 'End' }) // jumps to MAX_RAIL_WIDTH (420px)
    expect(rail).toHaveAttribute('data-avatar-only', 'false')
    expect(rail).not.toHaveClass('os-agent-sidebar--avatar-only')
  })

  it('initializes in avatar-only mode if stored width is <= threshold', async () => {
    localStorage.setItem('swarm_rail_width', '80')
    renderSidebar('/chat?narrow=false')
    const rail = await screen.findByTestId('os-agent-rail')
    expect(rail).toHaveAttribute('data-avatar-only', 'true')
    expect(rail).toHaveClass('os-agent-sidebar--avatar-only')
  })
})

describe('AgentSidebar REQ-172 — Alt hotkey spill into unpinned rows', () => {
  beforeEach(() => {
    localStorage.clear()
    global.fetch = mockFetch()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders spill hotkey badges on unpinned rows when favourites < 10', async () => {
    rememberEmptyFavourites()
    renderSidebar()

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const hotkeyBadges = screen.getAllByTestId('spill-hotkey')
    expect(hotkeyBadges.length).toBeGreaterThan(0)
    expect(hotkeyBadges[0].textContent).toMatch(/^(Alt\+|⌥)1$/)
  })

  it('navigates to unpinned row when pressing Alt+N for a spilled slot', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'support', name: 'Support', pinned_at: '2026-09-01T00:00:00Z' }]),
    )
    renderSidebar()

    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const alt2Event = new KeyboardEvent('keydown', {
      key: '2',
      altKey: true,
      bubbles: true,
      cancelable: true,
    })
    act(() => {
      window.dispatchEvent(alt2Event)
    })
    expect(alt2Event.defaultPrevented).toBe(true)
  })
})

describe('AgentSidebar drag-to-delete recycle bin', () => {
  beforeEach(() => {
    localStorage.clear()
    global.fetch = mockFetch()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders normal footer buttons when not dragging', async () => {
    renderSidebar()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('os-teams-button')).toBeInTheDocument()
    expect(screen.getByTestId('os-plugins-button')).toBeInTheDocument()
    expect(screen.queryByTestId('os-recycle-bin')).not.toBeInTheDocument()
  })

  it('replaces static menu with recycle bin when dragging an agent row', async () => {
    renderSidebar()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })

    const codeyRow = screen.getByRole('link', { name: /codey/i })
    expect(codeyRow).toBeInTheDocument()

    const dt = {
      setData: vi.fn(),
      getData: vi.fn(),
      clearData: vi.fn(),
      effectAllowed: 'uninitialized',
      dropEffect: 'none',
      types: [],
    }

    fireEvent.dragStart(codeyRow, { dataTransfer: dt })

    // When dragging, recycle bin replaces Teams & Plugins
    const bin = screen.getByTestId('os-recycle-bin')
    expect(bin).toBeInTheDocument()
    expect(within(bin).getByText('Delete')).toBeInTheDocument()
    expect(screen.queryByTestId('os-teams-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('os-plugins-button')).not.toBeInTheDocument()

    // Drag over bin
    fireEvent.dragOver(bin, { dataTransfer: dt })

    // Drop onto bin triggers delete confirmation
    fireEvent.drop(bin, { dataTransfer: dt })

    await waitFor(() => {
      expect(screen.getByText(/Delete Codey\?/i)).toBeInTheDocument()
    })
  })
})

describe('AgentSidebar REQ-861 conceal', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('#432 pinned team slides members when a worker is working', async () => {
    resetCliRunState()
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'team:research', name: 'Research' }]),
    )
    renderSidebar()
    const tile = await screen.findByRole('link', { name: 'Research' })
    expect(tile).toHaveClass('os-fav-tile')
    expect(tile).not.toHaveClass('os-fav-tile--working-stack')
    act(() => {
      notifyCliRunState('ada', true)
    })
    expect(tile).toHaveClass('os-fav-tile--working-stack')
    act(() => {
      notifyCliRunState('ada', false)
    })
    expect(tile).not.toHaveClass('os-fav-tile--working-stack')
    resetCliRunState()
  })

  it('REQ-891 sidepane team row gets os-agent-row--working-stack when a worker is working', async () => {
    resetCliRunState()
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const team = await within(list).findByRole('link', { name: /Research \(team\)/ })
    expect(team).toHaveClass('os-agent-row--team')
    expect(team).not.toHaveClass('os-agent-row--working-stack')
    act(() => {
      notifyCliRunState('ada', true)
    })
    expect(team).toHaveClass('os-agent-row--working-stack')
    act(() => {
      notifyCliRunState('ada', false)
    })
    expect(team).not.toHaveClass('os-agent-row--working-stack')
    resetCliRunState()
  })

  it('#542 keeps the seat row active for a blueprint scope', async () => {
    renderSidebar('/chat?blueprint=stewie')
    await waitFor(() => expect(railRow('stewie')).toBeTruthy())
    expect(isRowActive('stewie')).toBe(true)
  })

  it('#549 lists a hidden team in the hidden view so the badge and the list agree', async () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['team:research']))
    renderSidebar()
    const button = await screen.findByTestId('os-hidden-bots-button')
    // The badge counts it…
    expect(button.getAttribute('aria-label')).toContain('Hidden Agents 1')
    fireEvent.click(button)
    // …and now the list it opens shows the same thing, instead of nothing.
    const dialog = await screen.findByRole('dialog', { name: 'Search' })
    await waitFor(() => expect(within(dialog).getByText('Research')).toBeInTheDocument())
    expect(within(dialog).getByTestId('unhide-team:research')).toBeInTheDocument()
  })

  it('#555 keeps the collapse control out of the pane header and on the divider pill', async () => {
    renderSidebar()
    const pill = await screen.findByTestId('rail-divider-pill')
    // The pill is the only collapse affordance now…
    const conceal = within(pill).getByRole('button', { name: 'Collapse sidebar' })
    expect(conceal).toHaveAttribute('data-testid', 'sidebar-conceal')
    // …and it lives inside the resizer, which owns the divider.
    const handle = screen.getByTestId('rail-resize-handle')
    expect(handle.contains(pill)).toBe(true)

    // A drag starting on the pill must not reach the resizer, or clicking to
    // collapse would also begin a resize.
    fireEvent.pointerDown(pill, { clientX: 100 })
    expect(handle.className).not.toContain('os-rail-resizer--active')
    fireEvent.pointerDown(handle, { clientX: 100 })
    expect(handle.className).toContain('os-rail-resizer--active')

    // Collapsed state stays recoverable from the same divider.
    fireEvent.click(conceal)
    expect(screen.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'true')
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument()
  })

  it('renders standard pane icons for collapse/expand (#417, #767)', async () => {
    renderSidebar()
    const conceal = await screen.findByRole('button', { name: 'Collapse sidebar' })
    expect(conceal).toHaveAttribute('title', 'Collapse sidebar')
    expect(conceal).toHaveAttribute('data-testid', 'sidebar-conceal')
    expect(conceal.querySelector('svg.lucide-panel-left-close')).toBeTruthy()
    expect(conceal.querySelector('.os-brand-mark-geometric')).toBeNull()
    expect(screen.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'false')
    expect(screen.queryByRole('button', { name: 'Expand sidebar' })).not.toBeInTheDocument()

    fireEvent.click(conceal)
    expect(screen.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'true')
    expect(screen.queryByRole('button', { name: 'Collapse sidebar' })).not.toBeInTheDocument()
    const expand = screen.getByRole('button', { name: 'Expand sidebar' })
    expect(expand).toHaveAttribute('data-testid', 'sidebar-expand')
    expect(expand.querySelector('svg.lucide-panel-left-open')).toBeTruthy()
  })

  it('#421 collapsed rail hides Calendar label and info-i (hostname-only chrome)', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
    expect(css).toMatch(/os-agent-sidebar--avatar-only \.os-calendar-label/)
    expect(css).toMatch(/os-agent-sidebar--avatar-only \[data-testid="rail-update-chrome"\]/)

    renderSidebar()
    expect(screen.getByTestId('rail-update-chrome')).toBeInTheDocument()
    expect(screen.getByLabelText('Hostname')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Collapse sidebar' }))
    expect(screen.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'true')
    expect(screen.getByTestId('os-calendar-button').querySelector('.os-calendar-label')).toBeTruthy()
    expect(screen.queryByTestId('rail-update-chrome')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Hostname')).not.toBeInTheDocument()
  })

  it('restores the rail from the collapsed expand control (#417)', async () => {
    renderSidebar()
    fireEvent.click(await screen.findByRole('button', { name: 'Collapse sidebar' }))
    expect(screen.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }))
    expect(screen.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'false')
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument()
  })

  it('conceals the mobile drawer via the close button and backdrop', async () => {
    // #555: the narrow overlay's dismiss is the dedicated close button. The
    // divider pill (and so the collapse/expand control) only exists on the
    // desktop rail, because the drawer has no divider to ride — previously a
    // second control did the same `onClose()` the close button already does.
    const onClose = vi.fn()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AgentSidebar open narrow onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.queryByTestId('rail-divider-pill')).not.toBeInTheDocument()
    // [0] is the backdrop, [1] is the drawer's own close button.
    const drawerClose = screen.getAllByRole('button', { name: 'Close agents sidebar' })[1]
    fireEvent.click(drawerClose)
    expect(onClose).toHaveBeenCalledTimes(1)

    const backdrop = screen.getAllByRole('button', { name: 'Close agents sidebar' })[0]
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('AgentSidebar #446 awaiting-approval attention', () => {
  beforeEach(() => {
    resetAgentAttention()
    localStorage.clear()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    resetAgentAttention()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('paints the rail row snippet slot and restores it when the decision lands', async () => {
    rememberEmptyFavourites()
    renderSidebar()
    const row = await screen.findByRole('link', { name: /Codey/ })
    expect(within(row).queryByTestId('rail-needs-approval')).not.toBeInTheDocument()
    expect(within(row).getByText('Code assistant')).toBeInTheDocument()

    act(() => {
      notifyApprovalWait('codey', 'tool-1', true)
    })
    const mark = within(row).getByTestId('rail-needs-approval')
    expect(mark).toHaveTextContent(NEEDS_APPROVAL_LABEL)
    expect(mark).toHaveClass('os-rail-attention')
    expect(within(row).queryByText('Code assistant')).not.toBeInTheDocument()

    act(() => {
      notifyApprovalWait('codey', 'tool-1', false)
    })
    expect(within(row).queryByTestId('rail-needs-approval')).not.toBeInTheDocument()
    expect(within(row).getByText('Code assistant')).toBeInTheDocument()
  })

  it('overlays the pinned tile for the waiting agent', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'codey', name: 'Codey' }]),
    )
    renderSidebar()
    const tile = await screen.findByRole('link', { name: 'Codey' })
    expect(tile).toHaveClass('os-fav-tile')
    expect(within(tile).queryByTestId('pin-needs-approval')).not.toBeInTheDocument()

    act(() => {
      notifyApprovalWait('codey', 'tool-7', true)
    })
    expect(within(tile).getByTestId('pin-needs-approval')).toHaveTextContent(NEEDS_APPROVAL_LABEL)

    act(() => {
      notifyApprovalWait('codey', 'tool-7', false)
    })
    expect(within(tile).queryByTestId('pin-needs-approval')).not.toBeInTheDocument()
  })

  it('flags a pinned team while it still has other tools outstanding', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'team:research', name: 'Research' }]),
    )
    renderSidebar()
    const tile = await screen.findByRole('link', { name: 'Research' })

    act(() => {
      notifyApprovalWait('ada', 'tool-a', true)
      notifyApprovalWait('ada', 'tool-b', true)
    })
    expect(within(tile).getByTestId('pin-needs-approval')).toBeInTheDocument()

    act(() => {
      notifyApprovalWait('ada', 'tool-a', false)
    })
    expect(within(tile).getByTestId('pin-needs-approval')).toBeInTheDocument()

    act(() => {
      notifyApprovalWait('ada', 'tool-b', false)
    })
    expect(within(tile).queryByTestId('pin-needs-approval')).not.toBeInTheDocument()
  })
})



describe('#687 one delete removes at most one seat', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
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
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'omb',
                  title: 'OpenMousBot',
                  configured: true,
                  agents: [],
                },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/herdr-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/agents/designs')) {
          // #687: an explicit empty designs list — a blueprint-shaped fallback
          // here used to mint a designed-agent row per blueprint and duplicate
          // every name in the rail.
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              clis: [],
              native_consensus: {},
              catalog: {},
              rail: [],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              ...blueprints,
              blueprint('omb', 'Hermes', 'Agent sharing its id with a remote'),
            ],
          }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('deleting the Hermes agent keeps the same-id remote row', async () => {
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const hermesAgent = await within(list).findByRole('link', { name: /Hermes/ })
    const ombRemote = await within(list).findByRole('link', { name: /OpenMousBot \(remote\)/ })
    expect(hermesAgent).toBeInTheDocument()
    expect(ombRemote).toBeInTheDocument()

    fireEvent.contextMenu(hermesAgent)
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Delete$/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(within(list).queryByRole('link', { name: /Hermes/ })).not.toBeInTheDocument()
    })
    // The showstopper: the remote shares the bare id `omb` with the deleted
    // agent. It must survive — 1 delete = at most 1 seat lost.
    expect(
      await within(list).findByRole('link', { name: /OpenMousBot \(remote\)/ }),
    ).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(DELETED_RAIL_IDS_KEY) || '[]')).toEqual(['omb'])
  })
})

describe('#783/#781/#784 — drag footer: zero shift, distinct drop zones, centered compact icons', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  async function css() {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    return readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
  }

  it('#783: the recycle bin reserves the idle footer cluster height — no drag layout jump', async () => {
    // jsdom has no layout engine, so the zero-shift contract is pinned at the
    // source: the bin's min-height equals the idle cluster (Teams + Plugins +
    // Routines + hostname row), and the bin replaces — never stacks with —
    // the menu during a drag.
    const sheet = await css()
    expect(sheet).toMatch(/\.os-recycle-bin\s*\{[^}]*min-height:\s*10rem/)
    renderSidebar()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    fireEvent.dragStart(screen.getByRole('link', { name: /codey/i }), {
      dataTransfer: { setData: vi.fn(), getData: vi.fn(), types: [] },
    })
    const bin = screen.getByTestId('os-recycle-bin')
    expect(bin).toBeInTheDocument()
    expect(screen.queryByTestId('os-teams-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('os-plugins-button')).not.toBeInTheDocument()
  })

  it('#781: the Unassigned drop zone carries a distinct, non-error affordance', async () => {
    const sheet = await css()
    expect(sheet).toMatch(/\.os-rail-section-empty--unassigned/)
    expect(sheet).not.toMatch(/\.os-rail-section-empty--unassigned[^}]*border-error/)
  })

  it('#784: compact-rail footer icons are center-aligned with the avatars', async () => {
    const sheet = await css()
    expect(sheet).toMatch(/\.os-agent-sidebar--avatar-only \[data-testid='sidebar-footer-container'\]/)
    expect(sheet).toMatch(/\.os-agent-sidebar--avatar-only \.os-rail-hostname-row/)
  })
})

describe('#765 — drag the divider to the edge: full collapse to 0px and back', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('dragging the resizer below the collapse threshold snaps the rail fully shut', async () => {
    renderSidebar()
    const rail = await screen.findByTestId('os-agent-rail')
    const handle = await screen.findByTestId('rail-resize-handle')

    fireEvent.pointerDown(handle, { clientX: 200, pointerId: 1 })
    // Drag left past COLLAPSE_SNAP_THRESHOLD (52) from a 256px start…
    act(() => {
      window.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, pointerId: 1 }))
    })
    // …release: width 256 - 80 = 176 normally, but the snap contract sends
    // the rail to 0px only below the threshold; 176 stays continuous.
    act(() => {
      window.dispatchEvent(new PointerEvent('pointerup', { clientX: 120, pointerId: 1 }))
    })
    expect(rail.style.width).toBe('176px')

    // Now drag past the threshold: 256 - 230 = 26 < 52 → collapsed.
    fireEvent.pointerDown(handle, { clientX: 256, pointerId: 2 })
    act(() => {
      window.dispatchEvent(new PointerEvent('pointermove', { clientX: 26, pointerId: 2 }))
    })
    act(() => {
      window.dispatchEvent(new PointerEvent('pointerup', { clientX: 26, pointerId: 2 }))
    })
    expect(rail).toHaveAttribute('data-collapsed', 'true')
    expect(rail).toHaveClass('os-agent-sidebar--collapsed')
    expect(rail.style.width).toBe('0px')
    // Persisted, so a reload restores the divider-only state.
    expect(localStorage.getItem('swarm_rail_width')).toBe('0')
  })

  it('dragging open from the collapsed state snaps first to avatar width', async () => {
    localStorage.setItem('swarm_rail_width', '0')
    renderSidebar()
    const rail = await screen.findByTestId('os-agent-rail')
    expect(rail).toHaveAttribute('data-collapsed', 'true')

    // The expand pill is the only way back and is visible without hover.
    const expand = screen.getByRole('button', { name: 'Expand sidebar' })
    fireEvent.click(expand)
    expect(rail).toHaveAttribute('data-collapsed', 'false')
    expect(rail.style.width).toBe('256px')
    expect(localStorage.getItem('swarm_rail_width')).toBe('256')
  })

  it('the collapse button now conceals fully (0px) and keyboard Home matches', async () => {
    renderSidebar()
    const rail = await screen.findByTestId('os-agent-rail')
    const handle = await screen.findByTestId('rail-resize-handle')

    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(rail).toHaveAttribute('data-collapsed', 'true')
    expect(rail.style.width).toBe('0px')

    // End re-opens from the collapsed state.
    fireEvent.keyDown(handle, { key: 'End' })
    expect(rail).not.toHaveAttribute('data-collapsed', 'true')
    expect(rail.getAttribute('data-avatar-only')).toBe('false')
  })
})

describe('#741 — the pill is a handle: drag from it resizes, click still toggles', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('dragging from the pill resizes the rail (no stopPropagation wall)', async () => {
    renderSidebar()
    const rail = await screen.findByTestId('os-agent-rail')
    const pill = await screen.findByTestId('rail-divider-pill')

    fireEvent.pointerDown(pill, { clientX: 256, pointerId: 7 })
    act(() => {
      window.dispatchEvent(new PointerEvent('pointermove', { clientX: 336, pointerId: 7 }))
    })
    act(() => {
      window.dispatchEvent(new PointerEvent('pointerup', { clientX: 336, pointerId: 7 }))
    })
    // 256 + 80 = 336 — the drag went through to the shared resize body.
    expect(rail.style.width).toBe('336px')
    expect(localStorage.getItem('swarm_rail_width')).toBe('336')
  })

  it('a plain click on the pill still toggles, and the next click is not swallowed', async () => {
    renderSidebar()
    const rail = await screen.findByTestId('os-agent-rail')

    // Click collapse → collapses.
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(rail).toHaveAttribute('data-collapsed', 'true')

    // Click expand → expands. (A leaked drag-guard would eat this.)
    fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }))
    expect(rail).not.toHaveAttribute('data-collapsed', 'true')
    expect(rail.style.width).toBe('256px')

    // And collapse works again — intent gate fully reset.
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(rail).toHaveAttribute('data-collapsed', 'true')
  })

  it('a drag ended on the pill does not toggle on release', async () => {
    renderSidebar()
    const rail = await screen.findByTestId('os-agent-rail')
    const pill = await screen.findByTestId('rail-divider-pill')

    fireEvent.pointerDown(pill, { clientX: 256, pointerId: 8 })
    act(() => {
      window.dispatchEvent(new PointerEvent('pointermove', { clientX: 296, pointerId: 8 }))
    })
    act(() => {
      window.dispatchEvent(new PointerEvent('pointerup', { clientX: 296, pointerId: 8 }))
    })
    // The synthetic click React would fire after the gesture:
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    // Width is the dragged value (296), not the toggle's 0px.
    expect(rail.style.width).toBe('296px')
    expect(rail).not.toHaveAttribute('data-collapsed', 'true')
  })
})

describe('#747 — remote rows render their platform-themed face', () => {
  beforeEach(() => {
    localStorage.clear()
    rememberEmptyFavourites()
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('a Letta remote with no member faces shows the Letta face, not the generic Users mark', async () => {
    // Patch the remotes fixture for this test by re-stubbing fetch: the
    // shared mockFetch serves omb; this test needs a letta row.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                { id: 'letta-1', kind: 'letta', title: 'Letta Core', configured: true, agents: [] },
              ],
            }),
          } as Response
        }
        return (mockFetch() as unknown as (u: RequestInfo) => Promise<Response>)(input)
      }),
    )

    renderSidebar()
    await waitFor(async () => {
      const themed = document.querySelector("[data-remote-kind='letta']")
      expect(themed).not.toBeNull()
    })
    expect(document.querySelector('.os-remote-face')).not.toBeNull()
  })
})
