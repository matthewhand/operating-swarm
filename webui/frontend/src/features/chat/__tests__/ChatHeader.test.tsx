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
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, act, waitFor, within } from '@testing-library/react'
import type React from 'react'
import { ChatHeader } from '../ChatHeader'
import AgentAvatar from '../../../components/AgentAvatar'
import { OPEN_GENERATIONS_EVENT } from '../../../components/settings/generationsEntry'
import { recordTurnFrame, resetTurnRegistry } from '../../../lib/agentTurns'

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
    Pencil: () => <span data-testid="pencil-glyph" />,
    Folder: () => <span data-testid="folder-glyph" />,
    PanelLeft: () => <span data-testid="panel-left-glyph" />,
    roleCssClass: (role: string) => `os-agent-role-${role}`,
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

describe('#1244 — header avatar animates from the shared turn registry', () => {
  beforeEach(() => resetTurnRegistry())
  afterEach(() => resetTurnRegistry())

  function renderWithRealAvatar(agentId: string) {
    return render(
      <ChatHeader
        {...(baseProps({
          AgentAvatar,
          headerFaceAgentId: agentId,
          activeChatAgentId: agentId,
          selectedAgent: { id: agentId, name: agentId },
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
  }

  it('marks the header face active while its agent owns a live turn', () => {
    renderWithRealAvatar('codey')
    const avatar = screen.getByTestId('header-avatar-generations')
    expect(avatar.querySelector('[data-avatar-active="true"]')).toBeNull()

    act(() => {
      recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    })
    expect(avatar.querySelector('[data-avatar-active="true"]')).not.toBeNull()

    act(() => {
      recordTurnFrame({ kind: 'turn_finished', turnId: 't1', agentId: 'codey' })
    })
    expect(avatar.querySelector('[data-avatar-active="true"]')).toBeNull()
  })

  it('keeps animating after switching away and back (remount)', () => {
    const first = renderWithRealAvatar('codey')
    act(() => {
      recordTurnFrame({ kind: 'turn_started', turnId: 't2', agentId: 'codey' })
    })
    expect(
      first.getByTestId('header-avatar-generations').querySelector('[data-avatar-active="true"]'),
    ).not.toBeNull()
    first.unmount()

    const back = renderWithRealAvatar('codey')
    expect(
      back.getByTestId('header-avatar-generations').querySelector('[data-avatar-active="true"]'),
    ).not.toBeNull()
    back.unmount()
  })
})

describe('#1236 — avatar right-click opens agent config', () => {
  function renderHeader(overrides: Record<string, unknown> = {}) {
    const openAgentEditor = vi.fn()
    render(<ChatHeader {...baseProps({ openAgentEditor, ...overrides }) as React.ComponentProps<typeof ChatHeader>} />)
    return { openAgentEditor }
  }

  it('right-click on the header avatar opens the agent editor', () => {
    const { openAgentEditor } = renderHeader({ selectedBlueprint: 'general-assistant' })
    const avatar = screen.getByTestId('header-avatar-generations')
    fireEvent.contextMenu(avatar)
    expect(openAgentEditor).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: 'general-assistant' }),
    )
  })

  it('right-click prevents the native menu and does not open the config sidepane', () => {
    const setGenerationsOpen = vi.fn()
    const { openAgentEditor } = renderHeader({ selectedBlueprint: 'a1', setGenerationsOpen })
    const avatar = screen.getByTestId('header-avatar-generations')
    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    avatar.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(setGenerationsOpen).not.toHaveBeenCalled()
    expect(openAgentEditor).toHaveBeenCalledTimes(1)
  })

  it('left-click opens the agent config sidepane, not generations', () => {
    const setGenerationsOpen = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ profiles: [], data: [] }),
      }),
    )
    renderHeader({ selectedBlueprint: 'a1', setGenerationsOpen })
    fireEvent.click(screen.getByTestId('header-avatar-generations'))
    expect(screen.getByTestId('agent-config-sidepane')).toBeInTheDocument()
    expect(setGenerationsOpen).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('#1354: the generations affordance left the navbar for Settings', () => {
    const setGenerationsOpen = vi.fn()
    renderHeader({ setGenerationsOpen })
    // The prime navbar no longer hosts the diagnostics button.
    expect(screen.queryByTestId('header-generations-debug')).toBeNull()
    // The Settings entry dispatches this event; the mounted header opens it.
    window.dispatchEvent(new CustomEvent(OPEN_GENERATIONS_EVENT))
    expect(setGenerationsOpen).toHaveBeenCalledWith(true)
  })
})

