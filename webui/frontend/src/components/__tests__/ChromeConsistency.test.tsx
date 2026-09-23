import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * CSS contract tests for the chrome-consistency batch:
 *   #559 pinned tile centring
 *   #560 shared top-chrome height token
 *   #562 rail scrollbar gutter
 *
 * These read `index.css` directly, the same way the existing layout guards
 * (`AgentPinGridResponsive`, `CollapsedRailAlignment`, `AltHotkeyTipPosition`)
 * do — the defects are in the stylesheet, so the regression guard has to be too.
 */
const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
const sidebar =
    readFileSync(join(process.cwd(), 'src/components/AgentSidebar.tsx'), 'utf8') +
    readFileSync(join(process.cwd(), 'src/components/sidebar/RailSections.tsx'), 'utf8') // #856 slice I: fav-grid + section markup moved verbatim into sidebar/RailSections.tsx

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))?.[1] ?? ''
}

describe('#559 pinned tiles centre, rail rows stay left-aligned', () => {
  it('keeps host-specific alignment out of the shared .os-stacked-avatars base rule', () => {
    const base = rule('.os-stacked-avatars')
    expect(base).toBeTruthy()
    expect(base).toMatch(/display:\s*inline-flex/)
    expect(base).not.toMatch(/align-self/)
    expect(base).not.toMatch(/margin-top/)
  })

  it('a rail row keeps its left-aligned stack', () => {
    const row = rule('.os-agent-row .os-stacked-avatars')
    expect(row).toMatch(/align-self:\s*flex-start/)
    expect(row).toMatch(/margin-top:\s*0\.2rem/)
  })

  it('a pinned tile centres its stack on both axes', () => {
    const tile = rule('.os-fav-tile .os-stacked-avatars')
    expect(tile).toMatch(/align-self:\s*center/)
    expect(tile).toMatch(/margin-top:\s*0/)
  })
})

describe('#560 one height token for the top chrome band', () => {
  it('declares the token once on :root', () => {
    expect(rule(':root')).toMatch(/--os-top-chrome-h:\s*[\d.]+rem/)
  })

  it('the chat header consumes it and no longer guesses with min-height', () => {
    const header = rule('.os-chat-header')
    expect(header).toMatch(/height:\s*var\(--os-top-chrome-h\)/)
    expect(header).not.toMatch(/min-height/)
    expect(header).toMatch(/border-bottom/)
  })

  it("the rail's search strip consumes the same token", () => {
    const strip = rule('.os-rail-search-row')
    expect(strip).toMatch(/height:\s*var\(--os-top-chrome-h\)/)
  })

  it('both bands draw the divider, so the rule is continuous', () => {
    expect(rule('.os-chat-header')).toMatch(/border-bottom/)
    expect(rule('.os-rail-search-row')).toMatch(/border-bottom/)
  })
})

describe('#562 the rail scroller reserves a gutter', () => {
  it('reserves the gutter so revealing the scrollbar cannot reflow the pane', () => {
    expect(rule('.os-rail-scroller')).toMatch(/scrollbar-gutter:\s*stable/)
  })

  it('reclaims it in avatar-only mode, where the rail is only 68-96px wide', () => {
    const avatarOnly = rule('.os-agent-sidebar--avatar-only .os-rail-scroller')
    expect(avatarOnly).toMatch(/scrollbar-gutter:\s*auto/)
    expect(avatarOnly).toMatch(/scrollbar-width:\s*none/)
    expect(css).toMatch(
      /\.os-agent-sidebar--avatar-only \.os-rail-scroller::-webkit-scrollbar\s*\{[^}]*width:\s*0/,
    )
  })

  it('the scrolling element actually carries the hook', () => {
    // The class lives in a template literal (conditional #729 bottom pad),
    // so the hook match allows either quote form.
    expect(sidebar).toMatch(/os-rail-scroller[^\n]*overflow-y-auto/)
    expect(sidebar).toContain('data-testid="rail-agent-scroller"')
  })
})
