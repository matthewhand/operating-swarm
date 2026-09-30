/**
 * REQ-209: Sidepane agent sections (membership + names + collapse).
 *
 * Custom sections are ordered headers. Agents with no membership sit in the
 * implicit Unassigned bucket. Persistence is local-first
 * (`swarm_rail_sections`) with debounced server sync through
 * /v1/preferences/ (`rail_sections`, #786) — the server bag wins on
 * hydrate; localStorage is the immediate cache. Pinned favourites are
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

export function parseRailSectionsValue(parsed: unknown): RailSectionsState {
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
}

export function parseRailSections(raw: string | null): RailSectionsState {
  if (!raw) return { ...EMPTY_RAIL_SECTIONS, membership: {} }
  try {
    return parseRailSectionsValue(JSON.parse(raw))
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

/** True when the bag defines anything — used to avoid clobbering local state with an empty server default (#786). */
export function railSectionsHasContent(state: RailSectionsState | null | undefined): boolean {
  if (!state) return false
  return state.sections.length > 0 || Object.keys(state.membership).length > 0
}

/** True when this browser has ever persisted a sections bag (#786 import guard). */
export function hasRailSectionsStorage(): boolean {
  try {
    return localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY) !== null
  } catch {
    return false
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

/* ────────────────────────────────────────────────────────────────────────
 * #1714 — the rail's AUTO (derived) sections
 *
 * `partitionRowsBySection` files rows into the *stored* sections. The sidebar
 * then renders extra blocks it derives from the rows themselves: OS / Remote /
 * CLI / API (by seat kind) and Subagents. Those are real section blocks in the
 * DOM — they carry `data-section-id`, a header, a collapse chevron and a drop
 * target — but they are NOT in `state.sections` and nothing can be filed into
 * them, because membership is only honoured for a stored section id
 * (`sectionIdForAgent`).
 *
 * That is exactly why #1714's "Move to" list was a subset: it read
 * `state.sections` while the rail rendered `state.sections` PLUS these. The
 * menu must enumerate the rail's blocks, and the auto ones must be shown as
 * non-destinations rather than silently dropped or — worse — offered as
 * choices that would silently do nothing (`moveAgentToSection` discards an
 * unknown id, so a row filed into "CLI" would snap straight back).
 * ──────────────────────────────────────────────────────────────────────── */
export const AUTO_SECTION_IDS = ['os', 'remote', 'cli', 'api', 'subagents'] as const
export type AutoSectionId = (typeof AUTO_SECTION_IDS)[number]

export function isAutoSectionId(sectionId: string | null | undefined): sectionId is AutoSectionId {
  return Boolean(sectionId) && (AUTO_SECTION_IDS as readonly string[]).includes(sectionId as string)
}

/** #1714: a Move-to row, carrying the same honesty fields a top-level item has. */
/** #1714: the shape `railMoveToDestinations` needs from a rendered block. */
export type RailSectionBlockLike = Pick<SectionBlock<{ id: string }>, 'id' | 'name' | 'custom'>

export interface RailMoveToDestination {
  id: string
  name: string
  /** A destination the row can actually be moved into. */
  selectable: boolean
  /** True for the section the row sits in right now. */
  checked: boolean
  /** Why a non-selectable row cannot be chosen — shown as its title. */
  reason?: string
}

const AUTO_SECTION_REASON =
  'Sections are grouped by seat kind, so this one cannot be chosen — it is where the row already is.'

/**
 * #1714: the "Move to" destination list, derived from the blocks the rail
 * ACTUALLY RENDERED rather than from `state.sections` alone.
 *
 * `blocks` is the sidebar's own `sectionBlocks`, so the menu is a subset of the
 * rail by construction: a section that is on screen is in the menu, and a
 * section removed from the rail is gone from the menu. That is the whole bug —
 * the two used to be computed from different sources.
 *
 * Honesty about what a destination means:
 *  - a stored (`custom`) section is a filing choice and is selectable;
 *  - an auto section is a grouping, not a choice, so it is listed and
 *    checkmarked when the row is in it, but never selectable;
 *  - Unassigned is a real filing choice UNLESS the row has an auto group, in
 *    which case removing its membership only re-files it into that group and
 *    the click would be a silent no-op. Offering it anyway is the same grey
 *    lie the CLI menu avoids for Edit/Duplicate.
 *
 * `currentSectionId` is the row's *filed* section (membership). `autoGroup` is
 * the derived block that claims the row. The auto group wins for `checked`,
 * because that is the header the operator can see the row under.
 */
export function railMoveToDestinations(opts: {
  blocks: ReadonlyArray<RailSectionBlockLike>
  currentSectionId: string
  autoGroup?: string | null
}): RailMoveToDestination[] {
  const autoGroup = opts.autoGroup ?? null
  const currentId = autoGroup ?? opts.currentSectionId
  const seen = new Set<string>()
  const out: RailMoveToDestination[] = []
  for (const block of opts.blocks) {
    if (seen.has(block.id)) continue
    seen.add(block.id)
    const auto = isAutoSectionId(block.id)
    const unassigned = isUnassignedSection(block.id)
    // Unassigned is not a move for a row an auto group will re-file.
    const selectable = block.custom && !auto
      ? true
      : unassigned
        ? !autoGroup
        : false
    out.push({
      id: block.id,
      name: block.name,
      selectable,
      checked: block.id === currentId,
      reason: auto ? AUTO_SECTION_REASON : unassigned && !selectable
        ? 'This row is grouped by seat kind, so it returns to that group.'
        : undefined,
    })
  }
  // An emptied Unassigned block is hidden by the rail (#688) but is still a
  // legal destination, so the menu keeps it even when the rail dropped it.
  if (!seen.has(UNASSIGNED_SECTION_ID)) {
    out.push({
      id: UNASSIGNED_SECTION_ID,
      name: UNASSIGNED_SECTION_NAME,
      selectable: !autoGroup,
      checked: currentId === UNASSIGNED_SECTION_ID,
      reason: autoGroup ? 'This row is grouped by seat kind, so it returns to that group.' : undefined,
    })
  }
  return out
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
