/**
 * #577 — the composer's Plugins-Enabled badge must describe **exactly what
 * the send path will apply**, so it consumes the same resolved value the
 * send uses. #516 re-keyed that scope from the conversation to the **agent**
 * seat id, so the badge now follows `useCurrentAgent()` — the same channel
 * the popup's toggles read. Badge, toggles, and send cannot diverge.
 *
 * Label contract (issue §Ask):
 *   0 enabled → nothing rendered
 *   1 enabled → `<Plugin> Enabled` (display name, not the snake_case id —
 *               the same names the Plugins popup toggles use)
 *   2+        → `Plugins Enabled <N>`
 */
import { useCallback, useEffect, useState } from 'react'
import {
  CHAT_PLUGIN_TOOLS_EVENT,
  FIXTURE_PLUGIN_TOOLS,
  loadEnabledPluginToolIds,
  type PluginTool,
} from './chatPluginTools'
import { useCurrentAgent, isSwarmOwnedSeat } from './currentAgent'

function nameFor(toolId: string, tools: readonly PluginTool[]): string {
  const direct = tools.find((tool) => tool.id === toolId)
  if (direct?.name) return direct.name
  const fixture = FIXTURE_PLUGIN_TOOLS.find((tool) => tool.id === toolId)
  if (fixture?.name) return fixture.name
  return toolId
}

/**
 * Live view of the enabled plugin tools for the **current agent seat** — the
 * same key `enabledToolsParam` reads on send (#516). Re-resolves on seat
 * change and on every toggle so the badge can never drift from the send path.
 */
export function useEnabledPluginTools(): { agentId: string; ids: string[] } {
  const agent = useCurrentAgent()
  const agentId = agent?.id ?? ''
  const [ids, setIds] = useState<string[]>(() => loadEnabledPluginToolIds(agentId))

  const refresh = useCallback(() => {
    setIds(loadEnabledPluginToolIds(agentId))
  }, [agentId])

  useEffect(() => {
    refresh()
    window.addEventListener(CHAT_PLUGIN_TOOLS_EVENT, refresh)
    return () => {
      window.removeEventListener(CHAT_PLUGIN_TOOLS_EVENT, refresh)
    }
  }, [refresh])

  return { agentId, ids }
}

/** The badge's display contract. `null` → render nothing. */
export function pluginsBadgeLabel(ids: readonly string[], tools: readonly PluginTool[]): string | null {
  if (ids.length === 0) return null
  if (ids.length === 1) return `${nameFor(ids[0], tools)} Enabled`
  return `Plugins Enabled ${ids.length}`
}

/** #511 gate: the badge must not advertise plugins on a seat that cannot use them.
 * The rail's Plugins entry greys out on anything that is not swarm-owned, and
 * the popup toggles live per chat — so the badge follows the same swarm-owned
 * reading (#551's declared-capability channel) instead of a second kind check.
 * Unknown/unresolved selection stays allowed so a transient load state cannot
 * hide an operator's real plugin state. */
export function usePluginsBadgeAllowed(): boolean {
  const agent = useCurrentAgent()
  return agent === null || isSwarmOwnedSeat(agent)
}
