import { afterEach, describe, expect, it } from 'vitest'
import {
  AVATAR_THEME_SET_EVENT,
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEMES_ENABLED_KEY,
  ROBOT3D_THEME_RESERVED,
  defaultAvatarTheme,
  loadAvatarTheme,
  ROBOT_PACK_THEME_IDS,
  loadEnabledAvatarFamilies,
  loadEnabledAvatarThemes,
  resolveAvatarTheme,
  saveAvatarTheme,
  saveEnabledAvatarThemes,
  stripDisabledAvatarThemes,
  toggleEnabledAvatarTheme,
} from '../avatarTheme'

describe('avatar theme persist', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
  })

  it('defaults to Blobs and persists Bland like hostname', () => {
    expect(loadAvatarTheme()).toBe(defaultAvatarTheme())
    expect(loadAvatarTheme()).toBe('blobs')
    expect(saveAvatarTheme('bland')).toBe('bland')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('bland')
    expect(loadAvatarTheme()).toBe('bland')
  })

  it('treats unknown values as Blobs (default) and clears storage for Blobs', () => {
    expect(saveAvatarTheme('not-a-theme')).toBe('blobs')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBeNull()
    localStorage.setItem(AVATAR_THEME_STORAGE_KEY, 'bland')
    expect(saveAvatarTheme('bee')).toBe('bee')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('bee')
  })

  it('persists Bee as its own optional theme and clears storage for the Blobs default', () => {
    expect(saveAvatarTheme('bee')).toBe('bee')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('bee')
    expect(loadAvatarTheme()).toBe('bee')
    expect(saveAvatarTheme('blobs')).toBe('blobs')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBeNull()
    expect(loadAvatarTheme()).toBe('blobs')
  })

  it('uses Blobs as the factory default when storage is empty (#820)', () => {
    expect(defaultAvatarTheme()).toBe('blobs')
    expect(loadAvatarTheme()).toBe('blobs')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBeNull()
  })

  it('keeps Default (bland) as its own catalog choice without collapsing to Bee', () => {
    expect(saveAvatarTheme('bland')).toBe('bland')
    expect(loadAvatarTheme()).toBe('bland')
    expect(loadAvatarTheme()).not.toBe('bee')
    expect(saveAvatarTheme('default')).toBe('bland')
  })

  it('migrates legacy default to bland', () => {
    localStorage.setItem(AVATAR_THEME_STORAGE_KEY, 'default')
    expect(loadAvatarTheme()).toBe('bland')
    expect(saveAvatarTheme('default')).toBe('bland')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('bland')
  })

  it('persists robot3d since REQ-194 Phase 1 added it to the catalog', () => {
    expect(saveAvatarTheme(ROBOT3D_THEME_RESERVED)).toBe('robot3d')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('robot3d')
    expect(loadAvatarTheme()).toBe('robot3d')
  })

  it('dispatches a same-tab event so pickers update without reload', () => {
    const seen: string[] = []
    const onSet = (event: Event) => {
      seen.push((event as CustomEvent<string>).detail)
    }
    window.addEventListener(AVATAR_THEME_SET_EVENT, onSet)
    saveAvatarTheme('bland')
    window.removeEventListener(AVATAR_THEME_SET_EVENT, onSet)
    expect(seen).toEqual(['bland'])
  })
})

describe('enabled avatar themes (REQ-828)', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
  })

  it('defaults to blobs when nothing is stored', () => {
    expect(loadEnabledAvatarThemes()).toEqual(['blobs'])
  })

  it('derives the enabled set from a stored global theme', () => {
    saveAvatarTheme('bee')
    expect(loadEnabledAvatarThemes()).toEqual(['bee'])
  })

  it('persists a multi-theme install list', () => {
    expect(saveEnabledAvatarThemes(['blobs', 'bee'])).toEqual(['blobs', 'bee'])
    expect(JSON.parse(localStorage.getItem(AVATAR_THEMES_ENABLED_KEY) || '[]')).toEqual([
      'blobs',
      'bee',
    ])
    expect(loadEnabledAvatarThemes()).toEqual(['blobs', 'bee'])
  })

  it('refuses to disable the last remaining theme', () => {
    saveEnabledAvatarThemes(['blobs'])
    expect(toggleEnabledAvatarTheme('blobs', false)).toEqual(['blobs'])
  })

  it('resolves per-agent first, then the sole enabled theme, then global', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    saveAvatarTheme('blobs')
    expect(resolveAvatarTheme('bee', ['blobs', 'bee'], 'blobs')).toBe('bee')
    expect(resolveAvatarTheme('chassis', ['blobs', 'bee'], 'blobs')).toBe('blobs')
    expect(resolveAvatarTheme(null, ['bee'], 'blobs')).toBe('bee')
    expect(resolveAvatarTheme(null, ['blobs', 'bee'], 'bee')).toBe('bee')
  })

  it('treats chassis as the Robots family and expands the ten bodies', () => {
    expect(saveEnabledAvatarThemes(['chassis'])).toEqual([...ROBOT_PACK_THEME_IDS])
    expect(JSON.parse(localStorage.getItem(AVATAR_THEMES_ENABLED_KEY) || '[]')).toEqual(['robots'])
    expect(loadEnabledAvatarFamilies()).toEqual(['robots'])
  })

  it('rewrites retired per-agent packs to the sole remaining theme else blobs (REQ-841)', () => {
    expect(stripDisabledAvatarThemes({ a: 'bee', b: 'blobs' }, ['blobs'])).toEqual({
      a: 'blobs',
      b: 'blobs',
    })
    expect(stripDisabledAvatarThemes({ a: 'bee', b: 'bland' }, ['bland'])).toEqual({
      a: 'bland',
      b: 'bland',
    })
    const keep = { a: 'bee', b: 'blobs' }
    expect(stripDisabledAvatarThemes(keep, ['blobs', 'bee'])).toBe(keep)
  })
})
