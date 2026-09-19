/**
 * #544 / REQ-922 — the demo section profile (Showcase).
 *
 * The contract: apply derives CLI/API/Remote/Fancy from live rows with a
 * backup of the user's layout; remove restores it; kinds with no seats make
 * no section; role seats stay Unassigned; teams are Fancy; an existing
 * (even empty) stored state is user customization the profile replaces only
 * via an explicit apply, and restores on remove.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  DEMO_SECTION_NAMES,
  _RAIL_SECTIONS_STORAGE_KEY,
  applyDemoSectionProfile,
  demoSectionsFromRows,
  hasDemoProfileBackup,
  isDemoProfileActive,
  removeDemoSectionProfile,
} from '../demoSections'
import { loadRailSections, saveRailSections } from '../railSections'

const ROWS = [
  { id: 'grok', kind: 'cli' },
  { id: 'omp', kind: 'cli' },
  { id: 'jeeves', kind: 'api' },
  { id: 'example_api_minimal', kind: 'blueprint' },
  { id: 'remote:omb', kind: 'remote' },
  { id: 'herdr:fen', kind: 'herdr' },
  { id: 'team:research-squad', kind: null },
  { id: 'gate', kind: 'blueprint' }, // role seat
  { id: 'skeptic', kind: 'blueprint' }, // role seat
]

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})

describe('#544: profile derivation', () => {
  it('buckets rows by kind; teams land in Fancy; role seats stay Unassigned', () => {
    const state = demoSectionsFromRows(ROWS)
    const names = Object.fromEntries(state.sections.map((s) => [s.name, s.id]))

    expect(names[DEMO_SECTION_NAMES.cli]).toBeTruthy()
    expect(names[DEMO_SECTION_NAMES.api]).toBeTruthy()
    expect(names[DEMO_SECTION_NAMES.remote]).toBeTruthy()
    expect(names[DEMO_SECTION_NAMES.fancy]).toBeTruthy()

    const members = (name: string) =>
      Object.entries(state.membership)
        .filter(([, sectionId]) => sectionId === names[name])
        .map(([id]) => id)

    expect(members('CLI')).toEqual(['grok', 'omp'])
    expect(members('API')).toEqual(['jeeves', 'example_api_minimal'])
    expect(members('Remote')).toEqual(['remote:omb', 'herdr:fen'])
    expect(members('Fancy')).toEqual(['team:research-squad'])
    expect(state.membership['gate']).toBeUndefined()
    expect(state.membership['skeptic']).toBeUndefined()
  })

  it('creates no section for an empty category', () => {
    const state = demoSectionsFromRows([
      { id: 'grok', kind: 'cli' },
    ])
    expect(state.sections.map((s) => s.name)).toEqual(['CLI'])
  })

  it('a seat matching nothing stays Unassigned (no membership entry)', () => {
    const state = demoSectionsFromRows([
      { id: 'weird-seat', kind: 'something-else' },
      { id: 'grok', kind: 'cli' },
    ])
    expect(state.membership['weird-seat']).toBeUndefined()
    expect(state.membership['grok']).toBeTruthy()
  })
})

describe('#544: apply / remove round-trip', () => {
  it('apply backs up the prior layout and remove restores it', () => {
    // Pre-existing user layout: renamed section with one member.
    saveRailSections({
      sections: [{ id: 'sec_mine', name: 'Mine' }],
      membership: { jeeves: 'sec_mine' },
    })

    applyDemoSectionProfile(ROWS)
    const applied = loadRailSections()
    expect(isDemoProfileActive(applied)).toBe(true)
    expect(applied.sections.map((s) => s.name)).toContain('Fancy')
    // Re-bucketed: jeeves moved from the user's 'Mine' section into the
    // derived API demo section (and remove() puts it back below).
    const apiSection = applied.sections.find((s) => s.name === 'API')
    expect(applied.membership['jeeves']).toBe(apiSection?.id)

    const removed = removeDemoSectionProfile()
    expect(isDemoProfileActive(removed)).toBe(false)
    expect(removed.sections.map((s) => s.id)).toEqual(['sec_mine'])
    expect(removed.membership['jeeves']).toBe('sec_mine')
    expect(hasDemoProfileBackup()).toBe(false)
  })

  it('remove with no prior state returns to a flat rail (no sections)', () => {
    applyDemoSectionProfile(ROWS)
    const removed = removeDemoSectionProfile()
    expect(removed.sections).toEqual([])
    expect(removed.membership).toEqual({})
  })

  it('a second apply refreshes the same profile instead of duplicating sections', () => {
    applyDemoSectionProfile(ROWS)
    applyDemoSectionProfile(ROWS)
    const state = loadRailSections()
    const cliSections = state.sections.filter((s) => s.name === 'CLI')
    expect(cliSections).toHaveLength(1)
  })

  it('stores a backup key only while the profile is applied', () => {
    expect(hasDemoProfileBackup()).toBe(false)
    applyDemoSectionProfile(ROWS)
    expect(hasDemoProfileBackup()).toBe(true)
    removeDemoSectionProfile()
    expect(hasDemoProfileBackup()).toBe(false)
  })

  it('never writes through the canonical key on parse-only checks', () => {
    // isDemoProfileActive must not mutate storage (no resurrect-on-load).
    localStorage.setItem(_RAIL_SECTIONS_STORAGE_KEY, JSON.stringify({ sections: [], membership: {} }))
    expect(isDemoProfileActive(loadRailSections())).toBe(false)
    expect(JSON.parse(localStorage.getItem(_RAIL_SECTIONS_STORAGE_KEY) || '{}')).toEqual({
      sections: [],
      membership: {},
    })
  })
})
