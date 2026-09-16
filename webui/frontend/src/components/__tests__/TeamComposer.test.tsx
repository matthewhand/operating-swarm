import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import TeamComposer from '../TeamComposer'
import {
  DRAG_MIME,
  encodeDragAgent,
  encodeDragRole,
  encodeDragTool,
  FIRST_AGENT_VALUE,
  memberKey,
  ROLE_DRAG_MIME,
  ROSTER_DRAG_MIME,
  TOOL_DRAG_MIME,
} from '../../lib/teamRoster'
import type { TeamAgent } from '../../lib/api'

const AGENTS: TeamAgent[] = [
  { id: 'jeeves', name: 'Jeeves', kind: 'api', source: 'blueprint:jeeves' },
  { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok' },
  {
    id: 'acp',
    name: 'ACP harness',
    kind: 'remote',
    source: 'placeholder:remote:acp',
    placeholder: true,
  },
]

let agentsFixture: TeamAgent[] = AGENTS

function manyKindAgents(): TeamAgent[] {
  const api = Array.from({ length: 16 }, (_, i) => ({
    id: `api-${i}`,
    name: `API Agent ${i}`,
    kind: 'api' as const,
    source: `blueprint:api-${i}`,
  }))
  return [
    ...api,
    { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok' },
    { id: 'claude', name: 'claude', kind: 'cli', source: 'cli:claude' },
    {
      id: 'acp',
      name: 'ACP harness',
      kind: 'remote',
      source: 'placeholder:remote:acp',
      placeholder: true,
    },
  ]
}

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

function selectAgentKindTab(kind: 'API' | 'CLI' | 'Remote') {
  fireEvent.click(screen.getByRole('tab', { name: new RegExp(`^${kind}\\b`, 'i') }))
}

async function addAvailableAgent(kind: 'API' | 'CLI' | 'Remote') {
  const available = await screen.findByRole('list', { name: /available agents list/i })
  selectAgentKindTab(kind)
  fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[0])
}

describe('TeamComposer first-launch overlay', () => {
  beforeEach(() => {
    agentsFixture = AGENTS
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/team-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: agentsFixture }),
          } as Response
        }
        if (url.includes('/v1/team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        if (url.includes('/v1/marketplace')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'marketplace_catalog',
              kind: 'teams',
              sources: ['os_team_pack'],
              external: true,
              items: [],
              warnings: [],
            }),
          } as Response
        }
        if (url.includes('/v1/mcp-plugins')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'mcp_plugins',
              scope: 'user',
              servers: [
                {
                  name: 'github',
                  label: 'GitHub',
                  kind: 'local',
                  enabled: true,
                  command: 'uvx',
                  args: [],
                  url: '',
                  env: {},
                  headers: {},
                  provides: [],
                  note: '',
                  tools: [],
                },
              ],
            }),
          } as Response
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders two panes: dashed drop zone and available agents', async () => {
    renderComposer()

    const dropZone = await screen.findByTestId('team-drop-zone')
    expect(dropZone).toHaveClass('border-dashed')
    expect(dropZone).toHaveTextContent(/drop agents here/i)

    const available = await screen.findByRole('list', { name: /available agents list/i })
    expect(within(available).getByText('Jeeves')).toBeInTheDocument()
    expect(within(available).queryByText('grok')).not.toBeInTheDocument()
    expect(within(available).queryByText('API')).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^API\b/i })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /^CLI\b/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^Remote\b/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /new team/i })).toBeInTheDocument()
  })

  it('tabs available agents by kind without per-row KIND_LABEL badges', async () => {
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    expect(screen.getByRole('tab', { name: /^API\b/i })).toHaveAttribute('aria-selected', 'true')
    expect(within(available).getByText('Jeeves')).toBeInTheDocument()
    expect(within(available).queryByText('grok')).not.toBeInTheDocument()
    expect(within(available).queryByText('ACP harness')).not.toBeInTheDocument()
    expect(within(available).queryByText('API')).not.toBeInTheDocument()

    selectAgentKindTab('CLI')
    expect(screen.getByRole('tab', { name: /^CLI\b/i })).toHaveAttribute('aria-selected', 'true')
    expect(within(available).queryByText('Jeeves')).not.toBeInTheDocument()
    expect(within(available).getByText('grok')).toBeInTheDocument()
    expect(within(available).queryByText('CLI')).not.toBeInTheDocument()

    selectAgentKindTab('Remote')
    expect(screen.getByRole('tab', { name: /^Remote\b/i })).toHaveAttribute('aria-selected', 'true')
    expect(within(available).getByText('ACP harness')).toBeInTheDocument()
    expect(within(available).queryByText('remote')).not.toBeInTheDocument()
    expect(within(available).queryByText('Remote')).not.toBeInTheDocument()
  })

  it('defaults to the first non-empty kind tab when API is empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/team-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: AGENTS.filter((agent) => agent.kind !== 'api'),
            }),
          } as Response
        }
        if (url.includes('/v1/team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response
      }),
    )
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    expect(screen.getByRole('tab', { name: /^CLI\b/i })).toHaveAttribute('aria-selected', 'true')
    expect(within(available).getByText('grok')).toBeInTheDocument()
    expect(within(available).queryByText('Jeeves')).not.toBeInTheDocument()
  })

  it('locks the Tools pane until the roster has a member', async () => {
    renderComposer()
    const pane = await screen.findByTestId('team-tools-pane')
    expect(pane).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByTestId('team-tools-locked-hint')).toHaveTextContent(/add agents first/i)
    expect(screen.queryByRole('list', { name: /available tools list/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /handoff/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/gate is unwired/i)).not.toBeInTheDocument()

    await addAvailableAgent('API')
    expect(screen.getByTestId('team-tools-pane')).toHaveAttribute('aria-disabled', 'false')
    expect(screen.queryByTestId('team-tools-locked-hint')).not.toBeInTheDocument()
    expect(screen.getByRole('list', { name: /available tools list/i })).toBeInTheDocument()
    expect(screen.getByText(/drop tools here/i)).toBeInTheDocument()
  })

  it('adds a member via native HTML5 drop', async () => {
    renderComposer()
    const dropZone = await screen.findByTestId('team-drop-zone')
    const payload = encodeDragAgent(AGENTS[0])
    const dt = mockDataTransfer({ [DRAG_MIME]: payload })
    fireEvent.drop(dropZone, { dataTransfer: dt })

    const roster = await screen.findByRole('list', { name: /roster members/i })
    expect(within(roster).getByText('Jeeves')).toBeInTheDocument()
    expect(within(roster).queryByText('API')).not.toBeInTheDocument()
    expect(within(roster).getByTestId('roster-index')).toHaveTextContent('1')
    expect(within(roster).queryByDisplayValue('default')).not.toBeInTheDocument()
    expect(within(roster).queryByRole('radio')).not.toBeInTheDocument()
  })

  it('adds and removes via context menu for a11y', async () => {
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    selectAgentKindTab('CLI')
    const grokRow = within(available).getByText('grok').closest('li')
    expect(grokRow).toBeTruthy()
    fireEvent.contextMenu(grokRow as HTMLElement)
    fireEvent.click(screen.getByRole('menuitem', { name: /^add$/i }))

    const roster = await screen.findByRole('list', { name: /roster members/i })
    expect(within(roster).getByText('grok')).toBeInTheDocument()
    expect(within(roster).queryByText('CLI')).not.toBeInTheDocument()

    const chip = within(roster).getByText('grok').closest('article') as HTMLElement
    fireEvent.contextMenu(chip)
    fireEvent.click(screen.getByRole('menuitem', { name: /^remove$/i }))
    expect(screen.queryByRole('list', { name: /roster members/i })).not.toBeInTheDocument()
    expect(screen.getByText(/drop agents here/i)).toBeInTheDocument()
  })

  it('saves the roster contract without posting to /v1/teams/', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    const dropZone = await screen.findByTestId('team-drop-zone')
    fireEvent.drop(dropZone, {
      dataTransfer: mockDataTransfer({ [DRAG_MIME]: encodeDragAgent(AGENTS[1]) }),
    })
    fireEvent.change(screen.getByLabelText(/team name/i), {
      target: { value: 'Research Squad' },
    })

    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        expect(url).toContain('/v1/team-rosters/')
        expect(url).not.toContain('/v1/teams/')
        const body = JSON.parse(String(init?.body))
        expect(body.name).toBe('Research Squad')
        expect(body.members[0]).toMatchObject({
          id: 'grok',
          kind: 'cli',
          role: 'chief_of_staff',
          source: 'cli:grok',
        })
        expect(body.chief_of_staff_id).toBe('grok')
        expect(body.tools).toEqual([])
        expect(body.wires).toEqual({ handoff: false, as_tool: false })
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'research-squad',
            object: 'team_roster',
            name: 'Research Squad',
            members: body.members,
            wires: body.wires,
          }),
        } as Response
      }
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
    })

    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/team_rosters\.json/i)
  })

  it('keeps the Team lead picker disabled until agents are added and defaults to First agent', async () => {
    renderComposer()
    const select = await screen.findByTestId('team-cos-select')
    expect(select).toBeDisabled()
    expect(select).toHaveDisplayValue('First agent')
    expect(within(screen.getByTestId('team-cos-fieldset')).queryByRole('option', { name: /no chief of staff/i })).not.toBeInTheDocument()
    expect(screen.getAllByText(/add agents first/i).length).toBeGreaterThan(0)
    expect(screen.getByTestId('team-cos-instructions')).toBeDisabled()

    await addAvailableAgent('API')
    const enabled = screen.getByTestId('team-cos-select')
    expect(enabled).not.toBeDisabled()
    expect(enabled).toHaveDisplayValue('First agent')
    expect(enabled).toHaveValue(FIRST_AGENT_VALUE)
    expect(screen.getByTestId('team-cos-instructions')).not.toBeDisabled()
  })

  it('selects a CoS, saves team-scoped instructions, and can clear CoS', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    await addAvailableAgent('API')
    await addAvailableAgent('CLI')
    await addAvailableAgent('Remote')

    fireEvent.change(screen.getByLabelText(/team name/i), {
      target: { value: 'Research Squad' },
    })
    fireEvent.change(screen.getByTestId('team-cos-select'), { target: { value: 'jeeves' } })
    const instructions = screen.getByTestId('team-cos-instructions')
    expect(instructions).not.toBeDisabled()
    expect((instructions as HTMLTextAreaElement).value).toMatch(/coordinate this team's roster/i)
    fireEvent.change(instructions, {
      target: { value: 'prefer grok_agent for revision control' },
    })

    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init?.body))
        expect(body.chief_of_staff_id).toBe('jeeves')
        expect(body.chief_of_staff_instructions).toBe('prefer grok_agent for revision control')
        expect(body.members).toHaveLength(3)
        expect(body.members.find((m: { id: string }) => m.id === 'jeeves')?.role).toBe(
          'chief_of_staff',
        )
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'research-squad',
            object: 'team_roster',
            name: 'Research Squad',
            members: body.members,
            wires: body.wires,
            chief_of_staff_id: 'jeeves',
            chief_of_staff_instructions: body.chief_of_staff_instructions,
          }),
        } as Response
      }
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
    })

    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/team_rosters\.json/i)
    expect(screen.getByTestId('team-cos-select')).toHaveDisplayValue('First agent')
    expect(screen.getByTestId('team-cos-select')).toHaveValue(FIRST_AGENT_VALUE)
    expect(screen.getByTestId('team-cos-instructions')).toHaveValue(
      'prefer grok_agent for revision control',
    )

    fireEvent.change(screen.getByTestId('team-cos-select'), { target: { value: 'grok' } })
    expect(screen.getByTestId('team-cos-select')).toHaveValue('grok')
    fireEvent.change(screen.getByTestId('team-cos-select'), { target: { value: FIRST_AGENT_VALUE } })
    expect(screen.getByTestId('team-cos-select')).toHaveDisplayValue('First agent')
    expect(screen.getByTestId('team-cos-instructions')).not.toBeDisabled()
  })

  it('omits remotes from the CoS picker', async () => {
    renderComposer()
    await addAvailableAgent('Remote')
    const select = screen.getByTestId('team-cos-select')
    expect(select).toHaveDisplayValue('First agent')
    expect(within(select).queryByRole('option', { name: /acp/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/cos n\/a/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('team-cos-instructions')).toBeDisabled()
  })

  it('numbers roster members and reordering member 2 to first updates First agent', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    await addAvailableAgent('API')
    await addAvailableAgent('CLI')

    const roster = await screen.findByRole('list', { name: /roster members/i })
    const rows = within(roster).getAllByTestId('roster-member')
    expect(within(rows[0]).getByTestId('roster-index')).toHaveTextContent('1')
    expect(within(rows[0]).getByText('Jeeves')).toBeInTheDocument()
    expect(within(rows[1]).getByTestId('roster-index')).toHaveTextContent('2')
    expect(within(rows[1]).getByText('grok')).toBeInTheDocument()
    expect(screen.getByTestId('team-cos-select')).toHaveDisplayValue('First agent')
    expect(screen.getByTestId('team-cos-select')).toHaveValue(FIRST_AGENT_VALUE)

    fireEvent.drop(rows[0], {
      dataTransfer: mockDataTransfer({ [ROSTER_DRAG_MIME]: '1' }),
    })

    const reordered = within(roster).getAllByTestId('roster-member')
    expect(within(reordered[0]).getByText('grok')).toBeInTheDocument()
    expect(within(reordered[0]).getByTestId('roster-index')).toHaveTextContent('1')
    expect(within(reordered[1]).getByText('Jeeves')).toBeInTheDocument()
    expect(within(reordered[1]).getByTestId('roster-index')).toHaveTextContent('2')
    expect(screen.getByTestId('team-cos-select')).toHaveDisplayValue('First agent')

    fireEvent.change(screen.getByLabelText(/team name/i), {
      target: { value: 'Research Squad' },
    })
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init?.body))
        expect(body.members.map((m: { id: string }) => m.id)).toEqual(['grok', 'jeeves'])
        expect(body.chief_of_staff_id).toBe('grok')
        expect(body.members[0].role).toBe('chief_of_staff')
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'research-squad',
            object: 'team_roster',
            name: 'Research Squad',
            members: body.members,
            wires: body.wires,
            chief_of_staff_id: 'grok',
            chief_of_staff_instructions: body.chief_of_staff_instructions,
          }),
        } as Response
      }
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
    })
    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/team_rosters\.json/i)
  })

  it('keeps an explicit named lead when the roster is reordered', async () => {
    renderComposer()
    await addAvailableAgent('API')
    await addAvailableAgent('CLI')
    fireEvent.change(screen.getByTestId('team-cos-select'), { target: { value: 'jeeves' } })
    expect(screen.getByTestId('team-cos-select')).toHaveValue('jeeves')

    const roster = screen.getByRole('list', { name: /roster members/i })
    const rows = within(roster).getAllByTestId('roster-member')
    fireEvent.drop(rows[0], {
      dataTransfer: mockDataTransfer({ [ROSTER_DRAG_MIME]: '1' }),
    })
    expect(within(roster).getAllByTestId('roster-member')[0]).toHaveTextContent('grok')
    expect(screen.getByTestId('team-cos-select')).toHaveValue('jeeves')
    expect(screen.getByTestId('team-cos-instructions')).not.toBeDisabled()
  })

  it('marks available rows as HTML5-draggable (no dnd-kit)', async () => {
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    const row = within(available).getByText('Jeeves').closest('[draggable]')
    expect(row).toHaveAttribute('draggable', 'true')
  })

  it('uses one scroller for available agents; kind lists stay in document flow', async () => {
    renderComposer()
    const scroller = await screen.findByTestId('available-agents-scroller')
    expect(scroller).toHaveClass('overflow-y-auto')
    expect(scroller).toHaveClass('max-h-[22rem]')
    expect(scroller).not.toHaveClass('os-scrollable-picker-list')

    const group = screen.getByTestId('available-agents-group-api')
    const list = group.querySelector('ul')
    expect(list).toBeTruthy()
    expect(list).not.toHaveClass('os-scrollable-picker-list')
    expect(list).not.toHaveClass('overflow-y-auto')
    expect(list).not.toHaveClass('max-h-40')

    const headers = ['api', 'cli', 'remote'].map((kind) =>
      screen.getByTestId(`available-agents-kind-${kind}`),
    )
    expect(headers[0]).toHaveTextContent(/^API\s*\(1\)/)
    expect(headers[1]).toHaveTextContent(/^CLI\s*\(1\)/)
    expect(headers[2]).toHaveTextContent(/^Remote\s*\(1\)/)
    expect(
      headers[0].compareDocumentPosition(headers[1]) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      headers[1].compareDocumentPosition(headers[2]) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('keeps CLI and Remote after a long API list and still Adds', async () => {
    agentsFixture = manyKindAgents()
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    expect(screen.getByTestId('available-agents-kind-api')).toHaveTextContent('(16)')
    expect(screen.getByTestId('available-agents-kind-cli')).toHaveTextContent('(2)')
    expect(screen.getByTestId('available-agents-kind-remote')).toHaveTextContent('(1)')
    expect(within(available).getByText('API Agent 0')).toBeInTheDocument()
    expect(within(available).queryByText('grok')).not.toBeInTheDocument()
    expect(within(available).queryByText('ACP harness')).not.toBeInTheDocument()

    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[0])
    const roster = await screen.findByRole('list', { name: /roster members/i })
    expect(within(roster).getByText('API Agent 0')).toBeInTheDocument()
    selectAgentKindTab('CLI')
    const grokRow = within(available).getByText('grok').closest('li') as HTMLElement
    fireEvent.click(within(grokRow).getByRole('button', { name: 'Add' }))
    expect(within(roster).getByText('grok')).toBeInTheDocument()
  })

  it('locks the Roles pane until the roster has a member', async () => {
    renderComposer()
    const pane = await screen.findByTestId('team-roles-pane')
    expect(pane).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByTestId('team-roles-locked-hint')).toHaveTextContent(/add agents first/i)
    expect(screen.queryByRole('list', { name: /available roles list/i })).not.toBeInTheDocument()

    await addAvailableAgent('API')
    expect(screen.getByTestId('team-roles-pane')).toHaveAttribute('aria-disabled', 'false')
    expect(screen.queryByTestId('team-roles-locked-hint')).not.toBeInTheDocument()
    expect(screen.getByRole('list', { name: /available roles list/i })).toBeInTheDocument()
    expect(screen.getByText(/drop roles here/i)).toBeInTheDocument()
  })

  it('adds a role slot via drop and Add, and rejects cross-zone drags', async () => {
    renderComposer()
    const agentZone = await screen.findByTestId('team-drop-zone')
    const roleZone = screen.getByTestId('team-roles-drop-zone')
    fireEvent.drop(roleZone, {
      dataTransfer: mockDataTransfer({ [ROLE_DRAG_MIME]: encodeDragRole('skeptic') }),
    })
    expect(screen.queryByTestId('team-role-slot')).not.toBeInTheDocument()

    fireEvent.drop(agentZone, {
      dataTransfer: mockDataTransfer({ [DRAG_MIME]: encodeDragAgent(AGENTS[0]) }),
    })
    fireEvent.drop(roleZone, {
      dataTransfer: mockDataTransfer({ [DRAG_MIME]: encodeDragAgent(AGENTS[1]) }),
    })
    expect(screen.queryByRole('list', { name: /role slots/i })).not.toBeInTheDocument()
    fireEvent.drop(agentZone, {
      dataTransfer: mockDataTransfer({ [ROLE_DRAG_MIME]: encodeDragRole('gate') }),
    })
    expect(screen.queryByTestId('team-role-slot')).not.toBeInTheDocument()

    fireEvent.drop(roleZone, {
      dataTransfer: mockDataTransfer({ [ROLE_DRAG_MIME]: encodeDragRole('skeptic') }),
    })
    const slots = await screen.findByRole('list', { name: /role slots/i })
    expect(within(slots).getByText('skeptic')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /add engineer role/i }))
    expect(screen.getAllByTestId('team-role-slot')).toHaveLength(2)
    expect(within(slots).getByText('engineer')).toBeInTheDocument()
  })

  it('assigns unroled agents from a slot dropdown and frees them when cleared or removed', async () => {
    renderComposer()
    await addAvailableAgent('API')
    await addAvailableAgent('CLI')
    fireEvent.click(screen.getByRole('button', { name: /add skeptic role/i }))
    fireEvent.click(screen.getByRole('button', { name: /add gate role/i }))

    const skeptic = screen.getByTestId('team-role-assign-skeptic')
    const gate = screen.getByTestId('team-role-assign-gate')
    expect(within(skeptic).queryByRole('option', { name: 'Jeeves' })).not.toBeInTheDocument()
    expect(within(skeptic).getByRole('option', { name: 'grok' })).toBeInTheDocument()

    fireEvent.change(skeptic, { target: { value: memberKey({ id: 'grok', kind: 'cli', source: 'cli:grok' }) } })
    expect(within(gate).queryByRole('option', { name: 'grok' })).not.toBeInTheDocument()
    expect(within(skeptic).getByRole('option', { name: 'grok' })).toBeInTheDocument()

    fireEvent.change(skeptic, { target: { value: '' } })
    expect(within(gate).getByRole('option', { name: 'grok' })).toBeInTheDocument()

    fireEvent.change(skeptic, { target: { value: memberKey({ id: 'grok', kind: 'cli', source: 'cli:grok' }) } })
    fireEvent.click(screen.getByRole('button', { name: /remove skeptic role/i }))
    expect(screen.queryByTestId('team-role-assign-skeptic')).not.toBeInTheDocument()
    expect(within(screen.getByTestId('team-role-assign-gate')).getByRole('option', { name: 'grok' })).toBeInTheDocument()
  })

  it('assigns CoS from a role-slot dropdown with eligibility, and keeps No CoS valid', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    await addAvailableAgent('API')
    await addAvailableAgent('CLI')
    await addAvailableAgent('Remote')
    fireEvent.click(screen.getByRole('button', { name: /add chief_of_staff role/i }))

    const slot = screen.getByTestId('team-role-assign-chief_of_staff')
    expect(within(slot).getByRole('option', { name: /no chief of staff/i })).toBeInTheDocument()
    expect(within(slot).queryByRole('option', { name: /acp/i })).not.toBeInTheDocument()
    expect(within(slot).getByRole('option', { name: 'Jeeves' })).toBeInTheDocument()
    fireEvent.change(slot, {
      target: { value: memberKey({ id: 'jeeves', kind: 'api', source: 'blueprint:jeeves' }) },
    })
    expect(screen.getByTestId('team-cos-select')).toHaveValue('jeeves')
    expect(screen.getByRole('button', { name: /add chief_of_staff role/i })).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/team name/i), { target: { value: 'Research Squad' } })
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init?.body))
        expect(body.chief_of_staff_id).toBe('jeeves')
        expect(body.members.find((m: { id: string }) => m.id === 'jeeves')?.role).toBe(
          'chief_of_staff',
        )
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'research-squad',
            object: 'team_roster',
            name: 'Research Squad',
            members: body.members,
            wires: body.wires,
            chief_of_staff_id: 'jeeves',
            chief_of_staff_instructions: body.chief_of_staff_instructions,
          }),
        } as Response
      }
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
    })
    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/team_rosters\.json/i)

    fireEvent.change(screen.getByTestId('team-role-assign-chief_of_staff'), { target: { value: '' } })
    expect(screen.getByTestId('team-cos-select')).toHaveValue('')
    expect(screen.getByTestId('team-cos-instructions')).toBeDisabled()
  })

  it('adds a handoff tool whose target dropdown lists roster members', async () => {
    renderComposer()
    const toolZone = await screen.findByTestId('team-tools-drop-zone')
    fireEvent.drop(toolZone, {
      dataTransfer: mockDataTransfer({ [TOOL_DRAG_MIME]: encodeDragTool({ type: 'handoff' }) }),
    })
    expect(screen.queryByTestId('team-tool-slot')).not.toBeInTheDocument()

    await addAvailableAgent('API')
    await addAvailableAgent('CLI')
    fireEvent.click(screen.getByRole('button', { name: /add handoff tool/i }))

    const target = screen.getByTestId('team-tool-handoff-to')
    expect(within(target).getByRole('option', { name: 'Jeeves' })).toBeInTheDocument()
    expect(within(target).getByRole('option', { name: 'grok' })).toBeInTheDocument()
    expect(screen.getByTestId('team-tool-handoff-from')).toHaveDisplayValue('First agent')
  })

  it('saves MCP tools with empty or locked agents and derived wires', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    await addAvailableAgent('API')
    fireEvent.click(screen.getByRole('button', { name: /add handoff tool/i }))
    fireEvent.change(screen.getByTestId('team-tool-handoff-to'), { target: { value: 'jeeves' } })
    fireEvent.click(screen.getByRole('button', { name: /add github mcp tool/i }))
    expect(screen.getByTestId('team-tool-mcp-agents')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/team name/i), { target: { value: 'Research Squad' } })
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init?.body))
        expect(body.tools).toEqual([
          { type: 'handoff', to: 'jeeves' },
          { type: 'mcp', server: 'github', agents: [] },
        ])
        expect(body.wires).toEqual({ handoff: true, as_tool: false })
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'research-squad',
            object: 'team_roster',
            name: 'Research Squad',
            members: body.members,
            tools: body.tools,
            wires: body.wires,
          }),
        } as Response
      }
      if (url.includes('/v1/team-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: AGENTS }),
        } as Response
      }
      if (url.includes('/v1/mcp-plugins')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'mcp_plugins', scope: 'user', servers: [] }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    })
    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/team_rosters\.json/i)

    fireEvent.click(screen.getByRole('checkbox', { name: /lock github to jeeves/i }))
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'PUT' || init?.method === 'POST') {
        const body = JSON.parse(String(init?.body))
        expect(body.tools).toEqual([
          { type: 'handoff', to: 'jeeves' },
          { type: 'mcp', server: 'github', agents: ['jeeves'] },
        ])
        expect(body.wires).toEqual({ handoff: true, as_tool: false })
        return {
          ok: true,
          status: init?.method === 'PUT' ? 200 : 201,
          json: async () => ({
            id: 'research-squad',
            object: 'team_roster',
            name: 'Research Squad',
            members: body.members,
            tools: body.tools,
            wires: body.wires,
          }),
        } as Response
      }
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
    })
    fireEvent.click(screen.getByRole('button', { name: /save roster/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/team_rosters\.json/i)
  })
})
