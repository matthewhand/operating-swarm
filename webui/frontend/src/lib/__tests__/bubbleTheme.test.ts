import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import {
  allBubbleThemes,
  BUBBLE_THEME_LABELS,
  BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEMES,
  BubbleThemeBase,
  DEFAULT_BUBBLE_THEME,
  formatBubbleTime,
  getBubbleTheme,
  loadBubbleTheme,
  parseBubbleTheme,
  saveBubbleTheme,
} from '../bubbleTheme'

describe('bubbleTheme', () => {
  afterEach(() => {
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('lists four ids with Speech/Simple/IRC/Feed labels', () => {
    expect([...BUBBLE_THEMES]).toEqual(['speech', 'simple', 'irc', 'feed'])
    expect(BUBBLE_THEME_LABELS.speech).toBe('Speech')
    expect(BUBBLE_THEME_LABELS.simple).toBe('Simple')
    expect(BUBBLE_THEME_LABELS.irc).toBe('IRC')
    expect(BUBBLE_THEME_LABELS.feed).toBe('Feed')
  })

  it('parses known ids and falls back to speech', () => {
    expect(parseBubbleTheme('speech')).toBe('speech')
    expect(parseBubbleTheme('simple')).toBe('simple')
    expect(parseBubbleTheme('irc')).toBe('irc')
    expect(parseBubbleTheme('feed')).toBe('feed')
    expect(parseBubbleTheme('')).toBe(DEFAULT_BUBBLE_THEME)
    expect(parseBubbleTheme(null)).toBe('speech')
    expect(parseBubbleTheme('not-a-theme')).toBe('speech')
  })

  it('defaults load to speech and persists the chosen id', () => {
    expect(loadBubbleTheme()).toBe('speech')
    expect(saveBubbleTheme('irc')).toBe('irc')
    expect(localStorage.getItem(BUBBLE_THEME_STORAGE_KEY)).toBe('irc')
    expect(loadBubbleTheme()).toBe('irc')
  })

  it('saves unknown values as speech', () => {
    expect(saveBubbleTheme('nope')).toBe('speech')
    expect(localStorage.getItem(BUBBLE_THEME_STORAGE_KEY)).toBe('speech')
    expect(loadBubbleTheme()).toBe('speech')
  })

  it('simple theme uses rounded bubbles and no chat tails', () => {
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../index.css'),
      'utf8',
    )
    const simple = css.split('[data-bubble-theme="simple"] .chat-bubble')[1] || ''
    expect(simple).toMatch(/border-radius:\s*1\.15rem/)
    expect(css).toMatch(
      /\[data-bubble-theme="simple"\] \.chat-bubble::before,[\s\S]*content:\s*none/,
    )
  })

  it('irc theme uses monospace log with fixed-width nick gutter and transparent bubbles (#165)', () => {
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../index.css'),
      'utf8',
    )
    expect(css).toMatch(/\[data-bubble-theme="irc"\]\s*\{[\s\S]*font-family:\s*ui-monospace/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*flex:\s*0 0 10ch/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*text-align:\s*right/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat-end[\s\S]*justify-content:\s*flex-start/)
    expect(css).toMatch(/\[data-timestamp-placement="below"\]/)
    expect(css).toMatch(/\[data-timestamp-placement="inline"\]/)
  })

  it('formats a valid timestamp and skips invalid ones', () => {
    expect(formatBubbleTime(undefined)).toBe('')
    expect(formatBubbleTime('not-a-date')).toBe('')
    const label = formatBubbleTime('2026-09-03T06:54:00Z')
    expect(label.length).toBeGreaterThan(0)
    expect(label).toMatch(/\d/)
  })
})

describe('bubbleTheme registry (#217)', () => {
  afterEach(() => {
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('derives BUBBLE_THEMES and labels from registered subclasses',
    () => {
      expect(allBubbleThemes().map((theme) => theme.id)).toEqual([
        'speech',
        'simple',
        'irc',
        'feed',
      ])
      expect([...BUBBLE_THEMES]).toEqual(['speech', 'simple', 'irc', 'feed'])
      expect(BUBBLE_THEME_LABELS).toEqual({
        speech: 'Speech',
        simple: 'Simple',
        irc: 'IRC',
        feed: 'Feed',
      })
      expect(allBubbleThemes().every((theme) => theme instanceof BubbleThemeBase)).toBe(true)
    },
  )

  it('locks per-theme message layout and timestamp placement',
    () => {
      expect(getBubbleTheme('speech').describe()).toEqual({
        id: 'speech',
        label: 'Speech',
        messageLayout: 'bubble',
        timestampPlacement: 'above',
      })
      expect(getBubbleTheme('simple').describe()).toEqual({
        id: 'simple',
        label: 'Simple',
        messageLayout: 'bubble',
        timestampPlacement: 'below',
      })
      expect(getBubbleTheme('irc').describe()).toEqual({
        id: 'irc',
        label: 'IRC',
        messageLayout: 'line',
        timestampPlacement: 'inline',
      })
      expect(getBubbleTheme('feed').describe()).toEqual({
        id: 'feed',
        label: 'Feed',
        messageLayout: 'line',
        timestampPlacement: 'above',
      })
    },
  )

  it('falls unknown ids back to speech and keeps chrome hooks as no-ops',
    () => {
      expect(getBubbleTheme('nope').id).toBe('speech')
      expect(getBubbleTheme(null).id).toBe('speech')
      const speech = getBubbleTheme('speech')
      expect(speech.renderRoleBadge()).toBeNull()
      expect(speech.renderAvatar()).toBeNull()
      expect(speech.renderStreamingAffordance()).toBeNull()
      expect(speech.composerChrome()).toEqual({
        placeholder: '',
        workingIndicatorPlacement: 'above',
      })
      expect(speech.formatTimestamp(undefined)).toBe('')
      expect(speech.formatTimestamp('2026-09-03T06:54:00Z')).toBe(
        formatBubbleTime('2026-09-03T06:54:00Z'),
      )
    },
  )

  it('keeps parse/save fallbacks on the storage key os.bubbleTheme',
    () => {
      expect(BUBBLE_THEME_STORAGE_KEY).toBe('os.bubbleTheme')
      expect(parseBubbleTheme('not-a-theme')).toBe('speech')
      expect(saveBubbleTheme('nope')).toBe('speech')
      expect(localStorage.getItem(BUBBLE_THEME_STORAGE_KEY)).toBe('speech')
    },
  )
})

