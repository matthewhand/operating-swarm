import { useEffect, useId, useMemo, useState } from 'react'
import {
  beeSpecForAgent,
  isFaceBeeVariant,
  type BeeSpec,
} from '../lib/beeAvatar'
import { seededMotionDelays } from '../lib/avatarMotion'

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
  // #821: natural blink at seeded irregular intervals; reduced motion is
  // honoured by both the JS scheduler here and the CSS blocks in index.css.
  const [blinking, setBlinking] = useState(false)
  const delays = useMemo(() => seededMotionDelays(agentId, 'bee'), [agentId])
  useEffect(() => {
    const media = typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : null
    if (media?.matches) return
    let t: ReturnType<typeof setTimeout>
    const schedule = () => {
      const [lo, hi] = [2500, 5500]
      t = setTimeout(() => {
        setBlinking(true)
        setTimeout(() => setBlinking(false), 120)
        schedule()
      }, lo + Math.random() * (hi - lo))
    }
    schedule()
    return () => clearTimeout(t)
  }, [])

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
      data-bee-accessory={spec.accessory}
      data-bee-blink={blinking ? 'true' : 'false'}
      data-eye-state={eyeState}
      data-agent-id={agentId}
      style={{
        ...style,
        ['--px' as string]: `${spec.rest.x.toFixed(2)}px`,
        ['--py' as string]: `${spec.rest.y.toFixed(2)}px`,
        ['--ew' as string]: `${spec.wanderPhase[1].toFixed(2)}s`,
        ['--ed' as string]: `${duration.toFixed(2)}s`,
        ['--bh' as string]: `${(1.05 + spec.wanderPhase[2] * 0.35).toFixed(2)}s`,
        // #821: idle bob (1.8s) vs active hover (~0.6s) + wing flutter freq.
        ['--bf' as string]: active ? (0.55 + spec.wanderPhase[2] * 0.12).toFixed(2) + 's' : '1.8s',
        ['--wf' as string]: active ? '0.19s' : '1.1s',
        ['--bd' as string]: `${delays.bobDelaySec.toFixed(2)}s`,
        ['--wd' as string]: `${delays.wingDelaySec.toFixed(2)}s`,
      }}
    >
      <circle cx="32" cy="32" r="32" fill="#1D2226" />
      {spec.variant === 'side-on' ? (
        <SideOnBee spec={spec} uid={uid} />
      ) : spec.variant === 'flying' ? (
        <FlyingBee spec={spec} uid={uid} />
      ) : spec.variant === 'honeycell' ? (
        <HoneycellBee spec={spec} />
      ) : spec.variant === 'bumblebee' ? (
        <BumbleBee spec={spec} uid={uid} />
      ) : spec.variant === 'top-down' ? (
        <TopDownBee spec={spec} uid={uid} />
      ) : (
        <FaceOnlyBee spec={spec} />
      )}
      <BeeAccessoryLayer spec={spec} />
    </svg>
  )
}

function GeometricWings({ accent }: { accent: string }) {
  return (
    <g
      className="os-bee-wings"
      fill="#1D2226"
      stroke={accent}
      strokeWidth="1.7"
      strokeLinejoin="round"
    >
      <path d="M18 18 C8 8 4 22 16 28 C20 24 22 20 18 18 Z" />
      <path d="M22 14 C16 2 6 10 18 22 C24 18 26 16 22 14 Z" />
      <path d="M12.5 16 L16 22" fill="none" />
      <path d="M10 20 L17 24" fill="none" />
      <path d="M18 8 L20 16" fill="none" />
    </g>
  )
}

function Antennae({ accent }: { accent: string }) {
  return (
    <>
      <g fill="none" stroke={accent} strokeWidth="1.5" strokeLinecap="round">
        <path d="M29.6 8.2 C27.2 3.6 23.6 1.8 20.4 2.4" />
        <path d="M34.4 8.2 C36.8 3.6 40.4 1.8 43.6 2.4" />
      </g>
      <circle cx="20.4" cy="2.4" r="1.35" fill={accent} />
      <circle cx="43.6" cy="2.4" r="1.35" fill={accent} />
    </>
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
        <GeometricWings accent={spec.accent} />
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
        <Antennae accent={spec.accent} />
        <GooglyPair cx={32} cy={12.4} spacing={2.15} sclera={1.85} pupil={0.95} />
      </g>
    </g>
  )
}

