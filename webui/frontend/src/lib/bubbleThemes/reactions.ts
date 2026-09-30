/**
 * Reaction emoji sets owned by each bubble theme (#1411).
 *
 * Speech is the full palette. Simple and IRC define smaller sets.
 * Keep in sync with THEME_REACTION_EMOJIS in src/swarm/core/message_reactions.py.
 */
export const THEME_REACTION_EMOJIS = {
  speech: ['👍', '👎', '❤️', '😂', '🎉', '👀', '🚀', '✅'],
  simple: ['👍', '👎', '❤️', '😂', '✅'],
  irc: ['👍', '👎', '👀', '🎉'],
} as const

export type ReactionThemeId = keyof typeof THEME_REACTION_EMOJIS

export function reactionEmojisForTheme(theme: string | undefined | null): readonly string[] {
  if (theme === 'simple' || theme === 'irc' || theme === 'speech') {
    return THEME_REACTION_EMOJIS[theme]
  }
  return THEME_REACTION_EMOJIS.speech
}

export function allReactionEmojis(): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const set of Object.values(THEME_REACTION_EMOJIS)) {
    for (const emoji of set) {
      if (seen.has(emoji)) continue
      seen.add(emoji)
      out.push(emoji)
    }
  }
  return out
}
