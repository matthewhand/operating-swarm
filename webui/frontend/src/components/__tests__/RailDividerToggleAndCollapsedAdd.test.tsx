/**
 * #754 — the expand/collapse pill rides *beside* the divider, on the chat
 * side (immediately right of the border line), not centered on the line
 * itself where it fights the drag hit-zone.
 *
 * #764 — in avatar-only (collapsed) mode the Add-agent (+) button must stay
 * reachable directly under the search trigger; it used to be display:none.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync(join(__dirname, '..', '..', 'index.css'), 'utf8')
const sidebarSource = readFileSync(
  join(__dirname, '..', 'AgentSidebar.tsx'),
  'utf8',
)

describe('#754 divider pill placement', () => {
  it('anchors the pill to the chat side of the divider, not centered on it', () => {
    const pillBlock = css.match(/\.os-rail-divider-pill\s*\{[^}]*\}/)?.[0] ?? ''
    expect(pillBlock).toBeTruthy()
    // Chat side = right of the divider line: anchored from the left edge of
    // the resizer, offset right, no centering translate on the X axis.
    expect(pillBlock).toMatch(/left:\s*(100%|calc\(100%)/)
    expect(pillBlock).not.toMatch(/left:\s*50%/)
    expect(pillBlock).toMatch(/translate\(\s*0(?:%|px)?\s*,\s*-50%\s*\)/)
  })
})

describe('#764 add agent button in avatar-only rail', () => {
  it('no longer hides .os-search-add-btn in avatar-only mode', () => {
    expect(css).not.toMatch(
      /\.os-agent-sidebar--avatar-only [^{]*\.os-search-add-btn[^{]*\{[^}]*display:\s*none/,
    )
  })

  it('stacks the add button under the search trigger in avatar-only mode', () => {
    // The search row becomes a vertical stack when collapsed; the add button
    // (which follows search in the DOM) lands directly underneath it.
    expect(css).toMatch(
      /\.os-agent-sidebar--avatar-only\s+\.os-rail-search-row\s*\{[^}]*flex-direction:\s*column/,
    )
  })

  it('the add button renders in the search row in the component', () => {
    const row = sidebarSource.match(/os-rail-search-row[\s\S]{0,1400}os-search-add-btn/)
    expect(row).toBeTruthy()
  })
})
