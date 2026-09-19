/**
 * #691 — the role badge/pill on pinned avatar tiles anchors to the LEFT
 * corner (top-left), not the right. #579 pinned "corner placement" as a CSS
 * contract; this ticket flips the corner.
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

  it('hover hint still takes the corner; the badge yields to its right', () => {
    expect(css).toMatch(
      /\.os-fav-tile:hover:has\(\.os-fav-tile__shortcut\) \.os-fav-tile__badge \{[^}]*left:\s*1\.6rem/,
    )
  })
})
