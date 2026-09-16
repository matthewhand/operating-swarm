import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GripVertical, Plus, Tags, Users } from 'lucide-react'
import { Alert, Badge, Button, Input, Modal, Textarea } from './DaisyUI'
import { MarketplaceScanSection } from './MarketplaceScanSection'
import {
  createTeamRoster,
  fetchTeamAgents,
  fetchTeamRosters,
  updateTeamRoster,
  type TeamAgent,
  type TeamRosterRecord,
} from '../lib/api'
import {
  addMember,
  agentDisplayName,
  applySlotMemberChange,
  assignableMembersForSlot,
  assignRoleSlot,
  canAddRoleSlot,
  COMPOSABLE_TEAM_ROLES,
  COS_EMPTY_ROSTER_HINT,
  COS_INSTRUCTIONS_HELPER,
  dataTransferHasType,
  DEFAULT_COS_STARTER,
  DEFAULT_TEAM_WIRES,
  DRAG_MIME,
  eligibleCosMembers,
  emptyRosterDraft,
  encodeDragAgent,
  encodeDragRole,
  FIRST_AGENT_VALUE,
  firstAgentLeadId,
  isCosEligibleMember,
  KIND_LABEL,
  memberByKey,
  memberKey,
  newRoleSlot,
  NO_COS_VALUE,
  parseDragAgent,
  parseDragRole,
  parseDragRosterIndex,
  parseRosterMember,
  PLACEHOLDER_TEAM_AGENTS,
  removeMember,
  removeRoleSlot,
  reorderMembers,
  restoreCosId,
  ROLE_DRAG_MIME,
  ROSTER_DRAG_MIME,
  rosterHasMember,
  setMemberRole,
  slotsFromMembers,
  stampCosRole,
  unassignSlotsForMember,
  type ComposableTeamRole,
  type RoleSlot,
  type TeamRosterMember,
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

function kindBadgeType(kind: TeamAgent['kind']): 'info' | 'success' | 'warning' {
  if (kind === 'api') return 'info'
  if (kind === 'cli') return 'success'
  return 'warning'
}

export default function TeamComposer({ isOpen, onClose }: TeamComposerProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [members, setMembers] = useState<TeamRosterMember[]>([])
  const [wires, setWires] = useState<{ handoff: boolean; as_tool: boolean }>({
    ...DEFAULT_TEAM_WIRES,
  })
  const [chiefOfStaffId, setChiefOfStaffId] = useState<string | null>(null)
  const [leadFollowsFirst, setLeadFollowsFirst] = useState(true)
  const [cosInstructions, setCosInstructions] = useState(DEFAULT_COS_STARTER)
  const [savedId, setSavedId] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [roleDragOver, setRoleDragOver] = useState(false)
  const [roleSlots, setRoleSlots] = useState<RoleSlot[]>([])
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const cosChoices = useMemo(() => eligibleCosMembers(members), [members])
  const rolesUnlocked = members.length > 0

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

  const resetDraft = useCallback(() => {
    const draft = emptyRosterDraft()
    setName(draft.name)
    setMembers(draft.members)
    setWires({ ...draft.wires })
    setChiefOfStaffId(draft.chiefOfStaffId)
    setLeadFollowsFirst(true)
    setCosInstructions(draft.chiefOfStaffInstructions)
    setRoleSlots([])
    setSavedId(null)
    setStatus(null)
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

  const removeFromAgent = useCallback((agent: Pick<TeamRosterMember, 'kind' | 'id' | 'source'>) => {
    setMembers((prev) => {
      const next = removeMember(prev, agent)
      if (next.length === 0) {
        setChiefOfStaffId(null)
        setLeadFollowsFirst(true)
        setRoleSlots([])
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
        return stamped
      }
      setRoleSlots((slots) => unassignSlotsForMember(slots, agent))
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

  const onDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    if (dataTransferHasType(event.dataTransfer, ROLE_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)) {
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
      dataTransferHasType(event.dataTransfer, ROSTER_DRAG_MIME) &&
      !dataTransferHasType(event.dataTransfer, DRAG_MIME)
    ) {
      return
    }
    const raw = event.dataTransfer.getData(DRAG_MIME) || event.dataTransfer.getData('text/plain')
    if (parseDragRole(raw) && !parseDragAgent(raw)) return
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
    const raw =
      event.dataTransfer.getData(ROLE_DRAG_MIME) || event.dataTransfer.getData('text/plain')
    if (parseDragAgent(raw) && !parseDragRole(raw)) return
    const role = parseDragRole(raw)
    if (role) addFromRole(role)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const trimmed = name.trim()
      if (!trimmed) {
        throw new Error('Team name is required.')
      }
      const stamped = stampCosRole(members, chiefOfStaffId)
      const payload = {
        name: trimmed,
        members: stamped,
        wires,
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
    setWires({
      handoff: roster.wires?.handoff ?? true,
      as_tool: roster.wires?.as_tool ?? true,
    })
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

        <fieldset className="rounded-lg border border-base-300 bg-base-200/40 px-3 py-2">
          <legend className="px-1 text-xs font-semibold uppercase tracking-[0.08em] text-base-content/45">
            Wires
          </legend>
          <div className="flex flex-wrap gap-6">
            <label className="label cursor-pointer justify-start gap-2">
              <input
                type="checkbox"
                className="toggle toggle-sm"
                checked={wires.handoff}
                onChange={(event) =>
                  setWires((prev) => ({ ...prev, handoff: event.target.checked }))
                }
              />
              <span className="label-text">handoff</span>
            </label>
            <label className="label cursor-pointer justify-start gap-2">
              <input
                type="checkbox"
                className="toggle toggle-sm"
                checked={wires.as_tool}
                onChange={(event) =>
                  setWires((prev) => ({ ...prev, as_tool: event.target.checked }))
                }
              />
              <span className="label-text">as_tool</span>
            </label>
          </div>
          <p className="mt-2 text-xs text-base-content/50">
            Per-team openai-agents wiring. Both default on. Gate is unwired — all tools
            are approved.
          </p>
        </fieldset>

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
                        <Badge type={kindBadgeType(member.kind)} size="sm">
                          {KIND_LABEL[member.kind]}
                        </Badge>
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
              <div
                className="flex max-h-[22rem] flex-col gap-3 overflow-y-auto pr-1"
                aria-label="Available agents list"
                data-testid="available-agents-scroller"
                role="list"
              >
                {(['api', 'cli', 'remote'] as const).map((kind) => (
                  <div key={kind} data-testid={`available-agents-group-${kind}`}>
                    <h4
                      className="mb-1 text-xs font-semibold uppercase tracking-[0.08em] text-base-content/45"
                      data-testid={`available-agents-kind-${kind}`}
                    >
                      {KIND_LABEL[kind]}
                      <span className="ml-1 font-normal normal-case tracking-normal text-base-content/35">
                        ({agentsByKind[kind].length})
                      </span>
                    </h4>
                    <ul className="flex flex-col gap-1 pr-1">
                      {agentsByKind[kind].length === 0 ? (
                        <li className="px-2 py-1 text-xs text-base-content/40">None</li>
                      ) : (
                        agentsByKind[kind].map((agent) => {
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
                                <Badge type={kindBadgeType(agent.kind)} size="sm">
                                  {KIND_LABEL[agent.kind]}
                                </Badge>
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
                ))}
              </div>
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

        <div className="border-t border-base-300 pt-3" aria-label="Get more teams">
          <MarketplaceScanSection kind="teams" />
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
