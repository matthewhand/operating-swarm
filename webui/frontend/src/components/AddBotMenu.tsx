/**
 * #1674 — the `+` / "Add bot" dropdown.
 *
 * One control next to Search, three jobs, anchored to the button that opens it
 * (the rail's "search or create" strip) instead of a settings detour:
 *
 *  - **Create new agent** → `onCreateBot`, the caller's existing AddAgentWizard
 *    state. No second creation flow is invented here.
 *  - **Create group chat** → `onCreateGroupChat`, the caller's existing group
 *    chat composer entry point (the same one the rail's footer button uses).
 *  - **Your agents** → a filterable, keyboard-navigable list of the *existing*
 *    agents the caller already has (avatar + display name). Picking one runs
 *    `onStartChat(agentId)` — a NEW chat session with that agent, not a focus
 *    of whatever thread happens to be open.
 *
 * The component owns no agent registry of its own: it takes plain rows and
 * three callbacks, so the rail (and any future navbar mount) share one menu
 * and one set of handlers.
 *
 * Copy is the product's own vocabulary (the create wizard is "Add Agent", the
 * composer is "group chat") — no third-party chrome strings.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Plus, Users } from 'lucide-react'
import AgentAvatar from './AgentAvatar'

export interface AddBotMenuAgent {
  id: string
  /** Display name as the rail shows it (pin renames included). */
  label: string
  avatarSrc?: string | null
  /** Declared seat kind — remote rows render their platform face (#747). */
  remoteKind?: string | null
}

export interface AddBotMenuProps {
  /** The existing agents to offer. Same list the rail already renders. */
  agents?: AddBotMenuAgent[]
  /** Marks the currently open seat (visual only — picking still starts fresh). */
  activeAgentId?: string
  onCreateBot: () => void
  onCreateGroupChat: () => void
  /** Start a NEW chat session with this agent id. */
  onStartChat: (agentId: string) => void
  /** Trigger copy. The rail keeps its historical "Add agent" wording. */
  triggerLabel?: string
  className?: string
}

export const ADD_BOT_MENU_TRIGGER_TESTID = 'add-bot-menu-trigger'
export const ADD_BOT_MENU_PANEL_TESTID = 'os-add-bot-menu'
export const ADD_BOT_MENU_SEARCH_TESTID = 'os-add-bot-menu-search'
export const ADD_BOT_MENU_LIST_TESTID = 'os-add-bot-menu-agents'
export const ADD_BOT_MENU_CREATE_BOT_TESTID = 'os-add-bot-menu-create-bot'
export const ADD_BOT_MENU_CREATE_GROUP_TESTID = 'os-add-bot-menu-create-group'
export const ADD_BOT_MENU_EMPTY_TESTID = 'os-add-bot-menu-empty'
export const ADD_BOT_MENU_OPTION_TESTID = (agentId: string) =>
  `os-add-bot-menu-agent-${agentId}`

/** One navigable row: the two create actions, then the filtered agent rows. */
type AddBotMenuEntry =
  | { kind: 'create-bot' }
  | { kind: 'create-group' }
  | { kind: 'agent'; agent: AddBotMenuAgent }

const CREATE_BOT_ENTRY: AddBotMenuEntry = { kind: 'create-bot' }
const CREATE_GROUP_ENTRY: AddBotMenuEntry = { kind: 'create-group' }

function matchesQuery(agent: AddBotMenuAgent, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return (
    agent.label.toLowerCase().includes(q) || agent.id.toLowerCase().includes(q)
  )
}

