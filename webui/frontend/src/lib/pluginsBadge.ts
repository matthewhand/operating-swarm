/**
 * #577 — the composer's Plugins-Enabled badge must describe **exactly what
 * the send path will apply**, so it consumes the same resolved value the
 * send uses (`enabledToolsParam(conversationIdRef.current)`, ChatPage:2470).
 *
 * A badge that resolves its own scope can say "3 enabled" while the send
 * omits them all — the failure mode #516 warns about. Deriving from the same
 * accessor + the same scope event means the badge follows #516's future
 * per-agent re-key automatically.
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
import { CURRENT_CHAT_SCOPE_EVENT, loadCurrentChatScope } from './chatScope'
import { useCurrentAgent, isSwarmOwnedSeat } from './currentAgent'

function nameFor(toolId: string, tools: readonly PluginTool[]): string {
  const direct = tools.find((tool) => tool.id === toolId)
  if (direct?.name) return direct.name
  const fixture = FIXTURE_PLUGIN_TOOLS.find((tool) => tool.id === toolId)
  if (fixture?.name) return fixture.name
  return toolId
}

/**
 * Live view of the enabled plugin tools for the **current chat scope** — the
 * same key `enabledToolsParam` reads on send. Re-resolves on scope change and
 * on every toggle so the badge can never drift from the send path.
 */
export function useEnabledPluginTools(): { chatId: string; ids: string[] } {
  const [chatId, setChatId] = useState(() => loadCurrentChatScope())
  const [ids, setIds] = useState<string[]>(() => loadEnabledPluginToolIds(chatId))

  const refresh = useCallback(() => {
    const next = loadCurrentChatScope()
    setChatId(next)
    setIds(loadEnabledPluginToolIds(next))
  }, [])

  useEffect(() => {
    window.addEventListener(CURRENT_CHAT_SCOPE_EVENT, refresh)
    window.addEventListener(CHAT_PLUGIN_TOOLS_EVENT, refresh)
    return () => {
      window.removeEventListener(CURRENT_CHAT_SCOPE_EVENT, refresh)
      window.removeEventListener(CHAT_PLUGIN_TOOLS_EVENT, refresh)
    }
  }, [refresh])

  return { chatId, ids }
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
