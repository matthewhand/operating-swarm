/**
 * #529 — navbar theme toggle is a strict light ↔ dark switch (no system).
 * #530 — the token meter is centered in the top navbar, not right-aligned.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function readCss(): string {
  return readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
}

describe('#530 token meter centering', () => {
  it('the meter carries the centered-meter class in the navbar', () => {
    const src = readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8')
    const button = src.split('data-testid="token-meter-button"')[0]
    expect(button).toContain('os-chat-header__meter')
  })

  it('the CSS centers the meter absolutely within the header row', () => {
    const css = readCss()
    const header = css.split('.os-chat-header {')[1]?.split('}')[0] ?? ''
    expect(header).toMatch(/position:\s*relative/)
    const meter = css.split('.os-chat-header__meter {')[1]?.split('}')[0] ?? ''
    expect(meter).toMatch(/position:\s*absolute/)
    expect(meter).toMatch(/left:\s*50%/)
    expect(meter).toMatch(/translateX\(-50%\)/)
  })

  it('the right-hand controls cluster no longer owns the meter class', () => {
    const src = readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8')
    const controls = src.split('os-chat-header__controls')[1]?.split('</div>')[0] ?? ''
    // The meter class must not be applied to anything inside the controls div.
    expect(controls.includes('os-chat-header__meter')).toBe(false)
  })
})
