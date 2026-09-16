import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RemoteOperatePane } from '../RemotesSettings'
import { ToastProvider } from '../DaisyUI'
import * as api from '../../lib/api'

function renderPane(remote = { id: 'omb', label: 'OpenMousBot', base_url: 'http://localhost:8000' }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RemoteOperatePane remote={remote as any} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('RemotesSettings RemoteOperatePane (REQ-131)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('populates the target field from AnythingLLM sessions', async () => {
    vi.spyOn(api, 'operateRemote').mockResolvedValue({
      remote: 'anythingllm',
      op: 'list',
      ok: true,
      detail: 'listed 2 AnythingLLM thread(s) across 1 workspace(s)',
      data: {
        sessions: [
          { id: 'teamstinky:thread-1', title: 'latest hacker news?' },
          { id: 'teamstinky:thread-2', title: 'onboarding docs' },
        ],
        source: 'anythingllm',
      },
    })

    renderPane({
      id: 'anythingllm',
      label: 'AnythingLLM',
      base_url: 'http://127.0.0.1:3001',
    } as any)

    fireEvent.click(screen.getByRole('button', { name: /^list$/i }))

    await waitFor(() => {
      expect(screen.getByText(/teamstinky:thread-1 · latest hacker news\?/i)).toBeInTheDocument()
      expect(screen.getByText(/teamstinky:thread-2 · onboarding docs/i)).toBeInTheDocument()
      expect(screen.getByDisplayValue('teamstinky:thread-1')).toBeInTheDocument()
    })
  })

  it('renders List bots button and stops spinner on success', async () => {
    vi.spyOn(api, 'operateRemote').mockResolvedValue({
      remote: 'omb',
      op: 'list',
      ok: true,
      detail: 'OpenMousBot listed 2 bot(s) via GET /api/bots',
      data: { bots: [{ id: 'bot-1', name: 'Alpha Bot' }, { id: 'bot-2', name: 'Beta Bot' }] },
    })

    renderPane()

    const listBtn = screen.getByRole('button', { name: /list bots/i })
    expect(listBtn).toBeInTheDocument()

    fireEvent.click(listBtn)

    await waitFor(() => {
      expect(screen.getByText(/bot-1 · Alpha Bot/i)).toBeInTheDocument()
      expect(screen.getByText(/bot-2 · Beta Bot/i)).toBeInTheDocument()
      expect(listBtn).not.toHaveAttribute('aria-busy', 'true')
    })
  })

  it('stops spinner and renders error alert when list times out or fails', async () => {
    vi.spyOn(api, 'operateRemote').mockRejectedValue(
      new Error('OpenMousBot list operation timed out after 12s. Remote server is slow or hung.'),
    )

    renderPane()

    const listBtn = screen.getByRole('button', { name: /list bots/i })
    fireEvent.click(listBtn)

    await waitFor(() => {
      expect(
        screen.getByText(/OpenMousBot list operation timed out after 12s/i),
      ).toBeInTheDocument()
      expect(listBtn).not.toHaveAttribute('aria-busy', 'true')
    })
  })

  it('renders routines section when capabilities.routines is true and displays routines', async () => {
    vi.spyOn(api, 'fetchRemoteRoutines').mockResolvedValue({
      remote: 'trueforge',
      op: 'routines',
      ok: true,
      detail: 'TrueForge listed 1 routine(s)',
      data: {
        routines: [
          {
            id: 'sched-1',
            name: 'Morning Summary',
            agent: 'summarizer-agent',
            cron: '0 9 * * 1-5',
            timezone: 'America/New_York',
            task: 'Summarize news',
            status: 'active',
            last_run: {
              id: 'run-1',
              scheduled_for: '2026-09-15T09:00:00Z',
              status: 'scheduled',
            },
          },
        ],
      },
    })

    renderPane({
      id: 'trueforge',
      label: 'TrueForge',
      base_url: 'http://127.0.0.1:8791',
      capabilities: { routines: true },
    } as any)

    expect(screen.getByTestId('remote-routines-section')).toBeInTheDocument()
    expect(screen.getByText('Routines (TrueForge schedules)')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Morning Summary')).toBeInTheDocument()
      expect(screen.getByText(/Agent:/)).toBeInTheDocument()
      expect(screen.getByText('summarizer-agent')).toBeInTheDocument()
      expect(screen.getByText(/0 9 \* \* 1-5/)).toBeInTheDocument()
      expect(screen.getByText(/Weekdays at 09:00/)).toBeInTheDocument()
      expect(screen.getByText(/America\/New_York/)).toBeInTheDocument()
      expect(screen.getByText('Summarize news')).toBeInTheDocument()
      expect(screen.getByText('scheduled')).toBeInTheDocument()
      expect(screen.getByText('2026-09-15T09:00:00Z')).toBeInTheDocument()
    })
  })

  it('renders empty message when no routines configured', async () => {
    vi.spyOn(api, 'fetchRemoteRoutines').mockResolvedValue({
      remote: 'trueforge',
      op: 'routines',
      ok: true,
      detail: 'TrueForge listed 0 routine(s)',
      data: { routines: [] },
    })

    renderPane({
      id: 'trueforge',
      label: 'TrueForge',
      base_url: 'http://127.0.0.1:8791',
      capabilities: { routines: true },
    } as any)

    await waitFor(() => {
      expect(screen.getByText('No routines configured on this remote.')).toBeInTheDocument()
    })
  })

  it('lists AnythingLLM sessions from operate and lets the operator pick one', async () => {
    vi.spyOn(api, 'operateRemote').mockResolvedValue({
      remote: 'anythingllm',
      op: 'list',
      ok: true,
      detail: 'listed 2',
      data: {
        sessions: [
          { id: 'docs', title: 'Docs' },
          { id: 'docs:t1', title: 'latest hacker news?' },
        ],
      },
    })

    renderPane({
      id: 'anythingllm',
      label: 'AnythingLLM',
      base_url: 'http://127.0.0.1:3001',
      capabilities: { sessions: true, list: true, send: true },
    } as any)

    fireEvent.click(screen.getByRole('button', { name: /list/i }))

    await waitFor(() => {
      expect(screen.getByText(/docs:t1 · latest hacker news/i)).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /docs:t1/i }))
    expect(screen.getByLabelText(/target/i)).toHaveValue('docs:t1')
  })

  it('does not render routines section when capabilities.routines is false', () => {
    renderPane({
      id: 'omb',
      label: 'OpenMousBot',
      base_url: 'http://localhost:8000',
      capabilities: { routines: false },
    } as any)

    expect(screen.queryByTestId('remote-routines-section')).not.toBeInTheDocument()
    expect(screen.queryByText('Routines (TrueForge schedules)')).not.toBeInTheDocument()
  })

  it('hides routines section when remote probe reports DOWN', async () => {
    vi.spyOn(api, 'fetchRemoteRoutines').mockResolvedValue({
      remote: 'trueforge',
      op: 'routines',
      ok: true,
      detail: 'TrueForge listed 0 routine(s)',
      data: { routines: [] },
    })
    vi.spyOn(api, 'probeRemoteHealth').mockResolvedValue({
      remote: 'trueforge',
      ok: false,
      state: 'DOWN',
      detail: 'Connection refused',
    })

    renderPane({
      id: 'trueforge',
      label: 'TrueForge',
      base_url: 'http://127.0.0.1:8791',
      capabilities: { routines: true },
    } as any)

    expect(screen.getByTestId('remote-routines-section')).toBeInTheDocument()

    const healthBtn = screen.getByRole('button', { name: /health/i })
    fireEvent.click(healthBtn)

    await waitFor(() => {
      expect(screen.getByText(/report, not a crash/i)).toBeInTheDocument()
      expect(screen.queryByTestId('remote-routines-section')).not.toBeInTheDocument()
    })
  })
})
