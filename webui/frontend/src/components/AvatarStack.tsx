import { agentMarkIndex } from '../lib/hiddenAgents'
import AgentAvatar from './AgentAvatar'
import {
  STACK_FACE_LIMIT,
  earliestStartedAt,
  isAvatarStack,
  selectStackedFaces,
  stackAnimationDelayMs,
  type StackFace,
} from '../lib/avatarStack'

export type { StackFace }

export interface AvatarStackProps {
  faces: readonly StackFace[]
  /** When omitted, extras beyond `maxFaces` become the remainder. */
  remainder?: number
  /** Override the rail cap (tests may render 4 faces). Default 3. */
  maxFaces?: number
  /**
   * Animate every face (REQ-66 addendum / #398 addendum).
   * Default true — idle vs working is a caller concern, not this widget.
   */
  animate?: boolean
  className?: string
  label?: string
}

/**
 * Reusable hop-style stack: overlapping circular faces, then +N.
 *
 * Scale-out agents (#394) and later teams/remotes (#398) share this widget.
 * Do not fork it in the REQ-68 PR — import `AvatarStack` and `selectStackedFaces`.
 */
export default function AvatarStack({
  faces,
  remainder,
  maxFaces = STACK_FACE_LIMIT,
  animate = true,
  className = '',
  label,
}: AvatarStackProps) {
  const planned =
    remainder == null
      ? selectStackedFaces(faces, maxFaces)
      : {
          faces: faces.slice(0, Math.max(0, maxFaces)),
          remainder,
        }
  const shown = planned.faces
  const extra = planned.remainder
  if (shown.length === 0) return null

  const origin = earliestStartedAt(shown)
  const stacked = isAvatarStack(shown.length, extra)

  return (
    <span
      className={`os-stacked-avatars ${className}`.trim()}
      data-avatar-stack={stacked ? 'true' : 'false'}
      data-stack-count={String(shown.length)}
      data-face-count={String(shown.length)}
      data-remainder={String(extra)}
      aria-label={label}
    >
      {shown.map((face) => (
        <span
          key={face.id}
          className={`os-stacked-avatar os-avatar-stack__face os-stacked-avatar--stacked overflow-hidden flex items-center justify-center${
            animate ? ' os-stacked-avatar--pulse' : ''
          }${face.working ? ' os-avatar-stack__face--working' : ''}`}
          data-testid="os-stacked-avatar"
          data-face-id={face.id}
          data-session-id={face.id}
          data-started-at={String(face.startedAt)}
          data-mark={String(agentMarkIndex(face.markId || face.id))}
          data-role={face.role}
          title={face.name}
          style={{
            backgroundColor: 'transparent',
            overflow: 'hidden',
            ...(animate
              ? { animationDelay: `${stackAnimationDelayMs(face.startedAt, origin)}ms` }
              : {}),
          }}
        >
          <AgentAvatar
            agentId={face.agentId || face.id}
            src={face.avatarSrc || face.src}
            alt={face.name || face.id}
            size="xs"
            status={face.working ? 'working' : 'idle'}
            active={Boolean(face.working)}
            className="w-full h-full flex items-center justify-center"
            style={{ background: 'transparent' }}
          />
        </span>
      ))}
      {extra > 0 ? (
        <span
          className="os-stacked-remainder"
          data-testid="os-stacked-remainder"
          data-remainder-count={String(extra)}
        >
          +{extra}
        </span>
      ) : null}
    </span>
  )
}
