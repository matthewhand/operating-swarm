/**
 * Shared routine builder chrome (#1405).
 *
 * Maps Cursor-style builder controls onto OS concepts:
 * - Inactive / Active toggle = armed (`active`)
 * - Save persists a draft without requiring Active
 * - Test is a dry-run preview of trigger match + prompt
 * - Model picker sits next to Agent Instructions (`model`)
 *
 * Does not rebuild trigger chips (#1402) or Open PR defaults (#1403).
 */
import { useEffect, useMemo, useState } from 'react'
import { fetchLlmProfiles } from '../lib/api'
import {
  routineModelOptionIds,
  type RoutineDryRunPreview,
} from '../lib/routines'
import { Select, Textarea } from './DaisyUI'

export { resolveRoutinePreview } from '../lib/routines'

export const ROUTINE_DRY_RUN_NOTE =
  'Dry-run preview. No messages sent, no PRs merged, instruction not executed.'

const SEAT_DEFAULT = ''

export function RoutineArmedToggle({
  active,
  onChange,
  disabled = false,
}: {
  active: boolean
  onChange: (active: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className="os-routine-armed-toggle" data-testid="routine-armed-toggle">
      <span className={active ? 'os-routine-armed-toggle__off' : 'os-routine-armed-toggle__on'}>
        Inactive
      </span>
      <input
        type="checkbox"
        className="toggle toggle-sm"
        role="switch"
        aria-label="Armed"
        data-testid="routine-armed-switch"
        checked={active}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={active ? 'os-routine-armed-toggle__on' : 'os-routine-armed-toggle__off'}>
        Active
      </span>
    </label>
  )
}

export function useRoutineModelOptions(current?: string) {
  const [options, setOptions] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    void fetchLlmProfiles()
      .then((data) => {
        if (cancelled) return
        setOptions(routineModelOptionIds(data.profiles))
      })
      .catch(() => {
        if (!cancelled) setOptions([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  return useMemo(
    () => routineModelOptionIds(options.map((id) => ({ id })), current),
    [options, current],
  )
}

export function RoutineAgentInstructions({
  instruction,
  model,
  onInstructionChange,
  onModelChange,
  onInstructionBlur,
}: {
  instruction: string
  model?: string
  onInstructionChange: (value: string) => void
  onModelChange: (value: string) => void
  onInstructionBlur?: (value: string) => void
}) {
  const modelOptions = useRoutineModelOptions(model)

  return (
    <div className="os-routine-instructions" data-testid="routine-agent-instructions">
      <div className="os-routine-instructions__head">
        <span className="text-sm font-medium">Agent Instructions</span>
        <Select
          label="Model"
          size="sm"
          aria-label="Model"
          data-testid="routine-model-picker"
          value={model || SEAT_DEFAULT}
          onChange={(event) => onModelChange(event.target.value)}
        >
          <option value={SEAT_DEFAULT}>Seat default</option>
          {modelOptions.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </Select>
      </div>
      <Textarea
        size="sm"
        rows={4}
        aria-label="Agent Instructions"
        value={instruction}
        onChange={(event) => onInstructionChange(event.target.value)}
        onBlur={(event) => onInstructionBlur?.(event.target.value)}
      />
    </div>
  )
}

export function RoutineDryRunPreview({ preview }: { preview: RoutineDryRunPreview | null }) {
  if (!preview) return null
  return (
    <section
      className="os-routine-dry-run"
      data-testid="routine-dry-run-preview"
      aria-label="Routine test preview"
    >
      <h4 className="text-sm font-medium">Test preview</h4>
      <p className="text-xs text-base-content/70">{preview.note}</p>
      <dl className="os-routine-dry-run__grid">
        <div>
          <dt>Trigger match</dt>
          <dd data-testid="routine-dry-run-trigger">{preview.trigger_summary}</dd>
        </div>
        <div>
          <dt>Armed</dt>
          <dd>{preview.armed ? 'Active — would run if triggered' : 'Inactive — saved draft only'}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd data-testid="routine-dry-run-model">{preview.model || 'Seat default'}</dd>
        </div>
        <div>
          <dt>Prompt</dt>
          <dd data-testid="routine-dry-run-prompt">{preview.prompt || '(empty instruction)'}</dd>
        </div>
      </dl>
      <p className="text-xs text-base-content/50" data-testid="routine-dry-run-side-effects">
        Side effects: {preview.side_effects}
      </p>
    </section>
  )
}

