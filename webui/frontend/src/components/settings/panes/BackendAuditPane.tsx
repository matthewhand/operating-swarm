/** #856 slice B — BackendAuditPane (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useState } from 'react'
import { Server } from 'lucide-react'
import { Alert, Button } from '../../DaisyUI'
import {
  BACKEND_AUDIT_STORAGE_KEY,
  readBackendAudit,
  type BackendAuditEntry,
} from '../../../lib/backendAudit'

export function BackendAuditPane() {
  const [rows, setRows] = useState<BackendAuditEntry[]>([])

  useEffect(() => {
    const sync = () => setRows(readBackendAudit())
    sync()
    window.addEventListener('storage', sync)
    window.addEventListener('swarm:backend-audit', sync)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('swarm:backend-audit', sync)
    }
  }, [])

  const clearAll = () => {
    try {
      window.localStorage.removeItem(BACKEND_AUDIT_STORAGE_KEY)
    } catch {
      /* best-effort */
    }
    setRows([])
  }

  return (
    <div className="space-y-3" data-testid="backend-audit-pane">
      <div>
        <h4 className="text-lg font-semibold">Backend audit</h4>
        <p className="mt-1 text-sm text-base-content/70">
          What backend each send actually used, recorded by the send path — not
          what a label claims. An <em>inferred</em> CLI is a fallback guess for
          a seat that declares none; it is never the seat's own choice.
        </p>
      </div>
      {rows.length === 0 ? (
        <Alert type="info" icon={<Server className="h-5 w-5" />}>
          <span className="text-sm">No sends recorded yet.</span>
        </Alert>
      ) : (
        <>
          <ul className="space-y-1" aria-label="Backend audit log">
            {rows.map((row, index) => (
              <li
                key={`${row.at}-${row.agentId}-${index}`}
                className="flex items-start justify-between gap-3 rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
                data-testid="backend-audit-row"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    {row.agentName}{' '}
                    <span className="badge badge-ghost badge-sm">{row.kind}</span>
                  </p>
                  <p className="font-mono text-xs text-base-content/70">{row.backend}</p>
                  <p className="text-xs text-base-content/60">{row.reason}</p>
                </div>
                <time className="shrink-0 text-xs text-base-content/50">
                  {new Date(row.at).toLocaleTimeString()}
                </time>
              </li>
            ))}
          </ul>
          <Button type="button" variant="ghost" size="sm" onClick={clearAll}>
            Clear log
          </Button>
        </>
      )}
    </div>
  )
}
