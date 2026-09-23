import { formatUsageBadgeLabel, type ContextUsage } from '../lib/contextUsage'

export interface ContextUsageBadgeProps {
  usage: ContextUsage | null
  onOpenDetail?: () => void
}

/**
 * #773 — the ONE canonical token meter (composer bottom-right):
 * `out <last> · in <total> / <max> tok`. The old navbar estimate meter was
 * removed — two tallies with different sources disagreed.
 */
export function ContextUsageBadge({ usage, onOpenDetail }: ContextUsageBadgeProps) {
  if (!usage) return null
  const label = formatUsageBadgeLabel(usage)
  const title = usage.estimate
    ? `Estimate (chars/4). ${label}`
    : label
  return (
    <button
      type="button"
      className="badge badge-ghost badge-sm h-auto gap-1 px-2 py-1 font-normal normal-case text-base-content/70 hover:bg-base-300/40"
      data-testid="context-usage-badge"
      aria-label="Context window usage"
      title={title}
      onClick={onOpenDetail}
    >
      <span className="tabular-nums whitespace-nowrap">{label}</span>
    </button>
  )
}
