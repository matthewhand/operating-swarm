import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MailboxAclEditor from '../MailboxAclEditor'
import type { MailboxAcl } from '../../lib/mailboxAcl'

function aclPayload(overrides: Partial<MailboxAcl> = {}): MailboxAcl {
  return {
    object: 'mailbox_acl',
    scope: 'agent',
    id: 'support',
    role: 'support',
    source: 'default',
    inherited: true,
    mode: 'whitelist',
    allow_all: true,
    entries: [],
    entry_kinds: [
      { kind: 'agent', description: 'A catalogued rail or roster agent id.' },
      { kind: 'team', description: 'A team roster id.' },
      { kind: 'role', description: 'A canonical role.' },
    ],
    ...overrides,
  }
}

function stubAcl(initial = aclPayload()) {
  let current = initial
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method || 'GET').toUpperCase()
    if (!url.includes('/v1/mailbox-acl/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    }
    if (method === 'PUT') {
      const body = JSON.parse(String(init?.body || '{}'))
      current = {
        ...current,
        mode: body.mode,
        entries: body.entries || [],
        inherited: false,
        source: url.includes('/roles/') ? 'role' : 'agent',
        allow_all: body.mode === 'whitelist' && !(body.entries || []).length,
      }
    }
    if (method === 'DELETE') {
      current = aclPayload({
        id: current.id,
        role: current.role,
        scope: url.includes('/roles/') ? 'role' : 'agent',
      })
    }
    return {
      ok: true,
      status: 200,
      json: async () => current,
    } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('MailboxAclEditor (REQ-162)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows Support allow-all and documents entry kinds', async () => {
    stubAcl()
    render(<MailboxAclEditor agentId="support" role="support" />)
    expect(await screen.findByTestId('mailbox-acl-editor')).toBeInTheDocument()
    // #545: the heading and the toggle no longer use whitelist/blacklist jargon.
    expect(screen.getByText(/Who this seat may message/i)).toBeInTheDocument()
    expect(screen.queryByText(/Mailbox visibility/i)).not.toBeInTheDocument()
    expect(screen.getByText('Filter')).toBeInTheDocument()
    // Scope the two options to the toggle's own row: `Permitted` also appears in
    // the allow-all explanation below it.
    const filterRow = screen
      .getByLabelText('Filter the entries below: permitted or denied')
      .closest('label')
    expect(filterRow).toHaveTextContent('Permitted')
    expect(filterRow).toHaveTextContent('Denied')
    expect(screen.queryByText('Whitelist')).not.toBeInTheDocument()
    expect(screen.queryByText('Blacklist')).not.toBeInTheDocument()
    expect(screen.queryByText('White')).not.toBeInTheDocument()
    expect(screen.queryByText('Black')).not.toBeInTheDocument()
    expect(screen.getByTestId('mailbox-acl-allow-all')).toHaveTextContent(/open to everyone/i)
    expect(screen.getByText('agent', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('team', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('role', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByLabelText('ACL scope')).toBeInTheDocument()
    expect(
      screen.getByLabelText('Filter the entries below: permitted or denied'),
    ).toBeInTheDocument()
  })

  it('toggles white↔black and adds/removes an agent entry', async () => {
    const fetchMock = stubAcl()
    render(<MailboxAclEditor agentId="pat" role="default" />)
    await screen.findByTestId('mailbox-acl-editor')

    fireEvent.click(screen.getByLabelText('Filter the entries below: permitted or denied'))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/v1/mailbox-acl/agents/pat/'),
        expect.objectContaining({ method: 'PUT' }),
      )
    })

    fireEvent.change(screen.getByLabelText('Agent id'), { target: { value: 'cos' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => {
      expect(screen.getByText('cos')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Remove agent cos' }))
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Remove agent cos' })).not.toBeInTheDocument()
    })
  })

  it('can target a team or role entry', async () => {
    stubAcl(aclPayload({ id: 'pat', role: 'default', mode: 'blacklist', allow_all: false }))
    render(<MailboxAclEditor agentId="pat" role="default" />)
    await screen.findByTestId('mailbox-acl-editor')

    fireEvent.change(screen.getByLabelText('Entry kind'), { target: { value: 'team' } })
    fireEvent.change(screen.getByLabelText('Team id'), { target: { value: 'office' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => {
      expect(screen.getByText('office')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Entry kind'), { target: { value: 'role' } })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'support' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Remove role support' })).toBeInTheDocument()
    })
  })
})
