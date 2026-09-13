/**
 * Themeable SVG mascot. Packs: chassis, pixel, glyph, orb, antenna, cube, mask, beetle, ghost, crystal.
 * Eyes are always GooglyPair (animated pupils); status drives mouth / glow / blink.
 */
import { memo, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { AgentStatus, AvatarEyes, AvatarTheme } from '../../types/agent'

export interface RobotAvatarProps {
  color?: string
  isChiefOfStaff?: boolean
  status?: AgentStatus
  size?: number
  label?: string
  trackPointer?: boolean
  theme?: AvatarTheme
  eyes?: AvatarEyes
  /** Chat working/streaming — same contract as Blob/Bee `active`. */
  active?: boolean
  className?: string
}

function mixHex(a: string, b: string, t: number): string {
  const parse = (h: string) => {
    const s = h.replace('#', '')
    const hex = s.length === 3 ? s.split('').map((c) => c + c).join('') : s
    const n = parseInt(hex, 16)
    return Number.isFinite(n) ? n : 0
  }
  const av = parse(a)
  const bv = parse(b)
  const ch = (shift: number) => {
    const ac = (av >> shift) & 0xff
    const bc = (bv >> shift) & 0xff
    return Math.round(ac + (bc - ac) * t).toString(16).padStart(2, '0')
  }
  return `#${ch(16)}${ch(8)}${ch(0)}`
}

function chassisFromColor(color: string): 0 | 1 | 2 | 3 {
  const n = parseInt(color.replace('#', ''), 16)
  if (!Number.isFinite(n)) return 0
  return (n % 4) as 0 | 1 | 2 | 3
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const apply = () => setReduced(mq.matches)
    apply()
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', apply)
      return () => mq.removeEventListener('change', apply)
    }
    mq.addListener(apply)
    return () => mq.removeListener(apply)
  }, [])
  return reduced
}

type FaceProps = {
  color: string
  status: AgentStatus
  hi: string
  sh: string
  metal: string
  visor: string
  gradId: string
  visorId: string
  chassis: 0 | 1 | 2 | 3
}

