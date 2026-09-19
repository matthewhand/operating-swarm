import { afterEach, describe, expect, it } from 'vitest'
import {
  AGENT_PLUGIN_TOOLS_KEY,
  FIXTURE_PLUGIN_TOOLS,
  enabledToolsParam,
  filterPluginTools,
  loadEnabledPluginToolIds,
  resolvePluginCatalog,
  saveEnabledPluginToolIds,
  setPluginToolEnabled,
  snapshotPluginToolOrder,
  sortPluginTools,
  toolsFromMcpPlugins,
  visiblePluginTools,
  visiblePluginToolsFrozen,
} from '../chatPluginTools'
import { MCP_SERVERS_KEY } from '../mcpServers'

const zebra = {
  id: 'zebra_tool',
  name: 'Zebra',
  description: 'Last alphabetically when off',
  serverId: 'alpha',
  serverName: 'Alpha',
}
const mid = {
  id: 'mid_tool',
  name: 'Midrange',
  description: 'Middle name',
  serverId: 'beta',
  serverName: 'Beta',
}
const apple = {
  id: 'apple_tool',
  name: 'Apple Fetch',
  description: 'Fetch fruit docs',
  serverId: 'fetch',
  serverName: 'Fetch',
}

describe('plugin tool sort and search', () => {
  it('sorts enabled tools first, then name', () => {
    const sorted = sortPluginTools([zebra, apple, mid], ['zebra_tool'])
    expect(sorted.map((tool) => tool.id)).toEqual(['zebra_tool', 'apple_tool', 'mid_tool'])
  })

  it('keeps enabled-first order inside search matches', () => {
    const visible = visiblePluginTools(
      [zebra, apple, mid],
      'e',
      ['zebra_tool'],
    )
    expect(visible.map((tool) => tool.id)).toEqual(['zebra_tool', 'apple_tool', 'mid_tool'])
  })

  it('freezes snapshot order while filtering even if enablement changes (#278)', () => {
    const snapshot = snapshotPluginToolOrder([zebra, apple, mid], [])
    expect(snapshot).toEqual(['apple_tool', 'mid_tool', 'zebra_tool'])
    const frozen = visiblePluginToolsFrozen([zebra, apple, mid], 'e', snapshot)
    expect(frozen.map((tool) => tool.id)).toEqual(['apple_tool', 'mid_tool', 'zebra_tool'])
    const resorted = visiblePluginTools([zebra, apple, mid], 'e', ['zebra_tool'])
    expect(resorted.map((tool) => tool.id)).toEqual(['zebra_tool', 'apple_tool', 'mid_tool'])
  })

  it('filters by name, description, and server', () => {
    expect(filterPluginTools(FIXTURE_PLUGIN_TOOLS, 'convert').map((t) => t.id)).toEqual([
      'convert_timezone',
    ])
    expect(filterPluginTools(FIXTURE_PLUGIN_TOOLS, 'playwright').length).toBeGreaterThan(1)
    expect(filterPluginTools(FIXTURE_PLUGIN_TOOLS, 'zzzz-nope')).toEqual([])
  })
})

describe('per-agent toggle persist (#516 re-key)', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_PLUGIN_TOOLS_KEY)
    localStorage.removeItem(MCP_SERVERS_KEY)
  })

  it('persists enabled ids for one agent and not another', () => {
    setPluginToolEnabled('agent-a', 'web_search', true)
    setPluginToolEnabled('agent-a', 'web_fetch', true)
    setPluginToolEnabled('agent-b', 'git_status', true)
    expect(loadEnabledPluginToolIds('agent-a')).toEqual(['web_search', 'web_fetch'])
    expect(loadEnabledPluginToolIds('agent-b')).toEqual(['git_status'])
    expect(loadEnabledPluginToolIds('agent-c')).toEqual([])
  })

  it('reloads the same agent allowlist after remount (storage read)', () => {
    saveEnabledPluginToolIds('agent-1', ['read_file', 'git_diff'])
    expect(enabledToolsParam('agent-1')).toEqual({
      enabled_tools: ['read_file', 'git_diff'],
    })
    expect(JSON.parse(localStorage.getItem(AGENT_PLUGIN_TOOLS_KEY) || '{}')['agent-1']).toEqual([
      'read_file',
      'git_diff',
    ])
    expect(loadEnabledPluginToolIds('agent-1')).toEqual(['read_file', 'git_diff'])
  })
})

describe('catalog degrade', () => {
  afterEach(() => {
    localStorage.removeItem(MCP_SERVERS_KEY)
  })

  it('uses the fixture catalog when live discovery is empty', () => {
    const resolved = resolvePluginCatalog({
      skills: [],
      inference: { traits: [], cli_traits: {}, model_traits: {}, model_flags: {} },
      tools: { capabilities: [], mcp_catalog: [] },
    })
    expect(resolved.source).toBe('fixture')
    expect(resolved.tools.map((tool) => tool.id)).toEqual(
      FIXTURE_PLUGIN_TOOLS.map((tool) => tool.id),
    )
  })

  it('prefers live catalog tools and never includes auth env values', () => {
    const resolved = resolvePluginCatalog({
      skills: [],
      inference: { traits: [], cli_traits: {}, model_traits: {}, model_flags: {} },
      tools: {
        capabilities: ['web_search'],
        mcp_catalog: [
          {
            name: 'duckduckgo',
            provides: ['web_search'],
            command: 'uvx',
            args: ['duckduckgo-mcp-server'],
            needs_auth: false,
            auth_env: ['BRAVE_API_KEY'],
            note: 'Non-auth web search.',
          },
        ],
      },
    })
    expect(resolved.source).toBe('live')
    expect(JSON.stringify(resolved.tools)).not.toMatch(/BRAVE|API_KEY|secret/i)
    expect(resolved.tools[0].id).toBe('web_search')
  })

  it('maps discovered MCP plugin tools and skips disabled servers', () => {
    const tools = toolsFromMcpPlugins({
      object: 'mcp_plugins',
      scope: 'global_servers_per_chat_tools',
      servers: [
        {
          name: 'fetch',
          kind: 'local',
          source: 'generic',
          enabled: true,
          command: 'uvx',
          args: ['mcp-server-fetch'],
          url: '',
          env: {},
          headers: {},
          provides: [],
          note: '',
          tools: [{ name: 'fetch', description: 'Fetch a URL' }],
        },
        {
          name: 'time',
          kind: 'local',
          enabled: false,
          command: 'uvx',
          args: ['mcp-server-time'],
          url: '',
          env: {},
          headers: {},
          provides: ['get_current_time'],
          note: '',
          tools: [{ name: 'get_current_time', description: 'Now' }],
        },
      ],
    })
    expect(tools.map((tool) => tool.id)).toEqual(['fetch'])
    expect(JSON.stringify(tools)).not.toMatch(/token|secret|sk-/i)
  })
})
