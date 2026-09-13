import { create } from 'zustand'
import type { 
  Agent, 
  AgentStatus, 
  SidebarDensity, 
  AvatarTheme,
  AvatarEyes,
  RoutingStrategy, 
  DelegationEvent 
} from '../types/agent'
import {
  setRoleAssignment,
  type OversightRole,
  type RoleAssignments,
} from './agent-roles'
import { assignUniqueLooks } from './agent-utils'
import {
  agentsForTeam,
  captureTeam,
  emptyUnsavedTeam,
  loadActiveTeamId,
  loadTeamsFromStorage,
  saveActiveTeamId,
  saveTeamsToStorage,
  uniqueTeamId,
  upsertTeam,
  type TeamSnapshot,
} from './agent-teams'
import {
  STARTER_SUPPORT_ID,
  STARTER_IDS,
  STARTER_LAYOUT,
  hideAllExceptStarters,
  mergeStarters,
} from './starter-agents'
import { cycleSessionMode as nextSessionMode, normalizeSessionMode, type SessionMode } from './session-modes'
import {
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEME_SET_EVENT,
  AVATAR_THEMES_ENABLED_EVENT,
  dispatchAvatarTheme,
  stripDisabledAvatarThemes,
} from './avatarTheme'

interface AgentStoreState {
  // Bots/Agents
  agents: Agent[]
  catalogAgents: Agent[]
  teams: TeamSnapshot[]
  activeTeamId: string
  selectedAgentId: string | null
  agentStatus: Record<string, AgentStatus>
  unreadCounts: Record<string, number>
  chiefOfStaffId: string | null
  renames: Record<string, string>
  purposes: Record<string, string>
  customSections: Record<string, string>
  customOrder: string[]
  favouriteIds: string[]
  hiddenAgentIds: string[]
  /** subjectAgentId -> role -> assigneeAgentId */
  roleAssignments: RoleAssignments

  // Sidebar
  sidebarOpen: boolean
  sidebarDensity: SidebarDensity
  collapsedSections: string[]
  avatarTheme: AvatarTheme
  avatarThemeByAgent: Record<string, AvatarTheme>
  avatarEyes: AvatarEyes
  avatarEyesByAgent: Record<string, AvatarEyes>

  // Search
  searchQuery: string

  // Routing
  routingStrategy: RoutingStrategy
  targetAgentId: string | null
  /** Per-agent backend: `api`, `remote`, or `cli:<name>`. */
  backendByAgent: Record<string, string>
  /** Global default LLM profile name (API provider). */
  defaultLlmProfile: string
  /** Per-agent LLM profile override; empty inherits defaultLlmProfile. */
  llmProfileByAgent: Record<string, string>
  /** Per-agent CLI model id; empty uses the CLI's default. */
  cliModelByAgent: Record<string, string>
  /** Per-agent remote child id (remote_id / target / model). */
  remoteMemberByAgent: Record<string, string>
  /** Per-agent remote framework overlay (hermes / openmausbot / dsh / …). */
  frameworkByAgent: Record<string, string>
  /** Per-agent coded blueprint id for API agents. */
  blueprintByAgent: Record<string, string>
  /** Per-agent empty-chat quickstart pills (label + prompt). */
  quickstartsByAgent: Record<string, { key: string; label: string; prompt: string }[]>
  /** Operator session mode: default | plan | auto-edit (Shift+Tab). */
  sessionMode: SessionMode

  // Delegations & Comms
  delegations: DelegationEvent[]
  selectedCommDelegation: DelegationEvent | null

