/**
 * #1167 — typing anywhere in chat focuses the composer.
 *
 * When focus sits on the page body (after clicking around), printable typing
 * must land in the message input — keystrokes going nowhere is the classic
 * chat-app frustration. Deliberate exclusions:
 *
 * - Any modifier (ctrl/meta/alt) held → a shortcut, not prose; never capture.
 * - Focus already in an editable control (input, textarea, contenteditable,
 *   select) → the keystroke already has a home; never steal it.
 * - Non-printable keys (Tab, arrows, F-keys, Escape, Enter with no text yet,
 *   Space with modifiers, etc.) → not prose.
 * - IME composition (`isComposing`) → the IME owns the keystrokes.
 * - A focus trap is irrelevant here: dialogs' inputs are editable controls,
 *   so they are excluded by the editable-target rule anyway.
 *
 * Returns a cleanup fn via the caller's effect.
 */

const EDITABLE_SELECTOR =
  'input, textarea, select, [contenteditable="true"], [contenteditable=""]'

/** Printable prose keys: length-1 character keys (letters, digits, punctuation, space). */
export function isPrintableProseKey(event: globalThis.KeyboardEvent): boolean {
  if (event.ctrlKey || event.metaKey || event.altKey) return false
  if (event.isComposing) return false
  // `key.length === 1` covers letters/digits/punctuation/space (' ') and
  // excludes named keys ('Tab', 'Enter', 'ArrowLeft', 'F2', 'Escape', ...).
  return event.key.length === 1
}

export function targetIsEditable(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  if (target.closest(EDITABLE_SELECTOR)) return true
  return false
}

/**
 * Build the window-level keydown handler. `focusComposer` focuses the
 * textarea; the browser delivers the same keydown to it only if focus moves
 * synchronously — we therefore also append the character ourselves when the
 * target element supports it (via the passed `typeChar` hook).
 */
export function makeTypingFocusHandler(
  focusComposer: () => HTMLTextAreaElement | null,
  typeChar: (el: HTMLTextAreaElement, ch: string) => void,
): (event: globalThis.KeyboardEvent) => void {
  return (event) => {
    if (event.defaultPrevented) return
    if (!isPrintableProseKey(event)) return
    if (targetIsEditable(event.target)) return
    const el = focusComposer()
    if (!el) return
    // Take the keystroke into the now-focused composer so nothing is lost.
    typeChar(el, event.key)
    event.preventDefault()
  }
}
