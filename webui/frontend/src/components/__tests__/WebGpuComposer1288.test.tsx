/**
 * #1288 — composer integration: the WebGPU provider is offered in the routing
 * picker, and picking it activates ONLY the tab-local client seat. It must
 * never fire the seat-change (`onChange`), cross-kind navigation
 * (`onNavigateAgent`) or provider-reconfigure (`onProviderReconfigure`)
 * callbacks — i.e. the active agent seat and blueprint_id are untouched.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import NavbarRoutingPicker from '../NavbarRoutingPicker'
import type { ComposerProviderOption } from '../../lib/composerPicker'
import {
  clearActiveWebGpuSeat,
  getActiveWebGpuSeat,
  selectWebGpuClientModel,
} from '../../lib/webgpuClientSeat'

const providers: ComposerProviderOption[] = [
  { id: 'cli:codex', label: 'codex', kind: 'cli', defaultOptionId: 'codex' },
  {
    id: 'webgpu',
    label: 'WebGPU (in-browser)',
    kind: 'webgpu',
    defaultOptionId: 'bonsai2-27b',
  },
]

afterEach(() => {
  clearActiveWebGpuSeat()
})

function renderPicker(handlers: {
  onSelectClientProvider: (modelId: string | null) => void
  onChange?: (change: unknown) => void
  onNavigateAgent?: (id: string, kind?: string) => void
  onProviderReconfigure?: (id: string) => void
}) {
  return render(
    <NavbarRoutingPicker
      seatKind="cli"
      aria-label="CLI"
      agents={[{ id: 'codex', label: 'codex', kind: 'cli' as const }]}
      selectedAgent="codex"
      models={['gpt-4']}
      selectedModel="gpt-4"
      onChange={handlers.onChange ?? (() => {})}
      onNavigateAgent={handlers.onNavigateAgent ?? (() => {})}
      onProviderReconfigure={handlers.onProviderReconfigure ?? (() => {})}
      twoStage={{
        providers,
        getProviderOptions: (provider) =>
          provider.kind === 'webgpu'
            ? [{ id: 'bonsai2-27b', label: 'bonsai2-27b', tag: 'model' }]
            : [{ id: 'gpt-4', label: 'gpt-4', tag: 'model' }],
        onSelectClientProvider: handlers.onSelectClientProvider,
      }}
    />,
  )
}

describe('#1288 composer WebGPU provider', () => {
  it('shows the provider and selects it without touching any server seat', async () => {
    const onSelectClient = vi.fn()
    const onChange = vi.fn()
    const onNavigate = vi.fn()
    const onReconfigure = vi.fn()
    renderPicker({
      onSelectClientProvider: onSelectClient,
      onChange,
      onNavigateAgent: onNavigate,
      onProviderReconfigure: onReconfigure,
    })

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    // The provider is genuinely present in the composer's provider stage.
    const row = await screen.findByText('WebGPU (in-browser)')
    fireEvent.click(row)

    await waitFor(() => expect(onSelectClient).toHaveBeenCalledWith('bonsai2-27b'))
    // The invariant: no seat change, no navigation, no reconfigure.
    expect(onChange).not.toHaveBeenCalled()
    expect(onNavigate).not.toHaveBeenCalled()
    expect(onReconfigure).not.toHaveBeenCalled()
  })

  it('a later server-side pick clears the client seat (still no seat jump from the client pick)', async () => {
    const onSelectClient = vi.fn()
    const onChange = vi.fn()
    renderPicker({ onSelectClientProvider: onSelectClient, onChange })

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('WebGPU (in-browser)'))
    await waitFor(() => expect(onSelectClient).toHaveBeenCalledWith('bonsai2-27b'))

    // Now make a normal CLI model pick — emit() clears the client seat.
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('codex'))
    await waitFor(() => expect(onSelectClient).toHaveBeenLastCalledWith(null))
    expect(onChange).toHaveBeenCalledTimes(1)
  })
})

describe('#1288 client seat store', () => {
  it('activates and clears the tab-local seat without a server seat', () => {
    expect(getActiveWebGpuSeat()).toBeNull()
    selectWebGpuClientModel('bonsai2-27b')
    expect(getActiveWebGpuSeat()).toMatchObject({ modelId: 'bonsai2-27b' })
    clearActiveWebGpuSeat()
    expect(getActiveWebGpuSeat()).toBeNull()
  })
})
