/**
 * #818 — the navbar activity indicator for background (auxiliary) LLM work.
 *
 * Hidden when idle. With tasks active it shows a pulsing dot + count (and the
 * current label on wide viewports); clicking opens the audit list where any
 * cancellable task can be killed. Finished rows linger for the 4s decay
 * window so the user can see what just ran (`✓ label (1.4s)`).
 */
import { useState } from 'react'
import { activityLabel, type AuxTask } from '../lib/auxTasks'
import { requestAuxCancel } from '../lib/auxTasks'

export function AuxActivityIndicator({
  tasks,
  onCancel,
}: {
  tasks: AuxTask[]
  onCancel?: (taskId: string) => void
}) {
  const [open, setOpen] = useState(false)
  if (tasks.length === 0 && !open) return null
  const running = tasks.filter((t) => t.state === 'running')

  const kill = (taskId: string) => {
    ;(onCancel ?? requestAuxCancel)(taskId)
  }

  return (
    <div className="relative shrink-0" data-testid="aux-activity">
      <button
        type="button"
        className="btn btn-sm h-8 btn-ghost gap-1.5"
        aria-label={
          running.length > 0
            ? `${running.length} background tasks active`
            : 'Background task activity'
        }
        aria-expanded={open}
        data-testid="aux-activity-toggle"
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            running.length > 0 ? 'bg-success animate-pulse' : 'bg-base-content/30'
          }`}
          aria-hidden="true"
        />
        {running.length > 0 ? (
          <span className="text-xs font-medium">{running.length}</span>
        ) : null}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Background inference activity"
          data-testid="aux-activity-dialog"
          className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-base-300 bg-base-100 p-2 shadow-xl"
        >
          {tasks.length === 0 ? (
            <p className="px-2 py-1 text-xs text-base-content/60">No recent background tasks.</p>
          ) : (
            <ul className="space-y-1">
              {tasks.map((task) => (
                <li
                  key={task.task_id}
                  className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-base-200"
                  data-testid="aux-activity-row"
                >
                  <span
                    className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                      task.state === 'running' ? 'bg-success animate-pulse' : 'bg-base-content/30'
                    }`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1 truncate">{activityLabel(task)}</span>
                  {task.state === 'running' ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs px-1"
                      aria-label={`Cancel ${task.label}`}
                      data-testid={`aux-cancel-${task.task_id}`}
                      onClick={() => kill(task.task_id)}
                    >
                      ✕
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}

export default AuxActivityIndicator
