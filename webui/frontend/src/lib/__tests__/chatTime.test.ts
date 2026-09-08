import { describe, expect, it } from 'vitest'
import {
  CHAT_TIME_ZONE,
  formatGapLabel,
  formatRailTimestamp,
  parseCreatedAtMs,
  shouldShowGapStamp,
  sydneyDayKey,
} from '../chatTime'

/** 2026-09-03 07:21 AEST (UTC+10). */
const THU_721 = Date.parse('2026-09-02T21:21:00.000Z')
/** 14 minutes later the same Sydney morning. */
const THU_735 = THU_721 + 14 * 60 * 1000
/** Exactly 15 minutes later. */
const THU_736 = THU_721 + 15 * 60 * 1000
/** 2026-09-03 23:55 AEST. */
const THU_2355 = Date.parse('2026-09-03T13:55:00.000Z')
/** 2026-09-04 00:05 AEST — next Sydney day, 10 minutes later. */
const FRI_0005 = Date.parse('2026-09-03T14:05:00.000Z')
/** 2026-09-03 06:54 AEST. */
const WED_654 = Date.parse('2026-09-01T20:54:00.000Z')
const FRI_NOON = Date.parse('2026-09-04T02:00:00.000Z')

describe('parseCreatedAtMs', () => {
  it('reads ISO strings and epoch milliseconds', () => {
    expect(parseCreatedAtMs('2026-09-02T21:21:00.000Z')).toBe(THU_721)
    expect(parseCreatedAtMs(THU_721)).toBe(THU_721)
    expect(parseCreatedAtMs('nope')).toBeUndefined()
  })
})

describe('sydneyDayKey', () => {
  it('uses Australia/Sydney, not UTC', () => {
    expect(sydneyDayKey(THU_721)).toBe('2026-09-03')
    expect(sydneyDayKey(THU_721, 'UTC')).toBe('2026-09-02')
    expect(sydneyDayKey(FRI_0005)).toBe('2026-09-04')
  })
})

describe('shouldShowGapStamp', () => {
  it('omits a stamp when the gap is 14 minutes on the same Sydney day', () => {
    expect(shouldShowGapStamp(THU_721, THU_735)).toBe(false)
  })

  it('inserts a stamp at a 15 minute gap', () => {
    expect(shouldShowGapStamp(THU_721, THU_736)).toBe(true)
  })

  it('inserts a stamp when the Sydney calendar day changes, even under 15 minutes', () => {
    expect(FRI_0005 - THU_2355).toBe(10 * 60 * 1000)
    expect(shouldShowGapStamp(THU_2355, FRI_0005)).toBe(true)
    expect(shouldShowGapStamp(THU_2355, FRI_0005, CHAT_TIME_ZONE)).toBe(true)
  })

  it('does not stamp when either side is missing a time', () => {
    expect(shouldShowGapStamp(undefined, THU_736)).toBe(false)
    expect(shouldShowGapStamp(THU_721, undefined)).toBe(false)
  })
})

describe('formatGapLabel', () => {
  it('formats Today, Yesterday, and weekday dates in Sydney', () => {
    expect(formatGapLabel(THU_721, Date.parse('2026-09-03T10:00:00+10:00'))).toBe(
      'Today 7:21 AM',
    )
    expect(formatGapLabel(THU_721, FRI_NOON)).toBe('Yesterday 7:21 AM')
    expect(formatGapLabel(WED_654, FRI_NOON)).toBe('Wed 2 Sep 6:54 AM')
  })
})

describe('formatRailTimestamp', () => {
  it('appends the clock to dates older than yesterday', () => {
    expect(formatRailTimestamp(WED_654, FRI_NOON)).toBe('Wed 2 Sep 6:54 AM')
  })
})
