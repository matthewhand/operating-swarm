/**
 * #1697 — the composer agent/model selector must not be clipped by the left
 * sidepane.
 *
 * The palette is mounted inside the composer (`.os-routing-picker` →
 * `.os-chat-bottom-dock sticky bottom-0 z-20`). A positioned element with a
 * z-index opens a stacking context, so the overlay's own `position: fixed` +
 * `z-index: 100` only ranked *inside* that dock: the sidepane
 * (`lg:relative lg:z-30`) painted over the dialog's leading edge and the popup
 * read as `h models` / `ief of Staff` at 1280×800.
 *
 * The fix has two halves, and both are guarded here:
 *   1. the overlay is portalled to <body>, out of the dock's stacking context;
 *   2. `--os-rail-inset-start/end` (published by `useRailResize`) inset the
 *      centering box past the sidepane, so the dialog lands in the workspace.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { renderHook, act } from '@testing-library/react'
import ModelSearchPalette, { type ModelSearchOption } from '../ModelSearchPalette'
import { useRailResize } from '../sidebar/useRailResize'
import { DEFAULT_RAIL_WIDTH, COLLAPSED_RAIL_WIDTH } from '../../lib/railResize'
import { RAIL_SIDE_STORAGE_KEY } from '../../lib/railSide'

const MODELS: ModelSearchOption[] = [
  { id: 'all', label: 'All members' },
  { id: 'chief-of-staff', label: 'Chief of Staff' },
  { id: 'engineering-lead', label: 'Engineering Lead' },
]

/** Mirrors the live shell: the picker lives in the sticky composer dock. */
function renderInComposerDock() {
  return render(
    <div className="os-chat-bottom-dock sticky bottom-0 z-20" data-testid="dock">
      <div className="os-composer-row">
        <div className="os-composer">
          <div className="os-routing-picker" data-testid="routing-picker">
            <ModelSearchPalette
              open
              models={MODELS}
              selectedId="all"
              onClose={vi.fn()}
              onSelect={vi.fn()}
            />
          </div>
        </div>
      </div>
    </div>,
  )
}

describe('#1697 composer agent selector vs the left sidepane', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('style')
  })

  it('portals the palette out of the composer dock so the sidepane cannot overpaint it', () => {
    renderInComposerDock()
    const overlay = screen.getByTestId('os-model-search-overlay')
    const dock = screen.getByTestId('dock')
    const picker = screen.getByTestId('routing-picker')
    // The stacking trap was DOM containment, not geometry: the overlay reaches
    // <body> instead of descending from the z-20 dock.
    expect(document.body).toContainElement(overlay)
    expect(dock).not.toContainElement(overlay)
    expect(picker).not.toContainElement(overlay)
    expect(overlay).toContainElement(screen.getByRole('dialog', { name: 'Models' }))
  })

  it('marks the overlay and dialog as workspace-aware', () => {
    renderInComposerDock()
    expect(screen.getByTestId('os-model-search-overlay')).toHaveClass(
      'os-search-overlay--workspace',
    )
    expect(screen.getByRole('dialog', { name: 'Models' })).toHaveClass(
      'os-search-palette--workspace',
    )
  })

  it('keeps the portalled dialog closable with Escape and the backdrop', () => {
    const onClose = vi.fn()
    render(
      <div className="os-chat-bottom-dock z-20">
        <ModelSearchPalette open models={MODELS} onClose={onClose} onSelect={vi.fn()} />
      </div>,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.mouseDown(screen.getByTestId('os-model-search-overlay'))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('reserves the sidepane width in the centering box and sizes the frame from it', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')
    const overlay = css.split('.os-search-overlay--workspace {')[1]?.split('}')[0] ?? ''
    expect(overlay).toMatch(/padding-inline:/)
    expect(overlay).toMatch(/var\(--os-rail-inset-start,\s*0px\)/)
    expect(overlay).toMatch(/var\(--os-rail-inset-end,\s*0px\)/)

    // The frame follows the centered box, not the raw viewport, so it can never
    // be wider than the workspace the overlay now reserves.
    const palette = css.split('.os-search-palette--workspace {')[1]?.split('}')[0] ?? ''
    expect(palette).toMatch(/width:\s*min\(48rem,\s*100%\)/)
    expect(palette).toMatch(/min-width:\s*min\(560px,\s*100%\)/)
    expect(palette).not.toMatch(/100vw/)
  })
})

describe('#1697 sidepane reserved width reaches the overlay', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('style')
  })

  const rootVar = (name: string) =>
    document.documentElement.style.getPropertyValue(name)

  it('puts the reserved width on the docked edge for a left-docked rail', () => {
    localStorage.setItem(RAIL_SIDE_STORAGE_KEY, 'left')
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.setRailWidth(DEFAULT_RAIL_WIDTH))
    expect(rootVar('--os-rail-inset-start')).toBe(`${DEFAULT_RAIL_WIDTH}px`)
    expect(rootVar('--os-rail-inset-end')).toBe('0px')
  })

  it('mirrors onto the end edge when the #816 rail docks right', () => {
    localStorage.setItem(RAIL_SIDE_STORAGE_KEY, 'right')
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.setRailWidth(DEFAULT_RAIL_WIDTH))
    expect(rootVar('--os-rail-inset-start')).toBe('0px')
    expect(rootVar('--os-rail-inset-end')).toBe(`${DEFAULT_RAIL_WIDTH}px`)
  })

  it('collapses both insets to 0px with the rail (#1289 reclaim)', () => {
    localStorage.setItem(RAIL_SIDE_STORAGE_KEY, 'left')
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.setRailWidth(DEFAULT_RAIL_WIDTH))
    act(() => result.current.concealSidebar())
    expect(rootVar('--os-rail-inset-start')).toBe(`${COLLAPSED_RAIL_WIDTH}px`)
    expect(rootVar('--os-rail-inset-end')).toBe('0px')
  })

  it('drops the insets on narrow viewports so the drawer overlay stays full-bleed', () => {
    renderHook(() => useRailResize({ narrow: true }))
    expect(rootVar('--os-rail-inset-start')).toBe('')
    expect(rootVar('--os-rail-inset-end')).toBe('')
  })
})
