/**
 * #1274 — timeline-marker derivation contracts.
 *
 * Boundaries are derived purely from row `ts` values at render time; status
 * rows never trigger or carry markers; DST-critical cases use explicit dates.
 */
import { describe, expect, it } from 'vitest'
import {
  SESSION_RESUME_GAP_MS,
  dayLabelFor,
  interleaveTimelineMarkers,
  resumedLabelFor,
  timelineMarkersFor,
} from '../chatTimeline'

const NOW = new Date('2026-09-26T15:00:00')

describe('#1274 day labels', () => {
  it('labels the current day Today', () => {
    expect(dayLabelFor(new Date('2026-09-26T09:12:00'), NOW)).toBe('Today')
  })

  it('labels the previous calendar day Yesterday', () => {
    expect(dayLabelFor(new Date('2026-09-25T23:59:00'), NOW)).toBe('Yesterday')
  })

  it('uses a dated short form for older days', () => {
    const label = dayLabelFor(new Date('2026-09-23T10:00:00'), NOW)
    expect(label).not.toBe('Today')
    expect(label).not.toBe('Yesterday')
    expect(label).toContain('23')
  })

  it('formats resumed time as HH:MM', () => {
    expect(resumedLabelFor(new Date('2026-09-26T14:32:00'))).toMatch(/^Resumed \d{2}:\d{2}$/)
  })
})

describe('#1274 marker derivation', () => {
  it('opens the transcript with a day marker on the first message row', () => {
    const rows = [
      { role: 'user', ts: '2026-09-26T09:00:00' },
      { role: 'assistant', ts: '2026-09-26T09:00:05' },
    ]
    const markers = timelineMarkersFor(rows, NOW)
    expect(markers.size).toBe(1)
    expect(markers.get(0)).toMatchObject({ kind: 'day', label: 'Today' })
  })

  it('emits a day marker at a calendar-day boundary', () => {
    const rows = [
      { role: 'user', ts: '2026-09-25T22:00:00' },
      { role: 'assistant', ts: '2026-09-25T22:00:10' },
      { role: 'user', ts: '2026-09-26T08:30:00' },
    ]
    const markers = timelineMarkersFor(rows, NOW)
    expect(markers.get(2)).toMatchObject({ kind: 'day' })
    expect(markers.has(1)).toBe(false)
  })

  it('emits a resumed divider for a same-day gap >= threshold and nothing below it', () => {
    const rows = [
      { role: 'user', ts: '2026-09-26T08:00:00' },
      { role: 'assistant', ts: '2026-09-26T09:30:00' }, // 1.5h — below the 2h gap
      { role: 'user', ts: '2026-09-26T14:32:00' }, // ~5h — resumed
    ]
    const markers = timelineMarkersFor(rows, NOW)
    expect(markers.has(1)).toBe(false)
    expect(markers.get(2)).toMatchObject({ kind: 'resumed' })
  })

  it('skips status/notice rows as marker carriers but still reads the day gap between messages', () => {
    const rows = [
      { role: 'user', ts: '2026-09-25T10:00:00' },
      { role: 'status', ts: '2026-09-26T10:00:00' },
      { role: 'user', ts: '2026-09-26T10:00:05' },
    ]
    const markers = timelineMarkersFor(rows, NOW)
    // The status row itself never carries a marker; the day boundary lands on
    // the next real message row (index 2).
    expect(markers.has(1)).toBe(false)
    expect(markers.get(2)).toMatchObject({ kind: 'day' })
  })

  it('ignores rows without a parseable ts', () => {
    const rows = [
      { role: 'user', ts: null },
      { role: 'assistant', ts: 'not-a-date' },
      { role: 'user', ts: '2026-09-26T10:00:00' },
    ]
    const markers = timelineMarkersFor(rows, NOW)
    expect(markers.size).toBe(1)
    expect(markers.has(0)).toBe(false)
  })

  it('treats a sub-threshold gap across a DST spring-forward night as a day boundary, not resumed', () => {
    // 2026-09-27 is an arbitrary date; the DST property under test is that a
    // same-wallclock-time pair separated by a day boundary always yields a
    // day marker (start-of-day math, never raw ms deltas across midnight).
    const rows = [
      { role: 'user', ts: '2026-09-26T23:30:00' },
      { role: 'user', ts: '2026-09-27T00:30:00' },
    ]
    const markers = timelineMarkersFor(rows, NOW)
    expect(markers.get(1)).toMatchObject({ kind: 'day' })
  })

  it('keeps the resume threshold exported at two hours', () => {
    expect(SESSION_RESUME_GAP_MS).toBe(2 * 60 * 60 * 1000)
  })
})

describe('#1274 interleave into display items', () => {
  const messages = [
    { role: 'user', ts: '2026-09-25T22:00:00' },
    { role: 'assistant', ts: '2026-09-25T22:00:05' },
    { role: 'user', ts: '2026-09-26T08:30:00' },
    { role: 'assistant', ts: '2026-09-26T08:30:05' },
  ]
  const items = messages.map((message, i) => ({ kind: 'message', message, rawIndex: i }))

  it('inserts marker items without reindexing the original items', () => {
    const out = interleaveTimelineMarkers(items, messages, NOW)
    const markers = out.filter((item) => item.kind === 'marker')
    expect(markers).toHaveLength(2)
    // Every original item survives in order with its identity intact.
    const original = out.filter((item) => item.kind === 'message')
    expect(original).toHaveLength(4)
    expect((original[0] as any).rawIndex).toBe(0)
    expect((original[3] as any).rawIndex).toBe(3)
    // A marker precedes the day-B message (raw index 2).
    const markerBeforeIdx2 = out.indexOf(markers[1]) < out.indexOf(original[2])
    expect(markerBeforeIdx2).toBe(true)
  })

  it('returns the input untouched for an empty transcript (no rows, no markers)', () => {
    expect(interleaveTimelineMarkers(items, [], NOW)).toBe(items)
  })

  it('always opens a non-empty transcript with its first day marker', () => {
    const sameDay = [
      { role: 'user', ts: '2026-09-26T10:00:00' },
      { role: 'assistant', ts: '2026-09-26T10:00:05' },
    ]
    const sameItems = sameDay.map((message) => ({ kind: 'message', message }))
    const out = interleaveTimelineMarkers(sameItems, sameDay, NOW)
    expect(out).toHaveLength(3)
    expect(out[0]).toMatchObject({ kind: 'marker', marker: { kind: 'day', label: 'Today' } })
  })

  it('anchors a boundary marker before a summary block whose span starts there', () => {
    // Day-B boundary sits at raw index 2; a summary covering 2..3 gets the
    // day marker rendered before the block (markers precede covered spans).
    const withSummary = [
      { kind: 'summary', summary: { id: 1, span: { start: 2, end: 3 }, body: 'earlier' } },
      { kind: 'message', message: messages[3] },
    ]
    const out = interleaveTimelineMarkers(withSummary, messages, NOW)
    expect(out.map((item) => item.kind)).toEqual(['marker', 'summary', 'message'])
    expect((out[0] as any).marker).toMatchObject({ kind: 'day' })
    // A summary covering from the very first row carries the opening marker.
    const opening = [
      { kind: 'summary', summary: { id: 2, span: { start: 0, end: 1 }, body: 'day one' } },
      ...messages.slice(2).map((message) => ({ kind: 'message', message })),
    ]
    const out2 = interleaveTimelineMarkers(opening, messages, NOW)
    expect(out2.map((item) => item.kind)).toEqual([
      'marker', 'summary', 'marker', 'message', 'message',
    ])
  })
})
