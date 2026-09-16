import { describe, expect, it } from 'vitest'
import { MCP_SERVER_TEMPLATES } from '../mcpServers'
import {
  COMMUNITY_INSTALL_HINT,
  catalogText,
  envNamesOnly,
  filterCatalogItems,
  installAndProbe,
  itemToServerEntry,
  marketplaceToCatalogItem,
  mergeCatalog,
  safeGithubUrl,
  templateToCatalogItem,
  type InstallCatalogItem,
} from '../installCatalog'

const FETCH_ITEM: InstallCatalogItem = {
  id: 'fetch',
  name: 'Fetch',
  summary: 'Non-auth URL fetch.',
  sourceLabel: 'Shipped',
  sourceKind: 'shipped',
  kind: 'local',
  requiredEnv: ['MCP_TOKEN'],
  toolsProvided: ['web_fetch'],
  dangerNotes: [],
  external: false,
  installable: true,
  installed: false,
  command: 'uvx',
  args: ['mcp-server-fetch'],
}

describe('installCatalog sanitization', () => {
  it('never returns secret-shaped copy or javascript URLs', () => {
    expect(catalogText('use sk-live-secret now')).toBe('')
    expect(catalogText('Authorization Bearer abc')).toBe('')
    expect(catalogText('A cool MCP plugin')).toBe('A cool MCP plugin')
    expect(safeGithubUrl('javascript:alert(1)')).toBeUndefined()
    expect(safeGithubUrl('https://evil.example/alice/cool-mcp')).toBeUndefined()
    expect(safeGithubUrl('https://github.com/alice/cool-mcp')).toBe(
      'https://github.com/alice/cool-mcp',
    )
  })

  it('exposes env names only and drops invalid keys', () => {
    expect(
      envNamesOnly({
        MCP_TOKEN: 'sk-live-do-not-show',
        'not valid': 'x',
        OPENAPI_SPEC_URL: '${OPENAPI_SPEC_URL}',
      }),
    ).toEqual(['MCP_TOKEN', 'OPENAPI_SPEC_URL'])
  })
})

describe('installCatalog mapping', () => {
  it('maps shipped templates and marks already-installed ids', () => {
    const fetch = MCP_SERVER_TEMPLATES.find((row) => row.name === 'Fetch')
    expect(fetch).toBeTruthy()
    const item = templateToCatalogItem(fetch!, new Set(['fetch']))
    expect(item.id).toBe('fetch')
    expect(item.installable).toBe(true)
    expect(item.installed).toBe(true)
    expect(item.toolsProvided).toContain('web_fetch')
    expect(JSON.stringify(item)).not.toMatch(/sk-|bearer /i)
  })

  it('maps GitHub scan rows as community and not installable', () => {
    const item = marketplaceToCatalogItem({
      id: 'alice/cool-mcp',
      name: 'cool-mcp',
      full_name: 'alice/cool-mcp',
      owner: 'alice',
      description: 'A cool MCP plugin',
      html_url: 'https://github.com/alice/cool-mcp',
      stars: 42,
      topics: ['swarm-mcp-plugin'],
      updated_at: '2026-09-01T00:00:00Z',
    })
    expect(item.kind).toBe('community')
    expect(item.stars).toBe(42)
    expect(item.installable).toBe(false)
    expect(item.installHint).toBe(COMMUNITY_INSTALL_HINT)
    expect(item.external).toBe(true)
  })

  it('merges templates, installed leftovers, and marketplace', () => {
    const load = mergeCatalog({
      installed: [
        {
          id: 'custom-proxy',
          name: 'custom-proxy',
          kind: 'remote',
          enabled: true,
          url: 'https://example.invalid/mcp',
          provides: ['search_docs'],
          tools: [],
          env: { MCP_TOKEN: '${MCP_TOKEN}' },
        },
      ],
      marketplace: {
        object: 'marketplace_scan',
        kind: 'plugins',
        topics: ['swarm-mcp-plugin'],
        external: true,
        items: [
          {
            id: 'alice/cool-mcp',
            name: 'cool-mcp',
            full_name: 'alice/cool-mcp',
            owner: 'alice',
            description: 'A cool MCP plugin',
            html_url: 'https://github.com/alice/cool-mcp',
            stars: 7,
            topics: ['swarm-mcp-plugin'],
            updated_at: '',
          },
        ],
        warnings: [],
      },
    })
    expect(load.items.some((row) => row.id === 'fetch')).toBe(true)
    expect(load.items.some((row) => row.id === 'custom-proxy' && row.installed)).toBe(true)
    expect(load.items.some((row) => row.id === 'alice/cool-mcp' && row.stars === 7)).toBe(true)
    expect(JSON.stringify(load)).not.toMatch(/sk-live|Bearer /)
  })
})

