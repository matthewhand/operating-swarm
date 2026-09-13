import { describe, it, expect, beforeEach } from 'vitest'
import { useAgentStore } from '../agent-store'
import { STARTER_API_ID, STARTER_CLI_ID, STARTER_REMOTE_ID, STARTER_SUPPORT_ID } from '../starter-agents'
import { AVATAR_THEME_STORAGE_KEY, dispatchAvatarTheme } from '../avatarTheme'
import type { Agent } from '../../types/agent'

const mockAgents: Agent[] = [
  {
    agent_id: 'router',
    name: 'Agent Router',
    specialty: 'Coordination',
    color: '#6366f1',
    icon: '🧭',
    type: 'orchestrator',
    group: 'orchestration'
  },
  {
    agent_id: 'researcher',
    name: 'Researcher',
    specialty: 'Research',
    color: '#10b981',
    icon: '🔍',
    type: 'specialist',
    group: 'specialists'
  },
  {
    agent_id: 'coder',
    name: 'Coder',
    specialty: 'Development',
    color: '#f59e0b',
    icon: '💻',
    type: 'specialist',
    group: 'tools'
  }
]

describe('useAgentStore avatar themes', () => {
  beforeEach(() => {
    localStorage.clear()
    useAgentStore.setState({
      avatarTheme: 'chassis',
      avatarThemeByAgent: {},
    })
  })

  it('persists the Swarm-wide avatar pack to swarm_avatar_theme (REQ-188C-3)', () => {
    useAgentStore.getState().setAvatarTheme('pixel')
    expect(useAgentStore.getState().avatarTheme).toBe('pixel')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('pixel')
  })

  it('synchronizes Swarm-wide avatar pack when dispatchAvatarTheme is called (REQ-188C-3)', () => {
    dispatchAvatarTheme('bland')
    expect(useAgentStore.getState().avatarTheme).toBe('bland')
  })

  it('stores a per-agent override and can clear it', () => {
    useAgentStore.getState().setAgentAvatarTheme('coder', 'glyph')
    expect(useAgentStore.getState().avatarThemeByAgent.coder).toBe('glyph')
    useAgentStore.getState().setAgentAvatarTheme('coder', null)
    expect(useAgentStore.getState().avatarThemeByAgent.coder).toBeUndefined()
  })

  it('assigns unique looks when the roster is loaded', () => {
    useAgentStore.getState().setAgents([...mockAgents])
    const { avatarThemeByAgent, avatarEyesByAgent, agents } = useAgentStore.getState()
    const pairs = agents.map((a) => `${avatarThemeByAgent[a.agent_id]}:${avatarEyesByAgent[a.agent_id]}`)
    expect(pairs.every((p) => !p.includes('undefined'))).toBe(true)
    expect(new Set(pairs).size).toBe(agents.length)
  })

  it('persists googly eye style', () => {
    useAgentStore.getState().setAvatarEyes('googly')
    expect(useAgentStore.getState().avatarEyes).toBe('googly')
    expect(JSON.parse(localStorage.getItem('agent_avatar_eyes') || '""')).toBe('googly')
    useAgentStore.getState().setAgentAvatarEyes('coder', 'crazy')
    expect(useAgentStore.getState().avatarEyesByAgent.coder).toBe('crazy')
    useAgentStore.getState().setAgentAvatarEyes('coder', null)
    expect(useAgentStore.getState().avatarEyesByAgent.coder).toBeUndefined()
  })
})

describe('useAgentStore does not auto-hide agents on initial load', () => {
  beforeEach(() => {
    localStorage.clear()
    useAgentStore.setState({
      agents: [],
      hiddenAgentIds: [],
      favouriteIds: [],
      selectedAgentId: 'router',
    })
  })

  it('keeps all agents visible and favouriteIds empty when setAgents is called with clean storage', () => {
    useAgentStore.getState().setAgents([...mockAgents])
    const { hiddenAgentIds, favouriteIds, selectedAgentId } = useAgentStore.getState()
    expect(hiddenAgentIds).toEqual([])
    expect(favouriteIds).toEqual([])
    expect(selectedAgentId).toBe('router')
  })

  it('cleans up legacy agent_sidebar_starters without auto-hiding', () => {
    localStorage.setItem('agent_sidebar_starters', 'support-cli-api-remote')
    localStorage.setItem('agent_hidden_ids', JSON.stringify(Array.from({ length: 96 }, (_, i) => `agent-${i}`)))
    localStorage.setItem('agent_favourite_ids', JSON.stringify([STARTER_SUPPORT_ID, STARTER_CLI_ID, STARTER_API_ID, STARTER_REMOTE_ID]))

    useAgentStore.getState().setAgents([...mockAgents])
    const { hiddenAgentIds, favouriteIds } = useAgentStore.getState()
    expect(localStorage.getItem('agent_sidebar_starters')).toBeNull()
    expect(hiddenAgentIds).toEqual([])
    expect(favouriteIds).toEqual([])
  })
})

