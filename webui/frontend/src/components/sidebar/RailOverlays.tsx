/**
 * #856 slice E — the sidepane's overlay cluster, moved verbatim from
 * AgentSidebar.tsx behind explicit props: the pane-level RailContextMenu,
 * the row-delete ConfirmModal, the #546 notification-permission hint, and
 * the AddAgentWizard. AgentSidebar owns all state; this module renders it.
 */
import type { RefObject } from 'react'
import RailContextMenu from '../RailContextMenu'
import { ConfirmModal } from '../DaisyUI'
import AddAgentWizard, { type AgentKind } from '../AddAgentWizard'
import { NOTIFY_HINT_COPY } from '../../lib/agentNotifications'
import type { RailMenuItemId } from '../../lib/railContextMenu'
import type { ContextMenuState } from '../../features/sidebar/rows'
import type { RailMenuItemSpec } from '../../lib/railContextMenu'

/** Context menu payload for the pane-level (right-click on empty space) menu. */
export interface PaneMenuState {
  x: number
  y: number
}

/** #546: which permission outcome to explain, and for which seat. */
export interface NotifyOutcomeHint {
  agentId: string
  outcome: Exclude<
    import('../../lib/agentNotifications').NotifyEnableOutcome,
    'granted'
  >
  requestFailed: boolean
}

/** Delete-confirmation payload — the row context-menu state, reused. */
export type RailDeleteConfirmState = ContextMenuState

export interface RailOverlaysProps {
  paneMenu: PaneMenuState | null
  paneMenuItems: () => RailMenuItemSpec[]
  onPaneMenuSelect: (id: RailMenuItemId) => void
  deleteConfirm: RailDeleteConfirmState | null
  onDeleteCancel: () => void
  onDeleteConfirm: () => void
  notifyHint: NotifyOutcomeHint | null
  onNotifyRetry: () => void
  onNotifyDismiss: () => void
  addWizardOpen: boolean
  onAddWizardClose: () => void
  onAddWizardCreated: (created: { id: string; name: string; kind: AgentKind }) => void
  onAddWizardSelect: (agentId: string) => void
  menuRef: RefObject<HTMLUListElement>
}

export function RailOverlays({
  paneMenu,
  paneMenuItems,
  onPaneMenuSelect,
  deleteConfirm,
  onDeleteCancel,
  onDeleteConfirm,
  notifyHint,
  onNotifyRetry,
  onNotifyDismiss,
  addWizardOpen,
  onAddWizardClose,
  onAddWizardCreated,
  onAddWizardSelect,
  menuRef,
}: RailOverlaysProps) {
  return (
    <>
      {paneMenu && (
        <RailContextMenu
          agentName="Side pane"
          x={paneMenu.x}
          y={paneMenu.y}
          items={paneMenuItems()}
          menuRef={menuRef}
          onSelect={onPaneMenuSelect}
        />
      )}
      {deleteConfirm && (
        <ConfirmModal
          isOpen
          onClose={onDeleteCancel}
          onConfirm={onDeleteConfirm}
          title={`Delete ${deleteConfirm.agentName}?`}
          confirmText="Delete"
          cancelText="Cancel"
          confirmVariant="error"
        >
          <p>
            {deleteConfirm.kind === 'cli'
              ? 'This removes the CLI agent from the rail. It does not uninstall the CLI on this machine.'
              : deleteConfirm.kind === 'remote'
                ? 'This removes the configured remote from swarm. It does not change the far-side host.'
                : 'This deletes the local entity and removes it from the rail. This cannot be undone from Hidden Agents.'}
          </p>
        </ConfirmModal>
      )}
      {notifyHint ? (
        <div
          role="status"
          data-testid="notify-permission-hint"
          data-outcome={notifyHint.outcome}
          className="fixed bottom-4 right-4 z-50 max-w-xs rounded-lg border border-base-300 bg-neutral px-3 py-2 text-sm shadow-xl"
        >
          <span className="block">
            {notifyHint.requestFailed
              ? 'The browser blocked the permission request before it could show a prompt. Try again.'
              : NOTIFY_HINT_COPY[notifyHint.outcome]}
          </span>
          <span className="mt-1 flex items-center gap-2">
            {notifyHint.outcome === 'never-asked' ? (
              <button
                type="button"
                className="link link-primary text-xs"
                data-testid="notify-permission-retry"
                onClick={onNotifyRetry}
              >
                Try again
              </button>
            ) : null}
            <button
              type="button"
              className="link text-xs opacity-70"
              data-testid="notify-permission-dismiss"
              onClick={onNotifyDismiss}
            >
              Dismiss
            </button>
          </span>
        </div>
      ) : null}
      <AddAgentWizard
        isOpen={addWizardOpen}
        onClose={onAddWizardClose}
        onCreated={onAddWizardCreated}
        onSelectAgent={onAddWizardSelect}
      />
    </>
  )
}

export default RailOverlays
