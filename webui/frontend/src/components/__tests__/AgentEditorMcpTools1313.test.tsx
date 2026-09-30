import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={() => {}} agentId="bee" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  sessionStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/mcp-plugins/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'mcp_plugins',
            scope: 'local',
            servers: [
              {
                name: 'serverA',
                kind: 'local',
                enabled: true,
                command: 'true',
                args: [],
                url: '',
                env: {},
                headers: {},
                provides: [],
                note: '',
                tools: [
                  { name: 'tool1', description: 'one' },
                  { name: 'tool2', description: 'two' },
                ],
              },
            ],
          }),
        } as Response
      }
      if (url.includes('/mcp')) {
        if (init?.method === 'PATCH') {
          const body = JSON.parse(String(init.body || '{}')) as { mcp_tools?: unknown }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'agent_mcp',
              agent_id: 'bee',
              mcp_mode: 'all',
              mcp_servers: ['serverA'],
              mcp_tools: body.mcp_tools ?? {},
              enabled: true,
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_mcp',
            agent_id: 'bee',
            mcp_mode: 'all',
            mcp_servers: ['serverA'],
            mcp_tools: { serverA: ['tool1'] },
            enabled: true,
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
})

describe('AgentEditor MCP tool tree (#1313)', () => {
  it('pre-checks the grant, checks the rest on, then drops the cleared tool', async () => {
    renderEditor()
    fireEvent.click(screen.getByRole('tab', { name: 'Advanced' }))
    const tool1 = await screen.findByTestId('agent-mcp-tool-serverA-tool1')
    await waitFor(() => expect(tool1).toBeChecked())
    const tool2 = screen.getByTestId('agent-mcp-tool-serverA-tool2')
    expect(tool2).not.toBeChecked()

    fireEvent.click(tool2)
    await waitFor(() => {
      const fetchMock = vi.mocked(fetch)
      const patch = [...fetchMock.mock.calls].reverse().find((call) => {
        const init = call[1] as RequestInit | undefined
        return init?.method === 'PATCH' && String(call[0]).includes('/mcp')
      })
      expect(patch).toBeTruthy()
      const body = JSON.parse(String((patch?.[1] as RequestInit).body))
      expect(body.mcp_tools).toEqual({ serverA: '*' })
    })

    fireEvent.click(tool1)
    await waitFor(() => {
      const fetchMock = vi.mocked(fetch)
      const patch = [...fetchMock.mock.calls].reverse().find((call) => {
        const init = call[1] as RequestInit | undefined
        return init?.method === 'PATCH' && String(call[0]).includes('/mcp')
      })
      expect(patch).toBeTruthy()
      const body = JSON.parse(String((patch?.[1] as RequestInit).body))
      expect(body.mcp_tools).toEqual({ serverA: ['tool2'] })
    })
  })

  it('patches an explicit empty grant when the last checked tool is cleared', async () => {
    renderEditor()
    fireEvent.click(screen.getByRole('tab', { name: 'Advanced' }))
    const tool1 = await screen.findByTestId('agent-mcp-tool-serverA-tool1')
    await waitFor(() => expect(tool1).toBeChecked())
    fireEvent.click(tool1)
    await waitFor(() => {
      const fetchMock = vi.mocked(fetch)
      const patch = [...fetchMock.mock.calls].reverse().find((call) => {
        const init = call[1] as RequestInit | undefined
        return init?.method === 'PATCH' && String(call[0]).includes('/mcp')
      })
      const body = JSON.parse(String((patch?.[1] as RequestInit).body))
      expect(body.mcp_tools).toEqual({ serverA: [] })
    })
  })

  it('restores the checkbox when the grant PATCH fails', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/mcp-plugins/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'mcp_plugins',
            servers: [
              {
                name: 'serverA',
                enabled: true,
                tools: [
                  { name: 'tool1', description: 'one' },
                  { name: 'tool2', description: 'two' },
                ],
              },
            ],
          }),
        } as Response
      }
      if (url.includes('/mcp') && init?.method === 'PATCH') {
        return {
          ok: false,
          status: 500,
          json: async () => ({ error: 'nope' }),
        } as Response
      }
      if (url.includes('/mcp')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_mcp',
            agent_id: 'bee',
            mcp_mode: 'all',
            mcp_servers: ['serverA'],
            mcp_tools: { serverA: ['tool1'] },
            enabled: true,
          }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
    })

    renderEditor()
    fireEvent.click(screen.getByRole('tab', { name: 'Advanced' }))
    const tool1 = await screen.findByTestId('agent-mcp-tool-serverA-tool1')
    await waitFor(() => expect(tool1).toBeChecked())
    fireEvent.click(tool1)
    await waitFor(() => expect(tool1).toBeChecked())
    expect(await screen.findByText('Could not save this grant. The checkbox was restored.')).toBeTruthy()
  })
})
