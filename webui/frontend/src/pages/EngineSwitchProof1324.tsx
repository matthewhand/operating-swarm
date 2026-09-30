/**
 * Tiny #1324 proof harness. Not a product surface.
 *
 * `/__proof__/engine-switch-1324` shows path-in-frame chrome and fires the
 * same Engine switch toast the hop path uses, then lands the destination
 * engine so the shot proves the switch is not blocked.
 */
import { useEffect, useState } from 'react'
import { NavbarRoutingPicker } from '../components/NavbarRoutingPicker'
import { useToast } from '../components/DaisyUI'
import { engineSwitchCapabilityWarning } from '../lib/engineSwitchWarning'
import type { SeatCapabilityDirectory } from '../lib/seatRouting'

export const ENGINE_SWITCH_PROOF_PATH = '/__proof__/engine-switch-1324'
export const ENGINE_SWITCH_PROOF_URL = `http://127.0.0.1:4173${ENGINE_SWITCH_PROOF_PATH}`

const GROK_ROW = { export: 'summary', list: 'works', resume: true } as const
const CLAUDE_ROW = { export: 'summary', list: 'paste-only', resume: true } as const

const PROOF_CATALOG: SeatCapabilityDirectory = {
  seat_capabilities: {
    cli: {
      attach: { enabled: false },
      compact: { enabled: false },
      plugins: { enabled: false },
      routines: { enabled: false },
      coordination: { enabled: false },
    },
  },
  cli: {
    grok: { ...GROK_ROW, label: 'grok' },
    claude: { ...CLAUDE_ROW, label: 'claude' },
  },
  labels: { list: 'session list' },
}

export function grokToClaudeWarning(): string {
  return (
    engineSwitchCapabilityWarning({
      fromKind: 'cli',
      toKind: 'cli',
      fromRow: GROK_ROW,
      toRow: CLAUDE_ROW,
      fromLabel: 'grok',
      toLabel: 'claude',
    }) || ''
  )
}

export default function EngineSwitchProof1324() {
  const { addToast } = useToast()
  useEffect(() => {
    const style = document.createElement('style')
    style.setAttribute('data-engine-switch-1324-font', 'true')
    style.textContent =
      'html, body, [data-testid="engine-switch-1324-proof"], [data-toast-type] { font-family: Arial, Helvetica, sans-serif !important; font-feature-settings: "liga" 0; letter-spacing: 0; }'
    document.head.appendChild(style)
    return () => style.remove()
  }, [])
  const [engine, setEngine] = useState('grok')
  const [status, setStatus] = useState('')
  const [blocked, setBlocked] = useState(false)

  return (
    <div
      className="fixed inset-0 z-40 flex flex-col bg-base-200 text-base-content"
      data-testid="engine-switch-1324-proof"
      style={{ fontFamily: 'ui-sans-serif, system-ui, sans-serif' }}
    >
      <div
        className="border-b border-base-300 bg-base-100 px-4 py-3"
        data-testid="engine-switch-1324-chrome"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-base-content/60">
          OS proof #1324
        </p>
        <p
          className="mt-1 rounded-md bg-base-200 px-3 py-2 text-sm"
          data-testid="engine-switch-1324-url"
          style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
        >
          {ENGINE_SWITCH_PROOF_URL}
        </p>
      </div>
      <div className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-4 p-6">
        <h1 className="text-xl font-semibold">Engine switch · capability-loss warning</h1>
        <p className="text-sm text-base-content/70">
          grok → claude loses session list. The picker names the loss and waits;
          Switch anyway applies the hop.
        </p>
        <div className="flex items-center gap-3">
          <span className="text-sm">Current engine</span>
          <span
            className="badge badge-lg badge-neutral font-mono"
            data-testid="engine-switch-1324-current"
          >
            {engine}
          </span>
          <span
            className="badge badge-outline"
            data-testid="engine-switch-1324-blocked"
          >
            {blocked ? 'blocked' : 'not blocked'}
          </span>
        </div>
        <NavbarRoutingPicker
          seatKind="cli"
          aria-label="CLI"
          agents={[
            { id: 'grok', label: 'grok', kind: 'cli' },
            { id: 'claude', label: 'claude', kind: 'cli' },
          ]}
          selectedAgent={engine}
          models={[]}
          selectedModel=""
          capabilityCatalog={PROOF_CATALOG}
          onEngineSwitchWarning={(warning) => {
            addToast({
              type: 'warning',
              title: 'Engine switch',
              message: warning,
              sticky: true,
            })
          }}
          onChange={(next) => {
            if (next.changed !== 'agent') return
            setEngine(next.agent)
            setBlocked(false)
            const warning = next.capabilityWarning || grokToClaudeWarning()
            setStatus(
              `Started a new ${next.agent} session (grok → ${next.agent}). Carried summary context (12 tokens). ${warning}`,
            )
          }}
        />
        {status ? (
          <p
            className="rounded-md bg-base-100 p-3 text-sm"
            role="status"
            data-testid="engine-switch-1324-status"
          >
            {status}
          </p>
        ) : null}
      </div>
    </div>
  )
}
