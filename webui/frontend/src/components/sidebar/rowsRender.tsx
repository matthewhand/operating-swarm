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
import type { DeclaredTeamRoster } from '../../lib/declaredRoster'
import type { DragEvent as ReactDragEvent, MouseEvent as ReactMouseEvent } from 'react'
import type { RemoteEntry } from '../../lib/remotesCatalog'
import type { SidebarAgent } from '../../features/sidebar/rows'
import type { StackFace } from '../../lib/avatarStack'
import type { TeamRoster } from '../../lib/teamRosters'
import { getTurnSnapshot, isAgentTurnActive, type TurnSnapshot } from '../../lib/agentTurns'
export interface RowRendererDeps {
  [key: string]: any
}

export function createRowRenderers(props: RowRendererDeps) {
    const { AgentAvatar, Link, NEEDS_APPROVAL_LABEL, PersonaRoster, RailRowSlot, StackedAvatars, Users, activeHerdrRow, activeRail, activeTaskSessionCount, agentLabel, agentRole, agentTurns, allowRowDrop, approvalWaitIds, beginRowDrag, catalog, cliActivityByAgent, cliRunningIds, declaredRosterForTeam, defaultSessionForRemote, defaultSessionForTeam, draggingId, dropOnSelf, dropReorder, dropTargetId, finishDrag, formatRailTimestamp, getRowLastMessage, isAvatarOnly, isCliRailAgent, isHerdrAgent, isMac, isPinnedId, loadLocalNewChatPerTask, markStackWorking, navigate, onClose, openDefinition, openGroupPicker, orderedFacesByRecency, parseAgentDragPayload, peekApprovalWait, peekCliRunning, peekRailDrag, pickOrClose, railTeamStackLayout, remoteHideId, remoteThemeFace, resolvedHiddenIds, roleBadgeLabel, roleCssClass, rosterById, rowMenuHandlers, sessionsByAgent, sessionsForRemote, sessionsForTeam, setSessionPicker, settingsTick, shouldOpenSessionPicker, sidebarHref, stackFacesForRemote, stackFacesForTeam, teamChatFaceStack, teamHideId, teamSidepaneStack, unreadIds } = props as any
    const turnSnapshot: TurnSnapshot = agentTurns || getTurnSnapshot()
    const isSeatWorking = (id: string) =>
      Boolean(isAgentTurnActive(id, turnSnapshot) || cliRunningIds.has(id) || peekCliRunning(id))

  const renderAgentRow = (agent: SidebarAgent, hidden: boolean) => {
    const name = agentLabel(agent)
    const herdr = isHerdrAgent(agent)
    const sessions = sessionsByAgent[agent.id] ?? []
    const scaleOut = !herdr && shouldOpenSessionPicker(sessions)
    // #543: herdr seats are URL-addressable now (`herdrRowIdFromParams`), so
    // the targeted agent's row goes active exactly like a remote row.
    const active = Boolean(activeHerdrRow && herdr && activeHerdrRow === agent.id) ||
      Boolean(activeRail && !herdr && activeRail === agent.id)
    const role = agentRole(agent)
    const dragging = draggingId === agent.id
    const dropping = dropTargetId === agent.id
    const badge = roleBadgeLabel(role)
    const taskCount = settingsTick >= 0 && loadLocalNewChatPerTask(agent.id)
      ? activeTaskSessionCount(agent.id)
      : 0
    const dataRole = role !== 'default' ? role : undefined
    const className = `os-agent-row group/row ${active ? 'os-agent-row--active' : ''} ${
      dragging ? 'os-agent-row--dragging' : ''
    } ${dropping ? 'os-agent-row--drop' : ''}`
    const { snippet, timestamp } = getRowLastMessage(
      agent.id,
      sessions,
      agent, // #601: typed RowActivityMeta — no `as any`
      cliActivityByAgent[agent.id] ?? null,
    )
    const timestampLabel = formatRailTimestamp(timestamp)
    const unread = unreadIds.includes(agent.id)
    const needsApproval = approvalWaitIds.has(agent.id) || peekApprovalWait(agent.id)
    const agentWorking = isSeatWorking(agent.id)
    const mark = (
      scaleOut ? (
        // Teams/remotes (#398) must not be stacked here — import AvatarStack there.
        <StackedAvatars sessions={sessions} />
      ) : (
        <AgentAvatar
          src={agent.avatar_path}
          agentId={agent.id}
          size="sm"
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
    const body = (
      <>
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {mark}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            {/* #500/#501: name and slot share one line, so the tip layers over
                the time instead of occupying a line of its own. */}
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={name} data-testid="rail-agent-name">{name}</span>
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
              className={`block truncate min-w-0 flex-1${needsApproval ? ' os-rail-attention' : ''}`}
              data-testid={needsApproval ? 'rail-needs-approval' : undefined}
            >
              {needsApproval ? NEEDS_APPROVAL_LABEL : snippet || agent.description}
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
    if (herdr) {
      return (
        <a
          href={sidebarHref(agent)}
          className={className}
          data-agent-id={agent.id}
          data-role={dataRole}
          draggable={!hidden}
          onDragStart={(event) => beginRowDrag(event, { id: agent.id, name })}
          onDragEnd={finishDrag}
          onDragOver={(event) => allowRowDrop(event, agent.id)}
          onDrop={(event) => dropReorder(event, agent.id)}
          onClick={(event) => {
            pickOrClose?.()
            event.currentTarget.blur()
          }}
          onMouseLeave={(event) => event.currentTarget.blur()}
          {...rowMenuHandlers(agent.id, name, hidden, isHerdrAgent(agent) ? 'herdr' : 'api')}
        >
          {body}
        </a>
      )
    }
    const dragHandlers = {
      draggable: !hidden,
      onDragStart: (event: ReactDragEvent) => beginRowDrag(event, { id: agent.id, name }),
      onDragEnd: finishDrag,
      onDragOver: (event: ReactDragEvent) => allowRowDrop(event, agent.id),
      onDrop: (event: ReactDragEvent) => dropReorder(event, agent.id),
      onMouseLeave: (event: ReactMouseEvent<HTMLElement>) => {
        event.currentTarget.blur()
      },
      ...rowMenuHandlers(
        agent.id,
        name,
        hidden,
        isCliRailAgent(agent) ? 'cli' : isHerdrAgent(agent) ? 'remote' : 'api',
      ),
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
            data-agent-id={agent.id}
            data-role={dataRole}
            data-scale-out="true"
            aria-haspopup="dialog"
            aria-current={active ? 'page' : undefined}
            aria-label={`${name}, ${sessions.length} sessions`}
            {...dragHandlers}
            onClick={(event) => {
              setSessionPicker({ agentId: agent.id, agentName: name, sessions })
              event.currentTarget.blur()
            }}
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
          to={sidebarHref(agent)}
          className={className}
          data-agent-id={agent.id}
          data-role={dataRole}
          aria-current={active ? 'page' : undefined}
          {...dragHandlers}
          onClick={(event: ReactMouseEvent<HTMLElement>) => {
            pickOrClose?.()
            event.currentTarget.blur()
          }}
        >
          {body}
        </Link>
      </div>
    )
  }

  /**
   * #438: one face — the member you are talking to — plus a compact `+N` for
   * everyone else. No fan of overlapping faces at rail size. `remainder` is
   * omitted entirely for a one-member team, and a team whose roster has not
   * resolved keeps the generic team mark rather than inventing a member.
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
  }: {
    name: string
    face?: StackFace | null
    remainder: number
    declared?: DeclaredTeamRoster | null
    teamId?: string
    /** #639: recency-ordered faces for the graduated mini row (wide rail). */
    recencyFaces?: StackFace[]
    /** #639: collapsed (avatar-width) rail — one face only. */
    collapsed?: boolean
    /** #747: remote platform kind — themes the face-less fallback. */
    remoteKind?: string | null
  }) => {
    if (declared) {
      return <PersonaRoster roster={declared} groupId={teamId || name} label={`${name} declared members`} />
    }
    if (!face) {
      // #747: remotes with no member faces render their platform-themed
      // face (Letta, Slack, AnythingLLM, …) instead of the generic Users mark.
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
            src={solo.avatarSrc || solo.src}
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
              src={face.avatarSrc || face.src}
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
    const marked = markStackWorking(
      rawFaces,
      (id: string) => isSeatWorking(id),
    )
    const teamWorkerBusy = Boolean(
      marked.anyWorking ||
      isSeatWorking(hideId),
    )
    // #438: the face is the team's chat target — `chief_of_staff_id`, else the
    // CoS-roled member, else the first. `defaultSessionForTeam` already owns
    // that rule, so the rail reads it rather than inventing a second one.
    const chatTargetId = defaultSessionForTeam(team)?.memberId ?? ''
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
    const singleMember = !declared && totalMembers === 1
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
    const { snippet: teamSnippet, timestamp: teamTime } = getRowLastMessage(
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
    return (
      <Link
        to={`/chat?team=${encodeURIComponent(team.id)}`}
        className={`os-team-item os-agent-row group/row os-agent-row--team ${
          active ? 'os-agent-row--active' : ''
        } ${nested ? 'os-agent-row--nested' : ''} ${dragging ? 'os-agent-row--dragging' : ''} ${
          dropping ? 'os-agent-row--drop' : ''
        } ${teamWorkerBusy ? 'os-agent-row--working-stack' : ''}`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (team)`}
        data-agent-id={hideId}
        data-kind="team"
        data-stack-count={String(declared ? (declared.parsed ? declared.count : 1) : singleMember ? 1 : chatFace ? 1 : 0)}
        data-remainder={String(teamRemainder)}
        data-persona-count={declared ? String(declared.parsed ? declared.count : 1) : undefined}
        data-roster={declared ? 'declared' : undefined}
        draggable={!hidden}
        onDragStart={(event: ReactDragEvent) => beginRowDrag(event, { id: hideId, name })}
        onDragEnd={finishDrag}
        onDragOver={(event: ReactDragEvent) => allowRowDrop(event, hideId)}
        onDrop={(event: ReactDragEvent) => dropReorder(event, hideId)}
        onClick={(event: ReactMouseEvent) => {
          event.preventDefault()
          const def = defaultSessionForTeam(team)
          if (def) {
            navigate(def.href)
            onClose?.()
          } else {
            openGroupPicker(name, sessions)
          }
        }}
        {...rowMenuHandlers(hideId, name, hidden, 'team', sessions, team.id)}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {renderTeamAvatar({
            name,
            face: chatFace,
            remainder: teamRemainder,
            declared,
            teamId: team.id,
            recencyFaces: teamRecencyFaces,
            collapsed: isAvatarOnly,
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
              className={`block truncate min-w-0 flex-1${teamNeedsApproval ? ' os-rail-attention' : ''}`}
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
    const name = remote.title
    const hideId = remoteHideId(remote.id)
    const active = Boolean(activeRail) && activeRail === hideId
    const dragging = draggingId === hideId
    const sessions = sessionsForRemote(remote)
    const rawFaces = stackFacesForRemote(remote)
    const marked = markStackWorking(
      rawFaces,
      (id: string) => isSeatWorking(id),
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
    const chatFaceHasAvatar = Boolean(chatFace && (chatFace.avatarSrc || chatFace.src))
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
    const { snippet: remoteSnippet, timestamp: remoteTime } = getRowLastMessage(
      hideId,
      sessions,
      remote, // #601: RemoteEntry.lastMessageAt — no `as any`
    )
    const remoteTimestampLabel = formatRailTimestamp(remoteTime)
    const unread = unreadIds.includes(hideId)
    // #496: no `Remote` badge. Remote is a seat kind (transport), not a role, so
    // the pill was claiming role status. The kind stays on the row itself —
    // `data-kind="remote"`, `os-agent-row--remote`, and the `(remote)` aria
    // label all remain. The right slot now falls through to the timestamp.
    return (
      <Link
        to={`/chat?remote=${encodeURIComponent(remote.id)}`}
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
        onClick={(event: ReactMouseEvent) => {
          event.preventDefault()
          // #748: rail rows are launch surfaces — every row navigates
          // immediately, session-capable remotes included. The default is the
          // most recent session when one exists; otherwise the remote chat.
          // Session *switching* stays in the chat header, not the rail.
          const def = defaultSessionForRemote(remote)
          navigate(def?.href || `/chat?remote=${encodeURIComponent(remote.id)}`)
          onClose?.()
        }}
        {...rowMenuHandlers(hideId, name, hidden, 'remote', sessions, remote.id)}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {!chatFaceHasAvatar && remoteThemeFace(remote.kind) ? (
            // #747: platform-themed face (Letta, Slack, AnythingLLM, …) —
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
              className={`block truncate min-w-0 flex-1${remoteNeedsApproval ? ' os-rail-attention' : ''}`}
              data-testid={remoteNeedsApproval ? 'rail-needs-approval' : undefined}
            >
              {remoteNeedsApproval
                ? NEEDS_APPROVAL_LABEL
                : remoteSnippet || (remote as any).description || 'Remote team'}
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
