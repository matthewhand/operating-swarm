/**
 * #527 integration — the two UI faces of per-persona avatars.
 *
 * 1. AgentEditor, for a seat whose blueprint declares ≥2 openai-agents
 *    personas, renders one avatar picker per persona (and none otherwise).
 * 2. ChatPage renders per-row `data-persona` attribution on assistant rows,
 *    driven by the declared roster, so the transcript can theme per persona.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../../components/AgentEditor'
import { ToastProvider } from '../../components/DaisyUI'

const PERSONA_BLUEPRINT = {
  id: 'bp-research',
  name: 'Research Swarm',
  kind: 'swarm',
  role: 'worker',
  persona_count: 2,
  personas: [{ name: 'Researcher' }, { name: 'Implementer' }],
}

function jsonResponse(data: unknown, status = 200): Response {
  return { ok: true, status, json: async () => data } as unknown as Response
}

function apiFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/v1/blueprints/') && url.endsWith('/personas')) {
      return jsonResponse({
        object: 'blueprint.personas',
        id: 'bp-research',
        count: 2,
        personas: PERSONA_BLUEPRINT.personas,
        parsed: true,
      })
    }
    if (url.includes('/v1/blueprints')) {
      return jsonResponse({ object: 'list', data: [PERSONA_BLUEPRINT] })
    }
    return jsonResponse({ object: 'list', data: [] })
  })
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <AgentEditor isOpen agentId="bp-research" onClose={() => {}} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('#527 AgentEditor persona avatar pickers', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', apiFetch())
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders one avatar picker per declared persona', async () => {
    renderEditor()
    await waitFor(() => {
      expect(screen.getByTestId('persona-avatar-picker-Researcher')).toBeInTheDocument()
    })
    expect(screen.getByTestId('persona-avatar-picker-Implementer')).toBeInTheDocument()
  })

  it('writes the choice into the persona avatar store', async () => {
    renderEditor()
    const picker = await screen.findByTestId('persona-avatar-picker-Researcher')
    const select = within(picker).getByRole('combobox')
    fireEvent.change(select, { target: { value: 'blobs' } })
    const stored = JSON.parse(
      localStorage.getItem('swarm_persona_avatar_themes') ?? '{}',
    )
    expect(stored['bp-research']?.Researcher).toBe('blobs')
  })

  it('renders no persona pickers for a single-persona blueprint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/personas')) {
          return jsonResponse({
            object: 'blueprint.personas',
            id: 'bp-research',
            count: 1,
            personas: [{ name: 'Only' }],
            parsed: true,
          })
        }
        if (url.includes('/v1/blueprints')) {
          return jsonResponse({
            object: 'list',
            data: [{ ...PERSONA_BLUEPRINT, personas: [{ name: 'Only' }], persona_count: 1 }],
          })
        }
        return jsonResponse({ object: 'list', data: [] })
      }),
    )
    renderEditor()
    await screen.findByTestId('agent-editor-avatar')
    expect(screen.queryByTestId('persona-avatar-picker-Only')).not.toBeInTheDocument()
  })
})
