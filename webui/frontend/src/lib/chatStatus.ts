/**
 * REQ-46 — bubble-less transcript status when a chat dropdown changes.
 *
 * Format is "{kind}: {from} → {to}". Rendered as centred Grok-Bot status
 * chrome, never a DaisyUI chat-start / chat-end bubble.
 */

export const STATUS_ROLE = 'status' as const
export const INFO_ROLE = 'info' as const
export const SYSTEM_ROLE = 'system' as const

/** Transcript roles that render as centred chrome, never a speaker bubble. */
export const STATUS_CHROME_ROLES = [STATUS_ROLE, INFO_ROLE, SYSTEM_ROLE] as const
export type StatusChromeRole = (typeof STATUS_CHROME_ROLES)[number]

export type ChatTranscriptRole = 'user' | 'assistant' | StatusChromeRole

export type DropdownKind = 'team' | 'cli' | 'model' | 'mode' | 'api' | 'effort'

export const DROPDOWN_KIND_LABEL: Record<DropdownKind, string> = {
  team: 'Team target',
  cli: 'CLI',
  model: 'Model',
  mode: 'Mode',
  api: 'API',
  effort: 'Effort',
}

/** Navigation-only options — changing to these must not write a status line. */
export const MANAGE_SENTINELS = new Set([
  '__manage__',
  '__manage_cli__',
  '__manage_model__',
  '__manage_api__',
])

export const MANAGE_CLI_VALUE = '__manage_cli__'
export const MANAGE_CLI_HREF = '/settings/'
export const MANAGE_MODEL_VALUE = '__manage_model__'
export const MANAGE_MODEL_HREF = '/profiles/'

export const FALLBACK_CLIS = ['antigravity', 'grok', 'claude', 'gemini', 'codex'] as const

export const MODE_CLI = 'cli'
export const MODE_REMOTE = 'remote'
export type ChatRuntimeMode = typeof MODE_CLI | typeof MODE_REMOTE

export function formatDropdownStatus(
  kind: DropdownKind,
  fromLabel: string,
  toLabel: string,
): string {
  return `${DROPDOWN_KIND_LABEL[kind]}: ${fromLabel} → ${toLabel}`
}

export function shouldRecordDropdownChange(from: string, to: string): boolean {
  const a = from.trim()
  const b = to.trim()
  if (!a || !b || a === b) return false
  if (MANAGE_SENTINELS.has(b)) return false
  return true
}

export function isStatusRole(role: string | undefined): role is StatusChromeRole {
  return role === STATUS_ROLE || role === INFO_ROLE || role === SYSTEM_ROLE
}

/** Persist/render chrome lines as `status` so one presentation path covers the family. */
export function asTranscriptRole(role: string | undefined): 'user' | 'assistant' | typeof STATUS_ROLE {
  if (role === 'user' || role === 'assistant') return role
  if (isStatusRole(role)) return STATUS_ROLE
  return 'assistant'
}

export function modeLabel(mode: string): string {
  return mode === MODE_REMOTE ? 'Remote' : 'CLI'
}

export function isCliAgentContext(opts: {
  blueprintId?: string | null
  mode?: string | null
  cli?: string | null
}): boolean {
  const blueprint = (opts.blueprintId ?? '').trim().toLowerCase()
  const mode = (opts.mode ?? '').trim().toLowerCase()
  const cli = (opts.cli ?? '').trim()
  if (cli) return true
  if (mode === MODE_CLI || mode === 'cli_agent') return true
  return blueprint === 'cli_agent' || blueprint.startsWith('cli_')
}

export function uniqueCliNames(...groups: Array<Iterable<string> | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const group of groups) {
    if (!group) continue
    for (const raw of group) {
      const name = raw.trim()
      if (!name || MANAGE_SENTINELS.has(name) || seen.has(name)) continue
      seen.add(name)
      out.push(name)
    }
  }
  return out
}
