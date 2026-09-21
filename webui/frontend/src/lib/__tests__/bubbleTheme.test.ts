import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import {
  allBubbleThemes,
  BUBBLE_THEME_LABELS,
  BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEME_STREAMING,
  BUBBLE_THEMES,
  BubbleThemeBase,
  DEFAULT_BUBBLE_THEME,
  bubbleThemeSupportsStreaming,
  formatBubbleTime,
  getBubbleTheme,
  loadBubbleTheme,
  parseBubbleTheme,
  renderStreamingAffordance,
  saveBubbleTheme,
} from '../bubbleTheme'

describe('bubbleTheme', () => {
  afterEach(() => {
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('lists three ids with Speech/Simple/IRC labels (#808: feed retired)', () => {
    expect([...BUBBLE_THEMES]).toEqual(['speech', 'simple', 'irc'])
    expect(BUBBLE_THEME_LABELS.speech).toBe('Speech')
    expect(BUBBLE_THEME_LABELS.simple).toBe('Simple')
    expect(BUBBLE_THEME_LABELS.irc).toBe('IRC')
  })

  it('parses known ids and falls back to speech', () => {
    expect(parseBubbleTheme('speech')).toBe('speech')
    expect(parseBubbleTheme('simple')).toBe('simple')
    expect(parseBubbleTheme('irc')).toBe('irc')
    // #808: the retired theme id falls back to the default.
    expect(parseBubbleTheme('feed')).toBe(DEFAULT_BUBBLE_THEME)
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

  it('irc theme uses monospace log with a flexing, legible nick gutter and transparent bubbles (#165, #520.3)', () => {
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../index.css'),
      'utf8',
    )
    expect(css).toMatch(/\[data-bubble-theme="irc"\]\s*\{[\s\S]*font-family:\s*ui-monospace/)
    // #675 (superseding #520.3): the gutter is a fixed resizable width — the
    // persisted --irc-gutter-px — so all message bodies align on one vertical
    // edge; body-copy size and right-aligned nick are kept.
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*flex:\s*0 0 var\(--irc-gutter-px\)/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*width:\s*var\(--irc-gutter-px\)/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*font-size:\s*0\.8125rem/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*text-align:\s*right/)
    expect(css).toMatch(/\[data-bubble-theme="irc"\] \.chat\s*\{[\s\S]*?justify-content:\s*flex-start/)
    expect(css).toMatch(/\[data-timestamp-placement="below"\]/)
    expect(css).toMatch(/\[data-timestamp-placement="inline"\]/)
  })

  it('declares streaming support and affordance per theme (#220)', () => {
    expect(bubbleThemeSupportsStreaming('speech')).toBe(true)
    expect(bubbleThemeSupportsStreaming('simple')).toBe(true)
    expect(bubbleThemeSupportsStreaming('irc')).toBe(true)
    expect(renderStreamingAffordance('speech')).toBe('caret')
    expect(renderStreamingAffordance('simple')).toBe('caret')
    expect(renderStreamingAffordance('irc')).toBe('block')
    expect(BUBBLE_THEMES.every((id) => BUBBLE_THEME_STREAMING[id].id === id)).toBe(true)
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
      ])
      expect([...BUBBLE_THEMES]).toEqual(['speech', 'simple', 'irc'])
      expect(BUBBLE_THEME_LABELS).toEqual({
        speech: 'Speech',
        simple: 'Simple',
        irc: 'IRC',
      })
      expect(allBubbleThemes().every((theme) => theme instanceof BubbleThemeBase)).toBe(true)
    },
  )

  it('locks per-theme message layout, timestamp placement, and action-row placement',
    () => {
      // #505: actionRowPlacement joins the theme contract (default 'below').
      expect(getBubbleTheme('speech').describe()).toEqual({
        id: 'speech',
        label: 'Speech',
        messageLayout: 'bubble',
        timestampPlacement: 'above',
        actionRowPlacement: 'below',
        showAvatar: true,
      })
      expect(getBubbleTheme('simple').describe()).toEqual({
        id: 'simple',
        label: 'Simple',
        messageLayout: 'bubble',
        timestampPlacement: 'inline',
        actionRowPlacement: 'below',
        showAvatar: false,
      })
      expect(getBubbleTheme('irc').describe()).toEqual({
        id: 'irc',
        label: 'IRC',
        messageLayout: 'line',
        timestampPlacement: 'inline',
        actionRowPlacement: 'overlay',
        showAvatar: true,
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


describe('#782 — bubble-theme-aware notice rows', () => {
  it('IRC renders notice rows as gutter lines; other themes fall back to the card', () => {
    const irc = getBubbleTheme('irc')
    expect(irc.renderNoticeRow).toBeDefined()
    expect(irc.renderNoticeRow('System', 'Started a new omp session', undefined, 'notice-1')).toMatchObject(
      {
        kind: 'gutter-line',
        speaker: 'System',
        text: 'Started a new omp session',
        key: 'notice-1',
      },
    )

    // #533 card themes keep their existing disclosure chrome.
    for (const id of ['speech', 'simple'] as const) {
      const theme = getBubbleTheme(id)
      expect(theme.renderNoticeRow('System', 'ctx culled', undefined, 'k')).toMatchObject({
        kind: 'card',
      })
    }
  })

  it('IRC gutter-line notices stamp ts at arrival (--:-- when unknown)', () => {
    const irc = getBubbleTheme('irc')
    const row = irc.renderNoticeRow('System', 'Queued item promoted.', '2026-09-20T10:30:00Z', 'k')
    expect(row).toMatchObject({ kind: 'gutter-line', ts: '2026-09-20T10:30:00Z' })
    const unknown = irc.renderNoticeRow('System', 'x', undefined, 'k')
    expect(unknown).toMatchObject({ kind: 'gutter-line', ts: undefined })
  })

  it('IRC notice bodies are plain one-line labels (statusLineLabel)', () => {
    const irc = getBubbleTheme('irc')
    const row = irc.renderNoticeRow('System', '**Bold** notice\nsecond line', undefined, 'k')
    expect(row).toMatchObject({ kind: 'gutter-line', text: 'Bold notice second line' })
  })
})
