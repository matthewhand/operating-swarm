/**
 * #1324 — the routing picker names a capability loss and applies the
 * switch only after the operator acknowledges it.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { NavbarRoutingPicker } from '../NavbarRoutingPicker'
import type { SeatCapabilityDirectory } from '../../lib/seatRouting'
import type { ComposerProviderOption } from '../../lib/composerPicker'

const CATALOG: SeatCapabilityDirectory = {
  seat_capabilities: {
    api: {
      attach: { enabled: true, label: 'file attachments' },
      compact: { enabled: true, label: 'thread compact' },
      plugins: { enabled: true, label: 'plugins' },
      routines: { enabled: true, label: 'routines' },
    },
    cli: {
      attach: { enabled: false },
      compact: { enabled: false },
      plugins: { enabled: false },
      routines: { enabled: false },
    },
  },
  cli: {
    grok: { list: 'works', resume: true, export: 'summary' },
    claude: { list: 'paste-only', resume: true, export: 'summary' },
    agy: { list: 'works', resume: true, export: 'summary' },
  },
  labels: { list: 'session list' },
}

describe('#1324 NavbarRoutingPicker capability warning', () => {
  it('holds a CLI list loss until Switch anyway, and Stay does not apply', () => {
    const onChange = vi.fn()
    const onWarn = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        agents={[
          { id: 'grok', label: 'grok', kind: 'cli' },
          { id: 'claude', label: 'claude', kind: 'cli' },
          { id: 'agy', label: 'agy', kind: 'cli' },
        ]}
        selectedAgent="grok"
        models={[]}
        selectedModel=""
        capabilityCatalog={CATALOG}
        onEngineSwitchWarning={onWarn}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(screen.getByTestId('os-model-row-claude'))

    expect(onChange).not.toHaveBeenCalled()
    expect(onWarn).not.toHaveBeenCalled()
    expect(screen.getByTestId('engine-switch-warning')).toHaveTextContent(
      'Switching from grok to claude loses session list.',
    )

    fireEvent.click(screen.getByTestId('engine-switch-stay'))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.queryByTestId('engine-switch-warning')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(screen.getByTestId('os-model-row-claude'))
    expect(screen.getByTestId('engine-switch-stay')).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.queryByTestId('engine-switch-warning')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(screen.getByTestId('os-model-row-claude'))
    fireEvent.click(screen.getByTestId('engine-switch-acknowledge'))

    expect(onWarn).toHaveBeenCalledWith('Switching from grok to claude loses session list.')
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        changed: 'agent',
        agent: 'claude',
        capabilityWarning: 'Switching from grok to claude loses session list.',
      }),
    )
  })

  it('applies an equal CLI immediately', () => {
    const onChange = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        agents={[
          { id: 'grok', label: 'grok', kind: 'cli' },
          { id: 'agy', label: 'agy', kind: 'cli' },
        ]}
        selectedAgent="grok"
        models={[]}
        selectedModel=""
        capabilityCatalog={CATALOG}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(screen.getByTestId('os-model-row-agy'))
    expect(screen.queryByTestId('engine-switch-warning')).not.toBeInTheDocument()
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ changed: 'agent', agent: 'agy' }))
  })

  it('holds an API to CLI navigation until acknowledgment', () => {
    const navigate = vi.fn()
    render(
      <NavbarRoutingPicker
        seatKind="api"
        agents={[{ id: 'orchestration', label: 'API', kind: 'api' }]}
        allAgents={[
          { id: 'orchestration', label: 'API', kind: 'api' },
          { id: 'grok', label: 'grok', kind: 'cli' },
        ]}
        selectedAgent="orchestration"
        models={[]}
        selectedModel=""
        capabilityCatalog={CATALOG}
        onNavigateAgent={navigate}
        onChange={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(screen.getByTestId('os-palette-scope-clear'))
    fireEvent.click(screen.getByTestId('os-model-row-grok'))
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByTestId('engine-switch-warning')).toHaveTextContent('file attachments')
    fireEvent.click(screen.getByTestId('engine-switch-acknowledge'))
    expect(navigate).toHaveBeenCalledWith('grok', 'cli')
  })

  it('holds a two-stage API to CLI pick until acknowledgment', async () => {
    const navigate = vi.fn()
    const providers: ComposerProviderOption[] = [
      { id: 'api', label: 'API gateway', kind: 'api', defaultOptionId: 'orchestration' },
      { id: 'cli:grok', label: 'grok', kind: 'cli' },
    ]
    render(
      <NavbarRoutingPicker
        seatKind="api"
        agents={[{ id: 'orchestration', label: 'API', kind: 'api' }]}
        selectedAgent="orchestration"
        models={[]}
        selectedModel=""
        capabilityCatalog={CATALOG}
        onNavigateAgent={navigate}
        onChange={vi.fn()}
        twoStage={{
          providers,
          getProviderOptions: () => [],
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('grok'))
    fireEvent.click(screen.getAllByTestId('composer-picker-row')[0])
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByTestId('engine-switch-warning')).toHaveTextContent('file attachments')
    fireEvent.click(screen.getByTestId('engine-switch-acknowledge'))
    expect(navigate).toHaveBeenCalledWith('grok', 'cli')
  })
})
