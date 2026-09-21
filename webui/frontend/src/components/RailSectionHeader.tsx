import {
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from 'react'
import { MessageSquareOff } from 'lucide-react'
import { DisclosureChevron } from './DisclosureChevron'
import {
  EMPTY_SECTION_HINT,
  NEW_SECTION_PLACEHOLDER,
} from '../lib/railSections'
import { isRailMenuKey } from '../lib/railContextMenu'

export interface RailSectionHeaderProps {
  sectionId: string
  name: string
  count: number
  collapsed: boolean
  custom: boolean
  internalOnly?: boolean
  editing: boolean
  editValue: string
  dropActive?: boolean
  onToggle: () => void
  onToggleTalkLock?: () => void
  onContextMenu?: (event: { clientX: number; clientY: number }) => void
  onEditChange: (value: string) => void
  onEditCommit: () => void
  onEditCancel: () => void
  onDragOver?: (event: React.DragEvent) => void
  onDrop?: (event: React.DragEvent) => void
}

export default function RailSectionHeader({
  sectionId,
  name,
  count,
  collapsed,
  custom,
  internalOnly,
  editing,
  editValue,
  dropActive,
  onToggle,
  onToggleTalkLock,
  onContextMenu,
  onEditChange,
  onEditCommit,
  onEditCancel,
  onDragOver,
  onDrop,
}: RailSectionHeaderProps) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const displayName = name.trim() || NEW_SECTION_PLACEHOLDER

  useEffect(() => {
    if (!editing) return
    const node = inputRef.current
    if (!node) return
    node.focus()
    node.select()
  }, [editing])

  const openMenu = (event: ReactMouseEvent | ReactKeyboardEvent<HTMLElement>) => {
    if (!custom || !onContextMenu) return
    event.preventDefault()
    event.stopPropagation()
    if ('clientX' in event) {
      onContextMenu({ clientX: event.clientX, clientY: event.clientY })
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    onContextMenu({ clientX: rect.left + 12, clientY: rect.bottom })
  }

  return (
    <div
      className={`os-rail-section-header group/section ${dropActive ? 'os-rail-section-header--drop' : ''}`}
      data-testid="rail-section-header"
      data-section-id={sectionId}
      data-custom={custom ? 'true' : 'false'}
      data-collapsed={collapsed ? 'true' : 'false'}
      data-internal-only={internalOnly ? 'true' : 'false'}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onContextMenu={custom ? openMenu : undefined}
    >
      {editing ? (
        <input
          ref={inputRef}
          className="os-rail-section-rename"
          value={editValue}
          placeholder={NEW_SECTION_PLACEHOLDER}
          aria-label="Section name"
          data-testid="rail-section-rename"
          onChange={(event) => onEditChange(event.target.value)}
          onBlur={onEditCommit}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              onEditCommit()
            }
            if (event.key === 'Escape') {
              event.preventDefault()
              onEditCancel()
            }
          }}
        />
      ) : (
        <>
          <button
            type="button"
            className="os-rail-section-header__btn"
            aria-expanded={!collapsed}
            aria-label={
              collapsed
                ? `Expand ${displayName} (${count})`
                : `Collapse ${displayName} (${count})`
            }
            onClick={onToggle}
            onKeyDown={(event) => {
              if (custom && isRailMenuKey(event)) openMenu(event)
            }}
          >
            <span className="os-rail-section-name" data-testid="rail-section-name">
              {displayName}
            </span>
            <span className="os-rail-section-tail" data-testid="rail-section-tail">
              {custom && internalOnly ? (
                <button
                  type="button"
                  className="os-rail-section-lock"
                  data-testid="rail-section-awareness-toggle"
                  aria-pressed={true}
                  aria-label="Inter-agent awareness off — members isolated"
                  title="Awareness off — members operate in isolation, unaware of section peers"
                  onClick={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    onToggleTalkLock?.()
                  }}
                >
                  <MessageSquareOff className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              ) : null}
              <span
                className="os-rail-section-count inline group-hover/section:hidden"
                data-testid="rail-section-count"
              >
                {count}
              </span>
              <span
                className="os-rail-section-toggle hidden group-hover/section:inline"
                aria-hidden="true"
                data-testid="rail-section-toggle"
              >
                <DisclosureChevron expanded={!collapsed} className="h-3.5 w-3.5" />
              </span>
            </span>
          </button>
        </>
      )}
    </div>
  )
}

export function RailSectionEmpty({
  dropActive,
  onDragOver,
  onDrop,
  unassigned,
}: {
  dropActive?: boolean
  onDragOver?: (event: React.DragEvent) => void
  onDrop?: (event: React.DragEvent) => void
  /** #781: the Unassigned pool is a distinct drop target — named, and never
      styled like the destructive Delete bin. */
  unassigned?: boolean
}) {
  return (
    <div
      className={`os-rail-section-empty ${dropActive ? 'os-rail-section-empty--drop' : ''} ${
        unassigned ? 'os-rail-section-empty--unassigned' : ''
      }`}
      data-testid="rail-section-empty"
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {unassigned ? 'Unassigned — drop to move here' : EMPTY_SECTION_HINT}
    </div>
  )
}
