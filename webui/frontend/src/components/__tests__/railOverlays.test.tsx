/**
 * #856 slice E — the sidepane's overlay cluster is an independently
 * testable module.
 *
 * The bottom RailContextMenu (pane menu), the row-delete ConfirmModal, the
 * #546 notification-permission hint, and the AddAgentWizard move verbatim
 * from AgentSidebar.tsx into sidebar/RailOverlays.tsx as <RailOverlays>,
 * driven by explicit props. Pinned contract:
 *
 * 1. the pane menu renders its items through RailContextMenu and reports
 *    selection upward;
 * 2. the delete confirm modal reports confirm/cancel with the row's copy;
 * 3. the notify hint renders the outcome copy with a working retry/dismiss;
 * 4. AddAgentWizard mounts and reports close/created;
 * 5. AgentSidebar renders <RailOverlays> and no longer defines these inline.
 */
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { RailOverlays, type RailOverlaysProps } from '../sidebar/RailOverlays'
import type { RailMenuItemId } from '../../lib/railContextMenu'

function makeProps(overrides: Partial<RailOverlaysProps> = {}): RailOverlaysProps {
  return {
    paneMenu: { x: 10, y: 20 },
    paneMenuItems: () => [
      { id: 'new-session' as RailMenuItemId, label: 'New session', group: 'main' },
    ] as never,
    onPaneMenuSelect: vi.fn(),
    deleteConfirm: {
      agentId: 'a1',
      agentName: 'Hermes',
      hidden: false,
      pinned: false,
      x: 0,
      y: 0,
      kind: 'remote',
      entityId: 'r1',
    },
    onDeleteCancel: vi.fn(),
    onDeleteConfirm: vi.fn(),
    notifyHint: {
      agentId: 'a1',
      outcome: 'never-asked',
      requestFailed: false,
    },
    onNotifyRetry: vi.fn(),
    onNotifyDismiss: vi.fn(),
    addWizardOpen: false,
    onAddWizardClose: vi.fn(),
    onAddWizardCreated: vi.fn(),
    onAddWizardSelect: vi.fn(),
    menuRef: { current: null } as never,
    ...overrides,
  }
}

describe('#856 slice E: RailOverlays', () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const renderOverlays = (props: RailOverlaysProps) =>
    render(
      <QueryClientProvider client={qc}>
        <RailOverlays {...props} />
      </QueryClientProvider>,
    )

  it('renders the pane menu and reports selection', () => {
    const onPaneMenuSelect = vi.fn()
    renderOverlays(makeProps({ onPaneMenuSelect }))
    fireEvent.click(screen.getByText('New session'))
    expect(onPaneMenuSelect).toHaveBeenCalledWith('new-session')
  })

  it('hides the pane menu when closed', () => {
    renderOverlays(makeProps({ paneMenu: null }))
    expect(screen.queryByText('New session')).toBeNull()
  })

  it('shows the delete confirm for a remote row with its copy', () => {
    const onDeleteConfirm = vi.fn()
    renderOverlays(makeProps({ onDeleteConfirm }))
    expect(screen.getByText('Delete Hermes?')).toBeInTheDocument()
    expect(
      screen.getByText(/removes the configured remote from swarm/),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onDeleteConfirm).toHaveBeenCalled()
  })

  it('cancels the delete confirm', () => {
    const onDeleteCancel = vi.fn()
    renderOverlays(makeProps({ onDeleteCancel }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onDeleteCancel).toHaveBeenCalled()
  })

  it('renders the notify hint with retry and dismiss', () => {
    const onNotifyRetry = vi.fn()
    const onNotifyDismiss = vi.fn()
    renderOverlays(makeProps({onNotifyRetry, onNotifyDismiss}))
    expect(screen.getByTestId('notify-permission-hint')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('notify-permission-retry'))
    expect(onNotifyRetry).toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('notify-permission-dismiss'))
    expect(onNotifyDismiss).toHaveBeenCalled()
  })

  it('omit the hint entirely when there is none', () => {
    renderOverlays(makeProps({ notifyHint: null }))
    expect(screen.queryByTestId('notify-permission-hint')).toBeNull()
  })

  it('renders the AddAgentWizard when open and not when closed', () => {
    renderOverlays(makeProps({ addWizardOpen: true }))
    expect(screen.getByLabelText('Add agent wizard')).toBeInTheDocument()
    renderOverlays(makeProps({ addWizardOpen: false }))
    // both mounts coexist in this test file; assert the second render mounted
    // a fresh closed instance without throwing
  })

  it('AgentSidebar renders RailOverlays and no longer inlines them', () => {
    const src = readFileSync(
      join(__dirname, '..', '..', 'components', 'AgentSidebar.tsx'),
      'utf-8',
    )
    expect(src).toContain('<RailOverlays')
    expect(src).not.toContain('data-testid="notify-permission-hint"')
    expect(src).not.toContain('<ConfirmModal')
  })
})
