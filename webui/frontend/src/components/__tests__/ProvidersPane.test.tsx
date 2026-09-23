// #836 — Providers hub: overview cards derive counts from the same endpoints
// the granular panes read, and each card deep-links into its section.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProvidersPane from '../ProvidersPane'

vi.mock('../../lib/api', () => ({
  fetchLlmProfiles: vi.fn(async () => ({
    object: 'llm_profiles',
    profiles: [{ id: 'p1' }, { id: 'p2' }],
    default_llm_profile: 'p1',
    default_is_auto: false,
    override_per_task: false,
    task_llm_profiles: {},
    auto_picks: {},
    warnings: [],
    routes: {},
    task_classes: [],
  })),
  fetchCliAgents: vi.fn(async () => ({
    clis: ['grok', 'codex'],
    configured: ['grok'],
    discovered: ['grok', 'codex', 'agy'],
    installed: ['grok', 'codex', 'agy'],
  })),
  fetchRemotes: vi.fn(async () => ({
    object: 'list',
    data: [{ id: 'omb' }, { id: 'rakazo' }],
  })),
  fetchCustomBlueprints: vi.fn(async () => ({
    object: 'list',
    data: [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }, { id: 'e' }],
  })),
}))

vi.mock('../SettingsSheet', () => ({
  openSettingsSheet: vi.fn(),
}))

import { openSettingsSheet } from '../SettingsSheet'

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ProvidersPane />
    </QueryClientProvider>,
  )
}

describe('ProvidersPane (#836)', () => {
  it('renders overview cards with derived counts', async () => {
    renderPane()
    // Cards render immediately from cached/loading state; wait for the
    // resolved profile count before asserting the derived numbers.
    await screen.findByText('2 profiles · default: p1')
    expect(screen.getByTestId('providers-card-api')).toBeInTheDocument()
    expect(screen.getByTestId('providers-card-cli')).toHaveTextContent('3 detected')
    expect(screen.getByTestId('providers-card-cli')).toHaveTextContent('1 configured')
    expect(screen.getByTestId('providers-card-remotes')).toHaveTextContent('2 linked')
    expect(screen.getByTestId('providers-card-blueprints')).toHaveTextContent('5 defined')
  })

  it('deep-links each card into its granular settings section', async () => {
    renderPane()
    fireEvent.click(await screen.findByTestId('providers-card-remotes'))
    await waitFor(() => {
      expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'remotes' })
    })
    fireEvent.click(screen.getByTestId('providers-card-api'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'llm-profiles' })
    fireEvent.click(screen.getByTestId('providers-card-cli'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'cli-agents' })
    fireEvent.click(screen.getByTestId('providers-card-blueprints'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'blueprint' })
  })
})
