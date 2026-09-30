/**
 * Escape / sanitize helpers for SPA chat markdown.
 * Port of rest_mode htmlSafe.js — allowlist after marked.parse (no DOMPurify).
 */

const ALLOWED_TAGS = new Set([
  'A',
  'B',
  'BLOCKQUOTE',
  'BR',
  'CODE',
  'DEL',
  'EM',
  'H1',
  'H2',
  'H3',
  'H4',
  'H5',
  'H6',
  'HR',
  'I',
  'AUDIO',
  'IMG',
  'LI',
  'OL',
  'P',
  'PRE',
  'S',
  'SPAN',
  'STRONG',
  'TABLE',
  'TBODY',
  'TD',
  'TH',
  'THEAD',
  'TR',
  'UL',
])

const ALLOWED_ATTRS: Record<string, Set<string>> = {
  A: new Set(['href', 'title']),
  CODE: new Set(['class']),
  AUDIO: new Set(['src', 'controls', 'preload', 'controlslist']),
  IMG: new Set(['src', 'alt', 'title']),
  PRE: new Set(['class']),
  // REQ-1321: KaTeX emits `<span class="…" style="…" aria-hidden="true">` for
  // layout/metrics. `style` is validated declaration-by-declaration below.
  SPAN: new Set(['class', 'style', 'aria-hidden', 'title']),
  TD: new Set(['align']),
  TH: new Set(['align']),
}

/**
 * REQ-1321: KaTeX inline styles use a small, fixed vocabulary (em-based metrics
 * and colors). Allow only properties KaTeX actually emits, with values that
 * cannot smuggle `url(...)`, `expression(...)`, or additional declarations.
 */
const SAFE_STYLE_PROPS = new Set([
  'background-color',
  'border-bottom-width',
  'border-color',
  'border-right-width',
  'border-style',
  'border-top-width',
  'border-width',
  'bottom',
  'color',
  'font-size',
  'height',
  'left',
  'line-height',
  'margin',
  'margin-bottom',
  'margin-left',
  'margin-right',
  'margin-top',
  'max-height',
  'max-width',
  'min-height',
  'min-width',
  'padding',
  'padding-bottom',
  'padding-left',
  'padding-right',
  'padding-top',
  'position',
  'right',
  'top',
  'vertical-align',
  'width',
])

