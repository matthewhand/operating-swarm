import { type ComponentProps } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LibraryScopeBar } from '../LibraryScopeBar'

type FetchInit = { method?: string; body?: string }

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  } as Response
}

function renderBar(props: Partial<ComponentProps<typeof LibraryScopeBar>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <LibraryScopeBar surface="library" itemKey="helper" itemTitle="Helper" {...props} />
    </QueryClientProvider>,
  )
}

describe('LibraryScopeBar (#1311)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps Mine on the personal library and offers preset rail seats', () => {
    renderBar()
    expect(screen.getByRole('button', { name: 'Mine' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Mine keeps the personal library/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add Support to rail' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument()
  })

  it('refuses Team publish until a roster is chosen, then sends that team_id', async () => {
    const calls: Array<{ url: string; method: string; body?: unknown }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: FetchInit) => {
        const url = String(input)
        const method = init?.method || 'GET'
        const body = init?.body ? JSON.parse(init.body) : undefined
        calls.push({ url, method, body })
        if (url.includes('/v1/team-rosters') && method === 'GET') {
          return jsonResponse({
            object: 'list',
            data: [
              { id: 'eng', name: 'Engineering', members: [], object: 'team_roster' },
              { id: 'sales', name: 'Sales', members: [], object: 'team_roster' },
            ],
          })
        }
        if (url.includes('/v1/library/') && method === 'GET') {
          return jsonResponse({ object: 'list', data: [] })
        }
        if (url.includes('/v1/library/') && method === 'POST') {
          return jsonResponse({ id: '1', object: 'shared_library.item', scope: 'team', title: 'Helper' }, 201)
        }
        return jsonResponse({ object: 'list', data: [] })
      }),
    )

    renderBar()
    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    const publish = await screen.findByRole('button', { name: 'Publish' })
    expect(publish).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Team' })).toBeInTheDocument()

    await screen.findByRole('option', { name: 'Engineering' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Team' }), { target: { value: 'eng' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Publish' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }))

    await waitFor(() => {
      expect(screen.getByTestId('library-scope-notice')).toHaveTextContent('Blueprint published.')
    })
    const posted = calls.find((call) => call.method === 'POST' && call.url.includes('/v1/library/'))
    expect(posted?.body).toMatchObject({
      action: 'publish',
      scope: 'team',
      team_id: 'eng',
      id: 'helper',
      kind: 'blueprint',
    })
  })

  it('publishes to Organisation without a team id', async () => {
    const calls: Array<{ url: string; method: string; body?: unknown }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: FetchInit) => {
        const url = String(input)
        const method = init?.method || 'GET'
        calls.push({ url, method, body: init?.body ? JSON.parse(init.body) : undefined })
        if (method === 'POST') {
          return jsonResponse({ id: '9', object: 'shared_library.item', scope: 'org', title: 'Helper' }, 201)
        }
        return jsonResponse({ object: 'list', data: [] })
      }),
    )

    renderBar()
    fireEvent.click(screen.getByRole('button', { name: 'Organisation' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    await waitFor(() => {
      expect(screen.getByTestId('library-scope-notice')).toHaveTextContent('Blueprint published.')
    })
    const posted = calls.find((call) => call.method === 'POST')
    expect(posted?.body).toMatchObject({ action: 'publish', scope: 'org', id: 'helper' })
    expect(posted?.body).not.toHaveProperty('team_id')
  })

  it('adds a preset onto the rail and shows a missing-dependency import', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: FetchInit) => {
        const url = String(input)
        const method = init?.method || 'GET'
        const body = init?.body ? JSON.parse(String(init.body)) : undefined
        if (url.includes('/v1/library/') && method === 'POST' && body?.action === 'create_preset') {
          return jsonResponse({
            id: 'preset-support',
            name: 'Support',
            rail: true,
            role: 'support',
            provider: 'openai',
            model: 'gpt-4o-mini',
            plugins: ['support-tools'],
          }, 201)
        }
        if (url.includes('/v1/library/') && method === 'GET') {
          return jsonResponse({
            object: 'list',
            data: [
              {
                id: '44',
                object: 'shared_library.item',
                scope: 'org',
                title: 'Field pack',
                item_key: 'field',
              },
            ],
          })
        }
        if (url.includes('/v1/library/') && method === 'POST' && body?.action === 'import') {
          return jsonResponse({
            imported: true,
            needs_configuration: [{ id: 'scout', reason: 'Blueprint not available — needs configuration.' }],
          })
        }
        return jsonResponse({ object: 'list', data: [] })
      }),
    )

    renderBar()
    fireEvent.click(screen.getByRole('button', { name: 'Add Support to rail' }))
    await waitFor(() => {
      expect(screen.getByTestId('library-scope-notice')).toHaveTextContent('Support is on the rail.')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Organisation' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))
    await waitFor(() => {
      expect(screen.getByTestId('library-scope-notice')).toHaveTextContent(
        'Imported. Missing: Blueprint not available — needs configuration.',
      )
    })
  })
})
