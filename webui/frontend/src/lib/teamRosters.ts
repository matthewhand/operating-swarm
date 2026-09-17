/**
 * Team rosters for the AGENTS sidepane + team-member chat dropdown.
 *
 * Source of truth is team_rosters.json (or GET /v1/team-rosters/) — never the
 * Django LLM-alias /v1/teams/ admin registry.
 *
 * If no file/GET is present (or it is empty), a one-team stub fixture keeps
 * the sidepane populated so Teams are visible.
 */

export const TEAM_ROSTER_URLS = ['/team_rosters.json', '/v1/team-rosters/'] as const

export const ALL_MEMBERS_TARGET = 'all'
export const MANAGE_TEAMS_VALUE = '__manage__'
export const MANAGE_TEAMS_HREF = '/teams/'

/**
 * Explicit "All members" marker (#288).
 *
 * `session=` alone cannot carry the choice: a member id writes `session=<id>`,
 * while All members has no id to write — so a blank `session` is
 * indistinguishable from "no choice yet", and ChatPage re-defaults that state to
 * the team's nominated seat (#169). Without this marker an explicit All members
 * pick is silently lost on reload.
 */
export const ALL_MEMBERS_PARAM = 'members'

/** True when the URL carries an explicit All members pick. */
export function isAllMembersChoice(value: string | null | undefined): boolean {
  return value === ALL_MEMBERS_TARGET
}

/**
 * Shared ?team=&session= contract for the header Team members dropdown
 * and the rail SessionPicker (REQ-171A-1 / #601).
 *
 * A member id writes `session=<id>`. All members clears `session` and sets
 * `members=all` so the choice survives a reload (#288); the picker itself still
 * has no all-members href — `all` is only the send-target sentinel.
 */
export function applyTeamMemberSessionParam(
  params: URLSearchParams,
  teamId: string,
  memberId: string,
): URLSearchParams {
  const next = new URLSearchParams(params)
  if (teamId) next.set('team', teamId)
  if (!memberId || memberId === ALL_MEMBERS_TARGET) {
    next.delete('session')
    next.set(ALL_MEMBERS_PARAM, ALL_MEMBERS_TARGET)
  } else {
    next.set('session', memberId)
    next.delete(ALL_MEMBERS_PARAM)
  }
  return next
}

export interface TeamMember {
  id: string
  name: string
  kind?: string
  role?: string
  /** Nested roster id when kind=team (REQ-28 teams-of-teams). */
  team_id?: string
  /** ISO / epoch when this member became active (REQ-68 stack stagger). */
  started_at?: string
  startedAt?: number
  working?: boolean
  status?: 'running' | 'finished'
  snippet?: string
  avatar?: string
  avatar_path?: string
  avatarSrc?: string
  src?: string
}

export interface TeamRoster {
  id: string
  name: string
  description: string
  members: TeamMember[]
  /** Catalog recipe assigned to this team (REQ-81). */
  blueprintId?: string
  blueprint?: string
  persona_count?: number
  personas?: Array<{ name: string }>
}

