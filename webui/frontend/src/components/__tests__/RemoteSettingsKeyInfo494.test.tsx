/**
 * #494 scope 3 — the Remotes pane's API-key field needs an info affordance:
 * which env var this seat reads, whether it is currently set, and the actual
 * precedence relationship from provenance (env does NOT blanket-override).
 * Plus the correction: a literal key can never be stored in this field.
 */
import { describe, expect, it } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { RemoteOperatePane } from '../RemotesSettings'
import { ToastProvider } from '../DaisyUI'
import type { RemoteConnection } from '../../lib/api'

function renderPane(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{node}</ToastProvider>
    </QueryClientProvider>,
  )
}

function remote(overrides: Partial<RemoteConnection> = {}): RemoteConnection {
  return {
    id: 'omb',
    kind: 'omb',
    title: '',
    base_url: 'http://127.0.0.1:9',
    api_key_env: 'OMB_API_KEY',
    api_key_set: false,
    ...overrides,
  } as RemoteConnection
}

describe('RemoteOperatePane #494 api-key info affordance', () => {
  it('reveals the env var, its set state, and the env-only rule behind the info toggle', () => {
    renderPane(
      <RemoteOperatePane remote={remote({ api_key_set: false })} />,
    )
    const toggle = screen.getByTestId('remote-api-key-info-toggle')
    fireEvent.click(toggle)
    const info = screen.getByTestId('remote-api-key-info')
    expect(info).toHaveTextContent('OMB_API_KEY')
    expect(info).toHaveTextContent(/not set/i)
    expect(info).toHaveTextContent(/env var name/i)
    expect(info).toHaveTextContent(/literal key/i)
  })

  it('says the env var is set when api_key_set is true', () => {
    renderPane(
      <RemoteOperatePane remote={remote({ api_key_set: true })} />,
    )
    fireEvent.click(screen.getByTestId('remote-api-key-info-toggle'))
    expect(screen.getByTestId('remote-api-key-info')).toHaveTextContent(/set/i)
  })

  it('shows the forced-by-env precedence from provenance', () => {
    renderPane(
      <RemoteOperatePane
        remote={remote({
          api_key_set: true,
          provenance: {
            api_key: {
              kind: 'forced',
              label: 'Forced by env OMB_API_KEY (read-only)',
              env_var: 'OMB_API_KEY',
              forced: true,
            },
          },
        })}
      />,
    )
    fireEvent.click(screen.getByTestId('remote-api-key-info-toggle'))
    expect(screen.getByTestId('remote-api-key-info')).toHaveTextContent(
      /Forced by env OMB_API_KEY/,
    )
  })
})
