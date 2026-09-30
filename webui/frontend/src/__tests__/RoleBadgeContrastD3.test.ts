/**
 * D3 (#a11y): role-badge foregrounds are small text (0.55–0.62rem) and must
 * clear WCAG AA 4.5:1 against the badge surface. That surface is
 * `color-mix(in srgb, var(--color-base-content) 8%, transparent)` over the
 * pane behind the badge.
 *
 * The default theme is dark. A single solid colour cannot clear 4.5:1 on
 * both the lightest dark pane (active rail) and the darkest light pane
 * (hovered/active pin). Unscoped rules are the dark-theme colours; rules
 * under `[data-theme="light"]` are the light-theme colours. This test
 * derives those panes from the tokens in index.css, so a hue tweak or a
 * token change that drops a role under 4.5:1 fails here.
 *
 * Role colour lives only on `.os-agent-role-badge` (AGENTS.md).
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const CSS_PATH = path.resolve(__dirname, '../index.css')
const AA_SMALL_TEXT = 4.5

type RGB = { r: number; g: number; b: number }

function parseHex(hex: string): RGB {
  const value = hex.trim().replace(/^#/, '')
  const full =
    value.length === 3
      ? value
          .split('')
          .map((c) => c + c)
          .join('')
      : value
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  }
}

function channelLuminance(channel: number): number {
  const c = channel / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function relativeLuminance({ r, g, b }: RGB): number {
  return (
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)
  )
}

function contrastRatio(fg: RGB, bg: RGB): number {
  const l1 = relativeLuminance(fg)
  const l2 = relativeLuminance(bg)
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1]
  return (hi + 0.05) / (lo + 0.05)
}

/** `color-mix(in srgb, fg pct%, transparent)` composited over an opaque pane. */
function veil(fg: RGB, bg: RGB, amount: number): RGB {
  return {
    r: Math.round(fg.r * amount + bg.r * (1 - amount)),
    g: Math.round(fg.g * amount + bg.g * (1 - amount)),
    b: Math.round(fg.b * amount + bg.b * (1 - amount)),
  }
}

function themeBlock(css: string, name: string): string {
  const marker = `name: "${name}"`
  const start = css.indexOf(marker)
  expect(start, `missing daisyui theme "${name}"`).toBeGreaterThan(-1)
  const end = css.indexOf('}', start)
  return css.slice(start, end)
}

function hexDecl(css: string, prop: string): string {
  const match = css.match(new RegExp(`${prop}:\\s*(#[0-9a-fA-F]{6})`))
  expect(match, `missing ${prop}`).not.toBeNull()
  return match![1]
}

function mixPercent(css: string, selector: string, property: string): number {
  const pattern = new RegExp(
    `${property}:\\s*color-mix\\(\\s*in\\s+srgb\\s*,\\s*var\\(--color-[a-z0-9-]+\\)\\s+(\\d+)%`,
    'i',
  )
  let from = 0
  while (from < css.length) {
    const at = css.indexOf(selector, from)
    if (at === -1) break
    const open = css.indexOf('{', at)
    const close = css.indexOf('}', open)
    const body = css.slice(open, close)
    const match = body.match(pattern)
    if (match) return Number(match[1]) / 100
    from = close + 1
  }
  throw new Error(`missing ${property} color-mix percent in ${selector}`)
}

type BadgeColor = { dark: string; light: string }

