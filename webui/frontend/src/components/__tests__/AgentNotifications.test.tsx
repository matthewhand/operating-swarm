import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { ToastProvider } from '../DaisyUI'
import {
  NOTIFY_AGENTS_STORAGE_KEY,
  enableAgentNotify,
  resetNotifyDedupe,
} from '../../lib/agentNotifications'
import { GENERATION_COMPLETE_EVENT } from '../../lib/railOrder'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

class MockNotification {
  static permission: NotificationPermission = 'granted'
  static requestPermission = vi.fn(async () => MockNotification.permission)
  static instances: MockNotification[] = []

  title: string
  options: NotificationOptions | undefined
  onclick: ((this: Notification, ev: Event) => void) | null = null
  close = vi.fn()

  constructor(title: string, options?: NotificationOptions) {
    this.title = title
    this.options = options
    MockNotification.instances.push(this)
  }
}

function SearchProbe() {
  const [params] = useSearchParams()
  return <span data-testid="os-test-search">{params.toString()}</span>
}

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/blueprints')) {
      return {
        ok: true,
        json: async () => ({
          data: [
            { id: 'codey', name: 'Codey', role: 'default', rail: true },
            { id: 'stewie', name: 'Stewie', role: 'default', rail: true },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/remotes')) {
      return {
        ok: true,
        json: async () => ({
          object: 'list',
          data: [
            {
              id: 'omb',
              title: 'OMB',
              configured: true,
              agents: [{ id: 'omb-cos', name: 'CoS' }],
            },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        json: async () => ({
          object: 'user_preferences',
          empty: true,
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    return {
      ok: true,
      json: async () => ({ results: [], data: [] }),
    } as Response
  })
}

function renderRail(initialRoute = '/chat?blueprint=codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            <Route
              path="/chat"
              element={
                <>
                  <AgentSidebar />
                  <SearchProbe />
                </>
              }
            />
            <Route path="/" element={<AgentSidebar />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('REQ-98: per-agent rail notifications', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    resetNotifyDedupe()
    MockNotification.instances = []
    MockNotification.permission = 'granted'
    MockNotification.requestPermission = vi.fn(async () => MockNotification.permission)
    vi.stubGlobal('Notification', MockNotification)
    vi.stubGlobal('fetch', mockFetch())
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    resetNotifyDedupe()
  })

  it('defaults Off and persists Notifications On/Off per agent id', async () => {
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    const codey = within(list).getByRole('link', { name: /codey/i })

    fireEvent.contextMenu(codey)
    const offItem = await screen.findByRole('menuitem', { name: /Notifications: Off/i })
    expect(offItem).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(offItem)
    })
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY) || '[]')).toEqual(['codey'])
    })
    expect(MockNotification.requestPermission).not.toHaveBeenCalled()

    fireEvent.contextMenu(codey)
    const onItem = await screen.findByRole('menuitem', { name: /Notifications: On/i })
    await act(async () => {
      fireEvent.click(onItem)
    })
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY) || '[]')).toEqual([])
    })
  })

  it('requests permission on first enable when permission is default', async () => {
    MockNotification.permission = 'default'
    MockNotification.requestPermission.mockResolvedValueOnce('granted')
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(within(list).getByRole('link', { name: /stewie/i }))
    await act(async () => {
      fireEvent.click(await screen.findByRole('menuitem', { name: /Notifications: Off/i }))
    })
    await waitFor(() => {
      expect(MockNotification.requestPermission).toHaveBeenCalledTimes(1)
      expect(JSON.parse(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY) || '[]')).toEqual(['stewie'])
    })
  })

  it('shows a quiet hint when permission is denied and does not throw', async () => {
    MockNotification.permission = 'default'
    MockNotification.requestPermission.mockResolvedValueOnce('denied')
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(within(list).getByRole('link', { name: /codey/i }))
    await act(async () => {
      fireEvent.click(await screen.findByRole('menuitem', { name: /Notifications: Off/i }))
    })
    const hint = await screen.findByTestId('notify-permission-hint')
    expect(hint).toHaveTextContent(/browser site settings/i)
    expect(hint).toHaveAttribute('data-outcome', 'denied')
    expect(JSON.parse(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY) || '[]')).toEqual(['codey'])
  })

  it('#546: a prompt that never appears says so, and offers to ask again', async () => {
    // `default` in, `default` out: the browser never asked. The old copy sent the
    // user to site settings for a prompt they had not yet been shown.
    MockNotification.permission = 'default'
    MockNotification.requestPermission.mockResolvedValue('default')
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(within(list).getByRole('link', { name: /codey/i }))
    await act(async () => {
      fireEvent.click(await screen.findByRole('menuitem', { name: /Notifications: Off/i }))
    })

    const hint = await screen.findByTestId('notify-permission-hint')
    expect(hint).toHaveAttribute('data-outcome', 'never-asked')
    expect(hint).not.toHaveTextContent(/blocked/i)
    expect(hint).toHaveTextContent(/never asked/i)

    // The action is reachable, and it re-asks rather than dead-ending.
    const retry = within(hint).getByTestId('notify-permission-retry')
    MockNotification.requestPermission.mockResolvedValueOnce('granted')
    await act(async () => {
      fireEvent.click(retry)
    })
    await waitFor(() => {
      expect(screen.queryByTestId('notify-permission-hint')).not.toBeInTheDocument()
    })
  })

  it('#546: an unavailable Notification API names the real fix, not site settings', async () => {
    // A plain-HTTP LAN address: Chrome does not expose the API at all, so no
    // site setting can enable it — the old copy claimed "blocked", which is the
    // wrong fix for this row of the table.
    vi.stubGlobal('Notification', undefined)
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(within(list).getByRole('link', { name: /codey/i }))
    await act(async () => {
      fireEvent.click(await screen.findByRole('menuitem', { name: /Notifications: Off/i }))
    })

    const hint = await screen.findByTestId('notify-permission-hint')
    expect(hint).toHaveAttribute('data-outcome', 'unsupported')
    expect(hint).toHaveTextContent(/secure context/i)
    expect(hint).toHaveTextContent(/HTTPS or localhost/i)
    expect(hint).not.toHaveTextContent(/site settings/i)
  })

  it('#546: a request that throws is not reported as a denial', async () => {
    MockNotification.permission = 'default'
    MockNotification.requestPermission.mockRejectedValueOnce(new Error('no user gesture'))
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    fireEvent.contextMenu(within(list).getByRole('link', { name: /codey/i }))
    await act(async () => {
      fireEvent.click(await screen.findByRole('menuitem', { name: /Notifications: Off/i }))
    })

    const hint = await screen.findByTestId('notify-permission-hint')
    // Previously the catch returned the current permission, making a failed
    // prompt indistinguishable from a denial — and the reason was discarded.
    expect(hint).not.toHaveTextContent(/browser site settings/i)
    expect(hint).toHaveTextContent(/blocked the permission request/i)
  })

  it('fires Notification for an unselected agent when On + granted', async () => {
    enableAgentNotify('stewie')
    renderRail('/chat?blueprint=codey')
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    act(() => {
      window.dispatchEvent(
        new CustomEvent(GENERATION_COMPLETE_EVENT, {
          detail: { agentId: 'stewie', snippet: 'All green', agentName: 'Stewie' },
        }),
      )
    })
    expect(MockNotification.instances).toHaveLength(1)
    expect(MockNotification.instances[0].title).toBe('Stewie')
    expect(MockNotification.instances[0].options?.body).toBe('All green')
  })

  it('does not fire when the selected agent completes in a visible tab', async () => {
    enableAgentNotify('codey')
    renderRail('/chat?blueprint=codey')
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    act(() => {
      window.dispatchEvent(
        new CustomEvent(GENERATION_COMPLETE_EVENT, {
          detail: { agentId: 'codey', snippet: 'should stay quiet' },
        }),
      )
    })
    expect(MockNotification.instances).toHaveLength(0)
  })

  it('fires when the tab is hidden even if that agent is selected', async () => {
    enableAgentNotify('codey')
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    renderRail('/chat?blueprint=codey')
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    act(() => {
      window.dispatchEvent(
        new CustomEvent(GENERATION_COMPLETE_EVENT, {
          detail: { agentId: 'codey', snippet: 'background done', agentName: 'Codey' },
        }),
      )
    })
    expect(MockNotification.instances).toHaveLength(1)
    expect(MockNotification.instances[0].title).toBe('Codey')
  })

  it('clicking a popup selects that agent chat', async () => {
    enableAgentNotify('stewie')
    renderRail('/chat?blueprint=codey')
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    act(() => {
      window.dispatchEvent(
        new CustomEvent(GENERATION_COMPLETE_EVENT, {
          detail: { agentId: 'stewie', snippet: 'ping', agentName: 'Stewie' },
        }),
      )
    })
    expect(screen.getByTestId('os-test-search').textContent).toContain('blueprint=codey')
    act(() => {
      MockNotification.instances[0].onclick?.call(
        MockNotification.instances[0] as unknown as Notification,
        new Event('click'),
      )
    })
    await waitFor(() => {
      expect(screen.getByTestId('os-test-search').textContent).toContain('blueprint=stewie')
    })
  })

  it('toggles remotes by row id and keeps the OpenMousBot label', async () => {
    renderRail()
    await waitFor(() => {
      expect(screen.queryByText('Loading agents…')).not.toBeInTheDocument()
    })
    const list = screen.getByRole('navigation', { name: 'Agent list' })
    const omb = await within(list).findByRole('link', { name: /OpenMousBot \(remote\)/ })
    expect(omb).not.toHaveTextContent(/\bOMB\b/)
    fireEvent.contextMenu(omb)
    await act(async () => {
      fireEvent.click(await screen.findByRole('menuitem', { name: /Notifications: Off/i }))
    })
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY) || '[]')).toEqual([
        'remote:omb',
      ])
    })
    enableAgentNotify('remote:omb')
    resetNotifyDedupe()
    act(() => {
      window.dispatchEvent(
        new CustomEvent(GENERATION_COMPLETE_EVENT, {
          detail: { agentId: 'remote:omb', snippet: 'remote done' },
        }),
      )
    })
    expect(MockNotification.instances.at(-1)?.title).toBe('OpenMousBot')
    expect(MockNotification.instances.at(-1)?.title).not.toMatch(/\bOMB\b/)
  })
})
