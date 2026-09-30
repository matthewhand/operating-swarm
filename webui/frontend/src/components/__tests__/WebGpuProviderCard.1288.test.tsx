/**
 * #1288 — WebGPU provider surface: honest unsupported errors, gated mounting,
 * a mocked-WebGPU smoke run, and a UI download driven by stubbed fetch/env.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI'
import { WebGpuProviderCard } from '../WebGpuProviderCard'
import { ExperimentalPane } from '../settings/panes/ExperimentalPane'
import { resetWebGpuAdapter } from '../../lib/webgpuInference'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

const GPU_FLAG_KEY = 'swarm_experimental_webgpu'

function defineGpu(value: unknown) {
  Object.defineProperty(navigator, 'gpu', { configurable: true, value })
}

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function stubPrefsFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes('/v1/preferences/')) {
        return jsonResponse({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
          hostname_override: '',
          values: {},
        })
      }
      return jsonResponse({ object: 'list', data: [] })
    }),
  )
}

beforeEach(() => {
  localStorage.clear()
  __resetUserPrefsCacheForTests()
})

afterEach(() => {
  delete (navigator as { gpu?: unknown }).gpu
  resetWebGpuAdapter()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  localStorage.clear()
  __resetUserPrefsCacheForTests()
})

describe('#1288 WebGpuProviderCard', () => {
  it('reports WebGPU unavailable and surfaces an honest Test error', async () => {
    defineGpu(undefined)
    render(<WebGpuProviderCard />)

    await waitFor(() =>
      expect(screen.getByTestId('webgpu-support-status')).toHaveTextContent(
        /WebGPU unavailable/,
      ),
    )

    fireEvent.click(screen.getByTestId('webgpu-test'))
    const error = await screen.findByTestId('webgpu-test-error')
    expect(error).toHaveTextContent(/WebGPU unavailable/)
    expect(error).toHaveTextContent(/navigator\.gpu is not present/)
    // No silent fallback: the placeholder adapter must not have run.
    expect(screen.queryByTestId('webgpu-test-result')).not.toBeInTheDocument()
  })

  it('runs a 1-token smoke generation when WebGPU is present', async () => {
    defineGpu({ requestAdapter: async () => ({ info: { vendor: 'Mock GPU' } }) })
    render(<WebGpuProviderCard />)

    await screen.findByText(/WebGPU available/)

    fireEvent.click(screen.getByTestId('webgpu-test'))
    const result = await screen.findByTestId('webgpu-test-result')
    expect(result).toHaveTextContent('[webgpu-smoke]')
    expect(result).toHaveTextContent(/placeholder smoke adapter/)
  })

  it('downloads with progress callbacks and reports the cached model', async () => {
    vi.stubEnv('VITE_WEBGPU_TINY_URL', 'https://example.test/tiny.bin')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(new Uint8Array([1, 2, 3]))
              controller.enqueue(new Uint8Array([4, 5]))
              controller.close()
            },
          }),
          { status: 200, headers: { 'content-length': '5' } },
        ),
      ),
    )
    render(<WebGpuProviderCard />)

    fireEvent.click(screen.getByTestId('webgpu-download'))
    await waitFor(() =>
      expect(screen.getByTestId('webgpu-download-status')).toHaveTextContent(/Cached/),
    )
    expect(screen.queryByTestId('webgpu-download-error')).not.toBeInTheDocument()
  })
})

describe('#1288 ExperimentalPane gating', () => {
  function renderPane() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <ExperimentalPane />
        </ToastProvider>
      </QueryClientProvider>,
    )
  }

  it('hides the WebGPU provider card until its flag is enabled', async () => {
    stubPrefsFetch()
    const view = renderPane()
    await screen.findByTestId('experimental-pane')
    expect(screen.queryByTestId('webgpu-provider-card')).not.toBeInTheDocument()

    view.unmount()
    localStorage.setItem(GPU_FLAG_KEY, 'on')
    renderPane()
    expect(await screen.findByTestId('webgpu-provider-card')).toBeInTheDocument()
  })
})
