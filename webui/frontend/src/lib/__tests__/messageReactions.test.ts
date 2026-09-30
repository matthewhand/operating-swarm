import { describe, expect, it } from 'vitest'
import { getBubbleTheme } from '../bubbleTheme'
import {
  REACTION_EMOJIS,
  THEME_REACTION_EMOJIS,
  isReactionEmoji,
  parseMessageReactions,
  reactionEmojisForTheme,
  toggleUserReaction,
} from '../messageReactions'

describe('messageReactions (#1411)', () => {
  it('accepts only the eight palette emoji', () => {
    expect(REACTION_EMOJIS).toEqual(['👍', '👎', '❤️', '😂', '🎉', '👀', '🚀', '✅'])
    expect(isReactionEmoji('👍')).toBe(true)
    expect(isReactionEmoji('🔥')).toBe(false)
  })

  it('parses public wire rows and drops unknowns', () => {
    expect(
      parseMessageReactions([
        { emoji: '👍', count: 2, userReacted: true, agentReacted: true },
        { emoji: '🔥', count: 1 },
        { emoji: '👍', count: 9 },
      ]),
    ).toEqual([
      { emoji: '👍', count: 2, userReacted: true, agentReacted: true, viewerReacted: false },
    ])
  })

  it('toggles the operator reaction on and off', () => {
    const added = toggleUserReaction([], '🎉')
    expect(added).toEqual([{ emoji: '🎉', count: 1, userReacted: true, viewerReacted: true }])
    const removed = toggleUserReaction(added, '🎉')
    expect(removed).toEqual([])
    const shared = toggleUserReaction(
      [{ emoji: '👀', count: 2, userReacted: false, agentReacted: true }],
      '👀',
    )
    expect(shared[0]).toMatchObject({ emoji: '👀', count: 3, userReacted: true })
  })
})


describe('theme-defined reaction sets (#1411)', () => {
  it('lets each bubble theme own its emoji set', () => {
    expect(getBubbleTheme('speech').reactionEmojis()).toEqual([...THEME_REACTION_EMOJIS.speech])
    expect(getBubbleTheme('simple').reactionEmojis()).toEqual([...THEME_REACTION_EMOJIS.simple])
    expect(getBubbleTheme('irc').reactionEmojis()).toEqual([...THEME_REACTION_EMOJIS.irc])
    expect(reactionEmojisForTheme('irc')).not.toContain('🚀')
    expect(REACTION_EMOJIS).toContain('🚀')
  })
})
