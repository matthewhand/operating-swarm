/**
 * #1202 — Settings → Aesthetics exposes the two navbar-picker hide toggles and
 * writes them through the server-backed preference helpers (localStorage is
 * the immediate cache).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import {
  HIDE_UNSUPPORTED_AGENT_PICKER_KEY,
  HIDE_UNSUPPORTED_SESSION_PICKER_KEY,
  loadNavbarPickerPrefs,
} from '../../lib/navbarPickerPrefs'

function renderSheet() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet isOpen onClose={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1202 navbar picker hide toggles', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('defaults both toggles OFF and persists each independently', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: [] }) } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Aesthetics' }))

    const agentToggle = screen.getByTestId('hide-unsupported-agent-picker-toggle')
    const sessionToggle = screen.getByTestId('hide-unsupported-session-picker-toggle')
    expect(agentToggle).not.toBeChecked()
    expect(sessionToggle).not.toBeChecked()

    fireEvent.click(agentToggle)
    expect(loadNavbarPickerPrefs().hideUnsupportedAgentPicker).toBe(true)
    expect(loadNavbarPickerPrefs().hideUnsupportedSessionPicker).toBe(false)

    fireEvent.click(sessionToggle)
    expect(loadNavbarPickerPrefs().hideUnsupportedSessionPicker).toBe(true)

    // The server-backed keys are the declared registry names.
    expect(HIDE_UNSUPPORTED_AGENT_PICKER_KEY).toBe('hide_unsupported_agent_picker')
    expect(HIDE_UNSUPPORTED_SESSION_PICKER_KEY).toBe('hide_unsupported_session_picker')
  })
})
