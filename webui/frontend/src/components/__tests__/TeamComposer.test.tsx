import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import TeamComposer from '../TeamComposer'
import { DRAG_MIME, encodeDragAgent } from '../../lib/teamRoster'
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
    expect(within(available).getAllByText('API').length).toBeGreaterThan(0)
    expect(within(available).getAllByText('CLI').length).toBeGreaterThan(0)
    expect(within(available).getAllByText('remote').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /new team/i })).toBeInTheDocument()
  })

  it('defaults handoff and as_tool on, and states gate is unwired', async () => {
    renderComposer()
    const handoff = await screen.findByRole('checkbox', { name: /handoff/i })
    const asTool = screen.getByRole('checkbox', { name: /as_tool/i })
    expect(handoff).toBeChecked()
    expect(asTool).toBeChecked()
    expect(screen.getByText(/gate is unwired/i)).toBeInTheDocument()
  })

  it('adds a member via native HTML5 drop', async () => {
    renderComposer()
    const dropZone = await screen.findByTestId('team-drop-zone')
    const payload = encodeDragAgent(AGENTS[0])
    const dt = mockDataTransfer({ [DRAG_MIME]: payload })
    fireEvent.drop(dropZone, { dataTransfer: dt })

    const roster = await screen.findByRole('list', { name: /roster members/i })
    expect(within(roster).getByText('Jeeves')).toBeInTheDocument()
    expect(within(roster).getByText('API')).toBeInTheDocument()
    expect(within(roster).getByDisplayValue('default')).toBeInTheDocument()
  })

  it('adds and removes via context menu for a11y', async () => {
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    const grokRow = within(available).getByText('grok').closest('li')
    expect(grokRow).toBeTruthy()
    fireEvent.contextMenu(grokRow as HTMLElement)
    fireEvent.click(screen.getByRole('menuitem', { name: /^add$/i }))

    const roster = await screen.findByRole('list', { name: /roster members/i })
    expect(within(roster).getByText('CLI')).toBeInTheDocument()

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
          role: 'default',
          source: 'cli:grok',
        })
        expect(body.wires).toEqual({ handoff: true, as_tool: true })
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

  it('keeps CoS disabled until agents are added and does not auto-pick', async () => {
    renderComposer()
    const select = await screen.findByTestId('team-cos-select')
    expect(select).toBeDisabled()
    expect(select).toHaveDisplayValue('No Chief of Staff')
    expect(screen.getByText(/add agents first/i)).toBeInTheDocument()
    expect(screen.getByTestId('team-cos-instructions')).toBeDisabled()

    const available = await screen.findByRole('list', { name: /available agents list/i })
    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[0])
    const enabled = screen.getByTestId('team-cos-select')
    expect(enabled).not.toBeDisabled()
    expect(enabled).toHaveValue('')
    expect(screen.getByTestId('team-cos-instructions')).toBeDisabled()
  })

  it('selects a CoS, saves team-scoped instructions, and can clear CoS', async () => {
    const fetchMock = vi.mocked(fetch)
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[0])
    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[1])
    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[2])

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
    expect(screen.getByTestId('team-cos-select')).toHaveValue('jeeves')
    expect(screen.getByTestId('team-cos-instructions')).toHaveValue(
      'prefer grok_agent for revision control',
    )

    fireEvent.change(screen.getByTestId('team-cos-select'), { target: { value: '' } })
    expect(screen.getByTestId('team-cos-instructions')).toBeDisabled()
  })

  it('omits remotes from the CoS picker', async () => {
    renderComposer()
    const available = await screen.findByRole('list', { name: /available agents list/i })
    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[2])
    const select = screen.getByTestId('team-cos-select')
    expect(within(select).queryByRole('option', { name: /acp/i })).not.toBeInTheDocument()
    expect(screen.getByText(/cos n\/a/i)).toBeInTheDocument()
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

    for (const kind of ['api', 'cli', 'remote'] as const) {
      const group = screen.getByTestId(`available-agents-group-${kind}`)
      const list = group.querySelector('ul')
      expect(list).toBeTruthy()
      expect(list).not.toHaveClass('os-scrollable-picker-list')
      expect(list).not.toHaveClass('overflow-y-auto')
      expect(list).not.toHaveClass('max-h-40')
    }

    const headers = ['api', 'cli', 'remote'].map((kind) =>
      screen.getByTestId(`available-agents-kind-${kind}`),
    )
    expect(headers[0]).toHaveTextContent(/^API\s*\(1\)/)
    expect(headers[1]).toHaveTextContent(/^CLI\s*\(1\)/)
    expect(headers[2]).toHaveTextContent(/^remote\s*\(1\)/)
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
    expect(within(available).getByText('grok')).toBeInTheDocument()
    expect(within(available).getByText('ACP harness')).toBeInTheDocument()

    fireEvent.click(within(available).getAllByRole('button', { name: 'Add' })[0])
    const roster = await screen.findByRole('list', { name: /roster members/i })
    expect(within(roster).getByText('API Agent 0')).toBeInTheDocument()
    const grokRow = within(available).getByText('grok').closest('li') as HTMLElement
    fireEvent.click(within(grokRow).getByRole('button', { name: 'Add' }))
    expect(within(roster).getByText('grok')).toBeInTheDocument()
  })
})
