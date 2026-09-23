/**
 * #516 — the Plugins popup is the same control as the composer panel, scoped
 * to the **agent**: its toggles read/write the agent set, and its copy says
 * so ("Toggles apply to this chat only." / "This chat" were the old model).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PluginsPopup from '../PluginsPopup'
import { publishCurrentAgent } from '../../lib/currentAgent'

function renderPopup() {
  return render(
    <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
      <PluginsPopup open onClose={vi.fn()} />
    </MemoryRouter>,
  )
}

describe('#516 PluginsPopup — agent scope', () => {
  beforeEach(() => {
    localStorage.clear()
    publishCurrentAgent({ id: 'codey', kind: 'api' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('offline catalog — use fixture')),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('pane label and copy name the agent, not the chat', async () => {
    renderPopup()
    await screen.findByRole('switch', { name: /Web Search/i })
    expect(screen.getByText('This agent')).toBeInTheDocument()
    const copy = screen.getByTestId('os-plugins-source')
    expect(copy).toHaveTextContent(/this agent/i)
    expect(copy.textContent).not.toMatch(/this chat/i)
  })

  it('toggle writes under the agent key and reads back per agent', async () => {
    renderPopup()
    const toggle = await screen.findByRole('switch', { name: /Web Search/i })
    fireEvent.click(toggle)

    const raw = localStorage.getItem('swarm_agent_plugin_tools')
    expect(JSON.parse(raw!)).toMatchObject({ codey: ['web_search'] })
  })
})
