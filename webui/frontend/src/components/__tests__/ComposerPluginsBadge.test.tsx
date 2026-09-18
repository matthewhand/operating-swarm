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
import { publishCurrentChatScope } from '../../lib/chatScope'
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
    publishCurrentChatScope('chat-badge-0')
    setSeat({ id: 'api_agent', kind: 'api' })
    render(<ComposerPluginsBadge />)
    expect(screen.queryByTestId('composer-plugins-badge')).toBeNull()
  })

  it('names a single enabled plugin', () => {
    publishCurrentChatScope('chat-badge-1')
    saveEnabledPluginToolIds('chat-badge-1', ['web_search'])
    setSeat({ id: 'api_agent', kind: 'api' })
    render(<ComposerPluginsBadge />)
    const badge = screen.getByTestId('composer-plugins-badge')
    expect(badge).toHaveTextContent('Enabled')
    expect(badge.getAttribute('data-enabled-count')).toBe('1')
  })

  it('counts multiple enabled plugins', () => {
    publishCurrentChatScope('chat-badge-2')
    saveEnabledPluginToolIds('chat-badge-2', ['web_search', 'web_fetch'])
    setSeat({ id: 'api_agent', kind: 'api' })
    render(<ComposerPluginsBadge />)
    const badge = screen.getByTestId('composer-plugins-badge')
    expect(badge).toHaveTextContent('Plugins Enabled 2')
    expect(badge.getAttribute('data-enabled-count')).toBe('2')
  })

  it('does not render on a seat that cannot use plugins (#511)', () => {
    publishCurrentChatScope('chat-badge-cli')
    saveEnabledPluginToolIds('chat-badge-cli', ['web_search'])
    setSeat({ id: 'cli_agent', kind: 'cli' })
    render(<ComposerPluginsBadge />)
    expect(screen.queryByTestId('composer-plugins-badge')).toBeNull()
  })

  it('updates when the chat scope changes underneath it', () => {
    publishCurrentChatScope('chat-badge-live-a')
    saveEnabledPluginToolIds('chat-badge-live-a', ['web_search'])
    setSeat({ id: 'api_agent', kind: 'api' })
    render(<ComposerPluginsBadge />)
    expect(screen.getByTestId('composer-plugins-badge')).toBeInTheDocument()

    act(() => {
      publishCurrentChatScope('chat-badge-live-b')
    })
    // The other chat has nothing enabled — the badge disappears rather than
    // asserting a stale state.
    expect(screen.queryByTestId('composer-plugins-badge')).toBeNull()
  })

  it('opens the plugin toggles on click', () => {
    publishCurrentChatScope('chat-badge-click')
    saveEnabledPluginToolIds('chat-badge-click', ['web_search'])
    setSeat({ id: 'api_agent', kind: 'api' })
    const onOpen = vi.fn()
    window.addEventListener(OPEN_PLUGINS_EVENT, onOpen)
    render(<ComposerPluginsBadge />)
    fireEvent.click(screen.getByTestId('composer-plugins-badge'))
    expect(onOpen).toHaveBeenCalledTimes(1)
    window.removeEventListener(OPEN_PLUGINS_EVENT, onOpen)
  })
})
