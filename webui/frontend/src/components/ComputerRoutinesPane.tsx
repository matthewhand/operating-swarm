import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, Clock, GitMerge, Mail, Plus, Timer } from 'lucide-react'
import { Button, Input, Select, Textarea } from './DaisyUI'
import {
  createRoutine,
  deleteRoutine,
  emptyTrigger,
  fetchRoutines,
  formatDurationMs,
  formatRoutineHistoryTime,
  GITHUB_EVENT_TYPES,
  historySucceeded,
  ROUTINE_ACTOR_ANYONE,
  ROUTINE_EVENT_MERGED,
  ROUTINE_TRIGGER_CRON,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  ROUTINE_TRIGGER_INTERVAL,
  ROUTINE_TRIGGER_MAILBOX_MESSAGE,
  ROUTINE_TRIGGER_ONE_SHOT,
  runNowRoutine,
  testRunRoutine,
  triggerSummary,
  updateRoutine,
  type Routine,
  type RoutineTrigger,
  type RoutineTriggerKind,
} from '../lib/routines'

export interface ComputerRoutinesPaneProps {
  agentId: string
  agentName: string
  /** True only when a real computer-control session exists. Tests stay false. */
  hasScreenSession?: boolean
  nowMs?: number
  showThumbnail?: boolean
}

type PaneView = 'list' | 'editor'

function triggerIcon(kind: string | undefined) {
  if (kind === ROUTINE_TRIGGER_MAILBOX_MESSAGE) return Mail
  if (kind === ROUTINE_TRIGGER_INTERVAL || kind === ROUTINE_TRIGGER_CRON || kind === ROUTINE_TRIGGER_ONE_SHOT) {
    return Timer
  }
  return GitMerge
}

function ownerRepoOf(trigger: RoutineTrigger): string {
  if ('owner_repo' in trigger) return trigger.owner_repo || ''
  return ''
}