describe('installCatalog filter', () => {
  const items: InstallCatalogItem[] = [
    FETCH_ITEM,
    {
      ...FETCH_ITEM,
      id: 'alice/cool-mcp',
      name: 'cool-mcp',
      summary: 'A cool MCP plugin',
      kind: 'community',
      sourceKind: 'github',
      sourceLabel: 'GitHub',
      installable: false,
      installed: false,
      stars: 42,
      requiredEnv: [],
      toolsProvided: [],
    },
    {
      ...FETCH_ITEM,
      id: 'playwright',
      name: 'Playwright',
      summary: 'Local browser tools.',
      installed: true,
      installable: false,
      toolsProvided: ['browser_navigate'],
      requiredEnv: [],
    },
  ]

  it('filters by search and kind', () => {
    expect(filterCatalogItems(items, 'fetch', 'all').map((row) => row.id)).toEqual(['fetch'])
    expect(filterCatalogItems(items, '', 'community').map((row) => row.id)).toEqual([
      'alice/cool-mcp',
    ])
    expect(filterCatalogItems(items, '', 'installed').map((row) => row.id)).toEqual(['playwright'])
    expect(filterCatalogItems(items, 'zzzz', 'all')).toEqual([])
  })
})

describe('installAndProbe', () => {
  it('fails when the payload is not installable', async () => {
    const outcome = await installAndProbe(
      { ...FETCH_ITEM, installable: false, installHint: COMMUNITY_INSTALL_HINT },
      { upsert: async () => ({ object: 'mcp_plugins', scope: '', servers: [] }), discover: async () => ({ object: 'mcp_plugin_tools', name: 'x', kind: 'local', tools: [] }) },
    )
    expect(outcome.status).toBe('fail')
    expect(outcome.message).toBe(COMMUNITY_INSTALL_HINT)
  })

  it('returns fail when upsert throws', async () => {
    const outcome = await installAndProbe(FETCH_ITEM, {
      upsert: async () => {
        throw new Error('mcp refused')
      },
      discover: async () => ({ object: 'mcp_plugin_tools', name: 'fetch', kind: 'local', tools: [] }),
    })
    expect(outcome.status).toBe('fail')
    expect(outcome.message).toMatch(/mcp refused/)
  })

  it('returns ok + down when saved but connect check fails', async () => {
    const outcome = await installAndProbe(FETCH_ITEM, {
      upsert: async () => ({ object: 'mcp_plugins', scope: '', servers: [] }),
      discover: async () => {
        throw new Error('refused connect')
      },
    })
    expect(outcome.status).toBe('ok')
    expect(outcome.health).toBe('down')
    expect(outcome.message).toMatch(/could not connect/i)
  })

  it('returns ok + up after a successful connect check', async () => {
    const outcome = await installAndProbe(FETCH_ITEM, {
      upsert: async (body) => {
        expect(JSON.stringify(body)).not.toMatch(/sk-|Bearer /)
        return { object: 'mcp_plugins', scope: '', servers: [] }
      },
      discover: async () => ({
        object: 'mcp_plugin_tools',
        name: 'fetch',
        kind: 'local',
        tools: [{ name: 'web_fetch', description: 'Fetch a URL' }],
      }),
    })
    expect(outcome.status).toBe('ok')
    expect(outcome.health).toBe('up')
    expect(outcome.message).toMatch(/1 tool/)
  })

  it('stores env as ${VAR} placeholders only', () => {
    const entry = itemToServerEntry(FETCH_ITEM)
    expect(entry?.env).toEqual({ MCP_TOKEN: '${MCP_TOKEN}' })
    expect(JSON.stringify(entry)).not.toMatch(/sk-live/)
  })
})
