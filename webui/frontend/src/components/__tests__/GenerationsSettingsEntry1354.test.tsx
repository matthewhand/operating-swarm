/**
 * #1354 — the agent generations diagnostics entry lives in
 * Settings → System (About & diagnostics), not the prime navbar. Clicking it
 * dispatches the shared event; the sheet closes so the panel is not hidden.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import { SystemPane } from '../settings/panes/SystemPane'
import { OPEN_GENERATIONS_EVENT } from '../settings/generationsEntry'

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function stubFetch() {
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
}

describe('#1354 — Settings generations entry', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('SystemPane renders the About & diagnostics entry and dispatches the event', () => {
    stubFetch()
    const spy = vi.fn()
    window.addEventListener(OPEN_GENERATIONS_EVENT, spy)
    render(
      <QueryClientProvider client={client()}>
        <SystemPane />
      </QueryClientProvider>,
    )
    expect(screen.getByText('About & diagnostics')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('settings-open-generations'))
    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener(OPEN_GENERATIONS_EVENT, spy)
  })

  it('SettingsSheet surfaces the entry on the System section and closes on dispatch', async () => {
    stubFetch()
    const onClose = vi.fn()
    render(
      <QueryClientProvider client={client()}>
        <ToastProvider>
          <SettingsSheet isOpen={true} onClose={onClose} initialSection="system" />
        </ToastProvider>
      </QueryClientProvider>,
    )
    const entry = await screen.findByTestId('settings-open-generations')
    expect(entry).toHaveTextContent(/Open agent generations/i)
    window.dispatchEvent(new CustomEvent(OPEN_GENERATIONS_EVENT))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
