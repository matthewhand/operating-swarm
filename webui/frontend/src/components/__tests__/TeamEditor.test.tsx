import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TeamEditor from '../TeamEditor'
import SettingsSheet, { OPEN_SETTINGS_EVENT, type OpenSettingsDetail } from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import { TEAM_EDITS_KEY } from '../../lib/teamEdits'

const catalog = [
  {
    id: 'software_dev',
    object: 'blueprint' as const,
    name: 'Software-dev team',
    description: 'CoS / engineer / skeptic',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    persona_count: 3,
    personas: [
      { name: 'Researcher' },
      { name: 'Writer' },
      { name: 'Reviewer' },
    ],
  },
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    persona_count: 1,
    personas: [{ name: 'Solo' }],
  },
  {
    id: 'junk',
    object: 'blueprint' as const,
    name: 'Junk',
    description: 'Unparsable',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    persona_count: 1,
    personas: [] as Array<{ name: string }>,
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

function EditorThenSettings({ teamId = 'squad' }: { teamId?: string }) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsBlueprintId, setSettingsBlueprintId] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(true)

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<OpenSettingsDetail>).detail
      setSettingsBlueprintId(detail?.blueprintId ?? null)
      setSettingsOpen(true)
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen)
  }, [])

  return (
    <ToastProvider>
      <TeamEditor
        isOpen={editorOpen}
        onClose={() => setEditorOpen(false)}
        teamId={teamId}
        teamName="Squad"
      />
      <SettingsSheet
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        blueprintId={settingsBlueprintId}
      />
    </ToastProvider>
  )
}

describe('TeamEditor (REQ-81)', () => {
  afterEach(() => {
    localStorage.removeItem(TEAM_EDITS_KEY)
    vi.unstubAllGlobals()
  })

  it('shows Edit blueprint and three declared faces for a three-persona blueprint', async () => {
    stubCatalog()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <TeamEditor isOpen teamId="squad" teamName="Squad" onClose={vi.fn()} />
        </ToastProvider>
      </QueryClientProvider>,
    )

    const dialog = await screen.findByRole('dialog', { name: /Edit Squad/i, hidden: true })
    expect(within(dialog).getByTestId('team-editor')).toBeInTheDocument()
    expect(within(dialog).queryByText(/drop agents here/i)).not.toBeInTheDocument()
    const picker = await within(dialog).findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: 'Software-dev team' })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'software_dev' } })
    expect(JSON.parse(localStorage.getItem(TEAM_EDITS_KEY) || '{}').squad.blueprintId).toBe(
      'software_dev',
    )
    const roster = await within(dialog).findByTestId('declared-roster')
    expect(roster).toHaveAttribute('data-persona-count', '3')
    expect(within(dialog).getByText('Researcher')).toBeInTheDocument()
    expect(within(dialog).getByText('Writer')).toBeInTheDocument()
    expect(within(dialog).getByText('Reviewer')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /Edit blueprint/i })).toBeInTheDocument()
  })

  it('one-persona blueprint stays a single named face', async () => {
    stubCatalog()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <TeamEditor isOpen teamId="solo-team" teamName="Solo team" onClose={vi.fn()} />
        </ToastProvider>
      </QueryClientProvider>,
    )
    const picker = await screen.findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: 'Codey' })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'codey' } })
    const roster = await screen.findByTestId('declared-roster')
    expect(roster).toHaveAttribute('data-persona-count', '1')
    // #438 gave the single-face path the same `sr-only` persona list as every
    // other roster size, so the name now appears both there and in the picker —
    // scope the query to the roster rather than matching globally.
    expect(within(roster).getByText('Solo')).toBeInTheDocument()
  })

  it('garbage source is one generic face with no fake names', async () => {
    stubCatalog()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <TeamEditor isOpen teamId="junk-team" teamName="Junk team" onClose={vi.fn()} />
        </ToastProvider>
      </QueryClientProvider>,
    )
    const picker = await screen.findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: 'Junk' })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'junk' } })
    const roster = await screen.findByTestId('declared-roster')
    expect(roster).toHaveAttribute('data-persona-count', '1')
    expect(roster).toHaveAttribute('data-generic', 'true')
    expect(screen.getByTestId('generic-persona-face')).toBeInTheDocument()
    expect(screen.queryByText('FakeInvented')).not.toBeInTheDocument()
  })

  it('Edit blueprint opens Settings → Blueprints with that team blueprint selected', async () => {
    stubCatalog()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <EditorThenSettings teamId="squad" />
      </QueryClientProvider>,
    )

    const picker = await screen.findByLabelText('Blueprint')
    await waitFor(() => {
      expect(within(picker).getByRole('option', { name: 'Software-dev team' })).toBeInTheDocument()
    })
    fireEvent.change(picker, { target: { value: 'software_dev' } })
    fireEvent.click(screen.getByRole('button', { name: /Edit blueprint/i }))

    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    const nav = within(settings).getByRole('navigation', { name: 'Settings sections' })
    expect(within(nav).getByRole('button', { name: 'Blueprints' })).toHaveClass('menu-active')
    const list = within(settings).getByRole('listbox', { name: 'Blueprints' })
    const selected = within(list).getByRole('option', { name: 'Software-dev team' })
    expect(selected).toHaveAttribute('aria-selected', 'true')
    expect(selected).toHaveClass('menu-active')
  })
})
