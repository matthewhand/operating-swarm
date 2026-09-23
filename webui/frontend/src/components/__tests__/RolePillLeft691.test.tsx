/**
 * #691 — the role badge/pill on pinned avatar tiles anchors to the LEFT
 * corner (top-left), not the right. #579 pinned "corner placement" as a CSS
 * contract; this ticket flips the corner.
 *
 * #713 — and it STAYS put on hover. The `left: 1.6rem` hover slide is a #579
 * relic from when the badge lived in the top-RIGHT corner and had to clear
 * the ⌥N hint; with a left-anchored badge the hint owns the opposite corner,
 * so the slide just shoves the pill toward the tile's centre (measured live:
 * x 23 → 45 on a 104px tile — reads as "the role centres for some reason").
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#691 pinned tile role badge sits left', () => {
  const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

  it('anchors the tile badge to the left edge', () => {
    const block = css.match(/\.os-fav-tile__badge \{[^}]*\}/)?.[0] ?? ''
    expect(block).toContain('left: 0.2rem')
    expect(block).not.toMatch(/right:\s*0\.2rem/)
  })

  it('#713: hover never moves the badge — no slide rule may exist', () => {
    expect(css).not.toMatch(
      /\.os-fav-tile:hover[^{]*\.os-fav-tile__badge\s*\{[^}]*left:/,
    )
  })

  it('#713: the badge animates the properties it actually has (left, not right)', () => {
    const block = css.match(/\.os-fav-tile__badge \{[^}]*\}/)?.[0] ?? ''
    expect(block).not.toMatch(/transition:[^;]*\bright\b/)
  })
})
