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
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, AlertCircle, ChevronDown, Copy, FoldVertical, Layers, Mic, PanelLeft, Paperclip, Pencil, Plug, Plus, Reply, Server, Settings, Square, X } from 'lucide-react'
import AgentAvatar from '../components/AgentAvatar'
import ChatMessageInput from '../components/ChatMessageInput'
import {
  Alert,
  ConfirmModal,
  TOAST_KIND_WS_DISCONNECT,
  useToast,
} from '../components/DaisyUI'
import ThemeToggle from '../components/ThemeToggle'
import {
  OPEN_SETTINGS_EVENT,
  openSettingsSheet,
  settingsDetailFromQuery,
} from '../components/SettingsSheet'
import { OVERLAY_CHROME_CLASSES } from '../lib/chromeOverlay'
import RateLimitStatusLine from '../components/RateLimitStatusLine'
import { isRateLimitWait, settingsTargetForProvider, type RateLimitWait } from '../lib/providerRateLimits'
import { formatRateLimitNotice } from '../lib/statusLineText'
import { IrcNoticeLine } from '../components/IrcNoticeLine'
import {
  getScopedSelectionText,
  resolveReplyQuote,
  type CachedBubbleSelection,
} from '../lib/bubbleSelection'
import { buildOutboundReplyText } from '../lib/replyQuote'
import {
  copyTextToClipboard,
  COPY_EMPTY_MESSAGE,
  COPY_EMPTY_TITLE,
  COPY_FAILED_MESSAGE,
  COPY_FAILED_TITLE,
} from '../lib/clipboard'

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
import { personaForAgentMessage } from '../lib/personaAvatars'
import { useRailChrome } from '../components/RailChrome'
import { ComputerControlStub } from '../components/ComputerControlStub'
import { NavbarRoutingPicker, type RoutingPathChange } from '../components/NavbarRoutingPicker'
import { ChatMessageBubble } from '../components/ChatMessageBubble'
import {
  BUBBLE_THEME_CHANGED_EVENT,
  BUBBLE_THEME_STORAGE_KEY,
  getBubbleTheme,
  loadBubbleTheme,
  type BubbleTheme,
} from '../lib/bubbleTheme'
import {
  IRC_GUTTER_CHANGED_EVENT,
  loadIrcGutterPx,
  themeUsesIrcGutter,
  saveIrcGutterPx,
  IRC_GUTTER_DEFAULT_PX,
} from '../lib/ircGutter'
import ReadAloudButton from '../components/ReadAloudButton'
import { SkillPopup } from '../components/SkillPopup'
import MessageRowActions from '../components/MessageRowActions'
import { extractThinkingBlock } from '../lib/messageArtifacts'
import CliSessionSwitcher from '../components/CliSessionSwitcher'
import ApiSessionSwitcher from '../components/ApiSessionSwitcher'
import RemoteSessionSwitcher from '../components/RemoteSessionSwitcher'
import SessionPicker from '../components/SessionPicker'
import {
  fetchRemoteThreadSessions,
  mostRecentRemoteSession,
  remoteAgentsFromOperate,
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
  dataTransferHasFiles,
  filesFromList,
  imageFilesFromClipboard,
  readyAttachmentIds,
  revokePreviewUrl,
  uploadChatAttachment,
  type PendingAttachment,
} from '../lib/chatAttachments'
import { composerMenuCapabilities } from '../lib/composerMenu'
import { applyRemoteRoutingChange } from '../lib/remoteRouting'
import { ComposerPluginsPanel } from '../components/ComposerPluginsPanel'
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
  fetchHerdrAgents,
  fetchLlmProfiles,
  fetchRemotes,
  fetchSpeechSettings,
  isThrottleError,
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
import { canEditAgentMessages, classifyAgentKind, isSwarmOwnedAgent, type AgentKind } from '../lib/agentKind'
import { isCompressionNoticeText } from '../lib/compressionNotices'
import {
  composerInsetCustomProperty,
  isPinnedToTranscriptBottom,
  measureComposerDockInset,
  scrollTranscriptToBottom,
} from '../lib/composerInset'
import {
  initialComposerShowProvider,
  COMPOSER_SHOW_PROVIDER_SET_EVENT,
  COMPOSER_SHOW_PROVIDER_STORAGE_KEY,
} from '../lib/composerShowProvider'
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
import { AuxActivityIndicator } from '../components/AuxActivityIndicator'
import {
  applyAuxFrame,
  announceAuxTasks,
  requestAuxCancel,
  sweepAuxTasks,
  AUX_CANCEL_EVENT,
  type AuxTask,
} from '../lib/auxTasks'
import {
  fetchContextUsage,
  publishContextUsage,
  type ContextUsage,
} from '../lib/contextUsage'
import { QuestionCard } from '../components/QuestionCard'
import {
  parseDecisionQuestion,
  stripDecisionQuestion,
} from '../lib/decisionQuestion'
import type { DecisionQuestion } from '../lib/decisionQuestion'
import { loadElicitQuestions } from '../lib/elicitQuestions'
import { ToolCallPopup } from '../components/ToolCallPopup'
import GenerationsPanel, { type PanelToolCall } from '../components/GenerationsPanel'
import { PrOpenedCard } from '../components/PrOpenedCard'
import { TeammateTaskCard } from '../components/TeammateTaskCard'
import { SuggestionChips } from '../components/SuggestionChips'
import ConsumerPills from '../components/ConsumerPills'
import ComposerPluginsBadge from '../components/ComposerPluginsBadge'
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
import { RawResponseModal } from '../components/RawResponseModal'
import { isHerdrAgent } from '../lib/railHotkeys'
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
import { notifyApprovalWait } from '../lib/agentAttention'
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
  ombSendTarget,
} from '../lib/ombBots'
import { isOpenMousBotKind } from '../lib/remoteKinds'
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId } from '../lib/remotesCatalog'
import { buildComposerProviders, composerOptionsForProvider } from '../lib/composerSources'
import type { ComposerSources } from '../lib/composerSources'

/** #494: machine-readable remedy the backend stamps on classified failures. */
interface RemoteAction {
  kind: 'settings'
  section: 'remotes'
  remote?: string
  field?: string
}

function isRemoteAction(value: unknown): value is RemoteAction {
  if (!value || typeof value !== 'object') return false
  const rec = value as Record<string, unknown>
  return rec.kind === 'settings' && rec.section === 'remotes'
}
import {
  ADD_REMOTE_VALUE,
  configuredRemotes,
  isHerdrKind,
  remoteKinds,
  remoteOptionLabel,
  remoteSelectPlaceholder,
} from '../lib/remotes'
import { enabledToolsParam } from '../lib/chatPluginTools'
import { railSectionsParam } from '../lib/railSections'
import { publishCurrentChatScope } from '../lib/chatScope'
import { publishCurrentAgent } from '../lib/currentAgent'
import {
  AGENT_REMOTE_BINDINGS_CHANGED_EVENT,
  isRemoteKindAgent,
  loadAgentRemoteBinding,
  remotesListForSelect,
  resolveAgentBindingSubject,
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
  estimateTokensInContext,
  resolveContextMaxFromProfiles,
} from '../lib/chatMeter'
import { formatGapLabel, parseCreatedAtMs } from '../lib/chatTime'
import { workingLabel } from '../lib/chatBubble'
import { isExperimentalEnabled } from '../experimental/flags'
import { ChatMessageActions } from '../experimental/ChatMessageActions'
import { RoleAgentTip } from '../components/RoleAgentTip'
import { DefaultLlmTip } from '../components/DefaultLlmTip'
import { CliSessionRecoveryBanner } from '../components/CliSessionRecoveryBanner'
import { lastRecoveryTarget, lastTurnNeedsRecovery } from '../lib/cliSessionRecovery'
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
import { cliRemoteSessionChoices, isRemoteCapableCli, remoteEndpointLabel } from '../lib/cliRemote'
import { buildSkillParams, parseComposerSkillNames } from '../lib/skills'
import { chatFolderParams } from '../lib/agentFolder'
import { navbarWorkspaceSubtitle, persistSessionWorkspace } from '../lib/agentWorkspace'
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
import {
  CLI_SESSION_SWITCHED_EVENT,
  dispatchCliSessionSwitched,
  fetchCliSessions,
  selectCliSession,
} from '../lib/cliSessions'
import { CLI_SESSION_HOPPED_EVENT, dispatchCliSessionHopped, hopCliSession } from '../lib/cliSessionHop'
// #636: CLI-seat compact orchestration (summary + fresh session carrying it).
import { compactCliThread } from '../lib/cliCompact'
import {
  SUGGESTION_CHIP_EVENT,
  drainHoldUntilStreamStarts,
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
  resolveCurrentCli,
  MANAGE_CLI_VALUE,
} from '../lib/cliAgentContext'
import { productModesWhenSettled } from '../lib/productModes'
import { recordBackendUse } from '../lib/backendAudit'
import { isHiddenRoutingLabel, type RoutingSeatKind } from '../lib/routingPath'
import {
  providerReconfigureNotice,
  seatParamsForPick,
  type SeatPickKind,
} from '../lib/seatRouting'

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
  /** #527 — openai-agents persona that produced the row, when the server says. */
  persona?: string
  /** Persist/reload timestamp (ISO). Status/info chrome shows this. */
  ts?: string
  /** REQ-88 — provider queue wait; click opens that provider's rate-limit fields. */
  rateLimit?: RateLimitWait
  /** Terminal CLI/config failure — recovery banner (#274). */
  fatalConfigError?: boolean
  /** #850: Raw unstripped terminal response captured from Herdr. */
  rawResponse?: string
}

