import { marked } from 'marked'
import markedKatex from 'marked-katex-extension'
import 'katex/dist/katex.min.css'
import { escapeAttr, escapeHtml, sanitizeMarkdownHtml } from './htmlSafe'
import { highlightPython, isPythonFence } from './highlightPython'
import { isVoiceNoteMarkdown } from './voiceNotes'

marked.setOptions({ gfm: true, breaks: false })

/**
 * REQ-1321: render `$…$` / `$$…$$` LaTeX with KaTeX. Security posture:
 * - `throwOnError: false` — malformed math renders an inline error, never throws.
 * - `trust: false` — `\href`/`\url`/`\includegraphics` cannot emit live URLs.
 * - `strict: false` — untrusted TeX does not spam the console or fail hard.
 * - `output: 'html'` — no MathML/annotation branch, so raw TeX source never
 *   reaches the DOM as text; only the class/styled `<span>` tree is emitted.
 * The output is allowlist-sanitized afterwards by `sanitizeMarkdownHtml`.
 */
marked.use(
  markedKatex({
    throwOnError: false,
    strict: false,
    trust: false,
    output: 'html',
  }),
)

marked.use({
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      const language = String(lang || '').trim()
      const body = isPythonFence(language) ? highlightPython(text) : escapeHtml(text)
      const cls = language
        ? `language-${escapeHtml(language.split(/[\s{]/)[0] || '')}`
        : ''
      const extra = isPythonFence(language) ? ' os-code-python' : ''
      return `<pre class="os-code${extra}"><code class="${cls}">${body}</code></pre>`
    },
    image({ href, text }: { href: string; text?: string }) {
      const src = String(href || '')
      const alt = String(text || '')
      // #1322: voice-note markdown becomes a playable audio bubble.
      if (isVoiceNoteMarkdown(src, alt)) {
        return `<audio src="${escapeAttr(src)}"></audio>`
      }
      return `<img src="${escapeAttr(src)}" alt="${escapeAttr(alt)}" />`
    },
  },
})

/**
 * REQ-1320: tool/MCP/sandbox results often contain a bare raster `data:` image
 * URL with no markdown image syntax. Promote the standalone token to an
 * `<img>` so the transcript renders it inline. The sanitizer re-validates the
 * source, so this only affects presentation, never safety.
 */
const DATA_IMAGE_TOKEN_RE = /^data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+/i

marked.use({
  extensions: [
    {
      name: 'dataImage',
      level: 'inline',
      start(src: string) {
        const index = src.indexOf('data:image/')
        return index < 0 ? undefined : index
      },
      tokenizer(src: string) {
        const match = DATA_IMAGE_TOKEN_RE.exec(src)
        if (!match) return undefined
        return { type: 'dataImage', raw: match[0], href: match[0], text: '' }
      },
      renderer(token: Record<string, unknown>) {
        const src = String(token.href || token.raw || '')
        const alt = String(token.text || 'image')
        return `<img src="${escapeAttr(src)}" alt="${escapeAttr(alt)}" />`
      },
    },
  ],
})

/** Parse markdown then allowlist-sanitize for safe innerHTML. */
export function renderSafeMarkdown(source: string): string {
  const text = String(source ?? '')
  if (!text) return ''
  try {
    const parsed = marked.parse(text, { async: false })
    return sanitizeMarkdownHtml(typeof parsed === 'string' ? parsed : String(parsed))
  } catch {
    return escapeHtml(text)
  }
}
