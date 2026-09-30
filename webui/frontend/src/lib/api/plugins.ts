/** #856 slice A — plugins endpoints (moved verbatim from lib/api.ts). */
import {
  apiDelete,
  apiGet,
  apiPost,
} from './client'
import type {
  AgentPluginPack,
  AgentPluginsStatus,
  McpPluginDiscoverPayload,
  McpPluginsPayload,
} from './types'

function agentPluginsPath(agentId: string, suffix = ''): string {
  const id = encodeURIComponent(agentId.trim())
  return `/v1/agents/${id}/plugins/${suffix}`
}

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

/** GET /v1/agents/<id>/plugins/ — packed ids + host status, no tokens (#1397). */
export function fetchAgentPlugins(agentId: string): Promise<AgentPluginsStatus> {
  return apiGet<AgentPluginsStatus>(agentPluginsPath(agentId))
}

/** GET /v1/agents/<id>/plugins/pack/ — secret-free pack fragment. */
export function fetchAgentPluginPack(agentId: string): Promise<AgentPluginPack> {
  return apiGet<AgentPluginPack>(agentPluginsPath(agentId, 'pack/'))
}

/** POST /v1/agents/<id>/plugins/import/ — persist ids; status without tokens. */
export function importAgentPluginPack(
  agentId: string,
  body: unknown,
): Promise<AgentPluginsStatus> {
  return apiPost<AgentPluginsStatus>(agentPluginsPath(agentId, 'import/'), body)
}
