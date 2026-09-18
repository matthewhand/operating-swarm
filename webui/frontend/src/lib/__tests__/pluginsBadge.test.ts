/**
 * #577 — the composer's Plugins-Enabled badge.
 *
 * Contract under test:
 *   0 enabled  → null (render nothing)
 *   1 enabled  → `<Plugin> Enabled` using the popup's display names
 *   2+ enabled → `Plugins Enabled <N>`
 *   live: re-resolves the SAME scope accessor the send path reads
 *   gate: absent on seats that cannot use plugins (#511)
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import {
  CHAT_PLUGIN_TOOLS_KEY,
  FIXTURE_PLUGIN_TOOLS,
  saveEnabledPluginToolIds,
} from '../chatPluginTools'
import {
  pluginsBadgeLabel,
  useEnabledPluginTools,
  usePluginsBadgeAllowed,
} from '../pluginsBadge'
import {
  CURRENT_AGENT_STORAGE_KEY,
  publishCurrentAgent,
} from '../currentAgent'
import { publishCurrentChatScope } from '../chatScope'

describe('pluginsBadgeLabel (#577 label contract)', () => {
  const tools = FIXTURE_PLUGIN_TOOLS

  it('renders nothing with zero enabled', () => {
    expect(pluginsBadgeLabel([], tools)).toBeNull()
  })

  it('names the single plugin, not the count or the snake_case id', () => {
    expect(pluginsBadgeLabel(['web_search'], tools)).toBe('Web Search Enabled')
    expect(pluginsBadgeLabel(['web_search'], tools)).not.toMatch(/web_search/)
  })

  it('counts two or more', () => {
    expect(pluginsBadgeLabel(['web_search', 'web_fetch'], tools)).toBe('Plugins Enabled 2')
    expect(pluginsBadgeLabel(['a', 'b', 'c'], tools)).toBe('Plugins Enabled 3')
  })

  it('falls back to a readable name for an unknown id', () => {
    expect(pluginsBadgeLabel(['mystery_tool'], tools)).toBe('mystery_tool Enabled')
  })
})

describe('useEnabledPluginTools (same scope the send path reads)', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('resolves the live chat scope and follows scope changes', async () => {
    publishCurrentChatScope('chat-a')
    saveEnabledPluginToolIds('chat-a', ['web_search'])
    saveEnabledPluginToolIds('chat-b', ['web_fetch', 'browser_click'])

    const { result } = renderHook(() => useEnabledPluginTools())
    expect(result.current.chatId).toBe('chat-a')
    expect(result.current.ids).toEqual(['web_search'])

    act(() => {
      publishCurrentChatScope('chat-b')
    })
    await waitFor(() => {
      expect(result.current.chatId).toBe('chat-b')
    })
    expect(result.current.ids).toEqual(['web_fetch', 'browser_click'])
  })

  it('follows toggles without re-render pressure from the popup', async () => {
    publishCurrentChatScope('chat-live')
    const { result } = renderHook(() => useEnabledPluginTools())
    expect(result.current.ids).toEqual([])

    act(() => {
      saveEnabledPluginToolIds('chat-live', ['web_search'])
    })
    await waitFor(() => {
      expect(result.current.ids).toEqual(['web_search'])
    })
  })

  it('agrees with what the send path will apply (enabledToolsParam)', () => {
    publishCurrentChatScope('chat-send')
    saveEnabledPluginToolIds('chat-send', ['web_search', 'web_fetch'])
    const { result } = renderHook(() => useEnabledPluginTools())
    // The send path reads enabledToolsParam(conversationIdRef.current) with
    // the same scope id — the arrays must be identical for the same key.
    expect(result.current.ids).toEqual(
      JSON.parse(localStorage.getItem(CHAT_PLUGIN_TOOLS_KEY) || '{}')['chat-send'],
    )
  })
})

describe('usePluginsBadgeAllowed (#511 gate)', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('allows API and swarm-owned seats, denies CLI/remote kinds', () => {
    const { rerender, result } = renderHook(() => usePluginsBadgeAllowed())
    const set = (agent: unknown) => {
      localStorage.setItem(CURRENT_AGENT_STORAGE_KEY, JSON.stringify(agent))
      act(() => {
        publishCurrentAgent(agent as never)
      })
      rerender()
    }

    set({ id: 'api_agent', kind: 'api' })
    expect(result.current).toBe(true)
    set({ id: 'codey', kind: 'blueprint' })
    expect(result.current).toBe(true)
    set({ id: 'cli_agent', kind: 'cli' })
    expect(result.current).toBe(false)
    set({ id: 'herdr1', kind: 'remote' })
    expect(result.current).toBe(false)
  })

  it('stays allowed when the seat is not yet resolved (transient load)', () => {
    localStorage.removeItem(CURRENT_AGENT_STORAGE_KEY)
    const { result } = renderHook(() => usePluginsBadgeAllowed())
    expect(result.current).toBe(true)
  })
})
