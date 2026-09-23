import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import { saveAgentEdit } from '../../lib/agentEdits'
import ChatPage from '../ChatPage'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  onopen: ((e?: unknown) => void) | null = null
  onclose: ((e?: unknown) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }
}

function renderChat(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('navbar workspace subtitle (#65)', () => {
  beforeEach(() => {
    localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('hides the subtitle when no folder, workspace, or branch is bound', async () => {
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const card = screen.getByTestId('selected-agent-header')
    expect(card).toHaveTextContent('Support')
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).not.toBeInTheDocument()
    const title = card.querySelector('h1')
    expect(title).toHaveClass('os-navbar-identity-label')
    expect(title).not.toHaveClass('truncate')
  })

  it('renders a muted folder — branch subtitle under the agent name', async () => {
    saveAgentEdit('support', {
      folder: '/home/dev/very/long/path/to/open-swarm-private',
      gitBranch: 'main',
    })
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const subtitle = screen.getByTestId('os-navbar-workspace-subtitle')
    expect(subtitle.tagName).toBe('P')
    expect(subtitle).toHaveClass('os-navbar-identity-subtitle')
    expect(subtitle).toHaveTextContent(
      '/home/dev/very/long/path/to/open-swarm-private — branch: main',
    )
    expect(subtitle).toHaveAttribute(
      'title',
      '/home/dev/very/long/path/to/open-swarm-private — branch: main',
    )
    const card = screen.getByTestId('selected-agent-header')
    expect(card.querySelector('h1')).toHaveTextContent('Support')
    expect(card.querySelector('.os-navbar-identity-text')).toContainElement(subtitle)
  })

  it('updates the subtitle when folder or branch changes', async () => {
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).not.toBeInTheDocument()

    await act(async () => {
      saveAgentEdit('support', { folder: '/tmp/proj' })
    })
    expect(screen.getByTestId('os-navbar-workspace-subtitle')).toHaveTextContent('/tmp/proj')

    await act(async () => {
      saveAgentEdit('support', { gitBranch: 'feat/x' })
    })
    expect(screen.getByTestId('os-navbar-workspace-subtitle')).toHaveTextContent(
      '/tmp/proj — branch: feat/x',
    )

    await act(async () => {
      saveAgentEdit('support', { folder: '', gitBranch: '' })
    })
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).not.toBeInTheDocument()
  })
})
