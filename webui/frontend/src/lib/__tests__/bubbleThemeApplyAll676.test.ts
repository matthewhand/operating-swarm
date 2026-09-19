/**
 * #676 — Settings gains "Apply to all" for the bubble theme, enabled only
 * when some agent carries an override that differs from the selected default.
 *
 * The per-agent override store lives beside the global theme (same lib) so
 * the rail right-click menu and Settings stay one source of truth:
 * - `agentBubbleThemeOverrides()` — the {agentId → theme} map
 * - `setAgentBubbleTheme(agentId, theme|null)` — set/clear one override
 *   (null clears; the agent follows the default again)
 * - `overriddenBubbleThemeCount(defaultTheme)` — how many agents would be
 *   brought onto a new default (the Apply-to-all enablement + count)
 * - `applyBubbleThemeToAll(defaultTheme)` — clear every override; returns
 *   the number cleared
 */
import { beforeEach, describe, expect, it } from 'vitest'
import {
  AGENT_BUBBLE_THEME_STORAGE_KEY,
  agentBubbleThemeOverrides,
  applyBubbleThemeToAll,
  overriddenBubbleThemeCount,
  setAgentBubbleTheme,
} from '../bubbleTheme'

beforeEach(() => localStorage.clear())

describe('#676 per-agent bubble theme overrides', () => {
  it('starts with no overrides', () => {
    expect(agentBubbleThemeOverrides()).toEqual({})
    expect(overriddenBubbleThemeCount('speech')).toBe(0)
  })

  it('setAgentBubbleTheme writes one override; null clears it', () => {
    setAgentBubbleTheme('codey', 'irc')
    expect(agentBubbleThemeOverrides()).toEqual({ codey: 'irc' })
    setAgentBubbleTheme('codey', null)
    expect(agentBubbleThemeOverrides()).toEqual({})
  })

  it('overriddenBubbleThemeCount counts overrides differing from the default', () => {
    setAgentBubbleTheme('codey', 'irc')
    setAgentBubbleTheme('support', 'speech')
    setAgentBubbleTheme('zeus', 'feed')
    expect(overriddenBubbleThemeCount('speech')).toBe(2) // irc + feed differ
    expect(overriddenBubbleThemeCount('irc')).toBe(2) // speech + feed differ
  })

  it('applyBubbleThemeToAll clears every override and reports the count', () => {
    setAgentBubbleTheme('codey', 'irc')
    setAgentBubbleTheme('zeus', 'feed')
    expect(applyBubbleThemeToAll('speech')).toBe(2)
    expect(agentBubbleThemeOverrides()).toEqual({})
  })

  it('persists under the declared key (same channel the rail menu writes)', () => {
    setAgentBubbleTheme('codey', 'irc')
    expect(JSON.parse(localStorage.getItem(AGENT_BUBBLE_THEME_STORAGE_KEY) ?? '{}')).toEqual({
      codey: 'irc',
    })
  })
})
