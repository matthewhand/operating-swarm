/**
 * #1288 — Web Worker execution: typed protocol round-trip (tok/s + latency +
 * peak memory), cancellation, and the main-thread client against a mocked
 * `Worker`. No real GPU, weights, or Worker are used.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createWebGpuWorkerHandler,
  type WebGpuWorkerRequest,
  type WebGpuWorkerResponse,
  type WebGpuWorkerStats,
} from '../webgpuWorkerProtocol'
import {
  WebGpuWorkerClient,
  resetWebGpuWorkerClientForTests,
  type WebGpuWorkerLike,
} from '../webgpuWorkerClient'
import { resetWebGpuAdapter } from '../webgpuInference'

afterEach(() => {
  resetWebGpuWorkerClientForTests()
  resetWebGpuAdapter()
  vi.unstubAllGlobals()
})

function makeHandler(overrides: Partial<Parameters<typeof createWebGpuWorkerHandler>[0]> = {}) {
  const posted: WebGpuWorkerResponse[] = []
  let resolveDone: (value: WebGpuWorkerResponse[]) => void = () => {}
  const done = new Promise<WebGpuWorkerResponse[]>((resolve) => {
    resolveDone = resolve
  })
  const handler = createWebGpuWorkerHandler({
    backend: 'webgpu-worker',
    describeAdapter: () => 'test-adapter',
    runGeneration: async (request) => {
      request.onToken?.('Hel')
      request.onToken?.('lo')
      return { text: 'Hello', tokens: 2, adapterId: 'test-adapter', ms: 500 }
    },
    readPeakMemoryBytes: () => 2048,
    post: (message) => {
      posted.push(message)
      if (message.type === 'done' || message.type === 'error') resolveDone(posted)
    },
    ...overrides,
  })
  return { handler, posted, done }
}

describe('#1288 worker protocol round-trip', () => {
  it('streams tokens and reports tok/s, latency and peak memory', async () => {
    const { handler, posted, done } = makeHandler()
    handler({ type: 'generate', requestId: 'r1', modelId: 'm', prompt: 'hi', maxTokens: 2 })

    const messages = await done
    expect(messages.filter((m) => m.type === 'token').map((m) => (m as { token: string }).token)).toEqual([
      'Hel',
      'lo',
    ])
    const doneMsg = messages.find((m) => m.type === 'done') as
      | { result: WebGpuWorkerStats }
      | undefined
    expect(doneMsg).toBeTruthy()
    const result = doneMsg!.result
    expect(result).toMatchObject({
      text: 'Hello',
      tokens: 2,
      ms: 500,
      tokensPerSecond: 4,
      peakMemoryBytes: 2048,
      adapter: 'test-adapter',
      backend: 'webgpu-worker',
    })
    expect(posted).toHaveLength(3)
  })

  it('degrades peak memory honestly to null when performance.memory is absent', async () => {
    const { handler, done } = makeHandler({ readPeakMemoryBytes: () => null })
    handler({ type: 'generate', requestId: 'r2', modelId: 'm', prompt: 'hi' })
    const messages = await done
    const result = (messages.find((m) => m.type === 'done') as { result: WebGpuWorkerStats }).result
    expect(result.peakMemoryBytes).toBeNull()
  })

  it('cancels an in-flight generation and reports an abort', async () => {
    let seenSignal: AbortSignal | undefined
    const { handler, done } = makeHandler({
      runGeneration: async (request) => {
        seenSignal = request.signal
        await new Promise((_resolve, reject) => {
          request.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        })
        return { text: '', tokens: 0, adapterId: 'x', ms: 0 }
      },
    })
    handler({ type: 'generate', requestId: 'r3', modelId: 'm', prompt: 'hi' })
    handler({ type: 'cancel', requestId: 'r3' })
    const messages = await done
    expect(seenSignal?.aborted).toBe(true)
    expect(messages.at(-1)).toMatchObject({ type: 'error', aborted: true })
  })
})

interface FakeWorkerHarness {
  worker: WebGpuWorkerLike
  posted: WebGpuWorkerRequest[]
  emit: (message: WebGpuWorkerResponse) => void
}

function fakeWorker(): FakeWorkerHarness {
  const posted: WebGpuWorkerRequest[] = []
  const listeners = new Set<(event: MessageEvent) => void>()
  const worker = {
    postMessage(message: unknown) {
      posted.push(message as WebGpuWorkerRequest)
    },
    addEventListener(type: 'message' | 'error', listener: (event: never) => void) {
      if (type === 'message') listeners.add(listener as (event: MessageEvent) => void)
    },
    removeEventListener(type: 'message' | 'error', listener: (event: never) => void) {
      if (type === 'message') listeners.delete(listener as (event: MessageEvent) => void)
    },
    terminate() {
      listeners.clear()
    },
  } as unknown as WebGpuWorkerLike
  return {
    worker,
    posted,
    emit(message) {
      for (const listener of listeners) listener({ data: message } as MessageEvent)
    },
  }
}

describe('#1288 Web Worker client (mocked Worker)', () => {
  it('round-trips generate → token* → done through worker messages', async () => {
    const harness = fakeWorker()
    const client = new WebGpuWorkerClient(() => harness.worker)
    const tokens: string[] = []
    const pending = client.generate(
      { modelId: 'm', prompt: 'hi' },
      { onToken: (token) => tokens.push(token) },
    )

    const generate = harness.posted.find((m) => m.type === 'generate')
    expect(generate).toBeTruthy()
    const requestId = (generate as { requestId: string }).requestId
    harness.emit({ type: 'token', requestId, token: 'to' })
    harness.emit({ type: 'token', requestId, token: 'ken' })
    harness.emit({
      type: 'done',
      requestId,
      result: {
        text: 'token',
        tokens: 2,
        ms: 250,
        tokensPerSecond: 8,
        peakMemoryBytes: null,
        adapter: 'mock',
        backend: 'webgpu-worker',
      },
    })

    const stats = await pending
    expect(tokens).toEqual(['to', 'ken'])
    expect(stats).toMatchObject({ tokensPerSecond: 8, ms: 250, backend: 'webgpu-worker' })
  })

  it('posts a cancel request and rejects with AbortError', async () => {
    const harness = fakeWorker()
    const client = new WebGpuWorkerClient(() => harness.worker)
    const controller = new AbortController()
    const pending = client.generate({ modelId: 'm', prompt: 'hi' }, { signal: controller.signal })

    const generate = harness.posted.find((m) => m.type === 'generate') as { requestId: string }
    controller.abort()
    expect(harness.posted).toContainEqual({ type: 'cancel', requestId: generate.requestId })

    const requestId = generate.requestId
    harness.emit({ type: 'error', requestId, message: 'Aborted', aborted: true })
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('falls back to the in-process port when no Worker factory is available', async () => {
    const client = new WebGpuWorkerClient(() => null)
    const stats = await client.generate({ modelId: 'placeholder-tiny', prompt: 'hi', maxTokens: 1 })
    expect(stats.backend).toBe('in-process')
    expect(stats.text).toContain('[webgpu-smoke]')
    expect(stats.tokensPerSecond).toBeGreaterThan(0)
  })
})
