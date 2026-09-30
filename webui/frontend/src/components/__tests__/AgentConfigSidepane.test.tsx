/**
 * #1258 — the standalone agent configuration sidepane owns seat identity,
 * routing, working folder, skills and instructions, persisting through the
 * canonical `saveAgentEdit` path.
 *
 * #1447: this is the config surface. Computer Control no longer hosts an
 * Agent tab; per-agent sandbox opt-in (#719) lives here.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AgentConfigSidepane from '../AgentConfigSidepane'
import { loadAgentEdit } from '../../lib/agentEdits'

function stubCatalogFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        profiles: [{ id: 'profile-1', name: 'Profile One', model: 'gpt-x' }],
        data: [{ name: 'alpha', description: '', assets: [] }],
      }),
    }),
  )
}

describe('#1258 AgentConfigSidepane', () => {
  beforeEach(() => {
    localStorage.clear()
    stubCatalogFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders identity, routing, folder, skills and instructions for an API seat', async () => {
    render(
      <AgentConfigSidepane
        agentId="codey"
        agentName="Codey"
        agentKind="api"
        workspaceEditable
        onClose={() => {}}
      />,
    )
    expect(screen.getByTestId('agent-config-name-input')).toHaveValue('Codey')
    expect(screen.getByTestId('agent-config-role')).toBeInTheDocument()
    expect(screen.getByTestId('agent-config-profile')).toBeInTheDocument()
    expect(screen.getByTestId('agent-config-folder')).toBeInTheDocument()
    expect(screen.getByTestId('agent-config-skills')).toBeInTheDocument()
    expect(screen.getByTestId('agent-config-instructions')).toBeInTheDocument()
    expect(screen.getByTestId('sandbox-opt-in')).toBeInTheDocument()
    expect(await screen.findByText('alpha')).toBeInTheDocument()
  })

  it('#1447: non-API seats do not get instruction or sandbox fields', () => {
    render(
      <AgentConfigSidepane
        agentId="claude-code"
        agentName="Claude Code"
        agentKind="cli"
        onClose={() => {}}
      />,
    )
    expect(screen.getByTestId('agent-config-name-input')).toBeInTheDocument()
    expect(screen.queryByTestId('agent-config-instructions')).toBeNull()
    expect(screen.queryByTestId('sandbox-opt-in')).toBeNull()
  })

  it('#719: sandbox opt-in PATCH persists the provider and the clear sentinel', async () => {
    const patchBodies: Record<string, unknown>[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method || 'GET').toUpperCase()
        if (url.includes('/blueprints/custom/codey') && method === 'PATCH') {
          patchBodies.push(init?.body ? JSON.parse(String(init.body)) : {})
          return { ok: true, json: async () => ({ object: 'blueprint', id: 'codey' }) }
        }
        return {
          ok: true,
          json: async () => ({
            profiles: [{ id: 'profile-1', name: 'Profile One', model: 'gpt-x' }],
            data: [],
          }),
        }
      }),
    )
    render(
      <AgentConfigSidepane agentId="codey" agentName="Codey" agentKind="api" onClose={() => {}} />,
    )
    const select = screen.getByTestId('sandbox-opt-in')
    expect(select).toHaveValue('settings')
    fireEvent.change(select, { target: { value: 'daytona' } })
    fireEvent.click(screen.getByTestId('agent-config-save'))
    await waitFor(() => expect(patchBodies).toHaveLength(1))
    expect(patchBodies[0].sandbox).toEqual({ provider: 'daytona' })
    fireEvent.change(select, { target: { value: 'settings' } })
    fireEvent.click(screen.getByTestId('agent-config-save'))
    await waitFor(() => expect(patchBodies).toHaveLength(2))
    expect(patchBodies[1].sandbox).toEqual({ provider: 'none', _clear: true })
  })

  it('persists edits through saveAgentEdit on Save', async () => {
    render(
      <AgentConfigSidepane
        agentId="codey"
        agentName="Codey"
        agentKind="api"
        workspaceEditable
        onClose={() => {}}
      />,
    )
    fireEvent.change(screen.getByTestId('agent-config-name-input'), {
      target: { value: 'Codey Two' },
    })
    fireEvent.change(screen.getByTestId('agent-config-folder'), {
      target: { value: '/tmp/work' },
    })
    fireEvent.click(screen.getByTestId('agent-config-save'))
    await waitFor(() => {
      const edit = loadAgentEdit('codey')
      expect(edit.name).toBe('Codey Two')
      expect(edit.folder).toBe('/tmp/work')
    })
  })

  it('calls onClose from Cancel', () => {
    const onClose = vi.fn()
    render(<AgentConfigSidepane agentId="codey" agentName="Codey" onClose={onClose} />)
    fireEvent.click(screen.getByTestId('agent-config-cancel'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
