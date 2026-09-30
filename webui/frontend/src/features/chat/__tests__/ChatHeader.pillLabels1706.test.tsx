/**
 * #1698 / #1704 / #1706 — the floating agent pill as RENDERED.
 *
 * These assertions read the DOM, not the source. `agentPillLabels.test.ts`
 * pins the decision table; this file pins that the pill actually renders the
 * decision, that the three session shapes are mutually exclusive on screen,
 * and — for #1704 — that the folder affordance can no longer add a row to the
 * badge.
 *
 * #1704's "pill height does not jump" is a geometry claim and jsdom computes
 * no geometry, so it is expressed as its DOM cause: the control that used to
 * live inside `.os-navbar-identity-text` (a `flex-direction: column` stack, so
 * one more child IS one more line) now lives in `.os-agent-pill__actions`, a
 * SIBLING of that column, and paints no visible text. Containment in the
 * rendered tree is a strictly stronger statement than "the badge is not
 * taller", because it holds for any label, any seat and any folder state.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Folder as RealFolder, Pencil as RealPencil } from 'lucide-react'
import fs from 'fs'
import path from 'path'
import type React from 'react'
import { ChatHeader } from '../ChatHeader'
import { RAIL_SECTIONS_STORAGE_KEY } from '../../../lib/railSections'
import { setConversationIdForAgent } from '../../../lib/agentChat'

const css = fs.readFileSync(path.resolve(__dirname, '../../../index.css'), 'utf8')

/**
 * Parse the LAST top-level block for `selector` into its declarations.
 *
 * `index.css` layers history, so the cascade winner is the last declaration of
 * a selector — that is the one the browser uses and therefore the one under
 * test. Returns a property → value map, so a test asserts a declaration rather
 * than a character window over the file.
 *
 * The match is line-anchored, so `.os-navbar-edit-btn` cannot accidentally
 * match the tail of `.os-agent-pill .os-navbar-edit-btn`.
 */
function ruleDeclarations(selector: string): Record<string, string> {
  const pattern = new RegExp(`^[ \\t]*${escapeRegExp(selector)}[ \\t]*\\{`, 'gm')
  const matches = [...css.matchAll(pattern)]
  const last = matches[matches.length - 1]
  expect(matches.length, `index.css declares "${selector} {…}"`).toBeGreaterThan(0)
  const start = (last?.index ?? 0) + (last?.[0].length ?? 0)
  return parseBody(css.slice(start, css.indexOf('}', start)))
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function parseBody(body: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const part of body.replace(/\/\*[\s\S]*?\*\//g, '').split(';')) {
    const colon = part.indexOf(':')
    if (colon < 0) continue
    const prop = part.slice(0, colon).trim()
    if (prop) out[prop] = part.slice(colon + 1).trim()
  }
  return out
}

/**
 * Is `selector` the FIRST rule inside a `@media (hover: hover) and (pointer:
 * fine)` block? That is how the repo scopes a hover-only reveal, so "pointer-only
 * hover" is a placement fact, not a phrase.
 */
function insidePointerHoverBlock(selector: string): boolean {
  const at = css.indexOf(`${selector} {`)
  if (at < 0) return false
  const mediaAt = css.lastIndexOf('@media', at)
  if (mediaAt < 0) return false
  const open = css.indexOf('{', mediaAt)
  // Nothing but whitespace (or a comment) may precede it inside that block.
  if (css.slice(open + 1, at).replace(/\/\*[\s\S]*?\*\//g, '').trim() !== '') return false
  return css.slice(mediaAt, open + 1).includes('(hover: hover) and (pointer: fine)')
}

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: ({ agentId }: { agentId?: string }) => (
      <span data-testid="avatar">{agentId || ''}</span>
    ),
    ApiSessionSwitcher: () => null,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => null,
    ComputerControlStub: () => null,
    GroupAvatar: () => <span data-testid="group-avatar" />,
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

function pill() {
  return screen.getByTestId('selected-agent-header')
}

/** The pill's stacked label column. One more child here is one more line. */
function textColumn(): HTMLElement {
  return pill().querySelector('.os-navbar-identity-text') as HTMLElement
}

/** The pill's right-aligned action cluster (#1704). */
function actions(): HTMLElement {
  return pill().querySelector('.os-agent-pill__actions') as HTMLElement
}

function stubProfileFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ profiles: [], data: [] }) }),
  )
}

