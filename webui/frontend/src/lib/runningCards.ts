/**
 * #1374 Phase B — models for Cursor-like Running cards.
 *
 * One card per live turn (plus a synthetic card when the thread is awaiting
 * a first token but no `turn_started` bookend has arrived yet). The open
 * arrow uses the same rail href as every other seat jump.
 */

import { agentChatHref, agentIdFromBlueprint } from './agentChat'
import { runningTurns, type TurnSnapshot } from './agentTurns'

export const RUNNING_CARD_STOP_CLASS =
  'os-running-card__stop opacity-0 pointer-events-none transition-opacity motion-reduce:transition-none group-hover/badge:opacity-100 group-hover/badge:pointer-events-auto group-focus-within/badge:opacity-100 group-focus-within/badge:pointer-events-auto focus-visible:opacity-100 focus-visible:pointer-events-auto'

export interface RunningCardModel {
  key: string
  agentId: string
  openId: string
  turnId?: string
  name: string
  href: string
  current: boolean
}

/** Strip a team-member lock key (`team#member`) down to the openable seat. */
export function openIdForRunningAgent(agentId: string): string {
  const raw = String(agentId || '').trim()
  if (!raw) return ''
  const hash = raw.lastIndexOf('#')
  if (hash >= 0) {
    const member = raw.slice(hash + 1).trim()
    if (member && member !== 'all') return member
  }
  return raw.replace(/^(team|remote|agent|blueprint):/, '')
}

export function hrefForRunningAgent(agentId: string): string {
  const openId = openIdForRunningAgent(agentId)
  return openId ? agentChatHref(openId) : agentChatHref(agentIdFromBlueprint(agentId))
}

export function labelForRunningAgent(
  agentId: string,
  names: Record<string, string> | undefined,
  fallback?: string,
): string {
  const openId = openIdForRunningAgent(agentId)
  const fromMap = names?.[agentId] || names?.[openId]
  if (fromMap && fromMap.trim()) return fromMap.trim()
  if (fallback && fallback.trim()) return fallback.trim()
  return openId || agentId || 'Agent'
}

function sameAgent(left: string, right: string): boolean {
  if (!left || !right) return false
  if (left === right) return true
  return openIdForRunningAgent(left) === openIdForRunningAgent(right)
}

/**
 * True when `agentId` is this seat or a member lock key of it
 * (`teamId#member`, ADR-017 PR-5). Used to avoid a phantom card for the
 * team while a member turn is already on screen, and to decide whether a
 * card's Stop is this thread's turn.
 */
export function turnBelongsToSeat(agentId: string, seatId: string): boolean {
  const agent = String(agentId || '').trim()
  const seat = String(seatId || '').trim()
  if (!agent || !seat) return false
  if (sameAgent(agent, seat)) return true
  const seatOpen = openIdForRunningAgent(seat)
  if (seatOpen && agent.startsWith(`${seatOpen}#`)) return true
  if (agent.startsWith(`${seat}#`)) return true
  return false
}

/**
 * Cards to render when `parallel_fan_out` is enabled. Empty when the
 * capability is off — the transcript keeps the #1371 working row.
 */
export function runningCardsForDisplay(input: {
  enabled: boolean
  snapshot?: TurnSnapshot | null
  activeAgentId?: string | null
  awaitingAssistant?: boolean
  names?: Record<string, string>
  fallbackName?: string
}): RunningCardModel[] {
  if (!input.enabled) return []
  const snapshot = input.snapshot ?? {}
  const activeId = String(input.activeAgentId || '').trim()
  const seen = new Set<string>()
  const cards: RunningCardModel[] = []

  const push = (turn: { agentId: string; turnId?: string; key?: string }) => {
    const agentId = String(turn.agentId || '').trim()
    if (!agentId) return
    const dedupe = turn.turnId || `agent:${agentId}`
    if (seen.has(dedupe)) return
    seen.add(dedupe)
    const openId = openIdForRunningAgent(agentId)
    const isThisSeat = Boolean(activeId) && sameAgent(agentId, activeId)
    cards.push({
      key: turn.key || turn.turnId || `running-${agentId}`,
      agentId,
      openId,
      turnId: turn.turnId,
      // Fallback is the seat on screen. An unnamed sibling must keep its
      // own id — otherwise every unknown card is labeled as this agent.
      name: labelForRunningAgent(agentId, input.names, isThisSeat ? input.fallbackName : undefined),
      href: hrefForRunningAgent(agentId),
      current: isThisSeat,
    })
  }

  for (const turn of runningTurns(snapshot)) {
    push(turn)
  }

  if (input.awaitingAssistant && activeId) {
    const seatAlreadyRunning = cards.some((card) => turnBelongsToSeat(card.agentId, activeId))
    if (!seatAlreadyRunning) {
      push({
        key: `awaiting-${activeId}`,
        agentId: activeId,
        turnId: undefined,
      })
    }
  }

  return cards
}


export type FanOutLegStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled'

