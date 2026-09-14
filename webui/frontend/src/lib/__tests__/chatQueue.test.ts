import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  QUEUED_PANE_MAX_HEIGHT_CLASS,
  QUEUED_PANE_MAX_HEIGHT_STYLE,
  QUEUED_PREVIEW_MAX_CHARS,
  QUEUED_SENDS_KEY,
  enqueueQueuedSend,
  generationIsInFlight,
  loadQueuedSends,
  nextDrainableQueuedSend,
  prependQueuedSend,
  queuedPaneMaxHeightPx,
  queuedPreviewIsTruncated,
  queuedPreviewText,
  removeQueuedSend,
  saveQueuedSends,
  suggestionChipText,
  updateQueuedSend,
} from '../chatQueue'

describe('chatQueue (REQ-90)', () => {
  beforeEach(() => {
    localStorage.removeItem(QUEUED_SENDS_KEY)
  })

  afterEach(() => {
    localStorage.removeItem(QUEUED_SENDS_KEY)
  })

  it('persists queued rows with the conversation id', () => {
    const rows = enqueueQueuedSend([], 'first follow-up')
    saveQueuedSends('conv-a', rows)
    expect(loadQueuedSends('conv-a').map((row) => row.text)).toEqual(['first follow-up'])
    expect(loadQueuedSends('conv-b')).toEqual([])
  })

  it('restores queued rows after a simulated refresh', () => {
    saveQueuedSends('conv-a', enqueueQueuedSend([], 'still here'))
    expect(loadQueuedSends('conv-a')[0]?.text).toBe('still here')
  })

  it('drops an empty conversation key when the queue is cleared', () => {
    saveQueuedSends('conv-a', enqueueQueuedSend([], 'gone soon'))
    saveQueuedSends('conv-a', [])
    const raw = localStorage.getItem(QUEUED_SENDS_KEY)
    expect(raw).toBe('{}')
  })

  it('enqueues oldest-first and updates edited text', () => {
    let rows = enqueueQueuedSend([], 'alpha')
    rows = enqueueQueuedSend(rows, 'beta')
    expect(rows.map((row) => row.text)).toEqual(['alpha', 'beta'])
    rows = updateQueuedSend(rows, rows[0]!.id, 'alpha-edited')
    expect(rows[0]?.text).toBe('alpha-edited')
  })

  it('removes a deleted row so it never drains', () => {
    let rows = enqueueQueuedSend([], 'keep')
    rows = enqueueQueuedSend(rows, 'drop')
    const drop = rows[1]!
    rows = removeQueuedSend(rows, drop.id)
    expect(nextDrainableQueuedSend(rows, [])?.text).toBe('keep')
    expect(rows.some((row) => row.id === drop.id)).toBe(false)
  })

  it('skips a focused or dirty row and drains the next ready one', () => {
    let rows = enqueueQueuedSend([], 'editing')
    rows = enqueueQueuedSend(rows, 'ready')
    const held = nextDrainableQueuedSend(rows, [rows[0]!.id])
    expect(held?.text).toBe('ready')
    expect(nextDrainableQueuedSend(rows, [rows[0]!.id, rows[1]!.id])).toBeNull()
  })

  it('treats streaming or awaiting-assistant as in-flight', () => {
    expect(generationIsInFlight([{ streaming: true }], false)).toBe(true)
    expect(generationIsInFlight([{ streaming: false }], true)).toBe(true)
    expect(generationIsInFlight([{ streaming: false }], false)).toBe(false)
  })

  it('caps the pane at one-third of the transcript viewport', () => {
    expect(queuedPaneMaxHeightPx(900)).toBe(300)
    expect(QUEUED_PANE_MAX_HEIGHT_CLASS).toBe('max-h-[33%]')
    expect(QUEUED_PANE_MAX_HEIGHT_STYLE).toBe('33.333%')
  })

  it('reads chip-click text from the suggestion event', () => {
    const event = new CustomEvent('swarm:suggestion-chip', { detail: { text: 'chip prompt' } })
    expect(suggestionChipText(event)).toBe('chip prompt')
    expect(suggestionChipText(new Event('click'))).toBe('')
  })

  it('restores a failed drain at the front', () => {
    const row = enqueueQueuedSend([], 'retry-me')[0]!
    expect(prependQueuedSend([], row)[0]).toEqual(row)
  })

  // #198 — 80-char single-line previews with hover-reveal
  it('collapses whitespace and caps previews at 80 chars with an ellipsis', () => {
    expect(QUEUED_PREVIEW_MAX_CHARS).toBe(80)
    const long = 'a'.repeat(120)
    expect(queuedPreviewText(long)).toBe(`${'a'.repeat(80)}…`)
    const multiline = 'one\n\ntwo   three\tfour'
    expect(queuedPreviewText(multiline)).toBe('one two three four')
    expect(queuedPreviewText('  padded  ')).toBe('padded')
  })

  it('flags which previews are truncated (hover reveals full text)', () => {
    expect(queuedPreviewIsTruncated('a'.repeat(120))).toBe(true)
    expect(queuedPreviewIsTruncated('a'.repeat(80))).toBe(false)
    expect(queuedPreviewIsTruncated('a'.repeat(81))).toBe(true)
    expect(queuedPreviewIsTruncated('short')).toBe(false)
  })
})
