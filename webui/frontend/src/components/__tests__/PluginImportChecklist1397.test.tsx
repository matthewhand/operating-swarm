import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../DaisyUI'
import AgentPluginPackPane from '../AgentPluginPackPane'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const CHECKLIST = {
  object: 'agent_plugins',
  agent_id: 'worker',
  plugins: [
    { pluginId: 'fetch', name: 'fetch', description: '', status: 'enabled' },
    {
      pluginId: 'github',
      name: 'github',
      description: '',
      status: 'missing-auth',
      required_env: ['GH_NAME'],
    },
    { pluginId: 'gone', name: 'gone', description: '', status: 'missing-plugin' },
  ],
  enabled: ['fetch'],
  missing: ['gone'],
  memory_named: [{ name: 'Desk notes', note: 'named in memory only' }],
  pack: {
    object: 'agent_plugin_pack',
    schema: 1,
    kind: 'agent_plugin_pack',
    plugins: [
      { pluginId: 'fetch', name: 'fetch', description: '' },
      { pluginId: 'github', name: 'github', description: '' },
      { pluginId: 'gone', name: 'gone', description: '' },
    ],
  },
}

describe('import checklist #1397', () => {
  it('shows packable multi-select, memory-only names, and connect states', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/marketplace/install/') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        expect(body).toEqual({ kind: 'plugins', id: 'github' })
        expect(JSON.stringify(body)).not.toMatch(/sk-|bearer |token|password/i)
        return jsonResponse({ object: 'marketplace_install', kind: 'plugins', id: 'github', installed: false })
      }
      return jsonResponse(CHECKLIST)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(
      <ToastProvider>
        <AgentPluginPackPane agentId="worker" />
      </ToastProvider>,
    )

    expect(await screen.findByTestId('os-plugin-memory-only')).toHaveTextContent('Desk notes named in memory only')
    expect(screen.getByRole('checkbox', { name: 'Pack fetch' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Pack github' })).toBeChecked()

    const checklist = screen.getByRole('list', { name: 'Import checklist' })
    expect(checklist.querySelector('[data-checklist-state="connected"]')).toHaveTextContent('Connected')
    expect(checklist.querySelector('[data-checklist-state="needsAuth"]')).toHaveTextContent('Needs auth')
    expect(checklist.querySelector('[data-checklist-state="missing"]')).toHaveTextContent('Missing')

    fireEvent.click(screen.getByTestId('os-plugin-connect-github'))
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/marketplace/install/'))).toBe(true)
    })
  })
})
