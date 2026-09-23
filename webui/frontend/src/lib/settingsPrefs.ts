/**
 * Client-side settings-sheet preferences (REQ-19).
 *
 * Hostname override is also persisted on GET/PATCH /v1/preferences/ (REQ-168).
 * localStorage remains the cache. Retention mode is still browser-local.
 * Read/write is best-effort — private mode or quota failures must not throw.
 */

export const HOSTNAME_OVERRIDE_KEY = 'swarm_hostname_override'
export const RETENTION_MODE_KEY = 'swarm_retention_mode'
export const BUMP_COMPLETED_KEY = 'swarm_bump_completed'
export const BUMP_COMPLETED_EVENT = 'swarm:bump-completed-changed'

export const RETENTION_MODES = ['count', 'disk', 'archive', 'trash'] as const
export type RetentionMode = (typeof RETENTION_MODES)[number]

export const RETENTION_MODE_LABELS: Record<RetentionMode, string> = {
  count: 'Count',
  disk: 'Disk',
  archive: 'Archive',
  trash: 'Trash',
}

export function isRetentionMode(value: unknown): value is RetentionMode {
  return typeof value === 'string' && (RETENTION_MODES as readonly string[]).includes(value)
}

export function hasHostnameOverrideStorage(): boolean {
  try {
    return localStorage.getItem(HOSTNAME_OVERRIDE_KEY) !== null
  } catch {
    return false
  }
}

export function loadHostnameOverride(): string {
  try {
    return localStorage.getItem(HOSTNAME_OVERRIDE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveHostnameOverride(value: string): void {
  const trimmed = value.trim()
  try {
    if (trimmed) localStorage.setItem(HOSTNAME_OVERRIDE_KEY, trimmed)
    else localStorage.removeItem(HOSTNAME_OVERRIDE_KEY)
  } catch {
    /* persistence is best-effort */
  }
}

export function loadRetentionMode(): RetentionMode {
  try {
    const raw = localStorage.getItem(RETENTION_MODE_KEY)
    if (isRetentionMode(raw)) return raw
  } catch {
    /* fall through to default */
  }
  return 'count'
}

export function saveRetentionMode(mode: RetentionMode): void {
  if (!isRetentionMode(mode)) return
  try {
    localStorage.setItem(RETENTION_MODE_KEY, mode)
  } catch {
    /* persistence is best-effort */
  }
}

/** Browser hostname used when no override is stored. */
export function detectedHostname(): string {
  try {
    return window.location.hostname || ''
  } catch {
    return ''
  }
}

/**
 * When on (default), a finished generation moves that agent to the top of
 * the visible rail. Off: order changes only by drag.
 */
export function loadBumpCompleted(): boolean {
  try {
    const raw = localStorage.getItem(BUMP_COMPLETED_KEY)
    if (raw == null) return true
    return raw === '1' || raw === 'true'
  } catch {
    return true
  }
}

export type BumpScope = 'unassigned' | 'all'

export const BUMP_SCOPE_KEY = 'swarm_bump_completed_scope'
export const BUMP_SCOPE_EVENT = 'swarm:bump-completed-scope-changed'

/**
 * #552: where the activity bump is allowed to act.
 *
 * `unassigned` (default) — only rows in Unassigned move on completion. An agent
 * the operator placed in a section keeps the position they gave it.
 * `all` — the pre-#552 behaviour: any finished agent moves to the top.
 *
 * This is a scope on the existing preference, not a second switch: the master
 * toggle still turns the bump off entirely.
 */
export function loadBumpScope(): BumpScope {
  try {
    const raw = localStorage.getItem(BUMP_SCOPE_KEY)
    return raw === 'all' ? 'all' : 'unassigned'
  } catch {
    return 'unassigned'
  }
}

export function saveBumpScope(scope: BumpScope): BumpScope {
  const next: BumpScope = scope === 'all' ? 'all' : 'unassigned'
  try {
    localStorage.setItem(BUMP_SCOPE_KEY, next)
    window.dispatchEvent(
      new CustomEvent(BUMP_SCOPE_EVENT, { detail: { scope: next } }),
    )
  } catch {
    /* persistence is best-effort */
  }
  return next
}

export function saveBumpCompleted(enabled: boolean): boolean {
  try {
    localStorage.setItem(BUMP_COMPLETED_KEY, enabled ? '1' : '0')
    window.dispatchEvent(
      new CustomEvent(BUMP_COMPLETED_EVENT, { detail: { enabled } }),
    )
  } catch {
    /* persistence is best-effort */
  }
  return enabled
}
