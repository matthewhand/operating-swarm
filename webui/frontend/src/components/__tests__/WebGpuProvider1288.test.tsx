/**
 * #1288 — provider card: ready-state re-hydration across remounts, cache usage
 * + clear, and worker-backed test metrics (tok/s, latency, peak memory).
 */
import { afterEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { WebGpuProviderCard } from '../WebGpuProviderCard'
import {
  WEBGPU_DEFAULT_MODEL,
  memoryModelStore,
  setWebGpuModelStoreForTests,
} from '../../lib/webgpuInference'
import { resetWebGpuWorkerClientForTests } from '../../lib/webgpuWorkerClient'
import { resetWebGpuAdapter } from '../../lib/webgpuInference'

function defineGpu(value: unknown) {
  Object.defineProperty(navigator, 'gpu', { configurable: true, value })
}

afterEach(() => {
  setWebGpuModelStoreForTests(null)
  resetWebGpuWorkerClientForTests()
  resetWebGpuAdapter()
  delete (navigator as { gpu?: unknown }).gpu
})

describe('#1288 provider card cache persistence', () => {
  it('re-hydrates the ready state by probing the store after a remount', async () => {
    const store = memoryModelStore()
    await store.save(WEBGPU_DEFAULT_MODEL.id, new Uint8Array([1, 2, 3]))
    setWebGpuModelStoreForTests(store)

    const first = render(<WebGpuProviderCard />)
    await waitFor(() =>
      expect(screen.getByTestId('webgpu-download-status')).toHaveTextContent(/Cached/),
    )
    first.unmount()

    render(<WebGpuProviderCard />)
    await waitFor(() =>
      expect(screen.getByTestId('webgpu-download-status')).toHaveTextContent(/Cached/),
    )
  })

  it('clears the cache and updates the reported usage', async () => {
    const store = memoryModelStore()
    await store.save(WEBGPU_DEFAULT_MODEL.id, new Uint8Array(3))
    setWebGpuModelStoreForTests(store)

    render(<WebGpuProviderCard />)
    await waitFor(() =>
      expect(screen.getByTestId('webgpu-cache-usage')).toHaveTextContent(/3 B/),
    )

    fireEvent.click(screen.getByTestId('webgpu-clear-cache'))
    await waitFor(() =>
      expect(screen.getByTestId('webgpu-cache-usage')).toHaveTextContent(/0 B/),
    )
  })
})

describe('#1288 provider card worker metrics', () => {
  it('reports adapter, backend, latency, tok/s and peak memory from the worker', async () => {
    defineGpu({ requestAdapter: async () => ({ info: { vendor: 'Mock GPU' } }) })
    render(<WebGpuProviderCard />)
    await screen.findByText(/WebGPU available/)

    fireEvent.click(screen.getByTestId('webgpu-test'))
    const stats = await screen.findByTestId('webgpu-test-stats')
    expect(stats).toHaveTextContent(/placeholder smoke adapter/)
    expect(stats).toHaveTextContent(/backend: in-process/)
    expect(stats).toHaveTextContent(/tok\/s/)
    expect(stats).toHaveTextContent(/peak memory: unavailable/)
  })
})
