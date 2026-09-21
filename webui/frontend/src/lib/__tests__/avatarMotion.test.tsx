/**
 * #819/#821/#822/#823/#791 — avatar motion abstraction + theme identities.
 *
 * Contracts:
 * - The registry covers every installable theme family and every robot-pack
 *   variant; robot packs override the shared baseline (#822).
 * - Bee avatars expose idle-bob, seeded blink and wing-flutter hooks (#821).
 * - The default face renders the fluid aura (palette derived from the agent
 *   color, still declaring the two-dot eye group) (#823).
 * - Waiting agents swap eyes for bouncing dots (#791).
 * - Aura palettes are deterministic per color and hue-related to it (#823).
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AgentAvatar from '../../components/AgentAvatar'
import {
  AVATAR_MOTION_PROFILES,
  ROBOT_PACK_MOTION,
  motionProfileForTheme,
  seededMotionDelays,
} from '../avatarMotion'
import {
  AVATAR_THEMES,
  AVATAR_THEME_FAMILY_IDS,
  INSTALLABLE_AVATAR_THEMES,
} from '../avatarTheme'
import { saveAvatarTheme } from '../avatarTheme'
import { auraPaletteForColor } from '../auraPalette'

describe('avatar motion registry (#819)', () => {
  it('covers every installable theme', () => {
    for (const theme of INSTALLABLE_AVATAR_THEMES) {
      const profile = motionProfileForTheme(theme.id)
      expect(profile).toBeTruthy()
      expect(AVATAR_THEMES).toContain(theme.id)
    }
  })

  it('covers every theme family', () => {
    for (const family of AVATAR_THEME_FAMILY_IDS) {
      expect(AVATAR_MOTION_PROFILES[family]).toBeTruthy()
    }
  })

  it('gives the bee float/flutter with organic blink (#821)', () => {
    const bee = motionProfileForTheme('bee')
    expect(bee.idleMotion).toBe('float')
    expect(bee.activeMotion).toBe('flutter')
    expect(bee.blink.enabled).toBe(true)
    expect(bee.blink.style).toBe('organic')
    expect(bee.blink.intervalRangeMs[0]).toBeGreaterThanOrEqual(2500)
    expect(bee.blink.intervalRangeMs[1]).toBeLessThanOrEqual(5500)
  })

  it('gives robot packs their own identities, not one shared wobble (#822)', () => {
    const pixel = motionProfileForTheme('pixel')
    const chassis = motionProfileForTheme('chassis')
    const crystal = motionProfileForTheme('crystal')
    expect(pixel.gaze.tracking).toBe('stepped')
    expect(pixel.blink.style).toBe('pixel-slit')
    expect(chassis.activeMotion).toBe('scanline')
    expect(crystal.idleMotion).toBe('wisp')
    // Overrides differ from the shared pack baseline.
    expect(pixel).not.toEqual(ROBOT_PACK_MOTION)
    expect(chassis).not.toEqual(ROBOT_PACK_MOTION)
  })

  it('seeds per-agent delays so rail-mates do not animate in lockstep', () => {
    const a = seededMotionDelays('agent-a', 'bee')
    const b = seededMotionDelays('agent-b', 'bee')
    expect(a).not.toEqual(b)
    expect(seededMotionDelays('agent-a', 'bee')).toEqual(a) // stable
  })
})

describe('aura palette (#823)', () => {
  it('is deterministic per color', () => {
    expect(auraPaletteForColor('#6366f1')).toEqual(auraPaletteForColor('#6366f1'))
  })

  it('falls back sanely for missing colors', () => {
    const fallback = auraPaletteForColor(undefined)
    expect(fallback.blobs).toHaveLength(3)
    expect(fallback.base).toContain('hsl')
  })
})

describe('default avatar fluid aura + waiting dots (#823/#791)', () => {
  it('renders aura layers and keeps the two-dot eye group', () => {
    saveAvatarTheme('bland')
    render(<AgentAvatar agentId="codey" alt="Codey" />)
    const svg = document.querySelector('svg[data-avatar-theme="bland"]')
    expect(svg).toBeTruthy()
    expect(svg?.querySelectorAll('.os-aura-blob')).toHaveLength(3)
    expect(svg?.querySelector('.os-aura-glow')).toBeTruthy()
    expect(svg?.querySelectorAll('.os-bland-eyes circle')).toHaveLength(2)
  })

  it('swaps eyes for bouncing dots while waiting (#791)', () => {
    saveAvatarTheme('bland')
    const { rerender } = render(<AgentAvatar agentId="codey" active={false} />)
    expect(screen.queryByTestId('avatar-waiting-dots')).toBeNull()

    rerender(<AgentAvatar agentId="codey" active />)
    const dots = screen.getByTestId('avatar-waiting-dots')
    expect(dots.querySelectorAll('span')).toHaveLength(3)
  })
})
