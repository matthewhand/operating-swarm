/** #1314 — operator activity log client helpers. */

import { fetchActivityLog } from './api'
import type { ActivityEvent, ActivityList, ActivityLogVisibility } from './api'

export type { ActivityEvent, ActivityList, ActivityLogVisibility }

export const ACTIVITY_VISIBILITY_VALUES = ['off', 'operator', 'all'] as const

export const DEFAULT_ACTIVITY_VISIBILITY: ActivityLogVisibility = 'operator'

export function parseActivityVisibility(raw: unknown): ActivityLogVisibility {
  return raw === 'off' || raw === 'operator' || raw === 'all' ? raw : DEFAULT_ACTIVITY_VISIBILITY
}

export function activityEventKey(row: ActivityEvent, index: number): string {
  return row.id || `${row.created_at}-${row.action}-${row.entity_id}-${index}`
}

export function loadActivityLog(limit = 50): Promise<ActivityList> {
  return fetchActivityLog({ limit })
}
