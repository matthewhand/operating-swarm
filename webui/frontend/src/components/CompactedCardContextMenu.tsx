import { useCallback, useEffect, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  COPY_EMPTY_MESSAGE,
  COPY_EMPTY_TITLE,
  COPY_FAILED_MESSAGE,
  COPY_FAILED_TITLE,
  copyTextToClipboard,
  messageHasCopyableText,
} from '../lib/clipboard'
import {
  compactedCardMenuItems,
  type CompactedCardMenuId,
} from '../lib/compactedCardMenu'
import { isRailMenuKey, type RailMenuItemId } from '../lib/railContextMenu'
import { useOptionalToast } from './DaisyUI'
import RailContextMenu from './RailContextMenu'

export interface CompactedCardMenuPosition {
  x: number
  y: number
}

export interface CompactedCardContextMenuProps {
  label: string
  x: number
  y: number
  items: ReturnType<typeof compactedCardMenuItems>
  onSelect: (id: CompactedCardMenuId) => void
  onClose: () => void
}

/**
 * DaisyUI menu for compacted cards. Same chrome as RailContextMenu (#435).
 */
export default function CompactedCardContextMenu({
  label,
  x,
  y,
  items,
  onSelect,
  onClose,
}: CompactedCardContextMenuProps) {
  const maxX = typeof window !== 'undefined' ? window.innerWidth - 220 : x
  const maxY = typeof window !== 'undefined' ? window.innerHeight - 140 : y
  return (
    <>
      <div
        className="fixed inset-0 z-40"
        data-testid="compacted-card-menu-backdrop"
        onClick={onClose}
        onContextMenu={(event) => {
          event.preventDefault()
          onClose()
        }}
      />
      <RailContextMenu
        agentName={label}
        x={Math.min(x, maxX)}
        y={Math.min(y, maxY)}
        items={items}
        testId="compacted-card-context-menu"
        onSelect={(id: RailMenuItemId) => onSelect(id as CompactedCardMenuId)}
      />
    </>
  )
}

function selectionIsActive(): boolean {
  try {
    const sel = window.getSelection()
    return Boolean(sel && !sel.isCollapsed)
  } catch {
    return false
  }
}

export interface UseCompactedCardMenuOptions {
  label: string
  expanded: boolean
  copyText: string
  onToggleExpand: () => void
  onRemove: () => void
  /** Provided only for real summaries — adds the context tick item. */
  inContext?: boolean
  onToggleContext?: (include: boolean) => void
}

export function useCompactedCardMenu({
  label,
  expanded,
  copyText,
  onToggleExpand,
  onRemove,
  inContext,
  onToggleContext,
}: UseCompactedCardMenuOptions) {
  const [menu, setMenu] = useState<CompactedCardMenuPosition | null>(null)
  const toast = useOptionalToast()
  const canCopy = messageHasCopyableText(copyText)
  const items = compactedCardMenuItems({ expanded, canCopy, inContext })

  const closeMenu = useCallback(() => setMenu(null), [])

  useEffect(() => {
    if (!menu) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeMenu()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menu, closeMenu])

  const openAt = useCallback((x: number, y: number) => {
    setMenu({ x, y })
  }, [])

  const onContextMenu = useCallback(
    (event: MouseEvent) => {
      if (selectionIsActive()) return
      event.preventDefault()
      event.stopPropagation()
      openAt(event.clientX, event.clientY)
    },
    [openAt],
  )

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isRailMenuKey(event)) return
      event.preventDefault()
      event.stopPropagation()
      const target = event.currentTarget as HTMLElement
      const rect = target.getBoundingClientRect()
      openAt(rect.left, rect.bottom)
    },
    [openAt],
  )

  const onSelect = useCallback(
    async (id: CompactedCardMenuId) => {
      if (id === 'expand' || id === 'collapse') {
        onToggleExpand()
        closeMenu()
        return
      }
      if (id === 'copy') {
        try {
          const result = await copyTextToClipboard(copyText)
          if (result === 'empty') {
            toast?.error(COPY_EMPTY_TITLE, COPY_EMPTY_MESSAGE)
          } else if (result === 'failed') {
            toast?.error(COPY_FAILED_TITLE, COPY_FAILED_MESSAGE)
          }
        } catch {
          toast?.error(COPY_FAILED_TITLE, COPY_FAILED_MESSAGE)
        }
        closeMenu()
        return
      }
      if (id === 'include_context' || id === 'exclude_context') {
        onToggleContext?.(id === 'include_context')
        closeMenu()
        return
      }
      if (id === 'delete') {
        onRemove()
        closeMenu()
        return
      }
    },
    [closeMenu, copyText, onRemove, onToggleContext, onToggleExpand, toast],
  )

  const menuNode = menu ? (
    <CompactedCardContextMenu
      label={label}
      x={menu.x}
      y={menu.y}
      items={items}
      onSelect={onSelect}
      onClose={closeMenu}
    />
  ) : null

  return { onContextMenu, onKeyDown, menuNode, menuOpen: Boolean(menu), closeMenu }
}