  // Actions
  setAgents: (agents: Agent[]) => void
  selectAgent: (agentId: string) => void
  setAgentStatus: (agentId: string, status: AgentStatus) => void
  incrementUnread: (agentId: string) => void
  clearUnread: (agentId: string) => void
  setChiefOfStaff: (agentId: string | null) => void
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setSidebarDensity: (density: SidebarDensity) => void
  setAvatarTheme: (theme: AvatarTheme) => void
  setAgentAvatarTheme: (agentId: string, theme: AvatarTheme | null) => void
  setAvatarEyes: (eyes: AvatarEyes) => void
  setAgentAvatarEyes: (agentId: string, eyes: AvatarEyes | null) => void
  toggleSection: (section: string) => void
  setSearchQuery: (query: string) => void
  setRoutingStrategy: (strategy: RoutingStrategy) => void
  setTargetAgentId: (agentId: string | null) => void
  setAgentBackend: (agentId: string, backend: string) => void
  setDefaultLlmProfile: (profile: string) => void
  setAgentLlmProfile: (agentId: string, profile: string) => void
  setAgentCliModel: (agentId: string, model: string) => void
  setAgentRemoteMember: (agentId: string, remoteId: string) => void
  setAgentFramework: (agentId: string, framework: string) => void
  setAgentBlueprint: (agentId: string, blueprintId: string) => void
  setAgentQuickstarts: (
    agentId: string,
    items: { key: string; label: string; prompt: string }[],
  ) => void
  clearAgentQuickstarts: (agentId: string) => void
  setSessionMode: (mode: SessionMode) => void
  cycleSessionMode: () => void
  hideAgent: (agentId: string) => void
  unhideAgent: (agentId: string) => void
  hideAllAgents: () => void
  unhideAllAgents: () => void
  setDelegations: (events: DelegationEvent[]) => void
  addDelegation: (event: DelegationEvent) => void
  setSelectedCommDelegation: (event: DelegationEvent | null) => void
  renameAgent: (agentId: string, newName: string) => void
  setAgentPurpose: (agentId: string, purpose: string) => void
  moveAgentToSection: (agentId: string, section: string) => void
  reorderAgents: (sourceAgentId: string, targetAgentId: string) => void
  setCustomOrder: (order: string[]) => void
  pinFavourite: (agentId: string, beforeId?: string | null) => void
  unpinFavourite: (agentId: string) => void
  setAgentRole: (subjectId: string, role: OversightRole, assigneeId: string | null) => void
  shuffleLooks: () => void
  saveAsTeam: (name: string) => string | null
  loadTeam: (teamId: string) => void
}

function loadStored<T>(key: string, fallback: T): T {
  try {
    const item = localStorage.getItem(key)
    return item ? JSON.parse(item) : fallback
  } catch {
    return fallback
  }
}

function saveStored<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // best-effort persistence
  }
}

function loadAvatarThemeStored(fallback: AvatarTheme): AvatarTheme {
  try {
    const raw = localStorage.getItem(AVATAR_THEME_STORAGE_KEY)
    if (!raw) return fallback
    let parsed: any = raw
    try {
      parsed = JSON.parse(raw)
    } catch {
      /* plain string */
    }
    return (parsed as AvatarTheme) || fallback
  } catch {
    return fallback
  }
}

function saveAvatarThemeStored(theme: AvatarTheme): void {
  try {
    localStorage.setItem(AVATAR_THEME_STORAGE_KEY, theme)
  } catch {
    // best-effort persistence
  }
}

function persistOverlayKeys(state: {
  renames: Record<string, string>
  purposes: Record<string, string>
  backendByAgent: Record<string, string>
  customSections: Record<string, string>
  customOrder: string[]
  favouriteIds: string[]
  hiddenAgentIds: string[]
  chiefOfStaffId: string | null
  avatarThemeByAgent: Record<string, AvatarTheme>
  avatarEyesByAgent: Record<string, AvatarEyes>
  roleAssignments: RoleAssignments
  defaultLlmProfile: string
  llmProfileByAgent: Record<string, string>
  cliModelByAgent: Record<string, string>
  remoteMemberByAgent: Record<string, string>
  frameworkByAgent: Record<string, string>
  blueprintByAgent: Record<string, string>
  quickstartsByAgent: Record<string, { key: string; label: string; prompt: string }[]>
}): void {
  saveStored('agent_renames', state.renames)
  saveStored('agent_purposes', state.purposes)
  saveStored('agent_backends', state.backendByAgent)
  saveStored('agent_custom_sections', state.customSections)
  saveStored('agent_custom_order', state.customOrder)
  saveStored('agent_favourite_ids', state.favouriteIds)
  saveStored('agent_chief_of_staff', state.chiefOfStaffId)
  saveStored('agent_avatar_theme_by_agent', state.avatarThemeByAgent)
  saveStored('agent_avatar_eyes_by_agent', state.avatarEyesByAgent)
  saveStored('agent_role_assignments', state.roleAssignments)
  saveStored('agent_default_llm', state.defaultLlmProfile)
  saveStored('agent_llm_profiles', state.llmProfileByAgent)
  saveStored('agent_cli_models', state.cliModelByAgent)
  saveStored('agent_remote_members', state.remoteMemberByAgent)
  saveStored('agent_frameworks', state.frameworkByAgent)
  saveStored('agent_blueprints', state.blueprintByAgent)
  saveStored('agent_hidden_ids', state.hiddenAgentIds)
  saveStored('agent_quickstarts', state.quickstartsByAgent)
}

