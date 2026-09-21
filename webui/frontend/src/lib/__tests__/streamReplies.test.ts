import { afterEach, describe, expect, it } from 'vitest'
import { BUBBLE_THEME_STORAGE_KEY, saveBubbleTheme } from '../bubbleTheme'
import {
  STREAM_REPLIES_SEATS_STORAGE_KEY,
  STREAM_REPLIES_STORAGE_KEY,
  loadSeatStreamReplies,
  loadStreamReplies,
  saveSeatStreamReplies,
  saveStreamReplies,
  streamingPartialEnabled,
} from '../streamReplies'

describe('streamReplies (#220)', () => {
  afterEach(() => {
    localStorage.removeItem(STREAM_REPLIES_STORAGE_KEY)
    localStorage.removeItem(STREAM_REPLIES_SEATS_STORAGE_KEY)
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('defaults the user toggle off (opt-in)', () => {
    expect(loadStreamReplies()).toBe(false)
    expect(saveStreamReplies(true)).toBe(true)
    expect(localStorage.getItem(STREAM_REPLIES_STORAGE_KEY)).toBe('1')
    expect(loadStreamReplies()).toBe(true)
    saveStreamReplies(false)
    expect(loadStreamReplies()).toBe(false)
  })

  it('stores a per-seat override and inherits when unset', () => {
    expect(loadSeatStreamReplies('support')).toBeNull()
    expect(saveSeatStreamReplies('support', true)).toBe(true)
    expect(loadSeatStreamReplies('support')).toBe(true)
    saveSeatStreamReplies('support', false)
    expect(loadSeatStreamReplies('support')).toBe(false)
    saveSeatStreamReplies('support', null)
    expect(loadSeatStreamReplies('support')).toBeNull()
  })

  it('theme-gates partial rendering even when the user opted in', () => {
    saveStreamReplies(true)
    saveBubbleTheme('speech')
    expect(streamingPartialEnabled({ theme: 'speech' })).toBe(true)
    expect(streamingPartialEnabled({ theme: 'simple' })).toBe(true)
    expect(streamingPartialEnabled({ theme: 'irc' })).toBe(true)
  })

  it('applies the seat override on top of the theme gate and user toggle', () => {
    saveStreamReplies(false)
    saveBubbleTheme('speech')
    expect(streamingPartialEnabled({ theme: 'speech', seatId: 'support' })).toBe(false)
    saveSeatStreamReplies('support', true)
    expect(streamingPartialEnabled({ theme: 'speech', seatId: 'support' })).toBe(true)
    expect(streamingPartialEnabled({ theme: 'simple', seatId: 'support' })).toBe(true)
    saveStreamReplies(true)
    saveSeatStreamReplies('support', false)
    expect(streamingPartialEnabled({ theme: 'speech', seatId: 'support' })).toBe(false)
  })
})
