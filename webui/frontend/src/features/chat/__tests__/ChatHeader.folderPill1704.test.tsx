/**
 * #1704 — the pill's folder affordance, as a control.
 *
 * `ChatHeader.pillLabels1706.test.tsx` already pins that the unset-folder
 * affordance is a SIBLING of the stacked label column and paints no visible
 * text. This file pins the properties that are easy to lose in a refactor and
 * silent when they are:
 *
 *   - the cluster is icon-only chrome, so ANY text node rendered directly in it
 *     is a bug (this is the "one stray string in the pill" shape, and a comment
 *     or a word dropped between the braces lands in exactly this place);
 *   - the folder control is never display-gated. The pencil carries
 *     `hidden sm:flex`, so it disappears below 640px; copying that onto the
 *     folder button would take the affordance away from exactly the narrow,
 *     touch-sized viewport that needs it, and the CSS reveal is already
 *     pointer-gated, so opacity — not `display` — is the only thing hover may
 *     move;
 *   - the muted `--unset` colour class survives, because that rule is where the
 *     icon gets its "quiet until hovered" ink;
 *   - the pill no longer advertises a Tailwind `group` context, since the text
 *     row that used it is gone.
 *
 * The height claim itself is a geometry claim and jsdom computes no geometry:
 * `webui/frontend/scripts/measure-folder-pill-1704.mjs` measures it in a real
 * renderer. These tests pin the causes.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type React from 'react'
import { ChatHeader } from '../ChatHeader'
import { declaration, readCssSource } from '../../../lib/__tests__/helpers/cssRules'

const css = readCssSource()

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
    showEmptyRemoteChromeOnly: false,
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

function renderUnsetFolder(overrides: Record<string, unknown> = {}) {
  return render(
    <ChatHeader
      {...(baseProps({
        workspaceSubtitle: '',
        workspaceFolderEditable: true,
        ...overrides,
      }) as React.ComponentProps<typeof ChatHeader>)}
    />,
  )
}

function pill(): HTMLElement {
  return screen.getByTestId('selected-agent-header')
}

/** The pill's right-aligned action cluster; a class hook, so no role query. */
// eslint-disable-next-line testing-library/no-node-access -- .os-agent-pill__actions is a class hook
function actions(): HTMLElement {
  return pill().querySelector('.os-agent-pill__actions') as HTMLElement
}

function folderButton(): HTMLElement {
  return screen.getByTestId('os-navbar-workspace-subtitle-unset')
}

/**
 * Text nodes the browser would PAINT, i.e. not clipped away by `.sr-only`.
 *
 * `textContent` cannot answer this on its own — it includes the `sr-only` name,
 * so a control that is correctly named and correctly invisible looks identical to
 * one that paints a word. There is no Testing Library query for "visible text
 * nodes", because the answer is a property of the RENDER, and the render is the
 * thing under test.
 */
// eslint-disable-next-line testing-library/no-node-access -- a TreeWalker over the rendered text is the assertion
function visibleTextWithin(root: HTMLElement): string[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const out: string[] = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = (node.textContent || '').trim()
    if (!text) continue
    // eslint-disable-next-line testing-library/no-node-access -- .sr-only is a class hook, not a role
    if (node.parentElement?.closest('.sr-only')) continue
    out.push(text)
  }
  return out
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

