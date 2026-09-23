/**
 * #544 / REQ-922 — the demo section profile: a repeatable "Showcase" shape
 * for screenshots and docs, applied on demand and removed cleanly.
 *
 * Deliberately NOT first-run seeds: a fresh install stays flat unless the
 * operator asks for the showcase (the ticket's recommendation), and an
 * existing `swarm_rail_sections` key is user customization that is never
 * resurrected. The profile is derived from the seats actually present at
 * apply time — kinds with no seats create no section, and anything that
 * matches no bucket (support/gate/skeptic) stays Unassigned. Teams and
 * role-assigned agents are Fancy by definition (#544).
 */

import {
  EMPTY_RAIL_SECTIONS,
  RAIL_SECTIONS_STORAGE_KEY,
  loadRailSections,
  parseRailSections,
  saveRailSections,
  type RailSection,
  type RailSectionsState,
} from './railSections'
import { GATE_AGENT_ID, SKEPTIC_AGENT_ID } from './agentRoles'
import { SUPPORT_AGENT_ID } from './supportAgent'

export const DEMO_PROFILE_STORAGE_KEY = 'swarm_rail_sections_demo_backup'

export const DEMO_SECTION_NAMES = {
  cli: 'CLI',
  api: 'API',
  remote: 'Remote',
  fancy: 'Fancy',
} as const

/** Stable ids so a second Apply refreshes the same profile, not duplicates. */
const DEMO_SECTION_IDS = {
  cli: 'sec_demo_cli',
  api: 'sec_demo_api',
  remote: 'sec_demo_remote',
  fancy: 'sec_demo_fancy',
} as const

function isRoleSeat(id: string): boolean {
  const lower = id.toLowerCase()
  return (
    lower === GATE_AGENT_ID ||
    lower === SKEPTIC_AGENT_ID ||
    lower === SUPPORT_AGENT_ID ||
    lower.startsWith('tool_gate')
  )
}

function isTeamRow(id: string): boolean {
  return id.startsWith('team:') || id.includes('team')
}

function isRemoteRow(id: string, kind: string | null | undefined): boolean {
  return (
    kind === 'remote' ||
    kind === 'herdr' ||
    id.startsWith('remote:') ||
    id.startsWith('herdr:')
  )
}

/**
 * The profile derived from the rows visible right now. Kinds with no seats
 * are skipped (no empty Remote section on day one); Fancy holds teams and
 * role-assigned seats — the composed layer (#544 defines it that way).
 */
export function demoSectionsFromRows(
  rows: Array<{ id: string; kind?: string | null }>,
): RailSectionsState {
  const membership: Record<string, string> = {}
  const used = { cli: false, api: false, remote: false, fancy: false }

  for (const row of rows) {
    const id = row.id
    if (!id || isRoleSeat(id)) continue // role seats stay Unassigned
    const kind = (row.kind || '').toLowerCase()
    let target: keyof typeof DEMO_SECTION_IDS | null = null
    if (kind === 'cli') target = 'cli'
    else if (kind === 'api' || kind === 'blueprint') target = 'api'
    else if (isTeamRow(id) || isRemoteRow(id, kind)) {
      // Teams are Fancy; remote harness rows go to Remote.
      target = isTeamRow(id) && !id.startsWith('remote:') ? 'fancy' : 'remote'
    }
    if (!target) continue
    membership[id] = DEMO_SECTION_IDS[target]
    used[target] = true
  }

  const sections: RailSection[] = (
    ['cli', 'api', 'remote', 'fancy'] as const
  )
    .filter((key) => used[key])
    .map((key) => ({ id: DEMO_SECTION_IDS[key], name: DEMO_SECTION_NAMES[key] }))

  return { sections, membership, unassignedCollapsed: false }
}

/** True when the current stored state is (still) the demo profile. */
export function isDemoProfileActive(state: RailSectionsState): boolean {
  const demoIds = new Set<string>(Object.values(DEMO_SECTION_IDS))
  const ids = state.sections.map((section) => section.id)
  return ids.length > 0 && ids.every((id) => demoIds.has(id))
}

function readBackup(): RailSectionsState | null {
  // An empty backup is a REAL backup: the user's state at apply time was a
  // flat rail, and remove must restore exactly that ("even empty is user
  // customization"). Null only when nothing was ever backed up.
  try {
    const raw = localStorage.getItem(DEMO_PROFILE_STORAGE_KEY)
    if (!raw) return null
    return parseRailSections(raw)
  } catch {
    return null
  }
}

/**
 * Apply the showcase: back up whatever the user had (even flat), then write
 * the derived profile. Always applies — the caller gates on confirmation.
 */
export function applyDemoSectionProfile(
  rows: Array<{ id: string; kind?: string | null }>,
): RailSectionsState {
  const current = loadRailSections()
  try {
    localStorage.setItem(DEMO_PROFILE_STORAGE_KEY, JSON.stringify(current))
  } catch {
    /* best-effort */
  }
  return saveRailSections(demoSectionsFromRows(rows))
}

/**
 * Remove the showcase and restore the backed-up state. If there is no
 * backup (first-run flat), restores truly empty sections. Sections the
 * user emptied or renamed are restored as they were backed up — the
 * backup IS the user's state, taken at apply time.
 */
export function removeDemoSectionProfile(): RailSectionsState {
  const backup = readBackup()
  try {
    localStorage.removeItem(DEMO_PROFILE_STORAGE_KEY)
  } catch {
    /* best-effort */
  }
  if (backup) return saveRailSections(backup)
  return saveRailSections({ ...EMPTY_RAIL_SECTIONS, membership: {} })
}

/** Storage probe for tests and the Settings toggle's initial state. */
export function hasDemoProfileBackup(): boolean {
  return readBackup() !== null
}

/** Exposed for tests only — the canonical key this module manages. */
export const _RAIL_SECTIONS_STORAGE_KEY = RAIL_SECTIONS_STORAGE_KEY
