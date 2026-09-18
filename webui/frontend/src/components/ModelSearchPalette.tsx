import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Search, Settings2 } from 'lucide-react'
import { openSettingsSheet } from './SettingsSheet'
import {
  filterModelOptions,
  groupModelOptions,
  type ModelSearchOption,
} from '../lib/modelSearch'

export type { ModelSearchOption }

export interface ModelSearchPaletteProps {
  open: boolean
  models: readonly ModelSearchOption[]
  selectedId?: string
  defaultId?: string
  onClose: () => void
  onSelect: (model: ModelSearchOption) => void
  onManageSettings?: () => void
  /** #504: footer label for the manage deep-link. Defaults to the API wording. */
  manageLabel?: string
  /** #504: visible scope chip (e.g. `CLI · qwen`). Absent → no chip row. */
  scopeLabel?: string
  /** #504: full option set revealed when the scope chip is cleared. */
  allModels?: readonly ModelSearchOption[]
  /** #504: clears the caller's persisted scope preference (best-effort). */
  onClearScope?: () => void
  /** REQ-870: lazy CLI model probe in flight — the list is momentarily empty. */
  loading?: boolean
  /** #494: backend-classified failure surfaced with its Fix-in-Settings action. */
  warning?: { text: string; actionLabel?: string; onAction?: () => void }
}

function shortcutLabel(index: number): string {
  return `⌃${index + 1}`
}

