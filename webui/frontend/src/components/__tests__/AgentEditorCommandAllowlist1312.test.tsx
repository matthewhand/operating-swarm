import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'

function renderEditor(agentId = 'bee') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={() => {}} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function fetchMock() {
  return vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/settings/') && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body || '{}'))
      return {
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'bee',
          new_chat_per_task: false,
          command_allowlist: body.command_allowlist ?? { allow: [], deny: [], ask: [] },
        }),
      } as Response
    }
    if (url.includes('/settings/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'bee',
          new_chat_per_task: false,
          command_allowlist: { allow: [], deny: [], ask: [] },
        }),
      } as Response
    }
    return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
  })
}

describe('AgentEditor command allowlist (#1312)', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('renders the editor and reports inactive by default', async () => {
    vi.stubGlobal('fetch', fetchMock())
    renderEditor()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: /Advanced/i }),
    )
    const editor = await screen.findByTestId('agent-editor-command-allowlist')
    expect(editor).toBeInTheDocument()
    expect(screen.getByTestId('command-allowlist-status').textContent).toMatch(/No policy/)
  })

  it('persists deny rules to the server on blur', async () => {
    const mock = fetchMock()
    vi.stubGlobal('fetch', mock)
    renderEditor()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: /Advanced/i }),
    )
    const deny = await screen.findByTestId('command-allowlist-deny')
    fireEvent.change(deny, { target: { value: 'rm\ncurl' } })
    fireEvent.blur(deny)

    await waitFor(() => {
      const patches = mock.mock.calls.filter(
        (call) => String(call[0]).includes('/settings/') && call[1]?.method === 'PATCH',
      )
      expect(patches.length).toBeGreaterThan(0)
    })
    const bodies = mock.mock.calls
      .filter((call) => String(call[0]).includes('/settings/') && call[1]?.method === 'PATCH')
      .map((call) => JSON.parse(String(call[1]?.body || '{}')))
    expect(bodies.some((body) => body.command_allowlist?.deny?.join(',') === 'rm,curl')).toBe(true)
  })
})
