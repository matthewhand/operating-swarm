/**
 * #1288 — WebGPU engine unit coverage: support detection, download progress,
 * abort/cancel, and the generation adapter seam. `navigator.gpu` and `fetch`
 * are mocked; no weights are ever downloaded.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  WEBGPU_DEFAULT_MODEL,
  detectWebGpuSupport,
  downloadWebGpuModel,
  isAbortError,
  memoryModelStore,
  resetWebGpuAdapter,
  runWebGpuGeneration,
  setWebGpuAdapter,
  type DownloadProgress,
  type WebGpuAdapter,
  type WebGpuModelSpec,
} from '../webgpuInference'

function defineGpu(value: unknown) {
  Object.defineProperty(navigator, 'gpu', { configurable: true, value })
}

function streamingResponse(chunks: Uint8Array[], headers: Record<string, string> = {}) {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk)
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers })
}

const urlSpec: WebGpuModelSpec = {
  ...WEBGPU_DEFAULT_MODEL,
  url: 'https://example.test/model.bin',
}

afterEach(() => {
  delete (navigator as { gpu?: unknown }).gpu
  resetWebGpuAdapter()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('#1288 WebGPU support detection', () => {
  it('reports unsupported (with a reason) when navigator.gpu is missing', async () => {
    defineGpu(undefined)
    const result = await detectWebGpuSupport()
    expect(result.supported).toBe(false)
    expect(result.reason).toMatch(/navigator\.gpu is not present/)
  })

  it('reports unsupported when no adapter can be acquired', async () => {
    defineGpu({ requestAdapter: async () => null })
    const result = await detectWebGpuSupport()
    expect(result.supported).toBe(false)
    expect(result.reason).toMatch(/no GPU adapter/)
  })

  it('reports supported with adapter details when an adapter is acquired', async () => {
    defineGpu({
      requestAdapter: async () => ({ info: { vendor: 'NVIDIA', architecture: 'ampere' } }),
    })
    const result = await detectWebGpuSupport()
    expect(result.supported).toBe(true)
    expect(result.adapterInfo).toContain('NVIDIA')
    expect(result.adapterInfo).toContain('ampere')
  })
})

describe('#1288 model download', () => {
  it('emits byte-level progress and stores the artifact', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => streamingResponse([new Uint8Array([1, 2, 3]), new Uint8Array([4, 5])], {
        'content-length': '5',
      })),
    )
    const progress: DownloadProgress[] = []
    const store = memoryModelStore()
    const result = await downloadWebGpuModel(urlSpec, {
      onProgress: (p) => progress.push(p),
      store,
    })

    expect(progress.length).toBeGreaterThanOrEqual(2)
    expect(progress[0].bytesDownloaded).toBe(3)
    expect(progress.at(-1)).toMatchObject({ bytesDownloaded: 5, totalBytes: 5, percent: 100 })
    expect(result).toMatchObject({ modelId: urlSpec.id, bytes: 5, stored: true })
    expect((await store.load(urlSpec.id))?.byteLength).toBe(5)
  })

  it('refuses to invent a URL and reports an honest error', async () => {
    const noUrl: WebGpuModelSpec = { ...WEBGPU_DEFAULT_MODEL, id: 'no-url-model', url: '' }
    await expect(downloadWebGpuModel(noUrl)).rejects.toThrow(/No artifact URL configured/)
  })

  it('rejects immediately when the signal is already aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    const err = await downloadWebGpuModel(urlSpec, { signal: controller.signal }).catch((e) => e)
    expect(isAbortError(err)).toBe(true)
  })

  it('propagates an abort through fetch as an AbortError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            )
          }),
      ),
    )
    const controller = new AbortController()
    const pending = downloadWebGpuModel(urlSpec, { signal: controller.signal })
    controller.abort()
    const err = await pending.catch((e) => e)
    expect(isAbortError(err)).toBe(true)
  })
})

describe('#1288 generation adapter seam', () => {
  it('runs the placeholder smoke adapter and streams tokens', async () => {
    const tokens: string[] = []
    const result = await runWebGpuGeneration({
      modelId: WEBGPU_DEFAULT_MODEL.id,
      prompt: 'hello world',
      maxTokens: 1,
      onToken: (t) => tokens.push(t),
    })
    expect(result.adapterId).toBe('placeholder-smoke')
    expect(result.tokens).toBe(1)
    expect(tokens).toHaveLength(1)
    expect(result.text).toContain('[webgpu-smoke]')
  })

  it('honours a pre-aborted signal', async () => {
    const controller = new AbortController()
    controller.abort()
    const err = await runWebGpuGeneration({
      modelId: WEBGPU_DEFAULT_MODEL.id,
      prompt: 'hi',
      signal: controller.signal,
    }).catch((e) => e)
    expect(isAbortError(err)).toBe(true)
  })

  it('dispatches to an injected adapter', async () => {
    const injected: WebGpuAdapter = {
      id: 'test-adapter',
      describe: () => 'test adapter',
      load: vi.fn(async () => undefined),
      generate: vi.fn(async () => ({ text: 'ok', tokens: 1, adapterId: 'test-adapter' })),
    }
    setWebGpuAdapter(injected)
    const result = await runWebGpuGeneration({ modelId: 'm', prompt: 'x' })
    expect(result.adapterId).toBe('test-adapter')
    expect(injected.load).toHaveBeenCalledWith('m', { signal: undefined })
  })
})
