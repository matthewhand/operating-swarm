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

/** Team stacks show every member up to this count — no +N chip (#57). */
export const TEAM_STACK_ALL_MAX = 3

/** #523: the pinned team tile's front-face size in px. #639: 48 so the wide
 * rail's 80/20 layout (large face + mini row) keeps faces readable. */
export const PIN_STACK_BASE_PX = 48

/** #523: the size step per depth behind the front face. */
export const PIN_STACK_STEP_PX = 6

/** #523: chat stacking preference — the idle ordering for pinned team stacks. */
export type StackOrderPreference = 'first' | 'last'

/**
 * #523: order the pin's faces most-recently-active first. With no activity
 * (every `startedAt` at/below 0) fall back to the chat stacking preference:
 * `first` keeps roster order, `last` reverses it. Non-mutating.
 */
export function orderedFacesByRecency<T extends StackFace>(
  faces: readonly T[],
  preference: StackOrderPreference = 'first',
): T[] {
  const hasActivity = faces.some((face) => face.startedAt > 0)
  if (!hasActivity) {
    return preference === 'last' ? [...faces].reverse() : [...faces]
  }
  return [...faces].sort((a, b) => b.startedAt - a.startedAt)
}

/**
 * #523: graduated sizes for a pinned team stack — front face is
 * {@link PIN_STACK_BASE_PX}, each depth behind steps down by
 * {@link PIN_STACK_STEP_PX}, never below 12px so faces stay readable.
 */
export function pinStackSizes(count: number): number[] {
  const sizes: number[] = []
  for (let depth = 0; depth < count; depth += 1) {
    sizes.push(Math.max(12, PIN_STACK_BASE_PX - depth * PIN_STACK_STEP_PX))
  }
  return sizes
}

/**
 * Team **ordering** helper (#458): while any member is working, order faces
 * most-recently-active first; when idle, preserve stable roster order.
 *
 * #438 moved the rail off fanning a team into overlapping faces — it now shows
 * one face plus a `+N` via {@link teamChatFaceStack}. This helper is still the
 * owner of the *ordering* rule, so callers that need a list (the member
 * sessions picker, and `teamChatFaceStack`'s default when no chat target is
 * supplied) sort through it rather than re-deriving the rule.
 */
export function teamSidepaneStack<T extends StackFace>(
  faces: readonly T[],
  anyWorking?: boolean,
): { faces: T[]; remainder: number } {
  const isWorking = anyWorking !== undefined ? anyWorking : faces.some((face) => Boolean(face.working))
  const all = [...faces]
  const ordered = isWorking
    ? all.sort((a, b) => {
        if (b.startedAt !== a.startedAt) return b.startedAt - a.startedAt
        return 0
      })
    : all
  return {
    faces: ordered.slice(0, STACK_FACE_LIMIT),
    remainder: 0,
  }
}

/**
 * #438: the team's **rail face** — the member the operator will actually chat
 * with, plus a `+N` for everyone else.
 *
 * The rail used to fan a team into overlapping faces: all of them for 1–3
 * members (`TEAM_STACK_ALL_MAX`) and `2 faces + +(n-2)` for 4+. At rail sizes a
 * pinned 3-member team rendered as overlapping slivers that were not
 * individually readable (Live Demo Team read as a red blob with extra marks),
 * and the row's job is not to enumerate the roster — it is to say *who you are
 * talking to* and *how many others there are*.
 *
 * `chatTargetId` is the team's default talk-to member, or the navbar's current
 * member when one is targeted specifically. If it names nobody in `faces` (a
 * stale id, or a roster read that has not settled) the first face is used rather
 * than inventing one — see `#438`'s "do not invent members".
 *
 * Remainder is `max(0, faces.length - 1)`: a one-member team has no `+N`.
 */
export function teamChatFaceStack<T extends StackFace>(
  faces: readonly T[],
  chatTargetId?: string | null,
): { face: T | null; remainder: number } {
  const target = (chatTargetId ?? '').trim()
  const face =
    (target ? faces.find((item) => item.id === target || item.agentId === target) : undefined) ??
    faces[0] ??
    null
  return { face, remainder: Math.max(0, faces.length - 1) }
}

/** #639: how many recency faces the wide rail shows beside/behind the face. */
export const RAIL_TEAM_MINI_FACES = 3

/** #639: faces per team row when the rail is collapsed to avatar width. */
export const RAIL_TEAM_COLLAPSED_FACES = 1

/**
 * #639 (REQ-909): width-adaptive team rail stack.
 *
 * Collapsed rail (`isAvatarOnly`): exactly one face — the team's most recently
 * active member (`orderedFacesByRecency`, roster order when idle). Wide rail:
 * `RAIL_TEAM_MINI_FACES` recency faces at graduated sizes beside/behind the
 * large face; the large face itself stays the chat target.
 *
 * Faces come pre-marked (`working` set by the caller); ordering is the same
 * recency rule the #523 pin stack uses.
 */
export function railTeamStackLayout(
  faces: readonly StackFace[],
  collapsed: boolean,
): { faces: StackFace[]; count: number; collapsed: boolean } {
  const ordered = orderedFacesByRecency(faces)
  if (collapsed) {
    return {
      faces: ordered.slice(0, RAIL_TEAM_COLLAPSED_FACES),
      count: RAIL_TEAM_COLLAPSED_FACES,
      collapsed,
    }
  }
  return {
    faces: ordered.slice(0, RAIL_TEAM_MINI_FACES),
    count: RAIL_TEAM_MINI_FACES,
    collapsed,
  }
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

/** Overlay live run-state onto stacked faces (pinned team workers, #432). */
export function markStackWorking<T extends StackFace>(
  faces: readonly T[],
  isRunning: (id: string) => boolean,
): { faces: T[]; anyWorking: boolean } {
  const next = faces.map((face) => {
    const ids = [face.id, face.agentId].filter((id): id is string => Boolean(id))
    const working = Boolean(face.working) || ids.some((id) => isRunning(id))
    return { ...face, working }
  })
  return { faces: next, anyWorking: next.some((face) => face.working) }
}