function decorateRoster(
  catalog: Agent[],
  state: {
    teams: TeamSnapshot[]
    activeTeamId: string
    renames: Record<string, string>
    purposes: Record<string, string>
    customSections: Record<string, string>
    customOrder: string[]
    chiefOfStaffId: string | null
    frameworkByAgent?: Record<string, string>
  },
): Agent[] {
  const team = state.teams.find((t) => t.id === state.activeTeamId)
  let updated = agentsForTeam(catalog, team).map((a) => ({
    ...a,
    customName: state.renames[a.agent_id] || a.name,
    customPurpose: state.purposes[a.agent_id] || undefined,
    group: state.customSections[a.agent_id] || a.group || 'specialists',
    chiefOfStaff: state.chiefOfStaffId === a.agent_id,
    framework: state.frameworkByAgent?.[a.agent_id] || a.framework,
  }))
  if (state.customOrder && state.customOrder.length > 0) {
    const orderMap = new Map(state.customOrder.map((id, index) => [id, index]))
    updated = [...updated].sort((a, b) => {
      const idxA = orderMap.has(a.agent_id) ? orderMap.get(a.agent_id)! : 9999
      const idxB = orderMap.has(b.agent_id) ? orderMap.get(b.agent_id)! : 9999
      return idxA - idxB
    })
  }
  return updated
}

function snapshotActive(state: AgentStoreState): TeamSnapshot {
  const current = state.teams.find((t) => t.id === state.activeTeamId) || emptyUnsavedTeam()
  return captureTeam({
    id: current.id,
    name: current.name,
    saved: current.saved,
    agents: state.agents,
    renames: state.renames,
    purposes: state.purposes,
    backendByAgent: state.backendByAgent,
    customSections: state.customSections,
    customOrder: state.customOrder,
    favouriteIds: state.favouriteIds,
    chiefOfStaffId: state.chiefOfStaffId,
    avatarThemeByAgent: state.avatarThemeByAgent,
    avatarEyesByAgent: state.avatarEyesByAgent,
    roleAssignments: state.roleAssignments,
    defaultLlmProfile: state.defaultLlmProfile,
    llmProfileByAgent: state.llmProfileByAgent,
    cliModelByAgent: state.cliModelByAgent,
    remoteMemberByAgent: state.remoteMemberByAgent,
    frameworkByAgent: state.frameworkByAgent,
  })
}

