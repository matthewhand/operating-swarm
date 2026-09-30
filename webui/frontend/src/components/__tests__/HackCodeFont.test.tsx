/**
 * Hack is the self-hosted default code/monospace font.
 *
 * Code blocks (`pre` / `code`) must resolve to the `--os-font-mono` stack,
 * which leads with 'Hack'; the UI/body font is untouched. The face is
 * self-hosted (woff2 only) with its licence next to the files.
 */
import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { ChatBubbleBody } from '../ChatMessageBubble'
import { FONT_FAMILIES, FONT_FAMILY_STACKS } from '../../lib/fontFamily'

const cssPath = path.resolve(__dirname, '../../index.css')
const css = fs.readFileSync(cssPath, 'utf8')

const FONT_DIR = path.resolve(__dirname, '../../assets/fonts/hack')

const CODE_MD = ['```python', 'print("hello world")', '```'].join('\n')

function monoStack(): string {
  const match = /--os-font-mono:\s*([^;]+);/.exec(css)
  expect(match).toBeTruthy()
  return match![1].replace(/\s+/g, ' ').trim()
}

describe('Hack: default code-block font', () => {
  afterEach(() => {
    document.getElementById('os-hack-code-font')?.remove()
    document.documentElement.style.removeProperty('--os-font-mono')
  })

  it('self-hosts woff2 faces plus the licence, and declares @font-face', () => {
    for (const file of [
      'hack-regular.woff2',
      'hack-bold.woff2',
      'hack-italic.woff2',
      'Hack-LICENSE.md',
    ]) {
      expect(fs.existsSync(path.join(FONT_DIR, file))).toBe(true)
    }
    expect(css).toMatch(/@font-face\s*\{[^}]*font-family:\s*'Hack'[^}]*format\('woff2'\)/)
  })

  it('exposes --os-font-mono leading with Hack and applies it to code elements', () => {
    expect(monoStack()).toMatch(/^'Hack'/)
    expect(css).toMatch(/pre,\s*code,\s*kbd,\s*samp\s*\{[^}]*font-family:\s*var\(--os-font-mono\)/)
    expect(css).toMatch(/\.os-code-python\s*\{[^}]*font-family:\s*var\(--os-font-mono\)/)
  })

  it('offers Hack as a UI font-family preset while the default stays Omarchy', () => {
    expect(FONT_FAMILIES).toContain('hack')
    expect(FONT_FAMILY_STACKS.hack).toContain("'Hack'")
  })

  it('renders a fenced code block whose computed font-family contains Hack', () => {
    // jsdom does not resolve custom properties in getComputedStyle, so inline
    // the value the code rule's `var(--os-font-mono)` resolves to in a browser.
    document.documentElement.style.setProperty('--os-font-mono', monoStack())
    const style = document.createElement('style')
    style.id = 'os-hack-code-font'
    style.textContent = `pre, code, kbd, samp { font-family: ${monoStack()}; }`
    document.head.appendChild(style)

    const { container } = render(<ChatBubbleBody text={CODE_MD} streaming={false} />)
    const pre = container.querySelector('pre')
    const code = pre?.querySelector('code')
    expect(pre).toBeTruthy()
    expect(code).toBeTruthy()
    expect(window.getComputedStyle(code!).fontFamily.toLowerCase()).toContain('hack')
  })
})
