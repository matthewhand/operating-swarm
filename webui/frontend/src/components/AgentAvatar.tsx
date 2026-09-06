import { useEffect, useState } from 'react'
import { useGeneratedAvatar } from '../lib/agentAvatars'
import { isGeneratedStillSrc } from '../lib/imageGenSettings'
import { useAvatarTheme } from '../lib/useAvatarTheme'
import type { AgentStatus } from '../types/agent'
import BlobAvatar from './BlobAvatar'
import BeeAvatar from './BeeAvatar'
import { Robot3DAvatar } from './Robot3DAvatar'

/**
 * Bland circular fallback — not the Bert-like default owned by REQ-6 (#309).
 * Custom `src` wins; a broken image falls back here instead of a broken-icon.
 */
export const DEFAULT_AGENT_AVATAR_SRC =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" role="img" aria-hidden="true">
      <circle cx="20" cy="20" r="20" fill="#2a2a2a"/>
      <circle cx="20" cy="16" r="7" fill="#8a8a8a"/>
      <ellipse cx="20" cy="36" rx="12" ry="10" fill="#8a8a8a"/>
    </svg>`,
  )

export type AgentAvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

export interface AgentAvatarProps {
  /** Custom face URL. Blank / missing / broken uses the themed default (or bland if selected in settings). */
  src?: string | null
  alt?: string
  size?: AgentAvatarSize
  className?: string
  agentId?: string | null
  active?: boolean
  /** Agent working/listen/error state — drives the 3D robot clips (REQ-194 Phase 3). */
  status?: AgentStatus
  /** ADR-008 §2: enable the WebGL pose-player (chat header only — one GL context). */
  gl?: boolean
  style?: React.CSSProperties
}

export function resolveAgentAvatarSrc(src?: string | null): string {
  const trimmed = typeof src === 'string' ? src.trim() : ''
  return trimmed || DEFAULT_AGENT_AVATAR_SRC
}

export function agentAvatarKind(src?: string | null): 'custom' | 'default' {
  return resolveAgentAvatarSrc(src) === DEFAULT_AGENT_AVATAR_SRC ? 'default' : 'custom'
}

/**
 * Shared agent face for the rail tile, favourites large tiles, and the chat header.
 * Display-only: no click handler. Sizes: rail sm, header/favs lg.
 * Unset or broken avatars resolve to Blobs-with-eyes by default (REQ-155),
 * Bee geometric brand marks when that theme is chosen (#801),
 * or bland static circles when opt-in chosen in Settings. Uploaded custom
 * faces always win. Generated stills (REQ-83) apply on Bland/Default and
 * stay unused while Blobs or Bee is selected.
 */
export default function AgentAvatar({
  src,
  alt = '',
  size = 'sm',
  className = '',
  agentId,
  active = false,
  status = 'idle',
  gl = false,
  style,
}: AgentAvatarProps) {
  const [broken, setBroken] = useState(false)
  const theme = useAvatarTheme()
  const generatedSrc = useGeneratedAvatar(agentId)

  useEffect(() => {
    setBroken(false)
  }, [src, generatedSrc])

  const customSrc = typeof src === 'string' ? src.trim() : ''
  const uploadedSrc =
    customSrc && !isGeneratedStillSrc(customSrc) ? customSrc : ''
  const stillSrc =
    uploadedSrc ||
    (customSrc && isGeneratedStillSrc(customSrc) ? customSrc : '') ||
    generatedSrc
  const showGeneratedStill = Boolean(
    stillSrc && !uploadedSrc && theme !== 'blobs' && theme !== 'bee',
  )
  const showUploaded = Boolean(uploadedSrc && !broken)
  const isCustom = showUploaded || (showGeneratedStill && !broken)

  if (isCustom) {
    const faceSrc = uploadedSrc || stillSrc
    return (
      <div
        className={`avatar ${className}`.trim()}
        data-agent-avatar="custom"
        data-avatar-size={size}
        data-avatar-still={showGeneratedStill ? 'generated' : undefined}
        aria-hidden={alt ? undefined : true}
        style={style}
      >
        <div className={`os-agent-avatar os-agent-avatar--${size} rounded-full`}>
          <img
            src={faceSrc}
            alt={alt}
            draggable={false}
            data-agent-avatar="custom"
            onError={() => setBroken(true)}
          />
        </div>
      </div>
    )
  }

  // Unset or broken face -> resolve via avatar theme
  if (theme === 'robot3d') {
    return (
      <div
        className={`avatar ${className}`.trim()}
        data-agent-avatar="default"
        data-avatar-theme="robot3d"
        data-avatar-size={size}
        aria-hidden={alt ? undefined : true}
        style={style}
      >
        <Robot3DAvatar agentId={agentId} status={status} size={size} gl={gl} />
      </div>
    )
  }

  if (theme === 'bee') {
    return (
      <div
        className={`avatar ${className}`.trim()}
        data-agent-avatar="default"
        data-avatar-theme="bee"
        data-avatar-size={size}
        data-eye-state={active ? 'active' : 'idle'}
        aria-hidden={alt ? undefined : true}
        style={style}
      >
        <BeeAvatar
          agentId={agentId || 'agent'}
          active={active}
          size={size}
          className=""
        />
      </div>
    )
  }

  if (theme === 'blobs') {
    return (
      <div
        className={`avatar ${className}`.trim()}
        data-agent-avatar="default"
        data-avatar-theme="blobs"
        data-avatar-size={size}
        data-eye-state={active ? 'active' : 'idle'}
        aria-hidden={alt ? undefined : true}
        style={style}
      >
        <BlobAvatar
          agentId={agentId || 'agent'}
          active={active}
          size={size}
          className=""
        />
      </div>
    )
  }

  // Bland static fallback
  return (
    <div
      className={`avatar ${className}`.trim()}
      data-agent-avatar="default"
      data-avatar-size={size}
      aria-hidden={alt ? undefined : true}
      style={style}
    >
      <div className={`os-agent-avatar os-agent-avatar--${size} rounded-full`}>
        <img
          src={DEFAULT_AGENT_AVATAR_SRC}
          alt={alt}
          draggable={false}
          data-agent-avatar="default"
        />
      </div>
    </div>
  )
}
