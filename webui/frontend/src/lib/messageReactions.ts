/**
 * Chat message emoji reactions (#1411).
 *
 * Small Slack-style palette shared with `swarm.core.message_reactions`.
 * Wire rows store `{ emoji, count, userReacted, agentReacted }`.
 */

import { allReactionEmojis, reactionEmojisForTheme, THEME_REACTION_EMOJIS } from './bubbleThemes/reactions'

export { reactionEmojisForTheme, THEME_REACTION_EMOJIS }

/** Speech palette — the widest theme set. Other themes are subsets. */
export const REACTION_EMOJIS = THEME_REACTION_EMOJIS.speech

export type ReactionEmoji = (typeof REACTION_EMOJIS)[number]

export interface MessageReaction {
  emoji: string
  count: number
  userReacted?: boolean
  agentReacted?: boolean
  viewerReacted?: boolean
}

const EMOJI_SET = new Set<string>(allReactionEmojis())

export function isReactionEmoji(value: unknown): value is ReactionEmoji {
  return typeof value === 'string' && EMOJI_SET.has(value)
}

export function parseMessageReactions(value: unknown): MessageReaction[] {
  if (!Array.isArray(value)) return []
  const out: MessageReaction[] = []
  const seen = new Set<string>()
  for (const item of value) {
    if (!item || typeof item !== 'object') continue
    const row = item as {
      emoji?: unknown
      count?: unknown
      userReacted?: unknown
      agentReacted?: unknown
      viewerReacted?: unknown
    }
    if (!isReactionEmoji(row.emoji) || seen.has(row.emoji)) continue
    const count = typeof row.count === 'number' && row.count > 0 ? Math.floor(row.count) : 1
    seen.add(row.emoji)
    out.push({
      emoji: row.emoji,
      count,
      userReacted: row.userReacted === true,
      agentReacted: row.agentReacted === true,
      viewerReacted: row.viewerReacted === true,
    })
  }
  return out
}

/** Optimistic toggle of the operator's own reaction on a display row. */
export function toggleUserReaction(
  reactions: MessageReaction[] | undefined,
  emoji: string,
): MessageReaction[] {
  if (!isReactionEmoji(emoji)) return reactions ?? []
  const current = parseMessageReactions(reactions)
  const existing = current.find((row) => row.emoji === emoji)
  if (!existing) {
    return [...current, { emoji, count: 1, userReacted: true, viewerReacted: true }]
  }
  if (existing.userReacted) {
    const nextCount = existing.count - 1
    if (nextCount <= 0) return current.filter((row) => row.emoji !== emoji)
    return current.map((row) =>
      row.emoji === emoji
        ? { ...row, count: nextCount, userReacted: false, viewerReacted: false }
        : row,
    )
  }
  return current.map((row) =>
    row.emoji === emoji
      ? { ...row, count: row.count + 1, userReacted: true, viewerReacted: true }
      : row,
  )
}
