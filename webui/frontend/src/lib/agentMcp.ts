/** Per-bot MCP tool grants (#1313).

`mcp_tools` lives on the agent MCP record: `{ server: ["tool", ...] | "*" }`.
The editor checkbox tree is pre-checked from that record against the plugin
catalog (the same tools `catalog_tools` would expose).
*/
import { apiGet, apiPatch } from './api/client'

export type McpToolGrant = '*' | string[]
export type McpToolsMap = Record<string, McpToolGrant>

export interface AgentMcpRecord {
  mcp_mode: string
  mcp_servers: string[]
  mcp_tools: McpToolsMap
}

export interface CatalogTool {
  name: string
  description: string
}

export interface CatalogServer {
  name: string
  tools: CatalogTool[]
}

export function toolKey(server: string, tool: string): string {
  return `${server}\u0000${tool}`
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const item of value) {
    if (typeof item !== 'string') continue
    const name = item.trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}

export function parseMcpTools(raw: unknown): McpToolsMap {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: McpToolsMap = {}
  for (const [server, entry] of Object.entries(raw as Record<string, unknown>)) {
    const name = server.trim()
    if (!name) continue
    if (entry === '*') {
      out[name] = '*'
      continue
    }
    if (Array.isArray(entry)) out[name] = stringList(entry)
  }
  return out
}

export function parseAgentMcp(raw: unknown): AgentMcpRecord {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const mode = typeof row.mcp_mode === 'string' ? row.mcp_mode : typeof row.mode === 'string' ? row.mode : 'off'
  return {
    mcp_mode: mode,
    mcp_servers: stringList(row.mcp_servers),
    mcp_tools: parseMcpTools(row.mcp_tools),
  }
}

export function parseCatalogServers(raw: unknown): CatalogServer[] {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const servers = Array.isArray(row.servers) ? row.servers : []
  const out: CatalogServer[] = []
  for (const item of servers) {
    if (!item || typeof item !== 'object') continue
    const server = item as Record<string, unknown>
    if (server.enabled === false) continue
    const name = typeof server.name === 'string' ? server.name.trim() : ''
    if (!name) continue
    const tools: CatalogTool[] = []
    const seen = new Set<string>()
    const listed = Array.isArray(server.tools) ? server.tools : []
    for (const tool of listed) {
      if (!tool || typeof tool !== 'object') continue
      const toolName = typeof (tool as { name?: unknown }).name === 'string' ? (tool as { name: string }).name.trim() : ''
      if (!toolName || seen.has(toolName)) continue
      seen.add(toolName)
      const description =
        typeof (tool as { description?: unknown }).description === 'string'
          ? (tool as { description: string }).description
          : ''
      tools.push({ name: toolName, description })
    }
    for (const cap of stringList(server.provides)) {
      if (seen.has(cap)) continue
      seen.add(cap)
      tools.push({ name: cap, description: '' })
    }
    out.push({ name, tools })
  }
  return out
}

/** Checked boxes for the tree. An omitted map uses server-level selection. */
export function isToolPrechecked(record: AgentMcpRecord, server: string, tool: string): boolean {
  const keys = Object.keys(record.mcp_tools)
  if (keys.length > 0) {
    const entry = record.mcp_tools[server]
    if (entry === undefined) return false
    if (entry === '*') return true
    return entry.includes(tool)
  }
  if (record.mcp_mode === 'off') return false
  if (record.mcp_servers.length === 0) return true
  return record.mcp_servers.includes(server)
}

export function checkedKeysForRecord(record: AgentMcpRecord, catalog: readonly CatalogServer[]): Set<string> {
  const checked = new Set<string>()
  for (const server of catalog) {
    for (const tool of server.tools) {
      if (isToolPrechecked(record, server.name, tool.name)) {
        checked.add(toolKey(server.name, tool.name))
      }
    }
  }
  return checked
}

/**
 * Checked tools become the saved map.
 * A server with every tool checked collapses to `"*"`.
 * A server the operator cleared stays as `[]` so the next turn detaches those tools.
 * A server that was never in the map and has nothing checked stays omitted, so an
 * untouched connector keeps server-level behaviour.
 */
export function mcpToolsFromChecked(
  catalog: readonly CatalogServer[],
  checked: ReadonlySet<string>,
  previous: McpToolsMap = {},
): McpToolsMap {
  const out: McpToolsMap = {}
  for (const server of catalog) {
    const names = server.tools.map((tool) => tool.name).filter((name) => checked.has(toolKey(server.name, name)))
    if (server.tools.length > 0 && names.length === server.tools.length) out[server.name] = '*'
    else if (names.length > 0) out[server.name] = names
    else if (Object.prototype.hasOwnProperty.call(previous, server.name)) out[server.name] = []
  }
  return out
}

export function grantEnablesAny(map: McpToolsMap): boolean {
  return Object.values(map).some((entry) => entry === '*' || entry.length > 0)
}

export async function fetchAgentMcp(agentId: string): Promise<AgentMcpRecord> {
  const data = await apiGet<unknown>(`/v1/agents/${encodeURIComponent(agentId)}/mcp/`)
  return parseAgentMcp(data)
}

export async function patchAgentMcp(
  agentId: string,
  patch: { mcp_tools: McpToolsMap; mcp_mode?: string },
): Promise<AgentMcpRecord> {
  const data = await apiPatch<unknown>(`/v1/agents/${encodeURIComponent(agentId)}/mcp/`, patch)
  return parseAgentMcp(data)
}
