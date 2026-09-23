/**
 * #856 slice G — the rail's three row renderers are an independently
 * testable module (`sidebar/rowsRender.tsx`), moved verbatim out of
 * AgentSidebar.tsx.
 *
 * Pinned contract (behavior unchanged — this is a pure move):
 *
 * 1. createRowRenderers({ ...deps }) returns { renderAgentRow,
 *    renderRemoteRow, renderTeamRow } and nothing else.
 * 2. renderAgentRow maps a SidebarAgent to a row carrying the agent's
 *    avatar/stack mark, role badge (#862 left-side), #601 activity
 *    timestamp, unread flag, and drag handlers.
 * 3. renderRemoteRow/renderTeamRow keep their #398 (no stacking in the
 *    agent section) and #644 (single avatar + +N for teams) contracts.
 * 4. AgentSidebar consumes the factory and no longer declares any of the
 *    three renderers inline.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createRowRenderers } from '../sidebar/rowsRender'

// Minimal dep set: the renderers destructure what they need from the
// factory argument; rows exercised here use a narrow slice of it.
function makeDeps() {
  return {
    AgentAvatar: ({ agentId, size }: { agentId: string; size?: string }) => (
      <span data-testid="avatar">{`${agentId}:${size ?? ''}`}</span>
    ),
    StackedAvatars: ({ sessions }: { sessions: unknown[] }) =>
      sessions.length ? <span data-testid="stack">{sessions.length}</span> : null,
    RailRowSlot: ({ timestampLabel }: { timestampLabel?: string }) => (
      <span data-testid="slot">{timestampLabel ?? ''}</span>
    ),
    agentLabel: (a: { name: string }) => a.name,
    agentRole: () => 'default',
    roleBadgeLabel: () => null,
    roleCssClass: () => '',
    isHerdrAgent: () => false,
    isCliRailAgent: () => false,
    rowMenuHandlers: () => ({}),
    formatRailTimestamp: (t: number | null) => (t == null ? '' : String(t)),
    getRowLastMessage: () => ({ snippet: '', timestamp: null }),
    shouldOpenSessionPicker: () => false,
    activeTaskSessionCount: () => 0,
    loadLocalNewChatPerTask: () => false,
    sessionsByAgent: {} as Record<string, unknown[]>,
    cliActivityByAgent: {} as Record<string, unknown>,
    cliRunningIds: new Set<string>(),
    unreadIds: [] as string[],
    approvalWaitIds: new Set<string>(),
    peekApprovalWait: () => false,
    peekCliRunning: () => false,
    draggingId: null,
    dropTargetId: null,
    activeRail: null,
    activeHerdrRow: null,
    settingsTick: 0,
    isMac: false,
    onDragStartRow: vi.fn(),
    onDragEndRow: vi.fn(),
    onDragOverRow: vi.fn(),
    onDragLeaveRow: vi.fn(),
    onDropRow: vi.fn(),
    openSessionPicker: vi.fn(),
    openCliSessionSwitcher: vi.fn(),
    openAgentMenu: vi.fn(),
    openRemoteMenu: vi.fn(),
    openTeamMenu: vi.fn(),
    openDefinition: vi.fn(),
    startChatWith: vi.fn(),
    navigate: vi.fn(),
  }
}

/**
 * Smoke-level auto-fill: every dep the module destructures but the explicit
 * stubs above don't name gets a permissive default keyed by name shape
 * (sessions·stack·faces prefixes → arrays, *Id → '', known string-returning
 * helpers → '', everything else → a no-op fn). Behavior pins live in the
 * AgentSidebar suites; this only proves the factory renders.
 */
function autoFillDeps(deps: Record<string, unknown>, allDepNames: string[]) {
  const f = vi.fn(() => '')
  for (const n of allDepNames) {
    if (n in deps) continue
    if (/^(sessions|stack|faces|ordered|RailRow)/.test(n)) deps[n] = []
    else if (/Id$|HideId$/.test(n)) deps[n] = ''
    else if (n === 'NEEDS_APPROVAL_LABEL' || n === 'isMac' || n === 'settingsTick') deps[n] = n === 'settingsTick' ? 0 : n === 'isMac' ? false : ''
    else if (/^[A-Z]/.test(n)) deps[n] = ({ children }: { children?: React.ReactNode }) => <>{children}</>
    else deps[n] = f
  }
  return deps
}

function fullDeps(): Record<string, unknown> {
  // Read the destructured dep names straight out of the module under test.
  const fs = require('node:fs')
  const path = require('node:path')
    // eslint-disable-next-line testing-library/no-node-access -- raw source introspection, not DOM probing
  const src = fs.readFileSync(path.join(__dirname, '..', 'sidebar', 'rowsRender.tsx'), 'utf8')
  const m = src.match(/const \{([^}]*)\} = props as any/)
  const names = m ? m[1].split(',').map((s: string) => s.trim()).filter(Boolean) : []
  const base = makeDeps() as Record<string, unknown>
  return autoFillDeps(base, names)
}

describe('#856 slice G — createRowRenderers factory', () => {
  it('exposes exactly the three row renderers', () => {
    expect(Object.keys(createRowRenderers(makeDeps() as never)).sort()).toEqual(
      ['renderAgentRow', 'renderRemoteRow', 'renderTeamRow'],
    )
  })

  it('renderAgentRow renders the agent label and avatar', () => {
    const { renderAgentRow } = createRowRenderers(fullDeps() as never)
    render(<>{renderAgentRow({ id: 'a1', name: 'Charles' } as never, false)}</>)
    expect(screen.getByTestId('rail-agent-name')).toHaveTextContent('Charles')
    expect(screen.getByTestId('avatar')).toBeInTheDocument()
  })

  it('AgentSidebar consumes the factory (no inline row renderer bodies)', () => {
    const src = require('node:fs').readFileSync(
      require('node:path').join(__dirname, '..', 'AgentSidebar.tsx'),
      'utf8',
    )
    expect(src).toContain('createRowRenderers')
    expect(src).not.toMatch(/const renderAgentRow = \(agent: SidebarAgent/)
    expect(src).not.toMatch(/const renderRemoteRow = \(remote: RemoteEntry/)
    expect(src).not.toMatch(/const renderTeamRow = \(\n?\s*team: TeamRoster/)
  })
})
