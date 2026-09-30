/**
 * #1288 — typed message protocol between the main thread and the WebGPU
 * inference Web Worker. The worker owns `load` + `generate` (and, in a real
 * build, the transformers.js/ONNX runtime) so inference never blocks the UI
 * thread. This module is import-safe on both sides: the worker entry installs
 * `createWebGpuWorkerHandler`, the main thread drives it through
 * `webgpuWorkerClient.ts`.
 */
import {
  isAbortError,
  type WebGpuAdapterOutput,
  type WebGpuGenerationRequest,
} from './webgpuInference'

export interface WebGpuWorkerStats {
  text: string
  tokens: number
  /** End-to-end load + generate latency in milliseconds. */
  ms: number
  tokensPerSecond: number
  /** `performance.memory.usedJSHeapSize` when exposed; `null` otherwise. */
  peakMemoryBytes: number | null
  /** Honest description of the adapter actually used. */
  adapter: string
  /** `webgpu-worker` when a Worker ran it, `in-process` for the degraded path. */
  backend: string
}

export type WebGpuWorkerRequest =
  | {
      type: 'generate'
      requestId: string
      modelId: string
      prompt: string
      maxTokens?: number
    }
  | { type: 'cancel'; requestId: string }

export type WebGpuWorkerResponse =
  | { type: 'ready'; backend: string; adapter: string }
  | { type: 'token'; requestId: string; token: string }
  | { type: 'done'; requestId: string; result: WebGpuWorkerStats }
  | { type: 'error'; requestId: string; message: string; aborted: boolean }

export interface WebGpuWorkerHandlerDeps {
  /** Label reported in `done` — `webgpu-worker` or `in-process`. */
  backend: string
  describeAdapter: () => string
  runGeneration: (
    request: WebGpuGenerationRequest,
  ) => Promise<WebGpuAdapterOutput & { ms: number }>
  readPeakMemoryBytes: () => number | null
  post: (message: WebGpuWorkerResponse) => void
}

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return 'unknown error'
}

function safeTokensPerSecond(tokens: number, ms: number): number {
  if (!Number.isFinite(tokens) || tokens <= 0) return 0
  if (!Number.isFinite(ms) || ms <= 0) return tokens
  return tokens / (ms / 1000)
}

/**
 * Build the pure worker-side message handler. Kept free of `self`/`postMessage`
 * so it is unit-testable and reusable in the in-process fallback.
 */
export function createWebGpuWorkerHandler(
  deps: WebGpuWorkerHandlerDeps,
): (message: WebGpuWorkerRequest) => void {
  const controllers = new Map<string, AbortController>()

  return (message) => {
    if (message.type === 'cancel') {
      controllers.get(message.requestId)?.abort()
      return
    }

    const { requestId, modelId, prompt, maxTokens } = message
    const controller = new AbortController()
    controllers.set(requestId, controller)
    const startedAt = Date.now()
    const memoryBefore = deps.readPeakMemoryBytes()

    void (async () => {
      try {
        const output = await deps.runGeneration({
          modelId,
          prompt,
          maxTokens,
          signal: controller.signal,
          onToken: (token) => deps.post({ type: 'token', requestId, token }),
        })
        const ms = Math.max(0, Math.round(output.ms ?? Date.now() - startedAt))
        const memoryAfter = deps.readPeakMemoryBytes()
        const peakMemoryBytes =
          memoryBefore !== null && memoryAfter !== null
            ? Math.max(memoryBefore, memoryAfter)
            : (memoryAfter ?? memoryBefore)
        deps.post({
          type: 'done',
          requestId,
          result: {
            text: output.text,
            tokens: output.tokens,
            ms,
            tokensPerSecond: safeTokensPerSecond(output.tokens, ms),
            peakMemoryBytes,
            adapter: deps.describeAdapter(),
            backend: deps.backend,
          },
        })
      } catch (err) {
        deps.post({
          type: 'error',
          requestId,
          message: errorMessage(err),
          aborted: isAbortError(err),
        })
      } finally {
        controllers.delete(requestId)
      }
    })()
  }
}
