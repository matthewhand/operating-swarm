/**
 * REQ-82: Agent-rail context menu item contract.
 *
 * Visibility is honest per kind — omit Edit/Duplicate on CLI rather than
 * showing a disabled grey lie. Delete is always last and danger-styled.
 *
 * #1727: that omit rule is the strictest form of honesty and it stays the
 * default, but it only covered `kind === 'cli'`. A kind the caller did not
 * think about fell through to the `else` branch and got an ENABLED item whose
 * handler either did nothing or, worse, did the wrong thing —
 * `resolveMenuKind` documents herdr as "no Edit/Duplicate (no swarm-owned
 * profile)" while this file only ever checked for cli. So every item now
 * answers ONE question — {@link railMenuCapability} — and a kind that cannot
 * perform the action gets the item greyed with a reason, reusing the same
 * `disabled`/`reason` plumbing #1714 gave the Move-to submenu. No second
 * menu mechanism is introduced.
 */

import { BUBBLE_THEME_LABELS, BUBBLE_THEMES } from './bubbleTheme'
import { conversationIdForAgent, peekConversationIdForAgent } from './agentChat'
import { loadAgentChatSessions } from './agentChatSessions'
import { parseRailChatRowId } from './railChatRows'
import {
  NEW_SECTION_PLACEHOLDER,
  NEW_SECTION_TARGET,
  UNASSIGNED_SECTION_ID,
  UNASSIGNED_SECTION_NAME,
  type RailMoveToDestination,
  type RailSection,
} from './railSections'
import { teamThreadId } from './teamRosters'

export const RAIL_LONG_PRESS_MS = 500

export type RailMenuKind = 'api' | 'cli' | 'team' | 'remote' | 'blueprint' | 'herdr' | 'chat'

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
  | 'section-talk-lock'
  | 'section-move-up'
  | 'section-move-down'
  | 'section-delete'
  | 'expand'
  | 'collapse'
  | 'copy'
  | 'include_context'
  | 'exclude_context'
  | 'bubble-theme'

export interface RailMenuSubItemSpec {
  id: string
  label: string
  checked?: boolean
  /** #1714: a listed-but-not-choosable row (an auto section, or Unassigned for
   *  a row an auto group re-files). `reason` is its title, so the grey row
   *  explains itself instead of reading as a broken click. */
  disabled?: boolean
  reason?: string
  /** #497: draw a rule above this child so it does not read as one of the
   *  destinations it follows (e.g. `New section` after the section list). */
  dividerBefore?: boolean
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
  /**
   * #1714: the rail's own rendered blocks, so the list cannot be a subset of
   * what the operator can see. Takes precedence over `sections` when present.
   */
  destinations?: RailMoveToDestination[]
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
  /** #724: the agent's current bubble-theme override (for the check mark). */
  bubbleTheme?: string
  /** #724: the chat-wide default, so 'Default (x)' can be labelled honestly. */
  bubbleThemeDefault?: string
}

const CLI_NO_PROFILE = 'CLI agents have no swarm-owned profile'
const CLI_NO_DUPLICATE = 'CLI agents cannot be duplicated from the rail'
const NO_CONVERSATION_ID = 'No swarm-side conversation id for this row'
const NOTHING_RUNNING = 'Nothing running'
const HERDR_NO_PROFILE = 'Herdr seats run on the remote harness — there is no swarm-owned profile to edit.'
const HERDR_NO_DUPLICATE =
  'Duplicating a herdr seat would create a different kind of agent — copy the remote connection in Settings instead.'
const CHAT_NO_PROFILE = 'This row is a chat, not a seat — open the agent row to edit its profile.'
const CHAT_NO_DUPLICATE = 'Duplicate the agent row to copy its seat; a chat has no seat of its own.'
const NO_SWARM_SESSIONS =
  'This agent type has no swarm-side sessions, so a new session cannot be started from the rail.'

/**
 * #1727 — the ONE capability matrix. `true`/`false` is what the handler
 * actually does, derived by reading the dispatch, not by reading the label.
 *
 *  - **api / blueprint** — swarm-owned seat with a Django session store, a
 *    profile and a duplicate path. Everything works.
 *  - **cli** — a host subprocess. `seatHasSessions` says it has sessions, and
 *    the CLI session picker/hop backs it. No profile, no duplicate (the
 *    existing honest OMIT, unchanged).
 *  - **team / remote** — their own conversations live in the provider, not in
 *    the swarm session store, so `startNewAgentSession` cannot address them.
 *    Both keep a profile surface (team editor / remote settings) and a
 *    duplicate path.
 *  - **herdr** — the #543 comment already says "no Edit/Duplicate (no
 *    swarm-owned profile)", but nothing enforced it. `duplicateMenuRow` fell
 *    through to the API branch and minted a *custom API blueprint* from a seat
 *    that has no blueprint: a click that silently produced the wrong agent.
 *  - **chat** (#1726) — a session row, not a seat. It has no profile and
 *    nothing to duplicate, and its section comes from the seat it belongs to.
 */
