import { ChevronsRight } from 'lucide-react'
import { BrandMarkMono } from './BrandMarkMono'

/** DaisyUI `btn-sm` meets the ≥32px touch target; square keeps the mark centered. */
const CONCEAL_BTN =
  'btn btn-ghost btn-sm btn-square min-h-8 min-w-8 h-8 w-8 text-base-content'

/** Left rail: mono brand mark conceals the expanded sidebar. */
export function SidebarConcealButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className={CONCEAL_BTN}
      aria-label="Conceal sidebar"
      title="Conceal sidebar"
      data-testid="sidebar-conceal"
      onClick={onClick}
    >
      <BrandMarkMono className="h-5 w-5" />
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
