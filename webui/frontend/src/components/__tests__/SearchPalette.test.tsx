import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import SearchPalette, { SEARCH_PALETTE_TABS } from '../SearchPalette'
import { THEME_TOGGLE_EVENT } from '../../lib/theme'
import { OPEN_TECH_SUPPORT_EVENT } from '../TechSupportModal'
import { OPEN_SETTINGS_EVENT, type OpenSettingsDetail } from '../SettingsSheet'

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
]

function renderPalette(open = true, onClose = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <SearchPalette open={open} onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('SearchPalette', () => {
  beforeEach(() => {
    // #677: URL-aware stub — the palette reads the same feeds the rail does
    // (blueprints, cli-agents rail, remotes, herdr, team rosters), and the
    // coalesced remotes fetch hits `/v1/remotes/` (plural).
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/herdr')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/team-rosters/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ clis: [], rail: [] }),
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
  })

  it('opens as an overlay with Search placeholder, tab row, and keyboard focus', async () => {
    const { onClose } = renderPalette()

    const dialog = screen.getByRole('dialog', { name: 'Search' })
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveClass('os-search-palette--centered')
    expect(dialog).toHaveClass('os-search-palette--large')
    const overlay = screen.getByTestId('os-search-overlay')
    expect(overlay).toHaveClass('os-search-overlay--centered')
    const input = screen.getByRole('combobox', { name: 'Search' })
    expect(input).toHaveAttribute('placeholder', 'Search')
    expect(document.querySelector('.os-search-palette__kbd')).toBeTruthy()
    fireEvent.change(input, { target: { value: 'codey' } })
    expect(document.querySelector('.os-search-palette__kbd')).toBeNull()
    fireEvent.change(input, { target: { value: '' } })
    expect(document.querySelector('.os-search-palette__kbd')).toBeTruthy()

    for (const tab of SEARCH_PALETTE_TABS) {
      expect(screen.getByRole('tab', { name: tab })).toBeInTheDocument()
    }
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true')

    const first = await screen.findByRole('option', { name: /^Support/i })
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(first.textContent).toMatch(/⌃1/)

    fireEvent.keyDown(window, { key: 'ArrowDown' })
    await waitFor(() => {
      expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    })

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('shows an empty state on tabs without rows', () => {
    renderPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Messages' }))
    expect(screen.getByText('No results')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Messages' })).toHaveAttribute('aria-selected', 'true')
  })

  it('Agents tab lists Support + rail seats and Enter chooses a /chat href (REQ-17 / #322)', async () => {
    const { onClose } = renderPalette()
    expect(await screen.findByRole('option', { name: /Codey/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Agents' }))
    expect(screen.getByRole('tab', { name: 'Agents' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('option', { name: /Support/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Codey/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Toggle theme/ })).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onClose).toHaveBeenCalled()
  })

  it('REQ-170: Search Bots omit catalog recipes that are not rail seats', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 'support',
              object: 'blueprint',
              name: 'Support',
              description: 'Onboarding',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
              rail: true,
              role: 'support',
            },
            {
              id: 'poets',
              object: 'blueprint',
              name: 'Poets',
              description: 'Poet swarm',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
            },
            {
              id: 'chucks_angels',
              object: 'blueprint',
              name: "Chuck's Angels",
              description: 'Demo',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
            },
            {
              id: 'django_chat',
              object: 'blueprint',
              name: 'Django Chat',
              description: 'Retired leftover',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
            },
            {
              id: 'moa',
              object: 'blueprint',
              name: 'mixture_of_agents',
              description: 'MoA',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
            },
            {
              id: 'cli_fusion',
              object: 'blueprint',
              name: 'cli_fusion',
              description: 'CLI fusion',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
            },
            {
              id: 'codey',
              object: 'blueprint',
              name: 'Codey',
              description: 'Code assistant',
              abbreviation: null,
              required_mcp_servers: [],
              tags: [],
              installed: true,
              compiled: true,
            },
          ],
        }),
      } as Response),
    )
    renderPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Agents' }))
    expect(await screen.findByRole('option', { name: /Support/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Poets/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Chuck/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Django Chat/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /mixture_of_agents/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /cli_fusion/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Codey/ })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Actions' })).toBeInTheDocument()
  })

  it('#568: the dialog resolves to a concrete height, and the list absorbs the slack', async () => {
    // #568 was fixed by REQ-910 (#509) — the shell took a real `height` instead
    // of only a `max-height`, so it is no longer content-driven and cannot jump
    // as a tab changes its row count. This guards the mechanism, because the
    // symptom (a dialog that resizes under the pointer) comes straight back if
    // either half is dropped. Assertable without a browser: a fixed height on
    // the shell, and a flex child with `min-height: 0` inside it.
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

    const shell = css.split('.os-search-palette {')[1]?.split('}')[0] ?? ''
    // A concrete height, not a ceiling — a `max-height` alone is what made the
    // dialog content-driven in the first place.
    expect(shell).toMatch(/\bheight:/)
    expect(shell).toMatch(/flex-direction:\s*column/)

    const list = css.split('.os-search-palette__list {')[1]?.split('}')[0] ?? ''
    expect(list).toMatch(/flex:\s*1 1 auto/)
    // Without this the flex child refuses to shrink and overflows the shell.
    expect(list).toMatch(/min-height:\s*0/)
    expect(list).toMatch(/overflow-y:\s*auto/)
    // The list must not reintroduce its own ceiling — that was the other half of
    // the old content-driven height (`max-height: min(32rem, 60vh)`).
    expect(list).not.toMatch(/max-height:\s*min\(32rem/)
  })

  it('Actions tab lists theme + Django operator destinations, not live remotes (REQ-17 / #322)', () => {
    const toggled: string[] = []
    const onToggle = () => toggled.push('theme')
    window.addEventListener('swarm:toggle-theme', onToggle)
    const { onClose } = renderPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    expect(screen.getByRole('option', { name: /Toggle theme/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Blueprints/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Teams/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /^Settings/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Rail settings/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /System settings/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Show LLM profiles/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Hermes/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Rakazo/ })).not.toBeInTheDocument()
    // #550 / #182: Compose team belongs to the rail footer's Teams button.
    // Listing it here too made the palette read as a second owner.
    expect(screen.queryByRole('option', { name: /Compose team/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('option', { name: /Toggle theme/ }))
    expect(onClose).toHaveBeenCalled()
    expect(toggled).toEqual(['theme'])
    window.removeEventListener('swarm:toggle-theme', onToggle)
  })

  it('filters All-tab rows by query without hiding the overlay chrome', async () => {
    renderPalette()
    const input = screen.getByRole('combobox', { name: 'Search' })
    fireEvent.change(input, { target: { value: 'codey' } })
    expect(await screen.findByRole('option', { name: /Codey/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Support/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Toggle theme/ })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument()
  })
})

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="palette-loc">{`${loc.pathname}${loc.search}`}</div>
}

function renderRoutedPalette() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const onClose = vi.fn()
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/']}>
          <SearchPalette open onClose={onClose} />
          <LocationProbe />
          <Routes>
            <Route path="/" element={<div>home</div>} />
            <Route path="/chat" element={<div>chat</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('SearchPalette choose + actions (REQ-5c #322)', () => {
  beforeEach(() => {
    // #677: URL-aware stub — strict empty payloads for the rail feeds the
    // palette now reads, so only /v1/blueprints/ returns the fixture (no
    // duplicate rows from a leaky fallback).
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes/') || url.includes('/herdr') || url.includes('/v1/team-rosters/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ clis: [], rail: [] }),
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
    vi.restoreAllMocks()
  })

  it('navigates a bot row to /chat?blueprint= and closes the overlay', async () => {
    const { onClose } = renderRoutedPalette()
    const codey = await screen.findByRole('option', { name: /Codey/i })
    fireEvent.click(codey)
    expect(onClose).toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/chat?blueprint=codey')
  })

  it('chooses the first visible row with Ctrl+1', async () => {
    const { onClose } = renderRoutedPalette()
    await screen.findByRole('option', { name: /^Support/i })
    fireEvent.keyDown(window, { key: '1', ctrlKey: true })
    expect(onClose).toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/chat?blueprint=support')
  })

  it('chooses the first visible row with Cmd+1 (metaKey)', async () => {
    const { onClose } = renderRoutedPalette()
    await screen.findByRole('option', { name: /^Support/i })
    fireEvent.keyDown(window, { key: '1', metaKey: true })
    expect(onClose).toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/chat?blueprint=support')
  })

  it('closes the palette on Alt+1-9 rail hotkey without preventing default', async () => {
    const { onClose } = renderRoutedPalette()
    await screen.findByRole('option', { name: /^Support/i })
    const event = new KeyboardEvent('keydown', {
      key: '2',
      altKey: true,
      bubbles: true,
      cancelable: true,
    })
    const defaultPreventedSpy = vi.spyOn(event, 'preventDefault')
    window.dispatchEvent(event)
    expect(onClose).toHaveBeenCalled()
    expect(defaultPreventedSpy).not.toHaveBeenCalled()
  })

  it('filters bots by query and Enter chooses the highlighted row', async () => {
    const { onClose } = renderRoutedPalette()
    await screen.findByRole('option', { name: /Codey/i })
    fireEvent.change(screen.getByRole('combobox', { name: 'Search' }), {
      target: { value: 'codey' },
    })
    await waitFor(() => {
      expect(screen.queryByRole('option', { name: /Support/i })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('option', { name: /Codey/i })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onClose).toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/chat?blueprint=codey')
  })

  it('Actions → Toggle theme dispatches swarm:toggle-theme without leaving chat', async () => {
    const toggled = vi.fn()
    window.addEventListener(THEME_TOGGLE_EVENT, toggled)
    const { onClose } = renderRoutedPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('option', { name: /Toggle theme/i }))
    expect(onClose).toHaveBeenCalled()
    expect(toggled).toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/')
    window.removeEventListener(THEME_TOGGLE_EVENT, toggled)
  })

  it('Actions → Show LLM profiles opens Settings on the profiles pane', async () => {
    const opened: Array<{ section?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent<{ section?: string }>).detail ?? {})
    }
    window.addEventListener('swarm:open-settings', onOpen)
    const { onClose } = renderRoutedPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('option', { name: /Show LLM profiles/i }))
    window.removeEventListener('swarm:open-settings', onOpen)
    expect(onClose).toHaveBeenCalled()
    expect(opened).toEqual([{ section: 'llm-profiles' }])
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/')
  })

  it('Actions → Rail settings opens Settings on the rail pane (REQ-188C-1)', async () => {
    const opened: Array<{ section?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent<{ section?: string }>).detail ?? {})
    }
    window.addEventListener('swarm:open-settings', onOpen)
    const { onClose } = renderRoutedPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('option', { name: /Rail settings/i }))
    window.removeEventListener('swarm:open-settings', onOpen)
    expect(onClose).toHaveBeenCalled()
    expect(opened).toEqual([{ section: 'rail' }])
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/')
  })

  it('Actions → Speech settings opens Settings on the speech pane (REQ-77)', async () => {
    const opened: Array<{ section?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent<{ section?: string }>).detail ?? {})
    }
    window.addEventListener('swarm:open-settings', onOpen)
    const { onClose } = renderRoutedPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('option', { name: /Speech settings/i }))
    window.removeEventListener('swarm:open-settings', onOpen)
    expect(onClose).toHaveBeenCalled()
    expect(opened).toEqual([{ section: 'speech' }])
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/')
  })

  it('Actions → System settings opens Settings on the system pane (REQ-188C-1)', async () => {
    const opened: Array<{ section?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent<{ section?: string }>).detail ?? {})
    }
    window.addEventListener('swarm:open-settings', onOpen)
    const { onClose } = renderRoutedPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('option', { name: /System settings/i }))
    window.removeEventListener('swarm:open-settings', onOpen)
    expect(onClose).toHaveBeenCalled()
    expect(opened).toEqual([{ section: 'system' }])
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/')
  })

  it('Actions Blueprints stays on chat (overlay, not a Django eject)', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    const { onClose } = renderRoutedPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('option', { name: /^Blueprints/i }))
    expect(onClose).toHaveBeenCalled()
    expect(assign).not.toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/')
  })

  it('renders real agent avatars in search results instead of default bot icon (REQ-199)', async () => {
    renderPalette()
    const codeyRow = await screen.findByRole('option', { name: /Codey/i })
    expect(codeyRow).toBeInTheDocument()

    const avatarSlot = codeyRow.querySelector('.os-search-row__icon--avatar')
    expect(avatarSlot).toBeInTheDocument()

    // Real avatar component is rendered inside (e.g. data-agent-avatar)
    const avatar = avatarSlot?.querySelector('[data-agent-avatar]')
    expect(avatar).toBeInTheDocument()

    // No generic Bot lucide icon inside the bot avatar slot
    expect(avatarSlot?.querySelector('.lucide-bot')).toBeNull()
  })
})