export const useAgentStore = create<AgentStoreState>((set) => ({
  agents: [],
  catalogAgents: [],
  teams: loadTeamsFromStorage(),
  activeTeamId: loadActiveTeamId(),
  selectedAgentId: 'router',
  agentStatus: {},
  unreadCounts: {},
  chiefOfStaffId: loadStored<string | null>('agent_chief_of_staff', null),
  renames: loadStored<Record<string, string>>('agent_renames', {}),
  purposes: loadStored<Record<string, string>>('agent_purposes', {}),
  customSections: loadStored<Record<string, string>>('agent_custom_sections', {}),
  customOrder: loadStored<string[]>('agent_custom_order', []),
  favouriteIds: loadStored<string[]>('agent_favourite_ids', []),
  hiddenAgentIds: loadStored<string[]>('agent_hidden_ids', []),
  roleAssignments: loadStored<RoleAssignments>('agent_role_assignments', {}),

  sidebarOpen: loadStored<boolean>('agent_sidebar_open', true),
  sidebarDensity: loadStored<SidebarDensity>('agent_sidebar_density', 'compact'),
  collapsedSections: loadStored<string[]>('agent_collapsed_sections', []),
  avatarTheme: loadAvatarThemeStored('chassis'),
  avatarThemeByAgent: loadStored<Record<string, AvatarTheme>>('agent_avatar_theme_by_agent', {}),
  avatarEyes: loadStored<AvatarEyes>('agent_avatar_eyes', 'lens'),
  avatarEyesByAgent: loadStored<Record<string, AvatarEyes>>('agent_avatar_eyes_by_agent', {}),

  searchQuery: '',
  routingStrategy: 'auto_route',
  targetAgentId: null,
  backendByAgent: loadStored<Record<string, string>>('agent_backends', {}),
  defaultLlmProfile: loadStored<string>('agent_default_llm', ''),
  llmProfileByAgent: loadStored<Record<string, string>>('agent_llm_profiles', {}),
  cliModelByAgent: loadStored<Record<string, string>>('agent_cli_models', {}),
  remoteMemberByAgent: loadStored<Record<string, string>>('agent_remote_members', {}),
  frameworkByAgent: loadStored<Record<string, string>>('agent_frameworks', {}),
  blueprintByAgent: loadStored<Record<string, string>>('agent_blueprints', {}),
  quickstartsByAgent: loadStored<Record<string, { key: string; label: string; prompt: string }[]>>(
    'agent_quickstarts',
    {},
  ),
  sessionMode: normalizeSessionMode(loadStored<string>('agent_session_mode', 'default')),

  delegations: [],
  selectedCommDelegation: null,

  setAgents: (agents) =>
    set((state) => {
      const merged = mergeStarters(agents)
      const updated = decorateRoster(merged, state)
      const looks = assignUniqueLooks(
        updated.map((a) => a.agent_id),
        state.avatarThemeByAgent,
        state.avatarEyesByAgent,
      )
      saveStored('agent_avatar_theme_by_agent', looks.themes)
      saveStored('agent_avatar_eyes_by_agent', looks.eyes)
      let hiddenAgentIds = state.hiddenAgentIds
      let favouriteIds = state.favouriteIds
      const selectedAgentId = state.selectedAgentId
      try {
        // Clean up legacy abandoned starter layout auto-hiding
        if (localStorage.getItem('agent_sidebar_starters')) {
          localStorage.removeItem('agent_sidebar_starters')
          const storedHidden = localStorage.getItem('agent_hidden_ids')
          if (storedHidden) {
            try {
              const parsed = JSON.parse(storedHidden)
              if (Array.isArray(parsed) && parsed.length > 50) {
                localStorage.removeItem('agent_hidden_ids')
                hiddenAgentIds = []
              }
            } catch {
              /* ignore */
            }
          }
          const storedFavs = localStorage.getItem('agent_favourite_ids')
          if (storedFavs) {
            try {
              const favs = JSON.parse(storedFavs)
              if (Array.isArray(favs) && favs.length === STARTER_IDS.length && favs.every((id: string) => (STARTER_IDS as readonly string[]).includes(id))) {
                localStorage.removeItem('agent_favourite_ids')
                favouriteIds = []
              }
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        /* storage unavailable */
      }
      return {
        catalogAgents: agents,
        agents: updated,
        avatarThemeByAgent: looks.themes,
        avatarEyesByAgent: looks.eyes,
        hiddenAgentIds,
        favouriteIds,
        selectedAgentId,
      }
    }),

  selectAgent: (agentId) =>
    set((state) => {
      const newUnread = { ...state.unreadCounts, [agentId]: 0 }
      return {
        selectedAgentId: agentId,
        unreadCounts: newUnread,
        targetAgentId: agentId === 'router' ? null : agentId
      }
    }),

  setAgentStatus: (agentId, status) =>
    set((state) => ({
      agentStatus: { ...state.agentStatus, [agentId]: status }
    })),

  incrementUnread: (agentId) =>
    set((state) => ({
      unreadCounts: {
        ...state.unreadCounts,
        [agentId]: (state.unreadCounts[agentId] || 0) + 1
      }
    })),

  clearUnread: (agentId) =>
    set((state) => ({
      unreadCounts: { ...state.unreadCounts, [agentId]: 0 }
    })),

  setChiefOfStaff: (agentId) =>
    set((state) => {
      saveStored('agent_chief_of_staff', agentId)
      const updatedAgents = state.agents.map((a) => ({
        ...a,
        chiefOfStaff: a.agent_id === agentId
      }))
      return { chiefOfStaffId: agentId, agents: updatedAgents }
    }),

  toggleSidebar: () =>
    set((state) => {
      const next = !state.sidebarOpen
      saveStored('agent_sidebar_open', next)
      return { sidebarOpen: next }
    }),

  setSidebarOpen: (open) => {
    saveStored('agent_sidebar_open', open)
    set({ sidebarOpen: open })
  },

  setSidebarDensity: (density) => {
    saveStored('agent_sidebar_density', density)
    set({ sidebarDensity: density })
  },

  setSessionMode: (mode) => {
    const next = normalizeSessionMode(mode)
    saveStored('agent_session_mode', next)
    set({ sessionMode: next })
  },

  cycleSessionMode: () => {
    set((state) => {
      const next = nextSessionMode(state.sessionMode)
      saveStored('agent_session_mode', next)
      return { sessionMode: next }
    })
  },

  setAvatarTheme: (theme) => {
    saveAvatarThemeStored(theme)
    dispatchAvatarTheme(theme as any)
    set({ avatarTheme: theme })
  },

  setAgentAvatarTheme: (agentId, theme) =>
    set((state) => {
      const next = { ...state.avatarThemeByAgent }
      if (!theme) delete next[agentId]
      else next[agentId] = theme
      saveStored('agent_avatar_theme_by_agent', next)
      return { avatarThemeByAgent: next }
    }),

  setAvatarEyes: (eyes) => {
    saveStored('agent_avatar_eyes', eyes)
    set({ avatarEyes: eyes })
  },

  setAgentAvatarEyes: (agentId, eyes) =>
    set((state) => {
      const next = { ...state.avatarEyesByAgent }
      if (!eyes) delete next[agentId]
      else next[agentId] = eyes
      saveStored('agent_avatar_eyes_by_agent', next)
      return { avatarEyesByAgent: next }
    }),

  toggleSection: (section) =>
    set((state) => {
      const exists = state.collapsedSections.includes(section)
      const next = exists
        ? state.collapsedSections.filter((s) => s !== section)
        : [...state.collapsedSections, section]
      saveStored('agent_collapsed_sections', next)
      return { collapsedSections: next }
    }),

  setSearchQuery: (query) => set({ searchQuery: query }),

  setRoutingStrategy: (strategy) => set({ routingStrategy: strategy }),

  setTargetAgentId: (agentId) => set({ targetAgentId: agentId }),

  setAgentBackend: (agentId, backend) =>
    set((state) => {
      const backendByAgent = { ...state.backendByAgent, [agentId]: backend }
      saveStored('agent_backends', backendByAgent)
      return { backendByAgent }
    }),

  setDefaultLlmProfile: (profile) => {
    saveStored('agent_default_llm', profile)
    set({ defaultLlmProfile: profile })
  },

  setAgentLlmProfile: (agentId, profile) =>
    set((state) => {
      const llmProfileByAgent = { ...state.llmProfileByAgent }
      if (!profile) delete llmProfileByAgent[agentId]
      else llmProfileByAgent[agentId] = profile
      saveStored('agent_llm_profiles', llmProfileByAgent)
      return { llmProfileByAgent }
    }),

  setAgentCliModel: (agentId, model) =>
    set((state) => {
      const cliModelByAgent = { ...state.cliModelByAgent }
      if (!model) delete cliModelByAgent[agentId]
      else cliModelByAgent[agentId] = model
      saveStored('agent_cli_models', cliModelByAgent)
      return { cliModelByAgent }
    }),

  setAgentRemoteMember: (agentId, remoteId) =>
    set((state) => {
      const remoteMemberByAgent = { ...state.remoteMemberByAgent }
      if (!remoteId) delete remoteMemberByAgent[agentId]
      else remoteMemberByAgent[agentId] = remoteId
      saveStored('agent_remote_members', remoteMemberByAgent)
      return { remoteMemberByAgent }
    }),

  setAgentFramework: (agentId, framework) =>
    set((state) => {
      const next = (framework || '').trim()
      const frameworkByAgent = { ...state.frameworkByAgent }
      if (!next) delete frameworkByAgent[agentId]
      else frameworkByAgent[agentId] = next
      const remoteMemberByAgent = { ...state.remoteMemberByAgent }
      delete remoteMemberByAgent[agentId]
      saveStored('agent_frameworks', frameworkByAgent)
      saveStored('agent_remote_members', remoteMemberByAgent)
      const agents = state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, framework: next || a.framework } : a,
      )
      return { frameworkByAgent, remoteMemberByAgent, agents }
    }),

  setAgentBlueprint: (agentId, blueprintId) =>
    set((state) => {
      const blueprintByAgent = { ...state.blueprintByAgent }
      if (!blueprintId) delete blueprintByAgent[agentId]
      else blueprintByAgent[agentId] = blueprintId
      saveStored('agent_blueprints', blueprintByAgent)
      return { blueprintByAgent }
    }),

  setAgentQuickstarts: (agentId, items) =>
    set((state) => {
      const quickstartsByAgent = { ...state.quickstartsByAgent, [agentId]: items }
      saveStored('agent_quickstarts', quickstartsByAgent)
      return { quickstartsByAgent }
    }),

  clearAgentQuickstarts: (agentId) =>
    set((state) => {
      const quickstartsByAgent = { ...state.quickstartsByAgent }
      delete quickstartsByAgent[agentId]
      saveStored('agent_quickstarts', quickstartsByAgent)
      return { quickstartsByAgent }
    }),

  hideAgent: (agentId) =>
    set((state) => {
      if (!agentId || state.hiddenAgentIds.includes(agentId)) return state
      const hiddenAgentIds = [...state.hiddenAgentIds, agentId]
      saveStored('agent_hidden_ids', hiddenAgentIds)
      return { hiddenAgentIds }
    }),

  unhideAgent: (agentId) =>
    set((state) => {
      const hiddenAgentIds = state.hiddenAgentIds.filter((id) => id !== agentId)
      saveStored('agent_hidden_ids', hiddenAgentIds)
      return { hiddenAgentIds }
    }),

  hideAllAgents: () =>
    set((state) => {
      const hiddenAgentIds = hideAllExceptStarters(state.agents.map((a) => a.agent_id))
      const favouriteIds = state.favouriteIds.filter((id) => !hiddenAgentIds.includes(id))
      saveStored('agent_hidden_ids', hiddenAgentIds)
      saveStored('agent_favourite_ids', favouriteIds)
      const selectedHidden = state.selectedAgentId
        ? hiddenAgentIds.includes(state.selectedAgentId)
        : true
      return {
        hiddenAgentIds,
        favouriteIds,
        selectedAgentId: selectedHidden ? STARTER_SUPPORT_ID : state.selectedAgentId,
      }
    }),

  unhideAllAgents: () =>
    set(() => {
      saveStored('agent_hidden_ids', [])
      return { hiddenAgentIds: [] }
    }),

  setDelegations: (events) => set({ delegations: events }),

  addDelegation: (event) =>
    set((state) => ({
      delegations: [event, ...state.delegations]
    })),

  setSelectedCommDelegation: (event) => set({ selectedCommDelegation: event }),

  renameAgent: (agentId, newName) =>
    set((state) => {
      const renames = { ...state.renames, [agentId]: newName }
      saveStored('agent_renames', renames)
      const updated = state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, customName: newName } : a
      )
      return { renames, agents: updated }
    }),

  setAgentPurpose: (agentId, purpose) =>
    set((state) => {
      const trimmed = purpose.trim()
      const purposes = { ...state.purposes }
      if (trimmed) purposes[agentId] = trimmed
      else delete purposes[agentId]
      saveStored('agent_purposes', purposes)
      const updated = state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, customPurpose: trimmed || undefined } : a
      )
      return { purposes, agents: updated }
    }),

  moveAgentToSection: (agentId, section) =>
    set((state) => {
      const customSections = { ...state.customSections, [agentId]: section }
      saveStored('agent_custom_sections', customSections)
      const updated = state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, group: section } : a
      )
      return { customSections, agents: updated }
    }),

  reorderAgents: (sourceAgentId, targetAgentId) =>
    set((state) => {
      if (sourceAgentId === targetAgentId) return state

      const currentAgents = [...state.agents]
      const sourceIdx = currentAgents.findIndex((a) => a.agent_id === sourceAgentId)
      const targetIdx = currentAgents.findIndex((a) => a.agent_id === targetAgentId)
      if (sourceIdx === -1 || targetIdx === -1) return state

      const [movedAgent] = currentAgents.splice(sourceIdx, 1)

      // If moving into another section/group, inherit target section
      const targetAgent = state.agents[targetIdx]
      let updatedSections = state.customSections
      if (targetAgent && targetAgent.group && movedAgent.group !== targetAgent.group) {
        movedAgent.group = targetAgent.group
        updatedSections = { ...state.customSections, [movedAgent.agent_id]: targetAgent.group }
        saveStored('agent_custom_sections', updatedSections)
      }

      // Re-find target index in currentAgents (since length changed)
      const newTargetIdx = currentAgents.findIndex((a) => a.agent_id === targetAgentId)
      currentAgents.splice(newTargetIdx >= 0 ? newTargetIdx : targetIdx, 0, movedAgent)

      const newOrder = currentAgents.map((a) => a.agent_id)
      saveStored('agent_custom_order', newOrder)

      return {
        agents: currentAgents,
        customOrder: newOrder,
        customSections: updatedSections
      }
    }),

  setCustomOrder: (order) =>
    set((state) => {
      saveStored('agent_custom_order', order)
      const orderMap = new Map(order.map((id, index) => [id, index]))
      const sorted = [...state.agents].sort((a, b) => {
        const idxA = orderMap.has(a.agent_id) ? orderMap.get(a.agent_id)! : 9999
        const idxB = orderMap.has(b.agent_id) ? orderMap.get(b.agent_id)! : 9999
        return idxA - idxB
      })
      return { customOrder: order, agents: sorted }
    }),

  pinFavourite: (agentId, beforeId) =>
    set((state) => {
      const next = state.favouriteIds.filter((id) => id !== agentId)
      if (beforeId) {
        const idx = next.indexOf(beforeId)
        if (idx >= 0) next.splice(idx, 0, agentId)
        else next.push(agentId)
      } else {
        next.push(agentId)
      }
      saveStored('agent_favourite_ids', next)
      return { favouriteIds: next }
    }),

  unpinFavourite: (agentId) =>
    set((state) => {
      const next = state.favouriteIds.filter((id) => id !== agentId)
      saveStored('agent_favourite_ids', next)
      return { favouriteIds: next }
    }),

  setAgentRole: (subjectId, role, assigneeId) =>
    set((state) => {
      const roleAssignments = setRoleAssignment(state.roleAssignments, subjectId, role, assigneeId)
      saveStored('agent_role_assignments', roleAssignments)
      return { roleAssignments }
    }),

  shuffleLooks: () =>
    set((state) => {
      const looks = assignUniqueLooks(
        state.agents.map((a) => a.agent_id),
        state.avatarThemeByAgent,
        state.avatarEyesByAgent,
        { reassignAll: true },
      )
      saveStored('agent_avatar_theme_by_agent', looks.themes)
      saveStored('agent_avatar_eyes_by_agent', looks.eyes)
      return {
        avatarThemeByAgent: looks.themes,
        avatarEyesByAgent: looks.eyes,
      }
    }),

  saveAsTeam: (name) => {
    const trimmed = name.trim()
    if (!trimmed) return null
    let createdId: string | null = null
    set((state) => {
      const current = snapshotActive(state)
      const withCurrent = upsertTeam(state.teams, current)
      const id = uniqueTeamId(trimmed, withCurrent)
      createdId = id
      const named: TeamSnapshot = { ...current, id, name: trimmed, saved: true }
      const teams = upsertTeam(withCurrent, named)
      saveTeamsToStorage(teams)
      saveActiveTeamId(id)
      return { teams, activeTeamId: id }
    })
    return createdId
  },

  loadTeam: (teamId) =>
    set((state) => {
      if (!teamId || teamId === state.activeTeamId) return state
      const leaving = snapshotActive(state)
      const withLeaving = upsertTeam(state.teams, leaving)
      const target = withLeaving.find((t) => t.id === teamId)
      if (!target) return state
      saveTeamsToStorage(withLeaving)
      saveActiveTeamId(teamId)
      const next = {
        ...state,
        teams: withLeaving,
        activeTeamId: teamId,
        renames: { ...target.renames },
        purposes: { ...target.purposes },
        backendByAgent: { ...target.backends },
        customSections: { ...target.customSections },
        customOrder: [...target.customOrder],
        favouriteIds: [...target.favouriteIds],
        chiefOfStaffId: target.chiefOfStaffId,
        avatarThemeByAgent: { ...target.avatarThemeByAgent },
        avatarEyesByAgent: { ...target.avatarEyesByAgent },
        roleAssignments: { ...(target.roleAssignments || {}) },
        defaultLlmProfile: target.defaultLlmProfile || '',
        llmProfileByAgent: { ...(target.llmProfileByAgent || {}) },
        cliModelByAgent: { ...(target.cliModelByAgent || {}) },
        remoteMemberByAgent: { ...(target.remoteMemberByAgent || {}) },
        frameworkByAgent: { ...(target.frameworkByAgent || {}) },
      }
      persistOverlayKeys(next)
      const catalog = state.catalogAgents.length ? state.catalogAgents : target.agents
      const updated = decorateRoster(catalog, next)
      const looks = assignUniqueLooks(
        updated.map((a) => a.agent_id),
        next.avatarThemeByAgent,
        next.avatarEyesByAgent,
      )
      saveStored('agent_avatar_theme_by_agent', looks.themes)
      saveStored('agent_avatar_eyes_by_agent', looks.eyes)
      return {
        ...next,
        catalogAgents: catalog,
        agents: updated,
        avatarThemeByAgent: looks.themes,
        avatarEyesByAgent: looks.eyes,
      }
    }),
}))

