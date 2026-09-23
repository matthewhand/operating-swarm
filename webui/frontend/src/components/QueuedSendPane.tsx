import { useEffect, useMemo, useRef, useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { Textarea } from './DaisyUI'
import {
  QUEUED_PANE_MAX_HEIGHT_CLASS,
  QUEUED_PANE_MAX_HEIGHT_STYLE,
  type QueuedSendRow,
  queuedPreviewIsTruncated,
  queuedPreviewText,
} from '../lib/chatQueue'

export function QueuedSendPane({
  rows,
  maxHeightPx = 0,
  onChangeText,
  onDelete,
  onClearAll,
  onHoldIdsChange,
  interruptible = false,
}: {
  rows: QueuedSendRow[]
  maxHeightPx?: number
  onChangeText: (id: string, text: string) => void
  onDelete: (id: string) => void
  /** #223: drop every queued row ("Clear all") — no backend call. */
  onClearAll?: () => void
  onHoldIdsChange: (ids: string[]) => void
  /** #198: when true, the top row shows the "enter to interrupt" hint. */
  interruptible?: boolean
}) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const editorRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    if (editingId && !rows.some((row) => row.id === editingId)) {
      setEditingId(null)
      setDraft('')
    }
  }, [editingId, rows])

  useEffect(() => {
    if (!editingId) return
    const id = window.setTimeout(() => editorRef.current?.focus(), 0)
    return () => window.clearTimeout(id)
  }, [editingId])

  const holdIds = useMemo(() => {
    if (!editingId) return [] as string[]
    return [editingId]
  }, [editingId])

  useEffect(() => {
    onHoldIdsChange(holdIds)
  }, [holdIds, onHoldIdsChange])

  if (rows.length === 0) return null

  const maxHeight = maxHeightPx > 0 ? `${maxHeightPx}px` : QUEUED_PANE_MAX_HEIGHT_STYLE

  const commitEdit = (id: string) => {
    onChangeText(id, draft)
    setEditingId(null)
    setDraft('')
  }

  return (
    <section
      className={`os-queued-pane ${QUEUED_PANE_MAX_HEIGHT_CLASS} overflow-y-auto`}
      data-testid="queued-send-pane"
      aria-label="Queued messages"
      style={{ maxHeight }}
    >
      {rows.length > 1 && onClearAll ? (
        <div className="os-queued-pane__header flex items-center justify-end px-1 pt-1">
          <button
            type="button"
            className="btn btn-ghost btn-xs gap-1 text-base-content/60"
            aria-label="Clear all queued messages"
            title="Remove every queued message (no backend call)"
            data-testid="queued-clear-all"
            onMouseDown={(event) => event.preventDefault()}
            onClick={onClearAll}
          >
            <Trash2 className="h-3 w-3" aria-hidden="true" />
            Clear all
          </button>
        </div>
      ) : null}
      <ul className="os-queued-pane__list" role="list">
        {rows.map((row) => {
          const editing = editingId === row.id
          return (
            <li
              key={row.id}
              className="os-queued-row"
              data-testid="queued-row"
              data-status="queued"
              data-queued-id={row.id}
            >
              <span className="badge badge-ghost badge-sm os-queued-row__badge">Queued</span>
              {editing ? (
                <div className="os-queued-row__editor">
                  <Textarea
                    ref={editorRef}
                    aria-label="Edit queued message"
                    size="sm"
                    className="w-full min-h-16"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={() => commitEdit(row.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') {
                        event.preventDefault()
                        event.stopPropagation()
                        setEditingId(null)
                        setDraft('')
                      }
                      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                        event.preventDefault()
                        commitEdit(row.id)
                      }
                    }}
                  />
                  <div className="os-queued-row__actions">
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        setEditingId(null)
                        setDraft('')
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary btn-xs"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => commitEdit(row.id)}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className={`os-queued-row__text${
                    queuedPreviewIsTruncated(row.text) ? ' is-truncated' : ''
                  }`}
                  title={row.text}
                  onClick={() => {
                    setEditingId(row.id)
                    setDraft(row.text)
                  }}
                >
                  {queuedPreviewText(row.text)}
                </button>
              )}
              {interruptible && row.id === rows[0]?.id && (
                <span
                  className="os-queued-row__hint kbd kbd-xs"
                  data-testid="queued-interrupt-hint"
                  title="Enter on the empty composer interrupts the running turn and sends this"
                >
                  ↵ interrupt
                </span>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-square os-queued-row__remove"
                aria-label="Remove queued message"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onDelete(row.id)}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
