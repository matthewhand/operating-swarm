import { useEffect, useState } from 'react'
import {
  fetchContextUsage,
  formatContextUsageLabel,
  formatUsageTokens,
  parseContextUsage,
  publishContextUsage,
  readUsageSpark,
  type ContextUsage,
} from '../lib/contextUsage'
import { peekConversationIdForAgent } from '../lib/agentChat'

export interface ContextUsageDetailProps {
  agentId: string
  conversationId?: string | null
  modelId?: string | null
  usage?: ContextUsage | null
}

function UsageSparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const max = Math.max(...points, 1)
  const w = 160
  const h = 32
  const step = points.length === 1 ? 0 : w / (points.length - 1)
  const d = points
    .map((n, i) => {
      const x = i * step
      const y = h - (n / max) * (h - 2) - 1
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-8 w-40 text-primary"
      role="img"
      aria-label="Context usage over this session"
      data-testid="context-usage-sparkline"
    >
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function BreakdownRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-base-content/70">{label}</span>
      <span className="tabular-nums font-medium" data-testid={`context-usage-${label.toLowerCase().replace(/\s+/g, '-')}`}>
        ~{formatUsageTokens(value)}
      </span>
    </div>
  )
}

/** Seat-settings detail for #215 context-window usage. */
export function ContextUsageDetail({
  agentId,
  conversationId,
  modelId,
  usage: usageProp,
}: ContextUsageDetailProps) {
  const cid = (conversationId || peekConversationIdForAgent(agentId) || '').trim()
  const [usage, setUsage] = useState<ContextUsage | null>(usageProp ?? null)
  const [spark, setSpark] = useState<number[]>(() => (cid ? readUsageSpark(cid) : []))

  useEffect(() => {
    if (usageProp) {
      setUsage(usageProp)
      if (usageProp.conversation_id) {
        setSpark(readUsageSpark(usageProp.conversation_id))
      }
      return
    }
    if (!agentId || !cid) return
    let cancelled = false
    void fetchContextUsage({ agentId, conversationId: cid, modelId })
      .then((next) => {
        if (cancelled) return
        publishContextUsage(next)
        setUsage(next)
        setSpark(readUsageSpark(next.conversation_id))
      })
      .catch(() => {
        if (!cancelled) setUsage(null)
      })
    return () => {
      cancelled = true
    }
  }, [agentId, cid, modelId, usageProp])

  useEffect(() => {
    const onUsage = (event: Event) => {
      const parsed = parseContextUsage((event as CustomEvent).detail)
      if (!parsed) return
      if (parsed.agent_id && parsed.agent_id !== agentId) return
      setUsage(parsed)
      setSpark(readUsageSpark(parsed.conversation_id))
    }
    window.addEventListener('swarm:context-usage', onUsage)
    return () => window.removeEventListener('swarm:context-usage', onUsage)
  }, [agentId])

  const label = usage ? formatContextUsageLabel(usage) : 'No estimate yet'
  const windowKnown = usage?.window != null && usage.window > 0
  const pct = usage?.pct
  const barMax = windowKnown && usage?.window ? usage.window : Math.max(usage?.tokens ?? 0, 1)
  const barPct = usage
    ? Math.min(100, Math.round((Math.max(0, usage.tokens) / barMax) * 100))
    : 0

  return (
    <section
      className="space-y-3 rounded-box border border-base-300 bg-base-200/40 px-4 py-3"
      data-testid="context-usage-detail"
      aria-label="Context window usage"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h5 className="text-sm font-semibold">Context window</h5>
          <p className="mt-0.5 text-xs text-base-content/70">
            Messages, spliced summaries, instructions, and tool schemas.
            {usage?.estimate !== false ? ' Estimate (chars/4).' : ''}
          </p>
        </div>
        <UsageSparkline points={spark} />
      </div>
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="tabular-nums font-medium" data-testid="context-usage-label">
          {label}
        </span>
        {pct != null ? (
          <span className="text-xs text-base-content/60 tabular-nums">{pct}%</span>
        ) : null}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-base-300">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${Math.max(usage && usage.tokens > 0 ? 4 : 0, barPct)}%` }}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={barMax}
          aria-valuenow={usage?.tokens ?? 0}
          aria-label="Context window usage"
        />
      </div>
      {usage ? (
        <div className="space-y-1">
          <BreakdownRow label="Messages" value={usage.breakdown.messages} />
          <BreakdownRow label="Summaries" value={usage.breakdown.summaries} />
          <BreakdownRow label="System" value={usage.breakdown.system} />
          <BreakdownRow label="Tools" value={usage.breakdown.tools} />
        </div>
      ) : (
        <p className="text-xs text-base-content/60">Open a chat on this seat to measure usage.</p>
      )}
    </section>
  )
}
