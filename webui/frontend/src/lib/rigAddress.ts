/**
 * #1224 — qualified role addresses (`role@rig`).
 *
 * Sections are **dynamic rigs**; team rosters / Team Blueprints are **static
 * rigs**. This module owns the display/parse side only: the backend resolver
 * (`swarm.core.rig_addresses`) is the source of truth for routing. The `@rig`
 * suffix is optional — a bare role resolves inside the active rig.
 */

import {
  UNASSIGNED_SECTION_ID,
  customSectionById,
  sectionIdForAgent,
  type RailSectionsState,
} from './railSections'

export const RIG_ADDRESS_SEPARATOR = '@'
export const UNASSIGNED_RIG = 'unassigned'

export interface ParsedRigAddress {
  role: string
  rig?: string
}

/** Split `role@rig` into parts; `null` for empty/malformed input. */
export function parseRigAddress(value: unknown): ParsedRigAddress | null {
  const raw = String(value ?? '').trim()
  if (!raw) return null
  const parts = raw.split(RIG_ADDRESS_SEPARATOR)
  if (parts.length > 2) return null
  const role = parts[0].trim()
  if (!role) return null
  if (parts.length === 2) {
    const rig = parts[1].trim()
    if (!rig) return null
    return { role, rig }
  }
  return { role }
}

/** Render `role@rig`, or the bare role when no rig is known. */
export function formatRigAddress(role: string, rig?: string | null): string {
  const base = String(role ?? '').trim()
  const suffix = String(rig ?? '').trim()
  return suffix ? `${base}${RIG_ADDRESS_SEPARATOR}${suffix}` : base
}

/** Dynamic rig name for an agent's sidepane Section, or `undefined`. */
export function sectionRigName(
  agentId: string,
  state: RailSectionsState,
): string | undefined {
  const sectionId = sectionIdForAgent(agentId, state)
  if (!sectionId || sectionId === UNASSIGNED_SECTION_ID) return undefined
  const section = customSectionById(state, sectionId)
  return section?.name?.trim() || section?.id
}

export interface AgentRigAddressOptions {
  role: string
  /** Static rig name from the Team Blueprint; wins over a dynamic section. */
  rig?: string | null
  /** Dynamic rig name from a sidepane Section. */
  sectionRig?: string | null
  /** Render `role@unassigned` instead of a bare role when no rig is known. */
  showUnassigned?: boolean
}

/** Display address: `role@rig`, bare `role`, or `role@unassigned`. */
export function agentRigAddress(options: AgentRigAddressOptions): string {
  const role = String(options.role ?? '').trim()
  const rig =
    String(options.rig ?? '').trim() || String(options.sectionRig ?? '').trim()
  if (!rig) {
    return formatRigAddress(role, options.showUnassigned ? UNASSIGNED_RIG : undefined)
  }
  return formatRigAddress(role, rig)
}
