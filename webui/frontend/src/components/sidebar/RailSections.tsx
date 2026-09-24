/**
 * #856 slice H — the chat bottom dock, moved verbatim from ChatPage.tsx.
 *
 * Renders the pinned-agents grid and the collapsible section list with
 * their drag/drop plumbing. AgentSidebar owns all state and passes it down
 * as one props object.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- pass-through props during extraction

import type { RailSectionsState } from '../../lib/railSections'
import { herdrChatHref } from '../../lib/railHotkeys' // #1088: herdr pins chat like every kind
import type { DragEvent as ReactDragEvent, MouseEvent as ReactMouseEvent } from 'react'

export interface RailSectionsProps {
  [key: string]: any
}

export const RailSections = function RailSections(props: RailSectionsProps) {
    const { AgentAvatar, Link, NEEDS_APPROVAL_LABEL, RailSectionEmpty, RailSectionHeader, UNASSIGNED_SECTION_ID, activeRail, agentChatHref, agentLabel, agentRole, agents, allowListUnfavourite, allowRowDrop, allowSectionDrop, approvalWaitIds, beginRowDrag, cancelSectionRename, cliRunningIds, commitSectionRename, defaultSessionForTeam, draggingId, dropActive, dropOnSection, dropPin, dropPinReorder, dropTargetId, dropUnfavourite, editingSectionId, editingSectionName, finishDrag, isAvatarOnly, isHerdrAgent, isPinnedId, isUnassignedSection, listDropActive, loadFailed, loadingList, markStackWorking, navScrollRef, navigate, openDefinition, openPaneMenuAt, openSectionMenuAt, orderedRows, peekApprovalWait, peekCliRunning, pickOrClose, renderAgentRow, renderRemoteRow, renderTeamRow, resolveMenuKind, resolvedHiddenIds, roleBadgeLabel, roleCssClass, rowMenuHandlers, sectionBlocks, sectionDropId, setDropActive, setEditingSectionName, setListDropActive, setSectionState, setSubagentsCollapsed, stackFacesForTeam, teamChatFaceStack, teamHideId, teamSidepaneStack, teams, toggleSectionCollapsed, toggleSectionInternalOnly, unreadIds, updateCanScroll, visibleCount, visiblePins } = props as any

  return (
    <>
        <div
          className={`os-fav-grid ${dropActive ? 'os-fav-grid--active' : ''} ${
            visiblePins.length === 0 &&
            !dropActive &&
            !(draggingId && !isPinnedId(draggingId))
              ? 'os-fav-grid--bare'
              : ''
          } ${visiblePins.length === 0 ? 'os-fav-grid--empty' : ''}`}
            aria-label="Pinned agents"
            data-fav-layout="2-up"
            data-testid="agent-fav-grid"
            data-fav-empty={visiblePins.length === 0 ? 'true' : 'false'}
            onDragOver={(event) => {
              event.preventDefault()
              try {
                event.dataTransfer.dropEffect = 'move'
              } catch {
                /* synthetic events may omit dataTransfer */
              }
              setDropActive(true)
            }}
            onDragLeave={() => setDropActive(false)}
            onDrop={dropPin}
          >
            {visiblePins.length === 0 ? (
              <div
                className="os-fav-grid__hint"
                data-testid="fav-empty-hint"
              >
                {dropActive || (draggingId && !isPinnedId(draggingId)) ? 'drop' : '+'}
              </div>
            ) : null}
          {visiblePins.map((pin: any) => {
            const live = agents.find((agent: any) => agent.id === pin.id)
            const pinTeam = pin.id.startsWith('team:')
              ? teams.find((item: any) => teamHideId(item.id) === pin.id || item.id === pin.id.slice(5))
              : undefined
            const pinName = live ? agentLabel(live) : pinTeam?.name || pin.name || pin.id
            const role = live ? agentRole(live) : 'default'
            const badge = live ? roleBadgeLabel(role) : ''
            const pinActive = Boolean(activeRail && activeRail === pin.id)
            const pinUnread = unreadIds.includes(pin.id)
            const pinTeamPlan = pinTeam
              ? (() => {
                  const rawFaces = stackFacesForTeam(pinTeam)
                  const marked = markStackWorking(
                    rawFaces,
                    (id: string) => cliRunningIds.has(id) || peekCliRunning(id),
                  )
                  const busy = Boolean(
                    marked.anyWorking ||
                      cliRunningIds.has(pin.id) ||
                      peekCliRunning(pin.id),
                  )
                  // The remainder is the roster minus the one shown face — not
                  // the capped stack length, which would under-report.
                  const memberTotal = pinTeam.members ? pinTeam.members.length : marked.faces.length
                  const face = teamChatFaceStack(
                    teamSidepaneStack(marked.faces, busy).faces,
                    defaultSessionForTeam(pinTeam)?.memberId ?? '',
                  ).face
                  return {
                    ...marked,
                    anyWorking: busy,
                    remainder: memberTotal > 1 ? memberTotal - 1 : 0,
                    face,
                  }
                })()
              : null
            const pinWorkerBusy = Boolean(
              pinTeamPlan?.anyWorking ||
                cliRunningIds.has(pin.id) ||
                peekCliRunning(pin.id),
            )
            const pinNeedsApproval = Boolean(
              approvalWaitIds.has(pin.id) ||
                peekApprovalWait(pin.id) ||
                Boolean(
                  pinTeamPlan?.face &&
                    (approvalWaitIds.has(pinTeamPlan.face.id) ||
                      peekApprovalWait(pinTeamPlan.face.id)),
                ),
            )
            const pinClass = `os-fav-tile group/tile ${
              draggingId === pin.id ? 'os-fav-tile--dragging' : ''
            } ${dropTargetId === pin.id ? 'os-fav-tile--drop' : ''} ${
              pinActive ? 'os-fav-tile--active' : ''
            } ${pinWorkerBusy ? 'os-fav-tile--working-stack' : ''}`
            const pinFace = (
              <>
                {pinNeedsApproval ? (
                  <span
                    className="os-fav-tile__attention"
                    data-testid="pin-needs-approval"
                  >
                    {NEEDS_APPROVAL_LABEL}
                  </span>
                ) : null}
                {pinUnread && (
                  <span
                    className="os-rail-unread-dot absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-sky-500 z-10 group-hover/tile:hidden"
                    aria-label="Unread"
                    data-testid="rail-unread-dot"
                  />
                )}
                {badge ? (
                  <span
                    className={`os-fav-tile__badge os-agent-role-badge ${roleCssClass(role)}`}
                    data-role={role}
                    data-definition-id={pin.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open ${role} settings`}
                    onClick={(event) => {
                      event.preventDefault()
                      event.stopPropagation()
                      openDefinition('role', pin.id, { blueprintId: pin.id })
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        event.stopPropagation()
                        openDefinition('role', pin.id, { blueprintId: pin.id })
                      }
                    }}
                  >
                    {badge}
                  </span>
                ) : null}
                {/* #438: one full-size face + a corner `+N` overlay.
                    #689 (supersedes #523's graduated stack): exactly ONE
                    avatar + the +N counter on pinned team seats — the second
                    face read as a second agent at pin size. The face is
                    still the most recently active member (#523 ordering),
                    just no longer stacked. */}
                <span
                  className="os-fav-tile__face relative inline-flex shrink-0 items-center justify-center"
                  data-testid="pin-team-face"
                  data-remainder={String(pinTeamPlan?.remainder ?? 0)}
                >
                  <AgentAvatar
                    src={pinTeamPlan?.face?.avatarSrc || pinTeamPlan?.face?.src || live?.avatar_path}
                    agentId={pinTeamPlan?.face?.agentId || pinTeamPlan?.face?.id || pin.id}
                    alt={pinTeamPlan?.face?.name || pinName}
                    size="lg"
                    className="os-fav-tile__avatar"
                    status={pinWorkerBusy ? 'working' : 'idle'}
                    active={pinWorkerBusy}
                  />
                  {pinTeamPlan && pinTeamPlan.remainder > 0 ? (
                    <span
                      className="os-fav-tile__remainder"
                      data-testid="pin-team-remainder"
                      aria-hidden="true"
                    >
                      +{pinTeamPlan.remainder}
                    </span>
                  ) : null}
                </span>
                <span className="os-fav-tile__name">{pinName}</span>
              </>
            )
            const pinKind = resolveMenuKind(pin.id)
            const pinEntityId = pin.id.replace(/^(team|remote):/, '')
            const pinHandlers = {
              draggable: true as const,
              onDragStart: (event: ReactDragEvent) => beginRowDrag(event, pin),
              onDragEnd: finishDrag,
              onDragOver: (event: ReactDragEvent) => allowRowDrop(event, pin.id),
              onDrop: (event: ReactDragEvent) => dropPinReorder(event, pin.id),
              onClick: (event: ReactMouseEvent<HTMLElement>) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
                  pickOrClose?.()
                  event.currentTarget.blur()
                  return
                }
                event.preventDefault()
                navigate(agentChatHref(pin.id))
                pickOrClose?.()
                event.currentTarget.blur()
              },
              onMouseLeave: (event: ReactMouseEvent<HTMLElement>) => {
                event.currentTarget.blur()
              },
              ...rowMenuHandlers(
                pin.id,
                pinName,
                resolvedHiddenIds.includes(pin.id),
                pinKind,
                undefined,
                pinEntityId,
              ),
            }
            if (isHerdrAgent(pin)) {
              // #543/#1088: herdr pins chat like every other kind — the
              // session IS the conversation target, not the members page.
              return (
                <a
                  key={pin.id}
                  href={herdrChatHref(pin.id)}
                  className={pinClass}
                  title={pinName}
                  aria-label={pinName}
                  data-agent-id={pin.id}
                  {...pinHandlers}
                >
                  {pinFace}
                </a>
              )
            }
            return (
              <Link
                key={pin.id}
                to={agentChatHref(pin.id)}
                className={pinClass}
                title={pinName}
                aria-label={pinName}
                data-agent-id={pin.id}
                {...pinHandlers}
              >
                {pinFace}
              </Link>
            )
          })}
          </div>


        <div className="relative min-h-0 flex-1 flex flex-col">
          <nav
            ref={navScrollRef}
            onScroll={updateCanScroll}
            className={`os-rail-scroller min-h-0 flex-1 overflow-y-auto px-2 ${
              /* #729: the 4rem bottom pad exists to clear the drag ghost; it
                 is dead space when idle — active rows get the height back. */
              draggingId ? 'pb-16' : 'pb-4'
            }`}
            data-testid="rail-agent-scroller"
            aria-label="Agent list"
            onContextMenu={(event) => {
              const target = event.target as HTMLElement
              if (target.closest('[data-rail-id], .os-rail-section, .os-pin')) return
              event.preventDefault()
              openPaneMenuAt(event.clientX, event.clientY)
            }}
          >
            {/* #685: a disabled provider kind is COMPLETELY absent — no notice,
                no badge, no "enable in Settings" copy anywhere outside Settings.
                The old #594 rail notice advertised the withheld surfaces and was
                exactly the informative noise this ticket bans. Product modes are
                still discoverable where they belong: Settings → Rail. */}
            <div
              className={`os-agent-list ${listDropActive ? 'os-agent-list--unfav' : ''} ${
                /* #729: the 3rem floor is a drop affordance, not an idle
                   requirement — reserve it only while a drag can use it. */
                draggingId ? 'os-agent-list--dragging' : ''
              }`}
              data-testid="agent-list-drop"
              data-unfavourite-target="true"
              onDragOver={allowListUnfavourite}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node)) {
                  setListDropActive(false)
                }
              }}
              onDrop={dropUnfavourite}
            >
              {loadingList ? (
                <p className="px-2 py-3 text-sm text-base-content/45">Loading agents…</p>
              ) : loadFailed ? (
                <p className="px-2 py-3 text-sm text-base-content/45">Could not load agents.</p>
              ) : visibleCount === 0 ? (
                <p className="px-2 py-3 text-sm text-base-content/45">
                  {isPinnedId(draggingId) ? 'drop here to unfavourite' : 'No agents yet.'}
                </p>
              ) : (
                <ul className="os-rail-sections space-y-1">
                  {sectionBlocks.map((block: any) => {
                    // #688: an emptied Unassigned section is not a permanent
                    // empty block. It hides until it has rows again — or until
                    // a drag starts, when it reappears as a drop target (its
                    // drop handler below is live the whole time). "Move to →
                    // Unassigned" in the context menu works either way.
                    if (
                      isUnassignedSection(block.id) &&
                      block.rows.length === 0 &&
                      !draggingId
                    ) {
                      return null
                    }
                    const showMembers = isAvatarOnly || !block.collapsed
                    return (
                      <li
                        key={block.id}
                        className={`os-rail-section ${
                          sectionDropId === block.id ? 'os-rail-section--drop' : ''
                        }`}
                        data-testid="rail-section"
                        data-section-id={block.id}
                        data-section-custom={block.custom ? 'true' : 'false'}
                        data-collapsed={block.collapsed ? 'true' : 'false'}
                        data-internal-only={block.internalOnly ? 'true' : 'false'}
                        /* #564: the whole section block accepts a drop, not just
                           its header and its empty hint. Without this, a drop
                           on the padding or the gap between rows bubbled to the
                           list container's `dropUnfavourite`, which unpins but
                           never assigns — so a dragged pin landed in
                           Unassigned however carefully you aimed. */
                        onDragOver={(event) => allowSectionDrop(event, block.id)}
                        onDrop={(event) => dropOnSection(event, block.id)}
                      >
                        {isAvatarOnly ? null : (
                          <RailSectionHeader
                            sectionId={block.id}
                            name={block.name}
                            count={block.rows.length}
                            collapsed={block.collapsed}
                            custom={block.custom}
                            internalOnly={Boolean(block.internalOnly)}
                            editing={editingSectionId === block.id}
                            editValue={editingSectionId === block.id ? editingSectionName : block.name}
                            dropActive={sectionDropId === block.id}
                            onToggle={() => {
                              if (block.id === 'subagents') {
                                setSubagentsCollapsed((current: RailSectionsState) => !current)
                              } else {
                                setSectionState((current: RailSectionsState) => toggleSectionCollapsed(current, block.id))
                              }
                            }}
                            onToggleTalkLock={
                              block.custom
                                ? () =>
                                    setSectionState((current: RailSectionsState) =>
                                      toggleSectionInternalOnly(current, block.id),
                                    )
                                : undefined
                            }
                            onContextMenu={
                              block.custom
                                ? ({ clientX, clientY }: ReactMouseEvent<HTMLElement>) =>
                                    openSectionMenuAt(block.id, block.name, clientX, clientY)
                                : undefined
                            }
                            onEditChange={setEditingSectionName}
                            onEditCommit={commitSectionRename}
                            onEditCancel={cancelSectionRename}
                            onDragOver={(event: ReactDragEvent) => allowSectionDrop(event, block.id)}
                            onDrop={(event: ReactDragEvent) => dropOnSection(event, block.id)}
                          />
                        )}
                        {showMembers ? (
                          <ul className="space-y-0.5">
                            {block.rows.length === 0 && !isAvatarOnly ? (
                              <li>
                                <RailSectionEmpty
                                  dropActive={sectionDropId === block.id}
                                  onDragOver={(event: ReactDragEvent) => allowSectionDrop(event, block.id)}
                                  onDrop={(event: ReactDragEvent) => dropOnSection(event, block.id)}
                                  unassigned={block.id === UNASSIGNED_SECTION_ID}
                                />
                              </li>
                            ) : (
                              block.rows.map((row: any) => {
                                // #1088: Alt+1..9 slot badges are gone —
                                // sequential Alt+↑/↓ needs no per-row slot.
                                const index = orderedRows.findIndex((item: any) => item.id === row.id)
                                if (row.kind === 'team') {
                                  return renderTeamRow(row.team, false, [], index)
                                }
                                return (
                                  <li key={row.id} data-rail-id={row.id} data-rail-index={index}>
                                    {row.kind === 'remote'
                                      ? renderRemoteRow(row.remote, false)
                                      : renderAgentRow(row.agent, false)}
                                  </li>
                                )
                              })
                            )}
                          </ul>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </nav>
        </div>

    </>
  )
}
