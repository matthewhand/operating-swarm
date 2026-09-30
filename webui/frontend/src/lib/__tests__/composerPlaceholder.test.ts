/**
 * #1372 — empty composer placeholder is `Message <display name>`.
 */
import { describe, expect, it } from 'vitest'
import {
  COMPOSER_PLACEHOLDER_FALLBACK,
  COMPOSER_REPLY_PLACEHOLDER,
  composerEmptyPlaceholder,
  usableComposerDisplayName,
} from '../composerPlaceholder'

describe('#1372 composerEmptyPlaceholder', () => {
  it('uses a fake agent display name exactly as Message <name>', () => {
    expect(composerEmptyPlaceholder('Ada Lovelace')).toBe('Message Ada Lovelace')
  })

  it('trims surrounding whitespace on the display name', () => {
    expect(composerEmptyPlaceholder('  Codey  ')).toBe('Message Codey')
  })

  it.each([
    [undefined],
    [null],
    [''],
    ['   '],
    ['undefined'],
    ['null'],
    [0],
  ])('falls back for missing/unusable name %j (never Message undefined/null)', (name) => {
    expect(composerEmptyPlaceholder(name)).toBe(COMPOSER_PLACEHOLDER_FALLBACK)
    expect(composerEmptyPlaceholder(name)).not.toMatch(/undefined|null/)
    expect(usableComposerDisplayName(name)).toBeNull()
  })

  it('keeps the Reply… placeholder while a reply is armed', () => {
    expect(composerEmptyPlaceholder('Ada Lovelace', { reply: true })).toBe(
      COMPOSER_REPLY_PLACEHOLDER,
    )
    expect(composerEmptyPlaceholder('', { reply: true })).toBe(COMPOSER_REPLY_PLACEHOLDER)
  })
})
