/** Composition roster contract (REQ-20 / REQ-28). Not /v1/teams LLM aliases. */

export const MEMBER_KINDS = ['api', 'cli', 'remote', 'team', 'herdr'] as const
export type MemberKind = (typeof MEMBER_KINDS)[number]

export interface TeamRosterMember {
  id: string
  name?: string
  kind: MemberKind
  role: string
  source: string
  team_id?: string
}

export interface TeamRoster {
  id: string
  object?: 'team_roster'
  name: string
  members: TeamRosterMember[]
  wires?: { handoff: boolean; as_tool: boolean }
  /** Optional team-scoped CoS (REQ-107). Null = no CoS; never auto-picked. */
  chief_of_staff_id?: string | null
  chief_of_staff_instructions?: string
}

export type TeamMemberRole =
  | 'default'
  | 'support'
  | 'gate'
  | 'skeptic'
  | 'advisor'
  | 'chief_of_staff'
  | 'suggestions'

export const TEAM_MEMBER_ROLES: readonly TeamMemberRole[] = [
  'default',
  'support',
  'gate',
  'skeptic',
  'advisor',
  'chief_of_staff',
  'suggestions',
]

export const DEFAULT_TEAM_WIRES = { handoff: true, as_tool: true } as const

export const KIND_LABEL: Record<MemberKind, string> = {
  api: 'API',
  cli: 'CLI',
  remote: 'remote',
  team: 'team',
  herdr: 'herdr',
}

export const DRAG_MIME = 'application/x-swarm-team-agent'

export const COS_ELIGIBLE_KINDS: readonly MemberKind[] = ['api', 'cli']

export const DEFAULT_COS_STARTER =
  "Coordinate this team's roster. Hand off or use-as-tool according to each member's strengths. Do not duplicate work. Report back.\n\nAdd specifics for this team: …"

export const COS_INSTRUCTIONS_HELPER =
  "Add specifics for this team — for example prefer grok_agent for revision control, use skeptic only after implement, Hermes for long-running host tasks. The same agent can sit on multiple teams; this team's CoS brief steers how members are used here."

export const COS_EMPTY_ROSTER_HINT = 'Add agents first'

export const COS_REMOTE_REASON =
  'Remote members cannot be Chief of Staff yet — pick an API or CLI agent that can hand off or use them as tools.'

export const COS_NESTED_REASON = 'Nested teams and Herdr slots cannot be Chief of Staff.'

export const NO_COS_VALUE = ''

export interface TeamAgent {
  id: string
  name: string
  kind: MemberKind
  source: string
  placeholder?: boolean
}

export const PLACEHOLDER_TEAM_AGENTS: TeamAgent[] = [
  { id: 'jeeves', name: 'Jeeves', kind: 'api', source: 'blueprint:jeeves' },
  { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok' },
  {
    id: 'acp',
    name: 'ACP harness',
    kind: 'remote',
    source: 'placeholder:remote:acp',
    placeholder: true,
  },
]

export function isMemberKind(value: unknown): value is MemberKind {
  return typeof value === 'string' && (MEMBER_KINDS as readonly string[]).includes(value)
}

export function parseRosterMember(raw: unknown): TeamRosterMember | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const id = String(row.id || '').trim()
  const kind = String(row.kind || '').trim().toLowerCase()
  if (!id || !isMemberKind(kind)) return null
  const teamId = String(row.team_id || '').trim()
  const name = typeof row.name === 'string' && row.name.trim() ? row.name.trim() : id
  const member: TeamRosterMember = {
    id,
    name,
    kind,
    role: String(row.role || 'default'),
    source: String(row.source || ''),
  }
  if (kind === 'team') {
    member.team_id = teamId || id
  } else if (teamId) {
    member.team_id = teamId
  }
  return member
}

export function parseTeamRoster(raw: unknown): TeamRoster | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const id = String(row.id || '').trim()
  const looksLikeRoster =
    row.object === 'team_roster' || Array.isArray(row.members) || Array.isArray(row.agent_team)
  if (!id || !looksLikeRoster) return null
  const membersIn = Array.isArray(row.members)
    ? row.members
    : Array.isArray(row.agent_team)
      ? row.agent_team
      : []
  const members = membersIn.map(parseRosterMember).filter((m): m is TeamRosterMember => m !== null)
  const rawCos = row.chief_of_staff_id
  const cosId =
    rawCos === null || rawCos === undefined || rawCos === ''
      ? null
      : String(rawCos).trim() || null
  return {
    id,
    object: 'team_roster',
    name: String(row.name || id),
    members,
    wires: {
      handoff: row.wires && typeof row.wires === 'object' ? Boolean((row.wires as { handoff?: unknown }).handoff ?? true) : true,
      as_tool: row.wires && typeof row.wires === 'object' ? Boolean((row.wires as { as_tool?: unknown }).as_tool ?? true) : true,
    },
    chief_of_staff_id: cosId,
    chief_of_staff_instructions: String(row.chief_of_staff_instructions || ''),
  }
}

export function parseTeamRosterList(payload: unknown): TeamRoster[] {
  if (!payload || typeof payload !== 'object') return []
  const data = (payload as { data?: unknown }).data
  if (!Array.isArray(data)) return []
  return data.map(parseTeamRoster).filter((r): r is TeamRoster => r !== null)
}

export function childTeamIds(roster: TeamRoster): string[] {
  return roster.members
    .filter((m) => m.kind === 'team')
    .map((m) => m.team_id || m.id)
}

