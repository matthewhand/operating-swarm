/**
 * #858/#860 — Chat composer enhancements for API seats.
 *
 * Wraps the existing composer textarea and adds two inference-override
 * affordances:
 *
 * 1. Inline ghost-text autocompletion (#860): after 250ms of typing idle the
 *    `/v1/chat/autocomplete` endpoint is queried; the returned continuation
 *    renders muted text directly after the draft. Tab (or → at end-of-text)
 *    accepts it into the draft; Escape or any further edit dismisses it.
 *
 * (The prompt rewrite action previously embedded here (#858) has been
 * relocated to the composer `+` actions menu for a decluttered input area (#1069).)
 *
 * Ownership: the textarea element itself stays owned by ChatPage (via
 * `textareaRef`) so focus, IME, paste, slash-menu, and send handling keep
 * working unchanged. This component only adds the overlay + key interception.
 */

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { fetchAutocomplete } from '../lib/api'
import { useAutoResizeTextarea } from '../features/chat/useAutoResizeTextarea'

export const AUTOCOMPLETE_DEBOUNCE_MS = 250

export const AUTOCOMPLETE_PREF_KEY = 'os.autocompleteEnabled'
const AUTOCOMPLETE_PREF_EVENT = 'os:autocomplete-enabled-changed'

/** Read the user's inline-autocomplete preference (default: on). */
export function loadAutocompleteEnabled(): boolean {
  try {
    const raw = localStorage.getItem(AUTOCOMPLETE_PREF_KEY)
    return raw === null ? true : raw === '1'
  } catch {
    return true
  }
}

/** Persist the preference and broadcast so mounted composers update live. */
export function saveAutocompleteEnabled(value: boolean): void {
  try {
    localStorage.setItem(AUTOCOMPLETE_PREF_KEY, value ? '1' : '0')
  } catch {
    /* private mode — in-memory only for this session */
  }
  window.dispatchEvent(new CustomEvent(AUTOCOMPLETE_PREF_EVENT))
}

interface ChatMessageInputProps {
  /** ChatPage-owned textarea. Rendered here so the ghost overlay can align. */
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  /** All standard textarea props (value/onChange/onKeyDown/aria) forwarded from ChatPage. */
  textareaProps: React.TextareaHTMLAttributes<HTMLTextAreaElement>
  /** Draft text — controls ghost visibility and accept behaviour. */
  value: string
  /** Apply text to the draft (accept + enhance). */
  onApplyText: (next: string) => void
  /** Current agent id, passed to the autocomplete scorer. */
  agentId?: string
  /** Current conversation id, passed to the autocomplete scorer. */
  conversationId?: string
}

