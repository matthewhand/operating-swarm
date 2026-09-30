/**
 * #1729 — Herdr agent status replicated into OS affordances.
 *
 * Herdr publishes a four-value lifecycle per pane (`idle` | `working` |
 * `blocked` | `done`). The backend normalizes those into the five OS seat
 * states below and pushes each *transition* over the SPA mux as a
 * conversation-less `spa.event` frame (`swarm/spa_multiplex.py`,
 * `swarm/core/herdr_status_watch.py`). This module is the client half: it
 * holds the last known status per seat and decides what the operator sees.
 *
 * | OS status   | Herdr  | Affordance                                  |
 * |---|---|---|
 * | `working`   | working | busy — reported, never silent                  |
 * | `waiting`   | blocked | "needs you" indicator (the yellow dot)         |
 * | `finished`  | done    | **unread** on the seat, via the existing store   |
 * | `idle`      | idle    | nothing                                       |
 * | `unknown`   | —       | nothing. Absence of evidence is never a state   |
 *
 * Two rules the rest of the app depends on:
 *
 * 1. **Reuse the unread store.** A finished Herdr turn marks unread through
 *    `lib/unreadAgents`, the same localStorage key and the same
 *    `swarm:unread-changed` event the rail already listens for. The rail's
 *    existing dot therefore lights with no rail change and no second store.
 * 2. **`unknown` is a status, not a gap.** A pane OS has never heard from, a
 *    frame that failed to parse, and a Herdr that is down are all `unknown` —
 *    never `idle`, which would read as "nothing is happening".
 *
 * Out-of-order frames are resolved with Herdr's own `state_change_seq`, the
 * same counter the backend uses. A frame whose seq is lower than the one
 * already recorded is a late duplicate of a reading we already acted on, and
 * dropping it is what stops a slow socket from re-lighting a dot the operator
 * just cleared.
 */

import { useEffect, useState } from 'react'
import { markAgentUnread, markAgentRead } from './unreadAgents'

/** The five OS seat states. `unknown` is the honest default. */
export type HerdrSeatStatus = 'unknown' | 'idle' | 'working' | 'waiting' | 'finished'

export const UNKNOWN_STATUS: HerdrSeatStatus = 'unknown'

/** Every seat state, in one place. The identity table below derives from it. */
export const SEAT_STATUSES: readonly HerdrSeatStatus[] = [
  'unknown',
  'idle',
  'working',
  'waiting',
  'finished',
]

/** Herdr's published enum — the source vocabulary OS maps from. */
export const HERDR_AGENT_STATUSES = ['idle', 'working', 'blocked', 'done'] as const

/**
 * The single mapping table. Mirrors `swarm/herdr/status.py`; a second
 * hand-written copy in the client is how "blocked means something else here"
 * starts.
 */
const SEAT_STATUS_FOR_HERDR: Record<string, HerdrSeatStatus> = {
  idle: 'idle',
  working: 'working',
  blocked: 'waiting',
  done: 'finished',
}

export const HERDR_STATUS_FOR_SEAT: Record<HerdrSeatStatus, string> = {
  unknown: '',
  idle: 'idle',
  working: 'working',
  waiting: 'blocked',
  finished: 'done',
}

/** One seat's last known status. */
export interface HerdrSeatReading {
  seatId: string
  status: HerdrSeatStatus
  /** Herdr's `state_change_seq`; the ordering guard for late frames. */
  seq: number | null
  /** `working` → busy, `waiting` → needs a human, `finished` → new output. */
  attention: boolean
  updatedAt: number
}

export const HERDR_STATUS_CHANGED_EVENT = 'swarm:herdr-status-changed'

/** The frame the mux delivers (`spa_multiplex.SPA_EVENT_TAG`). */
export interface HerdrStatusFrame {
  type: 'herdr_status'
  seat_id: string
  target: string
  status: string
  previous_status?: string
  reason?: string
  herdr_status?: string
  needs_input?: boolean
  mark_unread?: boolean
  seat_is_open?: boolean
  state_change_seq?: number | null
  ts?: string
}

