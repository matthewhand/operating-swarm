import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, Clock, GitMerge, Mail, Package, Plus, Timer } from 'lucide-react'
import { Button, Input, Select } from './DaisyUI'
import { GithubTriggerComposer } from './GithubTriggerComposer'
import RoutinePackPicker from './RoutinePackPicker'
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
  fetchRoutines,
  formatDurationMs,
  formatRoutineHistoryTime,
  historySucceeded,
  isDuplicateRoutineError,
  mergeRoutineSave,
  previewRoutineDryRun,
  routineDraftWrite,
  ROUTINE_TRIGGER_CRON,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  ROUTINE_TRIGGER_INTERVAL,
  ROUTINE_TRIGGER_MAILBOX_MESSAGE,
  ROUTINE_TRIGGER_ONE_SHOT,
  runNowRoutine,
  testRunRoutine,
  toggleOpenPullRequestTool,
  triggerSummary,
  updateRoutine,
  type Routine,
  type RoutineDryRunPreview as DryRunPreview,
  type RoutineTrigger,
  type RoutineTriggerKind,
} from '../lib/routines'
import { RoutineToolsFields } from './RoutineToolsFields'
import {
  incompleteFillInMessage,
  unresolvedFillIns,
  routineEnableGate,
  routineListStatus,
  routineStatusLabel,
} from '../lib/routinePack'

export interface ComputerRoutinesPaneProps {
  agentId: string
  agentName: string
  /** True only when a real computer-control session exists. Tests stay false. */
  hasScreenSession?: boolean
  nowMs?: number
  showThumbnail?: boolean
  /** Proof harness only — open the + Add Tool or MCP picker (#1406). */
  toolsPickerOpen?: boolean
  /** Proof harness only — pre-dismiss instruction-gap suggestions (#1410). */
  suggestionDismissed?: Record<string, string>
}

type PaneView = 'list' | 'editor' | 'pack'

function triggerIcon(kind: string | undefined) {
  if (kind === ROUTINE_TRIGGER_MAILBOX_MESSAGE) return Mail
  if (kind === ROUTINE_TRIGGER_INTERVAL || kind === ROUTINE_TRIGGER_CRON || kind === ROUTINE_TRIGGER_ONE_SHOT) {
    return Timer
  }
  return GitMerge
}

function commitGithubTrigger(trigger: RoutineTrigger): RoutineTrigger | null {
  if (!isGithubRoutineTrigger(trigger)) return trigger
  return githubTriggerSaveError(trigger) ? null : trigger
}

