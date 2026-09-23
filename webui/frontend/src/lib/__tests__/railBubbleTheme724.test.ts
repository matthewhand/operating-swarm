/**
 * #724 — Bubble theme is an agent/chat presentation setting, so it belongs in
 * the rail agent right-click menu (per-agent override via #676's
 * setAgentBubbleTheme), not in the message right-click menu.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const railMenu = readFileSync(
  join(__dirname, '..', 'railContextMenu.ts'),
  'utf8',
)
// #856 slice 11: the sidebar surface is the component plus every module it
// has shed into features/sidebar/ — pins read behaviour, not file location.
const sidebarDir = join(__dirname, '..', '..', 'features', 'sidebar')
const sidebarSurface = [
  readFileSync(join(__dirname, '..', '..', 'components', 'AgentSidebar.tsx'), 'utf8'),
  ...readdirSync(sidebarDir)
    .filter((f) => /\.tsx?$/.test(f))
    .map((f) => readFileSync(join(sidebarDir, f), 'utf8')),
].join('\n')
const chatPage = readFileSync(join(__dirname, '..', '..', 'pages', 'ChatPage.tsx'), 'utf8')

describe('#724 bubble theme lives in the rail agent menu', () => {
  it('exposes a bubble-theme submenu item in the rail menu contract', () => {
    expect(railMenu).toMatch(/['"]bubble-theme['"]/)
  })

  it('AgentSidebar dispatches setAgentBubbleTheme from the submenu', () => {
    expect(sidebarSurface).toMatch(/agentBubbleThemeOverrides\(\)/)
    expect(sidebarSurface).toMatch(/setAgentBubbleTheme\(/)
    expect(sidebarSurface).toMatch(/parentId === ['"]bubble-theme['"]/)
  })

  it('ChatPage no longer renders the bubble-theme submenu in the message context menu', () => {
    expect(chatPage).not.toMatch(/context-menu-bubble-theme/)
  })
})