function FlyingBee({ spec, uid }: { spec: BeeSpec; uid: string }) {
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
      <g className="os-bee-trail" opacity="0.55">
        <circle cx="7.5" cy="38" r="1.7" fill={spec.accent} />
        <circle cx="12.5" cy="34.5" r="1.2" fill={spec.accent} />
        <circle cx="16.5" cy="37" r="0.8" fill={spec.accent} />
      </g>
      <g transform="rotate(-28 32 33)">
        <g transform="rotate(-22 18 18) translate(-2 -4)">
          <GeometricWings accent={spec.accent} />
        </g>
        <g transform="rotate(16 20 16) translate(2 2)">
          <GeometricWings accent={spec.accent} />
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
        <Antennae accent={spec.accent} />
        <GooglyPair cx={32} cy={12.4} spacing={2.15} sclera={1.85} pupil={0.95} />
      </g>
    </g>
  )
}

function HoneycellBee({ spec }: { spec: BeeSpec }) {
  const flip = spec.flip ? 'translate(64 0) scale(-1 1)' : undefined
  return (
    <g transform={flip}>
      <path
        d="M32 6 L51 17.5 V38.5 L32 50 L13 38.5 V17.5 Z"
        fill="#17212A"
        stroke={spec.accent}
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="M32 12 L45 19.5 V34.5 L32 42 L19 34.5 V19.5 Z"
        fill="none"
        stroke={spec.accent}
        strokeWidth="0.7"
        opacity="0.55"
      />
      <g transform="translate(32 34) scale(1.85) translate(-32 -12.6)">
        <Antennae accent={spec.accent} />
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
      <GooglyPair cx={32} cy={34} spacing={5.4} sclera={4.6} pupil={2.1} />
    </g>
  )
}

function BumbleBee({ spec, uid }: { spec: BeeSpec; uid: string }) {
  const honeyId = `os-bee-honey-${uid}`
  const clipId = `os-bee-round-${uid}`
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
          <circle cx="32" cy="36" r="16.4" />
        </clipPath>
      </defs>
      <g transform="translate(-10 10) scale(0.72)">
        <GeometricWings accent={spec.accent} />
      </g>
      <g transform="translate(46 14) scale(-0.72 0.72)">
        <GeometricWings accent={spec.accent} />
      </g>
      <circle cx="32" cy="36" r="16.4" fill={spec.accent} stroke="#1D2226" strokeWidth="1.5" />
      <g clipPath={`url(#${clipId})`}>
        <rect x="14" y="30" width="36" height="5" fill="#1D2226" />
        <rect x="14" y="39.5" width="36" height="5" fill="#1D2226" />
        <rect x="14" y="49" width="36" height="4.2" fill="#1D2226" />
        <rect x="16" y="25" width="32" height="5" fill={`url(#${honeyId})`} />
        <rect x="16" y="35" width="32" height="4.4" fill={`url(#${honeyId})`} />
      </g>
      <circle cx="32" cy="36" r="16.4" fill="none" stroke="#1D2226" strokeWidth="1.5" />
      <g transform="translate(0 10) scale(1) translate(0 0)">
        <g transform="translate(32 18) scale(0.85) translate(-32 -8)">
          <Antennae accent={spec.accent} />
        </g>
      </g>
      <GooglyPair cx={32} cy={28.5} spacing={5.1} sclera={4.4} pupil={2} />
    </g>
  )
}

