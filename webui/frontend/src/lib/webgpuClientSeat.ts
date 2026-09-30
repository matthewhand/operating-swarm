/**
 * #1288 — the client-side WebGPU "seat".
 *
 * Selecting a WebGPU model in the composer activates a tab-local seat that is
 * deliberately orthogonal to every server-side seat: it never rewrites the
 * active agent, `blueprint_id`, CLI, remote or team binding. A completion runs
 * in the Web Worker and streams into the caller's message list, so in-browser
 * inference is only alive while this tab is open (documented limitation).
 */
import { useSyncExternalStore } from 'react'
import { WEBGPU_MODEL_CATALOGUE } from './webgpuInference'
import { getWebGpuWorkerClient } from './webgpuWorkerClient'
import type { WebGpuWorkerStats } from './webgpuWorkerProtocol'

export interface WebGpuClientSeat {
  modelId: string
  label: string
}

let activeSeat: WebGpuClientSeat | null = null
const listeners = new Set<() => void>()

export function getActiveWebGpuSeat(): WebGpuClientSeat | null {
  return activeSeat
}

export function setActiveWebGpuSeat(seat: WebGpuClientSeat | null): void {
  if (activeSeat?.modelId === seat?.modelId && activeSeat?.label === seat?.label) return
  activeSeat = seat
  for (const listener of listeners) listener()
}

/** Clear the client seat when any server-side routing pick is applied. */
export function clearActiveWebGpuSeat(): void {
  setActiveWebGpuSeat(null)
}

export function subscribeWebGpuClientSeat(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Resolve a model id from the catalogue into a seat (honest fallback label). */
export function resolveWebGpuClientSeat(modelId: string | null): WebGpuClientSeat | null {
  if (!modelId) return null
  const spec = WEBGPU_MODEL_CATALOGUE.find((model) => model.id === modelId)
  return { modelId, label: spec?.label ?? modelId }
}

export function selectWebGpuClientModel(modelId: string | null): void {
  setActiveWebGpuSeat(resolveWebGpuClientSeat(modelId))
}

export function useActiveWebGpuSeat(): WebGpuClientSeat | null {
  return useSyncExternalStore(subscribeWebGpuClientSeat, getActiveWebGpuSeat, getActiveWebGpuSeat)
}

export interface WebGpuClientCompletionHandlers {
  onToken?: (token: string) => void
  signal?: AbortSignal
}

/** Run one local completion in the worker; stream tokens via `onToken`. */
export async function runWebGpuClientCompletion(
  seat: WebGpuClientSeat,
  prompt: string,
  handlers: WebGpuClientCompletionHandlers = {},
): Promise<WebGpuWorkerStats> {
  return getWebGpuWorkerClient().generate(
    { modelId: seat.modelId, prompt },
    { signal: handlers.signal, onToken: handlers.onToken },
  )
}
