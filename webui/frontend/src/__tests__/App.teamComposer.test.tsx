import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import App from '../App'

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
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
    renderApp()

    expect(screen.queryByRole('navigation', { name: 'Primary' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Home' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Chat' })).toBeNull()
    expect(
      screen.queryByRole('link', { name: 'Teams' }),
    ).toBeNull()

    fireEvent.click(screen.getByTestId('os-teams-button'))
    // The #892 redesign retitled the dialog to 'Manage Teams' (role entry).
    expect(await screen.findByRole('dialog', { name: /manage teams/i })).toBeInTheDocument()
    expect(screen.getByTestId('team-drop-zone')).toHaveTextContent(/drop agents here/i)
    expect(screen.getByTestId('team-cos-select')).toBeDisabled()
    expect(screen.getAllByText(/add agents first/i).length).toBeGreaterThan(0)
    // #508: roles/tools live behind tier tabs — absent from the opening frame.
    expect(screen.queryByTestId('team-roles-pane')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Roles' }))
    expect(screen.getByTestId('team-roles-pane')).toHaveAttribute('aria-disabled', 'true')
    // Overlay — Chat route stays mounted (REQ-364 / #364).
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })
})
