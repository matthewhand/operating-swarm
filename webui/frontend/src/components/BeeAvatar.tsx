import { useId, useMemo } from 'react'
import { beeSpecForAgent, type BeeSpec } from '../lib/beeAvatar'

export type BeeEyeState = 'idle' | 'active'

export interface BeeAvatarProps {
  agentId: string
  /** Selected conversation and/or streaming — pupils wander slowly. */
  active?: boolean
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  style?: React.CSSProperties
}

/**
 * Rail Bee faces. Path data is the shipped geometric WebUI mark
 * (`assets/brand/webui-geometric.svg` / #778). Marketing fanfare
 * marks stay out of the rail.
 */
export default function BeeAvatar({
  agentId,
  active = false,
  size = 'sm',
  className = '',
  style,
}: BeeAvatarProps) {
  const spec = useMemo(() => beeSpecForAgent(agentId), [agentId])
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const eyeState: BeeEyeState = active ? 'active' : 'idle'
  const duration = 8.5 + spec.wanderPhase[0] * 0.6

  return (
    <svg
      className={`os-bee-avatar os-bee-avatar--${size} ${className}`.trim()}
      viewBox="0 0 64 64"
      role="img"
      aria-hidden="true"
      data-avatar-theme="bee"
      data-bee-variant={spec.variant}
      data-bee-gaze={spec.gaze}
      data-bee-accent={spec.accent}
      data-eye-state={eyeState}
      data-agent-id={agentId}
      style={{
        ...style,
        ['--px' as string]: `${spec.rest.x.toFixed(2)}px`,
        ['--py' as string]: `${spec.rest.y.toFixed(2)}px`,
        ['--ew' as string]: `${spec.wanderPhase[1].toFixed(2)}s`,
        ['--ed' as string]: `${duration.toFixed(2)}s`,
        ['--bh' as string]: `${(1.05 + spec.wanderPhase[2] * 0.35).toFixed(2)}s`,
      }}
    >
      <circle cx="32" cy="32" r="32" fill="#1D2226" />
      {spec.variant === 'side-on' ? (
        <SideOnBee spec={spec} uid={uid} />
      ) : (
        <FaceOnlyBee spec={spec} />
      )}
    </svg>
  )
}

function SideOnBee({ spec, uid }: { spec: BeeSpec; uid: string }) {
  const honeyId = `os-bee-honey-${uid}`
  const clipId = `os-bee-abdomen-${uid}`
  const flip = spec.flip ? 'translate(64 0) scale(-1 1)' : undefined
  return (
    <g className="os-bee-body" transform={flip}>
      <defs>
        <pattern id={honeyId} width="6" height="5.2" patternUnits="userSpaceOnUse">
          <path
            d="M3 0.35 L5.7 1.9 V4.3 L3 5.85 L0.3 4.3 V1.9 Z"
            fill="none"
            stroke="#C48A1C"
            strokeWidth="0.45"
          />
        </pattern>
        <clipPath id={clipId}>
          <ellipse cx="32" cy="38.2" rx="10.4" ry="15.6" />
        </clipPath>
      </defs>
      {/* Same rotate + paths as assets/brand/webui-geometric.svg */}
      <g transform="rotate(-38 32 33)">
        <g fill="#1D2226" stroke={spec.accent} strokeWidth="1.7" strokeLinejoin="round">
          <path d="M18 18 C8 8 4 22 16 28 C20 24 22 20 18 18 Z" />
          <path d="M22 14 C16 2 6 10 18 22 C24 18 26 16 22 14 Z" />
          <path d="M12.5 16 L16 22" fill="none" />
          <path d="M10 20 L17 24" fill="none" />
          <path d="M18 8 L20 16" fill="none" />
        </g>
        <path d="M32 55.6 L28.6 50.2 H35.4 Z" fill={spec.accent} />
        <ellipse cx="32" cy="38.2" rx="10.4" ry="15.6" fill={spec.accent} stroke="#1D2226" strokeWidth="1.5" />
        <g clipPath={`url(#${clipId})`}>
          <rect x="20" y="28.6" width="24" height="4.4" fill="#1D2226" />
          <rect x="20" y="37.4" width="24" height="4.4" fill="#1D2226" />
          <rect x="20" y="46.2" width="24" height="3.6" fill="#1D2226" />
          <rect x="21.6" y="22.4" width="20.8" height="6.2" fill={`url(#${honeyId})`} />
          <rect x="21.6" y="33" width="20.8" height="4.4" fill={`url(#${honeyId})`} />
          <rect x="21.6" y="41.8" width="20.8" height="4.4" fill={`url(#${honeyId})`} />
        </g>
        <ellipse cx="32" cy="38.2" rx="10.4" ry="15.6" fill="none" stroke="#1D2226" strokeWidth="1.5" />
        <ellipse cx="32" cy="22.2" rx="7.6" ry="7.1" fill={spec.accent} stroke="#1D2226" strokeWidth="1.5" />
        <circle cx="32" cy="12.6" r="5.4" fill="#1D2226" stroke={spec.accent} strokeWidth="1.7" />
        <path
          d="M29.4 11.2 A3.4 3.4 0 0 1 34.8 12.4"
          fill="none"
          stroke={spec.accent}
          strokeWidth="1.3"
          strokeLinecap="round"
        />
        <g fill="none" stroke={spec.accent} strokeWidth="1.5" strokeLinecap="round">
          <path d="M29.6 8.2 C27.2 3.6 23.6 1.8 20.4 2.4" />
          <path d="M34.4 8.2 C36.8 3.6 40.4 1.8 43.6 2.4" />
        </g>
        <circle cx="20.4" cy="2.4" r="1.35" fill={spec.accent} />
        <circle cx="43.6" cy="2.4" r="1.35" fill={spec.accent} />
        <GooglyPair cx={32} cy={12.4} spacing={2.15} sclera={1.85} pupil={0.95} />
      </g>
    </g>
  )
}

