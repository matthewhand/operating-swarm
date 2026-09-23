import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Check, Copy, FoldVertical, Pencil, Reply, RotateCcw, ScrollText, Smile } from 'lucide-react'
import type { Agent, ChatMessage } from '../../types/agent'
import { AgentAvatar } from '../AgentSidebar/AgentAvatar'
import { Textarea, useToast } from '../DaisyUI'
import { roleMeta } from '../../lib/agent-roles'
import {
  COPY_EMPTY_MESSAGE,
  COPY_EMPTY_TITLE,
  COPY_FAILED_MESSAGE,
  COPY_FAILED_TITLE,
  copyButtonLabel,
  copyTextToClipboard,
  messageHasCopyableText,
} from '../../lib/clipboard'
import { renderSafeMarkdown } from '../../lib/markdown'
import { SystemPreloadPill } from '../SystemPreloadPill'
import { useCompactedCardMenu } from '../CompactedCardContextMenu'
import { compactedCardCopyText, messageFromLabel } from '../../lib/compactedCardMenu'

interface AgentMessageBubbleProps {
  message: ChatMessage
  agent?: Agent
  onOpenDelegation?: (delegationId: string) => void
  canCompact?: boolean
  compacting?: boolean
  regenerating?: boolean
  onCompactToHere?: () => void
  onRegenerateSummary?: (steer: string) => void
  onResolveApproval?: (status: 'approved' | 'rejected') => void
  onAddReaction?: (messageKey: string, emoji?: string) => void
  onReply?: () => void
  /** REQ-213: view-only hide. Raw transcript stays on disk. */
  onRemoveCard?: () => void
  /** Persist an in-place summary edit (draft → save). */
  onSaveEdit?: (text: string) => void
}

