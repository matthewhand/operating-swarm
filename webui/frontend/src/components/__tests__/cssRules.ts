/**
 * Parse `src/index.css` with PostCSS and expose the rules that target a
 * component's classes.
 *
 * Tests need to assert on *parsed CSS* rather than on source text: a literal
 * grep for `--waiting` passes on a comment and breaks on a reformat. This
 * walks the real AST, so a rule that exists in a comment or a string is
 * invisible to it, and a real rule that moved is still found.
 *
 * PostCSS ships with the Vite/Tailwind toolchain this project already uses, so
 * this adds no dependency.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import postcss, { type Declaration, type Rule, type AtRule } from 'postcss'

const HERE = dirname(fileURLToPath(import.meta.url))

export interface Decl {
  prop: string
  value: string
  important: boolean
}

export interface ParsedRules {
  /** Every selector the component's classes appear under. */
  selectors: Set<string>
  /** Declarations per selector, top level. */
  bySelector: Map<string, Decl[]>
  /** Declarations per selector, grouped by the @media condition wrapping them. */
  insideMedia: (condition: string) => Map<string, Decl[]>
}

function declsOf(rule: Rule): Decl[] {
  const out: Decl[] = []
  rule.walkDecls((decl: Declaration) => {
    out.push({ prop: decl.prop, value: decl.value, important: Boolean(decl.important) })
  })
  return out
}

function selectorList(rule: Rule): string[] {
  return rule.selectors.map((s) => s.trim())
}

function matches(selector: string, prefix: string): boolean {
  // Exact class match, or the class inside a compound/descendant selector such
  // as `html .os-herdr-status-dot--waiting` or `.a, .os-x`.
  return new RegExp(`(^|[\\s,>+~])\\.${prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w-])`).test(
    selector,
  )
}

export function parseComponentRules(
  cssPath: string,
  classNames: string[],
  mediaConditions: string[] = ['prefers-reduced-motion'],
): ParsedRules {
  const root = postcss.parse(readFileSync(cssPath, 'utf8'), { from: cssPath })
  const selectors = new Set<string>()
  const bySelector = new Map<string, Decl[]>()
  const byMedia = new Map<string, Map<string, Decl[]>>()
  for (const cond of mediaConditions) byMedia.set(cond, new Map())

  const bucket = (map: Map<string, Decl[]>, key: string, decls: Decl[]) => {
    const existing = map.get(key)
    if (existing) existing.push(...decls)
    else map.set(key, [...decls])
  }

  root.walkRules((rule: Rule) => {
    const names = selectorList(rule).filter((selector) =>
      classNames.some((name) => matches(selector, name)),
    )
    if (names.length === 0) return
    const decls = declsOf(rule)
    for (const name of names) {
      selectors.add(name)
      bucket(bySelector, name, decls)
    }
  })

  // @media blocks: the rules inside still belong to the same component, and
  // the reduced-motion guarantee lives there.
  root.walkAtRules('media', (at: AtRule) => {
    const condition = (at.params || '').trim()
    const target = [...byMedia.entries()].find(([key]) => condition.includes(key))
    if (!target) return
    at.walkRules((rule: Rule) => {
      const names = selectorList(rule).filter((selector) =>
        classNames.some((name) => matches(selector, name)),
      )
      if (names.length === 0) return
      const decls = declsOf(rule)
      for (const name of names) {
        selectors.add(name)
        bucket(target[1], name, decls)
      }
    })
  })

  return {
    selectors,
    bySelector,
    insideMedia: (condition: string) => byMedia.get(condition) ?? new Map(),
  }
}

/** The dot component's rules, straight out of the real stylesheet. */
export function parsedRules(): ParsedRules {
  return parseComponentRules(resolve(HERE, '../../index.css'), [
    'os-herdr-status-dot',
    'os-herdr-status-dot--waiting',
    'os-herdr-status-dot--finished',
    'os-herdr-status-dot__glyph',
  ])
}
