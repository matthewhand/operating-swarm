import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import {
  BUMP_COMPLETED_KEY,
  HOSTNAME_OVERRIDE_KEY,
  RETENTION_MODE_KEY,
} from '../../lib/settingsPrefs'
import { HOSTNAME_CHANGED_EVENT } from '../../lib/hostname'

function renderSheet({
  isOpen = true,
  blueprintId,
  initialSection,
  definitionKind,
  definitionId,
}: {
  isOpen?: boolean
  blueprintId?: string
  initialSection?: 'definition' | 'blueprint'
  definitionKind?: 'role' | 'blueprint' | 'team'
  definitionId?: string
} = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const onClose = vi.fn()
  const view = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet
          isOpen={isOpen}
          onClose={onClose}
          blueprintId={blueprintId}
          initialSection={initialSection}
          definitionKind={definitionKind}
          definitionId={definitionId}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...view, onClose, client }
}

describe('SettingsSheet', () => {
  afterEach(() => {
    localStorage.removeItem(HOSTNAME_OVERRIDE_KEY)
    localStorage.removeItem(RETENTION_MODE_KEY)
    localStorage.removeItem(BUMP_COMPLETED_KEY)
    localStorage.removeItem('swarm_theme')
    localStorage.removeItem('swarm_theme_navbar')
    localStorage.removeItem('swarm_mcp_servers')
    vi.unstubAllGlobals()
  })

  it('opens as a DaisyUI modal-end dialog with menu sections', () => {
    renderSheet()
    const dialog = screen.getByRole('dialog', { hidden: true })
    expect(dialog).toHaveClass('modal')
    expect(dialog).toHaveClass('modal-end')
    expect(dialog).not.toHaveClass('drawer')
    expect(dialog.className).not.toMatch(/btn-group/)

    const remotesToggle = screen.getByRole('button', { name: 'Remotes' })
    expect(remotesToggle).not.toHaveClass('menu-dropdown-toggle')
    expect(screen.getByRole('button', { name: 'General' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Definition' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Blueprints' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hermes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'OMB' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rakazo' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retention' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hostname' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show LLM profiles' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'MCP servers' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CLI agents' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Roles' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rail' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Image generation' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Speech' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Plugins' })).toBeInTheDocument()
  })

  it('defaults the rail bump toggle on and persists off', () => {
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Rail' }))
    const toggle = screen.getByRole('checkbox', { name: 'Bump completed agents to top' })
    expect(toggle).toBeChecked()
    fireEvent.click(toggle)
    expect(toggle).not.toBeChecked()
    expect(localStorage.getItem(BUMP_COMPLETED_KEY)).toBe('0')
  })

  it('adds a local MCP server from Plugins without storing secrets', async () => {
    const servers: Record<string, unknown>[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method || 'GET').toUpperCase()
        if (url.includes('/v1/mcp-plugins/') && method === 'POST' && !url.includes('discover')) {
          const body = JSON.parse(String(init?.body || '{}'))
          servers.push({
            name: String(body.name || '')
              .trim()
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, '-'),
            label: body.name,
            kind: body.kind,
            enabled: true,
            command: body.command || '',
            args: body.args || [],
            url: '',
            env: {},
            headers: {},
            provides: body.provides || [],
            note: body.note || '',
            tools: [],
          })
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'mcp_plugins', scope: 'global_servers_per_chat_tools', servers }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'mcp_plugins', scope: 'global_servers_per_chat_tools', servers }),
        } as Response
      }),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Plugins' }))
    expect(screen.getByTestId('os-plugins-settings')).toHaveTextContent(/never paste a token/i)
    fireEvent.click(screen.getByRole('button', { name: 'Fetch' }))
    expect(await screen.findByRole('list', { name: 'Configured MCP servers' })).toHaveTextContent('Fetch')
    expect(localStorage.getItem('swarm_mcp_servers') || '').not.toMatch(/api[_-]?key|token|secret/i)
  })

  it('shows remotes empty state and honest server link for retention', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          kinds: [
            { id: 'hermes', label: 'Hermes' },
            { id: 'omb', label: 'OpenMousBot' },
            { id: 'rakazo', label: 'Rakazo' },
            { id: 'swarm', label: 'Swarm' },
          ],
          configured: [],
          data: [],
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))
    expect(await screen.findByRole('button', { name: /Add remote/i })).toBeInTheDocument()
    expect(screen.getByText(/No remotes configured/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hermes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'OMB' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rakazo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Swarm' })).not.toBeInTheDocument()
    expect(screen.queryByText(/\bOMB\b/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Kind' }), {
      target: { value: 'swarm' },
    })
    expect(screen.getByText(/do not add this instance as its own remote/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retention' }))
    expect(screen.getByRole('heading', { name: 'Retention' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save retention' })).not.toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Server retention dashboard/i })
    expect(link).toHaveAttribute('href', '/settings/#chat-retention-title')
  })

  it('LLM profiles shows the empty-models copy when /v1/llm-profiles/ returns none', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'llm_profiles',
          profiles: [],
          default_llm_profile: '',
          default_is_auto: true,
          override_per_task: false,
          task_llm_profiles: {},
          auto_picks: {},
          warnings: [],
          routes: {},
          task_classes: ['orchestration', 'auxiliary', 'delegation'],
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    expect(await screen.findByRole('heading', { name: 'LLM profiles' })).toBeInTheDocument()
    expect(await screen.findByText(/No connected models yet/i)).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'No models connected' })).toBeInTheDocument()
  })

  it('LLM profiles shows the operator fallback when /v1/llm-profiles/ errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: 'down' }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    expect(
      await screen.findByText(/Could not load configured profiles/i, undefined, { timeout: 4000 }),
    ).toBeInTheDocument()
  })

  it('opens Roles without unmounting the settings sheet when /v1/roles/ is malformed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/roles')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [{ id: 'support', name: 'Support', description: 'Helper' }],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Roles' }))
    expect(await screen.findByTestId('settings-roles-pane')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { hidden: true })).toHaveClass('modal-open')
    expect(screen.queryByText(/Something went wrong/i)).not.toBeInTheDocument()
  })

  it('adds an OpenMousBot remote then lists it in Settings and the dropdown', async () => {
    const configured: Array<Record<string, unknown>> = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method || 'GET').toUpperCase()
        if (url.includes('/v1/remotes/') && method === 'POST') {
          const body = JSON.parse(String(init?.body || '{}')) as { kind?: string }
          const created = {
            id: body.kind || 'omb',
            kind: body.kind || 'omb',
            label: body.kind === 'omb' ? 'OpenMousBot' : body.kind,
            title: 'OpenMousBot',
            host_label: '',
            base_url: 'http://127.0.0.1:8802',
            source: 'config',
          }
          configured.push(created)
          return { ok: true, status: 201, json: async () => created } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            kinds: [
              { id: 'hermes', label: 'Hermes' },
              { id: 'omb', label: 'OpenMousBot' },
              { id: 'rakazo', label: 'Rakazo' },
            ],
            configured,
            data: [],
          }),
        } as Response
      }),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))
    fireEvent.click(await screen.findByRole('button', { name: /Add remote/i }))
    const kindSelect = await screen.findByRole('combobox', { name: 'Kind' })
    expect(within(kindSelect).getByRole('option', { name: 'OpenMousBot' })).toBeInTheDocument()
    fireEvent.change(kindSelect, { target: { value: 'omb' } })
    expect(kindSelect).toHaveValue('omb')
    fireEvent.change(screen.getByRole('textbox', { name: 'URL' }), {
      target: { value: 'http://127.0.0.1:8802' },
    })
    fireEvent.submit(kindSelect.closest('form') as HTMLFormElement)

    const rows = await screen.findByRole('list', { name: 'Configured remotes' })
    expect(within(rows).getByText('OpenMousBot')).toBeInTheDocument()
    expect(within(rows).getByText('http://127.0.0.1:8802')).toBeInTheDocument()
    const remoteSelect = screen.getByRole('combobox', { name: 'Remote' })
    expect(within(remoteSelect).getByRole('option', { name: 'OpenMousBot' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'OMB' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'OMB' })).not.toBeInTheDocument()
  })

  it('health, list bots, and send on an added OpenMousBot remote', async () => {
    const configured: Array<Record<string, unknown>> = [
      {
        id: 'omb',
        kind: 'omb',
        label: 'OpenMousBot',
        title: 'OpenMousBot',
        host_label: '',
        base_url: 'http://127.0.0.1:8802',
        source: 'config',
        api_key_env: 'OMB_API_KEY',
      },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method || 'GET').toUpperCase()
        if (url.includes('/health/') && method === 'POST') {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              remote: 'omb',
              ok: true,
              state: 'UP',
              detail: 'OpenMousBot /api/health',
            }),
          } as Response
        }
        if (url.includes('/operate/') && method === 'POST') {
          const body = JSON.parse(String(init?.body || '{}')) as { op?: string }
          if (body.op === 'send') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                remote: 'omb',
                op: 'send',
                ok: true,
                detail: 'started OpenMousBot turn',
              }),
            } as Response
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              remote: 'omb',
              op: 'list',
              ok: true,
              detail: 'OpenMousBot listed 1 bot(s)',
              data: { bots: [{ id: 'bot-9', name: 'alpha' }] },
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            kinds: [{ id: 'omb', label: 'OpenMousBot' }],
            configured,
            data: configured,
          }),
        } as Response
      }),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))
    expect(await screen.findByRole('heading', { name: 'OpenMousBot' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'OMB' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Health' }))
    expect(await screen.findByText('UP')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'List bots' }))
    expect(await screen.findByText(/bot-9/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Message' }), {
      target: { value: 'hello' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/started OpenMousBot turn/)).toBeInTheDocument()
    expect(screen.queryByText(/\bOMB\b/)).not.toBeInTheDocument()
  })

  it('shows honest retention pane linking to server dashboard without placebo save button (REQ-188B-1)', async () => {
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Retention' }))
    expect(screen.getByRole('heading', { name: 'Retention' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save retention' })).not.toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Server retention dashboard/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/settings/#chat-retention-title')
  })

  it('persists a hostname override, toasts on save, and dispatches HOSTNAME_CHANGED_EVENT (REQ-188B-2)', async () => {
    let dispatchedHost = ''
    const onHostChanged = (event: Event) => {
      dispatchedHost = (event as CustomEvent<{ hostname: string }>).detail?.hostname ?? ''
    }
    window.addEventListener(HOSTNAME_CHANGED_EVENT, onHostChanged)

    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Hostname' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Hostname override' }), {
      target: { value: 'swarm.example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save hostname' }))
    expect(localStorage.getItem(HOSTNAME_OVERRIDE_KEY)).toBe('swarm.example.com')
    expect(await screen.findByText('Hostname saved')).toBeInTheDocument()
    expect(dispatchedHost).toBe('swarm.example.com')

    window.removeEventListener(HOSTNAME_CHANGED_EVENT, onHostChanged)
  })

  it('lists configured profiles and persists the Default picker', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/v1/llm-profiles') && method === 'PATCH') {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'llm_profiles',
            profiles: [
              { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
              { id: 'gpt-4o-mini', object: 'llm_profile', source: 'config', owned_by: 'openai' },
            ],
            default_llm_profile: body.default_llm_profile,
            default_is_auto: false,
            override_per_task: Boolean(body.override_per_task),
            task_llm_profiles: body.task_llm_profiles || {},
            auto_picks: { default: 'gpt-5.6-terra' },
            warnings: [],
            routes: {},
            task_classes: ['orchestration', 'auxiliary', 'delegation'],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'llm_profiles',
          profiles: [
            { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
            { id: 'gpt-4o-mini', object: 'llm_profile', source: 'config', owned_by: 'openai' },
          ],
          default_llm_profile: 'gpt-5.6-terra',
          default_is_auto: true,
          override_per_task: false,
          task_llm_profiles: {
            orchestration: 'gpt-5.6-terra',
            auxiliary: 'gpt-4o-mini',
            delegation: 'gpt-5.6-terra',
          },
          auto_picks: { default: 'gpt-5.6-terra', auxiliary: 'gpt-4o-mini' },
          warnings: [],
          routes: {},
          task_classes: ['orchestration', 'auxiliary', 'delegation'],
          provenance: {
            default_llm_profile: {
              kind: 'overrides_env',
              label: 'Overrides env DEFAULT_LLM',
              env_var: 'DEFAULT_LLM',
              helper: '.env still has DEFAULT_LLM; this instance uses Settings.',
            },
          },
        }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    expect(await screen.findByRole('list', { name: 'Configured LLM profiles' })).toBeInTheDocument()
    expect(await screen.findByTestId('rate-limits-llm-gpt-4o-mini')).toBeInTheDocument()
    expect(screen.getByTestId('rate-limits-llm-gpt-4o-mini').textContent).not.toMatch(/Django/i)
    expect(await screen.findByText('Overrides env DEFAULT_LLM')).toBeInTheDocument()
    const defaultSelect = await screen.findByLabelText('Default')
    expect(defaultSelect).toHaveValue('gpt-5.6-terra')
    fireEvent.change(defaultSelect, { target: { value: 'gpt-4o-mini' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save LLM profiles' }))
    expect(await screen.findByText('LLM profiles saved')).toBeInTheDocument()
    const patchCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/v1/llm-profiles') && call[1]?.method === 'PATCH',
    )
    expect(patchCall).toBeTruthy()
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      default_llm_profile: 'gpt-4o-mini',
      override_per_task: false,
    })
  })

  it('hides the per-task map when override is off', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'llm_profiles',
          profiles: [
            { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
            { id: 'o3', object: 'llm_profile', source: 'config', owned_by: 'openai' },
          ],
          default_llm_profile: 'gpt-5.6-terra',
          default_is_auto: false,
          override_per_task: false,
          task_llm_profiles: { delegation: 'o3' },
          auto_picks: { default: 'gpt-5.6-terra' },
          warnings: [],
          routes: {},
          task_classes: ['orchestration', 'auxiliary', 'delegation'],
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    expect(await screen.findByLabelText('Default')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Override per task' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    expect(screen.queryByLabelText('Delegation (design / coding)')).not.toBeInTheDocument()
  })

  it('shows the per-task map when override is on', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'llm_profiles',
          profiles: [
            { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
            { id: 'o3', object: 'llm_profile', source: 'config', owned_by: 'openai' },
          ],
          default_llm_profile: 'gpt-5.6-terra',
          default_is_auto: false,
          override_per_task: true,
          task_llm_profiles: {
            orchestration: 'gpt-5.6-terra',
            auxiliary: 'gpt-5.6-terra',
            delegation: 'o3',
          },
          auto_picks: { default: 'gpt-5.6-terra' },
          warnings: [],
          routes: {},
          task_classes: ['orchestration', 'auxiliary', 'delegation'],
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    expect(await screen.findByLabelText('Delegation (design / coding)')).toHaveValue('o3')
    expect(screen.getByLabelText('Auxiliary (code summary)')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Override per task' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('strips REQ ticket jargon from list-models status copy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'llm_profiles',
          profiles: [],
          default_llm_profile: '',
          default_is_auto: true,
          override_per_task: false,
          task_llm_profiles: {},
          auto_picks: {},
          warnings: ['No connected cli_agents; skipped REQ-44 list-models probe.'],
          routes: {},
          task_classes: ['orchestration', 'auxiliary', 'delegation'],
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/CLI/i)
    expect(alert).not.toHaveTextContent(/REQ-/)
    expect(alert).not.toHaveTextContent(/#\d+/)
  })

  it('warns when a selected profile is missing from the catalog', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'llm_profiles',
          profiles: [
            { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
          ],
          default_llm_profile: 'missing-slug',
          default_is_auto: false,
          override_per_task: false,
          task_llm_profiles: {},
          auto_picks: { default: 'gpt-5.6-terra' },
          warnings: ["LLM profile 'missing-slug' not found; falling back to 'gpt-5.6-terra'."],
          routes: {},
          task_classes: ['orchestration', 'auxiliary', 'delegation'],
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Show LLM profiles' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/missing-slug/)
    expect(screen.getByRole('alert')).toHaveTextContent(/gpt-5.6-terra/)
  })

  it('calls onClose from the sheet Close button', () => {
    const { onClose } = renderSheet()
    fireEvent.click(screen.getByRole('button', { name: /^Close$/ }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('shows a System section with local store facts and no Django copy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          path: '~/share/swarm/store.db',
          size_bytes: 13_002_342,
          size_label: '12.4 MB',
          created: true,
          conversation_count: 3,
          message_count: 11,
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'System' }))
    const heading = await screen.findByRole('heading', { name: 'System' })
    expect(await screen.findByText('12.4 MB')).toBeInTheDocument()
    expect(screen.getByText('~/share/swarm/store.db')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('11')).toBeInTheDocument()
    expect(screen.getByText(/local database on this machine/i)).toBeInTheDocument()
    const pane = heading.closest('section')
    const copy = pane?.textContent ?? ''
    expect(copy).not.toMatch(/Django/i)
    expect(copy).not.toMatch(/sqlite3/i)
    expect(copy).not.toMatch(/\bORM\b/i)
  })

  it('shows 0 and not created yet when the local store is missing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          created: false,
          size_bytes: 0,
          path: '',
          conversation_count: 0,
          message_count: 0,
        }),
      } as Response),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'System' }))
    expect((await screen.findAllByText('not created yet')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Conversations').closest('div')).toHaveTextContent('0')
    expect(screen.getByText('Messages').closest('div')).toHaveTextContent('0')
    const pane = screen.getByRole('heading', { name: 'System' }).closest('section')
    expect(pane?.textContent).not.toMatch(/Django/i)
  })

  it('displays an error alert and retry button when /v1/system/ fails instead of painting empty store (REQ-188C-2)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/system')) {
          return {
            ok: false,
            status: 500,
            statusText: 'Internal Server Error',
            json: async () => ({ error: 'daemon error' }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', kinds: [], configured: [], data: [] }),
        } as Response
      }),
    )
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'System' }))
    expect(await screen.findByTestId('system-store-error')).toBeInTheDocument()
    expect(
      screen.getByText(/Failed to load local database facts. Check local daemon connection./i),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByText('not created yet')).not.toBeInTheDocument()
  })

  it('keeps the Django operator dump link', () => {
    renderSheet()
    expect(screen.getByRole('link', { name: 'Operator dump' })).toHaveAttribute(
      'href',
      '/settings/',
    )
  })
})

