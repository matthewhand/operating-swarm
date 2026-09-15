import { describe, it, expect } from 'vitest'
import { renderSafeMarkdown } from '../markdown'

describe('renderSafeMarkdown', () => {
  it('renders bold and code', () => {
    const view = renderSafeMarkdown('hello **world** and `code`')
    expect(view).toContain('<strong>world</strong>')
    expect(view).toContain('<code>code</code>')
  })

  it('does not execute raw HTML from markdown source', () => {
    const view = renderSafeMarkdown('hi <script>alert(1)</script> **ok**')
    expect(view.toLowerCase()).not.toContain('<script')
    expect(view).toContain('<strong>ok</strong>')
  })

  it('returns empty string for empty input', () => {
    expect(renderSafeMarkdown('')).toBe('')
  })

  it('highlights Python fenced code', () => {
    const view = renderSafeMarkdown('```python\ndef hello():\n    return "ok"\n```')
    expect(view).toContain('os-code-python')
    expect(view).toContain('os-py-kw')
    expect(view).toContain('def')
    expect(view).toContain('os-py-str')
  })

  it('REQ-127: user-bubble fences render as pre/code with newlines kept in source', () => {
    const source = '```python\nprint("hi")\nprint("there")\n```'
    const view = renderSafeMarkdown(source)
    expect(view).toContain('<pre')
    expect(view).toContain('<code')
    expect(view).toContain('language-python')
    expect(source).toContain('\n')
  })

  it('renders tables, blockquotes, hr, and links for themed chat-md chrome', () => {
    const view = renderSafeMarkdown(
      [
        '> quoted',
        '',
        '| Col | Val |',
        '| --- | --- |',
        '| a | 1 |',
        '',
        'See [docs](https://example.com/path)',
        '',
        '---',
      ].join('\n'),
    )
    expect(view).toContain('<blockquote>')
    expect(view).toContain('<table>')
    expect(view).toContain('<th>')
    expect(view).toContain('<td>')
    expect(view).toContain('<hr>')
    expect(view).toContain('href="https://example.com/path"')
  })

  it('REQ-868: Manage CLI markdown becomes an in-app settings href', () => {
    const view = renderSafeMarkdown(
      'Configure your installed CLIs in [Manage CLI](/chat?settings=cli-agents) (Settings → CLI Agents).',
    )
    expect(view).toContain('href="/chat?settings=cli-agents"')
    expect(view).toContain('Manage CLI')
  })
})
