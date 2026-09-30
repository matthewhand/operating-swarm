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
const addMenuSource = readFileSync(join(__dirname, '..', 'AddBotMenu.tsx'), 'utf8')

describe('#754 → #1246 divider affordance placement', () => {
  it('retires the mid-divider pill and keeps the draggable spine', () => {
    // #1246 supersedes #754: the pill no longer rides the divider at all.
    // The spine (::after) remains the resize affordance, with no floating
    // notch left behind.
    expect(css).not.toMatch(/\.os-rail-divider-pill/)
    expect(css).not.toMatch(/top:\s*40%/)
    expect(css).toMatch(/\.os-rail-resizer::after/)
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
    // #1674: the row now mounts the shared `AddBotMenu`, which owns the
    // `.os-search-add-btn` trigger. Pin both halves of that chain.
    const row = sidebarSource.match(/os-rail-search-row[\s\S]{0,1400}<AddBotMenu/)
    expect(row).toBeTruthy()
    expect(addMenuSource).toMatch(/className="os-search-add-btn"/)
  })
})
