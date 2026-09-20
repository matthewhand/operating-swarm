/**
 * #818 — navbar visibility for background (auxiliary) LLM inference.
 *
 * The backend announces `aux_task_started` / `aux_task_update` over the chat
 * socket. This module is the pure state reducer: upsert by task id, keep
 * finished rows in a 4s decay window so the user can see what just ran, and
 * report the live "tasks active" count the indicator renders. Transport is
 * decoupled via CustomEvents (`swarm:aux-tasks` snapshot out,
 * `swarm:aux-cancel` kill request in) so ChatPage stays thin.
 */

export interface AuxTask {
  task_id: string
  label: string
  model?: string
  state: 'running' | 'done' | 'failed' | 'cancelled'
  duration_s?: number
}

export const AUX_TASKS_EVENT = 'swarm:aux-tasks'
export const AUX_CANCEL_EVENT = 'swarm:aux-cancel'
export const AUX_DECAY_MS = 4_000

/** Upsert one task row from a backend frame; returns the new snapshot. */
export function applyAuxFrame(
  tasks: AuxTask[],
  frame: { type: string; task_id: string; label?: string; model?: string; state?: string; duration_s?: number },
): AuxTask[] {
  if (frame.type !== 'aux_task_started' && frame.type !== 'aux_task_update') return tasks
  if (!frame.task_id) return tasks
  const now = Date.now()
  const rest = tasks.filter((t) => t.task_id !== frame.task_id)
  const existing = tasks.find((t) => t.task_id === frame.task_id)
  const startedFrame = frame.type === 'aux_task_started' || !existing
  const state = (frame.state as AuxTask['state']) || (startedFrame ? 'running' : existing!.state)
  if (state !== 'running') {
    // Finished rows linger for the decay window, then leave the list.
    const endedAt = existing && (existing as AuxTask & { _endedAt?: number })._endedAt
    if (endedAt && now - endedAt > AUX_DECAY_MS) return rest
    return [
      ...rest,
      {
        task_id: frame.task_id,
        label: frame.label || existing?.label || frame.task_id,
        model: frame.model ?? existing?.model,
        state,
        duration_s: frame.duration_s,
        ...(frame.duration_s !== undefined ? {} : {}),
        _endedAt: endedAt ?? now,
      } as AuxTask & { _endedAt: number },
    ]
  }
  return [
    ...rest,
    {
      task_id: frame.task_id,
      label: frame.label || existing?.label || frame.task_id,
      model: frame.model ?? existing?.model,
      state: 'running',
      duration_s: frame.duration_s,
    },
  ]
}

/** Rows still active right now (finished ones have decayed). */
export function activeAuxTasks(tasks: AuxTask[]): AuxTask[] {
  return tasks.filter((t) => t.state === 'running')
}

/** Drop decayed finished rows; call on a timer while the indicator shows. */
export function sweepAuxTasks(tasks: AuxTask[], now = Date.now()): AuxTask[] {
  return tasks.filter(
    (t) =>
      t.state === 'running' ||
      now - ((t as AuxTask & { _endedAt?: number })._endedAt ?? now) <= AUX_DECAY_MS,
  )
}

/** Ask the socket layer to kill one task (#818 kill switch). */
export function requestAuxCancel(taskId: string): void {
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    try {
      window.dispatchEvent(new CustomEvent(AUX_CANCEL_EVENT, { detail: taskId }))
    } catch {}
  }
}

/** One-line label for the audit list / indicator tooltip. */
export function activityLabel(task: AuxTask): string {
  if (task.state === 'running') {
    return `${task.label}…${task.model ? ` (${task.model})` : ''}`
  }
  const mark = task.state === 'failed' || task.state === 'cancelled' ? '✕' : '✓'
  const suffix = task.duration_s !== undefined ? ` (${task.duration_s}s)` : ''
  return `${mark} ${task.label}${suffix}`
}

/** Emit a snapshot for the indicator (ChatPage listens, navbar renders). */
export function announceAuxTasks(tasks: AuxTask[]): void {
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    try {
      window.dispatchEvent(new CustomEvent(AUX_TASKS_EVENT, { detail: tasks }))
    } catch {}
  }
}