beforeEach(() => {
  stubProfileFetch()
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('#1698 §A / #1706 §A — the self seat renders role@rig', () => {
  it('renders one address inside the role badge, with the rig inside it', () => {
    renderHeader({
      selectedBlueprint: 'codey',
      selectedAgentName: 'Codey',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
      headerRigName: 'factory',
    })

    expect(pill()).toHaveAttribute('data-pill-mode', 'role')
    expect(pill()).toHaveTextContent('Codey')
    // The full canonical address, as one string, on the rendered surface.
    expect(pill()).toHaveTextContent('Engineer@factory')

    const badge = screen.getByTestId('os-header-role-badge')
    // The `@rig` half lives INSIDE `.os-agent-role-badge`, which is the only
    // element allowed to carry role colour (AGENTS.md). If the rig were a
    // sibling it would need its own colour, and the rule would be broken.
    expect(badge).toContainElement(screen.getByTestId('os-agent-pill-rig'))
    expect(badge).toHaveAttribute('data-pill-address', 'Engineer@factory')
    expect(badge).toHaveAttribute('data-role', 'engineer')
    expect(badge).toHaveClass('os-agent-role-badge')
    expect(badge.className).toContain('os-agent-role-engineer')
  })

  it('reads a dynamic rig from the seat sidepane section, with no rig prop', () => {
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_factory', name: 'factory' }],
        membership: { codey: 'sec_factory' },
      }),
    )
    renderHeader({
      selectedBlueprint: 'codey',
      showHeaderRole: true,
      headerRole: 'support',
      headerRoleLabel: 'Support',
    })
    expect(pill()).toHaveTextContent('Support@factory')
  })

  it('renders a bare role and no dangling @ when the seat is in no rig', () => {
    renderHeader({
      selectedBlueprint: 'codey',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
    })
    const badge = screen.getByTestId('os-header-role-badge')
    expect(badge).toHaveTextContent('Engineer')
    expect(badge.textContent || '').not.toContain('@')
    expect(screen.queryByTestId('os-agent-pill-rig')).toBeNull()
    expect(badge).toHaveAttribute('data-pill-address', 'Engineer')
  })

  it('reads the rig from THIS seat section only, never another seat s', () => {
    // Stated as a difference, not an absence. "No rig shows" is also what a
    // pill with no address logic at all shows, so asserting the absence alone
    // would pass on the unfixed code. The claim is that membership decides it.
    const roleSeat = {
      selectedBlueprint: 'codey',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
    }
    const section = {
      sections: [{ id: 'sec_factory', name: 'factory' }],
      membership: { codey: 'sec_factory' },
    }

    localStorage.setItem(RAIL_SECTIONS_STORAGE_KEY, JSON.stringify(section))
    const seated = renderHeader(roleSeat)
    const inRig = screen.getByTestId('os-header-role-badge').textContent
    seated.unmount()

    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({ ...section, membership: { someoneelse: 'sec_factory' } }),
    )
    renderHeader(roleSeat)
    const outOfRig = screen.getByTestId('os-header-role-badge').textContent

    expect(inRig).toBe('Engineer@factory')
    expect(outOfRig).toBe('Engineer')
  })

  it('never puts a model or a vendor name in the address', () => {
    renderHeader({
      selectedBlueprint: 'codey',
      selectedAgent: { id: 'codey', name: 'Codey', provider: 'anthropic', model: 'claude-x' },
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
      headerRigName: 'factory',
    })
    // A model is a weighted pool across vendors, so naming one here would be a
    // fresh lie. The address is the role and the rig, full stop.
    const address = screen.getByTestId('os-header-role-badge').textContent || ''
    expect(address).toBe('Engineer@factory')
    expect(address.toLowerCase()).not.toMatch(/claude|gpt|anthropic|openai|gemini/)
  })
})

