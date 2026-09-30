/**
 * #1222 — operator-facing display vocabulary for the virtual-team concept.
 *
 * The rebrand is **display-only**: code identifiers, API routes
 * (`/v1/team-rosters/`), Python/TS type names (`TeamRoster`, `TeamKindBase`)
 * and persisted data keys stay `team`. Only copy the operator reads says
 * "group chat" (#1362). Import these constants instead of hardcoding the term
 * so singular / plural stays consistent.
 *
 * Relationship to #1224 (`rigAddresses`): a **dynamic rig** is a sidepane
 * Section; a **static rig** is a team roster. Both read as "group chat" to the
 * operator, so the display term is shared.
 */

// #1362: the operator-facing term is "group chat". Identifiers/routes stay
// `team`; only the copy changes.
export const RIG = 'Group chat'
export const RIGS = 'Group chats'
export const RIG_LOWER = 'group chat'
export const RIGS_LOWER = 'group chats'

export interface RigWordOptions {
  /** Lowercase (`rig` / `rigs`) — for mid-sentence copy. */
  lower?: boolean
}

/** Singular/plural display term for a member/member count. */
export function rigWord(count: number, options: RigWordOptions = {}): string {
  const one = count === 1
  if (options.lower) return one ? RIG_LOWER : RIGS_LOWER
  return one ? RIG : RIGS
}

/**
 * OpenRig wire vocabulary (https://github.com/mvschwarz/openrig).
 *
 * The roster already declares these relationships:
 *   - a `handoff` tool → `delegates_to`
 *   - an `as_tool` tool → `collaborates_with`
 *
 * `can_observe` is part of the OpenRig vocabulary but no current roster store
 * declares an observer edge, so it is defined here for labels only — the
 * topology view never invents an edge the data does not carry.
 */
export const RIG_EDGE_KINDS = [
  'delegates_to',
  'collaborates_with',
  'can_observe',
] as const
export type RigEdgeKind = (typeof RIG_EDGE_KINDS)[number]

export const RIG_EDGE_LABEL: Record<RigEdgeKind, string> = {
  delegates_to: 'delegates to',
  collaborates_with: 'collaborates with',
  can_observe: 'can observe',
}