/** One-team fixture so the sidepane stays visible without a live roster file. */
export const DEMO_TEAM_ROSTER: TeamRoster = {
  id: 'demo-team',
  name: 'Demo Team',
  description: 'Example multi-agent roster',
  members: [
    { id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' },
    { id: 'stewie', name: 'Stewie', kind: 'agent', role: 'ops' },
  ],
}

export function teamHideId(teamId: string): string {
  return `team:${teamId}`
}

export function teamThreadId(teamId: string): string {
  return `team-${teamId}`
}

export function memberOptionLabel(member: TeamMember): string {
  const name = member.name || member.id
  const kindRole = [member.kind, member.role].filter(Boolean).join('/')
  return kindRole ? `${name} (${kindRole})` : name
}

/** Human label for the team send-target dropdown (All members or a seat). */
export function memberTargetLabel(target: string, team: TeamRoster | null | undefined): string {
  if (!target || target === ALL_MEMBERS_TARGET) return 'All members'
  const member = team?.members.find((item) => item.id === target)
  return member ? memberOptionLabel(member) : target
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function parseMember(raw: unknown): TeamMember | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const id = typeof rec.id === 'string' ? rec.id.trim() : ''
  if (!id) return null
  const name = typeof rec.name === 'string' && rec.name.trim() ? rec.name.trim() : id
  const kind = typeof rec.kind === 'string' ? rec.kind : undefined
  const role = typeof rec.role === 'string' ? rec.role : undefined
  const teamId = typeof rec.team_id === 'string' ? rec.team_id.trim() : ''
  const member: TeamMember = { id, name, kind, role }
  if (kind === 'team') {
    member.team_id = teamId || id
  } else if (teamId) {
    member.team_id = teamId
  }
  if (typeof rec.started_at === 'string' && rec.started_at.trim()) {
    member.started_at = rec.started_at.trim()
  }
  if (typeof rec.startedAt === 'number' && Number.isFinite(rec.startedAt)) {
    member.startedAt = rec.startedAt
  }
  if (rec.working === true) member.working = true
  if (rec.status === 'running' || rec.status === 'finished') member.status = rec.status
  if (typeof rec.snippet === 'string') member.snippet = rec.snippet
  return member
}

function looksLikeRoster(rec: Record<string, unknown>): boolean {
  if (rec.object === 'blueprint') return false
  // object=team without members is the Django LLM-alias /v1/teams/ shape — skip.
  if (rec.object === 'team_roster') return true
  return Array.isArray(rec.members)
}

function parseRoster(raw: unknown): TeamRoster | null {
  const rec = asRecord(raw)
  if (!rec || !looksLikeRoster(rec)) return null
  const id = typeof rec.id === 'string' ? rec.id.trim() : ''
  if (!id) return null
  const name = typeof rec.name === 'string' && rec.name.trim() ? rec.name.trim() : id
  const description = typeof rec.description === 'string' ? rec.description : ''
  const members = Array.isArray(rec.members)
    ? rec.members.map(parseMember).filter((m): m is TeamMember => m !== null)
    : []
  const blueprintId =
    typeof rec.blueprint_id === 'string' && rec.blueprint_id.trim()
      ? rec.blueprint_id.trim()
      : typeof rec.blueprint === 'string' && rec.blueprint.trim()
        ? rec.blueprint.trim()
        : undefined
  const personas = Array.isArray(rec.personas)
    ? rec.personas
        .map((item) => {
          if (!item || typeof item !== 'object') return null
          const personaName = typeof (item as { name?: unknown }).name === 'string'
            ? (item as { name: string }).name.trim()
            : ''
          return personaName ? { name: personaName } : null
        })
        .filter((item): item is { name: string } => item !== null)
    : undefined
  const personaCount =
    typeof rec.persona_count === 'number' && Number.isFinite(rec.persona_count)
      ? rec.persona_count
      : undefined
  return {
    id,
    name,
    description,
    members,
    ...(blueprintId ? { blueprintId, blueprint: blueprintId } : {}),
    ...(personaCount != null ? { persona_count: personaCount } : {}),
    ...(personas ? { personas } : {}),
  }
}

/** Accept list envelopes, `{ teams: [...] }`, or a bare array. */
export function parseTeamRosters(payload: unknown): TeamRoster[] {
  if (Array.isArray(payload)) {
    return payload.map(parseRoster).filter((t): t is TeamRoster => t !== null)
  }
  const rec = asRecord(payload)
  if (!rec) return []
  const list = Array.isArray(rec.data)
    ? rec.data
    : Array.isArray(rec.teams)
      ? rec.teams
      : null
  if (!list) return []
  return list.map(parseRoster).filter((t): t is TeamRoster => t !== null)
}

/**
 * Load rosters from team_rosters.json / GET. Empty or missing → demo stub.
 * Never reads /v1/teams/ (LLM-alias admin).
 */
export async function fetchTeamRosters(): Promise<TeamRoster[]> {
  for (const url of TEAM_ROSTER_URLS) {
    try {
      const response = await fetch(url, { headers: { Accept: 'application/json' } })
      if (!response.ok) continue
      const parsed = parseTeamRosters(await response.json())
      if (parsed.length > 0) return parsed
    } catch {
      // Try the next candidate; stub is the last resort.
    }
  }
  return [DEMO_TEAM_ROSTER]
}
