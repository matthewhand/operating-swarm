import { describe, expect, it } from 'vitest'
import { ROBOT3D_CLIP_LABELS, statusToClipId } from '../statusMap'

describe('statusToClipId (REQ-194 Phase 3)', () => {
  it('maps working / error / happy / waiting onto clips', () => {
    expect(statusToClipId('working')).toBe('working')
    expect(statusToClipId('error')).toBe('error')
    expect(statusToClipId('happy')).toBe('dance')
    expect(statusToClipId('waiting')).toBe('listen')
    expect(statusToClipId('idle')).toBe('idle')
  })

  it('defaults unknown / absent status to idle', () => {
    expect(statusToClipId(undefined)).toBe('idle')
    expect(statusToClipId(null)).toBe('idle')
  })

  it('labels every clip id', () => {
    expect(ROBOT3D_CLIP_LABELS.working).toBe('Working')
    expect(ROBOT3D_CLIP_LABELS.error).toBe('Error')
    expect(ROBOT3D_CLIP_LABELS.dance).toBe('Happy dance')
  })
})