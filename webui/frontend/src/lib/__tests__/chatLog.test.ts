import { describe, expect, it } from 'vitest'
import {
  countableChatCount,
  decorateConversationRows,
  effectiveUnreadWatermark,
  firstUnreadMessageKey,
} from '../chatLog'
import { hopFromAssistantName, type ChatItem } from '../interBot'

const THU_721 = Date.parse('2026-09-02T21:21:00.000Z')
const THU_735 = THU_721 + 14 * 60 * 1000
const THU_736 = THU_721 + 15 * 60 * 1000
const THU_2355 = Date.parse('2026-09-03T13:55:00.000Z')
const FRI_0005 = Date.parse('2026-09-03T14:05:00.000Z')
const FRI_NOON = Date.parse('2026-09-04T02:00:00.000Z')

function message(
  key: string,
  text: string,
  createdAtMs?: number,
  role: 'user' | 'assistant' = 'user',
): ChatItem {
  return { type: 'message', key, role, text, streaming: false, createdAtMs }
}

describe('decorateConversationRows', () => {
  it('does not insert a stamp for a 14 minute same-day gap', () => {
    const rows = decorateConversationRows(
      [message('a', 'first', THU_721), message('b', 'second', THU_735)],
      { nowMs: FRI_NOON },
    )
    expect(rows.map((row) => row.type)).toEqual(['message', 'message'])
  })

  it('inserts a centred stamp at a 15 minute gap', () => {
    const rows = decorateConversationRows(
      [message('a', 'first', THU_721), message('b', 'second', THU_736)],
      { nowMs: Date.parse('2026-09-03T10:00:00+10:00') },
    )
    expect(rows.map((row) => row.type)).toEqual(['message', 'gap', 'message'])
    expect(rows[1]).toMatchObject({ type: 'gap', label: 'Today 7:36 AM' })
  })

  it('inserts a stamp on a Sydney day change even when the clock gap is under 15 minutes', () => {
    const rows = decorateConversationRows(
      [message('a', 'late', THU_2355), message('b', 'early', FRI_0005)],
      { nowMs: FRI_NOON },
    )
    expect(rows.map((row) => row.type)).toEqual(['message', 'gap', 'message'])
    expect(rows[1]).toMatchObject({ type: 'gap', label: 'Today 12:05 AM' })
  })

  it('places the stamp after Messaged and before the next bubble', () => {
    const items: ChatItem[] = [
      message('a', 'go', THU_721),
      { type: 'hop', key: 'h1', hop: hopFromAssistantName('1', 'A', false) },
      { type: 'hop', key: 'h2', hop: hopFromAssistantName('2', 'B', false) },
      message('b', 'done', THU_736, 'assistant'),
    ]
    const rows = decorateConversationRows(items, {
      nowMs: Date.parse('2026-09-03T10:00:00+10:00'),
    })
    expect(rows.map((row) => row.type)).toEqual(['message', 'hop-line', 'gap', 'message'])
    expect(rows[1]).toMatchObject({ type: 'hop-line', line: { kind: 'multi' } })
    expect(rows[2]).toMatchObject({ type: 'gap', label: 'Today 7:36 AM' })
  })

  it('places the stamp before Message from so it is not inside the bubble', () => {
    const items: ChatItem[] = [
      message('a', 'go', THU_721),
      { type: 'hop', key: 'h1', hop: hopFromAssistantName('1', 'HASS', false) },
      message('b', 'hi', THU_736, 'assistant'),
    ]
    const rows = decorateConversationRows(items, {
      nowMs: Date.parse('2026-09-03T10:00:00+10:00'),
    })
    expect(rows.map((row) => row.type)).toEqual(['message', 'gap', 'hop-line', 'message'])
    expect(rows[2]).toMatchObject({ type: 'hop-line', line: { kind: 'single' } })
  })

  it('inserts NEW at the first message after the last-read cursor', () => {
    const rows = decorateConversationRows(
      [
        message('a', 'read', THU_721),
        message('b', 'also read', THU_735),
        message('c', 'unread', THU_736),
      ],
      { lastReadMessageCount: 2, nowMs: FRI_NOON },
    )
    expect(rows.map((row) => row.type)).toEqual(['message', 'message', 'new', 'message'])
    expect(rows[2]).toMatchObject({ type: 'new' })
  })

  it('places NEW above the gap stamp and before Message from', () => {
    const items: ChatItem[] = [
      message('a', 'old', THU_721),
      { type: 'hop', key: 'h1', hop: hopFromAssistantName('1', 'Taskmaster', false) },
      message('b', 'unread', THU_736, 'assistant'),
    ]
    const rows = decorateConversationRows(items, {
      lastReadMessageCount: 1,
      nowMs: Date.parse('2026-09-03T10:00:00+10:00'),
    })
    expect(rows.map((row) => row.type)).toEqual([
      'message',
      'new',
      'gap',
      'hop-line',
      'message',
    ])
    expect(rows[3]).toMatchObject({ type: 'hop-line', line: { kind: 'single' } })
    expect(rows[2]).toMatchObject({ type: 'gap', label: 'Today 7:36 AM' })
  })

  it('does not show NEW on a first visit or when everything is already read', () => {
    const items = [message('a', 'one', THU_721), message('b', 'two', THU_735)]
    expect(
      decorateConversationRows(items, { lastReadMessageCount: null }).map((row) => row.type),
    ).toEqual(['message', 'message'])
    expect(
      decorateConversationRows(items, { lastReadMessageCount: 2 }).map((row) => row.type),
    ).toEqual(['message', 'message'])
  })

  it('places NEW before the first message when the watermark is 0', () => {
    const rows = decorateConversationRows(
      [message('a', 'unread', THU_721), message('b', 'also', THU_735)],
      { lastReadMessageCount: 0, nowMs: FRI_NOON },
    )
    expect(rows.map((row) => row.type)).toEqual(['new', 'message', 'message'])
  })
})

describe('unread New divider helpers', () => {
  it('skips status rows when locating the first unread message', () => {
    const rows = [
      { key: 'u1', role: 'user' },
      { key: 's1', role: 'status' },
      { key: 'a1', role: 'assistant' },
      { key: 'a2', role: 'assistant' },
    ]
    expect(countableChatCount(rows)).toBe(3)
    expect(firstUnreadMessageKey(rows, 2)).toBe('a2')
    expect(firstUnreadMessageKey(rows, null)).toBeNull()
  })

  it('falls back to the last message when marked unread without a cursor', () => {
    expect(effectiveUnreadWatermark(false, 1, 3)).toBeNull()
    expect(effectiveUnreadWatermark(true, null, 3)).toBe(2)
    expect(effectiveUnreadWatermark(true, 3, 3)).toBe(2)
    expect(effectiveUnreadWatermark(true, 1, 3)).toBe(1)
  })
})
