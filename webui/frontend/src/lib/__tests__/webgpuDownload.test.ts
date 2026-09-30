/**
 * #1288 — download state machine: HTTP Range resume, honest integrity failure,
 * and cache-management usage/clear. `fetch` is stubbed; no network is touched.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import {
  WEBGPU_DEFAULT_MODEL,
  clearWebGpuCache,
  downloadWebGpuModel,
  memoryModelStore,
  isModelCached,
  partialModelKey,
  sha256Hex,
  webGpuCacheUsage,
  type WebGpuModelSpec,
} from '../webgpuInference'

const spec: WebGpuModelSpec = { ...WEBGPU_DEFAULT_MODEL, id: 'model-x', url: 'https://x.test/m.bin' }

beforeAll(() => {
  if (!globalThis.crypto || !(globalThis.crypto as Crypto).subtle) {
    vi.stubGlobal('crypto', webcrypto)
  }
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('#1288 resumable download', () => {
  it('resumes from a parked partial via Range and completes the artifact', async () => {
    const store = memoryModelStore()
    await store.save(partialModelKey(spec.id), new Uint8Array([1, 2, 3]))

    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect((init?.headers as Record<string, string>).Range).toBe('bytes=3-')
      return new Response(new Uint8Array([4, 5]), {
        status: 206,
        headers: { 'content-range': 'bytes 3-4/5' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await downloadWebGpuModel(spec, { store })
    expect(result).toMatchObject({ bytes: 5, resumedFrom: 3, stored: true })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect([...(await store.load(spec.id))!]).toEqual([1, 2, 3, 4, 5])
    // The parked partial is consumed, not left behind.
    expect(await store.load(partialModelKey(spec.id))).toBeNull()
  })

  it('restarts from zero when the server ignores Range (200, not 206)', async () => {
    const store = memoryModelStore()
    await store.save(partialModelKey(spec.id), new Uint8Array([9, 9, 9]))
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(new Uint8Array([1, 2, 3]), {
          status: 200,
          headers: { 'content-length': '3' },
        }),
      ),
    )
    const result = await downloadWebGpuModel(spec, { store })
    expect(result.bytes).toBe(3)
    expect([...(await store.load(spec.id))!]).toEqual([1, 2, 3])
  })

  it('fails the content-length integrity check honestly and stores nothing', async () => {
    const store = memoryModelStore()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(new Uint8Array([1, 2, 3, 4, 5]), {
          status: 200,
          headers: { 'content-length': '6' },
        }),
      ),
    )
    await expect(downloadWebGpuModel(spec, { store })).rejects.toThrow(/Integrity check failed/)
    expect(await isModelCached(spec.id, store)).toBe(false)
  })

  it('fails the SHA-256 integrity check when a digest is provided', async () => {
    const store = memoryModelStore()
    const body = new Uint8Array([1, 2, 3, 4, 5])
    const good = await sha256Hex(body)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(body, { status: 200, headers: { 'content-length': '5' } }),
      ),
    )
    // Wrong expected digest → reject.
    await expect(
      downloadWebGpuModel({ ...spec, sha256: 'deadbeef' }, { store }),
    ).rejects.toThrow(/SHA-256 mismatch/)
    expect(await isModelCached(spec.id, store)).toBe(false)

    // Correct digest → stored.
    const ok = await downloadWebGpuModel({ ...spec, sha256: good }, { store })
    expect(ok.sha256).toBe(good)
    expect(await isModelCached(spec.id, store)).toBe(true)
  })
})

describe('#1288 cache management', () => {
  it('reports usage across cached models and clears it', async () => {
    const store = memoryModelStore()
    await store.save('a', new Uint8Array(10))
    await store.save('b', new Uint8Array(32))
    await store.save('c.partial', new Uint8Array(999)) // partials excluded

    const usage = await webGpuCacheUsage(store)
    expect(usage.totalBytes).toBe(42)
    expect(usage.entries.map((e) => e.id).sort()).toEqual(['a', 'b'])

    await clearWebGpuCache(store)
    const cleared = await webGpuCacheUsage(store)
    expect(cleared.totalBytes).toBe(0)
    expect(cleared.entries).toEqual([])
  })
})
