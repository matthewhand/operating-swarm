import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RolesSettingsPane, { normalizeRoleDescriptor } from '../RolesSettingsPane'

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <RolesSettingsPane />
    </QueryClientProvider>,
  )
}

describe('RolesSettingsPane', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('normalizes missing aliases instead of throwing', () => {
    expect(normalizeRoleDescriptor({ name: 'support' })).toEqual({
      name: 'support',
      label: '',
      aliases: [],
      allow_all: false,
      mechanism: 'none',
      mechanism_detail: '',
      css_class: '',
    })
    expect(normalizeRoleDescriptor({ id: 'support' })).toBeNull()
  })

  it('renders a role row when /v1/roles/ omits aliases', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/roles')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [{ name: 'support', label: 'Support' }],
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
    renderPane()
    expect(await screen.findByTestId('role-row-support')).toBeInTheDocument()
    expect(screen.getByTestId('settings-roles-pane')).toBeInTheDocument()
    expect(screen.getByText(/aliases:/i)).toBeInTheDocument()
  })

  it('keeps the pane mounted with an honest error when /v1/roles/ fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/roles')) {
          return {
            ok: false,
            status: 500,
            json: async () => ({ error: 'roles down' }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }),
    )
    renderPane()
    expect(
      await screen.findByText(/roles down|Could not load roles|500/i, undefined, { timeout: 4000 }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('settings-roles-pane')).toBeInTheDocument()
  })

  it('maps roster members correctly to role usage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/roles')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [{ name: 'chief_of_staff', label: 'CoS', mechanism: 'intercept' }],
            }),
          } as Response
        }
        if (url.includes('/v1/team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'squad',
                  name: 'Research Squad',
                  members: [{ id: 'agent-1', name: 'Commander', role: 'chief_of_staff' }],
                },
              ],
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
    renderPane()
    expect(await screen.findByTestId('role-row-chief_of_staff')).toBeInTheDocument()
    expect(screen.getByText(/Commander \(Research Squad\)/i)).toBeInTheDocument()
  })

  it('allows attaching and detaching a role to an agent seat', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/roles')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [{ name: 'gate', label: 'Gate', mechanism: 'intercept' }],
            }),
          } as Response
        }
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [{ id: 'agent-codex', name: 'Code Expert' }],
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

    renderPane()
    expect(await screen.findByTestId('role-row-gate')).toBeInTheDocument()

    // Click "+ Attach to agent"
    const attachBtn = screen.getByTestId('role-attach-btn-gate')
    attachBtn.click()

    // Expect the agent selector to appear
    const select = await screen.findByTestId('role-attach-select-gate')
    expect(select).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'agent-codex' } })

    // Check that 'Code Expert' now appears under Used by
    expect(await screen.findByText('Code Expert')).toBeInTheDocument()

    // Check detach button
    const detachBtn = screen.getByTestId('detach-role-gate-agent-codex')
    expect(detachBtn).toBeInTheDocument()
    fireEvent.click(detachBtn)

    // After detaching, agent is no longer in used by
    await waitFor(() => {
      expect(screen.queryByTestId('detach-role-gate-agent-codex')).not.toBeInTheDocument()
    })
  })
})

