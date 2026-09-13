import { useMemo } from 'react'
import { blobSpecForAgent, type BlobShape } from '../lib/blobAvatar'

export type BlobEyeState = 'idle' | 'active'

export interface BlobAvatarProps {
  agentId: string
  /** Selected conversation and/or streaming — eyes wander slowly. */
  active?: boolean
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  style?: React.CSSProperties
}

function BlobShapePath({ shape, color }: { shape: BlobShape; color: string }) {
  switch (shape) {
    case 'hexagon':
      return (
        <path
          d="M20 5.2 32.4 12.3v15.4L20 34.8 7.6 27.7V12.3Z"
          fill={color}
          stroke={color}
          strokeWidth="3.2"
          strokeLinejoin="round"
        />
      )
    case 'circle':
      return <circle cx="20" cy="20" r="15.2" fill={color} />
    case 'teardrop':
      return (
        <path
          d="M20 4.2C20 4.2 7.2 17.2 7.2 25.2c0 7 5.7 10.6 12.8 10.6s12.8-3.6 12.8-10.6C32.8 17.2 20 4.2 20 4.2Z"
          fill={color}
        />
      )
    case 'triangle':
      return (
        <path
          d="M20 6.4c1.1 0 2.1.6 2.6 1.6l10.4 20.2c.8 1.6-.3 3.6-2.2 3.6H9.2c-1.9 0-3-2-2.2-3.6L17.4 8c.5-1 1.5-1.6 2.6-1.6Z"
          fill={color}
        />
      )
    case 'pill':
      return <rect x="3.2" y="13.2" width="33.6" height="13.6" rx="6.8" fill={color} />
    case 'cloud':
      return (
        <g fill={color}>
          <ellipse cx="13.6" cy="22.4" rx="10.4" ry="9.2" />
          <ellipse cx="26.4" cy="22.6" rx="10.2" ry="9" />
          <ellipse cx="20" cy="14.6" rx="9.4" ry="8.4" />
        </g>
      )
    case 'roundedRect':
      return <rect x="6.4" y="8.4" width="27.2" height="23.2" rx="6.4" fill={color} />
    case 'diamond':
      return (
        <path
          d="M20 5.4 34.2 20 20 34.6 5.8 20Z"
          fill={color}
          stroke={color}
          strokeWidth="4"
          strokeLinejoin="round"
        />
      )
    default:
      return <circle cx="20" cy="20" r="15.2" fill={color} />
  }
}

export default function BlobAvatar({
  agentId,
  active = false,
  size = 'sm',
  className = '',
  style,
}: BlobAvatarProps) {
  const spec = useMemo(() => blobSpecForAgent(agentId), [agentId])
  const eyeState: BlobEyeState = active ? 'active' : 'idle'
  const duration = 8.5 + spec.wanderPhase[0] * 0.6

  return (
    <svg
      className={`os-blob-avatar os-blob-avatar--${size} ${className}`.trim()}
      viewBox="0 0 40 40"
      role="img"
      aria-hidden="true"
      data-avatar-theme="blobs"
      data-blob-shape={spec.shape}
      data-eye-state={eyeState}
      data-agent-id={agentId}
      style={style}
    >
      <g className="os-blob-body">
        <BlobShapePath shape={spec.shape} color={spec.color} />
      </g>
      <g
        className="os-blob-eyes"
        style={{
          ['--ex' as string]: `${spec.rest.x}px`,
          ['--ey' as string]: `${spec.rest.y}px`,
          ['--ea' as string]: `${spec.rest.angle}deg`,
          ['--ew' as string]: `${spec.wanderPhase[1].toFixed(2)}s`,
          ['--ed' as string]: `${duration.toFixed(2)}s`,
        }}
      >
        <rect x="-5.1" y="-4.1" width="2.7" height="7.4" rx="1.35" fill="#111111" />
        <rect x="2.4" y="-4.1" width="2.7" height="7.4" rx="1.35" fill="#111111" />
      </g>
    </svg>
  )
}
