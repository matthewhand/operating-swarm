/**
 * REQ-213 / #693 — Compacted-card context menu contract.
 *
 * Shared with rail/chat menus (#435 / REQ-82): DaisyUI `menu menu-sm
 * rounded-box`, icon+label rows, danger Delete last.
 *
 * Delete / Remove from view is **view-only**. Raw transcript on disk
 * (`chat_store` JSON, Django `ChatMessage` rows, compact summary tree)
 * is not rewritten. Reload or a fresh thread hydrate restores the card.
 */

import type { RailMenuItemSpec } from './railContextMenu'

export type CompactedCardMenuId = 'expand' | 'collapse' | 'copy' | 'delete'

export const COMPACTED_CARD_DELETE_HONESTY =
  'Removes this card from the current view only. Raw transcript on disk is unchanged.'

export const COMPACTED_CARD_COPY_EMPTY = 'This card has no text to copy.'

export function messageFromLabel(source: string): string {
  const name = source.trim() || 'System'
  return `Message from ${name}`
}

export function compactedCardCopyText(opts: {
  text: string
  compacted?: Array<{ role: string; agent?: string; text: string }>
}): string {
  const main = (opts.text || '').trim()
  if (!opts.compacted?.length) return main
  const originals = opts.compacted
    .filter((line) => (line.text || '').trim())
    .map((line) => `[${line.agent || line.role}]: ${(line.text || '').trim()}`)
    .join('\n\n')
  if (!originals) return main
  return main ? `${main}\n\n---\n${originals}` : originals
}

export function compactedCardMenuItems(opts: {
  expanded: boolean
  canCopy?: boolean
}): RailMenuItemSpec[] {
  const canCopy = opts.canCopy !== false
  const items: RailMenuItemSpec[] = [
    opts.expanded
      ? { id: 'collapse', label: 'Collapse', group: 0 }
      : { id: 'expand', label: 'Expand', group: 0 },
    {
      id: 'copy',
      label: 'Copy',
      group: 1,
      disabled: !canCopy,
      reason: canCopy ? undefined : COMPACTED_CARD_COPY_EMPTY,
    },
    {
      id: 'delete',
      label: 'Remove from view',
      group: 2,
      danger: true,
      reason: COMPACTED_CARD_DELETE_HONESTY,
    },
  ]
  return items
}
