/**
 * #1222 — truthful rig topology derived from the **same** roster data the
 * composer edits. There is no parallel model: nodes come from `members` and
 * wires come from the roster's Tools slots (`handoff` / `as_tool`), falling
 * back to the legacy `wires` booleans only when a roster has no tools.
 *
 * OpenRig mapping:
 *   handoff  -> delegates_to
 *   as_tool  -> collaborates_with
 * No edge is invented for a relationship the roster does not declare.
 */

import type { RigEdgeKind } from './rigLabels'

export interface RigTopologyMember {
  id: string
  name?: string
  kind: string
  role?: string
  team_id?: string
}

export type RigTopologyTool =
  | { type: 'handoff'; to: string; from?: string }
  | { type: 'as_tool'; agent: string }
  | { type: 'mcp'; server: string; agents: string[] }

export interface RigTopologyInput {
  id?: string
  name?: string
  members?: RigTopologyMember[]
  tools?: RigTopologyTool[]
  wires?: { handoff?: boolean; as_tool?: boolean }
  chief_of_staff_id?: string | null
}

export interface RigNode {
  id: string
  name: string
  kind: string
  role: string
  /** `kind === 'team'` — a nested static rig shown as a pod. */
  pod: boolean
  lead: boolean
}

export interface RigEdge {
  from: string
  to: string
  kind: RigEdgeKind
  /** The roster tool this edge is derived from. */
  channel: 'handoff' | 'as_tool'
}

export interface RigTopology {
  id: string
  name: string
  leadId: string | null
  nodes: RigNode[]
  edges: RigEdge[]
}

function asMemberId(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function buildRigTopology(input: RigTopologyInput): RigTopology {
  const id = asMemberId(input.id)
  const name = asMemberId(input.name) || id
  const members = Array.isArray(input.members) ? input.members : []
  const nodeIds = new Set(members.map((member) => member.id))
  const requestedLead = asMemberId(input.chief_of_staff_id)
  const leadId = requestedLead && nodeIds.has(requestedLead)
    ? requestedLead
    : members[0]?.id ?? null

  const nodes: RigNode[] = members.map((member) => ({
    id: member.id,
    name: member.name || member.id,
    kind: member.kind,
    role: member.role || 'default',
    pod: member.kind === 'team',
    lead: member.id === leadId,
  }))

  const edges: RigEdge[] = []
  const seen = new Set<string>()
  const addEdge = (from: string, to: string, kind: RigEdgeKind, channel: RigEdge['channel']) => {
    if (!from || !to || from === to) return
    if (!nodeIds.has(from) || !nodeIds.has(to)) return
    const key = `${from}|${to}|${kind}`
    if (seen.has(key)) return
    seen.add(key)
    edges.push({ from, to, kind, channel })
  }

  const tools = Array.isArray(input.tools) ? input.tools : []
  for (const tool of tools) {
    if (tool.type === 'handoff') {
      addEdge(asMemberId(tool.from) || leadId || '', asMemberId(tool.to), 'delegates_to', 'handoff')
    } else if (tool.type === 'as_tool') {
      addEdge(leadId || '', asMemberId(tool.agent), 'collaborates_with', 'as_tool')
    }
  }

  // Legacy rosters predate Tools slots and only carry wires booleans. Only
  // consult them when no tools are declared, so the two never double-count.
  if (tools.length === 0 && input.wires) {
    const others = members.filter((member) => member.id !== leadId)
    if (input.wires.handoff) {
      for (const member of others) addEdge(leadId || '', member.id, 'delegates_to', 'handoff')
    }
    if (input.wires.as_tool) {
      for (const member of others) addEdge(leadId || '', member.id, 'collaborates_with', 'as_tool')
    }
  }

  return { id, name, leadId, nodes, edges }
}