describe('SettingsSheet blueprint editor', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens as a DaisyUI modal-end sheet selected to Blueprint', () => {
    renderSheet({ blueprintId: 'gate' })
    const dialog = screen.getByRole('dialog', { hidden: true })
    expect(dialog).toHaveClass('modal')
    expect(dialog).toHaveClass('modal-end')
    expect(dialog).not.toHaveClass('drawer')
    expect(screen.getByRole('button', { name: 'Blueprints' })).toHaveClass('menu-active')
    expect(screen.getByRole('heading', { name: 'Blueprints' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Blueprint' })).toBeInTheDocument()
  })

  it('selects the assigned blueprint in the Blueprints list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/source')) {
          return { ok: false, status: 404, json: async () => ({}) } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              {
                id: 'codey',
                object: 'blueprint',
                name: 'Codey',
                description: 'Code assistant',
                abbreviation: null,
                required_mcp_servers: [],
                tags: [],
                installed: true,
                compiled: true,
              },
            ],
          }),
        } as Response
      }),
    )
    renderSheet({ blueprintId: 'codey' })
    const list = await screen.findByRole('listbox', { name: 'Blueprints' })
    const selected = await within(list).findByRole('option', { name: 'Codey' })
    expect(selected).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument()
  })

  it('REQ-75: catalog shows a role badge and omits a webui kind', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/source')) {
          return { ok: false, status: 404, json: async () => ({}) } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              {
                id: 'fixture_gate',
                object: 'blueprint',
                name: 'Fixture Gate',
                description: 'REQ-75 fixture',
                abbreviation: null,
                required_mcp_servers: [],
                tags: [],
                installed: true,
                compiled: true,
                role: 'gate',
              },
              {
                id: 'django_chat',
                object: 'blueprint',
                name: 'Django Chat',
                description: 'HTTP-only leftover',
                abbreviation: null,
                required_mcp_servers: [],
                tags: [],
                installed: true,
                compiled: true,
                webui: true,
              },
            ],
          }),
        } as Response
      }),
    )
    renderSheet({ blueprintId: 'fixture_gate' })
    const list = await screen.findByRole('listbox', { name: 'Blueprints' })
    const gated = await within(list).findByRole('option', { name: 'Fixture Gate' })
    expect(gated).toHaveAttribute('data-role', 'gate')
    expect(within(gated).getByText('Gate')).toHaveClass('os-agent-role-badge')
    expect(within(list).queryByRole('option', { name: 'Django Chat' })).not.toBeInTheDocument()
  })

  it('shows highlighted gate YES/NO Python when source is missing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'blueprint not found' }),
      } as Response),
    )
    renderSheet({ blueprintId: 'gate' })
    const code = await screen.findByLabelText(/Safety blueprint Python/i)
    expect(code).toHaveClass('os-code-python')
    expect(code.textContent).toMatch(/YES/)
    expect(code.textContent).toMatch(/NO/)
    expect(code.querySelector('.os-py-kw')).toBeTruthy()
    expect(screen.getByTitle('src/swarm/core/tool_gate.py')).toHaveTextContent('tool_gate')
    expect(screen.queryByText(/Teams drop-zone/i)).not.toBeInTheDocument()
  })

  it('shows skeptic retry recipe', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'blueprint not found' }),
      } as Response),
    )
    renderSheet({ blueprintId: 'skeptic' })
    const code = await screen.findByLabelText(/Skeptic blueprint Python/i)
    expect(code.textContent).toMatch(/SKEPTIC_MAX_RETRIES/)
    expect(code.textContent).toMatch(/retry/)
  })

  it('renders live source when the API returns Python', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'support',
          files: [{ name: 'blueprint_support.py', path: 'blueprint_support.py' }],
          primary: 'blueprint_support.py',
          selected: 'blueprint_support.py',
          content: 'def ask_user(question):\n    return question\n',
        }),
      } as Response),
    )
    renderSheet({ blueprintId: 'support' })
    const code = await screen.findByLabelText(/Support blueprint Python/i)
    await waitFor(() => {
      expect(code.textContent).toMatch(/ask_user/)
    })
    expect(screen.getByRole('link', { name: 'blueprint_support.py' })).toHaveAttribute(
      'href',
      '/v1/blueprints/support/source?file=blueprint_support.py',
    )
  })

  it('REQ-19 #334: switches Blueprint file tabs and refetches the selected file', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      const selected = url.includes('roles.py') ? 'roles.py' : 'blueprint_support.py'
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: 'support',
          files: [
            { name: 'blueprint_support.py', path: 'blueprint_support.py' },
            { name: 'roles.py', path: 'roles.py' },
          ],
          primary: 'blueprint_support.py',
          selected,
          content:
            selected === 'roles.py'
              ? 'ROLE = "support"\n'
              : 'def ask_user(question):\n    return question\n',
        }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderSheet({ blueprintId: 'support' })
    const tabs = await screen.findByRole('tablist', { name: 'Blueprint files' })
    expect(within(tabs).getByRole('tab', { name: 'blueprint_support.py' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    fireEvent.click(within(tabs).getByRole('tab', { name: 'roles.py' }))
    await waitFor(() => {
      expect(screen.getByLabelText(/Support blueprint Python/i).textContent).toMatch(/ROLE/)
    })
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('file=roles.py'))).toBe(
      true,
    )
  })

  it('calls onClose from the sheet Close button', () => {
    const { onClose } = renderSheet({ blueprintId: 'gate' })
    fireEvent.click(screen.getByRole('button', { name: /^Close$/ }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('SettingsSheet definition pane (REQ-42)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens focused on the role definition with the static explanation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          kind: 'role',
          id: 'gate',
          title: 'Gate',
          role: 'gate',
          explanation: 'Gate is a YES/NO classifier.',
          source: 'GATE_INSTRUCTIONS',
          injected: {
            system_prompt: '',
            tools: {},
            metadata: {},
            handoff: '',
            extra: 'fixture',
          },
          default_llm: { configured: false, model: null },
        }),
      } as Response),
    )
    renderSheet({
      blueprintId: 'gate',
      initialSection: 'definition',
      definitionKind: 'role',
      definitionId: 'gate',
    })
    const dialog = screen.getByRole('dialog', { hidden: true })
    expect(dialog).toHaveClass('modal-end')
    expect(screen.getByRole('button', { name: 'Definition' })).toHaveClass('menu-active')
    const pane = await screen.findByRole('region', { name: /gate/i })
    expect(pane).toHaveAttribute('data-definition-id', 'gate')
    expect(screen.getByTestId('definition-explanation').textContent).toMatch(/YES\/NO/)
    expect(screen.queryByLabelText(/Gate blueprint Python/i)).not.toBeInTheDocument()
  })

  describe('SettingsSheet General/Visuals (REQ-110)', () => {
    it('sets light, dark, and system theme preferences via dropdown', () => {
      renderSheet()
      fireEvent.click(screen.getByRole('button', { name: 'General' }))

      const select = screen.getByRole('combobox', { name: 'Theme' })
      expect(select).toBeInTheDocument()
      expect(select).toHaveValue('dark')

      // Switch to light
      fireEvent.change(select, { target: { value: 'light' } })
      expect(select).toHaveValue('light')
      expect(localStorage.getItem('swarm_theme')).toBe('light')

      // Switch to system
      fireEvent.change(select, { target: { value: 'system' } })
      expect(select).toHaveValue('system')
      expect(localStorage.getItem('swarm_theme')).toBe('system')

      // Switch to dark
      fireEvent.change(select, { target: { value: 'dark' } })
      expect(select).toHaveValue('dark')
      expect(localStorage.getItem('swarm_theme')).toBe('dark')
    })

    it('toggles navbar theme control visibility and persists flag', () => {
      renderSheet()
      fireEvent.click(screen.getByRole('button', { name: 'General' }))

      const toggle = screen.getByRole('checkbox', { name: 'Show theme control in top bar' })
      expect(toggle).toBeChecked()

      fireEvent.click(toggle)
      expect(toggle).not.toBeChecked()
      expect(localStorage.getItem('swarm_theme_navbar')).toBe('false')

      fireEvent.click(toggle)
      expect(toggle).toBeChecked()
      expect(localStorage.getItem('swarm_theme_navbar')).toBe('true')
    })

    it('shows Auto-compress at default 80 and PATCHes 50 without Django copy', async () => {
      const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/v1/preferences/') && init?.method === 'PATCH') {
          const body = JSON.parse(String(init.body || '{}'))
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: false,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              context_auto_compress_pct: body.context_auto_compress_pct,
              values: {},
            }),
          } as Response
        }
        if (url.includes('/v1/preferences/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: true,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              context_auto_compress_pct: 80,
              values: {},
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      })
      vi.stubGlobal('fetch', fetchMock)
      renderSheet()
      fireEvent.click(screen.getByRole('button', { name: 'General' }))
      const input = await screen.findByTestId('auto-compress-pct')
      expect(input).toHaveValue(80)
      fireEvent.change(input, { target: { value: '50' } })
      expect(input).toHaveValue(50)
      await waitFor(() => {
        const patch = fetchMock.mock.calls.find(
          (entry) => String(entry[0]).includes('/v1/preferences/') && entry[1]?.method === 'PATCH',
        )
        expect(patch).toBeTruthy()
        expect(JSON.parse(String(patch?.[1]?.body || '{}')).context_auto_compress_pct).toBe(50)
      })
      const pane = screen.getByLabelText('Auto-compress at percent').closest('section')
      expect(pane?.textContent).not.toMatch(/Django/i)
    })

    it('shows Compress vs Cull defaults and PATCHes cull knobs without Django copy', async () => {
      const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/v1/preferences/') && init?.method === 'PATCH') {
          const body = JSON.parse(String(init.body || '{}'))
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: false,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              context_auto_compress_pct: 80,
              context_strategy: body.context_strategy ?? 'compress',
              context_cull_trigger_pct: body.context_cull_trigger_pct ?? 90,
              context_cull_fraction_pct: body.context_cull_fraction_pct ?? 50,
              values: {},
            }),
          } as Response
        }
        if (url.includes('/v1/preferences/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: true,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              context_auto_compress_pct: 80,
              context_strategy: 'compress',
              context_cull_trigger_pct: 90,
              context_cull_fraction_pct: 50,
              values: {},
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      })
      vi.stubGlobal('fetch', fetchMock)
      renderSheet()
      fireEvent.click(screen.getByRole('button', { name: 'General' }))
      expect(await screen.findByTestId('cull-trigger-pct')).toHaveValue(90)
      expect(screen.getByTestId('cull-fraction-pct')).toHaveValue(50)
      fireEvent.click(screen.getByTestId('context-strategy-cull'))
      fireEvent.change(screen.getByTestId('cull-trigger-pct'), { target: { value: '85' } })
      fireEvent.change(screen.getByTestId('cull-fraction-pct'), { target: { value: '40' } })
      await waitFor(() => {
        const patches = fetchMock.mock.calls.filter(
          (entry) => String(entry[0]).includes('/v1/preferences/') && entry[1]?.method === 'PATCH',
        )
        const bodies = patches.map((entry) => JSON.parse(String(entry[1]?.body || '{}')))
        expect(bodies.some((body) => body.context_strategy === 'cull')).toBe(true)
        expect(bodies.some((body) => body.context_cull_trigger_pct === 85)).toBe(true)
        expect(bodies.some((body) => body.context_cull_fraction_pct === 40)).toBe(true)
      })
      const pane = screen.getByTestId('context-strategy').closest('section')
      expect(pane?.textContent).not.toMatch(/Django/i)
    })
  })

  it('writes an MCP server via PATCH /v1/config/sections/mcpServers/', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/v1/config/sections/mcpServers') && method === 'PATCH') {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'config_section',
            section: 'mcpServers',
            data: body.upsert || {},
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'config_section', section: 'mcpServers', data: {} }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'MCP servers' }))
    expect(await screen.findByText(/No MCP servers/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Add MCP server/i }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'filesystem' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Command' }), { target: { value: 'npx' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save MCP server' }))
    expect(await screen.findByText('MCP server saved')).toBeInTheDocument()
    const patchCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/v1/config/sections/mcpServers') && call[1]?.method === 'PATCH',
    )
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      upsert: { filesystem: { command: 'npx' } },
    })
    expect(JSON.stringify(patchCall?.[1]?.body)).not.toMatch(/sk-/)
  })
})