// #677 — the palette's universe is the whole rail: relabel Bots → Agents,
// list every seat kind (recipes, CLI rail, remotes, herdr), and give teams
// their own tab so compositions are reachable from search.
describe('#677 search covers every seat kind', () => {
  const cliSeat = {
    id: 'pixi-helper',
    object: 'cli.agent' as const,
    name: 'Pixi Helper',
    cli: 'qwen',
    kind: 'cli' as const,
    description: 'Named qwen CLI seat',
    installed: true,
  }
  const remoteSeat = { id: 'trueforge', kind: 'trueforge', title: 'TrueForge GTX' }
  const herdrSeat = {
    id: 7,
    object: 'herdr.agent' as const,
    kind: 'herdr' as const,
    name: 'pane-one',
    remote: 'demo-host',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  }
  const teamRoster = {
    object: 'team_roster' as const,
    id: 'crew',
    name: 'Crew',
    description: 'Demo squad',
    members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder', source: 'catalog' }],
  }

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes/')) {
          return { ok: true, status: 200, json: async () => ({ object: 'list', data: [remoteSeat] }) } as Response
        }
        if (url.includes('/herdr')) {
          return { ok: true, status: 200, json: async () => ({ object: 'list', data: [herdrSeat] }) } as Response
        }
        if (url.includes('/v1/team-rosters/')) {
          return { ok: true, status: 200, json: async () => ({ object: 'list', data: [teamRoster] }) } as Response
        }
        if (url.includes('/v1/cli-agents/')) {
          return { ok: true, status: 200, json: async () => ({ clis: ['qwen'], rail: [cliSeat] }) } as Response
        }
        return { ok: true, status: 200, json: async () => ({ object: 'list', data: blueprints }) } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renames the Bots tab to Agents', async () => {
    renderPalette()
    expect(screen.queryByRole('tab', { name: 'Bots' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Agents' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Teams' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Groups' })).not.toBeInTheDocument()
  })

  it('Agents tab lists recipe, CLI, remote, and herdr seats', async () => {
    renderPalette()
    fireEvent.click(await screen.findByRole('tab', { name: 'Agents' }))
    expect(await screen.findByRole('option', { name: /Codey/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Pixi Helper/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /TrueForge GTX/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /pane-one/ })).toBeInTheDocument()
  })

  it('Teams tab lists team compositions and navigates to the team chat', async () => {
    const { onClose } = renderRoutedPalette()
    fireEvent.click(await screen.findByRole('tab', { name: 'Teams' }))
    const crew = await screen.findByRole('option', { name: /Crew/ })
    fireEvent.click(crew)
    expect(onClose).toHaveBeenCalled()
    expect(screen.getByTestId('palette-loc')).toHaveTextContent('/chat?team=crew')
  })
})

