import { describe, it, expect } from 'vitest'
import { escapeHtml, sanitizeInlineStyle, sanitizeMarkdownHtml } from '../htmlSafe'

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

  it('REQ-1320: keeps raster data-image and http(s)/same-origin image sources', () => {
    const png = 'data:image/png;base64,iVBORw0KGgo='
    const out = sanitizeMarkdownHtml(
      `<img src="${png}" alt="shot">` +
        '<img src="https://example.com/a.jpg" alt="remote">' +
        '<img src="/v1/chat/attachments/1/content" alt="local">',
    )
    expect(out).toContain(`src="${png}"`)
    expect(out).toContain('src="https://example.com/a.jpg"')
    expect(out).toContain('src="/v1/chat/attachments/1/content"')
    expect(out).toContain('class="os-msg-image"')
  })

  it('REQ-1320: drops javascript: image sources, event handlers, and the tag', () => {
    const out = sanitizeMarkdownHtml(
      '<img src="javascript:alert(1)" onerror="alert(2)" alt="x">',
    )
    expect(out).not.toContain('javascript:')
    expect(out).not.toContain('onerror')
    expect(out.toLowerCase()).not.toContain('<img')
  })

  it('#1322: drops data: and relative audio; keeps https and same-origin', () => {
    const out = sanitizeMarkdownHtml(
      '<audio src="data:audio/webm;base64,AAAA"></audio>' +
        '<audio src="../secret.webm"></audio>' +
        '<audio src="https://cdn.example/note.webm"></audio>',
    )
    expect(out).not.toContain('data:audio')
    expect(out).not.toContain('../secret')
    expect(out).toContain('src="https://cdn.example/note.webm"')
    expect(out.match(/<audio/g)?.length).toBe(1)
  })

  it('#1322: keeps same-origin audio and strips javascript: audio', () => {
    const out = sanitizeMarkdownHtml(
      '<audio src="/v1/chat/attachments/1/content" autoplay></audio>' +
        '<audio src="javascript:alert(1)"></audio>',
    )
    expect(out).toContain('src="/v1/chat/attachments/1/content"')
    expect(out).toContain('class="os-msg-audio"')
    expect(out).toContain('controls')
    expect(out).not.toContain('autoplay')
    expect(out).not.toContain('javascript:')
    expect(out.match(/<audio/g)?.length).toBe(1)
  })

  it('REQ-1320: drops SVG data URLs (script vector) but keeps raster data URLs', () => {
    const svg = 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4='
    const out = sanitizeMarkdownHtml(
      `<img src="${svg}" alt="s"><img src="data:image/gif;base64,R0lGOD" alt="g">`,
    )
    expect(out).not.toContain('svg')
    expect(out).toContain('data:image/gif;base64,R0lGOD')
  })

  it('REQ-1321: keeps KaTeX span classes/styles but strips unsafe ones', () => {
    const out = sanitizeMarkdownHtml(
      '<span class="katex" style="height:1em;margin-right:0.2778em;background:url(javascript:alert(1))">x</span>',
    )
    expect(out).toContain('class="katex"')
    expect(out).toContain('height:1em')
    expect(out).toContain('margin-right:0.2778em')
    expect(out).not.toContain('url(')
    expect(out).not.toContain('javascript:')
  })
})

describe('sanitizeInlineStyle (REQ-1321)', () => {
  it('keeps KaTeX metric declarations', () => {
    expect(sanitizeInlineStyle('height:0.8141em;margin-right:0.2778em;position:relative')).toBe(
      'height:0.8141em;margin-right:0.2778em;position:relative',
    )
    expect(sanitizeInlineStyle('color:#cc0000')).toBe('color:#cc0000')
  })

  it('drops url(), expression(), unknown props, and non-relative position', () => {
    expect(sanitizeInlineStyle('background:url(javascript:alert(1));color:red')).toBe('color:red')
    expect(sanitizeInlineStyle('width:expression(alert(1))')).toBe('')
    expect(sanitizeInlineStyle('behavior:url(#x)')).toBe('')
    expect(sanitizeInlineStyle('position:fixed;top:0')).toBe('top:0')
    expect(sanitizeInlineStyle('height:100vh;background-image:url(x)')).toBe('height:100vh')
  })
})
