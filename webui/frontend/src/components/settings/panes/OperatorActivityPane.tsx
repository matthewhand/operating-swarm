/** #1314 — operator ActivityEvent feed + visibility setting. */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ScrollText } from 'lucide-react'
import { Alert } from '../../DaisyUI'
import { ApiAuthError, ApiError } from '../../../lib/api'
import {
  ACTIVITY_VISIBILITY_VALUES,
  activityEventKey,
  loadActivityLog,
  parseActivityVisibility,
  type ActivityLogVisibility,
} from '../../../lib/activityLog'
import { fetchUserPrefs, saveUserPrefs } from '../../../lib/userPrefs'

export function OperatorActivityPane() {
  const queryClient = useQueryClient()
  const [draftVisibility, setDraftVisibility] = useState<ActivityLogVisibility | null>(null)

  const prefsQuery = useQuery({
    queryKey: ['user-prefs'],
    queryFn: fetchUserPrefs,
    retry: 1,
  })

  const feedQuery = useQuery({
    queryKey: ['operator-activity'],
    queryFn: () => loadActivityLog(50),
    retry: 1,
  })

  const visibilityMutation = useMutation({
    mutationFn: (next: ActivityLogVisibility) =>
      saveUserPrefs({ activity_log_visibility: next }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-prefs'] })
      void queryClient.invalidateQueries({ queryKey: ['operator-activity'] })
    },
  })

  const visibility = parseActivityVisibility(
    draftVisibility
      ?? feedQuery.data?.visibility
      ?? prefsQuery.data?.activity_log_visibility,
  )
  const feedError = feedQuery.error
  const denied = feedError instanceof ApiAuthError
  const hidden = feedError instanceof ApiError && feedError.status === 404
  const rows = feedQuery.data?.items ?? []

  const onVisibility = (next: ActivityLogVisibility) => {
    setDraftVisibility(next)
    visibilityMutation.mutate(next)
  }

  return (
    <div className="space-y-3" data-testid="operator-activity-pane">
      <div>
        <h4 className="text-lg font-semibold">Operator activity</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Append-only log of operator mutations — create/archive an agent, edit
          an ACL, fire a routine, patch settings. Credential-shaped detail is
          stored as <code>[REDACTED]</code>.
        </p>
      </div>

      <label className="form-control w-full max-w-xs" htmlFor="activity-log-visibility">
        <span className="label-text text-sm">Visibility</span>
        <select
          id="activity-log-visibility"
          className="select select-bordered select-sm"
          data-testid="activity-visibility-select"
          value={visibility}
          onChange={(event) => onVisibility(parseActivityVisibility(event.target.value))}
        >
          {ACTIVITY_VISIBILITY_VALUES.map((value) => (
            <option key={value} value={value}>
              {value === 'off' ? 'Off' : value === 'operator' ? 'Operators only' : 'Everyone (own events)'}
            </option>
          ))}
        </select>
      </label>

      {denied ? (
        <Alert type="warning" icon={<ScrollText className="h-5 w-5" />}>
          <span className="text-sm">Operator visibility only.</span>
        </Alert>
      ) : hidden ? (
        <Alert type="info" icon={<ScrollText className="h-5 w-5" />}>
          <span className="text-sm">Activity log is off.</span>
        </Alert>
      ) : feedQuery.isPending ? (
        <p className="text-sm text-base-content/60">Loading activity…</p>
      ) : feedQuery.isError ? (
        <Alert type="warning" icon={<ScrollText className="h-5 w-5" />}>
          <span className="text-sm">Could not load the activity log.</span>
        </Alert>
      ) : rows.length === 0 ? (
        <Alert type="info" icon={<ScrollText className="h-5 w-5" />}>
          <span className="text-sm">No operator activity recorded yet.</span>
        </Alert>
      ) : (
        <ul className="space-y-1" aria-label="Operator activity log">
          {rows.map((row, index) => (
            <li
              key={activityEventKey(row, index)}
              className="flex items-start justify-between gap-3 rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
              data-testid="operator-activity-row"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {row.action}{' '}
                  <span className="badge badge-ghost badge-sm">
                    {row.entity_type}:{row.entity_id}
                  </span>
                </p>
                <p className="font-mono text-xs text-base-content/70">{row.actor_id}</p>
              </div>
              <time className="shrink-0 text-xs text-base-content/50">
                {row.created_at ? new Date(row.created_at).toLocaleString() : ''}
              </time>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
