/** #856 slice A — plugins endpoints (moved verbatim from lib/api.ts). */
import {
  apiDelete,
  apiGet,
  apiPost,
} from './client'
import type {
  McpPluginDiscoverPayload,
  McpPluginsPayload,
} from './types'

export function fetchMcpPlugins(): Promise<McpPluginsPayload> {
  return apiGet<McpPluginsPayload>('/v1/mcp-plugins/')
}
export function upsertMcpPlugin(body: Record<string, unknown>): Promise<McpPluginsPayload> {
  return apiPost<McpPluginsPayload>('/v1/mcp-plugins/', body)
}
export async function deleteMcpPlugin(name: string): Promise<McpPluginsPayload> {
  await apiDelete(`/v1/mcp-plugins/${encodeURIComponent(name)}/`)
  return fetchMcpPlugins()
}
export function discoverMcpPluginTools(
  body: Record<string, unknown>,
): Promise<McpPluginDiscoverPayload> {
  return apiPost<McpPluginDiscoverPayload>('/v1/mcp-plugins/discover/', body)
}
