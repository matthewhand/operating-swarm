/**
 * REQ-84: teammate task cards — Open in {remote kind} on same-team remotes.
 * Href comes from the configured remotes catalog (ui_url || base_url).
 * Never invent hosts. Never show the letters OMB.
 */

import type { RemoteConnection } from './api'
import type { TeamMember, TeamRoster } from './teamRosters'

const SENSITIVE_QUERY = ['token', 'api_key', 'apikey', 'key', 'auth', 'auth_token', 'password', 'secret']

function cleanRemoteUrl(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl)
    for (const param of Array.from(parsed.searchParams.keys())) {
      if (SENSITIVE_QUERY.some((s) => param.toLowerCase().includes(s))) {
        parsed.searchParams.delete(param)
      }
    }
    return parsed.toString()
  } catch {
    return rawUrl
  }
}

export const TEAMMATE_TASK_TYPE = 'teammate_task' as const

export const OPEN_IN_KIND_LABELS: Record<string, string> = {
  hermes: 'Hermes',
  omb: 'OpenMousBot',
  rakazo: 'Rakazo',
  herdr: 'Herdr',
  swarm: 'Operating Swarm',
}

const KIND_ALIASES: Record<string, string> = {
  openmausbot: 'omb',
  openmaus: 'omb',
  openmousbot: 'omb',
  openmous: 'omb',
  rakoza: 'rakazo',
  'open-swarm': 'swarm',
  openswarm: 'swarm',
  open_swarm: 'swarm',
}

const REMOTE_MEMBER_KINDS = new Set(['remote', 'herdr'])
const OMB_WORD = /\bOMB\b/

export interface TeammateTaskEvent {
  type: typeof TEAMMATE_TASK_TYPE
  title?: string
  status?: string
  teamId?: string
  workerId?: string
  workerKind?: string
  sessionId?: string
  href?: string
  disabledReason?: string
  openInLabel?: string
}

export type OpenInAction =
  | { kind: 'link'; href: string; label: string; target: '_blank' | '_self' }
  | { kind: 'disabled'; label: string; reason: string }

export interface OpenInContext {
  teamId?: string
  team?: TeamRoster | null
  remotes?: RemoteConnection[]
}

function asTrimmed(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const text = value.trim()
  return text || undefined
}

export function normalizeRemoteKind(id: string | undefined): string {
  const rid = (id || '').trim().toLowerCase()
  const resolved = KIND_ALIASES[rid] || rid
  if (resolved in OPEN_IN_KIND_LABELS) return resolved
  return ''
}

export function openInKindLabel(kindId: string): string {
  const rid = normalizeRemoteKind(kindId) || (kindId || '').trim().toLowerCase()
  const label = OPEN_IN_KIND_LABELS[rid] || rid
  return OMB_WORD.test(label) ? 'OpenMousBot' : label
}

export function openInButtonLabel(kindId: string): string {
  return `Open in ${openInKindLabel(kindId)}`
}

export function isHttpUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const text = value.trim()
  return /^https?:\/\//i.test(text)
}

export function configuredRemoteOpenHref(remote: RemoteConnection | undefined): string | undefined {
  if (!remote) return undefined
  const raw = (remote.ui_url?.trim() || remote.base_url?.trim() || '')
  if (!isHttpUrl(raw)) return undefined
  return cleanRemoteUrl(raw)
}

export function isRemoteTeamMember(member: TeamMember | undefined): boolean {
  if (!member) return false
  const kind = (member.kind || '').trim().toLowerCase()
  if (REMOTE_MEMBER_KINDS.has(kind)) return true
  return Boolean(normalizeRemoteKind(member.id))
}

export function remoteMemberOnTeam(
  team: TeamRoster | null | undefined,
  workerId: string | undefined,
): TeamMember | undefined {
  if (!team || !workerId) return undefined
  const wanted = workerId.trim().toLowerCase()
  const wantedKind = normalizeRemoteKind(wanted)
  return team.members.find((member) => {
    if (!isRemoteTeamMember(member)) return false
    const mid = (member.id || '').trim().toLowerCase()
    return mid === wanted || (wantedKind !== '' && normalizeRemoteKind(mid) === wantedKind)
  })
}

function unwrapCandidate(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const obj = value as Record<string, unknown>
  for (const key of ['result', 'data', 'event', 'task']) {
    const nested = obj[key]
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      const inner = nested as Record<string, unknown>
      if (String(inner.type || '').trim() === TEAMMATE_TASK_TYPE) return inner
    }
  }
  return obj
}

