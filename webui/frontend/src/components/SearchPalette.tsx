import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  FileText,
  Link2,
  MessageSquare,
  Plug,
  Search,
  Settings,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react'
import {
  fetchBlueprints,
  fetchCliAgents,
  fetchHerdrAgents,
  fetchRemotes,
  fetchTeamRosters,
} from '../lib/api'
import { openChromeOverlay, type ChromeOverlay } from '../lib/chromeOverlay'
import { openSettingsSheet, SETTINGS_SEARCH_CONTENT, type SettingsSection } from './SettingsSheet'
import { openTechSupportModal } from './TechSupportModal'
import { agentMarkIndex, loadHiddenAgentIds, unhideAgentId } from '../lib/hiddenAgents'
import { railSeatAgents } from '../lib/railSeats'
import { agentLabel } from '../lib/supportAgent'
import { remoteHideId, remoteDisplayName } from '../lib/remotesCatalog'
import { parseTeamRosters, teamHideId } from '../lib/teamRosters'
import { dispatchToggleTheme } from '../lib/theme'
import { searchShortcutLabel } from '../lib/keybindingTips'
import AgentAvatar from './AgentAvatar'
import { OverlayFocusTrap } from './OverlayFocusTrap'

export const SEARCH_PALETTE_TABS = [
  'All',
  'Messages',
  'Agents',
  'Teams',
  'Files',
  'Links',
  'Routines',
  'Actions',
  'Settings',
] as const

export type SearchPaletteTab = (typeof SEARCH_PALETTE_TABS)[number]

export const OPEN_SEARCH_EVENT = 'swarm:open-search'

/**
 * #549: a hidden rail row the palette cannot derive from `/v1/blueprints/`.
 *
 * The rail badge counts **agents + teams + remotes**, assembled from blueprints,
 * rosters, remotes, cli and herdr feeds — but the palette's universe is
 * `railSeatAgents(blueprints)`, i.e. recipes only. So "Hidden Bots 3" could
 * open on an empty list whenever the hidden things were a team, a remote or a
 * CLI/herdr seat. The rail knows those rows, so it hands them over.
 */
export interface HiddenRailRow {
  /** The rail/pin id — a bare agent id, or `team:<id>` / `remote:<id>`. */
  id: string
  name: string
  description?: string
  href?: string
  avatarPath?: string | null
  tab?: 'Agents' | 'Teams'
}

export interface SearchPaletteOptions {
  filterHidden?: boolean
  tab?: SearchPaletteTab
  query?: string
  /**
   * #549: the **reconciled** hidden ids the rail badge counted (local storage
   * plus server prefs). The palette used to seed from localStorage alone, so
   * the count could exceed the list for an id hidden only on the server.
   */
  hiddenIds?: string[]
  /** #549: non-catalog hidden rows — teams, remotes, herdr and CLI seats. */
  hiddenRows?: HiddenRailRow[]
}

export function openSearchPalette(options?: SearchPaletteOptions): void {
  window.dispatchEvent(new CustomEvent(OPEN_SEARCH_EVENT, { detail: options }))
}

interface PaletteRow {
  id: string
  tab: Exclude<SearchPaletteTab, 'All'>
  name: string
  description: string
  keywords?: string[]
  href?: string
  overlay?: ChromeOverlay
  action?: () => void
  agentId?: string
  avatarPath?: string | null
}

export interface SearchPaletteProps {
  open: boolean
  onClose: () => void
  options?: SearchPaletteOptions
}

const SETTINGS_SECTION_NAMES: Record<SettingsSection, string> = {
  general: 'General',
  aesthetics: 'Aesthetics',
  hostname: 'Hostname',
  rail: 'Rail',
  providers: 'Providers',
  'cli-agents': 'CLI agents',
  'llm-profiles': 'LLM profiles',
  remotes: 'Remotes',
  sandboxes: 'Sandboxes',
  'backend-audit': 'Backend audit',
  mcp: 'MCP servers',
  plugins: 'Plugins',
  roles: 'Roles',
  blueprint: 'Blueprints',
  definition: 'Definition',
  'image-gen': 'Image gen',
  speech: 'Speech',
  retention: 'Retention',
  system: 'System',
}

function shortcutLabel(index: number): string {
  return `⌃${index + 1}`
}

