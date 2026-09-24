/**
 * #856 slice H — the chat bottom dock, moved verbatim from ChatPage.tsx.
 *
 * Renders the chat page's top header: agent identity/routing, session
 * pickers, computer-control stub, theme toggle, and settings entry.
 * ChatPage owns all state and passes it down as one props object.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- pass-through props during extraction

export interface ChatHeaderProps {
  [key: string]: any
}

export const ChatHeader = function ChatHeader(props: ChatHeaderProps) {
    const { AgentAvatar, ApiSessionSwitcher, AuxActivityIndicator, CliSessionSwitcher, ComputerControlStub, OPEN_SETTINGS_EVENT, PanelLeft, Pencil, PersonaRoster, RemoteSessionSwitcher, Settings, ThemeToggle, activeChatAgentId, activeRemoteId, auxTasks, cliQuery, cliRemoteSession, configuredRemoteRows, currentCli, generationsOpen, headerFaceAgentId, headerFaceAvatarSrc, headerRole, headerRoleLabel, identityTitleRef, isApiAgent, isChiefOfStaff, isCliAgent, isExampleRole, isRemoteCapableCli, isWorking, mobileHeaderHidden, narrow, openAgentEditor, openRail, openSettingsSheet, openTeamEditor, railOpen, requestAuxCancel, roleCssClass, searchParams, selectedAgent, selectedAgentName, selectedBlueprint, selectedRemote, selectedTeam, setGenerationsOpen, setSearchParams, showEmptyRemoteChrome, showHeaderRole, showRemotesControl, teamChatMemberId, teamDeclaredRoster, teamFromUrl, workspaceSubtitle, wsRef } = props as any

  return (
    <>
      <header className={`os-chat-header gap-1.5 sm:gap-3 ${mobileHeaderHidden ? 'os-chat-header--hidden' : ''}`} data-mobile-hidden={mobileHeaderHidden ? 'true' : 'false'}>
        <div className="os-chat-header__identity flex min-w-0 flex-1 items-center gap-2 group">
          {narrow ? (
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
          <div
            className="os-navbar-identity-card flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1 -my-1 border border-transparent transition-colors hover:bg-base-200/50 hover:border-base-content/10"
            data-testid="selected-agent-header"
            role="group"
            aria-label={
              workspaceSubtitle
                ? `Agent identity: ${selectedAgentName}. ${workspaceSubtitle}`
                : `Agent identity: ${selectedAgentName}`
            }

          >
            {teamFromUrl && teamDeclaredRoster ? (
              <PersonaRoster
                roster={teamDeclaredRoster}
                groupId={teamFromUrl}
                label={`${selectedAgentName} declared members`}
                size="md"
              />
            ) : (
              // #528: a team without a declared roster used to render nothing
              // here, so the navbar showed a bare name where a single agent gets
              // an avatar. It now shows the team's chat face. The button form is
              // only used when there is an agent to open generations *for* —
              // otherwise a clickable control would lead nowhere.
              <button
                type="button"
                className="os-chat-header__avatar-btn shrink-0"
                aria-label={
                  teamFromUrl && !teamChatMemberId
                    ? `${selectedAgentName} team`
                    : `Show ${selectedAgentName} generations`
                }
                {...(teamFromUrl && !teamChatMemberId
                  ? { 'aria-hidden': true as const, tabIndex: -1, disabled: true }
                  : { 'aria-haspopup': 'dialog' as const, 'aria-expanded': generationsOpen })}
                data-testid={teamFromUrl ? 'header-team-avatar' : 'header-avatar-generations'}
                data-face-agent-id={teamFromUrl ? teamChatMemberId || undefined : undefined}
                onClick={(event) => {
                  event.stopPropagation()
                  setGenerationsOpen((prev: boolean) => !prev)
                }}
              >
                <AgentAvatar
                  src={headerFaceAvatarSrc ?? (teamFromUrl ? undefined : selectedAgent?.avatar_path)}
                  agentId={headerFaceAgentId}
                  active={isWorking}
                  status={isWorking ? 'working' : 'idle'}
                  size="lg"
                  gl
                  className="os-chat-header__avatar"
                  remoteKind={teamFromUrl ? undefined : selectedRemote?.kind}
                />
              </button>
            )}
            <div className="os-navbar-identity-text min-w-0 flex-1">
              {/* #678: the fade mask is truncation-gated — the name renders in
                  full whenever it fits (tablet/desktop give it the space), and
                  the fade engages only when the text is actually clipped. */}
              <h1
                ref={identityTitleRef}
                className="os-navbar-identity-label min-w-0 flex-1 text-base font-semibold tracking-tight"
                data-truncated="auto"
              >
                <button
                  type="button"
                  className="os-identity-btn block w-full text-left"
                  aria-label={`Open ${selectedAgentName} definition`}
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
                  {selectedAgentName}
                </button>
              </h1>
              {workspaceSubtitle ? (
                <p
                  className="os-navbar-identity-subtitle"
                  data-testid="os-navbar-workspace-subtitle"
                  title={workspaceSubtitle}
                >
                  {workspaceSubtitle}
                </p>
              ) : null}
            </div>
            {showHeaderRole ? (
              <span
                className={`os-agent-role-badge shrink-0 ${roleCssClass(headerRole)}`}
                data-role={headerRole}
                data-testid="os-header-role-badge"
                title={`Role: ${headerRoleLabel}`}
              >
                {headerRoleLabel}
              </span>
            ) : null}
            {teamFromUrl ? (
              <div className="tooltip tooltip-bottom shrink-0 hidden sm:flex" data-tip="Edit team">
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
              <div className="tooltip tooltip-bottom shrink-0 hidden sm:flex" data-tip="Edit agent">
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
          {showRemotesControl && activeRemoteId ? (
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
                  const params = new URLSearchParams(prev)
                  params.set('remote', activeRemoteId)
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
            <ComputerControlStub
              agentId={activeChatAgentId}
              agentName={selectedAgentName}
              agentDetails={
                selectedAgent
                  ? {
                      id: selectedAgent.id,
                      name: selectedAgent.name,
                      kind: (selectedAgent as { kind?: string | null }).kind ?? null,
                      instructions: (selectedAgent as { instructions?: string | null }).instructions ?? null,
                      provider: (selectedAgent as { provider?: string | null }).provider ?? null,
                      model: (selectedAgent as { model?: string | null }).model ?? null,
                    }
                  : null
              }
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

    </>
  )
}
