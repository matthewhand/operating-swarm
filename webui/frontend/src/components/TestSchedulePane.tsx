import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Clock, Plus, Timer } from 'lucide-react'
import { Button, Input, Select } from './DaisyUI'
import { useOptionalToast } from './DaisyUI/Toast'
import {
  createTestSchedule,
  deleteTestSchedule,
  fetchTestSchedules,
  formatDurationMs,
  formatRoutineHistoryTime,
  historySucceeded,
  runNowTestSchedule,
  updateTestSchedule,
  type TestSchedule,
  type TestScheduleTrigger,
} from '../lib/testSchedules'
import { emptyTrigger, triggerSummary, type RoutineTriggerKind } from '../lib/routines'

export interface TestSchedulePaneProps {
  nowMs?: number
}

type PaneView = 'list' | 'editor'

function asScheduleTrigger(kind: string): TestScheduleTrigger {
  const next = emptyTrigger(kind as RoutineTriggerKind)
  if (next.kind === 'interval' || next.kind === 'cron' || next.kind === 'one_shot') return next
  return { kind: 'interval', seconds: 3600 }
}

export function TestSchedulePane({ nowMs }: TestSchedulePaneProps) {
  const toast = useOptionalToast()
  const [view, setView] = useState<PaneView>('list')
  const [schedules, setSchedules] = useState<TestSchedule[]>([])
  const [editing, setEditing] = useState<TestSchedule | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setSchedules(await fetchTestSchedules())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load test schedules.')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const openEditor = (schedule: TestSchedule) => {
    setEditing(schedule)
    setConfirmDelete(false)
    setError(null)
    setView('editor')
  }

  const backToList = async () => {
    setView('list')
    setEditing(null)
    setConfirmDelete(false)
    await load()
  }

  const onAdd = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await createTestSchedule({ name: 'New test schedule' })
      setSchedules((prev) => [...prev, created])
      openEditor(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create test schedule.')
    } finally {
      setBusy(false)
    }
  }

  const onSaveField = async (patch: Parameters<typeof updateTestSchedule>[1]) => {
    if (!editing) return
    try {
      const updated = await updateTestSchedule(editing.id, patch)
      setEditing(updated)
      setSchedules((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save test schedule.')
    }
  }

  const onRunNow = async () => {
    if (!editing || busy) return
    setBusy(true)
    setError(null)
    try {
      const updated = await runNowTestSchedule(editing.id)
      setEditing(updated)
      setSchedules((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
      const latest = updated.history?.[0]
      if (latest && !historySucceeded(latest)) {
        toast?.error('Test schedule failed', latest.error || latest.summary || updated.name)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Run now failed.'
      setError(message)
      toast?.error('Test schedule failed', message)
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async () => {
    if (!editing) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setBusy(true)
    try {
      await deleteTestSchedule(editing.id)
      await backToList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete test schedule.')
    } finally {
      setBusy(false)
    }
  }

  const history = useMemo(() => {
    const rows = [...(editing?.history ?? [])]
    rows.sort((a, b) => String(b.ran_at).localeCompare(String(a.ran_at)))
    return rows
  }, [editing])

  const trigger = editing?.trigger

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="test-schedule-pane">
      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      {view === 'list' ? (
        <>
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-base font-semibold">Test schedule</h3>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Add test schedule"
              onClick={() => void onAdd()}
              disabled={busy}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {schedules.length === 0 ? (
            <p className="text-sm text-base-content/60">No test schedules yet.</p>
          ) : (
            <ul className="menu w-full rounded-box bg-base-200 p-0">
              {schedules.map((schedule) => {
                const latest = schedule.history?.[0]
                const failed = latest && !historySucceeded(latest)
                return (
                  <li key={schedule.id}>
                    <button
                      type="button"
                      className="flex items-start gap-3 text-left"
                      onClick={() => openEditor(schedule)}
                    >
                      <Timer className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="block font-medium">
                          {schedule.name}
                          {!schedule.active ? (
                            <span className="ml-2 text-xs font-normal text-base-content/50">Paused</span>
                          ) : null}
                          {failed ? (
                            <span className="badge badge-error badge-xs ml-2">Failed</span>
                          ) : null}
                        </span>
                        <span className="block text-xs text-base-content/60">
                          {schedule.when_to_run || triggerSummary(schedule.trigger)}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      ) : editing && trigger ? (
        <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="test-schedule-editor">
          <div className="flex items-center justify-between gap-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void backToList()}>
              Back
            </button>
            <h3 className="text-base font-semibold">Test schedule</h3>
            <span className="w-16" aria-hidden="true" />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm">
              <span>Active</span>
              <input
                type="checkbox"
                className="toggle toggle-sm"
                role="switch"
                aria-label="Active"
                checked={editing.active}
                onChange={(event) => void onSaveField({ active: event.target.checked })}
              />
            </label>
            <Button type="button" size="sm" variant="ghost" onClick={() => void onRunNow()} disabled={busy}>
              Run now
            </Button>
            <Button type="button" size="sm" color="error" variant="ghost" onClick={() => void onDelete()}>
              {confirmDelete ? 'Confirm delete' : 'Delete'}
            </Button>
          </div>

          <Input
            label="Name"
            size="sm"
            value={editing.name}
            onChange={(event) => setEditing({ ...editing, name: event.target.value })}
            onBlur={(event) => void onSaveField({ name: event.target.value })}
          />

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">When to run</legend>
            <Select
              label="Trigger"
              size="sm"
              value={trigger.kind}
              onChange={(event) => void onSaveField({ trigger: asScheduleTrigger(event.target.value) })}
            >
              <option value="interval">Interval</option>
              <option value="cron">Cron</option>
              <option value="one_shot">One-shot</option>
            </Select>
            {trigger.kind === 'interval' ? (
              <Input
                label="Every (seconds)"
                size="sm"
                type="number"
                min={1}
                value={String(trigger.seconds || 3600)}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    trigger: { kind: 'interval', seconds: Number(event.target.value) || 0 },
                  })
                }
                onBlur={(event) =>
                  void onSaveField({ trigger: { kind: 'interval', seconds: Number(event.target.value) || 3600 } })
                }
              />
            ) : null}
            {trigger.kind === 'cron' ? (
              <Input
                label="Cron expression"
                size="sm"
                placeholder="0 3 * * *"
                value={trigger.expression}
                onChange={(event) =>
                  setEditing({ ...editing, trigger: { kind: 'cron', expression: event.target.value } })
                }
                onBlur={(event) =>
                  void onSaveField({ trigger: { kind: 'cron', expression: event.target.value } })
                }
              />
            ) : null}
            {trigger.kind === 'one_shot' ? (
              <Input
                label="Run at"
                size="sm"
                placeholder="2026-09-16T03:00:00Z"
                value={trigger.run_at}
                onChange={(event) =>
                  setEditing({ ...editing, trigger: { kind: 'one_shot', run_at: event.target.value } })
                }
                onBlur={(event) =>
                  void onSaveField({ trigger: { kind: 'one_shot', run_at: event.target.value } })
                }
              />
            ) : null}
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Target</legend>
            <Select
              label="Target kind"
              size="sm"
              value={editing.target?.kind || 'fleet'}
              onChange={(event) =>
                void onSaveField({
                  target:
                    event.target.value === 'agent'
                      ? { kind: 'agent', agent_id: editing.target?.agent_id || '' }
                      : { kind: 'fleet', fleet: editing.target?.fleet || 'all' },
                })
              }
            >
              <option value="fleet">Fleet subset</option>
              <option value="agent">Agent / seat</option>
            </Select>
            {editing.target?.kind === 'agent' ? (
              <Input
                label="Agent"
                size="sm"
                value={editing.target.agent_id || ''}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    target: { kind: 'agent', agent_id: event.target.value },
                  })
                }
                onBlur={(event) =>
                  void onSaveField({ target: { kind: 'agent', agent_id: event.target.value } })
                }
              />
            ) : (
              <Input
                label="Fleet"
                size="sm"
                value={editing.target?.fleet || 'all'}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    target: { kind: 'fleet', fleet: event.target.value },
                  })
                }
                onBlur={(event) =>
                  void onSaveField({ target: { kind: 'fleet', fleet: event.target.value || 'all' } })
                }
              />
            )}
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Check</legend>
            <Select
              label="Check kind"
              size="sm"
              value={editing.check?.kind || 'script'}
              onChange={(event) =>
                void onSaveField({
                  check: { kind: event.target.value, name: editing.check?.name || event.target.value },
                })
              }
            >
              <option value="harness_health">Harness health</option>
              <option value="blueprint_smoke">Blueprint smoke</option>
              <option value="script">Fleet proof script</option>
              <option value="remote_harness">Remote harness</option>
            </Select>
            <Input
              label="Check name"
              size="sm"
              value={editing.check?.name || ''}
              onChange={(event) =>
                setEditing({
                  ...editing,
                  check: { kind: editing.check?.kind || 'script', name: event.target.value },
                })
              }
              onBlur={(event) =>
                void onSaveField({
                  check: { kind: editing.check?.kind || 'script', name: event.target.value },
                })
              }
            />
          </fieldset>

          <section aria-label="Test schedule history" className="space-y-2">
            <h4 className="text-sm font-medium">History</h4>
            {history.length === 0 ? (
              <p className="text-sm text-base-content/60">No runs yet.</p>
            ) : (
              <ul className="space-y-2">
                {history.map((row) => {
                  const ok = historySucceeded(row)
                  return (
                    <li key={row.id} className="flex items-start gap-2 text-sm">
                      {ok ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                      ) : (
                        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-error" aria-hidden="true" />
                      )}
                      <span className="min-w-0">
                        <span className="block">
                          {formatRoutineHistoryTime(row.ran_at, nowMs)}
                          {row.duration_ms != null ? (
                            <span className="ml-2 text-xs text-base-content/60">
                              {formatDurationMs(row.duration_ms)}
                            </span>
                          ) : null}
                          {row.token_cost ? (
                            <span className="ml-2 text-xs text-base-content/60">{row.token_cost} tok</span>
                          ) : null}
                        </span>
                        {row.error || row.summary ? (
                          <span className="block text-xs text-base-content/60">{row.error || row.summary}</span>
                        ) : null}
                        {row.artifact?.url ? (
                          <a className="link text-xs" href={row.artifact.url}>
                            {row.artifact.label || row.artifact.kind || 'Artifact'}
                          </a>
                        ) : null}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
          {editing.next_run ? (
            <p className="flex items-center gap-1 text-xs text-base-content/60">
              <Clock className="h-3 w-3" aria-hidden="true" />
              Next run {editing.next_run}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export default TestSchedulePane
