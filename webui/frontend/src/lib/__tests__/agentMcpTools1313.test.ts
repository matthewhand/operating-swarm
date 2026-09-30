import { describe, expect, it } from 'vitest'
import {
  checkedKeysForRecord,
  isToolPrechecked,
  mcpToolsFromChecked,
  parseAgentMcp,
  parseCatalogServers,
  toolKey,
  type CatalogServer,
} from '../agentMcp'

const catalog: CatalogServer[] = [
  {
    name: 'serverA',
    tools: [
      { name: 'tool1', description: 'one' },
      { name: 'tool2', description: 'two' },
    ],
  },
]

describe('mcp_tools checkbox tree (#1313)', () => {
  it('pre-checks only the granted tool from the catalog', () => {
    const record = parseAgentMcp({
      mcp_mode: 'all',
      mcp_servers: ['serverA'],
      mcp_tools: { serverA: ['tool1'] },
    })
    expect(isToolPrechecked(record, 'serverA', 'tool1')).toBe(true)
    expect(isToolPrechecked(record, 'serverA', 'tool2')).toBe(false)
    const checked = checkedKeysForRecord(record, catalog)
    expect(checked.has(toolKey('serverA', 'tool1'))).toBe(true)
    expect(checked.has(toolKey('serverA', 'tool2'))).toBe(false)
  })

  it('treats * as every catalog tool on that server', () => {
    const record = parseAgentMcp({ mcp_mode: 'all', mcp_tools: { serverA: '*' } })
    expect(isToolPrechecked(record, 'serverA', 'tool1')).toBe(true)
    expect(isToolPrechecked(record, 'serverA', 'tool2')).toBe(true)
    expect(mcpToolsFromChecked(catalog, checkedKeysForRecord(record, catalog))).toEqual({
      serverA: '*',
    })
  })

  it('omitted map pre-checks the server-level selection', () => {
    const record = parseAgentMcp({ mcp_mode: 'all', mcp_servers: ['serverA'], mcp_tools: {} })
    expect(isToolPrechecked(record, 'serverA', 'tool2')).toBe(true)
    const off = parseAgentMcp({ mcp_mode: 'off' })
    expect(isToolPrechecked(off, 'serverA', 'tool1')).toBe(false)
  })

  it('writes only the server the operator touched', () => {
    const wider: CatalogServer[] = [
      ...catalog,
      { name: 'serverB', tools: [{ name: 'tool3', description: 'three' }] },
    ]
    const checked = new Set([toolKey('serverA', 'tool1')])
    expect(mcpToolsFromChecked(wider, checked)).toEqual({ serverA: ['tool1'] })
  })

  it('keeps an explicit empty list when a granted server is cleared', () => {
    const checked = new Set<string>()
    expect(mcpToolsFromChecked(catalog, checked, { serverA: ['tool1'] })).toEqual({ serverA: [] })
  })

  it('reads a plugins catalog payload into servers', () => {
    const servers = parseCatalogServers({
      object: 'mcp_plugins',
      servers: [
        {
          name: 'serverA',
          enabled: true,
          tools: [{ name: 'tool1', description: 'one' }],
          provides: ['tool1', 'extra'],
        },
      ],
    })
    expect(servers[0]?.tools.map((tool) => tool.name)).toEqual(['tool1', 'extra'])
  })
})
