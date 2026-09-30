/**
 * #1247 — directional scroll chevron indicators in ultra-compact mode.
 *
 * The avatar-only column conceals its native scrollbar; the 2rem bottom fade
 * (#99) is not enough to say "more agents this way". Two faint double-arrow
 * buttons bookend the column: `rail-scroll-chevron-up` when the list can
 * scroll up and `rail-scroll-chevron-down` when it can scroll down. Clicking
 * one scrolls the nav by one avatar tile.
 *
 * #1250 — subtle section capsule borders in ultra-compact mode.
 *
 * With the section headers hidden, the remaining avatar groups blend together.
 * Sections that carry rows are wrapped in the same subtle dashed capsule as
 * the pinned grid and expose their name via `title`/`aria-label`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type React from 'react'
import AgentSidebar from '../AgentSidebar'
import { RailSections } from '../sidebar/RailSections'
import { ToastProvider } from '../DaisyUI'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

/* ───────────────────────── #1247 (module-level) ───────────────────────── */

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    AgentAvatar: ({ agentId }: { agentId: string }) => <span data-testid="avatar">{agentId}</span>,
    RailSectionHeader: () => null,
    RailSectionEmpty: () => null,
    Link: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    visiblePins: [],
    sectionBlocks: [],
    draggingId: null,
    dropActive: false,
    listDropActive: false,
    sectionDropId: null,
    isAvatarOnly: true,
    isPinnedId: () => false,
    isUnassignedSection: (id: string) => id === 'unassigned',
    editingSectionId: null,
    editingSectionName: '',
    loadingList: false,
    loadFailed: false,
    visibleCount: 0,
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
    cancelSectionRename: vi.fn(),
    commitSectionRename: vi.fn(),
    cliRunningIds: new Set(),
    approvalWaitIds: new Set(),
    unreadIds: [],
    agentTurns: {},
    peekApprovalWait: () => false,
    peekCliRunning: () => false,
    navScrollRef: { current: null },
    updateCanScroll: vi.fn(),
    canScroll: false,
    canScrollUp: false,
    canScrollDown: false,
    orderedRows: [],
    renderAgentRow: () => null,
    renderRemoteRow: () => null,
    renderTeamRow: () => null,
    ...overrides,
  }
}

