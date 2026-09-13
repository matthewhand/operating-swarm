import {
  useEffect,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react'
import { useGeneratedAvatar } from '../lib/agentAvatars'
import { hashAgentId } from '../lib/blobAvatar'
import { isGeneratedStillSrc } from '../lib/imageGenSettings'
import { useAgentStore } from '../lib/agent-store'
import {
  isRobotPackTheme,
  resolveAvatarTheme,
} from '../lib/avatarTheme'
import { useAvatarTheme, useEnabledAvatarThemes } from '../lib/useAvatarTheme'
import type { AgentStatus, AvatarEyes, AvatarTheme } from '../types/agent'
import BlobAvatar from './BlobAvatar'
import BeeAvatar from './BeeAvatar'
import { Robot3DAvatar } from './Robot3DAvatar'
import { RobotAvatar } from './AgentSidebar/RobotAvatar'
import AgentThemePreviewDialog from './AgentThemePreviewDialog'
import { chooseThemeLabel } from './AgentThemeChooser'

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

const AVATAR_SIZE_PX: Record<AgentAvatarSize, number> = {
  xs: 24,
  sm: 32,
  md: 40,
  lg: 48,
  xl: 56,
}

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
  style?: CSSProperties
  /** Forced look (preview tiles). Skips per-agent / global resolve. */
  theme?: AvatarTheme
  /** Opt-in click-to-choose. Rail/pins stay false so left-click selects chat. */
  interactive?: boolean
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
 * Header may opt into click-to-choose (REQ-840). Rail and pins use the right-click
 * Choose theme item so left-click still selects and chats.
 * Unset or broken avatars resolve per-agent theme, then the sole enabled
 * theme, then the global default (REQ-828). Uploaded custom faces always win.
 * Generated stills (REQ-83) apply on Bland/Default and stay unused while
 * Blobs or Bee is selected.
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
  theme: forcedTheme,
  interactive,
}: AgentAvatarProps) {
  const [broken, setBroken] = useState(false)
  const [open, setOpen] = useState(false)
  const globalTheme = useAvatarTheme()
  const enabled = useEnabledAvatarThemes()
  const perAgentTheme = useAgentStore((s) =>
    agentId ? s.avatarThemeByAgent[agentId] : undefined,
  )
  const packColor = useAgentStore((s) => {
    if (!agentId) return '#6366f1'
    return s.agents.find((agent) => agent.agent_id === agentId)?.color || '#6366f1'
  })
  const packEyes = useAgentStore(
    (s) => (agentId && s.avatarEyesByAgent[agentId]) || s.avatarEyes,
  )
  const theme = forcedTheme ?? resolveAvatarTheme(perAgentTheme, enabled, globalTheme)
  const generatedSrc = useGeneratedAvatar(agentId)
  const choosable = Boolean(agentId) && interactive === true
  const chooseLabel = chooseThemeLabel(alt || agentId)
  const motionHash = hashAgentId(agentId || alt || 'agent')
  const motionStyle: CSSProperties = {
    ['--ew' as string]: `${((motionHash % 23) / 10).toFixed(2)}s`,
    ['--ed' as string]: `${(6 + (motionHash % 50) / 10).toFixed(2)}s`,
    ['--wd' as string]: `${(((motionHash >>> 8) % 14) / 10).toFixed(2)}s`,
    ['--wt' as string]: `${(0.72 + ((motionHash >>> 4) % 10) / 10).toFixed(2)}s`,
  }

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

  const effectiveStatus: AgentStatus =
    status && status !== 'idle' ? status : active ? 'working' : 'idle'
  const eyeState =
    active || effectiveStatus === 'working' || effectiveStatus === 'waiting'
      ? 'active'
      : 'idle'

  const shell = (attrs: Record<string, unknown>, children: ReactNode) => (
    <>
      <AvatarRoot
        choosable={choosable}
        chooseLabel={chooseLabel}
        open={open}
        onOpen={() => setOpen(true)}
        className={`avatar ${eyeState === 'active' ? 'os-avatar--active' : ''} ${className}`.trim()}
        style={{ ...motionStyle, ...style }}
        aria-hidden={choosable || alt ? undefined : true}
        data-avatar-active={eyeState === 'active' ? 'true' : undefined}
        {...attrs}
      >
        {children}
      </AvatarRoot>
      {choosable && open && agentId ? (
        <AgentThemePreviewDialog
          agentId={agentId}
          isOpen={open}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )

  if (isCustom) {
    const faceSrc = uploadedSrc || stillSrc
    return shell(
      {
        'data-agent-avatar': 'custom',
        'data-avatar-size': size,
        'data-avatar-still': showGeneratedStill ? 'generated' : undefined,
        'data-eye-state': eyeState,
      },
      <div
        className={`os-agent-avatar os-agent-avatar--${size} rounded-full ${eyeState === 'active' ? 'os-agent-avatar--active' : ''}`}
      >
        <img
          src={faceSrc}
          alt={alt}
          draggable={false}
          data-agent-avatar="custom"
          onError={() => setBroken(true)}
        />
      </div>,
    )
  }

  if (isRobotPackTheme(theme)) {
    return shell(
      {
        'data-agent-avatar': 'default',
        'data-avatar-theme': theme,
        'data-avatar-size': size,
        'data-eye-state': eyeState,
      },
      <RobotAvatar
        color={packColor}
        status={effectiveStatus}
        size={AVATAR_SIZE_PX[size]}
        theme={theme as AvatarTheme}
        eyes={packEyes as AvatarEyes}
        active={eyeState === 'active'}
        trackPointer={size === 'lg' || size === 'xl'}
        label={alt || undefined}
      />,
    )
  }

  if (theme === 'robot3d') {
    return shell(
      {
        'data-agent-avatar': 'default',
        'data-avatar-theme': 'robot3d',
        'data-avatar-size': size,
        'data-eye-state': eyeState,
      },
      <Robot3DAvatar
        agentId={agentId}
        status={effectiveStatus}
        size={size}
        gl={gl}
        active={eyeState === 'active'}
      />,
    )
  }

  if (theme === 'bee') {
    return shell(
      {
        'data-agent-avatar': 'default',
        'data-avatar-theme': 'bee',
        'data-avatar-size': size,
        'data-eye-state': eyeState,
      },
      <BeeAvatar
        agentId={agentId || 'agent'}
        active={eyeState === 'active'}
        size={size}
        className=""
      />,
    )
  }

  if (theme === 'blobs') {
    return shell(
      {
        'data-agent-avatar': 'default',
        'data-avatar-theme': 'blobs',
        'data-avatar-size': size,
        'data-eye-state': eyeState,
      },
      <BlobAvatar
        agentId={agentId || 'agent'}
        active={eyeState === 'active'}
        size={size}
        className=""
      />,
    )
  }

  return shell(
    {
      'data-agent-avatar': 'default',
      'data-avatar-theme': 'bland',
      'data-avatar-size': size,
      'data-eye-state': eyeState,
    },
    <BlandAvatar size={size} active={eyeState === 'active'} alt={alt} />,
  )
}

function AvatarRoot({
  choosable,
  chooseLabel,
  open,
  onOpen,
  children,
  className,
  style,
  ...rest
}: {
  choosable: boolean
  chooseLabel: string
  open: boolean
  onOpen: () => void
  children: ReactNode
  className?: string
  style?: CSSProperties
  [key: string]: unknown
}) {
  if (choosable) {
    return (
      <span
        role="button"
        tabIndex={0}
        data-theme-chooser=""
        className={`${className || ''} inline-flex cursor-pointer border-0 bg-transparent p-0`.trim()}
        style={style}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={chooseLabel}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event: MouseEvent<HTMLElement>) => {
          event.preventDefault()
          event.stopPropagation()
          onOpen()
        }}
        onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          event.stopPropagation()
          onOpen()
        }}
        {...rest}
      >
        {children}
      </span>
    )
  }
  return (
    <div className={className} style={style} {...rest}>
      {children}
    </div>
  )
}

function BlandAvatar({
  size,
  active,
  alt,
}: {
  size: AgentAvatarSize
  active: boolean
  alt: string
}) {
  return (
    <svg
      className={`os-bland-avatar os-bland-avatar--${size} os-agent-avatar os-agent-avatar--${size} ${active ? 'os-bland-avatar--active os-agent-avatar--active' : ''}`.trim()}
      viewBox="0 0 40 40"
      role="img"
      aria-hidden={alt ? undefined : true}
      aria-label={alt || undefined}
      data-agent-avatar="default"
      data-avatar-theme="bland"
      data-eye-state={active ? 'active' : 'idle'}
    >
      <circle cx="20" cy="20" r="20" fill="#2a2a2a" />
      <circle cx="20" cy="16" r="7" fill="#8a8a8a" />
      <ellipse cx="20" cy="36" rx="12" ry="10" fill="#8a8a8a" />
      <g className="os-bland-eyes">
        <circle cx="-3.15" cy="0" r="1.55" fill="#111111" />
        <circle cx="3.15" cy="0" r="1.55" fill="#111111" />
      </g>
    </svg>
  )
}
