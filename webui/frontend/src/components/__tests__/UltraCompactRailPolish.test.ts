import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { readFileSync } from 'node:fs'

/**
 * #1237 / #1238 / #1235 — ultra-compact (avatar-only) rail polish.
 *
 * #1237: hovering an avatar-only row must show the agent's name. The
 * `title={name}` used to live only on the hidden inner label span
 * (`display:none` drops it from hit-testing), so the outer row element now
 * carries it for agent / remote / team rows.
 *
 * #1238: the expand/collapse pill was unconditionally visible in avatar-only
 * mode (opacity 1 from a leftover comma-selector); it must conceal until the
 * divider/pill is hovered or focused, while the fully-collapsed (0px) pane
 * keeps its unconditional reveal so the rail can be restored.
 *
 * #1235: the pill is a drag handle too (#741), so its cursor must read
 * `col-resize` — the same affordance as the divider spine — on both the pill
 * container and its inner button.
 */
const rowsRenderSrc = fs.readFileSync(
  path.resolve(__dirname, '../sidebar/rowsRender.tsx'),
  'utf8',
)
const css = readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

describe('#1237: avatar-only rows carry the name tooltip on the outer element', () => {
  // #1726: the tooltip attribute is `rowTitle`, not `name` — for a plain seat
  // row `rowTitle` IS `name` (it is only different for a chat row, which
  // tooltips the session it names instead of the seat it belongs to). The
  // #1237 contract — the OUTER row element carries the tooltip, not the
  // `display:none` inner label — is unchanged.
  const outer = (tag: string, label: string) => {
    it(`${label}: outer <${tag}> row carries title={rowTitle}`, () => {
      expect(rowsRenderSrc).toMatch(
        new RegExp(`<${tag}[^>]*title=\\{rowTitle\\}`, 's'),
      )
    })
  }
  outer('a', 'herdr agent row')
  outer('button', 'session-picker agent row')
  outer('Link', 'default agent row')
  outer('Link', 'team row')
  outer('Link', 'remote row')

  // #1726 changed the attribute to `rowTitle` (a chat row tooltips the session
  // it names, not the seat it belongs to), so the source pin above no longer
  // says WHICH string reaches the DOM. This does: the rendered outer row
  // element carries the seat name for a seat and the session title for a chat
  // row — see `rowsRender.test.tsx` (#1726), which asserts it on the DOM.
})

describe('#1246: the mid-divider pill is retired', () => {
  it('removes the mid-pane divider pill entirely', () => {
    // #1246 supersedes #555/#741/#1235/#1238: collapse/expand moved to the
    // pane header and the top of the divider spine, so no pill rules remain.
    expect(css).not.toMatch(/\.os-rail-divider-pill/)
    expect(rowsRenderSrc).not.toMatch(/divider-pill/)
  })

  it('draws the collapse/expand spine without a floating notch', () => {
    expect(css).toMatch(/(?:^|\n)\.os-rail-resizer \{/)
    expect(css).toMatch(/\.os-rail-resizer::after/)
    // The divider has no `top: 40%` float left behind.
    expect(css).not.toMatch(/top:\s*40%/)
  })
})
