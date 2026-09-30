import AgentAvatar from './AgentAvatar'
import {
  avatarShapeClass,
  type AgentProfile,
} from '../lib/agentProfile'

export interface AgentProfilePreviewProps {
  agentId: string
  profile: AgentProfile
  fallbackName?: string
  caption?: string
}

/**
 * Compact storefront card used by the editor and template pack screens.
 * Name / title / description / avatar chrome only — never secrets.
 */
export default function AgentProfilePreview({
  agentId,
  profile,
  fallbackName = '',
  caption = 'Profile preview',
}: AgentProfilePreviewProps) {
  const name = profile.display_name.trim() || fallbackName || agentId
  const title = profile.title.trim()
  const description = profile.description.trim()
  return (
    <div
      className="flex items-start gap-3 rounded-box border border-base-300 bg-base-200/40 p-3"
      data-testid="agent-profile-preview"
      data-avatar-shape={profile.avatar_shape}
      data-avatar-color={profile.avatar_color || undefined}
    >
      <div
        className={`shrink-0 ${avatarShapeClass(profile.avatar_shape)}`}
        data-testid="agent-profile-preview-face"
      >
        <AgentAvatar
          agentId={agentId}
          src={profile.avatar_path}
          alt=""
          size="lg"
          className="shrink-0"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-wide text-base-content/50">{caption}</p>
        <p className="text-sm font-semibold truncate" data-testid="agent-profile-preview-name">
          {name}
        </p>
        {title ? (
          <p className="text-xs text-base-content/70 truncate" data-testid="agent-profile-preview-title">
            {title}
          </p>
        ) : null}
        {description ? (
          <p
            className="text-xs text-base-content/60 mt-0.5 line-clamp-2"
            data-testid="agent-profile-preview-description"
          >
            {description}
          </p>
        ) : (
          <p className="text-xs text-base-content/45 mt-0.5">No storefront description yet.</p>
        )}
      </div>
    </div>
  )
}
