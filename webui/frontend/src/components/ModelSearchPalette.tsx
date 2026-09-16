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
}: ModelSearchPaletteProps) {
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const visible = useMemo(() => filterModelOptions(models, query), [models, query])
  const groups = useMemo(() => groupModelOptions(visible), [visible])

  useEffect(() => {
    setActiveIdx(0)
  }, [query, models, open])

  useEffect(() => {
    if (!open) return
    setQuery('')
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
        if (event.target instanceof HTMLButtonElement) return
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
  }, [choose, onClose, open])

  if (!open) return null

  const emptySearch = models.length > 0 && visible.length === 0
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

        <ul
          id="os-model-results"
          role="listbox"
          aria-label="Models"
          className="os-search-palette__list"
        >
          {models.length === 0 ? (
            <li className="os-search-empty">No models.</li>
          ) : emptySearch ? (
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
            Manage API in Settings
          </button>
        </div>
      </div>
    </div>
  )
}
