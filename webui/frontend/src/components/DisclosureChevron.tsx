import { ChevronDown, ChevronRight } from 'lucide-react'

export interface DisclosureChevronProps {
  /** `true` when the region this chevron controls is open. */
  expanded: boolean
  className?: string
}

/**
 * The one disclosure chevron (#557).
 *
 * Closed points **right** (`→`), open points **down** (`↓`) — the convention the
 * rail has always used. Do **not** implement a disclosure by rotating a single
 * `ChevronDown`: `rotate-180` makes the closed state point *down* and the open
 * state point *up*, which is a different (and contradictory) language. Rotation
 * only suits a dropdown caret whose glyph never changes.
 *
 * The icon is decorative — the trigger element owns `aria-expanded`.
 */
export function DisclosureChevron({ expanded, className }: DisclosureChevronProps) {
  const Icon = expanded ? ChevronDown : ChevronRight
  return <Icon className={className} aria-hidden="true" />
}

export default DisclosureChevron
