import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, FoldVertical, Layers, Mic, PanelLeft, Pencil, Plus, Reply, Settings, Users } from 'lucide-react'
import AgentAvatar from '../components/AgentAvatar'
import { ConfirmModal, TOAST_KIND_WS_DISCONNECT, useToast } from '../components/DaisyUI'
import ThemeToggle from '../components/ThemeToggle'
import { OPEN_SETTINGS_EVENT, openSettingsSheet } from '../components/SettingsSheet'
import RateLimitStatusLine from '../components/RateLimitStatusLine'
import { isRateLimitWait, type RateLimitWait } from '../lib/providerRateLimits'
import { OPEN_TEAM_COMPOSER_EVENT } from '../components/TeamComposer'
import {
  AGENT_DROPDOWNS_CHANGED_EVENT,
  AGENT_SETTINGS_CHANGED_EVENT,
  fetchAgentSettings,
  loadAgentDropdownChoice,
  loadLocalNewChatPerTask,
  loadLocalUseSuggestions,
  openAgentEditor,
  type AgentSettingsChangedDetail,
} from '../lib/agentSettings'
import { openTeamEditor } from '../components/TeamEditor'
import PersonaRoster from '../components/PersonaRoster'
import { declaredRosterForTeam } from '../lib/declaredRoster'
import { fetchUserPrefs, persistAgentDropdownChoice } from '../lib/userPrefs'
import {
  DEFAULT_CONTEXT_STRATEGY,
  DEFAULT_CULL_TRIGGER_PCT,
  START_CONTEXT_FROM_HERE_LABEL,
  START_CONTEXT_FROM_HERE_TOOLTIP,
  overFullWarningCopy,
  parseContextStrategy,
  parseCullTriggerPct,
  type ContextMeta,
  type ContextStrategy,
} from '../lib/contextCull'
import { persistableMessages, putAgentChatSession } from '../lib/agentChatSessions'
import { useRailChrome } from '../components/RailChrome'
import { ComputerControlStub } from '../components/ComputerControlStub'
import { NavbarRoutingPicker, type RoutingPathChange } from '../components/NavbarRoutingPicker'
import { ChatMessageBubble } from '../components/ChatMessageBubble'
import { SkillPopup } from '../components/SkillPopup'
import ReadAloudButton from '../components/ReadAloudButton'
import { SystemPreloadPill } from '../components/SystemPreloadPill'
import { CompactSummaryCard } from '../components/CompactSummaryCard'
import { ComposerSlashPopup } from '../components/ComposerSlashPopup'
import {
  type SlashItem,
  buildSlashCatalog,
  filterSlashItems,
  getRecentSlashIds,
  recordRecentSlashId,
} from '../lib/slashMenu'
import {
  EMPTY_SPEECH,
  fetchConfigOptions,
  fetchSkills,
  type SkillRecord,
  fetchBlueprints,
  fetchCliAgents,
  fetchCliModels,
  fetchLlmProfiles,
  fetchRemotes,
  fetchSpeechSettings,
} from '../lib/api'
import {
  appendTranscript,
  listenSystemStt,
  recordMicrophoneAudio,
  resolveSttPath,
  sttUnavailableMessage,
  transcribeCustomBlob,
  type SpeechPath,
} from '../lib/speechRuntime'
import { SPEECH_QUERY_KEY, describeSpeechPath, parseSpeechSettings } from '../lib/speechSettings'
import {
  AGENT_CONVERSATION_EVENT,
  agentIdFromBlueprint,
  appendAgentMessage,
  compactAgentThread,
  conversationIdForAgent,
  conversationIdForTask,
  DEFAULT_AGENT_ID,
  fetchAgentThread,
  startContextFromHere,
  patchAgentMessage,
  peekConversationIdForAgent,
  setConversationIdForAgent,
  type ConversationSummary,
} from '../lib/agentChat'
import { canEditAgentMessages, classifyAgentKind, type AgentKind } from '../lib/agentKind'
import {
  composerInsetCustomProperty,
  isPinnedToTranscriptBottom,
  measureComposerDockInset,
  scrollTranscriptToBottom,
} from '../lib/composerInset'
import {
  buildDisplayItems,
  contextTextsForMeter,
  rawOffsetForMessage,
  summariesById,
} from '../lib/chatCompact'
import { turnIndexFromDisplay } from '../lib/transcriptReconstruct'
import {
  buildChatWsEditFrame,
  buildChatWsFrame,
  buildChatWsUrl,
  buildToolDecisionFrame,
  parseChatWsMessage,
  type ChatWsEvent,
} from '../lib/chatWs'
import { ToolCallPopup } from '../components/ToolCallPopup'
import { PrOpenedCard } from '../components/PrOpenedCard'
import { TeammateTaskCard } from '../components/TeammateTaskCard'
import { SuggestionChips } from '../components/SuggestionChips'
import {
  openerChatSearch,
  parsePrOpened,
  type PrOpenedEvent,
  type PrOpenedOpener,
} from '../lib/prOpened'
import { parseTeammateTask, type TeammateTaskEvent } from '../lib/teammateTask'
import { TokenDiagnosticsModal } from '../components/TokenDiagnosticsModal'
import {
  isToolAlwaysAllowed,
  rememberAlwaysAllow,
  upsertToolCall,
  type ToolCallState,
} from '../lib/safety'
import { notifyGenerationComplete } from '../lib/railOrder'
import {
  CLI_TERMINATED_EVENT,
  CLI_TERMINATED_STATUS,
  cliTerminatedFromEvent,
  notifyCliRunState,
} from '../lib/cliRunState'
import { publishExpectedSpaVersion } from '../lib/spaHello'
import { maybeNotifyAgentTurn } from '../lib/agentNotifications'
import {
  ALL_MEMBERS_TARGET,
  MANAGE_TEAMS_HREF,
  MANAGE_TEAMS_VALUE,
  applyTeamMemberSessionParam,
  fetchTeamRosters,
  parseTeamRosters,
  memberOptionLabel,
  teamHideId,
  teamThreadId,
} from '../lib/teamRosters'
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId } from '../lib/remotesCatalog'
import {
  ADD_REMOTE_VALUE,
  configuredRemotes,
  remoteKinds,
  remoteOptionLabel,
  remoteSelectPlaceholder,
} from '../lib/remotes'
import { enabledToolsParam } from '../lib/chatPluginTools'
import { publishCurrentChatScope } from '../lib/chatScope'
import {
  AGENT_REMOTE_BINDINGS_CHANGED_EVENT,
  isRemoteKindAgent,
  loadAgentRemoteBinding,
  remotesListForSelect,
  resolveBoundRemoteId,
  saveAgentRemoteBinding,
} from '../lib/agentRemote'
import {
  publishChatConnection,
  type ChatConnectionStatus,
} from '../lib/chatConnection'
import {
  reconnectBackoffMs,
  shouldAutoReconnect,
  WS_AUTH_REQUIRED_CODE,
} from '../lib/chatReconnect'
import {
  CONTEXT_METER_TOKENS,
  estimateTokensInContext,
  formatMeterLabel,
  resolveContextMaxFromProfiles,
} from '../lib/chatMeter'
import { formatGapLabel, parseCreatedAtMs } from '../lib/chatTime'
import { workingLabel } from '../lib/chatBubble'
import { isExperimentalEnabled } from '../experimental/flags'
import { ChatMessageActions } from '../experimental/ChatMessageActions'
import { RoleAgentTip } from '../components/RoleAgentTip'
import {
  hydrateRoleAgentTipDismissed,
  persistRoleAgentTipDismissed,
  isRoleAgentTipDismissed,
  shouldShowRoleAgentTip,
} from '../lib/roleAgentTip'
import { agentRole, exampleRoleAgents, isChiefOfStaff, isExampleRole } from '../lib/agentRoles'
import { assignedBlueprintId, AGENT_EDITS_CHANGED_EVENT, editedAgentLabel, loadAgentEdit, loadInferenceList } from '../lib/agentEdits'
import { buildSkillParams, parseComposerSkillNames } from '../lib/skills'
import { chatFolderParams } from '../lib/agentFolder'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import { nextInferenceIndex, serializeInferenceList } from '../lib/inferenceList'
import {
  agentLabel,
  defaultBlueprintId,
  isSupportAgent,
  SUPPORT_AGENT_ID,
  supportTurnExtras,
} from '../lib/supportAgent'
import {
  asTranscriptRole,
  formatDropdownStatus,
  isStatusRole,
  shouldRecordDropdownChange,
  type DropdownKind,
} from '../lib/chatStatus'
import { insertCliSessionNotice } from '../lib/chatTranscript'
import { fetchAgentSuggestions, shouldShowSuggestionChips } from '../lib/suggestions'
import {
  isSupportJourneyConsumer,
  supportJourneyKickstart,
} from '../lib/supportJourney'
import {
  missingSessionNotice,
  restoreKindForAgent,
  restoredSessionNotice,
  switchedSessionNotice,
} from '../lib/sessionRestore'
import { CLI_SESSION_SWITCHED_EVENT } from '../lib/cliSessions'
import { CLI_SESSION_HOPPED_EVENT, hopCliSession } from '../lib/cliSessionHop'
import {
  SUGGESTION_CHIP_EVENT,
  generationIsInFlight,
  nextDrainableQueuedSend,
  queuedPaneMaxHeightPx,
  suggestionChipText,
  useQueuedSends,
} from '../lib/chatQueue'
import { QueuedSendPane } from '../components/QueuedSendPane'
import {
  discoverChatClis,
  honestChatCliModels,
  isCliAgentContext,
  isCliBlueprintId,
  preferredChatCli,
  MANAGE_CLI_VALUE,
  MANAGE_CLI_HREF,
} from '../lib/cliAgentContext'
import { isHiddenRoutingLabel } from '../lib/routingPath'

/** EXPERIMENTAL flags are read once per module load; see experimental/flags.ts. */
const SHOW_MESSAGE_ACTIONS = isExperimentalEnabled('chat_message_actions')

type ConnectionStatus = ChatConnectionStatus

interface ChatMessage {
  /** Stable key; for assistant messages this is the server-issued container id. */
  key: string
  role: 'user' | 'assistant' | 'status' | 'system'
  text: string
  /** True while the assistant message is still streaming. */
  streaming: boolean
  tools?: ToolCallState[]
  edited?: boolean
  /** REQ-71 chrome — structured PR-opened tool result, not markdown. */
  prOpened?: PrOpenedEvent
  /** REQ-84 chrome — team task whose worker is a configured remote. */
  teammateTask?: TeammateTaskEvent
  /** REQ-104 — expandable archive of the previous swarm thread. */
  kind?: 'prior_history'
  /** Persist/reload timestamp (ISO). Status/info chrome shows this. */
  ts?: string
  /** REQ-88 — provider queue wait; click opens that provider's rate-limit fields. */
  rateLimit?: RateLimitWait
}

function chatMessageFromThreadRow(
  message: {
    role: string
    content: string
    edited?: boolean
    kind?: string
    ts?: string
    rate_limit?: RateLimitWait
  },
  index: number,
): ChatMessage {
  const prOpened = parsePrOpened(message.content) ?? undefined
  const teammateTask = parseTeammateTask(message.content) ?? undefined
  const prior = message.kind === 'prior_history'
  return {
    key: `hist-${index}-${message.role}`,
    role: prior ? 'system' : asTranscriptRole(message.role),
    text: prOpened || teammateTask ? '' : message.content,
    streaming: false,
    edited: message.edited === true,
    prOpened,
    teammateTask,
    kind: prior ? 'prior_history' : undefined,
    ts: message.ts,
    rateLimit: isRateLimitWait(message.rate_limit) ? message.rate_limit : undefined,
  }
}

/** Post-login return path for the Django session gate (rooted, same-origin). */
export function chatLoginNext(searchParams: URLSearchParams): string {
  const qs = searchParams.toString()
  return qs ? `/chat?${qs}` : '/chat'
}

export function chatLoginHref(searchParams: URLSearchParams): string {
  return `/accounts/login/?next=${encodeURIComponent(chatLoginNext(searchParams))}`
}

export {
  estimateTokensInContext,
  formatElapsed,
  formatTokenCount,
} from '../lib/chatMeter'

interface ReplyTarget {
  key: string
  role: string
  speaker: string
  text: string
}

interface MessageContextMenuState {
  x: number
  y: number
  message: ChatMessage
}

