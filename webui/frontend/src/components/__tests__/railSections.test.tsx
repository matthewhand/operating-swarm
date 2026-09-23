/**
 * #856 slice I — the rail's pinned grid + section list are an independently
 * testable module (`sidebar/RailSections.tsx`), moved verbatim out of
 * AgentSidebar.tsx.
 *
 * Pinned contract (pure move — behavior unchanged):
 *
 * 1. RailSections renders the pinned-agents grid (`agent-fav-grid`) and the
 *    section list (`agent-list-drop` → `os-rail-sections`).
 * 2. An emptied Unassigned section renders nothing while idle (#688) — no
 *    permanent empty block.
 * 3. Section blocks carry their collapsed/custom/internal-only state as
 *    data-attributes for the tests and hotkey logic that key off them.
 * 4. AgentSidebar consumes the module and no longer declares the fav-grid /
 *    section JSX inline.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type React from 'react'
import { RailSections } from '../sidebar/RailSections'

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: ({ agentId }: { agentId: string }) => <span data-testid="avatar">{agentId}</span>,
    RailSectionHeader: ({ name }: { name: string }) => <div data-testid="section-header">{name}</div>,
    RailSectionEmpty: () => null,
    Link: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    visiblePins: [],
    sectionBlocks: [
      {
        id: 'unassigned',
        name: 'Unassigned',
        rows: [],
        collapsed: false,
        custom: false,
        internalOnly: false,
      },
      {
        id: 'team-alpha',
        name: 'Alpha',
        rows: [{ id: 'r1', agent: { id: 'a1', name: 'Charles' } }],
        collapsed: false,
        custom: true,
        internalOnly: false,
      },
    ],
    draggingId: null,
    dropActive: false,
    listDropActive: false,
    sectionDropId: null,
    hiddenCount: 0,
    isAvatarOnly: false,
    isPinnedId: () => false,
    isUnassignedSection: (id: string) => id === 'unassigned',
    editingSectionId: null,
    editingSectionName: '',
    loadingList: false,
    loadFailed: false,
    visibleCount: 2,
    allowSectionDrop: vi.fn(),
    dropOnSection: vi.fn(),
    setDropActive: vi.fn(),
    setListDropActive: vi.fn(),
    allowListUnfavourite: vi.fn(),
    dropUnfavourite: vi.fn(),
    openPaneMenuAt: vi.fn(),
    openSectionMenuAt: vi.fn(),
    setSubagentsCollapsed: vi.fn(),
    setSectionState: vi.fn(),
    toggleSectionCollapsed: vi.fn(),
    toggleSectionInternalOnly: vi.fn(),
    startSectionRename: vi.fn(),
    cancelSectionRename: vi.fn(),
    navScrollRef: { current: null },
    updateCanScroll: vi.fn(),
    canScroll: false,
    orderedRows: [
      { id: 'r1', agent: { id: 'a1', name: 'Charles' } },
    ],
    renderAgentRow: (agent: { id: string; name: string }) => (
      <li key={agent.id} data-testid="agent-row">{agent.name}</li>
    ),
    renderRemoteRow: () => null,
    renderTeamRow: () => null,
    spillSlot: undefined,
    ...overrides,
  }
}

describe('#856 slice I — RailSections', () => {
  it('renders the pinned grid and the section list', () => {
    render(<RailSections {...baseProps() as React.ComponentProps<typeof RailSections>} />)
    expect(screen.getByTestId('agent-fav-grid')).toBeTruthy()
    expect(screen.getByTestId('agent-list-drop')).toBeTruthy()
    // sectionBlocks has 2 entries, but the emptied Unassigned block hides
    // while idle (#688) — exactly one <li data-testid=rail-section> renders.
    expect(screen.getAllByTestId('rail-section').length).toBe(1)
  })

  it('an emptied Unassigned section renders nothing while idle (#688)', () => {
    render(<RailSections {...baseProps() as React.ComponentProps<typeof RailSections>} />)
    const sections = screen.getAllByTestId('rail-section')
    expect(sections.some((s) => s.getAttribute('data-section-id') === 'unassigned')).toBe(false)
  })

  it('section blocks carry collapsed/custom/internal-only data-attributes', () => {
    render(<RailSections {...baseProps() as React.ComponentProps<typeof RailSections>} />)
    const alpha = screen
      .getAllByTestId('rail-section')
      .find((s) => s.getAttribute('data-section-id') === 'team-alpha')
    expect(alpha?.getAttribute('data-section-custom')).toBe('true')
    expect(alpha?.getAttribute('data-collapsed')).toBe('false')
  })

  it('rows render through the passed-in row renderers', () => {
    render(<RailSections {...baseProps() as React.ComponentProps<typeof RailSections>} />)
    expect(screen.getByTestId('agent-row')).toHaveTextContent('Charles')
  })

  it('AgentSidebar consumes the module (no inline section JSX)', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    // eslint-disable-next-line testing-library/no-node-access -- raw source introspection, not DOM probing
    const src = fs.readFileSync(
      path.join(__dirname, '..', '..', 'components', 'AgentSidebar.tsx'),
      'utf8',
    )
    expect(src).toContain('RailSections {...railSectionsProps}')
    expect(src).not.toContain('os-fav-grid')
  })
})
