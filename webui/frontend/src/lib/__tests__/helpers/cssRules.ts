/**
 * Parsed CSS rule reads for the properties that really do live in a stylesheet.
 *
 * A TS port of `tests/helpers/css_rules.py`, so the frontend suite gets the same
 * guarantee the python suite already relies on.
 *
 * Why this exists
 * ---------------
 * `expect(css).toContain('opacity: 0;')` over a 6,400-line `index.css` is the
 * canonical rotted assertion in this repo. It breaks when the rule is re-tuned
 * (formatting, spacing, a different container) even though the behaviour is
 * intact, and it passes when the same declaration appears under some unrelated
 * selector — `index.css` declares `opacity: 1` in several rules, so a bare
 * needle cannot tell the navbar pencil's from any other.
 *
 * `ruleBodies` brace-matches each rule body, so nested `@media` / `@container`
 * / `@keyframes` blocks are read whole rather than truncated at the first `}`.
 * `declarations` normalises whitespace, so a reformat is not a failure while a
 * different *value* still is.
 *
 * The selector must be a whole compound in the prelude: only whitespace then
 * `{` (or `,` for a grouped selector) may follow. That is what rejects
 * `.os-fav-tile` matching inside `.os-fav-tile .os-stacked-avatars`,
 * `.os-fav-tile:hover` and `.os-fav-grid--active` — three different rules that
 * a substring would all satisfy.
 */

const AT_RULE = /@[\w-]+/

/** Every brace-matched body whose prelude ends with `selector`, in source order. */
function balancedBodies(css: string, selector: string): string[] {
  const out: string[] = []
  let from = 0
  for (;;) {
    const at = css.indexOf(selector, from)
    if (at === -1) break
    from = at + selector.length
    const open = css.indexOf('{', at)
    if (open === -1) break
    // the selector must be a whole compound in its prelude
    let tail = css.indexOf(selector, at) + selector.length
    while (tail < css.length && (css[tail] === ' ' || css[tail] === '\t' || css[tail] === '\r' || css[tail] === '\n')) {
      tail += 1
    }
    if (tail >= css.length || (css[tail] !== '{' && css[tail] !== ',')) continue
    const close = matchingBrace(css, open)
    if (close === -1) continue
    out.push(css.slice(open + 1, close))
  }
  return out
}

function matchingBrace(css: string, openAt: number): number {
  let depth = 0
  for (let i = openAt; i < css.length; i += 1) {
    const char = css[i]
    if (char === '{') depth += 1
    else if (char === '}') {
      depth -= 1
      if (depth === 0) return i
    }
  }
  return -1
}

/** All bodies for `selector`, in source order (a repeated selector gives many). */
export function ruleBodies(css: string, selector: string): string[] {
  return balancedBodies(css, selector)
}

/** The first body for `selector`, or `''`. */
export function rule(css: string, selector: string): string {
  return balancedBodies(css, selector)[0] ?? ''
}

/**
 * `{'white-space': 'pre-wrap'}` for a rule body, comments stripped.
 *
 * Chunks containing a brace are skipped: a body taken from an at-rule still
 * holds the nested rule's selector text, and a pseudo-class in that selector
 * would otherwise parse as a declaration whose property is `html`.
 */
export function declarations(body: string): Record<string, string> {
  const flat = body.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/\s+/g, ' ')
  const out: Record<string, string> = {}
  for (const decl of flat.split(';')) {
    if (!decl.includes(':') || decl.includes('{')) continue
    const idx = decl.indexOf(':')
    const prop = decl.slice(0, idx).trim().toLowerCase()
    if (!/^-?[a-z][a-z0-9-]*$/.test(prop)) continue
    out[prop] = decl.slice(idx + 1).trim()
  }
  return out
}

/**
 * The value `prop` takes in the *first* body for `selector`.
 *
 * `undefined` when the rule or the declaration is absent, so callers can assert
 * on the absence explicitly rather than on a substring not appearing.
 */
export function declaration(css: string, selector: string, prop: string): string | undefined {
  const body = rule(css, selector)
  if (!body) return undefined
  return declarations(body)[prop.toLowerCase()]
}

/**
 * `prop` on the rule for `selector` inside the body of `within`.
 *
 * For nested rules — a `prefers-reduced-motion` block that carries a media
 * guard on every one of its selectors.
 */
export function declarationIn(
  css: string,
  selector: string,
  prop: string,
  within: string,
): string | undefined {
  for (const body of balancedBodies(css, within)) {
    for (const inner of balancedBodies(body, selector)) {
      const value = declarations(inner)[prop.toLowerCase()]
      if (value !== undefined) return value
    }
  }
  return undefined
}

/** Every selector/at-rule prelude in the sheet, in source order. */
export function selectors(css: string): string[] {
  const out: string[] = []
  const re = /([^{}]+)\{/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) {
    const prelude = m[1].trim()
    if (prelude) out.push(prelude)
  }
  return out
}

export { AT_RULE }

/**
 * Read the app stylesheet.
 *
 * `src/lib/__tests__/helpers/` is three levels below `src/`, so the sheet is
 * `../../../index.css` from here. Exported as a function rather than a
 * module-level constant so a test can re-read after a fixture rewrites it.
 */
export function readCssSource(): string {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const fs = require('fs') as typeof import('fs')
  const path = require('path') as typeof import('path')
  return fs.readFileSync(path.resolve(__dirname, '../../../index.css'), 'utf8')
}

