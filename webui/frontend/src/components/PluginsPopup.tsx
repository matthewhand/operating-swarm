import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plug, Search, Settings2, X } from 'lucide-react'
import { Tabs } from './DaisyUI'
import { openSettingsSheet } from './SettingsSheet'
import InstallCatalog from './InstallCatalog'
import {
  CHAT_PLUGIN_TOOLS_EVENT,
  loadEnabledPluginToolIds,
  loadPluginCatalog,
  setPluginToolEnabled,
  snapshotPluginToolOrder,
  visiblePluginToolsFrozen,
  type PluginCatalogSource,
  type PluginTool,
} from '../lib/chatPluginTools'
import { MCP_SERVERS_EVENT } from '../lib/mcpServers'
import {
  CURRENT_CHAT_SCOPE_EVENT,
  resolveChatScopeId,
} from '../lib/chatScope'
import { notifyOverlayClosed } from '../lib/chromeOverlay'
import { OverlayFocusTrap } from './OverlayFocusTrap'

const PLUGIN_PANES = [
  { key: 'chat', label: 'This chat' },
  { key: 'tools', label: 'Add tools' },
  { key: 'skills', label: 'Add skills' },
] as const

type PluginPane = (typeof PLUGIN_PANES)[number]['key']

export interface PluginsPopupProps {
  open: boolean
  onClose: () => void
}

function sourceCopy(source: PluginCatalogSource): string {
  if (source === 'live') return 'Tools from connected MCP servers.'
  if (source === 'configured') return 'Tools from servers you added in Manage.'
  return 'Showing the shipped catalog until MCP servers are connected.'
}

