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
  PRE: new Set(['class']),
  SPAN: new Set(['class']),
  TD: new Set(['align']),
  TH: new Set(['align']),
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

  const el = doc.createElement(tag.toLowerCase())
  const allowed = ALLOWED_ATTRS[tag]
  if (allowed && elNode.attributes) {
    for (const attr of Array.from(elNode.attributes)) {
      const name = attr.name.toLowerCase()
      if (!allowed.has(name)) continue
      if ((name === 'href' || name === 'src') && !isSafeUrl(attr.value)) continue
      if (name.startsWith('on')) continue
      el.setAttribute(name, attr.value)
    }
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