export function parseTeammateTask(value: unknown): TeammateTaskEvent | null {
  let raw: unknown = value
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text.startsWith('{')) return null
    try {
      raw = JSON.parse(text) as unknown
    } catch {
      return null
    }
  }
  const obj = unwrapCandidate(raw)
  if (!obj) return null
  if (String(obj.type || '').trim() !== TEAMMATE_TASK_TYPE) return null

  const teamId = asTrimmed(obj.team_id ?? obj.teamId ?? obj.team)
  const workerId = asTrimmed(obj.worker_id ?? obj.workerId ?? obj.remote_id ?? obj.remoteId)
  const workerKind = normalizeRemoteKind(
    asTrimmed(obj.worker_kind ?? obj.workerKind ?? obj.kind ?? workerId) || '',
  )
  if (!teamId || !(workerId || workerKind)) return null

  const event: TeammateTaskEvent = { type: TEAMMATE_TASK_TYPE, teamId }
  if (workerId) event.workerId = workerId
  if (workerKind) {
    event.workerKind = workerKind
    event.openInLabel = openInButtonLabel(workerKind)
  }
  const title = asTrimmed(obj.title ?? obj.name ?? obj.prompt)
  if (title) event.title = title
  const status = asTrimmed(obj.status ?? obj.state)
  if (status && status !== TEAMMATE_TASK_TYPE && status !== 'tool_status') {
    event.status = status
  }
  const sessionId = asTrimmed(obj.session_id ?? obj.sessionId)
  if (sessionId) event.sessionId = sessionId
  const href = obj.href ?? obj.url ?? obj.ui_url
  if (isHttpUrl(href)) event.href = cleanRemoteUrl(href.trim())
  const reason = asTrimmed(obj.disabled_reason ?? obj.disabledReason)
  if (reason) event.disabledReason = reason
  return event
}

export function teammateTaskRegionLabel(event: TeammateTaskEvent): string {
  const kind = openInKindLabel(event.workerKind || event.workerId || '')
  return kind ? `${kind} task` : 'Remote task'
}

function findConfiguredRemote(
  remotes: RemoteConnection[] | undefined,
  workerId: string | undefined,
  workerKind: string | undefined,
): RemoteConnection | undefined {
  if (!remotes?.length) return undefined
  const wanted = normalizeRemoteKind(workerKind || workerId) || (workerId || '').trim().toLowerCase()
  if (!wanted) return undefined
  return remotes.find((remote) => {
    const id = (remote.id || '').trim().toLowerCase()
    const kind = normalizeRemoteKind(remote.kind || remote.id)
    return id === wanted || kind === wanted || normalizeRemoteKind(id) === wanted
  })
}

/**
 * Same-team remote only. Solo local API chat returns null (no Open-in button).
 * Href is always the configured catalog URL — payload href is a fallback only
 * when it matches that catalog host.
 */
export function resolveOpenInAction(
  event: TeammateTaskEvent,
  ctx: OpenInContext,
): OpenInAction | null {
  const currentTeam = (ctx.teamId || '').trim()
  const eventTeam = (event.teamId || '').trim()
  if (!currentTeam || !eventTeam || currentTeam.toLowerCase() !== eventTeam.toLowerCase()) {
    return null
  }
  const workerId = event.workerId || event.workerKind
  const member = remoteMemberOnTeam(ctx.team, workerId)
  if (!member) return null

  const kind = normalizeRemoteKind(event.workerKind || member.id || workerId) || ''
  if (!kind) return null
  const label = event.openInLabel || openInButtonLabel(kind)
  if (OMB_WORD.test(label)) {
    return { kind: 'disabled', label: openInButtonLabel('omb'), reason: 'Invalid label' }
  }

  const remote = findConfiguredRemote(ctx.remotes, member.id || workerId, kind)
  const catalogHref = configuredRemoteOpenHref(remote)

  if (kind === 'swarm' && event.sessionId) {
    const inApp = `/chat?remote=${encodeURIComponent(remote?.id || 'swarm')}&session=${encodeURIComponent(event.sessionId)}`
    return { kind: 'link', href: inApp, label, target: '_self' }
  }

  if (catalogHref) {
    return { kind: 'link', href: catalogHref, label, target: '_blank' }
  }

  const reason =
    event.disabledReason ||
    (remote
      ? `No UI URL configured for ${openInKindLabel(kind)}`
      : `${openInKindLabel(kind)} is not configured`)
  return { kind: 'disabled', label, reason }
}
