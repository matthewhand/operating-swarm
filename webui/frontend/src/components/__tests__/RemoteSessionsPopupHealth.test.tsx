import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RemoteSessionsPopup from '../RemoteSessionsPopup'
import type { RemoteConnection } from '../../lib/api'
import {
  publishChatConnection,
  resetChatConnection,
} from '../../lib/chatConnection'

describe('REQ-195: RemoteSessionsPopup health indicators', () => {
  beforeEach(() => {
    resetChatConnection()
  })

  afterEach(() => {
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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, state: 'healthy', detail: 'OK' }),
      } as Response),
    )

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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes/remote-1/health/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ ok: true, state: 'healthy', detail: 'OK' }),
          } as Response
        }
        if (url.includes('/v1/remotes/remote-2/health/')) {
          return {
            ok: false,
            status: 500,
            json: async () => ({ ok: false, state: 'error', detail: 'Down' }),
          } as Response
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({ error: 'not found' }),
        } as Response
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

    // remote-2 fails -> red dot shown
    await waitFor(() => {
      expect(screen.getByTestId('remote-health-dot-remote-2')).toBeInTheDocument()
    })

    // remote-1 succeeds -> no red dot
    expect(screen.queryByTestId('remote-health-dot-remote-1')).not.toBeInTheDocument()
  })

  it('paints red-dot on local indicator when WS is disconnected and clears on reconnect', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, state: 'healthy', detail: 'OK' }),
      } as Response),
    )

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
