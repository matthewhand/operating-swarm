/**
 * Universal routing picker (REQ-906 / #504) + combined composer trigger
 * (REQ-907 / #629).
 *
 * Every seat kind opens the shared search palette — scoped by default with a
 * removable chip (#504) — and the composer shows ONE combined pill labelled
 * `provider/model(/effort)` (#629) instead of three separate pills.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ComponentProps } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NavbarRoutingPicker } from '../NavbarRoutingPicker'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'

const AGY_MODELS = [
  'gemini-3.8-flash-high',
  'gemini-3.8-flash-medium',
  'claude-sonnet-4-6',
  'default',
]

function renderPicker(
  props: Partial<ComponentProps<typeof NavbarRoutingPicker>> = {},
) {
  const onChange = vi.fn()
  const onNavigateAgent = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <NavbarRoutingPicker
        seatKind="cli"
        agents={[
          { id: 'agy', label: 'agy', kind: 'cli' },
          { id: 'grok', label: 'grok', kind: 'cli' },
        ]}
        selectedAgent="agy"
        models={AGY_MODELS}
        selectedModel="gemini-3.8-flash-medium"
        preferredEffort="medium"
        allAgents={[
          { id: 'agy', label: 'agy', kind: 'cli' },
          { id: 'grok', label: 'grok', kind: 'cli' },
          { id: 'api_agent', label: 'API Agent', kind: 'api' },
          { id: 'omb', label: 'OpenMousBot', kind: 'remote' },
        ]}
        onNavigateAgent={onNavigateAgent}
        onChange={onChange}
        footerAction={{ id: '__manage_cli__', label: 'Manage CLI', onSelect: vi.fn() }}
        {...props}
      />
    </QueryClientProvider>,
  )
  return { onChange, onNavigateAgent, ...view }
}

function openPalette() {
  fireEvent.click(screen.getByTestId('routing-pill-agent'))
  return screen.getByTestId('os-model-search-palette')
}

describe('NavbarRoutingPicker (universal palette, #504 + #629)', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('dir')
  })

  it('#629: renders ONE combined pill labelled provider/model/effort', () => {
    renderPicker()
    expect(screen.getByTestId('routing-pill-agent')).toHaveTextContent(
      'agy/gemini-3.8-flash/medium',
    )
    // The retired per-dimension pills are gone.
    expect(screen.queryByTestId('routing-pill-model')).not.toBeInTheDocument()
    expect(screen.queryByTestId('routing-pill-effort')).not.toBeInTheDocument()
  })

  it('#629: empty segments render as — and never leave dangling dividers', () => {
    renderPicker({ models: [], selectedModel: '', preferredEffort: undefined })
    expect(screen.getByTestId('routing-pill-agent')).toHaveTextContent('agy/—')
  })

  it('#504: every kind opens the palette (CLI included), not a flyout', () => {
    renderPicker()
    openPalette()
    expect(screen.getByTestId('os-model-search-palette')).toBeInTheDocument()
    expect(screen.queryByTestId('routing-flyout')).not.toBeInTheDocument()
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('#504: palette is scoped by default with a visible chip', () => {
    renderPicker()
    openPalette()
    // Agents group + the selection's model group, but not other kinds.
    expect(screen.getByTestId('os-model-row-agy')).toBeInTheDocument()
    expect(screen.getByTestId('os-model-row-grok')).toBeInTheDocument()
    expect(screen.getByTestId('os-model-row-gemini-3.8-flash-medium')).toBeInTheDocument()
    expect(screen.queryByTestId('os-model-row-api_agent')).not.toBeInTheDocument()
    expect(screen.queryByTestId('os-model-row-omb')).not.toBeInTheDocument()
  })

  it('#504: clearing the scope chip reveals all configured options', () => {
    renderPicker()
    openPalette()
    fireEvent.click(screen.getByTestId('os-palette-scope-clear'))
    expect(screen.getByTestId('os-model-row-api_agent')).toBeInTheDocument()
    expect(screen.getByTestId('os-model-row-omb')).toBeInTheDocument()
  })

  it('#504: picking a model emits a model change', () => {
    const { onChange } = renderPicker()
    openPalette()
    fireEvent.click(screen.getByTestId('os-model-row-claude-sonnet-4-6'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        changed: 'model',
        agent: 'agy',
        modelBase: 'claude-sonnet-4-6',
      }),
    )
  })

  it('#504: picking an agent of the same kind rebinds the seat', () => {
    const { onChange, onNavigateAgent } = renderPicker()
    openPalette()
    fireEvent.click(screen.getByTestId('os-model-row-grok'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ changed: 'agent', agent: 'grok' }),
    )
    expect(onNavigateAgent).not.toHaveBeenCalled()
  })

  it('#502: picking an out-of-scope kind navigates instead of rebinding', () => {
    const { onChange, onNavigateAgent } = renderPicker()
    openPalette()
    fireEvent.click(screen.getByTestId('os-palette-scope-clear'))
    fireEvent.click(screen.getByTestId('os-model-row-api_agent'))
    expect(onNavigateAgent).toHaveBeenCalledWith('api_agent', 'api')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('the manage footer action carries the kind-appropriate label', () => {
    const manage = vi.fn()
    renderPicker({
      footerAction: { id: '__manage_cli__', label: 'Manage CLI', onSelect: manage },
    })
    openPalette()
    const btn = screen.getByTestId('os-model-manage-api')
    expect(btn).toHaveTextContent('Manage CLI in Settings')
    fireEvent.click(btn)
    expect(manage).toHaveBeenCalledTimes(1)
  })

  it('surfaces the #494 warning with its Fix-in-Settings action', async () => {
    const listener = vi.fn()
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    try {
      renderPicker({
        modelWarning: 'OpenMousBot list requires auth.',
        modelWarningAction: {
          kind: 'settings',
          section: 'remotes',
          remote: 'omb',
          field: 'api_key_env',
        },
      })
      openPalette()
      const warning = await screen.findByTestId('routing-model-warning')
      expect(warning).toHaveTextContent('OpenMousBot list requires auth.')
      fireEvent.click(screen.getByTestId('routing-model-warning-action'))
      await waitFor(() => expect(listener).toHaveBeenCalledTimes(1))
      expect(listener.mock.calls[0][0].detail).toMatchObject({
        section: 'remotes',
        remoteId: 'omb',
      })
    } finally {
      window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
    }
  })

  it('REQ-870: shows Loading while the CLI model probe is in flight, rows stay navigable', () => {
    renderPicker({ loading: true })
    openPalette()
    expect(screen.getByTestId('routing-model-loading')).toBeInTheDocument()
    // REQ-870 parity: the agent rows remain pickable while models probe.
    expect(screen.getByTestId('os-model-row-agy')).toBeInTheDocument()
  })
})