export interface RailMenuCapability {
  /** False ⇒ the item may be listed, but never clicked. */
  supported: boolean
  /** The accessible reason shown as the item's title. */
  reason?: string
  /**
   * True when the honest answer is to leave the item OUT of the menu entirely
   * rather than grey it. CLI keeps this for Edit/Duplicate (REQ-82) and the
   * session items keep it for kinds that never had them.
   */
  omit?: boolean
}

const CAPABILITIES: Record<RailMenuKind, Partial<Record<RailMenuItemId, RailMenuCapability>>> = {
  api: {},
  blueprint: {},
  team: {
    'select-session': { supported: false, reason: NO_SWARM_SESSIONS },
    'new-session': { supported: false, reason: NO_SWARM_SESSIONS },
  },
  remote: {
    'select-session': { supported: false, reason: NO_SWARM_SESSIONS },
    'new-session': { supported: false, reason: NO_SWARM_SESSIONS },
  },
  cli: {
    edit: { supported: false, omit: true, reason: CLI_NO_PROFILE },
    duplicate: { supported: false, omit: true, reason: CLI_NO_DUPLICATE },
  },
  herdr: {
    'select-session': { supported: false, reason: NO_SWARM_SESSIONS },
    'new-session': { supported: false, reason: NO_SWARM_SESSIONS },
    edit: { supported: false, reason: HERDR_NO_PROFILE },
    duplicate: { supported: false, reason: HERDR_NO_DUPLICATE },
  },
  chat: {
    edit: { supported: false, reason: CHAT_NO_PROFILE },
    duplicate: { supported: false, reason: CHAT_NO_DUPLICATE },
  },
}

/** #1727: can `kind` perform `itemId`? The single answer, for every surface. */
export function railMenuCapability(kind: RailMenuKind, itemId: RailMenuItemId): RailMenuCapability {
  return CAPABILITIES[kind]?.[itemId] ?? { supported: true }
}

export function isRailMenuKey(event: { key: string; shiftKey: boolean }): boolean {
  return event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)
}

/**
 * #1727 — resolve one item against the matrix. Returns `null` only for the
 * one pre-existing honest OMIT (cli's Edit/Duplicate, REQ-82, which has its
 * own locked test). Everything else the caller asks for is RENDERED: a
 * requested item the kind cannot perform comes back greyed with its reason,
 * because a caller that asked for it wants the answer, and silence is the
 * bug this issue is about.
 */
function capabilityItem(
  kind: RailMenuKind,
  id: RailMenuItemId,
  label: string,
  group: number,
): RailMenuItemSpec | null {
  const cap = railMenuCapability(kind, id)
  if (cap.omit && !cap.supported) return null
  return {
    id,
    label,
    group,
    disabled: cap.supported ? undefined : true,
    reason: cap.supported ? undefined : cap.reason,
  }
}

