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
    expect(subtitle.tagName).toBe('BUTTON')
    expect(subtitle).toHaveClass('os-navbar-identity-subtitle')
    // #1257: leading ellipsis keeps the rightmost 32 chars of the folder.
    expect(subtitle).toHaveTextContent(
      '.../long/path/to/open-swarm-private — branch: main',
    )
    // Tooltip keeps the complete, un-truncated path.
    expect(subtitle).toHaveAttribute(
      'title',
      '/home/dev/very/long/path/to/open-swarm-private — branch: main',
    )
    const card = screen.getByTestId('selected-agent-header')
    expect(card.querySelector('h1')).toHaveTextContent('Support')
    expect(card.querySelector('.os-navbar-identity-text')).toContainElement(subtitle)
  })

  it('clicking the subtitle opens the folder/agent settings flow', async () => {
    saveAgentEdit('support', { folder: '/tmp/proj' })
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const openSpy = vi.fn()
    window.addEventListener('swarm:open-agent-editor', openSpy)
    screen.getByTestId('os-navbar-workspace-subtitle').click()
    window.removeEventListener('swarm:open-agent-editor', openSpy)
    expect(openSpy).toHaveBeenCalledTimes(1)
  })

  it('reveals an unset "Select folder" affordance that opens the folder flow', async () => {
    // A CLI seat: its editor destination really has the folder control, so the
    // offer is honest. This used to run against `support` (an API seat) and
    // assert the control was there — which was the #1713 dead end.
    renderChat('/chat?blueprint=cli_codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).not.toBeInTheDocument()
    const unset = screen.getByTestId('os-navbar-workspace-subtitle-unset')
    expect(unset.tagName).toBe('BUTTON')
    expect(unset).toHaveClass('os-navbar-identity-subtitle--unset')
    const openSpy = vi.fn()
    window.addEventListener('swarm:open-agent-editor', openSpy)
    unset.click()
    window.removeEventListener('swarm:open-agent-editor', openSpy)
    expect(openSpy).toHaveBeenCalledTimes(1)
  })

  it('does NOT offer it on an API seat, whose editor has no folder control', async () => {
    // The other half of #1713, on the seat the affordance used to appear on.
    // A control that looks actionable and lands on a "Coming soon" stub is the
    // defect; asserting its absence here is what keeps it fixed.
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(screen.queryByTestId('os-navbar-workspace-subtitle-unset')).toBeNull()
    // The subtitle row itself is untouched — only the unset button is gated.
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).toBeNull()
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
