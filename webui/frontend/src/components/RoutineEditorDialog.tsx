/**
 * Shared routine editor dialog (#513).
 *
 * One editor in the codebase: extracted from ComputerRoutinesPane's inline
 * editor so the calendar's `+` and the pane drive the same fields. Opened
 * with `initial` (an existing routine) or `prefill` ({ date, agentId }) —
 * a date prefill means a one-shot `run_at` on that date, since a single
 * date is only expressible there (issue #513 scope 3).
 */
import { useMemo, useState } from 'react'
import { Clock, X } from 'lucide-react'
import { Button, Input, Select, useOptionalToast } from './DaisyUI'
import { GithubTriggerComposer } from './GithubTriggerComposer'
import { githubTriggerSaveError, isGithubRoutineTrigger } from '../lib/githubTriggerComposer'
import {
  RoutineAgentInstructions,
  RoutineArmedToggle,
  RoutineDryRunPreview,
  resolveRoutinePreview,
} from './RoutineBuilderChrome'
import {
  createRoutine,
  defaultToolsForTrigger,
  deleteRoutine,
  emptyTrigger,
  effectiveRoutineTools,
  isDuplicateRoutineError,
  mergeRoutineSave,
  previewRoutineDryRun,
  routineDraftWrite,
  testRunRoutine,
  toggleOpenPullRequestTool,
  updateRoutine,
  type Routine,
  type RoutineDryRunPreview as DryRunPreview,
  type RoutineTrigger,
  type RoutineTriggerKind,
} from '../lib/routines'
import { RoutineToolsFields } from './RoutineToolsFields'
import { routineEnableGate } from '../lib/routinePack'

const ROUTINE_TRIGGER_GITHUB_PR_MERGED = 'github_pr_merged'
const ROUTINE_TRIGGER_GITHUB_EVENT = 'github_event'
const ROUTINE_TRIGGER_INTERVAL = 'interval'
const ROUTINE_TRIGGER_CRON = 'cron'
const ROUTINE_TRIGGER_ONE_SHOT = 'one_shot'
const ROUTINE_TRIGGER_MAILBOX_MESSAGE = 'mailbox_message'

export interface RoutineEditorDialogProps {
  open: boolean
  onClose: () => void
  /** Existing routine to edit; omit when creating from a prefill. */
  initial?: Routine | null
  /** Creation prefill: the day's `YYYY-MM-DD` and the seat's agent id. */
  prefill?: { date?: string; agentId?: string } | null
  /** Called with the saved routine after create/update. */
  onSaved?: (routine: Routine) => void
  /** Default agent id when creating without a prefill. */
  agentId?: string
  /** Proof harness only — open the + Add Tool or MCP picker (#1406). */
  toolsPickerOpen?: boolean
  /** Proof harness only — pre-dismiss instruction-gap suggestions (#1410). */
  suggestionDismissed?: Record<string, string>
}

/** Local ISO timestamp at mid-morning on the given YYYY-MM-DD. */
function dateKeyToRunAt(dateKey: string): string {
  return `${dateKey}T09:00:00`
}