export default function ModelSearchPalette({
  open,
  models,
  selectedId,
  defaultId,
  onClose,
  onSelect,
  onManageSettings,
  manageLabel,
  scopeLabel,
  allModels,
  onClearScope,
  loading = false,
  warning,
}: ModelSearchPaletteProps) {
  const [query, setQuery] = useState('')
  // #504: the scope starts on every open and survives until the user removes
  // the chip — a fresh open re-tightens the list, matching "scoped by default".
  const [scopeCleared, setScopeCleared] = useState(false)
  const [activeIdx, setActiveIdx] = useState(0)
  // #634: keyboard focus lives either on the result rows or on the scope row
  // (chip / reveal control), so ← and ↑ from the top of the list can reach it.
  const [focusMode, setFocusMode] = useState<'rows' | 'scope'>('rows')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const chipRef = useRef<HTMLSpanElement | null>(null)
  const scopeClearRef = useRef<HTMLButtonElement | null>(null)

  const scopeOn = Boolean(scopeLabel) && !scopeCleared
  // #504: the option set itself swaps — scoped list by default, the full
  // configured catalog when the chip is cleared. Scoped must be a subset of
  // all (caller contract), so the palette can branch on the arrays.
  const scopedList = models
  const allList = allModels && allModels.length >= models.length ? allModels : models
  const effectiveModels = scopeOn ? scopedList : allList

  const visible = useMemo(() => filterModelOptions(effectiveModels, query), [effectiveModels, query])
  const groups = useMemo(() => groupModelOptions(visible), [visible])

  useEffect(() => {
    setActiveIdx(0)
    setFocusMode('rows')
    descendFromRef.current = null
  }, [query, effectiveModels, open])

  useEffect(() => {
    if (!open) return
    setQuery('')
    setScopeCleared(false)
    setFocusMode('rows')
    descendFromRef.current = null
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  const choose = useCallback(
    (row: ModelSearchOption | undefined) => {
      if (!row) return
      onSelect(row)
      onClose()
    },
    [onClose, onSelect],
  )

  const openManage = useCallback(() => {
    onClose()
    if (onManageSettings) {
      onManageSettings()
      return
    }
    openSettingsSheet({ section: 'llm-profiles' })
  }, [onClose, onManageSettings])

  const activeIdxRef = useRef(activeIdx)
  activeIdxRef.current = activeIdx
  const visibleRef = useRef(visible)
  visibleRef.current = visible
  const groupsRef = useRef(groups)
  groupsRef.current = groups
  const scopeOnRef = useRef(scopeOn)
  scopeOnRef.current = scopeOn
  const focusModeRef = useRef(focusMode)
  focusModeRef.current = focusMode
  // #634: agent row the user descended from (agent row → its model group).
  const descendFromRef = useRef<number | null>(null)

  /** First visible row index of the given group (groups are contiguous). */
  const groupStart = useCallback((groupIdx: number) => {
    let start = 0
    for (let i = 0; i < groupIdx && i < groupsRef.current.length; i += 1) {
      start += groupsRef.current[i].models.length
    }
    return start
  }, [])

  /**
   * #634: the model group an agent row descends into. Groups nest by the
   * `Parent · child` naming convention (the picker emits `CLI · agy models`),
   * so prefer the selection's own subgroup; with exactly two groups the other
   * one is unambiguous.
   */
  const descendTargetGroup = useCallback((provider: string, label: string) => {
    const groups = groupsRef.current
    const own = groups.findIndex((g) => g.name === provider)
    const ownName = own >= 0 ? groups[own].name : provider
    const byLabel = groups.findIndex(
      (g) => g.name === `${ownName} · ${label} models` || g.name.startsWith(`${ownName} · ${label}`),
    )
    if (byLabel >= 0) return byLabel
    const byPrefix = groups.findIndex((g) => g.name.startsWith(`${ownName} ·`))
    if (byPrefix >= 0) return byPrefix
    if (groups.length === 2 && own >= 0) return 1 - own
    return -1
  }, [])

  const focusScope = useCallback(() => {
    const el = scopeOnRef.current ? chipRef.current : scopeClearRef.current
    if (!el) return
    setFocusMode('scope')
    el.focus()
  }, [])

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
        setFocusMode('rows')
        setActiveIdx((i) => Math.min(i + 1, Math.max(0, items.length - 1)))
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        // #634: from the very top, ↑ reaches the scope row (chip / reveal).
        if (activeIdxRef.current === 0 && focusModeRef.current === 'rows' && scopeLabel) {
          focusScope()
          return
        }
        setFocusMode('rows')
        setActiveIdx((i) => Math.max(i - 1, 0))
        return
      }
      if (event.key === 'Home') {
        event.preventDefault()
        setFocusMode('rows')
        setActiveIdx(0)
        return
      }
      if (event.key === 'End') {
        event.preventDefault()
        setFocusMode('rows')
        setActiveIdx(Math.max(0, items.length - 1))
        return
      }
      // #634: ←/→ mirror the reading direction. Inline-end descends from an
      // agent row into its model group (and exits the scope row); inline-start
      // returns from a descent, or reaches the scope row from the very top.
      const rtl = document.documentElement.getAttribute('dir') === 'rtl'
      const inlineEnd = rtl ? 'ArrowLeft' : 'ArrowRight'
      const inlineStart = rtl ? 'ArrowRight' : 'ArrowLeft'
      if (event.key === inlineEnd) {
        event.preventDefault()
        if (focusModeRef.current === 'scope') {
          setFocusMode('rows')
          setActiveIdx(0)
          return
        }
        const current = items[activeIdxRef.current]
        const provider = (current?.provider || '').trim()
        const isAgentRow = Boolean(current?.kind) && scopeOnRef.current && provider !== ''
        if (!isAgentRow) return
        const groupIdx = descendTargetGroup(provider, current?.label || '')
        if (groupIdx < 0) return
        descendFromRef.current = activeIdxRef.current
        setFocusMode('rows')
        setActiveIdx(groupStart(groupIdx))
        return
      }
      if (event.key === inlineStart) {
        event.preventDefault()
        if (activeIdxRef.current === 0 && descendFromRef.current === null) {
          focusScope()
          return
        }
        if (focusModeRef.current === 'rows') {
          const from = descendFromRef.current
          if (from !== null && items[from]) {
            descendFromRef.current = null
            setActiveIdx(from)
          }
        }
        return
      }
      if (event.key === 'Enter') {
        if (event.target instanceof HTMLButtonElement) return
        if (focusModeRef.current === 'scope') return // scope row handles its own activation
        event.preventDefault()
        choose(items[activeIdxRef.current])
        return
      }
      if ((event.ctrlKey || event.metaKey) && /^[1-9]$/.test(event.key)) {
        event.preventDefault()
        choose(items[Number(event.key) - 1])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [choose, onClose, open, groupStart, descendTargetGroup, focusScope, scopeLabel])

  if (!open) return null

  const emptySearch = effectiveModels.length > 0 && visible.length === 0
  let optionIndex = -1

  return (
    <div
      className="os-search-overlay os-search-overlay--centered"
      data-testid="os-model-search-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Models"
        data-testid="os-model-search-palette"
        className="os-search-palette os-search-palette--centered"
      >
        <div className="os-search-palette__field">
          <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search models"
            aria-label="Filter models"
            aria-controls="os-model-results"
            aria-activedescendant={
              visible[activeIdx] ? `os-model-row-${visible[activeIdx].id}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            autoComplete="off"
            className="os-search-palette__input"
          />
        </div>

        {scopeLabel ? (
          <div
            className={[
              'os-search-palette__scope',
              focusMode === 'scope' ? 'os-search-palette__scope--focus' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            data-testid="os-palette-scope-row"
          >
            <span
              ref={chipRef}
              tabIndex={scopeCleared ? -1 : 0}
              className="os-search-palette__scope-chip"
              data-testid="os-palette-scope"
              title="Showing options for the current context only"
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  event.stopPropagation()
                  setScopeCleared(true)
                  onClearScope?.()
                  setFocusMode('rows')
                }
              }}
            >
              {scopeLabel}
            </span>
            <button
              type="button"
              ref={scopeClearRef}
              className="os-search-palette__scope-clear"
              data-testid="os-palette-scope-clear"
              aria-label={
                scopeCleared ? 'Scope removed — showing all configured options' : 'Remove scope and show all configured options'
              }
              aria-pressed={scopeCleared}
              onClick={() => {
                // The label promises 'restore scope' — make the toggle real.
                if (!scopeCleared) onClearScope?.()
                setScopeCleared(!scopeCleared)
              }}
            >
              {scopeCleared ? 'Showing all — restore scope' : 'Show all configured options ✕'}
            </button>
          </div>
        ) : null}

        {loading ? (
          <div
            className="os-routing-menu__loading"
            data-testid="routing-model-loading"
            role="status"
            aria-live="polite"
            aria-label="Loading..."
          >
            <span className="loading loading-spinner loading-sm" aria-hidden="true" />
            <span>Loading...</span>
          </div>
        ) : null}
        {!loading && warning ? (
          <div className="os-routing-menu__warning" data-testid="routing-model-warning" role="status">
            {warning.text}
            {warning.onAction ? (
              <button
                type="button"
                className="btn btn-xs btn-primary mt-1"
                data-testid="routing-model-warning-action"
                onClick={() => {
                  onClose()
                  warning.onAction?.()
                }}
              >
                {warning.actionLabel || 'Fix in Settings'}
              </button>
            ) : null}
          </div>
        ) : null}
        <ul
          id="os-model-results"
          role="listbox"
          aria-label="Models"
          className="os-search-palette__list"
        >
          {effectiveModels.length === 0 && !loading && !warning ? (
            <li className="os-search-empty">No models.</li>
          ) : emptySearch && !loading && !warning ? (
            <li className="os-search-empty">
              {query.trim() ? `No matches for “${query.trim()}”.` : 'No models.'}
            </li>
          ) : (
            groups.flatMap((group) => {
              const heading = (
                <li
                  key={`group-${group.name}`}
                  className="os-search-group"
                  role="presentation"
                  data-testid={`os-model-group-${group.name}`}
                >
                  {group.name}
                </li>
              )
              const rows = group.models.map((row) => {
                optionIndex += 1
                const idx = optionIndex
                const current = row.id === selectedId
                const isDefault = Boolean(defaultId) && row.id === defaultId
                return (
                  <li
                    key={row.id}
                    id={`os-model-row-${row.id}`}
                    role="option"
                    aria-selected={idx === activeIdx}
                    aria-current={current ? 'true' : undefined}
                    data-testid={`os-model-row-${row.id}`}
                    data-model-id={row.id}
                    data-current={current ? 'true' : 'false'}
                    data-default={isDefault ? 'true' : 'false'}
                    className={[
                      'os-search-row',
                      idx === activeIdx ? 'os-search-row--active' : '',
                      current ? 'os-search-row--current' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onMouseMove={() => setActiveIdx(idx)}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => choose(row)}
                  >
                    <span className="os-search-row__icon" aria-hidden="true">
                      {current ? <Check className="h-4 w-4" /> : null}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="os-search-row__name">{row.label}</span>
                      <span className="os-search-row__desc">
                        {row.description || row.id}
                        {row.tag ? ` · ${row.tag}` : ''}
                      </span>
                    </span>
                    {isDefault ? (
                      <span className="os-search-row__badge">Default</span>
                    ) : null}
                    {idx < 9 ? (
                      <kbd className="os-search-shortcut">{shortcutLabel(idx)}</kbd>
                    ) : null}
                  </li>
                )
              })
              return [heading, ...rows]
            })
          )}
        </ul>

        <div className="os-search-palette__footer" aria-label="Model palette actions">
          <span className="os-search-tip">
            <kbd className="kbd kbd-xs">↑↓</kbd> Navigate
          </span>
          <span className="os-search-tip">
            <kbd className="kbd kbd-xs">↵</kbd> Select
          </span>
          <span className="os-search-tip">
            <kbd className="kbd kbd-xs">Esc</kbd> Close
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-xs ml-auto text-primary"
            data-testid="os-model-manage-api"
            onClick={openManage}
          >
            <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
            {manageLabel || 'Manage API in Settings'}
          </button>
        </div>
      </div>
    </div>
  )
}
