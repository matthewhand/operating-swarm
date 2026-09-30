/**
 * #1288 — provider registration/gating: the `webgpu` provider must be absent
 * unless the experimental flag is on, and its presence must never disturb the
 * server-side provider rows.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { buildComposerProviders, composerOptionsForProvider } from '../composerSources'
import {
  WEBGPU_PROVIDER_ID,
  buildWebGpuProviderRow,
  isWebGpuProviderEnabled,
} from '../webgpuProvider'
import { WEBGPU_DEFAULT_MODEL } from '../webgpuInference'

const FLAG_KEY = 'swarm_experimental_webgpu'

afterEach(() => {
  localStorage.removeItem(FLAG_KEY)
})

describe('#1288 WebGPU provider gating', () => {
  it('is disabled and unregistered by default', () => {
    expect(isWebGpuProviderEnabled()).toBe(false)
    expect(buildWebGpuProviderRow()).toBeNull()
  })

  it('becomes a first-class webgpu row once the flag is on', () => {
    localStorage.setItem(FLAG_KEY, 'on')
    expect(isWebGpuProviderEnabled()).toBe(true)
    const row = buildWebGpuProviderRow()
    expect(row).toMatchObject({
      id: WEBGPU_PROVIDER_ID,
      kind: 'webgpu',
      defaultOptionId: WEBGPU_DEFAULT_MODEL.id,
    })
  })

  it('does not appear in the composer catalogue unless a webgpu source is supplied', () => {
    const apiOnly = buildComposerProviders({
      api: { profiles: [{ id: 'p1', label: 'P1' }], defaultProfileId: 'p1' },
    })
    expect(apiOnly.map((r) => r.kind)).toEqual(['api'])
    expect(apiOnly.some((r) => r.id === WEBGPU_PROVIDER_ID)).toBe(false)

    const withGpu = buildComposerProviders({
      api: { profiles: [{ id: 'p1', label: 'P1' }], defaultProfileId: 'p1' },
      webgpu: { models: [{ id: 'bonsai2-27b', label: 'bonsai2-27b' }], defaultModelId: 'bonsai2-27b' },
    })
    expect(withGpu.map((r) => r.kind)).toEqual(['api', 'webgpu'])
    // Server-side rows are untouched (same first row).
    expect(withGpu[0].id).toBe('api')
  })

  it('offers catalogue models as stage-2 options', () => {
    const options = composerOptionsForProvider(
      { webgpu: { models: [{ id: 'bonsai2-27b', label: 'bonsai2-27b' }] } },
      buildWebGpuProviderRow() ?? {
        id: WEBGPU_PROVIDER_ID,
        label: 'WebGPU',
        kind: 'webgpu',
      },
    )
    expect(options).toEqual([{ id: 'bonsai2-27b', label: 'bonsai2-27b', tag: 'model' }])
  })
})
