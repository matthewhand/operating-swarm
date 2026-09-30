import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('REQ-196: Collapsed sidepane vertical alignment for Support and peer rows', () => {
  it('defines vertical centering, matching row heights, and hides role badge in avatar-only mode', () => {
    const cssPath = path.resolve(__dirname, '../../index.css')
    const css = fs.readFileSync(cssPath, 'utf8')

    // Expect .os-agent-sidebar--avatar-only .os-agent-row to have centering and height
    const avatarOnlyRowMatch = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-agent-row\s*\{([^}]+)\}/
    )
    expect(avatarOnlyRowMatch).toBeTruthy()
    const rowRules = avatarOnlyRowMatch![1]
    expect(rowRules).toMatch(/justify-content:\s*center/)
    expect(rowRules).toMatch(/align-items:\s*center/)
    // #1146: ultra-compact rows — 2.25rem (the REQ-196 alignment contract
    // itself is unchanged; only the density metric moved).
    expect(rowRules).toMatch(/height:\s*2\.25rem/)

    // Expect .os-agent-sidebar--avatar-only .os-agent-row__avatar-slot to center and reset margin
    const avatarSlotMatch = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-agent-row__avatar-slot\s*\{([^}]+)\}/
    )
    expect(avatarSlotMatch).toBeTruthy()
    const slotRules = avatarSlotMatch![1]
    expect(slotRules).toMatch(/margin-top:\s*0/)
    expect(slotRules).toMatch(/align-self:\s*center/)

    // Expect .os-agent-sidebar--avatar-only .os-agent-role-badge to be hidden
    const roleBadgeMatch = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-agent-role-badge\s*\{([^}]+)\}/
    )
    expect(roleBadgeMatch).toBeTruthy()
    const badgeRules = roleBadgeMatch![1]
    expect(badgeRules).toMatch(/display:\s*none/)
  })
})

describe('#574: the rail footer keeps its height when the labels are hidden', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
  const sidebar = fs.readFileSync(
    path.resolve(__dirname, '../AgentSidebar.tsx'),
    'utf8',
  )

  it('pins a height on the footer buttons in avatar-only mode', () => {
    // The labels are hidden with `display: none`, which removes their line-box as
    // well — so without a pinned height the footer shrinks and the whole block
    // jumps as the rail crosses the threshold.
    const match = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-rail-footer-btn\s*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    expect(match![1]).toMatch(/height:\s*2rem/)
    expect(match![1]).toMatch(/padding-block:\s*0/)
  })

  it('marks every persistent footer button with the hook class', () => {
    // Teams, Plugins, Calendar. If a fourth is added it must carry the class too,
    // or it will reintroduce the jump.
    const marked = sidebar.match(/os-rail-footer-btn/g) ?? []
    expect(marked).toHaveLength(3)
    for (const testid of ['os-teams-button', 'os-plugins-button', 'os-calendar-button']) {
      expect(sidebar).toContain(testid)
    }
  })

  it('#1206: equalizes vertical distribution between Routines and Server icon', () => {
    // In avatar-only mode, the hostname row matches the 2rem height of the footer buttons above it
    const avatarMatch = css.match(
      /\.os-agent-sidebar--avatar-only\s+\.os-rail-hostname-row\s*\{([^}]+)\}/,
    )
    expect(avatarMatch).toBeTruthy()
    expect(avatarMatch![1]).toMatch(/height:\s*2rem/)
    expect(avatarMatch![1]).toMatch(/align-items:\s*center/)

    // #1244: expanded mode white-space is gone — the row is exactly the 2rem
    // button height with no padding-block, so the Server icon is not nudged
    // below the Teams/Plugins/Routines centreline.
    const rowMatch = css.match(
      /(?:^|\n)\.os-rail-hostname-row\s*\{([^}]+)\}/,
    )
    expect(rowMatch).toBeTruthy()
    expect(rowMatch![1]).toMatch(/height:\s*2rem/)
    expect(rowMatch![1]).toMatch(/padding:\s*0/)
  })

  it('#1244: footer icons share one centreline and hit-area', () => {
    // Every footer control — the three .os-rail-footer-btn rows and the Server
    // icon — must resolve to the same 2rem row height and 1rem glyph box so
    // the fourth icon is not vertically offset from the first three.
    const rowMatch = css.match(/(?:^|\n)\.os-rail-hostname-row\s*\{([^}]+)\}/)
    expect(rowMatch![1]).toMatch(/align-items:\s*center/)
    expect(rowMatch![1]).toMatch(/height:\s*2rem/)
    expect(rowMatch![1]).toMatch(/padding:\s*0/)

    const iconMatch = css.match(/(?:^|\n)\.os-rail-hostname-icon\s*\{([^}]+)\}/)
    expect(iconMatch).toBeTruthy()
    expect(iconMatch![1]).toMatch(/align-items:\s*center/)
    expect(iconMatch![1]).toMatch(/height:\s*1rem/)
    expect(iconMatch![1]).toMatch(/width:\s*1rem/)
    expect(iconMatch![1]).toMatch(/padding:\s*0/)

    // The Server button itself stays a 1rem h-4 w-4 glyph like the other icons.
    expect(sidebar).toMatch(/rail-server-icon/)
    expect(sidebar).toMatch(/os-rail-hostname-icon[^"']*h-4 w-4/)
  })
})

