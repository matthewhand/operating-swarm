/**
 * #1677 — click-to-edit inline text field for the agent edit pane.
 *
 * Not a `<div onClick>`. The idle state is a real `<button>` (so it is in the
 * tab order, reachable, and activatable with Enter/Space from the keyboard) and
 * the editing state is a real `<input>`/`<textarea>` with a real `aria-label`.
 * The accessible name of the button says what the value is *and* that it is
 * editable, because "Codey, button" does not tell a screen-reader user that
 * anything can happen.
 *
 * Two rules this component exists to enforce:
 *
 * 1. **A failed save is visible.** `onSave` is expected to reject when the
 *    write fails. On rejection the component keeps the editor open with the
 *    draft intact, restores focus to the input, marks it `aria-invalid`, and
 *    renders the reason in a `role="alert"` region. It does NOT exit edit mode
 *    and it does NOT present the new value as saved — the parent owns the
 *    committed value and must not have optimistically changed it.
 * 2. **No handler is ever swallowed.** The idle button and the editor both
 *    accept and forward every standard handler `AGENTS.md` names:
 *    `onKeyDown`, `onKeyUp`, `onKeyPress`, `onChange`, `onInput`, `onFocus`,
 *    `onBlur`, `onPaste`, `onCompositionStart`, `onCompositionEnd`. The
 *    component's own logic runs first and then the caller's handler is invoked
 *    with the same event. Dropping `onKeyDown` here would be the same class of
 *    bug as dropping it when wrapping the composer textarea.
 */
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ClipboardEventHandler,
  type CompositionEventHandler,
  type FocusEventHandler,
  type FormEventHandler,
  type KeyboardEventHandler,
  type ChangeEventHandler,
} from 'react'

/** The element type the handlers are declared against. Both variants are
 *  `HTMLInputElement | HTMLTextAreaElement`; contravariance means a handler
 *  declared here is assignable to either element's prop. */
type EditableElement = HTMLInputElement | HTMLTextAreaElement

export interface InlineEditTextProps {
  value: string
  /** Field name. Used for the visible label, the editor's `aria-label`, and the
   *  idle button's accessible name. */
  label: string
  /** Persist the draft. **Reject to report a failure** — the editor will stay
   *  open, keep the draft, and surface the reason. Resolve to mean committed. */
  onSave: (next: string) => Promise<void> | void
  /** Multiline variant (description / blurb). Enter inserts a newline; commit is
   *  blur, Cmd/Ctrl+Enter, or the Save button. */
  multiline?: boolean
  rows?: number
  allowEmpty?: boolean
  maxLength?: number
  /** Shown when the value is empty, both in the button and in the editor. */
  placeholder?: string
  /** Extra guidance under the field. Also wired to `aria-describedby`. */
  hint?: string
  /** Stable hook for tests and for callers that need to address the control. */
  testId?: string
  className?: string
  // ---- forwarded handlers (AGENTS.md: never drop one) ----
  onKeyDown?: KeyboardEventHandler<EditableElement>
  onKeyUp?: KeyboardEventHandler<EditableElement>
  onKeyPress?: KeyboardEventHandler<EditableElement>
  onChange?: ChangeEventHandler<EditableElement>
  onInput?: FormEventHandler<EditableElement>
  onFocus?: FocusEventHandler<EditableElement>
  onBlur?: FocusEventHandler<EditableElement>
  onPaste?: ClipboardEventHandler<EditableElement>
  onCompositionStart?: CompositionEventHandler<EditableElement>
  onCompositionEnd?: CompositionEventHandler<EditableElement>
}

function messageOf(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return fallback
}

