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

export type TeamTool =
  | { type: 'handoff'; to: string; from?: string }
  | { type: 'as_tool'; agent: string }
  | { type: 'mcp'; server: string; agents: string[] }

export type TeamToolDraft = TeamTool
export type BuiltinTeamToolType = 'handoff' | 'as_tool'
export type AddableTeamTool =
  | { type: 'handoff' }
  | { type: 'as_tool' }
  | { type: 'mcp'; server: string }

export interface TeamRoster {
  id: string
  object?: 'team_roster'
  name: string
  members: TeamRosterMember[]
  wires?: { handoff: boolean; as_tool: boolean }
  /** Composer Tools pane slots (issue #107). Wires are derived from these. */
  tools?: TeamTool[]
  /** Optional team-scoped CoS (REQ-107). Composer defaults to First agent (#105). */
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
  | 'engineer'

/** Canonical composer roles (issue #104). `default` is unassigned; `advisor` stays on TEAM_MEMBER_ROLES. */
export type ComposableTeamRole = Exclude<TeamMemberRole, 'default' | 'advisor'>

export const TEAM_MEMBER_ROLES: readonly TeamMemberRole[] = [
  'default',
  'support',
  'gate',
  'skeptic',
  'advisor',
  'chief_of_staff',
  'suggestions',
  'engineer',
]

export const COMPOSABLE_TEAM_ROLES: readonly ComposableTeamRole[] = [
  'support',
  'gate',
  'skeptic',
  'chief_of_staff',
  'suggestions',
  'engineer',
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
export const ROLE_DRAG_MIME = 'application/x-swarm-team-role'
export const ROSTER_DRAG_MIME = 'application/x-swarm-team-roster-index'
export const TOOL_DRAG_MIME = 'application/x-swarm-team-tool'

export const BUILTIN_TEAM_TOOLS: readonly BuiltinTeamToolType[] = ['handoff', 'as_tool']

/** MCP row keys that must never land on a roster tool slot (secrets stay in Settings). */
export const SECRET_MCP_TOOL_KEYS = [
  'env',
  'headers',
  'token',
  'api_key',
  'secret',
  'authorization',
  'password',
  'credentials',
  'key',
] as const

export interface RoleSlot {
  id: string
  role: ComposableTeamRole
  memberKey: string | null
}

export interface ToolSlot {
  id: string
  tool: TeamToolDraft
}

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
/** Sentinel for the Team lead picker: CoS tracks members[0] (issue #105). */
export const FIRST_AGENT_VALUE = '__first__'

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
  const tools = Array.isArray(row.tools) ? parseTeamTools(row.tools) : []
  const hasToolsField = Array.isArray(row.tools)
  return {
    id,
    object: 'team_roster',
    name: String(row.name || id),
    members,
    tools,
    wires: hasToolsField
      ? deriveWiresFromTools(tools)
      : {
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
  tools: TeamTool[]
  chiefOfStaffId: string | null
  chiefOfStaffInstructions: string
} {
  return {
    name: '',
    members: [],
    tools: [],
    wires: deriveWiresFromTools([]),
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

export function reorderMembers(
  members: TeamRosterMember[],
  fromIndex: number,
  toIndex: number,
): TeamRosterMember[] {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= members.length ||
    toIndex >= members.length
  ) {
    return members
  }
  const next = members.slice()
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  return next
}

export function setMemberRole(
  members: TeamRosterMember[],
  agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>,
  role: TeamMemberRole,
): TeamRosterMember[] {
  const key = memberKey(agent)
  return members.map((row) => (memberKey(row) === key ? { ...row, role } : row))
}

export function isComposableTeamRole(value: unknown): value is ComposableTeamRole {
  return typeof value === 'string' && (COMPOSABLE_TEAM_ROLES as readonly string[]).includes(value)
}

export function isUnassignedRole(role: string | undefined | null): boolean {
  return !role || role === 'default'
}

export function unassignedMembers(members: TeamRosterMember[]): TeamRosterMember[] {
  return members.filter((row) => isUnassignedRole(row.role))
}

export function memberByKey(
  members: TeamRosterMember[],
  key: string | null | undefined,
): TeamRosterMember | undefined {
  if (!key) return undefined
  return members.find((row) => memberKey(row) === key)
}

export function newRoleSlot(
  role: ComposableTeamRole,
  assignedKey: string | null = null,
  id?: string,
): RoleSlot {
  return {
    id: id ?? `role-slot-${role}-${Math.random().toString(36).slice(2, 10)}`,
    role,
    memberKey: assignedKey,
  }
}

export function slotsFromMembers(members: TeamRosterMember[]): RoleSlot[] {
  return members
    .filter((row) => isComposableTeamRole(row.role))
    .map((row) => newRoleSlot(row.role as ComposableTeamRole, memberKey(row)))
}

export function canAddRoleSlot(slots: RoleSlot[], role: ComposableTeamRole): boolean {
  if (role === 'chief_of_staff') {
    return !slots.some((slot) => slot.role === 'chief_of_staff')
  }
  return true
}

export function addRoleSlot(slots: RoleSlot[], role: ComposableTeamRole): RoleSlot[] {
  if (!canAddRoleSlot(slots, role)) return slots
  return [...slots, newRoleSlot(role)]
}

export function removeRoleSlot(slots: RoleSlot[], slotId: string): RoleSlot[] {
  return slots.filter((slot) => slot.id !== slotId)
}

export function assignRoleSlot(
  slots: RoleSlot[],
  slotId: string,
  nextMemberKey: string | null,
): RoleSlot[] {
  return slots.map((slot) => (slot.id === slotId ? { ...slot, memberKey: nextMemberKey } : slot))
}

export function unassignSlotsForMember(
  slots: RoleSlot[],
  agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>,
): RoleSlot[] {
  const key = memberKey(agent)
  return slots.map((slot) => (slot.memberKey === key ? { ...slot, memberKey: null } : slot))
}

export function applySlotMemberChange(
  members: TeamRosterMember[],
  slot: RoleSlot,
  nextMember: TeamRosterMember | null,
): TeamRosterMember[] {
  let next = members
  const prev = memberByKey(members, slot.memberKey)
  if (prev) next = setMemberRole(next, prev, 'default')
  if (nextMember) next = setMemberRole(next, nextMember, slot.role)
  return next
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

export function newToolSlot(tool: TeamToolDraft, id?: string): ToolSlot {
  return {
    id: id ?? `tool-slot-${tool.type}-${Math.random().toString(36).slice(2, 10)}`,
    tool,
  }
}

export function slotsFromTools(tools: TeamTool[] | undefined | null): ToolSlot[] {
  if (!tools || tools.length === 0) return []
  return tools.map((tool) => newToolSlot(tool))
}

export function addToolSlot(slots: ToolSlot[], addable: AddableTeamTool): ToolSlot[] {
  if (addable.type === 'handoff') {
    return [...slots, newToolSlot({ type: 'handoff', to: '' })]
  }
  if (addable.type === 'as_tool') {
    return [...slots, newToolSlot({ type: 'as_tool', agent: '' })]
  }
  const server = addable.server.trim()
  if (!server) return slots
  return [...slots, newToolSlot({ type: 'mcp', server, agents: [] })]
}

export function removeToolSlot(slots: ToolSlot[], slotId: string): ToolSlot[] {
  return slots.filter((slot) => slot.id !== slotId)
}

export function updateToolSlot(
  slots: ToolSlot[],
  slotId: string,
  tool: TeamToolDraft,
): ToolSlot[] {
  return slots.map((slot) => (slot.id === slotId ? { ...slot, tool } : slot))
}

export function hasSecretMcpToolFields(row: Record<string, unknown>): boolean {
  return SECRET_MCP_TOOL_KEYS.some((key) => key in row)
}

export function parseTeamTool(raw: unknown): TeamTool | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const type = String(row.type || '').trim()
  if (type === 'handoff') {
    const to = String(row.to || '').trim()
    if (!to) return null
    const from = String(row.from || '').trim()
    return from ? { type: 'handoff', to, from } : { type: 'handoff', to }
  }
  if (type === 'as_tool') {
    const agent = String(row.agent || '').trim()
    if (!agent) return null
    return { type: 'as_tool', agent }
  }
  if (type === 'mcp') {
    if (hasSecretMcpToolFields(row)) return null
    const server = String(row.server || '').trim()
    if (!server) return null
    const agents = Array.isArray(row.agents)
      ? row.agents.map((item) => String(item || '').trim()).filter(Boolean)
      : []
    return { type: 'mcp', server, agents }
  }
  return null
}

export function parseTeamTools(raw: unknown): TeamTool[] {
  if (!Array.isArray(raw)) return []
  return raw.map(parseTeamTool).filter((row): row is TeamTool => row !== null)
}

export function deriveWiresFromTools(tools: readonly TeamTool[]): { handoff: boolean; as_tool: boolean } {
  return {
    handoff: tools.some((tool) => tool.type === 'handoff'),
    as_tool: tools.some((tool) => tool.type === 'as_tool'),
  }
}

export function isCompleteTeamTool(tool: TeamToolDraft): boolean {
  if (tool.type === 'handoff') return Boolean(tool.to.trim())
  if (tool.type === 'as_tool') return Boolean(tool.agent.trim())
  return Boolean(tool.server.trim())
}

export function serializeToolSlots(slots: ToolSlot[]): TeamTool[] {
  return slots.map((slot) => slot.tool).filter(isCompleteTeamTool)
}

export function pruneToolSlots(slots: ToolSlot[], members: TeamRosterMember[]): ToolSlot[] {
  const ids = new Set(members.map((row) => row.id))
  return slots.map((slot) => {
    const tool = slot.tool
    if (tool.type === 'handoff') {
      const next: TeamToolDraft = { type: 'handoff', to: tool.to && ids.has(tool.to) ? tool.to : '' }
      if (tool.from && ids.has(tool.from)) next.from = tool.from
      return { ...slot, tool: next }
    }
    if (tool.type === 'as_tool') {
      return {
        ...slot,
        tool: { type: 'as_tool', agent: tool.agent && ids.has(tool.agent) ? tool.agent : '' },
      }
    }
    return {
      ...slot,
      tool: { type: 'mcp', server: tool.server, agents: tool.agents.filter((id) => ids.has(id)) },
    }
  })
}

export function encodeDragTool(addable: AddableTeamTool): string {
  return JSON.stringify(addable)
}

export function parseDragTool(raw: string): AddableTeamTool | null {
  if (!raw || !raw.trim()) return null
  try {
    const row = JSON.parse(raw) as Record<string, unknown>
    const type = String(row.type || '').trim()
    if (type === 'handoff' || type === 'as_tool') return { type }
    if (type === 'mcp') {
      const server = String(row.server || '').trim()
      return server ? { type: 'mcp', server } : null
    }
    return null
  } catch {
    return null
  }
}

export function encodeDragRole(role: ComposableTeamRole): string {
  return JSON.stringify({ role })
}

export function parseDragRole(raw: string): ComposableTeamRole | null {
  if (!raw || !raw.trim()) return null
  try {
    const row = JSON.parse(raw) as Record<string, unknown>
    const role = String(row.role || '').trim()
    return isComposableTeamRole(role) ? role : null
  } catch {
    return null
  }
}

export function dataTransferHasType(
  dt: Pick<DataTransfer, 'types' | 'getData'> | null | undefined,
  mime: string,
): boolean {
  if (!dt) return false
  const types = Array.from(dt.types || [])
  if (types.includes(mime)) return true
  if (types.length === 0) {
    try {
      return Boolean(dt.getData(mime))
    } catch {
      return false
    }
  }
  return false
}

export function isCosEligibleKind(kind: string | undefined): boolean {
  return Boolean(kind && (COS_ELIGIBLE_KINDS as readonly string[]).includes(kind))
}

export function isCosEligibleMember(member: Pick<TeamRosterMember, 'kind'>): boolean {
  return isCosEligibleKind(member.kind)
}

export function firstAgentLeadId(members: TeamRosterMember[]): string | null {
  const first = members[0]
  if (!first || !isCosEligibleMember(first)) return null
  return first.id
}

export function parseDragRosterIndex(raw: string): number | null {
  if (typeof raw !== 'string') return null
  const text = raw.trim()
  if (!/^\d+$/.test(text)) return null
  return Number(text)
}

export function assignableMembersForSlot(
  members: TeamRosterMember[],
  slot: RoleSlot,
): TeamRosterMember[] {
  const used = new Set(
    members
      .filter((row) => !isUnassignedRole(row.role) && memberKey(row) !== slot.memberKey)
      .map((row) => memberKey(row)),
  )
  const candidates = members.filter((row) => !used.has(memberKey(row)))
  if (slot.role === 'chief_of_staff') {
    return candidates.filter(isCosEligibleMember)
  }
  return candidates
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
