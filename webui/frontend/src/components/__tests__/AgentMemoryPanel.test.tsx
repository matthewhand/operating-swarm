import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentMemoryPanel from '../AgentMemoryPanel'
import type { AgentMemory } from '../../lib/agentMemory'

const FIXTURES: AgentMemory[] = [
  {
    object: 'agent_memory',
    id: 'p1',
    agent_id: 'codey',
    kind: 'profile',
    tier: 'pack',
    title: 'Voice',
    body: 'Prefers short answers.',
    created_at: '2026-09-27T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'l1',
    agent_id: 'codey',
    kind: 'log',
    tier: 'pack',
    title: 'Weekly review',
    body: 'Shipped the rail polish.',
    created_at: '2026-09-26T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'e1',
    agent_id: 'codey',
    kind: 'episode',
    tier: 'local',
    title: 'Tuesday chat',
    body: 'Private Tuesday chat.',
    created_at: '2026-09-25T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'n1',
    agent_id: 'codey',
    kind: 'note',
    tier: 'local',
    title: 'Scratch',
    body: 'Do not pack this.',
    created_at: '2026-09-24T00:00:00.000Z',
  },
]

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function stubMemories(rows: AgentMemory[] = FIXTURES) {
  const store = [...rows]
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method || 'GET').toUpperCase()
    if (url.includes('/memories/') && method === 'GET' && !url.includes('/pack/')) {
      return jsonResponse({
        object: 'agent_memory_list',
        agent_id: 'codey',
        memories: store,
      })
    }
    if (url.includes('/memories/') && method === 'POST') {
      const payload = JSON.parse(String(init?.body || '{}')) as {
        kind?: string
        title?: string
        body?: string
      }
      const created: AgentMemory = {
        object: 'agent_memory',
        id: 'new-1',
        agent_id: 'codey',
        kind: (payload.kind as AgentMemory['kind']) || 'profile',
        tier: 'pack',
        title: payload.title || '',
        body: payload.body || '',
        created_at: '2026-09-27T12:00:00.000Z',
      }
      store.unshift(created)
      return jsonResponse(created, 201)
    }
    if (url.includes('/memories/') && method === 'DELETE') {
      const id = url.split('/memories/')[1]?.replace(/\/$/, '')
      const index = store.findIndex((row) => row.id === id)
      if (index >= 0) store.splice(index, 1)
      return { ok: true, status: 204, json: async () => ({}) } as Response
    }
    return jsonResponse({ object: 'list', data: [] })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, store }
}

function renderPanel(agentId = 'codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AgentMemoryPanel agentId={agentId} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('#1391 AgentMemoryPanel list/filter', () => {
  it('lists memories by pack and local tiers', async () => {
    stubMemories()
    renderPanel()
    expect(await screen.findByTestId('agent-memory-row-p1')).toHaveTextContent('Prefers short answers.')
    expect(screen.getByTestId('agent-memory-tier-pack')).toHaveTextContent('Voice')
    expect(screen.getByTestId('agent-memory-tier-pack')).toHaveTextContent('Weekly review')
    expect(screen.getByTestId('agent-memory-tier-local')).toHaveTextContent('Tuesday chat')
    expect(screen.getByTestId('agent-memory-tier-local')).toHaveTextContent('Scratch')
  })

  it('filters the list to pack or local', async () => {
    stubMemories()
    renderPanel()
    await screen.findByTestId('agent-memory-row-p1')
    fireEvent.click(screen.getByTestId('agent-memory-filter-pack'))
    expect(screen.getByTestId('agent-memory-tier-pack')).toBeInTheDocument()
    expect(screen.queryByTestId('agent-memory-tier-local')).not.toBeInTheDocument()
    expect(screen.getByTestId('agent-memory-row-p1')).toBeInTheDocument()
    expect(screen.queryByTestId('agent-memory-row-e1')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('agent-memory-filter-local'))
    expect(screen.getByTestId('agent-memory-tier-local')).toBeInTheDocument()
    expect(screen.queryByTestId('agent-memory-tier-pack')).not.toBeInTheDocument()
    expect(screen.getByTestId('agent-memory-row-e1')).toBeInTheDocument()
  })

  it('adds a convention and removes a listed memory', async () => {
    const { fetchMock } = stubMemories()
    renderPanel()
    await screen.findByTestId('agent-memory-row-p1')

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'House style' } })
    fireEvent.change(screen.getByLabelText('Body'), {
      target: { value: 'Use short commit subjects.' },
    })
    fireEvent.click(screen.getByTestId('agent-memory-add'))

    expect(await screen.findByTestId('agent-memory-row-new-1')).toHaveTextContent('House style')
    const post = fetchMock.mock.calls.find((call) => String(call[1]?.method || '').toUpperCase() === 'POST')
    expect(String(post?.[0])).toContain('/v1/agents/codey/memories/')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      kind: 'profile',
      title: 'House style',
      body: 'Use short commit subjects.',
    })

    fireEvent.click(screen.getByTestId('agent-memory-remove-e1'))
    await waitFor(() => {
      expect(screen.queryByTestId('agent-memory-row-e1')).not.toBeInTheDocument()
    })
  })

  it('opens the export wizard with included vs excluded counts', async () => {
    stubMemories()
    renderPanel()
    await screen.findByTestId('agent-memory-row-p1')
    fireEvent.click(screen.getByTestId('agent-memory-export-preview'))
    const wizard = await screen.findByTestId('memory-export-wizard')
    expect(wizard).toBeInTheDocument()
    expect(screen.getByTestId('memory-export-included-count')).toHaveTextContent('2')
    expect(screen.getByTestId('memory-export-excluded-count')).toHaveTextContent('2')
    expect(screen.getByTestId('memory-export-reason-episode')).toHaveTextContent('Episode skipped')
    expect(screen.getByTestId('memory-export-reason-note')).toHaveTextContent('Note skipped')
  })

  it('has no paste-secret affordance', async () => {
    stubMemories()
    renderPanel()
    await screen.findByTestId('agent-memory-add-form')
    const form = screen.getByTestId('agent-memory-add-form')
    expect(within(form).queryByLabelText(/secret|api key|password|token/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /paste secret/i })).toBeNull()
    expect(screen.queryByText(/paste (a |your )?secret/i)).toBeNull()
    expect(screen.getByText(/Do not store credentials/i)).toBeInTheDocument()
    expect(within(form).getByLabelText('Convention kind').querySelectorAll('option')).toHaveLength(2)
  })
})
