/**
 * #534 — compression notifications are API-seat only.
 *
 * The backend must not emit 'Auto-compress skipped' (and kin) for non-api
 * seats, and the client suppresses them as a second line of defense —
 * including rows already persisted into a transcript by older servers.
 * Restore banners ('Restored session', 'Resumed …') must stay distinct and
 * never match this filter.
 */
import { describe, expect, it } from 'vitest'
import {
  API_ONLY_SKIPPED_TEXT,
  AUTO_CULL_SKIPPED_PREFIX,
  AUTO_COMPRESS_SKIPPED_TEXT,
  COMPRESSION_NOTICE_TEXTS,
  isCompressionNoticeText,
} from '../compressionNotices'

describe('isCompressionNoticeText', () => {
  it('recognizes the exact auto-compress skip line the backend emits', () => {
    expect(isCompressionNoticeText(AUTO_COMPRESS_SKIPPED_TEXT)).toBe(true)
    expect(isCompressionNoticeText(API_ONLY_SKIPPED_TEXT)).toBe(true)
  })

  it('recognizes performed/failed variants and auto-cull skips', () => {
    for (const text of COMPRESSION_NOTICE_TEXTS) {
      expect(isCompressionNoticeText(text)).toBe(true)
    }
    expect(isCompressionNoticeText(AUTO_CULL_SKIPPED_PREFIX)).toBe(true)
    expect(isCompressionNoticeText('Auto-cull skipped — model context length unknown.')).toBe(true)
    expect(isCompressionNoticeText('Auto-compress skipped — model context length unknown.')).toBe(
      true,
    )
  })

  it('matches persisted rows with markdown or extra whitespace', () => {
    expect(isCompressionNoticeText('  *Auto-compress skipped — model context length unknown.* '))
      .toBe(true)
    expect(isCompressionNoticeText('**Context compression skipped** — API-only mode enabled')).toBe(
      true,
    )
    expect(isCompressionNoticeText('Context culling skipped — API-only mode enabled')).toBe(true)
  })

  it('never matches unrelated status chrome', () => {
    expect(isCompressionNoticeText('Started a new grok session.')).toBe(false)
    expect(isCompressionNoticeText('Resumed grok session.')).toBe(false)
    expect(isCompressionNoticeText('Restored session')).toBe(false)
    expect(isCompressionNoticeText('Reconnected remote')).toBe(false)
    expect(isCompressionNoticeText('Switched to session agt-1')).toBe(false)
    expect(isCompressionNoticeText('Compressed chat to here')).toBe(false)
    expect(isCompressionNoticeText('')).toBe(false)
    expect(isCompressionNoticeText(null)).toBe(false)
  })
})
