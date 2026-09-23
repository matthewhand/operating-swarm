/**
 * #542: which rail row the chat pane is currently showing.
 *
 * The rail used to derive its active state from `selectedId`, which the sidebar
 * deliberately blanked whenever the scope was a team or a remote:
 *
 *   const selectedId =
 *     selectedTeamId || selectedRemoteId ? '' : defaultBlueprintId(blueprint)
 *
 * So as soon as the current chat was a team (`?team=`) or a remote
 * (`?remote=`), **no pin could ever be active** — which is exactly the reported
 * asymmetry: API and CLI seats highlighted (they carry `?blueprint=`), team and
 * remote pins did not, even though the pane did switch.
 *
 * Selection is a property of *which row the chat pane is showing*, and there is
 * one source of truth for it: the URL. This module is that source, so the rail
 * and the pane cannot disagree.
 *
 * ## Id shape
 *
 * Team and remote rail/pin ids are prefixed (`team:<id>`, `remote:<id>`) while
 * the query params carry the bare id, so the comparison is never a plain
 * equality. We reuse the existing {@link teamHideId} / {@link remoteHideId}
 * helpers rather than re-deriving the prefix, so the shape has one owner.
 *
 * ## Herdr
 *
 * A herdr seat has **no URL representation** today: `sidebarHref()` sends it to
 * `/teams/#herdr-members` and the anchor does not name the member, so the seat
 * cannot be distinguished from its siblings. That gap is owned by the
 * herdr-agent-selection ticket, not by this resolver — see
 * {@link RAIL_ACTIVE_HERDR_NOTE}.
 */

import { remoteHideId } from './remotesCatalog'
import { defaultBlueprintId } from './supportAgent'
import { teamHideId } from './teamRosters'

/** Where the active rail state comes from, for callers that need to branch. */
export type RailScopeKind = 'team' | 'remote' | 'seat'

export interface RailSelection {
  /** `?team=` — bare team id, or ''. */
  teamId: string
  /** `?remote=` — bare remote id, or ''. */
  remoteId: string
  /** `?blueprint=` — resolved via `defaultBlueprintId`, never ''. */
  blueprintId: string
}

export const RAIL_ACTIVE_HERDR_NOTE =
  'herdr seats have no URL representation, so they cannot be individually active until the herdr-agent-selection ticket lands'

/** Empty-ish reader that tolerates a null `URLSearchParams`. */
export function railSelectionFromParams(params?: URLSearchParams | null): RailSelection {
  const teamId = (params?.get('team') ?? '').trim()
  const remoteId = (params?.get('remote') ?? '').trim()
  const blueprintId = defaultBlueprintId(params?.get('blueprint') ?? '')
  return { teamId, remoteId, blueprintId }
}

export function railSelectionKind(selection: RailSelection): RailScopeKind {
  if (selection.teamId) return 'team'
  if (selection.remoteId) return 'remote'
  return 'seat'
}

/**
 * #543: the rail id of the herdr row the chat pane is showing, or ''. A herdr
 * seat is now URL-addressable — `?remote=herdr&session=<agent>` names the
 * agent — so `herdr:<agent>` can be active exactly like a remote row. An
 * empty session (the bare remote scope) still names no seat.
 */
export function herdrRowIdFromParams(params?: URLSearchParams | null): string {
  const remoteId = (params?.get('remote') ?? '').trim()
  const session = (params?.get('session') ?? '').trim()
  if (remoteId !== 'herdr' || !session) return ''
  return `herdr:${session}`
}

/**
 * The rail id of the row the chat pane is showing — i.e. the value a pin's
 * `id` or a row's `data-rail-id` must equal to be active.
 *
 * Precedence matches the pane: a team scope wins over a remote scope, which
 * wins over the blueprint scope. Because a team/remote selection also carries
 * whatever `?blueprint=` happened to be in the URL, precedence here is what
 * keeps the team/remote row active instead of a stale seat row.
 */
export function activeRailId(selection: RailSelection): string {
  if (selection.teamId) return teamHideId(selection.teamId)
  if (selection.remoteId) return remoteHideId(selection.remoteId)
  return selection.blueprintId
}

/** Convenience: resolve straight from the current search params. */
export function activeRailIdFromParams(params?: URLSearchParams | null): string {
  return activeRailId(railSelectionFromParams(params))
}

/**
 * #543: herdr rows CAN be active now — `herdrRowIdFromParams` names the row
 * when the URL targets a herdr agent. Kept as a helper for the rail so the
 * comparison has one owner; returns '' when no herdr row is targeted.
 */
export function isHerdrRowActive(params?: URLSearchParams | null): string {
  return herdrRowIdFromParams(params)
}