const ChatPage = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToast, dismissByKind } = useToast()
  const { narrow, railOpen, openRail } = useRailChrome()
  const teamFromUrl = searchParams.get('team') ?? ''
  const remoteFromUrl = searchParams.get('remote') ?? ''
  const sessionFromUrl = searchParams.get('session') ?? ''
  const selectedBlueprint = teamFromUrl || remoteFromUrl
    ? ''
    : defaultBlueprintId(searchParams.get('blueprint'))
  const activeChatAgentId = useMemo(
    () =>
      teamFromUrl
        ? teamHideId(teamFromUrl)
        : remoteFromUrl
        ? remoteHideId(remoteFromUrl)
        : selectedBlueprint,
    [teamFromUrl, remoteFromUrl, selectedBlueprint],
  )
  const [newChatPerTask, setNewChatPerTask] = useState(() =>
    teamFromUrl || remoteFromUrl ? false : loadLocalNewChatPerTask(defaultBlueprintId(searchParams.get('blueprint'))),
  )
  const [useSuggestions, setUseSuggestions] = useState(() =>
    teamFromUrl ? false : loadLocalUseSuggestions(defaultBlueprintId(searchParams.get('blueprint'))),
  )
  const [suggestionChips, setSuggestionChips] = useState<string[]>([])
  const [threadReady, setThreadReady] = useState(false)
  /** Honest hydrate miss — not a blank new chat (REQ-171A-4 / #604). */
  const [hydrateError, setHydrateError] = useState<string | null>(null)

  const [threads, setThreads] = useState<Record<string, ChatMessage[]>>({})
  const [restoreNotice, setRestoreNotice] = useState<string | null>(null)
  const [summariesByThread, setSummariesByThread] = useState<
    Record<string, ConversationSummary[]>
  >({})
  const [contextStrategy, setContextStrategy] = useState<ContextStrategy>(DEFAULT_CONTEXT_STRATEGY)
  const [cullTriggerPct, setCullTriggerPct] = useState(DEFAULT_CULL_TRIGGER_PCT)
  const [contextMeta, setContextMeta] = useState<ContextMeta>({ start_offset: 0, last_event: null })
  const [startFromHereWarning, setStartFromHereWarning] = useState<{
    message: ChatMessage
    copy: string
    startOffset: number
  } | null>(null)
  const [input, setInput] = useState('')
  const [sttListening, setSttListening] = useState(false)
  const [sttPathUsed, setSttPathUsed] = useState<SpeechPath | null>(null)
  const sttStopRef = useRef<(() => void) | null>(null)
  const [replyTarget, setReplyTarget] = useState<ReplyTarget | null>(null)
  const [contextMenu, setContextMenu] = useState<MessageContextMenuState | null>(null)
  /** REQ-213: view-only hide. Raw transcript / summary tree on disk stay. */
  const [hiddenSummaryIds, setHiddenSummaryIds] = useState<number[]>([])
  const [hiddenMessageKeys, setHiddenMessageKeys] = useState<string[]>([])
  const [slashDismissed, setSlashDismissed] = useState(false)
  const [slashSelectedIndex, setSlashSelectedIndex] = useState(0)
  const [recentSlashIds, setRecentSlashIds] = useState<string[]>(() => getRecentSlashIds())
  const [roleTipDismissed, setRoleTipDismissed] = useState(isRoleAgentTipDismissed)
  const [dynamicSkills, setDynamicSkills] = useState<{ name: string; description?: string }[]>([])
  const [skillCatalog, setSkillCatalog] = useState<SkillRecord[]>([])
  const [openSkillName, setOpenSkillName] = useState<string | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [memberTarget, setMemberTarget] = useState(ALL_MEMBERS_TARGET)
  const [connectAttempt, setConnectAttempt] = useState(0)
  const [authRejected, setAuthRejected] = useState(false)
  const [plusOpen, setPlusOpen] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [agentKind, setAgentKind] = useState<AgentKind>(() =>
    classifyAgentKind(searchParams.get('remote') ? `remote:${searchParams.get('remote')}` : searchParams.get('blueprint')),
  )
  const [messagesEditable, setMessagesEditable] = useState(() =>
    canEditAgentMessages(searchParams.get('blueprint')) &&
    !searchParams.get('team') &&
    !searchParams.get('remote'),
  )
  const [, setEditsTick] = useState(0)
  const [dropdownTick, setDropdownTick] = useState(0)
  const [selectedRemoteId, setSelectedRemoteId] = useState('')
  const [conversationId, setConversationId] = useState(() =>
    teamFromUrl
      ? teamThreadId(teamFromUrl)
      : remoteFromUrl
        ? `remote-${remoteFromUrl}${sessionFromUrl ? `-${sessionFromUrl}` : ''}`
        : sessionFromUrl ||
          peekConversationIdForAgent(defaultBlueprintId(searchParams.get('blueprint'))) ||
          conversationIdForTask(agentIdFromBlueprint(selectedBlueprint), {
            newChatPerTask: loadLocalNewChatPerTask(
              defaultBlueprintId(searchParams.get('blueprint')),
            ),
          }),
  )
  const threadKey = teamFromUrl
    ? teamThreadId(teamFromUrl)
    : remoteFromUrl
      ? `remote-${remoteFromUrl}${sessionFromUrl ? `-${sessionFromUrl}` : ''}`
      : sessionFromUrl
        ? `${selectedBlueprint}::${sessionFromUrl}`
        : newChatPerTask
          ? conversationId
          : selectedBlueprint

  const messages = useMemo(() => threads[threadKey] ?? [], [threads, threadKey])
  const hasRateLimitWait = messages.some((row) => row.rateLimit)
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (!hasRateLimitWait) return
    setNowMs(Date.now())
    const id = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [hasRateLimitWait])
  const threadsRef = useRef(threads)
  threadsRef.current = threads
  const summaries = useMemo(
    () => summariesByThread[threadKey] ?? [],
    [summariesByThread, threadKey],
  )
  const displayItems = useMemo(
    () => buildDisplayItems(messages, summaries),
    [messages, summaries],
  )
  const summaryMap = useMemo(() => summariesById(summaries), [summaries])

  const wsRef = useRef<WebSocket | null>(null)
  const emptyRemoteOpenedForRef = useRef('')
  const conversationIdRef = useRef(conversationId)
  conversationIdRef.current = conversationId
  const contextMaxRef = useRef<number | null>(null)
  const listEndRef = useRef<HTMLDivElement | null>(null)
  const scrollBoxRef = useRef<HTMLDivElement | null>(null)
  const bottomDockRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const plusRef = useRef<HTMLDivElement | null>(null)
  const composerWrapRef = useRef<HTMLDivElement | null>(null)
  const [composerInsetPx, setComposerInsetPx] = useState(0)
  const [transcriptHeightPx, setTranscriptHeightPx] = useState(0)
  const [queuedHoldIds, setQueuedHoldIds] = useState<string[]>([])
  const [awaitingAssistant, setAwaitingAssistant] = useState(false)
  const drainLockRef = useRef(false)
  const queued = useQueuedSends(conversationId)
  /** Monotonic counter for collision-free user-echo keys. */
  const userKeyCounterRef = useRef(0)
  const prevStatusRef = useRef<ConnectionStatus>('connecting')
  /** Consecutive auto-reconnect attempts since last successful open. */
  const backoffAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)
  const lastUserTextRef = useRef('')
  /** Last hydrated agent or team thread; used to detect switch vs remount. */
  const lastHydratedAgentRef = useRef<string | null>(null)
  const previewSyncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // REQ-177: Sync active thread messages to localStorage so rail preview snippets update live.
  // Throttled to 250ms during streaming, and immediate on turn completion / user send.
  useEffect(() => {
    if (!activeChatAgentId) return
    const threadMessages = threads[threadKey]
    if (threadMessages === undefined) return
    const isStreaming = threadMessages.some((m) => m.streaming)
    const sync = () => {
      const persistable = persistableMessages(threadMessages)
      putAgentChatSession(activeChatAgentId, {
        conversationId,
        messages: persistable,
      })
    }

    if (isStreaming) {
      if (!previewSyncTimerRef.current) {
        previewSyncTimerRef.current = setTimeout(() => {
          previewSyncTimerRef.current = null
          sync()
        }, 250)
      }
    } else {
      if (previewSyncTimerRef.current) {
        clearTimeout(previewSyncTimerRef.current)
        previewSyncTimerRef.current = null
      }
      sync()
    }
    return () => {
      if (previewSyncTimerRef.current) {
        clearTimeout(previewSyncTimerRef.current)
        previewSyncTimerRef.current = null
      }
    }
  }, [activeChatAgentId, conversationId, threadKey, threads])

  useEffect(() => {
    publishCurrentChatScope(conversationId)
  }, [conversationId])

  useEffect(() => {
    setReplyTarget(null)
    setContextMenu(null)
    setHiddenSummaryIds([])
    setHiddenMessageKeys([])
  }, [threadKey])

  useEffect(() => {
    if (!contextMenu) return
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        setContextMenu(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [contextMenu])

  const handleBubbleContextMenu = useCallback(
    (event: React.MouseEvent<HTMLDivElement>, message: ChatMessage) => {
      if (message.streaming) return
      if (typeof window !== 'undefined' && window.getSelection && !window.getSelection()?.isCollapsed) {
        return
      }
      event.preventDefault()
      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        message,
      })
    },
    [],
  )

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
  })
  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
  })
  const teamsQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
  })
  const remotesQuery = useQuery({
    queryKey: ['configured-remotes'],
    queryFn: fetchConfiguredRemotes,
    retry: 1,
  })
  const llmProfilesQuery = useQuery({
    queryKey: ['llm-profiles'],
    queryFn: fetchLlmProfiles,
    retry: 1,
  })
  const remotesListQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    retry: 1,
  })
  const speechQuery = useQuery({
    queryKey: SPEECH_QUERY_KEY,
    queryFn: () => fetchSpeechSettings(false),
    staleTime: 30_000,
    retry: 1,
  })
  const blueprints = exampleRoleAgents(blueprintsQuery.data?.data ?? [])
  const cliAgents = cliQuery.data?.rail ?? []
  const teams = parseTeamRosters(teamsQuery.data ?? [])
  const remotes = remotesQuery.data ?? []
  const selectedTeam = teams.find((team) => team.id === teamFromUrl) ?? null
  const teamDeclaredRoster = selectedTeam
    ? declaredRosterForTeam(selectedTeam, blueprintsQuery.data?.data ?? [])
    : null
  const selectedRemote = remotes.find((remote) => remote.id === remoteFromUrl) ?? null
  const selectedRemoteSession = selectedRemote?.agents.find((agent) => agent.id === sessionFromUrl)
  const selectedTeamSession = selectedTeam?.members.find((member) => member.id === sessionFromUrl)
  const selectedCli = cliAgents.find((row) => row.id === selectedBlueprint)
  const selectedAgent = blueprints.find((bp) => bp.id === selectedBlueprint)
  const runtimeBlueprint = teamFromUrl ? '' : assignedBlueprintId(selectedBlueprint)
  const fallbackAgentName =
    selectedAgent?.name ||
    selectedCli?.name ||
    (selectedBlueprint === SUPPORT_AGENT_ID ? 'Support' : selectedBlueprint)
  const selectedAgentName = teamFromUrl
    ? selectedTeamSession?.name || selectedTeam?.name || teamFromUrl
    : remoteFromUrl
          ? selectedRemoteSession?.name || selectedRemote?.title || remoteFromUrl
          : editedAgentLabel({
              id: selectedBlueprint,
              name: fallbackAgentName,
            })
  const showRoleTip = shouldShowRoleAgentTip({
    teamId: teamFromUrl,
    remoteId: remoteFromUrl,
    dismissed: roleTipDismissed,
    agent: {
      id: selectedBlueprint,
      name: selectedAgentName,
      role: selectedAgent?.role,
    },
  })
  const dismissRoleTip = useCallback(() => {
    void persistRoleAgentTipDismissed()
    setRoleTipDismissed(true)
  }, [])
  useEffect(() => {
    if (!showRoleTip) return
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (document.querySelector('[role="dialog"], .modal-open, [data-testid="search-palette"]')) {
        return
      }
      e.preventDefault()
      dismissRoleTip()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showRoleTip, dismissRoleTip])
  const notifyCtxRef = useRef({
    agentId: activeChatAgentId,
    agentName: selectedAgentName,
  })
  notifyCtxRef.current = {
    agentId: activeChatAgentId,
    agentName: remoteFromUrl
      ? remoteDisplayName(selectedRemote || { id: remoteFromUrl, title: selectedAgentName })
      : selectedAgentName,
  }
  const signInHref = chatLoginHref(searchParams)

  const isRemoteBackedTeam = Boolean(
    selectedTeam && (
      (selectedTeam as { kind?: string }).kind === 'remote' ||
      Boolean((selectedTeam as { remote?: string }).remote) ||
      selectedTeam.members?.some(
        (m) =>
          m.kind === 'remote' ||
          (m as { role?: string }).role === 'remote' ||
          Boolean((m as { remote?: string }).remote),
      )
    ),
  )

  const isRemoteAgent = isRemoteKindAgent({
    remoteFromUrl,
    agentKind,
    blueprintId: selectedBlueprint,
    selectedKind: (selectedAgent as { kind?: string } | undefined)?.kind,
    agentType: (selectedAgent as { agent_type?: string })?.agent_type,
    remote: (selectedAgent as { remote?: string })?.remote,
    tags: (selectedAgent as { tags?: string[] })?.tags,
  }) || Boolean(selectedRemote)

  const showRemotesControl = isRemoteAgent || isRemoteBackedTeam
  const bindingAgentId = remoteFromUrl || (showRemotesControl ? selectedBlueprint : '')
  const persistedRemote = bindingAgentId ? loadAgentRemoteBinding(bindingAgentId) : null
  const remotesCatalog = remotesListForSelect(
    remotesListQuery.data,
    remotes,
    remoteFromUrl
      ? {
          id: remoteFromUrl,
          kind: selectedRemote?.kind || persistedRemote?.kind || remoteFromUrl,
          title: selectedRemote?.title,
        }
      : persistedRemote,
  )
  const configuredRemoteRows = configuredRemotes(remotesCatalog)
  const remotesCatalogReady = !remotesListQuery.isPending && !remotesQuery.isPending
  const showEmptyRemoteChrome =
    showRemotesControl && remotesCatalogReady && configuredRemoteRows.length === 0

  const isCliAgent = Boolean(
    !teamFromUrl &&
      !remoteFromUrl &&
      !isRemoteBackedTeam &&
      !isRemoteAgent &&
      (selectedCli ||
        agentKind === 'cli' ||
        isCliBlueprintId(selectedBlueprint) ||
        isCliAgentContext({
          blueprintId: selectedBlueprint,
          searchParams,
        })),
  )

  const isApiAgent = Boolean(
    !teamFromUrl &&
      !remoteFromUrl &&
      !isRemoteBackedTeam &&
      !isRemoteAgent &&
      !isCliAgent,
  )

  const dropdownAgentId = teamFromUrl
    ? `team-${teamFromUrl}`
    : remoteFromUrl || selectedBlueprint || DEFAULT_AGENT_ID
  const persistedDropdown = useMemo(
    () => loadAgentDropdownChoice(dropdownAgentId),
    [dropdownAgentId, dropdownTick],
  )

  const discoveredClis = useMemo(
    () =>
      discoverChatClis(
        cliQuery.data,
        searchParams.get('cli') || persistedDropdown.cli || selectedCli?.cli,
      ),
    [cliQuery.data, searchParams, persistedDropdown.cli, selectedCli],
  )
  const currentCli = useMemo(() => {
    const fromParam = (searchParams.get('cli') ?? '').trim()
    if (fromParam) return fromParam
    if (persistedDropdown.cli) return persistedDropdown.cli
    if (selectedCli?.cli) return selectedCli.cli
    return preferredChatCli(discoveredClis, '')
  }, [searchParams, persistedDropdown.cli, selectedCli, discoveredClis])

  const cliModelsQuery = useQuery({
    queryKey: ['cli-models', currentCli],
    queryFn: () => fetchCliModels(currentCli),
    enabled: Boolean(isCliAgent && currentCli),
    retry: 1,
  })
  const cliModelProbe = useMemo(
    () => honestChatCliModels(cliModelsQuery.data),
    [cliModelsQuery.data],
  )
  const availableCliModels = useMemo(() => {
    const merged = [...cliModelProbe.models]
    const saved = (persistedDropdown.model || '').trim()
    if (saved && !isHiddenRoutingLabel(saved) && !merged.includes(saved)) {
      merged.push(saved)
    }
    return merged
  }, [cliModelProbe.models, persistedDropdown.model])
  const cliModelWarning = useMemo(() => {
    if (availableCliModels.length > 0) return cliModelProbe.warning
    if (cliModelProbe.warning) return cliModelProbe.warning
    if (cliModelsQuery.isError) return 'Model probe failed'
    if (cliModelsQuery.isFetched && currentCli) return 'No models discovered'
    return null
  }, [
    availableCliModels.length,
    cliModelProbe.warning,
    cliModelsQuery.isError,
    cliModelsQuery.isFetched,
    currentCli,
  ])

  const currentCliModel = useMemo(() => {
    const fromParam = (searchParams.get('model') ?? '').trim()
    if (fromParam && availableCliModels.includes(fromParam)) return fromParam
    const saved = (persistedDropdown.model || '').trim()
    if (saved && availableCliModels.includes(saved)) return saved
    return availableCliModels[0] || ''
  }, [searchParams, availableCliModels, persistedDropdown.model])
  const recordDropdownChange = useCallback(
    (kind: DropdownKind, fromLabel: string, toLabel: string) => {
      if (!shouldRecordDropdownChange(fromLabel, toLabel)) return
      const statusText = formatDropdownStatus(kind, fromLabel, toLabel)
      const statusMsg: ChatMessage = {
        key: `status-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: 'status',
        text: statusText,
        streaming: false,
        ts: new Date().toISOString(),
      }
      setThreads((prev) => ({
        ...prev,
        [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
      }))
      const agent = teamFromUrl
        ? `team-${teamFromUrl}`
        : remoteFromUrl
          ? `remote-${remoteFromUrl}`
          : selectedBlueprint || DEFAULT_AGENT_ID
      void appendAgentMessage(
        agent,
        { role: 'status', content: statusText },
        conversationIdRef.current || undefined,
      ).catch(() => {})
    },
    [threadKey, teamFromUrl, remoteFromUrl, selectedBlueprint],
  )

  const applyCliRoutingChange = useCallback(
    (next: RoutingPathChange) => {
      if (next.changed === 'agent') {
        persistAgentDropdownChoice(dropdownAgentId, {
          cli: next.agent,
          ...(next.model ? { model: next.model } : {}),
          effort: next.effort || '',
        })
        setSearchParams(
          (prevParams) => {
            const nextParams = new URLSearchParams(prevParams)
            nextParams.set('cli', next.agent)
            if (next.model) nextParams.set('model', next.model)
            else nextParams.delete('model')
            return nextParams
          },
          { replace: true },
        )
        recordDropdownChange('cli', next.previous.agent, next.agent)
        const fromCli = (next.previous.agent || '').trim()
        const toCli = (next.agent || '').trim()
        if (fromCli && toCli && fromCli !== toCli) {
          const agent = teamFromUrl
            ? `team-${teamFromUrl}`
            : remoteFromUrl
              ? `remote-${remoteFromUrl}`
              : selectedBlueprint || DEFAULT_AGENT_ID
          void hopCliSession({
            agentId: agent,
            fromCli,
            toCli,
            conversationId: conversationIdRef.current || undefined,
            kind: 'cli',
          })
            .then((hop) => {
              if (!hop?.status?.trim()) return
              const statusMsg: ChatMessage = {
                key: `hop-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                role: 'status',
                text: hop.status,
                streaming: false,
                ts: new Date().toISOString(),
              }
              setThreads((prev) => ({
                ...prev,
                [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
              }))
              void appendAgentMessage(
                agent,
                { role: 'status', content: hop.status },
                conversationIdRef.current || undefined,
              ).catch(() => {})
            })
            .catch(() => {})
        }
        return
      }
      persistAgentDropdownChoice(dropdownAgentId, {
        model: next.model,
        effort: next.effort || '',
      })
      setSearchParams(
        (prevParams) => {
          const nextParams = new URLSearchParams(prevParams)
          if (next.model) nextParams.set('model', next.model)
          return nextParams
        },
        { replace: true },
      )
      if (next.changed === 'effort') {
        recordDropdownChange('effort', next.previous.effort || '', next.effort || '')
        return
      }
      recordDropdownChange('model', next.previous.modelBase || next.previous.model, next.modelBase || next.model)
    },
    [dropdownAgentId, recordDropdownChange, setSearchParams, teamFromUrl, remoteFromUrl, selectedBlueprint, threadKey],
  )

  useEffect(() => {
    // REQ-28: a selected composition team uses ?team=; do not clobber it
    // with the Support default (REQ-23 owns send-to-all).
    if (searchParams.get('team') || searchParams.get('remote')) return
    if (!searchParams.get('blueprint')) {
      setSearchParams({ blueprint: SUPPORT_AGENT_ID }, { replace: true })
    }
  }, [searchParams, setSearchParams])

  useEffect(() => {
    if (teamFromUrl && sessionFromUrl) {
      setMemberTarget(sessionFromUrl)
      return
    }
    setMemberTarget(ALL_MEMBERS_TARGET)
  }, [teamFromUrl, sessionFromUrl])

  // #794: persist the selected swarm conversation (CLI or Django) so remount
  // and rail browse-back restore the same id — not the prior default.
  useEffect(() => {
    if (teamFromUrl || remoteFromUrl || !sessionFromUrl || !selectedBlueprint) return
    setConversationIdForAgent(selectedBlueprint, sessionFromUrl)
  }, [sessionFromUrl, selectedBlueprint, teamFromUrl, remoteFromUrl])

  useEffect(() => {
    const onSwitched = (event: Event) => {
      const detail = (event as CustomEvent<{ agentId?: string; conversationId?: string }>).detail
      const agent = agentIdFromBlueprint(selectedBlueprint)
      if (!detail?.conversationId || teamFromUrl || remoteFromUrl) return
      if (detail.agentId && agentIdFromBlueprint(detail.agentId) !== agent) return
      setConversationId(detail.conversationId)
    }
    const onHopped = (event: Event) => {
      const detail = (event as CustomEvent<{ agentId?: string; status?: string }>).detail
      const agent = agentIdFromBlueprint(selectedBlueprint)
      if (!detail?.status?.trim() || teamFromUrl || remoteFromUrl) return
      if (detail.agentId && agentIdFromBlueprint(detail.agentId) !== agent) return
      const statusMsg: ChatMessage = {
        key: `hop-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: 'status',
        text: detail.status,
        streaming: false,
        ts: new Date().toISOString(),
      }
      setThreads((prev) => ({
        ...prev,
        [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
      }))
    }
    window.addEventListener(CLI_SESSION_SWITCHED_EVENT, onSwitched)
    window.addEventListener(AGENT_CONVERSATION_EVENT, onSwitched)
    window.addEventListener(CLI_SESSION_HOPPED_EVENT, onHopped)
    return () => {
      window.removeEventListener(CLI_SESSION_SWITCHED_EVENT, onSwitched)
      window.removeEventListener(AGENT_CONVERSATION_EVENT, onSwitched)
      window.removeEventListener(CLI_SESSION_HOPPED_EVENT, onHopped)
    }
  }, [selectedBlueprint, teamFromUrl, remoteFromUrl, threadKey])

  useEffect(() => {
    const onEdits = () => setEditsTick((tick) => tick + 1)
    const onDropdowns = () => setDropdownTick((tick) => tick + 1)
    window.addEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
    window.addEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
    window.addEventListener(AGENT_REMOTE_BINDINGS_CHANGED_EVENT, onEdits)
    window.addEventListener(AGENT_DROPDOWNS_CHANGED_EVENT, onDropdowns)
    return () => {
      window.removeEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
      window.removeEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
      window.removeEventListener(AGENT_REMOTE_BINDINGS_CHANGED_EVENT, onEdits)
      window.removeEventListener(AGENT_DROPDOWNS_CHANGED_EVENT, onDropdowns)
    }
  }, [])

  useEffect(() => {
    if (!showRemotesControl) return
    setSelectedRemoteId(
      resolveBoundRemoteId({
        remoteFromUrl,
        persisted: persistedRemote,
        agentRemoteId: (selectedAgent as { remote_id?: string })?.remote_id,
        configuredIds: configuredRemoteRows.map((row) => row.id),
      }),
    )
  }, [
    showRemotesControl,
    remoteFromUrl,
    bindingAgentId,
    persistedRemote,
    selectedAgent,
    remotesCatalog,
  ])

  useEffect(() => {
    if (!showEmptyRemoteChrome) return
    const key = bindingAgentId || selectedBlueprint
    if (!key || emptyRemoteOpenedForRef.current === key) return
    emptyRemoteOpenedForRef.current = key
    openSettingsSheet({ section: 'remotes', addRemote: true })
  }, [showEmptyRemoteChrome, bindingAgentId, selectedBlueprint])

  useEffect(() => {
    if (teamFromUrl) {
      setNewChatPerTask(false)
      setUseSuggestions(false)
      return
    }
    const agent = agentIdFromBlueprint(selectedBlueprint)
    setNewChatPerTask(loadLocalNewChatPerTask(agent))
    setUseSuggestions(loadLocalUseSuggestions(agent))
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<AgentSettingsChangedDetail>).detail
      if (detail?.agentId && detail.agentId === agent) {
        if (typeof detail.new_chat_per_task === 'boolean') {
          setNewChatPerTask(detail.new_chat_per_task)
        }
        if (typeof detail.use_suggestions === 'boolean') {
          setUseSuggestions(detail.use_suggestions)
        }
      }
    }
    window.addEventListener(AGENT_SETTINGS_CHANGED_EVENT, onChange)
    void fetchAgentSettings(agent).then((settings) => {
      setNewChatPerTask(settings.new_chat_per_task)
      setUseSuggestions(settings.use_suggestions)
    })
    return () => window.removeEventListener(AGENT_SETTINGS_CHANGED_EVENT, onChange)
  }, [selectedBlueprint, teamFromUrl])

  useEffect(() => {
    void fetchUserPrefs().then((server) => {
      if (!server) return
      setContextStrategy(parseContextStrategy(server.context_strategy))
      setCullTriggerPct(parseCullTriggerPct(server.context_cull_trigger_pct))
    })
  }, [])

  useEffect(() => {
    void hydrateRoleAgentTipDismissed().then((dismissed) => {
      if (dismissed) setRoleTipDismissed(true)
    })
  }, [])

  const noteHydrateFailure = useCallback((bucketKey: string, err: unknown) => {
    const hadMessages = (threadsRef.current[bucketKey] ?? []).length > 0
    const detail = err instanceof Error ? err.message.trim() : ''
    const fallback = 'The transcript could not be fetched.'
    addToast({
      type: 'error',
      title: 'Could not load chat',
      message: hadMessages
        ? 'The transcript could not be fetched. Existing messages were kept.'
        : detail || fallback,
    })
    if (!hadMessages) {
      setHydrateError(detail || fallback)
      setRestoreNotice(null)
    }
    setThreadReady(true)
  }, [addToast])

  // Per-agent thread: stable conversation id + hydrate from disk/DB.
  // Team threads use a stable team-* conversation id and do not use agent JSON.
  // No history chrome — messages just come back after reload / agent switch.
  //
  // Team hydrate is isolated from ?session= (member target). Writing the
  // header dropdown into the URL must not refetch or wipe the in-memory
  // team thread (REQ-171A-1 / #601).
  useEffect(() => {
    if (!teamFromUrl) return
    setThreadReady(false)
    setHydrateError(null)
    setSuggestionChips([])
    const key = teamThreadId(teamFromUrl)
    const switched =
      lastHydratedAgentRef.current !== null && lastHydratedAgentRef.current !== key
    lastHydratedAgentRef.current = key
    setConversationId(key)
    setEditingKey(null)
    setAgentKind('api')
    setMessagesEditable(false)
    userKeyCounterRef.current = 0
    let cancelled = false
    ;(async () => {
      try {
        const thread = await fetchAgentThread(key, key)
        if (cancelled) return
        setHydrateError(null)
        setSummariesByThread((prev) => ({
          ...prev,
          [key]: thread.summaries,
        }))
        if (thread.context_meta) setContextMeta(thread.context_meta)
        if (thread.messages.length === 0) {
          setRestoreNotice(null)
          if (switched) {
            setThreads((prev) => ({ ...prev, [key]: [] }))
          }
          setThreadReady(true)
          return
        }
        setRestoreNotice(restoredSessionNotice(thread.messages, 'team'))
        setThreads((prev) => ({
          ...prev,
          [key]: thread.messages.map(chatMessageFromThreadRow),
        }))
        setThreadReady(true)
      } catch (err) {
        if (cancelled) return
        noteHydrateFailure(key, err)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [teamFromUrl, noteHydrateFailure])

  useEffect(() => {
    if (teamFromUrl) return
    setThreadReady(false)
    setHydrateError(null)
    setSuggestionChips([])
    if (remoteFromUrl) {
      const key = `remote-${remoteFromUrl}${sessionFromUrl ? `-${sessionFromUrl}` : ''}`
      const switched =
        lastHydratedAgentRef.current !== null && lastHydratedAgentRef.current !== key
      lastHydratedAgentRef.current = key
      setConversationId(key)
      setEditingKey(null)
      setAgentKind('remote')
      setMessagesEditable(false)
      userKeyCounterRef.current = 0
      let cancelled = false
      ;(async () => {
        try {
          // Same GET /chat/thread/ path as API/team — do not return early (REQ-171A-4 / #604).
          const thread = await fetchAgentThread(`remote:${remoteFromUrl}`, key)
          if (cancelled) return
          setHydrateError(null)
          setSummariesByThread((prev) => ({
            ...prev,
            [key]: thread.summaries,
          }))
          if (thread.context_meta) setContextMeta(thread.context_meta)
          if (thread.messages.length === 0) {
            setRestoreNotice(null)
            if (switched) {
              setThreads((prev) => ({ ...prev, [key]: [] }))
            }
            setThreadReady(true)
            return
          }
          setRestoreNotice(restoredSessionNotice(thread.messages, 'remote'))
          setThreads((prev) => ({
            ...prev,
            [key]: thread.messages.map(chatMessageFromThreadRow),
          }))
          setThreadReady(true)
        } catch (err) {
          if (cancelled) return
          noteHydrateFailure(key, err)
        }
      })()
      return () => {
        cancelled = true
      }
    }

    const agent = agentIdFromBlueprint(selectedBlueprint)
    const stored = peekConversationIdForAgent(agent)
    const resolvedSession = sessionFromUrl || stored || ''
    const fresh = !resolvedSession && newChatPerTask
    const nextId = fresh
      ? conversationIdForTask(agent, { newChatPerTask: true })
      : resolvedSession || conversationIdForAgent(agent)
    const hydrateKey = sessionFromUrl
      ? `${agent}::${sessionFromUrl}`
      : fresh
        ? nextId
        : agent
    const switched =
      lastHydratedAgentRef.current !== null &&
      lastHydratedAgentRef.current !== hydrateKey
    lastHydratedAgentRef.current = hydrateKey
    setConversationId(nextId)
    if (resolvedSession) {
      setConversationIdForAgent(agent, nextId)
    }
    setEditingKey(null)
    setAgentKind(classifyAgentKind(selectedBlueprint))
    setMessagesEditable(canEditAgentMessages(selectedBlueprint) && !selectedCli)
    userKeyCounterRef.current = 0
    if (fresh) {
      // New empty session — do not restore a prior transcript.
      setRestoreNotice(null)
      setHydrateError(null)
      setThreadReady(true)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const thread = await fetchAgentThread(agent, resolvedSession || undefined)
        if (cancelled) return
        setHydrateError(null)
        setAgentKind(thread.kind ?? classifyAgentKind(selectedBlueprint))
        setMessagesEditable(
          !teamFromUrl &&
            !remoteFromUrl &&
            (thread.editable ?? canEditAgentMessages(selectedBlueprint, thread.kind)),
        )
        setSummariesByThread((prev) => ({
          ...prev,
          [threadKey]: thread.summaries,
        }))
        if (thread.context_meta) setContextMeta(thread.context_meta)
        if (thread.session_missing) {
          setRestoreNotice(missingSessionNotice(resolvedSession || nextId))
          setThreads((prev) => ({ ...prev, [threadKey]: [] }))
          setThreadReady(true)
          return
        }
        if (switched && sessionFromUrl) {
          setRestoreNotice(switchedSessionNotice(thread.session_title || thread.conversation_id))
          if (thread.messages.length === 0) {
            setThreads((prev) => ({ ...prev, [threadKey]: [] }))
            setThreadReady(true)
            return
          }
        } else if (thread.messages.length === 0) {
          setRestoreNotice(null)
          if (switched) {
            setThreads((prev) => ({ ...prev, [threadKey]: [] }))
          }
          setThreadReady(true)
          return
        } else {
          setRestoreNotice(restoredSessionNotice(thread.messages, restoreKindForAgent(agent)))
        }
        setThreads((prev) => ({
          ...prev,
          [threadKey]: thread.messages.map(chatMessageFromThreadRow),
        }))
        setThreadReady(true)
      } catch (err) {
        if (cancelled) return
        noteHydrateFailure(threadKey, err)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedBlueprint, sessionFromUrl, teamFromUrl, remoteFromUrl, newChatPerTask, threadKey, selectedCli, noteHydrateFailure])

  const attachToolToThread = useCallback(
    (tool: ToolCallState) => {
      setThreads((prev) => {
        const current = prev[threadKey] ?? []
        const targetIndex = [...current]
          .reverse()
          .findIndex((message) => message.role === 'assistant')
        const index = targetIndex === -1 ? -1 : current.length - 1 - targetIndex
        if (index === -1) {
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `tool-host-${tool.id}`,
                role: 'assistant' as const,
                text: '',
                streaming: true,
                tools: [tool],
              },
            ],
          }
        }
        const next = [...current]
        const host = next[index]!
        next[index] = { ...host, tools: upsertToolCall(host.tools ?? [], tool) }
        return { ...prev, [threadKey]: next }
      })
    },
    [threadKey],
  )

  const sendToolDecision = useCallback((id: string, decision: 'allow' | 'always' | 'deny') => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(buildToolDecisionFrame(id, decision))
  }, [])

  const jumpToPrOpener = useCallback(
    (opener: PrOpenedOpener) => {
      setSearchParams(openerChatSearch(opener))
    },
    [setSearchParams],
  )

  const handleWsEvent = useCallback(
    (event: ChatWsEvent) => {
      if (event.kind === 'unknown') {
        console.warn('Unrecognised chat websocket frame:', event.raw)
        return
      }
      if (event.kind === 'spa_hello') {
        publishExpectedSpaVersion(event.spaVersion)
        return
      }
      if (event.kind === 'tool_status') {
        attachToolToThread({
          id: event.id,
          name: event.name,
          status: event.status,
          agentId: event.agentId,
          needsApproval: false,
        })
        return
      }
      if (event.kind === 'suggestions') {
        if (!useSuggestions) {
          setSuggestionChips([])
          return
        }
        setSuggestionChips(event.suggestions)
        return
      }
      if (event.kind === 'pr_opened') {
        setThreads((prev) => {
          const current = prev[threadKey] ?? []
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `pr-opened-${current.length}-${Date.now()}`,
                role: 'status' as const,
                text: '',
                streaming: false,
                prOpened: event.event,
              },
            ],
          }
        })
        return
      }
      if (event.kind === 'teammate_task') {
        setThreads((prev) => {
          const current = prev[threadKey] ?? []
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `teammate-task-${current.length}-${Date.now()}`,
                role: 'status' as const,
                text: '',
                streaming: false,
                teammateTask: event.event,
              },
            ],
          }
        })
        return
      }
      if (event.kind === 'tool_approval') {
        const agentId = event.agentId || selectedBlueprint || threadKey
        if (isToolAlwaysAllowed(agentId, event.name)) {
          sendToolDecision(event.id, 'always')
          attachToolToThread({
            id: event.id,
            name: event.name,
            status: 'allowed',
            agentId,
            needsApproval: false,
            concerned: true,
          })
          return
        }
        attachToolToThread({
          id: event.id,
          name: event.name,
          status: 'running',
          agentId,
          needsApproval: true,
          concerned: true,
        })
        return
      }
      setThreads((prev) => {
        const current = prev[threadKey] ?? []
        let next = current
        switch (event.kind) {
          case 'user_echo':
            userKeyCounterRef.current += 1
            next = [
              ...current,
              {
                key: `user-${userKeyCounterRef.current}-${Date.now()}`,
                role: 'user',
                text: event.text,
                streaming: false,
              },
            ]
            break
          case 'assistant_start':
            if (current.some((m) => m.key === event.id)) return prev
            next = [...current, { key: event.id, role: 'assistant', text: '', streaming: true }]
            break
          case 'assistant_chunk':
            next = current.map((m) =>
              m.key === event.id ? { ...m, text: m.text + event.text } : m,
            )
            break
          case 'assistant_final':
            next = current.map((m) =>
              m.key === event.id ? { ...m, text: event.text, streaming: false } : m,
            )
            break
          case 'status':
            if (
              event.text === CLI_TERMINATED_STATUS &&
              current.some((row) => row.role === 'status' && row.text === CLI_TERMINATED_STATUS)
            ) {
              next = current.map((row) => (row.streaming ? { ...row, streaming: false } : row))
              break
            }
            next = insertCliSessionNotice(current, {
              key: `status-${current.length}-${Date.now()}`,
              role: 'status',
              text: event.text,
              streaming: false,
              rateLimit: event.rateLimit,
            })
            break
        }
        return { ...prev, [threadKey]: next }
      })
      if (event.kind === 'assistant_final') {
        const { agentId, agentName } = notifyCtxRef.current
        if (agentId) {
          notifyGenerationComplete(agentId, {
            snippet: event.text,
            agentName,
          })
          maybeNotifyAgentTurn({
            agentId,
            agentName,
            snippet: event.text,
            selectedAgentId: agentId,
          })
        }
      }
    },
    [activeChatAgentId, attachToolToThread, sendToolDecision, threadKey, useSuggestions],
  )

  useEffect(() => {
    let opened = false
    intentionalCloseRef.current = false
    setStatus('connecting')
    setAuthRejected(false)

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    let ws: WebSocket
    try {
      ws = new WebSocket(
        buildChatWsUrl(conversationId, teamFromUrl ? undefined : runtimeBlueprint || undefined),
      )
    } catch {
      setStatus('failed')
      const attempt = backoffAttemptRef.current
      if (shouldAutoReconnect(1006, false, attempt)) {
        const delay = reconnectBackoffMs(attempt)
        backoffAttemptRef.current = attempt + 1
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          setConnectAttempt((n) => n + 1)
        }, delay)
      }
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      opened = true
      backoffAttemptRef.current = 0
      setStatus('open')
    }
    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        handleWsEvent(parseChatWsMessage(event.data))
      }
    }
    ws.onclose = (event: CloseEvent) => {
      if (wsRef.current === ws) wsRef.current = null
      const rejected = event.code === WS_AUTH_REQUIRED_CODE
      setAuthRejected(rejected)
      setStatus(opened ? 'closed' : 'failed')
      let interrupted = false
      setThreads((prev) => {
        const current = prev[threadKey]
        if (!current || !current.some((m) => m.streaming)) return prev
        interrupted = true
        return {
          ...prev,
          [threadKey]: current.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
        }
      })
      if (interrupted) {
        const { agentId, agentName } = notifyCtxRef.current
        if (agentId) {
          notifyGenerationComplete(agentId, {
            failed: true,
            agentName,
          })
          maybeNotifyAgentTurn({
            agentId,
            agentName,
            failed: true,
            selectedAgentId: agentId,
          })
        }
      }

      const attempt = backoffAttemptRef.current
      if (shouldAutoReconnect(event.code, intentionalCloseRef.current, attempt)) {
        const delay = reconnectBackoffMs(attempt)
        backoffAttemptRef.current = attempt + 1
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          setConnectAttempt((n) => n + 1)
        }, delay)
      }
    }

    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      ws.onopen = null
      ws.onmessage = null
      ws.onclose = null
      ws.close()
      if (wsRef.current === ws) wsRef.current = null
    }
  }, [connectAttempt, handleWsEvent, conversationId, runtimeBlueprint, teamFromUrl])

  useEffect(() => {
    publishChatConnection(status)
  }, [status])

  const pinnedToBottomRef = useRef(true)

  const applyComposerInset = useCallback(() => {
    const next = measureComposerDockInset(bottomDockRef.current)
    setComposerInsetPx((prev) => (prev === next ? prev : next))
  }, [])

  useLayoutEffect(() => {
    applyComposerInset()
  }, [applyComposerInset, messages, replyTarget, input])

  useLayoutEffect(() => {
    const dock = bottomDockRef.current
    if (!dock || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      applyComposerInset()
    })
    observer.observe(dock)
    return () => observer.disconnect()
  }, [applyComposerInset])

  useLayoutEffect(() => {
    const box = scrollBoxRef.current
    if (!box) return undefined
    const apply = () => setTranscriptHeightPx(box.clientHeight)
    apply()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(apply)
    observer.observe(box)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (pinnedToBottomRef.current) {
      scrollTranscriptToBottom(scrollBoxRef.current, listEndRef.current)
    }
  }, [messages, composerInsetPx])

  useEffect(() => {
    const wasOpen = prevStatusRef.current === 'open'
    prevStatusRef.current = status
    if (status === 'open' && !wasOpen && connectAttempt > 0) {
      composerRef.current?.focus()
    }
  }, [status, connectAttempt])

  const reconnect = useCallback(() => {
    backoffAttemptRef.current = 0
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    setConnectAttempt((n) => n + 1)
  }, [])

  useEffect(() => {
    if (status === 'open') {
      dismissByKind(TOAST_KIND_WS_DISCONNECT)
      return
    }
    if (status !== 'failed' && status !== 'closed') return
    const title = authRejected
      ? 'Chat unavailable — sign in required'
      : status === 'failed'
        ? 'Chat websocket unreachable'
        : 'Chat disconnected'
    const detail = authRejected
      ? 'Live chat needs a Django session cookie. Sign in, then reconnect.'
      : status === 'failed'
        ? 'ASGI is not serving /ws/ or Origin does not match ALLOWED_HOSTS.'
        : 'The chat websocket closed. Message history is kept.'
    addToast({
      kind: TOAST_KIND_WS_DISCONNECT,
      type: 'error',
      title,
      message: (
        <span>
          {detail}{' '}
          {authRejected ? (
            <a href={signInHref} className="link">
              Sign in
            </a>
          ) : null}{' '}
          <button type="button" className="link" onClick={reconnect}>
            Reconnect
          </button>
        </span>
      ),
      position: 'bottom-right',
    })
  }, [status, authRejected, signInHref, addToast, dismissByKind, reconnect])

  const hasSendableDraft = input.trim().length > 0
  const canSend = status === 'open' && hasSendableDraft

  const sendText = useCallback(
    (text: string): boolean => {
      const ws = wsRef.current
      const trimmed = text.trim()
      if (!trimmed || !ws || ws.readyState !== WebSocket.OPEN) return false
      lastUserTextRef.current = trimmed
      // Team compose adds params { team, target: "all" | memberId }.
      const pluginParams = enabledToolsParam(conversationIdRef.current)
      if (teamFromUrl) {
        ws.send(
          buildChatWsFrame(trimmed, undefined, {
            team: teamFromUrl,
            target: memberTarget || ALL_MEMBERS_TARGET,
            ...pluginParams,
          }),
        )
        return true
      }
      const supportParams = isSupportAgent({
        id: runtimeBlueprint || selectedBlueprint || SUPPORT_AGENT_ID,
      })
        ? supportTurnExtras()
        : undefined
      const persistedModel = (persistedDropdown.model || persistedDropdown.api || '').trim()
      const selectedModelParam = (
        (searchParams.get('model') ?? '').trim() ||
        (isCliAgent ? currentCliModel : persistedModel)
      ).trim()
      const agentIdForInference =
        runtimeBlueprint || selectedBlueprint || SUPPORT_AGENT_ID
      const inferenceSeats = loadInferenceList(agentIdForInference)
      const inferenceKeys = serializeInferenceList(inferenceSeats)
      let inferenceIndex: number | undefined
      let scaleSeat = inferenceSeats[0]
      if (newChatPerTask && inferenceSeats.length > 0) {
        inferenceIndex = nextInferenceIndex(agentIdForInference, inferenceSeats.length)
        scaleSeat = inferenceSeats[inferenceIndex]
      }
      const folderParams = chatFolderParams(agentIdForInference)
      const persistedSkills = loadAgentEdit(agentIdForInference).skills ?? []
      const skillParams = buildSkillParams([
        ...persistedSkills,
        ...parseComposerSkillNames(trimmed),
      ])
      const cliParams = isCliAgent
        ? {
            cli: currentCli,
            ...(selectedModelParam && selectedModelParam !== 'default' ? { model: selectedModelParam } : {}),
          }
        : isApiAgent && selectedModelParam && selectedModelParam !== 'default'
          ? { model: selectedModelParam }
          : selectedCli
            ? { cli: selectedCli.cli }
            : newChatPerTask
              ? { new_session: messages.length === 0 }
              : undefined
      const inferenceParams =
        inferenceKeys.length > 0
          ? {
              inference_list: inferenceKeys,
              ...(inferenceIndex !== undefined ? { inference_index: inferenceIndex, scale_out: true } : {}),
              ...(scaleSeat?.kind === 'llm' ? { llm_profile: scaleSeat.id, model: scaleSeat.id } : {}),
              ...(scaleSeat?.kind === 'cli' ? { cli: scaleSeat.id } : {}),
              ...(scaleSeat?.kind === 'remote' ? { remote_id: scaleSeat.id } : {}),
            }
          : undefined
      ws.send(
        buildChatWsFrame(
          trimmed,
          runtimeBlueprint || selectedBlueprint || undefined,
          supportParams ||
          cliParams ||
          inferenceParams ||
          pluginParams ||
          folderParams ||
          Object.keys(skillParams).length
            ? {
                ...cliParams,
                ...inferenceParams,
                ...supportParams,
                ...pluginParams,
                ...folderParams,
                ...skillParams,
              }
            : undefined,
        ),
      )
      return true
    },
    [
      runtimeBlueprint,
      selectedBlueprint,
      selectedCli,
      isCliAgent,
      currentCli,
      currentCliModel,
      persistedDropdown.model,
      persistedDropdown.api,
      isApiAgent,
      searchParams,
      teamFromUrl,
      memberTarget,
      newChatPerTask,
      messages.length,
    ],
  )

  const submitUserText = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || status !== 'open') return
      // REQ-171A-3 / #603: queue before assistant_start, not only while
      // streaming. REQ-90 / #447 owns the pane chrome; this only closes
      // the pre-start double-{message} race.
      if (generationIsInFlight(messages, awaitingAssistant)) {
        queued.enqueue(trimmed)
        return
      }
      setAwaitingAssistant(true)
      if (!sendText(trimmed)) setAwaitingAssistant(false)
    },
    [awaitingAssistant, messages, queued, sendText, status],
  )

  useEffect(() => {
    const onChip = (event: Event) => {
      const text = suggestionChipText(event)
      if (text.trim()) submitUserText(text)
    }
    window.addEventListener(SUGGESTION_CHIP_EVENT, onChip)
    return () => {
      window.removeEventListener(SUGGESTION_CHIP_EVENT, onChip)
    }
  }, [submitUserText])

  const saveEditedMessage = useCallback(
    async (index: number, nextText: string) => {
      if (!messagesEditable) return
      const current = threads[threadKey] ?? []
      const target = current[index]
      if (!target || target.streaming) return
      setThreads((prev) => {
        const list = prev[threadKey] ?? []
        if (!list[index]) return prev
        const next = list.slice()
        next[index] = { ...next[index], text: nextText, edited: true }
        return { ...prev, [threadKey]: next }
      })
      setEditingKey(null)
      const turnIndex = turnIndexFromDisplay(current, index)
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(buildChatWsEditFrame(turnIndex, nextText))
      }
      try {
        await patchAgentMessage(agentIdFromBlueprint(selectedBlueprint), {
          index: turnIndex,
          content: nextText,
          conversation_id: conversationIdRef.current,
        })
      } catch {
        addToast({
          type: 'error',
          title: 'Could not save edit',
          message: 'The message was updated in this view, but persist failed.',
        })
      }
    },
    [addToast, messagesEditable, selectedBlueprint, threadKey, threads],
  )

  const handleSend = (event: FormEvent) => {
    event.preventDefault()
    if (!canSend) return
    const quotePrefix = replyTarget ? (replyTarget.speaker ? `> **${replyTarget.speaker}**: ` : `> `) : ''
    const textToSend = replyTarget
      ? `${quotePrefix}${replyTarget.text.replace(/\r\n/g, '\n').split('\n').join('\n> ')}\n\n${input}`
      : input
    submitUserText(textToSend)
    setInput('')
    setReplyTarget(null)
  }

  // Dynamic skills loading for slash catalog (REQ-169)
  useEffect(() => {
    let unmounted = false
    void Promise.all([fetchConfigOptions(), fetchSkills().catch(() => null)])
      .then(([opts, listed]) => {
        if (unmounted) return
        const rows = listed?.data?.length ? listed.data : opts?.skills || []
        if (rows.length) {
          setSkillCatalog(rows)
          setDynamicSkills(rows.map((s) => ({ name: s.name, description: s.description })))
        } else if (opts?.skills) {
          setDynamicSkills(
            opts.skills.map((s) => ({ name: s.name, description: s.description })),
          )
        }
      })
      .catch(() => {
        // Silently ignore if config options endpoint is unavailable
      })
    return () => {
      unmounted = true
    }
  }, [])

  const slashCatalog = useMemo(() => buildSlashCatalog(dynamicSkills), [dynamicSkills])
  const isSlashOpen = input.startsWith('/') && !slashDismissed
  const slashQuery = input.startsWith('/') ? input.slice(1) : ''
  const filteredSlashItems = useMemo(
    () => filterSlashItems(slashCatalog, slashQuery, recentSlashIds),
    [slashCatalog, slashQuery, recentSlashIds],
  )

  useEffect(() => {
    setSlashSelectedIndex(0)
  }, [slashQuery])

  useEffect(() => {
    if (!isSlashOpen) return
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (composerWrapRef.current && !composerWrapRef.current.contains(event.target as Node)) {
        setSlashDismissed(true)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('touchstart', onPointerDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('touchstart', onPointerDown)
    }
  }, [isSlashOpen])

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    if (val.startsWith('/') && !input.startsWith('/')) {
      setSlashDismissed(false)
      setSlashSelectedIndex(0)
    }
    setInput(val)
  }

  const speechSettings = parseSpeechSettings(speechQuery.data ?? EMPTY_SPEECH)

  const handleMic = () => {
    if (sttListening) {
      sttStopRef.current?.()
      return
    }
    const path = resolveSttPath(speechSettings)
    if (!path) {
      addToast({
        type: 'info',
        title: 'Voice input',
        message: sttUnavailableMessage(speechSettings),
      })
      return
    }
    if (path === 'system') {
      try {
        const handle = listenSystemStt({
          onTranscript: (spoken) => {
            setInput((prev) => appendTranscript(prev, spoken))
          },
          onEnd: () => {
            setSttListening(false)
            sttStopRef.current = null
          },
          onError: (message) => {
            addToast({ type: 'info', title: 'Voice input', message })
            setSttListening(false)
            sttStopRef.current = null
          },
        })
        sttStopRef.current = handle.stop
        setSttListening(true)
        setSttPathUsed('system')
        addToast({
          type: 'info',
          title: 'Voice input',
          message: `Using ${describeSpeechPath('system', 'stt')}. Transcript stays in the composer.`,
        })
      } catch (err) {
        addToast({
          type: 'info',
          title: 'Voice input',
          message: err instanceof Error ? err.message : sttUnavailableMessage(speechSettings),
        })
      }
      return
    }
    void (async () => {
      try {
        const session = await recordMicrophoneAudio()
        sttStopRef.current = () => {
          void (async () => {
            try {
              const blob = await session.stop()
              const spoken = await transcribeCustomBlob(blob)
              if (spoken) setInput((prev) => appendTranscript(prev, spoken))
            } catch (err) {
              addToast({
                type: 'info',
                title: 'Voice input',
                message: err instanceof Error ? err.message : 'Custom STT failed.',
              })
            } finally {
              setSttListening(false)
              sttStopRef.current = null
            }
          })()
        }
        setSttListening(true)
        setSttPathUsed('custom')
        addToast({
          type: 'info',
          title: 'Voice input',
          message: `Using ${describeSpeechPath('custom', 'stt')}. Click the mic again to stop.`,
        })
      } catch (err) {
        addToast({
          type: 'info',
          title: 'Voice input',
          message: err instanceof Error ? err.message : sttUnavailableMessage(speechSettings),
        })
        setSttListening(false)
        sttStopRef.current = null
      }
    })()
  }

  useEffect(() => {
    if (!plusOpen) return
    const onPointer = (event: Event) => {
      if (plusRef.current && !plusRef.current.contains(event.target as Node)) {
        setPlusOpen(false)
      }
    }
    window.addEventListener('mousedown', onPointer)
    return () => window.removeEventListener('mousedown', onPointer)
  }, [plusOpen])

  const streamingMessage = messages.find((message) => message.streaming)
  const chipsDisabled = status !== 'open'
  const supportSelected =
    !teamFromUrl &&
    !remoteFromUrl &&
    (isSupportJourneyConsumer(selectedBlueprint) ||
      isSupportAgent({
        id: selectedBlueprint || SUPPORT_AGENT_ID,
        name: selectedAgentName,
      }))
  const supportJourneyChips =
    supportSelected && messages.length === 0 ? supportJourneyKickstart() : []
  const showSupportJourneyChips = supportJourneyChips.length > 0
  const showSuggestionChips =
    !showSupportJourneyChips &&
    shouldShowSuggestionChips({
      enabled: useSuggestions,
      chips: suggestionChips,
    })

  useEffect(() => {
    if (!useSuggestions) {
      setSuggestionChips([])
      return
    }
    if (!threadReady || streamingMessage || teamFromUrl) return
    const agent = agentIdFromBlueprint(selectedBlueprint)
    if (!agent) return
    let cancelled = false
    const mode = messages.length === 0 ? 'kickstart' : 'continue'
    void fetchAgentSuggestions(agent, mode, conversationId).then((chips) => {
      if (!cancelled && chips.length > 0) setSuggestionChips(chips)
    })
    return () => {
      cancelled = true
    }
  }, [
    useSuggestions,
    threadReady,
    streamingMessage,
    teamFromUrl,
    selectedBlueprint,
    messages.length,
    threadKey,
    conversationId,
  ])

  const chooseSuggestion = useCallback(
    (text: string) => {
      if (status !== 'open') return
      submitUserText(text)
    },
    [status, submitUserText],
  )

  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (streamingMessage) {
      wasStreamingRef.current = true
      setAwaitingAssistant(false)
      drainLockRef.current = false
    } else if (wasStreamingRef.current) {
      wasStreamingRef.current = false
      if (activeChatAgentId) {
        const lastAssistant = [...messages]
          .reverse()
          .find((message) => message.role === 'assistant' && message.text)
        notifyGenerationComplete(activeChatAgentId, {
          snippet: lastAssistant?.text,
          agentName: selectedAgentName,
        })
        maybeNotifyAgentTurn({
          agentId: activeChatAgentId,
          agentName: selectedAgentName,
          snippet: lastAssistant?.text,
          selectedAgentId: activeChatAgentId,
        })
      }
    }
    if (isCliAgent && activeChatAgentId) {
      notifyCliRunState(activeChatAgentId, Boolean(streamingMessage))
    }
  }, [streamingMessage, activeChatAgentId, messages, selectedAgentName, isCliAgent])

  useEffect(() => {
    if (generationIsInFlight(messages, awaitingAssistant) || status !== 'open') return
    const next = nextDrainableQueuedSend(queued.rows, queuedHoldIds)
    if (!next || drainLockRef.current) return
    drainLockRef.current = true
    setAwaitingAssistant(true)
    queued.remove(next.id)
    if (!sendText(next.text)) {
      drainLockRef.current = false
      setAwaitingAssistant(false)
      queued.restore(next)
    }
  }, [awaitingAssistant, messages, queued, queuedHoldIds, sendText, status])

  useEffect(() => {
    const onTerminated = (event: Event) => {
      const detail = cliTerminatedFromEvent(event)
      if (!detail) return
      const matchesAgent = detail.agentId === activeChatAgentId
      const matchesConversation =
        Boolean(detail.conversationId) && detail.conversationId === conversationIdRef.current
      if (!matchesAgent && !matchesConversation) return
      const statusMsg: ChatMessage = {
        key: `status-terminated-${Date.now()}`,
        role: 'status',
        text: CLI_TERMINATED_STATUS,
        streaming: false,
        ts: new Date().toISOString(),
      }
      setThreads((prev) => {
        const current = prev[threadKey] ?? []
        const stopped = current.map((row) => (row.streaming ? { ...row, streaming: false } : row))
        if (stopped.some((row) => row.role === 'status' && row.text === CLI_TERMINATED_STATUS)) {
          return { ...prev, [threadKey]: stopped }
        }
        return { ...prev, [threadKey]: [...stopped, statusMsg] }
      })
    }
    window.addEventListener(CLI_TERMINATED_EVENT, onTerminated)
    return () => window.removeEventListener(CLI_TERMINATED_EVENT, onTerminated)
  }, [activeChatAgentId, threadKey])

  const handleCompact = useCallback(async () => {
    setPlusOpen(false)
    if (messages.length === 0) {
      addToast({
        type: 'info',
        title: 'Compact',
        message: 'Nothing to compact yet.',
      })
      return
    }
    try {
      const result = await compactAgentThread({
        conversationId,
        agentId: teamFromUrl || agentIdFromBlueprint(selectedBlueprint),
        messages: messages
          .filter((message) => message.role === 'user' || message.role === 'assistant')
          .map((message) => ({
            role: message.role,
            content: message.text,
          })),
      })
      setSummariesByThread((prev) => ({ ...prev, [threadKey]: result.summaries }))
    } catch (err) {
      const detail = err instanceof Error ? err.message.trim() : ''
      addToast({
        type: 'error',
        title: 'Compact failed',
        message: detail || 'Could not compact this chat. Sign in and try again.',
      })
    }
  }, [addToast, conversationId, messages, selectedBlueprint, teamFromUrl, threadKey])

  const handleCompressToHere = useCallback(
    async (message: ChatMessage) => {
      setPlusOpen(false)
      setContextMenu(null)
      const rawMessages = messages.filter(
        (row) => row.role === 'user' || row.role === 'assistant',
      )
      const spanEnd = rawOffsetForMessage(messages, message.key)
      if (spanEnd < 0 || rawMessages.length === 0) {
        addToast({
          type: 'info',
          title: 'Compress',
          message: 'Nothing to compact yet.',
        })
        return
      }
      try {
        const result = await compactAgentThread({
          conversationId,
          agentId: teamFromUrl || agentIdFromBlueprint(selectedBlueprint),
          messages: rawMessages.map((row) => ({
            role: row.role,
            content: row.text,
          })),
          spanStart: 0,
          spanEnd,
        })
        setSummariesByThread((prev) => ({ ...prev, [threadKey]: result.summaries }))
      } catch (err) {
        const detail = err instanceof Error ? err.message.trim() : ''
        addToast({
          type: 'error',
          title: 'Compact failed',
          message: detail || 'Could not compact this chat. Sign in and try again.',
        })
      }
    },
    [addToast, conversationId, messages, selectedBlueprint, teamFromUrl, threadKey],
  )

  const applyStartFromHere = useCallback(
    async (message: ChatMessage, confirm: boolean) => {
      const rawMessages = messages.filter(
        (row) => row.role === 'user' || row.role === 'assistant',
      )
      const startOffset = rawOffsetForMessage(messages, message.key)
      if (startOffset < 0 || rawMessages.length === 0) {
        addToast({
          type: 'info',
          title: START_CONTEXT_FROM_HERE_LABEL,
          message: 'Nothing to start from yet.',
        })
        return
      }
      try {
        const result = await startContextFromHere({
          conversationId,
          agentId: teamFromUrl || agentIdFromBlueprint(selectedBlueprint),
          messages: rawMessages.map((row) => ({
            role: row.role,
            content: row.text,
          })),
          startOffset,
          confirm,
          contextMax: contextMaxRef.current,
        })
        if (result.warning && !result.applied) {
          const pct = typeof result.estimated_pct === 'number' ? result.estimated_pct : 0
          const trigger = result.cull_trigger_pct ?? cullTriggerPct
          setStartFromHereWarning({
            message,
            startOffset,
            copy: result.info || overFullWarningCopy(pct, trigger),
          })
          return
        }
        if (result.context_meta) setContextMeta(result.context_meta)
        setStartFromHereWarning(null)
      } catch {
        addToast({
          type: 'error',
          title: START_CONTEXT_FROM_HERE_LABEL,
          message: 'Could not start context from here. Sign in and try again.',
        })
      }
    },
    [addToast, conversationId, cullTriggerPct, messages, selectedBlueprint, teamFromUrl],
  )

  const handleStartContextFromHere = useCallback(
    (message: ChatMessage) => {
      setPlusOpen(false)
      setContextMenu(null)
      void applyStartFromHere(message, false)
    },
    [applyStartFromHere],
  )

  const handleContextToHere = useCallback(
    (message: ChatMessage) => {
      if (contextStrategy === 'cull') {
        handleStartContextFromHere(message)
        return
      }
      void handleCompressToHere(message)
    },
    [contextStrategy, handleCompressToHere, handleStartContextFromHere],
  )

  const handleSelectSlashItem = useCallback(
    (item: SlashItem) => {
      recordRecentSlashId(item.id)
      setRecentSlashIds(getRecentSlashIds())
      setSlashDismissed(true)

      if (item.id === 'compact') {
        void handleCompact()
        setInput('')
      } else {
        setInput(`${item.command} `)
      }
      setTimeout(() => {
        composerRef.current?.focus()
      }, 0)
    },
    [handleCompact],
  )

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (isSlashOpen) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setSlashSelectedIndex((prev) =>
          filteredSlashItems.length > 0 ? (prev + 1) % filteredSlashItems.length : 0,
        )
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setSlashSelectedIndex((prev) =>
          filteredSlashItems.length > 0
            ? (prev - 1 + filteredSlashItems.length) % filteredSlashItems.length
            : 0,
        )
        return
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        if (filteredSlashItems.length > 0) {
          event.preventDefault()
          const selected = filteredSlashItems[slashSelectedIndex] || filteredSlashItems[0]
          if (selected) {
            handleSelectSlashItem(selected)
            return
          }
        }
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setSlashDismissed(true)
        return
      }
    }

    if (event.key === 'Escape') {
      if (replyTarget) {
        event.preventDefault()
        setReplyTarget(null)
        return
      }
      if (input.length > 0) {
        event.preventDefault()
        setInput('')
        return
      }
      if (showRoleTip) {
        event.preventDefault()
        dismissRoleTip()
        return
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (status === 'open' && input.trim().length > 0) {
        const quotePrefix = replyTarget ? (replyTarget.speaker ? `> **${replyTarget.speaker}**: ` : `> `) : ''
        const textToSend = replyTarget
          ? `${quotePrefix}${replyTarget.text.replace(/\r\n/g, '\n').split('\n').join('\n> ')}\n\n${input}`
          : input
        submitUserText(textToSend)
        setInput('')
        setReplyTarget(null)
      }
    }
  }

  const tokenCount = estimateTokensInContext(contextTextsForMeter(messages, summaries))
  const selectedModelId = (
    (searchParams.get('model') ?? '').trim() ||
    (isCliAgent ? currentCliModel : (persistedDropdown.model || persistedDropdown.api || ''))
  ).trim()
  const contextMax = resolveContextMaxFromProfiles(
    llmProfilesQuery.data?.profiles,
    selectedModelId || llmProfilesQuery.data?.default_llm_profile,
  )
  contextMaxRef.current = contextMax
  const meterMax = contextMax ?? CONTEXT_METER_TOKENS
  const tokenPct = Math.min(100, Math.round((tokenCount / meterMax) * 100))
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

  return (
    <div className="os-chat flex h-full min-h-0 w-full flex-col">
      <header className="os-chat-header">
        <div className="os-chat-header__identity flex min-w-0 items-center gap-2 group">
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
            className="os-navbar-identity-card flex min-w-0 items-center gap-2 rounded-lg px-2 py-1 -my-1 border border-transparent transition-colors hover:bg-base-200/50 hover:border-base-content/10 cursor-pointer"
            data-testid="selected-agent-header"
            role="button"
            tabIndex={0}
            aria-label={`Agent identity: ${selectedAgentName}`}
            onClick={() => {
              if (!teamFromUrl && selectedBlueprint) {
                openAgentEditor({
                  agentId: selectedBlueprint,
                })
                return
              }
              if (teamFromUrl) {
                openTeamEditor({
                  teamId: teamFromUrl,
                  teamName: selectedTeam?.name || teamFromUrl,
                })
                return
              }
              const role = agentRole({
                id: selectedBlueprint,
                name: selectedAgentName,
                role: selectedAgent?.role,
              })
              openSettingsSheet({
                section: 'definition',
                definitionKind: isExampleRole(role) || isChiefOfStaff(role) ? 'role' : 'blueprint',
                definitionId: selectedBlueprint,
                blueprintId: selectedBlueprint,
              })
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                if (!teamFromUrl && selectedBlueprint) {
                  openAgentEditor({
                    agentId: selectedBlueprint,
                  })
                  return
                }
                if (teamFromUrl) {
                  openTeamEditor({
                    teamId: teamFromUrl,
                    teamName: selectedTeam?.name || teamFromUrl,
                  })
                  return
                }
                const role = agentRole({
                  id: selectedBlueprint,
                  name: selectedAgentName,
                  role: selectedAgent?.role,
                })
                openSettingsSheet({
                  section: 'definition',
                  definitionKind: isExampleRole(role) || isChiefOfStaff(role) ? 'role' : 'blueprint',
                  definitionId: selectedBlueprint,
                  blueprintId: selectedBlueprint,
                })
              }
            }}
          >
            {teamFromUrl && teamDeclaredRoster ? (
              <PersonaRoster
                roster={teamDeclaredRoster}
                groupId={teamFromUrl}
                label={`${selectedAgentName} declared members`}
                size="md"
              />
            ) : !teamFromUrl ? (
              <AgentAvatar
                src={selectedAgent?.avatar_path}
                agentId={agentIdFromBlueprint(selectedBlueprint)}
                active={Boolean(streamingMessage)}
                status={streamingMessage ? 'working' : 'idle'}
                size="lg"
                gl
                className="os-chat-header__avatar shrink-0"
              />
            ) : null}
            <h1 className="truncate text-base font-semibold tracking-tight">
              <button
                type="button"
                className="os-identity-btn truncate text-left"
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
                  const role = agentRole({
                    id: selectedBlueprint,
                    name: selectedAgentName,
                    role: selectedAgent?.role,
                  })
                  openSettingsSheet({
                    section: 'definition',
                    definitionKind: isExampleRole(role) || isChiefOfStaff(role) ? 'role' : 'blueprint',
                    definitionId: selectedBlueprint,
                    blueprintId: selectedBlueprint,
                  })
                }}
              >
                {selectedAgentName}
              </button>
            </h1>
            {teamFromUrl ? (
              <div className="tooltip tooltip-bottom shrink-0" data-tip="Edit team">
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
              <div className="tooltip tooltip-bottom shrink-0" data-tip="Edit agent">
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
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-ghost btn-xs h-auto p-1 gap-1.5 font-normal text-inherit hover:bg-base-300/40 normal-case shrink-0"
            aria-label="Session token usage"
            data-testid="token-meter-button"
            onClick={() => setTokenDiagOpen(true)}
          >
            <div
              className="h-1 w-14 overflow-hidden rounded-full bg-base-300"
              role="meter"
              aria-label="Tokens in context"
              aria-valuemin={0}
              aria-valuemax={meterMax}
              aria-valuenow={tokenCount}
            >
              <div
                className="h-full rounded-full bg-base-content/45"
                style={{ width: `${Math.max(tokenCount > 0 ? 4 : 0, tokenPct)}%` }}
              />
            </div>
            <span className="tabular-nums whitespace-nowrap text-xs">{formatMeterLabel(tokenCount, contextMax)}</span>
          </button>
          {showEmptyRemoteChrome ? (
            <button
              type="button"
              className="btn btn-sm h-8 border border-base-300 bg-base-100"
              onClick={() => openSettingsSheet({ section: 'remotes', addRemote: true })}
            >
              Add remote
            </button>
          ) : showRemotesControl ? (
            <NavbarRoutingPicker
              seatKind="remote"
              aria-label="Remote"
              placeholder={remoteSelectPlaceholder(configuredRemoteRows.length, selectedRemoteId)}
              agents={configuredRemoteRows.map((remote) => ({
                id: remote.id,
                label: remoteOptionLabel(remote, remoteKinds(remotesCatalog)),
              }))}
              selectedAgent={selectedRemoteId}
              models={[]}
              selectedModel=""
              footerAction={{
                id: ADD_REMOTE_VALUE,
                label: 'Add remote',
                onSelect: () => openSettingsSheet({ section: 'remotes' }),
              }}
              onChange={(next) => {
                const nextId = next.agent
                setSelectedRemoteId(nextId)
                const remote = configuredRemoteRows.find((row) => row.id === nextId)
                if (bindingAgentId && remote) {
                  saveAgentRemoteBinding(bindingAgentId, {
                    id: remote.id,
                    kind: remote.kind || remote.id,
                  })
                  persistAgentDropdownChoice(bindingAgentId, { remote: remote.id })
                } else if (bindingAgentId && !nextId) {
                  saveAgentRemoteBinding(bindingAgentId, null)
                  persistAgentDropdownChoice(bindingAgentId, { remote: '' })
                }
                if (remoteFromUrl && nextId && nextId !== remoteFromUrl) {
                  setSearchParams((prev) => {
                    const params = new URLSearchParams(prev)
                    params.set('remote', nextId)
                    params.delete('session')
                    return params
                  })
                }
              }}
            />
          ) : null}
          {teamFromUrl ? (
            <select
              className="select select-sm h-8 max-w-[12rem] border border-base-300 bg-base-100"
              value={memberTarget}
              aria-label="Team members"
              onChange={(e) => {
                const value = e.target.value
                if (value === MANAGE_TEAMS_VALUE) {
                  if (teamFromUrl) {
                    window.location.assign(`${MANAGE_TEAMS_HREF}#${encodeURIComponent(teamFromUrl)}`)
                  } else {
                    window.location.assign(MANAGE_TEAMS_HREF)
                  }
                  return
                }
                const prev = memberTarget
                const prevMember = (selectedTeam?.members ?? []).find((m) => m.id === prev)
                const nextMember = (selectedTeam?.members ?? []).find((m) => m.id === value)
                const fromLabel = prev === ALL_MEMBERS_TARGET ? 'All members' : memberOptionLabel(prevMember || { id: prev, name: prev })
                const toLabel = value === ALL_MEMBERS_TARGET ? 'All members' : memberOptionLabel(nextMember || { id: value, name: value })
                setMemberTarget(value)
                if (teamFromUrl) {
                  setSearchParams(
                    (prevParams) => applyTeamMemberSessionParam(prevParams, teamFromUrl, value),
                    { replace: true },
                  )
                }
                recordDropdownChange('team', fromLabel, toLabel)
              }}
            >
              <option value={ALL_MEMBERS_TARGET}>All members</option>
              {(selectedTeam?.members ?? []).map((member) => (
                <option key={member.id} value={member.id}>
                  {memberOptionLabel(member)}
                </option>
              ))}
              <option disabled aria-hidden="true">
                ──────────
              </option>
              <option value={MANAGE_TEAMS_VALUE}>Manage Team</option>
            </select>
          ) : null}
          {isCliAgent ? (
            <NavbarRoutingPicker
              seatKind="cli"
              aria-label="CLI"
              agents={discoveredClis.map((cli) => ({ id: cli, label: cli }))}
              selectedAgent={currentCli}
              models={availableCliModels}
              selectedModel={currentCliModel}
              modelWarning={cliModelWarning}
              preferredEffort={persistedDropdown.effort}
              footerAction={{
                id: MANAGE_CLI_VALUE,
                label: 'Manage Cli',
                onSelect: () => {
                  window.location.assign(MANAGE_CLI_HREF)
                },
              }}
              onChange={applyCliRoutingChange}
            />
          ) : null}
          <div
            className="flex items-center gap-2"
            role="toolbar"
            aria-label="Chat tools"
          >
            <ComputerControlStub
              agentId={activeChatAgentId}
              agentName={selectedAgentName}
            />
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Compose team"
              aria-haspopup="dialog"
              title="Compose team"
              onClick={() => window.dispatchEvent(new CustomEvent(OPEN_TEAM_COMPOSER_EVENT))}
            >
              <Users className="h-4 w-4" aria-hidden="true" />
            </button>
            <ThemeToggle />
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Open settings"
              aria-haspopup="dialog"
              onClick={() => window.dispatchEvent(new CustomEvent(OPEN_SETTINGS_EVENT))}
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </header>

      {showRoleTip ? <RoleAgentTip onDismiss={dismissRoleTip} /> : null}

      <span role="status" aria-live="polite" aria-atomic="true" aria-label="Connection status" className="sr-only">
        {statusLabel}
      </span>

      <div
        ref={scrollBoxRef}
        className="os-chat-transcript min-h-0 flex-1 space-y-1 overflow-y-auto px-2 py-3 sm:px-3 select-none outline-none focus:outline-none flex flex-col justify-between relative"
        style={composerInsetCustomProperty(composerInsetPx) as CSSProperties}
        aria-live="polite"
        role="log"
        aria-label="Conversation"
        data-agent-kind={
          remoteFromUrl || isRemoteAgent || agentKind === 'remote'
            ? 'remote'
            : isCliAgent
              ? 'cli'
              : agentKind
        }
        data-messages-editable={messagesEditable && !isCliAgent && agentKind !== 'remote' ? 'true' : 'false'}
        data-composer-inset={composerInsetPx}
        tabIndex={0}
        onScroll={(e) => {
          pinnedToBottomRef.current = isPinnedToTranscriptBottom(e.currentTarget, composerInsetPx)
        }}
      >
        <div className="os-chat-messages space-y-1 flex-1" data-testid="chat-messages-container">
        {restoreNotice ? (
          <p className="os-chat-status" data-role="status" data-testid="chat-status">
            <span>{restoreNotice}</span>
          </p>
        ) : null}
        {messages.length === 0 && threadReady && hydrateError ? (
          <div
            className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/70"
            data-testid="chat-hydrate-error"
            role="alert"
          >
            <p className="text-sm font-medium">Could not load this chat</p>
            <p className="max-w-sm text-xs text-base-content/50">{hydrateError}</p>
          </div>
        ) : messages.length === 0 && threadReady ? (
          <div className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/45">
            <p className="text-sm">Message {selectedAgentName}</p>
            {showSupportJourneyChips ? (
              <>
                <p className="max-w-sm text-xs text-base-content/50">
                  Start with a team, a remote, or a CLI — one pane, no Settings maze.
                </p>
                <SuggestionChips
                  chips={supportJourneyChips}
                  disabled={chipsDisabled}
                  onChoose={chooseSuggestion}
                />
              </>
            ) : null}
          </div>
        ) : messages.length === 0 ? null : (
          <>
          {displayItems.map((item, idx) => {
            if (item.kind === 'summary') {
              if (hiddenSummaryIds.includes(item.summary.id)) return null
              return (
                <SummaryBlock
                  key={`sum-${item.summary.id}`}
                  summary={item.summary}
                  byId={summaryMap}
                  hiddenIds={hiddenSummaryIds}
                  onHide={(id) =>
                    setHiddenSummaryIds((prev) => (prev.includes(id) ? prev : [...prev, id]))
                  }
                />
              )
            }
            const message = item.message
            if (hiddenMessageKeys.includes(message.key)) return null
            const liveMessage = messages.find((row) => row.key === message.key)
            const teammateTask = liveMessage?.teammateTask
            if (teammateTask) {
              return (
                <div key={message.key} className="os-teammate-task-wrap my-2">
                  <TeammateTaskCard
                    event={teammateTask}
                    context={{
                      teamId: teamFromUrl,
                      team: selectedTeam,
                      remotes: configuredRemotes(remotesListQuery.data),
                    }}
                  />
                </div>
              )
            }
            const prOpened = liveMessage?.prOpened
            if (prOpened) {
              const openerId = prOpened.opener?.agentId
              const openerAgent = openerId
                ? blueprints.find((bp) => bp.id === openerId) ||
                  cliAgents.find((row) => row.id === openerId)
                : undefined
              const openerLabel =
                prOpened.opener?.name ||
                (openerAgent
                  ? editedAgentLabel({
                      id: openerId || '',
                      name: openerAgent.name || openerId,
                    })
                  : openerId)
              return (
                <div key={message.key} className="os-pr-opened-wrap my-2">
                  <PrOpenedCard
                    event={prOpened}
                    currentAgentId={activeChatAgentId}
                    currentConversationId={conversationId}
                    openerName={openerLabel}
                    openerAvatarSrc={(openerAgent as { avatar_path?: string } | undefined)?.avatar_path}
                    onJumpToOpener={jumpToPrOpener}
                  />
                </div>
              )
            }
            if (message.kind === 'prior_history') {
              return (
                <SystemPreloadPill
                  key={message.key}
                  text={message.text}
                  label="Prior history"
                  onRemove={() =>
                    setHiddenMessageKeys((prev) =>
                      prev.includes(message.key) ? prev : [...prev, message.key],
                    )
                  }
                />
              )
            }
            if (isStatusRole(message.role)) {
              const statusMs = parseCreatedAtMs(message.ts)
              if (message.rateLimit) {
                return (
                  <RateLimitStatusLine
                    key={message.key}
                    wait={message.rateLimit}
                    nowMs={nowMs}
                    ts={message.ts}
                    timeLabel={statusMs != null ? formatGapLabel(statusMs) : undefined}
                  />
                )
              }
              return (
                <p
                  key={message.key}
                  className="os-chat-status"
                  data-role="status"
                  data-testid="chat-status"
                  data-ts={message.ts || undefined}
                >
                  <span>{message.text}</span>
                  {statusMs != null ? (
                    <time dateTime={message.ts} data-testid="chat-status-time">
                      {formatGapLabel(statusMs)}
                    </time>
                  ) : null}
                </p>
              )
            }
            const isLast = idx === displayItems.length - 1
            const retryEnabled =
              SHOW_MESSAGE_ACTIONS &&
              isLast &&
              message.role === 'assistant' &&
              !message.streaming &&
              lastUserTextRef.current.length > 0
            const messageIndex = messages.findIndex((row) => row.key === message.key)
            const canEditThis =
              messagesEditable &&
              !selectedCli &&
              !message.streaming &&
              (message.role === 'user' || message.role === 'assistant')
            const rawOffset = rawOffsetForMessage(messages, message.key)
            const showStartMarker =
              contextMeta.start_offset > 0 && rawOffset === contextMeta.start_offset
            return (
              <div
                key={message.key}
                onContextMenu={(e) => {
                  if (message.role === 'system') return
                  handleBubbleContextMenu(e, message)
                }}
              >
                {showStartMarker ? (
                  <div
                    className="my-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-base-content/50"
                    data-testid="context-starts-here"
                    role="separator"
                    aria-label={START_CONTEXT_FROM_HERE_LABEL}
                  >
                    <span className="h-px flex-1 bg-base-300" />
                    <span>{START_CONTEXT_FROM_HERE_LABEL}</span>
                    <span className="h-px flex-1 bg-base-300" />
                  </div>
                ) : null}
                <ChatMessageBubble
                  role={message.role}
                  agentName={selectedAgentName}
                  text={message.text}
                  streaming={message.streaming}
                  edited={message.edited}
                  skillCatalog={skillCatalog}
                  onOpenSkill={setOpenSkillName}
                  onRemoveCard={() =>
                    setHiddenMessageKeys((prev) =>
                      prev.includes(message.key) ? prev : [...prev, message.key],
                    )
                  }
                  canEdit={canEditThis}
                  canCompress={
                    !message.streaming &&
                    (message.role === 'user' || message.role === 'assistant') &&
                    rawOffsetForMessage(messages, message.key) >= 0
                  }
                  contextStrategy={contextStrategy}
                  editing={editingKey === message.key}
                  onStartEdit={() => setEditingKey(message.key)}
                  onCancelEdit={() => setEditingKey(null)}
                  onSaveEdit={(next) => {
                    if (messageIndex >= 0) void saveEditedMessage(messageIndex, next)
                  }}
                  onCompressToHere={() => {
                    handleContextToHere(message)
                  }}
                >
                  {(message.tools ?? []).map((tool) => (
                    <ToolCallPopup
                      key={tool.id}
                      tool={tool}
                      onDecision={(decision) => {
                        const agentId = tool.agentId || selectedBlueprint || threadKey
                        if (decision === 'always') rememberAlwaysAllow(agentId, tool.name)
                        sendToolDecision(tool.id, decision)
                        attachToolToThread({
                          ...tool,
                          needsApproval: false,
                          status:
                            decision === 'deny'
                              ? 'denied'
                              : decision === 'always' || decision === 'allow'
                                ? 'allowed'
                                : tool.status,
                        })
                      }}
                    />
                  ))}
                </ChatMessageBubble>
                {message.role === 'assistant' && !message.streaming && message.text.trim() ? (
                  <ReadAloudButton text={message.text} />
                ) : null}
                {SHOW_MESSAGE_ACTIONS && message.role === 'assistant' && !message.streaming && (
                  <ChatMessageActions
                    text={message.text}
                    onRetry={
                      retryEnabled
                        ? () => {
                            sendText(lastUserTextRef.current)
                          }
                        : undefined
                    }
                  />
                )}
              </div>
            )
          })}
          </>
        )}
        <div ref={listEndRef} />
        </div>

        <QueuedSendPane
          rows={queued.rows}
          maxHeightPx={queuedPaneMaxHeightPx(transcriptHeightPx)}
          onChangeText={queued.update}
          onDelete={queued.remove}
          onHoldIdsChange={setQueuedHoldIds}
        />

        <div
          ref={bottomDockRef}
          className="os-chat-bottom-dock sticky bottom-0 z-20 -mx-2 sm:-mx-3 -mb-3 bg-base-100 border-t border-base-content/5"
          data-testid="chat-bottom-dock"
        >
          {showSuggestionChips ? (
            <SuggestionChips
              chips={suggestionChips}
              disabled={chipsDisabled}
              onChoose={chooseSuggestion}
            />
          ) : null}
          {streamingMessage ? (
            <div
              className="os-composer-working"
              data-testid="composer-working-indicator"
              role="status"
              aria-live="polite"
              aria-label={workingTip}
            >
              <span className="tooltip tooltip-top os-composer-working__tip" data-tip={workingTip}>
                <span className="os-composer-working__avatar">
                  <AgentAvatar
                    src={selectedAgent?.avatar_path}
                    agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                    active={true}
                    size="xs"
                    className="shrink-0"
                  />
                </span>
              </span>
            </div>
          ) : null}
          <form onSubmit={handleSend} className="os-composer-wrap">
            <div className="relative" ref={composerWrapRef}>
              <ComposerSlashPopup
                open={isSlashOpen}
                query={slashQuery}
                items={filteredSlashItems}
                selectedIndex={slashSelectedIndex}
                onSelectIndex={setSlashSelectedIndex}
                onSelectItem={handleSelectSlashItem}
                recentIds={recentSlashIds}
              />
              <div className={`os-composer ${replyTarget ? 'os-composer--reply flex-col items-stretch !rounded-2xl !p-2' : ''}`}>
                {replyTarget && (
                  <div
                    className="flex items-center justify-between gap-2 px-2.5 py-1 text-xs text-base-content/70 border-b border-base-content/10 mb-1 w-full"
                    data-testid="composer-reply-strip"
                  >
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <Reply className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden="true" />
                      <span className="truncate" title={replyTarget.text}>
                        {replyTarget.speaker ? (
                          <strong className="font-semibold text-base-content/90 mr-1">
                            {replyTarget.speaker}:
                          </strong>
                        ) : null}
                        <span className="opacity-75">
                          {replyTarget.text.replace(/\s+/g, ' ').slice(0, 100)}
                        </span>
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs btn-circle h-5 w-5 min-h-0 text-base-content/60 hover:text-base-content"
                      aria-label="Dismiss reply"
                      data-testid="dismiss-reply-button"
                      onClick={() => setReplyTarget(null)}
                    >
                      ×
                    </button>
                  </div>
                )}
                <div className={`flex items-center gap-1.5 min-h-0 ${replyTarget ? 'w-full' : 'flex-1'}`}>
                  <div className="relative" ref={plusRef}>
                    <button
                      type="button"
                      className="os-composer__icon"
                      aria-label="Add"
                      aria-haspopup="menu"
                      aria-expanded={plusOpen}
                      onClick={() => setPlusOpen((value) => !value)}
                    >
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </button>
                    {plusOpen && (
                      <ul
                        role="menu"
                        aria-label="Chat actions"
                        className="os-plus-menu"
                      >
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            className="os-plus-menu__item"
                            onClick={() => {
                              void handleCompact()
                            }}
                          >
                            <Layers className="h-4 w-4" aria-hidden="true" />
                            Compact
                          </button>
                        </li>
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            className="os-plus-menu__item"
                            onClick={() => {
                              setPlusOpen(false)
                              window.dispatchEvent(new CustomEvent(OPEN_TEAM_COMPOSER_EVENT))
                            }}
                          >
                            <Users className="h-4 w-4" aria-hidden="true" />
                            Compose team
                          </button>
                        </li>
                      </ul>
                    )}
                  </div>
                  <textarea
                    ref={composerRef}
                    rows={1}
                    className="os-composer__input"
                    placeholder={composerPlaceholder}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleComposerKeyDown}
                    disabled={status !== 'open'}
                    aria-label="Chat message"
                    aria-haspopup="listbox"
                    aria-expanded={isSlashOpen}
                    aria-controls={isSlashOpen ? 'composer-slash-menu' : undefined}
                  />
                  {!input ? (
                    <kbd
                      className="os-composer__hint kbd kbd-xs"
                      data-testid="composer-send-hint"
                      title="Enter to send"
                    >
                      ↵
                    </kbd>
                  ) : (
                    <kbd
                      className="os-composer__hint kbd kbd-xs"
                      data-testid="composer-clear-hint"
                      title="Esc to clear"
                    >
                      Esc
                    </kbd>
                  )}
                  <button
                    type="button"
                    className="os-composer__icon"
                    aria-label={sttListening ? 'Stop voice input' : 'Voice input'}
                    aria-pressed={sttListening}
                    data-testid="composer-mic"
                    data-stt-path={sttPathUsed ?? undefined}
                    onClick={handleMic}
                  >
                    <Mic className="h-4 w-4" aria-hidden="true" />
                  </button>
                  {sttPathUsed ? (
                    <span className="sr-only" data-testid="stt-path">
                      Voice input used {describeSpeechPath(sttPathUsed, 'stt')}
                    </span>
                  ) : null}
                  {hasSendableDraft ? (
                    <button
                      type="submit"
                      className="os-composer__send"
                      aria-label="Send"
                    >
                      <ArrowUp className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>

      {contextMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            data-testid="context-menu-backdrop"
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault()
              setContextMenu(null)
            }}
          />
          <div
            role="menu"
            aria-label="Message actions"
            data-testid="message-context-menu"
            className="fixed z-50 min-w-32 rounded-lg border border-base-300 bg-base-100 p-1 shadow-xl text-sm"
            style={{
              left: `${Math.min(contextMenu.x, typeof window !== 'undefined' ? window.innerWidth - 150 : 0)}px`,
              top: `${Math.min(contextMenu.y, typeof window !== 'undefined' ? window.innerHeight - 80 : 0)}px`,
            }}
          >
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
              data-testid="context-menu-reply"
              onClick={() => {
                setReplyTarget({
                  key: contextMenu.message.key,
                  role: contextMenu.message.role,
                  speaker:
                    contextMenu.message.role === 'user' ? 'You' : selectedAgentName,
                  text: contextMenu.message.text,
                })
                setContextMenu(null)
                composerRef.current?.focus()
              }}
            >
              <Reply className="h-4 w-4 opacity-70" aria-hidden="true" />
              Reply
            </button>
            {(contextMenu.message.role === 'user' || contextMenu.message.role === 'assistant') &&
            !contextMenu.message.streaming ? (
              <button
                type="button"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
                data-testid={
                  contextStrategy === 'cull'
                    ? 'context-menu-start-from-here'
                    : 'context-menu-compress-to-here'
                }
                title={
                  contextStrategy === 'cull' ? START_CONTEXT_FROM_HERE_TOOLTIP : 'Compress to here'
                }
                onClick={() => {
                  handleContextToHere(contextMenu.message)
                }}
              >
                <FoldVertical className="h-4 w-4 opacity-70" aria-hidden="true" />
                {contextStrategy === 'cull' ? START_CONTEXT_FROM_HERE_LABEL : 'Compress to here'}
              </button>
            ) : null}
          </div>
        </>
      )}

      <TokenDiagnosticsModal
        isOpen={tokenDiagOpen}
        onClose={() => setTokenDiagOpen(false)}
        agentName={selectedAgentName}
        conversationId={conversationId}
        tokenCount={tokenCount}
        contextMax={contextMax}
        inputTokens={inputTokens}
        outputTokens={outputTokens}
        compactsCount={summaries.length}
        toolCallsCount={toolCallsCount}
        messageCount={messages.length}
        userMessageCount={userMessageCount}
        assistantMessageCount={assistantMessageCount}
        contextStrategy={contextStrategy}
        lastContextEvent={contextMeta.last_event}
      />

      <SkillPopup
        name={openSkillName}
        open={openSkillName != null}
        onClose={() => setOpenSkillName(null)}
        catalog={skillCatalog}
      />

      <ConfirmModal
        isOpen={startFromHereWarning != null}
        onClose={() => setStartFromHereWarning(null)}
        onConfirm={async () => {
          const pending = startFromHereWarning
          if (!pending) return
          await applyStartFromHere(pending.message, true)
        }}
        title={START_CONTEXT_FROM_HERE_LABEL}
        confirmText="Confirm"
        cancelText="Cancel"
        confirmVariant="warning"
        aria-label="Start context from here warning"
      >
        <p className="text-sm" data-testid="start-from-here-warning">
          {startFromHereWarning?.copy}
        </p>
      </ConfirmModal>
    </div>
  )
}

function SummaryBlock({
  summary,
  byId,
  depth = 0,
  hiddenIds = [],
  onHide,
}: {
  summary: ConversationSummary
  byId: Record<number, ConversationSummary>
  depth?: number
  hiddenIds?: number[]
  onHide?: (id: number) => void
}) {
  const parent =
    summary.parent_summary_id != null ? byId[summary.parent_summary_id] : undefined
  const replaced =
    summary.replaced_count ?? summary.span.end - summary.span.start + 1
  return (
    <CompactSummaryCard
      title="Summary"
      body={summary.body}
      meta={`Replaced ${replaced} turns`}
      className={depth > 0 ? 'chat-summary chat-summary--nested' : 'chat-summary'}
      onRemove={() => onHide?.(summary.id)}
      nested={
        parent && !hiddenIds.includes(parent.id) ? (
          <SummaryBlock
            summary={parent}
            byId={byId}
            depth={depth + 1}
            hiddenIds={hiddenIds}
            onHide={onHide}
          />
        ) : null
      }
    />
  )
}

export default ChatPage
