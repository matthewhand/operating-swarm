/**
 * #1288 — client-side WebGPU inference engine (experimental, browser-only).
 *
 * ## Scope / honesty
 *
 * This module is the *pluggable engine seam*. It ships the parts that are safe
 * to commit: capability detection, a cancellable model download with progress
 * callbacks + a Cache-API/memory store, and a cancellable generation entry
 * point. It deliberately does **not** bundle any model weights and does not add
 * a heavy runtime dependency to the repo.
 *
 * ## Adapter seam — why transformers.js
 *
 * The production target is **transformers.js** (Hugging Face) backed by ONNX
 * Runtime Web's WebGPU execution provider: it already ships web-native
 * tokenizers + a WebGPU EP, publishes quantized (including 1-bit/ternary Q1)
 * ONNX artifacts, and keeps the JS surface small. WebLLM/MLC is the faster
 * alternative but requires a compiled per-model WASM/GPU shim that we cannot
 * generate or commit here; raw WGSL would mean hand-writing dequant + matmul
 * kernels — out of scope. transformers.js is therefore the documented target,
 * wired through the injected `WebGpuAdapter` below so this module never has a
 * hard dependency on it.
 *
 * Until a real adapter is injected, `createPlaceholderAdapter()` is active. It
 * runs a deterministic, clearly-labelled smoke completion (`[webgpu-smoke]`)
 * so the UI pipeline (load -> stream tokens -> cancel) can be exercised without
 * real weights. It is *not* a model and must never be presented as one.
 */

export type WebGpuSupportReason = string

export interface WebGpuSupport {
  supported: boolean
  /** Honest, user-facing reason when `supported` is false. */
  reason?: WebGpuSupportReason
  /** Vendor/architecture/description when the adapter exposes it. */
  adapterInfo?: string
}

export interface WebGpuModelSpec {
  id: string
  label: string
  /** Remote artifact URL; empty means "configure via env / not shipped". */
  url: string
  /** Approximate artifact size in bytes; 0 when unknown. */
  sizeBytes: number
  quantization: string
  license: string
  /** Placeholder models ship no real weights and are smoke-only. */
  placeholder: boolean
  /** Optional expected SHA-256 (hex) of the artifact, when upstream provides it. */
  sha256?: string
}

/**
 * Catalogue of offerable models. No URLs are invented and no weights are
 * committed: every entry is inert until the operator supplies an artifact URL
 * (per-entry `url`, or `VITE_WEBGPU_*` env at build time).
 */
export const WEBGPU_MODEL_CATALOGUE: readonly WebGpuModelSpec[] = [
  {
    id: 'placeholder-tiny',
    label: 'Tiny placeholder (smoke only — ships no weights)',
    url: '',
    sizeBytes: 0,
    quantization: 'none',
    license: 'n/a',
    placeholder: true,
  },
  {
    id: 'bonsai2-27b',
    label: 'bonsai2-27b (ternary PTQ 1-bit)',
    url: '',
    sizeBytes: 0,
    quantization: 'ternary-ptq-1bit',
    license: 'verify upstream license before enabling',
    placeholder: false,
  },
]

export const WEBGPU_DEFAULT_MODEL: WebGpuModelSpec = WEBGPU_MODEL_CATALOGUE[0]

function envModelUrl(id: string): string {
  const env = (import.meta.env ?? {}) as Record<string, string | undefined>
  if (id === 'placeholder-tiny') return env.VITE_WEBGPU_TINY_URL ?? ''
  if (id === 'bonsai2-27b') return env.VITE_WEBGPU_BONSAI2_URL ?? ''
  return env.VITE_WEBGPU_MODEL_URL ?? ''
}

/** Explicit URL wins; otherwise an env-provided URL; otherwise empty. */
export function resolveModelUrl(spec: WebGpuModelSpec): string {
  return spec.url || envModelUrl(spec.id)
}

export class WebGpuInferenceError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'WebGpuInferenceError'
  }
}

function abortError(): DOMException {
  return new DOMException('Aborted', 'AbortError')
}

export function isAbortError(err: unknown): boolean {
  return (
    !!err &&
    typeof err === 'object' &&
    (err as { name?: string }).name === 'AbortError'
  )
}

interface WebGpuAdapterLike {
  info?: { vendor?: string; architecture?: string; description?: string }
  requestAdapterInfo?: () => Promise<{
    vendor?: string
    architecture?: string
    description?: string
  }>
}

