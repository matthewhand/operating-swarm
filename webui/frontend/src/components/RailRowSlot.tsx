import { useEffect, useRef, useState, type ReactNode } from 'react'
import { HerdrStatusDot } from './HerdrStatusDot'
import {
  herdrStatusFor,
  subscribeHerdrStatus,
  type HerdrSeatStatus,
} from '../lib/herdrStatus'

/**
 * #500 / #501: the rail row's name-line right slot.
 *
 * One slot, several tenants, and they must not fight. This component is the
 * single implementation for **agent, team and remote** rows, so the precedence
 * below cannot drift between them.
 *
 * ## Tenants and precedence
 *
 * | Tenant | Role | Yields |
 * |---|---|---|
 * | unread dot | live and actionable | never — it wins while unread |
 * | timestamp | the slot's default owner (REQ-67 `#67`) | last (narrowest widths) |
 * | role badge | **static** | before the time *and* the tip |
 * | ⌥N tip | transient chrome | first |
 *
 * `#501` is a deliberate reversal of `#67`'s parenthetical: the role badge used
 * to outrank the time in a strict either/or, so any agent *with* a role never
 * showed its recency — which is why "recent activity time" read as
 * unimplemented when it was merely never allowed to render. The badge is static
 * and the time is not, so the time wins the scarce space.
 *
 * ## Why the tip is absolutely positioned
 *
 * `#500`'s root cause was that the tip lived on its **own line inside the label
 * column**. When the slot was otherwise empty — no dot, no badge, no time, i.e.
 * most freshly configured rows — that flex line had no content and collapsed to
 * zero height; on hover the tip created a real line box, so the row grew and
 * pushed everything below it. Rows that *did* have something in the slot stayed
 * put, because the tip replaced it in place. Hence "rows with a badge/time
 * behave; rows without them snap."
 *
 * The tip is now layered over the slot with `position: absolute`, so revealing
 * it is an **opacity change only** — it cannot add height, and it cannot take
 * width from the name because it occupies no box in the flow.
 *
 * Progressive disclosure lives in `index.css` as container queries on the rail
 * (which already sets `container-type: inline-size`): the tip disappears first,
 * then the badge, and the time survives longest. The name is `flex: 1 1 0%`, so
 * it always wins the remaining space and is cut with the existing fade.
 */
/**
 * #1729 — resolve the row's own seat id and keep re-reading it.
 *
 * The rail's row renderers already tag every row with `data-agent-id`
 * (`herdr:<pane>` for a Herdr row), so the status surface can identify itself
 * from the DOM instead of threading a new prop through `rowsRender` /
 * `AgentSidebar` — both of which are owned elsewhere. The subscription
 * re-renders on every status change, which is what makes the indicator appear
 * without a reload.
 */
const HERDR_SEAT_PREFIX = 'herdr:'

function useRailHerdrStatus(
  ref: React.RefObject<HTMLElement | null>,
  explicit?: string,
): { seatId: string; status: HerdrSeatStatus } {
  // The *status* is state, not a read-during-render: the store is external
  // and its changes arrive on their own schedule, so reading it inline would
  // leave the indicator frozen until something else re-rendered the row.
  const [reading, setReading] = useState<{ seatId: string; status: HerdrSeatStatus }>({
    seatId: '',
    status: 'unknown',
  })

  useEffect(() => {
    const resolve = () => {
      const fromProp = (explicit ?? '').trim()
      const node = ref.current
      const owner = node?.closest('[data-agent-id]') as HTMLElement | null
      const rowId = fromProp || owner?.getAttribute('data-agent-id')?.trim() || ''
      // Only a Herdr row can carry a Herdr status. Every other seat kind
      // shares this component, and a stale reading must never bleed onto one.
      const seatId = rowId.startsWith(HERDR_SEAT_PREFIX) ? rowId : ''
      setReading((current) => {
        const status = seatId ? herdrStatusFor(seatId) : 'unknown'
        if (current.seatId === seatId && current.status === status) return current
        return { seatId, status }
      })
    }
    resolve()
    // Re-resolve on mount and on every status change: the id is not a prop,
    // and the status can move while the row is mounted.
    return subscribeHerdrStatus(resolve)
  }, [explicit, ref])

  return reading
}

export interface RailRowSlotProps {
  unread?: boolean
  /** Static role badge. Rendered alongside the time, yielding before it. */
  badge?: ReactNode
  /** `formatRailTimestamp` returns null when there is no activity to show. */
  timestampLabel?: string | null
  dataRole?: string
  /**
   * #1729: the row's seat id. Optional — when omitted it is resolved from the
   * owning row's own `data-agent-id`, which every rail row already carries, so
   * the status surface needs no new plumbing through the row renderers.
   */
  seatId?: string
  /** Row label, used for the indicator's accessible name. */
  dataLabel?: string
}

export default function RailRowSlot({
  unread,
  badge,
  timestampLabel,
  dataRole,
  seatId,
  dataLabel,
}: RailRowSlotProps) {
  const ref = useRef<HTMLSpanElement | null>(null)
  const { seatId: herdrSeatId, status: herdrStatus } = useRailHerdrStatus(ref, seatId)
  return (
    <span
      ref={ref}
      className="os-rail-slot relative flex shrink-0 items-center" 
      data-testid="rail-row-slot"
      data-role={dataRole}
      data-herdr-status={herdrSeatId ? herdrStatus : undefined}
    >
      {/* #1729: the Herdr status indicator yields to the unread dot, exactly
          like the badge yields to both. A seat that is *waiting on you* is the
          more urgent of the two, so `waiting` is the one case that outranks
          unread — otherwise the question dot would be hidden by the very
          unread state it is about to clear. */}
      {herdrStatus === 'waiting' ? (
        <HerdrStatusDot seatId={herdrSeatId} status={herdrStatus} label={dataLabel} />
      ) : null}
      {/* Static badge first: it yields at narrow widths, so it cannot be the
          reason a role-assigned row shows no recency. */}
      {badge && !unread ? <span className="os-rail-slot__badge">{badge}</span> : null}
      {unread ? (
        <span
          className="os-rail-unread-dot inline-block h-2 w-2 shrink-0 rounded-full bg-sky-500"
          aria-label="Unread"
          data-testid="rail-unread-dot"
        />
      ) : timestampLabel ? (
        <span className="os-rail-timestamp os-rail-slot__time" data-testid="rail-row-timestamp">
          {timestampLabel}
        </span>
      ) : null}
    </span>
  )
}