// Numbers (optionally signed/decimal, optionally a length unit), hex colors,
// or bare keywords (`red`, `solid`, `currentColor`, `relative`). No parens,
// quotes, commas, backslashes, or extra `:`/`;` can reach a value.
const SAFE_STYLE_VALUE_RE =
  /^(?:-?(?:\d+|\d*\.\d+)(?:em|ex|pt|px|%|rem|ch|vh|vw)?|#[0-9a-f]{3,8}|[a-z]+)$/i

/** Return a sanitized subset of an inline `style` value (possibly empty). */
export function sanitizeInlineStyle(value: unknown): string {
  const out: string[] = []
  for (const declaration of String(value == null ? '' : value).split(';')) {
    const colon = declaration.indexOf(':')
    if (colon < 0) continue
    const prop = declaration.slice(0, colon).trim().toLowerCase()
    const val = declaration.slice(colon + 1).trim()
    if (!SAFE_STYLE_PROPS.has(prop)) continue
    if (!SAFE_STYLE_VALUE_RE.test(val)) continue
    // `position` is only ever used by KaTeX for `relative` vlist containers.
    if (prop === 'position' && val !== 'relative') continue
    out.push(`${prop}:${val}`)
  }
  return out.join(';')
}

/**
 * REQ-1320: image sources are stricter than link hrefs — a raster `data:` URL
 * or an `http(s)` / same-origin path. SVG data URLs (which can carry script)
 * and any other scheme (including `javascript:`) are rejected.
 */
const SAFE_RASTER_DATA_URL_RE =
  /^data:image\/(?:png|jpeg|gif|webp);base64,[a-z0-9+/=\s]+$/i

function isSafeImageUrl(value: string): boolean {
  // eslint-disable-next-line no-control-regex -- deliberate security normalization
  const raw = String(value || '').replace(/[\t\n\r\x00-\x1f\x7f]/g, '')
  const v = raw.trim()
  if (!v) return false
  if (SAFE_RASTER_DATA_URL_RE.test(v)) return true
  if (/^https?:\/\//i.test(v)) return true
  if (v.startsWith('/') || v.startsWith('./') || v.startsWith('../')) return true
  return false
}

/**
 * #1322: audio sources are same-origin paths or http(s) only.
 * `data:`, `javascript:`, and relative `./` / `../` are rejected. No autoplay.
 */
function isSafeAudioUrl(value: string): boolean {
  // eslint-disable-next-line no-control-regex -- deliberate security normalization
  const raw = String(value || '').replace(/[\t\n\r\x00-\x1f\x7f]/g, '')
  const v = raw.trim()
  if (!v) return false
  if (/^https?:\/\//i.test(v)) return true
  if (v.startsWith('/') && !v.startsWith('//')) return true
  return false
}

function isSafeSrc(tag: string, value: string): boolean {
  return tag === 'AUDIO' ? isSafeAudioUrl(value) : isSafeImageUrl(value)
}

/** Escape text for HTML element bodies. */
export function escapeHtml(text: unknown): string {
  return String(text == null ? '' : text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Escape text for HTML attribute values (double-quoted). */
export function escapeAttr(text: unknown): string {
  return escapeHtml(text)
}

function isSafeUrl(value: string): boolean {
  // Browsers strip TAB/LF/CR anywhere in a URL before resolution, so
  // "java\tscript:" would otherwise bypass scheme detection. Remove control
  // characters first and only then decide.
  // eslint-disable-next-line no-control-regex -- deliberate security normalization
  const raw = String(value || '').replace(/[\t\n\r\x00-\x1f\x7f]/g, '')
  const v = raw.trim()
  if (!v) return false
  if (/^(https?:|mailto:)/i.test(v)) return true
  // REQ-868: in-app Settings deep-link (`settings:cli-agents`).
  if (/^settings:[a-z0-9-]+$/i.test(v)) return true
  if (v.startsWith('/') || v.startsWith('#') || v.startsWith('./') || v.startsWith('../')) {
    return true
  }
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) return false
  return true
}

function sanitizeElement(node: ChildNode, doc: Document): Node | null {
  if (node.nodeType === Node.TEXT_NODE) {
    return doc.createTextNode(node.textContent ?? '')
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return null
  }

  const elNode = node as Element
  const tag = elNode.tagName.toUpperCase()
  const children = Array.from(elNode.childNodes)
    .map((child) => sanitizeElement(child, doc))
    .filter((c): c is Node => Boolean(c))

  if (!ALLOWED_TAGS.has(tag)) {
    const frag = doc.createDocumentFragment()
    children.forEach((c) => frag.appendChild(c))
    return frag
  }

  // REQ-1320 / #1322: media without a safe source is dropped entirely rather
  // than left as a broken/blank element (e.g. `javascript:` or SVG data URLs).
  if (tag === 'IMG' && !isSafeImageUrl(elNode.getAttribute('src') || '')) {
    return null
  }
  if (tag === 'AUDIO' && !isSafeAudioUrl(elNode.getAttribute('src') || '')) {
    return null
  }

  const el = doc.createElement(tag.toLowerCase())
  const allowed = ALLOWED_ATTRS[tag]
  if (allowed && elNode.attributes) {
    for (const attr of Array.from(elNode.attributes)) {
      const name = attr.name.toLowerCase()
      if (!allowed.has(name)) continue
      if (name === 'href' && !isSafeUrl(attr.value)) continue
      if (name === 'src' && !isSafeSrc(tag, attr.value)) continue
      if (name === 'style') {
        const safeStyle = sanitizeInlineStyle(attr.value)
        if (!safeStyle) continue
        el.setAttribute(name, safeStyle)
        continue
      }
      if (name.startsWith('on')) continue
      el.setAttribute(name, attr.value)
    }
  }
  if (tag === 'IMG') {
    // Force presentation/loading attributes; model-supplied classes are ignored.
    el.setAttribute('class', 'os-msg-image')
    el.setAttribute('loading', 'lazy')
    el.setAttribute('decoding', 'async')
    el.setAttribute('referrerpolicy', 'no-referrer')
  }
  if (tag === 'AUDIO') {
    // #1322: voice-note player. Controls only — never autoplay (not a call).
    el.setAttribute('class', 'os-msg-audio')
    el.setAttribute('controls', '')
    el.setAttribute('preload', 'metadata')
    el.setAttribute('controlslist', 'nodownload')
  }
  children.forEach((c) => el.appendChild(c))
  return el
}

/**
 * Sanitize HTML produced by markdown (marked.parse).
 * Drops scripts/event handlers and non-allowlisted tags; keeps basic formatting.
 */
export function sanitizeMarkdownHtml(html: unknown): string {
  const raw = String(html == null ? '' : html)
  if (!raw) return ''
  if (typeof DOMParser === 'undefined') {
    return escapeHtml(raw)
  }
  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div id="md-root">${raw}</div>`, 'text/html')
  const root = doc.getElementById('md-root')
  if (!root) return escapeHtml(raw)

  const out = doc.createElement('div')
  Array.from(root.childNodes).forEach((child) => {
    const clean = sanitizeElement(child, doc)
    if (clean) out.appendChild(clean)
  })
  return out.innerHTML
}