export function ComputerRoutinesPane({
  agentId,
  agentName,
  hasScreenSession = false,
  nowMs,
  /* #1077: the screen viewport moved above the tab strip (ComputerControlStub);
     the routines pane no longer renders a duplicate. */
  showThumbnail = false,
  toolsPickerOpen = false,
  suggestionDismissed,
}: ComputerRoutinesPaneProps) {
  const [view, setView] = useState<PaneView>('list')
  const [editing, setEditing] = useState<Routine | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<DryRunPreview | null>(null)
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
    setPreview(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId])

  const openEditor = (routine: Routine) => {
    setEditing(routine)
    setConfirmDelete(false)
    setError(null)
    setPreview(null)
    setView('editor')
  }

  const backToList = async () => {
    setView('list')
    setEditing(null)
    setConfirmDelete(false)
    setPreview(null)
    await load()
  }

  const onAdd = async () => {
    if (!agentId || busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await createRoutine(agentId, { name: 'New routine', active: false })
      refreshRoutines()
      openEditor(created)
    } catch (err) {
      // #1316 — the server refuses an identical "New routine". Open the one
      // that already exists rather than mint a twin or show a dead error.
      if (isDuplicateRoutineError(err) && err.existingRoutine) {
        refreshRoutines()
        openEditor(err.existingRoutine)
        return
      }
      setError(err instanceof Error ? err.message : 'Could not create routine.')
    } finally {
      setBusy(false)
    }
  }

  const onSaveField = async (patch: Parameters<typeof updateRoutine>[2]) => {
    if (!agentId || !editing) return
    const routineId = editing.id
    // `patch` is a partial update whose `trigger` is the loose draft shape, so
    // spreading it over the stored `Routine` widens the type. The merged row is
    // the routine being edited (same shape the optimistic `setEditing` write
    // below already asserts), so narrow it back to `Routine` here rather than
    // loosening `FillInCarrier` for every caller.
    const merged = {
      ...editing,
      ...patch,
      active: patch.active !== undefined ? patch.active : editing.active,
    } as Routine
    const slots = unresolvedFillIns([merged])
    const body = { ...patch }
    if (slots.length > 0 && merged.active) {
      body.active = false
      setError(incompleteFillInMessage(slots))
    }
    setEditing((current) =>
      current && current.id === routineId ? ({ ...current, ...body } as Routine) : current,
    )
    try {
      const updated = await updateRoutine(agentId, routineId, body)
      setEditing((current) => {
        if (!current || current.id !== updated.id) return current
        return mergeRoutineSave(current, updated, body as Partial<Routine>)
      })
      refreshRoutines()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save routine.')
    }
  }

  const onChangeKind = async (kind: RoutineTriggerKind) => {
    if (!editing) return
    const next = emptyTrigger(kind)
    const tools = editing.tools_explicit
      ? effectiveRoutineTools(editing)
      : defaultToolsForTrigger(next)
    setEditing({ ...editing, trigger: next, tools })
    // Trigger only — server re-defaults tools when they were not explicit.
    const committable = commitGithubTrigger(next)
    if (committable) await onSaveField({ trigger: committable })
  }

  const onToggleOpenPullRequest = async (enabled: boolean) => {
    if (!editing) return
    const tools = toggleOpenPullRequestTool(effectiveRoutineTools(editing), enabled)
    setEditing({ ...editing, tools, tools_explicit: true })
    await onSaveField({ tools })
  }

  const onChangeTools = async (tools: string[]) => {
    if (!editing) return
    setEditing({ ...editing, tools, tools_explicit: true })
    await onSaveField({ tools })
  }

  const onSaveDraft = async () => {
    if (!agentId || !editing || busy) return
    setBusy(true)
    setError(null)
    try {
      const write = routineDraftWrite(editing)
      const slots = unresolvedFillIns([editing])
      if (slots.length > 0 && write.active) {
        write.active = false
        setError(incompleteFillInMessage(slots))
      }
      const updated = await updateRoutine(agentId, editing.id, write)
      setEditing(updated)
      refreshRoutines()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save routine.')
    } finally {
      setBusy(false)
    }
  }

  const onTestRun = async () => {
    if (!editing || busy) return
    setBusy(true)
    setError(null)
    try {
      if (!agentId || !editing.id) {
        setPreview(previewRoutineDryRun(editing))
        return
      }
      const result = await testRunRoutine(agentId, editing.id)
      setPreview(resolveRoutinePreview(editing, result))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test preview failed.')
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
  const enableGate = editing ? routineEnableGate(editing) : null

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="computer-routines-pane">
      {error ? (
        <p className="text-sm text-error" role="alert" data-testid="computer-routines-error">
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
            <div className="flex items-center gap-1">
              <button
                type="button"
                className="btn btn-ghost btn-sm btn-square"
                aria-label="Export or import pack"
                data-testid="routine-pack-open"
                onClick={() => {
                  setError(null)
                  setView('pack')
                }}
                disabled={busy || !agentId}
              >
                <Package className="h-4 w-4" aria-hidden="true" />
              </button>
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
                      className="btn btn-sm justify-start gap-3 border-base-300 bg-base-100 text-left hover:bg-base-200"
                      onClick={() => openEditor(routine)}
                    >
                      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="block font-medium">
                          <span>{routine.name}</span>
                          <RoutineStatusBadge routine={routine} />
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
      ) : view === 'pack' ? (
        <div className="flex min-h-0 flex-1 flex-col gap-3" data-testid="routine-pack-pane">
          <div className="flex items-center justify-between gap-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void backToList()}>
              Back
            </button>
            <h3 className="text-base font-semibold">Routines pack</h3>
            <span className="w-16" aria-hidden="true" />
          </div>
          <RoutinePackPicker
            agentId={agentId}
            routines={routines}
            busy={busy}
            onImported={refreshRoutines}
          />
        </div>
      ) : editing && trigger ? (
        <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="routine-editor">
          <div className="flex items-center justify-between gap-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void backToList()}>
              Back
            </button>
            <h3 className="text-base font-semibold">Routine</h3>
            <span className="w-16" aria-hidden="true" />
          </div>

          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <RoutineArmedToggle
                active={editing.active}
                disabled={enableGate?.blocked}
                onChange={(active) => {
                  if (active && routineListStatus(editing) === 'pending-fill') {
                    setError(incompleteFillInMessage(unresolvedFillIns([editing])))
                    return
                  }
                  setError(null)
                  void onSaveField({ active })
                }}
              />
              {routineListStatus(editing) === 'pending-fill' ? (
                <p className="text-xs text-warning" data-testid="routine-editor-pending-fill">
                  Pending fill — complete required slots before enabling.
                </p>
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="primary"
                data-testid="routine-editor-save"
                onClick={() => void onSaveDraft()}
                disabled={busy}
              >
                Save
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => void onRunNow()} disabled={busy}>
                Run now
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                data-testid="routine-editor-test"
                onClick={() => void onTestRun()}
                disabled={busy}
              >
                Test
              </Button>
              <Button type="button" size="sm" color="error" variant="ghost" onClick={() => void onDelete()}>
                {confirmDelete ? 'Confirm delete' : 'Delete'}
              </Button>
            </div>
            {enableGate?.message ? (
              <p id="routine-enable-gated" className="text-xs text-base-content/60" data-testid="routine-enable-gated">
                {enableGate.message}
              </p>
            ) : null}
          </div>

          <Input
            label="Name"
            size="sm"
            value={editing.name}
            onChange={(event) => setEditing({ ...editing, name: event.target.value })}
            onBlur={(event) => void onSaveField({ name: event.target.value })}
          />
          <RoutineAgentInstructions
            instruction={editing.instruction}
            model={editing.model}
            onInstructionChange={(instruction) => setEditing({ ...editing, instruction })}
            onInstructionBlur={(instruction) => void onSaveField({ instruction })}
            onModelChange={(model) => {
              void onSaveField({ model })
            }}
          />
          <RoutineDryRunPreview preview={preview} />

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

            {isGithubRoutineTrigger(trigger) ? (
              <>
                <GithubTriggerComposer
                  trigger={trigger}
                  onChange={(next) => setEditing({ ...editing, trigger: next })}
                  onCommit={(next) => void onSaveField({ trigger: next })}
                />
                {trigger.kind === ROUTINE_TRIGGER_GITHUB_EVENT ? (
                  <>
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
                        const next = {
                          ...trigger,
                          filters: { ...trigger.filters, labels },
                        }
                        if (!githubTriggerSaveError(next)) {
                          void onSaveField({ trigger: next })
                        }
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
                          trigger: {
                            ...trigger,
                            filters: { ...trigger.filters, branch: event.target.value },
                          },
                        })
                      }
                      onBlur={(event) => {
                        const next = {
                          ...trigger,
                          filters: { ...trigger.filters, branch: event.target.value },
                        }
                        if (!githubTriggerSaveError(next)) {
                          void onSaveField({ trigger: next })
                        }
                      }}
                    />
                  </>
                ) : null}
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

          <RoutineToolsFields
            tools={effectiveRoutineTools(editing)}
            instruction={editing.instruction}
            trigger={editing.trigger}
            onToggleOpenPullRequest={(enabled) => void onToggleOpenPullRequest(enabled)}
            onChangeTools={(tools) => void onChangeTools(tools)}
            pickerOpen={toolsPickerOpen || undefined}
            suggestionDismissed={suggestionDismissed}
          />

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

function RoutineStatusBadge({ routine }: { routine: Routine }) {
  const status = routineListStatus(routine)
  const tone =
    status === 'pending-fill'
      ? 'text-warning'
      : status === 'enabled'
        ? 'text-success'
        : 'text-base-content/50'
  return (
    <span
      className={`ml-2 text-xs font-normal ${tone}`}
      data-testid={`routine-list-status-${routine.id}`}
      data-status={status}
    >
      {routineStatusLabel(status)}
    </span>
  )
}

export default ComputerRoutinesPane
