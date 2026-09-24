/**
 * #1119 — the remote themed face is a self-sizing box, not a 100%-of-nothing.
 *
 * `.os-remote-face` declared `width/height: 100%` but nothing sized the
 * AgentAvatar root, so the inner glyph SVG fell back to its intrinsic ~150px
 * default — the "comically large" AnythingLLM face. The bland path never had
 * this problem because `os-bland-avatar--{size}` declares the box. The face
 * now mirrors those exact metrics per size, with `flex: 0 0 auto` so flex
 * parents can't stretch it, and pinned remote tiles get the themed face too.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import AgentAvatar from '../AgentAvatar'
import { RailSections } from '../sidebar/RailSections'

function readCss(): string {
  return fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
}

function blockFor(css: string, selector: string): string {
  const start = css.indexOf(selector)
  expect(start, `${selector} exists in index.css`).toBeGreaterThanOrEqual(0)
  const open = css.indexOf('{', start)
  const close = css.indexOf('}', open)
  return css.slice(open + 1, close)
}

describe('#1119 face sizing contract (css)', () => {
  it('os-remote-face declares its own box: flex 0 0 auto + per-size metrics', () => {
    const css = readCss()
    const base = blockFor(css, '.os-remote-face {')
    // Without flex-basis protection a stretchy flex parent inflates the face.
    expect(base).toContain('flex: 0 0 auto')
    // Same declared metrics as os-bland-avatar--{size} — one sizing truth.
    const sizes: Array<[string, string]> = [
      ['xs', '1.5rem'],
      ['sm', '2.15rem'],
      ['md', '2.35rem'],
      ['lg', '2.75rem'],
      ['xl', '3.5rem'],
    ]
    for (const [size, rem] of sizes) {
      const block = blockFor(css, `.os-remote-face--${size} {`)
      expect(block).toContain(`width: ${rem}`)
      expect(block).toContain(`height: ${rem}`)
    }
  })
})

describe('#1119 face sizing contract (dom)', () => {
  it('renders the size modifier class so the declared box applies', () => {
    const { container } = render(
      <AgentAvatar agentId="agenty-1" alt="Agenty" size="sm" remoteKind="anythingllm" />,
    )
    const face = container.querySelector('.os-remote-face')
    expect(face).not.toBeNull()
    expect(face).toHaveClass('os-remote-face--sm')
  })

  it('AnythingLLM renders its themed face mark (documents + spark), not the default bust', () => {
    const { container } = render(
      <AgentAvatar agentId="agenty-1" alt="Agenty" size="sm" remoteKind="AnythingLLM" />,
    )
    const root = container.querySelector('[data-agent-avatar="remote-themed"]')
    expect(root).not.toBeNull()
    expect(root).toHaveAttribute('data-remote-face', 'AnythingLLM')
    // An inline SVG glyph inside a declared box — never the raw ~150px default.
    expect(container.querySelector('.os-remote-face__glyph')).not.toBeNull()
  })

  it('header size (lg) gets the same self-sizing treatment', () => {
    const { container } = render(
      <AgentAvatar agentId="agenty-1" alt="Agenty" size="lg" remoteKind="anythingllm" />,
    )
    expect(container.querySelector('.os-remote-face')).toHaveClass('os-remote-face--lg')
  })
})

describe('#1119 pinned remote tiles get the themed face', () => {
  const remotes = [
    { id: 'agenty-1', title: 'Agenty', kind: 'anythingllm' },
  ]

  function pinProps(): Record<string, unknown> {
    return {
      AgentAvatar,
      Link: ({ children, ...rest }: { children?: React.ReactNode; [key: string]: unknown }) => (
        <a {...rest}>{children}</a>
      ),
      RailSectionHeader: ({ name }: { name: string }) => (
        <div data-testid="section-header">{name}</div>
      ),
      RailSectionEmpty: () => null,
      agents: [],
      teams: [],
      remotes,
      visiblePins: [{ id: 'remote:agenty-1', name: 'Agenty' }],
      sectionBlocks: [],
      orderedRows: [],
      hiddenCount: 0,
      loadingList: false,
      loadFailed: false,
      visibleCount: 0,
      draggingId: null,
      dropActive: false,
      listDropActive: false,
      sectionDropId: null,
      editingSectionId: null,
      editingSectionName: '',
      activeRail: null,
      unreadIds: [],
      approvalWaitIds: new Set<string>(),
      cliRunningIds: new Set<string>(),
      resolvedHiddenIds: [],
      isAvatarOnly: () => false,
      isPinnedId: () => true,
      isUnassignedSection: () => false,
      isHerdrAgent: () => false,
      agentLabel: (agent: { name?: string }) => agent?.name || 'agent',
      agentRole: () => 'default',
      roleBadgeLabel: () => '',
      roleCssClass: () => '',
      markStackWorking: (faces: unknown[]) => ({ faces, anyWorking: false }),
      stackFacesForTeam: () => [],
      teamSidepaneStack: (faces: unknown[]) => ({ faces }),
      teamChatFaceStack: () => ({ face: null }),
      defaultSessionForTeam: () => null,
      peekApprovalWait: () => false,
      peekCliRunning: () => false,
      resolveMenuKind: () => 'remote',
      rowMenuHandlers: () => ({}),
      beginRowDrag: vi.fn(),
      finishDrag: vi.fn(),
      allowRowDrop: vi.fn(),
      dropPinReorder: vi.fn(),
      dropPin: vi.fn(),
      setDropActive: vi.fn(),
      navigate: vi.fn(),
      agentChatHref: (id: string) => `/chat?agent=${id}`,
      openDefinition: vi.fn(),
      pickOrClose: vi.fn(),
      navScrollRef: { current: null },
      updateCanScroll: vi.fn(),
      openPaneMenuAt: vi.fn(),
      openSectionMenuAt: vi.fn(),
      setSectionState: vi.fn(),
      setEditingSectionName: vi.fn(),
      cancelSectionRename: vi.fn(),
      commitSectionRename: vi.fn(),
      toggleSectionCollapsed: vi.fn(),
      toggleSectionInternalOnly: vi.fn(),
      setSubagentsCollapsed: vi.fn(),
      setListDropActive: vi.fn(),
      allowSectionDrop: vi.fn(),
      dropOnSection: vi.fn(),
      allowListUnfavourite: vi.fn(),
      dropUnfavourite: vi.fn(),
      remoteHideId: (id: string) => `remote:${id}`,
    }
  }

  it('a pinned remote seat renders its platform face, not the generic Users mark', () => {
    render(<RailSections {...(pinProps() as any)} />)
    const root = screen
      .getByTestId('agent-fav-grid')
      .querySelector('[data-remote-face="AnythingLLM"]')
    expect(root).not.toBeNull()
    expect(root!.querySelector('.os-remote-face')).toHaveClass('os-remote-face--lg')
  })
})
