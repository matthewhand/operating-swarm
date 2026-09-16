import { describe, expect, it } from 'vitest'
import {
  buildDisplayItems,
  contextTextsForMeter,
  outermostSummaries,
  rawOffsetForMessage,
  type ChatBubble,
  type ConversationSummary,
} from '../chatCompact'

function bubble(key: string, role: 'user' | 'assistant', text: string): ChatBubble {
  return { key, role, text, streaming: false }
}

function summary(
  id: number,
  start: number,
  end: number,
  body: string,
  parent: number | null = null,
): ConversationSummary {
  return {
    id,
    conversation_id: 'c1',
    span: { start, end },
    parent_summary_id: parent,
    body,
    created_at: '2026-09-03T00:00:00Z',
    replaced_count: end - start + 1,
  }
}

describe('buildDisplayItems', () => {
  const messages = [
    bubble('1', 'user', 'one'),
    bubble('2', 'assistant', 'two'),
    bubble('3', 'user', 'three'),
    bubble('4', 'assistant', 'four'),
  ]

  it('returns raw bubbles when there are no summaries', () => {
    const items = buildDisplayItems(messages, [])
    expect(items.every((item) => item.kind === 'message')).toBe(true)
    expect(items).toHaveLength(4)
  })

  it('replaces a covered span with a bordered summary item', () => {
    const items = buildDisplayItems(messages, [summary(1, 0, 1, 'first pair')])
    expect(items[0]).toMatchObject({ kind: 'summary', summary: { id: 1, body: 'first pair' } })
    expect(items[1]).toMatchObject({ kind: 'message', message: { text: 'three' } })
    expect(items[2]).toMatchObject({ kind: 'message', message: { text: 'four' } })
  })

  it('nests parent_summary_id so only the outer summary is a top-level item', () => {
    const inner = summary(1, 0, 1, 'inner')
    const outer = summary(2, 0, 3, 'outer', 1)
    const items = buildDisplayItems(messages, [inner, outer])
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ kind: 'summary', summary: { id: 2, parent_summary_id: 1 } })
    expect(outermostSummaries([inner, outer]).map((row) => row.id)).toEqual([2])
  })
})

describe('contextTextsForMeter', () => {
  it('counts summary body instead of covered raw turns', () => {
    const messages = [bubble('1', 'user', 'aaaaaaaa'), bubble('2', 'assistant', 'bbbbbbbb')]
    const texts = contextTextsForMeter(messages, [summary(1, 0, 1, 'short')])
    expect(texts).toEqual(['short'])
  })

  it('drops unticked summaries from the meter (#214 / #215)', () => {
    const messages = [
      bubble('1', 'user', 'aaaaaaaa'),
      bubble('2', 'assistant', 'bbbbbbbb'),
      bubble('3', 'user', 'later'),
    ]
    const archived = { ...summary(1, 0, 1, 'short'), include_in_context: false }
    expect(contextTextsForMeter(messages, [archived])).toEqual(['later'])
  })

  it('excludes status/info chrome from the meter (REQ-70)', () => {
    const messages: ChatBubble[] = [
      { key: 's', role: 'status', text: 'CLI: antigravity → grok', streaming: false },
      bubble('1', 'user', 'hello'),
      bubble('2', 'assistant', 'hi'),
    ]
    expect(contextTextsForMeter(messages, [])).toEqual(['hello', 'hi'])
  })

  it('maps a hovered bubble to a raw offset skipping status chrome', () => {
    const messages: ChatBubble[] = [
      { key: 's', role: 'status', text: 'info', streaming: false },
      bubble('1', 'user', 'one'),
      bubble('2', 'assistant', 'two'),
      bubble('3', 'user', 'three'),
    ]
    expect(rawOffsetForMessage(messages, '1')).toBe(0)
    expect(rawOffsetForMessage(messages, '3')).toBe(2)
    expect(rawOffsetForMessage(messages, 'missing')).toBe(-1)
  })
})
