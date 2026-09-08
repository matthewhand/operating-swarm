import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AddAgentWizard from '../AddAgentWizard'
import * as api from '../../lib/api'
import { OPENMOUSBOT_LABEL } from '../../lib/remotesCatalog'
import * as agentEdits from '../../lib/agentEdits'

function renderWizard(props: Partial<Parameters<typeof AddAgentWizard>[0]> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  const onClose = vi.fn()
  const onCreated = vi.fn()
  const onSelectAgent = vi.fn()

  const view = render(
    <QueryClientProvider client={queryClient}>
      <AddAgentWizard
        isOpen={true}
        onClose={onClose}
        onCreated={onCreated}
        onSelectAgent={onSelectAgent}
        {...props}
      />
    </QueryClientProvider>,
  )

  return { ...view, onClose, onCreated, onSelectAgent, queryClient }
}

describe('AddAgentWizard (REQ-109, REQ-165, REQ-167)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    vi.spyOn(api, 'fetchBlueprints').mockResolvedValue({ object: 'list', data: [] })
    vi.spyOn(api, 'fetchCustomBlueprints').mockResolvedValue({ object: 'list', data: [] })
    vi.spyOn(api, 'fetchCliAgents').mockResolvedValue({
      clis: [],
      native_consensus: {},
      catalog: {},
      rail: [],
    })
    vi.spyOn(api, 'fetchRemotes').mockResolvedValue({
      object: 'list',
      kinds: [{ id: 'omb', label: 'OpenMousBot' }],
      configured: [],
      data: [],
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders four agent kinds; Remote tab lists impls, not a Herdr kind', async () => {
    renderWizard()

    expect(screen.getByTestId('add-agent-wizard')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-cli')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-api')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-blueprint')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-blueprint')).toHaveTextContent('Blueprint')
    expect(screen.getByTestId('kind-option-remote')).toBeInTheDocument()
    expect(screen.queryByTestId('kind-option-herdr')).not.toBeInTheDocument()
    expect(screen.getByTestId('kind-option-remote')).toHaveTextContent('Remote')

    fireEvent.click(screen.getByTestId('kind-option-remote'))
    const implSelect = await screen.findByTestId('select-remote-kind')
    expect(within(implSelect).getByRole('option', { name: OPENMOUSBOT_LABEL })).toBeInTheDocument()
    expect(within(implSelect).getByRole('option', { name: 'Hermes' })).toBeInTheDocument()
    expect(within(implSelect).getByRole('option', { name: 'Herdr' })).toBeInTheDocument()
    expect(within(implSelect).queryByRole('option', { name: 'Generic Remote Agent' })).not.toBeInTheDocument()
    expect(screen.queryByText(/^OMB$/)).not.toBeInTheDocument()
  })

  it('shows manage surface on choosing CLI or API, with empty state when none exist', () => {
    renderWizard()

    // Select CLI kind -> shows manage surface
    fireEvent.click(screen.getByTestId('kind-option-cli'))
    expect(screen.getByTestId('manage-agent-surface')).toBeInTheDocument()
    expect(screen.getByText(/No CLI agents yet/i)).toBeInTheDocument()
    expect(screen.getByTestId('empty-add-btn')).toBeInTheDocument()
  })

  it('navigates to configure form from empty manage state and cancels back', () => {
    const { onClose, onCreated } = renderWizard()

    // Select CLI kind to see manage surface
    fireEvent.click(screen.getByTestId('kind-option-cli'))
    expect(screen.getByTestId('empty-add-btn')).toBeInTheDocument()

    // Click Add CLI Agent
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    expect(screen.getByTestId('add-agent-form')).toBeInTheDocument()

    // Click Cancel returns to manage surface (Cancel leaves no changes)
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.getByTestId('manage-agent-surface')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('creates a CLI agent with optional Folder field on happy-path submit', async () => {
    const createSpy = vi.spyOn(api, 'createCustomBlueprint').mockResolvedValue({
      id: 'custom_cli_agent',
      name: 'My CLI Tool',
      description: 'CLI: custom-tool',
      category: 'cli',
      tags: ['cli'],
      requirements: '',
      code: '# CLI agent: My CLI Tool\n# Command: custom-tool\n# Folder: /home/dev/tool\n',
      required_mcp_servers: [],
      env_vars: [],
    })

    const { onCreated, onClose } = renderWizard()

    // Select CLI -> manage surface -> Add new
    fireEvent.click(screen.getByTestId('kind-option-cli'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    expect(screen.getByTestId('input-cli-name')).toBeInTheDocument()

    expect(screen.getByTestId('agent-workspace-binding')).toBeInTheDocument()
    expect(screen.getByTestId('input-cli-folder')).toBeInTheDocument()
    expect(screen.getByText(/Working directory for this CLI agent/i)).toBeInTheDocument()
    expect(screen.getByTestId('input-github-repo')).toBeInTheDocument()
    expect(screen.getByTestId('toggle-workspaces')).toBeDisabled()

    // Fill in inputs
    fireEvent.change(screen.getByTestId('input-cli-name'), {
      target: { value: 'My CLI Tool' },
    })
    fireEvent.change(screen.getByTestId('input-cli-command'), {
      target: { value: 'custom-tool' },
    })
    fireEvent.change(screen.getByTestId('input-cli-folder'), {
      target: { value: '/home/dev/tool' },
    })
    fireEvent.change(screen.getByTestId('input-github-repo'), {
      target: { value: 'acme/app' },
    })

    // Submit
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'My CLI Tool',
          category: 'cli',
          kind: 'cli',
          command: 'custom-tool',
          rail: true,
          source: 'add-agent',
          code: expect.stringContaining('# Folder: /home/dev/tool'),
        }),
      )
      expect(onCreated).toHaveBeenCalledWith({
        id: 'custom_cli_agent',
        name: 'My CLI Tool',
        kind: 'cli',
      })
      expect(onClose).toHaveBeenCalled()
      expect(agentEdits.loadAgentEdit('custom_cli_agent')).toEqual(
        expect.objectContaining({
          folder: '/home/dev/tool',
          githubRepo: 'acme/app',
        }),
      )
    })
  })

  it('creates a Blueprint agent on happy-path submit', async () => {
    const createSpy = vi.spyOn(api, 'createCustomBlueprint').mockResolvedValue({
      id: 'custom_bp_agent',
      name: 'Release Captain',
      description: 'Coordinates releases',
      category: 'blueprint',
      tags: ['blueprint'],
      requirements: '',
      code: '# Blueprint: Release Captain\n',
      required_mcp_servers: [],
      env_vars: [],
    })

    const { onCreated, onClose } = renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-blueprint'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    expect(screen.getByTestId('input-blueprint-name')).toBeInTheDocument()
    expect(screen.getByTestId('input-blueprint-prompt')).toBeInTheDocument()

    fireEvent.change(screen.getByTestId('input-blueprint-name'), {
      target: { value: 'Release Captain' },
    })

    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Release Captain',
          category: 'blueprint',
          kind: 'blueprint',
          rail: true,
          source: 'add-agent',
        }),
      )
      expect(onCreated).toHaveBeenCalledWith({
        id: 'custom_bp_agent',
        name: 'Release Captain',
        kind: 'blueprint',
      })
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('shows inline error on invalid folder path format', () => {
    renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-cli'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))

    // Type invalid folder path with wildcard character
    fireEvent.change(screen.getByTestId('input-cli-folder'), {
      target: { value: '/invalid/*/path' },
    })

    expect(screen.getByTestId('folder-error')).toBeInTheDocument()
    expect(screen.getByTestId('submit-create-agent')).toBeDisabled()
  })

  it('shows inline repo format error and coming-soon workspace chrome on CLI', () => {
    renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-cli'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))

    expect(screen.getByTestId('workspace-folder-empty')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('input-github-repo'), {
      target: { value: 'not a repo' },
    })
    expect(screen.getByTestId('repo-error')).toBeInTheDocument()
    expect(screen.getByTestId('submit-create-agent')).toBeDisabled()
    expect(screen.getByTestId('toggle-workspaces')).toBeDisabled()
  })

  it('shows coming-soon workspace stub on API and Remote kinds', () => {
    renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-api'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    expect(screen.getByTestId('agent-workspace-binding')).toHaveAttribute(
      'data-workspace-kind',
      'api',
    )
    expect(screen.getByTestId('workspace-kind-stub')).toBeInTheDocument()
    expect(screen.queryByTestId('input-cli-folder')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('kind-option-remote'))
    expect(screen.getByTestId('agent-workspace-binding')).toHaveAttribute(
      'data-workspace-kind',
      'remote',
    )
    expect(screen.getByTestId('workspace-kind-stub')).toBeInTheDocument()
  })

  it('creates an API agent on happy-path submit', async () => {
    const createSpy = vi.spyOn(api, 'createCustomBlueprint').mockResolvedValue({
      id: 'api_researcher',
      name: 'Researcher',
      description: 'Deep market research',
      category: 'ai_assistants',
      tags: ['api'],
      requirements: '',
      code: 'You are a researcher',
      required_mcp_servers: [],
      env_vars: [],
    })

    const { onCreated, onClose } = renderWizard()

    // Select API -> manage surface -> Add new
    fireEvent.click(screen.getByTestId('kind-option-api'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    expect(screen.getByTestId('input-api-name')).toBeInTheDocument()

    // Fill in inputs
    fireEvent.change(screen.getByTestId('input-api-name'), {
      target: { value: 'Researcher' },
    })
    fireEvent.change(screen.getByTestId('input-api-prompt'), {
      target: { value: 'You are a researcher' },
    })

    // Submit
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Researcher',
          category: 'ai_assistants',
          kind: 'api',
          rail: true,
          source: 'add-agent',
        }),
      )
      expect(onCreated).toHaveBeenCalledWith({
        id: 'api_researcher',
        name: 'Researcher',
        kind: 'api',
      })
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('lists existing agents with Open and Edit actions', async () => {
    vi.spyOn(api, 'fetchCustomBlueprints').mockResolvedValue({
      object: 'list',
      data: [
        {
          id: 'custom_cli_1',
          name: 'My Custom CLI',
          description: 'CLI tool',
          category: 'cli',
          tags: ['cli'],
          requirements: '',
          code: '# CLI agent: My Custom CLI\n# Command: my-cli\n# Folder: /tmp/my-cli\n',
          required_mcp_servers: [],
          env_vars: [],
        },
      ],
    })

    const { onSelectAgent, onClose } = renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-cli'))

    await waitFor(() => {
      expect(screen.getByTestId('manage-agent-list')).toBeInTheDocument()
      expect(screen.getByText('My Custom CLI')).toBeInTheDocument()
      expect(screen.getByTestId('open-agent-custom_cli_1')).toBeInTheDocument()
      expect(screen.getByTestId('edit-agent-custom_cli_1')).toBeInTheDocument()
    })

    // Click Open -> selects agent and closes
    fireEvent.click(screen.getByTestId('open-agent-custom_cli_1'))
    expect(onSelectAgent).toHaveBeenCalledWith('custom_cli_1')
    expect(onClose).toHaveBeenCalled()
  })

  it('edits an existing agent and saves changes', async () => {
    vi.spyOn(api, 'fetchCustomBlueprints').mockResolvedValue({
      object: 'list',
      data: [
        {
          id: 'custom_cli_1',
          name: 'My Custom CLI',
          description: 'CLI tool',
          category: 'cli',
          tags: ['cli'],
          requirements: '',
          code: '# CLI agent: My Custom CLI\n# Command: my-cli\n# Folder: /tmp/my-cli\n',
          required_mcp_servers: [],
          env_vars: [],
        },
      ],
    })

    const updateSpy = vi.spyOn(api, 'updateCustomBlueprint').mockResolvedValue({
      id: 'custom_cli_1',
      name: 'Updated CLI Tool',
      description: 'Updated description',
      category: 'cli',
      tags: ['cli'],
      requirements: '',
      code: '# CLI agent: Updated CLI Tool\n# Command: updated-cli\n# Folder: /home/repo\n',
      required_mcp_servers: [],
      env_vars: [],
    })

    renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-cli'))

    await waitFor(() => {
      expect(screen.getByTestId('edit-agent-custom_cli_1')).toBeInTheDocument()
    })

    // Click Edit
    fireEvent.click(screen.getByTestId('edit-agent-custom_cli_1'))
    expect(screen.getByTestId('add-agent-form')).toBeInTheDocument()
    expect(screen.getByTestId('input-cli-name')).toHaveValue('My Custom CLI')

    // Modify fields
    fireEvent.change(screen.getByTestId('input-cli-name'), {
      target: { value: 'Updated CLI Tool' },
    })
    fireEvent.change(screen.getByTestId('input-cli-command'), {
      target: { value: 'updated-cli' },
    })
    fireEvent.change(screen.getByTestId('input-cli-folder'), {
      target: { value: '/home/repo' },
    })

    // Save changes
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'custom_cli_1',
        expect.objectContaining({
          name: 'Updated CLI Tool',
          code: expect.stringContaining('# Folder: /home/repo'),
        }),
      )
      // Returns to manage surface
      expect(screen.getByTestId('manage-agent-surface')).toBeInTheDocument()
    })
  })

  it('connects a Remote agent on happy-path submit', async () => {
    const createRemoteSpy = vi.spyOn(api, 'createRemote').mockResolvedValue({
      id: 'omb-remote-1',
      kind: 'omb',
      base_url: 'http://localhost:8000',
      agents: [],
      configured: true,
      created: 123456,
      object: 'remote',
    } as any)

    const { onCreated, onClose } = renderWizard()

    // Select Remote -> configure form
    fireEvent.click(screen.getByTestId('kind-option-remote'))
    expect(screen.getByTestId('input-remote-url')).toBeInTheDocument()

    // Fill in URL
    fireEvent.change(screen.getByTestId('input-remote-url'), {
      target: { value: 'http://localhost:8000' },
    })

    // Submit
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(createRemoteSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'omb',
          base_url: 'http://localhost:8000',
        }),
      )
      expect(onCreated).toHaveBeenCalledWith({
        id: 'omb-remote-1',
        name: OPENMOUSBOT_LABEL,
        kind: 'remote',
      })
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('requires picking a configured remote when remotes already exist', async () => {
    vi.spyOn(api, 'fetchRemotes').mockResolvedValue({
      object: 'list',
      kinds: [{ id: 'omb', label: 'OpenMousBot' }],
      configured: [
        {
          id: 'omb',
          kind: 'omb',
          label: 'OpenMousBot',
          title: 'OpenMousBot',
          host_label: '',
          base_url: 'http://127.0.0.1:8802',
          source: 'config',
        },
      ],
    })
    const createRemoteSpy = vi.spyOn(api, 'createRemote')
    const { onCreated, onClose } = renderWizard()

    fireEvent.click(screen.getByTestId('kind-option-remote'))
    const select = await screen.findByRole('combobox', { name: 'Remote' })
    expect(within(select).getByRole('option', { name: 'Pick a remote' })).toBeInTheDocument()
    // REQ-184: Add-new fields are visible on the same tab alongside configured remotes
    expect(screen.getByTestId('input-remote-url')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('submit-create-agent'))
    expect(await screen.findByText(/Select a configured remote/i)).toBeInTheDocument()
    expect(createRemoteSpy).not.toHaveBeenCalled()

    fireEvent.change(select, { target: { value: 'omb' } })
    fireEvent.click(screen.getByTestId('submit-create-agent'))
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith({
        id: 'omb',
        name: 'OpenMousBot',
        kind: 'remote',
      })
      expect(onClose).toHaveBeenCalled()
    })
    expect(createRemoteSpy).not.toHaveBeenCalled()
  })

  describe('REQ-184: Add-agent wizard tabs + manage + create on same view', () => {
    it('switches between tabs and shows both existing list and create section on each tab', async () => {
      vi.spyOn(api, 'fetchCustomBlueprints').mockResolvedValue({
        object: 'list',
        data: [
          {
            id: 'custom_cli_tool',
            name: 'CLI Helper',
            description: 'Helper binary',
            category: 'cli',
            tags: ['cli'],
            requirements: '',
            code: '# CLI agent: CLI Helper\n# Command: cli-helper\n',
            required_mcp_servers: [],
            env_vars: [],
          },
          {
            id: 'custom_api_assistant',
            name: 'API Assistant',
            description: 'Assistant bot',
            category: 'ai_assistants',
            tags: ['api'],
            requirements: '',
            code: 'Instructions',
            required_mcp_servers: [],
            env_vars: [],
          },
        ],
      })
      vi.spyOn(api, 'fetchRemotes').mockResolvedValue({
        object: 'list',
        kinds: [{ id: 'omb', label: 'OpenMousBot' }],
        configured: [
          {
            id: 'omb_remote',
            kind: 'omb',
            label: 'OpenMousBot Live',
            title: 'OpenMousBot Live',
            host_label: '',
            base_url: 'http://127.0.0.1:8802',
            source: 'config',
          },
        ],
      })

      renderWizard()

      // 1. Initial tab is CLI: has tabs, manage section with existing CLI item, and create form
      expect(screen.getByTestId('kind-option-cli')).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByTestId('manage-agent-surface')).toBeInTheDocument()
      await waitFor(() => {
        expect(screen.getByText('CLI Helper')).toBeInTheDocument()
      })
      expect(screen.getByTestId('add-agent-form')).toBeInTheDocument()
      expect(screen.getByTestId('input-cli-name')).toBeInTheDocument()

      // 2. Switch to API tab: shows API existing item and API create form
      fireEvent.click(screen.getByTestId('kind-option-api'))
      expect(screen.getByTestId('kind-option-api')).toHaveAttribute('aria-selected', 'true')
      await waitFor(() => {
        expect(screen.getByText('API Assistant')).toBeInTheDocument()
      })
      expect(screen.getByTestId('add-agent-form')).toBeInTheDocument()
      expect(screen.getByTestId('input-api-name')).toBeInTheDocument()

      // 3. Switch to Remote tab: shows configured remote item, OpenMousBot copy, and remote inputs
      fireEvent.click(screen.getByTestId('kind-option-remote'))
      expect(screen.getByTestId('kind-option-remote')).toHaveAttribute('aria-selected', 'true')
      await waitFor(() => {
        expect(screen.getByTestId('agent-row-omb_remote')).toBeInTheDocument()
      })
      expect(screen.getByTestId('input-remote-url')).toBeInTheDocument()
      expect(screen.getByTestId('select-remote-kind')).toBeInTheDocument()
      expect(screen.queryByText(/^OMB$/)).not.toBeInTheDocument()
    })

    it('allows canceling edit mode to return to create mode without closing modal', async () => {
      vi.spyOn(api, 'fetchCustomBlueprints').mockResolvedValue({
        object: 'list',
        data: [
          {
            id: 'custom_cli_1',
            name: 'Tool One',
            description: 'Tool',
            category: 'cli',
            tags: ['cli'],
            requirements: '',
            code: '# CLI agent: Tool One\n# Command: tool-one\n',
            required_mcp_servers: [],
            env_vars: [],
          },
        ],
      })

      const { onClose } = renderWizard()

      await waitFor(() => {
        expect(screen.getByTestId('edit-agent-custom_cli_1')).toBeInTheDocument()
      })

      // Click Edit
      fireEvent.click(screen.getByTestId('edit-agent-custom_cli_1'))
      expect(screen.getByTestId('cancel-edit-btn')).toBeInTheDocument()
      expect(screen.getByTestId('input-cli-name')).toHaveValue('Tool One')

      // Click Cancel edit
      fireEvent.click(screen.getByTestId('cancel-edit-btn'))
      expect(screen.queryByTestId('cancel-edit-btn')).not.toBeInTheDocument()
      expect(screen.getByTestId('input-cli-name')).toHaveValue('')
      expect(onClose).not.toHaveBeenCalled()
    })
  })

  it('REQ-171B: shows an honest error when CLI create is rejected without a command', async () => {
    const createSpy = vi.spyOn(api, 'createCustomBlueprint').mockRejectedValue(
      new api.ApiError(
        400,
        'CLI command is required. Enter a binary or command the AGENTS rail can list, or choose API instead.',
      ),
    )

    const { onCreated } = renderWizard()
    fireEvent.click(screen.getByTestId('kind-option-cli'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    fireEvent.change(screen.getByTestId('input-cli-name'), {
      target: { value: 'Blank CLI' },
    })
    fireEvent.change(screen.getByTestId('input-cli-command'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(screen.getByText(/CLI command or binary is required/i)).toBeInTheDocument()
    })
    expect(createSpy).not.toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('REQ-171B: surfaces backend kind-rejected copy', async () => {
    vi.spyOn(api, 'createCustomBlueprint').mockRejectedValue(
      new api.ApiError(
        400,
        'Add-agent custom seats only support CLI or API. Use Remotes for remote harnesses.',
      ),
    )

    const { onCreated } = renderWizard()
    fireEvent.click(screen.getByTestId('kind-option-api'))
    fireEvent.click(screen.getByTestId('empty-add-btn'))
    fireEvent.change(screen.getByTestId('input-api-name'), {
      target: { value: 'Bad Kind' },
    })
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(
        screen.getByText(/Add-agent custom seats only support CLI or API/i),
      ).toBeInTheDocument()
    })
    expect(onCreated).not.toHaveBeenCalled()
  })
})
