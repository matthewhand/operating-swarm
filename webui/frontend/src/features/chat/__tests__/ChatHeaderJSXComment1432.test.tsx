/**
 * #1432 — the chat header must never render source comments as visible text.
 *
 * A `//` block sat between the identity card's opening `>` and its child
 * `<button>` — inside JSX children `//` is text, not a comment, so React
 * printed it into the header on every chat page. The comment explained the
 * team-seat face (the #528/#1362 path), so the regression renders a team seat
 * and asserts the header text carries no `//`.
 *
 * The eslint guard is `react/jsx-no-comment-textnodes` raised to `error` in
 * `webui/frontend/package.json` (`eslintConfig.rules`).
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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
    Folder: () => <span data-testid="folder-glyph" />,
    GroupAvatar: ({ label }: { label?: string }) => (
      <span data-testid="os-group-avatar" aria-label={label} />
    ),
    OPEN_SETTINGS_EVENT: 'swarm:open-settings',
    PanelLeft: () => <span data-testid="panel-left-glyph" />,
    Pencil: () => <span data-testid="pencil-glyph" />,
    RemoteSessionSwitcher: () => null,
    Settings: () => <span data-testid="settings-glyph" />,
    ThemeToggle: () => <span data-testid="theme-toggle" />,
    activeChatAgentId: 'a1',
    auxTasks: [],
    cliQuery: { data: undefined },
    configuredRemoteRows: [],
    generationsOpen: false,
    isRemoteCapableCli: () => false,
    openAgentEditor: vi.fn(),
    openRail: vi.fn(),
    openSettingsSheet: vi.fn(),
    openTeamEditor: vi.fn(),
    railOpen: false,
    requestAuxCancel: vi.fn(),
    roleCssClass: (role: string) => `os-agent-role-${role}`,
    selectedAgent: { id: 'a1', name: 'Charles' },
    selectedAgentName: 'Charles',
    selectedRemote: null,
    setGenerationsOpen: vi.fn(),
    setSearchParams: vi.fn(),
    showEmptyRemoteChrome: false,
    showRemotesControl: false,
    wsRef: { current: null },
    ...overrides,
  }
}

function renderTeamHeader() {
  return render(
    <ChatHeader
      {...(baseProps({
        teamFromUrl: 'demo-team',
        teamChatMemberId: 'codey',
        selectedTeam: { id: 'demo-team', name: 'Demo Team' },
        selectedAgentName: 'Demo Team',
        headerFaceAgentId: 'codey',
        headerGroupMembers: [
          { id: 'codey', name: 'Codey' },
          { id: 'stewie', name: 'Stewie' },
        ],
      }) as React.ComponentProps<typeof ChatHeader>)}
    />,
  )
}

describe('#1432 — no source comment text in the chat header', () => {
  it('renders a team seat header without any `//` text node', () => {
    renderTeamHeader()

    // The team seat is the path that carried the offending comment block.
    expect(screen.getByTestId('selected-agent-header')).toBeTruthy()
    expect(screen.getByTestId('header-team-avatar')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Demo Team' })).toBeTruthy()

    const header = screen.getByRole('banner')
    expect(header).toBeTruthy()
    expect(header.textContent).not.toContain('//')
  })

  it('keeps the team name — the comment hid nothing the operator should see', () => {
    renderTeamHeader()
    const identity = screen.getByTestId('selected-agent-header')
    expect(identity.textContent).toContain('Demo Team')
    expect(identity.textContent).not.toContain('#528')
  })
})
