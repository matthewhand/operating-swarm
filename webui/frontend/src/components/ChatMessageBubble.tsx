import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { Textarea, LoadingDots } from './DaisyUI'
import { renderSafeMarkdown } from '../lib/markdown'
import { renderMarkdownSafe } from '../lib/markdownSafe'
import { setupCodeFenceControls } from '../lib/codeFences'
import { handleSettingsLinkClick } from '../lib/settingsLinks'
import { parseSupportNlBlueprintFence } from '../lib/supportNlBlueprint'
import { SystemPreloadPill } from './SystemPreloadPill'
import { SkillChip } from './SkillChip'
import SupportCreatedBlueprintCard from './SupportCreatedBlueprintCard'
import { splitSkillRefs, type SkillInfo } from '../lib/skills'
import { isFlagrantErrorText } from '../lib/flagrantErrors'
import {
  getBubbleTheme,
  loadBubbleTheme,
  renderStreamingAffordance,
  streamingAffordanceClass,
  type BubbleTheme,
} from '../lib/bubbleTheme'
import { STREAM_REPLIES_CHANGED_EVENT, streamingPartialEnabled } from '../lib/streamReplies'
import { splitLeadingQuote } from '../lib/replyQuote'
import { QuotedReply } from './QuotedReply'
import { SpecialStatusCard } from './SpecialCards'
import {
  IRC_GUTTER_DEFAULT_PX,
  loadIrcGutterPx,
  saveIrcGutterPx,
  themeUsesIrcGutter,
} from '../lib/ircGutter'

export interface ChatMessageBubbleProps {
  role: 'user' | 'assistant' | 'system' | 'status'
  agentName: string
  text: string
  streaming: boolean
  edited?: boolean
  editing: boolean
  onCancelEdit: () => void
  onSaveEdit: (text: string) => void
  children?: ReactNode
  isSystemPreload?: boolean
  skillCatalog?: SkillInfo[]
  onOpenSkill?: (name: string) => void
  /** REQ-213: view-only hide for compacted system pills. */
  onRemoveCard?: () => void
  /** ISO timestamp for theme-owned chrome; omitted when unknown. */
  ts?: string
  /** Active bubble theme; defaults to speech so isolated renders stay pixel-parity. */
  theme?: BubbleTheme
  avatar?: ReactNode
  /** Seat id for the per-seat stream-replies override (#220). */
  seatId?: string
}

/**
 * One chat bubble. Inline edit is entered from MessageRowActions (REQ-869);
 * the bubble itself never starts edit on click (REQ-867).
 */
export const ChatBubbleBody = memo(
  function ChatBubbleBody({
    text,
    streaming,
    skillCatalog,
    onOpenSkill,
    theme,
    seatId,
  }: {
    text: string
    streaming: boolean
    skillCatalog?: SkillInfo[]
    onOpenSkill?: (name: string) => void
    theme?: BubbleTheme
    seatId?: string
  }) {
    const mdRef = useRef<HTMLDivElement | null>(null)
    const expandedIndicesRef = useRef<Set<number>>(new Set())
    const [, setStreamEpoch] = useState(0)
    useEffect(() => {
      const onChange = () => setStreamEpoch((n) => n + 1)
      window.addEventListener(STREAM_REPLIES_CHANGED_EVENT, onChange)
      return () => window.removeEventListener(STREAM_REPLIES_CHANGED_EVENT, onChange)
    }, [])
    const activeTheme = theme ?? loadBubbleTheme()
    const allowPartial = streamingPartialEnabled({ theme: activeTheme, seatId })
    const displayText =
      streaming && !allowPartial ? '' : streaming ? renderMarkdownSafe(text) : text
    const affordanceClass =
      streaming && allowPartial && renderStreamingAffordance(activeTheme) !== 'none'
        ? streamingAffordanceClass(activeTheme)
        : ''
    // #565: a reply is only markdown — the quote is the blockquote the send
    // path prepends. Split it off so it can be clamped/expanded on screen while
    // the bytes that went on the wire stay whole.
    const quoted = splitLeadingQuote(displayText)
    const contentText = quoted ? quoted.body : displayText
    const { prose, card } = parseSupportNlBlueprintFence(contentText)
    const segments = splitSkillRefs(prose)

    useEffect(() => {
      const root = mdRef.current
      if (!root) return
      // Set up code-copy and collapsible code fence controls (REQ-127, REQ-117)
      setupCodeFenceControls(root, expandedIndicesRef.current)
      const onClick = (event: globalThis.MouseEvent) => {
        handleSettingsLinkClick(event)
      }
      root.addEventListener('click', onClick)
      return () => root.removeEventListener('click', onClick)
    }, [displayText])

    if (displayText.length === 0) {
      return streaming ? (
        <LoadingDots size="sm" />
      ) : (
        <span className="opacity-60">(empty response)</span>
      )
    }

    const mdClass =
      'chat-md break-words [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-base-300/40 [&_pre]:p-2 [&_code]:text-sm [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:underline'

    const markdown =
      segments.every((segment) => segment.type === 'text') ? (
        <div
          ref={mdRef}
          data-testid="chat-md"
          data-streaming-partial={streaming && allowPartial ? 'true' : undefined}
          className={mdClass}
          dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(prose) }}
        />
      ) : (
        <div
          ref={mdRef}
          data-testid="chat-md"
          data-streaming-partial={streaming && allowPartial ? 'true' : undefined}
          className={mdClass}
        >
          {segments.map((segment, index) => {
            if (segment.type === 'text') {
              return (
                <span
                  key={`t-${index}`}
                  dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(segment.text) }}
                />
              )
            }
            const info = skillCatalog?.find((row) => row.name === segment.ref.name)
            const missing = Boolean(skillCatalog && !info)
            return (
              <SkillChip
                key={`s-${index}-${segment.ref.name}`}
                name={segment.ref.name}
                raw={segment.ref.raw}
                skill={info}
                missing={missing}
                onClick={() => onOpenSkill?.(segment.ref.name)}
              />
            )
          })}
        </div>
      )

    const body = (
      <>
        {quoted ? <QuotedReply quote={quoted.quote} /> : null}
        {markdown}
        {affordanceClass ? (
          <span
            className={affordanceClass}
            data-testid="stream-affordance"
            aria-hidden="true"
          />
        ) : null}
      </>
    )

    if (!card) {
      return body
    }

    return (
      <div data-testid="chat-md-with-nl-card">
        {body}
        <SupportCreatedBlueprintCard card={card} />
      </div>
    )
  },
  (prev, next) =>
    prev.text === next.text &&
    prev.streaming === next.streaming &&
    prev.skillCatalog === next.skillCatalog &&
    prev.onOpenSkill === next.onOpenSkill &&
    prev.theme === next.theme &&
    prev.seatId === next.seatId,
)

