import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

/**
 * #1194 — ultra-compact (avatar-only) rail: pinned tiles keep their label-era
 * vertical spend even though the labels are `display:none`. The dead space
 * comes from the *grid* (4.75rem floor stretches every row) and the *tile*
 * (3rem face + block padding sized for avatar + two-line label), not from the
 * hidden labels themselves.
 *
 * Contracts, all scoped to `.os-agent-sidebar--avatar-only` so expanded-mode
 * geometry is untouched:
 * 1. the pinned grid loses its `min-height: 4.75rem` floor;
 * 2. the tile hugs its face — no inherited two-line-label min-height, tight
 *    block padding, centered contents;
 * 3. the pinned face is sized for the #1146 row rhythm (2.25rem), not the
 *    3rem label-era square.
 */
describe('#1194: ultra-compact pinned tiles drop the label-era height', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

  it('drops the pinned-grid min-height floor in avatar-only mode', () => {
    const match = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-fav-grid\s*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    // The floor is what stretches each grid row to 76px around a ~59px tile.
    expect(match![1]).toMatch(/min-height:\s*auto/)
    expect(match![1]).not.toMatch(/min-height:\s*4\.75rem/)
  })

  it('makes the pinned tile hug its face (no label-era min-height/padding)', () => {
    const match = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-fav-tile\s*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    // #1074 already resets width/min-height; #1194 also kills the vertical
    // padding (0.35rem block) and pins the height to the #1146 row rhythm.
    expect(match![1]).toMatch(/min-height:\s*auto/)
    expect(match![1]).toMatch(/padding:\s*0/)
    expect(match![1]).toMatch(/height:\s*2\.25rem/)
    expect(match![1]).toMatch(/justify-content:\s*center/)
  })

  it('sizes the pinned face to the compact rhythm instead of the 3rem square', () => {
    const match = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-fav-tile\s+\.os-agent-avatar--lg[^{]*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    // 2.25rem face inside the 2.25rem tile = the tile is exactly the avatar.
    expect(match![1]).toMatch(/width:\s*2\.25rem/)
    expect(match![1]).toMatch(/height:\s*2\.25rem/)
  })
})
