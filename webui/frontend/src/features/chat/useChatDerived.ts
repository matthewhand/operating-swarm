/**
 * #856 slice 19 — routing-picker inputs & derived chat metrics, verbatim
 * from ChatPage.
 *
 * selectedModelId (#207 default-LLM tip gating), contextMax resolution,
 * sendNowHint (#561), token/message tallies for the meter, composer
 * placeholder, status label, and the #681/#711 composer picker sources
 * (deferred CLI session fetch, per-remote stage-2 rows, #789 herdr panes).
 * Query payloads and setters stay page-owned.
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { buildComposerProviders } from '../../lib/composerSources'
import type { ComposerSources } from '../../lib/composerSources'
import { nextDrainableQueuedSend, type QueuedSendRow } from '../../lib/chatQueue'
import { estimateTokensInContext } from '../../lib/chatMeter'
import { resolveContextMaxFromProfiles } from '../../lib/chatMeter'
import { shouldShowDefaultLlmTip } from '../../lib/defaultLlmTip'
import { isHerdrKind } from '../../lib/remotes'
import { parseTeamRosters } from '../../lib/teamRosters'
import { workingLabel } from '../../lib/chatBubble'
import { fetchCliSessions } from '../../lib/cliSessions'
import type { ChatMessage } from './chatMessages'

export interface UseChatDerivedOptions {
  searchParams: URLSearchParams
  isCliAgent: boolean
  currentCli: string
  currentCliModel: string
  persistedDropdown: Partial<Record<'remote' | 'cli' | 'api' | 'blueprint' | 'model' | 'effort', string>>
  llmProfilesQuery: { data?: { profiles?: { id: string; name?: string }[]; default_llm_profile?: string; default_llm_ready?: boolean } | undefined }
  llmDefaultProfile: string | undefined
  input: string
  queuedRows: QueuedSendRow[]
  queuedHoldIds: string[]
  isApiAgent: boolean
  defaultLlmTipDismissed: boolean
  messages: ChatMessage[]
  replyTarget: unknown
  selectedAgentName: string
  status: string
  authRejected: boolean
  selectedBlueprint: string | null
  discoveredClis: string[]
  cliModelsQuery: { data?: { models?: string[] } | undefined }
  configuredRemoteRows: { id: string; title?: string; kind?: string }[]
  activeRemoteId: string
  remoteNavbarAgents: { id: string; label?: string }[]
  remoteAgentsQuery: { isPending: boolean }
  herdrAgentsQuery: { data?: { data?: { id: number | string; name: string }[] } | undefined; isPending: boolean }
  teamsQuery: { data?: unknown }
  blueprints: { id: string; name: string; description?: string }[]
  contextMaxRef: { current: number | null }
}

export function useChatDerived(opts: UseChatDerivedOptions) {
  const {
    searchParams,
    isCliAgent,
    currentCli,
    currentCliModel,
    persistedDropdown,
    llmProfilesQuery,
    llmDefaultProfile,
    input,
    queuedRows,
    queuedHoldIds,
    isApiAgent,
    defaultLlmTipDismissed,
    messages,
    replyTarget,
    selectedAgentName,
    status,
    authRejected,
    selectedBlueprint,
    discoveredClis,
    cliModelsQuery,
    configuredRemoteRows,
    activeRemoteId,
    remoteNavbarAgents,
    remoteAgentsQuery,
    herdrAgentsQuery,
    teamsQuery,
    blueprints,
    contextMaxRef,
  } = opts

  const selectedModelId = (
    (searchParams.get('model') ?? '').trim() ||
    (isCliAgent ? currentCliModel : (persistedDropdown.model || persistedDropdown.api || ''))
  ).trim()
  const contextMax = resolveContextMaxFromProfiles(
    llmProfilesQuery.data?.profiles,
    selectedModelId || llmDefaultProfile,
  )
  // #207: API seats on the default profile get a setup tip when the default
  // LLM is not usable. Explicit model/profile overrides (pinned seats) and
  // CLI/remote/team seats are exempt by design.
  // #561: with a queued send waiting, Enter on the empty composer sends that
  // row now (the interrupt path — see handleComposerKeyDown). Say so on the
  // input-hover hint instead of the default "Enter to send".
  const sendNowHint =
    !input.trim() && nextDrainableQueuedSend(queuedRows, queuedHoldIds) !== null
  const showDefaultLlmTip = shouldShowDefaultLlmTip({
    isApiAgent,
    hasExplicitModelOverride: Boolean(selectedModelId),
    defaultLlmReady: llmProfilesQuery.data?.default_llm_ready,
    dismissed: defaultLlmTipDismissed,
  })
  contextMaxRef.current = contextMax
  const [tokenDiagOpen, setTokenDiagOpen] = useState(false)

  const userTexts = useMemo(
    () => messages.filter((m) => m.role === 'user').map((m) => m.text),
    [messages],
  )
  const assistantTexts = useMemo(
    () => messages.filter((m) => m.role === 'assistant').map((m) => m.text),
    [messages],
  )
  const inputTokens = useMemo(() => estimateTokensInContext(userTexts), [userTexts])
  const outputTokens = useMemo(() => estimateTokensInContext(assistantTexts), [assistantTexts])
  const toolCallsCount = useMemo(
    () => messages.reduce((sum, m) => sum + (m.tools?.length ?? 0), 0),
    [messages],
  )
  const userMessageCount = useMemo(
    () => messages.filter((m) => m.role === 'user').length,
    [messages],
  )
  const assistantMessageCount = useMemo(
    () => messages.filter((m) => m.role === 'assistant').length,
    [messages],
  )
  const composerPlaceholder = replyTarget ? 'Reply…' : 'Message …'
  const workingTip = workingLabel(selectedAgentName)

  const statusLabel = useMemo(() => {
    if (status === 'open') return ''
    if (status === 'connecting') return 'Connecting…'
    if (authRejected) return 'Unavailable — sign in required'
    if (status === 'failed') return 'Unavailable — websocket unreachable'
    return 'Disconnected'
  }, [authRejected, status])

  // #681/#682/#683 — the two-stage composer picker's inputs, from the same
  // live payloads the seat controls already render. A provider with no data
  // (e.g. a CLI with no resumable sessions) still lists; its stage 2 simply
  // offers the default row only.
  // #711: resumable CLI sessions for the picker's stage 2 — fetched when the
  // picker opens (deferred-fetch doctrine, same as the History switcher),
  // never on mount.
  const [composerSessionsOpen, setComposerSessionsOpen] = useState(false)
  const composerSessionsQuery = useQuery({
    queryKey: ['cli-sessions-composer', currentCli],
    queryFn: () => fetchCliSessions(selectedBlueprint ?? '', currentCli),
    enabled: isCliAgent && Boolean(currentCli) && composerSessionsOpen,
    retry: false,
  })
  const composerCliSessions = useMemo<ReadonlyArray<{ id: string; label: string }>>(() => {
    const list = composerSessionsQuery.data
    if (!list) return []
    const out: Array<{ id: string; label: string }> = []
    const seen = new Set<string>()
    for (const s of [...(list.sessions ?? []), ...(list.recent ?? [])]) {
      if (!s?.id || seen.has(s.id)) continue
      seen.add(s.id)
      out.push({ id: s.id, label: (s.title || s.snippet || s.id).trim() || s.id })
    }
    return out
  }, [composerSessionsQuery.data])

  const composerSources: ComposerSources = useMemo(
    () => ({
      api: {
        profiles: (llmProfilesQuery.data?.profiles ?? []).map((p) => ({
          id: p.id,
          label: p.name || p.id,
        })),
        defaultProfileId: llmProfilesQuery.data?.default_llm_profile || undefined,
      },
      // #682: the probed model list belongs to the *current* CLI (the probe
      // is per-CLI); other CLIs list without models until selected.
      // #711: the current CLI also offers its resumable sessions. While that
      // payload is in flight the CLI is marked optionsPending — #803
      // auto-pick must not resolve on a partial list.
      clis: discoveredClis.map((name) => ({
        name,
        ...(name === currentCli && composerCliSessions.length
          ? { sessions: composerCliSessions }
          : {}),
        ...(name === currentCli && cliModelsQuery.data?.models?.length
          ? { models: cliModelsQuery.data.models }
          : {}),
        ...(name === currentCli && composerSessionsOpen && composerSessionsQuery.isPending
          ? { optionsPending: true }
          : {}),
      })),
      // Remote agent lists exist only for the *active* remote (the operate
      // `list` query is per-remote); others offer their default row only.
      // While the list is in flight the row is optionsPending (#803).
      remotes: configuredRemoteRows.map((r) => ({
        id: r.id,
        label: r.title || r.id,
        ...(r.id === activeRemoteId
          ? {
              agents: remoteNavbarAgents.map((row) => ({
                id: row.id,
                label: row.label || row.id,
              })),
              optionsPending: remoteAgentsQuery.isPending,
            }
          : {}),
        // #789: a herdr remote's configured panes (GET /v1/herdr-agents/)
        // are its stage-2 options — the composer picker replaces the #543
        // navbar popup, and picking a pane lands in ?session=<name>.
        ...(isHerdrKind(r.kind) || isHerdrKind(r.id)
          ? {
              herdrAgents: (herdrAgentsQuery.data?.data ?? []).map((a) => ({
                id: a.id,
                name: a.name,
              })),
              ...(herdrAgentsQuery.isPending ? { optionsPending: true } : {}),
            }
          : {}),
      })),
      teams: parseTeamRosters(teamsQuery.data ?? []).map((t) => ({
        id: t.id,
        label: t.name || t.id,
        members: (t.members ?? []).map((m) => ({ id: m.id, label: m.name || m.id })),
      })),
      blueprints: blueprints.map((b) => ({
        id: b.id,
        label: b.name || b.id,
        description: b.description,
      })),
    }),
    [
      llmProfilesQuery.data,
      discoveredClis,
      configuredRemoteRows,
      teamsQuery.data,
      blueprints,
      activeRemoteId,
      remoteNavbarAgents,
      currentCli,
      cliModelsQuery.data,
      composerCliSessions,
      herdrAgentsQuery.data,
      herdrAgentsQuery.isPending,
    ],
  )
  const composerProviders = useMemo(
    () => buildComposerProviders(composerSources),
    [composerSources],
  )
  // #856 slice F: one props object for the extracted message list —
  // tsc names every closure identifier the render body touches.

  return {
    selectedModelId, contextMax, sendNowHint, showDefaultLlmTip, tokenDiagOpen, setTokenDiagOpen,
    inputTokens, outputTokens, toolCallsCount, userMessageCount, assistantMessageCount,
    composerPlaceholder, workingTip, statusLabel, composerSessionsOpen, setComposerSessionsOpen,
    composerCliSessions, composerSources, composerProviders,
  }
}