export default function PluginsPopup({ open, onClose }: PluginsPopupProps) {
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [pane, setPane] = useState<PluginPane>('chat')
  const [activeIdx, setActiveIdx] = useState(0)
  const [chatId, setChatId] = useState(() => resolveChatScopeId(searchParams))
  const [enabledIds, setEnabledIds] = useState<string[]>(() =>
    loadEnabledPluginToolIds(resolveChatScopeId(searchParams)),
  )
  const [tools, setTools] = useState<PluginTool[]>([])
  const [source, setSource] = useState<PluginCatalogSource>('fixture')
  const inputRef = useRef<HTMLInputElement | null>(null)

  const refreshScope = useCallback(() => {
    const next = resolveChatScopeId(searchParams)
    setChatId(next)
    setEnabledIds(loadEnabledPluginToolIds(next))
  }, [searchParams])

  useEffect(() => {
    if (!open) return
    setQuery('')
    setPane('chat')
    setActiveIdx(0)
    refreshScope()
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open, refreshScope])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    void loadPluginCatalog().then((resolved) => {
      if (cancelled) return
      setTools(resolved.tools)
      setSource(resolved.source)
    })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    const onScope = () => refreshScope()
    const onPrefs = (event: Event) => {
      const detail = (event as CustomEvent<{ chatId?: string }>).detail
      if (!detail?.chatId || detail.chatId === chatId) {
        setEnabledIds(loadEnabledPluginToolIds(chatId || resolveChatScopeId(searchParams)))
      }
    }
    window.addEventListener(CURRENT_CHAT_SCOPE_EVENT, onScope)
    window.addEventListener(CHAT_PLUGIN_TOOLS_EVENT, onPrefs)
    window.addEventListener(MCP_SERVERS_EVENT, onScope)
    return () => {
      window.removeEventListener(CURRENT_CHAT_SCOPE_EVENT, onScope)
      window.removeEventListener(CHAT_PLUGIN_TOOLS_EVENT, onPrefs)
      window.removeEventListener(MCP_SERVERS_EVENT, onScope)
    }
  }, [chatId, refreshScope, searchParams])

  const enabledSet = useMemo(() => new Set(enabledIds), [enabledIds])
  // Re-sort only when the popup opens, the chat changes, or the catalog loads.
  // Live On/Off toggles must not move rows (#278 / REQ-881).
  const orderKey = open ? `${chatId}\0${tools.map((tool) => tool.id).join('\0')}` : ''
  const freezeRef = useRef<{ key: string; ids: string[] }>({ key: '', ids: [] })
  if (freezeRef.current.key !== orderKey) {
    freezeRef.current = {
      key: orderKey,
      ids: orderKey ? snapshotPluginToolOrder(tools, enabledSet) : [],
    }
  }
  const orderIds = freezeRef.current.ids
  const visible = useMemo(
    () => visiblePluginToolsFrozen(tools, query, orderIds),
    [orderIds, query, tools],
  )

  useEffect(() => {
    setActiveIdx(0)
  }, [query, tools, open])

  const toggle = useCallback(
    (tool: PluginTool | undefined) => {
      if (!tool || !chatId) return
      setEnabledIds(setPluginToolEnabled(chatId, tool.id, !enabledSet.has(tool.id)))
    },
    [chatId, enabledSet],
  )

  const close = useCallback(() => {
    onClose()
    notifyOverlayClosed()
  }, [onClose])

  const openManage = useCallback(() => {
    close()
    openSettingsSheet({ section: 'plugins' })
  }, [close])

  const activeIdxRef = useRef(activeIdx)
  activeIdxRef.current = activeIdx
  const visibleRef = useRef(visible)
  visibleRef.current = visible

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      const items = visibleRef.current
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
        return
      }
      if (pane !== 'chat') return
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setActiveIdx((i) => Math.min(i + 1, Math.max(0, items.length - 1)))
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setActiveIdx((i) => Math.max(i - 1, 0))
        return
      }
      if (event.key === 'Enter' || event.key === ' ') {
        if (event.target instanceof HTMLInputElement && event.key === ' ') return
        event.preventDefault()
        toggle(items[activeIdxRef.current])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, open, pane, toggle])

  if (!open) return null

  const emptyCatalog = tools.length === 0
  const emptySearch = !emptyCatalog && visible.length === 0

  return (
    <OverlayFocusTrap onClose={close} initialFocus={() => inputRef.current}>
    <div
      className="os-search-overlay os-search-overlay--centered"
      data-testid="os-plugins-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Plugins"
        data-testid="os-plugins-popup"
        /* REQ-910 (#509): the frame is pane-independent — the shell's height and
           width come from CSS, identical for all three panes, so switching tabs
           cannot move or resize the dialog. */
        className="os-search-palette os-search-palette--centered"
      >
        <div className="os-search-palette__field">
          {pane === 'chat' ? (
            <>
              <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
              <input
                ref={inputRef}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search tools"
                aria-label="Filter tools"
                aria-controls="os-plugin-results"
                aria-activedescendant={
                  visible[activeIdx] ? `os-plugin-row-${visible[activeIdx].id}` : undefined
                }
                role="combobox"
                aria-expanded="true"
                autoComplete="off"
                className="os-search-palette__input"
              />
            </>
          ) : (
            <span className="os-search-palette__input text-sm font-medium">
              {pane === 'tools' ? 'Add tools' : 'Add skills'}
            </span>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            aria-label="Close plugins"
            onClick={close}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="px-4 pb-2">
          <Tabs
            tabs={[...PLUGIN_PANES]}
            activeTab={pane}
            onChange={(key) => setPane(key as PluginPane)}
            variant="boxed"
            size="sm"
            className="os-plugins-panes"
          />
        </div>

        {pane === 'chat' ? (
        <p className="px-4 pb-2 text-[11px] text-base-content/50" data-testid="os-plugins-source">
          {sourceCopy(source)} Toggles apply to this chat only.
        </p>
        ) : null}

        {pane === 'chat' ? (
        <ul
          id="os-plugin-results"
          role="listbox"
          aria-label="Plugin tools"
          className="os-search-palette__list"
        >
          {emptyCatalog ? (
            <li className="os-search-empty">
              No tools.
              <button
                type="button"
                className="btn btn-ghost btn-xs mt-2 text-primary"
                onClick={openManage}
              >
                Connect a server in Manage…
              </button>
            </li>
          ) : emptySearch ? (
            <li className="os-search-empty">
              {query.trim()
                ? `No matches for “${query.trim()}”.`
                : 'No tools.'}
            </li>
          ) : (
            visible.map((tool, idx) => {
              const on = enabledSet.has(tool.id)
              return (
                <li
                  key={tool.id}
                  id={`os-plugin-row-${tool.id}`}
                  role="option"
                  aria-selected={idx === activeIdx}
                  data-tool-id={tool.id}
                  data-enabled={on ? 'true' : 'false'}
                  className={
                    idx === activeIdx
                      ? 'os-search-row os-plugin-row os-search-row--active'
                      : 'os-search-row os-plugin-row'
                  }
                  onMouseMove={() => setActiveIdx(idx)}
                >
                  <span className="os-search-row__icon" aria-hidden="true">
                    <Plug className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="os-search-row__name">{tool.name}</span>
                    <span className="os-search-row__desc">
                      {tool.serverName}
                      {tool.description ? ` · ${tool.description}` : ''}
                    </span>
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    aria-label={`${tool.name} ${on ? 'On' : 'Off'}`}
                    className="os-plugin-toggle flex items-center gap-2"
                    onClick={(event) => {
                      event.stopPropagation()
                      toggle(tool)
                    }}
                  >
                    <input
                      type="checkbox"
                      className="toggle toggle-sm toggle-primary pointer-events-none"
                      checked={on}
                      readOnly
                      tabIndex={-1}
                      aria-hidden="true"
                    />
                    <span className="text-xs font-semibold w-7">{on ? 'On' : 'Off'}</span>
                  </button>
                </li>
              )
            })
          )}
        </ul>
        ) : (
          <div className="os-search-palette__list" data-testid="os-plugins-catalog">
            <InstallCatalog
              surface={pane === 'skills' ? 'skills' : 'tools'}
              onManage={() => openManage()}
            />
          </div>
        )}

        <div className="os-search-palette__footer" aria-label="Plugins actions">
          {pane === 'chat' ? (
            <>
              <span className="os-search-tip">
                <kbd className="kbd kbd-xs">↑↓</kbd> Navigate
              </span>
              <span className="os-search-tip">
                <kbd className="kbd kbd-xs">↵</kbd> Toggle
              </span>
            </>
          ) : (
            <span className="os-search-tip">Browse → detail → install</span>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-xs ml-auto text-primary"
            onClick={openManage}
          >
            <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
            Manage servers
          </button>
        </div>
      </div>
    </div>
    </OverlayFocusTrap>
  )
}
