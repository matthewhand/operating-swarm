import { describe, expect, it } from 'vitest'
import {
  addMember,
  addRoleSlot,
  addToolSlot,
  applySlotMemberChange,
  assignableMembersForSlot,
  canAddRoleSlot,
  childTeamIds,
  COMPOSABLE_TEAM_ROLES,
  cosBriefForMember,
  DEFAULT_COS_STARTER,
  deriveWiresFromTools,
  DRAG_MIME,
  emptyRosterDraft,
  encodeDragAgent,
  encodeDragRole,
  encodeDragTool,
  FIRST_AGENT_VALUE,
  firstAgentLeadId,
  isCosEligibleMember,
  memberKey,
  nestRosters,
  parseDragAgent,
  parseDragRole,
  parseDragRosterIndex,
  parseDragTool,
  parseRosterMember,
  parseTeamRoster,
  parseTeamRosterList,
  parseTeamTool,
  pruneToolSlots,
  reorderMembers,
  restoreCosId,
  ROLE_DRAG_MIME,
  ROSTER_DRAG_MIME,
  runtimeBriefForTarget,
  serializeToolSlots,
  setMemberRole,
  slotsFromMembers,
  stampCosRole,
  TOOL_DRAG_MIME,
  unassignedMembers,
} from '../teamRoster'

