/**
 * #1701 — the top navbar band is glass: a TRANSLUCENT theme-token tint plus a
 * `backdrop-filter`, with a legible fallback where the filter is unavailable.
 *
 * The point of the ticket is that `backdrop-filter` needs a translucent colour
 * to have anything to blur — a solid `--color-base-100` blurs nothing — so the
 * token and the filter are asserted TOGETHER, and the progressive-enhancement
 * fallback is asserted to restore an opaque surface.
 *
 * jsdom has no layout or compositing engine, so the geometry/compositing half
 * of this cannot be measured here (a real-renderer Playwright pass against the
 * BUILT stylesheet is the only honest check; the harness named in the issue
 * does not exist in this repo — see the report). What IS assertable without a
 * layout engine is read here: the parsed stylesheet, plus the fact that the
 * element carrying those declarations is the navbar the app actually renders.
 */
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type React from 'react'
import { ChatHeader } from '../../../features/chat/ChatHeader'
import { declarationIn, declarations, ruleBodies } from '../../../lib/__tests__/helpers/cssRules'

const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

const SUPPORTS_GUARD =
  '@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))'

/**
 * Custom properties, read from a BRACE-MATCHED rule body.
 *
 * `declarations()` deliberately rejects `--*` names (its property pattern is
 * for standard properties), and a whole-file regex would be exactly the
 * substring assertion this suite is removing — so the tokens are read out of
 * the one rule that declares them, like any other declaration.
 */
function customProps(body: string): Record<string, string> {
  const out: Record<string, string> = {}
  // Whitespace is normalised first, so a multi-line `color-mix(` value reads as
  // one declaration and a reformat is not a failure.
  const flat = body.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/\s+/g, ' ')
  for (const chunk of flat.split(';')) {
    const match = /^\s*(--[a-z0-9-]+)\s*:\s*(.+?)\s*$/i.exec(chunk)
    if (match) out[match[1]] = match[2].trim()
  }
  return out
}

/** The FIRST `.os-chat-header` rule is the band itself, not a nested media one. */
function headerDeclarations() {
  const body = ruleBodies(css, '.os-chat-header')[0] ?? ''
  expect(body).not.toBe('')
  return declarations(body)
}

function rootCustomProps() {
  return customProps(ruleBodies(css, ':root')[0] ?? '')
}

function lightThemeCustomProps() {
  const merged: Record<string, string> = {}
  for (const body of ruleBodies(css, '[data-theme="light"]')) {
    Object.assign(merged, customProps(body))
  }
  return merged
}

describe('#1701 the navbar band paints a translucent, theme-derived tint', () => {
  it('the tint is a color-mix of the theme base with transparent — not a solid base', () => {
    const root = rootCustomProps()
    const tint = root['--os-navbar-glass-tint']
    const bg = root['--os-navbar-glass-bg']
    expect(tint, 'a mix percentage token').toMatch(/^\d+(\.\d+)?%$/)
    expect(bg, 'the tint is mixed with transparent, so it has alpha to blur').toMatch(/color-mix\(/)
    expect(bg).toMatch(/var\(--color-base-100\)/)
    expect(bg).toMatch(/var\(--os-navbar-glass-tint\)/)
    expect(bg).toMatch(/transparent/)
    // The regression this ticket is about: a solid base-100 "glass" is a lie.
    expect(bg).not.toBe('var(--color-base-100)')
  })

  it('the band consumes the token and blurs it', () => {
    const header = headerDeclarations()
    expect(header['background']).toBe('var(--os-navbar-glass-bg)')
    expect(header['backdrop-filter']).toMatch(/blur\(var\(--os-navbar-glass-blur\)\)/)
    // Safari still needs the prefixed property, and it must carry the same
    // token rather than a second hard-coded radius.
    expect(header['-webkit-backdrop-filter']).toMatch(/blur\(var\(--os-navbar-glass-blur\)\)/)
    expect(header['backdrop-filter']).not.toMatch(/\d+px\s*\)/)
  })

  it('the band keeps the shared chrome geometry it already had', () => {
    const header = headerDeclarations()
    expect(header['height']).toBe('var(--os-top-chrome-h)')
    expect(header['align-items']).toBe('center')
    expect(header['border-bottom']).toBeTruthy()
  })

  it('the light theme raises the mix, because a dark-mode alpha loses contrast', () => {
    const darkMix = parseFloat(rootCustomProps()['--os-navbar-glass-tint'])
    const lightMix = parseFloat(lightThemeCustomProps()['--os-navbar-glass-tint'])
    expect(Number.isFinite(darkMix)).toBe(true)
    expect(Number.isFinite(lightMix)).toBe(true)
    expect(lightMix).toBeGreaterThan(darkMix)
  })
})

describe('#1701 glass is progressive, never a hard dependency', () => {
  it('an opaque surface is restored where backdrop-filter is unavailable', () => {
    expect(
      ruleBodies(css, SUPPORTS_GUARD).length,
      'the @supports guard exists',
    ).toBeGreaterThan(0)
    expect(
      declarationIn(css, '.os-chat-header', 'background', SUPPORTS_GUARD),
      'and it puts an opaque base behind the band',
    ).toBe('var(--color-base-100)')
  })

  it('the only motion is the tint transition, and reduced motion removes it', () => {
    const header = headerDeclarations()
    expect(header['transition']).toMatch(/background-color/)
    // No transform/animation/filter animation to gate — a blur is not motion,
    // but the transition is, so it has to answer prefers-reduced-motion.
    expect(header['animation']).toBeUndefined()
    const reduced = ruleBodies(css, '.os-chat-header')
    const reducedRule = reduced.find((body) => /transition:\s*none/.test(body))
    expect(reducedRule, 'a prefers-reduced-motion block cancels the transition').toBeTruthy()
  })
})

describe('#1701 the declarations belong to the navbar the app renders', () => {
  it('ChatHeader mounts the element those selectors target', () => {
    // Pass-through props, same shape the sibling ChatHeader suites use.
    const props = {
      AgentAvatar: () => <span />,
      ApiSessionSwitcher: () => null,
      AuxActivityIndicator: () => null,
      CliSessionSwitcher: () => null,
      ComputerControlStub: () => null,
      RemoteSessionSwitcher: () => null,
      Settings: () => <span />,
      Pencil: () => <span />,
      Folder: () => <span />,
      PanelLeft: () => <span />,
      ThemeToggle: () => <span />,
      GroupAvatar: () => <span />,
      roleCssClass: () => '',
      activeChatAgentId: 'a1',
      selectedAgent: { id: 'a1', name: 'Charles' },
      selectedAgentName: 'Charles',
      selectedBlueprint: 'a1',
      auxTasks: [],
      requestAuxCancel: vi.fn(),
      wsRef: { current: null },
      showEmptyRemoteChrome: false,
      showRemotesControl: false,
      activeRemoteId: null,
      configuredRemoteRows: [],
      selectedRemote: null,
      setSearchParams: vi.fn(),
      setGenerationsOpen: vi.fn(),
      cliRemoteSession: null,
    }
    const { container } = render(
      <ChatHeader {...(props as unknown as React.ComponentProps<typeof ChatHeader>)} />,
    )
    const header = container.querySelector('.os-chat-header')
    expect(header).toBeTruthy()
    expect(header?.tagName).toBe('HEADER')
    // The band is the one the glass rule styles — the same class, one element,
    // so the stylesheet cannot be describing a surface the app never mounts.
    expect(container.querySelectorAll('.os-chat-header')).toHaveLength(1)
  })
})