export function ComputerRoutinesPane({
  agentId,
  agentName,
  hasScreenSession = false,
  nowMs,
  showThumbnail = true,
}: ComputerRoutinesPaneProps) {
  const [view, setView] = useState<PaneView>('list')
  const [editing, setEditing] = useState<Routine | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const screenCaption = `${agentName || 'Agent'}'s screen`

  // #760: routines live in TanStack Query — cached per agent, deduped across
  // remounts, and invalidated (not re-fetched ad hoc) after every mutation.
  const routinesQuery = useQuery({
    queryKey: ['routines', agentId],
    queryFn: () => fetchRoutines(agentId),
    enabled: Boolean(agentId),
    staleTime: 15_000,
  })
  const routines = useMemo(() => routinesQuery.data ?? [], [routinesQuery.data])

  useEffect(() => {
    if (routinesQuery.error) {
      setError(
        routinesQuery.error instanceof Error
          ? routinesQuery.error.message
          : 'Could not load routines.',
      )
    } else {
      setError(null)
    }
  }, [routinesQuery.error])

  const refreshRoutines = () => {
    void queryClient.invalidateQueries({ queryKey: ['routines', agentId] })
  }

  const load = async () => {
    refreshRoutines()
  }

  useEffect(() => {
    void load()
    setView('list')
    setEditing(null)
    setConfirmDelete(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId])

  const openEditor = (routine: Routine) => {
    setEditing(routine)
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
    if (!agentId || busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await createRoutine(agentId, { name: 'New routine' })
      refreshRoutines()
      openEditor(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create routine.')
    } finally {
      setBusy(false)
    }
  }

  const onSaveField = async (patch: Parameters<typeof updateRoutine>[2]) => {
    if (!agentId || !editing) return
    try {
      const updated = await updateRoutine(agentId, editing.id, patch)
      setEditing(updated)
      refreshRoutines()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save routine.')
    }
  }

  const onChangeKind = async (kind: RoutineTriggerKind) => {
    if (!editing) return
    const next = emptyTrigger(kind)
    setEditing({ ...editing, trigger: next })
    await onSaveField({ trigger: next })
  }

  const onTestRun = async () => {
    if (!agentId || !editing || busy) return
    setBusy(true)
    setError(null)
    try {
      const updated = await testRunRoutine(agentId, editing.id)
      setEditing(updated)
      refreshRoutines()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test run failed.')
    } finally {
      setBusy(false)
    }
  }

  const onRunNow = async () => {
    if (!agentId || !editing || busy) return
    setBusy(true)
    setError(null)
    try {
      const updated = await runNowRoutine(agentId, editing.id)
      setEditing(updated)
      refreshRoutines()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run now failed.')
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async () => {
    if (!agentId || !editing) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setBusy(true)
    try {
      await deleteRoutine(agentId, editing.id)
      await backToList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete routine.')
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
    <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="computer-routines-pane">
      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      {view === 'list' ? (
        <>
          {showThumbnail ? (
            <figure className="space-y-2" data-testid="agent-screen-thumbnail">
              <div
                className="flex aspect-video w-full items-center justify-center rounded-box border border-base-300 bg-base-200 text-sm text-base-content/60"
                role="img"
                aria-label={screenCaption}
              >
                {hasScreenSession ? 'Last frame' : 'No screen session'}
              </div>
              <figcaption className="text-sm text-base-content/70">{screenCaption}</figcaption>
            </figure>
          ) : null}

          <div className="flex items-center justify-between gap-2">
            <h3 className="text-base font-semibold">Routines</h3>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Add routine"
              onClick={() => void onAdd()}
              disabled={busy || !agentId}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          {routinesQuery.isLoading ? (
            <p className="text-sm text-base-content/60">Loading routines…</p>
          ) : routines.length === 0 ? (
            <p className="text-sm text-base-content/60">No routines yet.</p>
          ) : (
            <ul className="menu w-full rounded-box bg-base-200 p-0">
              {routines.map((routine) => {
                const Icon = triggerIcon(routine.trigger?.kind)
                return (
                  <li key={routine.id}>
                    <button
                      type="button"
                      className="flex items-start gap-3 text-left"
                      onClick={() => openEditor(routine)}
                    >
                      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="block font-medium">
                          {routine.name}
                          {!routine.active ? (
                            <span className="ml-2 text-xs font-normal text-base-content/50">Paused</span>
                          ) : null}
                        </span>
                        <span className="block text-xs text-base-content/60">
                          {routine.when_to_run || triggerSummary(routine.trigger)}
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
        <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="routine-editor">
          <div className="flex items-center justify-between gap-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void backToList()}>
              Back
            </button>
            <h3 className="text-base font-semibold">Routine</h3>
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
            <Button type="button" size="sm" variant="ghost" onClick={() => void onTestRun()} disabled={busy}>
              Test run
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
          <Textarea
            label="Instruction"
            size="sm"
            rows={4}
            value={editing.instruction}
            onChange={(event) => setEditing({ ...editing, instruction: event.target.value })}
            onBlur={(event) => void onSaveField({ instruction: event.target.value })}
          />

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">When to run</legend>
            <Select
              label="Trigger"
              size="sm"
              value={trigger.kind}
              onChange={(event) => void onChangeKind(event.target.value as RoutineTriggerKind)}
            >
              <option value={ROUTINE_TRIGGER_GITHUB_PR_MERGED}>When a PR merges</option>
              <option value={ROUTINE_TRIGGER_GITHUB_EVENT}>GitHub event</option>
              <option value={ROUTINE_TRIGGER_INTERVAL}>Interval</option>
              <option value={ROUTINE_TRIGGER_CRON}>Cron</option>
              <option value={ROUTINE_TRIGGER_ONE_SHOT}>One-shot</option>
              <option value={ROUTINE_TRIGGER_MAILBOX_MESSAGE}>Mailbox message</option>
            </Select>

            {trigger.kind === ROUTINE_TRIGGER_GITHUB_PR_MERGED ? (
              <>
                <Input
                  label="Repository"
                  size="sm"
                  placeholder="owner/repo"
                  value={ownerRepoOf(trigger)}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      trigger: { ...trigger, owner_repo: event.target.value },
                    })
                  }
                  onBlur={(event) =>
                    void onSaveField({
                      trigger: { ...trigger, owner_repo: event.target.value },
                    })
                  }
                />
                <Input label="Event" size="sm" value="Merged" readOnly />
                <Input
                  label="Actor"
                  size="sm"
                  value={trigger.actor || ROUTINE_ACTOR_ANYONE}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      trigger: { ...trigger, actor: event.target.value || ROUTINE_ACTOR_ANYONE },
                    })
                  }
                  onBlur={(event) =>
                    void onSaveField({
                      trigger: {
                        ...trigger,
                        actor: event.target.value || ROUTINE_ACTOR_ANYONE,
                        event: ROUTINE_EVENT_MERGED,
                      },
                    })
                  }
                />
              </>
            ) : null}

            {trigger.kind === ROUTINE_TRIGGER_GITHUB_EVENT ? (
              <>
                <Input
                  label="Repository"
                  size="sm"
                  placeholder="owner/repo"
                  value={trigger.owner_repo}
                  onChange={(event) =>
                    setEditing({ ...editing, trigger: { ...trigger, owner_repo: event.target.value } })
                  }
                  onBlur={(event) =>
                    void onSaveField({ trigger: { ...trigger, owner_repo: event.target.value } })
                  }
                />
                <Select
                  label="Event type"
                  size="sm"
                  value={trigger.event_type}
                  onChange={(event) =>
                    void onSaveField({ trigger: { ...trigger, event_type: event.target.value } })
                  }
                >
                  {GITHUB_EVENT_TYPES.map((eventType) => (
                    <option key={eventType} value={eventType}>
                      {eventType}
                    </option>
                  ))}
                </Select>
                <Input
                  label="Labels"
                  size="sm"
                  placeholder="bug, triage"
                  value={(trigger.filters?.labels || []).join(', ')}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      trigger: {
                        ...trigger,
                        filters: {
                          ...trigger.filters,
                          labels: event.target.value.split(',').map((item) => item.trim()).filter(Boolean),
                        },
                      },
                    })
                  }
                  onBlur={(event) => {
                    const labels = event.target.value
                      .split(',')
                      .map((item) => item.trim())
                      .filter(Boolean)
                    void onSaveField({
                      trigger: { ...trigger, filters: { ...trigger.filters, labels } },
                    })
                  }}
                />
                <Input
                  label="Branch"
                  size="sm"
                  placeholder="main"
                  value={trigger.filters?.branch || ''}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      trigger: { ...trigger, filters: { ...trigger.filters, branch: event.target.value } },
                    })
                  }
                  onBlur={(event) =>
                    void onSaveField({
                      trigger: { ...trigger, filters: { ...trigger.filters, branch: event.target.value } },
                    })
                  }
                />
              </>
            ) : null}

            {trigger.kind === ROUTINE_TRIGGER_INTERVAL ? (
              <Input
                label="Every (seconds)"
                size="sm"
                type="number"
                min={1}
                value={String(trigger.seconds || 3600)}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    trigger: { ...trigger, seconds: Number(event.target.value) || 0 },
                  })
                }
                onBlur={(event) =>
                  void onSaveField({
                    trigger: { kind: ROUTINE_TRIGGER_INTERVAL, seconds: Number(event.target.value) || 3600 },
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
                  setEditing({ ...editing, trigger: { ...trigger, expression: event.target.value } })
                }
                onBlur={(event) =>
                  void onSaveField({
                    trigger: { kind: ROUTINE_TRIGGER_CRON, expression: event.target.value },
                  })
                }
              />
            ) : null}

            {trigger.kind === ROUTINE_TRIGGER_ONE_SHOT ? (
              <Input
                label="Run at"
                size="sm"
                placeholder="2026-09-16T03:00:00Z"
                value={trigger.run_at}
                onChange={(event) =>
                  setEditing({ ...editing, trigger: { ...trigger, run_at: event.target.value } })
                }
                onBlur={(event) =>
                  void onSaveField({
                    trigger: { kind: ROUTINE_TRIGGER_ONE_SHOT, run_at: event.target.value },
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
                    setEditing({ ...editing, trigger: { ...trigger, sender: event.target.value } })
                  }
                  onBlur={(event) =>
                    void onSaveField({
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
                    setEditing({ ...editing, trigger: { ...trigger, pattern: event.target.value } })
                  }
                  onBlur={(event) =>
                    void onSaveField({
                      trigger: { ...trigger, pattern: event.target.value },
                    })
                  }
                />
              </>
            ) : null}
          </fieldset>

          <section aria-label="Routine history" className="space-y-2">
            <h4 className="text-sm font-medium">History</h4>
            {history.length === 0 ? (
              <p className="text-sm text-base-content/60">No successful runs yet.</p>
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

export default ComputerRoutinesPane
