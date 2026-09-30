import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

/**
 * #1648 — circular Search at the one-column pinned-grid detent.
 *
 * The rail is `container-type: inline-size`, so the one-col chrome is keyed
 * on a container query rather than a class toggle. These are CSS-contract
 * assertions (repo pattern: AddAgentButtonHeight.test.tsx): the container
 * block must mirror the ultra-compact circle rules, and the bounds must
 * agree with lib/railResize.ts's ONE_COL_RAIL_WIDTH so a drag-detent change
 * cannot silently desync the chrome.
 */
describe('#1648 one-column circular Search chrome', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')

  it('mirrors the ultra-compact circle rules in a 1-col container query', () => {
    // Extract the #1648 container block.
    const blockMatch = css.match(
      /\/\* #1648:[^*]*\*\/\s*@container \(max-width: 118px\) \{([\s\S]*?)\n\}/,
    )
    expect(blockMatch).not.toBeNull()
    const block = blockMatch![1]

    // Search control becomes a 2.25rem circle, padding collapses, icon centred.
    expect(block).toMatch(/\.os-rail-search\s*\{[^}]*?padding:\s*0;/)
    expect(block).toMatch(/\.os-rail-search\s*\{[^}]*?width:\s*2\.25rem;/)
    expect(block).toMatch(/\.os-rail-search\s*\{[^}]*?height:\s*2\.25rem;/)
    expect(block).toMatch(/\.os-rail-search\s*\{[^}]*?border-radius:\s*999px;/)
    // No visible text input or kbd hint at one column.
    expect(block).toMatch(/\.os-rail-search__input,\s*\n\s*\.os-agent-sidebar \.os-rail-search__kbd\s*\{[^}]*?display:\s*none;/)
  })

  it('keeps the expanded search row intact at two or more columns', () => {
    // The base (non-container) rule keeps the full-height pill row.
    expect(css).toMatch(/\.os-rail-search\s*\{[^}]*?height:\s*2\.25rem;\s*\n\s*padding:\s*0 0\.75rem;/)
    // The one-col bound must be strictly below the two-column detent width
    // (210px): otherwise 2-col rails would collapse the row too.
    const bound = Number(css.match(/@container \(max-width: (\d+)px\) \{[\s\S]*?#1648/)?.[1])
    expect(bound).toBeGreaterThan(0)
    expect(bound).toBeLessThan(210)
  })

  it('container bound matches railResize ONE_COL_RAIL_WIDTH (118px)', () => {
    const railResize = fs.readFileSync(
      path.resolve(__dirname, '../../lib/railResize.ts'),
      'utf-8',
    )
    // Guard the geometry chain: 84 track + 24 margin + 10 chrome = 118.
    expect(railResize).toContain('export const FAV_TILE_TRACK_PX = 84')
    expect(railResize).toContain('export const FAV_GRID_GAP_PX = 8')
    expect(railResize).toContain('export const FAV_GRID_MARGIN_PX = 24')
    expect(railResize).toContain('export const RAIL_CHROME_PX = 10')
    expect(railResize).toMatch(/ONE_COL_RAIL_WIDTH = railWidthForColumns\(1\)/)
  })
})
