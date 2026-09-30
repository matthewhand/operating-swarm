/**
 * #1202 — the navbar `[ 🤖 Agent ]` control.
 *
 * Two responsibilities, deliberately separated (#1202 follow-up):
 *
 *  - **Capability shell.** When the active seat advertises `agents` it renders
 *    the real control (or a provided child); when it does not, the control
 *    stays **mounted but greyed** (`opacity: .4`, `cursor: not-allowed`) with
 *    an inert click and a capability-aware tooltip. Unmounting is the caller's
 *    decision (the `hideUnsupportedAgentPicker` power-user toggle).
 *
 *  - **Picker semantics.** The enabled control opens a menu of the *available
 *    agents* to switch to. It never opens the current agent's configuration —
 *    that is the avatar + identity label + edit combo's job.
 *
 * It never switches the active seat itself: the caller owns `onSelect`, which
 * receives the chosen agent id and its declared kind.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Bot, Check } from 'lucide-react'
import { filterAgentsByProviderScope } from '../lib/seatRouting'

export interface NavbarAgentOption {
  id: string
  label: string
  /** Declared seat kind of the option — cross-kind picks navigate (#502). */
  kind?: string
  /**
   * #1352 — the provider scope this agent belongs to (`api`, `cli:opencode`,
   * `remote:hermes`, `team:<id>`). The picker lists only agents from the
   * selected agent's provider; the default inference profile never sets it.
   */
  provider?: string
}

export interface NavbarAgentPickerProps {
  /** True when the seat cannot support agent selection. */
  disabled?: boolean
  /** Capability-aware tooltip shown when disabled. */
  reason?: string
  label?: string
  /** The provider's selectable agents — what the picker lists. */
  agents?: NavbarAgentOption[]
  /** Highlight the currently active agent row. */
  selectedId?: string
  /**
   * #1352 — the current provider scope key. When omitted, the scope is read
   * from the selected agent's own `provider` field; when neither is known the
   * picker lists every agent (never the default inference profile).
   */
  provider?: string
  /** Switch to the chosen agent (id + declared kind). */
  onSelect?: (id: string, kind?: string) => void
  children?: ReactNode
}

export const NAVBAR_AGENT_PICKER_TESTID = 'os-navbar-agent-picker'
export const NAVBAR_AGENT_PICKER_MENU_TESTID = 'os-navbar-agent-picker-menu'
export const NAVBAR_AGENT_PICKER_SEARCH_TESTID = 'os-navbar-agent-picker-search'

export function NavbarAgentPicker({
  disabled = false,
  reason = '',
  label = 'Select agent',
  agents = [],
  selectedId = '',
  provider = '',
  onSelect,
  children,
}: NavbarAgentPickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // #1352: the picker is scoped to the selected agent's provider. An explicit
  // `provider` prop wins; otherwise the scope rides on the selected agent's
  // own row. No scope (or no row declaring one) keeps every agent — the list
  // is never derived from the default inference profile.
  const providerScope = useMemo(() => {
    const explicit = provider.trim()
    if (explicit) return explicit
    return (agents.find((agent) => agent.id === selectedId)?.provider ?? '').trim()
  }, [provider, agents, selectedId])
  const visibleAgents = useMemo(
    () => filterAgentsByProviderScope(agents, providerScope || null),
    [agents, providerScope],
  )
  // #1358: the picker is a search popup — the text filter runs on the
  // provider-scoped rows, so a search can never reveal a foreign provider.
  const filteredAgents = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return visibleAgents
    return visibleAgents.filter(
      (agent) =>
        agent.label.toLowerCase().includes(q) || agent.id.toLowerCase().includes(q),
    )
  }, [visibleAgents, query])

  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }
    requestAnimationFrame(() => searchRef.current?.focus())
  }, [open])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (disabled) {
    const tip = reason || label
    return (
      <span
        className="tooltip tooltip-bottom os-navbar-picker os-navbar-picker--disabled"
        data-tip={tip}
        data-disabled="true"
        title={tip}
      >
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-square opacity-40 cursor-not-allowed"
          disabled
          aria-disabled="true"
          aria-label={tip}
          title={tip}
          data-tip={tip}
          data-testid={NAVBAR_AGENT_PICKER_TESTID}
          data-disabled="true"
        >
          <Bot className="h-4 w-4" aria-hidden="true" />
        </button>
      </span>
    )
  }

  if (children) return <>{children}</>

  return (
    <div className="dropdown dropdown-end" ref={rootRef}>
      <button
        type="button"
        className="btn btn-ghost btn-sm btn-square os-navbar-picker"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        title={label}
        data-testid={NAVBAR_AGENT_PICKER_TESTID}
        data-disabled="false"
        onClick={() => setOpen((prev) => !prev)}
      >
        <Bot className="h-4 w-4" aria-hidden="true" />
      </button>
      {open ? (
        <div className="dropdown-content z-[70] mt-1 w-60 rounded-box border border-base-content/10 bg-base-100 p-1 shadow-lg">
          <div className="px-1 pb-1">
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') setOpen(false)
              }}
              placeholder="Search agents"
              aria-label={`Search ${label}`}
              data-testid={NAVBAR_AGENT_PICKER_SEARCH_TESTID}
              autoComplete="off"
              className="input input-sm input-bordered w-full"
            />
          </div>
          <ul
            role="menu"
            aria-label={label}
            data-testid={NAVBAR_AGENT_PICKER_MENU_TESTID}
            data-provider={providerScope || undefined}
            className="menu menu-sm max-h-[60vh] w-full overflow-y-auto p-0"
          >
            {filteredAgents.length === 0 ? (
              <li role="none">
                <span className="opacity-60">
                  {visibleAgents.length === 0 ? 'No agents available' : 'No matching agents'}
                </span>
              </li>
            ) : (
              filteredAgents.map((agent) => {
                const active = agent.id === selectedId
                return (
                  <li key={agent.id} role="none">
                    <button
                      type="button"
                      role="menuitem"
                      data-testid={`os-navbar-agent-option-${agent.id}`}
                      data-kind={agent.kind}
                      data-provider={agent.provider}
                      aria-current={active ? 'true' : undefined}
                      className={active ? 'active' : ''}
                      onClick={() => {
                        setOpen(false)
                        onSelect?.(agent.id, agent.kind)
                      }}
                    >
                      <span className="min-w-0 flex-1 truncate">{agent.label}</span>
                      {active ? <Check className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /> : null}
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export default NavbarAgentPicker
