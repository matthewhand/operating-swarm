import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  PluginPackClientError,
  displayTextIsSafe,
  parsePackInput,
  publicPackJson,
  publicStatusFromPayload,
  refuseSecrets,
  validatePack,
} from '../agentPluginPack'

const FIXTURE = join(process.cwd(), '../../tests/fixtures/agent_plugin_pack.json')

describe('#1397 agent plugin pack helpers (ids only, no tokens)', () => {
  it('parses the secret-free fixture and serializes ids only', () => {
    const raw = JSON.parse(readFileSync(FIXTURE, 'utf8'))
    const pack = validatePack(raw)
    expect(pack.plugins.map((row) => row.pluginId)).toEqual([
      'mcp:io.github.example/fetch',
      'web_search',
    ])
    const json = publicPackJson(pack)
    expect(json).toContain('web_search')
    expect(json).not.toMatch(/\"token\"|\"url\"|\"command\"|\"headers\"|sk-|bearer /i)
  })

  it('parses loose plugin ids from a textarea', () => {
    const pack = parsePackInput('web_search\nfetch, github-mcp')
    expect(pack.plugins.map((row) => row.pluginId)).toEqual(['web_search', 'fetch', 'github-mcp'])
  })

  it('refuses url, command, and credential-shaped values without echoing them', () => {
    expect(() =>
      parsePackInput(
        JSON.stringify({
          plugins: [
            {
              pluginId: 'leaky',
              url: 'https://example.invalid/mcp',
              headers: { Authorization: 'Bearer sk-notarealkeyABCDEFGH' },
            },
          ],
        }),
      ),
    ).toThrow(PluginPackClientError)
    try {
      refuseSecrets({ token: 'sk-notarealkeyABCDEFGH' }, 'pack')
      throw new Error('expected refuseSecrets to throw')
    } catch (err) {
      expect(err).toBeInstanceOf(PluginPackClientError)
      expect(String(err)).not.toContain('sk-notarealkeyABCDEFGH')
      expect((err as PluginPackClientError).code).toBe('plugin_pack_secrets')
    }
  })

  it('strips leaked tokens from a status payload before the UI can render them', () => {
    const safe = publicStatusFromPayload({
      object: 'agent_plugins',
      agent_id: 'worker',
      plugins: [
        {
          pluginId: 'fetch',
          name: 'fetch',
          description: 'Fetch a URL',
          status: 'enabled',
          token: 'sk-leakedSECRETVALUE',
          url: 'https://evil.example/mcp',
          command: 'uvx',
          required_env: ['GITHUB_TOKEN', 'API_KEY=sk-notarealkeyABCDEFGH'],
        },
      ],
      enabled: ['fetch', 'sk-leakedSECRETVALUE'],
      missing: [],
    })
    expect(safe).not.toBeNull()
    const dumped = JSON.stringify(safe)
    expect(dumped).not.toContain('sk-leakedSECRETVALUE')
    expect(dumped).not.toContain('https://evil.example/mcp')
    expect(dumped).not.toContain('uvx')
    expect(safe?.plugins[0].required_env).toEqual(['GITHUB_TOKEN'])
    expect(safe?.enabled).toEqual(['fetch'])
    expect(displayTextIsSafe(dumped)).toBe(true)
  })
})
