/**
 * #494 — the navbar warning stops being inert prose: when the backend stamps
 * an action on the failure, the picker renders a "Fix in Settings" link that
 * opens Remotes focused on that remote. No action → today's text, unchanged.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { NavbarRoutingPicker } from '../NavbarRoutingPicker'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'

function renderPicker(
  props: Partial<ComponentProps<typeof NavbarRoutingPicker>> = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NavbarRoutingPicker
        seatKind="remote"
        agents={[{ id: 'omb', label: 'OpenMousBot' }]}
        selectedAgent=""
        models={[]}
        selectedModel=""
        onChange={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  )
}

describe('NavbarRoutingPicker #494 actionable warning', () => {
  it('renders plain text when the warning has no action (no regression)', async () => {
    renderPicker({ modelWarning: 'Remote agent list failed' })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    const warning = await screen.findByTestId('routing-model-warning')
    expect(warning).toHaveTextContent('Remote agent list failed')
    expect(screen.queryByTestId('routing-model-warning-action')).not.toBeInTheDocument()
  })

  it('renders a Fix link when the warning carries an action', async () => {
    const listener = vi.fn()
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    try {
      renderPicker({
        modelWarning: 'OpenMousBot list requires auth.',
        modelWarningAction: {
          kind: 'settings',
          section: 'remotes',
          remote: 'omb',
          field: 'api_key_env',
        },
      })
      fireEvent.click(screen.getByTestId('routing-pill-model'))
      const warning = await screen.findByTestId('routing-model-warning')
      expect(warning).toHaveTextContent('OpenMousBot list requires auth.')
      const fix = screen.getByTestId('routing-model-warning-action')
      fireEvent.click(fix)
      await waitFor(() => expect(listener).toHaveBeenCalledTimes(1))
      const detail = listener.mock.calls[0][0].detail
      expect(detail).toMatchObject({ section: 'remotes', remoteId: 'omb' })
    } finally {
      window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
    }
  })
})