export const RobotAvatar = memo(function RobotAvatar({
  color = '#6366f1',
  isChiefOfStaff = false,
  status = 'idle',
  size = 40,
  label,
  trackPointer = true,
  theme = 'chassis',
  eyes = 'lens',
  active = false,
  className = '',
}: RobotAvatarProps) {
  const uid = useId()
  const gradId = `rg-${uid}`
  const visorId = `vg-${uid}`
  const chassis = useMemo(() => chassisFromColor(color), [color])
  const reducedMotion = usePrefersReducedMotion()

  const [gaze, setGaze] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const [wobble, setWobble] = useState({ lx: 0, ly: 0, rx: 0, ry: 0 })
  const svgRef = useRef<SVGSVGElement>(null)
  const [blink, setBlink] = useState(false)
  const eyesActive = active || status === 'working' || status === 'waiting'
  const eyeState = eyesActive ? 'active' : 'idle'

  useEffect(() => {
    if (!trackPointer) return
    const el = svgRef.current
    if (!el) return
    const move = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      const dx = e.clientX - cx
      const dy = e.clientY - cy
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const maxDist = r.width * 0.6
      const t = Math.min(dist / maxDist, 1)
      setGaze({ x: (dx / dist) * t * 0.6, y: (dy / dist) * t * 0.5 })
    }
    window.addEventListener('mousemove', move, { passive: true })
    return () => window.removeEventListener('mousemove', move)
  }, [trackPointer])

  useEffect(() => {
    if (reducedMotion) {
      setBlink(false)
      return
    }
    let t: ReturnType<typeof setTimeout>
    const schedule = () => {
      const delay = status === 'working'
        ? 800 + Math.random() * 1200
        : 2000 + Math.random() * 4000
      t = setTimeout(() => {
        setBlink(true)
        setTimeout(() => setBlink(false), 120)
        schedule()
      }, delay)
    }
    schedule()
    return () => clearTimeout(t)
  }, [status, reducedMotion])

  useEffect(() => {
    if (reducedMotion) {
      setWobble({ lx: 0, ly: 0, rx: 0, ry: 0 })
      return
    }
    const personality = eyes !== 'lens'
    if (!personality && !eyesActive) return
    let t: ReturnType<typeof setTimeout>
    const tick = () => {
      const amp = eyes === 'crazy' ? 2.8
        : eyes === 'googly' || eyes === 'mismatched' ? 1.6
        : eyesActive ? 0.9
        : 0.6
      setWobble({
        lx: (Math.random() - 0.5) * amp * 2,
        ly: (Math.random() - 0.5) * amp * 2,
        rx: (Math.random() - 0.5) * amp * 2,
        ry: (Math.random() - 0.5) * amp * 2,
      })
      t = setTimeout(tick, eyes === 'crazy' ? 180 : 420)
    }
    tick()
    return () => clearTimeout(t)
  }, [eyes, eyesActive, reducedMotion])

  const hi = mixHex(color, '#ffffff', 0.48)
  const mid = mixHex(color, '#ffffff', 0.12)
  const sh = mixHex(color, '#000000', 0.42)
  const metal = mixHex(color, '#94a3b8', 0.35)
  const visor = mixHex(color, '#0f172a', 0.72)
  const ex = gaze.x * 3.2
  const ey = gaze.y * 2.2
  const bodyClass =
    status === 'working' || eyesActive ? 'robot-working os-robot-avatar--active' :
    status === 'error' ? 'robot-error' :
    status === 'waiting' ? 'robot-waiting' :
    'robot-idle'
  const face: FaceProps = {
    color, status, hi, sh, metal, visor, gradId, visorId, chassis,
  }

  return (
    <span
      className={`relative inline-flex flex-shrink-0 select-none ${className}`}
      style={{ width: size, height: size }}
      data-avatar-theme={theme}
      data-avatar-eyes={eyes}
      data-eye-state={eyeState}
    >
      <svg
        ref={svgRef}
        viewBox="0 0 100 100"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label={label || 'Agent avatar'}
        className={`os-robot-avatar w-full h-full ${bodyClass}`}
        data-eye-state={eyeState}
        style={{ overflow: 'visible' }}
      >
        <defs>
          <linearGradient id={gradId} x1="18%" y1="8%" x2="86%" y2="96%">
            <stop offset="0%" stopColor={hi} />
            <stop offset="42%" stopColor={mid} />
            <stop offset="100%" stopColor={sh} />
          </linearGradient>
          <radialGradient id={`${gradId}-orb`} cx="38%" cy="32%" r="65%">
            <stop offset="0%" stopColor={hi} />
            <stop offset="55%" stopColor={color} />
            <stop offset="100%" stopColor={sh} />
          </radialGradient>
          <linearGradient id={visorId} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={mixHex(visor, '#ffffff', 0.18)} />
            <stop offset="100%" stopColor={visor} />
          </linearGradient>
        </defs>
        {theme === 'pixel' ? <PixelFace {...face} /> :
         theme === 'glyph' ? <GlyphFace {...face} /> :
         theme === 'orb' ? <OrbFace {...face} /> :
         theme === 'antenna' ? <AntennaFace {...face} /> :
         theme === 'cube' ? <CubeFace {...face} /> :
         theme === 'mask' ? <MaskFace {...face} /> :
         theme === 'beetle' ? <BeetleFace {...face} /> :
         theme === 'ghost' ? <GhostFace {...face} /> :
         theme === 'crystal' ? <CrystalFace {...face} /> :
         <ChassisFace {...face} />}
        <GooglyPair
          style={eyes}
          theme={theme}
          ex={ex}
          ey={ey}
          wobble={wobble}
          blink={blink}
          status={status}
        />
      </svg>

      {isChiefOfStaff && (
        <span
          className="absolute -top-1.5 -right-1.5 flex items-center justify-center rounded-full border border-amber-200 bg-amber-400 p-0.5 shadow z-10 text-amber-950"
          title="Chief of Staff"
          style={{ width: Math.round(size * 0.38), height: Math.round(size * 0.38) }}
          aria-hidden="true"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-full h-full">
            <path d="M3 13l2-6 3 4 3-4 2 6H3zm5-11a2 2 0 110 4 2 2 0 010-4z"/>
          </svg>
        </span>
      )}
      {status === 'working' && (
        <span
          className="absolute -bottom-1 -right-1 flex items-center justify-center rounded-full bg-emerald-500 text-white shadow border border-base-100 animate-spin z-10"
          style={{ width: Math.round(size * 0.32), height: Math.round(size * 0.32) }}
          aria-hidden="true"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" className="w-full h-full p-0.5">
            <path d="M8 2v2M8 12v2M2 8h2M12 8h2M4 4l1.5 1.5M10.5 10.5 12 12M4 12l1.5-1.5M10.5 5.5 12 4"/>
          </svg>
        </span>
      )}
      {status === 'error' && (
        <span
          className="absolute -bottom-1 -right-1 flex items-center justify-center rounded-full bg-rose-500 text-white shadow border border-base-100 animate-pulse z-10"
          style={{ width: Math.round(size * 0.32), height: Math.round(size * 0.32) }}
          aria-hidden="true"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-full h-full p-0.5">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.5c.4 0 .7.3.7.7v3.6a.7.7 0 01-1.4 0V5.2c0-.4.3-.7.7-.7zm0 7a.9.9 0 110-1.8.9.9 0 010 1.8z"/>
          </svg>
        </span>
      )}
    </span>
  )
})

