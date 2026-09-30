import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

/**
 * #1655 — the expander/collapse control shares the rail's icon axis.
 *
 * jsdom cannot resolve computed layout, so these are source-level contract
 * assertions (repo pattern): the control's footprint token must equal the
 * sibling rail controls' (2.25rem), and the avatar-only top-toggle band must
 * be symmetric so the control rides the same centerline as the search row.
 */
describe('#1655 expander alignment with sibling rail icons', () => {
  const concealSrc = fs.readFileSync(
    path.resolve(__dirname, '../SidepaneConceal.tsx'),
    'utf-8',
  )
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')

  it('sizes the conceal/expand control to the shared 2.25rem icon rhythm', () => {
    // h-9 w-9 = 2.25rem — matches .os-rail-search and .os-search-add-btn.
    expect(concealSrc).toMatch(/min-h-9 min-w-9 h-9 w-9/)
    expect(concealSrc).not.toMatch(/h-8 w-8/)
  })

  it('sibling rail controls carry the same 2.25rem footprint', () => {
    expect(css).toMatch(/\.os-rail-search\s*\{[^}]*?height:\s*2\.25rem;/)
    expect(css).toMatch(/\.os-search-add-btn\s*\{[^}]*?height:\s*2\.25rem;/)
  })

  it('avatar-only top-toggle band is vertically symmetric', () => {
    const rule = css.match(/\.os-rail-top-toggle\s*\{([^}]+)\}/)
    expect(rule).toBeTruthy()
    // Symmetric block padding (one value or top==bottom), never the old
    // top-heavy 0.4/0.15 split that floated the control off the axis.
    const pad = rule![1].match(/padding:\s*([^;]+);/)?.[1] ?? ''
    const parts = pad.trim().split(/\s+/)
    // 1–2 value shorthand is vertically symmetric by definition; 3–4 values
    // expose top/bottom explicitly — they must match.
    if (parts.length > 2) {
      expect(parts[0]).toBe(parts[2])
    }
    expect(pad).not.toContain('0.15rem')
    // Stays centred on the rail axis.
    expect(rule![1]).toMatch(/align-items:\s*center/)
    expect(rule![1]).toMatch(/justify-content:\s*center/)
  })
})
