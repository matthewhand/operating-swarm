import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, afterEach } from 'vitest'
import AgentSkillsPanel from '../AgentSkillsPanel'
import { ToastProvider } from '../DaisyUI'
import { loadAgentEdit } from '../../lib/agentEdits'

const welcome = {
  name: 'welcome-tour',
  description: 'Walk the first conversation.',
  instructions: 'Greet the operator.',
  source: 'authored',
}

function stubApi() {
  const skills = { ...welcome }
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = String(init?.method || 'GET').toUpperCase()
      if (url.includes('/pack/import')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_skill_list',
            agent_id: 'codey',
            skills: [skills],
            gettingStarted: { skill: 'welcome-tour' },
            first_run_pending: true,
          }),
        } as Response
      }
      if (url.includes('/pack/') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_pack',
            kind: 'swarm-agent-pack',
            skills: [skills],
            gettingStarted: body.gettingStarted,
          }),
        } as Response
      }
      if (url.includes('/v1/agents/') && url.includes('/skills') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          ok: true,
          status: 201,
          json: async () => ({
            object: 'agent_skill',
            agent_id: 'codey',
            name: body.name || body.attach,
            description: body.description || '',
            instructions: body.instructions || 'Copied.',
            source: body.attach ? 'library' : 'authored',
          }),
        } as Response
      }
      if (url.includes('/v1/agents/') && url.includes('/skills')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_skill_list',
            agent_id: 'codey',
            skills: [skills],
            gettingStarted: { skill: 'welcome-tour' },
            first_run_pending: false,
          }),
        } as Response
      }
      if (url.includes('/v1/skills')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentSkillsPanel agentId="codey" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('AgentSkillsPanel (#1393)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lists attached skills with when-to-use and exports a valid pack', async () => {
    stubApi()
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:pack')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    renderPanel()
    expect(await screen.findByTestId('agent-skill-when-welcome-tour')).toHaveTextContent(
      'Walk the first conversation.',
    )
    const exportBtn = await screen.findByTestId('agent-pack-export')
    expect(exportBtn).toBeEnabled()
    fireEvent.click(exportBtn)
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([input, init]) => {
        const url = String(input)
        return url.includes('/pack/') && !url.includes('import') && String(init?.method) === 'POST'
      })).toBe(true)
    })
  })

  it('importing a pack reports first-chat getting-started', async () => {
    stubApi()
    renderPanel()
    await screen.findByTestId('agent-pack-import-json')
    fireEvent.change(screen.getByTestId('agent-pack-import-json'), {
      target: {
        value: JSON.stringify({
          kind: 'swarm-agent-pack',
          skills: [welcome],
          gettingStarted: { skill: 'welcome-tour' },
        }),
      },
    })
    fireEvent.click(screen.getByTestId('agent-pack-import'))
    expect(await screen.findByTestId('agent-pack-import-result')).toHaveTextContent(
      /First chat will apply welcome-tour/,
    )
    await waitFor(() => {
      expect(loadAgentEdit('codey').skills).toEqual(['welcome-tour'])
    })
  })

  it('rejects malformed pack JSON without calling import', async () => {
    stubApi()
    renderPanel()
    await screen.findByTestId('agent-pack-import-json')
    fireEvent.change(screen.getByTestId('agent-pack-import-json'), {
      target: { value: '{' },
    })
    fireEvent.click(screen.getByTestId('agent-pack-import'))
    expect(await screen.findByTestId('agent-pack-error')).toHaveTextContent(/valid JSON/)
    expect(
      vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes('/pack/import')),
    ).toBe(false)
  })

  it('marks getting started without throwing on the success toast', async () => {
    const notes = {
      name: 'review-notes',
      description: 'When reviewing a diff.',
      instructions: 'Summarize the diff.',
      source: 'authored',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = String(init?.method || 'GET').toUpperCase()
        if (url.includes('/v1/agents/') && url.includes('/skills') && method === 'PATCH') {
          const body = JSON.parse(String(init?.body || '{}'))
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'agent_skill_list',
              agent_id: 'codey',
              skills: [welcome, notes],
              gettingStarted: body.gettingStarted,
              first_run_pending: false,
            }),
          } as Response
        }
        if (url.includes('/v1/agents/') && url.includes('/skills')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'agent_skill_list',
              agent_id: 'codey',
              skills: [welcome, notes],
              gettingStarted: { skill: 'welcome-tour' },
              first_run_pending: false,
            }),
          } as Response
        }
        if (url.includes('/v1/skills')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ object: 'list', data: [] }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({}) } as Response
      }),
    )
    renderPanel()
    fireEvent.click(await screen.findByTestId('agent-skill-mark-started-review-notes'))
    expect(await screen.findByText(/review-notes will run on first chat when marked/)).toBeInTheDocument()
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([input, init]) => {
        if (!String(input).includes('/skills') || String(init?.method) !== 'PATCH') return false
        const body = JSON.parse(String(init?.body || '{}'))
        return body.gettingStarted?.skill === 'review-notes'
      })).toBe(true)
    })
  })
})