export function railMenuItems(opts: RailMenuOptions): RailMenuItemSpec[] {
  const items: RailMenuItemSpec[] = []
  if (opts.hasSelectAgent) {
    items.push({ id: 'select-agent', label: 'Select Agent', group: 0 })
  }
  if (opts.hasSelectSession) {
    const spec = capabilityItem(opts.kind, 'select-session', 'Select session', 0)
    if (spec) items.push(spec)
  }
  if (opts.hasNewSession) {
    const spec = capabilityItem(opts.kind, 'new-session', 'New session', 0)
    if (spec) items.push(spec)
  }
  if (opts.pinned) {
    items.push({ id: 'unpin', label: 'Unpin', group: 1 })
  } else {
    items.push({ id: 'pin', label: 'Pin', group: 1 })
  }
  items.push(moveToMenuItem(opts.moveTo))
  items.push(bubbleThemeMenuItem(opts.bubbleTheme, opts.bubbleThemeDefault))
  items.push({
    id: 'unread',
    label: opts.unread ? 'Mark as read' : 'Mark as unread',
    group: 2,
  })

  // #1727: the omit/grey decision is the matrix's, not a `kind === 'cli'`
  // literal repeated here. cli still omits (REQ-82, unchanged); herdr and a
  // chat row are LISTED and greyed, so the operator learns the action exists
  // for other kinds instead of finding a click that silently did nothing.
  for (const id of ['edit', 'duplicate'] as const) {
    const spec = capabilityItem(opts.kind, id, id === 'edit' ? 'Edit Profile' : 'Duplicate', 3)
    if (spec) items.push(spec)
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
  const children: RailMenuSubItemSpec[] = moveTo?.destinations
    ? moveTo.destinations.map((destination) => ({
        id: destination.id,
        label: destination.name.trim() || NEW_SECTION_PLACEHOLDER,
        checked: destination.checked,
        disabled: !destination.selectable,
        reason: destination.reason,
      }))
    : (moveTo?.sections ?? []).map((section) => ({
        id: section.id,
        label: section.name.trim() || NEW_SECTION_PLACEHOLDER,
        checked: section.id === current,
      }))
  if (!moveTo?.destinations?.some((destination) => destination.id === UNASSIGNED_SECTION_ID)) {
    children.push({
      id: UNASSIGNED_SECTION_ID,
      label: UNASSIGNED_SECTION_NAME,
      checked: current === UNASSIGNED_SECTION_ID,
    })
  }
  children.push({
    id: NEW_SECTION_TARGET,
    label: NEW_SECTION_PLACEHOLDER,
    // #497: 'New section' is an action, not a destination — separate it.
    dividerBefore: true,
  })
  return {
    id: 'move-to',
    label: 'Move to',
    group: 1,
    children,
  }
}

/**
 * #724: per-agent bubble-theme picker as a rail submenu. 'Default (x)' is the
 * honest no-override entry; the rest are the registered themes from
 * BUBBLE_THEMES. Dispatch happens in AgentSidebar via setAgentBubbleTheme.
 */
export function bubbleThemeMenuItem(
  current?: string,
  defaultTheme?: string,
): RailMenuItemSpec {
  const children: RailMenuSubItemSpec[] = [
    {
      id: '__default__',
      label: `Default${defaultTheme ? ` (${defaultTheme})` : ''}`,
      checked: !current,
    },
  ]
  // Registry order (bubbleThemes.ts) — no hardcoded theme list here.
  for (const theme of BUBBLE_THEMES) {
    children.push({
      id: theme,
      label: BUBBLE_THEME_LABELS[theme] ?? theme,
      checked: current === theme,
    })
  }
  return {
    id: 'bubble-theme',
    label: 'Bubble theme',
    group: 1,
    children,
  }
}

export function sectionMenuItems(opts: {
  canMoveUp: boolean
  canMoveDown: boolean
  internalOnly?: boolean
}): RailMenuItemSpec[] {
  return [
    { id: 'section-create', label: 'New section', group: 0 },
    { id: 'section-rename', label: 'Rename', group: 0 },
    {
      // #828: awareness-first framing — the padlock read as security locking;
      // the toggle is about whether section peers know about each other.
      // #1199: the long parenthetical was wordy menu noise; the toggle state
      // itself ("Isolate members" ↔ "Enable inter-agent awareness") carries it.
      id: 'section-talk-lock',
      label: opts.internalOnly ? 'Enable inter-agent awareness' : 'Isolate members',
      group: 0,
    },
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
  // #1727 — the kind-capability reasons a greyed item carries.
  herdrNoProfile: HERDR_NO_PROFILE,
  herdrNoDuplicate: HERDR_NO_DUPLICATE,
  chatNoProfile: CHAT_NO_PROFILE,
  chatNoDuplicate: CHAT_NO_DUPLICATE,
  noSwarmSessions: NO_SWARM_SESSIONS,
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
  // #1726: a chat row's id already names its conversation, so it is copyable
  // without a stored probe — the one kind that is *more* capable here than a
  // plain seat, and it must not fall through to the "no swarm-side id" grey.
  if (kind === 'chat') return parseRailChatRowId(railId)?.sessionId ?? null
  if (kind === 'cli' || kind === 'remote' || kind === 'herdr') return null
  if (kind === 'team') return teamThreadId(entityId.replace(/^team:/, ''))
  return conversationIdForAgent(entityId || railId)
}

export function duplicateName(name: string): string {
  const trimmed = name.trim() || 'Agent'
  return `${trimmed} copy`
}

/**
 * Generate a unique remote id for duplication, maintaining kind compatibility.
 * e.g. trueforge -> trueforge_copy -> trueforge_copy_2
 */
export function duplicateRemoteId(sourceId: string, existingIds: Iterable<string>): string {
  const existing = new Set<string>()
  for (const id of existingIds) {
    if (id) existing.add(id.toLowerCase().trim())
  }
  const cleanSource = (sourceId || 'remote').replace(/^remote:/, '').toLowerCase().trim()
  const root = cleanSource.replace(/_copy(_\d+)?$/, '')
  let candidate = `${root}_copy`
  if (!existing.has(candidate)) return candidate
  let index = 2
  while (existing.has(`${root}_copy_${index}`)) {
    index++
  }
  return `${root}_copy_${index}`
}
