/**
 * #758 — IRC rows paint edge-to-edge like a terminal: the shaded line spans
 * the full transcript width across timestamp, <nickname> gutter, divider and
 * message text, with no unshaded islands and no row-width dependence on
 * content length. The bubble box itself stays transparent (flat IRC look).
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync(join(__dirname, '..', '..', 'index.css'), 'utf8')

const ircBlock = (selector: string) =>
  new RegExp(
    `\\.os-chat-transcript\\[data-bubble-theme="irc"\\][^{]*${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{[^}]*\\}`,
  )

describe('#758 IRC edge-to-edge row fill', () => {
  it('rows span the full transcript width regardless of content', () => {
    const block = css.match(ircBlock('.os-chat-row'))
    expect(block).toBeTruthy()
    expect(block![0]).toMatch(/width:\s*100%/)
  })

  it('hover and focus highlights live at ROW level (full line), not the bubble', () => {
    expect(css).toMatch(
      /\.os-chat-transcript\[data-bubble-theme="irc"\] \.os-chat-row:hover\s*\{[^}]*background:/,
    )
    expect(css).toMatch(
      /\.os-chat-transcript\[data-bubble-theme="irc"\] \.os-chat-row:focus-within\s*\{[^}]*background:/,
    )
  })

  it('the bubble box stays transparent — shading comes from the row', () => {
    const block = css.match(ircBlock('.chat-bubble'))
    expect(block).toBeTruthy()
    expect(block![0]).toMatch(/background-color:\s*transparent/)
  })

  it('row spacing stays tight so lines read as one continuous log', () => {
    const block = css.match(ircBlock('.os-chat-messages > * + *'))
    expect(block).toBeTruthy()
    expect(block![0]).toMatch(/margin-top:\s*0(?:\.0\d*)?rem/)
  })
})
