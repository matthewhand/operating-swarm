import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import { RemoteOperatePane } from '../RemotesSettings'

function renderSheet() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet isOpen={true} onClose={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('REQ-100 Herdr remotes are SSH-shaped', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows SSH-shaped copy and posts host/user without a private key', async () => {
    let postPayload: Record<string, unknown> | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        // Only the create call is the subject here. #453 added a target list on
        // pane mount, which POSTs to /v1/remotes/<id>/operate/ right after a
        // save selects the new remote — capturing that would clobber the payload.
        if (url.includes('/v1/remotes/') && !url.includes('/operate/') && init?.method === 'POST') {
          postPayload = JSON.parse(String(init.body))
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: 'herdr',
              kind: 'herdr',
              herdr_mode: 'ssh',
              ssh_host: 'herdr.example.test',
              ssh_user: 'herdr',
              transport: 'ssh',
              title: 'Herdr',
            }),
          }
        }
        if (url.includes('/v1/remotes/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              kinds: [
                { id: 'omb', label: 'OpenMousBot' },
                { id: 'herdr', label: 'Herdr' },
              ],
              configured: [],
              data: [],
            }),
          }
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        }
      }),
    )

    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))

    await waitFor(() => {
      expect(screen.getByText(/SSH-shaped/i)).toBeInTheDocument()
      expect(screen.getByText('No remotes configured yet.')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))

    // #573: kind is picked in the popup now
    fireEvent.click(screen.getByTestId('remote-kind-herdr'))

    expect(screen.getByText(/not HTTP/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/^URL$/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^API key$/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Herdr location/i), { target: { value: 'ssh' } })
    fireEvent.change(screen.getByLabelText(/SSH host/i), { target: { value: 'herdr.example.test' } })
    fireEvent.change(screen.getByLabelText(/SSH user/i), { target: { value: 'herdr' } })
    fireEvent.change(screen.getByLabelText(/SSH identity env/i), {
      target: { value: 'HERDR_SSH_IDENTITY' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Save remote' }))

    await waitFor(() => {
      expect(postPayload).not.toBeNull()
    })
    const payload = postPayload as unknown as Record<string, unknown>
    expect(payload.kind).toBe('herdr')
    expect(payload.herdr_mode).toBe('ssh')
    expect(payload.ssh_host).toBe('herdr.example.test')
    expect(payload.ssh_user).toBe('herdr')
    expect(payload.ssh_identity_env).toBe('HERDR_SSH_IDENTITY')
    expect(postPayload).not.toHaveProperty('api_key')
    expect(JSON.stringify(postPayload)).not.toMatch(/BEGIN .*PRIVATE KEY/)
  })

  it('operate pane says local Herdr uses no SSH', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <RemoteOperatePane
            remote={
              {
                id: 'herdr',
                title: 'Herdr',
                herdr_mode: 'local',
                transport: 'local',
                base_url: '',
              } as any
            }
          />
        </ToastProvider>
      </QueryClientProvider>,
    )
    expect(screen.getByText(/Local Herdr \(no SSH\)/i)).toBeInTheDocument()
    expect(screen.getByText(/SSH-shaped/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /List CLIs/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Interrogate CLI/i })).toBeInTheDocument()
  })
})