describe('#1704 — the action cluster is icon-only chrome', () => {
  it('renders no text of its own anywhere in the cluster', () => {
    renderUnsetFolder()
    // The cluster holds the folder icon and the pencil. A comment, a word, or a
    // stray string between the JSX braces lands HERE, inside a flex row that
    // nobody eyeballs, and paints in the middle of the badge. Assert on the
    // rendered tree, not on the source: the way this shipped once was a commit
    // message pasted into the markup.
    expect(visibleTextWithin(actions())).toEqual([])
  })

  it('keeps the folder control named without painting the name', () => {
    renderUnsetFolder()
    const button = folderButton()
    // The name lives in an sr-only span, so it reaches assistive tech and not
    // the badge's line box.
    expect(visibleTextWithin(button)).toEqual([])
    // eslint-disable-next-line testing-library/no-node-access -- .sr-only is a class hook, not a role
    expect(button.querySelector('.sr-only')?.textContent).toBe('Select folder')
    expect(button).toHaveAccessibleName('Select folder')
    // …and it says the same thing the tooltip says, so the two affordances
    // cannot drift into calling one control two names. `data-tip` is the tooltip
    // contract daisyUI reads; it has no accessible role to query by.
    //
    // Read it off the FOLDER'S OWN shell, not off "the cluster's first
    // `[data-tip]`": since #1724 the pencil's shell comes first, so a
    // positional query here would silently start asserting the pencil's label.
    // eslint-disable-next-line testing-library/no-node-access -- parentElement IS the tooltip shell
    const folderShell = button.parentElement as HTMLElement
    expect(folderShell.getAttribute('data-tip')).toBe('Select folder')
    expect(button).toHaveAttribute('title', 'Select a working folder')
  })

  it('keeps both controls as direct children of the one row, folder trailing', () => {
    renderUnsetFolder()
    // eslint-disable-next-line testing-library/no-node-access -- the cluster is chrome with no role
    const controls = [...actions().querySelectorAll('.os-navbar-edit-btn')]
    expect(controls).toHaveLength(2)
    // Siblings, not nested: a nested one would be a box inside a box, and the
    // cluster's single row would stop being a single row.
    for (const control of controls) {
      // eslint-disable-next-line testing-library/no-node-access -- parentElement IS the containment claim
      expect(control.parentElement?.parentElement).toBe(actions())
    }
    // ORDER, and this supersedes #1704's "folder-then-pencil". The old
    // ordering is what #1724 §3 fixed: only the pencil's shell carries
    // `hidden sm:flex`, so with the folder first the pencil took the trailing
    // slot at >=640px and left the folder 34px inboard, while below 640px the
    // hidden pencil vacated it and the folder became trailing — the same
    // control sitting on a different edge at two widths. #1704's actual
    // requirement ("right-aligned", stated in its own title) is satisfied by
    // folder-LAST: it is trailing at every width, and DOM order keeps focus
    // order and screen-reader order agreeing with the pixels, which a CSS
    // `order` would not.
    expect(controls[controls.length - 1]).toBe(folderButton())
    expect(controls[0]).toHaveAttribute('aria-label', 'Edit agent')
    // …asserted on the shells, because the ORDER is a property of the row and
    // the controls are wrapped in one each.
    // eslint-disable-next-line testing-library/no-node-access -- the shells are what the row orders
    const shells = [...actions().children]
    expect(shells[shells.length - 1]).toBe(folderButton().parentElement)
  })
})

describe('#1704 — the folder affordance is never display-gated', () => {
  it('carries no `hidden` / responsive display utility the pencil carries', () => {
    renderUnsetFolder()
    // The pencil wrapper is `hidden sm:flex`; the folder wrapper must not be.
    // Below 640px the pencil disappears, and a copied `hidden sm:flex` would
    // take the only folder affordance with it — on the narrow viewport where a
    // touch user has no hover to reveal it with.
    // eslint-disable-next-line testing-library/no-node-access -- the display gate lives on the WRAPPER
    const folderWrapper = folderButton().parentElement as HTMLElement
    // eslint-disable-next-line testing-library/no-node-access -- [data-tip] is a tooltip hook, not a role
    const pencilWrapper = actions().querySelector('[data-tip="Edit agent"]') as HTMLElement
    expect(pencilWrapper).toHaveClass('hidden', 'sm:flex')
    expect(folderWrapper.className).not.toContain('hidden')
    expect(folderWrapper.className).not.toContain('sm:flex')
  })

  it('reveals by opacity, which is what the pointer-gated CSS already governs', () => {
    renderUnsetFolder()
    // `.os-navbar-edit-btn` is opacity 1 at rest and 0 only inside
    // `@media (hover: hover) and (pointer: fine)`. `display: none` would defeat
    // that contract silently, because the media query is about hover, not about
    // width.
    expect(declaration(css, '.os-navbar-edit-btn', 'opacity')).toBe('1')
    // The muted colour class must still declare a colour, or the icon has no
    // ink of its own to inherit.
    expect(declaration(css, '.os-navbar-identity-subtitle--unset', 'color')).toBeTruthy()
    // The icon keeps that class, so it inherits the quiet ink instead of
    // dropping to a full-strength ghost button.
    expect(folderButton()).toHaveClass('os-navbar-identity-subtitle--unset')
  })
})

describe('#1704 — the pill no longer claims a Tailwind group context', () => {
  it('drops `group` from the pill, and nothing inside it uses a group variant', () => {
    renderUnsetFolder()
    expect(pill().className).not.toContain('group')
    // The text row was the pill's only `group-hover:` consumer. A `group`
    // marker nobody uses is a promise the next reader trusts: they add a
    // `group-hover:` and it silently does nothing, or worse, hovers an
    // unrelated ancestor. Assert the whole subtree is clean.
    // eslint-disable-next-line testing-library/no-node-access -- the whole subtree is the assertion
    const walker = document.createTreeWalker(pill(), NodeFilter.SHOW_ELEMENT)
    const offenders: string[] = []
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const { className, tagName } = node as Element
      if (typeof className === 'string' && /(?:^|\s)group-(?:hover|focus-within|focus|active)/.test(className)) {
        offenders.push(`${tagName}.${className.trim()}`)
      }
    }
    expect(offenders).toEqual([])
  })
})
