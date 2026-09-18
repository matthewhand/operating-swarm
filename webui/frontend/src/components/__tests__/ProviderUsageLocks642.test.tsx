/**
 * #642 — provider/type controls lock while agents depend on them.
 *
 * - CLI pane: the Remove control on a configured CLI greys with the usage
 *   tooltip while rail seats (`kind: 'cli'`, `cli: <name>`) reference it.
 * - Remotes pane: the Remove control greys while the remote's stamped
 *   `agents` rows (or persisted bindings) reference it. Zero dependents →
 *   the control behaves exactly as before.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import CliAgentsSettingsPane from '../CliAgentsSettingsPane'
import { ToastProvider } from '../DaisyUI'

const KNOWN = ['grok', 'omp']

function renderPane(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{node}</ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#642 CLI remove locks while rail seats use the CLI', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubCliFetch(catalog: Record<string, unknown>) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/config/sections/cli_agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'config_section',
              data: { grok: { cmd: ['grok', '-p', '{prompt}'] }, omp: { cmd: ['omp', '-p'] } },
            }),
          } as Response
        }
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              clis: KNOWN,
              known: KNOWN,
              configured: KNOWN,
              discovered: [],
              installed: [],
              suggestions: {},
              catalog: {},
              ...catalog,
            }),
          } as Response
        }
        if (url.includes('/v1/rate-limits')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'provider_rate_limits', data: [] }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({}) } as Response
      }),
    )
  }

  it('disables Remove with the usage tooltip while a rail seat uses the CLI', async () => {
    stubCliFetch({
      rail: [
        {
          id: 'Grok seat',
          object: 'cli.agent',
          name: 'Grok seat',
          cli: 'grok',
          kind: 'cli',
          description: 'Host CLI',
          installed: true,
        },
      ],
    })
    renderPane(<CliAgentsSettingsPane />)
    const grokRemove = await screen.findByTestId('cli-remove-grok')
    expect(grokRemove).toBeDisabled()
    expect(grokRemove).toHaveAttribute(
      'title',
      'Agents using this type of provider are still configured',
    )

    const ompRemove = screen.getByTestId('cli-remove-omp')
    expect(ompRemove).toBeEnabled() // unused → untouched control
    expect(ompRemove).not.toHaveAttribute('title')
  })

  it('shows the count in the tooltip when several seats use the CLI', async () => {
    stubCliFetch({
      rail: [
        { id: 'a', object: 'cli.agent', name: 'a', cli: 'grok', kind: 'cli', description: '', installed: true },
        { id: 'b', object: 'cli.agent', name: 'b', cli: 'grok', kind: 'cli', description: '', installed: true },
      ],
    })
    renderPane(<CliAgentsSettingsPane />)
    const remove = await screen.findByTestId('cli-remove-grok')
    expect(remove).toHaveAttribute(
      'title',
      'Agents using this type of provider are still configured (2 agents)',
    )
  })
})

describe('#642 remote remove locks while agents are registered', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  function stubRemotesFetch(configured: Record<string, unknown>[]) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes/')) {
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
        }
        return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
      }),
    )
  }

  function openRemotes() {
    renderPane(<SettingsSheet isOpen onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))
  }

  it('disables Remove with the tooltip while the payload lists dependent agents', async () => {
    stubRemotesFetch([
      {
        id: 'omb',
        kind: 'omb',
        title: 'OpenMousBot',
        base_url: 'http://localhost:9000',
        source: 'config',
        agents: [{ id: 'bee', name: 'Bee' }],
      },
    ])
    openRemotes()
    const remove = await screen.findByRole('button', { name: 'Remove' })
    expect(remove).toBeDisabled()
    expect(remove).toHaveAttribute(
      'title',
      'Agents using this type of provider are still configured',
    )
    expect(remove).toHaveAttribute('aria-disabled', 'true')
  })

  it('re-enables Remove once no agent depends on the remote', async () => {
    localStorage.setItem(
      'swarm_agent_remote_bindings',
      JSON.stringify({ bee: { id: 'herdr', kind: 'herdr' } }),
    )
    stubRemotesFetch([
      {
        id: 'omb',
        kind: 'omb',
        title: 'OpenMousBot',
        base_url: 'http://localhost:9000',
        source: 'config',
      },
      {
        id: 'herdr',
        kind: 'herdr',
        title: 'Herdr',
        base_url: '',
        source: 'config',
      },
    ])
    openRemotes()
    // omb: no dependents anywhere → enabled, no tooltip.
    const ombRemove = await screen.findByTestId('remote-remove-omb')
    expect(ombRemove).toBeEnabled()
    expect(ombRemove).not.toHaveAttribute('title')
    // herdr: the persisted binding locks it.
    const herdrRemove = screen.getByTestId('remote-remove-herdr')
    expect(herdrRemove).toBeDisabled()
    expect(herdrRemove).toHaveAttribute(
      'title',
      'Agents using this type of provider are still configured',
    )
    await waitFor(() => {
      expect(ombRemove).toBeEnabled()
    })
  })
})
