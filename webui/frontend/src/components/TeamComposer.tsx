import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GripVertical, Plus, Tags, Users, Wrench } from 'lucide-react'
import { Alert, Badge, Button, Input, Modal, Tabs, Textarea } from './DaisyUI'
import InstallCatalog from './InstallCatalog'
import {
  createTeamRoster,
  fetchMcpPlugins,
  fetchTeamAgents,
  fetchTeamRosters,
  updateTeamRoster,
  type TeamAgent,
  type TeamRosterRecord,
} from '../lib/api'
import {
  MCP_SERVER_TEMPLATES,
  newMcpServerId,
  serversFromApi,
} from '../lib/mcpServers'
import {
  addMember,
  addToolSlot,
  agentDisplayName,
  applySlotMemberChange,
  assignableMembersForSlot,
  assignRoleSlot,
  BUILTIN_TEAM_TOOLS,
  canAddRoleSlot,
  COMPOSABLE_TEAM_ROLES,
  COS_EMPTY_ROSTER_HINT,
  COS_INSTRUCTIONS_HELPER,
  dataTransferHasType,
  DEFAULT_COS_STARTER,
  deriveWiresFromTools,
  DRAG_MIME,
  eligibleCosMembers,
  emptyRosterDraft,
  encodeDragAgent,
  encodeDragRole,
  encodeDragTool,
  FIRST_AGENT_VALUE,
  firstAgentLeadId,
  isCosEligibleMember,
  memberByKey,
  memberKey,
  newRoleSlot,
  NO_COS_VALUE,
  parseDragAgent,
  parseDragRole,
  parseDragRosterIndex,
  parseDragTool,
  parseRosterMember,
  parseTeamTools,
  PLACEHOLDER_TEAM_AGENTS,
  pruneToolSlots,
  removeMember,
  removeRoleSlot,
  removeToolSlot,
  reorderMembers,
  restoreCosId,
  ROLE_DRAG_MIME,
  ROSTER_DRAG_MIME,
  rosterHasMember,
  serializeToolSlots,
  setMemberRole,
  slotsFromMembers,
  slotsFromTools,
  stampCosRole,
  TOOL_DRAG_MIME,
  unassignSlotsForMember,
  updateToolSlot,
  type AddableTeamTool,
  type ComposableTeamRole,
  type RoleSlot,
  type TeamRosterMember,
  type ToolSlot,
} from '../lib/teamRoster'

export const OPEN_TEAM_COMPOSER_EVENT = 'swarm:open-team-composer'

interface ContextMenuState {
  mode: 'add' | 'remove'
  agent: TeamAgent
  x: number
  y: number
}

export interface TeamComposerProps {
  isOpen: boolean
  onClose: () => void
}

const AVAILABLE_AGENT_KINDS = ['api', 'cli', 'remote'] as const
type AvailableAgentKind = (typeof AVAILABLE_AGENT_KINDS)[number]

const AVAILABLE_AGENT_KIND_LABEL: Record<AvailableAgentKind, string> = {
  api: 'API',
  cli: 'CLI',
  remote: 'Remote',
}

function defaultAvailableAgentKind(
  byKind: Record<AvailableAgentKind, readonly TeamAgent[]>,
): AvailableAgentKind {
  if (byKind.api.length > 0) return 'api'
  const firstNonEmpty = AVAILABLE_AGENT_KINDS.find((kind) => byKind[kind].length > 0)
  return firstNonEmpty ?? 'api'
}

