import { describe, expect, it } from 'vitest'
import {
  addMember,
  childTeamIds,
  cosBriefForMember,
  DEFAULT_COS_STARTER,
  emptyRosterDraft,
  encodeDragAgent,
  isCosEligibleMember,
  nestRosters,
  parseDragAgent,
  parseRosterMember,
  parseTeamRoster,
  parseTeamRosterList,
  restoreCosId,
  runtimeBriefForTarget,
  stampCosRole,
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
