/**
 * #732 — no layout shift inside the composer pill while typing.
 *
 * The conditional kbd hints (Esc-to-clear ↔ ↵-send-now) used to mount and
 * unmount with the draft, so every first/last keystroke re-flowed the pill
 * and shoved the routing picker + mic sideways. The hint *content* may still
 * change, but the slot node must exist permanently and be sized even when
 * hidden — the slot reserves a fixed min-width.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ChatPage from '../../pages/ChatPage'
import { ToastProvider } from '../../components/DaisyUI/Toast'

class MockWebSocket {
  static CONNECTING = 0
  readyState = 0
  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()
}

vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)

function renderChat(initialEntry = '/chat?blueprint=api_agent') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function hintSlot(): HTMLElement | null {
  return screen.queryByTestId('composer-hint-slot')
}

describe('#732 composer hint slot never unmounts', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('keeps one hint slot node mounted across empty → typed → empty', async () => {
    const view = renderChat()
    const textarea = await screen.findByLabelText('Chat message')

    // The slot exists even with an empty draft (hidden, but mounted).
    const slotWithEmpty = hintSlot()
    expect(slotWithEmpty).not.toBeNull()

    fireEvent.change(textarea, { target: { value: 'hello' } })
    await waitFor(() => {
      expect(hintSlot()).toBe(slotWithEmpty)
    })

    fireEvent.change(textarea, { target: { value: '' } })
    expect(hintSlot()).toBe(slotWithEmpty)
    expect(view.baseElement).toBeTruthy()
  })

  it('shows the clear hint while a draft exists and the placeholder when empty', async () => {
    renderChat()
    const textarea = await screen.findByLabelText('Chat message')

    expect(screen.queryByTestId('composer-clear-hint')).not.toBeInTheDocument()

    fireEvent.change(textarea, { target: { value: 'hello' } })
    await waitFor(() => {
      expect(screen.getByTestId('composer-clear-hint')).toBeInTheDocument()
    })

    fireEvent.change(textarea, { target: { value: '' } })
    expect(screen.queryByTestId('composer-clear-hint')).not.toBeInTheDocument()
  })
})