function FaceOnlyBee({ spec }: { spec: BeeSpec }) {
  const flip = spec.flip ? 'translate(64 0) scale(-1 1)' : undefined
  return (
    <g transform={flip}>
      {/* Crop / zoom the geometric head + antennae from the same mark. */}
      <g transform="translate(32 36) scale(2.45) translate(-32 -12.6)">
        <g fill="none" stroke={spec.accent} strokeWidth="1.5" strokeLinecap="round">
          <path d="M29.6 8.2 C27.2 3.6 23.6 1.8 20.4 2.4" />
          <path d="M34.4 8.2 C36.8 3.6 40.4 1.8 43.6 2.4" />
        </g>
        <circle cx="20.4" cy="2.4" r="1.35" fill={spec.accent} />
        <circle cx="43.6" cy="2.4" r="1.35" fill={spec.accent} />
        <ellipse cx="32" cy="22.2" rx="7.6" ry="4.2" fill={spec.accent} stroke="#1D2226" strokeWidth="1.5" />
        <circle cx="32" cy="12.6" r="5.4" fill="#1D2226" stroke={spec.accent} strokeWidth="1.7" />
        <path
          d="M29.4 11.2 A3.4 3.4 0 0 1 34.8 12.4"
          fill="none"
          stroke={spec.accent}
          strokeWidth="1.3"
          strokeLinecap="round"
        />
      </g>
      <GooglyPair cx={32} cy={34.2} spacing={6.4} sclera={5.6} pupil={2.45} />
    </g>
  )
}

function GooglyPair({
  cx,
  cy,
  spacing,
  sclera,
  pupil,
}: {
  cx: number
  cy: number
  spacing: number
  sclera: number
  pupil: number
}) {
  return (
    <g className="os-bee-googly" data-googly="true" transform={`translate(${cx} ${cy})`}>
      <GooglyEye cx={-spacing} cy={0} sclera={sclera} pupil={pupil} />
      <GooglyEye cx={spacing} cy={0} sclera={sclera} pupil={pupil} />
    </g>
  )
}

function GooglyEye({
  cx,
  cy,
  sclera,
  pupil,
}: {
  cx: number
  cy: number
  sclera: number
  pupil: number
}) {
  return (
    <g transform={`translate(${cx} ${cy})`}>
      <circle className="os-bee-sclera" r={sclera} fill="#FFF8EC" stroke="#1D2226" strokeWidth="0.55" />
      <g className="os-bee-pupils">
        <circle r={pupil} fill="#111111" />
      </g>
    </g>
  )
}
