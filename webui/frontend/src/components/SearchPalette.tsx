import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Bot,
  FileText,
  Link2,
  MessageSquare,
  Plug,
  Search,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react'
import { fetchBlueprints } from '../lib/api'
import { openChromeOverlay, type ChromeOverlay } from '../lib/chromeOverlay'
import { openSettingsSheet } from './SettingsSheet'
import { agentMarkIndex, loadHiddenAgentIds, unhideAgentId } from '../lib/hiddenAgents'
import { railSeatAgents } from '../lib/railSeats'
import { agentLabel } from '../lib/supportAgent'
import { dispatchToggleTheme } from '../lib/theme'
import { searchShortcutLabel } from '../lib/keybindingTips'
import AgentAvatar from './AgentAvatar'

export const SEARCH_PALETTE_TABS = [
  'All',
  'Messages',
  'Bots',
  'Groups',
  'Files',
  'Links',
  'Routines',
  'Actions',
] as const

export type SearchPaletteTab = (typeof SEARCH_PALETTE_TABS)[number]

export const OPEN_SEARCH_EVENT = 'swarm:open-search'

export interface SearchPaletteOptions {
  filterHidden?: boolean
  tab?: SearchPaletteTab
  query?: string
}

export function openSearchPalette(options?: SearchPaletteOptions): void {
  window.dispatchEvent(new CustomEvent(OPEN_SEARCH_EVENT, { detail: options }))
}

interface PaletteRow {
  id: string
  tab: Exclude<SearchPaletteTab, 'All'>
  name: string
  description: string
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
  const agents = railSeatAgents(blueprintsQuery.data?.data ?? [])

  const rows = useMemo<PaletteRow[]>(() => {
    const botRows: PaletteRow[] = agents.map((agent) => ({
      id: `bot-${agent.id}`,
      tab: 'Bots',
      name: agentLabel(agent),
      description: agent.description || `${agentLabel(agent)} agent`,
      href: `/chat?blueprint=${encodeURIComponent(agent.id)}`,
      agentId: agent.id,
      avatarPath: agent.avatar_path,
    }))
    const actionRows: PaletteRow[] = [
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
      {
        id: 'action-compose-team',
        tab: 'Actions',
        name: 'Compose team',
        description: 'Drag-drop roster overlay (team_rosters.json)',
        action: () => window.dispatchEvent(new CustomEvent('swarm:open-team-composer')),
      },
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
        name: 'Hidden Bots',
        description: 'Unhide agents without leaving chat',
        action: () => {
          setHiddenOnly(true)
          setTab('Bots')
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
    return [...botRows, ...actionRows]
  }, [agents])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (hiddenOnly) {
        if (row.tab !== 'Bots') return false
        if (!row.agentId || !hiddenIds.includes(row.agentId)) return false
      } else {
        if (tab !== 'All' && row.tab !== tab) return false
      }
      if (!q) return true
      return (
        row.name.toLowerCase().includes(q) ||
        row.description.toLowerCase().includes(q)
      )
    })
  }, [query, rows, tab, hiddenOnly, hiddenIds])

  useEffect(() => {
    setActiveIdx(0)
  }, [query, tab, open, hiddenOnly])

  useEffect(() => {
    if (!open) return
    const ids = loadHiddenAgentIds()
    setHiddenIds(ids)
    if (options?.filterHidden) {
      setHiddenOnly(true)
      setTab('Bots')
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
        setTab('Bots')
      } else if (detail?.tab) {
        setTab(detail.tab)
      }
      if (detail?.query !== undefined) setQuery(detail.query)
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
      if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey && /^[1-9]$/.test(event.key)) {
        // Rail hotkey Alt+1–9 (REQ-172 / REQ-208): close search overlay so operator lands on chat.
        // Do not call preventDefault so the rail listener handles navigation.
        onClose()
        return
      }
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
                      const next = unhideAgentId(row.agentId!, hiddenIds)
                      setHiddenIds(next)
                      window.dispatchEvent(new Event('storage'))
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
  if (tab === 'Bots') {
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
      : tab === 'Groups'
        ? Users
        : tab === 'Files'
          ? FileText
          : tab === 'Links'
            ? Link2
            : tab === 'Routines'
              ? Workflow
              : tab === 'Actions'
                ? Sparkles
                : Plug
  return (
    <span className="os-search-row__icon" aria-hidden="true">
      <Icon className="h-4 w-4" />
    </span>
  )
}
