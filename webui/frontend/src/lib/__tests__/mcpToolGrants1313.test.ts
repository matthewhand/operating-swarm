/**
 * #1313 — per-bot MCP / connector tool grants persist on the server.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AGENT_PLUGIN_TOOLS_KEY,
  loadEnabledPluginToolIds,
  setPluginToolEnabled,
} from '../chatPluginTools'
import { fetchAgentSettings } from '../agentSettings'

type FetchCall = { url: string; method: string; body: Record<string, unknown> | null }

function settingsOk(body: Record<string, unknown>) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response
}

describe('#1313 persistent MCP tool grants', () => {
  const calls: FetchCall[] = []

  beforeEach(() => {
    window.localStorage.clear()
    calls.length = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = String(init?.method || 'GET').toUpperCase()
        let body: Record<string, unknown> | null = null
        if (typeof init?.body === 'string' && init.body) {
          body = JSON.parse(init.body) as Record<string, unknown>
        }
        calls.push({ url, method, body })
        if (url.includes('/settings/') && method === 'PATCH') {
          return settingsOk({
            agent_id: 'support',
            new_chat_per_task: false,
            use_suggestions: false,
            command_allowlist: { allow: [], deny: [], ask: [] },
            mcp_tool_grants: Array.isArray(body?.mcp_tool_grants) ? body.mcp_tool_grants : [],
          })
        }
        if (url.includes('/settings/')) {
          return settingsOk({
            agent_id: 'support',
            new_chat_per_task: false,
            use_suggestions: false,
            command_allowlist: { allow: [], deny: [], ask: [] },
            mcp_tool_grants: ['web_search', 'web_fetch'],
          })
        }
        return settingsOk({})
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('toggle PATCHes mcp_tool_grants and never sends a secret', async () => {
    setPluginToolEnabled('support', 'web_search', true)
    await vi.waitFor(() => {
      expect(calls.some((call) => call.method === 'PATCH')).toBe(true)
    })
    const patch = calls.find((call) => call.method === 'PATCH')
    expect(patch?.url).toContain('/v1/agents/support/settings/')
    expect(patch?.body).toEqual({ mcp_tool_grants: ['web_search'] })
    expect(JSON.stringify(patch?.body)).not.toMatch(/sk-|token|api[_-]?key/i)
  })

  it('two agents never share a grant set', async () => {
    setPluginToolEnabled('support', 'web_search', true)
    setPluginToolEnabled('codey', 'web_fetch', true)
    expect(loadEnabledPluginToolIds('support')).toEqual(['web_search'])
    expect(loadEnabledPluginToolIds('codey')).toEqual(['web_fetch'])
    await vi.waitFor(() => {
      expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(2)
    })
    const patches = calls.filter((call) => call.method === 'PATCH')
    expect(patches.some((call) => call.url.includes('/v1/agents/support/settings/'))).toBe(true)
    expect(patches.some((call) => call.url.includes('/v1/agents/codey/settings/'))).toBe(true)
  })

  it('fetching settings hydrates the local grant cache from the server', async () => {
    const settings = await fetchAgentSettings('support')
    expect(settings.mcp_tool_grants).toEqual(['web_search', 'web_fetch'])
    expect(loadEnabledPluginToolIds('support')).toEqual(['web_search', 'web_fetch'])
  })

  it('empty server grants migrate the local #516 cache up, not wipe it', async () => {
    window.localStorage.setItem(
      AGENT_PLUGIN_TOOLS_KEY,
      JSON.stringify({ support: ['git_status'] }),
    )
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = String(init?.method || 'GET').toUpperCase()
        let body: Record<string, unknown> | null = null
        if (typeof init?.body === 'string' && init.body) {
          body = JSON.parse(init.body) as Record<string, unknown>
        }
        calls.push({ url, method, body })
        if (method === 'PATCH') {
          return settingsOk({
            agent_id: 'support',
            mcp_tool_grants: body?.mcp_tool_grants,
          })
        }
        return settingsOk({
          agent_id: 'support',
          new_chat_per_task: false,
          use_suggestions: false,
          command_allowlist: { allow: [], deny: [], ask: [] },
          mcp_tool_grants: [],
          mcp_tool_grants_set: false,
        })
      }),
    )
    await fetchAgentSettings('support')
    expect(loadEnabledPluginToolIds('support')).toEqual(['git_status'])
    await vi.waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === 'PATCH' &&
            JSON.stringify(call.body) === JSON.stringify({ mcp_tool_grants: ['git_status'] }),
        ),
      ).toBe(true)
    })
  })

  it('an explicit empty server grant clears a stale local cache and does not migrate it back', async () => {
    window.localStorage.setItem(
      AGENT_PLUGIN_TOOLS_KEY,
      JSON.stringify({ support: ['git_status'] }),
    )
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = String(init?.method || 'GET').toUpperCase()
        calls.push({ url, method, body: null })
        return settingsOk({
          agent_id: 'support',
          new_chat_per_task: false,
          use_suggestions: false,
          command_allowlist: { allow: [], deny: [], ask: [] },
          mcp_tool_grants: [],
          mcp_tool_grants_set: true,
        })
      }),
    )
    const settings = await fetchAgentSettings('support')
    expect(settings.mcp_tool_grants_set).toBe(true)
    expect(settings.mcp_tool_grants).toEqual([])
    expect(loadEnabledPluginToolIds('support')).toEqual([])
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false)
  })
})
