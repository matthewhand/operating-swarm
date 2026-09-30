/**
 * #1694 — a session hop rendered as a BOUNDARY MARKER you can open.
 *
 * Everything above this point in the conversation was folded into the summary
 * below it; that is what a hop is, and the marker says so rather than reading
 * as an ordinary status line that happens to mention tokens.
 *
 * Design constraints this component holds itself to:
 *
 *  - **Collapsed by default.** The summary can be thousands of tokens. It is
 *    one click away, not in the reader's face.
 *  - **The affordance is not colour.** A native `<button>` carries the state
 *    (`aria-expanded`) and the region (`aria-controls`); a chevron glyph shows
 *    open/closed for sighted users; and the label's own text flips
 *    "Show" → "Hide". Remove the hue entirely and the control still works,
 *    which is the only test of a non-colour affordance that means anything.
 *  - **It never claims more than it has.** The route, token count and turn
 *    count render only from fields the server actually sent, and the whole
 *    disclosure is absent when nothing was carried.
 */
import { useId, useState } from 'react'
import { DisclosureChevron } from './DisclosureChevron'
import {
  carriedSummaryRoute,
  carriedSummaryScale,
  type CarriedSummary,
} from '../lib/carriedSummary'
import './CarriedSummaryBlock.css'

export interface CarriedSummaryBlockProps {
  summary: CarriedSummary
  /** The server's own announcement, kept verbatim as the marker label. */
  notice: string
  className?: string
}

export function CarriedSummaryBlock({
  summary,
  notice,
  className = '',
}: CarriedSummaryBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const bodyId = useId()
  const route = carriedSummaryRoute(summary)
  const scale = carriedSummaryScale(summary)
  const omitted = summary.omitted.join(', ').replace(/_/g, ' ')

  return (
    <div
      className={`os-carried-summary ${className}`.trim()}
      data-testid="carried-summary"
      data-route={route}
    >
      <div className="os-carried-summary__rule" aria-hidden="true" />
      <button
        type="button"
        className="os-carried-summary__toggle"
        data-testid="carried-summary-toggle"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span
          className="os-carried-summary__chevron"
          data-carried-summary-chevron="true"
          aria-hidden="true"
        >
          <DisclosureChevron expanded={expanded} className="h-3.5 w-3.5 shrink-0" />
        </span>
        <span className="os-carried-summary__text">
          {/* The server's announcement, not a re-derivation — one phrasing of
              the fact, so the marker cannot disagree with history. */}
          <span data-testid="carried-summary-label">{notice}</span>
          <span className="os-carried-summary__meta">
            <span data-testid="carried-summary-route">{route}</span>
            {scale ? <span data-testid="carried-summary-scale"> · {scale}</span> : null}
          </span>
        </span>
        <span className="os-carried-summary__action" data-testid="carried-summary-action">
          {expanded ? 'Hide carried context' : 'Show carried context'}
        </span>
      </button>
      {expanded ? (
        <div
          id={bodyId}
          className="os-carried-summary__body"
          data-testid="carried-summary-body"
        >
          <pre className="os-carried-summary__pre">{summary.text}</pre>
          {omitted ? (
            <p
              className="os-carried-summary__omitted"
              data-testid="carried-summary-omitted"
            >
              Not carried: {omitted}. Everything above this line was folded into the
              summary above.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export default CarriedSummaryBlock
