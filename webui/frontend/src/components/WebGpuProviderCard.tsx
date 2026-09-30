/**
 * #1288 — WebGPU provider surface (experimental, browser-only).
 *
 * Shows honest support status, a model picker from the catalogue, a
 * resume-safe cancellable download with live byte progress + integrity
 * checking, persistent cache usage with a clear action, and a cancellable
 * smoke "Test" run executed in the Web Worker that reports device/backend,
 * latency, tok/s and peak memory (or an explicit "unavailable").
 *
 * There is no silent server fallback: when WebGPU is absent the Test action
 * reports the detection reason verbatim, and the target model degrades to the
 * clearly-labelled placeholder adapter.
 *
 * The component is only ever mounted behind the `webgpu` experimental flag
 * (see `ExperimentalPane` and `ProvidersPane`); it does not read the flag
 * itself so it stays a pure, testable leaf.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  WEBGPU_MODEL_CATALOGUE,
  clearWebGpuCache,
  detectWebGpuSupport,
  downloadWebGpuModel,
  getDefaultModelStore,
  isAbortError,
  isModelCached,
  webGpuCacheUsage,
  type DownloadProgress,
  type WebGpuCacheUsage,
  type WebGpuSupport,
} from '../lib/webgpuInference'
import { getWebGpuWorkerClient } from '../lib/webgpuWorkerClient'
import type { WebGpuWorkerStats } from '../lib/webgpuWorkerProtocol'
import { selectWebGpuClientModel } from '../lib/webgpuClientSeat'

type DownloadState =
  | { status: 'idle' }
  | { status: 'downloading'; progress: DownloadProgress }
  | { status: 'ready'; bytes: number }
  | { status: 'error'; error: string }

type TestState =
  | { status: 'idle' }
  | { status: 'running'; output: string }
  | { status: 'done'; output: string; stats: WebGpuWorkerStats }
  | { status: 'error'; error: string }

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return 'unknown error'
}

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatMemory(bytes: number | null): string {
  return bytes === null ? 'unavailable' : formatBytes(bytes)
}

export function WebGpuProviderCard() {
  const [support, setSupport] = useState<WebGpuSupport | null>(null)
  const [modelId, setModelId] = useState(WEBGPU_MODEL_CATALOGUE[0].id)
  const [download, setDownload] = useState<DownloadState>({ status: 'idle' })
  const [test, setTest] = useState<TestState>({ status: 'idle' })
  const [cacheUsage, setCacheUsage] = useState<WebGpuCacheUsage | null>(null)
  const downloadAbort = useRef<AbortController | null>(null)
  const testAbort = useRef<AbortController | null>(null)

  const model =
    WEBGPU_MODEL_CATALOGUE.find((m) => m.id === modelId) ?? WEBGPU_MODEL_CATALOGUE[0]

  const refreshCacheUsage = useCallback(async () => {
    try {
      setCacheUsage(await webGpuCacheUsage())
    } catch {
      setCacheUsage({ entries: [], totalBytes: 0 })
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void detectWebGpuSupport().then((result) => {
      if (!cancelled) setSupport(result)
    })
    return () => {
      cancelled = true
      downloadAbort.current?.abort()
      testAbort.current?.abort()
    }
  }, [])

  // Ready-state persistence: re-hydrate `ready` by probing the Cache API /
  // store for the selected model, so a reload reports accurately.
  useEffect(() => {
    let cancelled = false
    void isModelCached(model.id).then((cached) => {
      if (cancelled) return
      if (cached) setDownload({ status: 'ready', bytes: model.sizeBytes })
      else setDownload({ status: 'idle' })
    })
    void refreshCacheUsage()
    return () => {
      cancelled = true
    }
  }, [model.id, model.sizeBytes, refreshCacheUsage])

  const handleDownload = useCallback(async () => {
    downloadAbort.current?.abort()
    const controller = new AbortController()
    downloadAbort.current = controller
    setDownload({
      status: 'downloading',
      progress: {
        bytesDownloaded: 0,
        totalBytes: model.sizeBytes > 0 ? model.sizeBytes : null,
        percent: null,
        resumedFrom: 0,
      },
    })
    try {
      const result = await downloadWebGpuModel(model, {
        signal: controller.signal,
        store: getDefaultModelStore(),
        onProgress: (progress) => setDownload({ status: 'downloading', progress }),
      })
      setDownload({ status: 'ready', bytes: result.bytes })
      await refreshCacheUsage()
    } catch (err) {
      if (isAbortError(err)) {
        setDownload({ status: 'idle' })
        await refreshCacheUsage()
        return
      }
      setDownload({ status: 'error', error: errorMessage(err) })
    }
  }, [model, refreshCacheUsage])

  const handleCancelDownload = useCallback(() => {
    downloadAbort.current?.abort()
  }, [])

  const handleClearCache = useCallback(async () => {
    try {
      await clearWebGpuCache()
      await refreshCacheUsage()
      setDownload({ status: 'idle' })
    } catch (err) {
      setDownload({ status: 'error', error: errorMessage(err) })
    }
  }, [refreshCacheUsage])

  const handleTest = useCallback(async () => {
    testAbort.current?.abort()
    const controller = new AbortController()
    testAbort.current = controller
    setTest({ status: 'running', output: '' })

    const detected = await detectWebGpuSupport()
    setSupport(detected)
    if (!detected.supported) {
      setTest({ status: 'error', error: detected.reason ?? 'WebGPU unavailable.' })
      return
    }

    try {
      const stats = await getWebGpuWorkerClient().generate(
        { modelId: model.id, prompt: 'Hello from the WebGPU smoke test.', maxTokens: 1 },
        {
          signal: controller.signal,
          onToken: (token) =>
            setTest((prev) =>
              prev.status === 'running'
                ? { status: 'running', output: prev.output + token }
                : prev,
            ),
        },
      )
      setTest({ status: 'done', output: stats.text, stats })
    } catch (err) {
      if (isAbortError(err)) {
        setTest({ status: 'idle' })
        return
      }
      setTest({ status: 'error', error: errorMessage(err) })
    }
  }, [model])

  const handleCancelTest = useCallback(() => {
    testAbort.current?.abort()
  }, [])

  const handleUseInComposer = useCallback(() => {
    selectWebGpuClientModel(model.id)
  }, [model])

  return (
    <div
      className="card border border-base-300 bg-base-200/40 p-4"
      data-testid="webgpu-provider-card"
      data-supported={support?.supported ? 'true' : 'false'}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-medium">
            WebGPU in-browser provider
            <span className="ml-2 badge badge-ghost badge-xs align-middle">Experimental</span>
          </p>
          <p className="mt-1 text-sm text-base-content/70">
            Runs inference in this browser tab. There is no server fallback: if WebGPU is
            unavailable, nothing is silently routed elsewhere.
          </p>
        </div>
      </div>

      <div className="mt-3 space-y-3">
        <p className="text-xs" data-testid="webgpu-support-status">
          {support === null
            ? 'Checking WebGPU…'
            : support.supported
              ? `WebGPU available${support.adapterInfo ? ` · ${support.adapterInfo}` : ''}`
              : `WebGPU unavailable — ${support.reason ?? 'unsupported browser'}`}
        </p>

        <div className="flex flex-wrap items-end gap-2">
          <label className="form-control">
            <span className="mb-1 text-xs text-base-content/70">Model</span>
            <select
              className="select select-sm select-bordered"
              data-testid="webgpu-model-select"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
            >
              {WEBGPU_MODEL_CATALOGUE.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-sm"
            data-testid="webgpu-download"
            disabled={download.status === 'downloading'}
            onClick={() => void handleDownload()}
          >
            Download
          </button>
          {download.status === 'downloading' && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              data-testid="webgpu-cancel-download"
              onClick={handleCancelDownload}
            >
              Cancel
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm btn-primary"
            data-testid="webgpu-test"
            disabled={test.status === 'running'}
            onClick={() => void handleTest()}
          >
            Test
          </button>
          {test.status === 'running' && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              data-testid="webgpu-cancel-test"
              onClick={handleCancelTest}
            >
              Cancel test
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm btn-outline"
            data-testid="webgpu-use-in-composer"
            onClick={handleUseInComposer}
          >
            Use in composer
          </button>
        </div>

        <p className="text-xs text-base-content/70" data-testid="webgpu-download-status">
          {model.quantization !== 'none' ? `Quantization: ${model.quantization}. ` : ''}
          {download.status === 'downloading'
            ? `Downloading… ${formatBytes(download.progress.bytesDownloaded)}${
                download.progress.percent === null ? '' : ` (${download.progress.percent}%)`
              }${download.progress.resumedFrom > 0 ? ` · resumed from ${formatBytes(download.progress.resumedFrom)}` : ''}`
            : download.status === 'ready'
              ? `Cached (${formatBytes(download.bytes)})`
              : 'Not downloaded'}
        </p>

        {download.status === 'error' && (
          <p className="text-xs text-error" data-testid="webgpu-download-error">
            Download error: {download.error}
          </p>
        )}

        <div className="rounded-md border border-base-300/60 bg-base-100/40 px-2 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-base-content/70" data-testid="webgpu-cache-usage">
              Cache: {cacheUsage ? `${formatBytes(cacheUsage.totalBytes)} across ${cacheUsage.entries.length} model(s)` : 'checking…'}
            </p>
            <button
              type="button"
              className="btn btn-xs btn-ghost"
              data-testid="webgpu-clear-cache"
              onClick={() => void handleClearCache()}
            >
              Clear cache
            </button>
          </div>
        </div>

        {test.status === 'error' && (
          <p className="text-xs text-error" data-testid="webgpu-test-error">
            Test failed: {test.error}
          </p>
        )}

        {test.status === 'running' && (
          <p className="text-xs text-base-content/70" data-testid="webgpu-test-output">
            {test.output || 'Running…'}
          </p>
        )}

        {test.status === 'done' && (
          <div className="text-xs text-base-content/70" data-testid="webgpu-test-result">
            <p data-testid="webgpu-test-output">{test.output}</p>
            <p className="mt-1" data-testid="webgpu-test-stats">
              Adapter: {test.stats.adapter} · backend: {test.stats.backend} ·{' '}
              {test.stats.ms} ms · {test.stats.tokensPerSecond.toFixed(1)} tok/s · peak
              memory: {formatMemory(test.stats.peakMemoryBytes)}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default WebGpuProviderCard
