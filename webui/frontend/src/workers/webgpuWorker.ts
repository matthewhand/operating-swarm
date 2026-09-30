/**
 * #1288 — WebGPU inference Web Worker entry.
 *
 * This module runs on the worker thread. It installs the typed message handler
 * from `webgpuWorkerProtocol` so `load` + `generate` (and, in a real build, the
 * transformers.js/ONNX-Web runtime) never touch the main thread. No weights or
 * secrets live here; model artifacts are resolved/cached by the main thread.
 */
import {
  getWebGpuAdapter,
  readPeakMemoryBytes,
  runWebGpuGeneration,
} from '../lib/webgpuInference'
import {
  createWebGpuWorkerHandler,
  type WebGpuWorkerRequest,
} from '../lib/webgpuWorkerProtocol'

interface WorkerScopeLike {
  postMessage: (message: unknown) => void
  onmessage: ((event: { data: WebGpuWorkerRequest }) => void) | null
}

const scope = self as unknown as WorkerScopeLike

const handler = createWebGpuWorkerHandler({
  backend: 'webgpu-worker',
  describeAdapter: () => getWebGpuAdapter().describe(),
  runGeneration: (request) => runWebGpuGeneration(request),
  readPeakMemoryBytes,
  post: (message) => scope.postMessage(message),
})

scope.onmessage = (event) => handler(event.data)

scope.postMessage({
  type: 'ready',
  backend: 'webgpu-worker',
  adapter: getWebGpuAdapter().describe(),
})
