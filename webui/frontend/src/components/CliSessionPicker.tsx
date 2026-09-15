import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { History, Plus, Search } from 'lucide-react'
import { openSettingsSheet } from './SettingsSheet'
import {
  filterCliSessions,
  formatActivityAge,
  looksLikeSessionId,
  sanitizeCliSessionId,
  type CliProviderSession,
} from '../lib/cliSessions'
import { OverlayFocusTrap } from './OverlayFocusTrap'

export interface CliSessionPickerProps {
  open: boolean
  agentName: string
  cli: string
  sessions: readonly CliProviderSession[]
  canList: boolean
  emptyReason?: string | null
  loading?: boolean
  continueTargets?: readonly string[]
  onClose: () => void
  onSelect: (session: CliProviderSession) => void
  onStartNew: () => void
  onContinueOn?: (session: CliProviderSession, targetCli: string) => void
  onManageSession?: () => void
}

/**
 * Search-palette overlay for CLI-provider sessions (REQ-104).
 * Same chrome as SessionPicker; chat stays mounted. Paste-id + Start new
 * remain available when the CLI cannot list.
 */
export default function CliSessionPicker({
  open,
  agentName,
  cli,
  sessions,
  canList,
  emptyReason,
  loading = false,
  continueTargets = [],
  onClose,
  onSelect,
  onStartNew,
  onContinueOn,
  onManageSession,
}: CliSessionPickerProps) {
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const pasted = useMemo(() => sanitizeCliSessionId(query), [query])
  const visible = useMemo(() => filterCliSessions(sessions, query), [query, sessions])
  // Paste-id is for an arbitrary id that is not already in the list. If the
  // query matches existing title/snippet/id rows, treat it as a filter only.
  const showPaste =
    Boolean(pasted) &&
    looksLikeSessionId(query) &&
    !sessions.some((row) => row.id === pasted) &&
    visible.length === 0

  const rows = useMemo(() => {
    const list = [...visible]
    if (showPaste && pasted) {
      list.unshift({
        id: pasted,
        title: `Use session ${pasted}`,
        snippet: 'Pasted session id',
        updated_at: '',
        source: 'swarm',
      })
    }
    return list
  }, [pasted, showPaste, visible])

  useEffect(() => {
    setActiveIdx(0)
  }, [query, open, sessions])

  useEffect(() => {
    if (!open) return
    setQuery('')
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  const choose = useCallback(
    (row: CliProviderSession | undefined) => {
      if (!row) return
      onSelect(row)
      onClose()
    },
    [onClose, onSelect],
  )

  const startNew = useCallback(() => {
    onStartNew()
    onClose()
  }, [onClose, onStartNew])

  const manageSession = useCallback(() => {
    onClose()
    if (onManageSession) {
      onManageSession()
      return
    }
    openSettingsSheet({ section: 'cli-agents' })
  }, [onClose, onManageSession])

  const activeIdxRef = useRef(activeIdx)
  activeIdxRef.current = activeIdx
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      const items = rowsRef.current
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
        if (items[activeIdxRef.current]) {
          choose(items[activeIdxRef.current])
          return
        }
        const sid = sanitizeCliSessionId(query)
        if (sid) {
          choose({
            id: sid,
            title: sid,
            snippet: '',
            updated_at: '',
            source: 'swarm',
          })
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, choose, query])

  if (!open) return null

  const label = `${agentName} sessions`
  const emptyCopy =
    loading
      ? 'Loading sessions…'
      : emptyReason || (canList ? 'No sessions found' : "This CLI can't list sessions")

  return (
    <OverlayFocusTrap onClose={onClose} initialFocus={() => inputRef.current}>
    <div
      className="os-search-overlay"
      data-testid="os-cli-session-picker"
      data-session-picker="true"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div role="dialog" aria-modal="true" aria-label={label} className="os-search-palette">
        <span className="sr-only">{cli}</span>
        <div className="os-search-palette__field">
          <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search or paste a session id"
            aria-label={`Filter ${agentName} sessions`}
            aria-controls="os-cli-session-results"
            aria-activedescendant={
              rows[activeIdx] ? `os-cli-session-row-${rows[activeIdx].id}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            autoComplete="off"
            className="os-search-palette__input"
            data-testid="cli-session-filter"
          />
        </div>

        <ul
          id="os-cli-session-results"
          role="listbox"
          aria-label={label}
          className="os-search-palette__list"
        >
          {rows.length === 0 ? (
            <li className="os-search-empty" data-testid="cli-session-empty">
              {emptyCopy}
            </li>
          ) : (
            rows.map((row, idx) => {
              const age = formatActivityAge(row.updated_at)
              return (
                <li
                  key={row.id}
                  id={`os-cli-session-row-${row.id}`}
                  role="option"
                  aria-selected={idx === activeIdx}
                  data-session-id={row.id}
                  data-source={row.source}
                  className={
                    idx === activeIdx ? 'os-search-row os-search-row--active' : 'os-search-row'
                  }
                  onMouseMove={() => setActiveIdx(idx)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(row)}
                >
                  <History className="h-4 w-4 shrink-0 opacity-60" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="os-search-row__name">{row.title}</span>
                    <span className="os-search-row__desc">
                      {age ? `${age}` : row.source === 'provider' ? 'Provider' : 'Swarm'}
                      {row.snippet ? ` · ${row.snippet}` : ''}
                    </span>
                  </span>
                </li>
              )
            })
          )}
        </ul>
        <div
          role="separator"
          className="border-t border-base-300"
          data-testid="manage-surface-divider"
        />
        <div className="flex flex-wrap items-center gap-2 px-3 py-2">
          <button
            type="button"
            className="btn btn-ghost btn-xs gap-1 text-xs"
            data-testid="cli-session-start-new"
            onClick={startNew}
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Start new session
          </button>
          {onContinueOn && continueTargets.length > 0 ? (
            <label className="flex items-center gap-1 text-xs text-base-content/70">
              <span className="sr-only">Continue selected session on another CLI</span>
              <select
                className="select select-ghost select-xs"
                aria-label="Continue on CLI"
                data-testid="cli-session-continue-on"
                defaultValue=""
                onChange={(event) => {
                  const target = event.target.value
                  event.target.value = ''
                  const row = rows[activeIdx]
                  if (!target || !row) return
                  onContinueOn(row, target)
                  onClose()
                }}
              >
                <option value="">Continue on…</option>
                {continueTargets.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost btn-xs ms-auto text-xs"
            data-testid="cli-session-manage"
            onClick={manageSession}
          >
            Manage Session
          </button>
        </div>
      </div>
    </div>
    </OverlayFocusTrap>
  )
}
