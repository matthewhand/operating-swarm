/**
 * #533 — first-class rendering for special in-chat content.
 *
 * `SpecialStatusCard` is the collapsible card for `status`-role messages
 * (context-cull notices, session restores, generic system chatter): a one-line
 * summary with the full detail behind a native <details> disclosure. It renders
 * inside the bubble's `children` slot, so every bubble theme (speech, simple,
 * irc, feed) carries it without per-theme branches.
 *
 * Approvals already have a functional card (`ToolCallPopup`'s
 * `os-safety-approval` section with Allow once / Always allow / Deny); the
 * acceptance tests below pin that too.
 */
import type { ReactNode } from 'react'

export interface SpecialStatusCardProps {
  /** One-line summary shown on the collapsed row. */
  summary: string
  /** Longer detail (raw notice text) behind the disclosure. */
  detail?: ReactNode
  /** Optional badge text on the collapsed row (e.g. `context`, `session`). */
  badge?: string
  testId?: string
}

/** Collapsible status card — replaces raw status text in the transcript. */
export function SpecialStatusCard({
  summary,
  detail,
  badge,
  testId = 'special-status-card',
}: SpecialStatusCardProps) {
  return (
    <details
      className="collapse collapse-arrow os-special-card mt-2 rounded-box border border-base-300 bg-base-100"
      data-testid={testId}
    >
      <summary className="collapse-title min-h-0 py-2 px-3 flex items-center gap-2 text-xs text-base-content/80">
        {badge ? (
          <span className="badge badge-ghost badge-xs shrink-0 uppercase tracking-wide">
            {badge}
          </span>
        ) : null}
        <span className="truncate" title={summary}>
          {summary}
        </span>
      </summary>
      {detail != null ? (
        <div className="collapse-content px-3 pb-2 pt-0 text-xs text-base-content/70">
          <div className="whitespace-pre-wrap font-mono break-words">{detail}</div>
        </div>
      ) : null}
    </details>
  )
}

export default SpecialStatusCard
