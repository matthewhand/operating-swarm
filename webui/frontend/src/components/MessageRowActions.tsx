import { useEffect, useState, type ReactNode } from 'react'
import { Brain, Check, Copy, FoldVertical, Pencil, Reply, Terminal } from 'lucide-react'
import { ActionRowLabelsContext } from '../lib/actionRowLabelsContext'
import { useToast } from './DaisyUI'
import {
  COPY_EMPTY_MESSAGE,
  COPY_EMPTY_TITLE,
  COPY_FAILED_MESSAGE,
  COPY_FAILED_TITLE,
  copyButtonLabel,
  copyTextToClipboard,
  messageHasCopyableText,
} from '../lib/clipboard'
import {
  ACTION_ROW_LABELS_CHANGED_EVENT,
  loadActionRowLabels,
} from '../lib/actionRowLabels'

/**
 * Message action/reaction row (#70 / REQ-103 / REQ-869 / #578 / #850).
 *
 * ChatPage mounts this beside ChatMessageBubble inside `group/osrow`.
 * Combines Edit, Reply, Copy, Read Aloud, Retry, Raw Response, and context actions on one line.
 *
 * #505 / REQ-907: when the bubble theme declares `actionRowPlacement: 'overlay'`
 * (IRC) the caller passes `overlay` and the row renders out of flow — absolutely
 * positioned over the bubble's last line with a gradient scrim so the text
 * beneath fades rather than being sliced. Overlay is opt-in per mount and only
 * applied at `md:` and up (hover-capable); below that the row stays in flow so
 * touch devices never have text permanently covered.
 *
 * #506 / REQ-908: `labels=false` renders icon-only buttons. Every button keeps
 * its `aria-label`, so the accessible name survives; `title` tooltips are
 * always present so icon-only mode stays discoverable.
 */
export interface MessageRowActionsProps {
  text: string
  children?: ReactNode
  className?: string
  canEdit?: boolean
  onStartEdit?: () => void
  canCompress?: boolean
  onCompressToHere?: () => void
  contextStrategy?: 'compress' | 'cull'
  onReply?: () => void
  /** #505: render out of flow over the bubble (IRC) instead of a flow line below it. */
  overlay?: boolean
  /** Whether the message has thinking / reasoning content (#REQ-thinking-reaction). */
  hasThinking?: boolean
  /** Toggle thinking block callback (#REQ-thinking-reaction). */
  onToggleThinking?: () => void
  /** Whether thinking is currently revealed. */
  thinkingOpen?: boolean
  /** #850: Whether this message is from a Herdr agent. */
  isHerdr?: boolean
  /** #850: Raw unstripped terminal output. */
  rawResponse?: string | null
  /** #850: Callback to view the unfiltered terminal response. */
  onShowRawResponse?: () => void
}