let persistingTeam = false
useAgentStore.subscribe((state, prev) => {
  if (persistingTeam) return
  if (
    state.agents === prev.agents &&
    state.renames === prev.renames &&
    state.purposes === prev.purposes &&
    state.backendByAgent === prev.backendByAgent &&
    state.customSections === prev.customSections &&
    state.customOrder === prev.customOrder &&
    state.favouriteIds === prev.favouriteIds &&
    state.chiefOfStaffId === prev.chiefOfStaffId &&
    state.avatarThemeByAgent === prev.avatarThemeByAgent &&
    state.avatarEyesByAgent === prev.avatarEyesByAgent &&
    state.roleAssignments === prev.roleAssignments &&
    state.defaultLlmProfile === prev.defaultLlmProfile &&
    state.llmProfileByAgent === prev.llmProfileByAgent &&
    state.cliModelByAgent === prev.cliModelByAgent &&
    state.remoteMemberByAgent === prev.remoteMemberByAgent &&
    state.frameworkByAgent === prev.frameworkByAgent &&
    state.activeTeamId === prev.activeTeamId
  ) {
    return
  }
  const snap = snapshotActive(state)
  const teams = upsertTeam(state.teams, snap)
  if (JSON.stringify(teams) === JSON.stringify(state.teams)) return
  persistingTeam = true
  try {
    saveTeamsToStorage(teams)
    useAgentStore.setState({ teams })
  } finally {
    persistingTeam = false
  }
})

