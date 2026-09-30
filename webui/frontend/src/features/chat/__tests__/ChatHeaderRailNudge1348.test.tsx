/**
 * #1348 — the navbar expand/collapse affordance (the fully-collapsed rail's
 * "expand" pill that rides immediately left of the header avatar) must nudge
 * the agent avatar + label clear of it.
 *
 * The nudge is CSS-native (the rail's collapsed state and the chat header are
 * siblings under the themed layout root, so `:has()` scopes it without prop
 * plumbing). These tests pin the contract: the identity shifts when the rail is
 * collapsed, shifts further on affordance hover, never applies in the
 * narrow/mobile drawer, and is suppressed under reduced motion.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const css = fs.readFileSync(path.resolve(__dirname, '../../../index.css'), 'utf8')

describe('#1348 — the collapsed-rail affordance nudges the header identity', () => {
  it('shifts the identity clear of the collapsed rail affordance', () => {
    const rule = css.match(
      /\[data-theme\]:not\(\[data-narrow-viewport='true'\]\):has\(\.os-agent-sidebar--collapsed\)\s+\.os-chat-header__identity\s*\{([^}]+)\}/,
    )
    expect(rule).toBeTruthy()
    expect(rule![1]).toMatch(/transform:\s*translateX\(2\.25rem\)/)
  })

  it('nudges a little further while the affordance is hovered', () => {
    const rule = css.match(
      /\[data-theme\]:not\(\[data-narrow-viewport='true'\]\):has\(\.os-rail-collapsed-expand:hover\)\s+\.os-chat-header__identity\s*\{([^}]+)\}/,
    )
    expect(rule).toBeTruthy()
    expect(rule![1]).toMatch(/transform:\s*translateX\(2\.5rem\)/)
  })

  it('never nudges on a narrow viewport where the rail is a fixed drawer', () => {
    // Both nudge rules carry the :not([data-narrow-viewport='true']) guard.
    const nudges = css.match(
      /\[data-theme\][^\n]*:has\(\.os-(?:agent-sidebar--collapsed|rail-collapsed-expand:hover)\)[^\n]*\.os-chat-header__identity/g,
    )
    expect(nudges?.length).toBe(2)
    for (const selector of nudges!) {
      expect(selector).toContain(":not([data-narrow-viewport='true'])")
    }
  })

  it('suppresses the slide under prefers-reduced-motion', () => {
    const blocks = [...css.matchAll(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\n\}/g)].map(
      (m) => m[1],
    )
    const ours = blocks.find((block) => block.includes('.os-chat-header__identity'))
    expect(ours).toBeTruthy()
    expect(ours!).toMatch(/\.os-chat-header__identity\s*\{\s*transition:\s*none/)
  })
})