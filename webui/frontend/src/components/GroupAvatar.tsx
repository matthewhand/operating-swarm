import AgentAvatar from './AgentAvatar'
// #1692: one avatar-URL precedence for every seat surface.
import { seatAvatarSrc } from '../lib/seatAvatar'
import type { AgentStatus } from '../types/agent'

/**
 * #1362 — group-chat avatar.
 *
 * A group chat is a chat you add agents to, so its face is the *membership*
 * rather than one seat. Up to {@link GROUP_AVATAR_MAX_FACES} member avatars
 * are arranged on a circle (1 centred, 2 on a diagonal, 3 in a triangle);
 * any remaining members collapse to a `+N` badge in the middle of the ring.
 *
 * The face geometry lives in CSS (`index.css`, `.os-group-avatar`) keyed off
 * `data-count`, so the same component is legible at rail (`sm`) and navbar
 * (`lg`) sizes with no layout shift — the frame is a fixed square and every
 * face is positioned inside it. Colours are theme tokens only.
 */

/** A group chat never fans more than this many member faces; the rest → `+N`. */
export const GROUP_AVATAR_MAX_FACES = 3

export type GroupAvatarSize = 'xs' | 'sm' | 'md' | 'lg'

export interface GroupAvatarMember {
  /** Stable member id (roster member id / agent id). */
  id: string
  /** Display name, used for the face `alt`/title and the a11y label. */
  name?: string
  /** Explicit avatar agent id when it differs from `id` (e.g. blueprint mark). */
  agentId?: string
  /** Same fallbacks the rail/chat faces use. */
  markId?: string
  src?: string | null
  avatarSrc?: string | null
  /** Working members get the live pulsing ring (disabled under reduced motion). */
  working?: boolean
  status?: AgentStatus
}

export interface GroupAvatarPlan<T extends GroupAvatarMember = GroupAvatarMember> {
  /** The faces actually rendered (at most `maxFaces`). */
  faces: T[]
  /** Members beyond the cap — rendered as `+N`. */
  remainder: number
  /** Total membership, including the capped remainder. */
  total: number
}

/**
 * Select the faces for a group avatar. Deterministic: roster order is kept, the
 * first `maxFaces` render, the rest become the remainder. Never mutates input.
 */
export function groupAvatarPlan<T extends GroupAvatarMember>(
  members: readonly T[],
  maxFaces: number = GROUP_AVATAR_MAX_FACES,
): GroupAvatarPlan<T> {
  const list = Array.isArray(members) ? members.filter(Boolean) : []
  const cap = Math.max(0, Math.floor(maxFaces))
  const faces = list.slice(0, cap)
  return { faces, remainder: Math.max(0, list.length - faces.length), total: list.length }
}

export interface GroupAvatarProps {
  members: readonly GroupAvatarMember[]
  /** Rail (`sm`) and navbar (`lg`) are the sizes the design targets. */
  size?: GroupAvatarSize
  /** Override the face cap. Defaults to {@link GROUP_AVATAR_MAX_FACES}. */
  maxFaces?: number
  className?: string
  /** Accessible name; falls back to the member names. */
  label?: string
}

export default function GroupAvatar({
  members,
  size = 'sm',
  maxFaces = GROUP_AVATAR_MAX_FACES,
  className = '',
  label,
}: GroupAvatarProps) {
  const { faces, remainder, total } = groupAvatarPlan(members, maxFaces)
  if (total === 0) return null

  const names = faces.map((face) => face.name || face.id).filter(Boolean)
  const described = `${total} member${total === 1 ? '' : 's'}: ${names.join(', ')}`
  const ariaLabel = label || described

  return (
    <span
      className={`os-group-avatar ${className}`.trim()}
      data-testid="os-group-avatar"
      data-avatar-stack={total > 1 ? 'true' : 'false'}
      data-count={String(faces.length)}
      data-stack-count={String(faces.length)}
      data-member-count={String(total)}
      data-remainder={String(remainder)}
      data-size={size}
      role="img"
      aria-label={ariaLabel}
      title={described}
    >
      {faces.map((face, index) => (
        <span
          key={face.id}
          className={`os-group-avatar__face${face.working ? ' os-group-avatar__face--working' : ''}`}
          data-testid="os-group-avatar-face"
          data-face-index={String(index)}
          data-face-id={face.id}
        >
          <AgentAvatar
            agentId={face.agentId || face.markId || face.id}
            src={seatAvatarSrc(face)}
            alt={face.name || face.id}
            size="xs"
            status={face.working ? 'working' : face.status ?? 'idle'}
            active={Boolean(face.working)}
          />
        </span>
      ))}
      {remainder > 0 ? (
        <span
          className="os-group-avatar__remainder"
          data-testid="os-group-avatar-remainder"
          data-remainder-count={String(remainder)}
          aria-hidden="true"
        >
          +{remainder}
        </span>
      ) : null}
    </span>
  )
}
