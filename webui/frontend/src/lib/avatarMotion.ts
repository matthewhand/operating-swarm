/**
 * #819 — Avatar motion abstraction: what each theme looks like *and* how it
 * animates, in one registry.
 *
 * `AvatarMotionProfile` declares idle/active motion, blink behaviour, and
 * gaze tracking per theme. Components read it for behavioural switches; the
 * CSS keyframes it names live in `index.css` under the matching theme block.
 * Robot-pack variants (#822) override the shared robot profile so every body
 * gets its own motion identity instead of one googly wobble for all ten.
 *
 * Pure data + pure functions — no React — so both components and tests can
 * consume it without a renderer.
 */

import type { AvatarTheme, AvatarThemeFamily } from './avatarTheme'

export type AvatarIdleMotion = 'float' | 'breathe' | 'wisp' | 'pulse' | 'none'
export type AvatarActiveMotion =
  | 'eye-wander'
  | 'flutter'
  | 'scanline'
  | 'refract'
  | 'scuttle'
  | 'none'

export interface AvatarBlinkProfile {
  enabled: boolean
  style: 'organic' | 'mechanical' | 'pixel-slit' | 'none'
  /** Random interval bounds between blinks, in ms. */
  intervalRangeMs: [number, number]
  durationMs: number
}

export interface AvatarGazeProfile {
  tracking: 'smooth' | 'stepped' | 'none'
  /** Max pupil travel in SVG units. */
  radius: number
}

export interface AvatarMotionProfile {
  idleMotion: AvatarIdleMotion
  activeMotion: AvatarActiveMotion
  blink: AvatarBlinkProfile
  gaze: AvatarGazeProfile
}

/** Blink profile factory — keeps the registry declarative. */
function blink(
  enabled: boolean,
  style: AvatarBlinkProfile['style'],
  intervalRangeMs: [number, number],
  durationMs = 120,
): AvatarBlinkProfile {
  return { enabled, style, intervalRangeMs, durationMs }
}

/** Shared robot-pack baseline (#819): the classic googly wobble + blink. */
export const ROBOT_PACK_MOTION: AvatarMotionProfile = {
  idleMotion: 'breathe',
  activeMotion: 'eye-wander',
  blink: blink(true, 'mechanical', [2000, 6000]),
  gaze: { tracking: 'smooth', radius: 3.2 },
}

/**
 * Per-theme motion identities. Every installable theme family has an entry;
 * robot-pack variants (#822) refine the baseline below.
 */
export const AVATAR_MOTION_PROFILES: Record<AvatarThemeFamily, AvatarMotionProfile> = {
  bee: {
    // #821: natural sinusoidal hover; wings buzz when active.
    idleMotion: 'float',
    activeMotion: 'flutter',
    blink: blink(true, 'organic', [2500, 5500]),
    gaze: { tracking: 'smooth', radius: 2.4 },
  },
  blobs: {
    idleMotion: 'breathe',
    activeMotion: 'eye-wander',
    blink: blink(true, 'organic', [2600, 6200]),
    gaze: { tracking: 'smooth', radius: 2.6 },
  },
  // #823: the default face becomes a fluid aura orb.
  bland: {
    idleMotion: 'wisp',
    activeMotion: 'refract',
    blink: blink(false, 'none', [0, 0]),
    gaze: { tracking: 'none', radius: 0 },
  },
  robot3d: {
    idleMotion: 'breathe',
    activeMotion: 'eye-wander',
    blink: blink(true, 'mechanical', [2200, 5800]),
    gaze: { tracking: 'smooth', radius: 3.2 },
  },
  robots: ROBOT_PACK_MOTION,
}

/** #822: motion identity per robot-pack body, falling back to the pack baseline. */
const ROBOT_PACK_MOTION_OVERRIDES: Partial<Record<AvatarTheme, AvatarMotionProfile>> = {
  pixel: {
    // Retro stepped motion — discrete jumps, pixel-slit blinks, no smoothing.
    idleMotion: 'pulse',
    activeMotion: 'scuttle',
    blink: blink(true, 'pixel-slit', [1800, 4200], 90),
    gaze: { tracking: 'stepped', radius: 2.6 },
  },
  chassis: {
    // Heavy frame: slow breathing, sweeping visor instead of free pupil travel.
    idleMotion: 'breathe',
    activeMotion: 'scanline',
    blink: blink(true, 'mechanical', [3000, 7000]),
    gaze: { tracking: 'smooth', radius: 1.2 },
  },
  crystal: {
    // Prism shimmer — refractive idle drift, quick internal glints.
    idleMotion: 'wisp',
    activeMotion: 'refract',
    blink: blink(true, 'mechanical', [2800, 6400]),
    gaze: { tracking: 'smooth', radius: 2.2 },
  },
  ghost: {
    idleMotion: 'float',
    activeMotion: 'eye-wander',
    blink: blink(true, 'organic', [2400, 5600]),
    gaze: { tracking: 'smooth', radius: 2.8 },
  },
  orb: {
    idleMotion: 'wisp',
    activeMotion: 'refract',
    blink: blink(false, 'none', [0, 0]),
    gaze: { tracking: 'smooth', radius: 2.0 },
  },
  glyph: {
    idleMotion: 'breathe',
    activeMotion: 'eye-wander',
    blink: blink(true, 'pixel-slit', [2000, 5000], 90),
    gaze: { tracking: 'stepped', radius: 2.4 },
  },
  antenna: {
    idleMotion: 'breathe',
    activeMotion: 'eye-wander',
    blink: blink(true, 'mechanical', [2200, 5400]),
    gaze: { tracking: 'smooth', radius: 3.0 },
  },
  cube: {
    idleMotion: 'none',
    activeMotion: 'eye-wander',
    blink: blink(true, 'pixel-slit', [2400, 5800], 90),
    gaze: { tracking: 'stepped', radius: 2.0 },
  },
  mask: {
    idleMotion: 'none',
    activeMotion: 'scanline',
    blink: blink(false, 'none', [0, 0]),
    gaze: { tracking: 'none', radius: 0 },
  },
  beetle: {
    idleMotion: 'float',
    activeMotion: 'scuttle',
    blink: blink(true, 'organic', [2600, 6000]),
    gaze: { tracking: 'smooth', radius: 2.6 },
  },
}

export function motionProfileForTheme(theme: AvatarTheme): AvatarMotionProfile {
  const family = (
    theme === 'bee' || theme === 'blobs' || theme === 'bland' || theme === 'robot3d'
      ? theme
      : 'robots'
  ) as AvatarThemeFamily
  const override = ROBOT_PACK_MOTION_OVERRIDES[theme]
  return override ?? AVATAR_MOTION_PROFILES[family]
}

/** Seeded per-agent offsets so rail-mates never animate in lockstep. */
export function seededMotionDelays(agentId: string, theme: AvatarTheme): {
  bobDelaySec: number
  blinkDelaySec: number
  wingDelaySec: number
} {
  let h = 2166136261
  const key = `${theme}:${agentId}`
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return {
    bobDelaySec: ((h >>> 3) % 628) / 100,
    blinkDelaySec: ((h >>> 9) % 628) / 100,
    wingDelaySec: ((h >>> 17) % 628) / 100,
  }
}