function eyeAnchors(theme: AvatarTheme): [{ x: number; y: number }, { x: number; y: number }] {
  if (theme === 'ghost') return [{ x: 36, y: 46 }, { x: 64, y: 46 }]
  if (theme === 'mask') return [{ x: 36, y: 52 }, { x: 64, y: 52 }]
  if (theme === 'antenna') return [{ x: 38, y: 56 }, { x: 62, y: 56 }]
  if (theme === 'orb' || theme === 'glyph') return [{ x: 38, y: 48 }, { x: 62, y: 48 }]
  if (theme === 'crystal') return [{ x: 38, y: 50 }, { x: 62, y: 50 }]
  return [{ x: 38, y: 52 }, { x: 62, y: 52 }]
}

function GooglyPair({
  style,
  theme,
  ex,
  ey,
  wobble,
  blink,
  status,
}: {
  style: AvatarEyes
  theme: AvatarTheme
  ex: number
  ey: number
  wobble: { lx: number; ly: number; rx: number; ry: number }
  blink: boolean
  status: AgentStatus
}) {
  const [left, right] = eyeAnchors(theme)
  const sleepy = style === 'sleepy' || status === 'waiting'
  const leftR = style === 'mismatched' ? 12.5 : 9.2
  const rightR = style === 'mismatched' ? 7.2 : 9.2
  const leftPupil = style === 'mismatched' ? 5.2 : style === 'spiral' ? 2.4 : 4.2
  const rightPupil = style === 'mismatched' ? 3.1 : style === 'spiral' ? 2.4 : 4.2
  const crazyL = style === 'crazy' ? { x: -1.8, y: 1.4 } : { x: 0, y: 0 }
  const crazyR = style === 'crazy' ? { x: 2.2, y: -1.6 } : { x: 0, y: 0 }
  return (
    <g data-googly="true">
      <GooglyEye
        cx={left.x}
        cy={left.y}
        r={leftR}
        pupil={leftPupil}
        ox={ex + wobble.lx + crazyL.x}
        oy={ey + wobble.ly + crazyL.y}
        sleepy={sleepy}
        blink={blink}
        spiral={style === 'spiral'}
      />
      <GooglyEye
        cx={right.x}
        cy={right.y}
        r={rightR}
        pupil={rightPupil}
        ox={ex + wobble.rx + crazyR.x}
        oy={ey + wobble.ry + crazyR.y}
        sleepy={sleepy}
        blink={blink}
        spiral={style === 'spiral'}
      />
    </g>
  )
}

function GooglyEye({
  cx,
  cy,
  r,
  pupil,
  ox,
  oy,
  sleepy,
  blink,
  spiral,
}: {
  cx: number
  cy: number
  r: number
  pupil: number
  ox: number
  oy: number
  sleepy: boolean
  blink: boolean
  spiral: boolean
}) {
  const ry = blink ? r * 0.12 : sleepy ? r * 0.48 : r
  const maxOff = Math.max(0.4, r - pupil - 1.4)
  const px = Math.max(-maxOff, Math.min(maxOff, ox * 1.15))
  const py = Math.max(-maxOff, Math.min(maxOff, oy * 1.05))
  return (
    <g transform={`translate(${cx},${cy})`}>
      <ellipse rx={r + 0.6} ry={ry + 0.6} fill="#111" opacity="0.18" />
      <ellipse rx={r} ry={ry} fill="#fff" stroke="#1e1e2e" strokeWidth="1.7" />
      <ellipse rx={r * 0.92} ry={ry * 0.9} fill="#f8fafc" />
      <g className="os-robot-pupils">
        {spiral && !blink && (
          <>
            <circle cx={px} cy={py} r={pupil * 2.4} fill="none" stroke="#111" strokeWidth="1.1" />
            <circle cx={px} cy={py} r={pupil * 1.6} fill="none" stroke="#111" strokeWidth="1.1" />
          </>
        )}
        {!blink && (
          <>
            <circle cx={px} cy={py} r={pupil} fill="#111" />
            <circle cx={px - pupil * 0.32} cy={py - pupil * 0.38} r={pupil * 0.28} fill="#fff" opacity="0.9" />
          </>
        )}
      </g>
    </g>
  )
}

