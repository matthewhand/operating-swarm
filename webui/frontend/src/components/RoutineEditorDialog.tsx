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
import { Button, Input, Select, Textarea, useOptionalToast } from './DaisyUI'
import {
  createRoutine,
  emptyTrigger,
  testRunRoutine,
  updateRoutine,
  type Routine,
  type RoutineTrigger,
  type RoutineTriggerKind,
} from '../lib/routines'

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
}

function ownerRepoOf(trigger: RoutineTrigger): string {
  return (trigger as { owner_repo?: string }).owner_repo || ''
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
        active: true,
        agent_id: prefill.agentId || agentId || 'api_agent',
        when_to_run: '',
        next_run: '',
        trigger,
        history: [],
      } as unknown as Routine
    }
    return null
  }, [draft, initial, open, prefill, agentId])

  const targetAgent = editing?.agent_id || prefill?.agentId || agentId || ''

  const saveField = async (patch: Partial<Routine>) => {
    if (!editing) return
    setEditingState({ ...editing, ...patch })
    if (!editing.id) return // unsaved draft — fields persist in the draft
    try {
      const updated = await updateRoutine(targetAgent, editing.id, patch)
      setEditingState(updated)
      onSaved?.(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save routine.')
    }
  }

  const setEditingState = (next: Routine) => setDraft(next)

  const handleCreate = async () => {
    if (!editing) return
    setBusy(true)
    setError(null)
    try {
      const created = await createRoutine(targetAgent || 'api_agent', {
        name: editing.name,
        instruction: editing.instruction,
        active: editing.active,
        trigger: editing.trigger,
      })
      notifySuccess('Routine created', created.name || 'New routine')
      onSaved?.(created)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create routine.')
    } finally {
      setBusy(false)
    }
  }

  const handleTestRun = async () => {
    if (!editing?.id || busy) return
    setBusy(true)
    try {
      await testRunRoutine(targetAgent, editing.id)
      notifySuccess('Test run started', editing.name || '')
    } catch (err) {
      notifyError('Test run failed', err instanceof Error ? err.message : 'Unknown error.')
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
      const { deleteRoutine } = await import('../lib/routines')
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

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            <span>Active</span>
            <input
              type="checkbox"
              className="toggle toggle-sm"
              role="switch"
              aria-label="Active"
              checked={editing.active}
              onChange={(event) => void saveField({ active: event.target.checked })}
            />
          </label>
          {editing.id ? (
            <>
              <Button type="button" size="sm" variant="ghost" onClick={() => void handleTestRun()} disabled={busy}>
                Test run
              </Button>
              <Button type="button" size="sm" color="error" variant="ghost" onClick={() => void handleDelete()}>
                {confirmDelete ? 'Confirm delete' : 'Delete'}
              </Button>
            </>
          ) : null}
        </div>

        <div className="mt-3 space-y-3">
          <Input
            label="Name"
            size="sm"
            value={editing.name}
            onChange={(event) => setEditingState({ ...editing, name: event.target.value })}
          />
          <Textarea
            label="Instruction"
            size="sm"
            rows={4}
            value={editing.instruction}
            onChange={(event) => setEditingState({ ...editing, instruction: event.target.value })}
          />

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">When to run</legend>
            <Select
              label="Trigger"
              size="sm"
              value={trigger.kind}
              onChange={(event) => {
                const next = emptyTrigger(event.target.value as RoutineTriggerKind)
                setEditingState({ ...editing, trigger: next })
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

            {trigger.kind === ROUTINE_TRIGGER_GITHUB_PR_MERGED ? (
              <Input
                label="Repository"
                size="sm"
                placeholder="owner/repo"
                value={ownerRepoOf(trigger)}
                onChange={(event) =>
                  setEditingState({
                    ...editing,
                    trigger: { ...trigger, owner_repo: event.target.value },
                  })
                }
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
            onClick={() => void handleCreate()}
          >
            {editing.id ? 'Save' : 'Create'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default RoutineEditorDialog
