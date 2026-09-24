import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'

function renderEditor(agentId = 'bee') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={() => {}} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('AgentEditor voice bind (#116)', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('defaults to inherit next to the avatar and can bind a voice', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/settings/') && init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body || '{}'))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'bee',
            new_chat_per_task: false,
            speech_mode: body.speech_mode || 'inherit',
            tts_voice_instruction: body.tts_voice_instruction || '',
            auto_speak_replies: Boolean(body.auto_speak_replies),
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
            speech_mode: 'inherit',
            auto_speak_replies: false,
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderEditor()
    // #1127: voice and avatar live in different tab panels — visit both.
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: /Advanced/i }),
    )
    const voice = await screen.findByTestId('agent-editor-voice')
    expect(voice).toBeInTheDocument()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: /Identity/i }),
    )
    expect(screen.getByTestId('agent-editor-avatar')).toBeInTheDocument()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: /Advanced/i }),
    )
    const mode = screen.getByLabelText('Speech mode')
    expect(mode).toHaveValue('inherit')
    expect(screen.queryByLabelText('Voice instruction')).not.toBeInTheDocument()

    fireEvent.change(mode, { target: { value: 'voice' } })
    await waitFor(() => {
      expect(screen.getByLabelText('Voice instruction')).toBeInTheDocument()
    })
    fireEvent.change(screen.getByLabelText('Voice instruction'), {
      target: { value: 'Speak like a bee.' },
    })
    fireEvent.blur(screen.getByLabelText('Voice instruction'))
    fireEvent.click(screen.getByRole('switch', { name: 'Auto-speak replies' }))

    await waitFor(() => {
      const patches = fetchMock.mock.calls.filter(
        (call) => String(call[0]).includes('/settings/') && call[1]?.method === 'PATCH',
      )
      expect(patches.length).toBeGreaterThan(0)
    })
    const bodies = fetchMock.mock.calls
      .filter((call) => String(call[0]).includes('/settings/') && call[1]?.method === 'PATCH')
      .map((call) => JSON.parse(String(call[1]?.body || '{}')))
    expect(bodies.some((body) => body.speech_mode === 'voice')).toBe(true)
    expect(bodies.some((body) => body.tts_voice_instruction === 'Speak like a bee.')).toBe(true)
    expect(bodies.some((body) => body.auto_speak_replies === true)).toBe(true)
    expect(JSON.stringify(bodies)).not.toMatch(/sk-/)
  })
})