export function ChatMessageBubble({
  role,
  agentName,
  text,
  streaming,
  edited,
  editing,
  onCancelEdit,
  onSaveEdit,
  children,
  isSystemPreload,
  skillCatalog,
  onOpenSkill,
  onRemoveCard,
  ts,
  avatar,
  theme,
  seatId,
}: ChatMessageBubbleProps) {
  const [draft, setDraft] = useState(text)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  /** #521: last measured height of the rendered bubble, in px. */
  const bubbleRef = useRef<HTMLDivElement | null>(null)
  const bubbleHeightRef = useRef(0)

  useEffect(() => {
    if (editing) {
      setDraft(text)
      const id = window.setTimeout(() => textareaRef.current?.focus(), 0)
      return () => window.clearTimeout(id)
    }
    return undefined
  }, [editing, text])

  // #521: record the bubble's height while it is on screen, so entering edit
  // mode starts from the size of the message being edited rather than from a
  // fixed `min-h-24`, which is what made long messages shrink.
  useLayoutEffect(() => {
    if (editing) return
    const height = bubbleRef.current?.getBoundingClientRect().height ?? 0
    if (height > 0) bubbleHeightRef.current = height
  })

  // #675 — IRC rows carry a draggable divider as their first child, directly
  // after the ::before gutter, so every row shares one straight vertical edge.
  // The drag persists through the shared store (save fires the change event;
  // the transcript root re-syncs its --irc-gutter-px). Pointer capture keeps
  // the drag glued to the divider when the pointer outruns it; jsdom lacks
  // capture, so the optional calls are load-bearing for tests and harmless
  // in browsers. Hooks stay above the system-role early return below.
  const ircDragRef = useRef<{ startX: number; startWidth: number } | null>(null)
  const [ircDragging, setIrcDragging] = useState(false)
  const onIrcDividerPointerDown = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      event.preventDefault()
      event.currentTarget.setPointerCapture?.(event.pointerId)
      ircDragRef.current = { startX: event.clientX, startWidth: loadIrcGutterPx() }
      setIrcDragging(true)
    },
    [],
  )
  const onIrcDividerPointerMove = useCallback((event: React.PointerEvent<HTMLSpanElement>) => {
    const drag = ircDragRef.current
    if (!drag) return
    saveIrcGutterPx(drag.startWidth + (event.clientX - drag.startX))
  }, [])
  const onIrcDividerPointerUp = useCallback((event: React.PointerEvent<HTMLSpanElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    ircDragRef.current = null
    setIrcDragging(false)
  }, [])
  const onIrcDividerDoubleClick = useCallback(() => {
    saveIrcGutterPx(IRC_GUTTER_DEFAULT_PX)
  }, [])

  if (role === 'system' || isSystemPreload) {
    // #774: system-preload rows render the IRC gutter divider too, so the
    // vertical line does not visibly break at those rows. The pill itself
    // is unchanged; the divider is only mounted in the IRC theme.
    return (
      <div className="flex justify-start w-full my-1" data-testid="chat-system-preload">
        {themeUsesIrcGutter(getBubbleTheme(theme).id) ? (
          <span
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize IRC name column"
            className="os-irc-gutter-divider"
            data-testid="irc-gutter-divider"
          />
        ) : null}
        <SystemPreloadPill text={text} onRemove={onRemoveCard} />
      </div>
    )
  }

  const handleEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      onCancelEdit()
      return
    }
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      onSaveEdit(draft)
    }
  }

  const speaker = role === 'user' ? 'You' : agentName
  const themeDef = getBubbleTheme(theme)
  const timeLabel = themeDef.formatTimestamp(ts)
  const timeEl = timeLabel ? (
    <time className="os-bubble-time" dateTime={ts} data-testid="bubble-time">
      {timeLabel}
    </time>
  ) : null
  const placement = themeDef.timestampPlacement
  const ircDivider = themeUsesIrcGutter(themeDef.id)

  return (
    <div
      className={`chat group ${role === 'user' ? 'chat-end' : 'chat-start'}`}
      data-message-role={role}
      data-speaker={speaker}
      data-ts={ts || undefined}
      data-message-theme={themeDef.id}
      data-message-layout={themeDef.messageLayout}
      data-timestamp-placement={placement}
      data-action-row-placement={themeDef.actionRowPlacement}
      aria-label={`${speaker} message`}
    >
      {ircDivider ? (
        <span
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize IRC name column"
          className="os-irc-gutter-divider"
          data-testid="irc-gutter-divider"
          data-dragging={ircDragging ? 'true' : 'false'}
          onPointerDown={onIrcDividerPointerDown}
          onPointerMove={onIrcDividerPointerMove}
          onPointerUp={onIrcDividerPointerUp}
          onPointerCancel={onIrcDividerPointerUp}
          onDoubleClick={onIrcDividerDoubleClick}
        />
      ) : null}
      {avatar && themeDef.showAvatar ? (
        <div
          className="chat-image avatar shrink-0"
          data-testid="chat-avatar"
          data-avatar-anchor="bottom"
        >
          {avatar}
        </div>
      ) : null}
      {placement === 'inline' && timeEl ? (
        <span className="os-bubble-time-inline" data-testid="bubble-time-slot">
          {timeEl}
        </span>
      ) : null}
      <div
        className="chat-header os-bubble-meta text-xs opacity-60"
        data-speaker={speaker}
        data-testid={placement === 'above' ? 'bubble-time-slot' : undefined}
      >
        {placement === 'above' ? timeEl : null}
        {edited ? (
          <span className="font-normal opacity-70" data-testid="edited-hint">
            edited
          </span>
        ) : null}
      </div>
      {editing ? (
        // #521: the editor is the same bubble — same `chat-bubble` box, same
        // role colours, same width contract — so it cannot be narrower than
        // what it replaces. Height floors at the measured message height and
        // scrolls beyond it.
        <div
          className={`chat-bubble w-full max-w-xl select-text ${
            role === 'user' ? 'bg-neutral text-neutral-content' : 'bg-base-200 text-base-content'
          }`}
          data-testid="chat-bubble"
          data-editing="true"
        >
          <Textarea
            ref={textareaRef}
            aria-label="Edit message"
            size="sm"
            className="os-bubble-editor w-full"
            style={
              bubbleHeightRef.current > 0
                ? { minHeight: `${Math.round(bubbleHeightRef.current)}px` }
                : undefined
            }
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleEditorKeyDown}
          />
          <div className="mt-2 flex justify-end gap-1">
            <button type="button" className="btn btn-ghost btn-xs" onClick={onCancelEdit}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary btn-xs"
              onClick={() => onSaveEdit(draft)}
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <div
          ref={bubbleRef}
          className={`chat-bubble select-text ${
            role === 'user' ? 'bg-neutral text-neutral-content' : 'bg-base-200 text-base-content'
          }`}
          data-testid="chat-bubble"          >          {role === 'status' && isFlagrantErrorText(text) ? (
            // #746: flagrant transport/runtime failures render out-of-band —
            // a dedicated error element, not a chat-card lookalike, so the
            // conversation history is never contaminated by a dead turn.
            <div
              className="os-flagrant-error"
              role="alert"
              data-testid="flagrant-error"
            >
              <span className="os-flagrant-error__label">Error</span>
              <span className="os-flagrant-error__text">{text}</span>
            </div>
          ) : role === 'status' ? (
            // #533: status notices (context culls, session restores, hop
            // chatter) collapse to a one-line card instead of raw text — one
            // implementation, carried by every bubble theme.
            <SpecialStatusCard summary={text} />
          ) : (
            <ChatBubbleBody
              text={text}
              streaming={streaming}
              skillCatalog={skillCatalog}
              onOpenSkill={onOpenSkill}
              theme={theme}
              seatId={seatId}
            />
          )}
          {children}
        </div>
      )}
      {placement === 'below' && timeEl ? (
        <div className="chat-footer os-bubble-time-below" data-testid="bubble-time-slot">
          {timeEl}
        </div>
      ) : null}
    </div>
  )
}
