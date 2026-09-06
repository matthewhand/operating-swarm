/**
 * REQ-194 Phase 3 — agent status → 3D animation state.
 *
 * Maps the SPA's AgentStatus onto the semantic clip ids the pose-player
 * understands (ADR-008 §2.1). `error` holds its last frame (non-loop),
 * `happy` briefly plays the `dance` clip, `waiting` listens.
 */

import type { AgentStatus } from '../../types/agent'
import type { Robot3dClipId } from './types'

export function statusToClipId(status: AgentStatus | null | undefined): Robot3dClipId {
  switch (status) {
    case 'working':
      return 'working'
    case 'error':
      return 'error'
    case 'happy':
      return 'dance'
    case 'waiting':
      return 'listen'
    case 'idle':
      return 'idle'
    default:
      return 'idle'
  }
}

export const ROBOT3D_CLIP_LABELS: Record<Robot3dClipId, string> = {
  idle: 'Idle',
  listen: 'Listen',
  working: 'Working',
  dance: 'Happy dance',
  error: 'Error',
}