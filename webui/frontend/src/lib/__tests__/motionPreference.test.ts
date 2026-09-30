/**
 * #1244 — the avatar motion preference must (a) respect system reduce by
 * default, (b) let the operator opt back in, and (c) mirror that choice onto
 * the document root for the CSS reduced-motion gate.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AVATAR_MOTION_ATTRIBUTE,
  AVATAR_MOTION_STORAGE_KEY,
  applyAvatarMotionPreference,
  avatarMotionForced,
  loadAvatarMotionPreference,
  prefersReducedMotion,
  saveAvatarMotionPreference,
  systemPrefersReducedMotion,
} from '../motionPreference'

const originalMatchMedia = window.matchMedia

function stubMatchMedia(matches: boolean) {
  const media = {
    matches,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: vi.fn().mockReturnValue(media),
  })
  return media
}

describe('#1244 avatar motion preference', () => {
  beforeEach(() => {
    localStorage.removeItem(AVATAR_MOTION_STORAGE_KEY)
    document.documentElement.removeAttribute(AVATAR_MOTION_ATTRIBUTE)
  })

  afterEach(() => {
    localStorage.removeItem(AVATAR_MOTION_STORAGE_KEY)
    document.documentElement.removeAttribute(AVATAR_MOTION_ATTRIBUTE)
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    })
  })

  it('defaults to "system" and leaves the root attribute absent', () => {
    stubMatchMedia(false)
    expect(loadAvatarMotionPreference()).toBe('system')
    expect(applyAvatarMotionPreference()).toBe('system')
    expect(document.documentElement).not.toHaveAttribute(AVATAR_MOTION_ATTRIBUTE)
    expect(avatarMotionForced()).toBe(false)
  })

  it('honours system reduced motion by default', () => {
    stubMatchMedia(true)
    expect(systemPrefersReducedMotion()).toBe(true)
    expect(prefersReducedMotion()).toBe(true)
  })

  it('the opt-in overrides system reduce and mirrors onto <html>', () => {
    stubMatchMedia(true)
    expect(saveAvatarMotionPreference('always')).toBe('always')
    expect(localStorage.getItem(AVATAR_MOTION_STORAGE_KEY)).toBe('always')
    expect(document.documentElement).toHaveAttribute(AVATAR_MOTION_ATTRIBUTE, 'always')
    expect(avatarMotionForced()).toBe(true)
    // System still asks for reduce, but the explicit opt-in wins.
    expect(systemPrefersReducedMotion()).toBe(true)
    expect(prefersReducedMotion()).toBe(false)
  })

  it('reverts to system and clears the root attribute', () => {
    stubMatchMedia(true)
    saveAvatarMotionPreference('always')
    expect(saveAvatarMotionPreference('system')).toBe('system')
    expect(localStorage.getItem(AVATAR_MOTION_STORAGE_KEY)).toBe('system')
    expect(document.documentElement).not.toHaveAttribute(AVATAR_MOTION_ATTRIBUTE)
    expect(prefersReducedMotion()).toBe(true)
  })

  it('treats unknown stored values as "system"', () => {
    localStorage.setItem(AVATAR_MOTION_STORAGE_KEY, 'nonsense')
    expect(loadAvatarMotionPreference()).toBe('system')
    expect(applyAvatarMotionPreference()).toBe('system')
  })
})
