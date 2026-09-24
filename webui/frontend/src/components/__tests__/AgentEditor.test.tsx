import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import SettingsSheet, { OPEN_SETTINGS_EVENT, type OpenSettingsDetail } from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import { AGENT_EDITS_KEY, assignedBlueprintId, loadAgentEdit } from '../../lib/agentEdits'
import { AGENT_REMOTE_BINDINGS_KEY } from '../../lib/agentRemote'

/** #1127: the editor is a vertical-tab surface — tests navigate like users. */
function openEditorTab(name: string | RegExp) {
  fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name }))
}

const catalog = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
  {
    id: 'stewie',
    object: 'blueprint' as const,
    name: 'Stewie',
    description: 'Helpful agent',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
  {
    id: 'fixture_gate',
    object: 'blueprint' as const,
    name: 'Fixture Gate',
    description: 'REQ-75 fixture',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    role: 'gate',
  },
  {
    id: 'django_chat',
    object: 'blueprint' as const,
    name: 'Django Chat',
    description: 'HTTP-only leftover',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    webui: true,
  },
]

function stubCatalog() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/skills')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              {
                name: 'conventional-commit',
                id: 'conventional-commit',
                description: 'Write a conventional commit.',
                path: 'skills/conventional-commit/SKILL.md',
                assets: [],
              },
            ],
          }),
        } as Response
      }
      if (url.includes('/v1/models')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [{ id: 'default', object: 'model', created: 0, owned_by: 'swarm' }],
          }),
        } as Response
      }
      if (url.includes('/v1/blueprints') && url.includes('/source')) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ error: 'blueprint not found' }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: catalog }),
      } as Response
    }),
  )
}

function renderEditor({
  isOpen = true,
  agentId = 'support',
}: {
  isOpen?: boolean
  agentId?: string
} = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const onClose = vi.fn()
  const view = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen={isOpen} onClose={onClose} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...view, onClose, client }
}

function EditorThenSettings({ agentId = 'support' }: { agentId?: string }) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsBlueprintId, setSettingsBlueprintId] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(true)

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<OpenSettingsDetail>).detail
      setSettingsBlueprintId(detail?.blueprintId ?? null)
      setSettingsOpen(true)
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen)
  }, [])

  return (
    <ToastProvider>
      <AgentEditor isOpen={editorOpen} onClose={() => setEditorOpen(false)} agentId={agentId} />
      <SettingsSheet
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        blueprintId={settingsBlueprintId}
      />
    </ToastProvider>
  )
}

