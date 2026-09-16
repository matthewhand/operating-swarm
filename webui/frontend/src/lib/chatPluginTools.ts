/**
 * Per-chat plugin tool enablement (#805).
 *
 * Toggles persist in the document store (localStorage chat prefs) keyed by
 * conversation/session id — not Neon. Default is opt-in (Off) for the
 * current chat.
 *
 * Catalog priority: GET /v1/mcp-plugins/ discovered tools (#502 live), then
 * /v1/config-options mcp_catalog, then localStorage configured servers, then
 * the shipped fixture. No secrets are stored or shown.
 */

import {
  fetchConfigOptions,
  fetchMcpPlugins,
  type ConfigOptions,
  type McpPluginsPayload,
} from './api'
import { loadConfiguredMcpServers, serversFromApi } from './mcpServers'

export const CHAT_PLUGIN_TOOLS_KEY = 'swarm_chat_plugin_tools'
export const CHAT_PLUGIN_TOOLS_EVENT = 'swarm:chat-plugin-tools'

export type PluginCatalogSource = 'live' | 'configured' | 'fixture'

export interface PluginTool {
  id: string
  name: string
  description: string
  serverId: string
  serverName: string
}

/** Shipped catalog used when MCP discovery is not live yet (#502 / #805). */
export const FIXTURE_PLUGIN_TOOLS: PluginTool[] = [
  {
    id: 'web_search',
    name: 'Web Search',
    description: 'Search the public web without an API key.',
    serverId: 'duckduckgo',
    serverName: 'DuckDuckGo',
  },
  {
    id: 'web_fetch',
    name: 'Web Fetch',
    description: 'Fetch and read a URL.',
    serverId: 'fetch',
    serverName: 'Fetch',
  },
  {
    id: 'browser_navigate',
    name: 'Browser Navigate',
    description: 'Open a page in a local browser.',
    serverId: 'playwright',
    serverName: 'Playwright',
  },
  {
    id: 'browser_snapshot',
    name: 'Browser Snapshot',
    description: 'Read the current page accessibility tree.',
    serverId: 'playwright',
    serverName: 'Playwright',
  },
  {
    id: 'browser_click',
    name: 'Browser Click',
    description: 'Click an element on the current page.',
    serverId: 'playwright',
    serverName: 'Playwright',
  },
  {
    id: 'browser_type',
    name: 'Browser Type',
    description: 'Type text into a focused field.',
    serverId: 'playwright',
    serverName: 'Playwright',
  },
  {
    id: 'read_file',
    name: 'Read File',
    description: 'Read a file under the allowed path.',
    serverId: 'filesystem',
    serverName: 'Filesystem',
  },
  {
    id: 'write_file',
    name: 'Write File',
    description: 'Write a file under the allowed path.',
    serverId: 'filesystem',
    serverName: 'Filesystem',
  },
  {
    id: 'list_directory',
    name: 'List Directory',
    description: 'List files in a scoped folder.',
    serverId: 'filesystem',
    serverName: 'Filesystem',
  },
  {
    id: 'git_status',
    name: 'Git Status',
    description: 'Show the working tree status.',
    serverId: 'git',
    serverName: 'Git',
  },
  {
    id: 'git_diff',
    name: 'Git Diff',
    description: 'Show unstaged and staged diffs.',
    serverId: 'git',
    serverName: 'Git',
  },
  {
    id: 'git_log',
    name: 'Git Log',
    description: 'List recent commits.',
    serverId: 'git',
    serverName: 'Git',
  },
  {
    id: 'get_current_time',
    name: 'Current Time',
    description: 'Return the current time and timezone.',
    serverId: 'time',
    serverName: 'Time',
  },
  {
    id: 'convert_timezone',
    name: 'Convert Timezone',
    description: 'Convert a timestamp between timezones.',
    serverId: 'time',
    serverName: 'Time',
  },
]

export function filterPluginTools(tools: readonly PluginTool[], query: string): PluginTool[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...tools]
  return tools.filter((tool) => {
    return (
      tool.name.toLowerCase().includes(q) ||
      tool.description.toLowerCase().includes(q) ||
      tool.serverName.toLowerCase().includes(q) ||
      tool.id.toLowerCase().includes(q)
    )
  })
}

