/**
 * Shared stacked-avatar math (REQ-66 #394).
 *
 * One rail row shows at most {@link STACK_FACE_LIMIT} faces plus a +N
 * remainder. Every face animates; phase is staggered from `startedAt`
 * so the stack does not pulse in lockstep.
 *
 * #398 (teams / remotes) should import these helpers and `AvatarStack`.
 * This module is domain-agnostic: do not put session, team, or remote
 * catalog logic here.
 */

/** Rail stack shows this many faces; extras become a +N remainder. */
export const STACK_FACE_LIMIT = 3

/** Team rail stacks show this many faces; extras become a +N remainder. */
export const TEAM_STACK_FACE_LIMIT = 2

/** Team stacks show every member up to this count — no +N chip. */
export const TEAM_STACK_ALL_MAX = 4

/**
 * Team sidepane stack plan (Matthew's rule): a roster of 4 or fewer shows
 * every member with no remainder; a crowded roster (>4) collapses to the
 * first 2 members plus a +N chip. Roster order is preserved — unlike
 * {@link selectStackedFaces} this does not re-sort by recency, because a
 * team roster is a stable list, not an activity feed.
 */
export function teamSidepaneStack<T extends StackFace>(
  faces: readonly T[],
): { faces: T[]; remainder: number } {
  const all = [...faces]
  if (all.length <= TEAM_STACK_ALL_MAX) return { faces: all, remainder: 0 }
  return { faces: all.slice(0, TEAM_STACK_FACE_LIMIT), remainder: all.length - TEAM_STACK_FACE_LIMIT }
}

/** Matches `.os-scale-out-pulse` / `.os-stacked-avatar--pulse` (1.4s). */
export const STACK_PULSE_MS = 1400

export interface StackFace {
  id: string
  /** Agent to theme when this face is clicked (REQ-840). Defaults to `id`. */
  agentId?: string
  name?: string
  /** Epoch ms used to stagger animation-delay. */
  startedAt: number
  /** Color-hash key; defaults to `id`. */
  markId?: string
  role?: string
  working?: boolean
  avatarSrc?: string | null
  src?: string | null
}

export interface StackSelection<T extends StackFace = StackFace> {
  faces: T[]
  remainder: number
  delaysMs: number[]
}

/**
 * Phase offset for the shared pulse. Different `startedAt` values land on
 * different points in the loop so stacked faces do not lockstep.
 */
export function stackAnimationDelayMs(
  startedAt: number,
  origin = 0,
  periodMs = STACK_PULSE_MS,
): number {
  const period = periodMs > 0 ? periodMs : STACK_PULSE_MS
  const delta = startedAt - origin
  return ((delta % period) + period) % period
}

export function earliestStartedAt(faces: ReadonlyArray<{ startedAt: number }>): number {
  if (faces.length === 0) return 0
  return faces.reduce((min, face) => Math.min(min, face.startedAt), faces[0]!.startedAt)
}

/** Epoch ms from a number, ISO/date string, or a stable fallback index. */
export function parseStartedAt(value: unknown, fallbackIndex = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) return parsed
    const asNum = Number(value)
    if (Number.isFinite(asNum)) return asNum
  }
  return fallbackIndex
}

/**
 * Most recent `maxFaces` by `startedAt`, plus remainder.
 * Callers that need a different order (e.g. running-first) should pass
 * a pre-sliced list plus an explicit remainder to `AvatarStack`.
 */
export function selectStackedFaces<T extends StackFace>(
  faces: readonly T[],
  maxFaces = STACK_FACE_LIMIT,
): StackSelection<T> {
  const cap = Math.max(0, maxFaces)
  const sorted = [...faces].sort((a, b) => {
    if (b.startedAt !== a.startedAt) return b.startedAt - a.startedAt
    return a.id.localeCompare(b.id)
  })
  const visible = sorted.slice(0, cap)
  const origin = earliestStartedAt(visible)
  return {
    faces: visible,
    remainder: Math.max(0, faces.length - visible.length),
    delaysMs: visible.map((face) => stackAnimationDelayMs(face.startedAt, origin)),
  }
}

/** A single face is not a stack (no overlap, no remainder chip). */
export function isAvatarStack(faceCount: number, remainder = 0): boolean {
  return faceCount > 1 || remainder > 0
}
