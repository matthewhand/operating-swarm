/**
 * #856 slice J — the chat header is an independently testable module
 * (`features/chat/ChatHeader.tsx`), moved verbatim out of ChatPage.tsx.
 *
 * Pinned contract (pure move — behavior unchanged):
 *
 * 1. ChatHeader renders the `os-chat-header` bar: agent identity, session
 *    switchers (API/CLI/remote), aux-task indicator, and the tools toolbar
 *    (computer-control stub, theme toggle, settings).
 * 2. ChatPage consumes the module and no longer declares the header JSX
 *    inline.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type React from 'react'
import { ChatHeader } from '../ChatHeader'

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: ({ agentId }: { agentId: string }) => <span data-testid="avatar">{agentId}</span>,
    ApiSessionSwitcher: () => null,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => null,
    ComputerControlStub: () => null,
    ConsumerPills: () => null,
    OPEN_SETTINGS_EVENT: 'swarm:open-settings',
    RemoteSessionSwitcher: () => null,
    Settings: () => <span data-testid="settings-glyph" />,
    ThemeToggle: () => <span data-testid="theme-toggle" />,
    activeChatAgentId: 'a1',
    selectedAgentName: 'Charles',
    selectedAgent: { id: 'a1', name: 'Charles' },
    auxTasks: [],
    requestAuxCancel: vi.fn(),
    wsRef: { current: null },
    showEmptyRemoteChrome: false,
    showRemotesControl: false,
    activeRemoteId: null,
    configuredRemoteRows: [],
    selectedRemote: null,
    setSearchParams: vi.fn(),
    setGenerationsOpen: vi.fn(),
    generationsOpen: false,
    cliRemoteSession: null,
    ...overrides,
  }
}

describe('#856 slice J — ChatHeader', () => {
  it('renders the header bar with the tools toolbar', () => {
    render(<ChatHeader {...(baseProps() as React.ComponentProps<typeof ChatHeader>)} />)
    expect(document.querySelector('header.os-chat-header')).toBeTruthy()
    expect(screen.getByRole('toolbar', { name: 'Chat tools' })).toBeTruthy()
    expect(screen.getByTestId('theme-toggle')).toBeTruthy()
  })

  it('the settings button broadcasts OPEN_SETTINGS_EVENT', () => {
    const spy = vi.fn()
    window.addEventListener('swarm:open-settings', spy)
    render(<ChatHeader {...(baseProps() as React.ComponentProps<typeof ChatHeader>)} />)
    screen.getByLabelText('Open settings').click()
    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener('swarm:open-settings', spy)
  })

  it('renders the empty-remote Add remote affordance only when flagged', () => {
    const first = render(
      <ChatHeader {...(baseProps({ showEmptyRemoteChrome: true }) as React.ComponentProps<typeof ChatHeader>)} />,
    )
    expect(screen.getByText('Add remote')).toBeTruthy()
    first.unmount()
    render(<ChatHeader {...(baseProps() as React.ComponentProps<typeof ChatHeader>)} />)
    expect(screen.queryByText('Add remote')).toBeNull()
  })

  it('ChatPage consumes the module (no inline header JSX)', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    // eslint-disable-next-line testing-library/no-node-access -- raw source introspection, not DOM probing
    const src = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'pages', 'ChatPage.tsx'),
      'utf8',
    )
    expect(src).toContain('ChatHeader {...chatHeaderProps}')
    expect(src).not.toContain('os-chat-header')
  })
})