function TopDownBee({ spec, uid }: { spec: BeeSpec; uid: string }) {
  const honeyId = `os-bee-honey-${uid}`
  const clipId = `os-bee-dorsal-${uid}`
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
          <ellipse cx="32" cy="42" rx="8.2" ry="13.4" />
        </clipPath>
      </defs>
      <g transform="translate(-6 18) rotate(-18 18 18) scale(0.78)">
        <GeometricWings accent={spec.accent} />
      </g>
      <g transform="translate(70 18) scale(-1 1) rotate(-18 18 18) scale(0.78)">
        <GeometricWings accent={spec.accent} />
      </g>
      <g transform="translate(-2 28) rotate(12 18 18) scale(0.62)">
        <GeometricWings accent={spec.accent} />
      </g>
      <g transform="translate(66 28) scale(-1 1) rotate(12 18 18) scale(0.62)">
        <GeometricWings accent={spec.accent} />
      </g>
      <circle cx="32" cy="16.4" r="6.2" fill="#1D2226" stroke={spec.accent} strokeWidth="1.6" />
      <circle cx="32" cy="26.6" r="6.8" fill={spec.accent} stroke="#1D2226" strokeWidth="1.4" />
      <ellipse cx="32" cy="42" rx="8.2" ry="13.4" fill={spec.accent} stroke="#1D2226" strokeWidth="1.4" />
      <g clipPath={`url(#${clipId})`}>
        <rect x="22" y="34.4" width="20" height="3.6" fill="#1D2226" />
        <rect x="22" y="41.2" width="20" height="3.6" fill="#1D2226" />
        <rect x="22" y="48" width="20" height="3.2" fill="#1D2226" />
        <rect x="23.4" y="37.8" width="17.2" height="3.4" fill={`url(#${honeyId})`} />
        <rect x="23.4" y="44.6" width="17.2" height="3.4" fill={`url(#${honeyId})`} />
      </g>
      <ellipse cx="32" cy="42" rx="8.2" ry="13.4" fill="none" stroke="#1D2226" strokeWidth="1.4" />
      <g transform="translate(32 10.2) scale(0.55) translate(-32 -8)">
        <Antennae accent={spec.accent} />
      </g>
      <GooglyPair cx={32} cy={16.2} spacing={2.05} sclera={1.7} pupil={0.85} />
    </g>
  )
}

function FaceOnlyBee({ spec }: { spec: BeeSpec }) {
  const flip = spec.flip ? 'translate(64 0) scale(-1 1)' : undefined
  return (
    <g transform={flip}>
      {/* Crop / zoom the geometric head + antennae from the same mark. */}
      <g transform="translate(32 36) scale(2.45) translate(-32 -12.6)">
        <Antennae accent={spec.accent} />
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

function BeeAccessoryLayer({ spec }: { spec: BeeSpec }) {
  if (!isFaceBeeVariant(spec.variant) || spec.accessory === 'none') return null
  const face = spec.variant === 'bumblebee'
    ? { x: 32, y: 32, s: 0.85 }
    : spec.variant === 'honeycell'
      ? { x: 32, y: 36, s: 0.9 }
      : { x: 32, y: 38, s: 1 }
  const cls = `os-bee-accessory os-bee-accessory--${spec.accessory}`
  return (
    <g className={cls} transform={`translate(${face.x} ${face.y}) scale(${face.s})`}>
      {spec.accessory === 'blush' ? (
        <>
          <ellipse cx="-9.5" cy="4" rx="3.4" ry="1.7" fill={spec.accent} opacity="0.45" />
          <ellipse cx="9.5" cy="4" rx="3.4" ry="1.7" fill={spec.accent} opacity="0.45" />
        </>
      ) : spec.accessory === 'brow' ? (
        <g fill="none" stroke={spec.accent} strokeWidth="1.4" strokeLinecap="round">
          <path d="M-11 -8 Q-6 -12 -1.5 -8.2" />
          <path d="M1.5 -8.2 Q6 -12 11 -8" />
        </g>
      ) : (
        <g fill={spec.accent} transform="translate(14 -14)">
          <path d="M0 -3.4 L0.85 0 L0 3.4 L-0.85 0 Z" />
          <path d="M-3.4 0 L0 0.85 L3.4 0 L0 -0.85 Z" />
        </g>
      )}
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
      {/* #821: eyelid — a dark disc the CSS squashes over the eye when
          data-bee-blink flips true. No prop threading; the root attribute
          drives every eye at once. */}
      <circle className="os-bee-eyelid" r={sclera + 0.35} fill="#1D2226" />
    </g>
  )
}
