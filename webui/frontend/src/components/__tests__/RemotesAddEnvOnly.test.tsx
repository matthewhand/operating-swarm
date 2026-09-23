import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'

function renderSheet() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const onClose = vi.fn()
  const view = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet isOpen={true} onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...view, onClose, client }
}

describe('REQ-188A-5: Remotes Add must not post live api_key (env name only)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('provides api_key_env input and no live api_key password input', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes/')) {
          return Promise.resolve({
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
          } as Response)
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response)
      }),
    )

    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))

    await waitFor(() => {
      expect(screen.getByText('No remotes configured yet.')).toBeInTheDocument()
    })

    // #573: "Add remote" opens the kind picker; picking a kind opens the form.
    const addBtn = screen.getByRole('button', { name: /Add remote/i })
    fireEvent.click(addBtn)
    fireEvent.click(screen.getByTestId('remote-kind-omb'))

    // Verify "API key env (optional)" exists
    expect(screen.getByLabelText(/API key env/i)).toBeInTheDocument()

    // Verify live "API key" password field does NOT exist
    expect(screen.queryByLabelText(/^API key$/i)).not.toBeInTheDocument()
  })

  it('posts only kind, url, and api_key_env without live api_key payload', async () => {
    let postPayload: any = null
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        // Only the create call is the subject here. #453 added a target list on
        // pane mount, which POSTs to /v1/remotes/<id>/operate/ once a remote is
        // added — capturing that would clobber the create payload.
        if (url.includes('/v1/remotes/') && !url.includes('/operate/') && init?.method === 'POST') {
          postPayload = JSON.parse(String(init.body))
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: 'omb',
              kind: 'omb',
              base_url: 'http://127.0.0.1:8802',
              api_key_env: 'OMB_KEY_VAR',
            }),
          } as Response
        }
        if (url.includes('/v1/remotes/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              kinds: [{ id: 'omb', label: 'OpenMousBot' }],
              configured: [],
              data: [],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }),
    )

    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Remotes' }))

    await waitFor(() => {
      expect(screen.getByText('No remotes configured yet.')).toBeInTheDocument()
    })

    const addBtn = screen.getByRole('button', { name: /Add remote/i })
    fireEvent.click(addBtn)
    // #573: kind is picked in the popup, not a select
    fireEvent.click(screen.getByTestId('remote-kind-omb'))

    const envInput = screen.getByLabelText(/API key env/i)
    fireEvent.change(envInput, { target: { value: 'OMB_KEY_VAR' } })

    const saveBtn = screen.getByRole('button', { name: 'Save remote' })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(postPayload).not.toBeNull()
    })

    expect(postPayload.kind).toBe('omb')
    expect(postPayload.api_key_env).toBe('OMB_KEY_VAR')
    expect(postPayload).not.toHaveProperty('api_key')
  })
})