export function ChatMessageInput({
  textareaRef,
  textareaProps,
  value,
  onApplyText,
  agentId,
  conversationId,
}: ChatMessageInputProps) {
  const [ghost, setGhost] = useState('')
  const [enabled, setEnabled] = useState(loadAutocompleteEnabled)
  const debounceRef = useRef<number | null>(null)
  const requestIdRef = useRef(0)
  const requestRef = useRef<AbortController | null>(null)
  const composingRef = useRef(false)

  useAutoResizeTextarea(textareaRef, value)

  // Preference changes from Settings propagate live.
  useEffect(() => {
    const sync = () => setEnabled(loadAutocompleteEnabled())
    window.addEventListener(AUTOCOMPLETE_PREF_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(AUTOCOMPLETE_PREF_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  const clearDebounce = useCallback(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
  }, [])

  const cancelAutocomplete = useCallback(() => {
    clearDebounce()
    requestIdRef.current += 1
    requestRef.current?.abort()
    requestRef.current = null
  }, [clearDebounce])

  useEffect(() => {
    if (enabled) return
    cancelAutocomplete()
    setGhost('')
  }, [enabled, cancelAutocomplete])

  // Invalidate any in-flight completion when the draft changes shape outside
  // the debounced fetch (accept, enhance, clear) — stale ghost is worse than none.
  useEffect(() => {
    cancelAutocomplete()
    setGhost('')
  }, [value, cancelAutocomplete])

  // #1400: the composer stays mounted across agent and conversation changes,
  // so a completion scored for the previous target must not land on the new
  // one. The draft-text effect above only runs when `value` changes. A
  // same-text switch (another conversation for this agent, or two agents
  // sharing a draft) leaves the pending debounce alive, and that timer
  // adopts a fresh request id when it fires — bumping the id here is not
  // enough. Cancel the timer too. Do not re-arm: a remount did not fetch
  // for text the user had not just edited, and neither does a target change.
  const autocompleteTarget = `${agentId ?? ''}\0${conversationId ?? ''}`
  const seenAutocompleteTarget = useRef(autocompleteTarget)
  useEffect(() => {
    if (seenAutocompleteTarget.current === autocompleteTarget) return
    seenAutocompleteTarget.current = autocompleteTarget
    cancelAutocomplete()
    setGhost('')
  }, [autocompleteTarget, cancelAutocomplete])

  const scheduleAutocomplete = useCallback(
    (draft: string) => {
      cancelAutocomplete()
      if (!draft.trim()) {
        return
      }
      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null
        const requestId = ++requestIdRef.current
        const controller = new AbortController()
        requestRef.current = controller
        void fetchAutocomplete(draft, {
          agent_id: agentId || undefined,
          conversation_id: conversationId || undefined,
        }, controller.signal)
          .then((res) => {
            if (requestId !== requestIdRef.current) return // superseded
            const completion = res.completion || ''
            // A completion that merely repeats the draft tail is noise.
            setGhost(completion.trim() && !draft.endsWith(completion) ? completion : '')
          })
          .catch(() => {
            /* silent — ghost text is best-effort */
          })
          .finally(() => {
            if (requestRef.current === controller) requestRef.current = null
          })
      }, AUTOCOMPLETE_DEBOUNCE_MS)
    },
    [agentId, conversationId, cancelAutocomplete],
  )

  // Schedule on mount-of-value changes driven by typing. The [value] reset
  // effect above clears the ghost; here we re-arm the debounce for edits.
  const lastTypedRef = useRef(value)
  useEffect(() => {
    if (lastTypedRef.current === value) return
    lastTypedRef.current = value
    if (!enabled || composingRef.current) return
    scheduleAutocomplete(value)
  }, [value, enabled, scheduleAutocomplete])

  useEffect(() => cancelAutocomplete, [cancelAutocomplete])

  const acceptGhost = useCallback(() => {
    if (!ghost) return
    const el = textareaRef.current
    const next = value + ghost
    setGhost('')
    requestIdRef.current += 1
    onApplyText(next)
    if (el) {
      // Move the caret to the end where the accepted text now sits.
      requestAnimationFrame(() => {
        el.focus()
        const len = el.value.length
        el.setSelectionRange(len, len)
      })
    }
  }, [ghost, onApplyText, textareaRef, value])

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (composingRef.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) {
        textareaProps.onKeyDown?.(event)
        return
      }
      if (ghost) {
        if (event.key === 'Tab') {
          event.preventDefault()
          acceptGhost()
          return
        }
        if (event.key === 'ArrowRight') {
          const el = textareaRef.current
          const atEnd =
            el && el.selectionStart === el.value.length && el.selectionEnd === el.value.length
          if (atEnd) {
            event.preventDefault()
            acceptGhost()
            return
          }
        }
        if (event.key === 'Escape') {
          event.preventDefault()
          setGhost('')
          requestIdRef.current += 1
          return
        }
      }
      textareaProps.onKeyDown?.(event)
    },
    [acceptGhost, ghost, textareaProps],
  )

  return (
    <div className="os-composer-input-wrap" data-testid="chat-message-input">
      <div className="os-composer-ghost-stack">
        <textarea ref={textareaRef as React.RefObject<HTMLTextAreaElement>} {...textareaProps} onKeyDown={handleKeyDown}
          onCompositionStart={event => {
            composingRef.current = true
            cancelAutocomplete()
            setGhost('')
            textareaProps.onCompositionStart?.(event)
          }}
          onCompositionEnd={event => {
            composingRef.current = false
            textareaProps.onCompositionEnd?.(event)
            if (enabled) scheduleAutocomplete(event.currentTarget.value)
          }} />
        {ghost ? (
          <span
            className="os-composer-ghost"
            data-testid="composer-ghost-text"
            aria-hidden="true"
          >
            {/* The spacer reproduces the typed draft so the ghost begins
                exactly where the caret is. */}
            <span className="os-composer-ghost__spacer">{value}</span>
            {ghost}
          </span>
        ) : null}
      </div>
    </div>
  )
}

export default ChatMessageInput