function Mouth({ status, hi, sh, y = 76 }: { status: AgentStatus; hi: string; sh: string; y?: number }) {
  if (status === 'error') {
    return <path d={`M 38 ${y} Q 44 ${y - 6} 50 ${y} Q 56 ${y + 6} 62 ${y}`} fill="none" stroke={hi} strokeWidth="2.4" strokeLinecap="round" />
  }
  if (status === 'waiting') {
    return <line x1="40" y1={y} x2="60" y2={y} stroke={hi} strokeWidth="2.4" strokeLinecap="round" />
  }
  if (status === 'working') {
    return (
      <g>
        <rect x="40" y={y - 4} width="20" height="8" rx="2" fill={sh} opacity="0.55" />
        <rect x="43" y={y - 2} width="2.2" height="4" rx="0.6" fill={hi} />
        <rect x="48.9" y={y - 2.5} width="2.2" height="5" rx="0.6" fill={hi} />
        <rect x="54.8" y={y - 2} width="2.2" height="4" rx="0.6" fill={hi} />
      </g>
    )
  }
  return (
    <g>
      <rect x="40" y={y - 4} width="20" height="8" rx="2" fill={sh} opacity="0.4" />
      <rect x="43" y={y - 2} width="14" height="2.2" rx="1" fill={hi} opacity="0.7" />
    </g>
  )
}