describe('AgentEditor (REQ-58)', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
    localStorage.removeItem(AGENT_REMOTE_BINDINGS_KEY)
    vi.unstubAllGlobals()
  })

  it('attaches a discovered skill on an API / Blueprint seat', async () => {
    stubCatalog()
    renderEditor({ agentId: 'codey' })
    const checkbox = await screen.findByTestId('agent-skill-conventional-commit')
    fireEvent.click(checkbox)
    expect(loadAgentEdit('codey').skills).toEqual(['conventional-commit'])
  })

  it('is agent-scoped: name, role, blueprint picker — no Remotes or System nav', async () => {
    stubCatalog()
    renderEditor()

    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    expect(dialog).toHaveClass('modal')
    expect(within(dialog).getByLabelText('Name')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Role')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Blueprint')).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Remotes' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'System' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: /CLI catalog/i })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('navigation', { name: 'Settings sections' })).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Hermes')).not.toBeInTheDocument()
    openEditorTab(/Model & inference/i)
    expect(await within(dialog).findByRole('button', { name: /Edit blueprint/i })).toBeInTheDocument()
  })

  it('REQ-170: when name equals the recipe, Blueprint is secondary Recipe meta', async () => {
    stubCatalog()
    renderEditor({ agentId: 'codey' })

    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    await waitFor(() => {
      expect(within(dialog).getByLabelText('Name')).toHaveValue('Codey')
    })
    expect(within(dialog).getByTestId('blueprint-recipe-meta')).toHaveTextContent('Recipe: codey')
    expect(within(dialog).queryByText('Blueprint', { selector: 'label' })).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText('Blueprint')).toHaveValue('codey')

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Desk' } })
    expect(within(dialog).queryByTestId('blueprint-recipe-meta')).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText('Blueprint')).toBeInTheDocument()
  })

  it('assigns a blueprint from the picker and persists it on that agent', async () => {
    stubCatalog()
    renderEditor({ agentId: 'support' })

    openEditorTab(/Model & inference/i)
    const picker = await screen.findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: 'Codey' })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'codey' } })
    expect(assignedBlueprintId('support')).toBe('codey')
    expect(JSON.parse(localStorage.getItem(AGENT_EDITS_KEY) || '{}').support.blueprintId).toBe(
      'codey',
    )
    expect(picker).toHaveValue('codey')
  })

  it('REQ-75: picking a gate fixture applies the Gate role; webui kind is absent', async () => {
    stubCatalog()
    renderEditor({ agentId: 'codey' })

    openEditorTab(/Model & inference/i)
    const picker = await screen.findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: /Fixture Gate/ })).toBeInTheDocument()
    })
    expect(within(picker).queryByRole('option', { name: /Django Chat/ })).not.toBeInTheDocument()
    fireEvent.change(picker, { target: { value: 'fixture_gate' } })
    expect(assignedBlueprintId('codey')).toBe('fixture_gate')
    expect(loadAgentEdit('codey').role).toBe('gate')
    expect(screen.getByLabelText('Role')).toHaveValue('gate')
    expect(screen.getByTestId('role-override-rule').textContent).toMatch(/wins over the blueprint default/i)
  })

  it('REQ-75: editor role override survives a later blueprint re-pick', async () => {
    stubCatalog()
    renderEditor({ agentId: 'codey' })

    const roleSelect = await screen.findByLabelText('Role')
    fireEvent.change(roleSelect, { target: { value: 'skeptic' } })
    expect(loadAgentEdit('codey').roleOverridden).toBe(true)

    openEditorTab(/Model & inference/i)
    const picker = screen.getByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: /Fixture Gate/ })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'fixture_gate' } })
    expect(assignedBlueprintId('codey')).toBe('fixture_gate')
    expect(loadAgentEdit('codey').role).toBe('skeptic')
    expect(screen.getByLabelText('Role')).toHaveValue('skeptic')
  })

  it('Edit blueprint opens Settings → Blueprints with the assigned item selected', async () => {
    stubCatalog()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <EditorThenSettings agentId="support" />
      </QueryClientProvider>,
    )

    openEditorTab(/Model & inference/i)
    const picker = await screen.findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: 'Codey' })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'codey' } })
    fireEvent.click(screen.getByRole('button', { name: /Edit blueprint/i }))

    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    const nav = within(settings).getByRole('navigation', { name: 'Settings sections' })
    expect(within(nav).getByRole('button', { name: 'Blueprints' })).toHaveClass('menu-active')
    expect(within(nav).getByRole('button', { name: 'Remotes' })).toBeInTheDocument()

    const list = within(settings).getByRole('listbox', { name: 'Blueprints' })
    const selected = within(list).getByRole('option', { name: 'Codey' })
    expect(selected).toHaveAttribute('aria-selected', 'true')
    expect(selected).toHaveClass('menu-active')
    expect(within(list).getByRole('option', { name: 'Support' })).toHaveAttribute(
      'aria-selected',
      'false',
    )
  })

  describe('AgentEditor role explanations & LLM override by kind (REQ-124)', () => {
    it('shows role explanation blurb and updates on change', async () => {
      stubCatalog()
      renderEditor({ agentId: 'codey' })

      const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
      const explanation = within(dialog).getByTestId('role-explanation')
      expect(explanation).toBeInTheDocument()
      expect(explanation.textContent).toMatch(/worker blueprint/i)

      const roleSelect = within(dialog).getByLabelText('Role')
      fireEvent.change(roleSelect, { target: { value: 'support' } })
      expect(explanation.textContent).toMatch(/Support is Socratic/i)

      fireEvent.change(roleSelect, { target: { value: 'gate' } })
      expect(explanation.textContent).toMatch(/Gate is a YES\/NO/i)

      fireEvent.change(roleSelect, { target: { value: 'skeptic' } })
      expect(explanation.textContent).toMatch(/Skeptic is a bounded retry/i)

      fireEvent.change(roleSelect, { target: { value: 'suggestions' } })
      expect(explanation.textContent).toMatch(/quick-select/i)
    })

    it('remote agent: LLM override is disabled with explanation', async () => {
      stubCatalog()
      renderEditor({ agentId: 'remote-omb' })

      const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
      openEditorTab(/Advanced/i)
      expect(within(dialog).getByText(/Remotes keep their own models/i)).toBeInTheDocument()
      expect(within(dialog).queryByRole('combobox', { name: /CLI override/i })).not.toBeInTheDocument()
      expect(within(dialog).queryByRole('combobox', { name: /API profile override/i })).not.toBeInTheDocument()
    })

    it('remote agent: requires picking a configured remote', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
          const url = String(input)
          if (url.includes('/v1/remotes')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
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
              }),
            } as Response
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: catalog }),
          } as Response
        }),
      )
      renderEditor({ agentId: 'remote-omb' })
      const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
      openEditorTab(/Advanced/i)
      const select = await within(dialog).findByRole('combobox', { name: 'Remote' })
      expect(within(select).getByRole('option', { name: 'default' })).toBeInTheDocument()
      expect(within(select).getByRole('option', { name: 'OpenMousBot' })).toBeInTheDocument()
      expect(within(select).queryByRole('option', { name: 'No remotes' })).not.toBeInTheDocument()
    })

    it('CLI agent: renders CLIs and models, not agents from catalog', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
          const url = String(input)
          if (url.includes('/v1/cli-agents/copilot/models/')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                cli: 'copilot',
                models: ['gpt-4o', 'o1-mini'],
              }),
            } as Response
          }
          if (url.includes('/v1/cli-agents/')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                clis: ['copilot', 'claude-cli'],
                native_consensus: {},
                catalog: {},
              }),
            } as Response
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: catalog }),
          } as Response
        }),
      )

      renderEditor({ agentId: 'cli_agent' })
      const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
      openEditorTab(/Advanced/i)

      const cliSelect = await within(dialog).findByRole('combobox', { name: 'CLI override' })
      expect(within(cliSelect).getByRole('option', { name: 'copilot' })).toBeInTheDocument()
      expect(within(cliSelect).getByRole('option', { name: 'claude-cli' })).toBeInTheDocument()
      // Agents must NOT be listed
      expect(within(cliSelect).queryByRole('option', { name: 'Codey' })).not.toBeInTheDocument()
      expect(within(cliSelect).queryByRole('option', { name: 'Stewie' })).not.toBeInTheDocument()

      const modelSelect = await within(dialog).findByRole('combobox', { name: 'Model override' })
      await waitFor(() => {
        expect(within(modelSelect).getByRole('option', { name: 'gpt-4o' })).toBeInTheDocument()
      })
      expect(within(modelSelect).queryByRole('option', { name: 'Codey' })).not.toBeInTheDocument()
      expect(within(modelSelect).queryByRole('option', { name: 'Stewie' })).not.toBeInTheDocument()

      expect(within(dialog).getByTestId('default-llm-label')).toBeInTheDocument()
      expect(within(dialog).getByTestId('agent-workspace-binding')).toBeInTheDocument()
      expect(within(dialog).getByTestId('input-cli-folder')).toBeInTheDocument()
      expect(within(dialog).getByText(/Working directory for this CLI agent/i)).toBeInTheDocument()
      expect(within(dialog).getByTestId('toggle-workspaces')).toBeDisabled()

      // Save override
      fireEvent.change(cliSelect, { target: { value: 'copilot' } })
      fireEvent.change(modelSelect, { target: { value: 'gpt-4o' } })
      fireEvent.change(within(dialog).getByTestId('input-cli-folder'), {
        target: { value: '/home/dev/tool' },
      })
      fireEvent.change(within(dialog).getByTestId('input-github-repo'), {
        target: { value: 'acme/app' },
      })
      const stored = JSON.parse(localStorage.getItem(AGENT_EDITS_KEY) || '{}')['cli_agent']
      expect(stored.cliOverride).toBe('copilot')
      expect(stored.llmOverride).toBe('gpt-4o')
      expect(stored.folder).toBe('/home/dev/tool')
      expect(stored.githubRepo).toBe('acme/app')
    })

    it('API agent: renders profiles and models, not agents from catalog', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
          const url = String(input)
          if (url.includes('/v1/llm-profiles/')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                object: 'llm_profiles',
                profiles: [
                  { id: 'custom-profile', name: 'Custom Profile', model: 'gpt-4o' },
                ],
                default_llm_profile: 'orchestration',
                task_llm_profiles: {},
              }),
            } as Response
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: catalog }),
          } as Response
        }),
      )

      renderEditor({ agentId: 'codey' })
      const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
      openEditorTab(/Advanced/i)

      const profileSelect = await within(dialog).findByRole('combobox', { name: 'API profile override' })
      expect(within(profileSelect).getByRole('option', { name: /User chat \/ orchestration/i })).toBeInTheDocument()
      expect(within(profileSelect).getByRole('option', { name: 'Custom Profile' })).toBeInTheDocument()

      const modelSelect = await within(dialog).findByRole('combobox', { name: 'Model override' })
      expect(within(modelSelect).getByRole('option', { name: 'gpt-4o' })).toBeInTheDocument()
      // Bug fixed: Agent names filtered out
      expect(within(modelSelect).queryByRole('option', { name: 'codey' })).not.toBeInTheDocument()
      expect(within(modelSelect).queryByRole('option', { name: 'stewie' })).not.toBeInTheDocument()

      expect(within(dialog).getByTestId('default-llm-label')).toHaveTextContent(/Default would be:\s*orchestration/i)
      expect(within(dialog).getByTestId('agent-workspace-binding')).toHaveAttribute(
        'data-workspace-kind',
        'api',
      )
      expect(within(dialog).getByTestId('workspace-kind-stub')).toBeInTheDocument()

      // Save override
      fireEvent.change(profileSelect, { target: { value: 'custom-profile' } })
      fireEvent.change(modelSelect, { target: { value: 'gpt-4o' } })
      const stored = JSON.parse(localStorage.getItem(AGENT_EDITS_KEY) || '{}')['codey']
      expect(stored.profileOverride).toBe('custom-profile')
      expect(stored.llmOverride).toBe('gpt-4o')

      // Clear restores default
      fireEvent.change(profileSelect, { target: { value: '' } })
      fireEvent.change(modelSelect, { target: { value: '' } })
      const cleared = JSON.parse(localStorage.getItem(AGENT_EDITS_KEY) || '{}')['codey']
      expect(cleared?.profileOverride).toBeUndefined()
      expect(cleared?.llmOverride).toBeUndefined()
    })
  })
})
