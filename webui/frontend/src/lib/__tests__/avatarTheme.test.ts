import { afterEach, describe, expect, it } from 'vitest'
import {
  AVATAR_THEME_SET_EVENT,
  AVATAR_THEME_STORAGE_KEY,
  ROBOT3D_THEME_RESERVED,
  defaultAvatarTheme,
  loadAvatarTheme,
  saveAvatarTheme,
} from '../avatarTheme'

describe('avatar theme persist', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
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
    expect(saveAvatarTheme('blobs')).toBe('blobs')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBeNull()
  })

  it('persists Bee as its own theme and does not collapse it to Blobs', () => {
    expect(saveAvatarTheme('bee')).toBe('bee')
    expect(localStorage.getItem(AVATAR_THEME_STORAGE_KEY)).toBe('bee')
    expect(loadAvatarTheme()).toBe('bee')
  })

  it('keeps Bee opt-in: empty storage stays Blobs and is never Bee', () => {
    expect(defaultAvatarTheme()).toBe('blobs')
    expect(defaultAvatarTheme()).not.toBe('bee')
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
