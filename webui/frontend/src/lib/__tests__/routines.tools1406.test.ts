import { describe, expect, it } from 'vitest'
import {
  TOOL_OPEN_PULL_REQUEST,
  addRoutineTool,
  extraRoutineTools,
  removeRoutineTool,
  toggleOpenPullRequestTool,
} from '../routines'
import {
  fallbackRoutineToolCatalog,
  filterRoutineToolCatalog,
  mergeRoutineToolCatalog,
  scrubCatalogReason,
} from '../routineToolCatalog'

describe('routine extra tools (#1406)', () => {
  it('adds and removes catalog ids without dropping Open PR', () => {
    const withSearch = addRoutineTool([TOOL_OPEN_PULL_REQUEST], 'web_search')
    expect(withSearch).toEqual([TOOL_OPEN_PULL_REQUEST, 'web_search'])
    expect(extraRoutineTools(withSearch)).toEqual(['web_search'])
    expect(removeRoutineTool(withSearch, 'web_search')).toEqual([TOOL_OPEN_PULL_REQUEST])
    expect(toggleOpenPullRequestTool(['web_search'], true)).toEqual([
      TOOL_OPEN_PULL_REQUEST,
      'web_search',
    ])
  })

  it('does not duplicate an already-selected tool', () => {
    expect(addRoutineTool(['web_search'], 'web_search')).toEqual(['web_search'])
  })

  it('scrubs token-shaped catalog reasons', () => {
    expect(scrubCatalogReason('Needs BRAVE_API_KEY')).toBe('Needs BRAVE_API_KEY')
    expect(scrubCatalogReason('use ghp_notarealtokenhere')).toBe(
      'This connector needs configuration in Settings → Plugins.',
    )
  })

  it('merges backend catalog with plugin fixture and keeps disabled reasons', () => {
    const merged = mergeRoutineToolCatalog(
      [
        {
          id: 'brave_search',
          label: 'Brave Search',
          description: 'Needs a key',
          kind: 'mcp',
          source: 'mcp_catalog',
          server_id: 'brave_search',
          server_name: 'Brave Search',
          wired: false,
          available: false,
          reason: 'Needs BRAVE_API_KEY — set it in Settings → Plugins. Tokens stay out of this builder.',
        },
      ],
      [{ id: 'web_search', name: 'Web Search', description: 'Search', serverId: 'duckduckgo', serverName: 'DuckDuckGo' }],
      'live',
    )
    const byId = Object.fromEntries(merged.map((item) => [item.id, item]))
    expect(byId.web_search.available).toBe(true)
    expect(byId.brave_search.available).toBe(false)
    expect(byId.brave_search.reason).toContain('BRAVE_API_KEY')
    expect(byId[TOOL_OPEN_PULL_REQUEST]).toBeTruthy()
  })

  it('scrubs token-shaped labels and descriptions from the backend catalog', () => {
    const merged = mergeRoutineToolCatalog(
      [
        {
          id: 'acme_search',
          label: 'use ghp_notarealtokenhere',
          description: 'prefix ghp_notarealtokenhere',
          kind: 'plugin',
          source: 'mcp_plugins',
          server_id: 'acme',
          server_name: 'Acme',
          wired: true,
          available: true,
          reason: '',
        },
      ],
      [],
    )
    const row = merged.find((item) => item.id === 'acme_search')
    expect(row?.label).toBe('This connector needs configuration in Settings → Plugins.')
    expect(row?.description).toBe('This connector needs configuration in Settings → Plugins.')
    expect(JSON.stringify(row)).not.toContain('ghp_')
  })

  it('filters picker rows by query', () => {
    const rows = filterRoutineToolCatalog(fallbackRoutineToolCatalog(), 'brave')
    expect(rows.some((item) => item.id === 'brave_search')).toBe(true)
    expect(rows.every((item) => item.label.toLowerCase().includes('brave') || item.id.includes('brave'))).toBe(true)
  })
})