/** The colour a badge attribute declares, split by theme. */
function badgeColor(css: string, attribute: string, value: string): BadgeColor {
  const needle = `.os-agent-role-badge[${attribute}="${value}"]`
  let dark: string | null = null
  let light: string | null = null
  let from = 0
  while (from < css.length) {
    const at = css.indexOf(needle, from)
    if (at === -1) break
    const open = css.indexOf('{', at)
    const close = css.indexOf('}', open)
    const selector = css.slice(css.lastIndexOf('}', at) + 1, open)
    const body = css.slice(open + 1, close)
    const match = body.match(/color:\s*(#[0-9a-fA-F]{6})/)
    if (match) {
      const isLight = selector.includes('[data-theme="light"]')
      if (isLight) light = match[1].toLowerCase()
      else dark = match[1].toLowerCase()
    }
    from = close + 1
  }
  expect(dark, `missing dark-theme colour for ${needle}`).not.toBeNull()
  expect(light, `missing light-theme colour for ${needle}`).not.toBeNull()
  return { dark: dark!, light: light! }
}

describe('D3: role-badge contrast (WCAG AA, small text)', () => {
  const css = fs.readFileSync(CSS_PATH, 'utf-8')
  const darkContent = parseHex(hexDecl(themeBlock(css, 'dark'), '--color-base-content'))
  const lightContent = parseHex(hexDecl(themeBlock(css, 'light'), '--color-base-content'))
  const lightBase300 = parseHex(hexDecl(themeBlock(css, 'light'), '--color-base-300'))
  const tileSelected = parseHex(hexDecl(css, '--os-grok-tile-selected'))
  const root = css.slice(css.indexOf(':root'), css.indexOf('}', css.indexOf(':root')))
  const darkRail = parseHex(hexDecl(root, '--os-chrome-sidebar'))
  const lightScope = css.slice(css.indexOf('[data-theme="light"]'))
  const lightRail = parseHex(hexDecl(lightScope, '--os-chrome-sidebar'))
  const badgeAlpha = mixPercent(css, '.os-agent-role-badge {', 'background')
  const pinAlpha = mixPercent(css, '.os-fav-tile:hover,', 'background')
  const activeAlpha = mixPercent(css, '.os-agent-row--active {', 'background')

  // Light text fails first on the lightest dark pane; dark text fails first
  // on the darkest light pane. Take the worse of the rail, the active row,
  // and a hovered/active pin.
  const darkSurfaces = [
    veil(darkContent, tileSelected, badgeAlpha),
    veil(darkContent, darkRail, badgeAlpha),
    veil(darkContent, veil(darkContent, darkRail, pinAlpha), badgeAlpha),
  ]
  const lightSurfaces = [
    veil(lightContent, lightRail, badgeAlpha),
    veil(lightContent, veil(lightBase300, lightRail, activeAlpha), badgeAlpha),
    veil(lightContent, veil(lightContent, lightRail, pinAlpha), badgeAlpha),
  ]
  const darkWorst = darkSurfaces.reduce((worst, surface) =>
    relativeLuminance(surface) > relativeLuminance(worst) ? surface : worst,
  )
  const lightWorst = lightSurfaces.reduce((worst, surface) =>
    relativeLuminance(surface) < relativeLuminance(worst) ? surface : worst,
  )

  const roles = [
    'support',
    'admin',
    'gate',
    'belay',
    'skeptic',
    'advisor',
    'chief_of_staff',
    'suggestions',
    'engineer',
  ] as const
  const kinds = ['team', 'remote'] as const

  it.each(roles)('role %s clears 4.5:1 on the dark and light badge surfaces', (role) => {
    const colors = badgeColor(css, 'data-role', role)
    const darkRatio = contrastRatio(parseHex(colors.dark), darkWorst)
    const lightRatio = contrastRatio(parseHex(colors.light), lightWorst)
    expect(darkRatio, `dark ${role} ${colors.dark} is ${darkRatio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      AA_SMALL_TEXT,
    )
    expect(lightRatio, `light ${role} ${colors.light} is ${lightRatio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      AA_SMALL_TEXT,
    )
    expect(colors.dark, `${role} needs a different colour per theme`).not.toBe(colors.light)
  })

  it.each(kinds)('kind %s clears 4.5:1 on the dark and light badge surfaces', (kind) => {
    const colors = badgeColor(css, 'data-kind', kind)
    const darkRatio = contrastRatio(parseHex(colors.dark), darkWorst)
    const lightRatio = contrastRatio(parseHex(colors.light), lightWorst)
    expect(darkRatio, `dark ${kind} ${colors.dark} is ${darkRatio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      AA_SMALL_TEXT,
    )
    expect(lightRatio, `light ${kind} ${colors.light} is ${lightRatio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      AA_SMALL_TEXT,
    )
  })

  it('keeps an uncoloured badge readable via the base-content mix', () => {
    const at = css.indexOf('.os-agent-role-badge {')
    const body = css.slice(at, css.indexOf('}', at))
    const match = body.match(/color:\s*color-mix\(\s*in\s+srgb\s*,\s*var\(--color-base-content\)\s+(\d+)%/i)
    expect(match, 'base badge colour should stay a base-content mix').not.toBeNull()
    const amount = Number(match![1]) / 100
    const darkFg = veil(darkContent, darkWorst, amount)
    const lightFg = veil(lightContent, lightWorst, amount)
    expect(contrastRatio(darkFg, darkWorst)).toBeGreaterThanOrEqual(AA_SMALL_TEXT)
    expect(contrastRatio(lightFg, lightWorst)).toBeGreaterThanOrEqual(AA_SMALL_TEXT)
  })

  it('keeps the palette distinct per role within each theme', () => {
    const dark = new Map<string, string>()
    const light = new Map<string, string>()
    for (const role of roles) {
      const colors = badgeColor(css, 'data-role', role)
      dark.set(role, colors.dark)
      light.set(role, colors.light)
    }
    // gate and belay are aliases and share a hue on purpose.
    expect(dark.get('gate')).toBe(dark.get('belay'))
    expect(light.get('gate')).toBe(light.get('belay'))
    for (const hues of [dark, light]) {
      const distinct = new Set(
        roles.filter((role) => role !== 'belay').map((role) => hues.get(role)),
      )
      expect(distinct.size).toBe(roles.length - 1)
    }
  })
})
