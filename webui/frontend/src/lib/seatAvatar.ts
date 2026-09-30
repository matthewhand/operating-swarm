/**
 * #1692 — ONE avatar contract for a seat's identity face.
 *
 * The same agent used to render two different avatars depending on which pane
 * you looked at, because the chat header's face carried hero-only props that
 * no other seat surface passed:
 *
 *   - `size="lg"` — the header drew the agent at 48px where the rail row drew
 *     it at 32px (`rowsRender.tsx`), so one agent wore two sizes.
 *   - `gl`        — ADR-008 §2's single WebGL pose context. For the `robot3d`
 *     theme that made the header a live 3D mesh while every other surface
 *     showed the static SVG fallback: the same agent, a different avatar.
 *
 * Both arrived the same way — a prop added to ONE call site. A split identity
 * is the same class of defect as #1362's two sources of truth for team
 * membership: several components each resolve "who is this agent" by their own
 * path and the paths disagree.
 *
 * So the decision lives here, once, and both seat call sites read it:
 * the size tier, whether a seat face may take a WebGL context, and the avatar
 * URL precedence for the four accumulated field names.
 *
 * Why the precedence is `avatarSrc → avatar_path → avatar → src`: those names
 * are accumulated, not designed. `avatar_path` is the live-config field the
 * backend persists, and `avatarSrc` is the normalized value a caller has
 * already resolved from it — so `avatarSrc` wins where a caller bothered to
 * normalize, and the looser roster spellings are the last resort. The same
 * order was already used by `sessionPicker` and by ChatPage's
 * `headerGroupMembers`; the other call sites used a two-name subset, which is
 * exactly the kind of half-implementation that lets two panes disagree.
 *
 * ADR-008 §2 allows ONE WebGL pose context. The header mount is a 32px pill,
 * not a chat hero, so no seat face takes one: {@link SEAT_AVATAR_GL} is false
 * and both seat call sites pass it explicitly rather than relying on the
 * component default, so the invariant is greppable. A genuine GL hero
 * re-introduces the prop in exactly one place — and the #1692 suite fails if a
 * second site appears.
 */

/** The one size tier a seat's identity face renders at: the rail row and the
 *  chat-header pill. Tiles, stacks and bubbles are different affordances and
 *  declare their own tier. */
export const SEAT_AVATAR_SIZE = 'sm' as const

/** ADR-008 §2: a 32px seat face is not a chat hero. See the module note. */
export const SEAT_AVATAR_GL = false

/**
 * The four field names an agent/roster row may carry its face under, in
 * precedence order. One list, so no call site invents its own subset.
 */
export const SEAT_AVATAR_SRC_FIELDS = [
  'avatarSrc',
  'avatar_path',
  'avatar',
  'src',
] as const

/**
 * The one avatar-URL resolver. Returns the first non-blank string among
 * {@link SEAT_AVATAR_SRC_FIELDS}, or `null` so an absent face falls through to
 * `AgentAvatar`'s themed default rather than rendering a broken image.
 */
export function seatAvatarSrc(row: unknown): string | null {
  if (!row || typeof row !== 'object') return null
  const bag = row as Record<string, unknown>
  for (const field of SEAT_AVATAR_SRC_FIELDS) {
    const value = bag[field]
    if (typeof value !== 'string') continue
    const trimmed = value.trim()
    if (trimmed) return trimmed
  }
  return null
}
