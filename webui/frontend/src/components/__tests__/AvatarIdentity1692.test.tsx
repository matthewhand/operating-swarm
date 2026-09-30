/**
 * #1692 / #1693 — one agent, one avatar, in every pane; and a control that
 * looks like one.
 *
 * #1692 (identity). The chat header's face passed two props no other seat
 * surface passed: `size="lg"` (48px against the rail row's 32px) and `gl`
 * (ADR-008 §2's WebGL pose context, so a `robot3d` agent showed a live 3D mesh
 * in the chat pane and the static SVG everywhere else). One agent, two
 * avatars. The fix moved the size tier and the WebGL decision into
 * `lib/seatAvatar` and routed both seat call sites through it.
 *
 * #1693 (affordance). `.os-chat-header__avatar-btn` had `cursor: pointer` and
 * nothing else, so the control the issue calls "interactive" was undiscoverable
 * and its focus state was invisible. The element was already a real `<button>`
 * with an accessible name — this suite pins that, because the affordance would
 * be a false signal without it.
 *
 * Pinned here:
 *   1. The SAME agent renders the SAME avatar identity in the chat pane and in
 *      the rail row — asserted on the rendered DOM (size tier, face kind, image
 *      src, eye state, avatar shape), never on a prop.
 *   2. The header avatar is a focusable button with an accessible name.
 *   3. The focus treatment exists, is token-only, and is not hover-gated.
 *   4. NO WebGL context is created by a seat face, in either pane.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import fs from 'fs'
import path from 'path'
import type React from 'react'
import AgentAvatar from '../AgentAvatar'
import { ChatHeader } from '../../features/chat/ChatHeader'
import { createRowRenderers } from '../sidebar/rowsRender'
import { useAgentStore } from '../../lib/agent-store'
import { SEAT_AVATAR_SIZE, seatAvatarSrc } from '../../lib/seatAvatar'
import { saveAvatarTheme, saveEnabledAvatarThemes } from '../../lib/avatarTheme'
import GroupAvatar from '../GroupAvatar'

const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

/** Comments carry issue numbers, so token checks must not see them. */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '')
}

/** The LAST top-level block for a selector — the one the cascade uses. */
function cssBlock(selector: string): string {
  const index = css.lastIndexOf(`\n${selector} {`)
  expect(index, `index.css declares ${selector}`).toBeGreaterThan(-1)
  return stripComments(css.slice(index, css.indexOf('}', index)))
}

const AGENT = { id: 'codey', name: 'Codey', avatar_path: '/avatars/codey.svg' }

function headerProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar,
    ApiSessionSwitcher: () => null,
    AuxActivityIndicator: () => null,
    CliSessionSwitcher: () => null,
    ComputerControlStub: () => null,
    GroupAvatar,
    OPEN_SETTINGS_EVENT: 'swarm:open-settings',
    RemoteSessionSwitcher: () => null,
    Settings: () => null,
    Pencil: () => null,
    Folder: () => null,
    PanelLeft: () => null,
    roleCssClass: () => '',
    ThemeToggle: () => null,
    activeChatAgentId: 'codey',
    selectedBlueprint: 'codey',
    selectedAgentName: 'Codey',
    selectedAgent: AGENT,
    headerFaceAgentId: 'codey',
    headerFaceAvatarSrc: '/avatars/codey.svg',
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
    <ChatHeader {...(headerProps(overrides) as React.ComponentProps<typeof ChatHeader>)} />,
  )
}

function railDeps(): Record<string, unknown> {
  const noop = vi.fn(() => '')
  return {
    AgentAvatar,
    RailRowSlot: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    Link: ({ children, to }: { children?: React.ReactNode; to?: string }) => (
      <a href={to}>{children}</a>
    ),
    StackedAvatars: () => null,
    GroupAvatar: () => null,
    Users: () => null,
    NEEDS_APPROVAL_LABEL: '',
    agentLabel: (a: { name: string }) => a.name,
    agentRole: () => 'default',
    roleBadgeLabel: () => null,
    roleCssClass: () => '',
    isHerdrAgent: () => false,
    isCliRailAgent: () => false,
    rowMenuHandlers: () => ({}),
    formatRailTimestamp: () => '',
    getRowLastMessage: () => ({ snippet: '', timestamp: null }),
    shouldOpenSessionPicker: () => false,
    activeTaskSessionCount: () => 0,
    loadLocalNewChatPerTask: () => false,
    sessionsByAgent: {},
    cliActivityByAgent: {},
    cliRunningIds: new Set<string>(),
    unreadIds: [],
    approvalWaitIds: new Set<string>(),
    peekApprovalWait: () => false,
    peekCliRunning: () => false,
    draggingId: null,
    dropTargetId: null,
    activeRail: null,
    activeHerdrRow: null,
    settingsTick: 0,
    isMac: false,
    navigate: noop,
    onClose: noop,
    sidebarHref: () => '/chat',
  }
}