interface WebGpuNavigatorLike {
  requestAdapter: (options?: unknown) => Promise<WebGpuAdapterLike | null>
}

/** `navigator.gpu` without hard-depending on the WebGPU TS lib definitions. */
function getGpu(): WebGpuNavigatorLike | undefined {
  if (typeof navigator === 'undefined') return undefined
  return (navigator as unknown as { gpu?: WebGpuNavigatorLike }).gpu
}

export function isWebGpuApiPresent(): boolean {
  return getGpu() !== undefined
}

function describeAdapter(adapter: WebGpuAdapterLike, info: WebGpuAdapterLike['info']): string | undefined {
  const resolved = info ?? adapter.info
  if (!resolved) return undefined
  const parts = [resolved.vendor, resolved.architecture, resolved.description]
    .map((p) => (p ?? '').trim())
    .filter(Boolean)
  return parts.length ? parts.join(' · ') : undefined
}

/**
 * Honest capability probe. Never throws for a missing API — a browser without
 * WebGPU is an expected, reportable state, not an error.
 */
export async function detectWebGpuSupport(): Promise<WebGpuSupport> {
  const gpu = getGpu()
  if (!gpu) {
    return {
      supported: false,
      reason: 'WebGPU unavailable: navigator.gpu is not present in this browser.',
    }
  }
  try {
    const adapter = await gpu.requestAdapter()
    if (!adapter) {
      return {
        supported: false,
        reason: 'WebGPU unavailable: no GPU adapter could be acquired.',
      }
    }
    let info: WebGpuAdapterLike['info']
    try {
      info = adapter.requestAdapterInfo ? await adapter.requestAdapterInfo() : adapter.info
    } catch {
      info = adapter.info
    }
    return { supported: true, adapterInfo: describeAdapter(adapter, info) }
  } catch (err) {
    return {
      supported: false,
      reason: `WebGPU unavailable: ${errorMessage(err)}`,
    }
  }
}

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return 'unknown error'
}

/* ------------------------------------------------------------------ store */

/**
 * Persistence seam for downloaded artifacts. The Cache API store survives
 * reloads; the in-memory store keeps tests hermetic and covers browsers where
 * `caches` is unavailable.
 */
export interface WebGpuStoredEntry {
  id: string
  bytes: number
}

export interface WebGpuModelStore {
  save(modelId: string, bytes: Uint8Array): Promise<void>
  load(modelId: string): Promise<Uint8Array | null>
  delete(modelId: string): Promise<void>
  /** Optional listing for the cache-management UI (size/usage + clear). */
  list?(): Promise<WebGpuStoredEntry[]>
}

const STORE_ORIGIN = 'https://webgpu.swarm.local/'

/** Suffix under which a cancelled/partial download is parked for resume. */
export const WEBGPU_PARTIAL_SUFFIX = '.partial'

export function partialModelKey(modelId: string): string {
  return `${modelId}${WEBGPU_PARTIAL_SUFFIX}`
}

export function isPartialModelKey(modelId: string): boolean {
  return modelId.endsWith(WEBGPU_PARTIAL_SUFFIX)
}

export function modelCacheKey(modelId: string): string {
  return `${STORE_ORIGIN}models/${encodeURIComponent(modelId)}`
}

export function memoryModelStore(): WebGpuModelStore {
  const map = new Map<string, Uint8Array>()
  return {
    async save(modelId, bytes) {
      map.set(modelId, bytes)
    },
    async load(modelId) {
      return map.get(modelId) ?? null
    },
    async delete(modelId) {
      map.delete(modelId)
    },
    async list() {
      return [...map.entries()].map(([id, bytes]) => ({ id, bytes: bytes.byteLength }))
    },
  }
}

