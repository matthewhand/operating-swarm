/**
 * #856 slice H — the chat bottom dock, moved verbatim from ChatPage.tsx.
 *
 * Renders the chat page's top header: agent identity/routing, session
 * pickers, computer-control stub, theme toggle, and settings entry.
 * ChatPage owns all state and passes it down as one props object.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- pass-through props during extraction
import { useEffect, useRef, useState } from 'react'
import { isAgentTurnActive, useAgentTurns } from '../../lib/agentTurns'
import { saveAgentEdit as defaultSaveAgentEdit } from '../../lib/agentEdits'
import { saveAgentProfile, useAgentProfile } from '../../lib/agentProfile'
import { isFlagrantErrorText } from '../../lib/flagrantErrors'
import { navbarSeatCapabilities } from '../../lib/seatCapabilities'
import { useViewportTier } from '../../lib/responsivePrefs'
import { OPEN_GENERATIONS_EVENT } from '../../components/settings/generationsEntry'
import AgentConfigSidepane from '../../components/AgentConfigSidepane'
import NavbarAgentPicker from '../../components/NavbarAgentPicker'
import NavbarSessionPicker from '../../components/NavbarSessionPicker'
import { applySeatParamPatch, headerSeatKey, seatParamsForPick } from '../../lib/seatRouting'
import { SEAT_AVATAR_GL, SEAT_AVATAR_SIZE, seatAvatarSrc } from '../../lib/seatAvatar'
import { peekConversationIdForAgent } from '../../lib/agentChat'
import { loadRailSections } from '../../lib/railSections'
import { RIG_ADDRESS_SEPARATOR, sectionRigName } from '../../lib/rigAddress'
import {
  isDedicatedChatSession,
  memberDisplayName,
  resolveAgentPillLabels,
} from './agentPillLabels'

export interface ChatHeaderProps {
  [key: string]: any
}

export const ChatHeader = function ChatHeader(props: ChatHeaderProps) {
    const { AgentAvatar, ApiSessionSwitcher, AuxActivityIndicator, CliSessionSwitcher, ComputerControlStub, OPEN_SETTINGS_EVENT, Folder, GroupAvatar, PanelLeft, Pencil, RemoteSessionSwitcher, Settings, ThemeToggle, activeChatAgentId, activeRemoteId, agentKind, allPaletteAgents = [], navigateToPaletteAgent, auxTasks, cliQuery, cliRemoteSession, configuredRemoteRows, currentCli, headerFaceAgentId, headerFaceAvatarSrc, headerGroupMembers, pillChatName = '', headerRole, headerRoleLabel, headerRigName = '', headerSeat = '', headerWorking, identityTitleRef, isApiAgent, isChiefOfStaff, isCliAgent, isExampleRole, isRemoteBackedTeam, isRemoteCapableCli, isWorking, mobileHeaderHidden, narrow, openAgentEditor, openRail, openSettingsSheet, openTeamEditor, railOpen, remoteFromUrl, remoteAgentWarning, remoteNavbarAgents = [], requestAuxCancel, roleCssClass, saveAgentEdit: saveAgentEditProp, searchParams, selectedAgent, selectedAgentName, selectedBlueprint, selectedRemote, selectedTeam, sessionFromUrl = '', setGenerationsOpen, setSearchParams, showEmptyRemoteChrome, showHeaderRole, showRemotesControl, teamChatMemberId, teamFromUrl, workspaceSubtitle, workspaceSubtitleDisplay, workspaceFolderEditable, workspaceFolderPickerSeat = workspaceFolderEditable, wsRef, navbarCapabilities = { agents: { enabled: true, reason: '' }, sessions: { enabled: true, reason: '' } }, hideUnsupportedAgentPicker = false, hideUnsupportedSessionPicker = false } = props as any
    const resolvedHeaderSeat =
      headerSeat ||
      headerSeatKey({
        teamId: teamFromUrl,
        remoteId: remoteFromUrl,
        blueprintId: selectedBlueprint,
      })
    const parentAgentCapability = navbarCapabilities?.agents ?? { enabled: true, reason: '' }
    const parentSessionCapability = navbarCapabilities?.sessions ?? { enabled: true, reason: '' }

    /* #1202 remote seats (#hermes): the ACTIVE remote row declares its own
       sessions/agents. The parent may not have resolved `selectedRemote`
       (rail pick, lagging query), so the navbar consumes the configured
       remote row's `capabilities` — the same declared predicate, sourced
       where it is authoritative for a remote seat. */
    const activeRemoteRow =
      (configuredRemoteRows || []).find((row: any) => row?.id === activeRemoteId) ?? null
    // A remote *seat* is `?remote=<id>` (the rail/search always activates one
    // that way); a remote-bound API/CLI agent is not a remote seat and keeps
    // the parent's kind-derived capability.
    const isRemoteSeat = Boolean(String(remoteFromUrl || '').trim())
    const remoteProviderName =
      String(activeRemoteRow?.title || selectedRemote?.title || activeRemoteId || '').trim() ||
      'this remote'
    const remoteDeclaredSessions =
      (activeRemoteRow?.capabilities as { sessions?: boolean } | undefined)?.sessions ??
      (selectedRemote?.capabilities as { sessions?: boolean } | undefined)?.sessions

    /* A remote seat lists the remote's OWN agents (models/bots), never the
       cross-kind palette; a remote that exposes none stays greyed with an
       honest reason — never a fabricated empty picker. */
    const remoteAgentOptions: Array<{ id: string; label: string }> = (remoteNavbarAgents || [])
      .map((row: any) => ({
        id: String(row?.id || '').trim(),
        label: String(row?.label || row?.name || row?.id || '').trim(),
      }))
      .filter((row: { id: string }) => Boolean(row.id))
    const agentCapability = isRemoteSeat
      ? remoteAgentOptions.length > 0
        ? { enabled: true, reason: '' }
        : {
            enabled: false,
            reason: remoteAgentWarning || `${remoteProviderName} lists no selectable agents`,
          }
      : parentAgentCapability
    const agentOptions = isRemoteSeat ? remoteAgentOptions : allPaletteAgents
    const sessionCapability = isRemoteSeat
      ? navbarSeatCapabilities({
          kind: 'remote',
          remoteSessions: remoteDeclaredSessions,
          providerName: remoteProviderName,
        }).sessions
      : parentSessionCapability

    /* #1202: Tier 1 keeps an unsupported picker mounted but greyed; the
       power-user toggle unmounts it instead. Supported pickers stay mounted. */
    const showAgentPicker = !(hideUnsupportedAgentPicker && !agentCapability.enabled)
    const showSessionPicker = !(hideUnsupportedSessionPicker && !sessionCapability.enabled)
    // #1244: subscribe to the shared turn registry so the header face
    // animates reactively — a bookend that arrives while this header is
    // mounted must not wait on an unrelated parent state change, and the
    // motion must survive switching seats and back. `isWorking` still covers
    // the in-seat streaming case before the first bookend lands.
    const liveTurns = useAgentTurns()
    const headerActive = Boolean(
      isWorking || headerWorking || isAgentTurnActive(activeChatAgentId, liveTurns),
    )

    // #1202 follow-up: on mobile the navbar must fit at 390px. The rail toggle
    // is dropped on the mobile tier (the left-edge swipe stays the single
    // affordance); tablet keeps it. The role badge moves under the name.
    const viewportTier = useViewportTier()
    const isMobileViewport = viewportTier === 'mobile'
    const agentPickerSelected = isRemoteSeat
      ? remoteAgentOptions.some((row) => row.id === sessionFromUrl)
        ? sessionFromUrl
        : ''
      : selectedBlueprint || selectedRemote?.id || teamFromUrl || selectedAgent?.id || ''

    // #1258: the avatar opens the dedicated agent-config sidepane.
    const [agentConfigOpen, setAgentConfigOpen] = useState(false)
    // #1233: inline rename state for the navbar identity label.
    const [nameEditing, setNameEditing] = useState(false)
    const [nameDraft, setNameDraft] = useState('')
    const [optimisticName, setOptimisticName] = useState<string | null>(null)
    const nameEditSettledRef = useRef(false)

    // Optimistic rename must never leak onto another seat (#1233).
    useEffect(() => {
      setOptimisticName(null)
      setNameEditing(false)
      nameEditSettledRef.current = false
    }, [selectedBlueprint, selectedAgentName, resolvedHeaderSeat])

    // #1354: the generations diagnostics entry moved out of the prime navbar
    // into Settings → System. The header owns `setGenerationsOpen`, so it
    // listens for the settings dispatch and opens the panel over the chat.
    useEffect(() => {
      if (typeof setGenerationsOpen !== 'function') return
      const onOpenGenerations = () => setGenerationsOpen(true)
      window.addEventListener(OPEN_GENERATIONS_EVENT, onOpenGenerations)
      return () => window.removeEventListener(OPEN_GENERATIONS_EVENT, onOpenGenerations)
    }, [setGenerationsOpen])

    // #1354: diagnostics are also a recovery surface. When the thread fails to
    // hydrate — or a turn dies with a flagrant transport/config error — surface
    // the panel so the raw model context is one glance away. One open per
    // distinct error; clearing the error re-arms it.
    const hydrateErrorSignal = props.hydrateError as string | null | undefined
    const chatMessages = (props.messages ?? []) as Array<{
      key?: string
      role?: string
      text?: string
      sendFailed?: boolean
    }>
    const surfacedErrorKey = (() => {
      if (hydrateErrorSignal) return `hydrate:${hydrateErrorSignal}`
      const failed = chatMessages.find(
        (message) =>
          message?.sendFailed ||
          (message?.role === 'status' && isFlagrantErrorText(message?.text)),
      )
      return failed ? `message:${failed.key ?? failed.text ?? ''}` : null
    })()
    const surfacedErrorRef = useRef<string | null>(null)
    useEffect(() => {
      if (typeof setGenerationsOpen !== 'function') return
      if (!surfacedErrorKey) {
        surfacedErrorRef.current = null
        return
      }
      if (surfacedErrorRef.current === surfacedErrorKey) return
      surfacedErrorRef.current = surfacedErrorKey
      setGenerationsOpen(true)
    }, [surfacedErrorKey, setGenerationsOpen])

    const storefront = useAgentProfile(selectedBlueprint)
    const displayName = optimisticName ?? selectedAgentName
    const profileTitle = storefront.title.trim()

    /* #1676: the identity is a CENTERED floating pill — the primary
       "who am I talking to / edit this agent" affordance. Its whole surface
       opens the one existing editor (`AgentConfigSidepane`, the same pane the
       avatar opened since #1258); no second editor is introduced here. A team
       seat keeps the established `openTeamEditor` route so the pill, the name
       and the pencil never disagree. */
    const pillAgentId = String(selectedBlueprint || headerFaceAgentId || '').trim()
    const pillName = String(displayName || '').trim()
    /* A seat with no resolvable agent has no pane to open, so the pill
       degrades to a documented inert placeholder instead of a dead control. */
    const pillEmpty = !pillAgentId
    const pillLabel = pillName || 'No agent selected'
    const openPillEditor = () => {
      if (pillEmpty) return
      if (teamFromUrl) {
        openTeamEditor({ teamId: teamFromUrl, teamName: selectedTeam?.name || teamFromUrl })
        return
      }
      setAgentConfigOpen(true)
    }
    // A pane that loses its target must not stay "open" behind an empty seat.
    useEffect(() => {
      if (!pillAgentId) setAgentConfigOpen(false)
    }, [pillAgentId])

    const canEditName =
      !teamFromUrl && !remoteFromUrl && Boolean(selectedBlueprint) && Boolean(selectedAgentName)
    const saveName =
      typeof saveAgentEditProp === 'function' ? saveAgentEditProp : defaultSaveAgentEdit

    const beginNameEdit = () => {
      nameEditSettledRef.current = false
      setNameDraft(displayName)
      setNameEditing(true)
    }

    const cancelNameEdit = () => {
      nameEditSettledRef.current = true
      setNameEditing(false)
    }

    const commitNameEdit = async () => {
      // Enter/Escape settle the edit first; the trailing blur must not re-save.
      if (nameEditSettledRef.current) return
      nameEditSettledRef.current = true
      const next = nameDraft.trim()
      setNameEditing(false)
      if (!next || next === displayName) return
      const previous = optimisticName ?? selectedAgentName
      setOptimisticName(next)
      try {
        await saveName(selectedBlueprint, { name: next })
        void saveAgentProfile(selectedBlueprint, { display_name: next }).catch(() => undefined)
      } catch {
        setOptimisticName(previous)
      }
    }

    // #1362: a team seat's navbar face is its membership, not one seat. Chat
    // passes the resolved member list (declared personas or live roster).
    const groupMembers: any[] = Array.isArray(headerGroupMembers) ? headerGroupMembers : []

    /* #1698 / #1706 — the pill's bottom label has ONE correct answer per
       session shape, and the matrix that decides it lives in
       `agentPillLabels` so the pill never re-derives an identity inline.

       A group chat (team roster or remote bridge) wins over everything: its
       bottom label is the SELECTED MEMBER's name (#1706 §B.5), never
       `role@rig`, because a group chat owns no role of its own (#1706 §D).
       A dedicated chat session is next, and also never `role@rig` (#1698
       §B.5). Everything else is a self / home seat whose bottom label is the
       OpenRig address `role@rig` (#1698 §A, #1706 §A). */
    const pillGroupName = teamFromUrl
      ? String(selectedTeam?.name || teamFromUrl).trim()
      : remoteFromUrl
        ? String(selectedRemote?.title || remoteFromUrl).trim()
        : ''
    const pillMemberName = teamFromUrl
      ? memberDisplayName(groupMembers, teamChatMemberId) ||
        memberDisplayName(selectedTeam?.members as Record<string, unknown>[] | undefined, teamChatMemberId)
      : remoteFromUrl
        ? memberDisplayName(selectedRemote?.agents as Record<string, unknown>[] | undefined, sessionFromUrl) ||
          memberDisplayName(remoteNavbarAgents as Record<string, unknown>[], sessionFromUrl)
        : ''
    /* The `@rig` half is a real rig, never a model or a vendor: a dynamic rig
       is a sidepane Section and a static rig is a team roster (`rigAddress`).
       `headerRigName` lets the owner pass a reactive value; the rail-section
       read is the local fallback for a home seat. */
    const pillRigName =
      String(headerRigName || '').trim() ||
      (pillGroupName ? '' : (sectionRigName(pillAgentId, loadRailSections()) ?? ''))
    /* A dedicated chat is a `?session=` that is not the agent's own stable
       conversation id (`agentChat` mints one per agent and puts it back on the
       URL for the home seat). A team / remote `?session=` names a member, not
       a conversation, so group mode is excluded here too. */
    const pillChatSession =
      !pillGroupName && isDedicatedChatSession(sessionFromUrl, peekConversationIdForAgent(pillAgentId))
    const pillLabels = resolveAgentPillLabels({
      agentName: pillName,
      roleLabel: showHeaderRole ? headerRoleLabel : '',
      roleId: showHeaderRole ? headerRole : '',
      rigName: pillRigName,
      groupName: pillGroupName,
      selectedMemberName: pillMemberName,
      chatSession: pillChatSession,
      chatName: pillChatName,
    })
    // #1706 §D.14 — a team or a chat session cannot be assigned a role in the
    // UI, so the pill must not offer one either. Mode alone decides.
    const pillShowsRole = pillLabels.mode === 'role' && Boolean(showHeaderRole)
    /* #1706 §B.4 — a group chat's TOP label is the team / remote / parent seat
       name, with the selected member underneath (#1706 §B.5). `pillLabel` stays
       agent-centric: the avatar, the rename control and the config pane all
       name the seat being edited, and only the visible title follows the
       matrix. An empty seat falls back to the documented placeholder. */
    const pillTop = pillLabels.top || pillLabel

  return (
    <>
      <header className={`os-chat-header gap-1.5 sm:gap-3 ${mobileHeaderHidden ? 'os-chat-header--hidden' : ''}`} data-mobile-hidden={mobileHeaderHidden ? 'true' : 'false'}>
        {/* #1676: the rail toggle is the header's left LEAD slot. It used to
            share a wrapper with the identity card; now that the identity is a
            floating pill under the band) the lead stays a slim left slot so
            the toggle never drifts toward the middle. */}
        <div className="os-chat-header__identity flex min-w-0 flex-1 items-center gap-2">
          {narrow && !isMobileViewport ? (
            // #1202 follow-up: the mobile navbar has no room for the rail
            // toggle; the left-edge swipe is the single mobile affordance.
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square shrink-0"
              aria-label="Open agent list"
              aria-expanded={railOpen}
              onClick={openRail}
            >
              <PanelLeft className="h-5 w-5" aria-hidden="true" />
            </button>
          ) : null}
        </div>
        {/* #1676: the foreground agent's avatar + name ride a centered floating
            pill. Clicking anywhere on the pill surface opens (or focuses) the
            one right-side edit-agent pane for this agent. Inner controls
            (rename, folder, pencil, team editor) stopPropagation, so the pill
            handler is the fallback, never a second opinion.
            #1704: the `group` marker is gone with it — the unset-folder TEXT
            row was the pill's only `group-hover:` consumer, and the icon that
            replaced it reveals from the pill's own CSS rule instead. A
            `group` context nobody uses is a lie the next reader trusts. */}
        <div
          className="os-agent-pill os-navbar-identity-card flex min-w-0 items-center"
          data-testid="selected-agent-header"
          data-pill="agent"
          data-seat={resolvedHeaderSeat || undefined}
          data-empty={pillEmpty ? 'true' : 'false'}
          data-pill-action={pillEmpty ? 'none' : 'open-agent-config'}
          /* #1706 §11 — the mode is explicit on the DOM, so "no wrong bottom
             label when switching sessions" is assertable without re-reading
             component state. */
          data-pill-mode={pillLabels.mode}
          role="group"
          aria-label={
            workspaceSubtitle
              ? `Agent identity: ${pillTop}. ${workspaceSubtitle}`
              : `Agent identity: ${pillTop}`
          }
          aria-disabled={pillEmpty || undefined}
          onClick={openPillEditor}
        >
            {/* #528/#1362: a team without a declared roster used to render nothing
                here, so the navbar showed a bare name where a single agent gets
                an avatar. It now shows the group's membership — up to three
                member faces in a circle. The button form is only used when there
                is an agent to open generations *for* — otherwise a clickable
                control would lead nowhere. */}
            <button
                type="button"
                className="os-chat-header__avatar-btn shrink-0"
                aria-label={
                  teamFromUrl && !teamChatMemberId
                    ? `${pillLabel} team`
                    : `Open ${pillLabel} configuration`
                }
                {...(teamFromUrl && !teamChatMemberId
                  ? { 'aria-hidden': true as const, tabIndex: -1, disabled: true }
                  : { 'aria-haspopup': 'dialog' as const, 'aria-expanded': agentConfigOpen })}
                data-testid={teamFromUrl ? 'header-team-avatar' : 'header-avatar-generations'}
                data-face-agent-id={teamFromUrl ? teamChatMemberId || undefined : undefined}
                onClick={(event) => {
                  event.stopPropagation()
                  // #1258: avatar opens agent configuration. The generations
                  // panel is reached through its own explicit affordance below.
                  if (teamFromUrl && !teamChatMemberId) return
                  setAgentConfigOpen(true)
                }}
                // #1236: right-click opens the agent editor — provider, model
                // and role live there; left-click opens agent configuration.
                // Teams without a member pick stay disabled above.
                onContextMenu={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                  if (teamFromUrl && !teamChatMemberId) return
                  if (selectedBlueprint) {
                    openAgentEditor({ agentId: selectedBlueprint, agentName: selectedAgentName })
                  }
                }}
              >
                {teamFromUrl && groupMembers.length > 0 ? (
                  <GroupAvatar
                    members={groupMembers}
                    size="lg"
                    className="os-chat-header__avatar"
                    label={`${pillLabel} group chat members`}
                  />
                ) : (
                  <AgentAvatar
                    src={
                      headerFaceAvatarSrc ??
                      (teamFromUrl ? undefined : seatAvatarSrc(selectedAgent))
                    }
                    agentId={headerFaceAgentId}
                    active={headerActive}
                    status={headerActive ? 'working' : 'idle'}
                    // #1692: the size tier and the WebGL decision are the seat
                    // contract (`lib/seatAvatar`), not this pane's opinion. This
                    // mount used to pass `size="lg"` + `gl`, so the same agent
                    // was 48px with a live 3D mesh here and 32px on the static
                    // SVG in the rail — one agent, two avatars.
                    size={SEAT_AVATAR_SIZE}
                    gl={SEAT_AVATAR_GL}
                    className="os-chat-header__avatar"
                    remoteKind={teamFromUrl ? undefined : selectedRemote?.kind}
                  />
                )}
              </button>
            <div className="os-navbar-identity-text min-w-0 flex-1">
              {/* #678: the fade mask is truncation-gated — the name renders in
                  full whenever it fits (tablet/desktop give it the space), and
                  the fade engages only when the text is actually clipped. */}
              <h1
                ref={identityTitleRef}
                className="os-navbar-identity-label min-w-0 w-full text-base font-semibold tracking-tight"
                data-truncated="auto"
              >
                {nameEditing ? (
                  <input
                    type="text"
                    className="os-identity-name-input block w-full bg-transparent text-base font-semibold tracking-tight outline-none"
                    aria-label={`Rename ${displayName}`}
                    data-testid="os-identity-name-input"
                    // eslint-disable-next-line jsx-a11y/no-autofocus -- click-to-edit
                    autoFocus
                    value={nameDraft}
                    onChange={(e) => setNameDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        e.stopPropagation()
                        void commitNameEdit()
                      } else if (e.key === 'Escape') {
                        e.preventDefault()
                        e.stopPropagation()
                        cancelNameEdit()
                      }
                    }}
                    onFocus={(e) => e.stopPropagation()}
                    onBlur={() => void commitNameEdit()}
                    onPaste={(e) => e.stopPropagation()}
                  />
                ) : canEditName ? (
                  <button
                    type="button"
                    className="os-identity-btn block w-full text-left"
                    aria-label={`Rename ${displayName}`}
                    data-testid="os-identity-name"
                    onClick={(e) => {
                      e.stopPropagation()
                      beginNameEdit()
                    }}
                  >
                    {pillTop}
                  </button>
                ) : pillEmpty ? (
                  // #1676: documented no-seat placeholder. A seat with no
                  // agent has nothing to rename, define, or configure, so the
                  // pill states the fact instead of rendering a dead control
                  // (or an empty pill that reads as a broken one).
                  <span
                    className="os-agent-pill__placeholder block w-full text-left"
                    data-testid="os-agent-pill-placeholder"
                  >
                    {pillLabel}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="os-identity-btn block w-full text-left"
                    aria-label={`Open ${pillTop} definition`}
                    onClick={(e) => {
                      e.stopPropagation()
                      if (teamFromUrl) {
                        openTeamEditor({
                          teamId: teamFromUrl,
                          teamName: selectedTeam?.name || teamFromUrl,
                        })
                        return
                      }
                      openSettingsSheet({
                        section: 'definition',
                        definitionKind:
                          isExampleRole(headerRole) || isChiefOfStaff(headerRole) ? 'role' : 'blueprint',
                        definitionId: selectedBlueprint,
                        blueprintId: selectedBlueprint,
                      })
                    }}
                  >
                    {pillTop}
                  </button>
                )}
              </h1>
              {/* #1202 follow-up: the role badge sits directly under the agent
                  name as a slim, single-line pill. Role colour stays on
                  `.os-agent-role-badge` (AGENTS.md); `--slim` only trims its
                  geometry. Moving it out of the horizontal row also frees the
                  width the mobile name needs. */}
              {profileTitle && !teamFromUrl && !remoteFromUrl ? (
                <span
                  className="os-navbar-identity-title text-xs text-base-content/60 truncate"
                  data-testid="os-header-profile-title"
                  title={profileTitle}
                >
                  {profileTitle}
                </span>
              ) : null}
              {/* #1698 §A / #1706 §A: on a self / home seat the bottom label is
                  the OpenRig address `role@rig`. The role half is the existing
                  badge word (`ROLE_BADGE_LABELS`) so this reuses the one role
                  vocabulary instead of minting a second one, and the `@rig`
                  half rides INSIDE the badge — role colour therefore stays on
                  `.os-agent-role-badge` and nowhere else (AGENTS.md). No rig →
                  a bare role, never a dangling `@` (#1698 §A.2). */}
              {pillShowsRole ? (
                <span
                  className={`os-agent-role-badge os-agent-role-badge--slim os-agent-pill__address shrink-0 ${roleCssClass(headerRole)}`}
                  data-role={headerRole}
                  data-testid="os-header-role-badge"
                  data-pill-address={pillLabels.address}
                  title={`Role: ${headerRoleLabel}${pillLabels.rig ? ` @${pillLabels.rig}` : ''}`}
                >
                  {headerRoleLabel}
                  {pillLabels.rig ? (
                    <span className="os-agent-pill__rig" data-testid="os-agent-pill-rig">
                      {`${RIG_ADDRESS_SEPARATOR}${pillLabels.rig}`}
                    </span>
                  ) : null}
                </span>
              ) : null}
              {/* #1706 §B.5 / §C.8: a group chat's bottom label is the selected
                  member, a dedicated chat's is this chat's name. Neither may
                  render a role (#1706 §D.14), so this row is plain text in the
                  existing subtitle slot — one row, never a second line. An
                  unresolved member renders NO row rather than a wrong one. */}
              {pillLabels.mode !== 'role' && pillLabels.bottom ? (
                <span
                  className="os-navbar-identity-subtitle os-agent-pill__bottom"
                  data-testid="os-agent-pill-bottom"
                  data-pill-mode={pillLabels.mode}
                  title={pillLabels.bottom}
                >
                  {pillLabels.bottom}
                </span>
              ) : null}
              {workspaceSubtitle ? (
                <button
                  type="button"
                  className="os-navbar-identity-subtitle"
                  data-testid="os-navbar-workspace-subtitle"
                  title={workspaceSubtitle}
                  aria-label={`Change working folder. Current: ${workspaceSubtitle}`}
                  onClick={(event) => {
                    event.stopPropagation()
                    openAgentEditor({ agentId: selectedBlueprint, agentName: selectedAgentName })
                  }}
                >
                  {workspaceSubtitleDisplay || workspaceSubtitle}
                </button>
              ) : null}
            </div>
            {/* #1704: the pill's right-aligned action cluster. The unset-folder
                affordance used to be a TEXT row inside `.os-navbar-identity-
                text`, which grew the badge a whole line on hover. It is now an
                icon button beside the pencil — same `btn btn-ghost btn-sm
                btn-square` density, same `h-4 w-4` glyph, same
                `os-navbar-edit-btn` pointer-only reveal + focus-within
                treatment, and the same click target as before (#1704 §5:
                chrome only). The accessible name rides an `sr-only` span, so
                the control has a name without painting a word. The cluster's
                own `display`/alignment/flex-shrink live in index.css
                (`.os-agent-pill__actions`) so the geometry claim has exactly
                one source.

                #1713: this control's DESTINATION is the full agent editor, and
                that editor renders a folder control only for a CLI seat (see
                `workspaceFolderPickerSeat` in ChatPage). So the offer is gated
                on the same fact, not on `workspaceFolderEditable` — which
                stays wider because it feeds the sidepane's own free-text input.
                Offering an API seat a "Select folder" button whose destination
                answers "Coming soon" was the dead end.

                #1724 §3 — the folder is the TRAILING control, so it is last in
                DOM order, not merely inside the cluster. With the folder first,
                the pencil — the only member whose wrapper carries
                `hidden sm:flex` — took the trailing slot at >=640px and left
                the folder 34px inboard, while below 640px the hidden pencil
                vacated that slot and the folder became trailing: one control
                sitting on a different edge at two widths. DOM order (rather
                than a CSS `order`, which would desync focus order from visual
                order) makes the folder trailing at every width.

                `os-agent-pill__action` is the shared hook on each tooltip
                shell, so the hover-reveal can gate the SHELL's pointer events
                as well (#1724 §1): a `pointer-events: none` button would
                otherwise hand the hit to its wrapper, which still intercepts. */}
            <div className="os-agent-pill__actions" data-testid="os-agent-pill-actions">
            {teamFromUrl ? (
              <div className="tooltip tooltip-bottom shrink-0 hidden sm:flex os-agent-pill__action" data-tip="Edit team">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-square os-navbar-edit-btn"
                  aria-label="Edit team"
                  onClick={(e) => {
                    e.stopPropagation()
                    openTeamEditor({
                      teamId: teamFromUrl,
                      teamName: selectedTeam?.name || teamFromUrl,
                    })
                  }}
                >
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ) : selectedBlueprint ? (
              <div className="tooltip tooltip-bottom shrink-0 hidden sm:flex os-agent-pill__action" data-tip="Edit agent">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-square os-navbar-edit-btn"
                  aria-label="Edit agent"
                  onClick={(e) => {
                    e.stopPropagation()
                    openAgentEditor({
                      agentId: selectedBlueprint,
                    })
                  }}
                >
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ) : null}
            {!workspaceSubtitle && workspaceFolderPickerSeat ? (
                /* #1704 §4: no `hidden sm:flex` here, unlike the pencil — a
                   narrow viewport is exactly where a touch user needs the
                   affordance, and the reveal is already pointer-gated in CSS
                   (`@media (hover: hover) and (pointer: fine)`), so opacity
                   — not display — is the only thing hover may move. */
                <div className="tooltip tooltip-bottom shrink-0 os-agent-pill__action" data-tip="Select folder">
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square os-navbar-edit-btn os-navbar-identity-subtitle--unset"
                    data-testid="os-navbar-workspace-subtitle-unset"
                    title="Select a working folder"
                    onClick={(event) => {
                      event.stopPropagation()
                      openAgentEditor({ agentId: selectedBlueprint, agentName: selectedAgentName })
                    }}
                  >
                    <Folder className="h-4 w-4" aria-hidden="true" />
                    <span className="sr-only">Select folder</span>
                  </button>
                </div>
              ) : null}
            </div>
        </div>
        {/* #773: the navbar token meter was removed — the composer badge is
            the ONE canonical meter (server-reported, out/in/max shorthand).
            Two tallies with different sources disagreed. */}
        <div className="os-chat-header__controls flex items-center shrink-0 gap-1 sm:gap-2">
          <AuxActivityIndicator
            tasks={auxTasks}
            onCancel={(taskId: string) => {
              requestAuxCancel(taskId)
              wsRef.current?.send(JSON.stringify({ type: 'cancel_auxiliary', task_id: taskId }))
            }}
          />
          {showEmptyRemoteChrome ? (
            <button
              type="button"
              className="btn btn-sm h-8 border border-base-300 bg-base-100"
              onClick={() => openSettingsSheet({ section: 'remotes', addRemote: true })}
            >
              Add remote
            </button>
          ) : null}
          {/* #1202: capability-aware navbar Agent / Session pickers. The Agent
              control lists the selectable agents to switch to (#502
              navigation); configuration stays on the identity card. The
              Session shell reuses the kind's declared switcher (CLI / API /
              Remote) as its child. A seat that cannot support a capability
              keeps the control mounted but greyed; the Settings hide-toggle
              unmounts it instead (computed above). */}
          {showAgentPicker ? (
            // #1202 follow-up: the Agent control lists the provider's
            // selectable agents to switch to — it no longer opens the current
            // agent's configuration. Configuration stays on the avatar +
            // identity label + edit combo.
            <NavbarAgentPicker
              disabled={!agentCapability.enabled}
              reason={agentCapability.reason}
              label="Select agent"
              agents={agentOptions}
              selectedId={agentPickerSelected}
              onSelect={
                isRemoteSeat
                  ? (agentId: string) => {
                      // Remote convention: the remote id names the seat and the
                      // picked remote agent rides the session/target param.
                      // #1445: drop leftover ?team= so the header cannot stay
                      // on the previous team while AnythingLLM is selected.
                      setSearchParams(
                        (prev: URLSearchParams) => {
                          const params = applySeatParamPatch(
                            prev,
                            seatParamsForPick('remote', activeRemoteId),
                          )
                          params.set('session', agentId)
                          return params
                        },
                        { replace: true },
                      )
                    }
                  : typeof navigateToPaletteAgent === 'function'
                    ? (agentId: string, kind?: string) => navigateToPaletteAgent(agentId, kind)
                    : undefined
              }
            />
          ) : null}
          {showSessionPicker ? (
            <NavbarSessionPicker
              disabled={!sessionCapability.enabled}
              reason={sessionCapability.reason}
            >
              {showRemotesControl && activeRemoteId && (!teamFromUrl || isRemoteBackedTeam) ? (
                <RemoteSessionSwitcher
                  remoteId={activeRemoteId}
                  remoteKind={selectedRemote?.kind || activeRemoteId}
                  remoteTitle={
                    configuredRemoteRows.find((row: any) => row.id === activeRemoteId)?.title ||
                    selectedRemote?.title ||
                    activeRemoteId
                  }
                  onSelectSession={(sessionId: string) => {
                    setSearchParams((prev: URLSearchParams) => {
                      const params = applySeatParamPatch(
                        prev,
                        seatParamsForPick('remote', activeRemoteId),
                      )
                      params.set('session', sessionId)
                      return params
                    }, { replace: true })
                  }}
                />
              ) : null}
              {/* #755: the legacy team members <select> is retired — the composer
                  routing picker (seatKind=team) owns member routing now. */}
              {isCliAgent && currentCli ? (
                <CliSessionSwitcher
                  agentId={selectedBlueprint}
                  cli={currentCli}
                  agentName={selectedAgentName}
                />
              ) : null}
              {isApiAgent ? (
                /* #580: the rail offers Select/New session on API seats — the
                   navbar now keeps that promise via the same declared capability
                   (seatCapabilities), not a re-derived per-surface predicate. */
                <ApiSessionSwitcher
                  agentId={selectedBlueprint}
                  agentName={selectedAgentName}
                />
              ) : null}
            </NavbarSessionPicker>
          ) : null}
          {isCliAgent &&
          currentCli &&
          isRemoteCapableCli(currentCli, cliQuery.data?.remote) &&
          cliRemoteSession.hasChoice ? (
            <label className="flex items-center gap-1 min-w-0">
              <span className="sr-only">CLI remote box</span>
              <select
                className="select select-xs select-bordered h-7 min-h-0 max-w-[12rem] font-medium"
                aria-label="CLI remote box"
                data-testid="select-cli-session-remote"
                /* #570: value always resolves to exactly one listed option — the
                   override if set, otherwise the agent's own endpoint (the empty
                   row), never a bare `''` that matches nothing. */
                value={(searchParams.get('cli_remote') ?? '').trim() || cliRemoteSession.defaultTarget}
                onChange={(event) => {
                  const next = event.target.value
                  setSearchParams(
                    (prevParams: URLSearchParams) => {
                      const nextParams = new URLSearchParams(prevParams)
                      if (next) nextParams.set('cli_remote', next)
                      else nextParams.delete('cli_remote')
                      return nextParams
                    },
                    { replace: true },
                  )
                }}
              >
                {/* #570: the default row replaces the old `Local` row. Selecting it
                    clears `?cli_remote` and returns the session to the agent's own
                    endpoint — so the default stays reachable without a synonym row. */}
                <option value="">{cliRemoteSession.defaultLabel}</option>
                {cliRemoteSession.boxes.map((box: any) => (
                  <option key={box.value} value={box.value}>
                    {box.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div
            className="flex items-center shrink-0 gap-1 sm:gap-2"
            role="toolbar"
            aria-label="Chat tools"
          >
            {/* #1354: the raw generations/context diagnostics affordance left
                the prime navbar for Settings → System (About & diagnostics).
                The header still owns the open state and listens for it. */}
            <ComputerControlStub
              agentId={activeChatAgentId}
              agentName={selectedAgentName}
              agentDetails={selectedAgent ? { id: selectedAgent.id } : null}
            />
            {/* #752: hide the dark/light toggle first on narrow viewports so the
                agent identity and search stay prominent. */}
            <ThemeToggle className="hidden sm:inline-flex" />
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square shrink-0"
              aria-label="Open settings"
              aria-haspopup="dialog"
              onClick={() => window.dispatchEvent(new CustomEvent(OPEN_SETTINGS_EVENT))}
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </header>
      {agentConfigOpen && pillAgentId ? (
        <AgentConfigSidepane
          agentId={pillAgentId}
          agentName={pillName}
          agentKind={agentKind ?? null}
          instructions={selectedAgent?.instructions ?? null}
          provider={selectedAgent?.provider ?? null}
          model={selectedAgent?.model ?? null}
          workspaceEditable={workspaceFolderEditable === true}
          onClose={() => setAgentConfigOpen(false)}
        />
      ) : null}

    </>
  )
}
