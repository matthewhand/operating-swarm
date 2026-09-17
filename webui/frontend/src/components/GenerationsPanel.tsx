/**
 * #224 — agent-first generations panel.
 *
 * The transcript stays agent-first: answers + status chrome only. This panel
 * is the on-demand surface — click the agent in the chat header to see the
 * seat's tool calls as collapsible blocks and a read-only **Raw** view of
 * exactly what the model sees (`GET /chat/raw-context/`), including the #214
 * include-in-context state of spliced summaries.
 *
 * Honesty constraint (from the issue): the raw view renders the backend's
 * production context splice verbatim — nothing is fabricated client-side.
 * Tool args/output render only when the ws events actually carried them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Copy, X } from 'lucide-react'
import { ToolStatusBadge } from './ToolCallPopup'
import type { ToolCallState } from '../lib/safety'
import { SidepaneConcealButton } from './SidepaneConceal'

/** Tool calls as rendered in the panel; args/output appear when the backend sends them. */
export interface PanelToolCall extends ToolCallState {
  args?: unknown
  output?: string
}

export interface GenerationsContext {
  id: string
  label: string
}

interface RawContextPayload {
  conversation_id: string
  context: Array<{ role: string; content: string; name?: string }>
  summaries_included: number[]
  summaries_excluded: number[]
  cull_offset: number
  raw_turn_count: number
}

export interface GenerationsPanelProps {
  open: boolean
  onClose: () => void
  agentId: string
  agentName: string
  /** Contexts the seat has (current thread first); switcher across the top. */
  contexts: GenerationsContext[]
  activeContextId: string
  onSwitchContext: (conversationId: string) => void
  toolCalls: PanelToolCall[]
}

