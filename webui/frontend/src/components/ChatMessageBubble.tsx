import {
  memo,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react'
import { FoldVertical, Pencil } from 'lucide-react'
import { Textarea, LoadingDots } from './DaisyUI'
import { renderSafeMarkdown } from '../lib/markdown'
import { setupCodeFenceControls } from '../lib/codeFences'
import { parseSupportNlBlueprintFence } from '../lib/supportNlBlueprint'
import { SystemPreloadPill } from './SystemPreloadPill'
import { SkillChip } from './SkillChip'
import SupportCreatedBlueprintCard from './SupportCreatedBlueprintCard'
import { splitSkillRefs, type SkillInfo } from '../lib/skills'
import { formatBubbleTime } from '../lib/bubbleTheme'

export interface ChatMessageBubbleProps {
  role: 'user' | 'assistant' | 'system' | 'status'
  agentName: string
  text: string
  streaming: boolean
  edited?: boolean
  canEdit: boolean
  editing: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: (text: string) => void
  onCompressToHere?: () => void
  canCompress?: boolean
  contextStrategy?: 'compress' | 'cull'
  children?: ReactNode
  isSystemPreload?: boolean
  skillCatalog?: SkillInfo[]
  onOpenSkill?: (name: string) => void
  /** REQ-213: view-only hide for compacted system pills. */
  onRemoveCard?: () => void
  /** ISO timestamp for feed-theme meta; omitted when unknown. */
  ts?: string
  avatar?: ReactNode
}

function selectionIsActive(): boolean {
  try {
    const sel = window.getSelection()
    return Boolean(sel && !sel.isCollapsed)
  } catch {
    return false
  }
}

/**
 * One chat bubble. On API-agent threads, hover reveals Edit and clicking
 * the bubble (or the control) enters in-place edit. CLI/remote pass
 * ``canEdit={false}`` so neither control nor click-to-edit is offered.
 */
export const ChatBubbleBody = memo(
  function ChatBubbleBody({
    text,
    streaming,
    skillCatalog,
    onOpenSkill,
  }: {
    text: string
    streaming: boolean
    skillCatalog?: SkillInfo[]
    onOpenSkill?: (name: string) => void
  }) {
    const mdRef = useRef<HTMLDivElement | null>(null)
    const expandedIndicesRef = useRef<Set<number>>(new Set())
    const { prose, card } = parseSupportNlBlueprintFence(text)
    const segments = splitSkillRefs(prose)

    useEffect(() => {
      const root = mdRef.current
      if (!root) return
      // Set up code-copy and collapsible code fence controls (REQ-127, REQ-117)
      setupCodeFenceControls(root, expandedIndicesRef.current)
    }, [text])

    if (text.length === 0) {
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
          className={mdClass}
          dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(prose) }}
        />
      ) : (
        <div ref={mdRef} data-testid="chat-md" className={mdClass}>
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

    if (!card) {
      return markdown
    }

    return (
      <div data-testid="chat-md-with-nl-card">
        {markdown}
        <SupportCreatedBlueprintCard card={card} />
      </div>
    )
  },
  (prev, next) =>
    prev.text === next.text &&
    prev.streaming === next.streaming &&
    prev.skillCatalog === next.skillCatalog &&
    prev.onOpenSkill === next.onOpenSkill,
)

export function ChatMessageBubble({
  role,
  agentName,
  text,
  streaming,
  edited,
  canEdit,
  editing,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onCompressToHere,
  canCompress,
  contextStrategy = 'compress',
  children,
  isSystemPreload,
  skillCatalog,
  onOpenSkill,
  onRemoveCard,
  ts,
  avatar,
}: ChatMessageBubbleProps) {
  const startFromHere = contextStrategy === 'cull'
  const contextActionLabel = startFromHere ? 'Start context from here' : 'Compress to here'
  const [draft, setDraft] = useState(text)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    if (editing) {
      setDraft(text)
      const id = window.setTimeout(() => textareaRef.current?.focus(), 0)
      return () => window.clearTimeout(id)
    }
    return undefined
  }, [editing, text])

  if (role === 'system' || isSystemPreload) {
    return (
      <div className="flex justify-start w-full my-1" data-testid="chat-system-preload">
        <SystemPreloadPill text={text} onRemove={onRemoveCard} />
      </div>
    )
  }

  const handleBubbleClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!canEdit || streaming || editing) return
    const target = event.target as HTMLElement | null
    if (target?.closest('a, button, textarea, input')) return
    if (selectionIsActive()) return
    onStartEdit()
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
  const timeLabel = formatBubbleTime(ts)

  return (
    <div
      className={`chat group ${role === 'user' ? 'chat-end' : 'chat-start'}`}
      data-message-role={role}
      data-speaker={speaker}
      data-ts={ts || undefined}
      aria-label={`${speaker} message`}
    >
      {avatar ? (
        <div className="chat-image avatar shrink-0" data-testid="chat-avatar">
          {avatar}
        </div>
      ) : null}
      <div className="chat-header os-bubble-meta text-xs opacity-60" data-speaker={speaker}>
        {timeLabel ? (
          <time className="os-bubble-time" dateTime={ts} data-testid="bubble-time">
            {timeLabel}
          </time>
        ) : null}
        {edited ? (
          <span className="font-normal opacity-70" data-testid="edited-hint">
            edited
          </span>
        ) : null}
      </div>
      {editing ? (
        <div className="chat-bubble bg-base-200 text-base-content w-full max-w-xl">
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
          className={`chat-bubble select-text ${
            role === 'user' ? 'bg-neutral text-neutral-content' : 'bg-base-200 text-base-content'
          }`}
          data-testid="chat-bubble"
          onClick={handleBubbleClick}
        >
          <ChatBubbleBody
            text={text}
            streaming={streaming}
            skillCatalog={skillCatalog}
            onOpenSkill={onOpenSkill}
          />
          {children}
        </div>
      )}
      {(!streaming && !editing && (canEdit || (canCompress && onCompressToHere))) ? (
        <div className="mt-0.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
          {canEdit ? (
            <button
              type="button"
              className="btn btn-ghost btn-xs gap-1"
              aria-label="Edit message"
              onClick={onStartEdit}
            >
              <Pencil className="h-3 w-3" aria-hidden="true" />
              Edit
            </button>
          ) : null}
          {canCompress && onCompressToHere ? (
            <button
              type="button"
              className="btn btn-ghost btn-xs gap-1"
              aria-label={contextActionLabel}
              title={startFromHere ? 'Start context from here.' : 'Compress to here'}
              data-testid={startFromHere ? 'start-context-from-here' : 'compress-to-here'}
              onClick={onCompressToHere}
            >
              <FoldVertical className="h-3 w-3" aria-hidden="true" />
              {contextActionLabel}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
