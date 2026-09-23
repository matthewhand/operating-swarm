/**
 * #724 — Bubble theme is an agent/chat presentation setting, so it belongs in
 * the rail agent right-click menu (per-agent override via #676's
 * setAgentBubbleTheme), not in the message right-click menu.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const railMenu = readFileSync(
  join(__dirname, '..', 'railContextMenu.ts'),
  'utf8',
)
const sidebar = readFileSync(
  join(__dirname, '..', '..', 'components', 'AgentSidebar.tsx'),
  'utf8',
)
const chatPage = readFileSync(join(__dirname, '..', '..', 'pages', 'ChatPage.tsx'), 'utf8')

describe('#724 bubble theme lives in the rail agent menu', () => {
  it('exposes a bubble-theme submenu item in the rail menu contract', () => {
    expect(railMenu).toMatch(/['"]bubble-theme['"]/)
  })

  it('AgentSidebar dispatches setAgentBubbleTheme from the submenu', () => {
    expect(sidebar).toMatch(/agentBubbleThemeOverrides\(\)/)
    expect(sidebar).toMatch(/setAgentBubbleTheme\(/)
    expect(sidebar).toMatch(/parentId === ['"]bubble-theme['"]/)
  })

  it('ChatPage no longer renders the bubble-theme submenu in the message context menu', () => {
    expect(chatPage).not.toMatch(/context-menu-bubble-theme/)
  })
})
