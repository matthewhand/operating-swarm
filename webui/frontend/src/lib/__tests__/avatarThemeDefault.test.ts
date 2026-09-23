/**
 * #563 — "Apply to all agents" must mean what it says.
 *
 * A persisted default-theme choice (`mixed` = today's REQ-842 deal, or a
 * specific family) sits beside the installed-theme set. Apply acts on the
 * choice; reshuffling moves to its own action. `mixed` remains the default so
 * an existing install keeps its distribution on upgrade.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  AVATAR_DEFAULT_THEME_KEY,
  AVATAR_THEMES_ENABLED_KEY,
  DEFAULT_AVATAR_THEME_CHOICE,
  loadAvatarThemeChoice,
  saveAvatarThemeChoice,
} from '../avatarTheme'
import { applyAvatarThemeChoice } from '../agent-utils'

describe('avatar theme default choice (#563)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.removeItem(AVATAR_DEFAULT_THEME_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
  })

  it('defaults to mixed/rotate so upgrades keep REQ-842 behaviour', () => {
    expect(loadAvatarThemeChoice()).toBe(DEFAULT_AVATAR_THEME_CHOICE)
    expect(DEFAULT_AVATAR_THEME_CHOICE).toBe('mixed')
  })

  it('persists an explicit default theme choice', () => {
    expect(saveAvatarThemeChoice('bee').choice).toBe('bee')
    expect(loadAvatarThemeChoice()).toBe('bee')
    localStorage.removeItem(AVATAR_DEFAULT_THEME_KEY)
    expect(loadAvatarThemeChoice()).toBe('mixed')
  })

  it('round-trips the choice back to mixed when reset', () => {
    saveAvatarThemeChoice('bee')
    saveAvatarThemeChoice('mixed')
    expect(loadAvatarThemeChoice()).toBe('mixed')
  })

  it('Apply with a specific choice stamps every agent with that family', () => {
    const { themes } = applyAvatarThemeChoice(['a', 'b', 'c'], 'bee', ['blobs', 'bee'])
    expect(themes['a']).toBe('bee')
    expect(themes['b']).toBe('bee')
    expect(themes['c']).toBe('bee')
  })

  it('Apply with mixed preserves the shuffle (unique looks from the installed set)', () => {
    const ids = ['a', 'b', 'c', 'd']
    const { themes, eyes } = applyAvatarThemeChoice(ids, 'mixed', ['blobs', 'bee'])
    for (const id of ids) {
      expect(themes[id]).toBeTruthy()
      expect(eyes[id]).toBeTruthy()
    }
  })

  it('a deterministic random still produces the whole stamp under mixed', () => {
    const ids = Array.from({ length: 12 }, (_, i) => `a${i}`)
    let seed = 42
    const random = () => {
      seed = (seed * 9301 + 49297) % 233280
      return seed / 233280
    }
    const { themes } = applyAvatarThemeChoice(ids, 'mixed', ['blobs', 'bee'], random)
    for (const id of ids) {
      expect(themes[id]).toBeTruthy()
    }
  })

  it('falls back to the sole enabled theme when the chosen family is not installed', () => {
    const { themes } = applyAvatarThemeChoice(['a'], 'bee', ['blobs'])
    expect(themes['a']).toBe('blobs')
  })
})