export default function TeamComposer({ isOpen, onClose }: TeamComposerProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [members, setMembers] = useState<TeamRosterMember[]>([])
  const [chiefOfStaffId, setChiefOfStaffId] = useState<string | null>(null)
  const [leadFollowsFirst, setLeadFollowsFirst] = useState(true)
  const [cosInstructions, setCosInstructions] = useState(DEFAULT_COS_STARTER)
  const [savedId, setSavedId] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [roleDragOver, setRoleDragOver] = useState(false)
  const [toolDragOver, setToolDragOver] = useState(false)
  const [roleSlots, setRoleSlots] = useState<RoleSlot[]>([])
  const [toolSlots, setToolSlots] = useState<ToolSlot[]>([])
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [agentKindTab, setAgentKindTab] = useState<AvailableAgentKind>('api')
  const [agentKindTabTouched, setAgentKindTabTouched] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const cosChoices = useMemo(() => eligibleCosMembers(members), [members])
  const rolesUnlocked = members.length > 0
  const toolsUnlocked = members.length > 0

  const agentsQuery = useQuery({
    queryKey: ['team-agents'],
    queryFn: fetchTeamAgents,
    enabled: isOpen,
    retry: 1,
  })
  const rostersQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
    enabled: isOpen,
    retry: 1,
  })
  const mcpQuery = useQuery({
    queryKey: ['mcp-plugins'],
    queryFn: fetchMcpPlugins,
    enabled: isOpen,
    retry: 1,
  })

  const availableAgents = useMemo(() => {
    const data = agentsQuery.data?.data
    if (data && data.length > 0) return data
    if (agentsQuery.isError || (agentsQuery.isSuccess && (!data || data.length === 0))) {
      return PLACEHOLDER_TEAM_AGENTS
    }
    return data ?? []
  }, [agentsQuery.data, agentsQuery.isError, agentsQuery.isSuccess])

  const agentsByKind = useMemo(() => {
    return {
      api: availableAgents.filter((agent) => agent.kind === 'api'),
      cli: availableAgents.filter((agent) => agent.kind === 'cli'),
      remote: availableAgents.filter((agent) => agent.kind === 'remote'),
    }
  }, [availableAgents])

  const activeAgentKind = agentKindTabTouched
    ? agentKindTab
    : defaultAvailableAgentKind(agentsByKind)

  const mcpChoices = useMemo(() => {
    const configured = serversFromApi(mcpQuery.data).map((entry) => ({
      name: entry.id || newMcpServerId(entry.name),
      label: entry.name || entry.id,
    }))
    const seen = new Set(configured.map((entry) => entry.name.toLowerCase()))
    const catalog = MCP_SERVER_TEMPLATES.map((entry) => ({
      name: newMcpServerId(entry.name),
      label: entry.name,
    })).filter((entry) => {
      const key = entry.name.toLowerCase()
      const label = entry.label.toLowerCase()
      if (seen.has(key) || seen.has(label)) return false
      seen.add(key)
      return true
    })
    return [...configured, ...catalog]
  }, [mcpQuery.data])

  const resetDraft = useCallback(() => {
    const draft = emptyRosterDraft()
    setName(draft.name)
    setMembers(draft.members)
    setChiefOfStaffId(draft.chiefOfStaffId)
    setLeadFollowsFirst(true)
    setCosInstructions(draft.chiefOfStaffInstructions)
    setRoleSlots([])
    setToolSlots([])
    setSavedId(null)
    setStatus(null)
    setAgentKindTab('api')
    setAgentKindTabTouched(false)
  }, [])

  useEffect(() => {
    if (isOpen) resetDraft()
  }, [isOpen, resetDraft])

  const closeMenu = useCallback(() => setMenu(null), [])

  useEffect(() => {
    if (!menu) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu()
    }
    const onPointer = (event: Event) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        closeMenu()
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer)
    }
  }, [menu, closeMenu])

  const applyChiefOfStaff = useCallback((nextId: string | null, followsFirst = false) => {
    setLeadFollowsFirst(followsFirst)
    setChiefOfStaffId(nextId)
    setMembers((prev) => {
      const stamped = stampCosRole(prev, nextId)
      const holder = nextId ? stamped.find((row) => row.id === nextId) : undefined
      const nextKey = holder ? memberKey(holder) : null
      setRoleSlots((slots) =>
        slots.map((slot) => {
          if (slot.role === 'chief_of_staff') return { ...slot, memberKey: nextKey }
          if (nextKey && slot.memberKey === nextKey) return { ...slot, memberKey: null }
          return slot
        }),
      )
      return stamped
    })
    setCosInstructions((prev) => (prev.trim() ? prev : DEFAULT_COS_STARTER))
    setStatus(null)
  }, [])

  const addFromAgent = useCallback((agent: TeamAgent) => {
    setMembers((prev) => {
      const next = addMember(prev, agent)
      if (!leadFollowsFirst) return next
      const lead = firstAgentLeadId(next)
      setChiefOfStaffId(lead)
      const stamped = stampCosRole(next, lead)
      const holder = lead ? stamped.find((row) => row.id === lead) : undefined
      const nextKey = holder ? memberKey(holder) : null
      setRoleSlots((slots) =>
        slots.map((slot) => {
          if (slot.role === 'chief_of_staff') return { ...slot, memberKey: nextKey }
          if (nextKey && slot.memberKey === nextKey) return { ...slot, memberKey: null }
          return slot
        }),
      )
      return stamped
    })
    setStatus(null)
    closeMenu()
  }, [closeMenu, leadFollowsFirst])

  const addFromRole = useCallback(
    (role: ComposableTeamRole) => {
      if (members.length === 0) return
      setRoleSlots((prev) => {
        if (!canAddRoleSlot(prev, role)) return prev
        let assigned: string | null = null
        if (role === 'chief_of_staff' && chiefOfStaffId) {
          const holder = members.find((row) => row.id === chiefOfStaffId)
          if (holder) assigned = memberKey(holder)
        }
        return [...prev, newRoleSlot(role, assigned)]
      })
      closeMenu()
    },
    [members, chiefOfStaffId, closeMenu],
  )

  const addFromTool = useCallback(
    (addable: AddableTeamTool) => {
      if (members.length === 0) return
      setToolSlots((prev) => addToolSlot(prev, addable))
    },
    [members.length],
  )

  const removeFromAgent = useCallback((agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>) => {
    setMembers((prev) => {
      const next = removeMember(prev, agent)
      if (next.length === 0) {
        setChiefOfStaffId(null)
        setLeadFollowsFirst(true)
        setRoleSlots([])
        setToolSlots([])
        return next
      }
      const lostLead = Boolean(chiefOfStaffId && agent.id === chiefOfStaffId)
      const followsFirst = leadFollowsFirst || lostLead
      if (followsFirst) {
        setLeadFollowsFirst(true)
        const lead = firstAgentLeadId(next)
        setChiefOfStaffId(lead)
        const stamped = stampCosRole(next, lead)
        const holder = lead ? stamped.find((row) => row.id === lead) : undefined
        const nextKey = holder ? memberKey(holder) : null
        setRoleSlots((slots) =>
          unassignSlotsForMember(slots, agent).map((slot) => {
            if (slot.role === 'chief_of_staff') return { ...slot, memberKey: nextKey }
            if (nextKey && slot.memberKey === nextKey) return { ...slot, memberKey: null }
            return slot
          }),
        )
        setToolSlots((slots) => pruneToolSlots(slots, stamped))
        return stamped
      }
      setRoleSlots((slots) => unassignSlotsForMember(slots, agent))
      setToolSlots((slots) => pruneToolSlots(slots, next))
      return next
    })
    closeMenu()
  }, [chiefOfStaffId, closeMenu, leadFollowsFirst])

  const removeSlot = useCallback(
    (slot: RoleSlot) => {
      if (slot.role === 'chief_of_staff') {
        if (slot.memberKey) applyChiefOfStaff(null, false)
      } else if (slot.memberKey) {
        const prev = memberByKey(members, slot.memberKey)
        if (prev) setMembers((current) => setMemberRole(current, prev, 'default'))
      }
      setRoleSlots((slots) => removeRoleSlot(slots, slot.id))
    },
    [applyChiefOfStaff, members],
  )

  const onAssignSlot = useCallback(
    (slot: RoleSlot, nextKey: string) => {
      const nextMember = memberByKey(members, nextKey) ?? null
      if (slot.role === 'chief_of_staff') {
        if (nextMember && !isCosEligibleMember(nextMember)) return
        applyChiefOfStaff(nextMember?.id ?? null, false)
        return
      }
      setMembers((prev) => applySlotMemberChange(prev, slot, nextMember))
      if (nextMember && chiefOfStaffId === nextMember.id) {
        applyChiefOfStaff(null, false)
      }
      setRoleSlots((slots) =>
        assignRoleSlot(slots, slot.id, nextMember ? memberKey(nextMember) : null),
      )
    },
    [applyChiefOfStaff, chiefOfStaffId, members],
  )

  const clearForeignDrag = (event: React.DragEvent<HTMLElement>) => {
    try {
      event.dataTransfer.clearData('text/uri-list')
      event.dataTransfer.clearData('URL')
      event.dataTransfer.clearData('text/html')
    } catch {
      /* ignore */
    }
  }

  const onDragStart = (event: React.DragEvent<HTMLElement>, agent: TeamAgent) => {
    clearForeignDrag(event)
    event.dataTransfer.setData(DRAG_MIME, encodeDragAgent(agent))
    event.dataTransfer.setData('text/plain', encodeDragAgent(agent))
    event.dataTransfer.effectAllowed = 'copy'
    clearForeignDrag(event)
  }

  const onRoleDragStart = (event: React.DragEvent<HTMLElement>, role: ComposableTeamRole) => {
    if (members.length === 0) {
      event.preventDefault()
      return
    }
    clearForeignDrag(event)
    event.dataTransfer.setData(ROLE_DRAG_MIME, encodeDragRole(role))
    event.dataTransfer.setData('text/plain', encodeDragRole(role))
    event.dataTransfer.effectAllowed = 'copy'
    clearForeignDrag(event)
  }

  const onToolDragStart = (event: React.DragEvent<HTMLElement>, addable: AddableTeamTool) => {
    if (members.length === 0) {
      event.preventDefault()
      return
    }
    clearForeignDrag(event)
    event.dataTransfer.setData(TOOL_DRAG_MIME, encodeDragTool(addable))
    event.dataTransfer.setData('text/plain', encodeDragTool(addable))
    event.dataTransfer.effectAllowed = 'copy'
    clearForeignDrag(event)
  }

  const onDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    if (dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)) {
      event.dataTransfer.dropEffect = 'none'
      setDragOver(false)
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, TOOL_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)
    ) {
      event.dataTransfer.dropEffect = 'none'
      setDragOver(false)
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, ROSTER_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)
    ) {
      event.dataTransfer.dropEffect = 'none'
      setDragOver(false)
      return
    }
    event.dataTransfer.dropEffect = 'copy'
    setDragOver(true)
  }

  const onDragLeave = (event: React.DragEvent<HTMLElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node)) return
    setDragOver(false)
  }

  const onDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    setDragOver(false)
    if (
      dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)
    ) {
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, TOOL_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)
    ) {
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, ROSTER_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)
    ) {
      return
    }
    const raw = event.dataTransfer.getData(DRAG_MIME) || event.dataTransfer.getData('text/plain')
    if (parseDragRole(raw) && !parseDragAgent(raw)) return
    if (parseDragTool(raw) && !parseDragAgent(raw)) return
    if (parseDragRosterIndex(raw) !== null && !parseDragAgent(raw)) return
    const agent = parseDragAgent(raw)
    if (agent) addFromAgent(agent)
  }

  const onRosterDragStart = (event: React.DragEvent<HTMLElement>, index: number) => {
    event.stopPropagation()
    clearForeignDrag(event)
    event.dataTransfer.setData(ROSTER_DRAG_MIME, String(index))
    event.dataTransfer.setData('text/plain', String(index))
    event.dataTransfer.effectAllowed = 'move'
    clearForeignDrag(event)
  }

  const onRosterDragOver = (event: React.DragEvent<HTMLElement>) => {
    if (!dataTransferHasType(event.dataTransfer, ROSTER_DRAG_MIME)) return
    event.preventDefault()
    event.stopPropagation()
    event.dataTransfer.dropEffect = 'move'
  }

  const onRosterDrop = (event: React.DragEvent<HTMLElement>, toIndex: number) => {
    const raw =
      event.dataTransfer.getData(ROSTER_DRAG_MIME) || event.dataTransfer.getData('text/plain')
    const fromIndex = parseDragRosterIndex(raw)
    if (fromIndex === null) return
    event.preventDefault()
    event.stopPropagation()
    setDragOver(false)
    const next = reorderMembers(members, fromIndex, toIndex)
    if (next === members) return
    setMembers(next)
    if (leadFollowsFirst) applyChiefOfStaff(firstAgentLeadId(next), true)
  }

  const onRoleDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    if (!rolesUnlocked) {
      event.dataTransfer.dropEffect = 'none'
      setRoleDragOver(false)
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME)
    ) {
      event.dataTransfer.dropEffect = 'none'
      setRoleDragOver(false)
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, TOOL_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME)
    ) {
      event.dataTransfer.dropEffect = 'none'
      setRoleDragOver(false)
      return
    }
    event.dataTransfer.dropEffect = 'copy'
    setRoleDragOver(true)
  }

  const onRoleDragLeave = (event: React.DragEvent<HTMLElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node)) return
    setRoleDragOver(false)
  }

  const onRoleDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    setRoleDragOver(false)
    if (!rolesUnlocked) return
    if (
      dataTransferHasType(event.dataTransfer, DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME)
    ) {
      return
    }
    if (
      dataTransferHasType(event.dataTransfer, TOOL_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME)
    ) {
      return
    }
    const raw =
      event.dataTransfer.getData(ROLE_DRAG_MIME) || event.dataTransfer.getData('text/plain')
    if (parseDragAgent(raw) && !parseDragRole(raw)) return
    if (parseDragTool(raw) && !parseDragRole(raw)) return
    const role = parseDragRole(raw)
    if (role) addFromRole(role)
  }

  const onToolDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    if (!toolsUnlocked) {
      event.dataTransfer.dropEffect = 'none'
      setToolDragOver(false)
      return
    }
    if (
      (dataTransferHasType(event.dataTransfer, DRAG_MIME) ||
        dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME) ||
        dataTransferHasType(event.dataTransfer, ROSTER_DRAG_MIME)) &&
      !dataTransferHasType(event.dataTransfer, TOOL_DRAG_MIME)
    ) {
      event.dataTransfer.dropEffect = 'none'
      setToolDragOver(false)
      return
    }
    event.dataTransfer.dropEffect = 'copy'
    setToolDragOver(true)
  }

  const onToolDragLeave = (event: React.DragEvent<HTMLElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node)) return
    setToolDragOver(false)
  }

  const onToolDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    setToolDragOver(false)
    if (!toolsUnlocked) return
    if (
      (dataTransferHasType(event.dataTransfer, DRAG_MIME) ||
        dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME) ||
        dataTransferHasType(event.dataTransfer, ROSTER_DRAG_MIME)) &&
      !dataTransferHasType(event.dataTransfer, TOOL_DRAG_MIME)
    ) {
      return
    }
    const raw =
      event.dataTransfer.getData(TOOL_DRAG_MIME) || event.dataTransfer.getData('text/plain')
    if (parseDragAgent(raw) && !parseDragTool(raw)) return
    if (parseDragRole(raw) && !parseDragTool(raw)) return
    const addable = parseDragTool(raw)
    if (addable) addFromTool(addable)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const trimmed = name.trim()
      if (!trimmed) {
        throw new Error('Team name is required.')
      }
      const stamped = stampCosRole(members, chiefOfStaffId)
      const tools = serializeToolSlots(toolSlots)
      const payload = {
        name: trimmed,
        members: stamped,
        tools,
        wires: deriveWiresFromTools(tools),
        chief_of_staff_id: chiefOfStaffId,
        chief_of_staff_instructions: chiefOfStaffId ? cosInstructions : '',
      }
      if (savedId) {
        return updateTeamRoster(savedId, payload)
      }
      return createTeamRoster(payload)
    },
    onSuccess: (roster: TeamRosterRecord) => {
      const nextMembers = (roster.members || [])
        .map(parseRosterMember)
        .filter((row): row is TeamRosterMember => row !== null)
      const nextCos = restoreCosId({
        members: nextMembers,
        chief_of_staff_id: roster.chief_of_staff_id,
      })
      setSavedId(roster.id)
      setName(roster.name)
      setMembers(stampCosRole(nextMembers, nextCos))
      setChiefOfStaffId(nextCos)
      setLeadFollowsFirst(!nextCos || nextCos === firstAgentLeadId(nextMembers))
      setCosInstructions(
        nextCos ? roster.chief_of_staff_instructions || DEFAULT_COS_STARTER : DEFAULT_COS_STARTER,
      )
      setRoleSlots(slotsFromMembers(stampCosRole(nextMembers, nextCos)))
      setToolSlots(slotsFromTools(parseTeamTools(roster.tools)))
      queryClient.invalidateQueries({ queryKey: ['team-rosters'] })
      setStatus(`Saved roster “${roster.name}” to team_rosters.json.`)
    },
  })

  const loadRoster = (roster: TeamRosterRecord) => {
    setSavedId(roster.id)
    setName(roster.name)
    const nextMembers = (roster.members || [])
      .map(parseRosterMember)
      .filter((row): row is TeamRosterMember => row !== null)
    const nextCos = restoreCosId({
      members: nextMembers,
      chief_of_staff_id: roster.chief_of_staff_id,
    })
    setMembers(stampCosRole(nextMembers, nextCos))
    setChiefOfStaffId(nextCos)
    setLeadFollowsFirst(!nextCos || nextCos === firstAgentLeadId(nextMembers))
    setCosInstructions(
      nextCos ? roster.chief_of_staff_instructions || DEFAULT_COS_STARTER : DEFAULT_COS_STARTER,
    )
    setRoleSlots(slotsFromMembers(stampCosRole(nextMembers, nextCos)))
    setToolSlots(slotsFromTools(parseTeamTools(roster.tools)))
    setStatus(null)
  }

  const savedRosters = Array.isArray(rostersQuery.data)
    ? rostersQuery.data
    : rostersQuery.data?.data ?? []

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New team"
      size="2xl"
      className="max-h-[90vh] overflow-y-auto"
    >
      <div className="space-y-4">
        <p className="text-sm text-base-content/60">
          Compose a roster of API, CLI, and remote members. Django{' '}
          <a className="link" href="/teams/">
            /teams/
          </a>{' '}
          still edits LLM-profile aliases in teams.json — this overlay writes{' '}
          <code className="text-xs">team_rosters.json</code>.
        </p>

        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <Input
            label="Team name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="research-squad"
            size="sm"
          />
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={resetDraft}>
              New
            </Button>
            <Button
              type="button"
              size="sm"
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              Save roster
            </Button>
          </div>
        </div>

        {savedRosters.length > 0 && (
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Saved rosters</span>
            <select
              className="select select-sm"
              value={savedId ?? ''}
              onChange={(event) => {
                const next = savedRosters.find((row) => row.id === event.target.value)
                if (next) loadRoster(next)
                else resetDraft()
              }}
              aria-label="Saved rosters"
            >
              <option value="">New team</option>
              {savedRosters.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <fieldset
          className="rounded-lg border border-base-300 bg-base-200/40 px-3 py-2"
          data-testid="team-cos-fieldset"
        >
          <legend className="px-1 text-xs font-semibold uppercase tracking-[0.08em] text-base-content/45">
            Team
          </legend>
          <label className="flex flex-col gap-1 text-sm">
            <select
              className="select select-sm"
              value={
                leadFollowsFirst
                  ? FIRST_AGENT_VALUE
                  : (chiefOfStaffId ?? NO_COS_VALUE)
              }
              disabled={members.length === 0}
              aria-label="Chief of Staff"
              data-testid="team-cos-select"
              onChange={(event) => {
                const next = event.target.value
                if (next === FIRST_AGENT_VALUE) {
                  applyChiefOfStaff(firstAgentLeadId(members), true)
                  return
                }
                applyChiefOfStaff(next ? next : null, false)
              }}
            >
              <option value={FIRST_AGENT_VALUE}>First agent</option>
              {!leadFollowsFirst && !chiefOfStaffId ? (
                <option value={NO_COS_VALUE} hidden />
              ) : null}
              {cosChoices.map((member) => (
                <option key={`${member.kind}:${member.id}`} value={member.id}>
                  {agentDisplayName(member)}
                </option>
              ))}
            </select>
          </label>
          {members.length === 0 ? (
            <p className="mt-2 text-xs text-base-content/50">{COS_EMPTY_ROSTER_HINT}</p>
          ) : (
            <p className="mt-2 text-xs text-base-content/50">
              First agent is roster #1. Drag members to reorder. Remotes stay off
              this list until runtime can inject a CoS brief.
            </p>
          )}
          <Textarea
            id="team-cos-instructions"
            data-testid="team-cos-instructions"
            label="How to use this team"
            size="sm"
            rows={3}
            disabled={!chiefOfStaffId}
            value={chiefOfStaffId ? cosInstructions : ''}
            onChange={(event) => setCosInstructions(event.target.value)}
            placeholder={COS_INSTRUCTIONS_HELPER}
            aria-label="Chief of Staff instructions"
          />
        </fieldset>

        {saveMutation.isError && (
          <Alert type="error">
            {saveMutation.error instanceof Error
              ? saveMutation.error.message
              : 'Failed to save roster.'}
          </Alert>
        )}
        {status && (
          <Alert type="success">{status}</Alert>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <section
            aria-label="Team roster drop zone"
            data-testid="team-drop-zone"
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={`min-h-[18rem] rounded-xl border-2 border-dashed px-4 py-4 transition-colors ${
              dragOver
                ? 'border-primary bg-base-200'
                : 'border-base-content/25 bg-base-200/70'
            }`}
          >
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-base-content/70">
              <Users className="h-4 w-4" aria-hidden="true" />
              Roster
            </div>
            {members.length === 0 ? (
              <div className="flex h-[13rem] flex-col items-center justify-center text-center text-base-content/45">
                <p className="text-sm font-medium tracking-wide">drop agents here</p>
                <p className="mt-1 max-w-xs text-xs">
                  Drag from the available list, or use the context menu Add action.
                </p>
              </div>
            ) : (
              <ul className="flex flex-col gap-2 os-scrollable-picker-list pr-1" aria-label="Roster members">
                {members.map((member, index) => {
                  const agent: TeamAgent = {
                    id: member.id,
                    name: member.id,
                    kind: member.kind,
                    source: member.source,
                  }
                  return (
                    <li key={`${member.kind}:${member.source}`}>
                      <article
                        draggable
                        data-testid="roster-member"
                        data-index={index}
                        className="flex flex-wrap items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2 cursor-grab active:cursor-grabbing"
                        onDragStart={(event) => onRosterDragStart(event, index)}
                        onDragOver={onRosterDragOver}
                        onDrop={(event) => onRosterDrop(event, index)}
                        onContextMenu={(event) => {
                          event.preventDefault()
                          setMenu({
                            mode: 'remove',
                            agent,
                            x: event.clientX,
                            y: event.clientY,
                          })
                        }}
                      >
                        <GripVertical className="h-4 w-4 shrink-0 text-base-content/40" aria-hidden="true" />
                        <span
                          className="badge badge-ghost badge-sm font-mono"
                          data-testid="roster-index"
                        >
                          {index + 1}
                        </span>
                        <span className="font-medium">{agentDisplayName(member)}</span>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs ml-auto"
                          onClick={() => removeFromAgent(member)}
                        >
                          Remove
                        </button>
                      </article>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section aria-label="Available agents" className="min-h-[18rem]">
            <div className="mb-3 text-sm font-medium text-base-content/70">Available agents</div>
            {agentsQuery.isPending && availableAgents.length === 0 ? (
              <p className="text-sm text-base-content/45">Loading agents…</p>
            ) : (
              <>
                <Tabs
                  tabs={AVAILABLE_AGENT_KINDS.map((kind) => ({
                    key: kind,
                    label: (
                      <span data-testid={`available-agents-kind-${kind}`}>
                        {`${AVAILABLE_AGENT_KIND_LABEL[kind]} (${agentsByKind[kind].length})`}
                      </span>
                    ),
                  }))}
                  activeTab={activeAgentKind}
                  onChange={(key) => {
                    setAgentKindTabTouched(true)
                    setAgentKindTab(key as AvailableAgentKind)
                  }}
                  size="sm"
                  className="mb-2"
                />
                <div
                  className="flex max-h-[22rem] flex-col overflow-y-auto pr-1"
                  data-testid="available-agents-scroller"
                >
                  <div data-testid={`available-agents-group-${activeAgentKind}`}>
                    <ul
                      className="flex flex-col gap-1 pr-1"
                      aria-label="Available agents list"
                      role="list"
                    >
                      {agentsByKind[activeAgentKind].length === 0 ? (
                        <li className="px-2 py-1 text-xs text-base-content/40">None</li>
                      ) : (
                        agentsByKind[activeAgentKind].map((agent) => {
                          const already = rosterHasMember(members, agent)
                          return (
                            <li
                              key={`${agent.kind}:${agent.source}`}
                              draggable
                              onDragStart={(event) => onDragStart(event, agent)}
                              onContextMenu={(event) => {
                                event.preventDefault()
                                setMenu({
                                  mode: already ? 'remove' : 'add',
                                  agent,
                                  x: event.clientX,
                                  y: event.clientY,
                                })
                              }}
                              className="flex cursor-grab items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2 active:cursor-grabbing"
                            >
                              <div className="flex w-full items-center gap-2">
                                <span className="min-w-0 flex-1 truncate font-medium">
                                  {agentDisplayName(agent)}
                                </span>
                                {agent.placeholder && (
                                  <Badge type="ghost" size="xs">
                                    placeholder
                                  </Badge>
                                )}
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-xs"
                                  disabled={already}
                                  onClick={() => addFromAgent(agent)}
                                >
                                  Add
                                </button>
                              </div>
                            </li>
                          )
                        })
                      )}
                    </ul>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>

        <div
          className={`grid gap-4 lg:grid-cols-2 ${rolesUnlocked ? '' : 'opacity-60'}`}
          data-testid="team-roles-pane"
          aria-disabled={!rolesUnlocked}
        >
          <section
            aria-label="Team roles drop zone"
            data-testid="team-roles-drop-zone"
            onDragOver={onRoleDragOver}
            onDragLeave={onRoleDragLeave}
            onDrop={onRoleDrop}
            className={`min-h-[12rem] rounded-xl border-2 border-dashed px-4 py-4 transition-colors ${
              roleDragOver && rolesUnlocked
                ? 'border-primary bg-base-200'
                : 'border-base-content/25 bg-base-200/70'
            }`}
          >
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-base-content/70">
              <Tags className="h-4 w-4" aria-hidden="true" />
              Roles
            </div>
            {!rolesUnlocked ? (
              <p className="text-sm text-base-content/45" data-testid="team-roles-locked-hint">
                {COS_EMPTY_ROSTER_HINT}
              </p>
            ) : roleSlots.length === 0 ? (
              <div className="flex h-[8rem] flex-col items-center justify-center text-center text-base-content/45">
                <p className="text-sm font-medium tracking-wide">drop roles here</p>
                <p className="mt-1 max-w-xs text-xs">
                  Drag from the available list, or use Add. Assign an unroled roster agent to each
                  slot.
                </p>
              </div>
            ) : (
              <ul className="flex flex-col gap-2 os-scrollable-picker-list pr-1" aria-label="Role slots">
                {roleSlots.map((slot) => {
                  const choices = assignableMembersForSlot(members, slot)
                  return (
                    <li key={slot.id}>
                      <article
                        className="flex flex-wrap items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2"
                        data-testid="team-role-slot"
                        data-role={slot.role}
                      >
                        <span className="font-medium">{slot.role}</span>
                        <label className="sr-only" htmlFor={`role-slot-${slot.id}`}>
                          Assign {slot.role}
                        </label>
                        <select
                          id={`role-slot-${slot.id}`}
                          className="select select-xs"
                          value={slot.memberKey ?? ''}
                          aria-label={`Assign ${slot.role}`}
                          data-testid={`team-role-assign-${slot.role}`}
                          onChange={(event) => onAssignSlot(slot, event.target.value)}
                        >
                          <option value="">
                            {slot.role === 'chief_of_staff' ? 'No Chief of Staff' : 'Unassigned'}
                          </option>
                          {choices.map((member) => (
                            <option key={memberKey(member)} value={memberKey(member)}>
                              {agentDisplayName(member)}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs ml-auto"
                          aria-label={`Remove ${slot.role} role`}
                          onClick={() => removeSlot(slot)}
                        >
                          Remove
                        </button>
                      </article>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section aria-label="Available roles" className="min-h-[12rem]">
            <div className="mb-3 text-sm font-medium text-base-content/70">Available roles</div>
            {!rolesUnlocked ? (
              <p className="text-sm text-base-content/45">{COS_EMPTY_ROSTER_HINT}</p>
            ) : (
              <ul
                className="flex max-h-[14rem] flex-col gap-1 os-scrollable-picker-list overflow-y-auto pr-1"
                aria-label="Available roles list"
                role="list"
              >
                {COMPOSABLE_TEAM_ROLES.map((role) => {
                  const blocked = !canAddRoleSlot(roleSlots, role)
                  return (
                    <li
                      key={role}
                      draggable={!blocked}
                      onDragStart={(event) => onRoleDragStart(event, role)}
                      className="flex cursor-grab items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2 active:cursor-grabbing"
                      data-testid={`available-role-${role}`}
                    >
                      <span className="min-w-0 flex-1 truncate font-medium">{role}</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        disabled={blocked}
                        aria-label={`Add ${role} role`}
                        onClick={() => addFromRole(role)}
                      >
                        Add
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>

        <div
          className={`grid gap-4 lg:grid-cols-2 ${toolsUnlocked ? '' : 'opacity-60'}`}
          data-testid="team-tools-pane"
          aria-disabled={!toolsUnlocked}
        >
          <section
            aria-label="Team tools drop zone"
            data-testid="team-tools-drop-zone"
            onDragOver={onToolDragOver}
            onDragLeave={onToolDragLeave}
            onDrop={onToolDrop}
            className={`min-h-[12rem] rounded-xl border-2 border-dashed px-4 py-4 transition-colors ${
              toolDragOver && toolsUnlocked
                ? 'border-primary bg-base-200'
                : 'border-base-content/25 bg-base-200/70'
            }`}
          >
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-base-content/70">
              <Wrench className="h-4 w-4" aria-hidden="true" />
              Tools
            </div>
            {!toolsUnlocked ? (
              <p className="text-sm text-base-content/45" data-testid="team-tools-locked-hint">
                {COS_EMPTY_ROSTER_HINT}
              </p>
            ) : toolSlots.length === 0 ? (
              <div className="flex h-[8rem] flex-col items-center justify-center text-center text-base-content/45">
                <p className="text-sm font-medium tracking-wide">drop tools here</p>
                <p className="mt-1 max-w-xs text-xs">
                  Add handoff, as_tool, or an MCP server. Empty MCP agents means every roster
                  member.
                </p>
              </div>
            ) : (
              <ul className="flex flex-col gap-2 os-scrollable-picker-list pr-1" aria-label="Tool slots">
                {toolSlots.map((slot) => {
                  const tool = slot.tool
                  return (
                    <li key={slot.id}>
                      <article
                        className="flex flex-col gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2"
                        data-testid="team-tool-slot"
                        data-tool-type={tool.type}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">
                            {tool.type === 'mcp' ? `mcp:${tool.server}` : tool.type}
                          </span>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs ml-auto"
                            aria-label={`Remove ${tool.type} tool`}
                            onClick={() => setToolSlots((prev) => removeToolSlot(prev, slot.id))}
                          >
                            Remove
                          </button>
                        </div>
                        {tool.type === 'handoff' ? (
                          <div className="flex flex-wrap gap-2">
                            <label className="flex min-w-[8rem] flex-1 flex-col gap-1 text-xs">
                              <span>Target</span>
                              <select
                                className="select select-xs"
                                value={tool.to}
                                aria-label="Handoff target agent"
                                data-testid="team-tool-handoff-to"
                                onChange={(event) =>
                                  setToolSlots((prev) =>
                                    updateToolSlot(prev, slot.id, {
                                      ...tool,
                                      to: event.target.value,
                                    }),
                                  )
                                }
                              >
                                <option value="">Select agent</option>
                                {members.map((member) => (
                                  <option key={memberKey(member)} value={member.id}>
                                    {agentDisplayName(member)}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="flex min-w-[8rem] flex-1 flex-col gap-1 text-xs">
                              <span>From</span>
                              <select
                                className="select select-xs"
                                value={tool.from ?? ''}
                                aria-label="Handoff from agent"
                                data-testid="team-tool-handoff-from"
                                onChange={(event) => {
                                  const nextFrom = event.target.value
                                  const next = nextFrom
                                    ? { type: 'handoff' as const, to: tool.to, from: nextFrom }
                                    : { type: 'handoff' as const, to: tool.to }
                                  setToolSlots((prev) => updateToolSlot(prev, slot.id, next))
                                }}
                              >
                                <option value="">First agent</option>
                                {members.map((member) => (
                                  <option key={memberKey(member)} value={member.id}>
                                    {agentDisplayName(member)}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                        ) : null}
                        {tool.type === 'as_tool' ? (
                          <label className="flex min-w-[8rem] flex-col gap-1 text-xs">
                            <span>Agent as tool</span>
                            <select
                              className="select select-xs"
                              value={tool.agent}
                              aria-label="Agent exposed as a tool"
                              data-testid="team-tool-as-tool-agent"
                              onChange={(event) =>
                                setToolSlots((prev) =>
                                  updateToolSlot(prev, slot.id, {
                                    type: 'as_tool',
                                    agent: event.target.value,
                                  }),
                                )
                              }
                            >
                              <option value="">Select agent</option>
                              {members.map((member) => (
                                <option key={memberKey(member)} value={member.id}>
                                  {agentDisplayName(member)}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {tool.type === 'mcp' ? (
                          <fieldset className="flex flex-col gap-1" data-testid="team-tool-mcp-agents">
                            <legend className="text-xs">Agents</legend>
                            <p className="text-[11px] text-base-content/50">
                              Unset / empty = available to all roster agents.
                            </p>
                            {members.map((member) => {
                              const checked = tool.agents.includes(member.id)
                              return (
                                <label
                                  key={memberKey(member)}
                                  className="flex items-center gap-2 text-xs"
                                >
                                  <input
                                    type="checkbox"
                                    className="checkbox checkbox-xs"
                                    checked={checked}
                                    aria-label={`Lock ${tool.server} to ${agentDisplayName(member)}`}
                                    onChange={(event) => {
                                      const nextAgents = event.target.checked
                                        ? [...tool.agents, member.id]
                                        : tool.agents.filter((id) => id !== member.id)
                                      setToolSlots((prev) =>
                                        updateToolSlot(prev, slot.id, {
                                          type: 'mcp',
                                          server: tool.server,
                                          agents: nextAgents,
                                        }),
                                      )
                                    }}
                                  />
                                  {agentDisplayName(member)}
                                </label>
                              )
                            })}
                          </fieldset>
                        ) : null}
                      </article>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section aria-label="Available tools" className="min-h-[12rem]">
            <div className="mb-3 text-sm font-medium text-base-content/70">Available tools</div>
            {!toolsUnlocked ? (
              <p className="text-sm text-base-content/45">{COS_EMPTY_ROSTER_HINT}</p>
            ) : (
              <ul
                className="flex max-h-[14rem] flex-col gap-1 os-scrollable-picker-list overflow-y-auto pr-1"
                aria-label="Available tools list"
                role="list"
              >
                {BUILTIN_TEAM_TOOLS.map((type) => (
                  <li
                    key={type}
                    draggable
                    onDragStart={(event) => onToolDragStart(event, { type })}
                    className="flex cursor-grab items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2 active:cursor-grabbing"
                    data-testid={`available-tool-${type}`}
                  >
                    <span className="min-w-0 flex-1 truncate font-medium">{type}</span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      aria-label={`Add ${type} tool`}
                      onClick={() => addFromTool({ type })}
                    >
                      Add
                    </button>
                  </li>
                ))}
                {mcpChoices.map((server) => (
                  <li
                    key={`mcp:${server.name}`}
                    draggable
                    onDragStart={(event) =>
                      onToolDragStart(event, { type: 'mcp', server: server.name })
                    }
                    className="flex cursor-grab items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2 active:cursor-grabbing"
                    data-testid={`available-tool-mcp-${server.name}`}
                  >
                    <span className="min-w-0 flex-1 truncate font-medium">
                      mcp:{server.label}
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      aria-label={`Add ${server.label} MCP tool`}
                      onClick={() => addFromTool({ type: 'mcp', server: server.name })}
                    >
                      Add
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="border-t border-base-300 pt-3" aria-label="Get more teams">
          <InstallCatalog surface="teams" />
        </div>
      </div>

      {menu && (
        <div
          ref={menuRef}
          role="menu"
          aria-label={`Actions for ${agentDisplayName(menu.agent)}`}
          className="fixed z-[80] min-w-[10rem] rounded-lg border border-base-300 bg-neutral py-1 text-sm shadow-xl"
          style={{ left: menu.x, top: menu.y }}
        >
          {menu.mode === 'add' ? (
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-base-300/50"
              onClick={() => addFromAgent(menu.agent)}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add
            </button>
          ) : (
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-base-300/50"
              onClick={() => removeFromAgent(menu.agent)}
            >
              Remove
            </button>
          )}
        </div>
      )}
    </Modal>
  )
}
