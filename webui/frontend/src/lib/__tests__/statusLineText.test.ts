/**
 * #782 — notification/label rows must be bubble-theme aware.
 *
 * IRC lines are plain text (`<nick> message`); markdown chrome (bold links,
 * headings, code spans) belongs to bubble themes, not the gutter. This helper
 * strips inline/block markdown down to the words and URLs and flattens the
 * result to one transcript-safe line, truncating long notices with an ellipsis
 * (full text stays on disk and in the title/tooltip).
 */
import { describe, expect, it } from 'vitest'
import { statusLineLabel } from '../statusLineText'

describe('statusLineLabel (#782)', () => {
  it('passes plain text through untouched', () => {
    expect(statusLineLabel('Started a new omp session')).toBe('Started a new omp session')
  })

  it('strips markdown links to their label + URL', () => {
    const out = statusLineLabel('[OpenMausBot](http://x.test/api) requires auth')
    expect(out).toBe('OpenMausBot (http://x.test/api) requires auth')
  })

  it('drops emphasis, headings and code fences', () => {
    expect(statusLineLabel('**bold** _under_ `code`')).toBe('bold under code')
    const headed = statusLineLabel('# Heading\nbody line')
    expect(headed).toBe('Heading body line')
    const fenced = statusLineLabel('```\nconst x = 1\n```')
    expect(fenced).not.toContain('`')
    expect(fenced).toContain('const x = 1')
  })

  it('flattens multiline text to one line', () => {
    expect(statusLineLabel('line one\nline two\n\nline three')).toBe(
      'line one line two line three',
    )
  })

  it('truncates long text with an ellipsis', () => {
    const long = 'x'.repeat(500)
    const out = statusLineLabel(long)
    expect(out.endsWith('…')).toBe(true)
    expect(out.length).toBeLessThanOrEqual(201)
  })

  it('collapses excessive whitespace', () => {
    expect(statusLineLabel('a   b\tc')).toBe('a b c')
  })

  it('handles empty and whitespace-only input', () => {
    expect(statusLineLabel('')).toBe('')
    expect(statusLineLabel('   \n\t ')).toBe('')
  })

  it('keeps bare URLs as-is', () => {
    expect(statusLineLabel('see http://x.test/docs for details')).toBe(
      'see http://x.test/docs for details',
    )
  })
})