export interface FanOutLeg {
  id: string
  label: string
  status: FanOutLegStatus
  kind?: string
  openId?: string
  href?: string
  batchId?: string
}

const FAN_OUT_STATUSES = new Set<FanOutLegStatus>([
  'queued',
  'running',
  'done',
  'error',
  'cancelled',
])

export function normalizeFanOutStatus(value: string | undefined): FanOutLegStatus {
  const key = String(value || '').trim().toLowerCase()
  if (key === 'completed' || key === 'complete' || key === 'finished') return 'done'
  if (key === 'failed' || key === 'failure') return 'error'
  if (key === 'canceled') return 'cancelled'
  if (FAN_OUT_STATUSES.has(key as FanOutLegStatus)) return key as FanOutLegStatus
  return 'running'
}

export function badgeTextForStatus(status: FanOutLegStatus): string {
  switch (status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Running'
    case 'done':
      return 'Done'
    case 'error':
      return 'Error'
    case 'cancelled':
      return 'Cancelled'
  }
}

export function fanOutStatusIsLive(status: FanOutLegStatus): boolean {
  return status === 'running'
}

export interface FanOutLegFrame {
  id?: string
  label?: string
  status?: string
  legKind?: string
  openId?: string
  href?: string
  batchId?: string
}

/** Fold one server `fan_out_leg` frame. A new batch id replaces the stack. */
export function applyFanOutLeg(legs: FanOutLeg[], frame: FanOutLegFrame): FanOutLeg[] {
  const id = String(frame.id || '').trim()
  if (!id) return legs
  const batchId = String(frame.batchId || '').trim()
  const stale =
    Boolean(batchId) && legs.some((leg) => Boolean(leg.batchId) && leg.batchId !== batchId)
  const base = stale ? [] : legs
  const prev = base.find((leg) => leg.id === id)
  const next: FanOutLeg = {
    id,
    label: String(frame.label || '').trim() || prev?.label || id,
    status: frame.status ? normalizeFanOutStatus(frame.status) : prev?.status || 'queued',
    kind: String(frame.legKind || '').trim() || prev?.kind,
    openId: String(frame.openId || '').trim() || prev?.openId,
    href: String(frame.href || '').trim() || prev?.href,
    batchId: batchId || prev?.batchId,
  }
  if (!prev) return [...base, next]
  return base.map((leg) => (leg.id === id ? next : leg))
}

export interface FanOutCardModel {
  key: string
  legId: string
  name: string
  status: FanOutLegStatus
  badge: string
  live: boolean
  href?: string
  external: boolean
}

/** Local seats open their chat. Remote legs open only a real http(s) href. */
export function destinationForLeg(leg: FanOutLeg): { href: string; external: boolean } | null {
  const href = String(leg.href || '').trim()
  if (/^https?:\/\//i.test(href)) return { href, external: true }
  if ((leg.kind || '') === 'remote') return null
  if ((leg.kind || '') === 'cli') {
    const cli = String(leg.openId || '').trim()
    if (!cli) return null
    return {
      href: `/chat?blueprint=cli_agent&mode=cli&cli=${encodeURIComponent(cli)}`,
      external: false,
    }
  }
  const openId = openIdForRunningAgent(String(leg.openId || leg.id || ''))
  if (!openId) return null
  return { href: hrefForRunningAgent(openId), external: false }
}

/**
 * #1764: optional `excludeSeatIds` drops legs that ARE the seat being talked
 * to (a direct member chat still emits one roster `fan_out_leg`). Sibling
 * legs stay. Matching uses id / openId / openIdForRunningAgent so team lock
 * keys and bare member ids collapse the same way.
 */
export function cardsForFanOutLegs(
  legs: FanOutLeg[] | null | undefined,
  options?: { excludeSeatIds?: Array<string | null | undefined> },
): FanOutCardModel[] {
  if (!legs || legs.length === 0) return []
  const excluded = new Set<string>()
  for (const raw of options?.excludeSeatIds ?? []) {
    const id = String(raw || '').trim()
    if (!id) continue
    excluded.add(id)
    const openId = openIdForRunningAgent(id)
    if (openId) excluded.add(openId)
  }
  return legs
    .filter((leg) => {
      if (excluded.size === 0) return true
      const openId = openIdForRunningAgent(String(leg.openId || leg.id || ''))
      if (excluded.has(leg.id)) return false
      if (leg.openId && excluded.has(String(leg.openId))) return false
      if (openId && excluded.has(openId)) return false
      return true
    })
    .map((leg) => {
      const dest = destinationForLeg(leg)
      return {
        key: leg.batchId ? `${leg.batchId}:${leg.id}` : leg.id,
        legId: leg.id,
        name: leg.label || leg.id,
        status: leg.status,
        badge: badgeTextForStatus(leg.status),
        live: fanOutStatusIsLive(leg.status),
        href: dest?.href,
        external: Boolean(dest?.external),
      }
    })
}
