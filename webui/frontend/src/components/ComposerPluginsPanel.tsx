/**
 * #516 — the composer `+` menu's Plugins panel.
 *
 * A compact list of the current agent's connectors with the shared toggle
 * row — the same `PluginToggleRow` the Plugins popup renders, reading the
 * same agent-scoped accessors, so the panel, popup, badge, and send path all
 * resolve one store. Scope is the **agent** (`useCurrentAgent`), so switching
 * seats re-reads live without a remount.
 */
import { useEffect, useMemo, useState } from 'react'
import { loadPluginCatalog, type PluginCatalogSource, type PluginTool } from '../lib/chatPluginTools'
import { loadEnabledPluginToolIds, setPluginToolEnabled } from '../lib/chatPluginTools'
import { useCurrentAgent } from '../lib/currentAgent'
import { PluginToggleRow } from './PluginToggleRow'
import { openSettingsSheet } from './SettingsSheet'

function sourceCopy(source: PluginCatalogSource): string {
  if (source === 'live') return 'Tools from connected MCP servers.'
  if (source === 'configured') return 'Tools from servers you added in Manage.'
  return 'Showing the shipped catalog until MCP servers are connected.'
}

export interface ComposerPluginsPanelProps {
  onClose: () => void
}

export function ComposerPluginsPanel({ onClose }: ComposerPluginsPanelProps) {
  const agent = useCurrentAgent()
  const agentId = agent?.id ?? ''
  const [tools, setTools] = useState<PluginTool[]>([])
  const [source, setSource] = useState<PluginCatalogSource>('fixture')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    void loadPluginCatalog().then((resolved) => {
      if (cancelled) return
      setTools(resolved.tools)
      setSource(resolved.source)
      setLoaded(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const [enabledIds, setEnabledIds] = useState<string[]>([])

  // #516: re-read on agent change — no remount, the panel follows the seat.
  useEffect(() => {
    setEnabledIds(loadEnabledPluginToolIds(agentId))
  }, [agentId])

  const enabledSet = useMemo(() => new Set(enabledIds), [enabledIds])

  const toggle = (tool: PluginTool | undefined) => {
    if (!tool || !agentId) return
    setEnabledIds(setPluginToolEnabled(agentId, tool.id, !enabledSet.has(tool.id)))
  }

  const openManage = () => {
    onClose()
    openSettingsSheet({ section: 'plugins' })
  }

  return (
    <div
      role="menu"
      aria-label="Plugins for this agent"
      data-testid="composer-plugins-panel"
      className="os-plus-menu os-plus-menu--panel"
    >
      <p className="px-3 pt-2 pb-1 text-[11px] text-base-content/50" data-testid="composer-plugins-source">
        {sourceCopy(source)} Toggles apply to this agent only.
      </p>
      {!loaded ? (
        <div className="os-search-empty px-3 py-2 text-sm text-base-content/60" role="status">
          Loading plugins…
        </div>
      ) : tools.length === 0 ? (
        <div className="os-search-empty px-3 py-2 text-sm text-base-content/60">
          No plugins configured.
          <button type="button" className="btn btn-ghost btn-xs mt-2 text-primary" onClick={openManage}>
            Connect a server in Manage…
          </button>
        </div>
      ) : (
        <ul role="group" aria-label="Plugin tools" className="max-h-64 overflow-y-auto">
          {tools.map((tool) => (
            <li
              key={tool.id}
              data-tool-id={tool.id}
              data-enabled={enabledSet.has(tool.id) ? 'true' : 'false'}
              className="flex items-center gap-2 px-3 py-1.5"
            >
              <PluginToggleRow tool={tool} on={enabledSet.has(tool.id)} onToggle={toggle} />
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center justify-between px-3 py-2 border-t border-base-300/60">
        <span className="text-[11px] text-base-content/50">
          {agentId ? `For: ${agentId}` : 'No agent selected'}
        </span>
        <button type="button" className="btn btn-ghost btn-xs text-primary" onClick={openManage}>
          Manage servers
        </button>
      </div>
    </div>
  )
}

export default ComposerPluginsPanel
