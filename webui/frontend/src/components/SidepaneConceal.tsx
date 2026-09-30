import { ChevronsRight, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

/** #1655: 2.25rem square — the rail's shared icon-control rhythm (the search
 * pill and the Add agent button are both 2.25rem) — so the conceal/expand
 * control sits on the same hit-box axis as its row siblings instead of a
 * smaller 32px box on the same centerline. DaisyUI `btn-sm` sizes type;
 * the h-9/min-h-9 overrides set the footprint. */
const CONCEAL_BTN =
  'btn btn-ghost btn-sm btn-square min-h-9 min-w-9 h-9 w-9 text-base-content'

/** Left rail: standard pane icon collapses the expanded sidebar (#767). */
export function SidebarConcealButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      /* #1711: `os-rail-conceal` is the styling hook for the 1-col search row,
         which reorders this control ahead of `+` so the trio wraps as one group
         with Search instead of orphaning collapse on a row of its own. Named
         for the rail it lives in (this variant is rail-only) so the right-dock
         sidepane and the collapsed/avatar-only expanders stay unstyled by it. */
      className={`${CONCEAL_BTN} os-rail-conceal`}
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
