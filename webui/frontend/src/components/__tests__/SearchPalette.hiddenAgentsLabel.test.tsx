/**
 * #826 follow-up (visual sweep) — the search palette's Actions row must use
 * the relabelled "Hidden Agents" copy, not the legacy "Hidden Bots".
 *
 * The rail was relabelled in #826, but the palette's action row kept the old
 * word. The defensible contract: the string "Bots" must not appear anywhere
 * in the palette DOM (the tab is "Agents", the action row must read
 * "Hidden Agents"), so a future copy regression anywhere in the dialog fails
 * loudly.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SearchPalette from '../SearchPalette'

function renderPalette() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SearchPalette open={true} onClose={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('#826 follow-up: search palette copy', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ data: [{ id: 'codey', name: 'Codey', description: 'Dev agent', rail: true }] }),
          }
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) }
      }) as unknown as typeof fetch,
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('renders the unhide action as "Hidden Agents" (no "Bots" anywhere in the palette)', async () => {
    renderPalette()

    // Action rows live on the Actions tab.
    fireEvent.click(screen.getByRole('tab', { name: 'Actions' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Hidden Agents')).toBeInTheDocument()

    // Whole-dialog guard: the legacy word is gone from every surface of the
    // palette (tabs, action rows, empty states, hints).
    expect(within(dialog).queryByText(/bots/i)).not.toBeInTheDocument()
  })
})
