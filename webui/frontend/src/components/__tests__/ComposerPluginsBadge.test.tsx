/**
 * #577 — render-level tests for the composer's Plugins-Enabled badge.
 *
 * The badge is a shortcut, not a dead label: clicking it must dispatch the
 * same OPEN_PLUGINS_EVENT the rail footer's Plugins entry handles.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import ComposerPluginsBadge from '../ComposerPluginsBadge'
import { saveEnabledPluginToolIds } from '../../lib/chatPluginTools'
import { CURRENT_AGENT_STORAGE_KEY, publishCurrentAgent } from '../../lib/currentAgent'
import { OPEN_PLUGINS_EVENT } from '../../lib/chromeOverlay'

function setSeat(agent: unknown) {
  localStorage.setItem(CURRENT_AGENT_STORAGE_KEY, JSON.stringify(agent))
  act(() => {
    publishCurrentAgent(agent as never)
  })
}

describe('ComposerPluginsBadge (#577)', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('renders nothing when no plugins are enabled', () => {
    setSeat({ id: 'api_agent', kind: 'api' })
    render(<ComposerPluginsBadge />)
    expect(screen.queryByTestId('composer-plugins-badge')).toBeNull()
  })

  it('names a single enabled plugin', () => {
    setSeat({ id: 'api_agent', kind: 'api' })
    saveEnabledPluginToolIds('api_agent', ['web_search'])
    render(<ComposerPluginsBadge />)
    const badge = screen.getByTestId('composer-plugins-badge')
    expect(badge).toHaveTextContent('Enabled')
    expect(badge.getAttribute('data-enabled-count')).toBe('1')
  })

  it('counts multiple enabled plugins', () => {
    setSeat({ id: 'api_agent', kind: 'api' })
    saveEnabledPluginToolIds('api_agent', ['web_search', 'web_fetch'])
    render(<ComposerPluginsBadge />)
    const badge = screen.getByTestId('composer-plugins-badge')
    expect(badge).toHaveTextContent('Plugins Enabled 2')
    expect(badge.getAttribute('data-enabled-count')).toBe('2')
  })

  it('does not render on a seat that cannot use plugins (#511)', () => {
    setSeat({ id: 'cli_agent', kind: 'cli' })
    saveEnabledPluginToolIds('cli_agent', ['web_search'])
    render(<ComposerPluginsBadge />)
    expect(screen.queryByTestId('composer-plugins-badge')).toBeNull()
  })

  it('updates when the agent seat changes underneath it (#516 scope)', () => {
    setSeat({ id: 'api_agent', kind: 'api' })
    saveEnabledPluginToolIds('api_agent', ['web_search'])
    render(<ComposerPluginsBadge />)
    expect(screen.getByTestId('composer-plugins-badge')).toBeInTheDocument()

    act(() => {
      setSeat({ id: 'codey', kind: 'blueprint' })
    })
    // The other agent has nothing enabled — the badge disappears rather than
    // asserting a stale state.
    expect(screen.queryByTestId('composer-plugins-badge')).toBeNull()
  })

  it('opens the plugin toggles on click', () => {
    setSeat({ id: 'api_agent', kind: 'api' })
    saveEnabledPluginToolIds('api_agent', ['web_search'])
    const onOpen = vi.fn()
    window.addEventListener(OPEN_PLUGINS_EVENT, onOpen)
    render(<ComposerPluginsBadge />)
    fireEvent.click(screen.getByTestId('composer-plugins-badge'))
    expect(onOpen).toHaveBeenCalledTimes(1)
    window.removeEventListener(OPEN_PLUGINS_EVENT, onOpen)
  })
})
