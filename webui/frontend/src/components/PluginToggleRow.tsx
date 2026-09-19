/**
 * #516 — the shared plugin toggle row.
 *
 * The Plugins popup already rendered exactly the control the composer menu
 * needed: a `role="switch"` button wrapping a DaisyUI toggle with an On/Off
 * label. Two hand-rolled copies would drift (the REQ-914 lesson), so the row
 * lives here and both surfaces render it. The row is presentation only —
 * scope (per agent, #516) and persistence stay in `chatPluginTools.ts`.
 */
import { Plug } from 'lucide-react'
import type { PluginTool } from '../lib/chatPluginTools'

export interface PluginToggleRowProps {
  tool: PluginTool
  on: boolean
  onToggle: (tool: PluginTool) => void
  testId?: string
}

export function PluginToggleRow({ tool, on, onToggle, testId }: PluginToggleRowProps) {
  return (
    <>
      <span className="os-search-row__icon" aria-hidden="true">
        <Plug className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="os-search-row__name">{tool.name}</span>
        <span className="os-search-row__desc">
          {tool.serverName}
          {tool.description ? ` · ${tool.description}` : ''}
        </span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={`${tool.name} ${on ? 'On' : 'Off'}`}
        data-testid={testId}
        className="os-plugin-toggle flex items-center gap-2"
        onClick={(event) => {
          event.stopPropagation()
          onToggle(tool)
        }}
      >
        <input
          type="checkbox"
          className="toggle toggle-sm toggle-primary pointer-events-none"
          checked={on}
          readOnly
          tabIndex={-1}
          aria-hidden="true"
        />
        <span className="text-xs font-semibold w-7">{on ? 'On' : 'Off'}</span>
      </button>
    </>
  )
}

export default PluginToggleRow
