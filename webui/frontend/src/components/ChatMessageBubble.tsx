import {
  memo,
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
import { parseProviderSetupFence } from '../lib/providerSetupCard'
import { SystemPreloadPill } from './SystemPreloadPill'
import { SkillChip } from './SkillChip'
import SupportCreatedBlueprintCard from './SupportCreatedBlueprintCard'
import ProviderSetupCard from './ProviderSetupCard'
import { splitSkillRefs, type SkillInfo } from '../lib/skills'
import { isFlagrantErrorText } from '../lib/flagrantErrors'
import {
  getBubbleTheme,
  loadBubbleTheme,
  renderStreamingAffordance,
  streamingAffordanceClass,
  type BubbleTheme,
} from '../lib/bubbleTheme'
import { Brain, ChevronRight } from 'lucide-react'
import { STREAM_REPLIES_CHANGED_EVENT, streamingPartialEnabled } from '../lib/streamReplies'
import { splitLeadingQuote } from '../lib/replyQuote'
import { extractThinkingBlock } from '../lib/messageArtifacts'
import { QuotedReply } from './QuotedReply'
import { SpecialStatusCard } from './SpecialCards'

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
  /** Whether the collapsible thinking block is open (REQ-thinking-reaction). */
  thinkingOpen?: boolean
  /** Toggle thinking block callback (REQ-thinking-reaction). */
  onToggleThinking?: (open?: boolean) => void
  /** #850: Whether this message is from a Herdr agent. */
  isHerdr?: boolean
  /** #1168: server never confirmed this optimistic send — offer resend. */
  sendFailed?: boolean
  /** #1168: resend a lost send (same text, same row). */
  onResend?: () => void
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
    thinkingOpen,
    onToggleThinking,
    isHerdr,
  }: {
    text: string
    streaming: boolean
    skillCatalog?: SkillInfo[]
    onOpenSkill?: (name: string) => void
    theme?: BubbleTheme
    seatId?: string
    thinkingOpen?: boolean
    onToggleThinking?: (open?: boolean) => void
    isHerdr?: boolean
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
    const { body: cleanedText, thinking } = extractThinkingBlock(contentText)
    const { prose, card } = parseSupportNlBlueprintFence(cleanedText)
    // #894: the bootstrap seat may attach an in-chat provider setup card.
    const { prose: proseAfterSetup, card: setupCard } = parseProviderSetupFence(prose)
    const segments = splitSkillRefs(proseAfterSetup)

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

    if (displayText.length === 0 || (prose.length === 0 && !thinking)) {
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

    const thinkingEl = !isHerdr && thinking ? (
      <details
        className="group/thinking my-1.5 rounded border border-base-content/15 bg-base-300/30 text-xs transition-colors open:bg-base-300/50"
        open={thinkingOpen}
        onToggle={(e) => onToggleThinking?.((e.target as HTMLDetailsElement).open)}
        data-testid="chat-thinking-block"
      >
        <summary className="flex cursor-pointer select-none items-center gap-1.5 px-2.5 py-1.5 font-medium opacity-80 hover:opacity-100 focus:outline-none">
          <Brain className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          <span>Thinking</span>
          <ChevronRight className="h-3.5 w-3.5 opacity-60 transition-transform group-open/thinking:rotate-90 ml-auto" />
        </summary>
        <div
          className="border-t border-base-content/10 px-3 py-2 text-xs leading-relaxed opacity-85 font-mono whitespace-pre-wrap select-text"
          data-testid="chat-thinking-content"
        >
          {thinking}
        </div>
      </details>
    ) : null

    const body = (
      <>
        {quoted ? <QuotedReply quote={quoted.quote} /> : null}
        {thinkingEl}
        {prose.length > 0 ? markdown : null}
        {affordanceClass ? (
          <span
            className={affordanceClass}
            data-testid="stream-affordance"
            aria-hidden="true"
          />
        ) : null}
      </>
    )

    if (!card && !setupCard) {
      return body
    }

    return (
      <div data-testid="chat-md-with-nl-card">
        {body}
        {card ? <SupportCreatedBlueprintCard card={card} /> : null}
        {setupCard ? <ProviderSetupCard spec={setupCard} /> : null}
      </div>
    )
  },
  (prev, next) =>
    prev.text === next.text &&
    prev.streaming === next.streaming &&
    prev.skillCatalog === next.skillCatalog &&
    prev.onOpenSkill === next.onOpenSkill &&
    prev.theme === next.theme &&
    prev.seatId === next.seatId &&
    prev.thinkingOpen === next.thinkingOpen &&
    prev.onToggleThinking === next.onToggleThinking &&
    prev.isHerdr === next.isHerdr,
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
  thinkingOpen,
  onToggleThinking,
  isHerdr,
  sendFailed,
  onResend,
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

  // #721 (supersedes the per-row #675/#774 presentation): the divider is ONE
  // transcript-level rail — rows only own the fixed-width gutter, so the
  // line cannot re-flow when messages append.
  if (role === 'system' || isSystemPreload) {
    return (
      <div className="flex justify-start w-full my-1" data-testid="chat-system-preload">
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
              thinkingOpen={thinkingOpen}
              onToggleThinking={onToggleThinking}
              isHerdr={isHerdr}
            />
          )}
          {children}
          {sendFailed && role === 'user' ? (
            <div
              className="os-send-failed mt-1 flex items-center gap-2 text-[11px] text-error"
              data-testid="send-failed"
            >
              <span>Not sent — the connection dropped.</span>
              <button
                type="button"
                className="btn btn-ghost btn-xs text-error"
                onClick={onResend}
                data-testid="resend-button"
              >
                Resend
              </button>
            </div>
          ) : null}
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
