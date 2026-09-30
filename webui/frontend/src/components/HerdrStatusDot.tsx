/**
 * #1729 — the Herdr status dot on a seat avatar / rail row.
 *
 * Reuses the affordances that already exist rather than inventing a second
 * notification system: the **unread** state is the rail's existing blue dot
 * (fed through `lib/unreadAgents`), and this component adds only the one thing
 * the rail has no vocabulary for — *waiting on a human*.
 *
 * Accessibility is not optional here, because a coloured dot is exactly the
 * thing that disappears for a colour-blind user or in a monochrome theme:
 *
 * - `role="status"` + an `aria-label` naming the state in words, so the state
 *   is announced rather than inferred from a hue.
 * - A `?` glyph inside the dot — a non-colour affordance, so the waiting state
 *   is legible with colour removed entirely.
 * - The pulse is the only motion, and it is dropped under
 *   `prefers-reduced-motion: reduce` (see the `.os-herdr-status-dot` rules in
 *   `index.css`).
 * - `working` deliberately renders **nothing** here. The rail already animates
 *   a busy seat's avatar via `lib/agentTurns`, and a second busy marker
 *   competing with it is noise, not information. #1729 §4 asks for in-progress
 *   to be "an existing or new busy state, not silent" — the existing one is
 *   the right answer.
 */

import { useEffect } from 'react'
import { isAgentUnread } from '../lib/unreadAgents'
import {
  clearHerdrSeat,
  herdrStatusFor,
  statusLabel,
  subscribeHerdrStatus,
  useHerdrSeatStatus,
  type HerdrSeatStatus,
} from '../lib/herdrStatus'

export interface HerdrStatusDotProps {
  /** Rail/row seat id — `herdr:<pane>` (see `herdrStatus.seatIdFor`). */
  seatId: string
  /** Overrides the store read; used by tests and by forced states. */
  status?: HerdrSeatStatus
  /** Human name for the label, e.g. "grok (workbox)". */
  label?: string
  className?: string
}

export function herdrStatusCopy(
  status: HerdrSeatStatus,
  label: string,
): { text: string; tone: string } {
  const who = label.trim() || 'Herdr agent'
  if (status === 'waiting') return { text: `${who}: waiting on you`, tone: 'waiting' }
  if (status === 'finished') return { text: `${who}: ${statusLabel(status)}`, tone: 'finished' }
  return { text: `${who}: ${statusLabel(status)}`, tone: status }
}

/**
 * Render the indicator for a status. Exported so the chat header and the rail
 * can share one implementation — a second copy of this rule is how two
 * surfaces end up disagreeing about what "waiting" looks like.
 */
export function HerdrStatusDot({ seatId, status, label = '', className = '' }: HerdrStatusDotProps) {
  const live = useHerdrSeatStatus(seatId)
  const effective = status ?? live
  // `working` and `idle` render nothing; `unknown` never renders either — an
  // indicator OS cannot justify is worse than no indicator.
  if (effective !== 'waiting' && effective !== 'finished') return null
  const { text, tone } = herdrStatusCopy(effective, label)
  return (
    <span
      className={`os-herdr-status-dot os-herdr-status-dot--${tone} ${className}`.trim()}
      data-testid="herdr-status-dot"
      data-status={effective}
      data-tone={tone}
      role="status"
      aria-live="polite"
      aria-label={text}
      title={text}
    >
      <span className="os-herdr-status-dot__glyph" aria-hidden="true">
        {effective === 'waiting' ? '?' : '•'}
      </span>
    </span>
  )
}

export default HerdrStatusDot

/**
 * Clear a Herdr seat when the operator opens its chat.
 *
 * "Opening" is the only honest clear signal OS has: it is the moment the
 * operator demonstrably looked at the pane. Everything else (a timer, a
 * scroll) would clear a dot nobody read.
 */
export function useClearHerdrSeatOnOpen(seatId: string, open: boolean): void {
  useEffect(() => {
    if (!open || !seatId) return
    // Nothing to clear on a seat we have never heard from, and nothing to
    // clear on one already read — both are no-ops that must not churn the
    // store (or dispatch an unread-changed event for nothing).
    if (!isAgentUnread(seatId) && herdrStatusFor(seatId) === 'unknown') return
    clearHerdrSeat(seatId)
  }, [open, seatId])
}

export { subscribeHerdrStatus }
