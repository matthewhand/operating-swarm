/**
 * #508 (REQ-909) — the Teams composer is no longer one long scroll.
 *
 * Essentials (name, save/load, Chief of Staff) stay on the opening pane;
 * roles, tools and the catalog become real panes behind the shared DaisyUI
 * `Tabs` (role=tab, Arrow/Home/End support kept by the component). Only the
 * active tier occupies the frame, and the frame's height class never changes
 * when panes switch — the shell height is set once and the pane scrolls
 * internally (the REQ-910 pattern).
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import TeamComposer from '../TeamComposer'
import {
  DRAG_MIME,
  encodeDragAgent,
  encodeDragTool,
  encodeDragRole,
  ROLE_DRAG_MIME,
  TOOL_DRAG_MIME,
} from '../../lib/teamRoster'
import type { TeamAgent } from '../../lib/api'

const AGENTS: TeamAgent[] = [
  { id: 'jeeves', name: 'Jeeves', kind: 'api', source: 'blueprint:jeeves' },
  { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok' },
]

function mockDataTransfer(initial: Record<string, string> = {}) {
  const store = { ...initial }
  return {
    store,
    setData: (type: string, value: string) => {
      store[type] = value
    },
    getData: (type: string) => store[type] ?? '',
    get types() {
      return Object.keys(store)
    },
    effectAllowed: 'copy' as const,
    dropEffect: 'copy' as const,
  }
}

function renderComposer() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <TeamComposer isOpen onClose={() => {}} />
    </QueryClientProvider>,
  )
}

async function addAgent(kind: 'API' | 'CLI') {
  const available = await screen.findByRole('list', { name: /available agents list/i })
  fireEvent.click(screen.getByRole('tab', { name: new RegExp(`^${kind}\\b`, 'i') }))
  fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[0])
}

function gotoPane(name: 'Essentials' | 'Roles' | 'Tools' | 'Catalog') {
  fireEvent.click(screen.getByRole('tab', { name }))
}

describe('#508 Teams composer tiers', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/team-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: AGENTS }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens on Essentials: roles, tools and catalog are absent, not hidden', async () => {
    renderComposer()
    await screen.findByTestId('team-drop-zone')
    expect(screen.getByLabelText(/team name/i)).toBeInTheDocument()
    expect(screen.getByTestId('team-cos-fieldset')).toBeInTheDocument()
    expect(screen.queryByTestId('team-roles-pane')).not.toBeInTheDocument()
    expect(screen.queryByTestId('team-tools-pane')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/get more teams/i)).not.toBeInTheDocument()
  })

  it('renders each tier only while selected, via a real tablist', async () => {
    renderComposer()
    await screen.findByTestId('team-drop-zone')

    gotoPane('Roles')
    expect(screen.getByTestId('team-roles-pane')).toBeInTheDocument()
    expect(screen.queryByTestId('team-tools-pane')).not.toBeInTheDocument()

    gotoPane('Tools')
    expect(screen.getByTestId('team-tools-pane')).toBeInTheDocument()
    expect(screen.queryByTestId('team-roles-pane')).not.toBeInTheDocument()

    gotoPane('Catalog')
    expect(screen.getByLabelText(/get more teams/i)).toBeInTheDocument()
    expect(screen.queryByTestId('team-tools-pane')).not.toBeInTheDocument()

    gotoPane('Essentials')
    expect(screen.getByTestId('team-drop-zone')).toBeInTheDocument()
    expect(screen.queryByTestId('team-roles-pane')).not.toBeInTheDocument()
  })

  it('keeps the available-agents kind tabs as a nested tab set', async () => {
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    expect(screen.getByRole('tab', { name: /^API\b/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    // The top-level tier tabs and the nested kind tabs coexist.
    expect(screen.getByRole('tab', { name: 'Roles' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /^CLI\b/i }))
    expect(within(available).getByText('grok')).toBeInTheDocument()
  })

  it('keeps the shell height class stable across pane switches (CSS contract)', async () => {
    renderComposer()
    await screen.findByTestId('team-drop-zone')
    const body = screen.getByTestId('team-composer-body')
    const heightClass = [...body.classList].find((c) => /^h-\[/.test(c))
    expect(heightClass).toBeTruthy()

    gotoPane('Roles')
    const body2 = screen.getByTestId('team-composer-body')
    expect([...body2.classList]).toContain(heightClass as string)
    // The pane scrolls internally rather than the modal growing.
    // eslint-disable-next-line testing-library/no-node-access
    expect(body2.querySelector('.overflow-y-auto')).toBeTruthy()
  })

  it('drag-and-drop still lands after switching to the tier pane', async () => {
    renderComposer()
    await addAgent('API')
    gotoPane('Roles')
    const roleZone = screen.getByTestId('team-roles-drop-zone')
    fireEvent.drop(roleZone, {
      dataTransfer: mockDataTransfer({ [ROLE_DRAG_MIME]: encodeDragRole('skeptic') }),
    })
    expect(await screen.findByRole('list', { name: /role slots/i })).toBeInTheDocument()

    gotoPane('Tools')
    const toolZone = screen.getByTestId('team-tools-drop-zone')
    fireEvent.drop(toolZone, {
      dataTransfer: mockDataTransfer({
        [TOOL_DRAG_MIME]: encodeDragTool({ type: 'handoff' }),
      }),
    })
    expect(await screen.findByTestId('team-tool-slot')).toBeInTheDocument()
  })

  it('state survives pane switches: compose on Essentials, wire on Tools, save', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    await addAgent('API')

    gotoPane('Tools')
    const toolZone = screen.getByTestId('team-tools-drop-zone')
    fireEvent.drop(toolZone, {
      dataTransfer: mockDataTransfer({ [TOOL_DRAG_MIME]: encodeDragTool({ type: 'handoff' }) }),
    })
    await screen.findByTestId('team-tool-slot')

    let posted: { members: Array<{ id: string }>; tools: unknown; name?: string } | null = null
    fetchMock.mockImplementation(async (_input, init) => {
      if (init?.method === 'POST') {
        posted = JSON.parse(String(init?.body))
        return {
          ok: true,
          status: 201,
          json: async () => ({ object: 'team_roster', id: 'r1', name: posted?.name }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    })
    fireEvent.change(screen.getByLabelText(/team name/i), { target: { value: 'Cross' } })
    fireEvent.click(screen.getByTestId('team-tool-handoff-to'))
    fireEvent.change(screen.getByTestId('team-tool-handoff-to'), { target: { value: 'jeeves' } })
    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    // #841: user-facing status copy no longer names backend storage files.
    expect(await screen.findByRole('status')).toHaveTextContent(/Saved roster “Cross”\./)
    // Asserted after the await, outside the mock body (jest/no-conditional-expect).
    const sent = posted as unknown as { members: Array<{ id: string }>; tools: unknown }
    expect(sent.members.map((m) => m.id)).toEqual(['jeeves'])
    expect(sent.tools).toEqual([{ type: 'handoff', to: 'jeeves' }])
  })

  it('still refuses foreign-mime drops on the roster zone from other tiers', async () => {
    renderComposer()
    await screen.findByTestId('team-drop-zone')
    const dropZone = screen.getByTestId('team-drop-zone')
    fireEvent.drop(dropZone, {
      dataTransfer: mockDataTransfer({
        [ROLE_DRAG_MIME]: encodeDragRole('skeptic'),
      }),
    })
    expect(
      screen.queryByRole('list', { name: /roster members/i }),
    ).not.toBeInTheDocument()
    fireEvent.drop(dropZone, {
      dataTransfer: mockDataTransfer({ [DRAG_MIME]: encodeDragAgent(AGENTS[0]) }),
    })
    expect(await screen.findByRole('list', { name: /roster members/i })).toBeInTheDocument()
  })
})
