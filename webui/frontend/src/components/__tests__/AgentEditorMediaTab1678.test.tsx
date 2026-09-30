/**
 * #1678 — the Media tab is wired into the agent editor, and the editor's
 * tab-persistence contract still holds.
 *
 * Two things worth pinning here beyond "the tab exists":
 *  - the index is read only when the tab is selected, because every other
 *    panel stays mounted-but-hidden and a media fetch on every editor open
 *    would be a request nobody asked for;
 *  - the panel is still mounted while another tab is selected, so #1127's
 *    "in-progress edits survive a tab switch" contract is not quietly broken
 *    for the newest panel.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'

const CATALOG = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Worker seat',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
]

function stubApis(media: unknown[] | 'fail' = []) {
  const calls: string[] = []
  const fetchMock = vi
    .fn()
    .mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      if (url.includes('/v1/agents/codey/media')) {
        if (media === 'fail') {
          return { ok: false, status: 500, json: async () => ({ error: 'index down' }) } as Response
        }
        return { ok: true, status: 200, json: async () => ({ media }) } as Response
      }
      if (url.includes('/profile')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_profile',
            agent_id: 'codey',
            display_name: 'Codey',
            description: '',
            title: '',
            role: '',
            avatar_shape: 'circle',
            avatar_color: '',
            avatar_path: null,
            profile: {
              display_name: 'Codey',
              description: '',
              title: '',
              role: '',
              avatar_shape: 'circle',
              avatar_color: '',
              avatar_path: null,
            },
          }),
        } as Response
      }
      if (url.includes('/v1/agents/') && url.includes('/settings')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ new_chat_per_task: false, use_suggestions: false, folder: '' }),
        } as Response
      }
      if (url.includes('/personas')) {
        return { ok: true, status: 200, json: async () => ({ personas: [] }) } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return { ok: true, status: 200, json: async () => ({ clis: [] }) } as Response
      }
      if (url.includes('/v1/agents/llm-profiles')) {
        return { ok: true, status: 200, json: async () => ({ profiles: [] }) } as Response
      }
      if (url.includes('/v1/remotes')) {
        return { ok: true, status: 200, json: async () => ({ remotes: [] }) } as Response
      }
      if (url.includes('/image-gen')) {
        return { ok: true, status: 200, json: async () => ({}) } as Response
      }
      return { ok: true, status: 200, json: async () => ({ data: CATALOG }) } as Response
    })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={vi.fn()} agentId="codey" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('#1678 Media tab in the agent editor', () => {
  it('is a labelled tab in the vertical rail, right after Identity', async () => {
    stubApis()
    renderEditor()
    const rail = screen.getByTestId('agent-editor-tabs')
    const tabs = within(rail).getAllByRole('tab')
    const labels = tabs.map((tab) => tab.textContent)
    expect(labels.indexOf('Media')).toBe(labels.indexOf('Identity') + 1)
    const mediaTab = within(rail).getByRole('tab', { name: 'Media' })
    expect(mediaTab).toHaveAttribute('aria-controls', 'agent-editor-panel-media')
  })

  it('does not read the media index while another tab is selected', async () => {
    const calls = stubApis()
    renderEditor()
    await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    await waitFor(() => {
      expect(calls.some((url) => url.includes('/media'))).toBe(false)
    })
  })

  it('reads the index and shows the empty state when the tab is selected', async () => {
    const calls = stubApis([])
    renderEditor()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Media' }),
    )
    const panel = screen.getByTestId('agent-media-panel')
    expect(panel.closest('[role="tabpanel"]')).not.toHaveAttribute('hidden')
    await waitFor(() => expect(screen.getByTestId('agent-media-empty')).toBeInTheDocument())
    expect(calls.some((url) => url.includes('/v1/agents/codey/media/'))).toBe(true)
  })

  it('a failing index shows the error inside the tab, never the empty state', async () => {
    stubApis('fail')
    renderEditor()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Media' }),
    )
    await waitFor(() => expect(screen.getByTestId('agent-media-error')).toBeInTheDocument())
    expect(screen.queryByTestId('agent-media-empty')).not.toBeInTheDocument()
  })

  it('stays mounted-but-hidden on another tab, like every other panel', async () => {
    stubApis([])
    renderEditor()
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Media' }),
    )
    await waitFor(() => expect(screen.getByTestId('agent-media-empty')).toBeInTheDocument())
    fireEvent.click(
      within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Role & wiring' }),
    )
    const panel = screen.getByTestId('agent-media-panel')
    expect(panel).toBeInTheDocument()
    expect(panel.closest('[role="tabpanel"]')).toHaveAttribute('hidden')
  })
})
