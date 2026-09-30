/**
 * #1308 follow-up — rail chrome must not overflow the pane at the one-column
 * laptop detent, nor the viewport when the rail is docked right.
 *
 * jsdom has no layout, so this pins the CSS contract that produces the rendered
 * geometry (the rendered result is covered by e2e/rail-geometry.spec.ts):
 *  1. The footer hostname row overflowed the 118px rail because the hostname
 *     field's 4rem min-width beat every other flex item. The narrow container
 *     query must relax it before the row overflows, while wider rails keep the
 *     floor.
 *  2. A right-docked collapsed rail left the resize hit-zone hanging off the
 *     right viewport edge (document horizontal scroll). The mirror rule must
 *     target the real `--right` modifier, not a class nothing applies.
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const CSS = readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

function ruleBody(selector: string): string {
  const start = CSS.indexOf(`\n${selector} {`)
  expect(start, `expected index.css to declare ${selector}`).toBeGreaterThanOrEqual(0)
  const open = CSS.indexOf('{', start)
  return CSS.slice(open + 1, CSS.indexOf('}', open))
}

function containerBlock(predicate: string): string {
  const start = CSS.indexOf(`@container (${predicate})`)
  expect(start, `expected @container (${predicate})`).toBeGreaterThanOrEqual(0)
  const open = CSS.indexOf('{', start)
  let depth = 0
  for (let i = open; i < CSS.length; i++) {
    if (CSS[i] === '{') depth++
    else if (CSS[i] === '}') {
      depth--
      if (depth === 0) return CSS.slice(open + 1, i)
    }
  }
  return ''
}

describe('#1308 rail footer cannot outgrow the one-column pane', () => {
  it('keeps the 4rem hostname floor for rails wide enough to seat it', () => {
    expect(ruleBody('.os-rail-hostname')).toContain('min-width: 4rem')
  })

  it('relaxes the floor in a narrow container so the update chip stays in-pane', () => {
    const narrow = containerBlock('max-width: 9rem')
    expect(narrow).toContain('.os-rail-hostname')
    expect(narrow).toContain('min-width: 2rem')
  })
})

describe('#1308 right-docked collapsed resizer stays on-screen', () => {
  it('mirrors the collapsed hit-zone via the real right-rail modifier', () => {
    const body = ruleBody('.os-agent-sidebar--collapsed.os-agent-sidebar--right .os-rail-resizer')
    expect(body).toContain('left: -10px')
    expect(body).toContain('right: auto')
  })

  it('does not rely on a class nothing renders', () => {
    expect(CSS).not.toContain('os-rail-side-right-target')
  })
})
