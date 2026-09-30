/**
 * #1261 — the sidepane reserved scrollbar-gutter padding was permanent.
 *
 * Before this fix the rail compensated for the scrollbar by reserving a
 * hand-tuned `--os-rail-gutter` padding on `.os-fav-grid` / `.os-hidden-bots`.
 * That padding was always present, so the rail had dead space even when the
 * content fit, and it never shift-compensated when the scrollbar appeared.
 *
 * The contract is now: the scroll *container* (`.os-rail-scroller`) reserves
 * the gutter itself with `scrollbar-gutter: stable`, and the manual padding is
 * gone. Avatar-only mode (the narrowest rail) reclaims the gutter.
 *
 * jsdom does not compute layout (it cannot tell us whether a scrollbar is
 * present or how wide it is), so this test asserts the *stylesheet hook* the
 * fix keys off — the `scrollbar-gutter` declaration on the scroll container
 * and the absence of the compensating padding — rather than computed widths.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')

/** Rule body for an exact selector, up to its closing brace. */
function ruleBody(selector: string): string {
  const start = css.indexOf(selector)
  expect(start, `expected index.css to declare ${selector}`).toBeGreaterThanOrEqual(0)
  return css.slice(start, css.indexOf('}', start))
}

describe('#1261 scrollbar gutter lives on the scroll container', () => {
  it('.os-rail-scroller reserves the gutter with scrollbar-gutter: stable', () => {
    // The rail body is the element with `overflow-y-auto`; reserving the
    // gutter here (not as row padding) is what absorbs the scrollbar without
    // a horizontal jump and without dead space when the rail fits.
    expect(ruleBody('.os-rail-scroller {')).toMatch(/scrollbar-gutter:\s*stable/)
  })

  it('the manual reserved-gutter padding token is gone', () => {
    // The dead-space source: a permanent reserved gutter that never
    // compensated. Removing the token removes the permanent pad.
    expect(css).not.toMatch(/--os-rail-gutter:/)
  })

  it('.os-fav-grid no longer pads its right edge for a reserved gutter', () => {
    expect(ruleBody('.os-fav-grid {')).not.toMatch(
      /padding-right:\s*var\(--os-rail-gutter\)/,
    )
  })

  it('.os-hidden-bots no longer carries a gutter-compensating right margin', () => {
    expect(ruleBody('.os-hidden-bots {')).not.toMatch(
      /margin-right:\s*calc\(0\.5rem \+ var\(--os-rail-gutter/,
    )
  })

  it('avatar-only mode reclaims the gutter on the scroll container', () => {
    // Narrowest rail (68–96px): a reserved classic scrollbar gutter is a large
    // slice of the pane, so it is reclaimed — the scrollbar hides instead.
    const start = css.indexOf('.os-agent-sidebar--avatar-only')
    expect(start).toBeGreaterThanOrEqual(0)
    const avatarOnly = css.slice(start)
    expect(avatarOnly).toMatch(
      /\.os-agent-sidebar--avatar-only\s+\.os-rail-scroller\s*\{[^}]*scrollbar-gutter:\s*auto/,
    )
  })

  it('no rail content region carries a permanent gutter pad or margin', () => {
    // The bug: a reserved pad that never compensated, so rows jumped when the
    // scrollbar appeared and dead space stayed when it did not. No row/region
    // may reintroduce a hand-tuned gutter offset.
    expect(css).not.toMatch(/padding-right:\s*var\(--os-rail-gutter/)
    expect(css).not.toMatch(/margin-right:\s*calc\([^)]*--os-rail-gutter/)
    expect(ruleBody('.os-agent-row {')).not.toMatch(/--os-rail-gutter/)
  })

  it('the gutter hook is a single stable reservation on the scroll container', () => {
    // Exactly one `scrollbar-gutter` reservation declaration, and it lives on
    // the scroller — nothing else reserves a gutter that could desync from it.
    const declarations =
      css.match(/^\s*scrollbar-gutter:\s*(?:stable|auto|both-edges)\s*;/gm) ?? []
    expect(declarations.map((d) => d.trim())).toEqual([
      'scrollbar-gutter: stable;',
      'scrollbar-gutter: auto;',
    ])
  })
})
