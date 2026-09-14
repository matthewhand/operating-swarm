import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import {
  BUBBLE_THEME_LABELS,
  BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEMES,
  DEFAULT_BUBBLE_THEME,
  formatBubbleTime,
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
  })

  it('formats a valid timestamp and skips invalid ones', () => {
    expect(formatBubbleTime(undefined)).toBe('')
    expect(formatBubbleTime('not-a-date')).toBe('')
    const label = formatBubbleTime('2026-09-03T06:54:00Z')
    expect(label.length).toBeGreaterThan(0)
    expect(label).toMatch(/\d/)
  })
})

