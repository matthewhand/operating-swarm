import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')

function ruleBody(selector: string): string {
  const start = css.indexOf(`${selector} {`)
  expect(start, `expected index.css to declare ${selector}`).toBeGreaterThanOrEqual(0)
  return css.slice(start, css.indexOf('}', start))
}

describe('#556 narrow rail: the row cannot paint outside the pane', () => {
  it('the label column establishes paint containment', () => {
    // The leaf name already truncated; the spill came from an ancestor that did
    // not clip, so the fix has to be containment, not another `truncate`.
    expect(ruleBody('.os-agent-row__label-col')).toContain('overflow: hidden')
  })

  it('the name is cut with a fade rather than an ellipsis glyph', () => {
    const body = ruleBody('.os-rail-row-name')
    expect(body).toContain('white-space: nowrap')
    expect(body).toContain('overflow: hidden')
    expect(body).toContain('mask-image')
    // Safari still needs the prefix.
    expect(body).toContain('-webkit-mask-image')
  })

  it('the rail row name no longer relies on Tailwind truncate', () => {
    const sidebar = fs.readFileSync(
      path.resolve(__dirname, '../AgentSidebar.tsx'),
      'utf-8',
    )
    expect(sidebar).toContain('os-rail-row-name')
    expect(sidebar).not.toContain('block min-w-0 truncate text-sm font-semibold leading-5')
  })
})

describe('#547 rail footer update chrome', () => {
  it('is pinned to the right edge of the hostname row', () => {
    expect(ruleBody('.os-rail-update-chrome')).toContain('margin-left: auto')
  })

  it('is icon-only by default and gains a label only when the width allows', () => {
    expect(ruleBody('.os-rail-update-chrome__label')).toContain('display: none')
    expect(css).toContain('@container (min-width: 15rem)')
    const container = css.slice(css.indexOf('@container (min-width: 15rem)'))
    expect(container.slice(0, container.indexOf('\n}'))).toContain(
      '.os-rail-update-chrome__label',
    )
    // The square button must be allowed to grow once the label shows.
    expect(container.slice(0, container.indexOf('\n}'))).toContain('width: auto')
  })
})
