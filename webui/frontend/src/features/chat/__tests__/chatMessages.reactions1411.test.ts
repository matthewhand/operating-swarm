import { describe, expect, it } from 'vitest'
import { assistantCompletionSnippet, chatMessageFromThreadRow } from '../chatMessages'

describe('chatMessageFromThreadRow reactions (#1411)', () => {
  it('hydrates palette pills from the thread payload', () => {
    const row = chatMessageFromThreadRow(
      {
        role: 'assistant',
        content: 'done',
        reactions: [{ emoji: '✅', count: 1, agentReacted: true }],
      },
      1,
    )
    expect(row.reactions).toEqual([
      { emoji: '✅', count: 1, userReacted: false, agentReacted: true, viewerReacted: false },
    ])
  })
})

describe('reaction-only hydrate (#1411)', () => {
  it('hydrates a reaction-only turn with empty text', () => {
    const row = chatMessageFromThreadRow(
      {
        role: 'assistant',
        content: '',
        reaction_only: true,
        reactions: [{ emoji: '👍', count: 1, agentReacted: true }],
      },
      1,
    )
    expect(row.reactionOnly).toBe(true)
    expect(row.text).toBe('')
    expect(row.reactions?.[0]?.emoji).toBe('👍')
  })

  it('does not hydrate an empty shell when the emoji is not in the palette', () => {
    const row = chatMessageFromThreadRow(
      {
        role: 'assistant',
        content: '',
        reaction_only: true,
        reactions: [{ emoji: '🔥', count: 1, agentReacted: true }],
      },
      2,
    )
    expect(row.reactionOnly).toBe(false)
    expect(row.reactions).toEqual([])
  })
})

describe('assistantCompletionSnippet (#1411)', () => {
  it('uses the reaction emoji instead of the previous text reply', () => {
    expect(
      assistantCompletionSnippet([
        { key: 'a', role: 'assistant', text: 'landed', streaming: false },
        {
          key: 'b',
          role: 'assistant',
          text: '',
          streaming: false,
          reactionOnly: true,
          reactions: [{ emoji: '👍', count: 1, agentReacted: true }],
        },
      ]),
    ).toBe('👍')
  })
})