function ChassisFace({ color, status, hi, sh, metal, visorId, gradId, chassis }: FaceProps) {
  const headRx = chassis === 2 ? 22 : chassis === 3 ? 14 : 16
  const earKind = chassis === 1 ? 'horn' : chassis === 3 ? 'dish' : 'can'
  return (
    <>
      {status === 'working' && (
        <rect x="8" y="16" width="84" height="76" rx="20" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <rect x="38" y="84" width="24" height="10" rx="3" fill={sh} />
      <rect x="34" y="88" width="32" height="7" rx="3.5" fill={metal} />
      {earKind === 'horn' ? (
        <>
          <path d="M22 38 L12 22 L26 34 Z" fill={sh} />
          <path d="M78 38 L88 22 L74 34 Z" fill={sh} />
        </>
      ) : earKind === 'dish' ? (
        <>
          <ellipse cx="16" cy="52" rx="8" ry="14" fill={metal} />
          <ellipse cx="16" cy="52" rx="4" ry="8" fill={sh} />
          <ellipse cx="84" cy="52" rx="8" ry="14" fill={metal} />
          <ellipse cx="84" cy="52" rx="4" ry="8" fill={sh} />
        </>
      ) : (
        <>
          <rect x="8" y="42" width="12" height="22" rx="6" fill={metal} />
          <rect x="11" y="47" width="6" height="12" rx="2" fill={sh} />
          <rect x="80" y="42" width="12" height="22" rx="6" fill={metal} />
          <rect x="83" y="47" width="6" height="12" rx="2" fill={sh} />
        </>
      )}
      <rect x="18" y="20" width="64" height="66" rx={headRx} fill={`url(#${gradId})`} />
      <rect x="22" y="24" width="56" height="18" rx={Math.max(8, headRx - 6)} fill={mixHex(color, '#ffffff', 0.22)} opacity="0.35" />
      {chassis === 0 ? (
        <>
          <line x1="38" y1="12" x2="38" y2="24" stroke={metal} strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="38" cy="10" r="3.2" fill={hi} />
          <line x1="62" y1="12" x2="62" y2="24" stroke={metal} strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="62" cy="10" r="3.2" fill={status === 'working' ? '#34d399' : hi} />
        </>
      ) : chassis === 2 ? (
        <>
          <line x1="50" y1="6" x2="50" y2="22" stroke={metal} strokeWidth="2.6" strokeLinecap="round" />
          <circle cx="50" cy="6" r="4" fill={status === 'working' ? '#34d399' : hi} />
          <circle cx="50" cy="6" r="7" fill="none" stroke={hi} strokeWidth="1.2" opacity="0.55" />
        </>
      ) : (
        <>
          <line x1="50" y1="8" x2="50" y2="22" stroke={metal} strokeWidth="2.6" strokeLinecap="round" />
          <rect x="46" y="4" width="8" height="8" rx="1.5" fill={hi} />
        </>
      )}
      <rect x="26" y="40" width="48" height="26" rx="8" fill={`url(#${visorId})`} />
      <Mouth status={status} hi={hi} sh={sh} />
      <circle cx="26" cy="30" r="1.6" fill={sh} opacity="0.55" />
      <circle cx="74" cy="30" r="1.6" fill={sh} opacity="0.55" />
    </>
  )
}

function PixelFace({ color, status, hi, sh, metal }: FaceProps) {
  const px = (x: number, y: number, w: number, h: number, fill: string) => (
    <rect x={x} y={y} width={w} height={h} fill={fill} />
  )
  return (
    <>
      {status === 'working' && (
        <rect x="10" y="14" width="80" height="76" fill="none" stroke={color} strokeWidth="3" className="os-robot-glow-ring" />
      )}
      {px(42, 8, 6, 10, metal)}
      {px(40, 4, 10, 6, hi)}
      {px(22, 20, 56, 64, color)}
      {px(16, 36, 8, 20, metal)}
      {px(76, 36, 8, 20, metal)}
      {px(26, 26, 48, 8, hi)}
      {px(28, 40, 44, 24, sh)}
      {px(36, 70, 28, 8, sh)}
      {px(40, 72, 6, 4, hi)}
      {px(47, 72, 6, 4, status === 'working' ? '#34d399' : hi)}
      {px(54, 72, 6, 4, hi)}
    </>
  )
}

function GlyphFace({ color, status, hi, metal, chassis }: FaceProps) {
  const shape =
    chassis === 1 ? (
      <polygon points="50,12 88,50 50,88 12,50" fill={color} />
    ) : chassis === 2 ? (
      <polygon points="50,10 82,28 82,72 50,90 18,72 18,28" fill={color} />
    ) : chassis === 3 ? (
      <polygon points="50,14 86,82 14,82" fill={color} />
    ) : (
      <polygon points="50,10 78,26 78,62 50,90 22,62 22,26" fill={color} />
    )
  return (
    <>
      {status === 'working' && (
        <circle cx="50" cy="50" r="46" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <g opacity="0.95">{shape}</g>
      <polygon points="50,18 70,32 70,48 50,36 30,48 30,32" fill={hi} opacity="0.28" />
      <rect x="38" y="68" width="24" height="3" rx="1.5" fill={metal} />
      {status === 'error' && <path d="M42 74 L58 80" stroke={hi} strokeWidth="2.5" />}
    </>
  )
}

function OrbFace({ color, status, hi, sh, visor, gradId }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <circle cx="50" cy="50" r="49" fill="none" stroke={color} strokeWidth="3" opacity="0.55" className="os-robot-glow-ring" />
      )}
      <circle cx="50" cy="50" r="47" fill={`url(#${gradId}-orb)`} />
      <line x1="50" y1="4" x2="50" y2="18" stroke={hi} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="50" cy="4" r="3" fill={hi} />
      <ellipse cx="50" cy="55" rx="30" ry="26" fill={mixHex(visor, '#ffffff', 0.55)} opacity="0.25" />
      <Mouth status={status} hi={hi} sh={sh} y={68} />
    </>
  )
}

function AntennaFace({ color, status, hi, sh, metal, gradId, visorId }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <circle cx="50" cy="56" r="42" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <line x1="50" y1="4" x2="50" y2="28" stroke={metal} strokeWidth="3" strokeLinecap="round" />
      <circle cx="50" cy="6" r="5" fill={status === 'working' ? '#34d399' : hi} />
      <circle cx="50" cy="6" r="8" fill="none" stroke={hi} strokeWidth="1.4" opacity="0.5" />
      <ellipse cx="50" cy="62" rx="36" ry="32" fill={`url(#${gradId})`} />
      <ellipse cx="50" cy="48" rx="28" ry="12" fill={hi} opacity="0.28" />
      <ellipse cx="50" cy="58" rx="24" ry="16" fill={`url(#${visorId})`} />
      <Mouth status={status} hi={hi} sh={sh} y={78} />
      <ellipse cx="22" cy="62" rx="5" ry="8" fill={metal} />
      <ellipse cx="78" cy="62" rx="5" ry="8" fill={metal} />
    </>
  )
}

