/**
 * Missing-tool suggestions from Agent Instructions (#1410).
 *
 * One-click Add is the operator confirm. Nothing auto-enables — including
 * destructive tools (Open Pull Request). Dismiss lasts for this draft
 * until the instruction fingerprint changes materially.
 */
import { useMemo, useState } from 'react'
import {
  instructionFingerprint,
  visibleToolSuggestions,
  type RoutineToolSuggestion,
} from '../lib/routineToolSuggestions'
import type { RoutineTrigger } from '../lib/routines'

export interface RoutineToolSuggestionsProps {
  instruction: string
  tools: string[]
  trigger?: RoutineTrigger | null
  onAdd: (toolId: string) => void
  disabled?: boolean
  /** Proof harness only — pre-dismiss a tool for a static frame. */
  initialDismissed?: Record<string, string>
}

export function RoutineToolSuggestions({
  instruction,
  tools,
  trigger = null,
  onAdd,
  disabled = false,
  initialDismissed,
}: RoutineToolSuggestionsProps) {
  const fingerprint = instructionFingerprint(instruction, trigger)
  const [dismissed, setDismissed] = useState<Record<string, string>>(initialDismissed || {})

  const rows = useMemo(
    () => visibleToolSuggestions(instruction, tools, trigger, dismissed),
    [instruction, tools, trigger, dismissed],
  )

  if (rows.length === 0) return null

  const dismiss = (row: RoutineToolSuggestion) => {
    setDismissed((prev) => ({ ...prev, [row.id]: fingerprint }))
  }

  return (
    <div
      className="os-routine-tool-suggestions space-y-2"
      data-testid="routine-tool-suggestions"
      role="region"
      aria-label="Suggested tools"
    >
      <p className="text-xs font-medium text-base-content/70">Suggested tools</p>
      {rows.map((row) => (
        <div
          key={row.id}
          className="os-routine-tool-suggest rounded-box border border-base-300 bg-base-200/70 px-2 py-2"
          data-testid={`routine-tool-suggest-${row.id}`}
          data-destructive={row.destructive ? 'true' : 'false'}
        >
          <p className="text-sm" data-testid={`routine-tool-suggest-reason-${row.id}`}>
            {row.reason}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-primary btn-xs"
              data-testid={`routine-tool-suggest-add-${row.id}`}
              aria-label={`Add ${row.label}`}
              disabled={disabled}
              onClick={() => onAdd(row.id)}
            >
              Add {row.label}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              data-testid={`routine-tool-suggest-dismiss-${row.id}`}
              aria-label={`Dismiss ${row.label} suggestion`}
              disabled={disabled}
              onClick={() => dismiss(row)}
            >
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default RoutineToolSuggestions
