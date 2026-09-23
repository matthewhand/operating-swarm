/**
 * #846 — reply must quote what the user highlighted, not the whole message.
 *
 * `resolveReplyQuote` is the single decision point: live scoped selection
 * wins; when the browser already collapsed the selection (right-click's
 * mousedown fires before `contextmenu`), the pre-collapse cache is used —
 * but only for the SAME message. No cache and no selection → null (full-
 * message reply, the pre-#846 behavior).
 */
import { describe, expect, it } from 'vitest'
import { resolveReplyQuote, type CachedBubbleSelection } from '../bubbleSelection'

describe('#846 resolveReplyQuote', () => {
  it('prefers the live selection', () => {
    // jsdom has no real selection here; live=null, cache must be ignored for
    // a different message.
    const cached: CachedBubbleSelection = { messageKey: 'other', text: 'other message text' }
    expect(resolveReplyQuote({ targetElement: null, cached, messageKey: 'm1' })).toBeNull()
  })

  it('falls back to the cache for the same message', () => {
    const cached: CachedBubbleSelection = { messageKey: 'm1', text: 'only this sentence' }
    expect(resolveReplyQuote({ targetElement: null, cached, messageKey: 'm1' })).toBe(
      'only this sentence',
    )
  })

  it('never crosses messages', () => {
    const cached: CachedBubbleSelection = { messageKey: 'm1', text: 'selection in message one' }
    expect(resolveReplyQuote({ targetElement: null, cached, messageKey: 'm2' })).toBeNull()
  })

  it('ignores whitespace-only cache entries', () => {
    const cached: CachedBubbleSelection = { messageKey: 'm1', text: '   ' }
    expect(resolveReplyQuote({ targetElement: null, cached, messageKey: 'm1' })).toBeNull()
  })

  it('returns null with nothing at all (full-message reply path)', () => {
    expect(resolveReplyQuote({ targetElement: null, cached: null, messageKey: 'm1' })).toBeNull()
  })
})