function CubeFace({ color, status, hi, sh, metal, visor }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <rect x="10" y="16" width="80" height="74" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <polygon points="50,12 86,32 86,72 50,92 14,72 14,32" fill={color} />
      <polygon points="50,12 86,32 50,52 14,32" fill={hi} opacity="0.35" />
      <polygon points="50,52 86,32 86,72 50,92" fill={sh} opacity="0.28" />
      <rect x="28" y="40" width="44" height="28" rx="4" fill={mixHex(visor, '#0f172a', 0.2)} opacity="0.85" />
      <rect x="38" y="74" width="24" height="6" rx="1" fill={metal} />
      {status === 'error' && <path d="M40 80 L60 86" stroke={hi} strokeWidth="2.2" />}
    </>
  )
}

function MaskFace({ color, status, hi, sh, metal, visorId }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <ellipse cx="50" cy="52" rx="46" ry="42" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <path d="M50 10 C22 14 12 40 16 62 C20 84 38 94 50 94 C62 94 80 84 84 62 C88 40 78 14 50 10 Z" fill={color} />
      <path d="M28 18 L18 8 L32 22 Z" fill={sh} />
      <path d="M72 18 L82 8 L68 22 Z" fill={sh} />
      <path d="M50 18 C36 22 28 36 30 48 C40 40 60 40 70 48 C72 36 64 22 50 18 Z" fill={hi} opacity="0.3" />
      <ellipse cx="36" cy="52" rx="12" ry="10" fill={`url(#${visorId})`} />
      <ellipse cx="64" cy="52" rx="12" ry="10" fill={`url(#${visorId})`} />
      <path d="M50 58 L46 78 L50 74 L54 78 Z" fill={metal} />
      <Mouth status={status} hi={hi} sh={sh} y={80} />
    </>
  )
}

function BeetleFace({ color, status, hi, sh, metal, visorId }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <ellipse cx="50" cy="54" rx="44" ry="40" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <ellipse cx="22" cy="30" rx="10" ry="16" fill={metal} transform="rotate(-28 22 30)" />
      <ellipse cx="78" cy="30" rx="10" ry="16" fill={metal} transform="rotate(28 78 30)" />
      <ellipse cx="50" cy="56" rx="34" ry="36" fill={color} />
      <path d="M50 22 L50 90" stroke={sh} strokeWidth="2.2" opacity="0.45" />
      <ellipse cx="50" cy="34" rx="22" ry="14" fill={hi} opacity="0.28" />
      <rect x="28" y="42" width="44" height="22" rx="11" fill={`url(#${visorId})`} />
      <Mouth status={status} hi={hi} sh={sh} y={74} />
    </>
  )
}

function GhostFace({ color, status, hi, sh, gradId }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <ellipse cx="50" cy="48" rx="44" ry="46" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <path
        d="M18 48 C18 24 32 10 50 10 C68 10 82 24 82 48 L82 86 C76 78 70 84 64 86 C58 80 54 86 50 80 C46 86 42 80 36 86 C30 84 24 78 18 86 Z"
        fill={`url(#${gradId}-orb)`}
      />
      <ellipse cx="50" cy="36" rx="22" ry="10" fill={hi} opacity="0.3" />
      <Mouth status={status} hi={hi} sh={sh} y={64} />
    </>
  )
}

function CrystalFace({ color, status, hi, sh, metal, visor }: FaceProps) {
  return (
    <>
      {status === 'working' && (
        <polygon points="50,6 90,50 50,94 10,50" fill="none" stroke={color} strokeWidth="3" opacity="0.5" className="os-robot-glow-ring" />
      )}
      <polygon points="50,8 88,50 50,92 12,50" fill={color} />
      <polygon points="50,8 88,50 50,50" fill={hi} opacity="0.32" />
      <polygon points="50,50 88,50 50,92" fill={sh} opacity="0.3" />
      <polygon points="32,42 68,42 62,62 38,62" fill={mixHex(visor, '#0f172a', 0.15)} opacity="0.8" />
      <rect x="42" y="70" width="16" height="3" rx="1" fill={metal} />
    </>
  )
}
