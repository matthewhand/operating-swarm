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
})