export default function SearchPalette({ open, onClose, options }: SearchPaletteProps) {
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState<SearchPaletteTab>('All')
  const [hiddenOnly, setHiddenOnly] = useState(false)
  const [hiddenIds, setHiddenIds] = useState<string[]>(() => loadHiddenAgentIds())
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const navigate = useNavigate()

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    enabled: open,
    retry: 1,
  })
  // #677: the palette's universe is the whole rail, not just recipe seats —
  // the same feeds AgentSidebar reads, so CLI / remote / herdr / team seats
  // are searchable here too.
  const agents = railSeatAgents(blueprintsQuery.data?.data ?? [])
  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    enabled: open,
    retry: 1,
  })
  const remotesQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    enabled: open,
    retry: 1,
  })
  const herdrQuery = useQuery({
    queryKey: ['herdr-agents'],
    queryFn: fetchHerdrAgents,
    enabled: open,
    retry: 1,
  })
  const rostersQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
    enabled: open,
    retry: 1,
  })
  const cliAgents = cliQuery.data?.rail ?? []
  const remoteConnections = remotesQuery.data?.data ?? []
  const herdrAgents = herdrQuery.data?.data ?? []
  const teams = parseTeamRosters(rostersQuery.data ?? [])

  const rows = useMemo<PaletteRow[]>(() => {
    const seen = new Set<string>()
    const botRows: PaletteRow[] = []
    // Recipe / blueprint seats.
    for (const agent of agents) {
      seen.add(agent.id)
      botRows.push({
        id: `bot-${agent.id}`,
        tab: 'Agents',
        name: agentLabel(agent),
        description: agent.description || `${agentLabel(agent)} agent`,
        href: `/chat?blueprint=${encodeURIComponent(agent.id)}`,
        agentId: agent.id,
        avatarPath: agent.avatar_path,
      })
    }
    // Named CLI / API seats from /v1/cli-agents/ (rail list).
    for (const seat of cliAgents) {
      if (seen.has(seat.id)) continue
      seen.add(seat.id)
      botRows.push({
        id: `bot-${seat.id}`,
        tab: 'Agents',
        name: seat.name || seat.id,
        description: seat.description || `${seat.cli} CLI agent`,
        href: `/chat?blueprint=${encodeURIComponent(seat.id)}`,
        agentId: seat.id,
        avatarPath: null,
      })
    }
    // Configured remotes — each is a chat target of its own.
    for (const remote of remoteConnections) {
      const rid = remote.id
      if (!rid || seen.has(remoteHideId(rid))) continue
      seen.add(remoteHideId(rid))
      botRows.push({
        id: `bot-${remoteHideId(rid)}`,
        tab: 'Agents',
        name: remoteDisplayName(remote),
        description: remote.kind ? `${remote.kind} remote` : 'Remote agent host',
        href: `/chat?remote=${encodeURIComponent(rid)}`,
        agentId: remoteHideId(rid),
        avatarPath: null,
      })
    }
    // Herdr seats.
    for (const seat of herdrAgents) {
      const hid = `herdr:${seat.name}`
      if (!seat.name || seen.has(hid)) continue
      seen.add(hid)
      botRows.push({
        id: `bot-${hid}`,
        tab: 'Agents',
        name: seat.name,
        description: seat.remote ? `Herdr · ${seat.remote}` : 'Herdr · localhost',
        href: `/chat?remote=herdr&session=${encodeURIComponent(seat.name)}`,
        agentId: hid,
        avatarPath: null,
      })
    }
    // Teams — their own section so compositions are reachable from search.
    const teamRows: PaletteRow[] = []
    for (const team of teams) {
      teamRows.push({
        id: `team-row-${team.id}`,
        tab: 'Teams',
        name: team.name || team.id,
        description:
          team.description ||
          `Team · ${team.members?.length ?? 0} member${(team.members?.length ?? 0) === 1 ? '' : 's'}`,
        href: `/chat?team=${encodeURIComponent(team.id)}`,
        agentId: teamHideId(team.id),
        avatarPath: null,
      })
    }
    const actionRows: PaletteRow[] = [
      {
        id: 'action-tech-support',
        tab: 'Actions',
        name: 'Show Tech Support',
        description: 'Open a sanitized diagnostics dump for troubleshooting',
        keywords: ['tech', 'support', 'diagnostics', 'logs', 'debug', 'troubleshooting'],
        action: () => openTechSupportModal(),
      },
      {
        id: 'action-theme',
        tab: 'Actions',
        name: 'Toggle theme',
        description: 'Switch light and dark chrome',
        action: () => dispatchToggleTheme(),
      },
      {
        id: 'action-blueprints',
        tab: 'Actions',
        name: 'Blueprints',
        description: 'Open the blueprints sheet over chat',
        overlay: 'blueprints',
      },
      {
        id: 'action-teams',
        tab: 'Actions',
        name: 'Teams',
        description: 'Open the teams sheet over chat',
        overlay: 'teams',
      },
      // #550 / #182: `Compose team` was moved to the rail footer (the `Teams`
      // button, above Plugins). Listing it here as well made the palette look
      // like the owner of the action, which is why it read as a duplicate.
      {
        id: 'action-settings',
        tab: 'Actions',
        name: 'Settings',
        description: 'Open settings over chat',
        overlay: 'settings',
      },
      {
        id: 'action-hidden',
        tab: 'Actions',
        // #826: same copy the rail row uses — the legacy "Hidden Bots" was
        // the one place the relabel missed (visual sweep finding).
        name: 'Hidden Agents',
        description: 'Unhide agents without leaving chat',
        action: () => {
          setHiddenOnly(true)
          setTab('Agents')
        },
      },
      {
        id: 'action-computer',
        tab: 'Actions',
        name: 'Computer control',
        description: 'Browser control pane over chat',
        overlay: 'computer-control',
      },
      {
        id: 'action-llm',
        tab: 'Actions',
        name: 'Show LLM profiles',
        description: 'Open the connected models pane',
        action: () => openSettingsSheet({ section: 'llm-profiles' }),
      },
      {
        id: 'action-rail-settings',
        tab: 'Actions',
        name: 'Rail settings',
        description: 'Open rail preferences in Settings',
        action: () => openSettingsSheet({ section: 'rail' }),
      },
      {
        id: 'action-system-settings',
        tab: 'Actions',
        name: 'System settings',
        description: 'Open system diagnostics in Settings',
        action: () => openSettingsSheet({ section: 'system' }),
      },
      {
        id: 'action-mcp-settings',
        tab: 'Actions',
        name: 'MCP servers',
        description: 'Edit mcpServers in Settings',
        action: () => openSettingsSheet({ section: 'mcp' }),
      },
      {
        id: 'action-cli-agents-settings',
        tab: 'Actions',
        name: 'CLI agents',
        description: 'Edit cli_agents in Settings',
        action: () => openSettingsSheet({ section: 'cli-agents' }),
      },
      {
        id: 'action-speech-settings',
        tab: 'Actions',
        name: 'Speech settings',
        description: 'Microphone STT and read-aloud TTS',
        action: () => openSettingsSheet({ section: 'speech' }),
      },
    ]
    return [...botRows, ...teamRows, ...actionRows]
  }, [agents, cliAgents, remoteConnections, herdrAgents, teams])

  /**
   * #549: rail-supplied hidden rows. Merged in only for the hidden view — normal
   * search keeps its existing recipe-only universe, because widening that is a
   * separate change to what search *means*.
   */
  const extraHiddenRows = useMemo<PaletteRow[]>(() => {
    const rows: HiddenRailRow[] = options?.hiddenRows ?? []
    return rows.map((row) => ({
      id: `hidden-rail-${row.id}`,
      tab: row.tab ?? 'Agents',
      name: row.name,
      description: row.description || 'Hidden from the rail',
      href: row.href,
      agentId: row.id,
      avatarPath: row.avatarPath ?? null,
    }))
  }, [options?.hiddenRows])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    // #908: dynamically derive matching Settings rows from SETTINGS_SEARCH_CONTENT
    const settingsRows: PaletteRow[] = []
    const seenSections = new Set<string>()
    for (const [sectionKey, keywords] of Object.entries(SETTINGS_SEARCH_CONTENT)) {
      const section = sectionKey as SettingsSection
      const sectionLabel = SETTINGS_SECTION_NAMES[section] ?? section
      if (!q) {
        settingsRows.push({
          id: `settings-${section}-0`,
          tab: 'Settings',
          name: sectionLabel,
          description: `Open the ${section} pane in Settings`,
          action: () => openSettingsSheet({ section }),
        })
        continue
      }
      const normQ = q.replace(/[\s_-]+/g, '')
      const matchedKw = keywords.find((k) => {
        const lk = k.toLowerCase()
        return lk.includes(q) || lk.replace(/[\s_-]+/g, '').includes(normQ)
      })
      if (matchedKw && !seenSections.has(section)) {
        seenSections.add(section)
        settingsRows.push({
          id: `settings-${section}-0`,
          tab: 'Settings',
          name: matchedKw.toLowerCase() === section.toLowerCase() ? sectionLabel : `${sectionLabel}: ${matchedKw}`,
          description: `Open the ${section} pane in Settings`,
          keywords: [matchedKw, sectionLabel, section],
          action: () => openSettingsSheet({ section }),
        })
      }
    }

    const allRowsWithSettings = [...rows, ...settingsRows]
    // #549: the hidden view lists the same universe the badge counted.
    const universe = hiddenOnly ? [...extraHiddenRows, ...allRowsWithSettings] : allRowsWithSettings
    // Rail rows win a duplicate id: they carry the live href/avatar the
    // blueprints feed may not have.
    const seen = new Set<string>()
    return universe.filter((row) => {
      if (hiddenOnly) {
        if (row.tab !== 'Agents') return false
        if (!row.agentId || !hiddenIds.includes(row.agentId)) return false
        if (seen.has(row.agentId)) return false
        seen.add(row.agentId)
      } else {
        if (tab !== 'All' && row.tab !== tab) return false
      }
      if (!q) {
        if (tab === 'All' && row.tab === 'Settings') return false
        return true
      }
      if (row.tab === 'Settings') return true
      return (
        row.name.toLowerCase().includes(q) ||
        row.description.toLowerCase().includes(q) ||
        Boolean(row.keywords?.some((k) => k.toLowerCase().includes(q)))
      )
    })
  }, [query, rows, extraHiddenRows, tab, hiddenOnly, hiddenIds])

  useEffect(() => {
    setActiveIdx(0)
  }, [query, tab, open, hiddenOnly])

  useEffect(() => {
    if (!open) return
    // #549: prefer the rail's reconciled list when it supplied one, so the
    // count and the list read from one source instead of two.
    const ids = options?.hiddenIds ?? loadHiddenAgentIds()
    setHiddenIds(ids)
    if (options?.filterHidden) {
      setHiddenOnly(true)
      setTab('Agents')
    } else {
      setHiddenOnly(false)
      setTab(options?.tab || 'All')
    }
    setQuery(options?.query || '')
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open, options])

  useEffect(() => {
    const handleOpen = (e: Event) => {
      const detail = (e as CustomEvent<SearchPaletteOptions>).detail
      if (detail?.filterHidden) {
        setHiddenOnly(true)
        setTab('Agents')
      } else if (detail?.tab) {
        setTab(detail.tab)
      }
      if (detail?.query !== undefined) setQuery(detail.query)
      if (detail?.hiddenIds) setHiddenIds(detail.hiddenIds)
    }
    window.addEventListener(OPEN_SEARCH_EVENT, handleOpen)
    return () => window.removeEventListener(OPEN_SEARCH_EVENT, handleOpen)
  }, [])

  const choose = useCallback(
    (row: PaletteRow | undefined) => {
      if (!row) return
      onClose()
      if (row.action) {
        row.action()
        return
      }
      if (row.overlay) {
        openChromeOverlay(row.overlay)
        return
      }
      if (!row.href) return
      if (row.href.startsWith('/chat')) navigate(row.href)
      else window.location.assign(row.href)
    },
    [navigate, onClose],
  )

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      // #1088: Alt+1..9 are gone (native tab-switch collision). Alt+Arrow
      // rail navigation is handled by the sidebar's own listener; the palette
      // keeps plain Arrow keys for its own list and must not swallow them.
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setActiveIdx((i) => Math.min(i + 1, Math.max(0, visible.length - 1)))
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setActiveIdx((i) => Math.max(i - 1, 0))
        return
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        choose(visible[activeIdx])
        return
      }
      if ((event.ctrlKey || event.metaKey) && /^[1-9]$/.test(event.key)) {
        event.preventDefault()
        choose(visible[Number(event.key) - 1])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, choose, visible, activeIdx])

  if (!open) return null

  return (
    <OverlayFocusTrap onClose={onClose} initialFocus={() => inputRef.current}>
    <div
      className="os-search-overlay os-search-overlay--centered"
      data-testid="os-search-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        data-testid="os-search-palette"
        data-centered="true"
        className="os-search-palette os-search-palette--centered os-search-palette--large"
      >
        <div className="os-search-palette__field">
          <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search"
            aria-label="Search"
            aria-controls="os-search-results"
            aria-activedescendant={
              visible[activeIdx] ? `os-search-row-${visible[activeIdx].id}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            autoComplete="off"
            className="os-search-palette__input"
          />
          {!query.trim() ? (
            <kbd className="os-search-palette__kbd kbd kbd-xs">{searchShortcutLabel()}</kbd>
          ) : null}
        </div>

        <div className="os-search-palette__tabs" role="tablist" aria-label="Search categories">
          {SEARCH_PALETTE_TABS.map((name) => {
            const selected = tab === name
            return (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={selected}
                className={selected ? 'os-search-tab os-search-tab--active' : 'os-search-tab'}
                onClick={() => setTab(name)}
              >
                {name}
              </button>
            )
          })}
        </div>

        {hiddenOnly && (
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 bg-base-200/50 border-b border-base-300 text-xs text-base-content/70"
            data-testid="hidden-filter-indicator"
          >
            <span className="font-semibold text-primary">Filter:</span>
            <span className="inline-flex items-center gap-1 rounded bg-base-300 px-2 py-0.5 font-medium text-base-content">
              Hidden only
              <button
                type="button"
                className="cursor-pointer hover:opacity-75 ml-0.5"
                aria-label="Clear hidden filter"
                onClick={() => setHiddenOnly(false)}
              >
                ×
              </button>
            </span>
          </div>
        )}

        <ul
          id="os-search-results"
          role="listbox"
          aria-label="Search results"
          className="os-search-palette__list"
        >
          {visible.length === 0 ? (
            <li
              className="os-search-empty"
              data-testid={hiddenOnly ? 'search-empty-hidden' : undefined}
            >
              {hiddenOnly ? 'No hidden agents found' : 'No results'}
            </li>
          ) : (
            visible.map((row, idx) => (
              <li
                key={row.id}
                id={`os-search-row-${row.id}`}
                role="option"
                aria-selected={idx === activeIdx}
                className={
                  idx === activeIdx ? 'os-search-row os-search-row--active' : 'os-search-row'
                }
                onMouseMove={() => setActiveIdx(idx)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(row)}
              >
                <RowIcon
                  tab={row.tab}
                  id={row.id}
                  agentId={row.agentId}
                  avatarPath={row.avatarPath}
                  name={row.name}
                />
                <span className="min-w-0 flex-1">
                  <span className="os-search-row__name">{row.name}</span>
                  <span className="os-search-row__desc">{row.description}</span>
                </span>
                {row.agentId && hiddenIds.includes(row.agentId) && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs text-xs z-10 mr-1"
                    data-testid={`unhide-${row.agentId}`}
                    aria-label={`Unhide ${row.name}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      // #507: unhideAgentId dispatches HIDDEN_AGENTS_CHANGED_EVENT
                      // (a same-tab notification); faking a DOM `storage` event
                      // never worked in real browsers — it only fires cross-tab.
                      const next = unhideAgentId(row.agentId!, hiddenIds)
                      setHiddenIds(next)
                    }}
                  >
                    Unhide
                  </button>
                )}
                {idx < 9 && <kbd className="os-search-shortcut">{shortcutLabel(idx)}</kbd>}
              </li>
            ))
          )}
        </ul>

        <div className="os-search-palette__footer" aria-label="Keyboard tips">
          <span className="os-search-tip"><kbd className="kbd kbd-xs">↑↓</kbd> Navigate</span>
          <span className="os-search-tip"><kbd className="kbd kbd-xs">↵</kbd> Select</span>
          <span className="os-search-tip"><kbd className="kbd kbd-xs">Esc</kbd> Close</span>
        </div>
      </div>
    </div>
    </OverlayFocusTrap>
  )
}

function RowIcon({
  tab,
  id,
  agentId,
  avatarPath,
  name,
}: {
  tab: PaletteRow['tab']
  id: string
  agentId?: string
  avatarPath?: string | null
  name?: string
}) {
  if (tab === 'Agents') {
    const botId = agentId || id.replace(/^bot-/, '')
    const mark = agentMarkIndex(botId)
    return (
      <span
        className="os-search-row__icon os-search-row__icon--avatar flex items-center justify-center shrink-0 !bg-transparent rounded-full overflow-hidden"
        data-mark={String(mark)}
        aria-hidden="true"
      >
        <AgentAvatar
          src={avatarPath}
          agentId={botId}
          alt={name || botId}
          size="sm"
        />
      </span>
    )
  }
  const Icon =
    tab === 'Messages'
      ? MessageSquare
      : tab === 'Teams'
        ? Users
        : tab === 'Files'
          ? FileText
          : tab === 'Links'
            ? Link2
            : tab === 'Routines'
              ? Workflow
              : tab === 'Actions'
                ? Sparkles
                : tab === 'Settings'
                  ? Settings
                  : Plug
  return (
    <span className="os-search-row__icon" aria-hidden="true">
      <Icon className="h-4 w-4" />
    </span>
  )
}
