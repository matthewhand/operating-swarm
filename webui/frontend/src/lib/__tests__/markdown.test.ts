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

  it('REQ-1320: renders markdown images as inline os-msg-image', () => {
    const view = renderSafeMarkdown('![shot](/v1/chat/attachments/9/content)')
    expect(view).toContain('<img')
    expect(view).toContain('class="os-msg-image"')
    expect(view).toContain('src="/v1/chat/attachments/9/content"')
    expect(view).toContain('alt="shot"')
  })

  it('REQ-1320: promotes a bare raster data URL to an inline image', () => {
    const data = 'data:image/png;base64,iVBORw0KGgo='
    const view = renderSafeMarkdown(`screenshot:\n\n${data}`)
    expect(view).toContain('<img')
    expect(view).toContain(`src="${data}"`)
  })

  it('#1322: Voice note markdown renders as os-msg-audio, not an image', () => {
    const view = renderSafeMarkdown('![Voice note](/v1/chat/attachments/9/content)')
    expect(view).toContain('<audio')
    expect(view).toContain('class="os-msg-audio"')
    expect(view).toContain('src="/v1/chat/attachments/9/content"')
    expect(view).toContain('controls')
    expect(view.toLowerCase()).not.toContain('<img')
  })

  it('REQ-1320: strips javascript: image URLs from markdown', () => {
    const view = renderSafeMarkdown('![x](javascript:alert(1))')
    expect(view).not.toContain('javascript:')
    expect(view.toLowerCase()).not.toContain('<img')
  })

  it('REQ-1321: renders inline $…$ as KaTeX', () => {
    const view = renderSafeMarkdown('$E=mc^2$')
    expect(view).toContain('class="katex"')
    expect(view).not.toContain('$E=mc^2$')
    expect(view).not.toContain('katex-error')
  })

  it('REQ-1321: renders display $$…$$ as katex-display', () => {
    const view = renderSafeMarkdown('$$\\int_0^1 x\\,dx$$')
    expect(view).toContain('katex-display')
    expect(view).not.toContain('\\int_0^1')
  })

  it('REQ-1321: leaves $ literal inside inline code and fenced code', () => {
    const inline = renderSafeMarkdown('use `$x$` here')
    expect(inline).toContain('$x$')
    expect(inline).not.toContain('class="katex"')

    const fenced = renderSafeMarkdown('```\n$y=1$\n```')
    expect(fenced).toContain('$y=1$')
    expect(fenced).not.toContain('class="katex"')
  })

  it('REQ-1321: malformed LaTeX does not throw and renders an error node', () => {
    const source = '$\\frac{1}{$'
    expect(() => renderSafeMarkdown(source)).not.toThrow()
    expect(renderSafeMarkdown(source)).toContain('katex-error')
  })

  it('REQ-1321 security: \\href and raw HTML cannot inject links/scripts', () => {
    const href = renderSafeMarkdown('$\\href{javascript:alert(1)}{x}$')
    expect(href).not.toContain('<a ')
    expect(href).not.toContain('href=')
    expect(href).not.toContain('<script')

    const raw = renderSafeMarkdown('$$<img src=x onerror=alert(1)>$$')
    expect(raw).not.toContain('onerror')
    expect(raw.toLowerCase()).not.toContain('<img')
  })
})
