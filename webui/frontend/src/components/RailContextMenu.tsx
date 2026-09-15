import { Fragment, useLayoutEffect, useRef, useState, type Ref } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowDown,
  ArrowUp,
  Bell,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  CircleStop,
  ClipboardCopy,
  CopyPlus,
  Eye,
  EyeOff,
  FolderInput,
  FolderPlus,
  History,
  MessageSquarePlus,
  Pencil,
  Pin,
  PinOff,
  Trash2,
  Users,
  CircleCheck,
} from 'lucide-react'
import type { RailMenuItemId, RailMenuItemSpec, RailMenuSubItemSpec } from '../lib/railContextMenu'

const ICONS: Record<RailMenuItemId, LucideIcon> = {
  'select-agent': Users,
  'select-session': History,
  'new-session': MessageSquarePlus,
  unpin: PinOff,
  pin: Pin,
  'move-to': FolderInput,
  unread: Circle,
  edit: Pencil,
  duplicate: CopyPlus,
  'copy-id': ClipboardCopy,
  terminate: CircleStop,
  hide: EyeOff,
  unhide: Eye,
  notify: Bell,
  delete: Trash2,
  'section-create': FolderPlus,
  'section-rename': Pencil,
  'section-move-up': ArrowUp,
  'section-move-down': ArrowDown,
  'section-delete': Trash2,
  expand: ChevronDown,
  collapse: ChevronUp,
  copy: ClipboardCopy,
  include_context: CircleCheck,
  exclude_context: EyeOff,
}

export interface RailMenuItemProps {
  spec: RailMenuItemSpec
  onSelect: (id: RailMenuItemId) => void
  onSubSelect?: (parentId: RailMenuItemId, childId: string) => void
}

function SubMenuItem({
  parentId,
  child,
  onSubSelect,
}: {
  parentId: RailMenuItemId
  child: RailMenuSubItemSpec
  onSubSelect?: (parentId: RailMenuItemId, childId: string) => void
}) {
  return (
    <li>
      <button
        type="button"
        role="menuitem"
        data-menu-id={parentId}
        data-move-to={child.id}
        aria-checked={child.checked || undefined}
        onClick={() => onSubSelect?.(parentId, child.id)}
      >
        <Check
          className={`h-4 w-4 ${child.checked ? '' : 'opacity-0'}`}
          aria-hidden="true"
          data-menu-icon={child.checked ? 'checked' : 'unchecked'}
        />
        {child.label}
      </button>
    </li>
  )
}

/** Shared icon+label row for rail / section / compacted-card menus (REQ-82). */
export function RailMenuItem({ spec, onSelect, onSubSelect }: RailMenuItemProps) {
  const Icon = ICONS[spec.id]
  const danger = Boolean(spec.danger)
  const [open, setOpen] = useState(false)
  if (spec.children?.length) {
    return (
      <li>
        <button
          type="button"
          role="menuitem"
          aria-haspopup="menu"
          aria-expanded={open}
          data-menu-id={spec.id}
          data-testid="rail-menu-move-to"
          onClick={() => setOpen((current) => !current)}
        >
          <Icon className="h-4 w-4" aria-hidden="true" data-menu-icon={spec.id} />
          {spec.label}
        </button>
        {open ? (
          <ul className="os-rail-menu-submenu" data-testid="rail-menu-move-to-submenu">
            {spec.children.map((child) => (
              <SubMenuItem
                key={child.id}
                parentId={spec.id}
                child={child}
                onSubSelect={onSubSelect}
              />
            ))}
          </ul>
        ) : null}
      </li>
    )
  }
  return (
    <li className={spec.disabled ? 'disabled' : undefined}>
      <button
        type="button"
        role="menuitem"
        disabled={spec.disabled}
        title={spec.reason}
        data-menu-id={spec.id}
        className={danger ? 'text-error' : undefined}
        onClick={() => {
          if (spec.disabled) return
          onSelect(spec.id)
        }}
      >
        <Icon
          className={`h-4 w-4 ${danger ? 'text-error' : ''}`}
          aria-hidden="true"
          data-menu-icon={spec.id}
        />
        {spec.label}
      </button>
    </li>
  )
}

export interface RailContextMenuProps {
  agentName: string
  x: number
  y: number
  items: RailMenuItemSpec[]
  menuRef?: Ref<HTMLUListElement>
  onSelect: (id: RailMenuItemId) => void
  onSubSelect?: (parentId: RailMenuItemId, childId: string) => void
  /** Override `rail-context-menu` for compacted-card / other shared menus. */
  testId?: string
}

export default function RailContextMenu({
  agentName,
  x,
  y,
  items,
  menuRef,
  onSelect,
  onSubSelect,
  testId = 'rail-context-menu',
}: RailContextMenuProps) {
  // Clamp to the viewport so the menu never clips at the bottom/right edge.
  const nodeRef = useRef<HTMLUListElement | null>(null)
  const [pos, setPos] = useState({ left: x, top: y })
  useLayoutEffect(() => {
    const node = nodeRef.current
    if (!node || typeof window === 'undefined') {
      setPos({ left: x, top: y })
      return
    }
    const margin = 8
    const width = node.offsetWidth || 208
    const height = node.offsetHeight || 0
    setPos({
      left: Math.max(margin, Math.min(x, window.innerWidth - width - margin)),
      top: Math.max(margin, Math.min(y, window.innerHeight - height - margin)),
    })
  }, [x, y, items.length])
  const groups: RailMenuItemSpec[][] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    if (!last || last[0].group !== item.group) {
      groups.push([item])
    } else {
      last.push(item)
    }
  }

  return (
    <ul
      ref={(node) => {
        nodeRef.current = node
        if (typeof menuRef === 'function') menuRef(node)
        else if (menuRef) menuRef.current = node
      }}
      role="menu"
      aria-label={`Actions for ${agentName}`}
      className="menu menu-sm rounded-box fixed z-50 min-w-52 border border-base-300 bg-base-100 p-1 shadow-xl max-h-[calc(100vh-16px)] overflow-y-auto"
      style={{ left: pos.left, top: pos.top }}
      data-testid={testId}
    >
      {groups.map((group, index) => (
        <Fragment key={group[0].id}>
          {index > 0 ? (
            <li aria-hidden="true" className="pointer-events-none px-2 py-0.5">
              <hr className="border-base-300" />
            </li>
          ) : null}
          {group.map((spec) => (
            <RailMenuItem
              key={spec.id}
              spec={spec}
              onSelect={onSelect}
              onSubSelect={onSubSelect}
            />
          ))}
        </Fragment>
      ))}
    </ul>
  )
}
