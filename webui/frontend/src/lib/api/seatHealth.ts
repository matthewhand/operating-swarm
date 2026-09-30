/** Seat health endpoints (#1658 follow-up) — one batch call per poll tick. */
import { apiPost } from './client'

export interface SeatHealthRefPayload {
  kind: 'api' | 'cli' | 'remote'
  seat_id: string
  cli?: string
  base_url?: string
  api_key_env?: string
  model?: string
}

export interface SeatHealthRow {
  seat_id: string
  kind: string
  state: 'unknown' | 'ok' | 'broken'
  reason: string
  latency_ms: number
  checked_at: number
  broken: boolean
  /** #1783: the remote probe's machine-readable "nothing was probed" code. */
  gap?: string
}

export interface SeatHealthBatchResponse {
  object: string
  results: SeatHealthRow[]
  checked: number
  broken: number
}

export function probeSeatHealthBatch(
  seats: SeatHealthRefPayload[],
): Promise<SeatHealthRow[]> {
  return apiPost<SeatHealthBatchResponse>('/v1/seats/health', { seats, force: false }).then(
    (res) => res?.results ?? [],
  )
}

/**
 * #1783 — remote health rides the seat batch, so N remotes cost ONE write.
 *
 * There is no batch form of `POST /v1/remotes/<id>/health/`; the per-id route
 * stays for the one-shot "test this remote" button in Settings, which is a
 * deliberate single user action. The 60s poll cannot afford it: one POST per
 * remote per tick is what put ~290k requests on that endpoint in a day, against
 * a 1-per-minute DRF write throttle.
 *
 * `POST /v1/seats/health` already probes `kind: "remote"` through the same
 * `remotes.check_health`, cached server-side for `CACHE_TTL_S`, so this is one
 * real probe per remote per minute however many clients ask. `gap` rides along
 * in the row so "never configured" stays distinguishable from "no verdict"
 * without parsing `reason` prose.
 */
export function probeRemoteHealthBatch(
  remoteIds: string[],
): Promise<SeatHealthRow[]> {
  return apiPost<SeatHealthBatchResponse>('/v1/seats/health', {
    seats: remoteIds.map((id) => ({ kind: 'remote' as const, seat_id: id })),
    force: false,
  }).then((res) => res?.results ?? [])
}
