/**
 * #1202 — ChatHeader mounts the capability-aware navbar Agent / Session
 * pickers:
 *
 *   1. a provider-incapable control stays visible but greyed with a
 *      capability-aware tooltip;
 *   2. the operator hide-toggle unmounts the unsupported control;
 *   3. a supported control (and its reused switcher) stays mounted;
 *   4. the top navbar still mounts NO provider / routing selector (#679).
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatHeader } from '../ChatHeader'
import { resetTurnRegistry } from '../../../lib/agentTurns'

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: () => null,
    ApiSessionSwitcher: () => <span data-testid="api-session-switcher" />,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => <span data-testid="cli-session-switcher" />,
    ComputerControlStub: () => null,
    RemoteSessionSwitcher: () => <span data-testid="remote-session-switcher" />,
    Settings: () => null,
    Pencil: () => null,
    ThemeToggle: () => null,
    activeChatAgentId: 'a1',
    selectedAgentName: 'Charles',
    selectedAgent: { id: 'a1', name: 'Charles' },
    selectedBlueprint: 'a1',
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
    cliQuery: { data: undefined },
    isRemoteCapableCli: () => false,
    ...overrides,
  }
}

function renderHeader(overrides: Record<string, unknown> = {}) {
  return render(<ChatHeader {...baseProps(overrides)} />)
}

afterEach(() => resetTurnRegistry())

describe('#1202 ChatHeader navbar pickers', () => {
  it('CLI seat greys the Agent picker with a capability-aware tooltip and keeps Sessions active', () => {
    renderHeader({
      isCliAgent: true,
      currentCli: 'grok',
      navbarCapabilities: {
        agents: { enabled: false, reason: 'Agent selection is not supported by grok' },
        sessions: { enabled: true, reason: '' },
      },
    })
    const agent = screen.getByTestId('os-navbar-agent-picker')
    expect(agent).toBeDisabled()
    expect(agent).toHaveAttribute('data-disabled', 'true')
    expect(agent).toHaveAttribute('data-tip', 'Agent selection is not supported by grok')
    expect(screen.queryByTestId('os-navbar-session-picker')).toBeNull()
    expect(screen.getByTestId('cli-session-switcher')).toBeInTheDocument()
  })

  it('unmounts the unsupported Agent picker when hide_unsupported_agent_picker is on', () => {
    renderHeader({
      isCliAgent: true,
      currentCli: 'grok',
      hideUnsupportedAgentPicker: true,
      navbarCapabilities: {
        agents: { enabled: false, reason: 'Agent selection is not supported by grok' },
        sessions: { enabled: true, reason: '' },
      },
    })
    expect(screen.queryByTestId('os-navbar-agent-picker')).toBeNull()
    expect(screen.getByTestId('cli-session-switcher')).toBeInTheDocument()
  })

  it('does not unmount a supported control even with the hide-toggle on', () => {
    renderHeader({
      isApiAgent: true,
      hideUnsupportedAgentPicker: true,
      hideUnsupportedSessionPicker: true,
      navbarCapabilities: {
        agents: { enabled: true, reason: '' },
        sessions: { enabled: true, reason: '' },
      },
    })
    expect(screen.getByTestId('os-navbar-agent-picker')).not.toBeDisabled()
    expect(screen.getByTestId('api-session-switcher')).toBeInTheDocument()
  })

  it('stateless remote greys the Session picker and greys the Agent picker when it lists none', () => {
    renderHeader({
      showRemotesControl: true,
      remoteFromUrl: 'rakazo',
      activeRemoteId: 'rakazo',
      isCliAgent: false,
      isApiAgent: false,
      selectedRemote: { id: 'rakazo', title: 'Rakazo' },
      navbarCapabilities: {
        agents: { enabled: true, reason: '' },
        sessions: {
          enabled: false,
          reason: 'Rakazo is stateless and does not support persistent sessions',
        },
      },
    })
    // A remote seat lists the remote's own agents; Rakazo exposes none, so the
    // control stays mounted but greyed with an honest reason.
    const agent = screen.getByTestId('os-navbar-agent-picker')
    expect(agent).toBeInTheDocument()
    expect(agent).toBeDisabled()
    expect(agent).toHaveAttribute('data-tip', 'Rakazo lists no selectable agents')
    const session = screen.getByTestId('os-navbar-session-picker')
    expect(session).toBeDisabled()
    expect(session).toHaveAttribute(
      'data-tip',
      'Rakazo is stateless and does not support persistent sessions',
    )
    // The disabled shell never mounts the reused remote switcher.
    expect(screen.queryByTestId('remote-session-switcher')).toBeNull()
  })

  it('unmounts the unsupported Session picker when hide_unsupported_session_picker is on', () => {
    renderHeader({
      showRemotesControl: true,
      activeRemoteId: 'rakazo',
      hideUnsupportedSessionPicker: true,
      navbarCapabilities: {
        agents: { enabled: true, reason: '' },
        sessions: {
          enabled: false,
          reason: 'Rakazo is stateless and does not support persistent sessions',
        },
      },
    })
    expect(screen.queryByTestId('os-navbar-session-picker')).toBeNull()
  })

  // #hermes: the navbar reads the ACTIVE remote row's declared capability, so
  // a session-capable remote mounts the reused switcher even when the parent
  // could not resolve `selectedRemote`.
  it('enables the Session picker when the active remote row declares sessions', () => {
    renderHeader({
      showRemotesControl: true,
      remoteFromUrl: 'hermes',
      activeRemoteId: 'hermes',
      selectedRemote: { id: 'hermes', kind: 'hermes', title: 'Hermes Agent (dev-worker-gpu)' },
      configuredRemoteRows: [
        { id: 'hermes', title: 'Hermes Agent (dev-worker-gpu)', capabilities: { sessions: true } },
      ],
    })
    expect(screen.queryByTestId('os-navbar-session-picker')).toBeNull()
    expect(screen.getByTestId('remote-session-switcher')).toBeInTheDocument()
  })

  it('greys a stateless remote even when the parent enabled the Session picker', () => {
    renderHeader({
      showRemotesControl: true,
      remoteFromUrl: 'rakazo',
      activeRemoteId: 'rakazo',
      selectedRemote: { id: 'rakazo', kind: 'rakazo', title: 'Rakazo' },
      configuredRemoteRows: [
        { id: 'rakazo', title: 'Rakazo', capabilities: { sessions: false } },
      ],
      navbarCapabilities: {
        agents: { enabled: true, reason: '' },
        sessions: { enabled: true, reason: '' },
      },
    })
    const session = screen.getByTestId('os-navbar-session-picker')
    expect(session).toBeDisabled()
    expect(session).toHaveAttribute(
      'data-tip',
      'Rakazo is stateless and does not support persistent sessions',
    )
  })

  it('lists the remote seat’s own agents (never the palette) and targets the pick', () => {
    const setSearchParams = vi.fn()
    renderHeader({
      showRemotesControl: true,
      remoteFromUrl: 'hermes',
      activeRemoteId: 'hermes',
      selectedRemote: { id: 'hermes', kind: 'hermes', title: 'Hermes Agent (dev-worker-gpu)' },
      configuredRemoteRows: [
        { id: 'hermes', title: 'Hermes Agent (dev-worker-gpu)', capabilities: { sessions: true } },
      ],
      remoteNavbarAgents: [{ id: 'hermes-agent', label: 'hermes-agent' }],
      allPaletteAgents: [{ id: 'codey', label: 'Codey', kind: 'api' }],
      setSearchParams,
    })
    fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
    expect(screen.getByTestId('os-navbar-agent-option-hermes-agent')).toBeInTheDocument()
    expect(screen.queryByTestId('os-navbar-agent-option-codey')).toBeNull()

    fireEvent.click(screen.getByTestId('os-navbar-agent-option-hermes-agent'))
    expect(setSearchParams).toHaveBeenCalled()
    const updater = setSearchParams.mock.calls[0][0] as (p: URLSearchParams) => URLSearchParams
    const next = updater(new URLSearchParams('remote=hermes'))
    expect(next.get('remote')).toBe('hermes')
    expect(next.get('session')).toBe('hermes-agent')
  })

  it('greys the Agent picker with an honest reason when a remote lists no agents', () => {
    renderHeader({
      showRemotesControl: true,
      remoteFromUrl: 'emptybox',
      activeRemoteId: 'emptybox',
      selectedRemote: { id: 'emptybox', kind: 'hermes', title: 'Empty Box' },
      configuredRemoteRows: [
        { id: 'emptybox', title: 'Empty Box', capabilities: { sessions: true } },
      ],
      remoteNavbarAgents: [],
    })
    const agent = screen.getByTestId('os-navbar-agent-picker')
    expect(agent).toBeDisabled()
    expect(agent).toHaveAttribute('data-tip', 'Empty Box lists no selectable agents')
  })
})

describe('#1202 top navbar mounts no provider/routing selector', () => {
  it('ChatHeader source mounts no NavbarRoutingPicker / routing pill', () => {
    const src = readFileSync(join(__dirname, '..', 'ChatHeader.tsx'), 'utf8')
    expect(src).not.toMatch(/NavbarRoutingPicker/)
    expect(src).not.toMatch(/renderRoutingPicker\(\)/)
    expect(src).not.toMatch(/routing-pill/)
  })

  it('the rendered header exposes no routing-pill testid', () => {
    renderHeader({
      isApiAgent: true,
      navbarCapabilities: {
        agents: { enabled: true, reason: '' },
        sessions: { enabled: true, reason: '' },
      },
    })
    const header = document.querySelector('.os-chat-header')
    expect(header).toBeTruthy()
    expect(header!.querySelector('[data-testid="routing-pill-agent"]')).toBeNull()
  })
})
