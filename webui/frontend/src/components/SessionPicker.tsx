import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { agentMarkIndex } from '../lib/hiddenAgents'
import {
  compareSessions,
  type AgentSession,
} from '../lib/scaleOutSessions'
import type { MemberSession } from '../lib/sessionPicker'
import { sessionRelativeLabel } from '../lib/agentSessions'

export type SessionPickerSession = (AgentSession | MemberSession) & {
  agentId?: string
  href?: string
}

export interface SessionPickerProps {
  open: boolean
  title?: string
  agentName?: string
  sessions: readonly (AgentSession | MemberSession)[]
  onClose: () => void
  onSelect: (session: any) => void
  /** REQ-105: empty list still offers New session. #468 can reuse this chrome. */
  onNewSession?: () => void
}

function shortcutLabel(index: number): string {
  return `⌃${index + 1}`
}

function sessionCompare(a: any, b: any): number {
  if (typeof compareSessions === 'function' && 'startedAt' in a && 'startedAt' in b) {
    const aRunning = a.status === 'running'
    const bRunning = b.status === 'running'
    if (aRunning && !bRunning) return -1
    if (!aRunning && bRunning) return 1
    return (b.startedAt ?? 0) - (a.startedAt ?? 0)
  }
  return 0
}

function sessionFilter(sessions: readonly any[], query: string): any[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...sessions]
  return sessions.filter((s) => {
    const title = (s.title || '').toLowerCase()
    const snippet = (s.snippet || '').toLowerCase()
    const id = (s.id || s.memberId || '').toLowerCase()
    return title.includes(q) || snippet.includes(q) || id.includes(q)
  })
}

/**
 * Search-palette chrome, pre-filtered to one agent, team, or remote's running + finished
 * sessions. Not a new SPA page — overlay only; chat stays mounted.
 */
function sessionWhen(row: any): string {
  const relative = sessionRelativeLabel({
    updatedAt: row.updatedAt ?? row.updated_at_ms,
    startedAt: row.startedAt ?? row.started_at_ms,
  })
  if (relative) return relative
  return row.status === 'running' ? 'Running' : 'Finished'
}

export default function SessionPicker({
  open,
  title,
  agentName,
  sessions,
  onClose,
  onSelect,
  onNewSession,
}: SessionPickerProps) {
  const displayName = title || agentName || ''
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const visible = useMemo(
    () => sessionFilter([...sessions].sort(sessionCompare), query),
    [query, sessions],
  )

  const teamSession = useMemo(
    () => (sessions as readonly any[]).find((s) => s?.groupKind === 'team'),
    [sessions],
  )

  useEffect(() => {
    setActiveIdx(0)
  }, [query, open, sessions])

  useEffect(() => {
    if (!open) return
    setQuery('')
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  const choose = useCallback(
    (row: AgentSession | undefined) => {
      if (!row) return
      onSelect(row)
      onClose()
    },
    [onClose, onSelect],
  )

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
        onClose()
        return
      }
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
      if (event.key === 'Enter') {
        event.preventDefault()
        choose(items[activeIdxRef.current])
        return
      }
      if (event.ctrlKey && /^[1-9]$/.test(event.key)) {
        event.preventDefault()
        choose(items[Number(event.key) - 1])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, choose])

  if (!open) return null

  const label = `${displayName} sessions`

  return (
    <div
      className="os-search-overlay"
      data-testid="os-session-picker"
      data-session-picker="true"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className="os-search-palette"
      >
        <span className="sr-only">{displayName}</span>
        <div className="os-search-palette__field">
          <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search"
            aria-label={title ? 'Filter sessions' : `Filter ${displayName} sessions`}
            aria-controls="os-session-results"
            aria-activedescendant={
              visible[activeIdx] ? `os-session-row-${visible[activeIdx].id}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            autoComplete="off"
            className="os-search-palette__input"
          />
        </div>

        <ul
          id="os-session-results"
          role="listbox"
          aria-label={label}
          className="os-search-palette__list"
        >
          {visible.length === 0 ? (
            <li className="os-search-empty">no sessions yet</li>
          ) : (
            visible.map((row, idx) => (
              <li
                key={row.id}
                id={`os-session-row-${row.id}`}
                role="option"
                aria-selected={idx === activeIdx}
                data-session-id={row.id}
                data-status={row.status}
                className={
                  idx === activeIdx ? 'os-search-row os-search-row--active' : 'os-search-row'
                }
                onMouseMove={() => setActiveIdx(idx)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(row)}
              >
                <span
                  className="os-search-row__icon"
                  data-mark={String(agentMarkIndex(row.id))}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1">
                  <span className="os-search-row__name">{row.title}</span>
                  <span className="os-search-row__desc">
                    {sessionWhen(row)}
                    {row.snippet ? ` · ${row.snippet}` : ''}
                  </span>
                </span>
                {idx < 9 && <kbd className="os-search-shortcut">{shortcutLabel(idx)}</kbd>}
              </li>
            ))
          )}
        </ul>
        {(teamSession || onNewSession) && (
          <div className="flex items-center justify-between gap-2 border-t border-base-300 px-3 py-2">
            {onNewSession ? (
              <button
                type="button"
                className="btn btn-ghost btn-xs text-xs text-primary"
                data-testid="os-session-new"
                onClick={() => {
                  onNewSession()
                  onClose()
                }}
              >
                New session
              </button>
            ) : (
              <span />
            )}
            {teamSession ? (
              <a
                href={`/teams/#${encodeURIComponent(teamSession.groupId)}`}
                className="btn btn-ghost btn-xs text-xs text-primary"
                onClick={onClose}
              >
                Manage Team →
              </a>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}
