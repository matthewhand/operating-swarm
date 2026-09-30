/**
 * #1309 — three rail defects at the laptop default (118px):
 *
 *  D1  `.os-rail-row-name` collapsed to ~18px clientWidth (label col ~24px)
 *      and the #556 fade `calc(100% - 1.25rem)` went negative, so the whole
 *      name was transparent. The fix reclaims narrow-rail chrome, floors the
 *      label/name width, bounds the fade, and drops the empty slot's gap.
 *  D2  `.os-rail-update-chrome` was occluded by the resize handle (left dock)
 *      and pushed the document 5px past the viewport (right dock). The fix
 *      stacks the hostname row above the handle and lets its input shrink.
 *  D7  `expandSidebar` restored the 256px desktop constant; it now restores
 *      the viewport default (covered in sidebarPackage.test.tsx).
 *
 * jsdom has no layout, so this pins the stylesheet contract; the rendered
 * geometry is proven by `e2e/rail-geometry.spec.ts` (1440x900 + 1280x800).
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const CSS = readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

/** Rule body for an exact selector, up to its closing brace. */
function ruleBody(selector: string): string {
  // Anchor to line start: a bare indexOf also matches descendant-qualified
  // selectors (`.os-agent-sidebar--avatar-only .os-rail-hostname-row {`) that
  // appear earlier in the sheet and would report the wrong rule's body.
  const pattern = new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{`, 'm')
  const match = pattern.exec(CSS)
  expect(match, `expected index.css to declare ${selector}`).not.toBeNull()
  const start = match!.index
  return CSS.slice(start, CSS.indexOf('}', start))
}

describe('#1309 D1: agent names stay legible at the laptop default', () => {
  it('the label column has a sensible floor instead of collapsing to 0', () => {
    const body = ruleBody('.os-agent-row__label-col')
    expect(body).not.toMatch(/min-width:\s*0\s*;/)
    expect(body).toMatch(/min-width:\s*2\.75rem/)
  })

  it('the name itself is floored so a wide slot cannot push it to zero', () => {
    const body = ruleBody('.os-rail-name-line .os-rail-row-name')
    expect(body).toMatch(/min-width:\s*2\.5rem/)
  })

  it('the #556 fade stop can never exceed the visible width', () => {
    const body = ruleBody('.os-rail-row-name')
    expect(body).toContain('mask-image')
    expect(body).toContain('-webkit-mask-image')
    // Bounded fade: at least ~60% of the element stays opaque at any width.
    expect(body).toMatch(/min\(0\.5rem,\s*40%\)/)
    expect(body).not.toContain('calc(100% - 1.25rem)')
  })

  it('an empty slot claims no gap', () => {
    const start = CSS.indexOf('.os-rail-slot:empty {')
    expect(start, 'expected .os-rail-slot:empty rule').toBeGreaterThanOrEqual(0)
    const body = CSS.slice(start, CSS.indexOf('}', start))
    expect(body).toMatch(/display:\s*none/)
  })

  it('reclaims narrow-rail chrome so the label column keeps a real run', () => {
    const start = CSS.indexOf('@container (max-width: 160px)')
    expect(start, 'expected the 160px narrow-rail container query').toBeGreaterThanOrEqual(0)
    const block = CSS.slice(start, CSS.indexOf('\n}', start))
    expect(block).toContain('.os-agent-row')
    expect(block).toMatch(/padding:\s*0\.375rem/)
    expect(block).toMatch(/gap:\s*0\.375rem/)
    expect(block).toContain('.os-agent-row__avatar-slot')
    expect(block).toMatch(/2rem/)
  })

  it('uses a thin scrollbar so the reserved gutter does not starve rows', () => {
    expect(ruleBody('.os-rail-scroller')).toMatch(/scrollbar-width:\s*thin/)
  })
})

describe('#1309 D2: footer update chrome wins the hit-test and stays in-pane', () => {
  it('stacks the hostname row above the resize handle with pointer pass-through', () => {
    const row = ruleBody('.os-rail-hostname-row')
    expect(row).toMatch(/position:\s*relative/)
    expect(row).toMatch(/z-index:\s*51/)
    expect(row).toMatch(/pointer-events:\s*none/)
    expect(row).toMatch(/min-width:\s*0/)

    const resizerZ = Number(/z-index:\s*(\d+)/.exec(ruleBody('.os-rail-resizer'))?.[1])
    const rowZ = Number(/z-index:\s*(\d+)/.exec(row)?.[1])
    expect(resizerZ, 'resize handle z-index').toBe(50)
    expect(rowZ, 'hostname row must stack above the handle').toBeGreaterThan(resizerZ)
  })

  it('lets the row controls opt back into pointer events', () => {
    const children = ruleBody('.os-rail-hostname-row > *')
    expect(children).toMatch(/pointer-events:\s*auto/)
  })

  it('lets the hostname input shrink so the row cannot overflow the rail', () => {
    // #1308 owns the floor: 4rem while the rail can seat it, relaxed inside the
    // narrow container. What #1309 needs is that the input is actually allowed
    // to shrink (flex shrink > 0) and that the floor really is relaxed at the
    // 118px detent, otherwise the row pushes the update chip out of the pane.
    const input = ruleBody('.os-rail-hostname')
    expect(input).toMatch(/flex:\s*0 1 auto/)

    const narrow = CSS.slice(
      CSS.indexOf('@container (max-width: 9rem)'),
      CSS.indexOf('\n}', CSS.indexOf('@container (max-width: 9rem)')),
    )
    expect(narrow, 'narrow container relaxes the hostname floor').toContain('.os-rail-hostname')
    const relaxed = /min-width:\s*([0-9.]+)rem/.exec(narrow.slice(narrow.indexOf('.os-rail-hostname')))
    expect(relaxed, 'narrow container declares a rem floor').not.toBeNull()
    expect(Number(relaxed![1]), 'narrow floor is smaller than the 4rem base').toBeLessThan(4)

    // The row itself must not impose a floor wider than the pane.
    expect(ruleBody('.os-rail-hostname-row')).toMatch(/min-width:\s*0/)
  })
})