describe('useAgentStore hide all keeps starters', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('agent_hidden_ids', '[]')
    localStorage.setItem('agent_sidebar_starters', 'support-cli-api-remote')
    useAgentStore.setState({
      agents: [],
      hiddenAgentIds: [],
      favouriteIds: [],
      selectedAgentId: 'coder',
    })
  })

  it('hides the catalog and keeps CLI, API, and remote starters visible', () => {
    useAgentStore.getState().setAgents([...mockAgents])
    useAgentStore.getState().hideAllAgents()
    const { hiddenAgentIds, favouriteIds, selectedAgentId, agents } = useAgentStore.getState()
    expect(agents.map((a) => a.agent_id)).toEqual(expect.arrayContaining([
      STARTER_SUPPORT_ID,
      STARTER_CLI_ID,
      STARTER_API_ID,
      STARTER_REMOTE_ID,
      'coder',
    ]))
    expect(agents.map((a) => a.agent_id)).not.toEqual(expect.arrayContaining(['starter-hermes', 'starter-dsh']))
    expect(hiddenAgentIds).toEqual(expect.arrayContaining(['coder', 'researcher', 'router']))
    expect(hiddenAgentIds).not.toEqual(expect.arrayContaining([
      STARTER_SUPPORT_ID,
      STARTER_CLI_ID,
      STARTER_API_ID,
      STARTER_REMOTE_ID,
    ]))
    expect(favouriteIds).toEqual([])
    expect(selectedAgentId).toBe(STARTER_SUPPORT_ID)
  })
})

describe('useAgentStore rename and purpose', () => {
  beforeEach(() => {
    localStorage.clear()
    useAgentStore.setState({
      agents: [...mockAgents],
      renames: {},
      purposes: {},
    })
  })

  it('renames an agent and persists', () => {
    useAgentStore.getState().renameAgent('coder', 'Byte')
    expect(useAgentStore.getState().agents.find((a) => a.agent_id === 'coder')?.customName).toBe('Byte')
    expect(JSON.parse(localStorage.getItem('agent_renames') || '{}').coder).toBe('Byte')
  })

  it('sets purpose overlay and persists', () => {
    useAgentStore.getState().setAgentPurpose('researcher', 'Find the paper')
    const agent = useAgentStore.getState().agents.find((a) => a.agent_id === 'researcher')
    expect(agent?.customPurpose).toBe('Find the paper')
    expect(JSON.parse(localStorage.getItem('agent_purposes') || '{}').researcher).toBe('Find the paper')
    useAgentStore.getState().setAgents([...mockAgents])
    expect(useAgentStore.getState().agents.find((a) => a.agent_id === 'researcher')?.customPurpose).toBe('Find the paper')
  })

  it('persists a per-agent remote member', () => {
    useAgentStore.getState().setAgentRemoteMember('openmausbot', 'cos-1')
    expect(useAgentStore.getState().remoteMemberByAgent.openmausbot).toBe('cos-1')
    expect(JSON.parse(localStorage.getItem('agent_remote_members') || '{}').openmausbot).toBe('cos-1')
    useAgentStore.getState().setAgentRemoteMember('openmausbot', '')
    expect(useAgentStore.getState().remoteMemberByAgent.openmausbot).toBeUndefined()
  })
})

describe('useAgentStore reordering', () => {
  beforeEach(() => {
    localStorage.clear()
    useAgentStore.setState({
      agents: [...mockAgents],
      customOrder: [],
      customSections: {},
      favouriteIds: [],
      renames: {},
      selectedAgentId: 'router'
    })
  })

  it('reorders agents and updates customOrder array', () => {
    const { reorderAgents } = useAgentStore.getState()
    reorderAgents('coder', 'router')

    const state = useAgentStore.getState()
    expect(state.agents[0].agent_id).toBe('coder')
    expect(state.customOrder).toEqual(['coder', 'router', 'researcher'])

    // Verify localStorage persistence
    const stored = JSON.parse(localStorage.getItem('agent_custom_order') || '[]')
    expect(stored).toEqual(['coder', 'router', 'researcher'])
  })

  it('adopts target section when moved into another section', () => {
    const { reorderAgents } = useAgentStore.getState()
    // Move coder (tools) onto researcher (specialists)
    reorderAgents('coder', 'researcher')

    const state = useAgentStore.getState()
    const movedCoder = state.agents.find((a) => a.agent_id === 'coder')
    expect(movedCoder?.group).toBe('specialists')
    expect(state.customSections['coder']).toBe('specialists')
  })

  it('preserves custom order when setAgents is called', () => {
    const { reorderAgents, setAgents } = useAgentStore.getState()
    reorderAgents('coder', 'router')

    // Simulate backend refetch
    setAgents([...mockAgents])

    const state = useAgentStore.getState()
    expect(state.agents[0].agent_id).toBe('coder')
    expect(state.agents[1].agent_id).toBe('router')
    expect(state.agents[2].agent_id).toBe('researcher')
  })

  it('pins and unpins favourites in order', () => {
    const { pinFavourite, unpinFavourite } = useAgentStore.getState()
    pinFavourite('coder')
    pinFavourite('researcher', 'coder')
    expect(useAgentStore.getState().favouriteIds).toEqual(['researcher', 'coder'])
    expect(JSON.parse(localStorage.getItem('agent_favourite_ids') || '[]')).toEqual([
      'researcher',
      'coder',
    ])
    unpinFavourite('researcher')
    expect(useAgentStore.getState().favouriteIds).toEqual(['coder'])
  })

  it('supports explicit setCustomOrder', () => {
    const { setCustomOrder } = useAgentStore.getState()
    setCustomOrder(['researcher', 'coder', 'router'])

    const state = useAgentStore.getState()
    expect(state.agents.map((a) => a.agent_id)).toEqual(['researcher', 'coder', 'router'])
    expect(state.customOrder).toEqual(['researcher', 'coder', 'router'])
  })
})