export const WAITING_LABEL = 'Waiting on you'
export const WORKING_LABEL = 'Working'
export const FINISHED_LABEL = 'Finished'

const STATUS_LABEL: Record<HerdrSeatStatus, string> = {
  unknown: 'Status unknown',
  idle: 'Idle',
  working: WORKING_LABEL,
  waiting: WAITING_LABEL,
  finished: FINISHED_LABEL,
}

export function statusLabel(status: HerdrSeatStatus): string {
  return STATUS_LABEL[status] ?? STATUS_LABEL.unknown
}

const listeners = new Set<(seatId: string) => void>()
let readings: Record<string, HerdrSeatReading> = {}

/** Test seam — the module store is process-global by design (like agentTurns). */
export function resetHerdrStatusStore(): void {
  readings = {}
  notify('')
}

function notify(seatId: string): void {
  for (const listener of listeners) {
    try {
      listener(seatId)
    } catch {
      /* ignore listener errors */
    }
  }
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    try {
      window.dispatchEvent(
        new CustomEvent(HERDR_STATUS_CHANGED_EVENT, { detail: { seatId } }),
      )
    } catch {
      /* window unavailable */
    }
  }
}

export function parseHerdrStatusFrame(raw: unknown): HerdrStatusFrame | null {
  /**
   * Validate the frame before anything acts on it. A half-parsed payload
   * must become `unknown`, never a guessed status.
   */
  if (typeof raw !== 'object' || raw === null) return null
  const payload = raw as Record<string, unknown>
  if (payload.type !== 'herdr_status') return null
  const seatId = typeof payload.seat_id === 'string' ? payload.seat_id.trim() : ''
  if (!seatId) return null
  return {
    type: 'herdr_status',
    seat_id: seatId,
    target: typeof payload.target === 'string' ? payload.target : '',
    status: typeof payload.status === 'string' ? payload.status : '',
    previous_status:
      typeof payload.previous_status === 'string' ? payload.previous_status : undefined,
    reason: typeof payload.reason === 'string' ? payload.reason : undefined,
    herdr_status: typeof payload.herdr_status === 'string' ? payload.herdr_status : undefined,
    needs_input: payload.needs_input === true,
    mark_unread: payload.mark_unread === true,
    seat_is_open: payload.seat_is_open === true,
    state_change_seq:
      typeof payload.state_change_seq === 'number' ? payload.state_change_seq : null,
    ts: typeof payload.ts === 'string' ? payload.ts : undefined,
  }
}

/**
 * OS seat status → itself. Derived from the seat list, never hand-written, so
 * adding a seat state cannot leave this half of the table behind.
 *
 * Both vocabularies are accepted because the payload legitimately carries
 * both: the server sends the *already-mapped* OS status in `status` and
 * Herdr's own value in `herdr_status`. A client that understood only one
 * would need a fallback branch at every call site.
 */
const SEAT_STATUS_IDENTITY: Record<string, HerdrSeatStatus> = Object.fromEntries(
  SEAT_STATUSES.map((seat) => [seat, seat]),
) as Record<string, HerdrSeatStatus>

/**
 * Herdr value (or an already-mapped OS value) → OS seat status. Anything else
 * stays `unknown`: a status OS cannot vouch for is never upgraded into a
 * positive label.
 */
export function normalizeSeatStatus(raw: unknown): HerdrSeatStatus {
  if (typeof raw !== 'string') return UNKNOWN_STATUS
  const key = raw.trim().toLowerCase()
  return SEAT_STATUS_FOR_HERDR[key] ?? SEAT_STATUS_IDENTITY[key] ?? UNKNOWN_STATUS
}

/**
 * The value this frame actually asserts. `herdr_status` wins — it is the
 * source vocabulary — and `status` is the server's already-mapped form.
 */
function assertedStatus(frame: HerdrStatusFrame): unknown {
  return frame.herdr_status || frame.status
}

/**
 * A late frame is one carrying a **lower** `state_change_seq` than the one
 * already recorded. Equal seqes are a re-read of the same state; a missing
 * seq cannot be ordered, so neither may discard a frame.
 */
