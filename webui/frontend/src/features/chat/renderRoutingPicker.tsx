/**
 * #856 slice K — the per-seat-kind routing picker factory, moved verbatim
 * from ChatPage (#836 unified footer, #755 team routing, REQ-904/#502 remote
 * decision point all preserved). ChatPage passes the closure names as props
 * and renders `renderRoutingPickerImpl(...)`.
 */
import type * as React from 'react'

type Props = Record<string, any>

export function renderRoutingPickerImpl(props: Props): React.ReactNode {
  const {
    ADD_REMOTE_VALUE,
    ALL_MEMBERS_TARGET,
    MANAGE_CLI_VALUE,
    MANAGE_TEAMS_HREF,
    MANAGE_TEAMS_VALUE,
    NavbarRoutingPicker,
    allPaletteAgents,
    apiModelOptionsFromProfiles,
    applyApiRoutingChange,
    applyCliRoutingChange,
    applyRemoteRoutingChange,
    applyTeamMemberSessionParam,
    availableCliModels,
    bindingAgentId,
    cliModelWarning,
    cliModelsQuery,
    composerOptionsForProvider,
    composerProviders,
    composerShowProvider,
    composerSources,
    configuredRemoteRows,
    currentCli,
    currentCliModel,
    discoveredClis,
    isApiAgent,
    isCliAgent,
    isRemoteAction,
    llmProfilesQuery,
    memberOptionLabel,
    memberTarget,
    navigateToPaletteAgent,
    ombSelectedBotId,
    openSettingsSheet,
    persistAgentDropdownChoice,
    persistedDropdown,
    reconfigureProviderForSeat,
    recordDropdownChange,
    remoteAgentWarning,
    remoteAgentsQuery,
    remoteFromUrl,
    remoteKinds,
    remoteNavbarAgents,
    remoteOptionLabel,
    remoteSelectPlaceholder,
    remotesCatalog,
    resumeComposerSession,
    saveAgentRemoteBinding,
    selectedModelId,
    selectedRemoteId,
    selectedTeam,
    sessionFromUrl,
    setComposerSessionsOpen,
    setMemberTarget,
    setSearchParams,
    setSelectedRemoteId,
    showEmptyRemoteChrome,
    showRemotesControl,
    teamFromUrl,
  } = props



  if (!composerShowProvider) return null
  if (showRemotesControl && !showEmptyRemoteChrome) {
    return (
      <NavbarRoutingPicker
        seatKind="remote"
        aria-label="Remote"
        placeholder={remoteSelectPlaceholder(configuredRemoteRows.length, selectedRemoteId)}
        agents={configuredRemoteRows.map((remote: any) => ({
          id: remote.id,
          label: remoteOptionLabel(remote, remoteKinds(remotesCatalog)),
          kind: 'remote' as const,
        }))}
        allAgents={allPaletteAgents}
        onNavigateAgent={navigateToPaletteAgent}
        onProviderReconfigure={reconfigureProviderForSeat}
        selectedAgent={selectedRemoteId}
        models={remoteNavbarAgents.map((row: any) => row.id)}
        modelOptions={remoteNavbarAgents}
        twoStage={{
          providers: composerProviders,
          getProviderOptions: (provider: string) =>
            composerOptionsForProvider(composerSources, provider),
        }}
        selectedModel={ombSelectedBotId || sessionFromUrl}
        modelWarning={remoteAgentWarning}
        modelWarningAction={
          remoteAgentsQuery.isSuccess && remoteAgentsQuery.data?.ok === false
            ? isRemoteAction(remoteAgentsQuery.data.action)
              ? remoteAgentsQuery.data.action
              : null
            : null
        }
        footerAction={{
          id: ADD_REMOTE_VALUE,
          // #836: the picker is a cross-provider omnibus — the footer always
          // names the unified Providers hub, not the active seat's section.
          label: 'Manage providers',
          onSelect: () => openSettingsSheet({ section: 'providers' }),
        }}
        onChange={(next: any) => {
          const nextId = next.agent
          setSelectedRemoteId(nextId)
          // REQ-904 / #502: one decision point for both axes. A provider
          // pick on a named agent is inert on the route; only an identity
          // pick (viewing a remote seat) may navigate or reset the session.
          const decision = applyRemoteRoutingChange({
            next,
            bindingAgentId,
            remoteFromUrl,
            configured: configuredRemoteRows,
          })
          if (decision.binding !== undefined) {
            saveAgentRemoteBinding(bindingAgentId, decision.binding)
            persistAgentDropdownChoice(bindingAgentId, {
              remote: decision.binding?.id ?? '',
            })
          }
          setSearchParams((prev: URLSearchParams) => {
            const params = new URLSearchParams(prev)
            if (decision.setRemote) params.set('remote', decision.setRemote)
            if (decision.setSession) params.set('session', decision.setSession)
            else if (decision.deleteSession) params.delete('session')
            return params
          })
        }}
      />
    )
  }
  if (teamFromUrl) {
    // #755: team member routing is the same composer picker every other
    // seat uses — the legacy navbar <select> is retired. All members is
    // the first row (its id is the send-target sentinel 'all'); Manage
    // Team is the footer action, which never writes a session (#331).
    const members = selectedTeam?.members ?? []
    return (
      <NavbarRoutingPicker
        seatKind="team"
        aria-label="Team members"
        agents={[
          { id: ALL_MEMBERS_TARGET, label: 'All members', kind: 'team' as const },
          ...members.map((member: any) => ({
            id: member.id,
            label: memberOptionLabel(member),
            kind: 'team' as const,
          })),
        ]}
        selectedAgent={memberTarget || ALL_MEMBERS_TARGET}
        models={[]}
        selectedModel=""
        placeholder="Team"
        footerAction={{
          id: MANAGE_TEAMS_VALUE,
          label: 'Manage teams',
          onSelect: () => {
            window.location.assign(
              teamFromUrl
                ? `${MANAGE_TEAMS_HREF}#${encodeURIComponent(teamFromUrl)}`
                : MANAGE_TEAMS_HREF,
            )
          },
        }}
        onChange={(next: any) => {
          const value = next.agent
          const prev = memberTarget
          const prevMember = members.find((m: any) => m.id === prev)
          const nextMember = members.find((m: any) => m.id === value)
          const fromLabel = prev === ALL_MEMBERS_TARGET ? 'All members' : memberOptionLabel(prevMember || { id: prev, name: prev })
          const toLabel = value === ALL_MEMBERS_TARGET ? 'All members' : memberOptionLabel(nextMember || { id: value, name: value })
          setMemberTarget(value)
          setSearchParams(
            (prevParams: any) => applyTeamMemberSessionParam(prevParams, teamFromUrl, value),
            { replace: true },
          )
          recordDropdownChange('team', fromLabel, toLabel)
        }}
      />
    )
  }
  if (isCliAgent) {
    return (
      <NavbarRoutingPicker
        seatKind="cli"
        aria-label="CLI"
        agents={discoveredClis.map((cli: any) => ({ id: cli, label: cli, kind: 'cli' as const }))}
        selectedAgent={currentCli}
        models={availableCliModels}
        selectedModel={currentCliModel}
        modelWarning={cliModelWarning}
        preferredEffort={persistedDropdown.effort}
        allAgents={allPaletteAgents}
        onNavigateAgent={navigateToPaletteAgent}
        onProviderReconfigure={reconfigureProviderForSeat}
        loading={isCliAgent && (cliModelsQuery.isFetching || cliModelsQuery.isLoading)}
        onTwoStageOpen={() => setComposerSessionsOpen(true)}
        twoStage={{
          providers: composerProviders,
          getProviderOptions: (provider: any) =>
            composerOptionsForProvider(composerSources, provider),
          onResumeSession: resumeComposerSession,
        }}
        footerAction={{
          id: MANAGE_CLI_VALUE,
          // #836: unified cross-provider footer (see remote branch above).
          label: 'Manage providers',
          onSelect: () => openSettingsSheet({ section: 'providers' }),
        }}
        onChange={applyCliRoutingChange}
      />
    )
  }
  if (isApiAgent) {
    /* #108, #584: API seats route through LLM profiles, not host CLIs. */
    return (
      <NavbarRoutingPicker
        seatKind="api"
        aria-label="API"
        agents={apiModelOptionsFromProfiles(
          llmProfilesQuery.data?.profiles,
          llmProfilesQuery.data?.default_llm_profile
            ? [llmProfilesQuery.data.default_llm_profile]
            : [],
        ).map((opt: any) => ({ id: opt.id, label: opt.label, kind: 'api' as const }))}
        allAgents={allPaletteAgents}
        onNavigateAgent={navigateToPaletteAgent}
        selectedAgent={
          selectedModelId || llmProfilesQuery.data?.default_llm_profile || ''
        }
        models={[]}
        selectedModel=""
        defaultAgent={llmProfilesQuery.data?.default_llm_profile || ''}
        twoStage={{
          providers: composerProviders,
          getProviderOptions: (provider: any) =>
            composerOptionsForProvider(composerSources, provider),
        }}
        footerAction={{
          id: '__manage_api__',
          // #836: unified cross-provider footer (see remote branch above).
          label: 'Manage providers',
          onSelect: () => openSettingsSheet({ section: 'providers' }),
        }}
        onChange={applyApiRoutingChange}
      />
    )
  }
  return null

}
