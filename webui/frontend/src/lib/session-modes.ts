/** Operator session modes. Always-approve is Operating Swarm's CLI catalog flags, not a cycle stop. */

export const SESSION_MODES = ['default', 'plan', 'auto-edit'] as const
export type SessionMode = (typeof SESSION_MODES)[number]

export function normalizeSessionMode(value: string | null | undefined): SessionMode {
  const raw = (value || 'default').trim().toLowerCase().replace(/[_\s]+/g, '-')
  if (raw === 'plan') return 'plan'
  if (
    raw === 'auto-edit' ||
    raw === 'autoedit' ||
    raw === 'accept-edits' ||
    raw === 'acceptedits'
  ) {
    return 'auto-edit'
  }
  return 'default'
}

export function cycleSessionMode(current: string | null | undefined): SessionMode {
  const mode = normalizeSessionMode(current)
  const idx = SESSION_MODES.indexOf(mode)
  return SESSION_MODES[(idx + 1) % SESSION_MODES.length]
}

export function sessionModeLabel(mode: string | null | undefined): string {
  const resolved = normalizeSessionMode(mode)
  if (resolved === 'plan') return 'Plan'
  if (resolved === 'auto-edit') return 'Auto-edit'
  return 'Default'
}
