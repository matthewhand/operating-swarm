/**
 * REQ-82: Agent-rail context menu item contract.
 *
 * Visibility is honest per kind — omit Edit/Duplicate on CLI rather than
 * showing a disabled grey lie. Delete is always last and danger-styled.
 */

import { conversationIdForAgent, peekConversationIdForAgent } from './agentChat'
import { loadAgentChatSessions } from './agentChatSessions'
import {
  NEW_SECTION_PLACEHOLDER,
  NEW_SECTION_TARGET,
  UNASSIGNED_SECTION_ID,
  UNASSIGNED_SECTION_NAME,
  type RailSection,
} from './railSections'
import { teamThreadId } from './teamRosters'

export const RAIL_LONG_PRESS_MS = 500

export type RailMenuKind = 'api' | 'cli' | 'team' | 'remote' | 'blueprint'

export type RailMenuItemId =
  | 'select-agent'
  | 'select-session'
  | 'new-session'
  | 'unpin'
  | 'pin'
  | 'move-to'
  | 'unread'
  | 'edit'
  | 'duplicate'
  | 'copy-id'
  | 'terminate'
  | 'hide'
  | 'unhide'
  | 'notify'
  | 'delete'
  | 'section-create'
  | 'section-rename'
  | 'section-move-up'
  | 'section-move-down'
  | 'section-delete'
  | 'expand'
  | 'collapse'
  | 'copy'
  | 'include_context'
  | 'exclude_context'

export interface RailMenuSubItemSpec {
  id: string
  label: string
  checked?: boolean
}

export interface RailMenuItemSpec {
  id: RailMenuItemId
  label: string
  disabled?: boolean
  reason?: string
  danger?: boolean
  group: number
  children?: RailMenuSubItemSpec[]
}

export interface RailMenuMoveTo {
  sections?: Array<Pick<RailSection, 'id' | 'name'>>
  currentSectionId?: string | null
}

export interface RailMenuOptions {
  kind: RailMenuKind
  pinned: boolean
  hidden: boolean
  unread: boolean
  hasSelectAgent?: boolean
  hasSelectSession?: boolean
  hasNewSession?: boolean
  canCopyId?: boolean
  notifyEnabled?: boolean
  /** True when a CLI subprocess is running for this rail row (REQ-114). */
  cliRunning?: boolean
  /** REQ-209: existing sections for the Move to submenu. */
  moveTo?: RailMenuMoveTo
}

const CLI_NO_PROFILE = 'CLI agents have no swarm-owned profile'
const CLI_NO_DUPLICATE = 'CLI agents cannot be duplicated from the rail'
const NO_CONVERSATION_ID = 'No swarm-side conversation id for this row'
const NOTHING_RUNNING = 'Nothing running'

export function isRailMenuKey(event: { key: string; shiftKey: boolean }): boolean {
  return event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)
}

export function railMenuItems(opts: RailMenuOptions): RailMenuItemSpec[] {
  const items: RailMenuItemSpec[] = []
  if (opts.hasSelectAgent) {
    items.push({ id: 'select-agent', label: 'Select Agent', group: 0 })
  }
  if (opts.hasSelectSession) {
    items.push({ id: 'select-session', label: 'Select session', group: 0 })
  }
  if (opts.hasNewSession) {
    items.push({ id: 'new-session', label: 'New session', group: 0 })
  }
  if (opts.pinned) {
    items.push({ id: 'unpin', label: 'Unpin', group: 1 })
  } else {
    items.push({ id: 'pin', label: 'Pin', group: 1 })
  }
  items.push(moveToMenuItem(opts.moveTo))
  items.push({
    id: 'unread',
    label: opts.unread ? 'Mark as read' : 'Mark as unread',
    group: 2,
  })

  if (opts.kind === 'cli') {
    // Honest omit — no swarm-owned profile / duplicate.
  } else {
    items.push({
      id: 'edit',
      label: 'Edit Profile',
      group: 3,
    })
    items.push({
      id: 'duplicate',
      label: 'Duplicate',
      group: 3,
    })
  }

  const copyEnabled = opts.canCopyId !== false
  items.push({
    id: 'copy-id',
    label: 'Copy conversation ID',
    group: 3,
    disabled: !copyEnabled,
    reason: copyEnabled ? undefined : NO_CONVERSATION_ID,
  })

  if (opts.kind === 'cli') {
    const running = Boolean(opts.cliRunning)
    items.push({
      id: 'terminate',
      label: 'Terminate',
      group: 4,
      disabled: !running,
      reason: running ? undefined : NOTHING_RUNNING,
    })
  }

  if (opts.hidden) {
    items.push({ id: 'unhide', label: 'Unhide', group: 4 })
  } else {
    items.push({ id: 'hide', label: 'Hide from sidebar', group: 4 })
  }

  items.push({
    id: 'notify',
    label: opts.notifyEnabled ? 'Notifications: On' : 'Notifications: Off',
    group: 4,
  })

  items.push({
    id: 'delete',
    label: 'Delete',
    group: 5,
    danger: true,
  })

  return items
}

