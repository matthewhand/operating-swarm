/**
 * Routine Tools fieldset (#1403 defaults + #1406 extra tools + #1410 suggestions).
 *
 * Open Pull Request stays a checkbox (issue-trigger default). Additional
 * plugin/MCP tools are added from the existing catalog picker and can be
 * removed. Instruction-gap suggestions offer one-click add / dismiss and
 * never auto-enable a tool. Connector auth stays in Settings — never in
 * builder defaults.
 */
import { useEffect, useMemo, useState } from 'react'
import { Plus, X } from 'lucide-react'
import {
  catalogLabelFor,
  fallbackRoutineToolCatalog,
  fetchRoutineToolCatalog,
  type RoutineToolCatalogItem,
} from '../lib/routineToolCatalog'
import {
  ROUTINE_TOOL_CATALOG,
  TOOL_OPEN_PULL_REQUEST,
  extraRoutineTools,
  hasOpenPullRequestTool,
  type Routine,
  type RoutineTrigger,
} from '../lib/routines'
import { RoutineToolPicker } from './RoutineToolPicker'
import { RoutineToolSuggestions } from './RoutineToolSuggestions'

export interface RoutineToolsFieldsProps {
  tools: string[]
  onToggleOpenPullRequest: (enabled: boolean) => void
  onChangeTools?: (tools: string[]) => void
  disabled?: boolean
  catalog?: RoutineToolCatalogItem[]
  pickerOpen?: boolean
  instruction?: string
  trigger?: RoutineTrigger | null
  /** Proof harness only — pre-dismiss suggestions for a static frame. */
  suggestionDismissed?: Record<string, string>
}

export function toolsFromRoutine(routine: Pick<Routine, 'tools'> | null | undefined): string[] {
  return [...(routine?.tools || [])]
}

export function RoutineToolsFields({
  tools,
  onToggleOpenPullRequest,
  onChangeTools,
  disabled = false,
  catalog: catalogProp,
  pickerOpen: pickerOpenProp,
  instruction = '',
  trigger = null,
  suggestionDismissed,
}: RoutineToolsFieldsProps) {
  const builtin = ROUTINE_TOOL_CATALOG.find((row) => row.id === TOOL_OPEN_PULL_REQUEST)
  const checked = hasOpenPullRequestTool(tools)
  const extra = extraRoutineTools(tools)
  const [loadedCatalog, setLoadedCatalog] = useState<RoutineToolCatalogItem[] | null>(
    catalogProp ?? null,
  )
  const [pickerOpen, setPickerOpen] = useState(Boolean(pickerOpenProp))

  useEffect(() => {
    if (catalogProp) {
      setLoadedCatalog(catalogProp)
      return
    }
    let cancelled = false
    void fetchRoutineToolCatalog().then((items) => {
      if (!cancelled) setLoadedCatalog(items)
    })
    return () => {
      cancelled = true
    }
  }, [catalogProp])

  useEffect(() => {
    if (pickerOpenProp != null) setPickerOpen(pickerOpenProp)
  }, [pickerOpenProp])

  const catalog = useMemo(
    () => loadedCatalog ?? catalogProp ?? fallbackRoutineToolCatalog(),
    [loadedCatalog, catalogProp],
  )
  const openPrReason = catalog.find((item) => item.id === TOOL_OPEN_PULL_REQUEST)?.reason

  const changeTools = (next: string[]) => {
    onChangeTools?.(next)
  }

  const addSuggested = (toolId: string) => {
    if (toolId === TOOL_OPEN_PULL_REQUEST) {
      onToggleOpenPullRequest(true)
      return
    }
    if (tools.includes(toolId)) return
    changeTools([...tools, toolId])
  }

  return (
    <fieldset className="space-y-2" data-testid="routine-tools">
      <legend className="text-sm font-medium">Tools</legend>
      <RoutineToolSuggestions
        instruction={instruction}
        tools={tools}
        trigger={trigger}
        disabled={disabled}
        onAdd={addSuggested}
        initialDismissed={suggestionDismissed}
      />
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="checkbox checkbox-sm mt-0.5"
          aria-label="Open Pull Request"
          data-testid="routine-tool-open-pull-request"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onToggleOpenPullRequest(event.target.checked)}
        />
        <span>
          <span className="font-medium">{builtin?.label || 'Open Pull Request'}</span>
          <span className="block text-xs text-base-content/60">
            {builtin?.description || 'Open or update a GitHub pull request. Never auto-merges.'}
          </span>
          {openPrReason ? (
            <span className="block text-xs text-base-content/60" data-testid="routine-tool-open-pr-hint">
              {openPrReason}
            </span>
          ) : null}
        </span>
      </label>

      {extra.length > 0 ? (
        <ul className="os-routine-extra-tools space-y-1" data-testid="routine-tools-extra">
          {extra.map((id) => (
            <li
              key={id}
              className="flex items-center justify-between gap-2 rounded-box border border-base-300 bg-base-200/60 px-2 py-1.5 text-sm"
              data-testid={`routine-tool-chip-${id}`}
            >
              <span className="min-w-0">
                <span className="font-medium">{catalogLabelFor(catalog, id)}</span>
                <span className="ml-1 text-xs text-base-content/60">{id}</span>
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                aria-label={`Remove ${catalogLabelFor(catalog, id)}`}
                data-testid={`routine-tool-remove-${id}`}
                disabled={disabled}
                onClick={() => changeTools(tools.filter((item) => item !== id))}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-base-content/60" data-testid="routine-tools-extra-empty">
          No extra tools yet. Add a plugin or installed MCP connector.
        </p>
      )}

      <button
        type="button"
        className="btn btn-outline btn-sm"
        data-testid="routine-add-tool-or-mcp"
        disabled={disabled}
        onClick={() => setPickerOpen((open) => !open)}
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        Add Tool or MCP
      </button>

      {pickerOpen ? (
        <RoutineToolPicker
          tools={tools}
          catalog={catalog}
          onClose={() => setPickerOpen(false)}
          onAdd={(toolId) => {
            if (toolId === TOOL_OPEN_PULL_REQUEST) {
              onToggleOpenPullRequest(true)
              return
            }
            if (tools.includes(toolId)) return
            changeTools([...tools, toolId])
          }}
        />
      ) : null}
    </fieldset>
  )
}

export default RoutineToolsFields
