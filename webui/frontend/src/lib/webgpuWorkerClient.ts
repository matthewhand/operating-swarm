/**
 * #1288 — main-thread client for the WebGPU inference Worker.
 *
 * Wraps the typed protocol in a request/response API with token streaming and
 * cancellation. When `Worker` is unavailable (SSR, jsdom, an unsupported
 * browser) it degrades to an in-process port that runs the exact same handler
 * and reports `backend: 'in-process'` — honest, never a silent server fallback.
 */
import {
  getWebGpuAdapter,
  isAbortError,
  readPeakMemoryBytes,
  runWebGpuGeneration,
} from './webgpuInference'
import {
  createWebGpuWorkerHandler,
  type WebGpuWorkerRequest,
  type WebGpuWorkerResponse,
  type WebGpuWorkerStats,
} from './webgpuWorkerProtocol'

type MessageListener = (event: MessageEvent) => void
type ErrorListener = (event: ErrorEvent) => void

export interface WebGpuWorkerLike {
  postMessage(message: unknown): void
  addEventListener(type: 'message', listener: MessageListener): void
  addEventListener(type: 'error', listener: ErrorListener): void
  removeEventListener(type: 'message', listener: MessageListener): void
  removeEventListener(type: 'error', listener: ErrorListener): void
  terminate(): void
}

export type WebGpuWorkerFactory = () => WebGpuWorkerLike | null

export function defaultWebGpuWorkerFactory(): WebGpuWorkerLike | null {
  if (typeof Worker === 'undefined') return null
  try {
    return new Worker(new URL('../workers/webgpuWorker.ts', import.meta.url), {
      type: 'module',
    }) as unknown as WebGpuWorkerLike
  } catch {
    return null
  }
}

/** Same handler, main thread — the honest degraded path when Worker is absent. */
export function createInProcessWorkerPort(): WebGpuWorkerLike {
  const listeners = new Set<MessageListener>()
  const handler = createWebGpuWorkerHandler({
    backend: 'in-process',
    describeAdapter: () => getWebGpuAdapter().describe(),
    runGeneration: (request) => runWebGpuGeneration(request),
    readPeakMemoryBytes,
    post: (message) => {
      queueMicrotask(() => {
        for (const listener of listeners) listener({ data: message } as MessageEvent)
      })
    },
  })
  return {
    postMessage(message) {
      handler(message as WebGpuWorkerRequest)
    },
    addEventListener(type, listener) {
      if (type === 'message') listeners.add(listener as MessageListener)
    },
    removeEventListener(type, listener) {
      if (type === 'message') listeners.delete(listener as MessageListener)
    },
    terminate() {
      listeners.clear()
    },
  }
}

interface PendingGeneration {
  resolve: (stats: WebGpuWorkerStats) => void
  reject: (error: unknown) => void
  onToken?: (token: string) => void
}

export interface WebGpuWorkerGenerateOptions {
  signal?: AbortSignal
  onToken?: (token: string) => void
}

export interface WebGpuWorkerGenerateRequest {
  modelId: string
  prompt: string
  maxTokens?: number
}

export class WebGpuWorkerClient {
  private worker: WebGpuWorkerLike | null = null
  private seq = 0
  private readonly pending = new Map<string, PendingGeneration>()
  private readonly factory: WebGpuWorkerFactory

  constructor(factory: WebGpuWorkerFactory = defaultWebGpuWorkerFactory) {
    this.factory = factory
  }

  private readonly onMessage = (event: MessageEvent) => {
    const message = event.data as WebGpuWorkerResponse | undefined
    if (!message || typeof message !== 'object' || !('type' in message)) return
    if (message.type === 'ready') return
    const requestId = (message as { requestId?: string }).requestId
    if (!requestId) return
    const entry = this.pending.get(requestId)
    if (!entry) return
    if (message.type === 'token') {
      entry.onToken?.(message.token)
      return
    }
    if (message.type === 'done') {
      this.pending.delete(requestId)
      entry.resolve(message.result)
      return
    }
    this.pending.delete(requestId)
    entry.reject(
      message.aborted
        ? new DOMException('Aborted', 'AbortError')
        : new Error(message.message),
    )
  }

  private readonly onError = (event: ErrorEvent) => {
    for (const entry of this.pending.values()) {
      entry.reject(new Error(`WebGPU worker failed: ${event.message || 'unknown error'}`))
    }
    this.pending.clear()
  }

  private ensureWorker(): WebGpuWorkerLike {
    if (this.worker) return this.worker
    this.worker = this.factory() ?? createInProcessWorkerPort()
    this.worker.addEventListener('message', this.onMessage)
    this.worker.addEventListener('error', this.onError)
    return this.worker
  }

  generate(
    request: WebGpuWorkerGenerateRequest,
    options: WebGpuWorkerGenerateOptions = {},
  ): Promise<WebGpuWorkerStats> {
    if (options.signal?.aborted) {
      return Promise.reject(new DOMException('Aborted', 'AbortError'))
    }
    const worker = this.ensureWorker()
    const requestId = `webgpu-${++this.seq}`
    return new Promise<WebGpuWorkerStats>((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject, onToken: options.onToken })
      options.signal?.addEventListener(
        'abort',
        () => worker.postMessage({ type: 'cancel', requestId }),
        { once: true },
      )
      worker.postMessage({
        type: 'generate',
        requestId,
        modelId: request.modelId,
        prompt: request.prompt,
        maxTokens: request.maxTokens,
      })
    })
  }

  cancelAll(): void {
    this.worker?.terminate()
    this.worker = null
    for (const entry of this.pending.values()) {
      entry.reject(new DOMException('Aborted', 'AbortError'))
    }
    this.pending.clear()
  }

  terminate(): void {
    this.cancelAll()
  }
}

let singleton: WebGpuWorkerClient | null = null

export function getWebGpuWorkerClient(): WebGpuWorkerClient {
  if (!singleton) singleton = new WebGpuWorkerClient()
  return singleton
}

export function resetWebGpuWorkerClientForTests(): void {
  singleton?.terminate()
  singleton = null
}

export { isAbortError }
