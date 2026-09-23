import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  ALL_MEMBERS_PARAM,
  ALL_MEMBERS_TARGET,
  DEMO_TEAM_ROSTER,
  MANAGE_TEAMS_HREF,
  applyTeamMemberSessionParam,
  fetchTeamRosters,
  isAllMembersChoice,
  memberOptionLabel,
  memberTargetLabel,
  parseTeamRosters,
  teamHideId,
  teamThreadId,
} from '../teamRosters'

describe('parseTeamRosters', () => {
  it('reads a list envelope of team_roster objects', () => {
    const parsed = parseTeamRosters({
      object: 'list',
      data: [
        {
          id: 'alpha',
          object: 'team_roster',
          name: 'Alpha',
          description: 'First',
          members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
        },
      ],
    })
    expect(parsed).toHaveLength(1)
    expect(parsed[0].id).toBe('alpha')
    expect(parsed[0].members[0]).toEqual({
      id: 'codey',
      name: 'Codey',
      kind: 'agent',
      role: 'coder',
    })
  })

  it('keeps blueprint_id and declared personas', () => {
    const parsed = parseTeamRosters({
      object: 'list',
      data: [
        {
          id: 'squad',
          object: 'team_roster',
          name: 'Squad',
          blueprint_id: 'software_dev',
          persona_count: 3,
          personas: [{ name: 'Researcher' }, { name: 'Writer' }, { name: 'Reviewer' }],
          members: [],
        },
      ],
    })
    expect(parsed[0].blueprintId).toBe('software_dev')
    expect(parsed[0].persona_count).toBe(3)
    expect(parsed[0].personas?.map((p) => p.name)).toEqual(['Researcher', 'Writer', 'Reviewer'])
  })

  it('ignores /v1/teams LLM-alias shapes (no members / object=team without roster)', () => {
    expect(
      parseTeamRosters({
        object: 'list',
        data: [{ id: 'alias', object: 'team', description: 'LLM profile', llm_profile: 'gpt' }],
      }),
    ).toEqual([])
  })

  it('ignores blueprint catalog objects so a mixed GET cannot poison the pane', () => {
    expect(
      parseTeamRosters({
        object: 'list',
        data: [
          {
            id: 'codey',
            object: 'blueprint',
            name: 'Codey',
            description: 'Code assistant',
            members: [{ id: 'x', name: 'X' }],
          },
        ],
      }),
    ).toEqual([])
  })

  it('accepts a bare array or { teams } wrapper', () => {
    const team = {
      id: 'beta',
      name: 'Beta',
      members: [{ id: 'stewie', name: 'Stewie' }],
    }
    expect(parseTeamRosters([team])[0].id).toBe('beta')
    expect(parseTeamRosters({ teams: [team] })[0].id).toBe('beta')
  })
})

