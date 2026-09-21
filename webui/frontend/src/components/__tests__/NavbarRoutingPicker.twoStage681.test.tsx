/**
 * #681 — the routing picker gains an opt-in two-stage workflow.
 *
 * With `twoStage` present the pill opens the ComposerPickerDialog instead of
 * the flat palette: stage 1 lists every provider from the live payloads, the
 * API gateway pick descends to its options (Use default first), and picking
 * resolves through the same pickAgent path the flat palette uses — so all
 * existing change semantics (persist, URL, cross-kind navigation) are reused.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import NavbarRoutingPicker, { type RoutingPathChange } from '../NavbarRoutingPicker'
import type { ComposerProviderOption } from '../../lib/composerPicker'

const providers: ComposerProviderOption[] = [
  { id: 'api', label: 'API gateway', kind: 'api', defaultOptionId: 'orchestration' },
  { id: 'cli:codex', label: 'codex', kind: 'cli' },
]

function renderPicker(onChange: (c: RoutingPathChange) => void = () => {}) {
  return render(
    <NavbarRoutingPicker
      seatKind="api"
      aria-label="API"
      agents={[{ id: 'orchestration', label: 'Orchestration', kind: 'api' as const }]}
      selectedAgent="orchestration"
      models={[]}
      selectedModel=""
      onChange={onChange}
      twoStage={{
        providers,
        getProviderOptions: () => [
          { id: 'orchestration', label: 'Orchestration' },
          { id: 'claude-work', label: 'Claude Work' },
        ],
      }}
    />,
  )
}

describe('#681 NavbarRoutingPicker two-stage', () => {
  it('the pill opens the composer picker dialog, not the flat palette', async () => {
    renderPicker()
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    await waitFor(() => {
      expect(screen.getByTestId('composer-picker')).toBeTruthy()
    })
    expect(screen.getByText('API gateway')).toBeTruthy()
    expect(screen.queryByTestId('os-model-search-palette')).toBeNull()
  })

  it('accepting the API default resolves through pickAgent (agent change)', async () => {
    const changes: RoutingPathChange[] = []
    renderPicker((c) => changes.push(c))
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('API gateway'))
    fireEvent.click(screen.getAllByTestId('composer-picker-row')[0]) // Use-default row
    await waitFor(() => {
      expect(changes).toHaveLength(1)
    })
    expect(changes[0]).toMatchObject({ changed: 'agent', agent: 'orchestration' })
  })

  it('choosing a specific API option resolves to that profile', async () => {
    const changes: RoutingPathChange[] = []
    renderPicker((c) => changes.push(c))
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('API gateway'))
    fireEvent.click(screen.getByText('Claude Work'))
    await waitFor(() => {
      expect(changes).toHaveLength(1)
    })
    expect(changes[0]).toMatchObject({ changed: 'agent', agent: 'claude-work' })
  })

  it('picking another kind navigates to that seat (cross-kind doctrine)', async () => {
    const navigate = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={[{ id: 'orchestration', label: 'Orchestration', kind: 'api' as const }]}
        selectedAgent="orchestration"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        onNavigateAgent={navigate}
        twoStage={{
          providers,
          getProviderOptions: () => [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    // Descend into the codex provider, then accept its default — the pick
    // (not the descent) resolves onto the cli seat via navigation.
    fireEvent.click(await screen.findByText('codex'))
    fireEvent.click(screen.getAllByTestId('composer-picker-row')[0])
    expect(navigate).toHaveBeenCalledWith('codex', 'cli')
  })
})

describe('#711 CLI resumable sessions in the two-stage picker', () => {
  function renderWithSessions(onResumeSession: (id: string) => void, onTwoStageOpen?: () => void) {
    return render(
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={[{ id: 'orchestration', label: 'Orchestration', kind: 'api' as const }]}
        selectedAgent="orchestration"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        twoStage={{
          providers,
          getProviderOptions: (provider) =>
            provider.id === 'cli:codex'
              ? [
                  { id: 'codex:main', label: 'codex main session', tag: 'session' },
                  { id: 'grok-4', label: 'grok-4', tag: 'model' },
                ]
              : [{ id: 'orchestration', label: 'Orchestration' }],
          onResumeSession,
        }}
        onTwoStageOpen={onTwoStageOpen}
      />,
    )
  }

  it('a session-tagged pick routes to onResumeSession — never pickAgent/pickModel', async () => {
    const changes: RoutingPathChange[] = []
    const onResumeSession = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={[{ id: 'orchestration', label: 'Orchestration', kind: 'api' as const }]}
        selectedAgent="orchestration"
        models={[]}
        selectedModel=""
        onChange={(c) => changes.push(c)}
        twoStage={{
          providers,
          getProviderOptions: (provider) =>
            provider.id === 'cli:codex'
              ? [{ id: 'codex:main', label: 'codex main session', tag: 'session' }]
              : [],
          onResumeSession,
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('codex'))
    fireEvent.click(await screen.findByText('codex main session'))
    await waitFor(() => {
      expect(onResumeSession).toHaveBeenCalledWith('codex:main')
    })
    // A resume is a conversation change, not an agent/model change.
    expect(changes).toHaveLength(0)
  })

  it('onTwoStageOpen fires once per open (deferred fetch doctrine), not on descend', async () => {
    const onTwoStageOpen = vi.fn()
    renderWithSessions(vi.fn(), onTwoStageOpen)
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    await waitFor(() => {
      expect(screen.getByTestId('composer-picker')).toBeTruthy()
    })
    expect(onTwoStageOpen).toHaveBeenCalledTimes(1)
    // Descending into a provider re-renders stage 2 — it must not re-open.
    fireEvent.click(screen.getByText('API gateway'))
    expect(onTwoStageOpen).toHaveBeenCalledTimes(1)
  })

  it('no onResumeSession prop + session pick = inert (honest degradation)', async () => {
    render(
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={[{ id: 'orchestration', label: 'Orchestration', kind: 'api' as const }]}
        selectedAgent="orchestration"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        twoStage={{
          providers,
          getProviderOptions: (provider) =>
            provider.id === 'cli:codex'
              ? [{ id: 'codex:main', label: 'codex main session', tag: 'session' }]
              : [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('codex'))
    // Must not throw; the row pick simply resolves nothing.
    expect(() => fireEvent.click(screen.getByText('codex main session'))).not.toThrow()
  })
})

describe('#804 — cross-kind picks are never inert', () => {
  it('picking API gateway from a CLI seat navigates to the api seat', async () => {
    const navigate = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={[{ id: 'codex', label: 'codex', kind: 'cli' as const }]}
        selectedAgent="codex"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        onNavigateAgent={navigate}
        twoStage={{
          providers: [
            { id: 'api', label: 'API gateway', kind: 'api', description: 'LLM profiles' },
          ],
          getProviderOptions: (provider) =>
            provider.kind === 'api'
              ? [
                  { id: 'claude-work', label: 'Claude Work' },
                  { id: 'orchestration', label: 'orchestration' },
                ]
              : [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('API gateway'))
    // Stage 2: pick a named profile — the pick must navigate, not drop.
    fireEvent.click(screen.getByText('Claude Work'))
    await waitFor(() => {
      expect(navigate).toHaveBeenCalledTimes(1)
    })
    // Stage-2 options under API are profiles: land on the gateway (empty id)
    // with the profile applied as its model.
    expect(navigate).toHaveBeenCalledWith('', 'api', { apiModel: 'claude-work' })
  })

  it('#899: with onProviderReconfigure, an API-profile pick RECONFIGURES instead of jumping seats', async () => {
    const navigate = vi.fn()
    const reconfigure = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={[{ id: 'codex', label: 'codex', kind: 'cli' as const }]}
        selectedAgent="codex"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        onNavigateAgent={navigate}
        onProviderReconfigure={reconfigure}
        twoStage={{
          providers: [
            { id: 'api', label: 'API gateway', kind: 'api', description: 'LLM profiles' },
          ],
          getProviderOptions: (provider) =>
            provider.kind === 'api'
              ? [
                  { id: 'claude-work', label: 'Claude Work' },
                  { id: 'orchestration', label: 'orchestration' },
                ]
              : [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('API gateway'))
    fireEvent.click(screen.getByText('Claude Work'))
    await waitFor(() => {
      expect(reconfigure).toHaveBeenCalledTimes(1)
    })
    expect(reconfigure).toHaveBeenCalledWith('claude-work')
    // The seat keeps its identity — no navigation, no api_agent jump.
    expect(navigate).not.toHaveBeenCalled()
    // The dialog closes after the reconfigure pick.
    await waitFor(() => {
      expect(screen.queryByTestId('composer-picker')).toBeNull()
    })
  })

  it('#899: legacy fallback (no onProviderReconfigure) still navigates for un-migrated callers', async () => {
    const navigate = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={[{ id: 'codex', label: 'codex', kind: 'cli' as const }]}
        selectedAgent="codex"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        onNavigateAgent={navigate}
        twoStage={{
          providers: [
            { id: 'api', label: 'API gateway', kind: 'api', description: 'LLM profiles' },
          ],
          getProviderOptions: (provider) =>
            provider.kind === 'api'
              ? [
                  { id: 'claude-work', label: 'Claude Work' },
                  { id: 'orchestration', label: 'orchestration' },
                ]
              : [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    const dialog = await screen.findByTestId('composer-picker')
    fireEvent.click(within(dialog).getByText('API gateway'))
    fireEvent.click(await within(dialog).findByText('Claude Work'))
    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith('', 'api', { apiModel: 'claude-work' })
    })
  })

  it('accepting the API default (no profiles) still lands on the gateway seat', async () => {
    const navigate = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={[{ id: 'codex', label: 'codex', kind: 'cli' as const }]}
        selectedAgent="codex"
        models={[]}
        selectedModel=""
        onChange={() => {}}
        onNavigateAgent={navigate}
        twoStage={{
          providers: [
            { id: 'api', label: 'API gateway', kind: 'api', description: 'LLM profiles' },
          ],
          getProviderOptions: () => [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('API gateway'))
    // Accept the always-on "Use default" row → navigate to the gateway.
    fireEvent.click(screen.getAllByTestId('composer-picker-row')[0])
    await waitFor(() => {
      expect(navigate).toHaveBeenCalledTimes(1)
    })
    expect(navigate).toHaveBeenCalledWith('api', 'api')
  })
})