export function moveToMenuItem(moveTo?: RailMenuMoveTo): RailMenuItemSpec {
  const current = moveTo?.currentSectionId ?? UNASSIGNED_SECTION_ID
  const children: RailMenuSubItemSpec[] = (moveTo?.sections ?? []).map((section) => ({
    id: section.id,
    label: section.name.trim() || NEW_SECTION_PLACEHOLDER,
    checked: section.id === current,
  }))
  children.push({
    id: UNASSIGNED_SECTION_ID,
    label: UNASSIGNED_SECTION_NAME,
    checked: current === UNASSIGNED_SECTION_ID,
  })
  children.push({
    id: NEW_SECTION_TARGET,
    label: NEW_SECTION_PLACEHOLDER,
  })
  return {
    id: 'move-to',
    label: 'Move to',
    group: 1,
    children,
  }
}

export function sectionMenuItems(opts: {
  canMoveUp: boolean
  canMoveDown: boolean
}): RailMenuItemSpec[] {
  return [
    { id: 'section-create', label: 'New section', group: 0 },
    { id: 'section-rename', label: 'Rename', group: 0 },
    {
      id: 'section-move-up',
      label: 'Move up',
      group: 1,
      disabled: !opts.canMoveUp,
      reason: opts.canMoveUp ? undefined : 'Already at the top',
    },
    {
      id: 'section-move-down',
      label: 'Move down',
      group: 1,
      disabled: !opts.canMoveDown,
      reason: opts.canMoveDown ? undefined : 'Already at the bottom',
    },
    { id: 'section-delete', label: 'Delete', group: 2, danger: true },
  ]
}

/**
 * REQ-848 / #173: right-click on the rail background — create a fresh empty section.
 * Drag any agent/pin onto its header to move it in (dropOnSection already
 * accepts rows and pinned ids).
 */
export function paneMenuItems(): RailMenuItemSpec[] {
  return [{ id: 'section-create', label: 'New section', group: 0 }]
}

/** CLI-only reasons exported for tests / disabled titles if a caller shows them. */
export const RAIL_MENU_REASONS = {
  cliNoProfile: CLI_NO_PROFILE,
  cliNoDuplicate: CLI_NO_DUPLICATE,
  noConversationId: NO_CONVERSATION_ID,
  nothingRunning: NOTHING_RUNNING,
} as const

export function peekStoredConversationId(rowId: string): string | null {
  if (!rowId) return null
  const fromChat = peekConversationIdForAgent(rowId)
  if (fromChat) return fromChat
  try {
    const session = loadAgentChatSessions()[rowId]
    if (session?.conversationId) return session.conversationId
  } catch {
    /* jsdom / private mode */
  }
  return null
}

/**
 * Conversation id to copy for a rail row.
 *
 * API / team: always an API-owned id (stored, or minted / team thread id).
 * CLI / remote: existing swarm-side session id only — otherwise null (disable).
 */
export function copyableConversationId(
  kind: RailMenuKind,
  railId: string,
  entityId: string = railId,
): string | null {
  const candidates = [railId, entityId]
  if (kind === 'team' && entityId && !entityId.startsWith('team:')) {
    candidates.push(teamThreadId(entityId))
  }
  for (const id of candidates) {
    const existing = peekStoredConversationId(id)
    if (existing) return existing
  }
  if (kind === 'cli' || kind === 'remote') return null
  if (kind === 'team') return teamThreadId(entityId.replace(/^team:/, ''))
  return conversationIdForAgent(entityId || railId)
}

export function duplicateName(name: string): string {
  const trimmed = name.trim() || 'Agent'
  return `${trimmed} copy`
}