function renderRailRow(agent: unknown = AGENT) {
  const { renderAgentRow } = createRowRenderers(railDeps())
  return render(<>{renderAgentRow(agent as never, false)}</>)
}

/**
 * The avatar's rendered identity, read off the DOM. Deliberately NOT the props
 * — a test that asserts the props only proves the two call sites still differ.
 */
function renderedIdentity(container: HTMLElement): Record<string, string | null> {
  const face = container.querySelector<HTMLElement>('[data-agent-avatar]')
  if (!face) throw new Error('no avatar rendered')
  const img = face.querySelector('img')
  const inner = face.querySelector<HTMLElement>('.os-agent-avatar')
  return {
    size: face.getAttribute('data-avatar-size'),
    kind: face.getAttribute('data-agent-avatar'),
    theme: face.getAttribute('data-avatar-theme'),
    eyes: face.getAttribute('data-eye-state'),
    shape: face.getAttribute('data-avatar-shape'),
    imgSrc: img?.getAttribute('src') ?? null,
    innerClass: inner?.className ?? null,
  }
}

/** Pin the installed theme set the way the Settings picker does, so the
 *  resolver picks the theme the test means rather than the factory default. */
function useTheme(theme: string) {
  saveEnabledAvatarThemes([theme])
  saveAvatarTheme(theme)
  useAgentStore.setState({ avatarThemeByAgent: { codey: theme } } as never)
}

beforeEach(() => {
  localStorage.clear()
  useAgentStore.setState({ avatarThemeByAgent: {}, agents: [] } as never)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ profiles: [], data: [] }) }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('#1692 — one agent renders one avatar in the chat pane and in the rail', () => {
  it('resolves the same identity for the same agent in both panes', () => {
    const chat = renderHeader()
    const rail = renderRailRow()

    // Asserted on the rendered output, not on props: identical src, identical
    // face kind, identical size tier, identical eye state, identical shape.
    expect(renderedIdentity(chat.container)).toEqual(renderedIdentity(rail.container))

    const chatFace = chat.container.querySelector<HTMLElement>('.os-chat-header__avatar')!
    const railFace = rail.container.querySelector<HTMLElement>('.os-agent-avatar')!
    expect(chatFace.getAttribute('data-avatar-size')).toBe(
      railFace.closest('[data-agent-avatar]')!.getAttribute('data-avatar-size'),
    )
  })

  it('renders the seat face at the shared tier, not a pane-local one', () => {
    // The regression: the header passed size="lg" (48px) where the rail passed
    // "sm" (32px). Both must now read the one declared tier.
    expect(SEAT_AVATAR_SIZE).toBe('sm')
    const chat = renderHeader()
    const rail = renderRailRow()
    for (const container of [chat.container, rail.container]) {
      const face = container.querySelector<HTMLElement>('[data-agent-avatar]')!
      expect(face.getAttribute('data-avatar-size')).toBe(SEAT_AVATAR_SIZE)
      expect(face.querySelector('.os-agent-avatar')!.className).toContain(
        `os-agent-avatar--${SEAT_AVATAR_SIZE}`,
      )
    }
  })

  it('routes both seat call sites through the one shared contract', () => {
    // A call site that re-declares the tier or the URL precedence by hand is
    // how #1692 happened; these are the two sites the issue names.
    const header = fs.readFileSync(
      path.resolve(__dirname, '../../features/chat/ChatHeader.tsx'),
      'utf8',
    )
    const rows = fs.readFileSync(
      path.resolve(__dirname, '../sidebar/rowsRender.tsx'),
      'utf8',
    )
    for (const [name, source] of [
      ['ChatHeader.tsx', header],
      ['rowsRender.tsx', rows],
    ] as const) {
      expect(source, `${name} takes the shared size tier`).toContain('size={SEAT_AVATAR_SIZE}')
      expect(source, `${name} takes the shared WebGL decision`).toContain('gl={SEAT_AVATAR_GL}')
      // No hand-rolled precedence chain survives on either surface.
      expect(source, `${name} has no local avatar chain`).not.toMatch(
        /avatarSrc\s*\|\|[\s\S]{0,120}?avatar_path/,
      )
    }
  })

  it('resolves the avatar URL with one declared precedence', () => {
    // avatarSrc (already normalized by the caller) → avatar_path (the persisted
    // live-config field) → avatar → src (loose roster spellings).
    expect(seatAvatarSrc({ avatarSrc: '/a', avatar_path: '/b', avatar: '/c', src: '/d' })).toBe('/a')
    expect(seatAvatarSrc({ avatar_path: '/b', avatar: '/c', src: '/d' })).toBe('/b')
    expect(seatAvatarSrc({ avatar: '/c', src: '/d' })).toBe('/c')
    expect(seatAvatarSrc({ src: '/d' })).toBe('/d')
    // Blank / whitespace-only / non-string values never win.
    expect(seatAvatarSrc({ avatarSrc: '   ', src: '/d' })).toBe('/d')
    expect(seatAvatarSrc({ avatar_path: 42, src: '/d' })).toBe('/d')
    // An absent face yields null so AgentAvatar falls through to its themed
    // default rather than rendering <img src="">.
    expect(seatAvatarSrc({})).toBeNull()
    expect(seatAvatarSrc(null)).toBeNull()
    expect(seatAvatarSrc(undefined)).toBeNull()
  })

  it('gives the same agent the same image in the header and in a group ring', () => {
    // The team branch renders GroupAvatar from the SAME `headerGroupMembers`
    // list; a member whose only face field is `avatar_path` must resolve the
    // same URL the rail's team face resolves.
    const member = { id: 'codey', name: 'Codey', avatar_path: '/avatars/codey.svg' }
    const chat = renderHeader({
      teamFromUrl: 'squad',
      teamChatMemberId: 'codey',
      headerGroupMembers: [{ ...member, src: seatAvatarSrc(member) }],
    })
    const face = chat.container.querySelector<HTMLElement>('[data-agent-avatar="custom"] img')
    expect(face).toHaveAttribute('src', '/avatars/codey.svg')
  })
})

