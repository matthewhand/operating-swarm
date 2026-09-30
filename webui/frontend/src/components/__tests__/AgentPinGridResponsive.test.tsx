import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('REQ-206: Pinned grid columns adapt to sidepane width (1 / 2 / 3)', () => {
  const cssPath = path.resolve(__dirname, '../../index.css')
  const cssContent = fs.readFileSync(cssPath, 'utf-8')

  it('declares container-type: inline-size on .os-agent-sidebar', () => {
    expect(cssContent).toMatch(/\.os-agent-sidebar\s*\{[^}]*container-type:\s*inline-size/s)
  })

  it('uses fixed-width auto-fill tracks centred as a block, not fluid columns', () => {
    // #1262 revert: fixed 5.25rem tracks (width-independent tile geometry)
    // centred as a block. Fluid 1fr columns re-flowed at every rail width,
    // which read as wobble; auto-fill + fixed tracks keeps it stable.
    expect(cssContent).toMatch(
      /\.os-fav-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*5\.25rem\)/s,
    )
    expect(cssContent).toMatch(/\.os-fav-grid\s*\{[^}]*justify-content:\s*center/s)
  })

  it('keeps container queries as gap-only narrow/wide refinements', () => {
    expect(cssContent).toMatch(/@container\s*\([^)]*max-width:\s*200px[^)]*\)/)
    expect(cssContent).toMatch(/@container\s*\([^)]*min-width:\s*320px[^)]*\)/)
  })

  it('preserves single-column collapsed avatar-only mode', () => {
    expect(cssContent).toMatch(/\.os-agent-sidebar--avatar-only\s+\.os-fav-grid\s*\{[^}]*grid-template-columns:\s*1fr/s)
  })
})
