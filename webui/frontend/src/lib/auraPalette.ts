/**
 * #823 — Agent-harmonic palettes for the default fluid aura orb.
 *
 * Given the agent's base color, derive 3 accent hues (plus a deep base) that
 * read as one family: complementary/analogous neighbours with electric
 * saturation. Deterministic per color, so an agent's orb is stable across
 * renders without storing anything.
 *
 * HSL circle neighbours:
 *   hsl(h, s, l) → hsl((h + shift) % 360, s', l')
 */

export interface AuraPalette {
  /** Deep core behind the blobs. */
  base: string
  /** Orbiting chromatic hotspots. */
  blobs: [string, string, string]
  /** Perimeter caustic glow. */
  glow: string
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value))
}

function hexToHsl(hex: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  const raw = m ? m[1] : '6366f1'
  const r = parseInt(raw.slice(0, 2), 16) / 255
  const g = parseInt(raw.slice(2, 4), 16) / 255
  const b = parseInt(raw.slice(4, 6), 16) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h: number
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60
  else if (max === g) h = ((b - r) / d + 2) * 60
  else h = ((r - g) / d + 4) * 60
  return [h, s, l]
}

function hslCss(h: number, s: number, l: number): string {
  const hue = (((h % 360) + 360) % 360).toFixed(1)
  const sat = clamp(s, 0, 1).toFixed(2)
  const light = clamp(l, 0, 1).toFixed(2)
  return `hsl(${hue} ${sat} ${light})`
}

/**
 * Build the orb palette. Accent hue shifts stay in the ±40–200° band so the
 * result is always funky-but-related to the agent color, never random.
 */
export function auraPaletteForColor(color: string | undefined | null): AuraPalette {
  const [h, s, l] = hexToHsl(color || '#6366f1')
  const sat = clamp(s < 0.25 ? 0.55 : s, 0, 1)
  return {
    base: hslCss(h, sat, clamp(l * 0.32, 0.1, 0.22)),
    blobs: [
      hslCss(h + 46, Math.min(1, sat + 0.2), clamp(l + 0.16, 0.45, 0.72)),
      hslCss(h + 168, Math.min(1, sat + 0.28), clamp(l + 0.08, 0.42, 0.66)),
      hslCss(h - 38, Math.min(1, sat + 0.24), clamp(l + 0.2, 0.5, 0.74)),
    ],
    glow: hslCss(h + 120, Math.min(1, sat + 0.15), clamp(l + 0.26, 0.55, 0.8)),
  }
}