export function AddBotMenu({
  agents = [],
  activeAgentId = '',
  onCreateBot,
  onCreateGroupChat,
  onStartChat,
  triggerLabel = 'Add agent',
  className = '',
}: AddBotMenuProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const optionBaseId = `${listId}-option`

  const visibleAgents = useMemo(
    () => agents.filter((agent) => agent.id && matchesQuery(agent, query)),
    [agents, query],
  )
  const entries = useMemo<AddBotMenuEntry[]>(
    () => [
      CREATE_BOT_ENTRY,
      CREATE_GROUP_ENTRY,
      ...visibleAgents.map((agent): AddBotMenuEntry => ({ kind: 'agent', agent })),
    ],
    [visibleAgents],
  )

  // No separate `close`: every path out of the menu goes through `runEntry`
  // (pick an entry, or dismiss), and `runEntry` already owns `setOpen(false)`.
  // A second closure over the same setter was dead code (TS6133).
  const runEntry = useCallback(
    (entry: AddBotMenuEntry | undefined) => {
      if (!entry) return
      setOpen(false)
      setQuery('')
      if (entry.kind === 'create-bot') onCreateBot()
      else if (entry.kind === 'create-group') onCreateGroupChat()
      else onStartChat(entry.agent.id)
    },
    [onCreateBot, onCreateGroupChat, onStartChat],
  )

  // #1674: the filter owns the caret on open, so typing narrows the list
  // without a pointer. A closed menu always reopens clean.
  useEffect(() => {
    if (!open) {
      setQuery('')
      setActiveIndex(0)
      return
    }
    const frame = requestAnimationFrame(() => searchRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [open])

  // Keep the active row inside the list as the filter shrinks it.
  useEffect(() => {
    setActiveIndex((current) => (current < entries.length ? current : 0))
  }, [entries.length])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        searchRef.current?.blur()
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((current) => {
        const next = current + delta
        if (entries.length === 0) return 0
        if (next < 0) return entries.length - 1
        if (next >= entries.length) return 0
        return next
      })
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      setActiveIndex(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      setActiveIndex(Math.max(0, entries.length - 1))
      return
    }
    if (event.key === 'Enter') {
      // Enter runs the active row. The filter is a combobox over the same
      // rows, so typing never disarms Enter.
      event.preventDefault()
      runEntry(entries[activeIndex])
    }
  }

  const activeId = entries[activeIndex]
    ? `${optionBaseId}-${entries[activeIndex].kind === 'agent' ? entries[activeIndex].agent.id : entries[activeIndex].kind}`
    : ''

  const optionId = (entry: AddBotMenuEntry) =>
    `${optionBaseId}-${
      entry.kind === 'agent' ? entry.agent.id : entry.kind
    }`

  const renderOption = (entry: AddBotMenuEntry, index: number) => {
    const isActive = index === activeIndex
    const shared = {
      id: optionId(entry),
      type: 'button' as const,
      role: 'menuitem' as const,
      tabIndex: -1,
      'data-active': isActive ? 'true' : 'false',
      className: `os-add-bot-menu__row${isActive ? ' os-add-bot-menu__row--active' : ''}`,
    }
    if (entry.kind === 'create-bot') {
      return (
        <button
          {...shared}
          key="create-bot"
          data-testid={ADD_BOT_MENU_CREATE_BOT_TESTID}
          onClick={() => runEntry(entry)}
        >
          <Plus className="os-add-bot-menu__icon h-4 w-4" aria-hidden="true" />
          <span className="os-add-bot-menu__label">Create new agent</span>
        </button>
      )
    }
    if (entry.kind === 'create-group') {
      return (
        <button
          {...shared}
          key="create-group"
          data-testid={ADD_BOT_MENU_CREATE_GROUP_TESTID}
          onClick={() => runEntry(entry)}
        >
          <Users className="os-add-bot-menu__icon h-4 w-4" aria-hidden="true" />
          <span className="os-add-bot-menu__label">Create group chat</span>
        </button>
      )
    }
    const { agent } = entry
    return (
      <button
        {...shared}
        key={`agent-${agent.id}`}
        data-testid={ADD_BOT_MENU_OPTION_TESTID(agent.id)}
        data-agent-id={agent.id}
        data-active-agent={agent.id === activeAgentId ? 'true' : 'false'}
        title={agent.label}
        onClick={() => runEntry(entry)}
      >
        <AgentAvatar
          src={agent.avatarSrc ?? null}
          agentId={agent.id}
          alt=""
          size="xs"
          remoteKind={agent.remoteKind ?? null}
        />
        <span className="os-add-bot-menu__label truncate">{agent.label}</span>
      </button>
    )
  }

  return (
    <div className={`os-add-bot-menu ${className}`.trim()} ref={rootRef}>
      <button
        type="button"
        className="os-search-add-btn"
        aria-label={triggerLabel}
        title={triggerLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        data-testid={ADD_BOT_MENU_TRIGGER_TESTID}
        data-open={open ? 'true' : 'false'}
        onClick={() => setOpen((prev) => !prev)}
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
      </button>
      {open ? (
        <div
          className="os-add-bot-menu__panel"
          data-testid={ADD_BOT_MENU_PANEL_TESTID}
          onKeyDown={onMenuKeyDown}
        >
          <div className="os-add-bot-menu__search-slot">
            <input
              ref={searchRef}
              type="search"
              className="os-add-bot-menu__search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setActiveIndex(0)
              }}
              placeholder="Search agents"
              aria-label="Search agents"
              aria-controls={listId}
              aria-activedescendant={activeId || undefined}
              autoComplete="off"
              data-testid={ADD_BOT_MENU_SEARCH_TESTID}
            />
          </div>
          <div className="os-add-bot-menu__scroll">
            <div role="menu" aria-label="Add agent" className="os-add-bot-menu__group">
              {renderOption(CREATE_BOT_ENTRY, 0)}
              {renderOption(CREATE_GROUP_ENTRY, 1)}
            </div>
            <p className="os-add-bot-menu__heading" id={`${listId}-heading`}>
              Your agents
            </p>
            <div
              id={listId}
              role="group"
              aria-labelledby={`${listId}-heading`}
              data-testid={ADD_BOT_MENU_LIST_TESTID}
              className="os-add-bot-menu__list"
            >
              {visibleAgents.length === 0 ? (
                <p className="os-add-bot-menu__empty" data-testid={ADD_BOT_MENU_EMPTY_TESTID}>
                  {agents.length === 0 ? 'No agents yet' : 'No matching agents'}
                </p>
              ) : (
                entries.slice(2).map((entry, offset) => renderOption(entry, offset + 2))
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default AddBotMenu