/** #534: persisted compression rows never render on restored transcripts. */
function hydrateThreadRows(messages: Array<Parameters<typeof chatMessageFromThreadRow>[0]>): ChatMessage[] {
  return messages
    .filter((message) => !(message.role === 'status' && isCompressionNoticeText(message.content)))
    .map(chatMessageFromThreadRow)
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
    persona?: string
    raw_response?: string
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
    rawResponse: typeof message.raw_response === 'string' ? message.raw_response : undefined,
    streaming: false,
    edited: message.edited === true,
    prOpened,
    teammateTask,
    subagentFanOut,
    kind: prior ? 'prior_history' : undefined,
    ts: message.ts,
    rateLimit: isRateLimitWait(message.rate_limit) ? message.rate_limit : undefined,
    fatalConfigError: message.fatal_config_error === true,
    persona: typeof message.persona === 'string' ? message.persona : undefined,
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
  selectedText?: string | null
}

function warnStatusPersistFailure(err: unknown): void {
  const reason = err instanceof Error ? err.message : String(err)
  console.warn('Could not persist status line', reason)
}

const ChatPage = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToast, dismissByKind, error: toastError } = useToast()
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
    // #674: this effect runs on the CHILD before App (the sheet owner and
    // OPEN_SETTINGS_EVENT listener) has subscribed on a cold load, so an
    // immediate dispatch is dropped. Defer to the next macrotask so the
    // parent's listener exists first.
    const timer = window.setTimeout(() => {
      openSettingsSheet(detail)
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.delete('settings')
        return next
      }, { replace: true })
    }, 0)
    return () => {
      window.clearTimeout(timer)
    }
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
  /** #878: show/hide the provider routing picker in the message input bar. */
  const [composerShowProvider, setComposerShowProvider] = useState(() =>
    initialComposerShowProvider(),
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
  // #818: background (auxiliary) LLM inference visibility. Frames arrive on
  // the chat socket; the kill switch rides the same socket back.
  const [auxTasks, setAuxTasks] = useState<AuxTask[]>([])
  useEffect(() => {
    const onCancel = (e: Event) => {
      const taskId = (e as CustomEvent<string>).detail
      if (typeof taskId === 'string' && taskId) {
        wsRef.current?.send(JSON.stringify({ type: 'cancel_auxiliary', task_id: taskId }))
      }
    }
    window.addEventListener(AUX_CANCEL_EVENT, onCancel)
    const sweeper = setInterval(() => {
      setAuxTasks((prev) => {
        const next = sweepAuxTasks(prev)
        return next.length === prev.length ? prev : next
      })
    }, 1_000)
    return () => {
      window.removeEventListener(AUX_CANCEL_EVENT, onCancel)
      clearInterval(sweeper)
    }
  }, [])
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
  // #675: resizable IRC gutter — per-row dividers persist through the shared
  // store; the transcript only mirrors the store via the change event.
  const [ircGutterPx, setIrcGutterPx] = useState(() => loadIrcGutterPx())
  // #721: the universal divider is ONE transcript-level rail (not per-row
  // segments) — drag persists through the shared store, double-click resets.
  const ircDragRef = useRef<{ startX: number; startWidth: number } | null>(null)
  const [ircGutterDragging, setIrcGutterDragging] = useState(false)
  const onIrcRailPointerDown = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      event.preventDefault()
      event.currentTarget.setPointerCapture?.(event.pointerId)
      ircDragRef.current = { startX: event.clientX, startWidth: loadIrcGutterPx() }
      setIrcGutterDragging(true)
    },
    [],
  )
  const onIrcRailPointerMove = useCallback((event: React.PointerEvent<HTMLSpanElement>) => {
    const drag = ircDragRef.current
    if (!drag) return
    saveIrcGutterPx(drag.startWidth + (event.clientX - drag.startX))
  }, [])
  const onIrcRailPointerUp = useCallback((event: React.PointerEvent<HTMLSpanElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    ircDragRef.current = null
    setIrcGutterDragging(false)
  }, [])
  const onIrcRailDoubleClick = useCallback(() => {
    saveIrcGutterPx(IRC_GUTTER_DEFAULT_PX)
  }, [])
  useEffect(() => {
    const sync = () => setIrcGutterPx(loadIrcGutterPx())
    window.addEventListener(IRC_GUTTER_CHANGED_EVENT, sync)
    return () => window.removeEventListener(IRC_GUTTER_CHANGED_EVENT, sync)
  }, [])
  // #506: Settings is a second bubble-theme writer — keep an already-mounted
  // transcript in sync instead of going stale until reload.
  useEffect(() => {
    const onThemeChanged = (event: Event) => {
      const detail = (event as CustomEvent<BubbleTheme>).detail
      if (detail) setBubbleTheme(detail)
      else setBubbleTheme(loadBubbleTheme())
    }
    const onStorage = (event: StorageEvent) => {
      if (event.key === BUBBLE_THEME_STORAGE_KEY || event.key === null) {
        setBubbleTheme(loadBubbleTheme())
      }
      if (
        event.key === COMPOSER_SHOW_PROVIDER_STORAGE_KEY ||
        event.key === null
      ) {
        setComposerShowProvider(initialComposerShowProvider())
      }
    }
    const onComposerShowProviderChanged = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail
      setComposerShowProvider(typeof detail === 'boolean' ? detail : initialComposerShowProvider())
    }
    window.addEventListener(BUBBLE_THEME_CHANGED_EVENT, onThemeChanged)
    window.addEventListener('storage', onStorage)
    window.addEventListener(
      COMPOSER_SHOW_PROVIDER_SET_EVENT,
      onComposerShowProviderChanged,
    )
    return () => {
      window.removeEventListener(BUBBLE_THEME_CHANGED_EVENT, onThemeChanged)
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(
        COMPOSER_SHOW_PROVIDER_SET_EVENT,
        onComposerShowProviderChanged,
      )
    }
  }, [])
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
  // #516: the Plugins panel is a second face of the `+` menu — same anchor,
  // same Escape/outside-close behavior — so the menu cannot show both at once.
  const [pluginsPanelOpen, setPluginsPanelOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
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
  // #543: the herdr agent picker — the talk-to choice for a herdr seat, listed
  // from GET /v1/herdr-agents/ (configured agents only; discovery stays in
  // Settings). null = closed.
  const [herdrPickerOpen, setHerdrPickerOpen] = useState(false)
  const herdrAgentsQuery = useQuery({
    queryKey: ['herdr-agents-chat'],
    queryFn: fetchHerdrAgents,
    enabled: herdrPickerOpen,
    retry: 1,
  })
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
  const [expandedThinkingKeys, setExpandedThinkingKeys] = useState<Set<string>>(new Set())
  const [rawResponseModalText, setRawResponseModalText] = useState<string | null>(null)
  const toggleThinking = useCallback((key: string) => {
    setExpandedThinkingKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])
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
  // #885: track whether the current thread incarnation has actually streamed.
  // The drain hold uses this to tell the #229 reset race (awaiting cleared,
  // harness has streamed nothing yet) apart from a genuine turn completion.
  const streamSeenRef = useRef(false)
  useEffect(() => {
    streamSeenRef.current = false
  }, [threadKey, conversationId])
  useEffect(() => {
    if (messages.some((row) => row.streaming === true)) streamSeenRef.current = true
  }, [messages])
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

  // REQ-912 / REQ-914 / REQ-917: the rail and the routines calendar are siblings
  // of this page, not descendants, so the selected seat is published rather than
  // re-derived per surface. Published next to the chat scope so the two cannot
  // drift, but kept a separate signal — see lib/currentAgent.ts.
  useEffect(() => {
    publishCurrentAgent(activeChatAgentId ? { id: activeChatAgentId, kind: agentKind } : null)
  }, [activeChatAgentId, agentKind])

  useEffect(() => {
    setReplyTarget(null)
    setContextMenu(null)
    setHiddenSummaryIds([])
    setHiddenMessageKeys([])
  }, [threadKey])

  useEffect(() => {
    if (!contextMenu) {
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

  // #846: a right-click's mousedown collapses the DOM selection before
  // `contextmenu` fires (Chromium/WebKit), so the live read can be empty even
  // when the user has a highlight. Cache the last selection seen per row on
  // mouseup, and block the collapse on right-button mousedown long enough for
  // the context menu to read it.
  const activeSelectionRef = useRef<CachedBubbleSelection | null>(null)
  const cacheRowSelection = useCallback((messageKey: string, row: Element | null) => {
    const text = getScopedSelectionText(row)
    activeSelectionRef.current = text ? { messageKey, text } : null
  }, [])

  const handleBubbleContextMenu = useCallback(
    (event: React.MouseEvent<HTMLDivElement>, message: ChatMessage) => {
      if (message.streaming) return
      event.preventDefault()
      const selectedText = resolveReplyQuote({
        targetElement: event.currentTarget,
        cached: activeSelectionRef.current,
        messageKey: message.key,
      })
      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        message,
        selectedText,
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
    // #726: CLI agents rarely change — 60s keeps the list fresh enough
    staleTime: 60_000,
  })
  const teamsQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
    staleTime: 60_000,
  })
  const remotesQuery = useQuery({
    queryKey: ['configured-remotes'],
    queryFn: fetchConfiguredRemotes,
    staleTime: 60_000,
  })
  const llmProfilesQuery = useQuery({
    queryKey: ['llm-profiles'],
    queryFn: fetchLlmProfiles,
    // #726: LLM profiles are user-configured and rarely change
    staleTime: 120_000,
  })
  const remotesListQuery = useQuery({
    queryKey: ['remotes-list'],
    // #581: coalesced GET /v1/remotes/ — same network call as the
    // 'configured-remotes' query, no duplicate volley on seat selection.
    queryFn: fetchRemotes,
    staleTime: 60_000,
  })
  const speechQuery = useQuery({
    queryKey: SPEECH_QUERY_KEY,
    queryFn: () => fetchSpeechSettings(false),
    // #726: speech probe result is stable — 2 min is fine
    staleTime: 120_000,
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
  // #528: a team selection loses the navbar avatar that single agents get. The
  // member to show is "the one you are talking to": the navbar's explicit member
  // when one is targeted, else `defaultSessionForTeam`'s rule (chief_of_staff_id,
  // else CoS role, else first) — the same rule the rail's team row reads, so the
  // two surfaces cannot disagree about which face represents the team.
  const teamChatMemberId =
    teamFromUrl && selectedTeam
      ? memberTarget && memberTarget !== ALL_MEMBERS_TARGET
        ? memberTarget
        : (defaultSessionForTeam(selectedTeam)?.memberId ?? '')
      : ''
  const headerFaceAgentId = teamFromUrl
    ? teamChatMemberId || teamFromUrl
    : agentIdFromBlueprint(selectedBlueprint) || selectedBlueprint || ''
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
          ? // #543: a herdr session names the herdr AGENT being talked to —
            // surface it as the seat name, not just the provider.
            selectedRemoteSession?.name ||
            (isHerdrKind(remoteFromUrl) && sessionFromUrl
              ? sessionFromUrl
              : selectedRemote?.title || remoteFromUrl)
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
    agentKind,
    blueprintId: selectedBlueprint,
  })
  notifyCtxRef.current = {
    agentId: activeChatAgentId,
    agentName: remoteFromUrl
      ? remoteDisplayName(selectedRemote || { id: remoteFromUrl, title: selectedAgentName })
      : selectedAgentName,
    agentKind,
    blueprintId: selectedBlueprint,
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

  const isHerdrSeat =
    isHerdrKind(remoteFromUrl) ||
    isHerdrKind(selectedRemote?.kind) ||
    isHerdrKind(selectedRemoteId) ||
    isHerdrAgent(selectedAgent as { id?: string; kind?: string }) ||
    Boolean(selectedBlueprint && isHerdrAgent({ id: selectedBlueprint }))

  /* #594: same loading-state contract as the rail — `cliQuery` has no
     `initialData`, so reading it before it settles must not be read as "this
     server advertises nothing". */
  const productModes = useMemo(
    () =>
      productModesWhenSettled({
        data: cliQuery.data,
        settled: !cliQuery.isPending,
        failed: cliQuery.isError,
      }),
    [cliQuery.data, cliQuery.isPending, cliQuery.isError],
  )
  const showRemotesControl =
    Boolean(remoteFromUrl) ||
    (productModes.remote && (isRemoteAgent || isRemoteBackedTeam))
  // REQ-904 / #502: the binding subject is the agent — never the provider.
  // With `?remote=X` in the URL the user is viewing a remote *seat*; there is
  // no named agent in context, so nothing may be written under X itself.
  const bindingAgentId = resolveAgentBindingSubject({ remoteFromUrl, selectedBlueprint })
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
  // #504: the cross-kind union the routing palette's "show all" reveals. Each
  // row declares its kind so a pick outside the current scope navigates (#502)
  // instead of rebinding the current seat.
  const allPaletteAgents = useMemo(() => {
    const rows: Array<{ id: string; label: string; kind: 'api' | 'cli' | 'remote' | 'team' }> = []
    for (const bp of blueprints) {
      rows.push({ id: bp.id, label: bp.name || bp.id, kind: 'api' })
    }
    for (const cli of cliAgents) {
      rows.push({ id: cli.id, label: cli.name || cli.id, kind: 'cli' })
    }
    for (const remote of remotes) {
      rows.push({ id: remote.id, label: remote.title || remote.id, kind: 'remote' })
    }
    for (const team of teams) {
      rows.push({ id: team.id, label: team.name || team.id, kind: 'team' })
    }
    return rows
  }, [blueprints, cliAgents, remotes, teams])
  // #502 doctrine: choosing an out-of-scope agent navigates to it — it never
  // rewrites the current seat's provider/model binding.
  // #804: the destination kind decides which seat param gets written —
  // ?blueprint= for api, ?cli= for cli (the param the CLI resolution chain
  // actually consumes), ?remote=/ ?team= as before — and every other kind's
  // marker plus per-seat state (?session=, ?model=) is dropped so nothing
  // bleeds across. The old code wrote a dead ?agent= that nothing read.
  const navigateToPaletteAgent = useCallback(
    (
      targetId: string,
      kind?: RoutingSeatKind | 'team',
      detail?: { apiModel?: string },
    ) => {
      const pickKind: SeatPickKind =
        kind === 'cli' ? 'cli' : kind === 'remote' ? 'remote' : kind === 'team' ? 'team' : 'api'
      const patch = seatParamsForPick(pickKind, targetId, { apiModel: detail?.apiModel })
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        for (const key of patch.delete) next.delete(key)
        for (const [key, value] of Object.entries(patch.set)) next.set(key, value)
        return next
      })
    },
    [setSearchParams],
  )
  const ombRemoteId = isOpenMousBotKind(selectedRemoteId)
    ? selectedRemoteId
    : isOpenMousBotKind(remoteFromUrl)
      ? remoteFromUrl
      : ''
  const activeRemoteId = (selectedRemoteId || remoteFromUrl || '').trim()
  const remoteAgentsQuery = useQuery({
    queryKey: ['remote-operate-list', activeRemoteId],
    queryFn: () => operateRemote(activeRemoteId, { op: 'list' }, { timeoutMs: 12000 }),
    enabled: showRemotesControl && Boolean(activeRemoteId),
    retry: 1,
  })
  const remoteNavbarAgents = useMemo(
    () => (activeRemoteId ? remoteAgentsFromOperate(remoteAgentsQuery.data?.data) : []),
    [activeRemoteId, remoteAgentsQuery.data],
  )
  const remoteAgentWarning = !activeRemoteId
    ? null
    : remoteAgentsQuery.isError
      ? remoteAgentsQuery.error instanceof Error
        ? // #581: throttle errors get a friendly toast (see effect below) and
          // never raw throttler prose in the picker warning.
          isThrottleError(remoteAgentsQuery.error)
          ? ''
          : remoteAgentsQuery.error.message
        : 'Remote agent list failed'
      : remoteAgentsQuery.isSuccess && remoteAgentsQuery.data?.ok === false
        ? remoteAgentsQuery.data.detail || 'No agents listed on this remote'
        : remoteAgentsQuery.isSuccess && remoteNavbarAgents.length === 0 && ombRemoteId
          ? OMB_NO_AGENTS_WARNING
          : null
  const ombSelectedBotId = ombSendTarget(sessionFromUrl, ombRemoteId || remoteFromUrl)
  // #581: any failed remote query that trips the throttle shows one friendly
  // retry toast with the countdown — never the raw DRF line.
  const throttleToastRef = useRef(0)
  useEffect(() => {
    const err = remoteAgentsQuery.error
    if (!isThrottleError(err)) return
    const now = Date.now()
    if (now - throttleToastRef.current < 10_000) return
    throttleToastRef.current = now
    addToast({
      type: 'error',
      title: 'Slow down a moment',
      message: err.message,
    })
  }, [remoteAgentsQuery.error, addToast])

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
  // #566: one resolution chain, shared with the audit log. `cliSource` says
  // where the value came from — an `inferred` pick is a fallback guess and must
  // never be presented as the seat's own choice; a non-CLI seat resolves no CLI
  // at all, so a remote agent can no longer end up labelled with a CLI it does
  // not use.
  const cliResolution = useMemo(
    () =>
      resolveCurrentCli({
        isCliSeat: isCliAgent,
        param: searchParams.get('cli') ?? '',
        persisted: persistedDropdown.cli ?? '',
        declared: selectedCli?.cli ?? '',
        discovered: discoveredClis,
        preferred: (clis) => preferredChatCli(clis, ''),
      }),
    [isCliAgent, searchParams, persistedDropdown.cli, selectedCli, discoveredClis],
  )
  const currentCli = cliResolution.cli
  const currentCliSource = cliResolution.source

  // #550: the composer `+` menu's contents are derived from the seat rather than
  // hardcoded per item, so an item cannot be added ungated. See lib/composerMenu.
  // #636: CLI Compact lights up when a default API is configured (the same
  // `default_llm_ready` signal DefaultLlmTip consumes) or when the seat's CLI
  // declares a native cli_compact hook in the catalog.
  // #551: the kind base's published declarations (GET /v1/cli-agents/), when
  // the backend publishes them. The seat's own kind row wins; older payloads
  // leave this undefined and the menu falls back to the kind-derived gates.
  const declaredCapabilities = useMemo(() => {
    const payload = cliQuery.data as { seat_capabilities?: Record<string, Record<string, { enabled: boolean; reason: string }>> } | undefined
    const published = payload?.seat_capabilities
    if (!published) return undefined
    const kindKey = isCliAgent ? 'cli' : isRemoteAgent || isRemoteBackedTeam ? 'remote' : 'api'
    return published[kindKey]
  }, [cliQuery.data, isCliAgent, isRemoteAgent, isRemoteBackedTeam])

  const composerMenu = composerMenuCapabilities({
    isApi: isApiAgent,
    isCli: isCliAgent,
    isRemote: isRemoteAgent || isRemoteBackedTeam,
    defaultLlmReady: llmProfilesQuery.data?.default_llm_ready === true,
    cliCompactCapable: Boolean(
      isCliAgent &&
        currentCli &&
        (cliQuery.data?.cli_compact as Record<string, unknown> | undefined)?.[currentCli],
    ),
    // #830: the reason names the PROVIDER ("not implemented for Herdr"), and
    // a remote that declares a native compact hook gains the action — the
    // remote analogue of #636's cli_compact. No catalog payload carries a
    // compact flag yet, so nothing lights up until a provider ships one.
    providerName: selectedRemote ? remoteDisplayName(selectedRemote) : undefined,
    remoteCompactCapable: Boolean(
      (selectedRemote?.capabilities as { compact?: boolean } | undefined)?.compact,
    ),
    // #516: the same swarm-owned reading the rail's Plugins entry gates on,
    // using the exact seat pair ChatPage publishes (id + kind) so the composer
    // menu cannot disagree with the badge.
    pluginsSwarmOwned: isSwarmOwnedAgent(activeChatAgentId || '', agentKind),
    // #551: declarations outrank kind-derived gates (one channel, ADR-005).
    declaredCapabilities,
  })

  /** The agent's own configured remote endpoint, if any. */
  const agentRemote = useMemo(
    () => loadAgentEdit(selectedBlueprint).remote,
    [selectedBlueprint],
  )

  /**
   * #570: choices for the CLI session's remote box.
   *
   * There is deliberately **no `Local` row**. An empty value means "follow the
   * agent's own endpoint", which is also the state the select falls back to, so a
   * `Local` row duplicated the agent's endpoint in the common case — and was the
   * *only* row when the agent has no remote, i.e. a control offering a choice of
   * one. Instead:
   *
   *  - the agent's own endpoint is the default row (labelled with the endpoint, or
   *    `This host` when the agent has none), so the default is named by what it
   *    actually is rather than by a synonym for "not remote";
   *  - the listed boxes exclude that endpoint, so nothing is offered twice;
   *  - the picker is only rendered when at least one *other* box is discovered,
   *    because otherwise there is nothing to choose.
   *
   * This also fixes a silent misreport: the previous option value was
   * `remote.box || remoteEndpointLabel(remote)` while the select's value was
   * `remote.box || ''`, so an agent with `remote.host` and no `remote.box` had a
   * value matching no option and the browser displayed the first row (`Local`).
   */
  const cliRemoteSession = useMemo(
    () => cliRemoteSessionChoices(agentRemote, cliQuery.data?.remote_boxes),
    [agentRemote, cliQuery.data],
  )

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

  // #899: a cross-kind API-profile pick is a PROVIDER reconfiguration for the
  // current seat, never a seat jump — navigating to api_agent here dropped the
  // user's CLI/remote context. Until per-seat backend override exists, the
  // honest behavior is to keep the seat and say exactly what happened.
  const reconfigureProviderForSeat = useCallback(
    (profile: string) => {
      const kind: 'api' | 'cli' | 'remote' | 'team' =
        isRemoteAgent || isRemoteBackedTeam ? 'remote' : isCliAgent ? 'cli' : 'api'
      const statusMsg: ChatMessage = {
        key: `provider-reconfigure-${Date.now()}`,
        role: 'status',
        text: providerReconfigureNotice(profile, kind),
        streaming: false,
        ts: new Date().toISOString(),
      }
      setThreads((prev) => ({
        ...prev,
        [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
      }))
    },
    [isRemoteAgent, isRemoteBackedTeam, isCliAgent, threadKey],
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
        if (cancelled) return
        // #852: landing on a session-capable remote without a session in the
        // URL goes to the most recent conversation directly — the picker is
        // an explicit navbar action, never an automatic modal on click.
        const latest = mostRecentRemoteSession(sessions)
        if (latest) {
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev)
              next.set('remote', remoteFromUrl)
              next.set('session', String(latest.memberId || latest.id))
              return next
            },
            { replace: true },
          )
          return
        }
        setRemoteThreadPicker(null)
      })
      .catch(() => {
        if (!cancelled) setRemoteThreadPicker(null)
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
    // #581: a 429 shows the friendly retry toast (with countdown), never
    // raw throttler prose — the typed message from lib/api is already clean.
    if (isThrottleError(err)) {
      addToast({
        type: 'error',
        title: 'Slow down a moment',
        message: err.message,
      })
      setThreadReady(true)
      return
    }
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
    // #604/REQ-171A-4: never pre-wipe the destination rows before the hydrate
    // fetch — a failed fetch must keep the previous messages on screen with
    // the keep-toast, not an empty transcript. Freshness comes from flush=1.
    setConversationId(key)
    setEditingKey(null)
    setAgentKind('api')
    setMessagesEditable(false)
    userKeyCounterRef.current = 0
    let cancelled = false
    ;(async () => {
      try {
        const thread = await fetchAgentThread(key, key, { flush: switched })
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
          [key]: hydrateThreadRows(thread.messages),
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
      // #604/REQ-171A-4: no pre-wipe (see the API/team hydrate above).
      setConversationId(key)
      setEditingKey(null)
      setAgentKind('remote')
      setMessagesEditable(false)
      userKeyCounterRef.current = 0
      let cancelled = false
      ;(async () => {
        try {
          // Same GET /chat/thread/ path as API/team — do not return early (REQ-171A-4 / #604).
          const thread = await fetchAgentThread(`remote:${remoteFromUrl}`, key, { flush: switched })
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
            [key]: hydrateThreadRows(thread.messages),
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
    // #604/REQ-171A-4: no pre-wipe (see the API/team hydrate above).
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
        const thread = await fetchAgentThread(agent, resolvedSession || undefined, { flush: switched })
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
          [threadKey]: hydrateThreadRows(thread.messages),
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
      const waitAgent = tool.agentId || selectedBlueprint || threadKey
      notifyApprovalWait(waitAgent, tool.id, Boolean(tool.needsApproval))
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
                ts: new Date().toISOString(),
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
    [selectedBlueprint, threadKey],
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
                ts: new Date().toISOString(),
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
      if (event.kind === 'aux_started' || event.kind === 'aux_update') {
        // #818: background LLM work surfaces in the navbar indicator.
        setAuxTasks((prev) => {
          const next = applyAuxFrame(
            prev,
            event.kind === 'aux_started'
              ? { type: 'aux_task_started', ...event.task }
              : { type: 'aux_task_update', ...event.task },
          )
          announceAuxTasks(next)
          return next
        })
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
                ts: new Date().toISOString(),
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
                ts: new Date().toISOString(),
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
                ts: new Date().toISOString(),
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
                ts: new Date().toISOString(),
              },
            ]
            break
          case 'assistant_start':
            if (current.some((m) => m.key === event.id)) return prev
            next = [
              ...current,
              // #774: stamp arrival time now — the row's clock must not wait
              // for final text, or the IRC gutter shows nothing for the turn.
              { key: event.id, role: 'assistant', text: '', streaming: true, ts: new Date().toISOString() },
            ]
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
              const rawResp =
                typeof (event as { raw_response?: string }).raw_response === 'string'
                  ? (event as { raw_response?: string }).raw_response
                  : m.rawResponse
              return {
                ...m,
                text: fence ? stripDecisionQuestion(event.text) : event.text,
                rawResponse: rawResp,
                streaming: false,
                question: m.question ?? fence ?? undefined,
                questionBlocking: m.questionBlocking ?? false,
              }
            })
            break
          case 'status':
            // #534: compression notices belong to API seats only. Remote/CLI
            // seats manage their own context — never show the notice.
            if (
              isCompressionNoticeText(event.text) &&
              !isSwarmOwnedAgent(notifyCtxRef.current.blueprintId, notifyCtxRef.current.agentKind)
            ) {
              break
            }
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
              ts: new Date().toISOString(),
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

  // #738: stable ref so the WS effect doesn't list handleWsEvent as a dep.
  // The socket only rebuilds when connection coords change (conversationId,
  // runtimeBlueprint, teamFromUrl) — not on every inner state change.
  const handleWsEventRef = useRef(handleWsEvent)
  useEffect(() => {
    handleWsEventRef.current = handleWsEvent
  })

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
        handleWsEventRef.current(parseChatWsMessage(event.data))
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
      if (ws.readyState === 0) {
        // #738: closing during CONNECTING is what Chrome logs as "WebSocket
        // is closed before the connection established". Defer to the next
        // macrotask: if the handshake completes first, close() is legal from
        // OPEN (silent); if it fails first, onclose already ran and the
        // guard below makes close() a no-op. Either way no mid-handshake
        // teardown, and handlers are already detached so no events leak.
        setTimeout(() => {
          try {
            ws.close()
          } catch {
            /* already closed */
          }
          if (wsRef.current === ws) wsRef.current = null
        }, 0)
      } else {
        ws.onclose = null
        ws.close()
        if (wsRef.current === ws) wsRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectAttempt, conversationId, runtimeBlueprint, teamFromUrl])

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

  // #678: gate the navbar name's fade on actual truncation. The mask must
  // not engage while the name fits — the header's other items are not greedy
  // (shrink-0 clusters aside, the identity card owns the remaining width).
  const identityTitleRef = useRef<HTMLHeadingElement | null>(null)
  useLayoutEffect(() => {
    const title = identityTitleRef.current
    if (!title) return undefined
    const apply = () => {
      const clipped = title.scrollWidth > title.clientWidth
      title.dataset.truncated = clipped ? 'true' : 'auto'
    }
    apply()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(apply)
    observer.observe(title)
    return () => observer.disconnect()
  }, [selectedAgentName, workspaceSubtitle])

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
  // #595: one signal for the composer's trailing controls — the Stop button
  // swaps into the microphone's slot while a turn is in flight, so the row
  // keeps a constant control count and never shifts under the pointer.
  const composerBusy = status === 'open' && generationIsInFlight(messages, awaitingAssistant)

  const [composerDragOver, setComposerDragOver] = useState(false)
  const dragCounterRef = useRef(0)

  const handleComposerDragEnter = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!dataTransferHasFiles(event.dataTransfer?.types)) return
    event.preventDefault()
    dragCounterRef.current += 1
    if (dragCounterRef.current === 1) {
      setComposerDragOver(true)
    }
  }, [])

  const handleComposerDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!dataTransferHasFiles(event.dataTransfer?.types)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const handleComposerDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!dataTransferHasFiles(event.dataTransfer?.types)) return
    event.preventDefault()
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
    if (dragCounterRef.current === 0) {
      setComposerDragOver(false)
    }
  }, [])

  const enqueueComposerFiles = useCallback((files: File[]) => {
    if (files.length === 0) return
    const room = Math.max(0, 8 - pendingAttachments.length)
    const incoming = files.slice(0, room).map(createPendingAttachment)
    if (incoming.length === 0) return
    setPendingAttachments((prev) => [...prev, ...incoming])
    incoming.forEach((item) => {
      void uploadChatAttachment(item.file, item.abortController?.signal)
        .then((record) => {
          setPendingAttachments((prev) =>
            prev.map((row) =>
              row.localId === item.localId
                ? { ...row, uploadId: record.id, status: 'ready' }
                : row,
            ),
          )
        })
        .catch((err: unknown) => {
          if (
            (err instanceof DOMException && err.name === 'AbortError') ||
            (err as { name?: string })?.name === 'AbortError'
          ) {
            return
          }
          setPendingAttachments((prev) =>
            prev.map((row) =>
              row.localId === item.localId ? { ...row, status: 'error' } : row,
            ),
          )
        })
    })
  }, [pendingAttachments.length])

  const handleComposerDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!dataTransferHasFiles(event.dataTransfer?.types)) return
      event.preventDefault()
      dragCounterRef.current = 0
      setComposerDragOver(false)
      if (!composerMenu.addFiles.enabled) {
        addToast({
          type: 'info',
          title: 'Add files',
          message: `${composerMenu.addFiles.reason}. Switch to an API agent to attach.`,
        })
        return
      }
      const files = filesFromList(event.dataTransfer?.files)
      if (files.length > 0) {
        enqueueComposerFiles(files)
      }
    },
    [addToast, composerMenu.addFiles.enabled, composerMenu.addFiles.reason, enqueueComposerFiles],
  )

  const handleComposerPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      const files = imageFilesFromClipboard(event.clipboardData)
      if (files.length === 0) return
      event.preventDefault()
      if (!composerMenu.addFiles.enabled) {
        addToast({
          type: 'info',
          title: 'Add files',
          message: `${composerMenu.addFiles.reason}. Switch to an API agent to attach.`,
        })
        return
      }
      enqueueComposerFiles(files)
    },
    [addToast, composerMenu.addFiles.enabled, composerMenu.addFiles.reason, enqueueComposerFiles],
  )

  const clearPendingAttachments = useCallback(() => {
    setPendingAttachments((prev) => {
      prev.forEach((item) => {
        item.abortController?.abort()
        revokePreviewUrl(item.previewUrl)
      })
      return []
    })
  }, [])

  const pendingAttachmentsRef = useRef(pendingAttachments)
  useEffect(() => {
    pendingAttachmentsRef.current = pendingAttachments
  }, [pendingAttachments])

  useEffect(() => {
    return () => {
      pendingAttachmentsRef.current.forEach((item) => {
        item.abortController?.abort()
        revokePreviewUrl(item.previewUrl)
      })
    }
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
      // #516: the allowlist is the **agent's**, keyed by the same seat id the
      // toggles and the badge read — never the conversation id.
      const pluginParams = enabledToolsParam(activeChatAgentId || '')
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
          // #852: a session-capable remote with no chosen session sends
          // fresh instead of blocking the turn behind a picker toast. Users
          // resume explicitly from the navbar session button.
          ws.send(
            buildChatWsFrame(trimmed, 'remote_harness', {
              ...remoteChatTurnParams(remoteFromUrl, sessionFromUrl),
              ...pluginParams,
              ...sectionParams,
            }, attachArg),
          )
          return true
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
      const cliParams = isCliAgent && currentCli
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
      // #566: audit from the value the frame actually carries — the log is a
      // record of this send, not a parallel derivation of it.
      recordBackendUse({
        agentId: agentIdForInference,
        agentName: selectedAgentName,
        kind: isCliAgent ? 'cli' : isApiAgent ? 'api' : agentKind,
        backend: isCliAgent ? (currentCli || '(none)') : (selectedModelParam || 'default'),
        cliSource: isCliAgent ? currentCliSource : null,
      })
      clearPendingAttachments()
      return true
    },
    [
      runtimeBlueprint,
      selectedBlueprint,
      selectedCli,
      isCliAgent,
      currentCli,
      currentCliSource,
      currentCliModel,
      persistedDropdown.model,
      persistedDropdown.cli,
      persistedDropdown.api,
      isApiAgent,
      agentKind,
      selectedAgentName,
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
      activeChatAgentId,
    ],
  )

  const submitUserText = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      const readyAttach = readyAttachmentIds(pendingAttachments)
      if (!trimmed && readyAttach.length === 0) return
      // REQ-845 / #167: never drop a typed message on a closed/connecting socket. Keep
      // it in the per-conversation queue; the drain effect sends it on reopen.
      if (status !== 'open') {
        const fallbackText =
          trimmed ||
          (readyAttach.length > 0
            ? attachmentCaption(pendingAttachments.map((item) => item.name))
            : '')
        if (fallbackText) {
          queued.enqueue(fallbackText)
          addToast({
            type: 'info',
            title: 'Queued',
            message: 'Chat is reconnecting — your message will send when the socket is back.',
          })
        }
        return
      }
      // REQ-171A-3 / #603: queue before assistant_start, not only while
      // streaming. REQ-90 / #447 owns the pane chrome; this only closes
      // the pre-start double-{message} race.
      // #561: mid-generation queueing is a non-API affordance — a CLI/remote
      // turn is serial and a typed message must survive it. A proven API seat
      // takes a concurrent message instead, so only the transport queue above
      // (the closed-socket branch, kept for every kind) applies to it. Teams
      // and remotes keep queueing: their members run serially.
      //
      // "API" must be *proven*, not defaulted: classifyAgentKind falls back to
      // 'api' for any unknown id, and treating a stale-catalog CLI seat as
      // concurrent would corrupt its serial session. Proven = the id itself
      // (api_agent / api / api:*) or the server-declared blueprint kind. A
      // false queue merely waits for the drain; a false concurrent send cannot
      // be undone.
      if (generationIsInFlight(messages, awaitingAssistant)) {
        const apiSeatProven =
          isApiBlueprintId(selectedBlueprint) ||
          (selectedAgent as { kind?: string } | undefined)?.kind === 'api'
        if (!apiSeatProven) {
          const fallbackText =
            trimmed ||
            (readyAttach.length > 0
              ? attachmentCaption(pendingAttachments.map((item) => item.name))
              : '')
          if (fallbackText) {
            queued.enqueue(fallbackText)
          }
          return
        }
      }
      setAwaitingAssistant(true)
      if (!sendText(trimmed)) setAwaitingAssistant(false)
    },
    [
      addToast,
      awaitingAssistant,
      messages,
      pendingAttachments,
      queued,
      selectedAgent,
      selectedBlueprint,
      sendText,
      status,
    ],
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
  // #499: the banner's primary action opens Settings on the section that can
  // actually resolve the failure — session actions stay as secondary options.
  const cliRecoveryConfigTarget = showCliSessionRecovery
    ? lastRecoveryTarget(messages)
    : undefined

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
    const textToSend = replyTarget
      ? buildOutboundReplyText(replyTarget, input)
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

  // #641: the CLI seat's own declared slash commands, straight from the
  // cli-agents catalog (`slash_commands[<cli>]`). A non-CLI seat resolves no
  // CLI here, so API/team/remote composers keep their existing catalog.
  const cliSlashCommands = useMemo(() => {
    if (!isCliAgent) return undefined
    const cliName = currentCli || selectedCli?.cli || ''
    if (!cliName) return undefined
    return cliQuery.data?.slash_commands?.[cliName]
  }, [isCliAgent, currentCli, selectedCli, cliQuery.data])

  const slashCatalog = useMemo(
    () => buildSlashCatalog(dynamicSkills, cliSlashCommands),
    [dynamicSkills, cliSlashCommands],
  )
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
    if (!plusOpen) {
      // #516: closing the menu returns it to the actions face.
      setPluginsPanelOpen(false)
      return
    }
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
    // #885: a remote seat whose harness has not streamed yet cannot be
    // trusted to be "not in flight" — the #229 seat reset clears
    // awaitingAssistant before the harness's first frames arrive, and
    // draining in that gap removes the row before its pane ever renders.
    if (
      drainHoldUntilStreamStarts(isRemoteAgent || isRemoteBackedTeam ? 'remote' : 'api') &&
      !streamSeenRef.current
    ) {
      return
    }
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
  }, [awaitingAssistant, messages, queued, queuedHoldIds, sendText, status, isRemoteAgent, isRemoteBackedTeam])

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
    // #636: a CLI seat compacts through the same server-side summary and then
    // starts a fresh CLI session carrying it. The old provider transcript
    // stays on disk; the new process starts clean with the summary in context.
    if (isCliAgent) {
      const cliName = currentCli || selectedCli?.cli || ''
      if (!cliName) {
        addToast({
          type: 'error',
          title: 'Compact failed',
          message: 'No CLI is resolved for this seat.',
        })
        return
      }
      try {
        const result = await compactCliThread({
          conversationId,
          agentId: selectedBlueprint || '',
          cli: cliName,
          messages: messages
            .filter((message) => message.role === 'user' || message.role === 'assistant')
            .map((message) => ({ role: message.role, content: message.text })),
          defaultLlmReady: llmProfilesQuery.data?.default_llm_ready === true,
          cliCompactCapable: Boolean(
            (cliQuery.data?.cli_compact as Record<string, unknown> | undefined)?.[cliName],
          ),
        })
        dispatchCliSessionHopped({
          agentId: selectedBlueprint || '',
          conversationId: result.newConversationId,
          status: result.status,
          fromCli: cliName,
          toCli: cliName,
        })
        setConversationId(result.newConversationId)
      } catch (err) {
        const detail = err instanceof Error ? err.message.trim() : ''
        addToast({
          type: 'error',
          title: 'Compact failed',
          message: detail || 'Could not compact this chat. Sign in and try again.',
        })
      }
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
  }, [addToast, conversationId, messages, selectedBlueprint, teamFromUrl, threadKey, isCliAgent, currentCli, selectedCli, llmProfilesQuery.data, cliQuery.data])

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
      // #641: an unavailable CLI command is never sent as chat text.
      if (item.unavailableReason) {
        addToast({
          type: 'warning',
          title: item.title,
          message: item.unavailableReason,
        })
        setSlashDismissed(true)
        return
      }
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
    [handleCompact, addToast],
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
        const textToSend = replyTarget
          ? buildOutboundReplyText(replyTarget, input)
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
  // #561: with a queued send waiting, Enter on the empty composer sends that
  // row now (the interrupt path — see handleComposerKeyDown). Say so on the
  // input-hover hint instead of the default "Enter to send".
  const sendNowHint =
    !input.trim() && nextDrainableQueuedSend(queued.rows, queuedHoldIds) !== null
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
    queryFn: () => fetchCliSessions(selectedBlueprint, currentCli),
    enabled: productModes.cli && isCliAgent && Boolean(currentCli) && composerSessionsOpen,
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

  // #711: picking a session runs the same REQ-104 flow as the History
  // switcher — select, persist workspace, announce the switch, land on it.
  const resumeComposerSession = useCallback(
    async (sessionId: string) => {
      if (!isCliAgent || !currentCli) return
      try {
        const result = await selectCliSession({
          agentId: selectedBlueprint,
          cli: currentCli,
          sessionId,
          fromConversationId: conversationIdForAgent(selectedBlueprint),
        })
        persistSessionWorkspace(selectedBlueprint, {
          folder: result.folder ?? undefined,
          gitBranch: result.git_branch ?? undefined,
        })
        dispatchCliSessionSwitched({
          agentId: selectedBlueprint,
          conversationId: result.conversation_id,
          status: result.status,
        })
        // #794: the URL owns the selected session — set ?session= so remount
        // and rail browse-back restore the same conversation.
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          next.set('session', result.conversation_id)
          return next
        })
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : 'Could not switch session'
        addToast({ type: 'error', title: 'Could not start CLI session', message })
      }
    },
    [isCliAgent, currentCli, selectedBlueprint, setSearchParams, addToast],
  )

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
    ],
  )
  const composerProviders = useMemo(
    () => buildComposerProviders(composerSources),
    [composerSources],
  )
  const renderRoutingPicker = () => {
    if (!composerShowProvider) return null
    if (showRemotesControl && !showEmptyRemoteChrome) {
      return (
        <NavbarRoutingPicker
          seatKind="remote"
          aria-label="Remote"
          placeholder={remoteSelectPlaceholder(configuredRemoteRows.length, selectedRemoteId)}
          agents={configuredRemoteRows.map((remote) => ({
            id: remote.id,
            label: remoteOptionLabel(remote, remoteKinds(remotesCatalog)),
            kind: 'remote' as const,
          }))}
          allAgents={allPaletteAgents}
          onNavigateAgent={navigateToPaletteAgent}
          onProviderReconfigure={reconfigureProviderForSeat}
          selectedAgent={selectedRemoteId}
          models={remoteNavbarAgents.map((row) => row.id)}
          modelOptions={remoteNavbarAgents}
          twoStage={{
            providers: composerProviders,
            getProviderOptions: (provider) =>
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
          onChange={(next) => {
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
            setSearchParams((prev) => {
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
    if (productModes.cli && isCliAgent) {
      return (
        <NavbarRoutingPicker
          seatKind="cli"
          aria-label="CLI"
          agents={discoveredClis.map((cli) => ({ id: cli, label: cli, kind: 'cli' as const }))}
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
            getProviderOptions: (provider) =>
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
    if (productModes.api && isApiAgent) {
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
          ).map((opt) => ({ id: opt.id, label: opt.label, kind: 'api' as const }))}
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
            getProviderOptions: (provider) =>
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

  return (
    <div className="os-chat flex h-full min-h-0 w-full flex-col">
      {/* #445: no `overflow-hidden` here. It clipped the routing flyout to the
          header's box (the flyout is an absolutely-positioned child of the
          picker inside this header), leaving only its first row reachable.
          Titles still clamp in `.os-navbar-identity-label`. */}
      {/* #445: no `overflow-hidden` here. It clipped the routing flyout to the
          header's box (the flyout is an absolutely-positioned child of the
          picker inside this header), leaving only its first row reachable.
          Titles still clamp in `.os-navbar-identity-label`. */}
      <header className="os-chat-header gap-1.5 sm:gap-3">
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
                  setGenerationsOpen((prev) => !prev)
                }}
              >
                <AgentAvatar
                  src={teamFromUrl ? undefined : selectedAgent?.avatar_path}
                  agentId={headerFaceAgentId}
                  active={isWorking}
                  status={isWorking ? 'working' : 'idle'}
                  size="lg"
                  gl
                  className="os-chat-header__avatar"
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
            onCancel={(taskId) => {
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
                configuredRemoteRows.find((row) => row.id === activeRemoteId)?.title ||
                selectedRemote?.title ||
                activeRemoteId
              }
              onSelectSession={(sessionId) => {
                setSearchParams((prev) => {
                  const params = new URLSearchParams(prev)
                  params.set('remote', activeRemoteId)
                  params.set('session', sessionId)
                  return params
                }, { replace: true })
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
              {/* #727: aria-hidden is invalid on <option>; <optgroup> renders a
                  visual separator line in all browsers and is screen-reader safe. */}
              <optgroup label="──────────" />
              <option value={MANAGE_TEAMS_VALUE}>Manage Team</option>
            </select>
          ) : null}
          {isCliAgent && currentCli ? (
            <CliSessionSwitcher
              agentId={selectedBlueprint}
              cli={currentCli}
              agentName={selectedAgentName}
            />
          ) : null}
          {isHerdrKind(remoteFromUrl) ? (
            /* #543: the herdr talk-to picker — which herdr AGENT this
               conversation targets. Same popup shape as the other pickers;
               selection lands in `?session=`, the URL that owns the target. */
            <button
              type="button"
              className="btn btn-xs btn-outline h-7 min-h-0 max-w-[14rem] font-medium"
              data-testid="herdr-agent-picker"
              aria-haspopup="dialog"
              onClick={() => setHerdrPickerOpen(true)}
            >
              <span className="truncate">{selectedAgentName || 'Herdr'}</span>
              <ChevronDown className="h-3 w-3 shrink-0" aria-hidden="true" />
            </button>
          ) : null}
          {productModes.api && isApiAgent ? (
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
                {/* #570: the default row replaces the old `Local` row. Selecting it
                    clears `?cli_remote` and returns the session to the agent's own
                    endpoint — so the default stays reachable without a synonym row. */}
                <option value="">{cliRemoteSession.defaultLabel}</option>
                {cliRemoteSession.boxes.map((box) => (
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

      <ConsumerPills providerId={activeChatAgentId} />
      {showRoleTip ? <RoleAgentTip onDismiss={dismissRoleTip} /> : null}
      {showDefaultLlmTip ? <DefaultLlmTip onDismiss={dismissDefaultLlmTip} /> : null}

      <span role="status" aria-live="polite" aria-atomic="true" aria-label="Connection status" className="sr-only">
        {statusLabel}
      </span>

      <div
        ref={scrollBoxRef}
        className="os-chat-transcript min-h-0 flex-1 space-y-1 overflow-y-auto px-2 py-3 sm:px-3 select-none outline-none focus:outline-none flex flex-col justify-between relative"
        data-composer-inset={composerInsetPx}
        data-bubble-theme={bubbleTheme}
        style={
          {
            ...((composerInsetCustomProperty(composerInsetPx) as CSSProperties) ?? {}),
            ...(themeUsesIrcGutter(bubbleTheme)
              ? ({ ['--irc-gutter-px' as string]: `${ircGutterPx}px` } as React.CSSProperties)
              : {}),
          } as React.CSSProperties
        }
        data-message-layout={getBubbleTheme(bubbleTheme).messageLayout}
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
        data-timestamp-placement={getBubbleTheme(bubbleTheme).timestampPlacement}
        data-action-row-placement={getBubbleTheme(bubbleTheme).actionRowPlacement}
        tabIndex={0}
        onScroll={handleTranscriptScroll}
      >
          {themeUsesIrcGutter(bubbleTheme) ? (
            <span
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize IRC name column"
              className="os-irc-gutter-rail"
              data-testid="irc-gutter-rail"
              data-dragging={ircGutterDragging ? 'true' : 'false'}
              onPointerDown={onIrcRailPointerDown}
              onPointerMove={onIrcRailPointerMove}
              onPointerUp={onIrcRailPointerUp}
              onPointerCancel={onIrcRailPointerUp}
              onDoubleClick={onIrcRailDoubleClick}
            />
          ) : null}
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
              const pill = (
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
              // #782: bubble-theme aware — IRC keeps the pill's disclosure but
              // seats it in the gutter grid so the vertical line stays whole.
              if (themeUsesIrcGutter(bubbleTheme)) {
                return (
                  <div key={message.key} className="os-irc-notice-row" data-testid="irc-notice-line">
                    <span
                      role="separator"
                      aria-orientation="vertical"
                      aria-label="Resize IRC name column"
                      className="os-irc-gutter-divider"
                      data-testid="irc-gutter-divider"
                    />
                    {pill}
                  </div>
                )
              }
              return pill
            }
            if (isStatusRole(message.role)) {
              const statusMs = parseCreatedAtMs(message.ts)
              if (message.rateLimit) {
                // #782: rate-limit lines are bubble-theme aware — IRC renders
                // them as gutter lines; the settings click survives.
                const noticeSpec = getBubbleTheme(bubbleTheme).renderNoticeRow(
                  'System',
                  formatRateLimitNotice(message.rateLimit),
                  message.ts,
                  message.key,
                )
                if (noticeSpec.kind === 'gutter-line') {
                  const target =
                    message.rateLimit.settings ||
                    settingsTargetForProvider(message.rateLimit.provider)
                  return (
                    <IrcNoticeLine
                      key={message.key}
                      speaker={noticeSpec.speaker}
                      text={noticeSpec.text}
                      ts={noticeSpec.ts}
                      rowKey={noticeSpec.key}
                      onClick={() =>
                        openSettingsSheet({
                          section: target.section,
                          providerId: target.provider_id,
                          focusRateLimits: true,
                        })
                      }
                    />
                  )
                }
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
              // #782: notice rows follow the bubble theme — IRC renders them
              // as `<System> message` gutter lines so the transcript column
              // stays whole; every other theme keeps the legacy status line.
              const noticeSpec = getBubbleTheme(bubbleTheme).renderNoticeRow(
                'System',
                message.text,
                message.ts,
                message.key,
              )
              if (noticeSpec.kind === 'gutter-line') {
                return (
                  <IrcNoticeLine
                    key={message.key}
                    speaker={noticeSpec.speaker}
                    text={noticeSpec.text}
                    ts={noticeSpec.ts}
                    rowKey={noticeSpec.key}
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
            // #505 / REQ-907: IRC overlays the action row onto the bubble line.
            // Overlay is hover-scoped in CSS; below md the row stays in flow so
            // touch devices never permanently cover message text.
            const rowOverlay =
              getBubbleTheme(bubbleTheme).actionRowPlacement === 'overlay' && !message.streaming
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
            const rowPersona =
              message.role === 'assistant'
                ? personaForAgentMessage(message, selectedAgent?.personas)
                : null
            const parsedArtifacts = extractThinkingBlock(message.text)
            const hasThinking = Boolean(parsedArtifacts.thinking)
            const thinkingOpen = expandedThinkingKeys.has(message.key)
            const isHerdrMessage = isHerdrSeat || Boolean(message.rawResponse)
            return (
              <div
                key={message.key}
                data-message-key={message.key}
                data-persona={rowPersona ?? undefined}
                className="group/osrow os-chat-row"
                onContextMenu={(e) => {
                  if (message.role === 'system') return
                  handleBubbleContextMenu(e, message)
                }}
                onMouseUp={(e) => {
                  // #846: remember what was highlighted in THIS row before any
                  // right-click can collapse the selection.
                  if (message.role === 'system') return
                  cacheRowSelection(message.key, e.currentTarget)
                }}
                onMouseDown={(e) => {
                  if (message.role === 'system') return
                  if (e.button === 2) {
                    // #846: stop the right-click from wiping the selection
                    // before the context menu can read it.
                    e.preventDefault()
                  }
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
                  thinkingOpen={thinkingOpen}
                  onToggleThinking={() => toggleThinking(message.key)}
                  isHerdr={isHerdrMessage}
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
                    overlay={rowOverlay}
                    canEdit={canEditThis}
                    onStartEdit={() => setEditingKey(message.key)}
                    canCompress={canCompressThis}
                    contextStrategy={contextStrategy}
                    hasThinking={hasThinking}
                    thinkingOpen={thinkingOpen}
                    onToggleThinking={() => toggleThinking(message.key)}
                    isHerdr={isHerdrMessage}
                    rawResponse={message.rawResponse || (isHerdrMessage ? message.text : undefined)}
                    onShowRawResponse={() => setRawResponseModalText(message.rawResponse || message.text)}
                    onCompressToHere={() => {
                      handleContextToHere(message)
                    }}
                    onReply={() => {
                      // #846: row-action Reply honors a scoped selection in
                      // this bubble too — not just the context menu.
                      const row = document.querySelector<HTMLDivElement>(
                        `[data-message-key="${CSS.escape(message.key)}"]`,
                      )
                      const quoted =
                        resolveReplyQuote({
                          targetElement: row,
                          cached: activeSelectionRef.current,
                          messageKey: message.key,
                        }) || message.text
                      setReplyTarget({
                        key: message.key,
                        role: message.role,
                        speaker:
                          message.role === 'user' ? 'You' : selectedAgentName,
                        text: quoted,
                      })
                      composerRef.current?.focus()
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
            configTarget={cliRecoveryConfigTarget}
            onConfigure={(target) => openSettingsSheet({ section: target.section })}
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
          <ComposerPluginsBadge />
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
                onOpenDetail={() => setTokenDiagOpen(true)}
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
              <div className="os-composer-row">
              <div
                className={`os-composer ${
                  replyTarget || pendingAttachments.length > 0 || queued.rows.length > 0
                    ? 'flex-col items-stretch !rounded-2xl !p-2'
                    : ''
                } ${replyTarget ? 'os-composer--reply' : ''} ${
                  queued.rows.length > 0 ? 'os-composer--queued' : ''
                } ${composerDragOver ? 'os-composer--drag-over' : ''}`}
                onDragEnter={handleComposerDragEnter}
                onDragOver={handleComposerDragOver}
                onDragLeave={handleComposerDragLeave}
                onDrop={handleComposerDrop}
              >
                {/* #925: the queued pane mounts INSIDE .os-composer at the very
                    top, extending directly out of the message input box above
                    the reply and attachment preview strips. */}
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
                      gone?.abortController?.abort()
                      revokePreviewUrl(gone?.previewUrl)
                      return prev.filter((row) => row.localId !== localId)
                    })
                  }}
                />
                <div className={`flex items-center gap-1.5 min-h-0 ${replyTarget || pendingAttachments.length > 0 || queued.rows.length > 0 ? 'w-full' : 'flex-1'}`}>
                  <div className="relative" ref={plusRef}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      data-testid="composer-file-input"
                      aria-hidden="true"
                      tabIndex={-1}
                      onChange={(event) => {
                        enqueueComposerFiles(filesFromList(event.target.files))
                        event.target.value = ''
                      }}
                    />
                    <button
                      type="button"
                      className="os-composer__icon"
                      aria-label="Add"
                      aria-haspopup="menu"
                      aria-expanded={plusOpen}
                      data-testid="composer-plus-button"
                      onClick={() => setPlusOpen((value) => !value)}
                    >
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </button>
                    {plusOpen && !pluginsPanelOpen && (
                      <ul
                        role="menu"
                        aria-label="Chat actions"
                        className="os-plus-menu"
                      >
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            aria-disabled={!composerMenu.addFiles.enabled}
                            className={`os-plus-menu__item ${
                              !composerMenu.addFiles.enabled ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              composerMenu.addFiles.enabled
                                ? 'Add files to this chat'
                                : composerMenu.addFiles.reason
                            }
                            onClick={() => {
                              if (!composerMenu.addFiles.enabled) {
                                addToast({
                                  type: 'info',
                                  title: 'Add files',
                                  message: `${composerMenu.addFiles.reason}. Switch to an API agent to attach.`,
                                })
                                setPlusOpen(false)
                                return
                              }
                              setPlusOpen(false)
                              fileInputRef.current?.click()
                            }}
                          >
                            <Paperclip className="h-4 w-4" aria-hidden="true" />
                            Add files
                          </button>
                        </li>
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            // #550: Compact summarises server-side history, so a
                            // CLI/remote seat has nothing for it to act on. Kept
                            // visible-but-disabled with the reason (the same read
                            // `Add files` uses one item above, and #511's
                            // precedent) rather than vanishing silently.
                            // #636: CLI seats now light up when a default API is
                            // configured or the provider declares cli_compact; a
                            // greyed CLI item's hover says the API is missing.
                            data-testid="composer-compact-button"
                            aria-disabled={!composerMenu.compact.enabled}
                            className={`os-plus-menu__item ${
                              !composerMenu.compact.enabled ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              composerMenu.compact.enabled
                                ? 'Summarise this conversation and reclaim context'
                                : composerMenu.compact.reason
                            }
                            onClick={() => {
                              if (!composerMenu.compact.enabled) {
                                addToast({
                                  type: 'info',
                                  title: 'Compact',
                                  message: composerMenu.compact.reason,
                                })
                                setPlusOpen(false)
                                return
                              }
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
                            // #516: Plugins ride the swarm-owned gate (#511) —
                            // visible-but-disabled with the reason on CLI/remote
                            // seats, opening the per-agent panel on swarm seats.
                            data-testid="composer-plugins-button"
                            aria-disabled={!composerMenu.plugins.enabled}
                            aria-haspopup="menu"
                            className={`os-plus-menu__item ${
                              !composerMenu.plugins.enabled ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              composerMenu.plugins.enabled
                                ? 'Toggle this agent’s plugins'
                                : composerMenu.plugins.reason
                            }
                            onClick={() => {
                              if (!composerMenu.plugins.enabled) {
                                addToast({
                                  type: 'info',
                                  title: 'Plugins',
                                  message: composerMenu.plugins.reason,
                                })
                                setPlusOpen(false)
                                return
                              }
                              setPluginsPanelOpen(true)
                            }}
                          >
                            <Plug className="h-4 w-4" aria-hidden="true" />
                            Plugins
                          </button>
                        </li>
                      </ul>
                    )}
                    {plusOpen && pluginsPanelOpen && <ComposerPluginsPanel onClose={() => setPlusOpen(false)} />}
                  </div>
                  {/* #858/#860: API seats get the enhanced composer — inline
                      ghost-text autocomplete + sparkle enhance. Other kinds
                      keep the plain textarea (autocomplete is API-model
                      backed; CLI/remote input would need per-provider wiring). */}
                  {isApiAgent ? (
                    <ChatMessageInput
                      textareaRef={composerRef}
                      value={input}
                      onApplyText={setInput}
                      agentId={selectedBlueprint || undefined}
                      conversationId={conversationId || undefined}
                      textareaProps={{
                        rows: 1,
                        className: 'os-composer__input',
                        placeholder: composerPlaceholder,
                        value: input,
                        onChange: handleInputChange,
                        onPaste: handleComposerPaste,
                        onKeyDown: handleComposerKeyDown,
                        'aria-label': 'Chat message',
                        'aria-haspopup': 'listbox',
                        'aria-expanded': isSlashOpen,
                        'aria-controls': isSlashOpen ? 'composer-slash-menu' : undefined,
                      }}
                    />
                  ) : (
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
                  )}
                  {/* #732: ONE permanently mounted slot — the kbd used to
                      mount/unmount with the draft, re-flowing the pill on the
                      first and last keystroke. The glyph swaps in place; the
                      node (and its reserved width) never changes. */}
                  <span className="os-composer__hint-slot" data-testid="composer-hint-slot">
                    {sendNowHint ? (
                      /* #631: the ↵ reveal exists ONLY to announce the interrupt-
                         send action while a queued send waits. No queue → no hint. */
                      <kbd
                        className="os-composer__hint kbd kbd-xs"
                        data-testid="composer-send-hint"
                        title="Send Now! ↵"
                      >
                        ↵
                      </kbd>
                    ) : input ? (
                      <kbd
                        className="os-composer__hint kbd kbd-xs"
                        data-testid="composer-clear-hint"
                        title="Esc to clear"
                      >
                        Esc
                      </kbd>
                    ) : (
                      <kbd
                        className="os-composer__hint kbd kbd-xs"
                        data-testid="composer-hint-placeholder"
                        title=""
                        aria-hidden="true"
                      >
                        ↵
                      </kbd>
                    )}
                  </span>
                  {renderRoutingPicker()}
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
                </div>
                </div>{/* /os-composer */}
                {/* #632: the primary action lives OUTSIDE the input box, to its
                    right. Idle: send (↑) when there is a draft. Busy: square
                    stop (□) — and the send stays beside it when a draft is
                    typed, because clicking Send mid-flight is exactly how a
                    send gets QUEUED (#603); removing it would kill queueing.
                    The mic stays inside the input regardless. */}
                {composerBusy ? (
                  <button
                    type="button"
                    className="os-composer__send os-composer__send--stop"
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
              </div>{/* /os-composer-row */}
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
                  text: contextMenu.selectedText || contextMenu.message.text,
                })
                setContextMenu(null)
                composerRef.current?.focus()
              }}
            >
              <Reply className="h-4 w-4 opacity-70" aria-hidden="true" />
              {/* #846: label names the target — a partial selection is a quote. */}
              {contextMenu.selectedText ? 'Reply to quote' : 'Reply'}
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
              data-testid="context-menu-copy"
              onClick={() => {
                const textToCopy = contextMenu.selectedText || contextMenu.message.text
                setContextMenu(null)
                void copyTextToClipboard(textToCopy).then((result) => {
                  if (result === 'empty') {
                    toastError(COPY_EMPTY_TITLE, COPY_EMPTY_MESSAGE)
                  } else if (result === 'failed') {
                    toastError(COPY_FAILED_TITLE, COPY_FAILED_MESSAGE)
                  }
                })
              }}
            >
              <Copy className="h-4 w-4 opacity-70" aria-hidden="true" />
              {contextMenu.selectedText ? 'Copy selection' : 'Copy'}
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
            {/* #724: the bubble-theme picker moved to the rail agent
                right-click menu — presentation is an agent-level choice, not
                a message-level action. */}
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

      <RawResponseModal
        isOpen={rawResponseModalText !== null}
        onClose={() => setRawResponseModalText(null)}
        text={rawResponseModalText ?? ''}
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
        agentId={headerFaceAgentId}
        agentName={selectedAgentName || 'Agent'}
        contexts={generationContexts}
        activeContextId={conversationId}
        onSwitchContext={() => {
          /* Single-context today; multi-context switching lands with session history UI. */
        }}
        toolCalls={seatToolCalls}
      />

      {herdrPickerOpen ? (
        /* #543: which herdr agent am I talking to? Lists CONFIGURED agents
           (GET /v1/herdr-agents/); discovery and add/remove stay in Settings
           per the ticket's constraint. Empty/error states say why — no silent
           fallback to a default agent (#494's rule). */
        <div
          role="dialog"
          aria-label="Choose herdr agent"
          data-testid="herdr-agent-popup"
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40"
          onClick={() => setHerdrPickerOpen(false)}
        >
          <div
            className={`w-[min(24rem,90vw)] space-y-2 rounded-box p-4 ${OVERLAY_CHROME_CLASSES}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <h5 className="text-sm font-semibold">Choose herdr agent</h5>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                aria-label="Close herdr agent picker"
                onClick={() => setHerdrPickerOpen(false)}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            {herdrAgentsQuery.isPending ? (
              <p className="text-sm text-base-content/60" data-testid="herdr-picker-loading">
                Loading herdr agents…
              </p>
            ) : herdrAgentsQuery.isError ? (
              <div className="space-y-2" data-testid="herdr-picker-error">
                <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
                  <span className="text-sm">
                    Herdr is unreachable — check that it is running, or add it
                    under Settings → Remotes.
                  </span>
                </Alert>
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={() => openSettingsSheet({ section: 'remotes' })}
                >
                  Open Remotes settings
                </button>
              </div>
            ) : (herdrAgentsQuery.data?.data ?? []).length === 0 ? (
              <div className="space-y-2" data-testid="herdr-picker-empty">
                <Alert type="info" icon={<Server className="h-5 w-5" />}>
                  <span className="text-sm">No herdr agents configured yet.</span>
                </Alert>
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={() => openSettingsSheet({ section: 'remotes' })}
                >
                  Add one in Settings
                </button>
              </div>
            ) : (
              <ul className="space-y-1" aria-label="Herdr agents">
                {(herdrAgentsQuery.data?.data ?? []).map((agent) => (
                  <li key={`${agent.remote || 'local'}:${agent.name}`}>
                    <button
                      type="button"
                      className={`btn btn-sm w-full justify-between ${
                        sessionFromUrl === agent.name ? 'btn-primary' : ''
                      }`}
                      data-testid="herdr-agent-option"
                      data-herdr-agent={agent.name}
                      data-herdr-remote={agent.remote || 'localhost'}
                      title={
                        sessionFromUrl === agent.name
                          ? 'Currently selected'
                          : `Talk to ${agent.name}`
                      }
                      onClick={() => {
                        setSearchParams(
                          (prev) => {
                            const next = new URLSearchParams(prev)
                            next.set('remote', 'herdr')
                            next.set('session', agent.name)
                            return next
                          },
                          { replace: true },
                        )
                        setHerdrPickerOpen(false)
                      }}
                    >
                      <span>{agent.name}</span>
                      <span className="text-xs opacity-60">
                        {agent.remote ? `remote: ${agent.remote}` : 'localhost'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}

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
