/**
 * #516 — plugin enablement is a property of the **agent**, not the chat.
 *
 * The old accessors were keyed by conversation id, which meant the same agent
 * in two threads had two independent plugin sets and a fresh thread started
 * from nothing. The accessors keep their names and shapes but take an
 * `agentId`; the two id spaces are stored under separate namespaced keys so a
 * re-key can never silently read the other's data.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  AGENT_PLUGIN_TOOLS_KEY,
  CHAT_PLUGIN_TOOLS_EVENT,
  enabledToolsParam,
  loadEnabledPluginToolIds,
  setPluginToolEnabled,
} from '../chatPluginTools'

describe('#516 agent-scoped plugin enablement', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  it('stores the enabled set under the agent-scoped key, not the chat key', () => {
    setPluginToolEnabled('support', 'web_search', true)

    const raw = window.localStorage.getItem(AGENT_PLUGIN_TOOLS_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!)).toEqual({ support: ['web_search'] })
    // The old per-chat store stays untouched — no cross-namespace reads.
    expect(window.localStorage.getItem('swarm_chat_plugin_tools')).toBeNull()
  })

  it('the same agent reads the same set from a different conversation scope', () => {
    setPluginToolEnabled('support', 'web_search', true)
    // The regression that defines the ticket: the read is keyed by agent, so
    // whatever conversation-derived value a caller passes cannot fork it.
    expect(loadEnabledPluginToolIds('support')).toEqual(['web_search'])
  })

  it('two different agents never share a set', () => {
    setPluginToolEnabled('support', 'web_search', true)
    expect(loadEnabledPluginToolIds('codey')).toEqual([])
  })

  it('empty or whitespace agent ids act as a no-op (no key written)', () => {
    expect(loadEnabledPluginToolIds('')).toEqual([])
    setPluginToolEnabled('  ', 'web_search', true)
    expect(window.localStorage.getItem(AGENT_PLUGIN_TOOLS_KEY)).toBeNull()
  })

  it('the save event carries agentId', () => {
    const seen: Array<Record<string, unknown>> = []
    const onPrefs = (event: Event) => {
      seen.push((event as CustomEvent).detail as Record<string, unknown>)
    }
    window.addEventListener(CHAT_PLUGIN_TOOLS_EVENT, onPrefs)
    try {
      setPluginToolEnabled('support', 'web_fetch', true)
    } finally {
      window.removeEventListener(CHAT_PLUGIN_TOOLS_EVENT, onPrefs)
    }
    expect(seen).toEqual([{ agentId: 'support', enabled: ['web_fetch'] }])
  })

  it('the send param reads the agent set — the toggle and the send cannot diverge', () => {
    setPluginToolEnabled('support', 'web_search', true)
    setPluginToolEnabled('support', 'web_fetch', true)
    expect(enabledToolsParam('support')).toEqual({
      enabled_tools: ['web_search', 'web_fetch'],
    })
  })
})
