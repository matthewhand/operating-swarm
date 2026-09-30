/**
 * #1705 — the rail's bulk-action bar.
 *
 * Multi-select used to be silent: rows highlighted, nothing said what to do
 * with them. This is the affordance that makes the gesture worth knowing —
 * it appears at two or more selected seats (never at one, where a plain click
 * already opened the seat) and it is ALWAYS visible, never hover-revealed, so
 * a selection is never a state only the pointer can see.
 *
 * Presentational on purpose: the store writes live in the rail (they are the
 * same `lib/hiddenAgents` / `lib/pinnedAgents` helpers the per-row context
 * menu uses), so this only needs ids, labels and callbacks.
 */
import { EyeOff, PinOff, X } from 'lucide-react'

export interface RailBulkBarProps {
  selectedIds: string[]
  /** How many of the selection are currently hidden / pinned (label accuracy). */
  hiddenCount: number
  pinnedCount: number
  onClear: () => void
  onHide: () => void
  onUnpin: () => void
}

export const RAIL_BULK_BAR_TESTID = 'os-rail-bulk-bar'

export default function RailBulkBar({
  selectedIds,
  hiddenCount,
  pinnedCount,
  onClear,
  onHide,
  onUnpin,
}: RailBulkBarProps) {
  const count = selectedIds.length
  if (count < 2) return null
  const hideLabel = `Hide ${count} selected`
  const unpinLabel = pinnedCount > 0 ? `Unpin ${pinnedCount} selected` : 'Unpin selected'
  return (
    <div
      className="os-rail-bulk-bar"
      data-testid={RAIL_BULK_BAR_TESTID}
      data-selected-count={String(count)}
      role="group"
      aria-label={`Bulk actions for ${count} selected agents`}
    >
      <span className="os-rail-bulk-bar__count" data-testid="os-rail-bulk-count">
        {/* The count is the live region: a screen reader hears the selection
            grow without the focus ever leaving the row it is on. */}
        <span role="status" aria-live="polite">
          {count} selected
        </span>
        {/* Success criterion #1 — the gesture model was undocumented, which is
            why operators only found it by accident. */}
        <span className="sr-only">
          . Click a row to open it, Ctrl or Command click to add or remove one,
          Shift click for a range, Space on a focused row to toggle it, Escape
          to clear.
        </span>
      </span>
      <div className="os-rail-bulk-bar__actions">
        <button
          type="button"
          className="os-rail-bulk-bar__btn"
          data-testid="os-rail-bulk-hide"
          aria-label={hideLabel}
          title={hideLabel}
          disabled={hiddenCount === count}
          onClick={onHide}
        >
          <EyeOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="os-rail-bulk-bar__btn-label">Hide</span>
        </button>
        <button
          type="button"
          className="os-rail-bulk-bar__btn"
          data-testid="os-rail-bulk-unpin"
          aria-label={unpinLabel}
          title={unpinLabel}
          disabled={pinnedCount === 0}
          onClick={onUnpin}
        >
          <PinOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="os-rail-bulk-bar__btn-label">Unpin</span>
        </button>
        <button
          type="button"
          className="os-rail-bulk-bar__btn os-rail-bulk-bar__btn--clear"
          data-testid="os-rail-bulk-clear"
          aria-label="Clear selection"
          title="Clear selection (Esc)"
          onClick={onClear}
        >
          <X className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="os-rail-bulk-bar__btn-label">Clear</span>
        </button>
      </div>
    </div>
  )
}
