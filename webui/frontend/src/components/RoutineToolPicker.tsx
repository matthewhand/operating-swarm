/**
 * + Add Tool or MCP picker (#1406).
 *
 * Lists built-in routine tools plus the existing plugin/MCP catalog.
 * Disabled rows show an honest reason. Tokens never appear.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Plug, Search, X } from 'lucide-react'
import {
  filterRoutineToolCatalog,
  type RoutineToolCatalogItem,
} from '../lib/routineToolCatalog'
import { extraRoutineTools, TOOL_OPEN_PULL_REQUEST } from '../lib/routines'

export interface RoutineToolPickerProps {
  tools: string[]
  catalog: RoutineToolCatalogItem[]
  onAdd: (toolId: string) => void
  onClose: () => void
}

function kindLabel(item: RoutineToolCatalogItem): string {
  if (item.kind === 'builtin') return 'Built-in'
  if (item.kind === 'mcp') return 'MCP connector'
  return item.server_name || 'Plugin'
}

export function RoutineToolPicker({ tools, catalog, onAdd, onClose }: RoutineToolPickerProps) {
  const [query, setQuery] = useState('')
  const selected = useMemo(() => new Set(tools), [tools])
  const rows = useMemo(() => filterRoutineToolCatalog(catalog, query), [catalog, query])
  const extraCount = extraRoutineTools(tools).length
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const node = rootRef.current
    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'nearest', behavior: 'auto' })
    }
  }, [])

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-label="Add Tool or MCP"
      data-testid="routine-tool-picker"
      className="os-routine-tool-picker rounded-box border border-base-300 bg-base-100 shadow"
    >
      <div className="flex items-center justify-between gap-2 border-b border-base-300 px-3 py-2">
        <p className="text-sm font-medium">Add Tool or MCP</p>
        <button
          type="button"
          className="btn btn-ghost btn-xs btn-square"
          aria-label="Close tool picker"
          data-testid="routine-tool-picker-close"
          onClick={onClose}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <p className="px-3 pt-2 text-xs text-base-content/60" data-testid="routine-tool-picker-hint">
        Same plugin/MCP catalog as chat. Connector tokens stay in Settings → Plugins
        ({extraCount} extra tool{extraCount === 1 ? '' : 's'} on this routine).
      </p>
      <label className="flex items-center gap-2 px-3 py-2">
        <Search className="h-4 w-4 text-base-content/50" aria-hidden="true" />
        <input
          type="search"
          className="input input-sm input-bordered w-full"
          placeholder="Search tools or connectors"
          aria-label="Search tools or MCP connectors"
          data-testid="routine-tool-picker-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      <ul className="os-routine-tool-picker__list max-h-64 overflow-y-auto" data-testid="routine-tool-picker-list">
        {rows.length === 0 ? (
          <li className="px-3 py-2 text-sm text-base-content/60">No matching tools.</li>
        ) : (
          rows.map((item) => {
            const added = selected.has(item.id)
            const disabled = !item.available || added
            const reason = item.reason
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className="os-search-row os-routine-tool-pick-row w-full text-left"
                  data-testid={`routine-tool-pick-${item.id}`}
                  data-available={item.available ? 'true' : 'false'}
                  data-added={added ? 'true' : 'false'}
                  disabled={disabled}
                  title={
                    added
                      ? `${item.label} is already on this routine`
                      : reason || `Add ${item.label}`
                  }
                  onClick={() => {
                    if (!item.available || added) return
                    onAdd(item.id)
                  }}
                >
                  <span className="os-search-row__icon" aria-hidden="true">
                    <Plug className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="os-search-row__name">{item.label}</span>
                    <span className="os-search-row__desc">
                      {kindLabel(item)}
                      {item.description ? ` · ${item.description}` : ''}
                    </span>
                    {!item.available && reason ? (
                      <span
                        className="os-routine-tool-reason block text-xs text-warning"
                        data-testid={`routine-tool-reason-${item.id}`}
                      >
                        {reason}
                      </span>
                    ) : null}
                    {item.id === TOOL_OPEN_PULL_REQUEST && item.reason && item.can_live === false ? (
                      <span className="block text-xs text-base-content/60">{item.reason}</span>
                    ) : null}
                  </span>
                  <span className="text-xs font-semibold text-base-content/70">
                    {added ? 'Added' : item.available ? 'Add' : 'Unavailable'}
                  </span>
                </button>
              </li>
            )
          })
        )}
      </ul>
    </div>
  )
}

export default RoutineToolPicker
