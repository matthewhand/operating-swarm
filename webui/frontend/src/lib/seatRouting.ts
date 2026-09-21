/**
 * #804 — cross-kind routing picks must land on a real seat.
 *
 * The seat URL vocabulary is `?blueprint=` (api seats, incl. the api_agent
 * gateway), `?cli=` (host CLI seats), `?remote=` and `?team=`. Nothing reads
 * `?agent=` — yet cross-kind picks used to write exactly that dead param, and
 * the two-stage picker dropped API picks from non-API seats entirely.
 *
 * This helper turns a cross-kind pick into an explicit URL patch so every
 * kind resolves to a seat ChatPage actually reads, and stale params from the
 * previous seat (`?session=`, a previous kind's marker, an old `?model=`)
 * cannot bleed through.
 */

/** Params that mark a seat kind; picking one kind clears the others. */
const SEAT_KIND_PARAMS = ['blueprint', 'cli', 'remote', 'team'] as const
/** Per-seat state cleared on any seat change so nothing bleeds across (#804). */
const SEAT_STATE_PARAMS = ['session', 'model'] as const
const deleteListFrom = (kinds: readonly string[], set: Record<string, string>): string[] => [
  ...kinds.filter((p) => !(p in set)),
]

export type SeatPickKind = 'api' | 'cli' | 'remote' | 'team'

export interface SeatParamPatch {
  /** Params to set for the picked seat (id may be empty for defaults). */
  set: Record<string, string>
  /** Stale params to delete (other kinds' markers + per-seat state). */
  delete: string[]
}

export interface SeatPickOpts {
  /**
   * API gateway profile picked from stage 2 (`API gateway → Claude Work`):
   * lands on the `api_agent` gateway with that profile applied as its model.
   * Absent for flat-palette picks of named api blueprints.
   */
  apiModel?: string
}

/**
 * #899: honest copy for a provider pick the current seat cannot apply.
 * The picker only surfaces API-gateway profiles as a reconfiguration —
 * it must never silently jump seats (#899's bug), so the attempt is
 * acknowledged with what happened and what will actually work.
 */
export function providerReconfigureNotice(
  profile: string,
  currentKind: 'api' | 'cli' | 'remote' | 'team',
): string {
  const seatLabel =
    currentKind === 'cli'
      ? 'CLI agent'
      : currentKind === 'remote'
        ? 'remote agent'
        : currentKind === 'team'
          ? 'team'
          : 'API agent'
  return `Provider profile '${profile}' noted — the ${seatLabel} keeps its own backend. Use the agent picker (stage 1 → API gateway) to switch to that profile as a seat.`
}

/**
 * The canonical seat-param patch for a cross-kind pick.
 *
 * - `api`: `?blueprint=<id>` (empty id → the `api_agent` gateway); a gateway
 *   profile pick adds `?model=<profile>` for the gateway to apply.
 * - `cli`: `?cli=<name>` — the param ChatPage's CLI resolution chain consumes.
 * - `remote` / `team` keep their existing params.
 * - `session` is per-seat state: always cleared so a new seat never inherits
 *   the previous seat's conversation. `model` is cleared too unless the pick
 *   explicitly sets it.
 */
export function seatParamsForPick(
  kind: SeatPickKind,
  id: string,
  opts: SeatPickOpts = {},
): SeatParamPatch {
  const trimmed = (id ?? '').trim()
  const set: Record<string, string> = {}
  if (kind === 'api') {
    set.blueprint = trimmed || 'api_agent'
    if (opts.apiModel) set.model = opts.apiModel
  } else if (kind === 'cli') {
    set.cli = trimmed
  } else if (kind === 'remote') {
    set.remote = trimmed
  } else {
    set.team = trimmed
  }
  const deleteList = deleteListFrom(SEAT_KIND_PARAMS, set)
  deleteList.push(...SEAT_STATE_PARAMS.filter((p) => !(p in set)))
  return { set, delete: deleteList }
}
