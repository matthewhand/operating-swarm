import type { ReactNode } from 'react'

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
export interface RailRowSlotProps {
  /** The row's ⌥N / Alt+N spill index, when the row has one. */
  spillSlot?: number
  isMac: boolean
  unread?: boolean
  /** Static role badge. Rendered alongside the time, yielding before it. */
  badge?: ReactNode
  /** `formatRailTimestamp` returns null when there is no activity to show. */
  timestampLabel?: string | null
  dataRole?: string
}

export default function RailRowSlot({
  spillSlot,
  isMac,
  unread,
  badge,
  timestampLabel,
  dataRole,
}: RailRowSlotProps) {
  const tip = spillSlot ? (isMac ? `⌥${spillSlot}` : `Alt+${spillSlot}`) : ''
  return (
    <span
      className={`os-rail-slot relative flex shrink-0 items-center${
        tip ? ' os-rail-slot--has-tip' : ''
      }`}
      data-testid="rail-row-slot"
      data-role={dataRole}
    >
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
      {tip ? (
        <span
          className="os-rail-shortcut os-rail-shortcut--layered text-[10px] font-mono text-base-content/40"
          aria-label={`Shortcut ${isMac ? '⌥' : 'Alt+'}${spillSlot}`}
          data-testid="spill-hotkey"
        >
          {tip}
        </span>
      ) : null}
    </span>
  )
}
