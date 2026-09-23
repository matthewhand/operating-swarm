import { describe, it, expect } from 'vitest'
import { escapeHtml, sanitizeMarkdownHtml } from '../htmlSafe'

describe('escapeHtml', () => {
  it('escapes angle brackets and ampersands', () => {
    expect(escapeHtml(`<script>alert("x")</script>`)).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
    )
  })
})

/* eslint-disable no-script-url */
describe('sanitizeMarkdownHtml', () => {
  it('keeps allowlisted formatting tags', () => {
    const out = sanitizeMarkdownHtml('<p>hi <strong>there</strong></p>')
    expect(out).toContain('<strong>there</strong>')
    expect(out).toContain('<p>')
  })

  it('strips script tags and event handlers', () => {
    const out = sanitizeMarkdownHtml(
      '<p onclick="evil()">ok</p><script>alert(1)</script>',
    )
    expect(out).not.toContain('script')
    expect(out).not.toContain('onclick')
    expect(out).toContain('ok')
  })

  it('blocks javascript: hrefs', () => {
    // eslint-disable-next-line no-script-url
    const jsString = '<a href="javascript:alert(1)">click</a><a href="https://example.com">safe</a>'
    const out = sanitizeMarkdownHtml(jsString)
    expect(out).not.toContain('javascript:')
    expect(out).toContain('https://example.com')
  })

  it('blocks javascript: hrefs smuggled with control characters', () => {
    // Browsers strip TAB/LF/CR before URL resolution, so these would become
    // live javascript: URLs if the sanitizer tested the raw value.
    for (const href of [
      'java\tscript:alert(1)',
      'jav\nascript:alert(1)',
      'jav\rascript:alert(1)',
      ' \t javascript:alert(1)',
    ]) {
      const out = sanitizeMarkdownHtml(`<a href="${href}">click</a>`)
      expect(out).not.toContain('alert(1)')
      expect(out).not.toContain('javascript')
    }
  })

  it('keeps relative and fragment links', () => {
    const out = sanitizeMarkdownHtml(
      '<a href="/docs">a</a><a href="#sec">b</a>',
    )
    expect(out).toContain('href="/docs"')
    expect(out).toContain('href="#sec"')
  })

  it('REQ-868: keeps in-app settings hrefs including settings: protocol', () => {
    const out = sanitizeMarkdownHtml(
      '<a href="/chat?settings=cli-agents">Manage CLI</a>' +
        '<a href="settings:cli-agents">pane</a>',
    )
    expect(out).toContain('href="/chat?settings=cli-agents"')
    expect(out).toContain('href="settings:cli-agents"')
  })
})
