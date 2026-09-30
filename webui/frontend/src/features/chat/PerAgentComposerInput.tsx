/**
 * #1331 (per-agent drafts) + #1400 (keep the composer mounted).
 *
 * The draft lives in `usePerAgentDraft` (localStorage-backed, one slot per
 * agent) and is handed to this input as a controlled `value`, so switching
 * agent swaps the **contents** while the textarea instance itself is
 * preserved. The earlier implementation keyed the element on the agent id,
 * which remounted the composer on every pick: that dropped focus and IME
 * state mid-typing and broke REQ-54's "keeps chat mounted" invariant
 * (`src/App.rail.test.tsx`). Because `value` is controlled, React rewrites
 * the element's contents in the same commit as the switch — there is no
 * async repopulation to race the seat hydration that follows a pick, and no
 * switch ever writes into another agent's draft.
 *
 * Every standard textarea handler is forwarded verbatim
 * (onKeyDown/KeyUp/KeyPress/onChange/onInput/onFocus/onBlur/onPaste/
 * onCompositionStart/onCompositionEnd), so Enter-to-send, Esc-to-clear, the
 * slash menu, reply quotes, and attachment chips keep working unchanged.
 */
import type { ComponentType, RefObject, TextareaHTMLAttributes } from 'react'
import { normalizeDraftAgentId } from './usePerAgentDraft'

export interface PerAgentComposerInputProps {
  /** Active agent id — its slot supplies `value`; the element never remounts. */
  agentId?: string
  /** Active agent's draft, supplied by the wired `usePerAgentDraft` state. */
  value: string
  /** Push a draft to the active agent's state owner (setInput). */
  onValueChange: (next: string) => void
  isApiAgent: boolean
  /** Enhanced API composer (ghost text); omit for the plain textarea. */
  ChatMessageInput?: ComponentType<any>
  composerRef: RefObject<HTMLTextAreaElement | null>
  composerPlaceholder: string
  /** All standard textarea props/handlers, forwarded verbatim. */
  textareaProps: TextareaHTMLAttributes<HTMLTextAreaElement>
  selectedBlueprint?: string
  conversationId?: string
}

export function PerAgentComposerInput({
  agentId,
  value,
  onValueChange,
  isApiAgent,
  ChatMessageInput,
  composerRef,
  composerPlaceholder,
  textareaProps,
  selectedBlueprint,
  conversationId,
}: PerAgentComposerInputProps) {
  // Stable fallback for the autocomplete scorer when no blueprint is selected.
  const activeAgentKey = normalizeDraftAgentId(agentId)

  if (isApiAgent && ChatMessageInput) {
    return (
      <ChatMessageInput
        textareaRef={composerRef}
        value={value}
        onApplyText={onValueChange}
        agentId={selectedBlueprint || activeAgentKey}
        conversationId={conversationId || undefined}
        textareaProps={{
          ...textareaProps,
          rows: 1,
          className: 'os-composer__input',
          placeholder: composerPlaceholder,
          value,
        }}
      />
    )
  }

  return (
    <textarea
      {...textareaProps}
      ref={composerRef as RefObject<HTMLTextAreaElement>}
      rows={1}
      className="os-composer__input"
      placeholder={composerPlaceholder}
      value={value}
    />
  )
}

export default PerAgentComposerInput