export function isStaleFrame(incomingSeq: number | null, knownSeq: number | null): boolean {
  if (incomingSeq === null || knownSeq === null) return false
  return incomingSeq < knownSeq
}

export interface HerdrStatusDecision {
  /** The seat status to store. `unknown` for a frame we cannot vouch for. */
  status: HerdrSeatStatus
  /** True when the frame moved the seat and should be rendered. */
  changed: boolean
  /** True when the frame was an out-of-order duplicate and was dropped. */
  stale: boolean
  /** True when this transition should light the seat's unread dot. */
  markUnread: boolean
  /** True when the transition should show the "needs you" indicator. */
  attention: boolean
}

/**
 * The one transition rule, pure, so it can be reasoned about (and tested)
 * without a store, a socket, or a DOM.
 *
 * The backend already decided `mark_unread` — it knows whether the operator
 * has the seat open, and it must not guess here. The client honours that
 * decision rather than re-deriving it, because two derivations of "should
 * this be unread" is precisely the divergence that makes a dot lie.
 */
export function decideHerdrStatus(
  frame: HerdrStatusFrame,
  previous?: HerdrSeatReading | null,
): HerdrStatusDecision {
  const status = normalizeSeatStatus(assertedStatus(frame))
  const seq = typeof frame.state_change_seq === 'number' ? frame.state_change_seq : null
  if (previous && isStaleFrame(seq, previous.seq)) {
    return {
      status: previous.status,
      changed: false,
      stale: true,
      markUnread: false,
      attention: previous.attention,
    }
  }
  const changed = !previous || previous.status !== status
  // The server already decided `mark_unread`; honour it rather than re-deriving.
  const markUnread = changed && status === 'finished' && frame.mark_unread === true
  return {
    status,
    changed,
    stale: false,
    markUnread,
    attention: status === 'waiting',
  }
}

export function getHerdrReading(seatId: string): HerdrSeatReading | null {
  return readings[(seatId || '').trim()] ?? null
}

export function herdrStatusFor(seatId: string): HerdrSeatStatus {
  return getHerdrReading(seatId)?.status ?? UNKNOWN_STATUS
}

export function herdrAttentionSeats(): string[] {
  return Object.values(readings)
    .filter((row) => row.attention)
    .map((row) => row.seatId)
}

/**
 * Fold one frame into the store and apply its affordances.
 *
 * Returns the decision so a caller (and a test) can see what happened without
 * reading the store back. Unread is written through `markAgentUnread` — the
 * existing rail store — so the dot the operator already knows appears with no
 * rail change.
 */
export function applyHerdrStatusFrame(frame: HerdrStatusFrame): HerdrStatusDecision {
  const seatId = frame.seat_id.trim()
  const previous = readings[seatId] ?? null
  const decision = decideHerdrStatus(frame, previous)
  if (decision.stale) return decision

  readings = {
    ...readings,
    [seatId]: {
      seatId,
      status: decision.status,
      seq: typeof frame.state_change_seq === 'number' ? frame.state_change_seq : null,
      attention: decision.attention,
      updatedAt: Date.now(),
    },
  }
  if (decision.markUnread) markAgentUnread(seatId)
  notify(seatId)
  return decision
}

/** Clear a seat: opening its chat is the operator saying "I have seen it". */
export function clearHerdrSeat(seatId: string): void {
  const key = (seatId || '').trim()
  if (!key || !readings[key]) return
  const next = { ...readings }
  delete next[key]
  readings = next
  markAgentRead(key)
  notify(key)
}

export function clearAllHerdrSeats(): void {
  const ids = Object.keys(readings)
  if (ids.length === 0) return
  readings = {}
  for (const id of ids) markAgentRead(id)
  notify('')
}

export function subscribeHerdrStatus(listener: (seatId: string) => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Reactive read of one seat's status. */
export function useHerdrSeatStatus(seatId: string): HerdrSeatStatus {
  const [status, setStatus] = useState<HerdrSeatStatus>(() => herdrStatusFor(seatId))
  useEffect(() => {
    setStatus(herdrStatusFor(seatId))
    return subscribeHerdrStatus(() => setStatus(herdrStatusFor(seatId)))
  }, [seatId])
  return status
}
