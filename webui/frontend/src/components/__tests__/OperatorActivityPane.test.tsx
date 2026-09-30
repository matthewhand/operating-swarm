import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI'
import { OperatorActivityPane } from '../settings/panes/OperatorActivityPane'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: new Headers(),
  } as Response
}

function prefsPayload() {
  return {
    object: 'user_preferences',
    principal: 'user:alice',
    guest: false,
    empty: false,
    favourites: [],
    hidden_agents: [],
    hostname_override: '',
    activity_log_visibility: 'operator',
    values: {},
  }
}

function activityPayload(items: Array<Record<string, unknown>> = []) {
  return {
    object: 'activity_list',
    items,
    count: items.length,
    visibility: 'operator',
  }
}

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <OperatorActivityPane />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1314 OperatorActivityPane', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  it('renders activity rows from GET /v1/activity/', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/preferences/')) return jsonResponse(prefsPayload())
        if (url.includes('/v1/activity/')) {
          return jsonResponse(
            activityPayload([
              {
                id: 'evt-1',
                actor_type: 'user',
                actor_id: 'user:alice',
                action: 'agent.created',
                entity_type: 'agent',
                entity_id: 'desk_bot',
                created_at: '2026-09-27T12:00:00Z',
              },
            ]),
          )
        }
        return jsonResponse({ object: 'list', data: [] })
      }),
    )
    renderPane()
    expect(screen.getByTestId('operator-activity-pane')).toBeInTheDocument()
    expect(await screen.findByTestId('operator-activity-row')).toHaveTextContent('agent.created')
    expect(screen.getByTestId('operator-activity-row')).toHaveTextContent('user:alice')
  })

  it('denies a non-operator with operator visibility', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/preferences/')) return jsonResponse(prefsPayload())
        if (url.includes('/v1/activity/')) {
          return jsonResponse({ error: 'operator visibility only' }, 403)
        }
        return jsonResponse({ object: 'list', data: [] })
      }),
    )
    renderPane()
    expect(await screen.findByText('Operator visibility only.')).toBeInTheDocument()
  })

  it('patches activity_log_visibility through preferences', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/v1/preferences/') && init?.method === 'PATCH') {
        return jsonResponse({ ...prefsPayload(), activity_log_visibility: 'all' })
      }
      if (url.includes('/v1/preferences/')) return jsonResponse(prefsPayload())
      if (url.includes('/v1/activity/')) return jsonResponse(activityPayload())
      return jsonResponse({ object: 'list', data: [] })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPane()
    const select = await screen.findByTestId('activity-visibility-select')
    fireEvent.change(select, { target: { value: 'all' } })
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        (call) => String(call[0]).includes('/v1/preferences/') && call[1]?.method === 'PATCH',
      )
      expect(patch).toBeTruthy()
      expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({
        activity_log_visibility: 'all',
      })
    })
  })
})
