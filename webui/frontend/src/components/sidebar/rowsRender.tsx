/**
 * #856 slice G — the rail's three row renderers, moved verbatim from
 * AgentSidebar.tsx behind a createRowRenderers(deps) factory.
 *
 * The factory receives every closure dependency the span referenced
 * (avatars, slot, helpers, drag/menu handlers, activity state) as one deps
 * object and returns exactly the three renderers. Behavior is unchanged —
 * this is a pure move; the pins live in components/__tests__/rowsRender.test.tsx.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- pass-through deps during extraction
import { facesFromDeclaredRoster, type DeclaredTeamRoster } from '../../lib/declaredRoster'
import { GROUP_AVATAR_MAX_FACES } from '../GroupAvatar'
// #1705: the selected-state glyph. Imported here (not injected) because it is a
// static decoration, not one of the injectable seat renderers.
import { Check, MessageSquare } from 'lucide-react'
// #1726: a chat row's destination and id shape.
import { railChatRowHref, type RailChatRow } from '../../lib/railChatRows'
import type { DragEvent as ReactDragEvent, MouseEvent as ReactMouseEvent } from 'react'
import type { RemoteEntry } from '../../lib/remotesCatalog'
import type { SidebarAgent } from '../../features/sidebar/rows'
import type { StackFace } from '../../lib/avatarStack'
import type { TeamRoster } from '../../lib/teamRosters'
import { getTurnSnapshot, isAgentTurnActive, type TurnSnapshot } from '../../lib/agentTurns'
import { peekAgentProfile } from '../../lib/agentProfile'
import { remoteRailDetail, remoteQuietSubtitle } from '../../lib/remoteKinds'
import { seatDisplayName } from '../../lib/seatHealth' // #1658
// #1692: one avatar-URL precedence for every seat surface.
import { SEAT_AVATAR_GL, SEAT_AVATAR_SIZE, seatAvatarSrc } from '../../lib/seatAvatar'
export interface RowRendererDeps {
  [key: string]: any
}

export function createRowRenderers(props: RowRendererDeps) {
    const { AgentAvatar, Link, NEEDS_APPROVAL_LABEL, GroupAvatar, RailRowSlot, StackedAvatars, Users, activeCliRail, activeHerdrRow, activeRail, activeSessionId, activeTaskSessionCount, agentLabel, agentRole, agentTurns, allowRowDrop, approvalWaitIds, beginRowDrag, catalog, cliActivityByAgent, cliRunningIds, declaredRosterForTeam, defaultSessionForRemote, defaultSessionForTeam, draggingId, dropOnSelf, dropReorder, dropTargetId, finishDrag, formatRailTimestamp, getRowLastMessage, isAvatarOnly, isCliRailAgent, isHerdrAgent, isMac, isPinnedId, isRailRowSelectable, isRailRowSelected, isRemoteOffline, loadLocalNewChatPerTask, markStackWorking, navigate, onClose, openDefinition, openGroupPicker, orderedFacesByRecency, parseAgentDragPayload, peekApprovalWait, peekCliRunning, peekRailDrag, pickOrClose, railKeyboardReorder, railTeamStackLayout, remoteHideId, remoteThemeFace, resolvedHiddenIds, roleBadgeLabel, roleCssClass, rosterById, rowMenuHandlers, selectRailRowRange, sessionsByAgent, sessionsForRemote, sessionsForTeam, setSessionPicker, settingsTick, shouldOpenSessionPicker, sidebarHref, stackFacesForRemote, stackFacesForTeam, teamChatFaceStack, teamHideId, teamSidepaneStack, toggleRailRowSelection, unreadIds } = props as any
    // #1244: the working motion is a cross-seat contract. Renderers must read
    // the live global registry, not just the snapshot the (possibly stale or
    // unmounted) parent passed down. When the parent prop is present it is
    // still OR'd in so a parent can surface turns the registry has not seen.
    const workingSnapshot: TurnSnapshot = agentTurns
      ? { ...getTurnSnapshot(), ...agentTurns }
      : getTurnSnapshot()
    const isSeatWorking = (id: string) =>
      Boolean(isAgentTurnActive(id, workingSnapshot) || cliRunningIds.has(id) || peekCliRunning(id))

    /* #1740 — Alt+Arrow reordering, on the SAME handler #1705 owns.
     *
     * `railReorderIntent` is the single gate (Alt alone, one of four arrows),
     * and it mirrors the guard of the window-level `onAltArrow` navigation
     * handler in AgentSidebar byte for byte — so the two can never both claim
     * one event. This one runs first (React's root listener is inside the
     * window), and when it claims the key it calls `preventDefault`, which the
     * window handler honours via its `defaultPrevented` bail. The existing
     * #1705 Space branch above is unchanged and still wins on Space, and
     * `inner.onKeyDown` (the row's ContextMenu / Shift+F10 opener) is still
     * forwarded for every key this does not claim. */
    const railRowSelection = (
      id: string,
      inner: {
        onClick?: (event: ReactMouseEvent<HTMLElement>) => void
        onKeyDown?: (event: any) => void
      } = {},
    ) => {
      const selected = Boolean(isRailRowSelected?.(id))
      return {
        'data-selected': selected ? 'true' : 'false',
        onClick: (event: ReactMouseEvent<HTMLElement>) => {
          if (isRailRowSelectable?.(id) !== false && (event.metaKey || event.ctrlKey)) {
            event.preventDefault()
            toggleRailRowSelection?.(id)
            return
          }
          if (isRailRowSelectable?.(id) !== false && event.shiftKey) {
            event.preventDefault()
            selectRailRowRange?.(id)
            return
          }
          inner.onClick?.(event)
        },
        onKeyDown: (event: any) => {
          if (
            event.key === ' ' &&
            !event.metaKey &&
            !event.ctrlKey &&
            !event.altKey &&
            isRailRowSelectable?.(id) !== false
          ) {
            // Space on a <button> would also fire a synthetic click and open
            // the seat, so it is consumed here rather than appended to.
            event.preventDefault()
            toggleRailRowSelection?.(id)
            return
          }
          // #1740: reorder within the section, or change section. `handled`
          // is false when the row is not re-orderable (a collapsed block, a
          // row the caller excluded) so the key falls through untouched.
          if (isRailRowSelectable?.(id) !== false && railKeyboardReorder?.(id, event)) {
            event.preventDefault()
            event.stopPropagation()
            return
          }
          inner.onKeyDown?.(event)
        },
      }
    }

    /* Selection is not a colour: a glyph rides the row's avatar slot (already a
       `position: relative` box) so the state reads without colour AND without
       reflowing the name. `aria-hidden` — the bulk bar's live count is the
       announced part. */
    const railRowSelectedCheck = (id: string) =>
      isRailRowSelected?.(id) ? (
        <span
          className="os-rail-selected-check absolute -left-0.5 -top-0.5"
          data-testid="rail-selected-check"
          aria-hidden="true"
        >
          <Check className="h-3 w-3" />
        </span>
      ) : null

  const renderAgentRow = (agent: SidebarAgent, hidden: boolean) => {
    const profile = peekAgentProfile(agent.id)
    const name = agentLabel(agent)
    const herdr = isHerdrAgent(agent)
    /* #1726: this row may be a CHAT with the seat, not the seat itself.
     *
     * The chat rides on the row's own agent object (`railChat`, set by the
     * rail when it builds the row) rather than in a seat-keyed lookup, which
     * is the difference between "a second row" and "the seat row wearing the
     * chat's hat": a lookup keyed by `agent.id` would hand the chat to the
     * SEAT row too, and one of the two would win. Tagged per row, both render
     * and each keeps its own rail id. `agent.id` stays the SEAT id, so the
     * avatar, role, profile and kind buckets still resolve to the agent. */
    const chat = (agent as { railChat?: RailChatRow | null }).railChat ?? null
    const railId = chat ? chat.id : agent.id
    const chatTitle = chat ? chat.title : ''
    const sessions = chat ? [] : sessionsByAgent[agent.id] ?? []
    // A chat row is already ONE session: it must not also become the seat's
    // scale-out picker, or clicking the twin would open the seat's list again
    // instead of the session the row names.
    const scaleOut = !herdr && !chat && shouldOpenSessionPicker(sessions)
    // #543: herdr seats are URL-addressable now (`herdrRowIdFromParams`), so
    // the targeted agent's row goes active exactly like a remote row.
    // A derived CLI row is targeted by `?blueprint=cli_agent&cli=<cli>`
    // (`activeCliRail`), which `activeRail` alone cannot resolve — and when it
    // is set it is the only CLI row that should light, so the generic
    // `cli_agent` seat does not stay active beside it.
    //
    // #1726: when the URL names a session, the CHAT row is the row the pane
    // is showing — the seat row yields its active state so the two cannot
    // both light up and leave the operator guessing which one is focused.
    const chatOwnsUrl = Boolean(chat && activeRail === chat.agentId && activeSessionId === chat.sessionId)
    const active = chatOwnsUrl || Boolean(!chat && (
      (activeHerdrRow && herdr && activeHerdrRow === agent.id) ||
      Boolean(activeCliRail && activeCliRail === agent.id) ||
      Boolean(activeRail && !activeCliRail && !herdr && activeRail === agent.id)
    ))
    const role = agentRole(agent)
    const dragging = draggingId === railId
    const dropping = dropTargetId === railId
    const badge = roleBadgeLabel(role)
    const taskCount = !chat && settingsTick >= 0 && loadLocalNewChatPerTask(agent.id)
      ? activeTaskSessionCount(agent.id)
      : 0
    const dataRole = role !== 'default' ? role : undefined
    const className = `os-agent-row group/row ${active ? 'os-agent-row--active' : ''} ${
      dragging ? 'os-agent-row--dragging' : ''
    } ${dropping ? 'os-agent-row--drop' : ''}`
    const { snippet, timestamp, previewClass } = getRowLastMessage(
      railId,
      sessions,
      agent, // #601: typed RowActivityMeta — no `as any`
      cliActivityByAgent[agent.id] ?? null,
    )
    const timestampLabel = formatRailTimestamp(timestamp)
    const unread = unreadIds.includes(railId)
    const needsApproval = approvalWaitIds.has(agent.id) || peekApprovalWait(agent.id)
    const agentWorking = isSeatWorking(agent.id)
    // #1196: a seat whose execution kind is a remote harness (herdr, trueforge,
    // …) shows the offline dot when that harness is unreachable. Unknown kinds
    // read 'pending' → false, so CLI/API rows are untouched.
    const agentRemoteOffline = Boolean(isRemoteOffline?.(agent.kind ?? ''))
    const mark = (
      scaleOut ? (
        // Teams/remotes (#398) must not be stacked here — import AvatarStack there.
        <StackedAvatars sessions={sessions} />
      ) : (
        <AgentAvatar
          src={seatAvatarSrc(agent)}
          agentId={agent.id}
          // #1692: the rail row and the chat-header pill are the two seat
          // identity surfaces; both take their size tier and their WebGL
          // decision from `lib/seatAvatar` so one agent cannot wear two.
          size={SEAT_AVATAR_SIZE}
          gl={SEAT_AVATAR_GL}
          active={agentWorking}
          status={agentWorking ? 'working' : 'idle'}
        />
      )
    )
    const roleBadgeNode = badge ? (
      <span
        className={`os-agent-role-badge shrink-0 ${roleCssClass(role)}`}
        data-role={role}
        data-definition-id={agent.id}
        style={{
          fontSize: '0.55rem',
          padding: '0 0.25rem',
          lineHeight: '1.2',
          height: '0.9rem',
          boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
          whiteSpace: 'nowrap',
        }}
      >
        {badge}
      </span>
    ) : null
    /* #1726: a chat row is labelled by its SESSION, and says whose chat it
     * is on the second line. Two rows with the same name would leave the
     * operator unable to tell the seat from its own twin, so the session
     * title is the primary label and the seat name becomes the subtitle. */
    const rowTitle = chat ? chatTitle || 'New chat' : name
    const rowSubtitle = chat ? `Chat with ${name}` : null
    const accessibleLabel = chat ? `Chat with ${name}: ${rowTitle}` : null
    const body = (
      <>
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {railRowSelectedCheck(railId)}
          {chat ? (
            // #1726: the affordance the issue asks for — a chat is marked as a
            // chat ON the avatar, so the twin is distinguishable from the
            // seat row without reading the label. `aria-hidden` because the
            // row's own accessible name already says "Chat with <seat>"; the
            // glyph is the visual half of that same statement.
            <span
              className="os-rail-chat-badge absolute -bottom-0.5 -right-0.5 z-10 inline-flex items-center justify-center rounded-full bg-base-100 text-base-content ring-1 ring-base-300"
              data-testid="rail-chat-badge"
              aria-hidden="true"
            >
              <MessageSquare className="h-2.5 w-2.5" strokeWidth={2.5} />
            </span>
          ) : null}
          {agentRemoteOffline && (
            // #1196: a remote-harness seat (herdr, trueforge, …) whose backing
            // gateway is down — same dot the remote rows and popup use.
            <span
              className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-error ring-1 ring-base-100 z-10"
              data-testid="rail-remote-offline-dot"
              aria-label="Remote offline"
            />
          )}
          {mark}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            {/* #500/#501: name and slot share one line, so the tip layers over
                the time instead of occupying a line of its own. */}
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={rowTitle} data-testid="rail-agent-name">{rowTitle}</span>
              <RailRowSlot
                isMac={isMac}
                unread={unread}
                badge={roleBadgeNode}
                timestampLabel={timestampLabel}
              />
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span
              className={`block truncate min-w-0 flex-1${needsApproval ? ' os-rail-attention' : ''}${
                !needsApproval && previewClass === 'error' ? ' os-rail-error-preview' : ''
              }`}
              data-preview={!needsApproval && previewClass === 'error' ? 'error' : undefined}
              data-testid={needsApproval ? 'rail-needs-approval' : undefined}
            >
              {needsApproval
                ? NEEDS_APPROVAL_LABEL
                : rowSubtitle
                  ? `${rowSubtitle}${snippet ? ` — ${snippet}` : ''}`
                  : snippet || profile?.description || agent.description}
            </span>
            {taskCount > 1 ? (
              <span
                className="badge badge-sm badge-outline shrink-0"
                data-task-sessions={taskCount}
                title={`${taskCount} running chats`}
              >
                {taskCount} chats
              </span>
            ) : null}
          </span>
        </span>
      </>
    )
    /* #1726: a chat row links to its OWN session; a seat row keeps
     * `sidebarHref`. One destination each, no conditional inside JSX. */
    const rowHref = chat ? railChatRowHref(chat) : sidebarHref(agent)
    if (herdr) {
      const herdrMenu = rowMenuHandlers(
        agent.id,
        name,
        hidden,
        isHerdrAgent(agent) ? 'herdr' : 'api',
      )
      return (
        <a
          href={rowHref}
          className={className}
          title={rowTitle}
          data-agent-id={railId}
          data-role={dataRole}
          data-chat-row={chat ? 'true' : undefined}
          aria-label={accessibleLabel ?? undefined}
          draggable={!hidden}
          onDragStart={(event) => beginRowDrag(event, { id: railId, name })}
          onDragEnd={finishDrag}
          onDragOver={(event) => allowRowDrop(event, railId)}
          onDrop={(event) => dropReorder(event, railId)}
          onMouseLeave={(event) => event.currentTarget.blur()}
          {...herdrMenu}
          {...railRowSelection(railId, {
            onClick: (event) => {
              pickOrClose?.()
              event.currentTarget.blur()
            },
            onKeyDown: herdrMenu.onKeyDown,
          })}
        >
          {body}
        </a>
      )
    }
    /* #1726: the row's menu identity. A chat row is a session, so the menu
     * gets the `'chat'` kind (which the capability matrix reads to grey Edit /
     * Duplicate) while `entityId` stays the SEAT, so every seat-shaped action
     * still addresses the agent. `resolveMenuKind` unwraps the id as a
     * fallback for the paths that only have the rail id. */
    const rowMenuKind = chat
      ? 'chat'
      : isCliRailAgent(agent)
        ? 'cli'
        : isHerdrAgent(agent)
          ? 'remote'
          : 'api'
    const rowMenu = rowMenuHandlers(railId, rowTitle, hidden, rowMenuKind)
    const dragHandlers = {
      draggable: !hidden,
      onDragStart: (event: ReactDragEvent) => beginRowDrag(event, { id: railId, name }),
      onDragEnd: finishDrag,
      onDragOver: (event: ReactDragEvent) => allowRowDrop(event, railId),
      onDrop: (event: ReactDragEvent) => dropReorder(event, railId),
      onMouseLeave: (event: ReactMouseEvent<HTMLElement>) => {
        event.currentTarget.blur()
      },
      ...rowMenu,
    }

    if (scaleOut) {
      return (
        <div
          className="os-agent-row-wrap"
          data-role={role}
          data-scale-out="true"
        >
          <button
            type="button"
            className={`${className} w-full`}
            title={rowTitle}
            data-agent-id={railId}
            data-role={dataRole}
            data-scale-out="true"
            aria-haspopup="dialog"
            aria-current={active ? 'page' : undefined}
            aria-label={`${name}, ${sessions.length} sessions`}
            {...dragHandlers}
            {...railRowSelection(railId, {
              onClick: (event) => {
                setSessionPicker({ agentId: agent.id, agentName: name, sessions })
                event.currentTarget.blur()
              },
              onKeyDown: rowMenu.onKeyDown,
            })}
          >
            {body}
          </button>
        </div>
      )
    }

    return (
      <div
        className="os-agent-row-wrap"
        data-role={role}
      >
        <Link
          to={rowHref}
          className={className}
          title={rowTitle}
          data-agent-id={railId}
          data-role={dataRole}
          data-chat-row={chat ? 'true' : undefined}
          // #1726: the row's TEXT runs the session title into the seat name
          // ("Fresh threadChat with Alpha"), so a chat row states its own
          // accessible name instead of leaving a screen reader to guess where
          // one ends. A seat row keeps its text-derived name untouched.
          aria-label={accessibleLabel ?? undefined}
          aria-current={active ? 'page' : undefined}
          {...dragHandlers}
          {...railRowSelection(railId, {
            onClick: (event) => {
              pickOrClose?.()
              event.currentTarget.blur()
            },
            onKeyDown: rowMenu.onKeyDown,
          })}
        >
          {body}
        </Link>
      </div>
    )
  }

  /**
   * #1362: a team's rail avatar is its membership — up to
   * {@link GROUP_AVATAR_MAX_FACES} member faces arranged in a circle (the
   * shared `GroupAvatar`), with a `+N` remainder. Remotes keep the #438 single
   * chat-face rule, and a team whose roster has not resolved keeps the generic
   * team mark rather than inventing a member.
   */
  const renderTeamAvatar = ({
    name,
    face,
    remainder,
    declared,
    teamId,
    recencyFaces,
    collapsed,
    remoteKind,
    groupChat,
  }: {
    name: string
    face?: StackFace | null
    remainder: number
    declared?: DeclaredTeamRoster | null
    teamId?: string
    /** #639: recency-ordered team faces (also the group-avatar membership). */
    recencyFaces?: StackFace[]
    /** #639: collapsed (avatar-width) rail — one face only. */
    collapsed?: boolean
    /** #747: remote platform kind — themes the face-less fallback. */
    remoteKind?: string | null
    /** #1362: a real team (not a remote) renders the circular group avatar. */
    groupChat?: boolean
  }) => {
    if (groupChat) {
      const members = declared
        ? facesFromDeclaredRoster(declared, teamId || name)
        : (recencyFaces ?? [])
      if (members.length > 0) {
        const faceCount = Math.min(GROUP_AVATAR_MAX_FACES, members.length)
        return (
          <span
            className="os-team-face os-team-face--group relative inline-flex shrink-0 items-center justify-center"
            data-testid="team-chat-face"
            data-remainder={String(Math.max(0, members.length - faceCount))}
            data-stack-count={String(faceCount)}
            data-member-count={String(members.length)}
            data-rail-collapsed={collapsed ? 'true' : 'false'}
          >
            <GroupAvatar members={members} size="sm" />
          </span>
        )
      }
    }
    if (!face) {
      // #747: remotes with no member faces render their platform-themed
      // face (Slack, AnythingLLM, …) instead of the generic Users mark.
      if (remoteKind) {
        return (
          <AgentAvatar
            agentId={teamId || name}
            alt={name}
            size="sm"
            remoteKind={remoteKind}
          />
        )
      }
      return (
        <span
          className="os-team-mark os-agent-team-icon flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-base-300 text-base-content/80"
          aria-hidden="true"
        >
          <Users className="h-3.5 w-3.5" />
        </span>
      )
    }
    // face — collapsed shows the most recently active member, wide shows the
    // chat target — and the `+N` remainder sticker (roster minus the face)
    // rides along in both. The graduated mini row is retired.
    const layout = railTeamStackLayout(recencyFaces ?? [], Boolean(collapsed))
    if (collapsed) {
      const solo = layout.faces[0] ?? face
      return (
        <span
          className="os-team-face relative inline-flex shrink-0 items-center justify-center"
          data-testid="team-chat-face"
          data-remainder={String(remainder)}
          data-stack-count="1"
          data-rail-collapsed="true"
        >
          <AgentAvatar
            src={seatAvatarSrc(solo)}
            agentId={solo.agentId || solo.id}
            alt={solo.name || name}
            size="sm"
            status={solo.working ? 'working' : 'idle'}
            active={Boolean(solo.working)}
          />
          {remainder > 0 ? (
            <span className="os-team-face__remainder" data-testid="team-remainder" aria-hidden="true">
              +{remainder}
            </span>
          ) : null}
        </span>
      )
    }
    return (
      <span
        className="os-team-face relative inline-flex shrink-0 items-center justify-center"
        data-testid="team-chat-face"
        data-remainder={String(remainder)}
        data-stack-count="1"
        data-rail-collapsed="false"
      >
        <span className="inline-flex items-end justify-center">
          <span
            className="relative inline-flex shrink-0"
            style={{ width: 32, height: 32 }}
          >
            <AgentAvatar
              src={seatAvatarSrc(face)}
              agentId={face.agentId || face.id}
              alt={face.name || name}
              size="sm"
              className="os-team-face__large"
              status={face.working ? 'working' : 'idle'}
              active={Boolean(face.working)}
            />
          </span>
        </span>
        {remainder > 0 ? (
          <span
            className="os-team-face__remainder"
            data-testid="team-remainder"
            aria-hidden="true"
          >
            +{remainder}
          </span>
        ) : null}
      </span>
    )
  }

  const renderTeamLink = (team: TeamRoster, hidden: boolean, nested = false) => {
    const name = team.name || team.id
    const hideId = teamHideId(team.id)
    const active = Boolean(activeRail) && activeRail === hideId
    const sessions = sessionsForTeam(team)
    const declared = declaredRosterForTeam(team, catalog)
    const rawFaces = stackFacesForTeam(team)
    // #438: the face is the team's chat target — `chief_of_staff_id`, else the
    // CoS-roled member, else the first. `defaultSessionForTeam` already owns
    // that rule, so the rail reads it rather than inventing a second one.
    const chatTargetId = defaultSessionForTeam(team)?.memberId ?? ''
    const marked = markStackWorking(
      rawFaces,
      (id: string) =>
        isSeatWorking(id) ||
        (isSeatWorking(hideId) && (rawFaces.length <= 1 || id === chatTargetId)),
    )
    const teamWorkerBusy = Boolean(
      marked.anyWorking ||
      isSeatWorking(hideId),
    )
    // NOTE: `teamSidepaneStack` caps the list at STACK_FACE_LIMIT, so it cannot
    // be the source of the remainder — a 5-member team would report +2. The
    // remainder is the *roster* minus the one face, which is what #438 specifies.
    const chatFace = declared
      ? null
      : teamChatFaceStack(teamSidepaneStack(marked.faces, teamWorkerBusy).faces, chatTargetId)
        .face
    const totalMembers = declared
      ? declared.parsed
        ? declared.count
        : 1
      : team.members
        ? team.members.length
        : rawFaces.length
    const teamRemainder = declared || totalMembers <= 1 ? 0 : totalMembers - 1
    const dragging = draggingId === hideId
    const dropping = dropTargetId === hideId
    // #438: the roster is no longer fanned into faces, so "needs approval" is the
    // chat face's state (the member the row represents) rather than any member.
    const teamNeedsApproval =
      approvalWaitIds.has(teamHideId(team.id)) ||
      peekApprovalWait(teamHideId(team.id)) ||
      Boolean(
        chatFace &&
          (approvalWaitIds.has(chatFace.id) || peekApprovalWait(chatFace.id)),
      )
    const { snippet: teamSnippet, timestamp: teamTime, previewClass: teamPreviewClass } = getRowLastMessage(
      teamHideId(team.id),
      sessions,
      team, // #601: TeamRoster.lastMessageAt — no `as any`
    )
    const teamTimestampLabel = formatRailTimestamp(teamTime)
    const unread = unreadIds.includes(hideId)
    // #639 (REQ-909) as revised by #817: recency-ordered faces — every state
    // renders one face (most recently active when collapsed, chat target when
    // wide) plus the roster `+N` sticker. No mini row in either state.
    const teamRecencyFaces = orderedFacesByRecency(marked.faces)
    // #525: no `Team` badge. Team membership is not a role, so the pill was
    // claiming role status — same reason #496 removed `Remote`. The right slot
    // now falls through to the row's timestamp.
    const teamMenu = rowMenuHandlers(hideId, name, hidden, 'team', sessions, team.id)
    return (        <Link
          to={`/chat?team=${encodeURIComponent(team.id)}`}
          title={name}
          className={`os-team-item os-agent-row group/row os-agent-row--team ${
          active ? 'os-agent-row--active' : ''
        } ${nested ? 'os-agent-row--nested' : ''} ${dragging ? 'os-agent-row--dragging' : ''} ${
          dropping ? 'os-agent-row--drop' : ''
        } ${teamWorkerBusy ? 'os-agent-row--working-stack' : ''}`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (team)`}
        data-agent-id={hideId}
        data-kind="team"
        data-stack-count={String(Math.min(GROUP_AVATAR_MAX_FACES, totalMembers))}
        data-remainder={String(Math.max(0, totalMembers - GROUP_AVATAR_MAX_FACES))}
        data-persona-count={declared ? String(declared.parsed ? declared.count : 1) : undefined}
        data-roster={declared ? 'declared' : undefined}
        draggable={!hidden}
        onDragStart={(event: ReactDragEvent) => beginRowDrag(event, { id: hideId, name })}
        onDragEnd={finishDrag}
        onDragOver={(event: ReactDragEvent) => allowRowDrop(event, hideId)}
        onDrop={(event: ReactDragEvent) => dropReorder(event, hideId)}
        {...teamMenu}
        {...railRowSelection(hideId, {
          onClick: (event: ReactMouseEvent<HTMLElement>) => {
          event.preventDefault()
          const def = defaultSessionForTeam(team)
          if (def) {
            navigate(def.href)
            onClose?.()
          } else {
            openGroupPicker(name, sessions)
          }
        },
          onKeyDown: teamMenu.onKeyDown,
        })}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {railRowSelectedCheck(hideId)}
          {renderTeamAvatar({
            name,
            face: chatFace,
            remainder: teamRemainder,
            declared,
            teamId: team.id,
            recencyFaces: teamRecencyFaces,
            collapsed: isAvatarOnly,
            groupChat: true,
          })}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={name} data-testid="rail-agent-name">{name}</span>
              <RailRowSlot
                isMac={isMac}
                unread={unread}
                timestampLabel={teamTimestampLabel}
              />
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span
              className={`block truncate min-w-0 flex-1${teamNeedsApproval ? ' os-rail-attention' : ''}${
                !teamNeedsApproval && teamPreviewClass === 'error' ? ' os-rail-error-preview' : ''
              }`}
              data-preview={!teamNeedsApproval && teamPreviewClass === 'error' ? 'error' : undefined}
              data-testid={teamNeedsApproval ? 'rail-needs-approval' : undefined}
            >
              {teamNeedsApproval ? NEEDS_APPROVAL_LABEL : teamSnippet || team.description}
            </span>
          </span>
        </span>
      </Link>
    )
  }

  const renderRemoteRow = (remote: RemoteEntry, hidden: boolean) => {
    // #1658 follow-up: a remote seat's name does not flow through agentLabel,
    // so it is decorated here — the same `⚠ broken` marker, from the same
    // health store, and it clears itself when the seat recovers.
    const name = seatDisplayName(remote.title, { kind: 'remote', seatId: remote.id })
    const hideId = remoteHideId(remote.id)
    const active = Boolean(activeRail) && activeRail === hideId
    const dragging = draggingId === hideId
    const sessions = sessionsForRemote(remote)
    const rawFaces = stackFacesForRemote(remote)
    const remoteTargetId = defaultSessionForRemote(remote)?.memberId ?? ''
    const marked = markStackWorking(
      rawFaces,
      (id: string) =>
        isSeatWorking(id) ||
        (isSeatWorking(hideId) && (rawFaces.length <= 1 || id === remoteTargetId)),
    )
    const remoteWorkerBusy = Boolean(
      marked.anyWorking ||
      isSeatWorking(hideId),
    )
    // #438: a remote has no CoS concept, so its chat face is the default talk-to
    // member — first, in the ordering the working-aware stack already produced.
    // The remainder comes from the member total, never from the capped list.
    const chatFace = teamChatFaceStack(
      teamSidepaneStack(marked.faces, remoteWorkerBusy).faces,
      defaultSessionForRemote(remote)?.memberId ?? '',
    ).face
    // #747: sessionsForRemote fabricates a member for empty remotes, so the
    // face is rarely null — the themed face applies whenever the chat face
    // carries no custom avatar (uploaded faces always win).
    const chatFaceHasAvatar = Boolean(seatAvatarSrc(chatFace))
    const totalMembers = remote.agents ? remote.agents.length : rawFaces.length
    const singleMember = totalMembers === 1
    const remoteRemainder = totalMembers <= 1 ? 0 : totalMembers - 1
    const remoteNeedsApproval =
      approvalWaitIds.has(hideId) ||
      peekApprovalWait(hideId) ||
      Boolean(
        chatFace &&
          (approvalWaitIds.has(chatFace.id) || peekApprovalWait(chatFace.id)),
      )
    const { snippet: remoteSnippet, timestamp: remoteTime, previewClass: remotePreviewClass } = getRowLastMessage(
      hideId,
      sessions,
      remote, // #601: RemoteEntry.lastMessageAt — no `as any`
    )
    const remoteTimestampLabel = formatRailTimestamp(remoteTime)
    const unread = unreadIds.includes(hideId)
    // #1196: the row's own remote is the health subject here.
    const remoteRowOffline = Boolean(isRemoteOffline?.(remote.id))
    // #496: no `Remote` badge. Remote is a seat kind (transport), not a role, so
    // the pill was claiming role status. The kind stays on the row itself —
    // `data-kind="remote"`, `os-agent-row--remote`, and the `(remote)` aria
    // label all remain. The right slot now falls through to the timestamp.
    const remoteMenu = rowMenuHandlers(hideId, name, hidden, 'remote', sessions, remote.id)
    return (
      <Link
        to={`/chat?remote=${encodeURIComponent(remote.id)}`}
        title={name}
        className={`os-remote-item os-agent-row group/row os-agent-row--remote ${
          active ? 'os-agent-row--active' : ''
        } ${dragging ? 'os-agent-row--dragging' : ''} ${
          remoteWorkerBusy ? 'os-agent-row--working-stack' : ''
        }`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (remote)`}
        data-agent-id={hideId}
        data-kind="remote"
        data-remote-id={remote.id}
        data-stack-count={String(singleMember ? 1 : chatFace ? 1 : 0)}
        data-remainder={String(remoteRemainder)}
        draggable={!hidden}
        onDragStart={(event: ReactDragEvent) => beginRowDrag(event, { id: hideId, name })}
        onDragEnd={finishDrag}
        onDragOver={(event: ReactDragEvent) => {
          const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
          if (isPinnedId(fromId)) {
            allowRowDrop(event, hideId)
            return
          }
          try {
            event.dataTransfer.dropEffect = 'none'
          } catch {
            /* synthetic events may omit dataTransfer */
          }
        }}
        onDrop={dropOnSelf}
        {...remoteMenu}
        {...railRowSelection(hideId, {
          onClick: (event: ReactMouseEvent<HTMLElement>) => {
          event.preventDefault()
          // #748: rail rows are launch surfaces — every row navigates
          // immediately, session-capable remotes included. The default is the
          // most recent session when one exists; otherwise the remote chat.
          // Session *switching* stays in the chat header, not the rail.
          const def = defaultSessionForRemote(remote)
          navigate(def?.href || `/chat?remote=${encodeURIComponent(remote.id)}`)
          onClose?.()
        },
          onKeyDown: remoteMenu.onKeyDown,
        })}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {railRowSelectedCheck(hideId)}
          {remoteRowOffline && (
            // #1196: this row IS a remote — dot when its gateway is down.
            <span
              className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-error ring-1 ring-base-100 z-10"
              data-testid="rail-remote-offline-dot"
              aria-label="Remote offline"
            />
          )}
          {!chatFaceHasAvatar && remoteThemeFace(remote.kind) ? (
            // #747: platform-themed face (Slack, AnythingLLM, …) —
            // only for kinds the registry actually covers, so omb/herdr and
            // other stack remotes keep their existing member-face rendering.
            <AgentAvatar
              agentId={remote.id}
              alt={name}
              size="sm"
              remoteKind={remote.kind}
              active={remoteWorkerBusy}
              status={remoteWorkerBusy ? 'working' : 'idle'}
            />
          ) : (
            renderTeamAvatar({
              name,
              face: chatFace,
              remainder: remoteRemainder,
              teamId: remote.id,
              remoteKind: remote.kind,
            })
          )}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={name} data-testid="rail-agent-name">{name}</span>
              <RailRowSlot
                isMac={isMac}
                unread={unread}
                timestampLabel={remoteTimestampLabel}
              />
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span
              className={`block truncate min-w-0 flex-1${remoteNeedsApproval ? ' os-rail-attention' : ''}${
                !remoteNeedsApproval && remotePreviewClass === 'error' ? ' os-rail-error-preview' : ''
              }`}
              data-preview={!remoteNeedsApproval && remotePreviewClass === 'error' ? 'error' : undefined}
              data-testid={remoteNeedsApproval ? 'rail-needs-approval' : undefined}
            >
              {remoteNeedsApproval
                ? NEEDS_APPROVAL_LABEL
                : remoteRailDetail(remote, remoteSnippet) || remoteQuietSubtitle(remote)}
            </span>
          </span>
        </span>
      </Link>
    )
  }

  const renderTeamRow = (
    team: TeamRoster,
    nested = false,
    seen: string[] = [],
    railIndex?: number,
  ) => {
    const hidden = resolvedHiddenIds.includes(teamHideId(team.id))
    if (hidden && !nested) return null
    const childSlots = team.members.filter((m) => m.kind === 'team')
    return (
      <li
        key={`team-${team.id}`}
        data-rail-id={nested ? undefined : teamHideId(team.id)}
        data-rail-index={nested ? undefined : railIndex}
      >
        {hidden ? null : renderTeamLink(team, false, nested)}
        {childSlots.length > 0 && !seen.includes(team.id) ? (
          <ul className="os-agent-team-nest">
            {childSlots.map((m) => {
              const child = rosterById.get(m.team_id || m.id)
              if (child) return renderTeamRow(child, true, seen.concat(team.id))
              return (
                <li key={`team-slot-${m.id}`}>
                  <span className="os-agent-row os-agent-row--team os-agent-row--nested">
                    <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
                      <Users className="os-agent-team-icon h-4 w-4 shrink-0" aria-hidden="true" />
                    </span>
                    <span className="os-agent-row__label-col min-w-0 flex-1">
                      <span className="flex min-w-0 items-center justify-between gap-1.5">
                        <span className="block truncate text-sm font-semibold leading-5">
                          {m.team_id || m.id}
                        </span>
                        <span className="flex items-center gap-1 shrink-0">
                          <span
                            className="os-agent-role-badge shrink-0"
                            data-kind="team"
                            data-definition-id={m.team_id || m.id}
                            role="button"
                            tabIndex={0}
                            aria-label={`Open ${m.team_id || m.id} team settings`}
                            style={{
                              fontSize: '0.55rem',
                              padding: '0 0.25rem',
                              lineHeight: '1.2',
                              height: '0.9rem',
                              boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
                              whiteSpace: 'nowrap',
                            }}
                            onClick={(event) => {
                              event.preventDefault()
                              event.stopPropagation()
                              const teamId = m.team_id || m.id
                              openDefinition('team', teamId, { teamId })
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                event.stopPropagation()
                                const teamId = m.team_id || m.id
                                openDefinition('team', teamId, { teamId })
                              }
                            }}
                          >
                            Team
                          </span>
                        </span>
                      </span>
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>
        ) : null}
      </li>
    )
  }

  return { renderAgentRow, renderRemoteRow, renderTeamRow }
}
