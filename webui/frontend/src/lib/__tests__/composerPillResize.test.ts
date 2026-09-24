import {
  COMPOSER_PILL_AUTO_MAX,
  COMPOSER_PILL_MIN_WIDTH,
  COMPOSER_PILL_WIDTH_STORAGE_KEY,
  clampPillWidth,
  loadPillWidth,
  pillWidthFromDrag,
  savePillWidth,
} from '../composerPillResize'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#770 — composer pill resize math', () => {
  it('clamps to min ~3 chars and never above the full text width', () => {
    expect(clampPillWidth(10, 300)).toBe(COMPOSER_PILL_MIN_WIDTH)
    expect(clampPillWidth(500, 300)).toBe(300)
    expect(clampPillWidth(220, 300)).toBe(220)
  })

  it('full text width below min still yields a usable handle (min wins)', () => {
    expect(clampPillWidth(500, 20)).toBe(COMPOSER_PILL_MIN_WIDTH)
  })

  it('drag math expands on left-drag (negative delta) and contracts on right-drag (positive delta)', () => {
    // Dragging left (negative deltaX) widens the pill toward fullText
    expect(pillWidthFromDrag(100, -40, 300)).toBe(140)
    expect(pillWidthFromDrag(280, -40, 300)).toBe(300)
    // Dragging right (positive deltaX) narrows the pill toward min
    expect(pillWidthFromDrag(100, 30, 300)).toBe(70)
    expect(pillWidthFromDrag(100, 80, 300)).toBe(COMPOSER_PILL_MIN_WIDTH)
  })

  it('persists and clears the width across refreshes', () => {
    savePillWidth(240)
    expect(loadPillWidth()).toBe(240)
    savePillWidth(null)
    expect(loadPillWidth()).toBeNull()
    expect(localStorage.getItem(COMPOSER_PILL_WIDTH_STORAGE_KEY)).toBeNull()
  })

  it('garbage or below-min persisted values fall back to auto', () => {
    localStorage.setItem(COMPOSER_PILL_WIDTH_STORAGE_KEY, 'nonsense')
    expect(loadPillWidth()).toBeNull()
    localStorage.setItem(COMPOSER_PILL_WIDTH_STORAGE_KEY, '4')
    expect(loadPillWidth()).toBeNull()
    localStorage.setItem(COMPOSER_PILL_WIDTH_STORAGE_KEY, String(COMPOSER_PILL_AUTO_MAX))
    expect(loadPillWidth()).toBe(COMPOSER_PILL_AUTO_MAX)
    localStorage.removeItem(COMPOSER_PILL_WIDTH_STORAGE_KEY)
  })
})

describe('#1136 — provider/model pill stops clipping long names', () => {
  const css = readFileSync(join(__dirname, '..', '..', 'index.css'), 'utf8')

  it('auto cap grows from 152 (9.5rem) to 200 (12.5rem)', () => {
    expect(COMPOSER_PILL_AUTO_MAX).toBe(200)
  })

  it('CSS max-width matches the JS cap so the pill can actually reach it', () => {
    // #1135 landed the base block at 13rem (≥ the 200px JS cap); the
    // composer-scoped override must not re-clip below it (#1136).
    const block = css.match(/\.os-routing-pill \{[^}]*\}/)?.[0] ?? ''
    expect(block).toContain('max-width: 13rem')
    const composerBlock = css.match(/\.os-composer \.os-routing-pill \{[^}]*\}/)?.[0] ?? ''
    expect(composerBlock).toContain('max-width: 13rem')
  })
})
