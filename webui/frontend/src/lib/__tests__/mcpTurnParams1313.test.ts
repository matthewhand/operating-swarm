import { beforeEach, describe, expect, it, vi } from 'vitest'
import { saveEnabledPluginToolIds } from '../chatPluginTools'
import {
  chatTurnToolParams,
  prefetchAgentMcpTools,
  rememberAgentMcpTools,
  resetRememberedMcpTools,
} from '../mcpTurnParams'

describe('live turn mcp_tools params (#1313)', () => {
  beforeEach(() => {
    resetRememberedMcpTools()
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('omits enabled_tools once the bot has a saved map', () => {
    saveEnabledPluginToolIds('worker', ['tool2'])
    rememberAgentMcpTools('worker', { serverA: ['tool1'] })
    expect(chatTurnToolParams('worker')).toEqual({})
  })

  it('still sends the per-chat allowlist when the map is omitted', () => {
    saveEnabledPluginToolIds('worker', ['web_search'])
    rememberAgentMcpTools('worker', {})
    expect(chatTurnToolParams('worker')).toEqual({ enabled_tools: ['web_search'] })
  })

  it('prefetches the record so the next send can omit enabled_tools', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          mcp_mode: 'all',
          mcp_servers: ['serverA'],
          mcp_tools: { serverA: ['tool1'] },
        }),
      }),
    )
    await prefetchAgentMcpTools('worker')
    expect(chatTurnToolParams('worker')).toEqual({})
  })
})
