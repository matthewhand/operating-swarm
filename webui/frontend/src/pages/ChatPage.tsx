import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Check, ChevronRight, FoldVertical, Layers, Mic, Palette, PanelLeft, Pencil, Plus, Reply, Settings, Square, Users } from 'lucide-react'
import AgentAvatar from '../components/AgentAvatar'
import { ConfirmModal, TOAST_KIND_WS_DISCONNECT, useToast } from '../components/DaisyUI'
import ThemeToggle from '../components/ThemeToggle'
import { OPEN_SETTINGS_EVENT, openSettingsSheet, settingsDetailFromQuery } from '../components/SettingsSheet'
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
import {
  EMPTY_VOICE_BIND,
  applyVoiceBindToSpeechSettings,
  nextAutoSpeakText,
  parseVoiceBind,
  type AgentVoiceBind,
} from '../lib/agentVoiceBind'
import { openTeamEditor } from '../components/TeamEditor'
import PersonaRoster from '../components/PersonaRoster'
import { declaredRosterForTeam } from '../lib/declaredRoster'
import {
  fetchUserPrefs,
  persistAgentDropdownChoice,
  USER_PREFS_CHANGED_EVENT,
  type UserPrefs,
} from '../lib/userPrefs'
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
import {
  BUBBLE_THEME_LABELS,
  BUBBLE_THEMES,
  getBubbleTheme,
  loadBubbleTheme,
  saveBubbleTheme,
  type BubbleTheme,
} from '../lib/bubbleTheme'
import ReadAloudButton from '../components/ReadAloudButton'
import { SkillPopup } from '../components/SkillPopup'
import MessageRowActions from '../components/MessageRowActions'
import CliSessionSwitcher from '../components/CliSessionSwitcher'
import SessionPicker from '../components/SessionPicker'
import {
  fetchRemoteThreadSessions,
  remoteChatTurnParams,
  remoteListsSessions,
} from '../lib/remoteSessions'
import type { MemberSession } from '../lib/sessionPicker'
import { SystemPreloadPill } from '../components/SystemPreloadPill'
import { CompactSummaryCard } from '../components/CompactSummaryCard'
import { ComposerSlashPopup } from '../components/ComposerSlashPopup'
import ComposerAttachChips from '../components/ComposerAttachChips'
import {
  attachmentCaption,
  createPendingAttachment,
  imageFilesFromClipboard,
  readyAttachmentIds,
  revokePreviewUrl,
  uploadChatAttachment,
  type PendingAttachment,
} from '../lib/chatAttachments'
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
  operateRemote,
} from '../lib/api'
import {
  appendTranscript,
  listenSystemStt,
  recordMicrophoneAudio,
  resolveSttPath,
  resolveTtsPath,
  speakCustom,
  speakSystem,
  sttUnavailableMessage,
  transcribeCustomBlob,
  type SpeechPath,
} from '../lib/speechRuntime'
import { SPEECH_QUERY_KEY, describeSpeechPath, parseSpeechSettings } from '../lib/speechSettings'
import {
  AGENT_CONVERSATION_EVENT,
  agentIdFromBlueprint,
  appendAgentMessage,
  clearAgentThread,
  compactAgentThread,
  conversationIdForAgent,
  conversationIdForTask,
  DEFAULT_AGENT_ID,
  fetchAgentThread,
  startContextFromHere,
  patchAgentMessage,
  peekConversationIdForAgent,
  setConversationIdForAgent,
  toggleSummaryInContext,
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
  buildCancelTurnFrame,
  buildChatWsEditFrame,
  buildChatWsFrame,
  buildChatWsUrl,
  buildQuestionAnswerFrame,
  buildToolDecisionFrame,
  newConversationId,
  cliAgentChatParams,
  mergeChatSendParams,
  parseChatWsMessage,
  summarizeUnknownWsFrame,
  type ChatWsEvent,
} from '../lib/chatWs'
import { ContextUsageBadge } from '../components/ContextUsageBadge'
import {
  fetchContextUsage,
  publishContextUsage,
  type ContextUsage,
} from '../lib/contextUsage'
import { QuestionCard } from '../components/QuestionCard'
import {
  parseDecisionQuestion,
  stripDecisionQuestion,
  type DecisionQuestion,
} from '../lib/decisionQuestion'
import { loadElicitQuestions } from '../lib/elicitQuestions'
import { ToolCallPopup } from '../components/ToolCallPopup'
import GenerationsPanel, { type PanelToolCall } from '../components/GenerationsPanel'
import { PrOpenedCard } from '../components/PrOpenedCard'
import { TeammateTaskCard } from '../components/TeammateTaskCard'
import { SuggestionChips } from '../components/SuggestionChips'
import { DemoTourBanner } from '../components/DemoTourBanner'
import { isDemoMode } from '../lib/demo/mode'
import { demoSuggestionChips } from '../lib/demo/scenarios'
import {
  openerChatSearch,
  parsePrOpened,
  type PrOpenedEvent,
  type PrOpenedOpener,
} from '../lib/prOpened'
import { parseTeammateTask, type TeammateTaskEvent } from '../lib/teammateTask'
import SubagentFanOutBlock from '../components/SubagentFanOutBlock'
import { parseSubagentFanOut, type SubagentFanOutData } from '../lib/subagentFanOut'
import { registerDynamicSubagent } from '../lib/dynamicSubagents'
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
  ALL_MEMBERS_PARAM,
  ALL_MEMBERS_TARGET,
  MANAGE_TEAMS_HREF,
  MANAGE_TEAMS_VALUE,
  applyTeamMemberSessionParam,
  fetchTeamRosters,
  isAllMembersChoice,
  parseTeamRosters,
  memberOptionLabel,
  teamHideId,
  teamThreadId,
} from '../lib/teamRosters'
import { defaultSessionForTeam } from '../lib/sessionPicker'
import {
  OMB_BOT_REQUIRED_GAP,
  OMB_NO_AGENTS_WARNING,
  OMB_SELECT_AGENT_WARNING,
  ombBotsFromOperate,
  ombNavbarOptions,
  ombSendTarget,
} from '../lib/ombBots'
import { isOpenMousBotKind } from '../lib/remoteKinds'
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId } from '../lib/remotesCatalog'
import {
  ADD_REMOTE_VALUE,
  configuredRemotes,
  remoteKinds,
  remoteOptionLabel,
  remoteSelectPlaceholder,
} from '../lib/remotes'
import { enabledToolsParam } from '../lib/chatPluginTools'
import { railSectionsParam } from '../lib/railSections'
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
import { DefaultLlmTip } from '../components/DefaultLlmTip'
import { CliSessionRecoveryBanner } from '../components/CliSessionRecoveryBanner'
import { lastTurnNeedsRecovery } from '../lib/cliSessionRecovery'
import {
  hydrateRoleAgentTipDismissed,
  persistRoleAgentTipDismissed,
  isRoleAgentTipDismissed,
  shouldShowRoleAgentTip,
} from '../lib/roleAgentTip'
import {
  hydrateDefaultLlmTipDismissed,
  persistDefaultLlmTipDismissed,
  isDefaultLlmTipDismissed,
  shouldShowDefaultLlmTip,
} from '../lib/defaultLlmTip'
import {
  agentHasRole,
  agentRole,
  exampleRoleAgents,
  isChiefOfStaff,
  isExampleRole,
  roleBadgeLabel,
  roleCssClass,
} from '../lib/agentRoles'
import { assignedBlueprintId, AGENT_EDITS_CHANGED_EVENT, editedAgentLabel, loadAgentEdit, loadInferenceList } from '../lib/agentEdits'
import { isRemoteCapableCli, remoteEndpointLabel } from '../lib/cliRemote'
import { buildSkillParams, parseComposerSkillNames } from '../lib/skills'
import { chatFolderParams } from '../lib/agentFolder'
import { navbarWorkspaceSubtitle } from '../lib/agentWorkspace'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import { nextInferenceIndex, serializeInferenceList } from '../lib/inferenceList'
import {
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
import { ChatNewRule } from '../components/ChatLogMarkers'
import {
  countableChatCount,
  effectiveUnreadWatermark,
  firstUnreadMessageKey,
} from '../lib/chatLog'
import { loadLastRead, saveLastRead } from '../lib/chatLastRead'
import {
  UNREAD_CHANGED_EVENT,
  isAgentUnread,
  loadUnreadAgentIds,
  markAgentRead,
  markAgentUnread,
} from '../lib/unreadAgents'
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
  apiModelOptionsFromProfiles,
  discoverChatClis,
  honestChatCliModels,
  isApiBlueprintId,
  isCliAgentContext,
  isCliBlueprintId,
  preferredChatCli,
  MANAGE_CLI_VALUE,
} from '../lib/cliAgentContext'
import { resolveProductModes } from '../lib/productModes'
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
  /** Blocking ``ask_user`` card or a non-blocking ```question fence. */
  question?: DecisionQuestion
  questionBlocking?: boolean
  questionAnswered?: boolean
  edited?: boolean
  /** REQ-71 chrome — structured PR-opened tool result, not markdown. */
  prOpened?: PrOpenedEvent
  /** REQ-84 chrome — team task whose worker is a configured remote. */
  teammateTask?: TeammateTaskEvent
  subagentFanOut?: SubagentFanOutData
  /** REQ-104 — expandable archive of the previous swarm thread. */
  kind?: 'prior_history'
  /** Persist/reload timestamp (ISO). Status/info chrome shows this. */
  ts?: string
  /** REQ-88 — provider queue wait; click opens that provider's rate-limit fields. */
  rateLimit?: RateLimitWait
  /** Terminal CLI/config failure — recovery banner (#274). */
  fatalConfigError?: boolean
}

