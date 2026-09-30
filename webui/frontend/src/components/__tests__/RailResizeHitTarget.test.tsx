/**
 * The rail resize handle must not steal clicks from the collapse control.
 * jsdom has no layout, so the rendered geometry is proven by
 * `e2e/rail-geometry.spec.ts`; this pins the CSS contract that produces it.
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const CSS = readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

function ruleBody(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = CSS.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([\\s\\S]*?)\\}`))
  expect(match, `missing CSS rule: ${selector}`).not.toBeNull()
  return match![1]
}

describe('rail hit-target stacking (resize handle vs collapse control)', () => {
  it('positions the search row above the resize handle', () => {
    const resizer = ruleBody('.os-rail-resizer')
    const searchRow = ruleBody('.os-rail-search-row')
    const resizerZ = Number(/z-index:\s*(\d+)/.exec(resizer)?.[1])
    const searchRowZ = Number(/z-index:\s*(\d+)/.exec(searchRow)?.[1])
    expect(resizerZ, 'resize handle z-index').toBe(50)
    expect(searchRowZ, 'search row must stack above the handle').toBeGreaterThan(resizerZ)
    expect(searchRow, 'stacking requires a positioned row').toMatch(/position:\s*relative/)
  })

  it('lets pointer events pass through the row but keeps its controls clickable', () => {
    const searchRow = ruleBody('.os-rail-search-row')
    expect(searchRow, 'row background must not block the handle').toMatch(/pointer-events:\s*none/)
    const children = ruleBody('.os-rail-search-row > *')
    expect(children, 'controls opt back into pointer events').toMatch(/pointer-events:\s*auto/)
  })
})