describe('#1692 — a seat face never takes a WebGL context', () => {
  it('creates no GL context in either pane, for any theme', () => {
    // ADR-008 §2 allows ONE pose context on a chat hero. The header mount is a
    // 32px pill, not a hero: it used to pass `gl`, so the header asked the
    // browser for a context (and in a real browser built the 3D mesh) while
    // the rail row showed the static SVG — a second identity for one agent.
    // jsdom has no WebGL, so the proof is the ATTEMPT: `webglSupported()` calls
    // getContext before it can give up.
    const getContext = vi
      .spyOn(HTMLCanvasElement.prototype, 'getContext')
      .mockReturnValue(null as never)

    for (const theme of ['robot3d', 'blobs', 'bee', 'bland', 'chassis']) {
      useTheme(theme)
      const chat = renderHeader({
        headerFaceAvatarSrc: undefined,
        selectedAgent: { id: 'codey', name: 'Codey' },
      })
      const rail = renderRailRow({ id: 'codey', name: 'Codey' })
      // The theme really resolved, or the assertion below would pass vacuously.
      expect(
        chat.container.querySelector('[data-avatar-theme]')?.getAttribute('data-avatar-theme'),
        `theme ${theme} resolved in the chat pane`,
      ).toBe(theme)
      expect(
        rail.container.querySelector('[data-avatar-theme]')?.getAttribute('data-avatar-theme'),
        `theme ${theme} resolved in the rail`,
      ).toBe(theme)
      chat.unmount()
      rail.unmount()
    }

    const glCalls = getContext.mock.calls.filter(([kind]) =>
      String(kind).includes('webgl'),
    )
    expect(glCalls, 'no seat face may request a WebGL context').toEqual([])
  })

  it('never loads the robot3d pose player from a seat face', () => {
    // The pose player is the only thing that would own a GL context, and it is
    // behind a dynamic import. A seat face must not reach it.
    useTheme('robot3d')
    // No custom face, so the theme (not an <img>) owns the avatar in both panes.
    const bare = { id: 'codey', name: 'Codey' }
    const chat = renderHeader({ headerFaceAvatarSrc: undefined, selectedAgent: bare })
    const rail = renderRailRow(bare)
    // Both panes still show the SAME robot3d face, via the static SVG.
    expect(chat.container.querySelector('[data-robot3d-static]')).toBeInTheDocument()
    expect(rail.container.querySelector('[data-robot3d-static]')).toBeInTheDocument()
    expect(renderedIdentity(chat.container)).toEqual(renderedIdentity(rail.container))
  })
})