export function nestRosters(rosters: TeamRoster[]): Array<TeamRoster & { children: TeamRoster[] }> {
  const byId = new Map(rosters.map((r) => [r.id, r]))
  const childIds = new Set<string>()
  for (const roster of rosters) {
    for (const id of childTeamIds(roster)) childIds.add(id)
  }
  return rosters
    .filter((r) => !childIds.has(r.id))
    .map((r) => ({
      ...r,
      children: childTeamIds(r)
        .map((id) => byId.get(id))
        .filter((c): c is TeamRoster => Boolean(c)),
    }))
}

export function emptyRosterDraft(): {
  name: string
  members: TeamRosterMember[]
  wires: { handoff: boolean; as_tool: boolean }
  chiefOfStaffId: string | null
  chiefOfStaffInstructions: string
} {
  return {
    name: '',
    members: [],
    wires: { ...DEFAULT_TEAM_WIRES },
    chiefOfStaffId: null,
    chiefOfStaffInstructions: DEFAULT_COS_STARTER,
  }
}

export function agentDisplayName(agent: { id: string; name?: string }): string {
  return (agent.name && agent.name.trim()) || agent.id
}

export function memberKey(member: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>): string {
  return `${member.kind}:${member.source || member.id}`
}

export function rosterHasMember(
  members: TeamRosterMember[],
  agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>,
): boolean {
  const key = memberKey(agent)
  return members.some((row) => memberKey(row) === key)
}

export function addMember(members: TeamRosterMember[], agent: TeamAgent): TeamRosterMember[] {
  if (rosterHasMember(members, agent)) return members
  return [
    ...members,
    {
      id: agent.id,
      name: agent.name || agent.id,
      kind: agent.kind,
      role: 'default',
      source: agent.source,
    },
  ]
}

export function removeMember(
  members: TeamRosterMember[],
  agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>,
): TeamRosterMember[] {
  const key = memberKey(agent)
  return members.filter((row) => memberKey(row) !== key)
}

export function setMemberRole(
  members: TeamRosterMember[],
  agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>,
  role: TeamMemberRole,
): TeamRosterMember[] {
  const key = memberKey(agent)
  return members.map((row) => (memberKey(row) === key ? { ...row, role } : row))
}

export function encodeDragAgent(agent: TeamAgent): string {
  return JSON.stringify({
    id: agent.id,
    name: agent.name,
    kind: agent.kind,
    source: agent.source,
    placeholder: agent.placeholder ?? false,
  })
}

export function parseDragAgent(raw: string): TeamAgent | null {
  if (!raw || !raw.trim()) return null
  try {
    const row = JSON.parse(raw) as Record<string, unknown>
    const id = String(row.id || '').trim()
    const kind = String(row.kind || '').trim().toLowerCase()
    if (!id || !isMemberKind(kind)) return null
    return {
      id,
      name: String(row.name || id),
      kind,
      source: String(row.source || ''),
      placeholder: row.placeholder === true,
    }
  } catch {
    return null
  }
}

export function isCosEligibleKind(kind: string | undefined): boolean {
  return Boolean(kind && (COS_ELIGIBLE_KINDS as readonly string[]).includes(kind))
}

export function isCosEligibleMember(member: Pick<TeamRosterMember, 'kind'>): boolean {
  return isCosEligibleKind(member.kind)
}

export function cosIneligibleReason(member: Pick<TeamRosterMember, 'kind'>): string | null {
  if (isCosEligibleMember(member)) return null
  if (member.kind === 'remote') return COS_REMOTE_REASON
  if (member.kind === 'team' || member.kind === 'herdr') return COS_NESTED_REASON
  return COS_REMOTE_REASON
}

export function eligibleCosMembers(members: TeamRosterMember[]): TeamRosterMember[] {
  return members.filter(isCosEligibleMember)
}

export function restoreCosId(roster: Pick<TeamRoster, 'members' | 'chief_of_staff_id'>): string | null {
  const saved = roster.chief_of_staff_id?.trim() || ''
  if (saved && roster.members.some((m) => m.id === saved && isCosEligibleMember(m))) {
    return saved
  }
  const tagged = roster.members.filter(
    (m) => m.role === 'chief_of_staff' && isCosEligibleMember(m),
  )
  if (tagged.length === 1) return tagged[0].id
  return null
}

export function stampCosRole(
  members: TeamRosterMember[],
  cosId: string | null,
): TeamRosterMember[] {
  const want = cosId?.trim() || ''
  return members.map((row) => {
    if (want && row.id === want) return { ...row, role: 'chief_of_staff' }
    if (row.role === 'chief_of_staff') return { ...row, role: 'default' }
    return row
  })
}

export function cosBriefForMember(
  roster: Pick<TeamRoster, 'chief_of_staff_id' | 'chief_of_staff_instructions'>,
  memberId: string | null | undefined,
): string | null {
  const cosId = roster.chief_of_staff_id?.trim() || ''
  const want = (memberId || '').trim()
  if (!cosId || !want || cosId !== want) return null
  const text = (roster.chief_of_staff_instructions || '').trim()
  return text || null
}

export function runtimeBriefForTarget(
  roster: Pick<TeamRoster, 'chief_of_staff_id' | 'chief_of_staff_instructions'>,
  target: string | null | undefined,
): string | null {
  const cosId = roster.chief_of_staff_id?.trim() || ''
  if (!cosId) return null
  const dest = (target || '').trim() || 'all'
  if (dest === 'all' || dest === '*' || dest === cosId) {
    return cosBriefForMember(roster, cosId)
  }
  return null
}
