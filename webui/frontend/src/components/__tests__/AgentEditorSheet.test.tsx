import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentEditorSheet from '../AgentEditorSheet'
import { ToastProvider } from '../DaisyUI'
import {
  NEW_CHAT_PER_TASK_LABEL,
  NEW_CHAT_PER_TASK_TOOLTIP,
  USE_SUGGESTIONS_LABEL,
  localSettingsKey,
} from '../../lib/agentSettings'
import { STREAM_REPLIES_SEAT_LABEL, STREAM_REPLIES_SEATS_STORAGE_KEY } from '../../lib/streamReplies'

function renderEditor(agentId = 'worker') {
  const onClose = vi.fn()
  const view = render(
    <ToastProvider>
      <AgentEditorSheet
        isOpen
        onClose={onClose}
        agentId={agentId}
        agentName="Worker"
      />
    </ToastProvider>,
  )
  return { ...view, onClose }
}

describe('AgentEditorSheet', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('shows the New chat per task label, tooltip, and default off', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'worker',
          new_chat_per_task: false,
        }),
      } as Response),
    )
    renderEditor()
    const toggle = await screen.findByRole('switch', { name: NEW_CHAT_PER_TASK_LABEL })
    expect(toggle).not.toBeChecked()
    expect(screen.getByText(NEW_CHAT_PER_TASK_LABEL)).toBeInTheDocument()
    expect(document.querySelector('[data-tip]')).toHaveAttribute(
      'data-tip',
      NEW_CHAT_PER_TASK_TOOLTIP,
    )
    expect(screen.queryByRole('button', { name: 'Remotes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'System' })).not.toBeInTheDocument()
    expect(screen.queryByText('Retention')).not.toBeInTheDocument()
    expect(await screen.findByRole('switch', { name: USE_SUGGESTIONS_LABEL })).not.toBeChecked()
    expect(screen.getByLabelText(STREAM_REPLIES_SEAT_LABEL)).toHaveValue('inherit')
  })

  it('persists the toggle on', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/settings/') && init?.method === 'PATCH') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ agent_id: 'worker', new_chat_per_task: true }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ agent_id: 'worker', new_chat_per_task: false }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderEditor()
    const toggle = await screen.findByRole('switch', { name: NEW_CHAT_PER_TASK_LABEL })
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(toggle).toBeChecked()
    })
    expect(JSON.parse(localStorage.getItem(localSettingsKey('worker')) || '{}')).toMatchObject({
      new_chat_per_task: true,
    })
    expect(fetchMock.mock.calls.some((call) => String(call[1]?.method) === 'PATCH')).toBe(true)
  })

  it('persists a per-seat stream-replies override (#220)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'worker',
          new_chat_per_task: false,
        }),
      } as Response),
    )
    renderEditor()
    const select = await screen.findByLabelText(STREAM_REPLIES_SEAT_LABEL)
    fireEvent.change(select, { target: { value: 'on' } })
    expect(select).toHaveValue('on')
    expect(JSON.parse(localStorage.getItem(STREAM_REPLIES_SEATS_STORAGE_KEY) || '{}')).toEqual({
      worker: true,
    })
  })
})