describe('#1247 directional scroll chevrons (module-level)', () => {
  it('hides both chevrons when the column cannot scroll either way', () => {
    render(
      <RailSections
        {...(baseProps({ canScrollUp: false, canScrollDown: false }) as React.ComponentProps<
          typeof RailSections
        >)}
      />,
    )
    expect(screen.queryByTestId('rail-scroll-chevron-up')).not.toBeInTheDocument()
    expect(screen.queryByTestId('rail-scroll-chevron-down')).not.toBeInTheDocument()
  })

  it('shows the up chevron only when canScrollUp is true', () => {
    render(
      <RailSections
        {...(baseProps({ canScrollUp: true }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    expect(screen.getByTestId('rail-scroll-chevron-up')).toBeInTheDocument()
    expect(screen.queryByTestId('rail-scroll-chevron-down')).not.toBeInTheDocument()
  })

  it('shows the down chevron only when canScrollDown is true', () => {
    render(
      <RailSections
        {...(baseProps({ canScrollDown: true }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    expect(screen.getByTestId('rail-scroll-chevron-down')).toBeInTheDocument()
    expect(screen.queryByTestId('rail-scroll-chevron-up')).not.toBeInTheDocument()
  })

  it('never renders the chevrons outside avatar-only mode', () => {
    render(
      <RailSections
        {...(baseProps({
          isAvatarOnly: false,
          canScrollUp: true,
          canScrollDown: true,
        }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    expect(screen.queryByTestId('rail-scroll-chevron-up')).not.toBeInTheDocument()
    expect(screen.queryByTestId('rail-scroll-chevron-down')).not.toBeInTheDocument()
  })

  it('clicking an indicator scrolls the nav by one avatar tile', () => {
    const scrollBy = vi.fn()
    const ref = { current: null as HTMLElement | null }
    render(
      <RailSections
        {...(baseProps({
          canScrollUp: true,
          canScrollDown: true,
          navScrollRef: ref,
        }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    // RailSections attaches the real scroller to the ref; spy on its scrollBy.
    const scroller = ref.current as HTMLElement
    expect(scroller).toBeTruthy()
    scroller.scrollBy = scrollBy as unknown as HTMLElement['scrollBy']
    fireEvent.click(screen.getByTestId('rail-scroll-chevron-up'))
    expect(scrollBy).toHaveBeenCalledWith({ top: -48, behavior: 'smooth' })
    fireEvent.click(screen.getByTestId('rail-scroll-chevron-down'))
    expect(scrollBy).toHaveBeenCalledWith({ top: 48, behavior: 'smooth' })
  })
})

describe('#1250 section capsules in ultra-compact mode (module-level)', () => {
  it('wraps a populated section and labels it with its name', () => {
    render(
      <RailSections
        {...(baseProps({
          sectionBlocks: [
            {
              id: 'dev',
              name: 'Dev',
              rows: [{ id: 'r1', kind: 'agent', agent: { id: 'a1', name: 'Ada' } }],
              collapsed: false,
              custom: false,
              internalOnly: false,
            },
          ],
          visibleCount: 1,
          renderAgentRow: () => <li data-testid="agent-row">Ada</li>,
        }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    const section = screen.getByTestId('rail-section')
    expect(section.className).toContain('os-rail-section--grouped')
    expect(section).toHaveAttribute('title', 'Dev')
    expect(section).toHaveAttribute('aria-label', 'Dev')
  })

  it('does not box an empty section', () => {
    render(
      <RailSections
        {...(baseProps({
          sectionBlocks: [
            {
              id: 'empty',
              name: 'Empty',
              rows: [],
              collapsed: false,
              custom: true,
              internalOnly: false,
            },
          ],
          visibleCount: 1,
        }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    const section = screen.getByTestId('rail-section')
    expect(section.className).not.toContain('os-rail-section--grouped')
  })

  it('leaves sections ungrouped outside avatar-only mode', () => {
    render(
      <RailSections
        {...(baseProps({
          isAvatarOnly: false,
          sectionBlocks: [
            {
              id: 'dev',
              name: 'Dev',
              rows: [{ id: 'r1', kind: 'agent', agent: { id: 'a1', name: 'Ada' } }],
              collapsed: false,
              custom: false,
              internalOnly: false,
            },
          ],
          visibleCount: 1,
          renderAgentRow: () => <li data-testid="agent-row">Ada</li>,
        }) as React.ComponentProps<typeof RailSections>)}
      />,
    )
    expect(screen.getByTestId('rail-section').className).not.toContain(
      'os-rail-section--grouped',
    )
  })
})

/* ─────────────────── #1250 CSS capsule contract ─────────────────── */

describe('#1250 avatar-only section capsule CSS', () => {
  it('styles the grouped section as a subtle dashed capsule', () => {
    const css = require('node:fs').readFileSync(
      require('node:path').resolve(__dirname, '../../index.css'),
      'utf8',
    ) as string
    const match = css.match(
      /\.os-agent-sidebar--avatar-only \.os-rail-section--grouped\s*\{([^}]+)\}/,
    )
    expect(match).toBeTruthy()
    const rule = match![1]
    expect(rule).toMatch(/border-radius:\s*0\.75rem/)
    expect(rule).toMatch(/border:\s*1px dashed/)
    expect(rule).toMatch(/color-mix\(in srgb, var\(--color-base-content\) 10%/)
    expect(rule).toMatch(/background:\s*color-mix\(in srgb, var\(--color-base-content\) 2%/)
    expect(rule).toMatch(/margin:\s*0\.35rem 0\.25rem/)
    expect(rule).toMatch(/padding:\s*0\.25rem 0\.15rem/)
  })
})


const yesterday = Date.now() - 26 * 60 * 60 * 1000

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        json: async () => ({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    if (url.includes('/v1/blueprints')) {
      return {
        ok: true,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 'codey',
              object: 'blueprint',
              name: 'Codey',
              description: 'Code assistant',
              last_message_at: yesterday,
              rail: true,
            },
          ],
        }),
      } as Response
    }
    return {
      ok: true,
      json: async () => ({ object: 'list', data: [], results: [] }),
    } as Response
  })
}

describe('#1247 chevrons drive from the real rail scroll box', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    // 88px = the ultra-compact (avatar-only) detent (#1289, #1350).
    localStorage.setItem('swarm_rail_width', '88')
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('shows the down chevron mid-scroll and the up chevron after scrolling down', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat']}>
            <AgentSidebar open />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    const rail = await screen.findByTestId('os-agent-rail')
    expect(rail).toHaveAttribute('data-avatar-only', 'true')
    const nav = await screen.findByTestId('rail-agent-scroller')
    // Fake an overflowing avatar-only column, scrolled to the top.
    Object.defineProperty(nav, 'scrollHeight', { value: 600, configurable: true })
    Object.defineProperty(nav, 'clientHeight', { value: 200, configurable: true })
    Object.defineProperty(nav, 'scrollTop', { value: 0, configurable: true })
    fireEvent.scroll(nav)
    expect(await screen.findByTestId('rail-scroll-chevron-down')).toBeInTheDocument()
    expect(screen.queryByTestId('rail-scroll-chevron-up')).not.toBeInTheDocument()

    // Scroll into the middle → both directions exist.
    Object.defineProperty(nav, 'scrollTop', { value: 200, configurable: true })
    fireEvent.scroll(nav)
    expect(await screen.findByTestId('rail-scroll-chevron-up')).toBeInTheDocument()
    expect(screen.getByTestId('rail-scroll-chevron-down')).toBeInTheDocument()
  })
})