export function cacheApiModelStore(cacheName = 'swarm-webgpu-models'): WebGpuModelStore {
  return {
    async save(modelId, bytes) {
      const cache = await caches.open(cacheName)
      await cache.put(new Request(modelCacheKey(modelId)), new Response(bytes.buffer as ArrayBuffer))
    },
    async load(modelId) {
      const cache = await caches.open(cacheName)
      const hit = await cache.match(new Request(modelCacheKey(modelId)))
      if (!hit) return null
      return new Uint8Array(await hit.arrayBuffer())
    },
    async delete(modelId) {
      const cache = await caches.open(cacheName)
      await cache.delete(new Request(modelCacheKey(modelId)))
    },
    async list() {
      const cache = await caches.open(cacheName)
      const requests = await cache.keys()
      const entries: WebGpuStoredEntry[] = []
      for (const request of requests) {
        const match = await cache.match(request)
        const id = decodeURIComponent(new URL(request.url).pathname.replace(/^\/models\//, ''))
        entries.push({ id, bytes: match ? (await match.clone().arrayBuffer()).byteLength : 0 })
      }
      return entries
    },
  }
}

let memoryStoreSingleton: WebGpuModelStore | null = null

export function defaultModelStore(): WebGpuModelStore {
  if (typeof caches !== 'undefined' && typeof caches.open === 'function') {
    return cacheApiModelStore()
  }
  // Memoised so a download and the card's cache read observe the same bytes.
  if (!memoryStoreSingleton) memoryStoreSingleton = memoryModelStore()
  return memoryStoreSingleton
}

let storeOverride: WebGpuModelStore | null = null

/** The store the card + download use. Tests inject a stable memory store. */
export function getDefaultModelStore(): WebGpuModelStore {
  return storeOverride ?? defaultModelStore()
}

export function setWebGpuModelStoreForTests(store: WebGpuModelStore | null): void {
  storeOverride = store
}

/* ---------------------------------------------------------- cache management */

export interface WebGpuCacheUsage {
  entries: WebGpuStoredEntry[]
  totalBytes: number
}

/** Enumerate cached (complete) artifacts; partials are reported separately. */
export async function webGpuCacheUsage(
  store: WebGpuModelStore = getDefaultModelStore(),
): Promise<WebGpuCacheUsage> {
  const listed = (await store.list?.()) ?? []
  const entries = listed.filter((entry) => !isPartialModelKey(entry.id))
  return {
    entries,
    totalBytes: entries.reduce((sum, entry) => sum + entry.bytes, 0),
  }
}

/** Delete every cached artifact (complete + partial) from the store. */
export async function clearWebGpuCache(
  store: WebGpuModelStore = getDefaultModelStore(),
): Promise<void> {
  const listed = (await store.list?.()) ?? []
  for (const entry of listed) await store.delete(entry.id)
  if (!store.list) {
    // Stores without `list` still expose the default catalogue ids.
    for (const spec of WEBGPU_MODEL_CATALOGUE) {
      await store.delete(spec.id)
      await store.delete(partialModelKey(spec.id))
    }
  }
}

/** HONEST both-way probe: is a complete artifact present in the store? */
export async function isModelCached(
  modelId: string,
  store: WebGpuModelStore = getDefaultModelStore(),
): Promise<boolean> {
  return (await store.load(modelId)) !== null
}

/* --------------------------------------------------------------- download */

export interface DownloadProgress {
  bytesDownloaded: number
  totalBytes: number | null
  percent: number | null
  /** Bytes already present from a prior cancelled download (HTTP Range resume). */
  resumedFrom: number
}

export interface DownloadOptions {
  signal?: AbortSignal
  onProgress?: (progress: DownloadProgress) => void
  store?: WebGpuModelStore
  /** Expected SHA-256 (hex) of the full artifact; overrides `spec.sha256`. */
  expectedSha256?: string
}

export interface DownloadResult {
  modelId: string
  bytes: number
  stored: boolean
  resumedFrom: number
  sha256: string | null
}

function concatChunks(chunks: readonly Uint8Array[], total: number): Uint8Array {
  const out = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.byteLength
  }
  return out
}

function parseContentRangeTotal(header: string | null): number | null {
  // e.g. `bytes 200-999/1000`
  const match = header ? /\/\s*(\d+)\s*$/.exec(header) : null
  if (!match) return null
  const total = Number.parseInt(match[1], 10)
  return Number.isFinite(total) && total > 0 ? total : null
}

/** SHA-256 hex via WebCrypto (present in browsers + Node ≥18). */
export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const subtle = (globalThis.crypto as Crypto | undefined)?.subtle
  if (!subtle) {
    throw new WebGpuInferenceError(
      'Integrity check unavailable: crypto.subtle is not present in this environment.',
    )
  }
  const digest = await subtle.digest('SHA-256', bytes as unknown as BufferSource)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Download a model artifact with byte-level progress callbacks, resumable via
 * HTTP `Range` when a cancelled partial is parked in the store. Cancellable
 * via `signal`; rejects with an `AbortError` DOMException. Throws an honest
 * `WebGpuInferenceError` when no artifact URL is configured, when the server
 * fails, or when the content-length/SHA-256 integrity check fails — never
 * invents a URL, never silently no-ops, and never stores a corrupt artifact.
 */
export async function downloadWebGpuModel(
  spec: WebGpuModelSpec,
  options: DownloadOptions = {},
): Promise<DownloadResult> {
  const { signal, onProgress, store = getDefaultModelStore() } = options
  const url = resolveModelUrl(spec)
  if (!url) {
    throw new WebGpuInferenceError(
      `No artifact URL configured for "${spec.id}". Set its url or a VITE_WEBGPU_* env value.`,
    )
  }
  if (signal?.aborted) throw abortError()

  const parked = await store.load(partialModelKey(spec.id))
  let offset = parked?.byteLength ?? 0
  if (signal?.aborted) throw abortError()
  const headers: Record<string, string> = offset > 0 ? { Range: `bytes=${offset}-` } : {}
  const response = await fetch(url, { signal, headers })
  if (!response.ok) {
    throw new WebGpuInferenceError(
      `Download failed: HTTP ${response.status} ${response.statusText}`.trim(),
    )
  }

  // The server ignored our Range and restarted from zero (200, not 206):
  // drop the parked partial so we do not splice mismatched bytes.
  const resumed = offset > 0 && response.status === 206
  if (offset > 0 && !resumed) offset = 0

  const headerLength = Number.parseInt(response.headers.get('content-length') ?? '', 10)
  const rangeTotal = resumed ? parseContentRangeTotal(response.headers.get('content-range')) : null
  const totalBytes =
    rangeTotal ??
    (Number.isFinite(headerLength) && headerLength > 0
      ? resumed
        ? offset + headerLength
        : headerLength
      : spec.sizeBytes > 0
        ? spec.sizeBytes
        : null)

  const emit = (bytesDownloaded: number) => {
    onProgress?.({
      bytesDownloaded,
      totalBytes,
      percent:
        totalBytes && totalBytes > 0
          ? Math.min(100, Math.round((bytesDownloaded / totalBytes) * 100))
          : null,
      resumedFrom: offset,
    })
  }

  const finish = async (full: Uint8Array): Promise<DownloadResult> => {
    if (totalBytes && full.byteLength !== totalBytes) {
      await store.delete(spec.id)
      await store.delete(partialModelKey(spec.id))
      throw new WebGpuInferenceError(
        `Integrity check failed: received ${full.byteLength} bytes, expected ${totalBytes}.`,
      )
    }
    const expectedSha = (options.expectedSha256 ?? spec.sha256 ?? '').trim().toLowerCase()
    let actualSha: string | null = null
    if (expectedSha) {
      actualSha = await sha256Hex(full)
      if (actualSha !== expectedSha) {
        await store.delete(spec.id)
        await store.delete(partialModelKey(spec.id))
        throw new WebGpuInferenceError(
          `Integrity check failed: SHA-256 mismatch (expected ${expectedSha.slice(0, 12)}…, got ${actualSha.slice(0, 12)}…).`,
        )
      }
    }
    await store.save(spec.id, full)
    await store.delete(partialModelKey(spec.id))
    return {
      modelId: spec.id,
      bytes: full.byteLength,
      stored: true,
      resumedFrom: offset,
      sha256: actualSha,
    }
  }

  const reader = response.body?.getReader()
  if (!reader) {
    const buffer = new Uint8Array(await response.arrayBuffer())
    const full =
      resumed && parked ? concatChunks([parked, buffer], parked.byteLength + buffer.byteLength) : buffer
    emit(full.byteLength)
    return finish(full)
  }

  const chunks: Uint8Array[] = []
  let received = 0
  const persistPartial = async () => {
    if (offset + received <= 0) return
    try {
      await store.save(
        partialModelKey(spec.id),
        concatChunks(resumed && parked ? [parked, ...chunks] : chunks, offset + received),
      )
    } catch {
      /* partial persistence is best-effort */
    }
  }
  try {
    for (;;) {
      if (signal?.aborted) throw abortError()
      const { done, value } = await reader.read()
      if (done) break
      if (value && value.byteLength > 0) {
        chunks.push(value)
        received += value.byteLength
        emit(offset + received)
      }
    }
  } catch (err) {
    try {
      await reader.cancel()
    } catch {
      /* cancel is best-effort */
    }
    if (isAbortError(err)) await persistPartial()
    throw err
  }

  const full = concatChunks(resumed && parked ? [parked, ...chunks] : chunks, offset + received)
  return finish(full)
}

/* -------------------------------------------------------------- inference */

export interface WebGpuGenerationRequest {
  modelId: string
  prompt: string
  maxTokens?: number
  signal?: AbortSignal
  onToken?: (token: string) => void
}

export interface WebGpuAdapterOutput {
  text: string
  tokens: number
  adapterId: string
}

export interface WebGpuGenerationResult extends WebGpuAdapterOutput {
  /** Wall-clock milliseconds for load + generate. */
  ms: number
}

/**
 * The pluggable backend. A real adapter (transformers.js / ONNX / WebLLM)
 * implements `load` + `generate` and can stream via `request.onToken`.
 */
export interface WebGpuAdapter {
  id: string
  /** Honest, user-facing description of the *actual* backend in use. */
  describe(): string
  load(modelId: string, options?: { signal?: AbortSignal }): Promise<void>
  generate(request: WebGpuGenerationRequest): Promise<WebGpuAdapterOutput>
}

export const WEBGPU_PLACEHOLDER_ADAPTER_ID = 'placeholder-smoke'

/**
 * Deterministic smoke adapter. It never claims to be a real model: the output
 * is prefixed `[webgpu-smoke]` and `describe()` says so explicitly.
 */
export function createPlaceholderAdapter(): WebGpuAdapter {
  let loadedModel: string | null = null
  return {
    id: WEBGPU_PLACEHOLDER_ADAPTER_ID,
    describe: () =>
      'placeholder smoke adapter — no real weights; a transformers.js/WebGPU backend is not wired in this build',
    async load(modelId, options) {
      if (options?.signal?.aborted) throw abortError()
      loadedModel = modelId
    },
    async generate(request) {
      if (request.signal?.aborted) throw abortError()
      if (!loadedModel) {
        throw new WebGpuInferenceError('Adapter not loaded: call load() before generate().')
      }
      const text = `[webgpu-smoke] ${request.prompt.slice(0, 60)}`
      const allTokens = text.split(/\s+/).filter(Boolean)
      const limit = typeof request.maxTokens === 'number' ? Math.max(1, request.maxTokens) : allTokens.length
      const tokens = allTokens.slice(0, limit)
      let emitted = ''
      for (const token of tokens) {
        if (request.signal?.aborted) throw abortError()
        emitted += `${token} `
        request.onToken?.(`${token} `)
        await Promise.resolve()
      }
      return { text: emitted, tokens: tokens.length, adapterId: WEBGPU_PLACEHOLDER_ADAPTER_ID }
    },
  }
}

let activeAdapter: WebGpuAdapter = createPlaceholderAdapter()

export function getWebGpuAdapter(): WebGpuAdapter {
  return activeAdapter
}

/** Inject a real backend (transformers.js adapter, test double, …). */
export function setWebGpuAdapter(adapter: WebGpuAdapter): void {
  activeAdapter = adapter
}

export function resetWebGpuAdapter(): void {
  activeAdapter = createPlaceholderAdapter()
}

function monotonicNow(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

/**
 * Load + run one cancellable generation against the active adapter. Aborts
 * surface as `AbortError` so callers can distinguish cancel from failure.
 */
export async function runWebGpuGeneration(
  request: WebGpuGenerationRequest,
): Promise<WebGpuGenerationResult> {
  if (request.signal?.aborted) throw abortError()
  const adapter = activeAdapter
  const startedAt = monotonicNow()
  await adapter.load(request.modelId, { signal: request.signal })
  const output = await adapter.generate(request)
  return { ...output, ms: Math.max(0, Math.round(monotonicNow() - startedAt)) }
}

/**
 * Best-effort peak/current JS-heap reading. Chromium exposes
 * `performance.memory.usedJSHeapSize`; every other engine (and the test env)
 * does not, in which case we return `null` and the UI must say "unavailable"
 * rather than fabricate a number.
 */
export function readPeakMemoryBytes(): number | null {
  const memory = (
    performance as unknown as { memory?: { usedJSHeapSize?: number } } | undefined
  )?.memory
  const used = memory?.usedJSHeapSize
  return typeof used === 'number' && Number.isFinite(used) && used > 0 ? used : null
}
