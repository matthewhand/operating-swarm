import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RemoteSessionsPopup from '../RemoteSessionsPopup'
import type { RemoteConnection } from '../../lib/api'
import {
  publishChatConnection,
  resetChatConnection,
} from '../../lib/chatConnection'
import {
  __resetRemoteHealthForTests,
  stopRemoteHealthPolling,
} from '../../lib/remoteHealth'

/**
 * #1783: the popup's health dots come from the shared remote-health store, and
 * the store probes over ONE batched write. Before this the popup fired a
 * `POST /v1/remotes/<id>/health/` per browsable remote on every open, and again
 * on every `remotes` poll while it stayed open — the N-per-open half of the
 * traffic the issue is about. The last test in this file counts the actual
 * requests so that cannot come back quietly.
 */

/** A seat-batch reply that marks the named remote ids broken. */
function batchReply(down: string[]) {
  return async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    if (url === '/v1/seats/health') {
      const body = JSON.parse(String(init?.body || '{}')) as {
        seats?: { kind: string; seat_id: string }[]
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'seat_health_batch',
          checked: (body.seats || []).length,
          broken: down.length,
          results: (body.seats || []).map((s) => ({
            seat_id: s.seat_id,
            kind: s.kind,
            state: down.includes(s.seat_id) ? 'broken' : 'ok',
            reason: '',
            latency_ms: 1,
            checked_at: 1_700_000_000_000,
            broken: down.includes(s.seat_id),
          })),
        }),
      } as Response
    }
    return {
      ok: false,
      status: 404,
      json: async () => ({ error: 'not found' }),
    } as Response
  }
}

describe('REQ-195: RemoteSessionsPopup health indicators', () => {
  beforeEach(() => {
    resetChatConnection()
    stopRemoteHealthPolling('popup')
    __resetRemoteHealthForTests()
  })

  afterEach(() => {
    stopRemoteHealthPolling('popup')
    __resetRemoteHealthForTests()
    resetChatConnection()
    vi.unstubAllGlobals()
  })

  const testRemotes: RemoteConnection[] = [
    {
      id: 'remote-1',
      title: 'Remote One',
      base_url: 'http://198.51.100.10:8000',
    },
    {
      id: 'remote-2',
      title: 'Remote Two',
      base_url: 'http://198.51.100.20:8000',
    },
  ]

  it('renders a server icon for each browsable remote', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ object: 'seat_health_batch', results: [], checked: 0, broken: 0 }),
    } as Response))

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={vi.fn()}
        remotes={testRemotes}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    expect(screen.getByTestId('remote-server-icon-remote-1')).toBeInTheDocument()
    expect(screen.getByTestId('remote-server-icon-remote-2')).toBeInTheDocument()
  })

  it('displays red-dot overlay when remote health fails, and no red-dot when ok', async () => {
    vi.stubGlobal('fetch', vi.fn(batchReply(['remote-2'])))

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={vi.fn()}
        remotes={testRemotes}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    // remote-2 fails -> red dot shown
    await waitFor(() => {
      expect(screen.getByTestId('remote-health-dot-remote-2')).toBeInTheDocument()
    })

    // remote-1 succeeds -> no red dot
    expect(screen.queryByTestId('remote-health-dot-remote-1')).not.toBeInTheDocument()
  })

  it('NON-REGRESSION GUARD: a remote nothing was said about is not painted offline', async () => {
    // The batch answers `unknown` for remote-2 — no verdict, not a fault. The
    // dot must stay off rather than inventing an offline gateway.
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo, init?: RequestInit) => {
        const stub = batchReply([])
        const res = await stub(input, init)
        const body = await res.json()
        body.results = body.results.map((r: { seat_id: string }) =>
          r.seat_id === 'remote-2' ? { ...r, state: 'unknown', broken: false } : r,
        )
        return { ...res, json: async () => body } as Response
      }),
    )

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={vi.fn()}
        remotes={testRemotes}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('remote-server-icon-remote-1')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('remote-health-dot-remote-2')).not.toBeInTheDocument()
  })

  it('#1783: two remotes cost ONE health request, and no per-remote probe at all', async () => {
    const fetchMock = vi.fn(batchReply([]))
    vi.stubGlobal('fetch', fetchMock)

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={vi.fn()}
        remotes={testRemotes}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) => String(input) === '/v1/seats/health'),
      ).toHaveLength(1)
    })
    // The whole point: the per-remote write this popup used to fire N of is not
    // sent even once, and the batch that is sent carries both ids.
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        /\/v1\/remotes\/[^/]+\/health\//.test(String(input)),
      ),
    ).toHaveLength(0)
    const [, init] = fetchMock.mock.calls.find(([input]) => String(input) === '/v1/seats/health')!
    const body = JSON.parse(String((init as RequestInit)?.body))
    expect(body.seats.map((s: { seat_id: string }) => s.seat_id).sort()).toEqual([
      'remote-1',
      'remote-2',
    ])
  })

  it('paints red-dot on local indicator when WS is disconnected and clears on reconnect', async () => {
    vi.stubGlobal('fetch', vi.fn(batchReply([])))

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={vi.fn()}
        remotes={testRemotes}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    // Initially connecting/open: no red dot on local
    expect(screen.queryByTestId('popup-local-health-dot')).not.toBeInTheDocument()

    // Disconnect WS
    act(() => {
      publishChatConnection('closed')
    })

    expect(screen.getByTestId('popup-local-health-dot')).toBeInTheDocument()

    // Reconnect WS
    act(() => {
      publishChatConnection('open')
    })

    expect(screen.queryByTestId('popup-local-health-dot')).not.toBeInTheDocument()
  })
})