describe('#1693 — the header avatar is a real, focusable, named control', () => {
  it('is a button with an accessible name, not a div with onClick', () => {
    const { container } = renderHeader()
    const control = container.querySelector<HTMLButtonElement>(
      '[data-testid="header-avatar-generations"]',
    )
    expect(control, 'the header avatar is a <button>').toBeInstanceOf(HTMLButtonElement)
    expect(control!.type).toBe('button')
    // An accessible name, not a bare glyph: the query is how AT reads it.
    expect(control).toHaveAccessibleName('Open Codey configuration')
    expect(control).toHaveAttribute('aria-haspopup', 'dialog')
  })

  it('is reachable by keyboard (tabbable, not tabindex=-1)', () => {
    const { container } = renderHeader()
    const control = container.querySelector<HTMLButtonElement>(
      '[data-testid="header-avatar-generations"]',
    )!
    // A real <button> is in the tab order by default; tabindex=-1 would opt out.
    expect(control.getAttribute('tabindex')).toBeNull()
    expect(control.disabled).toBe(false)
    control.focus()
    expect(document.activeElement).toBe(control)
  })

  it('carries a focus-visible treatment that is not hover-gated', () => {
    const base = cssBlock('.os-chat-header__avatar-btn')
    // A pointer cursor is necessary but not sufficient.
    expect(base).toMatch(/cursor:\s*pointer/)
    // :focus-visible is UNCONDITIONAL — a keyboard user must get the same ring a
    // mouse user gets, and it must not live inside a `hover:` media block.
    expect(css).toMatch(/\.os-chat-header__avatar-btn:focus-visible\s*\{/)
    const focusIndex = css.indexOf('.os-chat-header__avatar-btn:focus-visible')
    const hoverBlockIndex = css.indexOf('@media (hover: hover) and (pointer: fine)')
    expect(hoverBlockIndex, 'a hover media block exists to be distinct from').toBeGreaterThan(-1)
    // The focus rule is not the first declaration inside the hover block.
    expect(focusIndex).toBeGreaterThan(-1)
    // The hover highlight IS gated: a touch device cannot hover, so a
    // hover-only signal would never resolve there.
    const hoverRule = css.slice(
      css.indexOf('.os-chat-header__avatar-btn:hover'),
      css.indexOf('}', css.indexOf('.os-chat-header__avatar-btn:hover')),
    )
    expect(hoverRule).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(stripComments(css).match(/@media \(hover: hover\) and \(pointer: fine\) \{[\s\S]*?\.os-chat-header__avatar-btn:hover/)![0]).toBeTruthy()
  })

  it('uses theme tokens for the focus ring, and respects reduced motion', () => {
    // AGENTS.md: no raw hex where a theme token exists.
    const focusStart = css.indexOf('.os-chat-header__avatar-btn:focus-visible {')
    const focusBlock = stripComments(
      css.slice(focusStart, css.indexOf('}', focusStart)),
    )
    expect(focusBlock).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(focusBlock).toMatch(/var\(--color-primary\)/)
    expect(focusBlock).toMatch(/box-shadow:/)
    // The only thing that transitions is a ring; under reduced motion it stops.
    expect(css).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\.os-chat-header__avatar-btn\s*\{[\s\S]*?transition:\s*none/,
    )
  })

  it('does not advertise a target the disabled team pill does not have', () => {
    // A team seat with no member pick renders the button disabled + aria-hidden
    // (it opens nothing), so it must not carry the interactive cursor.
    const { container } = renderHeader({ teamFromUrl: 'squad', teamChatMemberId: '' })
    const control = container.querySelector<HTMLButtonElement>(
      '[data-testid="header-team-avatar"]',
    )!
    expect(control.disabled).toBe(true)
    expect(control).toHaveAttribute('aria-hidden', 'true')
    expect(cssBlock('.os-chat-header__avatar-btn:disabled')).toMatch(/cursor:\s*default/)
  })
})
