/**
 * #1434 — Settings → System shows the resolved config root.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SystemPane } from '../settings/panes/SystemPane'

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('#1434 settings config root', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the resolved config root from config ownership', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/config-ownership/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'config_ownership',
              decision: 'Full',
              note: 'coverage',
              force_env: false,
              force_env_var: 'SWARM_CONFIG_FORCE_ENV',
              advanced_sections: [],
              inventory: [],
              config_root: '/tmp/example-config-root',
              config_root_env: 'SWARM_CONFIG_DIR',
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            created: false,
            size_bytes: 0,
            path: '',
            conversation_count: 0,
            message_count: 0,
          }),
        } as Response
      }),
    )

    render(
      <QueryClientProvider client={client()}>
        <SystemPane />
      </QueryClientProvider>,
    )

    expect(await screen.findByTestId('settings-config-root')).toHaveTextContent(
      '/tmp/example-config-root',
    )
    expect(screen.getByTestId('settings-config-root')).toHaveTextContent('SWARM_CONFIG_DIR')
  })
})