describe('#1706 §B — a group chat renders the selected member, never role@rig', () => {
  const team = {
    teamFromUrl: 'squad',
    selectedBlueprint: '',
    selectedTeam: { id: 'squad', name: 'Squad', members: [{ id: 'ada', name: 'Ada' }] },
    teamChatMemberId: 'ada',
    selectedAgentName: 'Squad',
    headerGroupMembers: [{ id: 'ada', name: 'Ada' }],
    // ChatPage only offers a role for non-team seats, but a stale
    // `showHeaderRole` must still not put `role@rig` on a group chat.
    showHeaderRole: true,
    headerRole: 'engineer',
    headerRoleLabel: 'Engineer',
  }

  it('puts the group name on top and the selected member underneath', () => {
    renderHeader(team)
    expect(pill()).toHaveAttribute('data-pill-mode', 'group')
    const top = pill().querySelector('.os-navbar-identity-label') as HTMLElement
    expect(top).toHaveTextContent('Squad')
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent('Ada')
  })

  it('suppresses the role badge entirely for a group chat (#1706 §D.14)', () => {
    renderHeader(team)
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()
    expect(screen.queryByTestId('os-agent-pill-rig')).toBeNull()
    expect(pill().textContent || '').not.toContain('@')
  })

  it('renders no bottom row rather than a wrong one when the member is unknown', () => {
    renderHeader({ ...team, teamChatMemberId: 'stranger', headerGroupMembers: [] })
    expect(pill()).toHaveAttribute('data-pill-mode', 'group')
    expect(screen.queryByTestId('os-agent-pill-bottom')).toBeNull()
  })

  it('follows the selected member as it changes, without a wrong label in between', () => {
    const { rerender } = renderHeader(team)
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent('Ada')

    rerender(
      <ChatHeader
        {...(baseProps({
          ...team,
          teamChatMemberId: 'grace',
          headerGroupMembers: [
            { id: 'ada', name: 'Ada' },
            { id: 'grace', name: 'Grace' },
          ],
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    const bottom = screen.getByTestId('os-agent-pill-bottom')
    expect(bottom).toHaveTextContent('Grace')
    expect(bottom).not.toHaveTextContent('Ada')
  })

  it('names the selected remote agent for a remote seat', () => {
    renderHeader({
      remoteFromUrl: 'anythingllm',
      selectedBlueprint: 'hermes-bot',
      selectedAgentName: 'Hermes',
      selectedRemote: { id: 'anythingllm', kind: 'anythingllm', title: 'AnythingLLM' },
      remoteNavbarAgents: [{ id: 'ha-suno-archive', label: 'HASS Agent' }],
      sessionFromUrl: 'ha-suno-archive',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
    })
    expect(pill()).toHaveAttribute('data-pill-mode', 'group')
    expect(pill().querySelector('.os-navbar-identity-label')).toHaveTextContent('AnythingLLM')
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent('HASS Agent')
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()
  })
})

describe('#1706 §C / #1698 §B — a dedicated chat renders `chat: <peer>`', () => {
  function chatSeat(overrides: Record<string, unknown> = {}) {
    return {
      selectedBlueprint: 'ha-suno-archive',
      selectedAgentName: 'ha-suno-archive',
      // A `?session=` that is NOT the agent own stable conversation id.
      sessionFromUrl: 'conv-dedicated',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
      headerRigName: 'factory',
      ...overrides,
    }
  }

  beforeEach(() => {
    // The agent's own stable conversation id — the home seat, not a chat.
    setConversationIdForAgent('ha-suno-archive', 'conv-home')
  })

  it('defaults to `chat: <peer name>` with the peer on top and no role@rig', () => {
    renderHeader(chatSeat())
    expect(pill()).toHaveAttribute('data-pill-mode', 'chat')
    expect(pill().querySelector('.os-navbar-identity-label')).toHaveTextContent('ha-suno-archive')
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent(
      'chat: ha-suno-archive',
    )
    // #1698 §B.5 — the secondary chip must not be the current user role@rig.
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()
    expect(pill().textContent || '').not.toContain('@')
  })

  it("prefers this chat's assigned name when one is given", () => {
    renderHeader(chatSeat({ pillChatName: 'Sunset mixes' }))
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent('Sunset mixes')
  })

  it('stays on the home seat when the session is the agent own conversation', () => {
    renderHeader(chatSeat({ sessionFromUrl: 'conv-home' }))
    expect(pill()).toHaveAttribute('data-pill-mode', 'role')
    expect(screen.queryByTestId('os-agent-pill-bottom')).toBeNull()
    expect(pill()).toHaveTextContent('Engineer@factory')
  })

  it('reads a ?session= absent from the URL as the home seat', () => {
    renderHeader(chatSeat({ sessionFromUrl: '' }))
    expect(pill()).toHaveAttribute('data-pill-mode', 'role')
  })
})

describe('#1706 §11 — switching sessions never leaves a wrong bottom label', () => {
  it('moves home → group → chat with the seat, one mode at a time', () => {
    const { rerender } = renderHeader({
      selectedBlueprint: 'codey',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
      headerRigName: 'factory',
    })
    expect(pill()).toHaveAttribute('data-pill-mode', 'role')
    expect(pill()).toHaveTextContent('Engineer@factory')

    rerender(
      <ChatHeader
        {...(baseProps({
          teamFromUrl: 'squad',
          selectedBlueprint: '',
          selectedAgentName: 'Squad',
          selectedTeam: { id: 'squad', name: 'Squad', members: [{ id: 'ada', name: 'Ada' }] },
          teamChatMemberId: 'ada',
          headerGroupMembers: [{ id: 'ada', name: 'Ada' }],
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(pill()).toHaveAttribute('data-pill-mode', 'group')
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent('Ada')
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()

    rerender(
      <ChatHeader
        {...(baseProps({
          selectedBlueprint: 'ada',
          selectedAgentName: 'Ada',
          sessionFromUrl: 'conv-dedicated',
          showHeaderRole: true,
          headerRole: 'engineer',
          headerRoleLabel: 'Engineer',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    expect(pill()).toHaveAttribute('data-pill-mode', 'chat')
    expect(screen.getByTestId('os-agent-pill-bottom')).toHaveTextContent('chat: Ada')
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()
  })

  it('keeps the pill in one slot: a mode contributes at most one bottom row', () => {
    renderHeader({
      remoteFromUrl: 'anythingllm',
      selectedBlueprint: 'hermes-bot',
      selectedAgentName: 'Hermes',
      selectedRemote: { id: 'anythingllm', kind: 'anythingllm', title: 'AnythingLLM' },
      remoteNavbarAgents: [{ id: 'ha-suno-archive', label: 'HASS Agent' }],
      sessionFromUrl: 'ha-suno-archive',
      showHeaderRole: true,
      headerRole: 'engineer',
      headerRoleLabel: 'Engineer',
      headerRigName: 'factory',
    })
    // `avatar | top label | bottom label | actions` — one bottom element, and
    // the action cluster is a sibling of the column, so nothing wraps.
    expect(screen.getAllByTestId('os-agent-pill-bottom')).toHaveLength(1)
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()
    expect(actions().parentElement).toBe(pill())
    expect(actions().parentElement).toBe(textColumn().parentElement)
  })
})

describe('#1704 — Select folder is a right-aligned icon, not a taller text row', () => {
  const unsetSeat = {
    selectedBlueprint: 'general-assistant',
    selectedAgentName: 'General Assistant',
    workspaceSubtitle: '',
    workspaceFolderEditable: true,
  }

  it('lives in the right-aligned action cluster, NOT in the label column', () => {
    renderHeader(unsetSeat)
    const folder = screen.getByTestId('os-navbar-workspace-subtitle-unset')

    // THE height claim, in DOM terms. `.os-navbar-identity-text` is a
    // `flex-direction: column` stack, so a child there is a line. The control
    // is a SIBLING of that column now, inside the single-row action cluster, so
    // it cannot add a row at any viewport width or label length.
    expect(textColumn().contains(folder)).toBe(false)
    expect(actions().contains(folder)).toBe(true)
    expect(folder.parentElement?.parentElement).toBe(actions())
    // The cluster is itself a sibling of the label column, not nested in it.
    expect(actions().parentElement).toBe(textColumn().parentElement)
  })

  it('paints an icon and no visible text', () => {
    renderHeader(unsetSeat)
    const folder = screen.getByTestId('os-navbar-workspace-subtitle-unset')
    expect(folder.tagName).toBe('BUTTON')
    expect(folder.querySelector('[data-testid="folder-glyph"]')).not.toBeNull()
    // Every text node in the control is screen-reader-only, so the badge cannot
    // grow a word of visible text.
    const walker = document.createTreeWalker(folder, NodeFilter.SHOW_TEXT)
    const visible: string[] = []
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = (node.textContent || '').trim()
      if (!text) continue
      const owner = node.parentElement?.closest('.sr-only') ? 'sr-only' : 'visible'
      if (owner === 'visible') visible.push(text)
    }
    expect(visible).toEqual([])
    // …and it still HAS an accessible name.
    expect(folder).toHaveAccessibleName('Select folder')
  })

  it('keeps the pencil density: same square button classes and glyph size', () => {
    // Real lucide glyphs — the stubbed ones carry no `h-4` sizing class, so a
    // stub comparison would prove nothing about the density #1704 §2 names.
    renderHeader({
      ...unsetSeat,
      Folder: RealFolder,
      Pencil: RealPencil,
    })
    const folder = screen.getByTestId('os-navbar-workspace-subtitle-unset')
    const pencil = screen.getByRole('button', { name: 'Edit agent' })
    for (const cls of ['btn', 'btn-ghost', 'btn-sm', 'btn-square', 'os-navbar-edit-btn']) {
      expect(folder).toHaveClass(cls)
      expect(pencil).toHaveClass(cls)
    }
    // One h-4 glyph each — the old folder was h-3, which is the density mismatch
    // #1704 §2 names.
    expect(folder.querySelector('svg')?.getAttribute('class')).toContain('h-4')
    expect(pencil.querySelector('svg')?.getAttribute('class')).toContain('h-4')
  })

  it('still opens the same folder-select flow (#1704 §5: chrome only)', () => {
    const openAgentEditor = vi.fn()
    renderHeader({ ...unsetSeat, openAgentEditor })
    fireEvent.click(screen.getByTestId('os-navbar-workspace-subtitle-unset'))
    expect(openAgentEditor).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: 'general-assistant' }),
    )
  })

  it('does not double up: a bound folder keeps the text subtitle and drops the icon', () => {
    // Driven as a transition so the assertion is about the CHANGE: the icon
    // appears when nothing is bound and disappears when a path is, rather than
    // "the icon is absent" — which the unfixed code also satisfies.
    const { rerender } = renderHeader(unsetSeat)
    expect(actions()).toBeInTheDocument()
    expect(screen.getByTestId('os-navbar-workspace-subtitle-unset')).toBeInTheDocument()

    rerender(
      <ChatHeader
        {...(baseProps({
          ...unsetSeat,
          workspaceSubtitle: '/srv/work — branch: main',
          workspaceSubtitleDisplay: '.../work — branch: main',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    // The bound path is information, so it stays in the label column.
    expect(textColumn().contains(screen.getByTestId('os-navbar-workspace-subtitle'))).toBe(true)
    // …and the "nothing bound" icon is gone rather than stacked beside it.
    expect(screen.queryByTestId('os-navbar-workspace-subtitle-unset')).toBeNull()
    expect(screen.queryByTestId('folder-glyph')).toBeNull()
    // The cluster itself survives: the pencil is still there.
    expect(actions()).toBeInTheDocument()
  })

  it('never offers the affordance on a seat that cannot bind a folder', () => {
    renderHeader({ ...unsetSeat, workspaceFolderEditable: false })
    expect(screen.queryByTestId('os-navbar-workspace-subtitle-unset')).toBeNull()
    expect(actions()).toBeInTheDocument()
  })
})

describe('#1704 — the action cluster is one row, with theme tokens only', () => {
  it('lays the cluster out as a single centred, non-shrinking row', () => {
    const rule = ruleDeclarations('.os-agent-pill__actions')
    expect(rule['display']).toBe('inline-flex')
    // One line box: the children are side by side, never stacked.
    expect(rule['flex-direction'] || '').not.toBe('column')
    expect(rule['align-items']).toBe('center')
    // `flex-shrink: 0` so the labels keep the width and the icons keep theirs.
    expect(rule['flex-shrink']).toBe('0')
  })

  it('sets no colour of its own — the icons inherit the ghost button styling', () => {
    const rule = ruleDeclarations('.os-agent-pill__actions')
    expect(Object.keys(rule)).not.toContain('color')
    expect(Object.keys(rule)).not.toContain('background')
    // AGENTS.md: theme tokens, never raw hex, anywhere in the new cluster rules.
    for (const selector of [
      '.os-agent-pill__actions',
      '.os-agent-pill__actions .os-navbar-edit-btn',
      '.os-agent-pill .os-agent-role-badge',
      '.os-agent-pill__rig',
    ]) {
      const pattern = new RegExp(`^[ \\t]*${escapeRegExp(selector)}[ \\t]*\\{([^}]*)\\}`, 'gm')
      for (const match of css.matchAll(pattern)) {
        expect(match[1], `${selector} must not hardcode a colour`).not.toMatch(
          /#[0-9a-fA-F]{3,8}\b|rgba?\(/,
        )
      }
    }
  })

  it('reveals the cluster on pointer hover AND on keyboard focus, not hover-only', () => {
    // Touch / no-hover: the icon is simply visible (base `opacity: 1`).
    expect(ruleDeclarations('.os-navbar-edit-btn')['opacity']).toBe('1')
    // Fine pointer: hidden, and shown again on pill hover / focus-within.
    expect(insidePointerHoverBlock('.os-agent-pill .os-navbar-edit-btn')).toBe(true)
    expect(ruleDeclarations('.os-agent-pill .os-navbar-edit-btn')['opacity']).toBe('0')
    // #1704 §4 — a keyboard user must be able to reach the folder icon, so the
    // reveal is not hover-only: the cluster carries its own focus-visible rule,
    // scoped to the same pointer block.
    expect(insidePointerHoverBlock('.os-agent-pill__actions .os-navbar-edit-btn:focus-visible')).toBe(
      true,
    )
    expect(
      ruleDeclarations('.os-agent-pill__actions .os-navbar-edit-btn:focus-visible')['opacity'],
    ).toBe('1')
  })

  it('keeps the address in the role badge, so role colour stays in one place', () => {
    const pillBadge = ruleDeclarations('.os-agent-pill .os-agent-role-badge')
    // `text-transform: none` is scoped to the pill so `Support@local` is not
    // folded to `support@local`; the rail's badge is deliberately untouched.
    expect(pillBadge['text-transform']).toBe('none')
    expect(ruleDeclarations('.os-agent-pill__rig')['opacity']).toBe('0.75')
  })
})
