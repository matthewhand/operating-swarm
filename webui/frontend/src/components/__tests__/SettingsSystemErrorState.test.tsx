import {render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, afterEach } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'

describe('REQ-188C-2: Settings System must not look empty when /v1/system/ fails', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders visible error UI with retry button when GET /v1/system/ fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Internal server error 500')),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <SettingsSheet isOpen={true} onClose={vi.fn()} initialSection="system" />
        </ToastProvider>
      </QueryClientProvider>,
    )

    // Should display the error UI
    const errorContainer = await screen.findByTestId('system-store-error')
    expect(errorContainer).toBeInTheDocument()
    expect(errorContainer).toHaveTextContent(/Failed to load local database facts/i)

    // Should have retry button
    const retryBtn = screen.getByRole('button', { name: 'Retry' })
    expect(retryBtn).toBeInTheDocument()

    // Must NOT paint false "not created yet" or "0 B"
    expect(screen.queryByText('not created yet')).toBeNull()
  })

  it('renders 0 and not created yet when local store returns honest missing 200 (created: false)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          created: false,
          size_bytes: 0,
          path: '',
          conversation_count: 0,
          message_count: 0,
        }),
      } as Response),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <SettingsSheet isOpen={true} onClose={vi.fn()} initialSection="system" />
        </ToastProvider>
      </QueryClientProvider>,
    )

    const notCreated = await screen.findAllByText('not created yet')
    expect(notCreated.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Conversations').closest('div')).toHaveTextContent('0')
    expect(screen.getByText('Messages').closest('div')).toHaveTextContent('0')
    expect(screen.queryByTestId('system-store-error')).toBeNull()
  })
})
