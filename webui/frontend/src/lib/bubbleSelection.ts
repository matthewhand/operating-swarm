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
