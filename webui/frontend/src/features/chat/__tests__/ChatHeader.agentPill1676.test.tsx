/**
 * #1676 — the foreground agent's avatar + name ride a CENTERED floating pill in
 * the chat header, and clicking that pill opens the right-side edit-agent pane.
 *
 * Pinned contract:
 *
 * 1. Geometry. The header stays the #560 flex band; the pill floats under it with
 *    equal `1fr` side tracks, and the pill is a child of the header in the
 *    middle track. That is what makes it centered rather than left-flush, and
 *    it is asserted against `index.css` because jsdom computes no layout.
 * 2. Click to edit. A click on the pill surface opens the ONE existing editor
 *    (`AgentConfigSidepane`, the same pane the avatar has opened since #1258) —
 *    no second editor is introduced.
 * 3. The pill is not a greedy overlay: the rail toggle and the controls cluster
 *    keep their own grid columns, and inner controls (rename, folder, pencil)
 *    still own their clicks instead of leaking to the pill.
 * 4. The pill follows the foreground seat, and degrades to a documented inert
 *    placeholder when no seat resolves.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import fs from 'fs'
import path from 'path'
import type React from 'react'
import { ChatHeader } from '../ChatHeader'

const css = fs.readFileSync(path.resolve(__dirname, '../../../index.css'), 'utf8')

/** Comments carry issue numbers, so the token checks below must not see them. */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '')
}

/**
 * The LAST top-level block for a selector. `index.css` layers history, so
 * `.os-chat-header` is declared by #560 and re-declared by #1676 — the winning
 * declaration is the one the cascade uses, and that is the one under test.
 */
function cssBlock(selector: string): string {
  const index = css.lastIndexOf(`\n${selector} {`)
  expect(index, `index.css declares ${selector}`).toBeGreaterThan(-1)
  return stripComments(css.slice(index, css.indexOf('}', index)))
}

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: ({ agentId }: { agentId: string }) => <span data-testid="avatar">{agentId}</span>,
    ApiSessionSwitcher: () => null,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => null,
    ComputerControlStub: () => null,
    GroupAvatar: ({ members }: { members: Array<{ id: string }> }) => (
      <span data-testid="group-avatar">{members.map((member) => member.id).join(',')}</span>
    ),
    OPEN_SETTINGS_EVENT: 'swarm:open-settings',
    RemoteSessionSwitcher: () => null,
    Settings: () => <span data-testid="settings-glyph" />,
    Pencil: () => <span data-testid="pencil-glyph" />,
    Folder: () => <span data-testid="folder-glyph" />,
    PanelLeft: () => <span data-testid="panel-left-glyph" />,
    roleCssClass: (role: string) => `os-agent-role-${role}`,
    ThemeToggle: () => <span data-testid="theme-toggle" />,
    activeChatAgentId: 'codey',
    selectedBlueprint: 'codey',
    selectedAgentName: 'Codey',
    selectedAgent: { id: 'codey', name: 'Codey' },
    headerFaceAgentId: 'codey',
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
    cliRemoteSession: null,
    openAgentEditor: vi.fn(),
    openRail: vi.fn(),
    openSettingsSheet: vi.fn(),
    openTeamEditor: vi.fn(),
    ...overrides,
  }
}

function renderHeader(overrides: Record<string, unknown> = {}) {
  return render(
    <ChatHeader {...(baseProps(overrides) as React.ComponentProps<typeof ChatHeader>)} />,
  )
}

function stubProfileFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ profiles: [], data: [] }),
    }),
  )
}

beforeEach(() => stubProfileFetch())
afterEach(() => vi.unstubAllGlobals())

