/**
 * #1240 — turn slug-shaped seat ids/names into human-readable labels.
 *
 * The catalog's `name` field often *is* the slug (`software_dev`), and seat
 * ids are kebab-case by doctrine. Labels shown to humans (navbar, working
 * indicator) must not echo that shape. This is deliberately conservative:
 * only lowercase slug-looking inputs are transformed; anything with spaces,
 * mixed case, or digits passes through untouched so renames like "CoS" or
 * "Hermes" survive verbatim.
 */

/** A slug-looking word: all-lowercase letters (separators allowed between). */
const SLUG_RE = /^[a-z][a-z0-9]*(?:[-_ ][a-z][a-z0-9]*)*$/

/**
 * `general-assistant` → `General Assistant`; `software_dev` → `Software Dev`.
 * Returns ``''`` for empty input and passes non-slug strings through as-is.
 */
export function humanizeAgentSlug(raw: string | null | undefined): string {
  const value = (raw ?? '').trim()
  if (!value) return ''
  if (!SLUG_RE.test(value)) return value
  return value
    .split(/[-_ ]+/)
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(' ')
}
