/**
 * #1073 — drawer header layout + docked behaviour pins.
 *
 * Source-level pins (the suite's convention for chrome contracts):
 * - X sits on the LEFT of the drawer header, pin toggle on the RIGHT.
 * - Pin toggle is tablet-only (hidden below `sm`), carries aria-pressed.
 * - Docked rail suppresses the overlay backdrop and gains the docked class.
 * - App suppresses pick auto-dismiss while docked.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const sidebar = readFileSync(
  join(process.cwd(), 'src/components/AgentSidebar.tsx'),
  'utf8',
)
const app = readFileSync(join(process.cwd(), 'src/App.tsx'), 'utf8')

describe('#1073 tablet sticky dock chrome', () => {
  it('renders the drawer header with X left and pin right', () => {
    const header = sidebar.slice(
      sidebar.indexOf('#1073: drawer header'),
      sidebar.indexOf('os-rail-search-row'),
    )
    expect(header).toContain('justify-between')
    expect(header).toContain('Close agents sidebar')
    expect(header).toContain('rail-drawer-close')
    expect(header).toContain('Pin agents sidebar')
    expect(header).toContain('Unpin agents sidebar')
    // pin button comes after the close button in source order → right side
    expect(header.indexOf('rail-drawer-close')).toBeLessThan(
      header.indexOf('rail-tablet-dock-toggle'),
    )
  })

  it('hides the pin toggle on mobile widths (sm:inline-flex)', () => {
    expect(sidebar).toContain('hidden sm:inline-flex')
    expect(sidebar).toContain('aria-pressed={tabletDocked}')
  })

  it('suppresses the backdrop and applies the docked class when pinned', () => {
    expect(sidebar).toContain('{!tabletDocked && (')
    expect(sidebar).toContain('os-agent-sidebar--tablet-docked')
  })

  it('docked tablet rail keeps the drawer open across tier changes', () => {
    expect(app).toContain('setRailOpen(loadTabletStickyDock())')
  })
})
