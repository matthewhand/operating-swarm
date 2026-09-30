/**
 * Live chat turns and the persisted `mcp_tools` map (#1313).
 *
 * A bot with a saved map must not send `enabled_tools`. That list used to
 * replace the grant on the server, so a turn attached the browser cache
 * instead of the tools checked in Agent Editor.
 */
import { enabledToolsParam } from './chatPluginTools'
import { fetchAgentMcp, grantEnablesAny, type McpToolsMap } from './agentMcp'

const remembered = new Map<string, McpToolsMap>()

export function rememberAgentMcpTools(agentId: string, map: McpToolsMap): void {
  const id = agentId.trim()
  if (!id) return
  remembered.set(id, map)
}

export function rememberedMcpTools(agentId: string): McpToolsMap | undefined {
  return remembered.get(agentId.trim())
}

/** Test helper. */
export function resetRememberedMcpTools(): void {
  remembered.clear()
}

export function chatTurnToolParams(agentId: string): { enabled_tools: string[] } | Record<string, never> {
  const map = remembered.get(agentId.trim())
  if (map && (grantEnablesAny(map) || Object.keys(map).length > 0)) {
    return {}
  }
  return enabledToolsParam(agentId)
}

export async function prefetchAgentMcpTools(agentId: string): Promise<void> {
  const id = agentId.trim()
  if (!id || remembered.has(id)) return
  try {
    const record = await fetchAgentMcp(id)
    remembered.set(id, record.mcp_tools)
  } catch {
    // Unknown record: keep the per-chat allowlist. The server still enforces
    // a saved map when this frame includes enabled_tools.
  }
}