/** Enabled first, then Off; stable secondary sort by name. */
export function sortPluginTools(
  tools: readonly PluginTool[],
  enabledIds: ReadonlySet<string> | readonly string[],
): PluginTool[] {
  const enabled = enabledIds instanceof Set ? enabledIds : new Set(enabledIds)
  return [...tools].sort((a, b) => {
    const aOn = enabled.has(a.id)
    const bOn = enabled.has(b.id)
    if (aOn !== bOn) return aOn ? -1 : 1
    return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  })
}

export function visiblePluginTools(
  tools: readonly PluginTool[],
  query: string,
  enabledIds: ReadonlySet<string> | readonly string[],
): PluginTool[] {
  return sortPluginTools(filterPluginTools(tools, query), enabledIds)
}

/** Enabled-first ids captured when the Plugins popup opens or the catalog loads. */
export function snapshotPluginToolOrder(
  tools: readonly PluginTool[],
  enabledIds: ReadonlySet<string> | readonly string[],
): string[] {
  return sortPluginTools(tools, enabledIds).map((tool) => tool.id)
}

/**
 * Filter matches while keeping a frozen row order (#278).
 * Tools not in the snapshot are appended in filtered catalog order.
 */
export function visiblePluginToolsFrozen(
  tools: readonly PluginTool[],
  query: string,
  orderIds: readonly string[],
): PluginTool[] {
  const filtered = filterPluginTools(tools, query)
  if (orderIds.length === 0) return filtered
  const byId = new Map(filtered.map((tool) => [tool.id, tool]))
  const ordered: PluginTool[] = []
  const seen = new Set<string>()
  for (const id of orderIds) {
    const tool = byId.get(id)
    if (!tool) continue
    ordered.push(tool)
    seen.add(id)
  }
  for (const tool of filtered) {
    if (seen.has(tool.id)) continue
    ordered.push(tool)
  }
  return ordered
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

export function loadChatPluginPrefs(): Record<string, string[]> {
  try {
    const raw = localStorage.getItem(CHAT_PLUGIN_TOOLS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: Record<string, string[]> = {}
    for (const [chatId, ids] of Object.entries(parsed as Record<string, unknown>)) {
      if (chatId && isStringArray(ids)) {
        out[chatId] = [...new Set(ids.filter(Boolean))]
      }
    }
    return out
  } catch {
    return {}
  }
}

export function loadEnabledPluginToolIds(chatId: string): string[] {
  const key = String(chatId || '').trim()
  if (!key) return []
  return loadChatPluginPrefs()[key] ?? []
}

export function saveEnabledPluginToolIds(chatId: string, ids: readonly string[]): string[] {
  const key = String(chatId || '').trim()
  const unique = [...new Set(ids.filter((id) => typeof id === 'string' && id))]
  if (!key) return unique
  const all = loadChatPluginPrefs()
  all[key] = unique
  try {
    localStorage.setItem(CHAT_PLUGIN_TOOLS_KEY, JSON.stringify(all))
  } catch {
    /* private mode */
  }
  try {
    window.dispatchEvent(
      new CustomEvent(CHAT_PLUGIN_TOOLS_EVENT, { detail: { chatId: key, enabled: unique } }),
    )
  } catch {
    /* jsdom / SSR */
  }
  return unique
}

export function setPluginToolEnabled(chatId: string, toolId: string, enabled: boolean): string[] {
  const current = new Set(loadEnabledPluginToolIds(chatId))
  if (enabled) current.add(toolId)
  else current.delete(toolId)
  return saveEnabledPluginToolIds(chatId, [...current])
}

export function isPluginToolEnabled(chatId: string, toolId: string): boolean {
  return loadEnabledPluginToolIds(chatId).includes(toolId)
}

/** WS/chat params: On tools the agent may call; Off are omitted. */
export function enabledToolsParam(chatId: string): { enabled_tools: string[] } {
  return { enabled_tools: loadEnabledPluginToolIds(chatId) }
}

function titleCase(value: string): string {
  return value
    .split(/[_-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function toolsFromCatalogEntry(entry: ConfigOptions['tools']['mcp_catalog'][number]): PluginTool[] {
  const serverId = String(entry.name || '').trim()
  if (!serverId) return []
  const serverName = titleCase(serverId)
  const provides = Array.isArray(entry.provides) ? entry.provides : []
  if (provides.length === 0) {
    return [
      {
        id: serverId,
        name: serverName,
        description: String(entry.note || '').trim() || `${serverName} tools`,
        serverId,
        serverName,
      },
    ]
  }
  return provides.map((cap) => {
    const id = String(cap || '').trim()
    const fixture = FIXTURE_PLUGIN_TOOLS.find((tool) => tool.id === id || tool.serverId === serverId)
    return {
      id: id || serverId,
      name: fixture?.name || titleCase(id || serverId),
      description: String(entry.note || '').trim() || fixture?.description || `${serverName} capability`,
      serverId,
      serverName,
    }
  })
}

function mergeTools(groups: PluginTool[][]): PluginTool[] {
  const byId = new Map<string, PluginTool>()
  for (const group of groups) {
    for (const tool of group) {
      if (!tool.id || byId.has(tool.id)) continue
      byId.set(tool.id, tool)
    }
  }
  return [...byId.values()]
}

export function toolsFromConfigOptions(options: ConfigOptions | null | undefined): PluginTool[] {
  const catalog = options?.tools?.mcp_catalog
  if (!Array.isArray(catalog) || catalog.length === 0) return []
  return mergeTools(catalog.map(toolsFromCatalogEntry))
}

export function toolsFromConfiguredServers(): PluginTool[] {
  return loadConfiguredMcpServers()
    .filter((server) => server.enabled !== false)
    .flatMap((server) => {
    const discovered = server.tools && server.tools.length > 0
      ? server.tools.map((tool) => ({
          id: tool.name,
          name: titleCase(tool.name),
          description: tool.description || server.note || `${server.name} tool`,
          serverId: server.id,
          serverName: server.name,
        }))
      : []
    if (discovered.length > 0) return discovered
    if (server.provides.length > 0) {
      return server.provides.map((cap) => ({
        id: cap,
        name: titleCase(cap),
        description: server.note || `${server.name} capability`,
        serverId: server.id,
        serverName: server.name,
      }))
    }
    return [
      {
        id: `${server.id}:tools`,
        name: server.name,
        description: server.note || 'Configured MCP server',
        serverId: server.id,
        serverName: server.name,
      },
    ]
  })
}

export function toolsFromMcpPlugins(payload: McpPluginsPayload | null | undefined): PluginTool[] {
  if (!payload) return []
  const cached = serversFromApi(payload)
  if (cached.length === 0) return []
  return cached
    .filter((server) => server.enabled !== false)
    .flatMap((server) => {
      if (server.tools.length > 0) {
        return server.tools.map((tool) => ({
          id: tool.name,
          name: titleCase(tool.name),
          description: tool.description || server.note || `${server.name} tool`,
          serverId: server.id,
          serverName: server.name,
        }))
      }
      return server.provides.map((cap) => ({
        id: cap,
        name: titleCase(cap),
        description: server.note || `${server.name} capability`,
        serverId: server.id,
        serverName: server.name,
      }))
    })
}

export interface ResolvedPluginCatalog {
  tools: PluginTool[]
  source: PluginCatalogSource
}

/**
 * Prefer live / configured discovery. Fall back to the fixture catalog so
 * toggle, sort, and search stay real when MCP list_tools is not connected.
 */
export function resolvePluginCatalog(options?: ConfigOptions | null): ResolvedPluginCatalog {
  const live = toolsFromConfigOptions(options)
  if (live.length > 0) return { tools: live, source: 'live' }
  const configured = toolsFromConfiguredServers()
  if (configured.length > 0) return { tools: configured, source: 'configured' }
  return { tools: FIXTURE_PLUGIN_TOOLS, source: 'fixture' }
}

export async function loadPluginCatalog(): Promise<ResolvedPluginCatalog> {
  try {
    const plugins = await fetchMcpPlugins()
    const live = toolsFromMcpPlugins(plugins)
    if (live.length > 0) return { tools: live, source: 'live' }
  } catch {
    /* fall through to config-options / fixture */
  }
  try {
    const options = await fetchConfigOptions()
    return resolvePluginCatalog(options)
  } catch {
    return resolvePluginCatalog(null)
  }
}
