import { describe, expect, it } from 'vitest'
import {
  formatChromeTime,
  messagesFromThreadPayload,
  reconstructTranscript,
  splitMixedMessages,
  turnIndexFromDisplay,
} from '../transcriptReconstruct'

describe('reconstructTranscript', () => {
  it('interleaves turns and ui_events by seq', () => {
    const display = reconstructTranscript(
      [
        { role: 'user', content: 'hi', seq: 0 },
        { role: 'assistant', content: 'hello', seq: 2 },
      ],
      [{ role: 'status', content: 'Started a new grok session.', ts: '2026-09-05T12:00:00Z', seq: 1 }],
    )
    expect(display.map((row) => row.role)).toEqual(['user', 'status', 'assistant'])
    expect(display[1]?.ts).toBe('2026-09-05T12:00:00Z')
  })
})

describe('messagesFromThreadPayload', () => {
  it('prefers turns + ui_events over mixed messages', () => {
    const display = messagesFromThreadPayload({
      messages: [{ role: 'user', content: 'stale mixed' }],
      turns: [{ role: 'user', content: 'hi', seq: 0 }],
      ui_events: [{ role: 'info', content: 'Rate limited — retrying with grok', ts: '2026-09-05T12:00:00Z', seq: 1 }],
    })
    expect(display).toEqual([
      { role: 'user', content: 'hi' },
      {
        role: 'status',
        content: 'Rate limited — retrying with grok',
        ts: '2026-09-05T12:00:00Z',
      },
    ])
  })

  it('splits mixed messages when no side channel is present', () => {
    const split = splitMixedMessages([
      { role: 'user', content: 'hi' },
      { role: 'status', content: 'CLI: antigravity → grok', ts: '2026-09-05T12:00:00Z' },
      { role: 'assistant', content: 'ok' },
    ])
    expect(split.turns.map((row) => row.role)).toEqual(['user', 'assistant'])
    expect(split.events[0]?.content).toBe('CLI: antigravity → grok')
  })

  it('keeps #1411 reactions on reconstructed turns', () => {
    const display = messagesFromThreadPayload({
      messages: [
        {
          role: 'user',
          content: 'hi',
          reactions: [{ emoji: '👍', count: 1, userReacted: true }],
        },
      ],
    })
    expect(display[0]?.reactions).toEqual([
      { emoji: '👍', count: 1, userReacted: true, agentReacted: false, viewerReacted: false },
    ])
  })
})

describe('turnIndexFromDisplay', () => {
  it('maps a display index past chrome onto the model-turn list', () => {
    const rows = [
      { role: 'user' },
      { role: 'status' },
      { role: 'assistant' },
    ]
    expect(turnIndexFromDisplay(rows, 0)).toBe(0)
    expect(turnIndexFromDisplay(rows, 2)).toBe(1)
  })
})

describe('formatChromeTime', () => {
  it('returns an ISO string for a valid timestamp', () => {
    expect(formatChromeTime('2026-09-05T12:00:00Z')).toBe('2026-09-05T12:00:00.000Z')
  })
})

describe('reaction-only reconstruct (#1411)', () => {
it('keeps a reaction-only turn with empty content (#1411)', () => {
    const display = reconstructTranscript(
      [
        {
          role: 'assistant',
          content: '',
          reaction_only: true,
          reactions: [{ emoji: '👍', count: 1, agentReacted: true }],
          seq: 1,
        },
      ],
      [],
    )
    expect(display[0]?.content).toBe('')
    expect(display[0]?.reactionOnly).toBe(true)
    expect(display[0]?.reactions?.[0]?.emoji).toBe('👍')
  })

  it('drops the reaction-only flag when no palette emoji survived', () => {
    const display = reconstructTranscript(
      [
        {
          role: 'assistant',
          content: '',
          reaction_only: true,
          reactions: [{ emoji: '🔥', count: 1, agentReacted: true }],
          seq: 1,
        },
      ],
      [],
    )
    expect(display[0]?.reactionOnly).toBeUndefined()
    expect(display[0]?.reactions).toBeUndefined()
  })
})