describe('teamRoster (REQ-28)', () => {
  it('parses kind=remote Hermes/OMB/Rakazo members (PR #318 / REQ-28)', () => {
    const roster = parseTeamRoster({
      id: 'harness',
      object: 'team_roster',
      name: 'Harness',
      members: [
        { id: 'hermes', kind: 'remote', role: 'default', source: 'placeholder:remote:hermes' },
        { id: 'omb', kind: 'remote', role: 'default', source: 'placeholder:remote:omb' },
        { id: 'rakazo', kind: 'remote', role: 'default', source: 'placeholder:remote:rakazo' },
      ],
    })
    expect(roster?.members.map((m) => [m.id, m.kind])).toEqual([
      ['hermes', 'remote'],
      ['omb', 'remote'],
      ['rakazo', 'remote'],
    ])
    expect(parseRosterMember({ id: 'grok-cli', name: 'Grok CLI', kind: 'cli', role: 'default', source: 'cli:grok' })).toMatchObject(
      { id: 'grok-cli', name: 'Grok CLI', kind: 'cli' },
    )
    expect(parseTeamRoster({ id: 'alias', object: 'team', llm_profile: 'gpt' })).toBeNull()
  })

  it('parses kind=team with team_id and ignores blueprint-shaped rows', () => {
    const roster = parseTeamRoster({
      id: 'office',
      object: 'team_roster',
      name: 'Office',
      members: [
        { id: 'research', kind: 'team', team_id: 'research', role: 'default', source: 'team:research' },
        { id: 'w3p1', kind: 'herdr', role: 'default', source: 'herdr:w3:p1' },
      ],
    })
    expect(roster?.members[0]).toMatchObject({ kind: 'team', team_id: 'research' })
    expect(roster?.members[1].kind).toBe('herdr')
    expect(parseTeamRoster({ id: 'codey', name: 'Codey', object: 'blueprint' })).toBeNull()
  })

  it('nests child teams under the parent', () => {
    const list = parseTeamRosterList({
      object: 'list',
      data: [
        {
          id: 'office',
          object: 'team_roster',
          name: 'Office',
          members: [{ id: 'research', kind: 'team', team_id: 'research', role: 'default', source: 'team:research' }],
        },
        {
          id: 'research',
          object: 'team_roster',
          name: 'Research',
          members: [{ id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' }],
        },
      ],
    })
    expect(childTeamIds(list[0])).toEqual(['research'])
    const tree = nestRosters(list)
    expect(tree).toHaveLength(1)
    expect(tree[0].id).toBe('office')
    expect(tree[0].children.map((c) => c.id)).toEqual(['research'])
  })
})

describe('teamRoster CoS + composer helpers (REQ-107)', () => {
  it('does not auto-pick a CoS on an empty draft', () => {
    const draft = emptyRosterDraft()
    expect(draft.chiefOfStaffId).toBeNull()
    expect(draft.chiefOfStaffInstructions).toBe(DEFAULT_COS_STARTER)
    expect(DEFAULT_COS_STARTER.toLowerCase()).not.toMatch(/api_key|secret|token|:8001/)
  })

  it('round-trips drag payload and adds members without assigning CoS', () => {
    const agent = { id: 'jeeves', name: 'Jeeves', kind: 'api' as const, source: 'blueprint:jeeves' }
    const parsed = parseDragAgent(encodeDragAgent(agent))
    expect(parsed).toMatchObject(agent)
    const members = addMember([], agent)
    expect(members).toHaveLength(1)
    expect(restoreCosId({ members, chief_of_staff_id: null })).toBeNull()
  })

  it('omits remotes from CoS eligibility and keeps two team briefs', () => {
    const remote = { id: 'hermes', kind: 'remote' as const, role: 'default', source: 'remote:hermes' }
    const jeeves = { id: 'jeeves', kind: 'api' as const, role: 'default', source: 'blueprint:jeeves' }
    expect(isCosEligibleMember(remote)).toBe(false)
    expect(isCosEligibleMember(jeeves)).toBe(true)
    const stamped = stampCosRole([jeeves, remote], 'jeeves')
    expect(stamped[0].role).toBe('chief_of_staff')
    const teamA = {
      chief_of_staff_id: 'jeeves',
      chief_of_staff_instructions: 'prefer grok_agent for revision control',
    }
    const teamB = {
      chief_of_staff_id: 'jeeves',
      chief_of_staff_instructions: 'use skeptic only after implement',
    }
    expect(cosBriefForMember(teamA, 'jeeves')).toContain('revision control')
    expect(cosBriefForMember(teamB, 'jeeves')).toContain('after implement')
    expect(runtimeBriefForTarget(teamA, 'all')).toContain('revision control')
    expect(runtimeBriefForTarget(teamA, 'skeptic')).toBeNull()
    expect(runtimeBriefForTarget({ chief_of_staff_id: null, chief_of_staff_instructions: 'x' }, 'all')).toBeNull()
  })

  it('parses saved CoS fields on a roster', () => {
    const roster = parseTeamRoster({
      id: 'lab',
      object: 'team_roster',
      name: 'Lab',
      members: [{ id: 'jeeves', kind: 'api', role: 'chief_of_staff', source: 'blueprint:jeeves' }],
      chief_of_staff_id: 'jeeves',
      chief_of_staff_instructions: 'coordinate the roster',
    })
    expect(roster?.chief_of_staff_id).toBe('jeeves')
    expect(roster?.chief_of_staff_instructions).toBe('coordinate the roster')
  })
})

// #181 — advisor selectable as a team member role
describe('advisor in TEAM_MEMBER_ROLES (#181)', () => {
  it('offers advisor alongside skeptic and CoS', async () => {
    const { TEAM_MEMBER_ROLES } = await import('../teamRoster')
    expect(TEAM_MEMBER_ROLES).toContain('advisor')
    expect(TEAM_MEMBER_ROLES).toContain('skeptic')
  })
})

describe('teamRoster role slots (issue #104)', () => {
  const jeeves = { id: 'jeeves', name: 'Jeeves', kind: 'api' as const, source: 'blueprint:jeeves', role: 'default' }
  const grok = { id: 'grok', name: 'grok', kind: 'cli' as const, source: 'cli:grok', role: 'default' }
  const acp = { id: 'acp', name: 'ACP', kind: 'remote' as const, source: 'placeholder:remote:acp', role: 'default' }

  it('lists canonical composer roles without default', () => {
    expect(COMPOSABLE_TEAM_ROLES).toEqual([
      'support',
      'gate',
      'skeptic',
      'chief_of_staff',
      'suggestions',
      'engineer',
    ])
    expect(COMPOSABLE_TEAM_ROLES).not.toContain('default')
    expect(COMPOSABLE_TEAM_ROLES).not.toContain('advisor')
  })

  it('uses a distinct MIME from agent drags', () => {
    expect(ROLE_DRAG_MIME).toBe('application/x-swarm-team-role')
    expect(ROLE_DRAG_MIME).not.toBe(DRAG_MIME)
    expect(parseDragRole(encodeDragRole('skeptic'))).toBe('skeptic')
    expect(parseDragRole(encodeDragAgent(jeeves))).toBeNull()
    expect(parseDragAgent(encodeDragRole('gate'))).toBeNull()
    expect(parseDragRole(encodeDragRole('default' as never))).toBeNull()
  })

  it('treats default as unassigned and builds slots from assigned members', () => {
    const members = [jeeves, { ...grok, role: 'skeptic' }]
    expect(unassignedMembers(members).map((m) => m.id)).toEqual(['jeeves'])
    const slots = slotsFromMembers(members)
    expect(slots).toHaveLength(1)
    expect(slots[0]).toMatchObject({ role: 'skeptic', memberKey: memberKey(grok) })
  })

  it('dropdown options skip members already in another slot, keeping the current pick', () => {
    const members = [
      { ...jeeves, role: 'skeptic' },
      grok,
      acp,
    ]
    const slot = { id: 's1', role: 'skeptic' as const, memberKey: memberKey(jeeves) }
    const options = assignableMembersForSlot(members, slot)
    expect(options.map((m) => m.id)).toEqual(['jeeves', 'grok', 'acp'])
    const empty = { id: 's2', role: 'gate' as const, memberKey: null }
    expect(assignableMembersForSlot(members, empty).map((m) => m.id)).toEqual(['grok', 'acp'])
  })

  it('CoS slot options omit remotes and at most one CoS slot is allowed', () => {
    const members = [jeeves, grok, acp]
    const slot = { id: 'cos', role: 'chief_of_staff' as const, memberKey: null }
    expect(assignableMembersForSlot(members, slot).map((m) => m.id)).toEqual(['jeeves', 'grok'])
    const withCos = addRoleSlot([], 'chief_of_staff')
    expect(canAddRoleSlot(withCos, 'chief_of_staff')).toBe(false)
    expect(addRoleSlot(withCos, 'chief_of_staff')).toHaveLength(1)
    expect(canAddRoleSlot(withCos, 'skeptic')).toBe(true)
  })

  it('assigning or clearing a slot returns the previous agent to unassigned', () => {
    const members = [jeeves, grok]
    const slot = { id: 's1', role: 'engineer' as const, memberKey: null }
    const assigned = applySlotMemberChange(members, slot, grok)
    expect(assigned.find((m) => m.id === 'grok')?.role).toBe('engineer')
    const moved = applySlotMemberChange(
      assigned,
      { ...slot, memberKey: memberKey(grok) },
      jeeves,
    )
    expect(moved.find((m) => m.id === 'grok')?.role).toBe('default')
    expect(moved.find((m) => m.id === 'jeeves')?.role).toBe('engineer')
    const cleared = applySlotMemberChange(moved, { ...slot, memberKey: memberKey(jeeves) }, null)
    expect(cleared.every((m) => m.role === 'default')).toBe(true)
    expect(setMemberRole(cleared, jeeves, 'support')[0].role).toBe('support')
  })
})

describe('teamRoster First agent lead (issue #105)', () => {
  it('reorders members and firstAgentLeadId tracks roster index 0', () => {
    const jeeves = { id: 'jeeves', name: 'Jeeves', kind: 'api' as const, source: 'blueprint:jeeves' }
    const grok = { id: 'grok', name: 'grok', kind: 'cli' as const, source: 'cli:grok' }
    const remote = { id: 'acp', name: 'ACP', kind: 'remote' as const, source: 'placeholder:remote:acp' }
    const members = addMember(addMember([], jeeves), grok)
    expect(firstAgentLeadId(members)).toBe('jeeves')
    const moved = reorderMembers(members, 1, 0)
    expect(moved.map((row) => row.id)).toEqual(['grok', 'jeeves'])
    expect(firstAgentLeadId(moved)).toBe('grok')
    expect(reorderMembers(members, 0, 0)).toBe(members)
    expect(reorderMembers(members, -1, 0)).toBe(members)
    expect(firstAgentLeadId([
      { id: 'acp', kind: 'remote', role: 'default', source: 'placeholder:remote:acp' },
    ])).toBeNull()
    expect(firstAgentLeadId(addMember([remote], jeeves))).toBeNull()
    expect(parseDragRosterIndex('1')).toBe(1)
    expect(parseDragRosterIndex('nope')).toBeNull()
    expect(ROSTER_DRAG_MIME).not.toBe(DRAG_MIME)
    expect(FIRST_AGENT_VALUE).toBe('__first__')
  })
})

describe('teamRoster Tools pane (issue #107)', () => {
  const jeeves = { id: 'jeeves', name: 'Jeeves', kind: 'api' as const, source: 'blueprint:jeeves', role: 'default' }
  const grok = { id: 'grok', name: 'grok', kind: 'cli' as const, source: 'cli:grok', role: 'default' }

  it('parses tools and derives wires, rejecting unknown types and secret MCP fields', () => {
    const roster = parseTeamRoster({
      id: 'lab',
      object: 'team_roster',
      name: 'Lab',
      members: [jeeves, grok],
      tools: [
        { type: 'handoff', to: 'grok' },
        { type: 'as_tool', agent: 'jeeves' },
        { type: 'mcp', server: 'github', agents: [] },
      ],
    })
    expect(roster?.tools).toEqual([
      { type: 'handoff', to: 'grok' },
      { type: 'as_tool', agent: 'jeeves' },
      { type: 'mcp', server: 'github', agents: [] },
    ])
    expect(roster?.wires).toEqual({ handoff: true, as_tool: true })
    expect(parseTeamTool({ type: 'nope', to: 'x' })).toBeNull()
    expect(parseTeamTool({ type: 'mcp', server: 'github', agents: [], env: { API_KEY: 'sk-live' } })).toBeNull()
    expect(parseTeamTool({ type: 'mcp', server: 'github', agents: ['jeeves'] })).toEqual({
      type: 'mcp',
      server: 'github',
      agents: ['jeeves'],
    })
    expect(deriveWiresFromTools([])).toEqual({ handoff: false, as_tool: false })
    expect(emptyRosterDraft().tools).toEqual([])
    expect(emptyRosterDraft().wires).toEqual({ handoff: false, as_tool: false })
  })

  it('keeps incomplete slots in the UI and serializes only complete tools', () => {
    expect(TOOL_DRAG_MIME).toBe('application/x-swarm-team-tool')
    expect(TOOL_DRAG_MIME).not.toBe(DRAG_MIME)
    expect(parseDragTool(encodeDragTool({ type: 'handoff' }))).toEqual({ type: 'handoff' })
    expect(parseDragTool(encodeDragTool({ type: 'mcp', server: 'github' }))).toEqual({
      type: 'mcp',
      server: 'github',
    })
    expect(parseDragTool(encodeDragRole('skeptic'))).toBeNull()
    let slots = addToolSlot([], { type: 'handoff' })
    slots = addToolSlot(slots, { type: 'mcp', server: 'github' })
    expect(serializeToolSlots(slots)).toEqual([{ type: 'mcp', server: 'github', agents: [] }])
    slots = [
      { id: 'h', tool: { type: 'handoff', to: 'grok', from: 'jeeves' } },
      { id: 'm', tool: { type: 'mcp', server: 'github', agents: ['grok', 'missing'] } },
    ]
    const pruned = pruneToolSlots(slots, [jeeves])
    expect(pruned[0].tool).toEqual({ type: 'handoff', to: '', from: 'jeeves' })
    expect(pruned[1].tool).toEqual({ type: 'mcp', server: 'github', agents: [] })
  })
})
