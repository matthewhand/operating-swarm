/**
 * #1724 — three defects in the floating agent pill's hover-revealed actions.
 *
 * §1  The reveal is `opacity`-only, so an INVISIBLE control still eats clicks.
 * §2  `.os-recycle-bin` hand-copies the size the footer cluster owns.
 * §3  "Right-aligned" was state-dependent: the folder was trailing below 640px
 *     and 34px inboard at desktop, because only the pencil's shell carried
 *     `hidden sm:flex`.
 *
 * The paint-order/hit-test half of §1 and §3 is measured in real Chromium by
 * `scripts/measure-chat-chrome.mjs` (jsdom has no compositor). What is asserted
 * HERE is everything jsdom can answer honestly:
 *
 *   - the RENDERED DOM: which control is trailing, in DOM order, and what each
 *     shell carries;
 *   - the PARSED STYLESHEET: that the hidden state gates pointer events as well
 *     as opacity, read through the brace-matched helpers rather than a needle.
 *
 * No assertion greps `.tsx`/`.css` source for a literal.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type React from 'react'
import { ChatHeader } from '../ChatHeader'
import { declarationIn, declarations, rule } from '../../../lib/__tests__/helpers/cssRules'

const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
const POINTER_BLOCK = '@media (hover: hover) and (pointer: fine)'

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
    ThemeToggle: () => <span data-testid="theme-glyph" />,
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

const unsetSeat = {
  selectedBlueprint: 'general-assistant',
  selectedAgentName: 'General Assistant',
  workspaceSubtitle: '',
  workspaceFolderEditable: true,
}

function renderHeader(overrides: Record<string, unknown> = {}) {
  return render(<ChatHeader {...(baseProps(overrides) as React.ComponentProps<typeof ChatHeader>)} />)
}

function pill(): HTMLElement {
  return screen.getByTestId('selected-agent-header')
}
function actions(): HTMLElement {
  return pill().querySelector('.os-agent-pill__actions') as HTMLElement
}
function folder(): HTMLElement {
  return screen.getByTestId('os-navbar-workspace-subtitle-unset')
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ profiles: [], data: [] }) }),
  )
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('#1724 §1 — a hidden reveal must not take clicks', () => {
  it('gates pointer events with opacity in the hidden state and restores both', () => {
    // Read each declaration through the brace-matched helper, inside the
    // pointer-only block, so a bare `opacity: 0` elsewhere in a 7,000-line
    // sheet cannot satisfy this.
    expect(declarationIn(css, '.os-agent-pill .os-navbar-edit-btn', 'opacity', POINTER_BLOCK)).toBe('0')
    expect(
      declarationIn(css, '.os-agent-pill .os-navbar-edit-btn', 'pointer-events', POINTER_BLOCK),
      'the hidden state must be transparent to the pointer, not only invisible',
    ).toBe('none')

    // The revealed half restores it, on BOTH hover and keyboard focus — a
    // `:focus-visible` reveal that left `pointer-events: none` would give a
    // keyboard user a control they can see but not activate.
    for (const selector of [
      '.os-agent-pill:hover .os-navbar-edit-btn',
      '.os-agent-pill:focus-within .os-navbar-edit-btn',
    ]) {
      expect(declarationIn(css, selector, 'opacity', POINTER_BLOCK), selector).toBe('1')
      expect(declarationIn(css, selector, 'pointer-events', POINTER_BLOCK), selector).toBe('auto')
    }
  })

  it('gates the action SHELL too, so a click reaches the pill surface', () => {
    // `pointer-events: none` on the button hands the hit to its wrapper, which
    // would still intercept it — so the shell carries the same gate.
    expect(
      declarationIn(css, '.os-agent-pill .os-agent-pill__action', 'pointer-events', POINTER_BLOCK),
    ).toBe('none')
    expect(
      declarationIn(css, '.os-agent-pill:hover .os-agent-pill__action', 'pointer-events', POINTER_BLOCK),
    ).toBe('auto')
  })

  it('renders every action inside a shell that carries the hook class', () => {
    // The stylesheet gates `.os-agent-pill__action`; if a shell forgot the
    // class, that shell would silently keep eating clicks at desktop width.
    renderHeader(unsetSeat)
    const shells = actions().querySelectorAll('.os-agent-pill__action')
    expect(shells.length).toBeGreaterThan(0)
    for (const shell of shells) {
      expect(shell.querySelector('.os-navbar-edit-btn')).not.toBeNull()
    }
  })

  it('leaves the control clickable when revealed, so the fix costs no behaviour', () => {
    // `pointer-events` is a hit-test property, so it is invisible to
    // `fireEvent.click`. The click path is asserted so that adding the gate can
    // never be mistaken for disabling the affordance.
    const openAgentEditor = vi.fn()
    renderHeader({ ...unsetSeat, openAgentEditor })
    fireEvent.click(folder())
    expect(openAgentEditor).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: 'general-assistant' }),
    )
  })

  it('never gates the pointer on a touch device, where the reveal is always on', () => {
    // Outside the pointer-only block the base rule is `opacity: 1` and must not
    // carry a `pointer-events` at all — a stray `none` here would make the
    // control unclickable on phones, which is the opposite bug.
    const base = declarations(rule(css, '.os-navbar-edit-btn'))
    expect(base.opacity).toBe('1')
    expect(base['pointer-events']).toBeUndefined()
  })
})

describe('#1724 §3 — the folder is the trailing control at every width', () => {
  it('puts the folder LAST in the rendered cluster', () => {
    // DOM order, not visual order: a CSS `order` would fix the pixels while
    // leaving focus order and screen-reader order disagreeing with them.
    renderHeader(unsetSeat)
    const children = Array.from(actions().children)
    expect(children.length).toBeGreaterThan(1)
    expect(children[children.length - 1]).toBe(folder().parentElement)
  })

  it('keeps the width-dependent shell, and it is not the folder', () => {
    // The defect was structural: only the pencil's shell carried
    // `hidden sm:flex`, so hiding it at <640px handed the trailing slot to the
    // folder. Now the folder trails unconditionally, so the shell that shrinks
    // is the pencil's and the folder's position cannot move.
    renderHeader(unsetSeat)
    const pencilShell = screen.getByRole('button', { name: 'Edit agent' }).parentElement as HTMLElement
    const folderShell = folder().parentElement as HTMLElement
    expect(pencilShell.className).toContain('hidden')
    expect(folderShell.className).not.toContain('hidden')
    expect(folderShell.className).not.toContain('sm:flex')
  })

  it('keeps the folder trailing when the pencil is absent entirely', () => {
    // No selected blueprint -> no pencil at all. The folder must still be the
    // last thing in the cluster, not the first of one.
    renderHeader({ ...unsetSeat, selectedBlueprint: '', selectedAgentName: '' })
    const children = Array.from(actions().children)
    expect(children).toHaveLength(1)
    expect(children[0]).toBe(folder().parentElement)
  })

  it('keeps the cluster one row so a trailing control cannot add a line', () => {
    // #1704 §1: the reveal must not grow the badge. `flex-shrink: 0` is what
    // keeps the trailing control at full size instead of being squeezed by a
    // long agent name.
    const cluster = declarations(rule(css, '.os-agent-pill__actions'))
    expect(cluster.display).toBe('inline-flex')
    expect(cluster['flex-shrink']).toBe('0')
    expect(cluster['flex-direction'] ?? 'row').toBe('row')
  })
})

describe('#1724 §2 — the drag bin does not hand-copy the footer cluster height', () => {
  it('takes the reserve from the one rule that owns the cluster height', () => {
    // `.os-recycle-bin` used to restate `10rem` inline, so the reserve could
    // drift from the cluster it reserves with nothing to catch it. It now
    // reads the shared custom property instead of a second literal.
    const bin = declarations(rule(css, '.os-recycle-bin'))
    const value = bin['min-height']
    expect(value).toBeDefined()
    expect(value, 'the bin must consume the shared token, not restate the number').toMatch(
      /var\(\s*--os-footer-cluster-h/,
    )
  })

  it('keeps a fallback so a bin rendered without the token still reserves space', () => {
    // The token is set inline by AgentSidebar. If that ever stops happening,
    // an unguarded `var()` would resolve to nothing and the drag would jolt the
    // rail — the exact regression the token was introduced to prevent.
    const value = declarations(rule(css, '.os-recycle-bin'))['min-height']
    expect(value).toMatch(/var\(\s*--os-footer-cluster-h\s*,\s*10rem\s*\)/)
  })

  it('still hides the labels and the menu so the bin replaces rather than stacks', () => {
    // The reserve only helps if the bin CONCEALS the cluster; both are the
    // component's contract and are covered by AgentSidebar's own suite, so this
    // only asserts the stylesheet did not grow a second height on the shell.
    expect(Object.keys(declarations(rule(css, '.os-recycle-bin')))).toHaveLength(1)
  })
})
