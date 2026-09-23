import { useEffect, useState } from 'react'
import { Plug } from 'lucide-react'
import {
  FIXTURE_PLUGIN_TOOLS,
  loadPluginCatalog,
  type PluginTool,
} from '../lib/chatPluginTools'
import {
  pluginsBadgeLabel,
  useEnabledPluginTools,
  usePluginsBadgeAllowed,
} from '../lib/pluginsBadge'
import { OPEN_PLUGINS_EVENT } from '../lib/chromeOverlay'

/**
 * #577 — the composer's Plugins-Enabled badge.
 *
 * Reads the **same scope the send path reads** (`useEnabledPluginTools`
 * consumes the chat scope / toggle events that back
 * `enabledToolsParam(conversationIdRef.current)`), so the label can never
 * claim plugins are on while the send omits them. Clicking dispatches the
 * same `OPEN_PLUGINS_EVENT` the rail footer's Plugins entry handles, so the
 * badge is a shortcut into the toggles rather than a dead label.
 *
 * Label contract: 0 → nothing; 1 → `<Plugin> Enabled`; 2+ → `Plugins Enabled <N>`.
 * Never rendered on a seat kind that cannot use plugins (#511 gate).
 */
export default function ComposerPluginsBadge() {
  const { ids } = useEnabledPluginTools()
  const allowed = usePluginsBadgeAllowed()
  const [tools, setTools] = useState<PluginTool[]>(FIXTURE_PLUGIN_TOOLS)

  // Display names come from the same catalog the Plugins popup renders, so
  // the badge's `<Plugin> Enabled` cannot drift from the toggle labels.
  useEffect(() => {
    let cancelled = false
    void loadPluginCatalog()
      .then((resolved) => {
        if (!cancelled && resolved.tools.length > 0) setTools(resolved.tools)
      })
      .catch(() => {
        /* fixture names already in place */
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!allowed) return null
  const label = pluginsBadgeLabel(ids, tools)
  if (!label) return null

  return (
    <div className="flex justify-end px-3 pt-1.5" data-testid="composer-plugins-badge-slot">
      <button
        type="button"
        className="badge badge-sm badge-ghost gap-1.5 border border-base-300/70 font-normal text-base-content/60 hover:border-primary/50 hover:text-base-content"
        data-testid="composer-plugins-badge"
        data-enabled-count={ids.length}
        aria-label={`${label} — open plugin toggles`}
        title="Open plugin toggles"
        onClick={() => window.dispatchEvent(new CustomEvent(OPEN_PLUGINS_EVENT))}
      >
        <Plug className="h-3 w-3" aria-hidden="true" />
        {label}
      </button>
    </div>
  )
}