export function AgentMessageBubble({
  message,
  agent,
  onOpenDelegation,
  canCompact = false,
  compacting = false,
  regenerating = false,
  onCompactToHere,
  onRegenerateSummary,
  onResolveApproval,
  onAddReaction,
  onReply,
  onRemoveCard,
  onSaveEdit,
}: AgentMessageBubbleProps) {
  const isUser = message.role === 'user'
  const isSummary = message.kind === 'summary'
  const [copied, setCopied] = useState(false)
  const [originalOpen, setOriginalOpen] = useState(false)
  const [steer, setSteer] = useState('')
  const [summaryExpanded, setSummaryExpanded] = useState(true)
  const [summaryRemoved, setSummaryRemoved] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.text)
  const [savedText, setSavedText] = useState<string | null>(null)
  const [localEdited, setLocalEdited] = useState(Boolean(message.edited))
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const { error } = useToast()
  const summaryBody = savedText ?? message.text
  const summaryEdited = Boolean(message.edited) || localEdited
  const displayText = isSummary ? summaryBody : message.text
  const canCopy = messageHasCopyableText(displayText)
  const summaryCopyText = compactedCardCopyText({
    text: summaryBody,
    compacted: message.compacted,
  })
  const summaryMenu = useCompactedCardMenu({
    label: 'Conversation summary',
    expanded: summaryExpanded,
    copyText: summaryCopyText,
    onToggleExpand: () => setSummaryExpanded((prev) => !prev),
    onRemove: () => {
      if (onRemoveCard) onRemoveCard()
      else setSummaryRemoved(true)
    },
  })

  useEffect(() => {
    setSavedText(null)
    setLocalEdited(Boolean(message.edited))
    setDraft(message.text)
    setEditing(false)
  }, [message.text, message.edited])

  useEffect(() => {
    if (!editing) return undefined
    const id = window.setTimeout(() => textareaRef.current?.focus(), 0)
    return () => window.clearTimeout(id)
  }, [editing])

  if (message.kind === 'system' || message.isSystemPreload || (message.role as string) === 'system') {
    const source =
      message.agent && message.agent.trim() && message.agent !== 'System'
        ? message.agent
        : 'System'
    return (
      <SystemPreloadPill
        text={message.text}
        label={messageFromLabel(source)}
        onRemove={onRemoveCard}
      />
    )
  }

  const startSummaryEdit = () => {
    setDraft(summaryBody)
    setEditing(true)
  }

  const cancelSummaryEdit = () => {
    setDraft(summaryBody)
    setEditing(false)
  }

  const saveSummaryEdit = () => {
    setSavedText(draft)
    setLocalEdited(true)
    setEditing(false)
    onSaveEdit?.(draft)
  }

  const handleSummaryEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      cancelSummaryEdit()
      return
    }
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      saveSummaryEdit()
    }
  }

  const handleCopy = async () => {
    const result = await copyTextToClipboard(displayText)
    if (result === 'copied') {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
      return
    }
    if (result === 'empty') {
      error(COPY_EMPTY_TITLE, COPY_EMPTY_MESSAGE)
      return
    }
    error(COPY_FAILED_TITLE, COPY_FAILED_MESSAGE)
  }

  if (message.kind === 'approval') {
    const pending = (message.approval?.status || 'pending') === 'pending'
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] w-full rounded-none border border-warning/50 bg-warning/10 px-3.5 py-2.5 text-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-warning mb-1">
            Stupidity checker · needs approval
          </div>
          <p className="whitespace-pre-wrap">{message.text}</p>
          {pending ? (
            <div className="mt-2 flex gap-1">
              <button
                type="button"
                className="btn btn-xs btn-warning rounded-none"
                onClick={() => onResolveApproval?.('approved')}
              >
                Approve
              </button>
              <button
                type="button"
                className="btn btn-xs btn-ghost rounded-none"
                onClick={() => onResolveApproval?.('rejected')}
              >
                Reject
              </button>
            </div>
          ) : (
            <p className="mt-1 text-[11px] uppercase tracking-wide opacity-70">
              {message.approval?.status}
            </p>
          )}
        </div>
      </div>
    )
  }

  const speaker = isUser ? 'You' : message.agent || agent?.name || 'Assistant'

  if (message.kind === 'review' && message.oversightRole) {
    const meta = roleMeta(message.oversightRole) || { label: message.oversightRole }
    return (
      <div
        className={`flex gap-2 group ${isUser ? 'justify-end' : 'justify-start'}`}
        data-message-role={message.role}
        aria-label={`${speaker} message`}
      >
        {!isUser && agent && <AgentAvatar agent={agent} size={32} />}
        <div className="relative max-w-[80%]">
          <div className="rounded-sm border-l-4 border-primary bg-base-200 px-3.5 py-2 text-sm whitespace-pre-wrap">
            <div className="text-[11px] font-bold uppercase tracking-wider text-primary/80 mb-0.5">
              {meta.label}
            </div>
            {message.text}
          </div>
          <div className="absolute -top-3 right-1 flex items-center gap-0.5 rounded-full border border-base-300 bg-base-100 px-0.5 py-0.5 shadow-sm opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto transition-opacity">
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label={copyButtonLabel(copied, canCopy)}
              title={canCopy ? 'Copy to clipboard' : COPY_EMPTY_TITLE}
              disabled={!canCopy}
              onClick={handleCopy}
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (isSummary) {
    if (summaryRemoved) return null
    return (
      <div
        className="flex justify-start group"
        data-testid="conversation-summary-card"
        onContextMenu={summaryMenu.onContextMenu}
      >
        <div className="relative max-w-[85%] w-full rounded-none border border-base-content/25 bg-base-300/50 px-3.5 py-2.5 text-sm shadow-xs">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-1.5 min-w-0">
              <button
                type="button"
                className="text-[11px] font-bold uppercase tracking-wider text-base-content/55 text-left"
                aria-expanded={summaryExpanded}
                aria-label="Conversation summary"
                onClick={() => setSummaryExpanded((prev) => !prev)}
                onKeyDown={summaryMenu.onKeyDown}
              >
                Conversation summary
              </button>
              {summaryEdited ? (
                <span className="font-normal opacity-70" data-testid="edited-hint">
                  edited
                </span>
              ) : null}
            </div>
            {editing ? null : (
            <div className="flex items-center gap-0.5 opacity-100 md:opacity-0 group-hover:md:opacity-100 group-focus-within:md:opacity-100 transition-opacity">
              <button
                type="button"
                className="btn btn-ghost btn-xs gap-1"
                aria-label="Edit message"
                title="Edit"
                disabled={regenerating}
                onClick={startSummaryEdit}
              >
                <Pencil className="h-3 w-3" aria-hidden="true" />
                Edit
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-square"
                aria-label={
                  !canCopy ? COPY_EMPTY_TITLE : copied ? 'Copied' : 'Copy summary'
                }
                title={canCopy ? 'Copy summary' : COPY_EMPTY_TITLE}
                disabled={!canCopy}
                onClick={handleCopy}
              >
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-square"
                aria-label="Regenerate summary"
                title="Regenerate summary"
                disabled={regenerating || !onRegenerateSummary}
                onClick={() => onRegenerateSummary?.(steer)}
              >
                <RotateCcw className={`w-3.5 h-3.5 ${regenerating ? 'animate-spin' : ''}`} />
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-square"
                aria-label="View original messages"
                title="View original messages"
                onClick={() => setOriginalOpen(true)}
              >
                <ScrollText className="w-3.5 h-3.5" />
              </button>
            </div>
            )}
          </div>
          {summaryExpanded ? (
            editing ? (
              <>
                <Textarea
                  ref={textareaRef}
                  aria-label="Edit message"
                  size="sm"
                  className="w-full min-h-24 rounded-none"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleSummaryEditorKeyDown}
                />
                <div className="mt-2 flex justify-end gap-1">
                  <button type="button" className="btn btn-ghost btn-xs" onClick={cancelSummaryEdit}>
                    Cancel
                  </button>
                  <button type="button" className="btn btn-primary btn-xs" onClick={saveSummaryEdit}>
                    Save
                  </button>
                </div>
              </>
            ) : (
            <>
          <p className="whitespace-pre-wrap">{regenerating ? 'Regenerating summary…' : summaryBody}</p>
          <label className="mt-2 block">
            <span className="sr-only">Steer next regenerate</span>
            <input
              className="input input-xs input-bordered w-full rounded-none"
              value={steer}
              onChange={(e) => setSteer(e.target.value)}
              placeholder="Steer next regenerate (optional)"
            />
          </label>
            </>
            )
          ) : null}
        </div>
        {summaryMenu.menuNode}
        {originalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Original messages"
              className="w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-none border border-base-300 bg-base-100 p-4 shadow-xl"
            >
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-bold text-sm">Original messages</h2>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => setOriginalOpen(false)}
                  aria-label="Close dialog"
                >
                  Close
                </button>
              </div>
              <ol className="space-y-2 text-sm">
                {(message.compacted || []).map((line, i) => (
                  <li key={`${line.role}-${i}`} className="border border-base-300 rounded-none p-2">
                    <div className="text-[11px] font-semibold uppercase tracking-wide opacity-60 mb-0.5">
                      {line.agent || line.role}
                    </div>
                    <div className="whitespace-pre-wrap">{line.text}</div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      className={`flex gap-2 group ${isUser ? 'justify-end' : 'justify-start'}`}
      data-message-role={message.role}
      aria-label={`${speaker} message`}
    >
      {!isUser && agent && <AgentAvatar agent={agent} size={32} />}
      <div className="relative max-w-[80%]">
        <div
          className={`rounded-2xl px-3.5 py-2 text-sm ${
            isUser ? 'bg-primary text-primary-content whitespace-pre-wrap' : 'bg-base-200'
          }`}
        >
          {isUser ? (
            message.text
          ) : (
            <div
              className="chat-md os-chat-md break-words [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:underline"
              dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(message.text) }}
            />
          )}
          {message.delegationId && onOpenDelegation && (
            <button
              type="button"
              className="block mt-1 text-[11px] underline"
              onClick={() => onOpenDelegation(message.delegationId!)}
            >
              View delegation
            </button>
          )}
        </div>
        {message.reactions && message.reactions.length > 0 && (
          <div
            data-testid="message-reactions-row"
            className="os-message-reactions flex flex-wrap items-center gap-1 mt-1 opacity-100 pointer-events-auto md:opacity-0 md:pointer-events-none group-hover:md:opacity-100 group-hover:md:pointer-events-auto group-focus-within:md:opacity-100 group-focus-within:md:pointer-events-auto transition-opacity"
            aria-label="Message reactions"
          >
            {message.reactions.map((r, idx) => (
              <button
                key={`${r.emoji}-${idx}`}
                type="button"
                data-testid={`reaction-${r.emoji}`}
                className={`badge badge-sm cursor-pointer select-none gap-1 py-2 px-2 text-xs transition-colors ${
                  r.userReacted ? 'badge-primary' : 'badge-ghost border-base-300'
                }`}
                onClick={() =>
                  onAddReaction?.(
                    message.key || message.id || `${message.sender || message.role}-${message.timestamp || ''}`,
                    r.emoji,
                  )
                }
                aria-label={`Reaction ${r.emoji} count ${r.count}`}
              >
                <span>{r.emoji}</span>
                {r.count > 1 && <span className="text-[10px] font-semibold">{r.count}</span>}
              </button>
            ))}
          </div>
        )}
        <div
          data-testid="message-actions"
          className="os-message-actions absolute -top-3 right-1 flex items-center gap-0.5 rounded-full border border-base-300 bg-base-100 px-0.5 py-0.5 shadow-sm opacity-100 pointer-events-auto md:opacity-0 md:pointer-events-none group-hover:md:opacity-100 group-hover:md:pointer-events-auto group-focus-within:md:opacity-100 group-focus-within:md:pointer-events-auto transition-opacity"
        >
          {onAddReaction && (
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label="Add reaction"
              title="Add reaction"
              onClick={() =>
                onAddReaction(
                  message.key || message.id || `${message.sender || message.role}-${message.timestamp || ''}`,
                )
              }
            >
              <Smile className="w-3.5 h-3.5" />
            </button>
          )}
          {onReply && (
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label="Reply to message"
              title="Reply to message"
              data-testid="message-reply-action"
              onClick={onReply}
            >
              <Reply className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            aria-label={copyButtonLabel(copied, canCopy)}
            title={canCopy ? 'Copy to clipboard' : COPY_EMPTY_TITLE}
            disabled={!canCopy}
            onClick={handleCopy}
          >
            {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          {canCompact && onCompactToHere && (
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label="Compact to here"
              title="Compact older messages into a summary (keep last 3)"
              disabled={compacting}
              onClick={onCompactToHere}
            >
              <FoldVertical className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