function chatMessageFromThreadRow(
  message: {
    role: string
    content: string
    edited?: boolean
    kind?: string
    ts?: string
    rate_limit?: RateLimitWait
    fatal_config_error?: boolean
  },
  index: number,
): ChatMessage {
  const prOpened = parsePrOpened(message.content) ?? undefined
  const teammateTask = parseTeammateTask(message.content) ?? undefined
  const subagentFanOut = parseSubagentFanOut(message.content) ?? undefined
  const prior = message.kind === 'prior_history'
  return {
    key: `hist-${index}-${message.role}`,
    role: prior ? 'system' : asTranscriptRole(message.role),
    text: prOpened || teammateTask || subagentFanOut ? '' : message.content,
    streaming: false,
    edited: message.edited === true,
    prOpened,
    teammateTask,
    subagentFanOut,
    kind: prior ? 'prior_history' : undefined,
    ts: message.ts,
    rateLimit: isRateLimitWait(message.rate_limit) ? message.rate_limit : undefined,
    fatalConfigError: message.fatal_config_error === true,
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

function warnStatusPersistFailure(err: unknown): void {
  const reason = err instanceof Error ? err.message : String(err)
  console.warn('Could not persist status line', reason)
}

const ChatPage = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToast, dismissByKind } = useToast()
  const { narrow, railOpen, openRail } = useRailChrome()
  const teamFromUrl = searchParams.get('team') ?? ''
  const remoteFromUrl = searchParams.get('remote') ?? ''
  const sessionFromUrl = searchParams.get('session') ?? ''
  // #288: an explicit "All members" pick rides `?members=all` so a reload keeps it
  // instead of re-defaulting to the team's nominated seat.
  const allMembersFromUrl = isAllMembersChoice(searchParams.get(ALL_MEMBERS_PARAM))
  const settingsQuery = searchParams.get('settings')
  const settingsQueryOpenedRef = useRef(false)
  useEffect(() => {
    if (settingsQueryOpenedRef.current) return
    const detail = settingsDetailFromQuery(settingsQuery)
    if (detail == null) return
    settingsQueryOpenedRef.current = true
    openSettingsSheet(detail)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('settings')
      return next
    }, { replace: true })
  }, [settingsQuery, setSearchParams])
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
  const [voiceBind, setVoiceBind] = useState<AgentVoiceBind>(EMPTY_VOICE_BIND)
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
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null)
  const [startFromHereWarning, setStartFromHereWarning] = useState<{
    message: ChatMessage
    copy: string
    startOffset: number
  } | null>(null)
  const [input, setInput] = useState('')
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const [sttListening, setSttListening] = useState(false)
  const [sttPathUsed, setSttPathUsed] = useState<SpeechPath | null>(null)
  const sttStopRef = useRef<(() => void) | null>(null)
  const spokenReplyKeysRef = useRef<Set<string>>(new Set())
  const autoSpeakHydratedRef = useRef(false)
  const [replyTarget, setReplyTarget] = useState<ReplyTarget | null>(null)
  const [contextMenu, setContextMenu] = useState<MessageContextMenuState | null>(null)
  const [bubbleTheme, setBubbleTheme] = useState<BubbleTheme>(() => loadBubbleTheme())
  const [bubbleThemeMenuOpen, setBubbleThemeMenuOpen] = useState(false)
  /** REQ-213: view-only hide. Raw transcript / summary tree on disk stay. */
  const [hiddenSummaryIds, setHiddenSummaryIds] = useState<number[]>([])
  const [hiddenMessageKeys, setHiddenMessageKeys] = useState<string[]>([])
  const [slashDismissed, setSlashDismissed] = useState(false)
  const [slashSelectedIndex, setSlashSelectedIndex] = useState(0)
  const [recentSlashIds, setRecentSlashIds] = useState<string[]>(() => getRecentSlashIds())
  const [roleTipDismissed, setRoleTipDismissed] = useState(isRoleAgentTipDismissed)
  const [defaultLlmTipDismissed, setDefaultLlmTipDismissed] = useState(isDefaultLlmTipDismissed)
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
  const [remoteThreadPicker, setRemoteThreadPicker] = useState<MemberSession[] | null>(null)
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
  const [unreadIds, setUnreadIds] = useState<string[]>(() => loadUnreadAgentIds())
  const seatUnread = Boolean(activeChatAgentId && isAgentUnread(activeChatAgentId, unreadIds))
  const newBeforeKey = useMemo(() => {
    if (!seatUnread || !activeChatAgentId) return null
    const stored = loadLastRead(activeChatAgentId, conversationId)
    const watermark = effectiveUnreadWatermark(
      true,
      stored?.messageCount ?? null,
      countableChatCount(messages),
    )
    return firstUnreadMessageKey(messages, watermark)
  }, [seatUnread, activeChatAgentId, conversationId, messages])
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

  // #214: persist the include-in-context tick; optimistic update, honest revert.
  const handleToggleSummaryContext = useCallback(
    async (summaryId: number, include: boolean) => {
      const threadSummaries = summariesByThread[threadKey] ?? []
      setSummariesByThread((prev) => ({
        ...prev,
        [threadKey]: (prev[threadKey] ?? []).map((row) =>
          row.id === summaryId ? { ...row, include_in_context: include } : row,
        ),
      }))
      try {
        const result = await toggleSummaryInContext({ summaryId, includeInContext: include })
        if (result.usage) {
          publishContextUsage(result.usage)
          setContextUsage(result.usage)
        }
      } catch {
        setSummariesByThread((prev) => ({ ...prev, [threadKey]: threadSummaries }))
      }
    },
    [summariesByThread, threadKey],
  )

  const handleSaveSummary = useCallback(
    (summaryId: number, nextText: string) => {
      if (!messagesEditable) return
      setSummariesByThread((prev) => ({
        ...prev,
        [threadKey]: (prev[threadKey] ?? []).map((row) =>
          row.id === summaryId ? { ...row, body: nextText } : row,
        ),
      }))
    },
    [messagesEditable, threadKey],
  )

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
  // #229: a seat/session switch starts with clean working chrome — the old
  // seat's in-flight turn must never leak into the new seat's UI. The old
  // socket's close resets its own thread's streaming flag; this covers the
  // awaiting side. Stale closes from a replaced socket are harmless because
  // isWorking also derives from the (per-thread) streaming flag.
  useEffect(() => {
    setAwaitingAssistant(false)
  }, [threadKey, conversationId])
  // #229: when the seat changes or the page unmounts, clear the working
  // state published for the departed seat so its rail avatar stops animating
  // (the working set is cross-seat; nothing else would clear the old id).
  const runStateSeatRef = useRef<string | null>(null)
  useEffect(() => {
    runStateSeatRef.current = activeChatAgentId
    return () => {
      if (runStateSeatRef.current) notifyCliRunState(runStateSeatRef.current, false)
    }
  }, [activeChatAgentId])
  // #224: agent-first — workings live in the on-demand panel, not the transcript.
  const [generationsOpen, setGenerationsOpen] = useState(false)
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
    if (!contextMenu) {
      setBubbleThemeMenuOpen(false)
      return
    }
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
  // #108: only rail rows whose kind is actually 'cli' may drive the CLI
  // picker. api_agent is a rail row too (kind 'api') and must never match.
  const selectedCli = cliAgents.find(
    (row) => row.id === selectedBlueprint && row.kind !== 'api',
  )
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
  const workspaceSubtitle =
    teamFromUrl || remoteFromUrl ? '' : navbarWorkspaceSubtitle(selectedBlueprint)
  // #69: the top bar shows the agent NAME; an assigned role rides beside it as
  // its own badge so a role seat can never look like it renamed the agent.
  const headerRole = agentRole({
    id: selectedBlueprint,
    name: selectedAgentName,
    role: selectedAgent?.role,
  })
  const headerRoleLabel = roleBadgeLabel(headerRole)
  const showHeaderRole =
    !teamFromUrl &&
    !remoteFromUrl &&
    agentHasRole({ id: selectedBlueprint, name: selectedAgentName, role: selectedAgent?.role })
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
  const dismissDefaultLlmTip = useCallback(() => {
    void persistDefaultLlmTipDismissed()
    setDefaultLlmTipDismissed(true)
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

  const productModes = useMemo(
    () => resolveProductModes(cliQuery.data),
    [cliQuery.data],
  )
  const showRemotesControl = productModes.remote && (isRemoteAgent || isRemoteBackedTeam)
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
  const ombRemoteId = isOpenMousBotKind(selectedRemoteId)
    ? selectedRemoteId
    : isOpenMousBotKind(remoteFromUrl)
      ? remoteFromUrl
      : ''
  const ombListQuery = useQuery({
    queryKey: ['omb-operate-list', ombRemoteId],
    queryFn: () => operateRemote(ombRemoteId, { op: 'list' }, { timeoutMs: 12000 }),
    enabled: showRemotesControl && Boolean(ombRemoteId),
    retry: 1,
  })
  const ombBots = useMemo(
    () => (ombRemoteId ? ombBotsFromOperate(ombListQuery.data?.data) : []),
    [ombRemoteId, ombListQuery.data],
  )
  const ombNavbarAgents = useMemo(() => ombNavbarOptions(ombBots), [ombBots])
  const ombModelWarning = !ombRemoteId
    ? null
    : ombListQuery.isError
      ? ombListQuery.error instanceof Error
        ? ombListQuery.error.message
        : 'OpenMousBot agent list failed'
      : ombListQuery.isSuccess && ombListQuery.data?.ok === false
        ? ombListQuery.data.detail || OMB_NO_AGENTS_WARNING
        : ombListQuery.isSuccess && ombBots.length === 0
          ? OMB_NO_AGENTS_WARNING
          : null
  const ombSelectedBotId = ombSendTarget(sessionFromUrl, ombRemoteId || remoteFromUrl)

  const isCliAgent = Boolean(
    !teamFromUrl &&
      !remoteFromUrl &&
      !isRemoteBackedTeam &&
      !isRemoteAgent &&
      !isApiBlueprintId(selectedBlueprint) &&
      (selectedCli ||
        agentKind === 'cli' ||
        isCliBlueprintId(selectedBlueprint) ||
        isCliAgentContext({
          blueprintId: selectedBlueprint,
          searchParams,
        })),
  )

  const supportSelected = Boolean(
    !teamFromUrl &&
      !remoteFromUrl &&
      (isSupportJourneyConsumer(selectedBlueprint) ||
        isSupportAgent({
          id: selectedBlueprint || SUPPORT_AGENT_ID,
          name: selectedAgentName,
        })),
  )

  const isApiAgent = Boolean(
    !teamFromUrl &&
      !remoteFromUrl &&
      !isRemoteBackedTeam &&
      !isRemoteAgent &&
      !isCliAgent,
  )
  const showContextUsage = isApiAgent || agentKind === 'blueprint'

  useEffect(() => {
    if (!showContextUsage || !conversationId) {
      setContextUsage(null)
      return
    }
    let cancelled = false
    const agent = teamFromUrl || agentIdFromBlueprint(selectedBlueprint)
    const modelId = (searchParams.get('model') ?? '').trim() || undefined
    void fetchContextUsage({ agentId: agent, conversationId, modelId })
      .then((usage) => {
        if (cancelled) return
        publishContextUsage(usage)
        setContextUsage(usage)
      })
      .catch(() => {
        if (!cancelled) setContextUsage(null)
      })
    return () => {
      cancelled = true
    }
  }, [showContextUsage, conversationId, teamFromUrl, selectedBlueprint, searchParams])

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
    if (cliModelsQuery.isFetching || cliModelsQuery.isLoading) return null
    if (cliModelProbe.warning) return cliModelProbe.warning
    if (cliModelsQuery.isError) return 'Model probe failed'
    if (cliModelsQuery.isFetched && currentCli) return 'No models discovered'
    return null
  }, [
    availableCliModels.length,
    cliModelProbe.warning,
    cliModelsQuery.isError,
    cliModelsQuery.isFetched,
    cliModelsQuery.isFetching,
    cliModelsQuery.isLoading,
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
      ).catch(warnStatusPersistFailure)
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
              ).catch(warnStatusPersistFailure)
            })
            .catch((err: unknown) => {
              const reason = err instanceof Error ? err.message : 'Request failed'
              addToast({
                type: 'error',
                title: 'Could not hop CLI session',
                message: reason,
              })
              const statusText = `Could not hop CLI session: ${reason}`
              const statusMsg: ChatMessage = {
                key: `hop-fail-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                role: 'status',
                text: statusText,
                streaming: false,
                ts: new Date().toISOString(),
              }
              setThreads((prev) => ({
                ...prev,
                [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
              }))
            })
        } else {
          recordDropdownChange('cli', next.previous.agent, next.agent)
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
    [addToast, dropdownAgentId, recordDropdownChange, setSearchParams, teamFromUrl, remoteFromUrl, selectedBlueprint, threadKey],
  )

  // #108: API seats route via LLM profiles. A pick lands in the same
  // ?model= channel the WS send path already reads, plus the per-agent
  // dropdown memory ('api' field) so the choice survives navigation.
  const applyApiRoutingChange = useCallback(
    (next: RoutingPathChange) => {
      if (next.changed !== 'agent') return
      const model = next.agent.trim()
      persistAgentDropdownChoice(dropdownAgentId, {
        api: model,
        model: '',
        effort: '',
      })
      setSearchParams(
        (prevParams) => {
          const nextParams = new URLSearchParams(prevParams)
          if (model) nextParams.set('model', model)
          else nextParams.delete('model')
          return nextParams
        },
        { replace: true },
      )
      recordDropdownChange('api', next.previous.agent, model)
    },
    [dropdownAgentId, recordDropdownChange, setSearchParams],
  )

  useEffect(() => {
    // REQ-28: a selected composition team uses ?team=; do not clobber it
    // with the Support default (REQ-23 owns send-to-all). Merge blueprint
    // onto the existing query so ?cli= / ?model= / ?session= survive.
    if (searchParams.get('team') || searchParams.get('remote') || searchParams.get('blueprint')) {
      return
    }
    setSearchParams(
      (prev) => {
        if (prev.get('team') || prev.get('remote') || prev.get('blueprint')) return prev
        const next = new URLSearchParams(prev)
        next.set('blueprint', SUPPORT_AGENT_ID)
        return next
      },
      { replace: true },
    )
  }, [searchParams, setSearchParams])

  // #169: remember which team already got the seat default, so roster
  // re-renders never clobber an explicit later pick (All members / a member).
  const teamDefaultedRef = useRef<string | null>(null)

  useEffect(() => {
    if (teamFromUrl && sessionFromUrl) {
      setMemberTarget(sessionFromUrl)
      teamDefaultedRef.current = teamFromUrl
      return
    }
    if (!teamFromUrl) {
      teamDefaultedRef.current = null
      setMemberTarget(ALL_MEMBERS_TARGET)
      return
    }
    // #169: default the send-target to the chat pane's nominated seat — the
    // configured Chief of Staff, else the first roster member ("First") — the
    // same REQ-130 policy the sidebar picker uses. An explicit pick wins.
    if (teamDefaultedRef.current === teamFromUrl) return
    // An explicit All members pick outranks the nominated-seat default (#288).
    if (allMembersFromUrl) {
      teamDefaultedRef.current = teamFromUrl
      setMemberTarget(ALL_MEMBERS_TARGET)
      return
    }
    if (!selectedTeam) return
    teamDefaultedRef.current = teamFromUrl
    setMemberTarget(defaultSessionForTeam(selectedTeam)?.memberId ?? ALL_MEMBERS_TARGET)
  }, [teamFromUrl, sessionFromUrl, allMembersFromUrl, selectedTeam])

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
    if (!remoteFromUrl) {
      setRemoteThreadPicker(null)
      return
    }
    if (sessionFromUrl) {
      setRemoteThreadPicker(null)
      return
    }
    if (!remoteListsSessions({ id: remoteFromUrl, kind: remoteFromUrl })) return
    let cancelled = false
    void fetchRemoteThreadSessions({
      id: remoteFromUrl,
      kind: remoteFromUrl,
      title: remoteFromUrl,
    })
      .then((sessions) => {
        if (!cancelled) setRemoteThreadPicker(sessions)
      })
      .catch(() => {
        if (!cancelled) setRemoteThreadPicker([])
      })
    return () => {
      cancelled = true
    }
  }, [remoteFromUrl, sessionFromUrl])

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
      setVoiceBind(EMPTY_VOICE_BIND)
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
        setVoiceBind((prev) => parseVoiceBind({ ...prev, ...detail }))
      }
    }
    window.addEventListener(AGENT_SETTINGS_CHANGED_EVENT, onChange)
    let cancelled = false
    void fetchAgentSettings(agent).then((settings) => {
      if (cancelled) return
      if (settings.agent_id && settings.agent_id !== agent) return
      setNewChatPerTask(settings.new_chat_per_task)
      setUseSuggestions(settings.use_suggestions)
      setVoiceBind(parseVoiceBind(settings))
    })
    return () => {
      cancelled = true
      window.removeEventListener(AGENT_SETTINGS_CHANGED_EVENT, onChange)
    }
  }, [selectedBlueprint, teamFromUrl])

  useEffect(() => {
    spokenReplyKeysRef.current = new Set()
    autoSpeakHydratedRef.current = false
  }, [activeChatAgentId, conversationId])

  useEffect(() => {
    if (!autoSpeakHydratedRef.current) {
      for (const message of messages) {
        if (message.role === 'assistant' && !message.streaming) {
          spokenReplyKeysRef.current.add(message.key)
        }
      }
      if (threadReady) autoSpeakHydratedRef.current = true
      return
    }
    const next = nextAutoSpeakText({
      autoSpeak: voiceBind.auto_speak_replies,
      messages,
      alreadySpoken: spokenReplyKeysRef.current,
      hydrated: true,
    })
    if (!next) return
    spokenReplyKeysRef.current.add(next.key)
    const seatSpeech = applyVoiceBindToSpeechSettings(
      parseSpeechSettings(speechQuery.data ?? EMPTY_SPEECH),
      voiceBind,
    )
    const path = resolveTtsPath(seatSpeech)
    if (!path) return
    void (async () => {
      try {
        if (path === 'system') {
          speakSystem(next.text)
          return
        }
        await speakCustom(next.text, {
          voice: voiceBind.speech_mode === 'inherit' ? undefined : voiceBind.tts_voice || undefined,
          instruction:
            voiceBind.speech_mode === 'inherit'
              ? undefined
              : voiceBind.tts_voice_instruction || undefined,
          agentId: activeChatAgentId,
        })
      } catch {
        /* auto-speak is best-effort */
      }
    })()
  }, [
    messages,
    voiceBind,
    threadReady,
    speechQuery.data,
    activeChatAgentId,
  ])

  useEffect(() => {
    let cancelled = false
    const applyPrefs = (server: UserPrefs | null | undefined) => {
      if (cancelled || !server) return
      setContextStrategy(parseContextStrategy(server.context_strategy))
      setCullTriggerPct(parseCullTriggerPct(server.context_cull_trigger_pct))
    }
    void fetchUserPrefs().then(applyPrefs)
    const onPrefs = (event: Event) => {
      applyPrefs((event as CustomEvent<UserPrefs>).detail)
    }
    window.addEventListener(USER_PREFS_CHANGED_EVENT, onPrefs)
    return () => {
      cancelled = true
      window.removeEventListener(USER_PREFS_CHANGED_EVENT, onPrefs)
    }
  }, [])

  useEffect(() => {
    void hydrateRoleAgentTipDismissed().then((dismissed) => {
      if (dismissed) setRoleTipDismissed(true)
    })
  }, [])

  useEffect(() => {
    void hydrateDefaultLlmTipDismissed().then((dismissed) => {
      if (dismissed) setDefaultLlmTipDismissed(true)
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
    setMessagesEditable(canEditAgentMessages(selectedBlueprint) && !remoteFromUrl)
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

  const sendQuestionAnswer = useCallback((id: string, answer: string) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(buildQuestionAnswerFrame(id, answer))
  }, [])

  const attachQuestionToThread = useCallback(
    (question: DecisionQuestion, blocking: boolean) => {
      setThreads((prev) => {
        const current = prev[threadKey] ?? []
        const targetIndex = [...current]
          .reverse()
          .findIndex((message) => message.role === 'assistant')
        const index = targetIndex === -1 ? -1 : current.length - 1 - targetIndex
        const patch = {
          question,
          questionBlocking: blocking,
          questionAnswered: false,
        }
        if (index === -1) {
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `question-host-${question.id}`,
                role: 'assistant' as const,
                text: '',
                streaming: true,
                ...patch,
              },
            ],
          }
        }
        const next = [...current]
        const host = next[index]!
        next[index] = { ...host, ...patch }
        return { ...prev, [threadKey]: next }
      })
    },
    [threadKey],
  )

  const jumpToPrOpener = useCallback(
    (opener: PrOpenedOpener) => {
      setSearchParams(openerChatSearch(opener))
    },
    [setSearchParams],
  )

  const handleWsEvent = useCallback(
    (event: ChatWsEvent) => {
      if (event.kind === 'unknown') {
        console.warn('Unrecognised chat websocket frame:', summarizeUnknownWsFrame(event.raw))
        return
      }
      if (event.kind === 'spa_hello') {
        publishExpectedSpaVersion(event.spaVersion)
        return
      }
      if (event.kind === 'context_usage') {
        publishContextUsage(event.usage)
        setContextUsage(event.usage)
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
      if (event.kind === 'user_question') {
        attachQuestionToThread(event.question, true)
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
      if (event.kind === 'subagent_fan_out') {
        setThreads((prev) => {
          const current = prev[threadKey] ?? []
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `subagent-fan-out-${current.length}-${Date.now()}`,
                role: 'assistant' as const,
                text: '',
                streaming: false,
                subagentFanOut: event.event,
              },
            ],
          }
        })
        for (const s of event.event.subagents ?? []) {
          registerDynamicSubagent({
            id: s.id,
            name: s.name,
            parentAgentId: s.parentAgentId,
            role: s.role,
            status: s.status,
            summary: s.summary,
            task: s.task,
          })
        }
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
            next = current.map((m) => {
              if (m.key !== event.id) return m
              const fence = parseDecisionQuestion(event.text)
              return {
                ...m,
                text: fence ? stripDecisionQuestion(event.text) : event.text,
                streaming: false,
                question: m.question ?? fence ?? undefined,
                questionBlocking: m.questionBlocking ?? false,
              }
            })
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
        // #96: a turn finishing on the open-but-scrolled-up seat was never
        // seen — mark it unread (the rail only dots unselected seats today).
        if (
          agentId &&
          !seatUnread &&
          !pinnedToBottomRef.current &&
          !(typeof document !== 'undefined' && document.visibilityState === 'hidden')
        ) {
          setUnreadIds(markAgentUnread(agentId))
        }
      }
    },
    [
      activeChatAgentId,
      attachQuestionToThread,
      attachToolToThread,
      sendToolDecision,
      threadKey,
      useSuggestions,
      seatUnread,
    ],
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
        buildChatWsUrl(
          conversationId,
          teamFromUrl ? undefined : remoteFromUrl ? 'remote_harness' : runtimeBlueprint || undefined,
        ),
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
      return () => {
        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current)
          reconnectTimerRef.current = null
        }
      }
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
      setAwaitingAssistant(false)
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
    const onUnread = () => setUnreadIds(loadUnreadAgentIds())
    window.addEventListener(UNREAD_CHANGED_EVENT, onUnread)
    window.addEventListener('storage', onUnread)
    return () => {
      window.removeEventListener(UNREAD_CHANGED_EVENT, onUnread)
      window.removeEventListener('storage', onUnread)
    }
  }, [])

  useEffect(() => {
    if (newBeforeKey) {
      const marker = scrollBoxRef.current?.querySelector('[data-testid="chat-new-divider"]')
      if (marker) {
        marker.scrollIntoView({ block: 'center', inline: 'nearest' })
        pinnedToBottomRef.current = false
        return
      }
    }
    if (pinnedToBottomRef.current) {
      scrollTranscriptToBottom(scrollBoxRef.current, listEndRef.current)
    }
  }, [messages, composerInsetPx, newBeforeKey, awaitingAssistant])

  useEffect(() => {
    if (!activeChatAgentId || seatUnread) return
    if (!pinnedToBottomRef.current) return
    // #96: a hidden tab never counts as reading the transcript.
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    saveLastRead(activeChatAgentId, conversationId, countableChatCount(messages))
  }, [activeChatAgentId, conversationId, messages, seatUnread])

  // #96: returning to a visible tab while pinned at the bottom counts as
  // catching up — the scroll handler alone would miss it (no scroll event).
  useEffect(() => {
    const onVisibility = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      if (!pinnedToBottomRef.current || !seatUnread || !activeChatAgentId) return
      setUnreadIds(markAgentRead(activeChatAgentId))
      saveLastRead(activeChatAgentId, conversationId, countableChatCount(messages))
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [seatUnread, activeChatAgentId, conversationId, messages])

  // #96: unread clears only when the seat is visible AND pinned to the
  // transcript bottom — not merely because a scroll happened.
  const handleTranscriptScroll = useCallback(
    (e: React.UIEvent<HTMLElement>) => {
      const atBottom = isPinnedToTranscriptBottom(e.currentTarget, composerInsetPx)
      pinnedToBottomRef.current = atBottom
      if (!atBottom || !seatUnread || !activeChatAgentId) return
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      setUnreadIds(markAgentRead(activeChatAgentId))
      saveLastRead(activeChatAgentId, conversationId, countableChatCount(messages))
    },
    [composerInsetPx, seatUnread, activeChatAgentId, conversationId, messages],
  )

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

  const readyAttachIds = readyAttachmentIds(pendingAttachments)
  const hasSendableDraft =
    !pendingAttachments.some((item) => item.status === 'uploading') &&
    (input.trim().length > 0 || readyAttachIds.length > 0)

  const enqueueComposerFiles = useCallback((files: File[]) => {
    if (files.length === 0) return
    const room = Math.max(0, 8 - pendingAttachments.length)
    const incoming = files.slice(0, room).map(createPendingAttachment)
    if (incoming.length === 0) return
    setPendingAttachments((prev) => [...prev, ...incoming])
    incoming.forEach((item) => {
      void uploadChatAttachment(item.file)
        .then((record) => {
          setPendingAttachments((prev) =>
            prev.map((row) =>
              row.localId === item.localId
                ? { ...row, uploadId: record.id, status: 'ready' }
                : row,
            ),
          )
        })
        .catch(() => {
          setPendingAttachments((prev) =>
            prev.map((row) =>
              row.localId === item.localId ? { ...row, status: 'error' } : row,
            ),
          )
        })
    })
  }, [pendingAttachments.length])

  const handleComposerPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      const files = imageFilesFromClipboard(event.clipboardData)
      if (files.length === 0) return
      event.preventDefault()
      enqueueComposerFiles(files)
    },
    [enqueueComposerFiles],
  )

  const clearPendingAttachments = useCallback(() => {
    setPendingAttachments((prev) => {
      prev.forEach((item) => revokePreviewUrl(item.previewUrl))
      return []
    })
  }, [])

  const sendText = useCallback(
    (text: string): boolean => {
      const ws = wsRef.current
      const attachIds = readyAttachmentIds(pendingAttachments)
      const trimmed =
        text.trim() ||
        (attachIds.length > 0
          ? attachmentCaption(pendingAttachments.map((item) => item.name))
          : '')
      if (!trimmed || !ws || ws.readyState !== WebSocket.OPEN) return false
      lastUserTextRef.current = trimmed
      // Team compose adds params { team, target: "all" | memberId }.
      const pluginParams = enabledToolsParam(conversationIdRef.current)
      const sectionParams = railSectionsParam()
      const attachArg = attachIds.length > 0 ? attachIds : undefined
      if (teamFromUrl) {
        ws.send(
          buildChatWsFrame(trimmed, undefined, {
            team: teamFromUrl,
            target: memberTarget || ALL_MEMBERS_TARGET,
            ...pluginParams,
            ...sectionParams,
          }, attachArg),
        )
        clearPendingAttachments()
        return true
      }
      if (remoteFromUrl) {
        if (isOpenMousBotKind(remoteFromUrl)) {
          const target = ombSendTarget(sessionFromUrl, remoteFromUrl)
          if (!target) {
            addToast({
              type: 'warning',
              title: 'Select an OpenMousBot agent',
              message: `${OMB_SELECT_AGENT_WARNING} gap=${OMB_BOT_REQUIRED_GAP}`,
            })
            return false
          }
          ws.send(
            buildChatWsFrame(trimmed, 'remote_harness', {
              remote: remoteFromUrl,
              name: remoteFromUrl,
              op: 'send',
              target,
              ...pluginParams,
              ...sectionParams,
            }),
          )
          return true
        }
        if (remoteListsSessions({ id: remoteFromUrl, kind: remoteFromUrl }) && !sessionFromUrl) {
          void fetchRemoteThreadSessions({
            id: remoteFromUrl,
            kind: remoteFromUrl,
            title: remoteFromUrl,
          })
            .then((sessions) => setRemoteThreadPicker(sessions))
            .catch(() => setRemoteThreadPicker([]))
          addToast({
            type: 'info',
            title: 'Pick a session',
            message: 'Choose a remote session to resume, then send.',
          })
          return false
        }
        ws.send(
          buildChatWsFrame(trimmed, 'remote_harness', {
            ...remoteChatTurnParams(remoteFromUrl, sessionFromUrl),
            ...pluginParams,
            ...sectionParams,
          }, attachArg),
        )
        clearPendingAttachments()
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
      const seatRemote = loadAgentEdit(agentIdForInference).remote
      const sessionRemote =
        (searchParams.get('cli_remote') ?? '').trim() ||
        (seatRemote?.box || remoteEndpointLabel(seatRemote) || '')
      const elicitParams =
        isApiAgent && loadElicitQuestions(agentIdForInference)
          ? { elicit_questions: true }
          : undefined
      const cliParams = isCliAgent
        ? {
            ...cliAgentChatParams(currentCli, selectedModelParam),
            ...(sessionRemote ? { cli_remote: sessionRemote } : {}),
          }
        : isApiAgent && selectedModelParam && selectedModelParam !== 'default'
          ? { model: selectedModelParam }
          : selectedCli
            ? { cli: selectedCli.cli, failover: false }
            : newChatPerTask
              ? { new_session: messages.length === 0 }
              : undefined
      // #849: an explicit dropdown pick (persisted cli/model or ?cli=/?model=)
      // is the operator's latest word — do not let the REQ-69 seat list rotate
      // them back onto a CLI they did not choose. Seats only drive turns the
      // user left open.
      const explicitCliPick = Boolean(
        (searchParams.get('cli') ?? '').trim() || (persistedDropdown.cli || '').trim(),
      )
      const explicitModelPick = Boolean(
        (searchParams.get('model') ?? '').trim() || (persistedDropdown.model || '').trim(),
      )
      const seatsDeferred = explicitCliPick || explicitModelPick
      const inferenceParams =
        !seatsDeferred && inferenceKeys.length > 0
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
          mergeChatSendParams(
            inferenceParams,
            supportParams,
            pluginParams,
            folderParams,
            skillParams,
            sectionParams,
            elicitParams,
            cliParams,
          ),
          attachArg,
        ),
      )
      clearPendingAttachments()
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
      persistedDropdown.cli,
      persistedDropdown.api,
      isApiAgent,
      searchParams,
      teamFromUrl,
      memberTarget,
      newChatPerTask,
      messages.length,
      remoteFromUrl,
      sessionFromUrl,
      addToast,
      pendingAttachments,
      clearPendingAttachments,
    ],
  )

  const submitUserText = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed && readyAttachmentIds(pendingAttachments).length === 0) return
      // REQ-845 / #167: never drop a typed message on a closed/connecting socket. Keep
      // it in the per-conversation queue; the drain effect sends it on reopen.
      if (status !== 'open') {
        queued.enqueue(trimmed)
        addToast({
          type: 'info',
          title: 'Queued',
          message: 'Chat is reconnecting — your message will send when the socket is back.',
        })
        return
      }
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
    [addToast, awaitingAssistant, messages, pendingAttachments, queued, sendText, status],
  )

  const startFreshCliSession = useCallback(() => {
    const agent = agentIdFromBlueprint(selectedBlueprint)
    const minted = newConversationId()
    setConversationIdForAgent(agent, minted)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (agent && agent !== DEFAULT_AGENT_ID) next.set('blueprint', agent)
      next.set('session', minted)
      return next
    })
  }, [selectedBlueprint, setSearchParams])

  const retryCliSession = useCallback(() => {
    const lastUser = [...messages].reverse().find((row) => row.role === 'user')
    const text = (lastUserTextRef.current || lastUser?.text || '').trim()
    if (text) submitUserText(text)
  }, [messages, submitUserText])

  const clearCliSessionHistory = useCallback(() => {
    const agent = agentIdFromBlueprint(selectedBlueprint)
    const previousId = conversationId
    setThreads((prev) => ({ ...prev, [threadKey]: [] }))
    void clearAgentThread(agent, previousId).catch(() => undefined)
    startFreshCliSession()
  }, [conversationId, selectedBlueprint, startFreshCliSession, threadKey])

  const showCliSessionRecovery =
    threadReady && !awaitingAssistant && lastTurnNeedsRecovery(messages)

  /**
   * #198: interrupt the turn in flight (enter-to-interrupt on a queued send).
   * The drain effect promotes the top queued row automatically once the
   * cancelled turn closes, so this only needs to request the cancel.
   */
  const interruptRunningTurn = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(buildCancelTurnFrame())
      setAwaitingAssistant(false)
    }
  }, [])

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
        const patched = await patchAgentMessage(
          agentIdFromBlueprint(selectedBlueprint),
          {
            index: turnIndex,
            content: nextText,
            conversation_id: conversationIdRef.current,
          },
        )
        if (patched.cli_session_reset) {
          addToast({
            type: 'info',
            title: 'CLI session restarted',
            message:
              'A message was edited and the CLI session cannot rewind. The next message starts a fresh session.',
          })
        }
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
    if (!hasSendableDraft) return
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

  const speechSettings = applyVoiceBindToSpeechSettings(
    parseSpeechSettings(speechQuery.data ?? EMPTY_SPEECH),
    voiceBind,
  )

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
              const spoken = await transcribeCustomBlob(blob, 'audio.webm', {
                agentId: activeChatAgentId,
              })
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
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setPlusOpen(false)
      }
    }
    window.addEventListener('mousedown', onPointer)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointer)
      window.removeEventListener('keydown', onKey)
    }
  }, [plusOpen])

  const streamingMessage = messages.find((message) => message.streaming)
  const isWorking = Boolean(streamingMessage) || awaitingAssistant
  // #224: every tool call this seat has produced in the active context.
  const seatToolCalls = useMemo<PanelToolCall[]>(
    () => messages.flatMap((message) => message.tools ?? []),
    [messages],
  )
  const generationContexts = useMemo(
    () =>
      conversationId
        ? [{ id: conversationId, label: selectedAgentName || 'Current context' }]
        : [],
    [conversationId, selectedAgentName],
  )
  const chipsDisabled = status !== 'open'
  const demoMode = isDemoMode()
  const demoChips = demoMode ? demoSuggestionChips() : []
  const supportJourneyChips =
    supportSelected && messages.length === 0 ? supportJourneyKickstart() : []
  const showSupportJourneyChips = !demoMode && supportJourneyChips.length > 0
  const showDemoChips = demoMode && demoChips.length > 0
  const showSuggestionChips =
    !demoMode &&
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
    if (!threadReady || isWorking || teamFromUrl) return
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
    isWorking,
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
    if (activeChatAgentId) {
      notifyCliRunState(activeChatAgentId, isWorking)
    }
  }, [streamingMessage, awaitingAssistant, isWorking, activeChatAgentId, messages, selectedAgentName, isCliAgent])

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
      if (result.usage) {
        publishContextUsage(result.usage)
        setContextUsage(result.usage)
      }
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
        if (result.usage) {
          publishContextUsage(result.usage)
          setContextUsage(result.usage)
        }
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
      if (plusOpen) {
        event.preventDefault()
        setPlusOpen(false)
        return
      }
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
      if (input.trim().length > 0 || readyAttachmentIds(pendingAttachments).length > 0) {
        const quotePrefix = replyTarget ? (replyTarget.speaker ? `> **${replyTarget.speaker}**: ` : `> `) : ''
        const textToSend = replyTarget
          ? `${quotePrefix}${replyTarget.text.replace(/\r\n/g, '\n').split('\n').join('\n> ')}\n\n${input}`
          : input
        submitUserText(textToSend)
        setInput('')
        setReplyTarget(null)
        return
      }
      // #198: enter on an empty composer with a queued send interrupts the
      // running turn; the drain effect then sends the promoted top row.
      const nextQueued = nextDrainableQueuedSend(queued.rows, queuedHoldIds)
      if (nextQueued) {
        interruptRunningTurn()
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
  // #207: API seats on the default profile get a setup tip when the default
  // LLM is not usable. Explicit model/profile overrides (pinned seats) and
  // CLI/remote/team seats are exempt by design.
  const showDefaultLlmTip = shouldShowDefaultLlmTip({
    isApiAgent,
    hasExplicitModelOverride: Boolean(selectedModelId),
    defaultLlmReady: llmProfilesQuery.data?.default_llm_ready,
    dismissed: defaultLlmTipDismissed,
  })
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
      <header className="os-chat-header overflow-hidden gap-1.5 sm:gap-3">
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
            ) : !teamFromUrl ? (
              <button
                type="button"
                className="os-chat-header__avatar-btn shrink-0"
                aria-label={`Show ${selectedAgentName} generations`}
                aria-haspopup="dialog"
                aria-expanded={generationsOpen}
                data-testid="header-avatar-generations"
                onClick={(event) => {
                  event.stopPropagation()
                  setGenerationsOpen((prev) => !prev)
                }}
              >
                <AgentAvatar
                  src={selectedAgent?.avatar_path}
                  agentId={agentIdFromBlueprint(selectedBlueprint)}
                  active={isWorking}
                  status={isWorking ? 'working' : 'idle'}
                  size="lg"
                  gl
                  className="os-chat-header__avatar"
                />
              </button>
            ) : null}
            <div className="os-navbar-identity-text min-w-0 flex-1">
              <h1 className="os-navbar-identity-label min-w-0 flex-1 text-base font-semibold tracking-tight">
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
        <div className="os-chat-header__controls flex items-center shrink-0 gap-1 sm:gap-2">
          {/* Token visibility: only when using API agents (swarm owns the numbers).
              For remote, CLI, and non-API agent types, the token counter must not exist in the top navbar. */}
          {isApiAgent && (
            <button
              type="button"
              className="btn btn-ghost btn-xs h-auto p-1 gap-1.5 font-normal text-inherit hover:bg-base-300/40 normal-case hidden sm:flex shrink-0"
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
          )}
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
              models={ombNavbarAgents.map((row) => row.id)}
              modelOptions={ombNavbarAgents}
              selectedModel={ombSelectedBotId}
              modelWarning={ombModelWarning}
              footerAction={{
                id: ADD_REMOTE_VALUE,
                label: 'Manage Remote',
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
                setSearchParams((prev) => {
                  const params = new URLSearchParams(prev)
                  if (nextId) params.set('remote', nextId)
                  if (next.changed === 'model' && next.model) {
                    params.set('session', next.model)
                  } else if (next.changed === 'agent') {
                    params.delete('session')
                  }
                  return params
                })
              }}
            />
          ) : null}
          {productModes.team && teamFromUrl ? (
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
          {productModes.cli && isCliAgent ? (
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
                label: 'Manage CLI',
                onSelect: () => openSettingsSheet({ section: 'cli-agents' }),
              }}
              onChange={applyCliRoutingChange}
            />
          ) : null}
          {isCliAgent && currentCli ? (
            <CliSessionSwitcher
              agentId={selectedBlueprint}
              cli={currentCli}
              agentName={selectedAgentName}
            />
          ) : null}
          {isCliAgent && currentCli && isRemoteCapableCli(currentCli, cliQuery.data?.remote) ? (
            <label className="flex items-center gap-1 min-w-0">
              <span className="sr-only">CLI remote box</span>
              <select
                className="select select-xs select-bordered h-7 min-h-0 max-w-[12rem] font-medium"
                aria-label="CLI remote box"
                data-testid="select-cli-session-remote"
                value={(searchParams.get('cli_remote') ?? '').trim() || loadAgentEdit(selectedBlueprint).remote?.box || ''}
                onChange={(event) => {
                  const next = event.target.value
                  setSearchParams(
                    (prevParams) => {
                      const nextParams = new URLSearchParams(prevParams)
                      if (next) nextParams.set('cli_remote', next)
                      else nextParams.delete('cli_remote')
                      return nextParams
                    },
                    { replace: true },
                  )
                }}
              >
                <option value="">Local</option>
                {(cliQuery.data?.remote_boxes ?? []).map((box) => (
                  <option key={box.id || box.host} value={box.id || `${box.host}:${box.port}`}>
                    {box.id || box.host}:{box.port}
                  </option>
                ))}
                {loadAgentEdit(selectedBlueprint).remote?.host ? (
                  <option
                    value={
                      loadAgentEdit(selectedBlueprint).remote?.box ||
                      remoteEndpointLabel(loadAgentEdit(selectedBlueprint).remote)
                    }
                  >
                    {remoteEndpointLabel(loadAgentEdit(selectedBlueprint).remote)}
                  </option>
                ) : null}
              </select>
            </label>
          ) : null}
          {productModes.api && isApiAgent ? (
            /* #108: API seats route through LLM profiles, not host CLIs. */
            <NavbarRoutingPicker
              seatKind="api"
              aria-label="API"
              agents={apiModelOptionsFromProfiles(
                llmProfilesQuery.data?.profiles,
                llmProfilesQuery.data?.default_llm_profile
                  ? [llmProfilesQuery.data.default_llm_profile]
                  : [],
              ).map((opt) => ({ id: opt.id, label: opt.label }))}
              selectedAgent={
                selectedModelId || llmProfilesQuery.data?.default_llm_profile || ''
              }
              models={[]}
              selectedModel=""
              defaultAgent={llmProfilesQuery.data?.default_llm_profile || ''}
              footerAction={{
                id: '__manage_api__',
                label: 'Manage API',
                onSelect: () => openSettingsSheet({ section: 'llm-profiles' }),
              }}
              onChange={applyApiRoutingChange}
            />
          ) : null}
          <div
            className="flex items-center shrink-0 gap-1 sm:gap-2"
            role="toolbar"
            aria-label="Chat tools"
          >
            <ComputerControlStub
              agentId={activeChatAgentId}
              agentName={selectedAgentName}
            />
            {/* #182: Compose team moved to the rail footer, above Plugins. */}
            <ThemeToggle />
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

      {showRoleTip ? <RoleAgentTip onDismiss={dismissRoleTip} /> : null}
      {showDefaultLlmTip ? <DefaultLlmTip onDismiss={dismissDefaultLlmTip} /> : null}

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
        data-messages-editable={messagesEditable && agentKind !== 'remote' ? 'true' : 'false'}
        data-composer-inset={composerInsetPx}
        data-bubble-theme={bubbleTheme}
        data-message-layout={getBubbleTheme(bubbleTheme).messageLayout}
        data-timestamp-placement={getBubbleTheme(bubbleTheme).timestampPlacement}
        tabIndex={0}
        onScroll={handleTranscriptScroll}
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
            {demoMode ? (
              <DemoTourBanner disabled={chipsDisabled} onChoose={chooseSuggestion} />
            ) : showSupportJourneyChips ? (
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
                  onToggleContext={handleToggleSummaryContext}
                  canEdit={messagesEditable}
                  onSaveEdit={handleSaveSummary}
                />
              )
            }
            const message = item.message
            if (hiddenMessageKeys.includes(message.key)) return null
            const liveMessage = messages.find((row) => row.key === message.key)
            const teammateTask = liveMessage?.teammateTask
            const subagentFanOut =
              liveMessage?.subagentFanOut ||
              ((teammateTask as any)?.subagents?.length
                ? (teammateTask as unknown as SubagentFanOutData)
                : undefined)
            if (subagentFanOut) {
              return (
                <div key={message.key} className="os-subagent-fan-out-wrap my-2">
                  <SubagentFanOutBlock event={subagentFanOut} />
                </div>
              )
            }
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
              !message.streaming &&
              (message.role === 'user' || message.role === 'assistant')
            const canCompressThis =
              (isApiAgent || agentKind === 'blueprint') &&
              !message.streaming &&
              (message.role === 'user' || message.role === 'assistant') &&
              rawOffsetForMessage(messages, message.key) >= 0
            const showRowActions =
              !message.streaming &&
              editingKey !== message.key &&
              (message.role === 'user' || message.role === 'assistant') &&
              (Boolean(message.text.trim()) || retryEnabled || canEditThis || canCompressThis)
            const isStreamingAssistant = message.role === 'assistant' && Boolean(message.streaming)
            const bubbleAvatar =
              message.role === 'assistant' ? (
                isStreamingAssistant ? (
                  <div
                    className="os-composer-working os-inline-working"
                    data-testid="composer-working-indicator"
                    role="status"
                    aria-live="polite"
                    aria-label={workingTip}
                  >
                    <span
                      className="tooltip tooltip-right os-composer-working__tip"
                      data-tip={workingTip}
                    >
                      <span className="os-composer-working__avatar os-inline-working__avatar">
                        <AgentAvatar
                          src={selectedAgent?.avatar_path}
                          agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                          active={true}
                          status="working"
                          size="xs"
                          className="shrink-0"
                        />
                      </span>
                    </span>
                  </div>
                ) : (
                  <AgentAvatar
                    src={selectedAgent?.avatar_path}
                    agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                    active={false}
                    status="idle"
                    size="xs"
                    className="shrink-0"
                  />
                )
              ) : undefined
            const rawOffset = rawOffsetForMessage(messages, message.key)
            const showStartMarker =
              contextMeta.start_offset > 0 && rawOffset === contextMeta.start_offset
            return (
              <div
                key={message.key}
                className="group/osrow"
                onContextMenu={(e) => {
                  if (message.role === 'system') return
                  handleBubbleContextMenu(e, message)
                }}
              >
                {newBeforeKey === message.key ? <ChatNewRule /> : null}
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
                  theme={bubbleTheme}
                  role={message.role}
                  agentName={selectedAgentName}
                  text={message.text}
                  streaming={message.streaming}
                  seatId={activeChatAgentId}
                  edited={message.edited}
                  ts={message.ts}
                  avatar={bubbleAvatar}
                  skillCatalog={skillCatalog}
                  onOpenSkill={setOpenSkillName}
                  onRemoveCard={() =>
                    setHiddenMessageKeys((prev) =>
                      prev.includes(message.key) ? prev : [...prev, message.key],
                    )
                  }
                  editing={editingKey === message.key}
                  onCancelEdit={() => setEditingKey(null)}
                  onSaveEdit={(next) => {
                    if (messageIndex >= 0) void saveEditedMessage(messageIndex, next)
                  }}
                >
                  {message.subagentFanOut ? (
                    <div className="my-2">
                      <SubagentFanOutBlock event={message.subagentFanOut} />
                    </div>
                  ) : null}
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
                  {message.question ? (
                    <QuestionCard
                      question={message.question}
                      disabled={
                        message.questionAnswered === true ||
                        (message.tools ?? []).some((tool) => tool.needsApproval)
                      }
                      onChoose={(value) => {
                        if (message.questionBlocking) {
                          sendQuestionAnswer(message.question!.id, value)
                        } else {
                          sendText(value)
                        }
                        setThreads((prev) => {
                          const current = prev[threadKey] ?? []
                          return {
                            ...prev,
                            [threadKey]: current.map((row) =>
                              row.key === message.key
                                ? { ...row, questionAnswered: true }
                                : row,
                            ),
                          }
                        })
                      }}
                    />
                  ) : null}
                </ChatMessageBubble>
                {showRowActions ? (
                  <MessageRowActions
                    text={message.text}
                    canEdit={canEditThis}
                    onStartEdit={() => setEditingKey(message.key)}
                    canCompress={canCompressThis}
                    contextStrategy={contextStrategy}
                    onCompressToHere={() => {
                      handleContextToHere(message)
                    }}
                    className={message.role === 'user' ? 'w-full justify-end' : undefined}
                  >
                    {message.role === 'assistant' && message.text.trim() ? (
                      <ReadAloudButton
                        text={message.text}
                        agentId={activeChatAgentId}
                        bind={voiceBind}
                      />
                    ) : null}
                    {message.role === 'assistant' && SHOW_MESSAGE_ACTIONS && (
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
                  </MessageRowActions>
                ) : null}
              </div>
            )
          })}
          </>
        )}
        {showCliSessionRecovery ? (
          <CliSessionRecoveryBanner
            onStartFresh={startFreshCliSession}
            onRetry={retryCliSession}
            onClearHistory={clearCliSessionHistory}
          />
        ) : null}
        {awaitingAssistant && !streamingMessage && (
          <div
            className="os-chat-message os-chat-message--assistant group/osrow flex flex-col gap-1 items-start my-2"
            role="status"
            aria-live="polite"
            aria-label={workingTip}
          >
            <div className="flex items-center gap-2.5 py-1 px-1">
              <div
                className="os-composer-working os-inline-working"
                data-testid="composer-working-indicator"
                role="status"
                aria-live="polite"
                aria-label={workingTip}
              >
                <span className="tooltip tooltip-right os-composer-working__tip" data-tip={workingTip}>
                  <span className="os-composer-working__avatar os-inline-working__avatar">
                    <AgentAvatar
                      src={selectedAgent?.avatar_path}
                      agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                      active={true}
                      status="working"
                      size="xs"
                      className="shrink-0"
                    />
                  </span>
                </span>
              </div>
              <span className="inline-flex items-center gap-2 text-xs text-base-content/70 italic">
                <span>{workingTip || 'Thinking…'}</span>
                <span className="loading loading-dots loading-xs opacity-70" />
              </span>
            </div>
          </div>
        )}
        <div ref={listEndRef} />
        </div>

        <QueuedSendPane
          rows={queued.rows}
          maxHeightPx={queuedPaneMaxHeightPx(transcriptHeightPx)}
          onChangeText={queued.update}
          onDelete={queued.remove}
          onClearAll={queued.clearAll}
          onHoldIdsChange={setQueuedHoldIds}
          interruptible={
            status === 'open' && queued.rows.length > 0 && generationIsInFlight(messages, awaitingAssistant)
          }
        />

        <div
          ref={bottomDockRef}
          className="os-chat-bottom-dock sticky bottom-0 z-20 -mx-2 sm:-mx-3 -mb-3 bg-base-100 border-t border-base-content/5"
          data-testid="chat-bottom-dock"
        >
          {showDemoChips ? (
            <SuggestionChips
              chips={demoChips}
              disabled={chipsDisabled}
              onChoose={chooseSuggestion}
            />
          ) : showSuggestionChips ? (
            <SuggestionChips
              chips={suggestionChips}
              disabled={chipsDisabled}
              onChoose={chooseSuggestion}
            />
          ) : null}
          {status !== 'open' ? (
            <div
              className="os-conn-status"
              data-testid="chat-conn-status"
              aria-live="polite"
            >
              <span className="os-conn-status__dot" aria-hidden="true" />
              <span className="os-conn-status__label">
                {authRejected
                  ? 'Sign in to chat — your draft is kept locally.'
                  : 'Chat is offline — you can keep typing; sends will queue until it reconnects.'}
              </span>
            </div>
          ) : null}
          {showContextUsage && contextUsage ? (
            <div
              className="flex justify-end px-3 pt-1.5"
              data-testid="context-usage-badge-slot"
            >
              <ContextUsageBadge
                usage={contextUsage}
                onOpenDetail={() =>
                  openAgentEditor({
                    agentId: selectedBlueprint || DEFAULT_AGENT_ID,
                  })
                }
              />
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
              <div className={`os-composer ${replyTarget || pendingAttachments.length > 0 ? 'flex-col items-stretch !rounded-2xl !p-2' : ''} ${replyTarget ? 'os-composer--reply' : ''}`}>
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
                <ComposerAttachChips
                  attachments={pendingAttachments}
                  onRemove={(localId) => {
                    setPendingAttachments((prev) => {
                      const gone = prev.find((row) => row.localId === localId)
                      revokePreviewUrl(gone?.previewUrl)
                      return prev.filter((row) => row.localId !== localId)
                    })
                  }}
                />
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
                    onPaste={handleComposerPaste}
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
                  {status === 'open' && generationIsInFlight(messages, awaitingAssistant) ? (
                    <button
                      type="button"
                      className="os-composer__icon os-composer__stop"
                      aria-label="Stop generating"
                      title="Stop the generation in flight (queued sends stay queued)"
                      data-testid="composer-stop"
                      onClick={interruptRunningTurn}
                    >
                      <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
                    </button>
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
            {(isApiAgent || agentKind === 'blueprint') &&
            (contextMenu.message.role === 'user' || contextMenu.message.role === 'assistant') &&
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
            <div
              className="os-bubble-theme-item relative"
              data-testid="context-menu-bubble-theme-item"
              data-open={bubbleThemeMenuOpen ? 'true' : undefined}
              onMouseEnter={() => setBubbleThemeMenuOpen(true)}
              onMouseLeave={() => setBubbleThemeMenuOpen(false)}
            >
              <button
                type="button"
                role="menuitem"
                aria-haspopup="menu"
                aria-expanded={bubbleThemeMenuOpen}
                className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
                data-testid="context-menu-bubble-theme"
                onClick={() => setBubbleThemeMenuOpen((open) => !open)}
              >
                <Palette className="h-4 w-4 opacity-70" aria-hidden="true" />
                <span className="flex-1">Bubble theme</span>
                <ChevronRight className="h-3.5 w-3.5 opacity-70" aria-hidden="true" />
              </button>
              {bubbleThemeMenuOpen ? (
                <ul
                  role="menu"
                  aria-label="Bubble theme"
                  className="os-bubble-theme-submenu"
                  data-testid="context-menu-bubble-theme-submenu"
                >
                  {BUBBLE_THEMES.map((id) => {
                    const selected = bubbleTheme === id
                    return (
                      <li key={id}>
                        <button
                          type="button"
                          role="menuitemradio"
                          aria-checked={selected}
                          className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
                          data-testid={`context-menu-bubble-theme-${id}`}
                          onClick={() => {
                            setBubbleTheme(saveBubbleTheme(id))
                            setContextMenu(null)
                          }}
                        >
                          <Check
                            className={`h-4 w-4 ${selected ? '' : 'opacity-0'}`}
                            aria-hidden="true"
                          />
                          {BUBBLE_THEME_LABELS[id]}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              ) : null}
            </div>
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

      <GenerationsPanel
        open={generationsOpen}
        onClose={() => setGenerationsOpen(false)}
        agentId={agentIdFromBlueprint(selectedBlueprint) || selectedBlueprint || ''}
        agentName={selectedAgentName || 'Agent'}
        contexts={generationContexts}
        activeContextId={conversationId}
        onSwitchContext={() => {
          /* Single-context today; multi-context switching lands with session history UI. */
        }}
        toolCalls={seatToolCalls}
      />

      <SessionPicker
        open={remoteThreadPicker !== null}
        title={remoteFromUrl || 'Remote'}
        sessions={remoteThreadPicker ?? []}
        onClose={() => setRemoteThreadPicker(null)}
        onSelect={(session) => {
          const resumeId = String(session.memberId || session.id || '').trim()
          if (!resumeId || !remoteFromUrl) return
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev)
              next.set('remote', remoteFromUrl)
              next.set('session', resumeId)
              return next
            },
            { replace: true },
          )
          setRemoteThreadPicker(null)
        }}
      />
    </div>
  )
}

function SummaryBlock({
  summary,
  byId,
  depth = 0,
  hiddenIds = [],
  onHide,
  onToggleContext,
  canEdit = false,
  onSaveEdit,
}: {
  summary: ConversationSummary
  byId: Record<number, ConversationSummary>
  depth?: number
  hiddenIds?: number[]
  onHide?: (id: number) => void
  /** #214: persist the include-in-context tick for this summary. */
  onToggleContext?: (id: number, include: boolean) => void
  canEdit?: boolean
  onSaveEdit?: (id: number, text: string) => void
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
      inContext={summary.include_in_context !== false}
      onToggleContext={(include) => onToggleContext?.(summary.id, include)}
      canEdit={canEdit}
      onSaveEdit={(text) => onSaveEdit?.(summary.id, text)}
      nested={
        parent && !hiddenIds.includes(parent.id) ? (
          <SummaryBlock
            summary={parent}
            byId={byId}
            depth={depth + 1}
            hiddenIds={hiddenIds}
            onHide={onHide}
            onToggleContext={onToggleContext}
            canEdit={canEdit}
            onSaveEdit={onSaveEdit}
          />
        ) : null
      }
    />
  )
}

export default ChatPage
