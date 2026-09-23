/**
 * Markdown-safe partial rendering for optional streaming (#220).
 *
 * Naive re-render of each SSE/WS chunk flashes unclosed `**`, `*`, `` ` ``,
 * fences, and links. This helper returns only the balanced prefix; the tail
 * stays buffered until closers arrive or the stream ends (`complete: true`).
 *
 * Invariant: `visible + held === source` (never drops text).
 */

export interface MarkdownSafePartial {
  visible: string
  held: string
}

export interface MarkdownSafeOptions {
  /** When true (generation ended), flush the held tail as-is. */
  complete?: boolean
}

type Kind =
  | 'strong-star'
  | 'em-star'
  | 'strong-under'
  | 'em-under'
  | 'code'
  | 'fence'
  | 'link'
  | 'linkdest'

interface Frame {
  kind: Kind
  start: number
  ticks?: number
  fenceChar?: string
  fenceLen?: number
}

function countRun(src: string, i: number, ch: string): number {
  let n = 0
  while (i + n < src.length && src[i + n] === ch) n++
  return n
}

function isLineStart(src: string, i: number): boolean {
  return i === 0 || src[i - 1] === '\n'
}

function matchFenceClose(
  src: string,
  i: number,
  fenceChar: string,
  fenceLen: number,
): number {
  let j = i
  let spaces = 0
  while (j < src.length && src[j] === ' ' && spaces < 3) {
    j++
    spaces++
  }
  if (j >= src.length || src[j] !== fenceChar) return -1
  const run = countRun(src, j, fenceChar)
  if (run < fenceLen) return -1
  j += run
  while (j < src.length && (src[j] === ' ' || src[j] === '\t')) j++
  if (j === src.length || src[j] === '\n') {
    return j < src.length ? j + 1 : j
  }
  return -1
}

function popKind(stack: Frame[], kind: Kind): boolean {
  for (let s = stack.length - 1; s >= 0; s--) {
    if (stack[s].kind === kind) {
      stack.splice(s, 1)
      return true
    }
  }
  return false
}

function oddTrailingBackslash(src: string): number {
  const n = src.length
  if (n === 0 || src[n - 1] !== '\\') return n
  let k = n - 1
  while (k >= 0 && src[k] === '\\') k--
  const count = n - 1 - k
  return count % 2 === 1 ? n - 1 : n
}

function firstHeldIndex(src: string): number {
  const n = src.length
  const stack: Frame[] = []
  let i = 0

  const top = (): Frame | undefined => stack[stack.length - 1]

  while (i < n) {
    const ch = src[i]
    const t = top()

    if (t?.kind === 'fence') {
      if (isLineStart(src, i)) {
        const close = matchFenceClose(src, i, t.fenceChar!, t.fenceLen!)
        if (close >= 0) {
          stack.pop()
          i = close
          continue
        }
      }
      i++
      continue
    }

    if (t?.kind === 'code') {
      if (ch === '`') {
        const run = countRun(src, i, '`')
        if (run === t.ticks) {
          stack.pop()
          i += run
          continue
        }
      }
      i++
      continue
    }

    if (t?.kind === 'linkdest') {
      if (ch === ')') {
        stack.pop()
        i++
        continue
      }
      i++
      continue
    }

    if (ch === '\\' && i + 1 < n) {
      i += 2
      continue
    }

    if (isLineStart(src, i)) {
      let j = i
      let spaces = 0
      while (j < n && src[j] === ' ' && spaces < 3) {
        j++
        spaces++
      }
      if (j < n && (src[j] === '`' || src[j] === '~')) {
        const fenceChar = src[j]
        const run = countRun(src, j, fenceChar)
        if (run >= 3) {
          let k = j + run
          while (k < n && src[k] !== '\n') k++
          stack.push({ kind: 'fence', start: i, fenceChar, fenceLen: run })
          i = k < n ? k + 1 : k
          continue
        }
        if (fenceChar === '~' && j + run === n) {
          stack.push({ kind: 'fence', start: i, fenceChar, fenceLen: 3 })
          break
        }
      }
    }

    if (ch === '`') {
      const run = countRun(src, i, '`')
      stack.push({ kind: 'code', start: i, ticks: run })
      i += run
      continue
    }

    if (ch === '!' && i + 1 < n && src[i + 1] === '[') {
      stack.push({ kind: 'link', start: i })
      i += 2
      continue
    }
    if (ch === '[') {
      stack.push({ kind: 'link', start: i })
      i++
      continue
    }
    if (ch === ']' && t?.kind === 'link') {
      if (i + 1 < n && src[i + 1] === '(') {
        t.kind = 'linkdest'
        i += 2
        continue
      }
      stack.pop()
      i++
      continue
    }

    if (ch === '*' || ch === '_') {
      const run = countRun(src, i, ch)
      if (
        isLineStart(src, i) &&
        ch === '*' &&
        run === 1 &&
        (i + 1 >= n || src[i + 1] === ' ' || src[i + 1] === '\t')
      ) {
        i++
        continue
      }
      let remaining = run
      let pos = i
      const strongKind: Kind = ch === '*' ? 'strong-star' : 'strong-under'
      const emKind: Kind = ch === '*' ? 'em-star' : 'em-under'
      const prev = i > 0 ? src[i - 1] : ''
      const canClose = prev !== '' && prev !== ' ' && prev !== '\t' && prev !== '\n'
      const next = i + run < n ? src[i + run] : ''
      const canOpen = next !== ' ' && next !== '\t' && next !== '\n'
      const openAtEos = next === ''

      while (remaining > 0) {
        if (remaining >= 2 && canClose && popKind(stack, strongKind)) {
          remaining -= 2
          pos += 2
          continue
        }
        if (remaining >= 1 && canClose && popKind(stack, emKind)) {
          remaining -= 1
          pos += 1
          continue
        }
        if (remaining >= 2 && (canOpen || openAtEos)) {
          stack.push({ kind: strongKind, start: pos })
          remaining -= 2
          pos += 2
          continue
        }
        if (remaining >= 1 && (canOpen || openAtEos)) {
          stack.push({ kind: emKind, start: pos })
          remaining -= 1
          pos += 1
          continue
        }
        remaining -= 1
        pos += 1
      }
      i += run
      continue
    }

    i++
  }

  let cut = n
  if (stack.length > 0) cut = Math.min(cut, stack[0].start)
  cut = Math.min(cut, oddTrailingBackslash(src))
  return cut
}

/** Split `source` into a renderable prefix and a held tail. */
export function markdownSafePartial(
  source: string,
  options?: MarkdownSafeOptions,
): MarkdownSafePartial {
  const text = String(source ?? '')
  if (!text) return { visible: '', held: '' }
  if (options?.complete) return { visible: text, held: '' }
  const cut = firstHeldIndex(text)
  if (cut >= text.length) return { visible: text, held: '' }
  if (cut <= 0) return { visible: '', held: text }
  return { visible: text.slice(0, cut), held: text.slice(cut) }
}

/**
 * Safe prefix of a (possibly incomplete) markdown stream.
 * Pass `{ complete: true }` at generation end to flush the remainder.
 */
export function renderMarkdownSafe(source: string, options?: MarkdownSafeOptions): string {
  return markdownSafePartial(source, options).visible
}
