import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchAgentPluginPack, fetchAgentPlugins, importAgentPluginPack } from '../api'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('#1397 plugin pack API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('GETs status and pack, POSTs import, and never sends tokens', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url === '/v1/agents/worker/plugins/' && method === 'GET') {
        return jsonResponse({
          object: 'agent_plugins',
          agent_id: 'worker',
          plugins: [{ pluginId: 'web_search', name: 'web_search', description: '', status: 'enabled' }],
          enabled: ['web_search'],
          missing: [],
        })
      }
      if (url === '/v1/agents/worker/plugins/pack/' && method === 'GET') {
        return jsonResponse({
          object: 'agent_plugin_pack',
          schema: 1,
          kind: 'agent_plugin_pack',
          plugins: [{ pluginId: 'web_search', name: 'web_search', description: '' }],
        })
      }
      if (url === '/v1/agents/worker/plugins/import/' && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        expect(JSON.stringify(body)).not.toMatch(/sk-|token|bearer |url|command/i)
        return jsonResponse({
          object: 'agent_plugin_pack_import',
          agent_id: 'worker',
          plugins: [
            { pluginId: 'web_search', name: 'web_search', description: '', status: 'enabled' },
            { pluginId: 'unknown-plugin-id', name: 'unknown-plugin-id', description: '', status: 'missing' },
          ],
          enabled: ['web_search'],
          missing: ['unknown-plugin-id'],
        })
      }
      throw new Error(`unexpected ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const listed = await fetchAgentPlugins('worker')
    expect(listed.object).toBe('agent_plugins')
    expect(listed.enabled).toEqual(['web_search'])

    const pack = await fetchAgentPluginPack('worker')
    expect(pack.object).toBe('agent_plugin_pack')
    expect(pack.plugins[0].pluginId).toBe('web_search')

    const imported = await importAgentPluginPack('worker', {
      plugins: [{ pluginId: 'web_search' }, { pluginId: 'unknown-plugin-id' }],
    })
    expect(imported.missing).toEqual(['unknown-plugin-id'])
    expect(JSON.stringify(imported)).not.toMatch(/sk-|bearer /i)
  })
})
