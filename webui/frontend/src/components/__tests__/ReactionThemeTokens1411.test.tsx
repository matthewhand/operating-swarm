import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

describe('#1411 reaction light/dark theme tokens', () => {
  it('defines distinct light and dark reaction tokens', () => {
    expect(css).toContain('--os-reaction-bg: #2a2a2a')
    expect(css).toContain('--os-reaction-fg: #f4f4f5')
    const light = css.match(/\[data-theme="light"\]\s*\{([^}]+)\}/)
    expect(light?.[1]).toContain('--os-reaction-bg: #f4f4f5')
    expect(light?.[1]).toContain('--os-reaction-fg: #27272a')
    expect(light?.[1]).not.toContain('--os-reaction-bg: #2a2a2a')
  })

  it('paints pills and reaction-only bubbles from the tokens', () => {
    expect(css).toMatch(/\.os-reaction-pill\.badge\s*\{[^}]*var\(--os-reaction-bg\)/)
    expect(css).toMatch(/data-user-reacted="true"/)
    expect(css).toContain('var(--os-reaction-own-bg)')
    expect(css).toContain('.os-reaction-only-bubble')
    expect(css).toContain('var(--os-reaction-fg)')
    expect(css).toMatch(/\.os-reaction-only \.os-message-reactions\s*\{[^}]*opacity:\s*1 !important/)
    expect(css).toMatch(/\.os-reaction-only \.os-reaction-pill\.badge\s*\{[^}]*opacity:\s*1 !important/)
  })
})
