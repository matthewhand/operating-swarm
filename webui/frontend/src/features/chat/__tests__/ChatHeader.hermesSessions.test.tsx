/**
 * Hermes remote seat — the top navbar Session control lists the gateway's
 * sessions and selecting one writes ?remote=hermes&session=<id>.
 *
 * Guards the actual control chain (not a stubbed switcher): the real
 * RemoteSessionSwitcher fetches via fetchRemoteThreadSessions and ChatHeader's
 * onSelectSession resolves the URL.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatHeader } from '../ChatHeader'
import { resetTurnRegistry } from '../../../lib/agentTurns'
import RemoteSessionSwitcher from '../../../components/RemoteSessionSwitcher'

vi.mock('../../../lib/remoteSessions', () => ({
  fetchRemoteThreadSessions: vi.fn(async () => [
    {
      id: 'hermes:run_a',
      groupId: 'hermes',
      groupKind: 'remote',
      memberId: 'run_a',
      title: 'Reply with exactly OK #5',
      snippet: 'Reply with exactly: OK',
      status: 'finished',
      startedAt: Date.parse('2026-09-26T22:32:35.230Z'),
      href: '/chat?remote=hermes&session=run_a',
    },
  ]),
}))

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: () => null,
    ApiSessionSwitcher: () => null,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => null,
    ComputerControlStub: () => null,
    RemoteSessionSwitcher,
    Settings: () => null,
    Pencil: () => null,
    ThemeToggle: () => null,
    activeChatAgentId: 'hermes',
    selectedAgentName: 'Hermes',
    selectedAgent: { id: 'hermes', name: 'Hermes' },
    selectedBlueprint: '',
    auxTasks: [],
    requestAuxCancel: vi.fn(),
    wsRef: { current: null },
    showEmptyRemoteChrome: false,
    showRemotesControl: true,
    remoteFromUrl: 'hermes',
    activeRemoteId: 'hermes',
    configuredRemoteRows: [
      { id: 'hermes', title: 'Hermes', capabilities: { sessions: true } },
    ],
    selectedRemote: { id: 'hermes', kind: 'hermes', title: 'Hermes', capabilities: { sessions: true } },
    remoteNavbarAgents: [{ id: 'hermes-agent', label: 'hermes-agent' }],
    setSearchParams: vi.fn(),
    setGenerationsOpen: vi.fn(),
    generationsOpen: false,
    cliRemoteSession: null,
    cliQuery: { data: undefined },
    isRemoteCapableCli: () => false,
    navbarCapabilities: {
      agents: { enabled: true, reason: '' },
      sessions: { enabled: true, reason: '' },
    },
    ...overrides,
  }
}

afterEach(() => resetTurnRegistry())

describe('hermes navbar session picker', () => {
  it('lists Hermes sessions and selecting one writes ?remote=hermes&session=<id>', async () => {
    const setSearchParams = vi.fn()
    render(<ChatHeader {...baseProps({ setSearchParams })} />)

    // The session control is the History button inside the navbar shell. An
    // enabled picker drops the disabled shell, so the switcher mounts directly.
    const switcher = await screen.findByTestId('os-remote-session-switcher')
    switcher.click()

    // The picker lists the gateway session by title.
    const row = await screen.findByText('Reply with exactly OK #5')
    row.closest('[data-session-id]')?.dispatchEvent(
      new MouseEvent('click', { bubbles: true }),
    )

    await waitFor(() => expect(setSearchParams).toHaveBeenCalled())
    const updater = setSearchParams.mock.calls[0][0] as (p: URLSearchParams) => URLSearchParams
    const next = updater(new URLSearchParams('remote=hermes'))
    expect(next.get('remote')).toBe('hermes')
    expect(next.get('session')).toBe('run_a')
  })
})
