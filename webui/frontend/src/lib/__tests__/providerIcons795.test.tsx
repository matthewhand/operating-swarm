/**
 * #795 — the composer routing pill is an icon button on mobile.
 *
 * On narrow viewports the joined text pill (`provider/model/effort`) ate
 * ~120px of a ~360px composer row. The pill now carries a provider icon
 * from one registry (`providerIcons.tsx`); on mobile the label+chevron are
 * hidden and the pill collapses to a compact circle around the icon. The
 * accessible name and title keep the full label for screen readers and
 * desktop hover.
 */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { getProviderIcon, providerIconKey } from '../providerIcons'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#795 provider icon registry', () => {
  it('maps every declared remote kind to a stable icon key', () => {
    const kinds = [
      'hermes',
      'anythingllm',
      'letta',
      'openwebui',
      'flowise',
      'n8n',
      'omb',
      'openmousbot',
      'openmausbot',
      'rakazo',
      'herdr',
      'swarm',
      'trueforge',
    ]
    for (const kind of kinds) {
      const key = providerIconKey({ seatKind: 'remote', providerId: kind })
      expect(key, `${kind} should resolve`).toBeTruthy()
    }
  })

  it('maps common LLM providers', () => {
    for (const provider of [
      'anthropic',
      'openai',
      'google',
      'gemini',
      'ollama',
      'groq',
      'mistral',
      'openrouter',
      'deepseek',
    ]) {
      expect(
        providerIconKey({ seatKind: 'api', providerId: provider }),
      ).toBeTruthy()
    }
  })

  it('infers the provider from the model id when the provider id is generic', () => {
    expect(providerIconKey({ seatKind: 'api', providerId: '', modelId: 'claude-3-5-sonnet' })).toBe('anthropic')
    expect(providerIconKey({ seatKind: 'api', providerId: '', modelId: 'gpt-4o' })).toBe('openai')
    expect(providerIconKey({ seatKind: 'api', providerId: '', modelId: 'gemini-2.0' })).toBe('google')
    expect(providerIconKey({ seatKind: 'api', providerId: '', modelId: 'llama3:8b' })).toBe('ollama')
  })

  it('has kind fallbacks: team, cli, api, and a last-resort icon', () => {
    expect(providerIconKey({ seatKind: 'team' })).toBe('team')
    expect(providerIconKey({ seatKind: 'cli', providerId: 'grok' })).toBeTruthy()
    expect(providerIconKey({ seatKind: 'api' })).toBe('api')
    expect(providerIconKey({ seatKind: 'api', providerId: 'unknown-thing' })).toBe('api')
  })

  it('getProviderIcon renders an svg with the icon key stamped', () => {
    const { container } = render(
      getProviderIcon({ seatKind: 'remote', providerId: 'herdr', className: 'w-4 h-4' }),
    )
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(svg?.getAttribute('data-provider-icon')).toBe('herdr')
    expect(svg?.getAttribute('class')).toContain('w-4 h-4')
  })
})

describe('#795 mobile icon-button pill', () => {
  const css = readFileSync(
    join(__dirname, '..', '..', 'index.css'),
    'utf8',
  )

  it('the composer pill collapses to an icon circle on narrow viewports', () => {
    expect(css).toMatch(/@media \(max-width: 40rem\)[^}]*\{[\s\S]*?\.os-composer \.os-routing-pill \{/)
    expect(css).toMatch(/\.os-composer \.os-routing-pill \{[^}]*border-radius: 9999px[^}]*\}/)
  })

  it('the label and chevron are hidden on mobile, the icon shown', () => {
    // Pull just the #795 media block (delimited by the blank line after it).
    const start = css.indexOf('@media (max-width: 40rem) {')
    expect(start).toBeGreaterThan(-1)
    const mobileBlock = css.slice(start, css.indexOf('\n}\n', start))
    expect(mobileBlock).toContain('.os-routing-pill__label')
    expect(mobileBlock).toMatch(/display:\s*none/)
    expect(mobileBlock).toContain('.os-routing-pill__icon')
  })

  it('the pill source renders the icon span and keeps aria naming', () => {
    const src = readFileSync(
      join(__dirname, '..', '..', 'components', 'NavbarRoutingPicker.tsx'),
      'utf8',
    )
    expect(src).toContain('os-routing-pill__icon')
    expect(src).toMatch(/getProviderIcon\(/)
    // Accessibility: the full label survives as aria-label/title on mobile.
    expect(src).toMatch(/aria-label=\{/)
    expect(src).toMatch(/title=\{/)
  })
})
