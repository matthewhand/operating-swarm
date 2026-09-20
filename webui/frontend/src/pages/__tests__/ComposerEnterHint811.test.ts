/**
 * #811 — the composer's ↵ reveal must require a *reason to submit*.
 *
 * The #732 permanently-mounted hint slot kept a legacy CSS rule alive:
 * `.os-composer:hover .os-composer__hint { opacity: 1 }` revealed EVERY hint,
 * including the aria-hidden placeholder — so hovering an EMPTY composer with
 * no queue showed `↵` even though Enter does nothing. Reveal is now
 * testid-scoped: only the send (queued) and clear (draft) hints light up, and
 * only on hover/focus-within. The placeholder stays invisible always.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const css = () => readFileSync(join(__dirname, '..', '..', 'index.css'), 'utf8')

describe('#811 enter hint needs a reason to submit', () => {
  it('the legacy reveal-everything rule is gone', () => {
    expect(css()).not.toMatch(/\.os-composer:hover \.os-composer__hint\b[^[]*\{\s*opacity: 1/)
  })

  it('only the queued-send and draft-clear hints are revealed on hover/focus', () => {
    const text = css()
    for (const testid of ['composer-send-hint', 'composer-clear-hint']) {
      expect(text).toMatch(new RegExp(`data-testid='${testid}'`))
    }
    // The placeholder never appears in any reveal selector.
    const revealBlock = text.slice(text.indexOf('.os-composer:hover .os-composer__hint-slot'))
    expect(revealBlock).not.toMatch(/composer-hint-placeholder/)
  })
})
