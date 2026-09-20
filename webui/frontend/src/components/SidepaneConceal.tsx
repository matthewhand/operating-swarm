import { ChevronsRight, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

/** DaisyUI `btn-sm` meets the ≥32px touch target; square keeps the mark centered. */
const CONCEAL_BTN =
  'btn btn-ghost btn-sm btn-square min-h-8 min-w-8 h-8 w-8 text-base-content'

/** Left rail: standard pane icon collapses the expanded sidebar (#767). */
export function SidebarConcealButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className={CONCEAL_BTN}
      aria-label="Collapse sidebar"
      title="Collapse sidebar"
      data-testid="sidebar-conceal"
      onClick={onClick}
    >
      <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
    </button>
  )
}

/** Left rail: close-pane / expand control when the rail is avatar-only (#417, #767). */
export function SidebarExpandButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className={CONCEAL_BTN}
      aria-label="Expand sidebar"
      title="Expand sidebar"
      data-testid="sidebar-expand"
      onClick={onClick}
    >
      <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
    </button>
  )
}

/** Right-docked sheets/panels: `>>` tucks the pane toward the right edge. */
export function SidepaneConcealButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className={CONCEAL_BTN}
      aria-label="Conceal sidepane"
      title="Conceal sidepane"
      data-testid="sidepane-conceal"
      onClick={onClick}
    >
      <ChevronsRight className="h-4 w-4" aria-hidden="true" />
    </button>
  )
}
