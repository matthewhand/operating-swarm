/**
 * REQ-925 / #578: Scoped text selection within a chat message bubble.
 *
 * When replying to or copying from a message via the context menu:
 * - If text is actively selected inside the clicked bubble, returns that text slice.
 * - If the selection spans outside the bubble, or across multiple messages,
 *   falls back to null (so the entire message is quoted/copied instead of
 *   attributing text from message A to message B's speaker).
 * - Empty or whitespace-only selection returns null.
 * - Collapsed or missing selection returns null.
 */

export function getScopedSelectionText(targetElement: Element | null): string | null {
  if (typeof window === 'undefined' || !window.getSelection || !targetElement) {
    return null
  }
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null
  }
  try {
    const range = selection.getRangeAt(0)
    const ancestor = range.commonAncestorContainer
    const ancestorEl =
      ancestor.nodeType === Node.ELEMENT_NODE ? (ancestor as Element) : ancestor.parentElement
    if (!ancestorEl || !targetElement.contains(ancestorEl)) {
      return null
    }
    const text = selection.toString().trim()
    return text.length > 0 ? text : null
  } catch {
    return null
  }
}

/** #846: the last selection seen inside a bubble, keyed by message. */
export interface CachedBubbleSelection {
  messageKey: string
  text: string
}

/**
 * #846: resolve the quote text for a Reply action.
 *
 * Live scoped selection wins. When the browser has already collapsed the
 * selection (a right-click's mousedown collapses it before `contextmenu`
 * fires), fall back to the pre-collapse cache — but ONLY for the same
 * message: a selection made in message A must never quote message B.
 */
export function resolveReplyQuote(opts: {
  targetElement: Element | null
  cached: CachedBubbleSelection | null
  messageKey: string
}): string | null {
  const live = getScopedSelectionText(opts.targetElement)
  if (live) return live
  const cached = opts.cached
  if (cached && cached.messageKey === opts.messageKey && cached.text.trim().length > 0) {
    return cached.text
  }
  return null
}