describe('SearchPalette Tech Support and Settings (#906, #908)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
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
    vi.restoreAllMocks()
  })

  it('#906: Show Tech Support action row is listed in Actions tab and opens modal', async () => {
    let opened = false
    const onOpen = () => {
      opened = true
    }
    window.addEventListener(OPEN_TECH_SUPPORT_EVENT, onOpen)
    const { onClose } = renderPalette()

    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))
    const actionRow = screen.getByRole('option', { name: /Show Tech Support/i })
    expect(actionRow).toBeInTheDocument()

    fireEvent.click(actionRow)
    expect(opened).toBe(true)
    expect(onClose).toHaveBeenCalled()
    window.removeEventListener(OPEN_TECH_SUPPORT_EVENT, onOpen)
  })

  it('#906: Show Tech Support action row matches tech, support, diagnostics, logs, debug, troubleshooting keywords', async () => {
    const keywords = ['tech', 'diagnostics', 'logs', 'debug', 'troubleshooting']
    for (const kw of keywords) {
      const { unmount } = renderPalette()
      const input = screen.getByRole('combobox', { name: 'Search' })
      fireEvent.change(input, { target: { value: kw } })
      expect(screen.getByRole('option', { name: /Show Tech Support/i })).toBeInTheDocument()
      unmount()
    }
  })

  it('#906 / #908: Show Tech Support action row appears above Settings rows when query matches both', async () => {
    renderPalette()
    const input = screen.getByRole('combobox', { name: 'Search' })
    fireEvent.change(input, { target: { value: 'diagnostics' } })

    const options = screen.getAllByRole('option')
    const techSupportIdx = options.findIndex((opt) => opt.id === 'os-search-row-action-tech-support')
    const settingsIdx = options.findIndex((opt) => opt.id.startsWith('os-search-row-settings-'))

    expect(techSupportIdx).toBeGreaterThanOrEqual(0)
    expect(settingsIdx).toBeGreaterThan(techSupportIdx)
  })

  it('#908: Settings tab lists all settings sections when selected', async () => {
    renderPalette()
    fireEvent.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveAttribute('aria-selected', 'true')

    expect(screen.getByRole('option', { name: /General/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Aesthetics/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Speech/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /MCP servers/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /System/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Remotes/i })).toBeInTheDocument()
  })

  it('#908: surfaces settings sections matching keywords and omits unrelated queries', async () => {
    const { unmount: u1 } = renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Search' }), { target: { value: 'theme' } })
    expect(screen.getByRole('option', { name: /^Aesthetics:\s*theme/i })).toBeInTheDocument()
    u1()

    const { unmount: u2 } = renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Search' }), { target: { value: 'mcpServers' } })
    expect(screen.getByRole('option', { name: /^MCP servers:\s*mcpServers/i })).toBeInTheDocument()
    u2()

    const { unmount: u3 } = renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Search' }), { target: { value: 'read-aloud' } })
    expect(screen.getByRole('option', { name: /^Speech:\s*read-aloud/i })).toBeInTheDocument()
    u3()

    const { unmount: u4 } = renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Search' }), { target: { value: 'zebra' } })
    const allOptions = screen.queryAllByRole('option')
    const settingsOptions = allOptions.filter((opt) => opt.id.startsWith('os-search-row-settings-'))
    expect(settingsOptions).toHaveLength(0)
    u4()
  })

  it('#908: selecting a Settings row dispatches openSettingsSheet for that section', async () => {
    let openedDetail: OpenSettingsDetail | null = null
    const onOpen = (e: Event) => {
      openedDetail = (e as CustomEvent<OpenSettingsDetail>).detail
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen)
    const { onClose } = renderPalette()

    fireEvent.change(screen.getByRole('combobox', { name: 'Search' }), { target: { value: 'read-aloud' } })
    const speechOption = screen.getByRole('option', { name: /^Speech:\s*read-aloud/i })
    fireEvent.click(speechOption)

    expect(openedDetail).toEqual({ section: 'speech' })
    expect(onClose).toHaveBeenCalled()
    window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen)
  })
})

