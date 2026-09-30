/**
 * #1288 — first-class `webgpu` provider descriptor (client-side, experimental).
 *
 * This is a *frontend-only* provider: it is never sent to, resolved by, or
 * proxied through the Django/LiteLLM backend. It exists so the composer
 * provider catalogue can offer "run this model in the browser", while
 * server-side `api`/`cli`/`remote` profiles are completely untouched.
 *
 * Gating: the provider is absent unless the `webgpu` experimental feature is
 * enabled (#1230 catalogue). `buildWebGpuProviderRow()` is the single funnel
 * the catalogue uses, so there is exactly one place that can leak it.
 */
import { isExperimentalFeatureEnabled } from './experimentalFeatures'
import { WEBGPU_DEFAULT_MODEL } from './webgpuInference'
import type { ComposerProviderOption } from './composerPicker'

export const WEBGPU_PROVIDER_ID = 'webgpu'
export const WEBGPU_EXPERIMENTAL_FLAG = 'webgpu' as const

export interface WebGpuProviderDescriptor {
  id: typeof WEBGPU_PROVIDER_ID
  label: string
  kind: 'webgpu'
  description: string
  /** Hard marker: this provider must never be routed server-side. */
  clientSide: true
}

export const WEBGPU_PROVIDER: WebGpuProviderDescriptor = {
  id: WEBGPU_PROVIDER_ID,
  label: 'WebGPU (in-browser)',
  kind: 'webgpu',
  description: 'Runs in this browser tab — no server GPU, no API hop',
  clientSide: true,
}

/** True only when the operator has opted into the WebGPU experiment. */
export function isWebGpuProviderEnabled(): boolean {
  return isExperimentalFeatureEnabled(WEBGPU_EXPERIMENTAL_FLAG)
}

/**
 * The stage-1 composer row, or `null` when the experiment is off. Callers must
 * treat `null` as "provider not registered".
 */
export function buildWebGpuProviderRow(): ComposerProviderOption | null {
  if (!isWebGpuProviderEnabled()) return null
  return {
    id: WEBGPU_PROVIDER.id,
    label: WEBGPU_PROVIDER.label,
    kind: 'webgpu',
    defaultOptionId: WEBGPU_DEFAULT_MODEL.id,
    description: WEBGPU_PROVIDER.description,
  }
}
