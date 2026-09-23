/**
 * #675 — IRC gutter width preference: clamped, persisted, resettable.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import {
  IRC_GUTTER_DEFAULT_PX,
  IRC_GUTTER_MAX_PX,
  IRC_GUTTER_MIN_PX,
  IRC_GUTTER_STORAGE_KEY,
  loadIrcGutterPx,
  saveIrcGutterPx,
  themeUsesIrcGutter,
} from '../ircGutter'

beforeEach(() => localStorage.clear())

describe('#675 IRC gutter preference', () => {
  it('defaults when unset', () => {
    expect(loadIrcGutterPx()).toBe(IRC_GUTTER_DEFAULT_PX)
  })

  it('persists a width inside the bounds', () => {
    saveIrcGutterPx(200)
    expect(localStorage.getItem(IRC_GUTTER_STORAGE_KEY)).toBe('200')
    expect(loadIrcGutterPx()).toBe(200)
  })

  it('clamps below min and above max', () => {
    expect(saveIrcGutterPx(10)).toBe(IRC_GUTTER_MIN_PX)
    expect(saveIrcGutterPx(9999)).toBe(IRC_GUTTER_MAX_PX)
  })

  it('falls back to default on corrupt values', () => {
    localStorage.setItem(IRC_GUTTER_STORAGE_KEY, 'not-a-number')
    expect(loadIrcGutterPx()).toBe(IRC_GUTTER_DEFAULT_PX)
  })

  it('only the irc theme uses the gutter', () => {
    expect(themeUsesIrcGutter('irc')).toBe(true)
    expect(themeUsesIrcGutter('speech')).toBe(false)
  })
})
