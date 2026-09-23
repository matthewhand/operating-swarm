/**
 * #529 — navbar theme toggle is a strict light ↔ dark switch (no system).
 * #530/#773 — the navbar token meter was REMOVED: the composer badge is the
 * one canonical meter (two tallies with different sources disagreed).
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#530/#773 token meter centering (meter retired)', () => {
  it('ChatPage no longer renders a navbar token meter', () => {
    const src = readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8')
    expect(src.includes('data-testid="token-meter-button"')).toBe(false)
    expect(src.includes('os-chat-header__meter')).toBe(false)
  })

  it('the composer badge is the canonical meter', () => {
    const src = readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8')
    expect(src).toContain('ContextUsageBadge')
  })
})
