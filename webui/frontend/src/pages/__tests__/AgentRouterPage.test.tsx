import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import AgentRouterPage from '../AgentRouterPage'
import { useAgentStore } from '../../lib/agent-store'
import { OPEN_TEAMS_EVENT } from '../../lib/chromeOverlay'
import * as agentApi from '../../lib/agent-api'
import { createTeam } from '../../lib/api'
import type { Agent, DelegationEvent } from '../../types/agent'

vi.mock('../../lib/agent-api', () => ({
  fetchAgents: vi.fn(),
  fetchRoutingOptions: vi.fn(),
  fetchDelegations: vi.fn(),
  routeMessage: vi.fn(),
  fetchCliCatalog: vi.fn(),
  fetchLlmProfiles: vi.fn(),
  fetchRemoteCatalog: vi.fn(),
  launchRemoteFramework: vi.fn(),
  generateAgentQuickstarts: vi.fn(),
  createDesignedAgent: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  fetchBlueprints: vi.fn().mockResolvedValue({
    object: 'list',
    data: [{ id: 'codey', name: 'Codey', object: 'blueprint' }],
  }),
  fetchTeams: vi.fn().mockResolvedValue({
    object: 'list',
    data: [],
  }),
  createTeam: vi.fn().mockResolvedValue({
    id: 'test-team',
    name: 'test-team',
  }),
}))

const mockAgents: Record<string, Agent> = {
  router: {
    agent_id: 'router',
    name: 'Agent Router',
    specialty: 'Request routing and multi-agent coordination',
    color: '#6366f1',
    icon: '🧭',
    type: 'orchestrator',
    group: 'orchestration',
    description: 'Central router that delegates tasks to specialists'
  },
  coder: {
    agent_id: 'coder',
    name: 'Coder',
    specialty: 'Software development and bug fixes',
    color: '#f59e0b',
    icon: '💻',
    type: 'specialist',
    group: 'tools',
    description: 'Specialist for writing code and debugging'
  },
  researcher: {
    agent_id: 'researcher',
    name: 'Researcher',
    specialty: 'Fact finding and literature review',
    color: '#10b981',
    icon: '🔍',
    type: 'specialist',
    group: 'specialists',
    description: 'Specialist for deep research and synthesis'
  },
  codey: {
    agent_id: 'codey',
    name: 'Codey',
    specialty: 'Coded agent team',
    color: '#38bdf8',
    icon: '📦',
    type: 'team',
    group: 'blueprints',
    kind: 'blueprint',
    description: 'Python BlueprintBase coding team'
  },
  localGrok: {
    agent_id: 'local-grok',
    name: 'Local grok',
    specialty: 'grok CLI',
    color: '#6366f1',
    icon: '⌨️',
    type: 'specialist',
    group: 'tools',
    kind: 'cli',
    cli: 'grok',
    description: 'Host grok CLI'
  },
  hermes: {
    agent_id: 'hermes',
    name: 'Hermes',
    specialty: 'Remote Hermes agent team',
    color: '#22d3ee',
    icon: '🛰️',
    type: 'specialist',
    group: 'remote',
    kind: 'remote',
    agent_type: 'remote',
    framework: 'hermes',
    description: 'Remote Hermes team'
  },
  openmausbot: {
    agent_id: 'openmausbot',
    name: 'OpenMausBot',
    specialty: 'Remote OpenMausBot team',
    color: '#a78bfa',
    icon: '🛰️',
    type: 'specialist',
    group: 'remote',
    kind: 'remote',
    agent_type: 'remote',
    framework: 'openmausbot',
    description: 'Remote OpenMausBot team'
  },
  ombCos: {
    agent_id: 'openmausbot--cos-1',
    name: 'Chief of Staff',
    specialty: 'OpenMausBot',
    color: '#a78bfa',
    icon: '🛰️',
    type: 'specialist',
    group: 'remote',
    kind: 'remote',
    agent_type: 'remote',
    framework: 'openmausbot',
    parent_id: 'openmausbot',
    remote_id: 'cos-1',
    description: 'OMB Chief of Staff'
  },
  ombNight: {
    agent_id: 'openmausbot--night',
    name: 'Night editor',
    specialty: 'OpenMausBot',
    color: '#a78bfa',
    icon: '🛰️',
    type: 'specialist',
    group: 'remote',
    kind: 'remote',
    agent_type: 'remote',
    framework: 'openmausbot',
    parent_id: 'openmausbot',
    remote_id: 'night',
    description: 'OMB night editor'
  }
}

