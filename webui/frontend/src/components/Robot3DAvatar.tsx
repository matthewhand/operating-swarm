/**
 * REQ-194 — the `robot3d` theme avatar for the chat header.
 *
 * ADR-008 host path: lazy `import()` of the pose-player on the chat hero —
 * `three` is code-split out of the main chat graph and chat never waits on
 * GL. WebGL-less environments (and the first paint) render the static SVG
 * robot fallback, which still reacts to status via CSS.
 */

import { memo, useEffect, useRef, useState } from 'react'
import {
  ROBOT3D_COMBO_SET_EVENT,
  ROBOT3D_COMBO_STORAGE_KEY,
  loadRobot3dCombo,
} from '../lib/robot3d/comboStore'
import { statusToClipId } from '../lib/robot3d/statusMap'
import type { Robot3dCombo } from '../lib/robot3d/types'
import type { AgentStatus } from '../types/agent'

export type Robot3dAvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

const SIZE_PX: Record<Robot3dAvatarSize, number> = {
  xs: 20,
  sm: 28,
  md: 40,
  lg: 56,
  xl: 72,
}

type Robot3dMode = 'pending' | 'gl' | 'fallback'

export interface Robot3DAvatarProps {
  agentId?: string | null
  status?: AgentStatus
  size?: Robot3dAvatarSize
  className?: string
  /**
   * ADR-008 §2: ONE WebGL context, on the chat hero. Only the header site
   * passes `gl`; every other AgentAvatar render site (rail, fav tiles,
   * bubbles, search) shows the static SVG robot so a large rail cannot
   * exhaust the browser's WebGL context limit.
   */
  gl?: boolean
}

function webglSupported(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(
      canvas.getContext('webgl2') ||
        canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl'),
    )
  } catch {
    return false
  }
}

export const Robot3DAvatar = memo(function Robot3DAvatar({
  agentId,
  status = 'idle',
  size = 'sm',
  className = '',
  gl = false,
}: Robot3DAvatarProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const playerRef = useRef<{ play(id: string): void; dispose(): void } | null>(null)
  const [mode, setMode] = useState<Robot3dMode>('pending')
  const [combo, setCombo] = useState<Robot3dCombo>(loadRobot3dCombo)
  const comboKey = `${combo.bodyId}/${combo.headId}`

  // Keep the combo in sync with the Settings sub-picker (same tab + other tabs).
  useEffect(() => {
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<Robot3dCombo>).detail
      if (detail?.bodyId && detail?.headId) setCombo(detail)
    }
    const onStorage = (event: StorageEvent) => {
      if (event.key === ROBOT3D_COMBO_STORAGE_KEY || event.key === null) {
        setCombo(loadRobot3dCombo())
      }
    }
    window.addEventListener(ROBOT3D_COMBO_SET_EVENT, onSet)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(ROBOT3D_COMBO_SET_EVENT, onSet)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  // Lazy-load the pose-player only on the chat hero (`gl`), when GL exists.
  useEffect(() => {
    let cancelled = false
    if (!gl) {
      setMode('fallback')
      return
    }
    if (!webglSupported()) {
      setMode('fallback')
      return
    }
    setMode('pending')
    let player: { play(id: string): void; dispose(): void } | null = null
    import('../lib/robot3d/posePlayer').then(({ createRobot3dPlayer }) => {
      if (cancelled) return
      const canvas = canvasRef.current
      if (!canvas) return
      try {
        player = createRobot3dPlayer({ canvas, combo })
        playerRef.current = player
        player.play(statusToClipId(status))
        setMode('gl')
      } catch {
        setMode('fallback')
      }
    })
    return () => {
      cancelled = true
      player?.dispose()
      playerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [comboKey, gl])

  // Status drives the clip (Phase 3) — both for GL and the fallback pose.
  useEffect(() => {
    playerRef.current?.play(statusToClipId(status))
  }, [status])

  const px = SIZE_PX[size]

  return (
    <span
      className={`relative inline-flex flex-shrink-0 select-none ${className}`}
      style={{ width: px, height: px }}
      data-avatar-theme="robot3d"
      data-robot3d-mode={mode}
      data-robot3d-status={status}
      data-agent-id={agentId ?? undefined}
      aria-hidden="true"
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 h-full w-full"
        style={{ display: mode === 'gl' ? 'block' : 'none' }}
      />
      {mode !== 'gl' && <Robot3dStaticSvg status={status} />}
    </span>
  )
})

/**
 * Original stylised SVG robot — the non-blocking fallback while the GL
 * module loads and on WebGL-less environments. Status still animates it.
 */
function Robot3dStaticSvg({ status }: { status: AgentStatus }) {
  const working = status === 'working'
  const error = status === 'error'
  const listen = status === 'waiting'
  const tilt = working ? '-3deg' : error ? '4deg' : listen ? '1.5deg' : '0deg'
  const headDy = error ? 2 : 0
  return (
    <svg
      viewBox="0 0 64 64"
      className="absolute inset-0 h-full w-full"
      data-robot3d-static="true"
      role="img"
      aria-hidden="true"
    >
      <g className="robot3d-fallback" style={{ transform: `rotate(${tilt})`, transformOrigin: '32px 40px' }}>
        {/* pedestal */}
        <ellipse cx="32" cy="56" rx="13" ry="4" fill="#3b4152" />
        <rect x="24" y="38" width="16" height="16" rx="4" fill="#64748b" />
        {/* chest light */}
        <circle cx="32" cy="44" r="2.4" fill={working ? '#34d399' : error ? '#f87171' : '#64748b'}>
          {working && <animate attributeName="opacity" values="1;0.35;1" dur="0.9s" repeatCount="indefinite" />}
        </circle>
        {/* neck + head */}
        <g transform={`translate(0 ${headDy})`}>
          <rect x="29" y="33" width="6" height="6" rx="1.5" fill="#475569" />
          <rect x="20" y="18" width="24" height="15" rx="5" fill="#818cf8" />
          <rect x="22" y="24" width="20" height="5" rx="2.5" fill="#0f172a" />
          <circle cx="24.5" cy="21.5" r="1.3" fill="#0f172a" />
          <circle cx="39.5" cy="21.5" r="1.3" fill="#0f172a" />
          {/* antennas */}
          <line x1="25" y1="18" x2="22" y2="10" stroke="#64748b" strokeWidth="1.6" strokeLinecap="round">
            {listen && <animateTransform attributeName="transform" type="rotate" values="-2 25 18;2 25 18;-2 25 18" dur="1.6s" repeatCount="indefinite" />}
          </line>
          <circle cx="22" cy="9" r="1.8" fill="#34d399" />
          <line x1="39" y1="18" x2="42" y2="10" stroke="#64748b" strokeWidth="1.6" strokeLinecap="round">
            {listen && <animateTransform attributeName="transform" type="rotate" values="2 39 18;-2 39 18;2 39 18" dur="1.6s" repeatCount="indefinite" />}
          </line>
          <circle cx="42" cy="9" r="1.8" fill="#34d399" />
        </g>
      </g>
    </svg>
  )
}