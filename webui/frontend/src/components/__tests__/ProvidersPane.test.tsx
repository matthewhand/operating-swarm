// #836 — Providers hub: overview cards derive counts from the same endpoints
// the granular panes read, and each card deep-links into its section.
// #1745 — System1 gets a card of its own, and a gate is not an API chat profile.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProvidersPane from '../ProvidersPane'

vi.mock('../../lib/api', () => ({
  fetchLlmProfiles: vi.fn(async () => ({
    object: 'llm_profiles',
    profiles: [
      { id: 'p1' },
      { id: 'p2' },
      {
        id: 'system1-filter',
        source: 'config',
        owned_by: 'system1',
        model_type: 'categorizer',
      },
    ],
    default_llm_profile: 'p1',
    default_is_auto: false,
    override_per_task: false,
    task_llm_profiles: {},
    auto_picks: {},
    warnings: [],
    routes: {},
    task_classes: [],
    model_types: ['chat', 'categorizer'],
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

vi.mock('../settings/kernel', () => ({
  openSettingsSheet: vi.fn(),
}))

import { openSettingsSheet } from '../settings/kernel'

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
    await screen.findByText('2 chat profiles · default: p1')
    expect(screen.getByTestId('providers-card-api')).toBeInTheDocument()
    expect(screen.getByTestId('providers-card-cli')).toHaveTextContent('3 detected')
    expect(screen.getByTestId('providers-card-cli')).toHaveTextContent('1 configured')
    expect(screen.getByTestId('providers-card-remotes')).toHaveTextContent('2 linked')
    expect(screen.getByTestId('providers-card-blueprints')).toHaveTextContent('5 defined')
  })

  it('gives System1 a card of its own and keeps gates out of the API count (#1745)', async () => {
    renderPane()
    // Three profiles exist, but the third is a gate — the API card counts 2.
    await screen.findByText('2 chat profiles · default: p1')
    const system1 = screen.getByTestId('providers-card-system1')
    expect(system1).toHaveTextContent('System1 categorizers')
    expect(system1).toHaveTextContent('1 gate model')
    expect(system1).toHaveTextContent('filter-in / filter-out seats')
    expect(screen.getByTestId('providers-card-api')).not.toHaveTextContent('system1-filter')
  })

  it('deep-links each card into its granular settings section', async () => {
    renderPane()
    fireEvent.click(await screen.findByTestId('providers-card-remotes'))
    await waitFor(() => {
      expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'remotes' })
    })
    fireEvent.click(screen.getByTestId('providers-card-api'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'llm-profiles' })
    // System1 lives in the models pane — one destination, two typed sub-lists.
    fireEvent.click(screen.getByTestId('providers-card-system1'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'llm-profiles' })
    fireEvent.click(screen.getByTestId('providers-card-cli'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'cli-agents' })
    fireEvent.click(screen.getByTestId('providers-card-blueprints'))
    expect(openSettingsSheet).toHaveBeenCalledWith({ section: 'blueprint' })
  })
})
