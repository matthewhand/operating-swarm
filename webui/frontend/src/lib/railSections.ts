/**
 * REQ-209: Sidepane agent sections (membership + names + collapse).
 *
 * Custom sections are ordered headers. Agents with no membership sit in the
 * implicit Unassigned bucket. Persistence is localStorage for v1
 * (`swarm_rail_sections`); Django prefs (#540) later. Pinned favourites are
 * not a section — the pin grid stays above this list.
 */

export const RAIL_SECTIONS_STORAGE_KEY = 'swarm_rail_sections'
export const UNASSIGNED_SECTION_ID = 'unassigned'
export const NEW_SECTION_TARGET = 'new'
export const UNASSIGNED_SECTION_NAME = 'Unassigned'
export const NEW_SECTION_PLACEHOLDER = 'New section'
export const EMPTY_SECTION_HINT = 'Drag agents here'

export interface RailSection {
  id: string
  name: string
  collapsed?: boolean
  /** Issue #163: members may only message each other. Unassigned is never lockable. */
  internalOnly?: boolean
}

export interface RailSectionsState {
  sections: RailSection[]
  membership: Record<string, string>
  unassignedCollapsed?: boolean
}

export const EMPTY_RAIL_SECTIONS: RailSectionsState = {
  sections: [],
  membership: {},
  unassignedCollapsed: false,
}

function newSectionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `sec_${crypto.randomUUID()}`
  }
  return `sec_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function parseRailSections(raw: string | null): RailSectionsState {
  if (!raw) return { ...EMPTY_RAIL_SECTIONS, membership: {} }
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed)) return { ...EMPTY_RAIL_SECTIONS, membership: {} }
    const sections: RailSection[] = []
    if (Array.isArray(parsed.sections)) {
      for (const item of parsed.sections) {
        if (!isRecord(item)) continue
        if (typeof item.id !== 'string' || item.id.length === 0) continue
        if (item.id === UNASSIGNED_SECTION_ID) continue
        const name = typeof item.name === 'string' ? item.name : ''
        sections.push({
          id: item.id,
          name,
          collapsed: Boolean(item.collapsed),
          internalOnly: Boolean(item.internalOnly),
        })
      }
    }
    const membership: Record<string, string> = {}
    if (isRecord(parsed.membership)) {
      for (const [agentId, sectionId] of Object.entries(parsed.membership)) {
        if (!agentId || typeof sectionId !== 'string' || !sectionId) continue
        if (sectionId === UNASSIGNED_SECTION_ID) continue
        membership[agentId] = sectionId
      }
    }
    return {
      sections,
      membership,
      unassignedCollapsed: Boolean(parsed.unassignedCollapsed),
    }
  } catch {
    return { ...EMPTY_RAIL_SECTIONS, membership: {} }
  }
}

export function loadRailSections(): RailSectionsState {
  try {
    return parseRailSections(localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY))
  } catch {
    return { ...EMPTY_RAIL_SECTIONS, membership: {} }
  }
}

export function saveRailSections(state: RailSectionsState): RailSectionsState {
  try {
    localStorage.setItem(RAIL_SECTIONS_STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* persistence is best-effort */
  }
  return state
}

export function sectionIdForAgent(
  agentId: string,
  state: RailSectionsState,
): string {
  const assigned = state.membership[agentId]
  if (assigned && state.sections.some((section) => section.id === assigned)) {
    return assigned
  }
  return UNASSIGNED_SECTION_ID
}

export function isUnassignedSection(sectionId: string | null | undefined): boolean {
  return !sectionId || sectionId === UNASSIGNED_SECTION_ID
}

export function sectionDisplayName(section: Pick<RailSection, 'name'> | null | undefined): string {
  const name = section?.name?.trim() ?? ''
  return name || NEW_SECTION_PLACEHOLDER
}

export function customSectionById(
  state: RailSectionsState,
  sectionId: string,
): RailSection | undefined {
  return state.sections.find((section) => section.id === sectionId)
}

export function moveAgentToSection(
  state: RailSectionsState,
  agentId: string,
  sectionId: string,
): RailSectionsState {
  if (!agentId) return state
  const membership = { ...state.membership }
  if (isUnassignedSection(sectionId) || !state.sections.some((section) => section.id === sectionId)) {
    delete membership[agentId]
  } else {
    membership[agentId] = sectionId
  }
  return saveRailSections({ ...state, membership })
}

export function createSection(
  state: RailSectionsState,
  name = '',
): { state: RailSectionsState; section: RailSection } {
  const section: RailSection = { id: newSectionId(), name, collapsed: false, internalOnly: false }
  const next = saveRailSections({
    ...state,
    sections: [...state.sections, section],
  })
  return { state: next, section }
}

export function createSectionWithAgent(
  state: RailSectionsState,
  agentId: string,
  name = '',
): { state: RailSectionsState; section: RailSection } {
  const created = createSection(state, name)
  return {
    state: moveAgentToSection(created.state, agentId, created.section.id),
    section: created.section,
  }
}

export function renameSection(
  state: RailSectionsState,
  sectionId: string,
  name: string,
): RailSectionsState {
  if (isUnassignedSection(sectionId)) return state
  return saveRailSections({
    ...state,
    sections: state.sections.map((section) =>
      section.id === sectionId ? { ...section, name } : section,
    ),
  })
}

export function deleteSection(state: RailSectionsState, sectionId: string): RailSectionsState {
  if (isUnassignedSection(sectionId)) return state
  const membership = { ...state.membership }
  for (const [agentId, assigned] of Object.entries(membership)) {
    if (assigned === sectionId) delete membership[agentId]
  }
  return saveRailSections({
    ...state,
    sections: state.sections.filter((section) => section.id !== sectionId),
    membership,
  })
}

export function moveSection(
  state: RailSectionsState,
  sectionId: string,
  direction: 'up' | 'down',
): RailSectionsState {
  const index = state.sections.findIndex((section) => section.id === sectionId)
  if (index < 0) return state
  const swapWith = direction === 'up' ? index - 1 : index + 1
  if (swapWith < 0 || swapWith >= state.sections.length) return state
  const sections = [...state.sections]
  const current = sections[index]
  sections[index] = sections[swapWith]
  sections[swapWith] = current
  return saveRailSections({ ...state, sections })
}

export function setSectionCollapsed(
  state: RailSectionsState,
  sectionId: string,
  collapsed: boolean,
): RailSectionsState {
  if (isUnassignedSection(sectionId)) {
    return saveRailSections({ ...state, unassignedCollapsed: collapsed })
  }
  return saveRailSections({
    ...state,
    sections: state.sections.map((section) =>
      section.id === sectionId ? { ...section, collapsed } : section,
    ),
  })
}

export function toggleSectionCollapsed(
  state: RailSectionsState,
  sectionId: string,
): RailSectionsState {
  if (isUnassignedSection(sectionId)) {
    return setSectionCollapsed(state, sectionId, !state.unassignedCollapsed)
  }
  const section = customSectionById(state, sectionId)
  return setSectionCollapsed(state, sectionId, !section?.collapsed)
}

export function removeSectionMembership(
  state: RailSectionsState,
  agentId: string,
): RailSectionsState {
  if (!state.membership[agentId]) return state
  const membership = { ...state.membership }
  delete membership[agentId]
  return saveRailSections({ ...state, membership })
}

export function isSectionCollapsed(state: RailSectionsState, sectionId: string): boolean {
  if (isUnassignedSection(sectionId)) return Boolean(state.unassignedCollapsed)
  return Boolean(customSectionById(state, sectionId)?.collapsed)
}

export function isSectionInternalOnly(state: RailSectionsState, sectionId: string): boolean {
  if (isUnassignedSection(sectionId)) return false
  return Boolean(customSectionById(state, sectionId)?.internalOnly)
}

export function setSectionInternalOnly(
  state: RailSectionsState,
  sectionId: string,
  internalOnly: boolean,
): RailSectionsState {
  if (isUnassignedSection(sectionId)) return state
  return saveRailSections({
    ...state,
    sections: state.sections.map((section) =>
      section.id === sectionId ? { ...section, internalOnly: Boolean(internalOnly) } : section,
    ),
  })
}

export function toggleSectionInternalOnly(
  state: RailSectionsState,
  sectionId: string,
): RailSectionsState {
  return setSectionInternalOnly(state, sectionId, !isSectionInternalOnly(state, sectionId))
}

export type SectionTalkReason =
  | 'self'
  | 'same_section'
  | 'section_unlocked'
  | 'section_internal_only'
  | 'target_section_internal_only'
  | 'missing_id'

export interface SectionTalkDecision {
  allowed: boolean
  reason: SectionTalkReason
  callerId: string
  targetId: string
  sectionId: string
}

export const SECTION_TALK_HINT = {
  internalOnly: 'Members of this section may only message each other.',
  targetLocked: 'That agent is in an internal-only section.',
} as const

export function sectionMemberIds(state: RailSectionsState, sectionId: string): string[] {
  if (isUnassignedSection(sectionId)) return []
  return Object.entries(state.membership)
    .filter(([, assigned]) => assigned === sectionId)
    .map(([agentId]) => agentId)
}

export function canSectionTalk(
  callerId: string,
  targetId: string,
  state: RailSectionsState,
): SectionTalkDecision {
  const caller = callerId.trim()
  const target = targetId.trim()
  if (!caller || !target) {
    return { allowed: false, reason: 'missing_id', callerId: caller, targetId: target, sectionId: '' }
  }
  if (caller === target) {
    return { allowed: true, reason: 'self', callerId: caller, targetId: target, sectionId: '' }
  }
  const callerSection = sectionIdForAgent(caller, state)
  const targetSection = sectionIdForAgent(target, state)
  if (isSectionInternalOnly(state, callerSection)) {
    if (callerSection === targetSection) {
      return {
        allowed: true,
        reason: 'same_section',
        callerId: caller,
        targetId: target,
        sectionId: callerSection,
      }
    }
    return {
      allowed: false,
      reason: 'section_internal_only',
      callerId: caller,
      targetId: target,
      sectionId: callerSection,
    }
  }
  if (isSectionInternalOnly(state, targetSection)) {
    return {
      allowed: false,
      reason: 'target_section_internal_only',
      callerId: caller,
      targetId: target,
      sectionId: targetSection,
    }
  }
  return { allowed: true, reason: 'section_unlocked', callerId: caller, targetId: target, sectionId: '' }
}

export function filterTalkTargets(
  callerId: string,
  targetIds: Iterable<string>,
  state: RailSectionsState,
): string[] {
  return [...targetIds].filter((id) => canSectionTalk(callerId, id, state).allowed)
}

/** Snapshot locked sections onto a chat turn so mailbox tools can enforce the lock. */
export function railSectionsParam(): { rail_sections?: RailSectionsState } {
  const state = loadRailSections()
  if (!state.sections.some((section) => section.internalOnly)) return {}
  return { rail_sections: state }
}

export interface SectionBlock<T extends { id: string }> {
  id: string
  name: string
  collapsed: boolean
  rows: T[]
  custom: boolean
  internalOnly?: boolean
}

export function partitionRowsBySection<T extends { id: string }>(
  rows: T[],
  state: RailSectionsState,
): SectionBlock<T>[] {
  const buckets = new Map<string, T[]>()
  for (const section of state.sections) {
    buckets.set(section.id, [])
  }
  const unassigned: T[] = []
  for (const row of rows) {
    const sectionId = sectionIdForAgent(row.id, state)
    const bucket = buckets.get(sectionId)
    if (bucket) bucket.push(row)
    else unassigned.push(row)
  }
  const custom = state.sections.map((section) => ({
    id: section.id,
    name: section.name,
    collapsed: Boolean(section.collapsed),
    rows: buckets.get(section.id) ?? [],
    custom: true,
    internalOnly: Boolean(section.internalOnly),
  }))
  return [
    ...custom,
    {
      id: UNASSIGNED_SECTION_ID,
      name: UNASSIGNED_SECTION_NAME,
      collapsed: Boolean(state.unassignedCollapsed),
      rows: unassigned,
      custom: false,
      internalOnly: false,
    },
  ]
}
