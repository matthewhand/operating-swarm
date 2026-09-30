/**
 * #1356 — a CLI seat lists the selected CLI provider's models only. API /
 * LiteLLM profile ids are a different namespace and must never be offered to a
 * CLI seat (they would fail at `<cli> --model`).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NavbarRoutingPicker from '../NavbarRoutingPicker'

describe('#1356 NavbarRoutingPicker — CLI model namespace', () => {
  it('never lists an API/LiteLLM profile id on a CLI seat', () => {
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={[{ id: 'opencode', label: 'opencode', kind: 'cli' }]}
        selectedAgent="opencode"
        models={['opencode-go/x', 'litellm/orchestration']}
        selectedModel=""
        foreignModelIds={['litellm/orchestration']}
        onChange={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    expect(screen.getByTestId('os-model-row-opencode-go/x')).toBeInTheDocument()
    expect(screen.queryByTestId('os-model-row-litellm/orchestration')).toBeNull()
  })

  it('an API seat is unaffected (its profile ids are its own namespace)', () => {
    render(
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={[{ id: 'codey', label: 'Codey', kind: 'api' }]}
        selectedAgent="codey"
        models={['litellm/orchestration']}
        selectedModel="litellm/orchestration"
        foreignModelIds={['litellm/orchestration']}
        onChange={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    expect(screen.getByTestId('os-model-row-litellm/orchestration')).toBeInTheDocument()
  })

  it('the two-stage CLI provider drops API profile ids from its model rows', () => {
    render(
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={[{ id: 'opencode', label: 'opencode', kind: 'cli' }]}
        selectedAgent="opencode"
        models={['opencode-go/x']}
        selectedModel=""
        foreignModelIds={['litellm/orchestration']}
        twoStage={{
          providers: [{ id: 'cli:opencode', label: 'opencode', kind: 'cli' }],
          getProviderOptions: () => [
            { id: 'opencode-go/x', label: 'opencode-go/x', tag: 'model' as const },
            { id: 'litellm/orchestration', label: 'litellm/orchestration', tag: 'model' as const },
            { id: 'sess-1', label: 'session 1', tag: 'session' as const },
          ],
        }}
        onChange={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    // Stage 1 lists the CLI provider; pick it to descend to stage 2.
    fireEvent.click(screen.getByTestId('composer-picker-row'))
    expect(screen.getAllByText('opencode-go/x').length).toBeGreaterThan(0)
    expect(screen.queryByText('litellm/orchestration')).toBeNull()
    // Session rows are a different axis — they survive the model guard.
    expect(screen.getByText('session 1')).toBeInTheDocument()
  })
})