describe('#1676 — the header centers the agent as a floating pill', () => {
  it('keeps the header as a flex band and floats the pill out of flow', () => {
    const header = cssBlock('.os-chat-header')
    // #560 pin: fixed chrome height. #1676 must not reintroduce a taller grid band.
    expect(header).toMatch(/height:\s*var\(--os-top-chrome-h\)/)
    expect(header).toMatch(/display:\s*flex/)
    expect(cssBlock('.os-agent-pill')).not.toMatch(/grid-column:\s*2/)
    expect(cssBlock('.os-agent-pill')).toMatch(/position:\s*absolute/)
    expect(cssBlock('.os-agent-pill')).toMatch(/left:\s*50%/)
    expect(cssBlock('.os-agent-pill')).toMatch(/top:\s*calc\(100% \+ 0\.5rem\)/)
    expect(cssBlock('.os-agent-pill')).toMatch(/transform:\s*translateX\(-50%\)/)
  })

  it('anchors the pill under the header, not inside the left-flush identity', () => {
    const { container } = renderHeader()
    const header = container.querySelector('header.os-chat-header')!
    const pill = screen.getByTestId('selected-agent-header')
    // Absolute child of the header: floats under the band, not nested under lead.
    expect(pill.parentElement).toBe(header)
    expect(pill).toHaveClass('os-agent-pill')
    expect(pill).toHaveAttribute('data-pill', 'agent')
    const lead = header.querySelector('.os-chat-header__identity')!
    expect(lead.querySelector('.os-agent-pill')).toBeNull()
  })

  it('styles the pill with theme tokens only, so dark and light both work', () => {
    const pill = cssBlock('.os-agent-pill')
    // AGENTS.md: no raw hex where a theme token exists.
    expect(pill).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(pill).toMatch(/var\(--color-base-100\)/)
    expect(pill).toMatch(/var\(--color-base-content\)/)
    expect(pill).toMatch(/border-radius:\s*9999px/)
    // Clamped so a long name truncates inside the pill rather than shoving the
    // controls cluster off the band.
    expect(pill).toMatch(/max-width:\s*min\(26rem/)
  })

  it('reveals the pill pencil on pill hover, not on the lead slot hover', () => {
    // The pencil moved into the pill with the identity; a lead-scoped reveal
    // would leave it permanently invisible.
    expect(css).toMatch(/\.os-agent-pill:hover \.os-navbar-edit-btn/)
    expect(css).not.toMatch(/\.os-chat-header__identity:hover \.os-navbar-edit-btn/)
  })
})

describe('#1676 — clicking the pill opens the edit-agent pane', () => {
  it('opens the existing AgentConfigSidepane for the pill agent', () => {
    renderHeader({ selectedBlueprint: 'codey', selectedAgentName: 'Codey' })
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()

    fireEvent.click(screen.getByTestId('selected-agent-header'))

    const pane = screen.getByTestId('agent-config-sidepane')
    expect(pane).toBeInTheDocument()
    expect(screen.getByTestId('agent-config-name-heading')).toHaveTextContent('Codey')
    // The pane is the ONE config surface (#1447), mounted as a right-side sheet.
    expect(screen.getByRole('dialog', { name: 'Agent configuration' })).toBeInTheDocument()
  })

  it('opens the pane for whichever agent the pill is showing', () => {
    const { rerender } = renderHeader({ selectedBlueprint: 'agy', selectedAgentName: 'Agy' })
    fireEvent.click(screen.getByTestId('selected-agent-header'))
    expect(screen.getByTestId('agent-config-name-input')).toHaveValue('Agy')

    rerender(
      <ChatHeader
        {...(baseProps({
          selectedBlueprint: 'codey',
          selectedAgentName: 'Codey',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    // The pane follows the foreground seat rather than stranding the old one.
    expect(screen.getByTestId('agent-config-name-input')).toHaveValue('Codey')
  })

  it('clicking the avatar still opens the same pane exactly once', () => {
    renderHeader({ selectedBlueprint: 'codey', selectedAgentName: 'Codey' })
    fireEvent.click(screen.getByTestId('header-avatar-generations'))
    // stopPropagation on the avatar keeps the pill handler from double-firing;
    // a second open would remount the sheet and drop the pane's focus.
    expect(screen.getAllByTestId('agent-config-sidepane')).toHaveLength(1)
  })

  it('leaves rename, folder and pencil clicks to their own controls', () => {
    const openAgentEditor = vi.fn()
    const openSettingsSheet = vi.fn()
    renderHeader({
      selectedBlueprint: 'codey',
      selectedAgentName: 'Codey',
      openAgentEditor,
      openSettingsSheet,
      workspaceSubtitle: '/srv/work',
      workspaceSubtitleDisplay: '/srv/work',
    })

    // The name keeps its #1233 click-to-rename; the pane is not a rename field.
    fireEvent.click(screen.getByTestId('os-identity-name'))
    expect(screen.getByTestId('os-identity-name-input')).toBeInTheDocument()
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()

    // The folder subtitle still routes to the agent editor, not the pane.
    fireEvent.click(screen.getByTestId('os-navbar-workspace-subtitle'))
    expect(openAgentEditor).toHaveBeenCalledWith(expect.objectContaining({ agentId: 'codey' }))
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()
  })

  it('routes a team seat to the team editor so the pill, name and pencil agree', () => {
    const openTeamEditor = vi.fn()
    renderHeader({
      teamFromUrl: 'demo-team',
      selectedBlueprint: '',
      selectedAgentName: 'Demo Team',
      selectedTeam: { id: 'demo-team', name: 'Demo Team', members: [] },
      openTeamEditor,
    })
    fireEvent.click(screen.getByTestId('selected-agent-header'))
    expect(openTeamEditor).toHaveBeenCalledWith(
      expect.objectContaining({ teamId: 'demo-team', teamName: 'Demo Team' }),
    )
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()
  })
})

describe('#1676 — the pill follows the foreground seat', () => {
  it('re-renders name, seat stamp and avatar when the foreground agent changes', () => {
    const { rerender } = renderHeader({
      selectedBlueprint: 'codey',
      selectedAgentName: 'Codey',
      headerFaceAgentId: 'codey',
    })
    const pill = () => screen.getByTestId('selected-agent-header')
    expect(pill()).toHaveTextContent('Codey')
    expect(pill()).toHaveAttribute('data-seat', 'api:codey')
    expect(screen.getByTestId('avatar')).toHaveTextContent('codey')

    rerender(
      <ChatHeader
        {...(baseProps({
          selectedBlueprint: 'agy',
          selectedAgentName: 'Agy',
          headerFaceAgentId: 'agy',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(pill()).toHaveTextContent('Agy')
    expect(pill()).toHaveAttribute('data-seat', 'api:agy')
    expect(screen.getByTestId('avatar')).toHaveTextContent('agy')
  })

  it('keeps the pill live for a remote seat', () => {
    renderHeader({
      remoteFromUrl: 'anythingllm',
      selectedBlueprint: 'hermes-bot',
      selectedAgentName: 'Hermes',
      selectedRemote: { id: 'anythingllm', kind: 'anythingllm', title: 'AnythingLLM' },
    })
    const pill = screen.getByTestId('selected-agent-header')
    expect(pill).toHaveAttribute('data-seat', 'remote:anythingllm')
    fireEvent.click(pill)
    expect(screen.getByTestId('agent-config-sidepane')).toBeInTheDocument()
  })
})

describe('#1676 — empty / no-seat states', () => {
  it('renders a documented placeholder pill and no dead edit control', () => {
    renderHeader({
      selectedBlueprint: '',
      selectedAgentName: '',
      headerFaceAgentId: '',
      selectedAgent: null,
    })
    const pill = screen.getByTestId('selected-agent-header')
    expect(pill).toHaveAttribute('data-empty', 'true')
    expect(pill).toHaveAttribute('data-pill-action', 'none')
    expect(pill).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByTestId('os-agent-pill-placeholder')).toHaveTextContent('No agent selected')
    // Nothing to rename and nothing to configure on an empty seat.
    expect(screen.queryByTestId('os-identity-name')).toBeNull()

    fireEvent.click(pill)
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()
  })

  it('closes the pane when the seat it was editing goes away', () => {
    const { rerender } = renderHeader({ selectedBlueprint: 'codey', selectedAgentName: 'Codey' })
    fireEvent.click(screen.getByTestId('selected-agent-header'))
    expect(screen.getByTestId('agent-config-sidepane')).toBeInTheDocument()

    rerender(
      <ChatHeader
        {...(baseProps({
          selectedBlueprint: '',
          selectedAgentName: '',
          headerFaceAgentId: '',
          selectedAgent: null,
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()
    expect(screen.getByTestId('os-agent-pill-placeholder')).toBeInTheDocument()
  })

  it('recovers the live pill when a seat resolves again', () => {
    const { rerender } = renderHeader({
      selectedBlueprint: '',
      selectedAgentName: '',
      headerFaceAgentId: '',
      selectedAgent: null,
    })
    expect(screen.getByTestId('selected-agent-header')).toHaveAttribute('data-empty', 'true')

    rerender(
      <ChatHeader
        {...(baseProps({
          selectedBlueprint: 'codey',
          selectedAgentName: 'Codey',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    const pill = screen.getByTestId('selected-agent-header')
    expect(pill).toHaveAttribute('data-empty', 'false')
    expect(pill).toHaveAttribute('data-pill-action', 'open-agent-config')
    fireEvent.click(pill)
    expect(screen.getByTestId('agent-config-sidepane')).toBeInTheDocument()
  })
})