describe('labels and ids', () => {
  it('labels All members vs a chosen seat', () => {
    const team = {
      id: 'demo-team',
      name: 'Demo Team',
      description: '',
      members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
    }
    expect(memberTargetLabel('all', team)).toBe('All members')
    expect(memberTargetLabel('codey', team)).toBe('Codey (agent/coder)')
  })

  it('formats name + kind/role for the unlabeled dropdown', () => {
    expect(memberOptionLabel({ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' })).toBe(
      'Codey (agent/coder)',
    )
    expect(memberOptionLabel({ id: 'x', name: 'X', role: 'ops' })).toBe('X (ops)')
    expect(memberOptionLabel({ id: 'y', name: 'Y' })).toBe('Y')
    expect(memberOptionLabel({ id: 'hermes', name: 'Hermes', kind: 'remote', role: 'default' })).toBe(
      'Hermes (remote/default)',
    )
    expect(memberOptionLabel({ id: 'omb', name: 'OMB', kind: 'remote', role: 'default' })).toBe(
      'OMB (remote/default)',
    )
    expect(memberOptionLabel({ id: 'rakazo', name: 'Rakazo', kind: 'remote', role: 'default' })).toBe(
      'Rakazo (remote/default)',
    )
    expect(
      memberOptionLabel({
        id: 'openmousbot-remote',
        name: 'OpenMousBot Remote',
        kind: 'remote',
        role: 'default',
      }),
    ).toBe('OpenMousBot Remote (remote/default)')
    expect(
      memberOptionLabel({
        id: 'openmousbot-remote',
        name: 'OpenMousBot Remote',
        kind: 'remote',
        role: 'default',
      }),
    ).not.toMatch(/\bOMB\b/)
  })

  it('keeps Mode A kind-clear names from the showoff fixture', () => {
    const parsed = parseTeamRosters({
      object: 'list',
      data: [
        {
          id: 'demo-harness-kinds',
          object: 'team_roster',
          name: 'Demo Harness Kinds',
          members: [
            { id: 'grok-cli', name: 'Grok CLI', kind: 'cli', role: 'default' },
            { id: 'litellm-api', name: 'LiteLLM API', kind: 'api', role: 'default' },
            { id: 'hermes-remote', name: 'Hermes Remote', kind: 'remote', role: 'default' },
          ],
        },
      ],
    })
    expect(parsed[0].members.map((m) => m.name)).toEqual(['Grok CLI', 'LiteLLM API', 'Hermes Remote'])
    expect(memberOptionLabel(parsed[0].members[0])).toBe('Grok CLI (cli/default)')
  })

  it('keeps Mode B persona names and does not mix kind labels', () => {
    const parsed = parseTeamRosters({
      object: 'list',
      data: [
        {
          id: 'demo-sdlc-pipeline',
          object: 'team_roster',
          name: 'Demo SDLC Pipeline',
          members: [
            { id: 'cos', name: 'Chief of Staff', kind: 'api', role: 'chief_of_staff' },
            { id: 'ba', name: 'BA', kind: 'api', role: 'default' },
            { id: 'engineer', name: 'Engineer', kind: 'api', role: 'default' },
          ],
        },
      ],
    })
    expect(parsed[0].members.map((m) => m.name)).toEqual(['Chief of Staff', 'BA', 'Engineer'])
    expect(parsed[0].members.map((m) => m.name).join(' ')).not.toMatch(/LiteLLM API|Grok CLI/)
  })

  it('namespaces hide ids so a team cannot collide with an agent slug', () => {
    expect(teamHideId('demo-team')).toBe('team:demo-team')
    expect(teamThreadId('demo-team')).toBe('team-demo-team')
  })

  it('keeps All members / Manage Teams constants stable', () => {
    expect(ALL_MEMBERS_TARGET).toBe('all')
    expect(MANAGE_TEAMS_HREF).toBe('/teams/')
  })

  it('writes ?team=&session= for a member and clears session for All members', () => {
    const member = applyTeamMemberSessionParam(
      new URLSearchParams('team=demo-team'),
      'demo-team',
      'codey',
    )
    expect(member.get('team')).toBe('demo-team')
    expect(member.get('session')).toBe('codey')

    const all = applyTeamMemberSessionParam(member, 'demo-team', ALL_MEMBERS_TARGET)
    expect(all.get('team')).toBe('demo-team')
    expect(all.get('session')).toBeNull()
    // #288: All members is marked explicitly so a reload does not re-default to
    // the team's nominated seat (#169).
    expect(all.get(ALL_MEMBERS_PARAM)).toBe(ALL_MEMBERS_TARGET)
    expect(all.toString()).toBe('team=demo-team&members=all')
  })

  it('marks All members explicitly and drops the marker when a member is picked (#288)', () => {
    const all = applyTeamMemberSessionParam(
      new URLSearchParams('team=demo-team&session=codey'),
      'demo-team',
      ALL_MEMBERS_TARGET,
    )
    expect(isAllMembersChoice(all.get(ALL_MEMBERS_PARAM))).toBe(true)
    expect(all.get('session')).toBeNull()

    const member = applyTeamMemberSessionParam(all, 'demo-team', 'stewie')
    expect(member.get('session')).toBe('stewie')
    expect(member.get(ALL_MEMBERS_PARAM)).toBeNull()
    expect(isAllMembersChoice(member.get(ALL_MEMBERS_PARAM))).toBe(false)

    // A bare team link carries no member choice at all.
    expect(isAllMembersChoice(null)).toBe(false)
    expect(isAllMembersChoice('stewie')).toBe(false)
  })
})

describe('fetchTeamRosters', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns GET payload when team_rosters.json is present', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 'live',
              object: 'team_roster',
              name: 'Live',
              description: '',
              members: [{ id: 'a', name: 'A', kind: 'agent', role: 'lead' }],
            },
          ],
        }),
      } as Response),
    )
    const teams = await fetchTeamRosters()
    expect(teams).toHaveLength(1)
    expect(teams[0].id).toBe('live')
  })

  it('falls back to the demo stub when GET is missing or empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({}),
      } as Response),
    )
    await expect(fetchTeamRosters()).resolves.toEqual([DEMO_TEAM_ROSTER])
  })
})
