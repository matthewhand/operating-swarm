import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import App from '../App'

async function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
  // #1629: the chat surface is a lazy chunk now; wait for the first painted
  // frame instead of racing the dynamic import.
  await screen.findByRole('textbox', { name: 'Chat message' })
  return view
}

describe('SPA + team composer entry', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens the overlay from + without restoring a Home/Chat top nav', async () => {
    await renderApp()

    expect(screen.queryByRole('navigation', { name: 'Primary' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Home' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Chat' })).toBeNull()
    expect(
      screen.queryByRole('link', { name: 'Teams' }),
    ).toBeNull()

    fireEvent.click(screen.getByTestId('os-teams-button'))
    // #1222: the dialog is the Rigs composer now.
    expect(await screen.findByRole('dialog', { name: /group chats/i })).toBeInTheDocument()
    expect(screen.getByTestId('team-drop-zone')).toHaveTextContent(/drop agents here/i)
    expect(screen.getByTestId('team-cos-select')).toBeDisabled()
    expect(screen.getAllByText(/add agents first/i).length).toBeGreaterThan(0)
    // #780: the Roles facet is the default tab below the permanent roster —
    // present on the opening frame and disabled until agents are added.
    expect(screen.getByTestId('team-roles-pane')).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Roles' }))
    expect(screen.getByTestId('team-roles-pane')).toHaveAttribute('aria-disabled', 'true')
    // Overlay — Chat route stays mounted (REQ-364 / #364).
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })
})