export default function MessageRowActions({
  text,
  children,
  className,
  canEdit,
  onStartEdit,
  canCompress,
  onCompressToHere,
  contextStrategy = 'compress',
  onReply,
  overlay = false,
  hasThinking = false,
  onToggleThinking,
  thinkingOpen = false,
  isHerdr = false,
  onShowRawResponse,
}: MessageRowActionsProps) {
  const [copied, setCopied] = useState(false)
  const [labels, setLabels] = useState(() => loadActionRowLabels())
  const { error } = useToast()
  const canCopy = messageHasCopyableText(text)
  const startFromHere = contextStrategy === 'cull'
  const contextActionLabel = startFromHere ? 'Start context from here' : 'Compress to here'

  useEffect(() => {
    const sync = () => setLabels(loadActionRowLabels())
    window.addEventListener(ACTION_ROW_LABELS_CHANGED_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(ACTION_ROW_LABELS_CHANGED_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  const handleCopy = async () => {
    const result = await copyTextToClipboard(text)
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

  const btnClass = 'btn btn-ghost btn-xs gap-1'

  const editButton = canEdit && onStartEdit ? (
    <button
      type="button"
      className={btnClass}
      aria-label="Edit message"
      title="Edit message"
      onClick={onStartEdit}
    >
      <Pencil className="h-3 w-3" aria-hidden="true" />
      {labels ? 'Edit' : null}
    </button>
  ) : null

  const replyButton = onReply ? (
    <button
      type="button"
      className={btnClass}
      aria-label="Reply to message"
      title="Reply"
      data-testid="message-reply-action"
      onClick={onReply}
    >
      <Reply className="h-3 w-3" aria-hidden="true" />
      {labels ? 'Reply' : null}
    </button>
  ) : null

  const rawResponseButton = isHerdr && onShowRawResponse ? (
    <button
      type="button"
      className={btnClass}
      aria-label="Raw Response"
      title="View raw terminal response"
      data-testid="message-raw-response-action"
      onClick={onShowRawResponse}
    >
      <Terminal className="h-3 w-3 text-base-content/70" aria-hidden="true" />
      {labels ? 'Raw Response' : null}
    </button>
  ) : null

  const thinkingButton = !isHerdr && hasThinking && onToggleThinking ? (
    <button
      type="button"
      className={btnClass}
      aria-label="Thinking"
      title={thinkingOpen ? 'Hide thinking' : 'Show thinking'}
      data-testid="message-thinking-action"
      onClick={onToggleThinking}
    >
      <Brain
        className={`h-3 w-3 ${thinkingOpen ? 'text-primary' : 'text-primary/70'}`}
        aria-hidden="true"
      />
      {labels ? 'Thinking' : null}
    </button>
  ) : null

  const copyButton = (
    <button
      type="button"
      className={btnClass}
      aria-label={copyButtonLabel(copied, canCopy)}
      title={canCopy ? 'Copy to clipboard' : COPY_EMPTY_TITLE}
      disabled={!canCopy}
      onClick={() => {
        void handleCopy()
      }}
    >
      {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
      {labels ? (copied ? 'Copied' : 'Copy') : null}
    </button>
  )

  const compressButton = canCompress && onCompressToHere ? (
    <button
      type="button"
      className={btnClass}
      aria-label={contextActionLabel}
      title={startFromHere ? 'Start context from here.' : 'Compress to here'}
      data-testid={startFromHere ? 'start-context-from-here' : 'compress-to-here'}
      onClick={onCompressToHere}
    >
      <FoldVertical className="h-3 w-3" aria-hidden="true" />
      {labels ? contextActionLabel : null}
    </button>
  ) : null

  const row = (
    <div
      data-testid="os-message-row-actions"
      className={`flex flex-row items-center gap-1 opacity-100 pointer-events-auto md:opacity-0 md:pointer-events-none group-hover/osrow:md:opacity-100 group-hover/osrow:md:pointer-events-auto group-focus-within/osrow:md:opacity-100 group-focus-within/osrow:md:pointer-events-auto transition-opacity${overlay ? ' os-row-actions-overlay' : ''}${
        className ? ` ${className}` : ''
      }`}
    >
      {editButton}
      {replyButton}
      {rawResponseButton}
      {thinkingButton}
      {copyButton}
      {compressButton}
      {children}
    </div>
  )

  if (!overlay) {
    return <ActionRowLabelsContext.Provider value={labels}>{row}</ActionRowLabelsContext.Provider>
  }

  // #505 overlay wrapper: out of flow, pinned over the bubble's trailing edge.
  // The scrim fades the text behind the controls (linear-gradient to the
  // surface) instead of slicing it mid-glyph. Applied only at md+ via CSS.
  return (
    <div className="os-row-actions-overlay-wrap pointer-events-none absolute bottom-0 right-0 z-10 w-full">
      <ActionRowLabelsContext.Provider value={labels}>{row}</ActionRowLabelsContext.Provider>
    </div>
  )
}
