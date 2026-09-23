import { afterEach, describe, expect, it } from 'vitest'
import {
  EMPTY_SECTION_HINT,
  NEW_SECTION_PLACEHOLDER,
  RAIL_SECTIONS_STORAGE_KEY,
  UNASSIGNED_SECTION_ID,
  createSection,
  createSectionWithAgent,
  deleteSection,
  canSectionTalk,
  filterTalkTargets,
  isSectionCollapsed,
  isSectionInternalOnly,
  loadRailSections,
  moveAgentToSection,
  moveSection,
  parseRailSections,
  partitionRowsBySection,
  railSectionsParam,
  renameSection,
  sectionIdForAgent,
  setSectionCollapsed,
  setSectionInternalOnly,
  toggleSectionCollapsed,
  toggleSectionInternalOnly,
} from '../railSections'

describe('railSections (REQ-209)', () => {
  afterEach(() => {
    localStorage.removeItem(RAIL_SECTIONS_STORAGE_KEY)
  })

  it('treats missing or corrupt storage as empty Unassigned membership', () => {
    expect(loadRailSections()).toEqual({
      sections: [],
      membership: {},
      unassignedCollapsed: false,
    })
    expect(parseRailSections('{not-json')).toEqual({
      sections: [],
      membership: {},
      unassignedCollapsed: false,
    })
    expect(parseRailSections(JSON.stringify({ sections: [1], membership: { x: 2 } }))).toEqual({
      sections: [],
      membership: {},
      unassignedCollapsed: false,
    })
  })

  it('creates a section, places the agent, and persists names + membership', () => {
    const created = createSectionWithAgent(
      { sections: [], membership: {}, unassignedCollapsed: false },
      'rakazo',
    )
    expect(created.section.name).toBe('')
    expect(sectionIdForAgent('rakazo', created.state)).toBe(created.section.id)
    expect(sectionIdForAgent('reachy', created.state)).toBe(UNASSIGNED_SECTION_ID)
    const renamed = renameSection(created.state, created.section.id, 'stuff')
    expect(JSON.parse(localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY) || '{}')).toMatchObject({
      sections: [{ id: created.section.id, name: 'stuff' }],
      membership: { rakazo: created.section.id },
    })
    expect(partitionRowsBySection([{ id: 'rakazo' }, { id: 'reachy' }], renamed).map((block) => ({
      id: block.id,
      name: block.name || NEW_SECTION_PLACEHOLDER,
      members: block.rows.map((row) => row.id),
    }))).toEqual([
      { id: created.section.id, name: 'stuff', members: ['rakazo'] },
      { id: UNASSIGNED_SECTION_ID, name: 'Unassigned', members: ['reachy'] },
    ])
    expect(EMPTY_SECTION_HINT).toBe('Drag agents here')
  })

  it('creates an empty section that agents can be dragged into (#173)', () => {
    const created = createSection({ sections: [], membership: {}, unassignedCollapsed: false })
    expect(created.section.name).toBe('')
    expect(created.state.sections.map((section) => section.id)).toEqual([created.section.id])
    expect(created.state.membership).toEqual({})
    expect(sectionIdForAgent('codey', created.state)).toBe(UNASSIGNED_SECTION_ID)
    const moved = moveAgentToSection(created.state, 'codey', created.section.id)
    expect(sectionIdForAgent('codey', moved)).toBe(created.section.id)
    expect(partitionRowsBySection([{ id: 'codey' }], moved)[0].rows.map((row) => row.id)).toEqual([
      'codey',
    ])
  })

  it('moves between existing sections and Unassigned', () => {
    const first = createSectionWithAgent(
      { sections: [], membership: {}, unassignedCollapsed: false },
      'codey',
      'stuff',
    )
    const second = createSectionWithAgent(first.state, 'stewie', 'other')
    const toStuff = moveAgentToSection(second.state, 'stewie', first.section.id)
    expect(sectionIdForAgent('stewie', toStuff)).toBe(first.section.id)
    const unassigned = moveAgentToSection(toStuff, 'stewie', UNASSIGNED_SECTION_ID)
    expect(sectionIdForAgent('stewie', unassigned)).toBe(UNASSIGNED_SECTION_ID)
  })

  it('delete returns members to Unassigned; move up/down reorders custom sections', () => {
    const first = createSectionWithAgent(
      { sections: [], membership: {}, unassignedCollapsed: false },
      'codey',
      'alpha',
    )
    const second = createSectionWithAgent(first.state, 'stewie', 'beta')
    const down = moveSection(second.state, first.section.id, 'down')
    expect(down.sections.map((section) => section.id)).toEqual([
      second.section.id,
      first.section.id,
    ])
    const removed = deleteSection(down, first.section.id)
    expect(sectionIdForAgent('codey', removed)).toBe(UNASSIGNED_SECTION_ID)
    expect(removed.sections.map((section) => section.name)).toEqual(['beta'])
  })

  it('persists collapse for custom sections and Unassigned', () => {
    const created = createSectionWithAgent(
      { sections: [], membership: {}, unassignedCollapsed: false },
      'codey',
      'stuff',
    )
    const collapsed = toggleSectionCollapsed(created.state, created.section.id)
    expect(isSectionCollapsed(collapsed, created.section.id)).toBe(true)
    const unassigned = setSectionCollapsed(collapsed, UNASSIGNED_SECTION_ID, true)
    expect(unassigned.unassignedCollapsed).toBe(true)
    expect(loadRailSections().unassignedCollapsed).toBe(true)
  })

  it('Issue #163: persists internal-only lock and restricts talk to section members', () => {
    const created = createSectionWithAgent(
      { sections: [], membership: {}, unassignedCollapsed: false },
      'pat',
      'office',
    )
    const withCos = moveAgentToSection(created.state, 'cos', created.section.id)
    expect(isSectionInternalOnly(withCos, created.section.id)).toBe(false)
    expect(railSectionsParam()).toEqual({})
    const locked = toggleSectionInternalOnly(withCos, created.section.id)
    expect(isSectionInternalOnly(locked, created.section.id)).toBe(true)
    expect(JSON.parse(localStorage.getItem(RAIL_SECTIONS_STORAGE_KEY) || '{}').sections[0].internalOnly).toBe(
      true,
    )
    expect(canSectionTalk('pat', 'cos', locked).reason).toBe('same_section')
    expect(canSectionTalk('pat', 'ada', locked).allowed).toBe(false)
    expect(canSectionTalk('ada', 'pat', locked).reason).toBe('target_section_internal_only')
    expect(filterTalkTargets('pat', ['cos', 'ada', 'pat'], locked)).toEqual(['cos', 'pat'])
    expect(railSectionsParam().rail_sections?.sections[0]?.internalOnly).toBe(true)
    const unlocked = setSectionInternalOnly(locked, created.section.id, false)
    expect(canSectionTalk('pat', 'ada', unlocked).allowed).toBe(true)
    expect(isSectionInternalOnly(unlocked, UNASSIGNED_SECTION_ID)).toBe(false)
  })

  it('Issue #163: a locked team of one cannot talk outside until unlock', () => {
    const created = createSectionWithAgent(
      { sections: [], membership: {}, unassignedCollapsed: false },
      'pat',
      'solo',
    )
    const locked = toggleSectionInternalOnly(created.state, created.section.id)
    expect(canSectionTalk('pat', 'cos', locked).reason).toBe('section_internal_only')
    expect(canSectionTalk('cos', 'pat', locked).allowed).toBe(false)
    expect(partitionRowsBySection([{ id: 'pat' }], locked)[0].internalOnly).toBe(true)
    const unlocked = toggleSectionInternalOnly(locked, created.section.id)
    expect(canSectionTalk('pat', 'cos', unlocked).reason).toBe('section_unlocked')
  })
})
