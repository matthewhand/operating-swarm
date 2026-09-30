/**
 * #1372 — empty composer placeholder is `Message <display name>`.
 *
 * Uses the same display name the navbar / Edit agent already resolve
 * (`selectedAgentName` / `editedAgentLabel`). HTML placeholder text only
 * appears while the input is empty; this helper never touches send, queue,
 * mic, or routing.
 */

export const COMPOSER_PLACEHOLDER_FALLBACK = 'Message …'
export const COMPOSER_REPLY_PLACEHOLDER = 'Reply…'

/** Reject empty, whitespace, and the JS-coercion leftovers `undefined`/`null`. */
export function usableComposerDisplayName(name: unknown): string | null {
  if (typeof name !== 'string') return null
  const trimmed = name.trim()
  if (!trimmed || trimmed === 'undefined' || trimmed === 'null') return null
  return trimmed
}

export function composerEmptyPlaceholder(
  displayName: unknown,
  options?: { reply?: boolean },
): string {
  if (options?.reply) return COMPOSER_REPLY_PLACEHOLDER
  const name = usableComposerDisplayName(displayName)
  return name ? `Message ${name}` : COMPOSER_PLACEHOLDER_FALLBACK
}