const mockDelegationsList: DelegationEvent[] = [
  {
    id: 'del-101',
    from_agent: 'router',
    from_agent_name: 'Agent Router',
    to_agent: 'coder',
    to_agent_name: 'Coder',
    query: 'Can you implement a queue?',
    response: 'Here is the queue implementation',
    timestamp: 1700000000
  }
]

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter>
          <AgentRouterPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}

function getChatInput() {
  return within(screen.getByRole('main')).getByPlaceholderText(/Message|Query/)
}

describe('AgentRouterPage integration', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    localStorage.clear()
    localStorage.setItem('agent_hidden_ids', '[]')
    localStorage.setItem('agent_sidebar_starters', 'support-cli-api-remote')

    useAgentStore.setState({
      agents: Object.values(mockAgents),
      selectedAgentId: 'router',
      agentStatus: {},
      unreadCounts: {},
      chiefOfStaffId: null,
      renames: {},
      purposes: {},
      customSections: {},
      favouriteIds: [],
      hiddenAgentIds: [],
      blueprintByAgent: {},
      quickstartsByAgent: {},
      sidebarOpen: true,
      sidebarDensity: 'comfortable',
      collapsedSections: [],
      searchQuery: '',
      routingStrategy: 'auto_route',
      targetAgentId: null,
      backendByAgent: {},
      delegations: [],
      selectedCommDelegation: null,
      avatarTheme: 'chassis',
      avatarThemeByAgent: {},
      avatarEyes: 'lens',
      avatarEyesByAgent: {},
      roleAssignments: {},
      defaultLlmProfile: '',
      llmProfileByAgent: {},
      cliModelByAgent: {},
      remoteMemberByAgent: {},
      frameworkByAgent: {},
      sessionMode: 'default',
      catalogAgents: Object.values(mockAgents),
      teams: [
        {
          id: 'unsaved',
          name: 'Unsaved',
          saved: false,
          agentIds: [],
          agents: [],
          renames: {},
          purposes: {},
          backends: {},
          customSections: {},
          customOrder: [],
          favouriteIds: [],
          chiefOfStaffId: null,
          avatarThemeByAgent: {},
          avatarEyesByAgent: {},
          roleAssignments: {},
          defaultLlmProfile: '',
          llmProfileByAgent: {},
          cliModelByAgent: {},
          remoteMemberByAgent: {},
          frameworkByAgent: {},
        },
      ],
      activeTeamId: 'unsaved',
    })

    vi.mocked(agentApi.fetchAgents).mockResolvedValue({
      status: 'success',
      data: {
        agents: mockAgents,
        router: 'router',
        handoff_rules: []
      }
    })

    vi.mocked(agentApi.fetchRoutingOptions).mockResolvedValue({
      status: 'success',
      data: {
        routing_strategies: [
          { id: 'auto_route', name: 'Auto Route', description: 'Auto' },
          { id: 'direct', name: 'Direct', description: 'Direct' },
          { id: 'router', name: 'Router', description: 'Router' },
          { id: 'consensus', name: 'Consensus', description: 'Consensus' }
        ],
        agents: Object.values(mockAgents)
      }
    })

    vi.mocked(agentApi.fetchDelegations).mockResolvedValue({
      status: 'success',
      delegations: mockDelegationsList
    })

    vi.mocked(agentApi.routeMessage).mockResolvedValue({
      status: 'success',
      agent: 'Coder',
      response: 'Here is the completed task response.',
      routing_decision: {
        strategy: 'auto_route',
        target_agent: 'coder',
        message: 'Routed to Coder'
      }
    })

    vi.mocked(agentApi.fetchCliCatalog).mockResolvedValue({
      status: 'success',
      clis: [{
        name: 'grok',
        executable: 'grok',
        installed: true,
        model_flag: '-m',
        models: ['grok-4.6', 'grok-4.5'],
      }],
    })
    vi.mocked(agentApi.fetchLlmProfiles).mockResolvedValue({
      status: 'success',
      default: 'auxiliary',
      profiles: [
        { name: 'auxiliary', provider: 'openai', model: 'auxiliary', base_url: 'http://198.51.100.30:8000/v1', description: '' },
        { name: 'orchestration', provider: 'openai', model: 'orchestration', base_url: 'http://198.51.100.30:8000/v1', description: '' },
      ],
    })
    vi.mocked(agentApi.fetchRemoteCatalog).mockResolvedValue({
      status: 'success',
      frameworks: [
        { id: 'hermes', name: 'Hermes', specialty: 'Remote Hermes', description: '' },
        { id: 'openmausbot', name: 'OpenMausBot', specialty: 'Remote OMB', description: '' },
        { id: 'rakazo', name: 'Rakazo', specialty: 'Remote Rakazo', description: '' },
        { id: 'herdr', name: 'Herdr', specialty: 'Herdr CLI multiplexer', description: '' },
        { id: 'dsh', name: 'DeepSeek Harness', specialty: 'DSH', description: '', ollama_available: true, launch_cmd: 'ollama launch dsh' },
      ],
    })
    vi.mocked(agentApi.generateAgentQuickstarts).mockResolvedValue({
      status: 'success',
      quickstarts: [
        { key: 'A', label: 'Explain Coder', prompt: 'Who are you as Coder?' },
        { key: 'B', label: 'Customise Coder', prompt: 'How do I customise Coder?' },
        { key: 'C', label: 'CLI for Coder', prompt: 'Does Coder need grok?' },
        { key: 'D', label: 'Remote for Coder', prompt: 'Connect Coder to Hermes?' },
      ],
    })
    vi.mocked(agentApi.launchRemoteFramework).mockResolvedValue({
      status: 'success',
      ok: true,
      launched: false,
      via: 'already-up',
      ollama: true,
      base_url: 'http://127.0.0.1:3080/v1',
    })
    vi.mocked(agentApi.createDesignedAgent).mockResolvedValue({
      status: 'success',
      agent: { agent_id: 'night-editor', name: 'Night editor', kind: 'personality' },
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders chat execution view and inspector (rail lives in the App shell)', async () => {
    renderPage()

    // #930: no nested sidebar panel — the App shell owns the rail.
    expect(screen.queryByRole('complementary', { name: 'Agent sidebar' })).not.toBeInTheDocument()

    // Main chat view
    const main = screen.getByRole('main')
    expect(main).toBeInTheDocument()
    expect(screen.getByText(/Nice to meet you/)).toBeInTheDocument()
    expect(getChatInput()).toBeInTheDocument()

    // Inspector overview
    const inspector = screen.getByRole('complementary', { name: 'Agent overview inspector' })
    expect(inspector).toBeInTheDocument()
    expect(within(inspector).getByText('Domain Specialty')).toBeInTheDocument()
  })

  it('toggles the right inspector panel open and closed', async () => {
    renderPage()

    expect(screen.getByRole('complementary', { name: 'Agent overview inspector' })).toBeInTheDocument()

    // Click header toggle button to hide inspector
    const toggleBtn = screen.getByTitle('Hide inspector')
    fireEvent.click(toggleBtn)

    expect(screen.queryByRole('complementary', { name: 'Agent overview inspector' })).not.toBeInTheDocument()

    // Click toggle button to reopen inspector
    const reopenBtn = screen.getByTitle('Show inspector')
    fireEvent.click(reopenBtn)

    expect(screen.getByRole('complementary', { name: 'Agent overview inspector' })).toBeInTheDocument()
  })

  it('displays agents from query and store, and handles agent selection', async () => {
    renderPage()

    // Catalog agents land in the shared store (starters merged in).
    await waitFor(() => {
      expect(useAgentStore.getState().agents.some((a) => a.agent_id === 'coder')).toBe(true)
    })

    const inspector = screen.getByRole('complementary', { name: 'Agent overview inspector' })
    expect(within(inspector).getByText('Central router that delegates tasks to specialists')).toBeInTheDocument()

    // Selection is driven by the shared store (the rail writes it).
    useAgentStore.getState().selectAgent('coder')

    // Coder becomes active agent, reflected in inspector identity card and specialty
    await waitFor(() => {
      expect(within(inspector).getByText('Specialist for writing code and debugging')).toBeInTheDocument()
    })
  })

  it('handles sending a message and renders assistant response', async () => {
    renderPage()

    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'Create a fibonacci generator' } })
    expect(input).toHaveValue('Create a fibonacci generator')

    fireEvent.keyDown(input, { key: 'Enter' })

    // Input should be cleared immediately
    expect(input).toHaveValue('')

    // Should render optimistic user message and placeholder
    expect(screen.getByText('Create a fibonacci generator')).toBeInTheDocument()
    expect(screen.getByText('Thinking & routing…')).toBeInTheDocument()

    // Verify routeMessage was called
    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'Create a fibonacci generator',
        routing_strategy: 'auto_route',
        target_agent: null,
        agent_ids: undefined,
        params: { backend: 'api', llm_profile: 'auxiliary' },
      })
    })

    // After mutation resolves, placeholder is replaced with response
    await waitFor(() => {
      expect(screen.getByText('Here is the completed task response.')).toBeInTheDocument()
    })
    // The placeholder message in the chat area is removed
    expect(within(screen.getByRole('main')).queryByText('Thinking & routing…')).not.toBeInTheDocument()
  })

  it('#403 header wraps backends so the agent name stays readable', async () => {
    renderPage()
    const header = await screen.findByTestId('agents-chat-header')
    expect(header.className).toMatch(/flex-wrap/)
    expect(screen.getByTestId('agents-header-backends')).toBeInTheDocument()
    const nameBtn = within(header).getByRole('button', { name: /click to edit name/i })
    expect(nameBtn.className).not.toMatch(/max-w-\[12rem\]/)
  })

  it('edits the bot name and purpose from the chat header', async () => {
    renderPage()
    const header = screen.getByRole('banner')
    const nameBtn = within(header).getByRole('button', { name: /click to edit name/i })
    fireEvent.click(nameBtn)
    const nameInput = within(header).getByLabelText('Edit name')
    fireEvent.change(nameInput, { target: { value: 'Desk chief' } })
    fireEvent.keyDown(nameInput, { key: 'Enter' })
    expect(useAgentStore.getState().renames.router).toBe('Desk chief')
    expect(within(header).getByRole('button', { name: /click to edit name/i })).toHaveTextContent('Desk chief')

    const purposeBtn = within(header).getByRole('button', { name: /click to edit purpose/i })
    fireEvent.click(purposeBtn)
    const purposeInput = within(header).getByLabelText('Edit purpose')
    fireEvent.change(purposeInput, { target: { value: 'Keep the team moving' } })
    fireEvent.blur(purposeInput)
    expect(useAgentStore.getState().purposes.router).toBe('Keep the team moving')
    expect(JSON.parse(localStorage.getItem('agent_purposes') || '{}').router).toBe('Keep the team moving')
  })

  it('lets you pick CLI vs API from the header dropdown', async () => {
    // #930: the (deleted) sidebar used to select the CLI starter; the shared
    // store performs that selection now.
    useAgentStore.setState({ selectedAgentId: 'starter-cli', targetAgentId: 'starter-cli' })
    renderPage()
    const header = screen.getByRole('banner')
    const select = await within(header).findByLabelText('Model backend')
    await waitFor(() => {
      expect(within(select).getByRole('option', { name: 'CLI · grok' })).toBeInTheDocument()
    })
    expect(within(select).getByRole('option', { name: 'CLI · agy (not installed)' })).toBeInTheDocument()
    expect(select).toHaveValue('cli:grok')

    const modelSelect = await within(header).findByLabelText('CLI model')
    expect(within(modelSelect).getByRole('option', { name: 'grok-4.5' })).toBeInTheDocument()
    fireEvent.change(modelSelect, { target: { value: 'grok-4.5' } })
    expect(useAgentStore.getState().cliModelByAgent['starter-cli']).toBe('grok-4.5')

    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'use grok' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'use grok',
        routing_strategy: 'direct',
        target_agent: 'starter-cli',
        agent_ids: undefined,
        params: { backend: 'cli', cli: 'grok', cli_model: 'grok-4.5' },
      })
    })
  })

  it('defaults OpenMausBot remote member to Chief of Staff and routes remote_id', async () => {
    useAgentStore.setState({ selectedAgentId: 'openmausbot', targetAgentId: 'openmausbot' })
    renderPage()
    const header = screen.getByRole('banner')
    const memberSelect = await within(header).findByLabelText('Remote member')
    expect(memberSelect).toHaveValue('cos-1')
    fireEvent.change(memberSelect, { target: { value: 'night' } })
    expect(useAgentStore.getState().remoteMemberByAgent.openmausbot).toBe('night')

    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'ask night' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'ask night',
        routing_strategy: 'direct',
        target_agent: 'openmausbot',
        agent_ids: undefined,
        params: { backend: 'remote', remote_id: 'night', target: 'night', model: 'night', framework: 'openmausbot' },
      })
    })
  })

  it('lets you set a default LLM and override it per agent', async () => {
    renderPage()
    const header = screen.getByRole('banner')
    const defaultSelect = await within(header).findByLabelText('Default LLM')
    await waitFor(() => {
      expect(within(defaultSelect).getByRole('option', { name: 'LiteLLM · orchestration' })).toBeInTheDocument()
    })
    fireEvent.change(defaultSelect, { target: { value: 'orchestration' } })
    expect(useAgentStore.getState().defaultLlmProfile).toBe('orchestration')

    const llmSelect = within(header).getByLabelText('LLM profile')
    expect(llmSelect).toHaveDisplayValue('LiteLLM · orchestration (default)')
    fireEvent.change(llmSelect, { target: { value: 'auxiliary' } })
    expect(useAgentStore.getState().llmProfileByAgent.router).toBe('auxiliary')

    fireEvent.change(getChatInput(), { target: { value: 'plan it' } })
    fireEvent.keyDown(getChatInput(), { key: 'Enter' })
    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'plan it',
        routing_strategy: 'auto_route',
        target_agent: null,
        agent_ids: undefined,
        params: { backend: 'api', llm_profile: 'auxiliary' },
      })
    })
  })

  it('sends CLI and remote agents with Direct routing', async () => {
    useAgentStore.setState({ selectedAgentId: 'local-grok', targetAgentId: 'local-grok' })
    renderPage()

    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'hi grok' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'hi grok',
        routing_strategy: 'direct',
        target_agent: 'local-grok',
        agent_ids: undefined,
        params: { backend: 'cli', cli: 'grok' },
      })
    })

    vi.mocked(agentApi.routeMessage).mockClear()
    useAgentStore.setState({ selectedAgentId: 'hermes', targetAgentId: 'hermes' })
    fireEvent.change(getChatInput(), { target: { value: 'hi hermes' } })
    fireEvent.keyDown(getChatInput(), { key: 'Enter' })

    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'hi hermes',
        routing_strategy: 'direct',
        target_agent: 'hermes',
        agent_ids: undefined,
        params: { backend: 'remote', framework: 'hermes' },
      })
    })
  })

  it('handles message send error gracefully and sets agent status to error', async () => {
    vi.mocked(agentApi.routeMessage).mockRejectedValueOnce(new Error('Network gateway timeout'))

    renderPage()

    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'Failing query' } })

    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(screen.getByText('Error processing request: Network gateway timeout')).toBeInTheDocument()
    })
    // Agent status in store should be error
    expect(useAgentStore.getState().agentStatus['router']).toBe('error')
  })

  it('allows strategy switching and modifies routing behavior', async () => {
    renderPage()

    const header = screen.getByRole('banner')
    // Strategy pills should no longer be in the header navbar
    expect(within(header).queryByRole('button', { name: 'Auto Route' })).toBeNull()
    expect(within(header).queryByRole('button', { name: 'Direct' })).toBeNull()
    expect(within(header).queryByRole('button', { name: 'Router' })).toBeNull()
    expect(within(header).queryByRole('button', { name: /Consensus/i })).toBeNull()

    // #984: the strategy selector is page-owned in the composer dock — the
    // deleted sidebar used to host the pills, and the redesigned TeamsSheet
    // (#763) is a registry that no longer carries them.
    const strategy = screen.getByRole('combobox', { name: 'Routing strategy' })
    expect(strategy).toHaveValue('auto_route')

    // 1. Switch to Direct
    fireEvent.change(strategy, { target: { value: 'direct' } })
    expect(useAgentStore.getState().routingStrategy).toBe('direct')
    expect(screen.getByPlaceholderText(/Message .* directly…/i)).toBeInTheDocument()

    // 2. Switch to Consensus
    fireEvent.change(strategy, { target: { value: 'consensus' } })
    expect(useAgentStore.getState().routingStrategy).toBe('consensus')
    expect(screen.getByPlaceholderText(/Query the multi-agent consensus panel…/i)).toBeInTheDocument()

    // 3. Send message with consensus strategy
    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'Consensus decision request' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(agentApi.routeMessage).toHaveBeenCalledWith({
        message: 'Consensus decision request',
        routing_strategy: 'consensus',
        target_agent: null,
        agent_ids: ['researcher', 'writer', 'analyst', 'coder'],
        params: { backend: 'api', llm_profile: 'auxiliary' },
      })
    })

    // 4. Switch to Router
    fireEvent.change(strategy, { target: { value: 'router' } })
    expect(useAgentStore.getState().routingStrategy).toBe('router')

    // 5. Switch back to Auto Route
    fireEvent.change(strategy, { target: { value: 'auto_route' } })
    expect(useAgentStore.getState().routingStrategy).toBe('auto_route')
  })

  it('hide all keeps starters and drops selection onto Support (store doctrine)', async () => {
    renderPage()
    // #930: hide-all lives in the store; the (deleted) sidebar only rendered it.
    await waitFor(() => {
      expect(useAgentStore.getState().agents.some((a) => a.agent_id === 'starter-support')).toBe(true)
    })
    useAgentStore.getState().hideAllAgents()
    const state = useAgentStore.getState()
    expect(state.hiddenAgentIds.length).toBeGreaterThan(0)
    for (const id of ['starter-support', 'starter-cli', 'starter-api', 'starter-remote']) {
      expect(state.hiddenAgentIds).not.toContain(id)
      expect(state.agents.some((a) => a.agent_id === id)).toBe(true)
    }
    expect(state.selectedAgentId).toBe('starter-support')
    expect(state.agents.some((a) => a.agent_id === 'coder' && state.hiddenAgentIds.includes('coder'))).toBe(true)
  })

  it('Shift+Tab cycles Default → Plan → Auto-edit', async () => {
    renderPage()
    const mode = screen.getByRole('button', { name: 'Session mode' })
    expect(mode).toHaveTextContent('Default')
    const input = getChatInput()
    fireEvent.keyDown(input, { key: 'Tab', shiftKey: true })
    expect(mode).toHaveTextContent('Plan')
    fireEvent.keyDown(input, { key: 'Tab', shiftKey: true })
    expect(mode).toHaveTextContent('Auto-edit')
    fireEvent.keyDown(input, { key: 'Tab', shiftKey: true })
    expect(mode).toHaveTextContent('Default')
  })

  it('Support quickstart pills start the journey', async () => {
    useAgentStore.setState({ selectedAgentId: 'starter-support', targetAgentId: 'starter-support' })
    renderPage()
    const pill = await screen.findByRole('button', { name: /Create a team/i })
    fireEvent.click(pill)
    expect(getChatInput()).toHaveValue(
      'Create a team: walk me through a local roster of personas, optional Chief of Staff, then Save as team. Chat stays the main view.',
    )
    expect(screen.getByRole('button', { name: /Add a remote/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Wire a CLI/i })).toBeInTheDocument()
  })

  it('populates input from quick prompt starter pill', async () => {
    renderPage()

    const pill = screen.getByRole('button', { name: /Explain Operating Swarm/i })
    fireEvent.click(pill)

    const input = getChatInput()
    expect(input).toHaveValue(
      'Explain Operating Swarm: what it is, how agents, teams, and blueprints fit together, and how I talk to them here.',
    )
  })

  it('generates per-agent quickstart overrides from name and purpose', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Generate quickstarts' }))
    await waitFor(() => {
      expect(agentApi.generateAgentQuickstarts).toHaveBeenCalled()
    })
    expect(screen.getByRole('button', { name: /Explain Coder/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Explain Coder/i }))
    expect(getChatInput()).toHaveValue('Who are you as Coder?')
  })

  it('clears conversation messages when clear button is clicked', async () => {
    renderPage()

    const input = getChatInput()
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(screen.getByText('Here is the completed task response.')).toBeInTheDocument()
    })

    // Clear messages button should appear
    const clearBtn = screen.getByTitle('Clear conversation')
    expect(clearBtn).toBeInTheDocument()

    fireEvent.click(clearBtn)

    // Message should be gone and welcome hub restored
    expect(screen.queryByText('Here is the completed task response.')).not.toBeInTheDocument()
    expect(screen.getByText(/Nice to meet you/)).toBeInTheDocument()
  })

  it('opens and closes bot communication popup when clicking timeline delegation', async () => {
    renderPage()

    // Wait for delegations to populate timeline
    await waitFor(() => {
      expect(screen.getByText('Agent Router → Coder')).toBeInTheDocument()
    })

    // Click delegation item in inspector timeline
    fireEvent.click(screen.getByText('Agent Router → Coder'))

    // Popup modal should open
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(within(dialog).getByText('Bot-to-Bot Delegation')).toBeInTheDocument()
    expect(within(dialog).getByText('Can you implement a queue?')).toBeInTheDocument()

    // Close the popup modal
    const closeBtn = within(dialog).getByRole('button', { name: 'Close dialog' })
    fireEvent.click(closeBtn)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('lists discovered blueprints as coded-team agents in the store', async () => {
    renderPage()
    // #930: blueprint discovery feeds the shared roster the rail renders.
    await waitFor(() => {
      const codey = useAgentStore.getState().agents.find((a) => a.agent_id === 'codey')
      expect(codey).toBeDefined()
      expect(codey?.kind).toBe('blueprint')
    })
  })

  it('opens the agent designer with API, CLI, and remote types', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'New agent' }))
    const dialog = await screen.findByRole('dialog', { name: 'Design agent' })
    expect(within(dialog).getByText('LiteLLM (API)')).toBeInTheDocument()
    expect(within(dialog).getByText('CLI agent')).toBeInTheDocument()
    expect(within(dialog).getByText('Coded blueprint')).toBeInTheDocument()
    expect(within(dialog).getByText('Remote team')).toBeInTheDocument()
    expect(within(dialog).queryByText('Single personality')).not.toBeInTheDocument()
  })

  it('seeds API swarm design with the Dev team of 3 example', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'New agent' }))
    const dialog = await screen.findByRole('dialog', { name: 'Design agent' })
    fireEvent.click(within(dialog).getByText('LiteLLM (API)'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use Dev team of 3' }))
    expect(within(dialog).getByDisplayValue('Dev team of 3')).toBeInTheDocument()
    expect(within(dialog).getByDisplayValue('Chief of Staff')).toBeInTheDocument()
    expect(within(dialog).getByDisplayValue('Engineer')).toBeInTheDocument()
    expect(within(dialog).getByDisplayValue('Skeptic')).toBeInTheDocument()
    expect(within(dialog).getByRole('textbox', { name: 'Persona 1 name' })).toHaveDisplayValue(
      'Chief of Staff',
    )
    expect(within(dialog).getByRole('textbox', { name: 'Persona 1 instructions' })).toBeInTheDocument()
  })

  it('saves the current agents as a named team and reloads Unsaved', async () => {
    renderPage()

    // Team selection is no longer in top navbar header
    const header = screen.getByRole('banner')
    expect(within(header).queryByRole('combobox', { name: 'Team' })).toBeNull()

    // #984: the Teams overlay is a registry (redesigned by #763) — browsing
    // registered teams and creating new ones. The save-current-selection
    // flow lives in TeamComposer (#780), not here.
    fireEvent(window, new Event(OPEN_TEAMS_EVENT))
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByRole('button', { name: '+ New Team' })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '+ New Team' }))

    const form = await within(dialog).findByRole('form', { name: 'Create team' })
    fireEvent.change(within(form).getByRole('textbox', { name: 'Team name' }), {
      target: { value: 'Night shift' },
    })
    fireEvent.submit(within(form).getByRole('button', { name: 'Create team' }))

    await waitFor(() => {
      expect(createTeam).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Night shift' }),
        expect.anything(),
      )
    })
  })

  it('compacts earlier turns into a rectangular summary and can show originals', async () => {
    vi.mocked(agentApi.routeMessage)
      .mockResolvedValueOnce({
        status: 'success',
        agent: 'Coder',
        response: 'First answer',
        routing_decision: { strategy: 'auto_route', target_agent: 'coder', message: 'a' },
      })
      .mockResolvedValueOnce({
        status: 'success',
        agent: 'Coder',
        response: 'Second answer',
        routing_decision: { strategy: 'auto_route', target_agent: 'coder', message: 'b' },
      })
      .mockResolvedValueOnce({
        status: 'success',
        agent: 'Agent Router',
        response: 'Prior work summarized.',
        routing_decision: { strategy: 'direct', target_agent: 'router', message: 'summary' },
      })

    renderPage()
    fireEvent.change(getChatInput(), { target: { value: 'first task' } })
    fireEvent.keyDown(getChatInput(), { key: 'Enter' })
    await screen.findByText('First answer')
    fireEvent.change(getChatInput(), { target: { value: 'second task' } })
    fireEvent.keyDown(getChatInput(), { key: 'Enter' })
    await screen.findByText('Second answer')

    const compactBtns = screen.getAllByRole('button', { name: 'Compact to here' })
    fireEvent.click(compactBtns[0])

    await screen.findByText('Conversation summary')
    expect(screen.getByText('Prior work summarized.')).toBeInTheDocument()
    const summaryCard = screen.getByText('Prior work summarized.').closest('div')
    expect(summaryCard?.className).toContain('rounded-none')

    fireEvent.click(screen.getByRole('button', { name: 'View original messages' }))
    expect(await screen.findByRole('dialog', { name: 'Original messages' })).toHaveTextContent('first task')
  })

  it('assigns a socratic skeptic who auto-replies after a generation', async () => {
    vi.mocked(agentApi.routeMessage)
      .mockResolvedValueOnce({
        status: 'success',
        agent: 'Coder',
        response: 'Here is the completed task response.',
        routing_decision: { strategy: 'direct', target_agent: 'coder', message: 'done' },
      })
      .mockResolvedValueOnce({
        status: 'success',
        agent: 'Researcher',
        response: 'What assumption did you skip?',
        routing_decision: { strategy: 'direct', target_agent: 'researcher', message: 'skeptic' },
      })

    renderPage()
    const inspector = await screen.findByRole('complementary', { name: 'Agent overview inspector' })
    useAgentStore.getState().selectAgent('coder')
    await waitFor(() => {
      expect(within(inspector).getByText('Specialist for writing code and debugging')).toBeInTheDocument()
    })
    const skepticSelect = within(inspector).getByLabelText('Socratic skeptic')
    fireEvent.change(skepticSelect, { target: { value: 'researcher' } })
    expect(useAgentStore.getState().roleAssignments.coder.socratic_skeptic).toBe('researcher')

    fireEvent.change(getChatInput(), { target: { value: 'Ship it' } })
    fireEvent.keyDown(getChatInput(), { key: 'Enter' })
    await screen.findByText('Here is the completed task response.')
    expect(await screen.findByText('What assumption did you skip?')).toBeInTheDocument()
    expect(agentApi.routeMessage).toHaveBeenCalledTimes(2)
  })

  it('prevents auto-hiding 96 agents and keeps catalog agents visible on clean load', async () => {
    localStorage.clear()
    useAgentStore.setState({
      agents: Object.values(mockAgents),
      selectedAgentId: 'router',
      favouriteIds: [],
      hiddenAgentIds: [],
    })

    renderPage()
    // #930: visibility is store truth — clean load must not auto-hide anyone.
    await waitFor(() => {
      expect(useAgentStore.getState().agents.some((a) => a.agent_id === 'coder')).toBe(true)
    })
    const state = useAgentStore.getState()
    expect(state.hiddenAgentIds).toEqual([])
    expect(state.agents.some((a) => a.agent_id === 'researcher')).toBe(true)
  })

  it('unhides deep-linked agent if it was previously hidden', async () => {
    localStorage.clear()
    useAgentStore.setState({
      agents: Object.values(mockAgents),
      selectedAgentId: 'router',
      hiddenAgentIds: ['coder'],
      favouriteIds: [],
    })

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/agents?agent=coder']}>
          <ToastProvider>
            <AgentRouterPage />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(useAgentStore.getState().selectedAgentId).toBe('coder')
    })
    expect(useAgentStore.getState().hiddenAgentIds).not.toContain('coder')
  })
})

describe('#930: single sidebar doctrine', () => {
  it('renders no nested AgentSidebar inside AgentRouterPage', () => {
    renderPage()
    // The duplicate sidebar rendered its own searchbox and a "Focused" rail
    // section; neither may exist inside the /agents page anymore.
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    expect(screen.queryByText('Focused')).not.toBeInTheDocument()
  })

  it('new-agent creation is reachable from the page header', () => {
    renderPage()
    fireEvent.click(screen.getByTestId('agents-new-agent-button'))
    // AgentDesigner overlay opens rather than relying on the removed sidebar.
    expect(screen.getByTestId('agents-new-agent-button')).toBeInTheDocument()
  })
})