export function InlineEditText({
  value,
  label,
  onSave,
  multiline = false,
  rows = 2,
  allowEmpty = false,
  maxLength,
  placeholder,
  hint,
  testId,
  className = '',
  onKeyDown,
  onKeyUp,
  onKeyPress,
  onChange,
  onInput,
  onFocus,
  onBlur,
  onPaste,
  onCompositionStart,
  onCompositionEnd,
}: InlineEditTextProps) {
  const uid = useId()
  const fieldId = `${uid}-field`
  const statusId = `${uid}-status`
  const hintId = hint ? `${uid}-hint` : undefined

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const editorRef = useRef<EditableElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const settledRef = useRef(false)
  const composingRef = useRef(false)
  // Focus has to travel back to the trigger AFTER it remounts. Calling
  // `trigger.focus()` inside the click/key handler that ended the edit is a
  // no-op, because at that instant `editing` is still true and the button is
  // not in the tree — the ref is null and focus lands on <body>, stranding a
  // keyboard user at the top of the document.
  const returnFocusRef = useRef(false)
  // Bumped by every `begin` and every `cancel`. A commit captures it and only
  // reports a failure if it is still the live attempt — a rejection that lands
  // after the user walked away must not resurrect an error they never saw the
  // cause of. (`settledRef` cannot serve here: it is deliberately `true` for
  // the whole duration of a commit, failure included.)
  const attemptRef = useRef(0)
  const onSaveRef = useRef(onSave)
  onSaveRef.current = onSave

  const display = value.trim() ? value : ''
  const shown = display || placeholder || `Add ${label.toLowerCase()}`

  // A committed value arriving from the server (or a rollback) resets the
  // editor. While the user is typing, the draft is theirs.
  useEffect(() => {
    if (!editing) setDraft(value)
  }, [value, editing])

  useEffect(() => {
    if (editing) {
      const node = editorRef.current
      if (!node) return
      node.focus()
      node.select?.()
      return
    }
    if (!returnFocusRef.current) return
    returnFocusRef.current = false
    const trigger = triggerRef.current
    if (trigger && typeof trigger.focus === 'function') trigger.focus()
  }, [editing])

  const begin = useCallback(() => {
    settledRef.current = false
    composingRef.current = false
    returnFocusRef.current = false
    attemptRef.current += 1
    setError(null)
    setDraft(value)
    setEditing(true)
  }, [value])

  /** Leave edit mode and hand focus back to the trigger that opened it. */
  const settle = useCallback(() => {
    returnFocusRef.current = true
    setEditing(false)
  }, [])

  const commit = useCallback(async () => {
    // Enter/Escape settle first; the trailing blur must not re-run the commit.
    if (settledRef.current) return
    settledRef.current = true
    const attempt = attemptRef.current
    const next = draft.trim()
    const previous = value

    if (!next && !allowEmpty) {
      setError(`${label} cannot be empty.`)
      settledRef.current = false
      return
    }
    if (maxLength && next.length > maxLength) {
      setError(`${label} must be ${maxLength} characters or fewer.`)
      settledRef.current = false
      return
    }
    if (next === previous.trim()) {
      settle()
      return
    }

    setSaving(true)
    setError(null)
    try {
      await onSaveRef.current(next)
      setDraft(next)
      settle()
    } catch (err) {
      // The editor was cancelled or re-opened while this write was in flight.
      // The user's intent wins over a stale failure notice: without this,
      // cancelling a slow save would leave the error text sitting under the
      // idle trigger for a write they explicitly walked away from.
      if (attemptRef.current !== attempt) return
      // Keep the draft and the editor open. The parent must not have adopted
      // `next`, so the idle value on re-entry is still the last saved one.
      setError(messageOf(err, `Could not save ${label.toLowerCase()}.`))
      const node = editorRef.current
      if (node) {
        node.focus()
        node.select?.()
      }
    } finally {
      setSaving(false)
      settledRef.current = false
    }
  }, [allowEmpty, draft, label, maxLength, settle, value])

  const cancel = useCallback(() => {
    settledRef.current = true
    attemptRef.current += 1
    setDraft(value)
    setError(null)
    settle()
  }, [settle, value])

  if (!editing) {
    return (
      <div className={`os-inline-edit ${className}`.trim()} data-testid={testId}>
        <span className="os-inline-edit__label text-sm font-medium" data-testid={`${testId}-label`}>
          {label}
        </span>
        <button
          ref={triggerRef}
          type="button"
          className="os-inline-edit__value"
          data-testid={`${testId}-trigger`}
          // Announced as: "<label>: <value>. Activate to edit <label>."
          aria-label={`${label}: ${shown}. Activate to edit ${label}.`}
          aria-describedby={hintId}
          onClick={begin}
        >
          <span className={display ? '' : 'text-base-content/50'}>{shown}</span>
        </button>
        {hint ? (
          <p className="os-inline-edit__hint text-xs text-base-content/60" id={hintId}>
            {hint}
          </p>
        ) : null}
        {error ? (
          <p className="os-inline-edit__error text-xs text-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    )
  }

  const shared = {
    id: fieldId,
    ref: editorRef as never,
    className: `os-inline-edit__editor ${error ? 'input-error' : ''}`.trim(),
    'aria-label': label,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': [hintId, error ? statusId : null].filter(Boolean).join(' ') || undefined,
    value: draft,
    disabled: saving,
    spellCheck: false,
    autoComplete: 'off',
    onCompositionStart: (event: React.CompositionEvent<EditableElement>) => {
      composingRef.current = true
      onCompositionStart?.(event)
    },
    onCompositionEnd: (event: React.CompositionEvent<EditableElement>) => {
      composingRef.current = false
      onCompositionEnd?.(event)
    },
    onChange: (event: React.ChangeEvent<EditableElement>) => {
      setDraft(event.target.value)
      onChange?.(event)
    },
    onInput: (event: React.FormEvent<EditableElement>) => {
      onInput?.(event)
    },
    onKeyDown: (event: React.KeyboardEvent<EditableElement>) => {
      if (composingRef.current) {
        onKeyDown?.(event)
        return
      }
      if (event.key === 'Escape') {
        // Cancel, and keep Escape from reaching a global hotkey handler.
        event.preventDefault()
        event.stopPropagation()
        cancel()
        onKeyDown?.(event)
        return
      }
      const isCommit =
        event.key === 'Enter' && (!multiline || event.metaKey || event.ctrlKey)
      if (isCommit) {
        event.preventDefault()
        event.stopPropagation()
        void commit()
      }
      onKeyDown?.(event)
    },
    onKeyUp: (event: React.KeyboardEvent<EditableElement>) => {
      onKeyUp?.(event)
    },
    onKeyPress: (event: React.KeyboardEvent<EditableElement>) => {
      onKeyPress?.(event)
    },
    onFocus: (event: React.FocusEvent<EditableElement>) => {
      onFocus?.(event)
    },
    onBlur: (event: React.FocusEvent<EditableElement>) => {
      // Blur commits. `settledRef` makes the blur that follows an Enter/Escape
      // (and the blur that follows a failed commit) a no-op.
      void commit()
      onBlur?.(event)
    },
    onPaste: (event: React.ClipboardEvent<EditableElement>) => {
      onPaste?.(event)
    },
  }

  return (
    <div className={`os-inline-edit ${className}`.trim()} data-testid={testId}>
      <label className="os-inline-edit__label text-sm font-medium" htmlFor={fieldId}>
        {label}
      </label>
      {multiline ? (
        <textarea
          {...shared}
          className={`${shared.className} textarea`}
          rows={rows}
          maxLength={maxLength}
        />
      ) : (
        <input {...shared} className={`${shared.className} input`} type="text" maxLength={maxLength} />
      )}
      <div className="os-inline-edit__actions">
        <button
          type="button"
          className="btn btn-primary btn-xs"
          data-testid={`${testId}-save`}
          disabled={saving}
          onClick={() => void commit()}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-xs"
          data-testid={`${testId}-cancel`}
          // Deliberately NOT disabled while a write is in flight: a user must
          // be able to walk away from a save that is stuck. The commit's
          // attempt token makes the late rejection a no-op when they do.
          onClick={cancel}
        >
          Cancel
        </button>
        {/* One live region for both outcomes. `role="alert"` on failure so the
            reason interrupts; `status` while saving so it does not. */}
        <p
          className="os-inline-edit__status text-xs"
          id={statusId}
          role={error ? 'alert' : 'status'}
          aria-live={error ? 'assertive' : 'polite'}
        >
          {error ? error : saving ? `Saving ${label.toLowerCase()}…` : ''}
        </p>
      </div>
      {hint ? (
        <p className="os-inline-edit__hint text-xs text-base-content/60" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export default InlineEditText
