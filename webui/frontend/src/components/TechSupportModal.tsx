/**
 * #907 — TechSupportModal: fetch GET /v1/diagnostics/ (#905) and render the
 * sanitized bundle for inspection and copy.
 *
 * Security stance: the payload is masked server-side (#904); the modal does
 * not un-mask and additionally redacts secret-shaped keys client-side, so a
 * malformed/poisoned payload cannot leak raw env-style values. What is
 * rendered is exactly what "Copy Diagnostics" puts on the clipboard.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, Check, Copy, X } from 'lucide-react'
import { Modal } from './DaisyUI/Modal'
import { apiGet } from '../lib/api'

interface LogLine {
  ts?: string
  level?: string
  logger?: string
  message?: string
}

interface DiagnosticsPayload {
  recent_logs?: { lines?: LogLine[]; counts?: Record<string, number>; unavailable?: boolean }
  config_dump?: Record<string, unknown>
  server_facts?: Record<string, unknown>
}

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const

/** #906 contract: any surface can open the modal via this event/API. */
export const OPEN_TECH_SUPPORT_EVENT = 'swarm:open-tech-support'

export function openTechSupportModal(): void {
  window.dispatchEvent(new CustomEvent(OPEN_TECH_SUPPORT_EVENT))
}

/**
 * Client-side last line of defense (#907 security): keys that look like they
 * carry secrets are stripped from the payload before it is rendered or
 * copied. The server already masks (#904); this guards a poisoned payload.
 */
const SECRET_KEY_RE = /(api[_-]?key|(?<!not_a_)secret|password|passwd|token|authorization|credential)/i

export function redactSecretShaped(payload: unknown, depth = 0): unknown {
  if (depth > 6) return '…'
  if (Array.isArray(payload)) return payload.map((v) => redactSecretShaped(v, depth + 1))
  if (payload && typeof payload === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
      out[key] = SECRET_KEY_RE.test(key) ? '[redacted]' : redactSecretShaped(value, depth + 1)
    }
    return out
  }
  return payload
}

export default function TechSupportModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [payload, setPayload] = useState<DiagnosticsPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [levelFilter, setLevelFilter] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setPayload(null)
    setError(null)
    setLevelFilter(null)
    setCopied(false)
    apiGet<DiagnosticsPayload>('/v1/diagnostics/')
      .then((data) => {
        if (!cancelled) setPayload(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const redacted = useMemo(
    () => redactSecretShaped(payload) as DiagnosticsPayload | null,
    [payload],
  )

  const counts = payload?.recent_logs?.counts ?? {}
  const lines = useMemo(() => {
    const all = redacted?.recent_logs?.lines ?? []
    return levelFilter ? all.filter((l) => (l.level ?? '').toUpperCase() === levelFilter) : all
  }, [redacted, levelFilter])

  const handleCopy = useCallback(() => {
    if (!redacted) return
    navigator.clipboard?.writeText(JSON.stringify(redacted, null, 2)).then(
      () => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      },
      () => {},
    )
  }, [redacted])

  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      size="2xl"
      placement="middle"
      aria-label="Tech Support diagnostics"
    >
      <div className="space-y-4" data-testid="tech-support-modal">
        <div className="flex items-center justify-between border-b border-base-300 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" aria-hidden="true" />
            <h2 className="text-base font-semibold">Tech Support</h2>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-circle"
            aria-label="Close diagnostics"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {error !== null && (
          <div
            className="alert alert-error text-sm"
            role="alert"
            data-testid="tech-support-error"
          >
            <span>Could not load diagnostics: {error}</span>
          </div>
        )}

        {!payload && error === null && (
          <div className="py-8 text-center text-sm text-base-content/60" data-testid="tech-support-loading">
            <span className="loading loading-spinner loading-sm" aria-hidden="true" />
            <span className="ml-2">Collecting diagnostics…</span>
          </div>
        )}

        {payload !== null && (
          <div className="space-y-4">
            {/* 1. Recent log activity — level filter + per-level counts */}
            <section className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5" data-testid="tech-support-log-filters">
                <button
                  type="button"
                  className={`btn btn-xs ${levelFilter === null ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setLevelFilter(null)}
                >
                  All
                </button>
                {LOG_LEVELS.filter((level) => (counts[level] ?? 0) > 0).map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`btn btn-xs ${levelFilter === level ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setLevelFilter(levelFilter === level ? null : level)}
                  >
                    {level} ({counts[level]})
                  </button>
                ))}
              </div>
              <pre
                className="max-h-64 overflow-auto rounded-lg border border-base-300 bg-base-200/50 p-3 text-xs leading-relaxed"
                data-testid="tech-support-logs"
              >
                {lines.length === 0
                  ? payload.recent_logs?.unavailable
                    ? 'Log capture unavailable on this server.'
                    : 'No log lines.'
                  : lines
                      .map((l) => `${l.ts ?? ''} ${l.level ?? ''} ${l.logger ?? ''}: ${l.message ?? ''}`.trim())
                      .join('\n')}
              </pre>
            </section>

            {/* 2. Configuration dump — structured list, not raw JSON */}
            <section className="space-y-1" data-testid="tech-support-config">
              <h3 className="text-sm font-semibold">Configuration</h3>
              <ConfigList rows={flattenSection(redacted?.config_dump)} />
            </section>

            {/* 3. Server facts */}
            <section className="space-y-1" data-testid="tech-support-facts">
              <h3 className="text-sm font-semibold">Server facts</h3>
              <ConfigList rows={flattenSection(redacted?.server_facts)} />
            </section>

            <p className="text-[11px] text-base-content/50 leading-normal">
              Secrets are masked server-side and redacted again here. This bundle is for
              inspection and copy only — nothing is submitted anywhere.
            </p>
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-base-300 pt-2">
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={handleCopy}
            disabled={payload === null}
          >
            {copied ? (
              <>
                <Check className="h-4 w-4" aria-hidden="true" />
                <span data-testid="tech-support-copied">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-4 w-4" aria-hidden="true" />
                Copy Diagnostics
              </>
            )}
          </button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** Flatten one nested section into label → display-string rows. */
function flattenSection(section: unknown): Array<[string, string]> {
  const rows: Array<[string, string]> = []
  const walk = (value: unknown, prefix: string, depth: number) => {
    if (value == null) {
      rows.push([prefix, '—'])
      return
    }
    if (Array.isArray(value)) {
      rows.push([prefix, value.length === 0 ? '—' : JSON.stringify(value)])
      return
    }
    if (typeof value === 'object') {
      const entries = Object.entries(value as Record<string, unknown>)
      if (entries.length === 0) {
        rows.push([prefix, '—'])
      } else if (depth >= 2) {
        rows.push([prefix, JSON.stringify(value)])
      } else {
        for (const [key, child] of entries) walk(child, prefix ? `${prefix} › ${key}` : key, depth + 1)
      }
      return
    }
    rows.push([prefix, String(value)])
  }
  walk(section, '', 0)
  return rows
}

function ConfigList({ rows }: { rows: Array<[string, string]> }) {
  if (rows.length === 0) return <p className="text-xs text-base-content/50">No data.</p>
  return (
    <ul className="divide-y divide-base-300 rounded-lg border border-base-300 text-xs">
      {rows.map(([label, value]) => (
        <li key={label} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
          <span className="shrink-0 font-medium text-base-content/70">{label}</span>
          <span className="truncate font-mono text-base-content">{value}</span>
        </li>
      ))}
    </ul>
  )
}
