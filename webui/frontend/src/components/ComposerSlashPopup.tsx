import { useMemo, useEffect, useRef } from 'react'
import {
  Layers,
  HelpCircle,
  Cpu,
  Trash2,
  Shield,
  History,
  GitCommit,
  FileText,
  CheckSquare,
  LifeBuoy,
  ListPlus,
  Sparkles,
  Terminal,
} from 'lucide-react'
import { SlashItem, groupSlashItems } from '../lib/slashMenu'

export interface ComposerSlashPopupProps {
  open: boolean
  query: string
  items: SlashItem[]
  selectedIndex: number
  onSelectIndex: (index: number) => void
  onSelectItem: (item: SlashItem) => void
  recentIds?: string[]
}

function SlashIcon({ iconName, className }: { iconName?: string; className?: string }) {
  switch (iconName) {
    case 'Layers':
      return <Layers className={className} aria-hidden="true" />
    case 'HelpCircle':
      return <HelpCircle className={className} aria-hidden="true" />
    case 'Cpu':
      return <Cpu className={className} aria-hidden="true" />
    case 'Trash2':
      return <Trash2 className={className} aria-hidden="true" />
    case 'Shield':
      return <Shield className={className} aria-hidden="true" />
    case 'History':
      return <History className={className} aria-hidden="true" />
    case 'GitCommit':
      return <GitCommit className={className} aria-hidden="true" />
    case 'FileText':
      return <FileText className={className} aria-hidden="true" />
    case 'CheckSquare':
      return <CheckSquare className={className} aria-hidden="true" />
    case 'LifeBuoy':
      return <LifeBuoy className={className} aria-hidden="true" />
    case 'ListPlus':
      return <ListPlus className={className} aria-hidden="true" />
    case 'Sparkles':
      return <Sparkles className={className} aria-hidden="true" />
    default:
      return <Terminal className={className} aria-hidden="true" />
  }
}

export function ComposerSlashPopup({
  open,
  query,
  items,
  selectedIndex,
  onSelectIndex,
  onSelectItem,
  recentIds = [],
}: ComposerSlashPopupProps) {
  const listRef = useRef<HTMLDivElement>(null)

  const groups = useMemo(
    () => groupSlashItems(items, query, recentIds),
    [items, query, recentIds],
  )

  // Scroll active item into view
  useEffect(() => {
    if (!open || !listRef.current) return
    const activeEl = listRef.current.querySelector('[aria-selected="true"]')
    if (activeEl && typeof activeEl.scrollIntoView === 'function') {
      activeEl.scrollIntoView({ block: 'nearest' })
    }
  }, [open, selectedIndex])

  if (!open) return null

  let itemCounter = 0

  return (
    <div
      ref={listRef}
      id="composer-slash-menu"
      role="listbox"
      aria-label="Skills and actions"
      className="os-slash-popup absolute bottom-[calc(100%+0.5rem)] left-0 right-0 z-30 max-h-80 overflow-y-auto rounded-2xl border border-base-300 bg-base-100/95 p-1.5 shadow-2xl backdrop-blur-md"
      data-testid="composer-slash-popup"
    >
      {items.length === 0 ? (
        <div
          className="py-6 text-center text-sm text-base-content/50"
          data-testid="slash-empty"
        >
          No matching skills or actions
        </div>
      ) : (
        groups.map((group) => (
          <div key={group.label} className="mb-1.5 last:mb-0">
            <div className="px-2.5 py-1 text-[11px] font-semibold tracking-wider uppercase text-base-content/40">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const currentIndex = itemCounter++
                const isSelected = currentIndex === selectedIndex
                return (
                  <button
                    key={`${group.label}-${item.id}`}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={item.unavailableReason ? true : undefined}
                    disabled={Boolean(item.unavailableReason)}
                    title={item.unavailableReason || undefined}
                    data-testid={`slash-item-${item.id}`}
                    data-slash-kind={item.kind}
                    className={`group flex w-full min-h-[44px] items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors ${
                      isSelected
                        ? 'bg-base-200 text-base-content font-medium'
                        : 'text-base-content/85 hover:bg-base-200/60'
                    } ${
                      item.unavailableReason
                        ? 'cursor-not-allowed opacity-50 hover:bg-transparent'
                        : ''
                    }`}
                    onMouseEnter={() => onSelectIndex(currentIndex)}
                    onClick={(e) => {
                      e.preventDefault()
                      if (item.unavailableReason) return
                      onSelectItem(item)
                    }}
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-base-300/60 text-base-content/70 group-hover:text-base-content">
                        <SlashIcon iconName={item.iconName} className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm truncate">{item.title}</span>
                          <code className="text-xs text-base-content/50 font-mono">
                            {item.command}
                          </code>
                        </div>
                        <p className="text-xs text-base-content/60 truncate">
                          {item.description}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {group.label === 'Recent' ? (
                        <span className="badge badge-xs badge-ghost text-[10px] text-base-content/60 px-1.5 py-0.5">
                          Recent
                        </span>
                      ) : null}
                      {item.kind === 'action' ? (
                        <span className="badge badge-xs badge-primary badge-outline text-[10px] tracking-wide uppercase px-1.5 py-0.5">
                          Action
                        </span>
                      ) : item.kind === 'cli' ? (
                        item.unavailableReason ? (
                          <span className="badge badge-xs badge-warning badge-outline text-[10px] tracking-wide uppercase px-1.5 py-0.5">
                            Unavailable
                          </span>
                        ) : (
                          <span className="badge badge-xs badge-accent badge-outline text-[10px] tracking-wide uppercase px-1.5 py-0.5">
                            CLI
                          </span>
                        )
                      ) : (
                        <span className="badge badge-xs badge-neutral text-[10px] tracking-wide uppercase px-1.5 py-0.5">
                          Skill
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        ))
      )}

      <div className="border-t border-base-300/50 mt-1 px-3 py-1.5 flex items-center justify-between text-[11px] text-base-content/40">
        <span>Type to filter</span>
        <span className="hidden sm:flex items-center gap-1.5">
          <kbd className="kbd kbd-xs">↑</kbd>
          <kbd className="kbd kbd-xs">↓</kbd>
          <span>navigate</span>
          <span className="mx-0.5">·</span>
          <kbd className="kbd kbd-xs">↵</kbd>
          <span>select</span>
          <span className="mx-0.5">·</span>
          <kbd className="kbd kbd-xs">esc</kbd>
          <span>dismiss</span>
        </span>
      </div>
    </div>
  )
}
