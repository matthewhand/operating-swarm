/**
 * #1354 — the generations diagnostics entry moved out of the prime navbar
 * into Settings → System, and error states surface the panel automatically.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatHeader } from '../ChatHeader'
import { OPEN_GENERATIONS_EVENT } from '../../../components/settings/generationsEntry'

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: () => <span data-testid="avatar" />,
    ApiSessionSwitcher: () => null,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => null,
    ComputerControlStub: () => null,
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

describe('#1354 — generations entry + error surface', () => {
  it('no longer hosts the generations diagnostics affordance in the navbar', () => {
    render(<ChatHeader {...(baseProps() as React.ComponentProps<typeof ChatHeader>)} />)
    expect(screen.queryByTestId('header-generations-debug')).toBeNull()
  })

  it('opens the panel when Settings dispatches the generations event', () => {
    const setGenerationsOpen = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({ setGenerationsOpen }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    window.dispatchEvent(new CustomEvent(OPEN_GENERATIONS_EVENT))
    expect(setGenerationsOpen).toHaveBeenCalledWith(true)
  })

  it('surfaces the panel when the thread fails to hydrate', () => {
    const setGenerationsOpen = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({
          setGenerationsOpen,
          hydrateError: 'thread store unavailable',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(setGenerationsOpen).toHaveBeenCalledWith(true)
  })

  it('surfaces the panel on a flagrant runtime error row', () => {
    const setGenerationsOpen = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({
          setGenerationsOpen,
          messages: [
            {
              key: 'err-1',
              role: 'status',
              text: 'send: FAIL — connection refused',
            },
          ],
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(setGenerationsOpen).toHaveBeenCalledWith(true)
  })

  it('does not surface the panel when there is no error', () => {
    const setGenerationsOpen = vi.fn()
    render(
      <ChatHeader
        {...(baseProps({
          setGenerationsOpen,
          messages: [{ key: 'm1', role: 'assistant', text: 'all good' }],
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(setGenerationsOpen).not.toHaveBeenCalled()
  })
})
