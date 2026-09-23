/**
 * REQ-910 (#509) — stable popup frame across panes.
 * REQ-911 (#510) — the pane strip is a legible segmented control.
 * REQ-912 (#511) — Plugins/Calendar gated to swarm-owned seats on every open
 * route (rail buttons AND window events), with an accessible reason.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PluginsPopup from '../PluginsPopup'
import AgentSidebar from '../AgentSidebar'
import { OPEN_PLUGINS_EVENT } from '../../lib/chromeOverlay'
import { OPEN_CALENDAR_EVENT } from '../AgentSidebar'
import { publishCurrentAgent, CURRENT_AGENT_STORAGE_KEY } from '../../lib/currentAgent'
import { publishCurrentChatScope } from '../../lib/chatScope'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

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

function renderRail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function readCss(selector: string): string {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { readFileSync } = require('node:fs') as typeof import('node:fs')
  const { join } = require('node:path') as typeof import('node:path')
  const src = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
  return src.split(selector)[1]?.split('}')[0] ?? ''
}

describe('REQ-910 (#509): plugins popup frame is pane-independent', () => {
  beforeEach(() => {
    localStorage.clear()
    publishCurrentChatScope('chat-codey')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline fixture')))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('the shell CSS declares a real height, not just a max-height', async () => {
    const block = readCss('.os-search-palette {')
    expect(block).toMatch(/height:\s*min\(38rem/)
    expect(block).not.toMatch(/max-height/)
  })

  it('the catalog variant no longer widens the shell', () => {
    const block = readCss('.os-search-palette--catalog {')
    expect(block).toMatch(/width:\s*min\(48rem/)
  })

  it('switching panes keeps one dialog class — the frame cannot move', async () => {
    renderPopup()
    const dialog = await screen.findByRole('dialog', { name: 'Plugins' })
    const initial = dialog.className
    expect(initial).not.toContain('--catalog')

    fireEvent.click(await screen.findByRole('tab', { name: 'Add tools' }))
    expect(screen.getByRole('dialog', { name: 'Plugins' }).className).toBe(initial)
    fireEvent.click(screen.getByRole('tab', { name: 'Add skills' }))
    expect(screen.getByRole('dialog', { name: 'Plugins' }).className).toBe(initial)
    // #516: the pane label renamed from "This chat" — the scope is the agent.
    fireEvent.click(screen.getByRole('tab', { name: 'This agent' }))
    expect(screen.getByRole('dialog', { name: 'Plugins' }).className).toBe(initial)
  })

  it('the catalog body renders inside the shared scroll region with the footer outside it', async () => {
    renderPopup()
    fireEvent.click(await screen.findByRole('tab', { name: 'Add tools' }))
    const body = await screen.findByTestId('os-plugins-catalog')
    expect(body).toHaveClass('os-search-palette__list')
    const dialog = screen.getByRole('dialog', { name: 'Plugins' })
    expect(within(body).queryByLabelText('Plugins actions')).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText('Plugins actions')).toBeInTheDocument()
  })
})

function renderPopup(open = true) {
  const onClose = vi.fn()
  return render(
    <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
      <PluginsPopup open={open} onClose={onClose} />
    </MemoryRouter>,
  )
}

describe('REQ-911 (#510): the pane strip is a legible tab control', () => {
  beforeEach(() => {
    localStorage.clear()
    publishCurrentChatScope('chat-codey')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline fixture')))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('os-plugins-panes is defined in CSS with separators and an active state', () => {
    const strip = readCss('.os-plugins-panes {')
    expect(strip).toMatch(/display:\s*flex/)
    expect(strip).toMatch(/border/)
    const item = readCss('.os-plugins-panes .tab {')
    expect(item).toMatch(/border-inline-start/)
    const active = readCss('.os-plugins-panes .tab-active {')
    expect(active).toMatch(/background/)
    const light = readCss('[data-theme="light"] .os-plugins-panes .tab-active {')
    expect(light).toMatch(/background/)
  })

  it('renders three real tabs whose aria-selected tracks the active pane', async () => {
    renderPopup()
    const tabs = await screen.findAllByRole('tab')
    // #516: the pane label renamed from "This chat" — the scope is the agent.
    expect(tabs.map((t) => t.textContent)).toEqual(['This agent', 'Add tools', 'Add skills'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(tabs[1])
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false')
  })
})

describe('REQ-912 (#511): Plugins/Calendar gated to swarm-owned seats', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    publishCurrentChatScope('chat-codey')
    vi.stubGlobal('fetch', mockFetch())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  async function openRail() {
    renderRail()
    await screen.findByRole('navigation', { name: 'Agent list' })
  }

  it('API seat: both entries enabled and both routes open their popup', async () => {
    publishCurrentAgent({ id: 'api_agent', kind: 'api' })
    await openRail()
    const plugins = screen.getByTestId('os-plugins-button')
    const calendar = screen.getByTestId('os-calendar-button')
    expect(plugins).not.toHaveAttribute('data-disabled')
    fireEvent.click(plugins)
    expect(screen.getByTestId('os-plugins-popup')).toBeInTheDocument()
    fireEvent.click(calendar)
    expect(screen.getByTestId('agent-calendar-overlay')).toBeInTheDocument()
  })

  it('CLI seat: buttons refuse, and the window-event routes are gated too', async () => {
    publishCurrentAgent({ id: 'cli_agent', kind: 'cli' })
    await openRail()
    const plugins = screen.getByTestId('os-plugins-button')
    expect(plugins).toHaveAttribute('data-disabled', 'true')
    expect(plugins).toHaveAttribute('aria-disabled', 'true')
    expect(plugins.getAttribute('title')).toContain('Currently only supported for OS API agents')

    fireEvent.click(plugins)
    expect(screen.queryByTestId('os-plugins-popup')).not.toBeInTheDocument()

    // The route a button-only fix would miss:
    window.dispatchEvent(new CustomEvent(OPEN_PLUGINS_EVENT))
    await waitFor(() => {
      expect(screen.queryByTestId('os-plugins-popup')).not.toBeInTheDocument()
    })
    window.dispatchEvent(new Event(OPEN_CALENDAR_EVENT))
    await waitFor(() => {
      expect(screen.queryByTestId('agent-calendar-overlay')).not.toBeInTheDocument()
    })
  })

  it('remote seat: gated the same way; blueprint seat: enabled (swarm-owned)', async () => {
    publishCurrentAgent({ id: 'remote:w1', kind: 'remote' })
    await openRail()
    expect(screen.getByTestId('os-plugins-button')).toHaveAttribute('data-disabled', 'true')

    publishCurrentAgent({ id: 'codey', kind: 'blueprint' })
    await waitFor(() => {
      expect(screen.getByTestId('os-plugins-button')).not.toHaveAttribute('data-disabled')
    })
  })

  it('unknown selection (no publish): enabled so a load state cannot lock the operator out', async () => {
    await openRail()
    expect(screen.getByTestId('os-plugins-button')).not.toHaveAttribute('data-disabled')
    expect(localStorage.getItem(CURRENT_AGENT_STORAGE_KEY)).toBeNull()
  })

  it('Teams is never gated, on a CLI seat', async () => {
    publishCurrentAgent({ id: 'cli_agent', kind: 'cli' })
    await openRail()
    const teams = screen.getByTestId('os-teams-button')
    expect(teams).not.toHaveAttribute('data-disabled')
    fireEvent.click(teams)
    expect(teams).toBeInTheDocument()
  })
})
