import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchMcpPlugins } from '../lib/api'
import { useOptionalToast } from './DaisyUI'
import {
  checkedKeysForRecord,
  fetchAgentMcp,
  grantEnablesAny,
  mcpToolsFromChecked,
  parseCatalogServers,
  patchAgentMcp,
  toolKey,
  type AgentMcpRecord,
  type CatalogServer,
} from '../lib/agentMcp'
import { rememberAgentMcpTools } from '../lib/mcpTurnParams'

export interface AgentMcpToolTreeProps {
  agentId: string
  /** Fetch only while the Advanced panel is the selected tab. */
  active: boolean
}

/**
 * Per-server checkbox tree for persistent `mcp_tools` (#1313).
 * Boxes are pre-checked from the saved grant against the connector catalog.
 */
export default function AgentMcpToolTree({ agentId, active }: AgentMcpToolTreeProps) {
  const toast = useOptionalToast()
  const mcpQuery = useQuery({
    queryKey: ['agent-mcp', agentId],
    queryFn: () => fetchAgentMcp(agentId),
    enabled: active && Boolean(agentId),
    retry: 1,
  })
  const pluginsQuery = useQuery({
    queryKey: ['mcp-plugins-catalog'],
    queryFn: () => fetchMcpPlugins(),
    enabled: active && Boolean(agentId),
    retry: 1,
  })
  const catalog: CatalogServer[] = useMemo(
    () => parseCatalogServers(pluginsQuery.data),
    [pluginsQuery.data],
  )
  const [checked, setChecked] = useState<Set<string>>(() => new Set())
  const [hydrated, setHydrated] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setHydrated(false)
    setChecked(new Set())
  }, [agentId])

  useEffect(() => {
    if (!mcpQuery.data || hydrated) return
    rememberAgentMcpTools(agentId, mcpQuery.data.mcp_tools)
    setChecked(checkedKeysForRecord(mcpQuery.data, catalog))
    if (pluginsQuery.isSuccess || pluginsQuery.isError) setHydrated(true)
  }, [agentId, mcpQuery.data, catalog, hydrated, pluginsQuery.isSuccess, pluginsQuery.isError])

  const toggle = async (server: string, tool: string) => {
    if (!agentId || saving) return
    const key = toolKey(server, tool)
    const previous = new Set(checked)
    const next = new Set(checked)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setHydrated(true)
    setChecked(next)
    const record: AgentMcpRecord | undefined = mcpQuery.data
    const mcp_tools = mcpToolsFromChecked(catalog, next, record?.mcp_tools ?? {})
    const patch: { mcp_tools: typeof mcp_tools; mcp_mode?: string } = { mcp_tools }
    if ((record?.mcp_mode ?? 'off') === 'off' && grantEnablesAny(mcp_tools)) {
      patch.mcp_mode = 'all'
    }
    setSaving(true)
    try {
      const saved = await patchAgentMcp(agentId, patch)
      rememberAgentMcpTools(agentId, saved.mcp_tools)
    } catch {
      setChecked(previous)
      toast?.error('Connector tools', 'Could not save this grant. The checkbox was restored.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
      data-testid="agent-editor-mcp-tools"
    >
      <div>
        <span className="text-sm font-semibold text-base-content/80">Connector tools</span>
        <p className="text-xs text-base-content/60 mt-0.5">
          Saved connector grant for this bot. A chat turn that sends its own tool list replaces this grant for that turn.
        </p>
      </div>
      {pluginsQuery.isPending ? (
        <p className="text-xs text-base-content/60">Loading connector catalog…</p>
      ) : null}
      {pluginsQuery.isError ? (
        <p className="text-xs text-error">Connector catalog unavailable.</p>
      ) : null}
      {!pluginsQuery.isPending && !pluginsQuery.isError && catalog.length === 0 ? (
        <p className="text-xs text-base-content/60">No MCP connectors in the catalog.</p>
      ) : null}
      <ul className="space-y-3">
        {catalog.map((server) => (
          <li key={server.name}>
            <div className="text-sm font-medium">{server.name}</div>
            {server.tools.length === 0 ? (
              <p className="text-xs text-base-content/60">No discovered tools.</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {server.tools.map((tool) => {
                  const id = `agent-mcp-${server.name}-${tool.name}`
                  return (
                    <li key={tool.name}>
                      <label htmlFor={id} className="label cursor-pointer justify-start gap-2 px-0 py-0.5">
                        <input
                          id={id}
                          type="checkbox"
                          className="checkbox checkbox-sm"
                          data-testid={`agent-mcp-tool-${server.name}-${tool.name}`}
                          checked={checked.has(toolKey(server.name, tool.name))}
                          disabled={saving}
                          onChange={() => {
                            void toggle(server.name, tool.name)
                          }}
                        />
                        <span>
                          <span className="text-sm">{tool.name}</span>
                          {tool.description ? (
                            <span className="block text-xs text-base-content/60">{tool.description}</span>
                          ) : null}
                        </span>
                      </label>
                    </li>
                  )
                })}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
