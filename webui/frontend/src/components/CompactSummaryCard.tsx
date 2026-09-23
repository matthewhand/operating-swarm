import { useEffect, useId, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { Pencil } from 'lucide-react'
import { DisclosureChevron } from './DisclosureChevron'
import { compactedCardCopyText } from '../lib/compactedCardMenu'
import { useCompactedCardMenu } from './CompactedCardContextMenu'
import { Textarea } from './DaisyUI'

export interface CompactSummaryCardProps {
  title?: string
  body: string
  meta?: string
  nested?: ReactNode
  className?: string
  defaultExpanded?: boolean
  /** Extra original turns copied with the summary (full underlying text). */
  compacted?: Array<{ role: string; agent?: string; text: string }>
  onRemove?: () => void
  children?: ReactNode
  /** #214: live include-in-context state; omit for view-only/system pills. */
  inContext?: boolean
  onToggleContext?: (include: boolean) => void
  /** #57: summaries edit the same way regular chat bubbles do. */
  canEdit?: boolean
  onSaveEdit?: (text: string) => void
}

/**
 * Compact / summary chip (#672 / REQ-37) with REQ-213 right-click menu.
 * Default stays expanded so the LLM summary text remains visible.
 *
 * #214: when ``inContext`` is provided the card carries a live checkbox —
 * unticked = the summary (and its span) stop feeding model context while the
 * transcript row stays put (visual state: dimmed + "not in context").
 */
export function CompactSummaryCard({
  title = 'Summary',
  body,
  meta,
  nested,
  className = '',
  defaultExpanded = true,
  compacted,
  onRemove,
  children,
  inContext,
  onToggleContext,
  canEdit = false,
  onSaveEdit,
}: CompactSummaryCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [removed, setRemoved] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(body)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const contentId = useId()
  const copyText = compactedCardCopyText({ text: body, compacted })
  const { onContextMenu, onKeyDown, menuNode } = useCompactedCardMenu({
    label: title,
    expanded,
    copyText,
    onToggleExpand: () => setExpanded((prev) => !prev),
    onRemove: () => {
      if (onRemove) onRemove()
      else setRemoved(true)
    },
    inContext,
    onToggleContext,
  })

  useEffect(() => {
    if (!editing) return
    setDraft(body)
    const id = window.setTimeout(() => textareaRef.current?.focus(), 0)
    return () => window.clearTimeout(id)
  }, [editing, body])

  if (removed) return null
  const hasContextToggle = typeof inContext === 'boolean'
  const excluded = hasContextToggle && !inContext
  const startEdit = () => {
    if (!canEdit || editing) return
    setEditing(true)
    setExpanded(true)
  }
  const cancelEdit = () => {
    setDraft(body)
    setEditing(false)
  }
  const saveEdit = () => {
    onSaveEdit?.(draft)
    setEditing(false)
  }

  const handleBodyClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!canEdit || editing) return
    const target = event.target as HTMLElement | null
    if (target?.closest('a, button, textarea, input')) return
    startEdit()
  }

  const handleEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      cancelEdit()
      return
    }
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      saveEdit()
    }
  }

  return (
    <div
      className={`group ${className} ${excluded ? 'opacity-60' : ''}`.trim()}
      data-testid="chat-summary"
      data-in-context={hasContextToggle ? String(inContext) : undefined}
      data-can-edit={canEdit ? 'true' : 'false'}
      onContextMenu={onContextMenu}
    >
      <div className="inline-flex items-start gap-2">
        {hasContextToggle ? (
          <input
            type="checkbox"
            className="checkbox checkbox-xs mt-0.5"
            checked={inContext}
            onChange={(event) => onToggleContext?.(event.target.checked)}
            aria-label="Include in chat context"
            title={
              inContext
                ? 'Included in chat context — untick to stop feeding the model (saves tokens).'
                : 'Not in chat context — tick to resume feeding the model.'
            }
            data-testid="summary-context-checkbox"
          />
        ) : null}
        <button
          type="button"
          className="chat-summary__chip inline-flex items-center gap-1.5 rounded-full border border-base-content/20 bg-base-200/80 hover:bg-base-200 px-2.5 py-1 text-xs font-medium text-base-content/75 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary cursor-pointer select-none"
          data-testid="chat-summary-chip"
          aria-expanded={expanded}
          aria-controls={contentId}
          aria-label={title}
          onClick={() => setExpanded((prev) => !prev)}
          onKeyDown={onKeyDown}
        >
          <span>{title}</span>
          <DisclosureChevron
            expanded={expanded}
            className="h-3.5 w-3.5 opacity-60 shrink-0"
          />
        </button>
        {canEdit && !editing ? (
          <button
            type="button"
            className="btn btn-ghost btn-xs gap-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
            aria-label="Edit message"
            data-testid="summary-edit-button"
            onClick={startEdit}
          >
            <Pencil className="h-3 w-3" aria-hidden="true" />
            Edit
          </button>
        ) : null}
      </div>
      {expanded ? (
        <div id={contentId} data-testid="chat-summary-content">
          {editing ? (
            <div className="mt-2">
              <Textarea
                ref={textareaRef}
                aria-label="Edit message"
                size="sm"
                className="w-full min-h-24"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleEditorKeyDown}
              />
              <div className="mt-2 flex justify-end gap-1">
                <button type="button" className="btn btn-ghost btn-xs" onClick={cancelEdit}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary btn-xs" onClick={saveEdit}>
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div
              className="chat-summary__body whitespace-pre-wrap break-words"
              data-testid="chat-summary-body"
              onClick={handleBodyClick}
            >
              {body}
            </div>
          )}
          {meta ? <div className="chat-summary__meta">{meta}</div> : null}
          {excluded ? (
            <div className="chat-summary__meta" data-testid="summary-excluded-note">
              Not included in chat context — the model will not see this summary.
            </div>
          ) : null}
          {children}
          {nested}
        </div>
      ) : null}
      {menuNode}
    </div>
  )
}