describe('#1207: hides pinned avatars, hidden bots, and footer when completely collapsed', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

  it('hides .os-fav-grid, hidden bots row, and footer container in collapsed mode', () => {
    const match = css.match(
      /\.os-agent-sidebar--collapsed\s+\.os-fav-grid[^{]*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    expect(match![1]).toMatch(/display:\s*none\s*!important/)

    expect(css).toMatch(
      /\.os-agent-sidebar--collapsed\s+\[data-testid=['"]hidden-bots-row['"]\]/,
    )
    expect(css).toMatch(
      /\.os-agent-sidebar--collapsed\s+\[data-testid=['"]sidebar-footer-container['"]\]/,
    )
  })
})

describe('#1246: collapse/expand affordances moved off the mid-divider', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
  const sidebar = fs.readFileSync(
    path.resolve(__dirname, '../AgentSidebar.tsx'),
    'utf8',
  )

  it('keeps the collapse toggle out of the mid-divider and in the search row', () => {
    // The pill is gone entirely; the control is the one in the search row.
    expect(css).not.toMatch(/\.os-rail-divider-pill/)
    expect(css).not.toMatch(/top:\s*40%/)
    expect(sidebar).not.toMatch(/os-rail-divider-pill/)
  })

  // The placement assertion that used to live here was a character window over
  // the component source:
  //
  //   expect(sidebar).toMatch(
  //     /os-rail-search-row[\s\S]{0,1600}?<SidebarConcealButton onClick=\{concealSidebar\}/,
  //   )
  //
  // It asserted "these two tokens are within 1600 characters of each other in
  // the file", not "the control is inside the row" -- and it matched the call
  // spelling `onClick={concealSidebar}` as well. It went red when #1674 and the
  // `sidebar/` package split widened the row, with the behaviour fully intact:
  // a window is not a contract, it is a statement about how large the file may
  // grow.
  //
  // It is now asserted by rendering, in
  // `components/__tests__/RailConcealInSearchRow1246.test.tsx`, which checks
  // real DOM containment (`searchRow.contains(toggle)`), that the control is
  // the last button in the row (the top-right placement claim, which a source
  // offset cannot express at all), and that it is reachable by its accessible
  // name rather than only by testid.

  it('pins the collapsed (0px) expand control to the top of the divider', () => {
    const expand = css.match(/\.os-rail-collapsed-expand\s*\{([^}]+)\}/)
    expect(expand).toBeTruthy()
    expect(expand![1]).toMatch(/position:\s*absolute/)
    expect(expand![1]).toMatch(/top:/)
    // Mirrors to the content side on a right-docked rail.
    expect(css).toMatch(
      /\.os-agent-sidebar--right\s+\.os-rail-collapsed-expand\s*\{[^}]*right:\s*100%/,
    )
  })
})

