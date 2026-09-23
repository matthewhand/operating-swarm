import { describe, expect, it, vi, afterEach } from 'vitest'
import { getScopedSelectionText } from '../bubbleSelection'

describe('getScopedSelectionText (#578)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns null when window.getSelection returns null or is collapsed', () => {
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: true,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: document.body } as any),
      toString: () => '',
    } as any)

    const el = document.createElement('div')
    expect(getScopedSelectionText(el)).toBeNull()
  })

  it('returns selected text when selection is contained within targetElement', () => {
    const container = document.createElement('div')
    const p = document.createElement('p')
    p.textContent = 'Hello world from inside bubble'
    container.appendChild(p)
    document.body.appendChild(container)

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: p } as any),
      toString: () => 'world from inside',
    } as any)

    expect(getScopedSelectionText(container)).toBe('world from inside')
    document.body.removeChild(container)
  })

  it('returns null when selection spans outside targetElement (e.g. across multiple bubbles)', () => {
    const bubbleA = document.createElement('div')
    const bubbleB = document.createElement('div')
    const parent = document.createElement('div')
    parent.appendChild(bubbleA)
    parent.appendChild(bubbleB)
    document.body.appendChild(parent)

    // Selection spans both bubbles, so common ancestor is the parent div, NOT bubbleA
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: parent } as any),
      toString: () => 'text spanning both bubbles',
    } as any)

    expect(getScopedSelectionText(bubbleA)).toBeNull()
    expect(getScopedSelectionText(bubbleB)).toBeNull()
    document.body.removeChild(parent)
  })

  it('returns null when selection contains only whitespace', () => {
    const container = document.createElement('div')
    const span = document.createElement('span')
    span.textContent = '   '
    container.appendChild(span)
    document.body.appendChild(container)

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: span } as any),
      toString: () => '   \n  ',
    } as any)

    expect(getScopedSelectionText(container)).toBeNull()
    document.body.removeChild(container)
  })

  it('returns null when targetElement is null', () => {
    expect(getScopedSelectionText(null)).toBeNull()
  })
})
