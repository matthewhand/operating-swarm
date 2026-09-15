import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import RailContextMenu from '../RailContextMenu'
import type { RailMenuItemSpec } from '../../lib/railContextMenu'

// #74 — "Rail context menu clips at viewport bottom".
//
// The menu is `position: fixed` and clamps itself to the viewport in a
// layout effect using its measured box (with fallbacks for jsdom, which
// reports zero offsets). These tests pin both axes: a menu opened at the very
// bottom-right corner must be pulled back inside the viewport instead of
// overflowing, and the measured height must be honoured over the fallback.

const items: RailMenuItemSpec[] = [
  { id: 'pin', label: 'Pin', group: 0 },
  { id: 'duplicate', label: 'Duplicate', group: 1 },
  { id: 'copy-id', label: 'Copy ID', group: 1 },
]

const VIEWPORT = { width: 1024, height: 768 }
const MARGIN = 8
const FALLBACK_WIDTH = 208

function stubViewport() {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: VIEWPORT.width })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: VIEWPORT.height })
}

function stubMenuBox(height: number) {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get: () => 0,
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => height,
  })
}

function styleOf(el: HTMLElement) {
  return { left: Number.parseFloat(el.style.left), top: Number.parseFloat(el.style.top) }
}

describe('RailContextMenu viewport clamping (#74)', () => {
  beforeEach(() => {
    stubViewport()
  })

  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).offsetHeight
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).offsetWidth
  })

  it('pulls a context menu opened at the bottom-right corner back inside the viewport', () => {
    stubMenuBox(320)
    render(
      <RailContextMenu
        agentName="Codey"
        x={VIEWPORT.width - 2}
        y={VIEWPORT.height - 2}
        items={items}
        onSelect={() => {}}
      />,
    )

    const menu = screen.getByTestId('rail-context-menu')
    const { left, top } = styleOf(menu)

    // Never past the edge…
    expect(left).toBeLessThanOrEqual(VIEWPORT.width - FALLBACK_WIDTH - MARGIN)
    expect(top).toBeLessThanOrEqual(VIEWPORT.height - 320 - MARGIN)
    // …and never pushed off the opposite edge either.
    expect(left).toBeGreaterThanOrEqual(MARGIN)
    expect(top).toBeGreaterThanOrEqual(MARGIN)
    // Concretely: the menu's bottom edge sits inside the viewport.
    expect(top + 320).toBeLessThanOrEqual(VIEWPORT.height)
  })

  it('keeps an in-viewport position untouched', () => {
    stubMenuBox(200)
    render(<RailContextMenu agentName="Codey" x={120} y={140} items={items} onSelect={() => {}} />)

    expect(styleOf(screen.getByTestId('rail-context-menu'))).toEqual({ left: 120, top: 140 })
  })

  it('falls back to the default width when the node reports no measured box', () => {
    stubMenuBox(0)
    render(
      <RailContextMenu
        agentName="Codey"
        x={VIEWPORT.width - 2}
        y={VIEWPORT.height - 2}
        items={items}
        onSelect={() => {}}
      />,
    )

    const { left, top } = styleOf(screen.getByTestId('rail-context-menu'))
    expect(left).toBe(VIEWPORT.width - FALLBACK_WIDTH - MARGIN)
    expect(top).toBe(VIEWPORT.height - MARGIN)
  })
})