export function RoutineEditorDialog({
  open,
  onClose,
  initial = null,
  prefill = null,
  onSaved,
  agentId,
  toolsPickerOpen = false,
  suggestionDismissed,
}: RoutineEditorDialogProps) {
  // Optional toast: the dialog must render inside hosts that do not mount a
  // ToastProvider (e.g. the calendar overlay in isolated tests).
  const toast = useOptionalToast()
  const notifySuccess = (title: string, message: string) => toast?.success(title, message)
  const notifyError = (title: string, message: string) => toast?.error(title, message)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [draft, setDraft] = useState<Routine | null>(null)
  const [preview, setPreview] = useState<DryRunPreview | null>(null)
  // #1316 — the conflicting routine when the server blocks a twin.
  const [conflictRoutine, setConflictRoutine] = useState<Routine | null>(null)

  const editing = useMemo<Routine | null>(() => {
    if (draft) return draft
    if (initial) return initial
    if (open && prefill) {
      const trigger: RoutineTrigger = prefill.date
        ? { kind: ROUTINE_TRIGGER_ONE_SHOT, run_at: dateKeyToRunAt(prefill.date) }
        : emptyTrigger(ROUTINE_TRIGGER_GITHUB_PR_MERGED)
      return {
        id: '',
        name: 'New routine',
        instruction: '',
        active: false,
        model: '',
        agent_id: prefill.agentId || agentId || 'api_agent',
        when_to_run: '',
        next_run: '',
        trigger,
        tools: defaultToolsForTrigger(trigger),
        tools_explicit: false,
        history: [],
      } as unknown as Routine
    }
    return null
  }, [draft, initial, open, prefill, agentId])

  const targetAgent = editing?.agent_id || prefill?.agentId || agentId || ''

  const saveField = async (patch: Partial<Routine>, local?: Partial<Routine>) => {
    if (!editing) return
    const routineId = editing.id
    const previous = editing
    setConflictRoutine(null)
    // `local` is optimistic UI only. The API rejects unknown keys such as tools_explicit.
    setDraft((current) => {
      const base = current ?? editing
      return { ...base, ...patch, ...local }
    })
    if (!routineId) return // unsaved draft — fields persist in the draft
    try {
      const updated = await updateRoutine(targetAgent, routineId, patch)
      setDraft((current) => {
        const base = current ?? { ...editing, ...patch, ...local }
        if (base.id !== updated.id) return current
        return mergeRoutineSave(base, updated, patch)
      })
      onSaved?.(updated)
    } catch (err) {
      // Revert only this save's fields. A full draft reset would drop a name
      // or instruction edit the operator made while the PATCH was in flight.
      setDraft((current) => {
        if (!current) return previous
        const localPatch = { ...patch, ...local }
        const optimistic = { ...previous, ...localPatch }
        const keys = Object.keys(localPatch) as (keyof Routine)[]
        const stillOurs = keys.every((key) => Object.is(current[key], optimistic[key]))
        if (!stillOurs) return current
        const reverted = { ...current }
        for (const key of keys) {
          ;(reverted as unknown as Record<string, unknown>)[key] = (
            previous as unknown as Record<string, unknown>
          )[key]
        }
        return reverted
      })
      setError(err instanceof Error ? err.message : 'Could not save routine.')
    }
  }

  const setEditingState = (next: Routine) => {
    // Any edit invalidates a previous duplicate warning.
    setConflictRoutine(null)
    setDraft(next)
  }

  const handleSave = async ({ allowDuplicate = false }: { allowDuplicate?: boolean } = {}) => {
    if (!editing) return
    const triggerProblem = githubTriggerSaveError(editing.trigger)
    if (triggerProblem) {
      setError(triggerProblem)
      return
    }
    setBusy(true)
    setError(null)
    setConflictRoutine(null)
    const write = routineDraftWrite(editing)
    try {
      if (editing.id) {
        const updated = await updateRoutine(targetAgent, editing.id, write)
        setEditingState(updated)
        notifySuccess('Routine saved', updated.name || 'Routine')
        onSaved?.(updated)
        return
      }
      const created = await createRoutine(targetAgent || 'api_agent', {
        ...write,
        ...(editing.tools_explicit ? { tools: effectiveRoutineTools(editing) } : {}),
        allow_duplicate: allowDuplicate,
      })
      notifySuccess('Routine saved', created.name || 'New routine')
      onSaved?.(created)
      onClose()
    } catch (err) {
      if (isDuplicateRoutineError(err)) {
        // Honest "already exists" instead of a silent twin (#1316).
        setConflictRoutine(err.existingRoutine)
        return
      }
      setError(err instanceof Error ? err.message : 'Could not save routine.')
    } finally {
      setBusy(false)
    }
  }

  const openExisting = () => {
    if (!conflictRoutine) return
    notifySuccess('Routine already exists', conflictRoutine.name || '')
    onSaved?.(conflictRoutine)
    onClose()
  }

  const handleTestRun = async () => {
    if (!editing || busy) return
    setBusy(true)
    try {
      if (!editing.id) {
        setPreview(previewRoutineDryRun(editing))
        notifySuccess('Test preview', 'Dry-run only — no messages sent.')
        return
      }
      const result = await testRunRoutine(targetAgent, editing.id)
      setPreview(resolveRoutinePreview(editing, result))
      notifySuccess('Test preview', 'Dry-run only — no messages sent.')
    } catch (err) {
      notifyError('Test preview failed', err instanceof Error ? err.message : 'Unknown error.')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    if (!editing?.id) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setBusy(true)
    try {
      await deleteRoutine(targetAgent, editing.id)
      notifySuccess('Routine deleted', editing.name || '')
      onSaved?.(editing)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete routine.')
    } finally {
      setBusy(false)
    }
  }

  if (!open || !editing) return null
  const trigger = editing.trigger
  const enableGate = routineEnableGate(editing)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      data-testid="routine-editor-dialog"
      role="dialog"
      aria-modal="true"
      aria-label={editing.id ? `Edit routine ${editing.name}` : 'New routine'}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-box bg-base-100 p-4 shadow-xl">
        <div className="flex items-center justify-between gap-2 pb-2">
          <h3 className="text-base font-semibold">
            {editing.id ? 'Routine' : 'New routine'}
          </h3>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            aria-label="Close routine editor"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {error ? (
          <p className="mb-2 text-sm text-error" role="alert">
            {error}
          </p>
        ) : null}

        {conflictRoutine ? (
          <div
            className="mb-2 flex flex-wrap items-center gap-2 rounded-box bg-base-200 p-2"
            data-testid="routine-duplicate-conflict"
            role="alert"
          >
            <span className="text-sm">
              A routine with the same name, instruction, and trigger already exists.
            </span>
            <Button type="button" size="sm" variant="ghost" onClick={openExisting}>
              Open existing
            </Button>
            <Button
              type="button"
              size="sm"
              color="warning"
              data-testid="routine-create-anyway"
              onClick={() => void handleSave({ allowDuplicate: true })}
            >
              Create anyway
            </Button>
          </div>
        ) : null}

        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <RoutineArmedToggle
              active={editing.active}
              disabled={enableGate.blocked}
              onChange={(active) => {
                if (enableGate.blocked && active) return
                void saveField({ active })
              }}
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              data-testid="routine-editor-test"
              onClick={() => void handleTestRun()}
              disabled={busy}
            >
              Test
            </Button>
            {editing.id ? (
              <Button type="button" size="sm" color="error" variant="ghost" onClick={() => void handleDelete()}>
                {confirmDelete ? 'Confirm delete' : 'Delete'}
              </Button>
            ) : null}
          </div>
          {enableGate.message ? (
            <p id="routine-enable-gated" className="text-xs text-base-content/60" data-testid="routine-enable-gated">
              {enableGate.message}
            </p>
          ) : null}
        </div>

        <div className="mt-3 space-y-3">
          <Input
            label="Name"
            size="sm"
            value={editing.name}
            onChange={(event) => setEditingState({ ...editing, name: event.target.value })}
          />
          <RoutineAgentInstructions
            instruction={editing.instruction}
            model={editing.model}
            onInstructionChange={(instruction) => setEditingState({ ...editing, instruction })}
            onModelChange={(model) => setEditingState({ ...editing, model })}
          />

          <RoutineDryRunPreview preview={preview} />

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">When to run</legend>
            <Select
              label="Trigger"
              size="sm"
              value={trigger.kind}
              onChange={(event) => {
                const next = emptyTrigger(event.target.value as RoutineTriggerKind)
                const tools = editing.tools_explicit
                  ? effectiveRoutineTools(editing)
                  : defaultToolsForTrigger(next)
                setEditingState({ ...editing, trigger: next, tools })
              }}
            >
              <option value={ROUTINE_TRIGGER_GITHUB_PR_MERGED}>When a PR merges</option>
              <option value={ROUTINE_TRIGGER_GITHUB_EVENT}>GitHub event</option>
              <option value={ROUTINE_TRIGGER_INTERVAL}>Interval</option>
              <option value={ROUTINE_TRIGGER_CRON}>Cron</option>
              <option value={ROUTINE_TRIGGER_ONE_SHOT}>One-shot</option>
              <option value={ROUTINE_TRIGGER_MAILBOX_MESSAGE}>Mailbox message</option>
            </Select>

            {trigger.kind === ROUTINE_TRIGGER_ONE_SHOT ? (
              <Input
                label="Run at"
                size="sm"
                placeholder="2026-09-16T03:00:00Z"
                value={trigger.run_at}
                onChange={(event) =>
                  setEditingState({
                    ...editing,
                    trigger: { kind: ROUTINE_TRIGGER_ONE_SHOT, run_at: event.target.value },
                  })
                }
              />
            ) : null}

            {trigger.kind === ROUTINE_TRIGGER_INTERVAL ? (
              <Input
                label="Every (seconds)"
                size="sm"
                type="number"
                min={1}
                value={String(trigger.seconds || 3600)}
                onChange={(event) =>
                  setEditingState({
                    ...editing,
                    trigger: { kind: ROUTINE_TRIGGER_INTERVAL, seconds: Number(event.target.value) || 0 },
                  })
                }
              />
            ) : null}

            {trigger.kind === ROUTINE_TRIGGER_CRON ? (
              <Input
                label="Cron expression"
                size="sm"
                placeholder="0 3 * * *"
                value={trigger.expression}
                onChange={(event) =>
                  setEditingState({
                    ...editing,
                    trigger: { kind: ROUTINE_TRIGGER_CRON, expression: event.target.value },
                  })
                }
              />
            ) : null}

            {isGithubRoutineTrigger(trigger) ? (
              <GithubTriggerComposer
                trigger={trigger}
                onChange={(next) => setEditingState({ ...editing, trigger: next })}
              />
            ) : null}

            {trigger.kind === ROUTINE_TRIGGER_MAILBOX_MESSAGE ? (
              <>
                <Input
                  label="Sender"
                  size="sm"
                  placeholder="anyone"
                  value={trigger.sender}
                  onChange={(event) =>
                    setEditingState({
                      ...editing,
                      trigger: { ...trigger, sender: event.target.value },
                    })
                  }
                />
                <Input
                  label="Pattern"
                  size="sm"
                  placeholder="substring match"
                  value={trigger.pattern}
                  onChange={(event) =>
                    setEditingState({
                      ...editing,
                      trigger: { ...trigger, pattern: event.target.value },
                    })
                  }
                />
              </>
            ) : null}
          </fieldset>

          <RoutineToolsFields
            tools={effectiveRoutineTools(editing)}
            instruction={editing.instruction}
            trigger={editing.trigger}
            onToggleOpenPullRequest={(enabled) => {
              const tools = toggleOpenPullRequestTool(effectiveRoutineTools(editing), enabled)
              if (editing.id) {
                // tools_explicit stays off the wire; without it locally the checkbox
                // keeps the trigger default and the uncheck looks ignored.
                void saveField({ tools }, { tools_explicit: true })
                return
              }
              setEditingState({ ...editing, tools, tools_explicit: true })
            }}
            onChangeTools={(tools) => {
              if (editing.id) {
                void saveField({ tools }, { tools_explicit: true })
                return
              }
              setEditingState({ ...editing, tools, tools_explicit: true })
            }}
            pickerOpen={toolsPickerOpen || undefined}
            suggestionDismissed={suggestionDismissed}
          />

          {editing.next_run ? (
            <p className="flex items-center gap-1 text-xs text-base-content/60">
              <Clock className="h-3 w-3" aria-hidden="true" />
              Next run {editing.next_run}
            </p>
          ) : null}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            variant="primary"
            loading={busy}
            data-testid="routine-editor-save"
            onClick={() => void handleSave()}
          >
            Save
          </Button>
        </div>
      </div>
    </div>
  )
}

export default RoutineEditorDialog