export function GenerationsPanel({
  open,
  onClose,
  agentId,
  agentName,
  contexts,
  activeContextId,
  onSwitchContext,
  toolCalls,
}: GenerationsPanelProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set())
  const [rawOpen, setRawOpen] = useState(false)
  const [rawData, setRawData] = useState<RawContextPayload | null>(null)
  const [rawLoading, setRawLoading] = useState(false)
  const [rawError, setRawError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target
      const el = target instanceof Element ? target : (target as Node | null)?.parentElement
      if (!el) return
      if (panelRef.current?.contains(el)) return
      if (el.closest('[data-testid="header-avatar-generations"]')) return
      onClose()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open, onClose])

  useEffect(() => {
    if (!open) {
      setExpandedIds(new Set())
      setRawOpen(false)
      setRawData(null)
      setRawError(null)
      setCopied(false)
    }
  }, [open])

  useEffect(() => {
    if (!rawOpen || !open || !activeContextId) return
    let cancelled = false
    setRawLoading(true)
    setRawError(null)
    fetch(
      `/chat/raw-context/?agent=${encodeURIComponent(agentId)}&conversation_id=${encodeURIComponent(activeContextId)}`,
    )
      .then(async (resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        return (await resp.json()) as RawContextPayload
      })
      .then((data) => {
        if (!cancelled) setRawData(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) setRawError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setRawLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [agentId, activeContextId, open, rawOpen])

  const expandAll = useCallback(() => {
    setExpandedIds(new Set(toolCalls.map((tool) => tool.id)))
  }, [toolCalls])

  const collapseAll = useCallback(() => {
    setExpandedIds(new Set())
  }, [])

  const toggleTool = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const rawText = useMemo(() => {
    if (!rawData) return ''
    const lines = rawData.context.map((item) => {
      const who = item.name ? `${item.role} (${item.name})` : item.role
      return `[${who}] ${item.content}`
    })
    return lines.join('\n')
  }, [rawData])

  const copyRaw = useCallback(() => {
    if (!rawText) return
    void navigator.clipboard?.writeText(rawText).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    })
  }, [rawText])

  if (!open) return null

  return (
    <section
      ref={panelRef}
      className="os-generations-panel"
      data-testid="generations-panel"
      role="dialog"
      aria-label={`${agentName} generations`}
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-base-content/10">
        <SidepaneConcealButton onClick={onClose} />
        <h2 className="min-w-0 flex-1 text-sm font-semibold truncate">
          {agentName} · generations
        </h2>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            aria-pressed={rawOpen}
            data-testid="generations-raw-toggle"
            onClick={() => setRawOpen((prev) => !prev)}
          >
            Raw
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-square"
            aria-label="Close generations panel"
            data-testid="generations-close"
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {contexts.length > 1 ? (
        <div
          className="flex flex-wrap gap-1 px-3 py-2 border-b border-base-content/10"
          role="tablist"
          aria-label="Generation contexts"
        >
          {contexts.map((context) => (
            <button
              key={context.id}
              type="button"
              role="tab"
              aria-selected={context.id === activeContextId}
              className={`btn btn-xs ${context.id === activeContextId ? 'btn-primary' : 'btn-ghost'}`}
              data-testid={`generations-context-${context.id}`}
              onClick={() => onSwitchContext(context.id)}
            >
              {context.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex items-center justify-end gap-1 px-3 py-1">
        <span className="text-xs text-base-content/60 mr-auto">
          {toolCalls.length} tool call{toolCalls.length === 1 ? '' : 's'}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-xs"
          data-testid="generations-expand-all"
          onClick={expandAll}
        >
          Expand all
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-xs"
          data-testid="generations-collapse-all"
          onClick={collapseAll}
        >
          Collapse all
        </button>
      </div>

      <ul className="px-3 pb-2 space-y-1" data-testid="generations-tool-list">
        {toolCalls.map((tool) => {
          const expanded = expandedIds.has(tool.id)
          return (
            <li key={tool.id} data-testid="generations-tool" data-tool-status={tool.status}>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded px-2 py-1 hover:bg-base-200/70 text-left"
                aria-expanded={expanded}
                onClick={() => toggleTool(tool.id)}
              >
                {expanded ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                )}
                <span className="font-mono text-xs truncate">{tool.name}</span>
                <ToolStatusBadge status={tool.status} />
              </button>
              {expanded ? (
                <div
                  className="ml-6 rounded bg-base-200/50 px-2 py-1 text-xs"
                  data-testid={`generations-tool-body-${tool.id}`}
                >
                  <div className="font-mono text-base-content/60">id: {tool.id}</div>
                  {tool.args !== undefined ? (
                    <pre className="whitespace-pre-wrap font-mono">
                      {safeStringify(tool.args)}
                    </pre>
                  ) : null}
                  {tool.output ? (
                    <pre className="whitespace-pre-wrap font-mono">{tool.output}</pre>
                  ) : null}
                  {tool.args === undefined && !tool.output ? (
                    <p className="text-base-content/50 italic">
                      Args/output not sent by this tool event yet (backend enrichment
                      pending).
                    </p>
                  ) : null}
                </div>
              ) : null}
            </li>
          )
        })}
        {toolCalls.length === 0 ? (
          <li className="px-2 py-1 text-xs text-base-content/50" data-testid="generations-tools-empty">
            No tool calls in this context.
          </li>
        ) : null}
      </ul>

      {rawOpen ? (
        <div className="border-t border-base-content/10 px-3 py-2" data-testid="generations-raw-section">
          <div className="flex items-center justify-between pb-1">
            <span className="text-xs font-semibold">Raw model context</span>
            <button
              type="button"
              className="btn btn-ghost btn-xs gap-1"
              data-testid="generations-raw-copy"
              onClick={copyRaw}
            >
              {copied ? (
                <Check className="h-3 w-3" aria-hidden="true" />
              ) : (
                <Copy className="h-3 w-3" aria-hidden="true" />
              )}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          {rawLoading ? (
            <p className="text-xs text-base-content/60" data-testid="generations-raw-loading">
              Loading…
            </p>
          ) : null}
          {rawError ? (
            <p className="text-xs text-error" data-testid="generations-raw-error" role="alert">
              Raw context unavailable: {rawError}
            </p>
          ) : null}
          {rawData ? (
            <>
              <p className="text-xs text-base-content/60 pb-1" data-testid="generations-raw-meta">
                {rawData.raw_turn_count} raw turns · cull offset {rawData.cull_offset}
                {rawData.summaries_excluded.length
                  ? ` · summaries excluded from context: ${rawData.summaries_excluded.join(', ')}`
                  : ''}
              </p>
              <pre
                className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-base-200/50 p-2 font-mono text-xs"
                data-testid="generations-raw-view"
              >
                {rawText}
              </pre>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? ''
  } catch {
    return String(value)
  }
}

export default GenerationsPanel