if (typeof window !== 'undefined') {
  const onAvatarThemeSet = (event: Event) => {
    const detail = (event as CustomEvent<AvatarTheme>).detail
    if (detail && detail !== useAgentStore.getState().avatarTheme) {
      useAgentStore.setState({ avatarTheme: detail })
    }
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key === AVATAR_THEME_STORAGE_KEY && event.newValue) {
      try {
        const val = JSON.parse(event.newValue)
        if (val) useAgentStore.setState({ avatarTheme: val })
      } catch {
        useAgentStore.setState({ avatarTheme: event.newValue as AvatarTheme })
      }
    }
  }
  /** REQ-841: rewrite per-agent packs that are no longer installed. */
  const onEnabledThemesSet = (event: Event) => {
    const detail = (event as CustomEvent<AvatarTheme[]>).detail
    if (!Array.isArray(detail) || detail.length === 0) return
    const byAgent = useAgentStore.getState().avatarThemeByAgent
    const next = stripDisabledAvatarThemes(byAgent, detail)
    if (next === byAgent) return
    saveStored('agent_avatar_theme_by_agent', next)
    useAgentStore.setState({ avatarThemeByAgent: next })
  }
  window.addEventListener(AVATAR_THEME_SET_EVENT, onAvatarThemeSet)
  window.addEventListener(AVATAR_THEMES_ENABLED_EVENT, onEnabledThemesSet)
  window.addEventListener('storage', onStorage)
}