describe('#1233 — inline agent name edit in the navbar', () => {
  function renderName(overrides: Record<string, unknown> = {}) {
    render(
      <ChatHeader
        {...(baseProps({
          selectedBlueprint: 'a1',
          selectedAgentName: 'Charles',
          ...overrides,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
  }

  it('saves on Enter through the agent edit path', async () => {
    const saveAgentEdit = vi.fn().mockResolvedValue(undefined)
    renderName({ saveAgentEdit })
    fireEvent.click(screen.getByTestId('os-identity-name'))
    const input = screen.getByTestId('os-identity-name-input')
    fireEvent.change(input, { target: { value: 'Charlie' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(saveAgentEdit).toHaveBeenCalledWith('a1', { name: 'Charlie' })
    await waitFor(() => {
      expect(screen.getByTestId('os-identity-name')).toHaveTextContent('Charlie')
    })
  })

  it('cancels on Escape without saving', () => {
    const saveAgentEdit = vi.fn()
    renderName({ saveAgentEdit })
    fireEvent.click(screen.getByTestId('os-identity-name'))
    fireEvent.change(screen.getByTestId('os-identity-name-input'), {
      target: { value: 'Charlie' },
    })
    fireEvent.keyDown(screen.getByTestId('os-identity-name-input'), { key: 'Escape' })
    expect(saveAgentEdit).not.toHaveBeenCalled()
    expect(screen.getByTestId('os-identity-name')).toHaveTextContent('Charles')
  })

  it('reverts the optimistic rename when the save fails', async () => {
    const saveAgentEdit = vi.fn().mockRejectedValue(new Error('offline'))
    renderName({ saveAgentEdit })
    fireEvent.click(screen.getByTestId('os-identity-name'))
    fireEvent.change(screen.getByTestId('os-identity-name-input'), {
      target: { value: 'Charlie' },
    })
    fireEvent.keyDown(screen.getByTestId('os-identity-name-input'), { key: 'Enter' })
    expect(saveAgentEdit).toHaveBeenCalledWith('a1', { name: 'Charlie' })
    await waitFor(() => {
      expect(screen.getByTestId('os-identity-name')).toHaveTextContent('Charles')
    })
  })
})

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
    expect(src).toContain('<ChatHeader {...allChatScope} />')
    expect(src).not.toContain('os-chat-header')
  })

  it('renders with os-chat-header--hidden when mobileHeaderHidden is true', () => {
    const { unmount } = render(
      <ChatHeader {...(baseProps({ mobileHeaderHidden: true }) as React.ComponentProps<typeof ChatHeader>)} />,
    )
    const header = document.querySelector('header.os-chat-header')
    expect(header).toHaveClass('os-chat-header--hidden')
    expect(header).toHaveAttribute('data-mobile-hidden', 'true')
    unmount()

    render(
      <ChatHeader {...(baseProps({ mobileHeaderHidden: false }) as React.ComponentProps<typeof ChatHeader>)} />,
    )
    const visibleHeader = document.querySelector('header.os-chat-header')
    expect(visibleHeader).not.toHaveClass('os-chat-header--hidden')
    expect(visibleHeader).toHaveAttribute('data-mobile-hidden', 'false')
  })

  it('passes headerFaceAgentId and headerFaceAvatarSrc to AgentAvatar', () => {
    render(
      <ChatHeader
        {...(baseProps({
          headerFaceAgentId: 'trueforge',
          headerFaceAvatarSrc: '/custom/avatar.png',
          AgentAvatar: ({ agentId, src }: { agentId: string; src?: string }) => (
            <span data-testid="avatar" data-src={src}>
              {agentId}
            </span>
          ),
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    // #1676 added a second face: the centered pill renders the same seat's
    // avatar from the same props. Scope to the left identity card, which is
    // the surface this assertion is about.
    const identity = within(screen.getByTestId('selected-agent-header'))
    const avatar = identity.getByTestId('avatar')
    expect(avatar).toHaveTextContent('trueforge')
    expect(avatar).toHaveAttribute('data-src', '/custom/avatar.png')
  })
})

describe('#1257 — folder subtitle leading-ellipsis + click-to-change', () => {
  const full = '/home/dev/very/long/path/to/open-swarm-private — branch: main'
  const display = '.../long/path/to/open-swarm-private — branch: main'

  it('renders the truncated display while the title keeps the full path', () => {
    render(
      <ChatHeader
        {...(baseProps({
          workspaceSubtitle: full,
          workspaceSubtitleDisplay: display,
          workspaceFolderEditable: true,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    const subtitle = screen.getByTestId('os-navbar-workspace-subtitle')
    expect(subtitle.tagName).toBe('BUTTON')
    expect(subtitle).toHaveTextContent(display)
    expect(subtitle).not.toHaveTextContent(full)
    expect(subtitle).toHaveAttribute('title', full)
  })

  it('clicking the subtitle opens the agent/folder settings flow', () => {
    const openAgentEditor = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({
          openAgentEditor,
          selectedBlueprint: 'general-assistant',
          workspaceSubtitle: full,
          workspaceSubtitleDisplay: display,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    fireEvent.click(screen.getByTestId('os-navbar-workspace-subtitle'))
    expect(openAgentEditor).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: 'general-assistant' }),
    )
  })

  it('reveals a Select folder affordance when nothing is bound and opens the flow', () => {
    const openAgentEditor = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({
          openAgentEditor,
          selectedBlueprint: 'general-assistant',
          workspaceSubtitle: '',
          workspaceFolderEditable: true,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    const unset = screen.getByTestId('os-navbar-workspace-subtitle-unset')
    expect(unset).toHaveClass('os-navbar-identity-subtitle--unset')
    expect(unset).toHaveTextContent('Select folder')
    fireEvent.click(unset)
    expect(openAgentEditor).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: 'general-assistant' }),
    )
  })

  it('never offers the folder affordance when the seat cannot bind a folder', () => {
    render(
      <ChatHeader
        {...(baseProps({
          workspaceSubtitle: '',
          workspaceFolderEditable: false,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).toBeNull()
    expect(screen.queryByTestId('os-navbar-workspace-subtitle-unset')).toBeNull()
  })
})

describe('#1202 follow-up — mobile navbar fits, role badge under the name, agent picker', () => {
  function setViewportWidth(width: number) {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  }

  afterEach(() => {
    setViewportWidth(1024)
  })

  it('drops the rail toggle when the window is on the mobile tier', () => {
    setViewportWidth(390)
    render(<ChatHeader {...(baseProps({ narrow: true, openRail: vi.fn() }) as React.ComponentProps<typeof ChatHeader>)} />)
    expect(screen.queryByRole('button', { name: 'Open agent list' })).not.toBeInTheDocument()
  })

  it('keeps the rail toggle on the tablet tier', () => {
    setViewportWidth(768)
    render(<ChatHeader {...(baseProps({ narrow: true, openRail: vi.fn() }) as React.ComponentProps<typeof ChatHeader>)} />)
    expect(screen.getByRole('button', { name: 'Open agent list' })).toBeInTheDocument()
  })

  it('renders the role badge under the name as a slim pill', () => {
    render(
      <ChatHeader
        {...(baseProps({
          narrow: false,
          showHeaderRole: true,
          headerRole: 'support',
          headerRoleLabel: 'Support',
          selectedAgentName: 'Support',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    const textColumn = document.querySelector('.os-navbar-identity-text')
    const badge = screen.getByTestId('os-header-role-badge')
    expect(textColumn).toContainElement(badge)
    expect(badge).toHaveClass('os-agent-role-badge')
    expect(badge).toHaveClass('os-agent-role-badge--slim')
    // The badge follows the name in the stacked identity column.
    const name = document.querySelector('.os-navbar-identity-label') as HTMLElement
    expect(name).toBeTruthy()
    expect(name.compareDocumentPosition(badge) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('lists available agents instead of opening the current agent config', () => {
    const onNavigate = vi.fn()
    const openAgentEditor = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({
          allPaletteAgents: [
            { id: 'codey', label: 'Codey', kind: 'api' },
            { id: 'agy', label: 'Agy', kind: 'cli' },
          ],
          selectedBlueprint: 'codey',
          navigateToPaletteAgent: onNavigate,
          openAgentEditor,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )

    fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
    expect(screen.getByTestId('os-navbar-agent-picker-menu')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('os-navbar-agent-option-agy'))
    expect(onNavigate).toHaveBeenCalledWith('agy', 'cli')
    expect(openAgentEditor).not.toHaveBeenCalled()
  })
})

describe('#1445 header seat identity', () => {
  it('stamps data-seat from the URL and hides the AnythingLLM switcher on a team', () => {
    render(
      <ChatHeader
        {...(baseProps({
          teamFromUrl: 'demo-team',
          selectedTeam: { id: 'demo-team', name: 'Demo Team', members: [] },
          selectedAgentName: 'Demo Team',
          showRemotesControl: true,
          activeRemoteId: 'anythingllm',
          RemoteSessionSwitcher: () => (
            <button type="button" data-testid="os-remote-session-switcher">
              Select AnythingLLM session
            </button>
          ),
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
      'data-seat',
      'team:demo-team',
    )
    expect(screen.queryByTestId('os-remote-session-switcher')).not.toBeInTheDocument()
  })

  it('keeps the AnythingLLM switcher on a remote seat', () => {
    render(
      <ChatHeader
        {...(baseProps({
          remoteFromUrl: 'anythingllm',
          selectedRemote: {
            id: 'anythingllm',
            kind: 'anythingllm',
            title: 'AnythingLLM',
            capabilities: { sessions: true },
          },
          configuredRemoteRows: [
            {
              id: 'anythingllm',
              title: 'AnythingLLM',
              capabilities: { sessions: true },
            },
          ],
          selectedAgentName: 'AnythingLLM',
          showRemotesControl: true,
          activeRemoteId: 'anythingllm',
          RemoteSessionSwitcher: () => (
            <button type="button" data-testid="os-remote-session-switcher">
              Select AnythingLLM session
            </button>
          ),
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
      'data-seat',
      'remote:anythingllm',
    )
    expect(screen.getByTestId('os-remote-session-switcher')).toBeInTheDocument()
  })
})
