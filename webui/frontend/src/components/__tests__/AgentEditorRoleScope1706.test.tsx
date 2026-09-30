/**
 * #1706 D.14/D.15 — the agent editor must not offer a role for a seat that
 * cannot carry one.
 *
 * A team roster and a dedicated chat session own no role, so the editor hides
 * the field and says why. The "why" is the point: a missing control with no
 * explanation is an invisible hole in the form, so the reason is rendered text
 * and is programmatically associated (the panel is announced, and the reason
 * carries a stable id a caller can point `aria-describedby` at).
 *
 * The decision itself lives in `lib/agentRoles.roleEditableForSeat`, so these
 * tests exercise the editor's *use* of it, not a re-implementation.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'
import { ROLE_FIELD_UNAVAILABLE_REASON } from '../../lib/agentRoles'

const catalog = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Worker seat',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
]

function stubCatalog() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/blueprints') && url.includes('/source')) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ error: 'blueprint not found' }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: catalog }),
      } as Response
    }),
  )
}

function renderEditor(agentId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={vi.fn()} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

/** The role select is inside the "Role & wiring" tabpanel. */
function roleSelect(): HTMLSelectElement | null {
  return document.querySelector<HTMLSelectElement>('select[name="agent-role"]')
}

async function openRoleTab() {
  const tab = screen.getByRole('tab', { name: /role/i })
  fireEvent.click(tab)
  return tab
}

describe('#1706 D.14/D.15 — role field is withheld from team / chat seats', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    stubCatalog()
  })

  it('offers the role field for an ordinary agent seat', async () => {
    renderEditor('codey')
    await openRoleTab()
    await waitFor(() => expect(roleSelect()).not.toBeNull())
    expect(screen.queryByTestId('role-field-unavailable')).toBeNull()
  })

  it('hides the role field for a TEAM seat', async () => {
    renderEditor('team:alpha')
    await openRoleTab()
    await waitFor(() => expect(screen.getByTestId('role-field-unavailable')).toBeTruthy())
    expect(roleSelect()).toBeNull()
  })

  it('hides the role field for a dedicated CHAT session', async () => {
    // The rail's own chat row id shape (`lib/railChatRows.ts`).
    renderEditor('chat:codey:conv-1')
    await openRoleTab()
    await waitFor(() => expect(screen.getByTestId('role-field-unavailable')).toBeTruthy())
    expect(roleSelect()).toBeNull()
  })

  it('gives a programmatic reason, not just a missing control', async () => {
    renderEditor('chat:codey:conv-1')
    await openRoleTab()
    const panel = await screen.findByTestId('role-field-unavailable')
    // Announced, so a screen-reader user learns why the field is gone rather
    // than landing on a form with an unexplained hole.
    const reason = panel.querySelector('[role="status"]')
    expect(reason).not.toBeNull()
    expect(reason?.textContent).toBe(ROLE_FIELD_UNAVAILABLE_REASON)
    // And the reason has a stable id a caller can point aria-describedby at.
    expect(reason?.id).toBeTruthy()
  })

  it('leaves no role in the local store for a team seat', async () => {
    renderEditor('team:alpha')
    await openRoleTab()
    await screen.findByTestId('role-field-unavailable')
    // Nothing to click into, and nothing written: the editor never advertised
    // a role, so it never persisted one.
    expect(screen.queryByRole('combobox', { name: /role/i })).toBeNull()
    const stored = window.localStorage.getItem('swarm_agent_edits')
    expect(stored === null || !/"role"/.test(stored)).toBe(true)
  })

  it('still offers the role field for a seat whose id merely contains "team"', async () => {
    // Guards the classifier against a sloppy substring test: an ordinary agent
    // called "teamster" is an api seat and keeps its role field.
    renderEditor('teamster')
    await openRoleTab()
    await waitFor(() => expect(roleSelect()).not.toBeNull())
    expect(screen.queryByTestId('role-field-unavailable')).toBeNull()
  })
})
