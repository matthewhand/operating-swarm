/**
 * #1231 — the composer routing pill drops the #770 drag-resize grip in
 * favour of a fixed 32-character label cap with ellipsis; the unclipped
 * provider/model path stays on the tooltip (`title`) and `data-value`.
 */
import { describe, expect, it } from 'vitest'
import { truncatePillLabel, COMPOSER_PILL_MAX_CHARS } from '../routingPillLabel'

describe('#1231: pill label truncation', () => {
  it('caps at 32 characters', () => {
    expect(COMPOSER_PILL_MAX_CHARS).toBe(32)
  })

  it('leaves short labels alone', () => {
    expect(truncatePillLabel('agy/grok-4.6')).toBe('agy/grok-4.6')
  })

  it('truncates long labels with an ellipsis', () => {
    const long = 'orchestration/anthropic/claude-3-7-sonnet-latest'
    const out = truncatePillLabel(long)
    expect(out.length).toBeLessThanOrEqual(32)
    expect(out.endsWith('…')).toBe(true)
    expect(out.startsWith('orchestration/')).toBe(true)
  })

  it('is exactly 32 chars when truncating (ellipsis inclusive)', () => {
    const out = truncatePillLabel('x'.repeat(80))
    expect(out.length).toBe(32)
  })

  it('collapses whitespace before measuring', () => {
    expect(truncatePillLabel('agy/  grok-4.6  ')).toBe('agy/ grok-4.6')
  })

  it('is empty-safe', () => {
    expect(truncatePillLabel('')).toBe('')
    expect(truncatePillLabel(null)).toBe('')
  })
})

describe('#1231: resize machinery removed', () => {
  it('composerPillResize module is gone', () => {
    // Static import analysis would fail the suite on a live import, so probe
    // the filesystem instead (the module must not exist to import).
    expect(() => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      require.resolve('../composerPillResize')
    }).toThrow()
  })
})
