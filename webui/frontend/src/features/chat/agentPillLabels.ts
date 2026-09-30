/**
 * #1698 / #1706 — the label matrix for the floating agent pill.
 *
 * The pill is `avatar | top label | bottom label | right-aligned actions`
 * (#1706), so the bottom label has exactly ONE correct answer per session
 * shape. Deciding it in one pure module keeps the matrix honest: the pill
 * renders whatever this returns and never re-derives an identity inline, so
 * "no wrong bottom label when switching sessions" (#1706 §11) is a property of
 * this function rather than of a chain of ternaries in JSX.
 *
 * Three modes, and they are mutually exclusive by construction:
 *
 *   `role`  — a self / home seat. Bottom is the OpenRig address `role@rig`
 *             (#1698 §A, #1706 §A). No rig → bare role, never a dangling `@`.
 *   `group` — a team roster or a remote bridge. Bottom is the SELECTED member's
 *             display name (#1706 §B) — deliberately NOT `role@rig`, because a
 *             group chat owns no role of its own (#1706 §D).
 *   `chat`  — a dedicated chat session. Bottom is this chat's name, defaulting
 *             to `chat: <agent name>` (#1706 §C.9). Also never `role@rig`
 *             (#1698 §B.5).
 *
 * The role token is the operator badge word (`ROLE_BADGE_LABELS`, e.g.
 * `Support` / `Belay` / `CoS`) with the raw role id as the fallback, so the
 * address reuses the one existing role vocabulary instead of minting a second
 * one. `agent_id` is never part of the address and never rewritten.
 *
 * The `@rig` half is a REAL rig name, never a model or a vendor: a dynamic rig
 * is a sidepane Section and a static rig is a team roster (`lib/rigAddress`).
 * Every model name in this system is a weighted pool across several vendors, so
 * a vendor or model string here would be a fresh lie.
 */

import { agentRigAddress } from '../../lib/rigAddress'

/** Bottom-label shapes, in precedence order. */
export const AGENT_PILL_MODES = ['role', 'group', 'chat'] as const
export type AgentPillMode = (typeof AGENT_PILL_MODES)[number]

/** #1706 §C.9 — the default name for a new dedicated chat. */
export const CHAT_NAME_PREFIX = 'chat: '

export interface AgentPillLabelInput {
  /** Agent display name. The top label for `role` / `chat`, ignored for `group`. */
  agentName: string
  /** Operator badge word for the role (`ROLE_BADGE_LABELS`). */
  roleLabel?: string | null
  /** Raw role id, used when the badge word is empty (a custom role). */
  roleId?: string | null
  /** Rig name for the `@rig` half. Empty / null → bare role, no dangling `@`. */
  rigName?: string | null
  /** Team / remote name. Non-empty selects `group` mode. */
  groupName?: string | null
  /** Selected member within the team / remote. Empty → no bottom label. */
  selectedMemberName?: string | null
  /** True when this seat is a dedicated chat session rather than the home seat. */
  chatSession?: boolean
  /** This chat's assigned name. Empty → the `chat: <agent name>` default. */
  chatName?: string | null
}

export interface AgentPillLabels {
  mode: AgentPillMode
  /** Top label: agent name, or the group-chat name. */
  top: string
  /** Bottom label. Empty means "render no bottom row" (never a blank one). */
  bottom: string
  /** The full OpenRig address for `role` mode; `''` for the other modes. */
  address: string
  /** The rig half on its own, for composing the `@rig` span. `''` when unknown. */
  rig: string
}

function trimmed(value: unknown): string {
  return String(value ?? '').trim()
}

/**
 * #1706 §C.9 — the default name for a chat that has not been renamed.
 *
 * `chat: <agent name>`, where the agent is the peer / target for that session.
 */
export function defaultChatName(agentName: string): string {
  const name = trimmed(agentName)
  return name ? `${CHAT_NAME_PREFIX}${name}` : ''
}

/**
 * Is this URL `?session=` a dedicated chat rather than the agent's home thread?
 *
 * `lib/agentChat` mints ONE stable conversation id per agent and puts it on the
 * URL when navigating to that agent's chat (`agentChatHref`), so the home seat
 * always carries its own id back. A DIFFERENT id is a separate conversation the
 * operator explicitly opened — the `chat` mode. No id at all is the home seat.
 *
 * Pure on purpose: the caller owns the storage read, so this stays testable
 * without a `localStorage` fixture.
 */
export function isDedicatedChatSession(
  sessionId: string | null | undefined,
  stableConversationId: string | null | undefined,
): boolean {
  const session = trimmed(sessionId)
  if (!session) return false
  return session !== trimmed(stableConversationId)
}

/**
 * The one function that owns the pill's identity (#1706 §11).
 *
 * `group` wins over `chat`: a team / remote seat can also carry a member
 * session, and its bottom label is the member, not the chat.
 */
export function resolveAgentPillLabels(input: AgentPillLabelInput): AgentPillLabels {
  const agentName = trimmed(input.agentName)
  const groupName = trimmed(input.groupName)

  if (groupName) {
    // #1706 §B.5 — the selected member, never `role@rig`. An unresolved member
    // renders NO bottom row rather than the wrong one.
    return {
      mode: 'group',
      top: groupName,
      bottom: trimmed(input.selectedMemberName),
      address: '',
      rig: '',
    }
  }

  if (input.chatSession) {
    // #1706 §C.7/C.8 — owner on top, this chat's name underneath. #1698 §B.5
    // forbids `role@rig` here.
    const name = trimmed(input.chatName)
    return {
      mode: 'chat',
      top: agentName,
      bottom: name || defaultChatName(agentName),
      address: '',
      rig: '',
    }
  }

  // #1698 §A / #1706 §A — `role@rig`, or a bare role when no rig is known.
  const role = trimmed(input.roleLabel) || trimmed(input.roleId)
  const rig = trimmed(input.rigName)
  return {
    mode: 'role',
    top: agentName,
    bottom: role ? agentRigAddress({ role, rig }) : '',
    address: role ? agentRigAddress({ role, rig }) : '',
    rig,
  }
}

/**
 * Display name of a group / remote member, matched on the several id shapes the
 * session pickers use (`MemberSession.id` may be the `remote:agent` composite
 * while `memberId` is the bare agent id).
 *
 * Returns `''` when the id does not resolve: printing a raw id where a name is
 * owed would be a wrong bottom label (#1706 §11).
 */
export function memberDisplayName(
  rows: ReadonlyArray<Record<string, unknown>> | null | undefined,
  memberId: string | null | undefined,
): string {
  const target = trimmed(memberId)
  if (!target) return ''
  const tail = target.includes(':') ? target.slice(target.lastIndexOf(':') + 1) : target
  for (const row of rows ?? []) {
    if (!row) continue
    const candidates = [row.id, row.memberId, row.agentId].map(trimmed).filter(Boolean)
    if (!candidates.includes(target) && !candidates.includes(tail)) continue
    return trimmed(row.name) || trimmed(row.label) || trimmed(row.title)
  }
  return ''
}