describe('useAgentStore save as team', () => {
  const extra: Agent = {
    agent_id: 'writer',
    name: 'Writer',
    specialty: 'Prose',
    color: '#ec4899',
    icon: '✍️',
    type: 'specialist',
    group: 'specialists',
  }

  beforeEach(() => {
    localStorage.clear()
    useAgentStore.setState({
      agents: [],
      catalogAgents: [],
      teams: [
        {
          id: 'unsaved',
          name: 'Unsaved',
          saved: false,
          agentIds: [],
          agents: [],
          renames: {},
          purposes: {},
          backends: {},
          customSections: {},
          customOrder: [],
          favouriteIds: [],
          chiefOfStaffId: null,
          avatarThemeByAgent: {},
          avatarEyesByAgent: {},
          roleAssignments: {},
        },
      ],
      activeTeamId: 'unsaved',
      renames: {},
      purposes: {},
      backendByAgent: {},
      customSections: {},
      customOrder: [],
      favouriteIds: [],
      chiefOfStaffId: null,
      roleAssignments: {},
    })
    useAgentStore.getState().setAgents([...mockAgents])
  })

  it('saves the current roster as a named team and keeps Unsaved', () => {
    useAgentStore.getState().renameAgent('coder', 'Byte')
    const id = useAgentStore.getState().saveAsTeam('Research desk')
    expect(id).toBe('research-desk')
    const state = useAgentStore.getState()
    expect(state.activeTeamId).toBe('research-desk')
    expect(state.teams.some((t) => t.id === 'unsaved' && !t.saved)).toBe(true)
    expect(state.teams.find((t) => t.id === 'research-desk')?.name).toBe('Research desk')
    expect(state.agents.find((a) => a.agent_id === 'coder')?.customName).toBe('Byte')
  })

  it('repopulates overlays and membership when loading a team', () => {
    useAgentStore.getState().renameAgent('coder', 'Byte')
    useAgentStore.getState().saveAsTeam('Desk')
    useAgentStore.getState().renameAgent('coder', 'Nibble')
    expect(useAgentStore.getState().agents.find((a) => a.agent_id === 'coder')?.customName).toBe('Nibble')

    useAgentStore.getState().loadTeam('unsaved')
    expect(useAgentStore.getState().activeTeamId).toBe('unsaved')
    expect(useAgentStore.getState().agents.find((a) => a.agent_id === 'coder')?.customName).toBe('Byte')

    useAgentStore.getState().loadTeam('desk')
    expect(useAgentStore.getState().agents.find((a) => a.agent_id === 'coder')?.customName).toBe('Nibble')
  })

  it('named teams freeze membership; Unsaved tracks the live catalog', () => {
    useAgentStore.getState().saveAsTeam('Core')
    useAgentStore.getState().setAgents([...mockAgents, extra])
    expect(useAgentStore.getState().agents.map((a) => a.agent_id)).not.toContain('writer')

    useAgentStore.getState().loadTeam('unsaved')
    expect(useAgentStore.getState().agents.map((a) => a.agent_id)).toContain('writer')
  })

  it('assigns oversight roles to other agents', () => {
    useAgentStore.getState().setAgentRole('coder', 'socratic_skeptic', 'researcher')
    expect(useAgentStore.getState().roleAssignments.coder.socratic_skeptic).toBe('researcher')
    expect(JSON.parse(localStorage.getItem('agent_role_assignments') || '{}').coder.socratic_skeptic).toBe(
      'researcher',
    )
  })
})
