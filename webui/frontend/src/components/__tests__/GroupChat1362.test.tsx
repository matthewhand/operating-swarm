import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TeamComposer from '../TeamComposer'

/**
 * #1362 — the "Create team" affordance is now "Create group chat", and a group
 * chat is a chat you add agents to. These tests pin the user-visible copy, the
 * add/remove member flow, and the live group avatar in the composer.
 */

const AGENTS = [
  { id: 'jeeves', name: 'Jeeves', kind: 'api', source: 'blueprint:jeeves' },
  { id: 'codey', name: 'Codey', kind: 'api', source: 'blueprint:codey' },
  { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok' },
]

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/team-agents')) return json({ object: 'list', data: AGENTS })
      if (url.includes('/v1/team-rosters')) return json({ object: 'list', data: [] })
      if (url.includes('/v1/marketplace')) {
        return json({
          object: 'marketplace_catalog',
          kind: 'teams',
          sources: ['os_team_pack'],
          external: true,
          items: [],
          warnings: [],
        })
      }
      if (url.includes('/v1/mcp-plugins')) {
        return json({ object: 'mcp_plugins', scope: 'user', servers: [] })
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }),
  )
}

function renderComposer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TeamComposer isOpen onClose={() => {}} />
    </QueryClientProvider>,
  )
}

async function addAgentNamed(name: string) {
  const available = await screen.findByRole('list', { name: /available agents list/i })
  const row = within(available).getByText(name).closest('li') as HTMLElement
  fireEvent.click(within(row).getByRole('button', { name: 'Add' }))
}

describe('#1362 group chat affordance', () => {
  beforeEach(() => {
    stubFetch()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('names the create affordance "Create group chat" and the manager "Group chats"', async () => {
    renderComposer()

    expect(await screen.findByRole('heading', { name: 'Group chats' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create group chat' })).toBeInTheDocument()
    expect(screen.getByText('Add agents')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Group chat name' })).toBeInTheDocument()
  })

  it('adds agents to the group chat and removes them again', async () => {
    renderComposer()

    // Add the first agent (Jeeves) from the available list.
    await addAgentNamed('Jeeves')
    let roster = await screen.findByRole('list', { name: 'Roster members' })
    await waitFor(() => expect(within(roster).getAllByTestId('roster-member')).toHaveLength(1))
    expect(screen.getByTestId('os-group-avatar')).toHaveAttribute('data-member-count', '1')

    // Add a second agent — the group avatar grows with the membership.
    await addAgentNamed('Codey')
    roster = screen.getByRole('list', { name: 'Roster members' })
    await waitFor(() => expect(within(roster).getAllByTestId('roster-member')).toHaveLength(2))
    expect(screen.getByTestId('os-group-avatar')).toHaveAttribute('data-member-count', '2')
    expect(screen.getAllByTestId('os-group-avatar-face')).toHaveLength(2)

    // Remove one member — the avatar shrinks back to a single face.
    fireEvent.click(within(roster).getAllByRole('button', { name: 'Remove' })[0])
    await waitFor(() =>
      expect(within(screen.getByRole('list', { name: 'Roster members' })).getAllByTestId('roster-member')).toHaveLength(1),
    )
    expect(screen.getByTestId('os-group-avatar')).toHaveAttribute('data-member-count', '1')
  })
})
