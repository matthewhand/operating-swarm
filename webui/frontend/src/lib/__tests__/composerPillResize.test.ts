import {
  COMPOSER_PILL_AUTO_MAX,
  COMPOSER_PILL_MIN_WIDTH,
  COMPOSER_PILL_WIDTH_STORAGE_KEY,
  clampPillWidth,
  loadPillWidth,
  pillWidthFromDrag,
  savePillWidth,
} from '../composerPillResize'

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
