import {
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import {
  chatHeaderSuppressed,
  setChatHeaderSuppressed,
  shouldShowChatHeader,
  subscribeChatHeaderSurface,
  useChatHeaderSuppressed,
} from '../lib/chatHeaderSurface'
import { ChatBottomDock } from '../features/chat/ChatBottomDock'
import { usePerAgentDraft } from '../features/chat/usePerAgentDraft'
import { ChatOverlays } from '../features/chat/ChatOverlays'
import { ChatTranscriptShell } from '../features/chat/ChatTranscriptShell'
import { renderRoutingPickerImpl } from '../features/chat/renderRoutingPicker'
import { ChatHeader } from '../features/chat/ChatHeader'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Copy, FoldVertical, Folder, Layers, Mic, PanelLeft, Paperclip, Pencil, Plug, Plus, Reply, Settings, Sparkles, Square } from 'lucide-react'
import AgentAvatar from '../components/AgentAvatar'
import GroupAvatar from '../components/GroupAvatar'
import ChatMessageInput from '../components/ChatMessageInput'
import {
  ConfirmModal,
  useToast,
} from '../components/DaisyUI'
import ThemeToggle from '../components/ThemeToggle'
import {
  OPEN_SETTINGS_EVENT,
  openSettingsSheet,
  settingsDetailFromQuery,
} from '../components/settings/kernel'
import RateLimitStatusLine from '../components/RateLimitStatusLine'
import {
  REMOTE_HEALTH_CHANGED_EVENT,
  isRemoteOffline,
  startRemoteHealthPolling,
  stopRemoteHealthPolling,
} from '../lib/remoteHealth' // #1196



import {
  getScopedSelectionText,
  resolveReplyQuote,
  type CachedBubbleSelection,
} from '../lib/bubbleSelection'
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
import { prefetchAgentMcpTools } from '../lib/mcpTurnParams'
import { openTeamEditor } from '../components/teamEditorKernel'
import PersonaRoster from '../components/PersonaRoster'
import { declaredRosterForTeam, facesFromDeclaredRoster } from '../lib/declaredRoster'
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
  parseContextStrategy,
  parseCullTriggerPct,
  type ContextMeta,
  type ContextStrategy,
} from '../lib/contextCull'
import { persistableMessages, putAgentChatSession } from '../lib/agentChatSessions'
import { navbarSeatCapabilities } from '../lib/seatCapabilities'
import { useNavbarPickerPrefs } from '../features/chat/useNavbarPickerPrefs'

import { useRailChrome } from '../components/RailChrome'
import { ComputerControlStub } from '../components/ComputerControlStub'
import { NavbarRoutingPicker } from '../components/NavbarRoutingPicker'

import {
  AGENT_BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEME_CHANGED_EVENT,
  BUBBLE_THEME_STORAGE_KEY,
  agentBubbleThemeOverrides,
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
import MessageRowActions from '../components/MessageRowActions'

import CliSessionSwitcher from '../components/CliSessionSwitcher'
import ApiSessionSwitcher from '../components/ApiSessionSwitcher'
import RemoteSessionSwitcher from '../components/RemoteSessionSwitcher'
import {
  fetchRemoteThreadSessions,
  fetchTrueForgeNavbarCatalog,
  isTrueForgeKind,
  mostRecentRemoteSession,
  remoteAgentsFromOperate,
  remoteListsSessions,
} from '../lib/remoteSessions'
import type { MemberSession } from '../lib/sessionPicker'
import type { CliRailAgent } from '../lib/api/types'
import type { RemoteEntry } from '../lib/remotesCatalog'
import { emptyArray } from '../lib/stableEmpty'

// #856 slice 2: summary card tree moved verbatim to features/chat/SummaryBlock.tsx.

import { ComposerSlashPopup } from '../components/ComposerSlashPopup'
import ComposerAttachChips from '../components/ComposerAttachChips'
import {
  filesFromList,
  readyAttachmentIds,
} from '../lib/chatAttachments'
import { composeOutboundDisplayText } from '../lib/voiceNotes'
import { composerMenuCapabilities } from '../lib/composerMenu'
import { applyRemoteRoutingChange } from '../lib/remoteRouting'
import { ComposerPluginsPanel } from '../components/ComposerPluginsPanel'
import {
  getRecentSlashIds,
} from '../lib/slashMenu'
import { fetchCompanyRoute } from '../lib/companyRoute'
import {
  EMPTY_SPEECH,
  type SkillRecord,
  fetchBlueprints,
  fetchCliAgents,
  fetchCliModels,
  fetchDesignedAgents,
  fetchHerdrAgents,
  fetchLlmProfiles,
  fetchRemotes,
  fetchSpeechSettings,
  fetchSupportContext,
  isThrottleError,
  operateRemote,
} from '../lib/api'
import {
  resolveTtsPath,
  speakCustom,
  speakSystem,
  type SpeechPath,
} from '../lib/speechRuntime'
import { SPEECH_QUERY_KEY, describeSpeechPath, parseSpeechSettings } from '../lib/speechSettings'
import {
  AGENT_CONVERSATION_EVENT,
  agentIdFromBlueprint,
  conversationIdForAgent,
  conversationIdForTask,
  DEFAULT_AGENT_ID,
  fetchAgentThread,
  peekConversationIdForAgent,
  setConversationIdForAgent,
  toggleSummaryInContext,
  type ConversationSummary,
} from '../lib/agentChat'
import { canEditAgentMessages, classifyAgentKind, isSwarmOwnedAgent, type AgentKind } from '../lib/agentKind'
import {
  composerInsetCustomProperty,
} from '../lib/composerInset'
import {
  currentShowProviderResolved,
  COMPOSER_SHOW_PROVIDER_TIERS_EVENT,
  COMPOSER_REWRITE_ENABLED_EVENT,
  loadRewriteEnabled,
} from '../lib/composerAffordances'
import { subscribeViewportTier } from '../lib/responsivePrefs'
import {
  COMPOSER_SHOW_PROVIDER_SET_EVENT,
  COMPOSER_SHOW_PROVIDER_STORAGE_KEY,
} from '../lib/composerShowProvider'
import {
  buildDisplayItems,
  contextTextsForMeter,
  rawOffsetForMessage,
  summariesById,
} from '../lib/chatCompact'
import {
  buildCancelFanOutLegFrame,
  buildQuestionAnswerFrame,
  buildToolDecisionFrame,
} from '../lib/chatWs'
import type { FanOutLeg } from '../lib/runningCards'
import { ContextUsageBadge } from '../components/ContextUsageBadge'
import { AuxActivityIndicator } from '../components/AuxActivityIndicator'
import {
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
import { activeTurnFor, isAgentTurnActive, type TurnSnapshot } from '../lib/agentTurns'

import type { DecisionQuestion } from '../lib/decisionQuestion'

import { SuggestionChips } from '../components/SuggestionChips'
import ConsumerPills from '../components/ConsumerPills'
import ComposerPluginsBadge from '../components/ComposerPluginsBadge'

import {
  openerChatSearch,
  type PrOpenedOpener,
} from '../lib/prOpened'
import SubagentFanOutBlock from '../components/SubagentFanOutBlock'

import { isHerdrAgent } from '../lib/railHotkeys'
import {
  rememberAlwaysAllow,
  upsertToolCall,
  type ToolCallState,
} from '../lib/safety'
import {
  notifyCliRunState,
} from '../lib/cliRunState'
import { notifyApprovalWait } from '../lib/agentAttention'
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
import { defaultSessionForRemote, defaultSessionForTeam } from '../lib/sessionPicker'
import {
  OMB_NO_AGENTS_WARNING,
  ombBotsFromOperate,
  ombSendTarget,
} from '../lib/ombBots'
import { isOpenMousBotKind } from '../lib/remoteKinds'
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId } from '../lib/remotesCatalog'
import { composerOptionsForProvider } from '../lib/composerSources'
import {
  ADD_REMOTE_VALUE,
  configuredRemotes,
  isHerdrKind,
  remoteKinds,
  remoteOptionLabel,
  remoteSelectPlaceholder,
} from '../lib/remotes'
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
  estimateTokensInContext,
} from '../lib/chatMeter'
// #1168: pending-send watchdog (fail lost sends fast, offer resend).
import {
  PENDING_SEND_GRACE_MS,
  failStalePendingSends,
  restorePendingSend,
} from '../lib/pendingSends'
// #1167: typing anywhere in chat focuses the composer.
import { makeTypingFocusHandler } from '../lib/typingFocus'
import { useChatWebSocket } from '../features/chat/useChatWebSocket'
import { useChatWsDispatcher } from '../features/chat/useChatWsDispatcher'
import { useChatSend } from '../features/chat/useChatSend'
import { useComposerCommands } from '../features/chat/useComposerCommands'
import { useChatCompact } from '../features/chat/useChatCompact'
import { useChatTurnOps } from '../features/chat/useChatTurnOps'
import { useComposerControls } from '../features/chat/useComposerControls'
import { useTranscriptLayout } from '../features/chat/useTranscriptLayout'
import { useChatDerived } from '../features/chat/useChatDerived'
import { useSlashLifecycle } from '../features/chat/useSlashLifecycle'
import { useChatRouting } from '../features/chat/useChatRouting'
import { useComposerAttachments } from '../features/chat/useComposerAttachments'
import { ChatMessageList } from '../features/chat/ChatMessageList'
import { remoteThreadId } from '../features/chat/threadLoadState'
import { ChatMessageActions } from '../experimental/ChatMessageActions'
import { ChatMessageBubble } from '../components/ChatMessageBubble'
import { ChatNewRule } from '../components/ChatLogMarkers'
import CliSessionRecoveryBanner from '../components/CliSessionRecoveryBanner'
import { DemoTourBanner } from '../components/DemoTourBanner'
import { IrcNoticeLine } from '../components/IrcNoticeLine'
import { PrOpenedCard } from '../components/PrOpenedCard'
import { QuestionCard } from '../components/QuestionCard'
import { SummaryBlock } from '../features/chat/SummaryBlock'
// #1694: the hop boundary marker, injected into ChatMessageList the same way
// its sibling cards are (the #856 extraction keeps card components as props).
import { CarriedSummaryBlock } from '../components/CarriedSummaryBlock'
import { SystemPreloadPill } from '../components/SystemPreloadPill'
import { TeammateTaskCard } from '../components/TeammateTaskCard'
import { ToolCallPopup } from '../components/ToolCallPopup'
import { extractThinkingBlock } from '../lib/messageArtifacts'
import { formatRateLimitNotice } from '../lib/statusLineText'
import { personaForAgentMessage } from '../lib/personaAvatars'
import { settingsTargetForProvider } from '../lib/providerRateLimits'
import { formatGapLabel, parseCreatedAtMs } from '../lib/chatTime'
import { isExperimentalEnabled } from '../experimental/flags'

import { RoleAgentTip } from '../components/RoleAgentTip'
import { DefaultLlmTip } from '../components/DefaultLlmTip'
import { HostCliTip } from '../components/HostCliTip'
import { VanillaSetupTip } from '../components/VanillaSetupTip'

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
} from '../lib/defaultLlmTip'
import {
  hydrateHostCliTipDismissed,
  hostCliDetectedName,
  isHostCliTipDismissed,
  persistHostCliTipDismissed,
  shouldShowHostCliTip,
} from '../lib/hostCliTip'
import {
  CONFIGURE_API_TIP_ID,
  firstVanillaTip,
  hydrateVanillaTipDismissals,
  isVanillaTipDismissedLocal,
  persistVanillaTipDismissed,
} from '../lib/vanillaTips'
import { pickerSeatRows } from '../lib/blueprintSeats'
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
import { AGENT_PROFILE_CHANGED_EVENT, fetchAgentProfile } from '../lib/agentProfile'
import { cliRemoteSessionChoices, isRemoteCapableCli } from '../lib/cliRemote'
import { navbarWorkspaceSubtitleParts } from '../lib/agentWorkspace'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import {
  defaultBlueprintId,
  isSupportAgent,
  SUPPORT_AGENT_ID,
} from '../lib/supportAgent'
import { isStatusRole } from '../lib/chatStatus'

import {
  countableChatCount,
  effectiveUnreadWatermark,
  firstUnreadMessageKey,
} from '../lib/chatLog'
import { loadLastRead } from '../lib/chatLastRead'
import {
  isAgentUnread,
  loadUnreadAgentIds,
} from '../lib/unreadAgents'
// #1729: clearing the Herdr status indicator when its chat is opened.
import { useClearHerdrSeatOnOpen } from '../components/HerdrStatusDot'
import {
  isSupportJourneyConsumer,
} from '../lib/supportJourney'
import {
  missingSessionNotice,
  restoreKindForAgent,
  restoredSessionNotice,
  switchedSessionNotice,
} from '../lib/sessionRestore'
import {
  CLI_SESSION_SWITCHED_EVENT,
} from '../lib/cliSessions'
import {
  CLI_SESSION_HOPPED_EVENT,
} from '../lib/cliSessionHop'
// #636: CLI-seat compact orchestration (summary + fresh session carrying it).
import {
  generationIsInFlight,
  queuedPaneMaxHeightPx,
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
  designedCliSeat,
  MANAGE_CLI_VALUE,
} from '../lib/cliAgentContext'
import { isHiddenRoutingLabel, type RoutingSeatKind } from '../lib/routingPath'
import {
  activeHeaderSeatKey,
  canonicalSeatTargetId,
  seatParamsForPick,
  headerSeatKey,
  seatPickKindForTarget,
  providerScopeForAgent,
  providerScopeKey,
  fetchSeatCapabilities,
} from '../lib/seatRouting'
// #1692: one avatar-URL precedence for every seat surface (rail, header, pickers).
import { seatAvatarSrc } from '../lib/seatAvatar'
import { filterCliModels } from '../lib/composerPicker'

// #856 slice 1: module-scope message/session types and helpers moved verbatim to
// features/chat/chatMessages.ts; re-imported here so the component body and the
// '../ChatPage' import surface are unchanged.
import {
  chatLoginHref,
  hydrateThreadRows,
  type ChatMessage,
} from '../features/chat/chatMessages'

const SessionPicker = lazy(() => import('../components/SessionPicker'))
const GenerationsPanel = lazy(() => import('../components/GenerationsPanel'))
const TokenDiagnosticsModal = lazy(() =>
  import('../components/TokenDiagnosticsModal').then((mod) => ({ default: mod.TokenDiagnosticsModal })),
)
const SkillPopup = lazy(() =>
  import('../components/SkillPopup').then((mod) => ({ default: mod.SkillPopup })),
)
const RawResponseModal = lazy(() =>
  import('../components/RawResponseModal').then((mod) => ({ default: mod.RawResponseModal })),
)

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
export { chatLoginHref, chatLoginNext } from '../features/chat/chatMessages'

/** EXPERIMENTAL flags are read once per module load; see experimental/flags.ts. */
const SHOW_MESSAGE_ACTIONS = isExperimentalEnabled('chat_message_actions')

type ConnectionStatus = ChatConnectionStatus

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

const ChatPage = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { pathname } = useLocation()
  // #1445: header controls are chat-only. Settings suppresses them in the
  // same render that opens the sheet. The nodes stay mounted (hidden) so the
  // gear can take focus back on close. Non-chat routes never qualify.
  const headerSuppressed = useSyncExternalStore(
    subscribeChatHeaderSurface,
    chatHeaderSuppressed,
    () => false,
  )
  const contextSuppressed = useChatHeaderSuppressed()
  const { addToast, dismissByKind, error: toastError } = useToast()
  const { narrow, railOpen, openRail } = useRailChrome()
  const teamFromUrl = searchParams.get('team') ?? ''
  const remoteFromUrl = searchParams.get('remote') ?? ''
  const sessionFromUrl = searchParams.get('session') ?? ''
  // #288: an explicit "All members" pick rides `?members=all` so a reload keeps it
  // instead of re-defaulting to the team's nominated seat.
  const allMembersFromUrl = isAllMembersChoice(searchParams.get(ALL_MEMBERS_PARAM))
  const settingsQuery = searchParams.get('settings')
  const cliFromUrl = (searchParams.get('cli') ?? '').trim()
  const explicitBlueprint = (searchParams.get('blueprint') ?? '').trim()
  // URL seat only. The Support default is not a seat until the effect below
  // writes `?blueprint=support`. `api:` (no id) stays hidden.
  const headerGateSeat = activeHeaderSeatKey({
    teamId: teamFromUrl,
    remoteId: remoteFromUrl,
    cliId: cliFromUrl,
    blueprintId: teamFromUrl || remoteFromUrl ? '' : explicitBlueprint,
  })
  // #1445: `/chat?settings=true` must hide AnythingLLM/team chrome on the
  // first paint. The sheet itself opens one macrotask later (#674).
  const settingsDeepLink = settingsDetailFromQuery(settingsQuery) != null
  const showChatHeader = shouldShowChatHeader(
    pathname,
    headerSuppressed || contextSuppressed || settingsDeepLink,
    headerGateSeat,
  )
  // #1445: while suppressed the header is dropped from the DOM entirely — a
  // `hidden` wrapper still matches queryBy* and leaks the stale identity.
  // Exception: when the header currently holds focus (the gear that opened
  // the sheet), it stays mounted-but-hidden so Modal can restore focus to
  // that exact node on close. Checked during the suppress render, while the
  // previous commit (header still present) is in the DOM.
  const headerWrapRef = useRef<HTMLDivElement | null>(null)
  const headerHoldsFocus =
    !showChatHeader &&
    headerWrapRef.current != null &&
    headerWrapRef.current.contains(document.activeElement)
  const renderChatHeader = showChatHeader || headerHoldsFocus
  const settingsQueryOpenedRef = useRef(false)
  useEffect(() => {
    if (settingsQueryOpenedRef.current) return
    const detail = settingsDetailFromQuery(settingsQuery)
    if (detail == null) return
    settingsQueryOpenedRef.current = true
    // #674: this effect runs on the CHILD before App (the sheet owner and
    // OPEN_SETTINGS_EVENT listener) has subscribed on a cold load, so an
    // immediate dispatch is dropped. Defer to the next macrotask so the
    // parent's listener exists first. Suppress before that open so the
    // header cannot return in the render that strips `?settings=`.
    const timer = window.setTimeout(() => {
      setChatHeaderSuppressed(true)
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
  useEffect(() => {
    if (!activeChatAgentId) return
    void prefetchAgentMcpTools(activeChatAgentId)
  }, [activeChatAgentId])
  const [newChatPerTask, setNewChatPerTask] = useState(() =>
    teamFromUrl || remoteFromUrl ? false : loadLocalNewChatPerTask(defaultBlueprintId(searchParams.get('blueprint'))),
  )
  const [useSuggestions, setUseSuggestions] = useState(() =>
    teamFromUrl ? false : loadLocalUseSuggestions(defaultBlueprintId(searchParams.get('blueprint'))),
  )
  /** #878: show/hide the provider routing picker in the message input bar.
   * #1219: now resolved per viewport tier (mobile ships hidden); the legacy
   * #878 boolean migrates into the tiered store inside the prefs module. */
  const [composerShowProvider, setComposerShowProvider] = useState<boolean>(
    () => currentShowProviderResolved(),
  )
  const [composerRewriteEnabled, setComposerRewriteEnabled] = useState<boolean>(
    () => loadRewriteEnabled(),
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
  // ADR-017 PR-2: SPA-side registry of the server's per-turn bookends
  // (turn_started/turn_finished), so the row stop cancels the exact turn.
  const [agentTurns, setAgentTurns] = useState<TurnSnapshot>({})
  // #1374: legs of the roster fan-out currently in this thread.
  const [fanOutLegs, setFanOutLegs] = useState<FanOutLeg[]>([])
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
  const [input, setInput] = usePerAgentDraft(activeChatAgentId)
  const [sttListening, setSttListening] = useState(false)
  const [sttPathUsed, setSttPathUsed] = useState<SpeechPath | null>(null)
  const sttStopRef = useRef<(() => void) | null>(null)
  const spokenReplyKeysRef = useRef<Set<string>>(new Set())
  const autoSpeakHydratedRef = useRef(false)
  const [replyTarget, setReplyTarget] = useState<ReplyTarget | null>(null)
  const [contextMenu, setContextMenu] = useState<MessageContextMenuState | null>(null)
  // #1121: the transcript renders the *effective* theme — the agent's own
  // override (rail menu → theme, os.bubbleThemeByAgent) wins over the global
  // default. Both layers re-resolve on the change event / storage so a rail
  // or Settings write restyles the mounted transcript immediately; the tick
  // forces recomputation even when the global value is unchanged.
  const [globalBubbleTheme, setGlobalBubbleTheme] = useState<BubbleTheme>(() => loadBubbleTheme())
  const [bubbleThemeTick, setBubbleThemeTick] = useState(0)
  const bubbleTheme = useMemo<BubbleTheme>(
    () =>
      (activeChatAgentId && agentBubbleThemeOverrides()[activeChatAgentId]) ||
      globalBubbleTheme,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeChatAgentId, globalBubbleTheme, bubbleThemeTick],
  )
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
    // #506/#1121: Settings and the rail agent menu are both theme writers —
    // re-resolve the effective theme (global + per-agent override) instead of
    // trusting the event detail, so either surface keeps a mounted
    // transcript in sync.
    const onThemeChanged = () => {
      setGlobalBubbleTheme(loadBubbleTheme())
      setBubbleThemeTick((t) => t + 1)
    }
    const onStorage = (event: StorageEvent) => {
      if (
        event.key === BUBBLE_THEME_STORAGE_KEY ||
        event.key === AGENT_BUBBLE_THEME_STORAGE_KEY ||
        event.key === null
      ) {
        setGlobalBubbleTheme(loadBubbleTheme())
        setBubbleThemeTick((t) => t + 1)
      }
      if (
        event.key === COMPOSER_SHOW_PROVIDER_STORAGE_KEY ||
        event.key === null
      ) {
        setComposerShowProvider(currentShowProviderResolved())
      }
    }
    const onComposerShowProviderChanged = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail
      setComposerShowProvider(typeof detail === 'boolean' ? detail : currentShowProviderResolved())
    }
    // #1220: the rewrite opt-in reacts live so the + menu updates without a
    // reload (and an opt-OUT removes the affordance immediately).
    const onRewriteEnabledChanged = () => setComposerRewriteEnabled(loadRewriteEnabled())
    // #1219: the tiered provider-dropdown pref + live viewport-tier changes
    // both re-resolve visibility without a remount.
    const onShowProviderTiersChanged = () => setComposerShowProvider(currentShowProviderResolved())
    const unsubscribeTier = subscribeViewportTier(() =>
      setComposerShowProvider(currentShowProviderResolved()),
    )
    window.addEventListener(BUBBLE_THEME_CHANGED_EVENT, onThemeChanged)
    window.addEventListener('storage', onStorage)
    window.addEventListener(
      COMPOSER_SHOW_PROVIDER_SET_EVENT,
      onComposerShowProviderChanged,
    )
    window.addEventListener(COMPOSER_SHOW_PROVIDER_TIERS_EVENT, onShowProviderTiersChanged)
    window.addEventListener(COMPOSER_REWRITE_ENABLED_EVENT, onRewriteEnabledChanged)
    return () => {
      unsubscribeTier()
      window.removeEventListener(COMPOSER_SHOW_PROVIDER_TIERS_EVENT, onShowProviderTiersChanged)
      window.removeEventListener(COMPOSER_REWRITE_ENABLED_EVENT, onRewriteEnabledChanged)
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
  // #1703: persisted opt-out is the "Don't show this again" flag; the separate
  // session flag backs the X / Esc dismiss so a reload can re-offer the tip.
  const [hostCliTipNeverDismissed, setHostCliTipNeverDismissed] =
    useState(isHostCliTipDismissed)
  const [hostCliTipHidden, setHostCliTipHidden] = useState(false)
  /** #1700 (3): this tip's dismissal, persisted through `/v1/preferences/` on
   *  dismiss and rehydrated on mount, so it survives a reload instead of
   *  coming back every session. Distinct from the #1703 host-CLI flag above —
   *  two conditions, two dismissals. */
  const [vanillaTipDismissed, setVanillaTipDismissed] = useState(() =>
    isVanillaTipDismissedLocal(CONFIGURE_API_TIP_ID),
  )
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
  const [editsTick, setEditsTick] = useState(0)
  const [dropdownTick, setDropdownTick] = useState(0)
  const [selectedRemoteId, setSelectedRemoteId] = useState('')
  const [remoteThreadPicker, setRemoteThreadPicker] = useState<MemberSession[] | null>(null)
  // #789: the herdr talk-to choice lives in the composer routing picker —
  // its two-stage dialog lists the configured panes (GET /v1/herdr-agents/)
  // for a herdr seat and lands a pick in ?session=<name>, the same URL the
  // retired #543 navbar button wrote. The query stays warm for it.
  const herdrAgentsQuery = useQuery({
    queryKey: ['herdr-agents-chat'],
    queryFn: fetchHerdrAgents,
    // #789: warm whenever a herdr seat is on screen — the composer picker's
    // stage 2 lists these panes without a separate open-gated fetch.
    enabled: isHerdrKind(remoteFromUrl),
    retry: 1,
  })
  // #1793: ONE remote conversation id. The first-mount initialiser, the
  // render key and the hydrate request all call remoteThreadId(), so a remount
  // cannot ask for a different thread than the one it just rendered.
  const remoteConversationId = remoteFromUrl ? remoteThreadId(remoteFromUrl, sessionFromUrl) : ''
  const [conversationId, setConversationId] = useState(() =>
    teamFromUrl
      ? teamThreadId(teamFromUrl)
      : remoteFromUrl
        ? remoteThreadId(remoteFromUrl, sessionFromUrl)
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
      ? remoteConversationId
      : sessionFromUrl
        ? `${selectedBlueprint}::${sessionFromUrl}`
        : newChatPerTask
          ? conversationId
          : selectedBlueprint

  const messages = useMemo(() => threads[threadKey] ?? [], [threads, threadKey])
  // #1729: opening a Herdr seat IS the operator saying "I have seen it", so the
  // chat is where the status indicator and the unread dot are cleared. A Herdr
  // seat's row id is `herdr:<pane>` and the pane is the `session` param — the
  // same pair the backend's `seat_id_for` builds, so no second id spelling.
  const herdrSeatId = isHerdrKind(remoteFromUrl) && sessionFromUrl
    ? `herdr:${sessionFromUrl}`
    : ''
  useClearHerdrSeatOnOpen(herdrSeatId, Boolean(herdrSeatId))
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
  /** Consecutive auto-reconnect attempts since last successful open. */
  const lastUserTextRef = useRef('')
  // #1149: keys for optimistic user rows (upgraded in place by user_echo).
  const optimisticEchoCounterRef = useRef(0)
  // #1168: grace timer ref — fails still-pending echoes when the server never
  // confirms (dead socket race, restart). Cleared on user_echo/turn bookends.
  const pendingSendTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /** #1168: any server confirmation (user_echo / turn bookend) cancels the watchdog. */
  const disarmPendingSendWatchdog = useCallback(() => {
    if (pendingSendTimerRef.current) {
      clearTimeout(pendingSendTimerRef.current)
      pendingSendTimerRef.current = null
    }
  }, [])
  /** #1168: socket-close path disarms via ref (the hook runs before this decl). */
  const disarmPendingSendWatchdogRef = useRef<(() => void) | null>(null)
  disarmPendingSendWatchdogRef.current = disarmPendingSendWatchdog
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

  // #1167: typing anywhere in chat focuses the composer. Printable typing
  // with no editable control focused (body focus after clicking around) is
  // captured: the composer is focused and the character lands in it, so no
  // keystroke vanishes. Modifier combos, named keys, IME, and real inputs
  // are never captured (see lib/typingFocus.ts).
  useEffect(() => {
    const handler = makeTypingFocusHandler(
      () => composerRef.current,
      (el, ch) => {
        setInput((prev) => prev + ch)
        el.focus()
      },
    )
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

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
  // #1324: declared seat capabilities for the engine-switch warning.
  const seatCapabilitiesQuery = useQuery({
    queryKey: ['seat-capabilities'],
    queryFn: fetchSeatCapabilities,
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
  // #1700 (3) / #1725: the *first* consumer of GET /v1/support/context/ in the
  // SPA. `inference.configured` is the server's own answer to "can this host
  // run an API seat at all", and until now nothing in the UI asked — the fact
  // was emitted, serialised, and read by nobody. `retry: false` so a failed
  // read yields no tip rather than a speculative one.
  const supportContextQuery = useQuery({
    queryKey: ['support-context'],
    queryFn: fetchSupportContext,
    staleTime: 120_000,
    retry: false,
  })
  // #1317: Company model for this signed-in principal. Advisory on the
  // composer pill; the active blueprint stays whatever the seat already is.
  const companyRouteQuery = useQuery({
    queryKey: ['company-route'],
    queryFn: fetchCompanyRoute,
    staleTime: 60_000,
    retry: false,
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
  // #1699 / #1700: the agent picker is the one place a "seat" actually becomes a
  // chat target, so the server's admission verdict is applied here. Withheld
  // rows are dropped (a Remote-kind recipe on a host with no remote); listed-but-
  // unrunnable rows stay and carry their reason + repair label in the
  // description. `lib/blueprintSeats.ts` owns both rules.
  //
  // Keyed on the query data, not on `exampleRoleAgents`'s result: that call
  // returns a fresh array every render, so a memo over it would never hit.
  const blueprints = useMemo(
    () => pickerSeatRows(exampleRoleAgents(blueprintsQuery.data?.data ?? [])),
    [blueprintsQuery.data],
  )
  // `?? []` would allocate a fresh array every render while the query is empty
  // and these three sit in the same dep list, so the memo that owns the picker
  // rows (and every health poll that keys on `remotes`) would miss on every
  // render. `parseTeamRosters` also returns fresh objects, so it is memoized on
  // the query data rather than given a constant.
  const cliAgents = useMemo(
    () => cliQuery.data?.rail ?? emptyArray<CliRailAgent>(),
    [cliQuery.data],
  )
  const teams = useMemo(() => parseTeamRosters(teamsQuery.data), [teamsQuery.data])
  const remotes = useMemo(
    () => remotesQuery.data ?? emptyArray<RemoteEntry>(),
    [remotesQuery.data],
  )
  const selectedTeam = teams.find((team) => team.id === teamFromUrl) ?? null
  const teamDeclaredRoster = selectedTeam
    ? declaredRosterForTeam(selectedTeam, blueprintsQuery.data?.data ?? [])
    : null
  const selectedRemote = remotes.find((remote) => remote.id === remoteFromUrl) ?? null
  // #1196: the active chat's remote is polled (shared store) and its health
  // state re-read on every probe completion so the banner flips live.
  // `startRemoteHealthPolling` probes only ids this owner has just ADDED, so
  // re-running on a `remotes` identity change with the same selection costs
  // nothing — only an actual remote switch spends a request. The cleanup
  // releases this owner's demand, so leaving a remote (or unmounting) stops
  // re-probing it; the store keeps the interval alive for the rail.
  const [remoteHealthTick, setRemoteHealthTick] = useState(0)
  useEffect(() => {
    if (!selectedRemote) return
    startRemoteHealthPolling([selectedRemote.id], 'chat')
    const onHealth = () => setRemoteHealthTick((n) => n + 1)
    window.addEventListener(REMOTE_HEALTH_CHANGED_EVENT, onHealth)
    return () => {
      window.removeEventListener(REMOTE_HEALTH_CHANGED_EVENT, onHealth)
      stopRemoteHealthPolling('chat')
    }
  }, [selectedRemote?.id])
  const activeRemoteOffline =
    remoteHealthTick >= 0 && selectedRemote ? isRemoteOffline(selectedRemote.id) : false
  // #528: a team selection loses the navbar avatar that single agents get. The
  // member to show is "the one you are talking to": the navbar's explicit member
  // when one is targeted, else `defaultSessionForTeam`'s rule (chief_of_staff_id,
  // else CoS role, else first) — the same rule the rail's team row reads, so the
  // two surfaces cannot disagree about which face represents the team.
  const selectedRemoteSession = selectedRemote?.agents.find((agent) => agent.id === sessionFromUrl)
  const defaultRemoteSession = selectedRemote ? defaultSessionForRemote(selectedRemote) : null
  const remoteChatMemberId =
    selectedRemoteSession?.id ||
    sessionFromUrl ||
    defaultRemoteSession?.memberId ||
    remoteFromUrl
  const selectedTeamSession = selectedTeam?.members.find((member) => member.id === sessionFromUrl)
  const defaultTeamSession = selectedTeam ? defaultSessionForTeam(selectedTeam) : null
  const teamChatMemberId =
    teamFromUrl && selectedTeam
      ? memberTarget && memberTarget !== ALL_MEMBERS_TARGET
        ? memberTarget
        : (defaultTeamSession?.memberId ?? '')
      : ''
  const activeTeamMember = selectedTeamSession || defaultTeamSession
  const headerFaceAgentId = teamFromUrl
    ? teamChatMemberId || teamFromUrl
    : remoteFromUrl
    ? remoteChatMemberId
    : agentIdFromBlueprint(selectedBlueprint) || selectedBlueprint || ''
  // #1244: the header face must animate whenever its seat owns a live turn in
  // the shared registry — not only while the active thread streams. Without
  // this, sending a prompt then switching seats left the header idle (the
  // per-thread streaming flag belongs to the seat just left). `isWorking` is
  // still OR'd in by ChatHeader for the in-seat case.
  const headerWorking = isAgentTurnActive(headerFaceAgentId, agentTurns)
  // #108: only rail rows whose kind is actually 'cli' may drive the CLI
  // picker. api_agent is a rail row too (kind 'api') and must never match.
  // Designer-created CLI seats (`router_designs.json`, e.g. `antigravity` →
  // `agy`, `hass-eng` → `opencode`) are not in the `/v1/cli-agents/` rail.
  // Share AgentSidebar's `router-designs` cache and honour the seat's declared
  // `cli` so it renders as a CLI seat with that CLI's models — never an API
  // seat on the system default profile.
  const designsQuery = useQuery({
    queryKey: ['router-designs'],
    queryFn: fetchDesignedAgents,
    retry: 1,
    staleTime: 60_000,
  })
  const selectedCli = useMemo(() => {
    const rail = cliAgents.find(
      (row) => row.id === selectedBlueprint && row.kind !== 'api',
    )
    if (rail) return rail
    const design = designedCliSeat(selectedBlueprint, designsQuery.data?.data)
    if (!design) return undefined
    return {
      id: design.id,
      object: 'cli.agent' as const,
      name: design.name,
      cli: design.cli,
      kind: 'cli' as const,
      description: design.description,
      installed: true,
    }
  }, [cliAgents, selectedBlueprint, designsQuery.data])
  const selectedAgent = blueprints.find((bp) => bp.id === selectedBlueprint)
  // #1692: every seat avatar URL goes through `seatAvatarSrc` so the chat
  // header, the rail row and the pickers cannot each invent their own
  // precedence over the four accumulated field names. Each branch still picks
  // its own seat (member → session → remote → agent/CLI); only the "which
  // field is the face" question is shared.
  const headerFaceAvatarSrc = teamFromUrl
    ? seatAvatarSrc(activeTeamMember) ?? undefined
    : remoteFromUrl
    ? seatAvatarSrc(selectedRemoteSession) ??
      seatAvatarSrc(defaultRemoteSession) ??
      seatAvatarSrc(selectedRemote) ??
      undefined
    : seatAvatarSrc(selectedAgent) ?? seatAvatarSrc(selectedCli) ?? undefined
  // #1362: the navbar group-chat face is the team's membership — declared
  // personas when the blueprint declares a roster, else the live team members.
  // `ChatHeader` caps the ring at three faces and shows a `+N` remainder.
  const headerGroupMembers = teamFromUrl
    ? teamDeclaredRoster
      ? facesFromDeclaredRoster(teamDeclaredRoster, teamFromUrl)
      : (selectedTeam?.members ?? []).map((member) => ({
          id: member.id,
          name: member.name || member.id,
          agentId: member.id,
          src: seatAvatarSrc(member),
          working: isAgentTurnActive(member.id, agentTurns),
        }))
    : []
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
  const workspaceSubtitleParts =
    teamFromUrl || remoteFromUrl
      ? { full: '', display: '' }
      : navbarWorkspaceSubtitleParts(selectedBlueprint)
  const workspaceSubtitle = workspaceSubtitleParts.full
  const workspaceSubtitleDisplay = workspaceSubtitleParts.display
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
  // #1703: reuse the `/v1/cli-agents/` PATH seed the chat already fetches —
  // a detected-but-unconfigured CLI is the whole trigger.
  const showHostCliTip = shouldShowHostCliTip({
    info: cliQuery.data,
    dismissed: hostCliTipNeverDismissed || hostCliTipHidden,
  })
  const hostCliTipName = showHostCliTip ? hostCliDetectedName(cliQuery.data) : ''
  const dismissHostCliTip = useCallback(() => {
    setHostCliTipHidden(true)
  }, [])
  const neverShowHostCliTip = useCallback(() => {
    void persistHostCliTipDismissed()
    setHostCliTipNeverDismissed(true)
    setHostCliTipHidden(true)
  }, [])
  /** #1700 (3): persist first, then update state — a dismissal that only lived
   *  in component state would reappear on reload, the same defect class as the
   *  rest of this batch. */
  const dismissVanillaTip = useCallback(() => {
    void persistVanillaTipDismissed(CONFIGURE_API_TIP_ID)
    setVanillaTipDismissed(true)
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
  // #1703: Esc dismisses the host-CLI tip for this session, same guards as the
  // role tip so it never steals Esc from the composer or an open overlay.
  useEffect(() => {
    if (!showHostCliTip) return
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (document.querySelector('[role="dialog"], .modal-open, [data-testid="search-palette"]')) {
        return
      }
      e.preventDefault()
      dismissHostCliTip()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showHostCliTip, dismissHostCliTip])
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

  // #1445: leftover `agentKind === 'remote'` from an AnythingLLM visit must
  // not keep remotes chrome (or a remote send path) after the URL is a team
  // or a named API/CLI seat. Kind state is only authoritative while `?remote=`
  // is the seat; otherwise the selected agent's declared kind wins.
  const headerKindForRemote = remoteFromUrl
    ? agentKind
    : teamFromUrl
      ? undefined
      : (selectedAgent as { kind?: string } | undefined)?.kind ||
        classifyAgentKind(selectedBlueprint)
  const isRemoteAgent = isRemoteKindAgent({
    remoteFromUrl,
    agentKind: headerKindForRemote,
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

  /* #736: product-modes gating is retired — surfaces are always-on if
     configured. The remote control shows for any remote-backed seat. */
  const showRemotesControl =
    Boolean(remoteFromUrl) ||
    Boolean(isRemoteBackedTeam) ||
    (!teamFromUrl && Boolean(isRemoteAgent))
  const headerSeat = headerSeatKey({
    teamId: teamFromUrl,
    remoteId: remoteFromUrl,
    blueprintId: selectedBlueprint,
  })
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
  // #1352/#1353: each row also declares its **provider** (from Edit agent's
  // configured inference list, falling back to the row's own kind) so the
  // navbar Agent / Session pickers can scope to the selected agent's provider.
  // The default inference profile is never consulted here.
  const allPaletteAgents = useMemo(() => {
    const rows: Array<{
      id: string
      label: string
      kind: 'api' | 'cli' | 'remote' | 'team'
      provider: string
    }> = []
    const cliById = new Map(cliAgents.map((row) => [row.id, row]))
    const urlCli = (searchParams.get('cli') ?? '').trim()
    const scopeKey = (
      id: string,
      kind: 'api' | 'cli' | 'remote' | 'team',
      providerId: string,
    ): string => {
      // Edit agent (REQ-69) always wins over the row's declared kind.
      const scope = providerScopeForAgent({
        id,
        kind,
        providerId,
        inference: loadInferenceList(id)[0] ?? null,
      })
      return scope ? providerScopeKey(scope) : `${kind}:${providerId || id}`
    }
    for (const bp of blueprints) {
      const railCli = cliById.get(bp.id)
      const kind: 'api' | 'cli' = railCli
        ? 'cli'
        : isApiBlueprintId(bp.id)
          ? 'api'
          : isCliBlueprintId(bp.id)
            ? 'cli'
            : 'api'
      const providerId =
        kind === 'cli' ? railCli?.cli || bp.cli || urlCli || bp.id : 'api'
      rows.push({
        id: bp.id,
        label: bp.name || bp.id,
        kind,
        provider: scopeKey(bp.id, kind, providerId),
      })
    }
    for (const cli of cliAgents) {
      rows.push({
        id: cli.id,
        label: cli.name || cli.id,
        kind: 'cli',
        provider: scopeKey(cli.id, 'cli', cli.cli || cli.id),
      })
    }
    for (const remote of remotes) {
      rows.push({
        id: remote.id,
        label: remote.title || remote.id,
        kind: 'remote',
        provider: scopeKey(remote.id, 'remote', remote.id),
      })
    }
    for (const team of teams) {
      rows.push({
        id: team.id,
        label: team.name || team.id,
        kind: 'team',
        provider: scopeKey(team.id, 'team', team.id),
      })
    }
    return rows
  }, [blueprints, cliAgents, remotes, teams, searchParams, editsTick])
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
      const pickKind = seatPickKindForTarget(kind, targetId)
      const seatId = canonicalSeatTargetId(pickKind, targetId)
      const patch = seatParamsForPick(pickKind, seatId, { apiModel: detail?.apiModel })
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
  // #1358: a TrueForge seat lists agents + sessions from the dedicated
  // TrueForge endpoint — the source is TrueForge only, never the generic
  // operate path and never the default inference profile.
  const isTrueForgeSeat = isTrueForgeKind(selectedRemote?.kind || activeRemoteId)
  const remoteAgentsQuery = useQuery({
    queryKey: ['remote-operate-list', activeRemoteId, isTrueForgeSeat ? 'trueforge' : 'operate'],
    queryFn: () =>
      isTrueForgeSeat
        ? fetchTrueForgeNavbarCatalog(activeRemoteId)
        : operateRemote(activeRemoteId, { op: 'list' }, { timeoutMs: 12000 }),
    enabled: showRemotesControl && Boolean(activeRemoteId),
    retry: 1,
  })
  const remoteNavbarAgents = useMemo(
    () => (activeRemoteId ? remoteAgentsFromOperate(remoteAgentsQuery.data?.data) : []),
    [activeRemoteId, remoteAgentsQuery.data],
  )
  const ombBots = useMemo(
    () => ombBotsFromOperate(remoteAgentsQuery.data?.data),
    [remoteAgentsQuery.data],
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
  const ombSelectedBotId = ombSendTarget(sessionFromUrl, ombRemoteId || remoteFromUrl, ombBots)
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
  // #1257: folder picker applies to local-bound seats only — remote bridges
  // own a different filesystem and must not offer it.
  //
  // #1713 split this in two, because the two consumers CANNOT share one gate.
  // `workspaceFolderEditable` feeds `AgentConfigSidepane`, which renders a real
  // free-text "Working folder" input for any local-bound seat — including an API
  // agent, whose folder the navbar subtitle reads back. Narrowing that gate to
  // CLI would delete working behaviour.
  //
  // The second consumer is the pill's `os-navbar-workspace-subtitle-unset`
  // control, whose destination is the full `AgentEditor`. That editor routes its
  // Workspace section through `AgentWorkspaceBinding`, which offers a folder
  // input and the server directory picker for `kind === 'cli'` ONLY and renders
  // an explicit "Coming soon" stub otherwise. So an API seat was offered a
  // "Select folder" affordance whose destination had no folder control at all.
  //
  // `workspaceFolderPickerSeat` is the one-line gate #1713 asks for, and it is
  // derived from the seat the EDITOR will see rather than from a hand-kept list,
  // so the offer and the destination cannot drift apart.
  const workspaceFolderEditable = Boolean(
    !teamFromUrl && !remoteFromUrl && (isCliAgent || isApiAgent),
  )
  // What `AgentEditor` maps to `kind`, and what `AgentWorkspaceBinding` keys its
  // folder control on. `AgentEditor.tsx` maps anything that is not cli/remote to
  // 'api', and the binding renders the picker for `kind === 'cli'` only — so
  // this is the exact set of seats whose editor destination has the control.
  const workspaceFolderPickerSeat = Boolean(
    !teamFromUrl && !remoteFromUrl && isCliAgent,
  )

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
  // #1230: Compact is API-only — no CLI/remote opt-in lights it up any more.
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
    // #1220: the operator's rewrite opt-in gates the + menu item.
    rewriteEnabled: composerRewriteEnabled,
    // #516: the same swarm-owned reading the rail's Plugins entry gates on,
    // using the exact seat pair ChatPage publishes (id + kind) so the composer
    // menu cannot disagree with the badge.
    pluginsSwarmOwned: isSwarmOwnedAgent(activeChatAgentId || '', agentKind),
    // #551: declarations outrank kind-derived gates (one channel, ADR-005).
    declaredCapabilities,
  })

  // #1202: the navbar Agent / Session pickers consume ONE declared predicate
  // (never a re-derived per-surface kind identity) plus the operator's
  // hide-unsupported toggles. The Agent control never switches the seat.
  const navbarCapabilities = useMemo(
    () =>
      navbarSeatCapabilities({
        kind: teamFromUrl
          ? 'team'
          : remoteFromUrl
            ? 'remote'
            : isCliAgent
              ? 'cli'
              : 'api',
        isCli: isCliAgent,
        remoteSessions:
          (configuredRemoteRows.find((row) => row.id === activeRemoteId)?.capabilities as
            | { sessions?: boolean }
            | undefined)?.sessions ??
          (selectedRemote?.capabilities as { sessions?: boolean } | undefined)?.sessions,
        declared: declaredCapabilities,
        providerName: selectedRemote
          ? remoteDisplayName(selectedRemote)
          : isCliAgent
            ? currentCli || 'CLI host'
            : selectedAgentName,
      }),
    [
      teamFromUrl,
      remoteFromUrl,
      isCliAgent,
      selectedRemote,
      configuredRemoteRows,
      activeRemoteId,
      declaredCapabilities,
      currentCli,
      selectedAgentName,
    ],
  )
  const navbarPickerPrefs = useNavbarPickerPrefs()

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
  // #1356: the set of API / LiteLLM profile ids. They are a *different*
  // namespace from CLI model ids — a CLI seat must never offer one (it would
  // fail at `<cli> --model`).
  const apiProfileModelIds = useMemo(
    () =>
      new Set(
        apiModelOptionsFromProfiles(
          llmProfilesQuery.data?.profiles,
          llmProfilesQuery.data?.default_llm_profile
            ? [llmProfilesQuery.data.default_llm_profile]
            : [],
        ).map((opt) => opt.id),
      ),
    [llmProfilesQuery.data],
  )
  const availableCliModels = useMemo(() => {
    // #1356: keep only the CLI's own probed models; a stale saved model that
    // is an API profile id (leaked from a previous API seat or `?model=`) is
    // foreign and must not be listed.
    const merged = filterCliModels(cliModelProbe.models, apiProfileModelIds)
    const saved = (persistedDropdown.model || '').trim()
    if (
      saved &&
      !isHiddenRoutingLabel(saved) &&
      !apiProfileModelIds.has(saved) &&
      !merged.includes(saved)
    ) {
      merged.push(saved)
    }
    return merged
  }, [cliModelProbe.models, persistedDropdown.model, apiProfileModelIds])
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
  // #856: routing/dropdown plumbing moved verbatim to features/chat/useChatRouting.ts.
  const routingHook = useChatRouting({
    threadKey,
    setThreads,
    teamFromUrl,
    remoteFromUrl,
    selectedBlueprint,
    conversationIdRef,
    isRemoteAgent,
    isRemoteBackedTeam,
    isCliAgent,
    activeChatAgentId,
    currentCli,
    activeRemoteId,
    dropdownAgentId,
    setSearchParams,
    addToast,
  })
  const {
    recordDropdownChange,
    reconfigureProviderForSeat,
    applyCliRoutingChange,
    applyApiRoutingChange,
    warnBeforeEngineSwitch,
  } = routingHook

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
    window.addEventListener(AGENT_PROFILE_CHANGED_EVENT, onEdits)
    window.addEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
    window.addEventListener(AGENT_REMOTE_BINDINGS_CHANGED_EVENT, onEdits)
    window.addEventListener(AGENT_DROPDOWNS_CHANGED_EVENT, onDropdowns)
    return () => {
      window.removeEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
      window.removeEventListener(AGENT_PROFILE_CHANGED_EVENT, onEdits)
      window.removeEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
      window.removeEventListener(AGENT_REMOTE_BINDINGS_CHANGED_EVENT, onEdits)
      window.removeEventListener(AGENT_DROPDOWNS_CHANGED_EVENT, onDropdowns)
    }
  }, [])

  useEffect(() => {
    if (!showRemotesControl) {
      // #1445: leaving AnythingLLM / a remote seat must drop the bound id so
      // the header session switcher cannot keep showing that remote.
      setSelectedRemoteId('')
      return
    }
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
    void fetchAgentProfile(agent)
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

  useEffect(() => {
    void hydrateHostCliTipDismissed().then((dismissed) => {
      if (dismissed) setHostCliTipNeverDismissed(true)
    })
  }, [])

  // #1700 (3): pull the server-persisted dismissal in on mount. A tip dismissed
  // yesterday must not greet the operator again today.
  useEffect(() => {
    let cancelled = false
    void hydrateVanillaTipDismissals([CONFIGURE_API_TIP_ID]).then((ids) => {
      if (cancelled || ids.length === 0) return
      setVanillaTipDismissed(true)
    })
    return () => {
      cancelled = true
    }
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
    // #1793: a failed load says so EVEN WHEN a previous copy is on screen.
    // Recording it unconditionally lets the transcript label the rows it is
    // showing as the kept copy rather than live data; the empty-thread error
    // block still requires an empty transcript to render.
    setHydrateError(detail || fallback)
    if (!hadMessages) {
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
      // #1793: the same remoteThreadId() the render key uses, so the request
      // and the render can never address different conversations.
      const key = remoteConversationId
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
  }, [selectedBlueprint, sessionFromUrl, teamFromUrl, remoteFromUrl, remoteConversationId, newChatPerTask, threadKey, selectedCli, noteHydrateFailure])

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

  const pinnedToBottomRef = useRef(true)


  // #856 slice 5: the WS frame dispatcher moved verbatim to
  // features/chat/useChatWsDispatcher.ts.
  const stopFanOutLeg = useCallback((legId: string) => {
    const id = String(legId || '').trim()
    const ws = wsRef.current
    if (!id || !ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(buildCancelFanOutLegFrame(id))
  }, [])

  useEffect(() => {
    setFanOutLegs([])
  }, [threadKey])

  const handleWsEvent = useChatWsDispatcher({
    activeChatAgentId,
    attachQuestionToThread,
    attachToolToThread,
    sendToolDecision,
    threadKey,
    useSuggestions,
    seatUnread,
    pinnedToBottomRef,
    setContextUsage,
    setAgentTurns,
    setFanOutLegs,
    setAuxTasks,
    setSuggestionChips,
    setThreads,
    setUnreadIds,
    selectedBlueprint,
    userKeyCounterRef,
    notifyCtxRef,
    disarmPendingSendWatchdog: disarmPendingSendWatchdog,
  })

  // #738: stable ref so the WS effect doesn't list handleWsEvent as a dep.
  // The socket only rebuilds when connection coords change (conversationId,
  // runtimeBlueprint, teamFromUrl) — not on every inner state change.
  const handleWsEventRef = useRef(handleWsEvent)

  // #856 slice 4: chat WebSocket lifecycle (connect/reconnect/interrupt
  // handling) moved verbatim to features/chat/useChatWebSocket.ts.
  const wsControls = useChatWebSocket({
    connectAttempt,
    conversationId,
    runtimeBlueprint,
    teamFromUrl,
    remoteFromUrl,
    threadKey,
    wsRef,
    handleWsEventRef,
    notifyCtxRef,
    setStatus,
    setAuthRejected,
    setAwaitingAssistant,
    setThreads,
    setConnectAttempt,
    disarmPendingSendWatchdogRef,
  })
  const { reconnect } = wsControls

  // #856 slice 18: transcript layout & read-state effects moved verbatim to
  // features/chat/useTranscriptLayout.tsx.
  const { handleTranscriptScroll, composerBusy, identityTitleRef, mobileHeaderHidden } = useTranscriptLayout({
    messages,
    replyTarget,
    input,
    awaitingAssistant,
    selectedAgentName,
    workspaceSubtitle,
    status,
    connectAttempt,
    authRejected,
    signInHref,
    seatUnread,
    activeChatAgentId,
    conversationId,
    newBeforeKey,
    bottomDockRef,
    scrollBoxRef,
    listEndRef,
    composerRef,
    pinnedToBottomRef,
    composerInsetPx,
    setComposerInsetPx,
    setTranscriptHeightPx,
    setUnreadIds,
    addToast,
    dismissByKind,
    reconnect,
  })

  useEffect(() => {
    handleWsEventRef.current = handleWsEvent
  })


  useEffect(() => {
    publishChatConnection(status)
  }, [status])


  // #595: one signal for the composer's trailing controls — the Stop button
  // swaps into the microphone's slot while a turn is in flight, so the row
  // keeps a constant control count and never shifts under the pointer.


  // #856 slice D: attachment queue moved verbatim to features/chat/useComposerAttachments.
  const {
    pendingAttachments,
    composerDragOver,
    readyAttachIds,
    enqueueComposerFiles,
    handleComposerDragEnter,
    handleComposerDragOver,
    handleComposerDragLeave,
    handleComposerDrop,
    handleComposerPaste,
    removeAttachment,
    clearPendingAttachments,
  } = useComposerAttachments({
    addFilesEnabled: composerMenu.addFiles.enabled,
    addFilesReason: composerMenu.addFiles.reason,
    addToast,
  })
  const hasSendableDraft =
    !pendingAttachments.some((item) => item.status === 'uploading') &&
    (input.trim().length > 0 || readyAttachIds.length > 0)

  // #856: the send path moved verbatim to features/chat/useChatSend.ts.
  const sendText = useChatSend({
    wsRef,
    lastUserTextRef,
    pendingAttachments,
    clearPendingAttachments,
    runtimeBlueprint,
    selectedBlueprint,
    selectedCli,
    isCliAgent,
    isApiAgent,
    currentCli,
    currentCliSource,
    currentCliModel,
    persistedDropdown,
    companyRoute: companyRouteQuery.data,
    agentKind,
    selectedAgentName,
    searchParams,
    teamFromUrl,
    memberTarget,
    newChatPerTask,
    messages,
    remoteFromUrl,
    sessionFromUrl,
    ombBots,
    addToast,
    activeChatAgentId,
    bubbleTheme,
  })

  const submitUserText = useCallback(
    (text: string, resendKey?: string) => {
      const trimmed = text.trim()
      const readyAttach = readyAttachmentIds(pendingAttachments)
      if (!trimmed && readyAttach.length === 0) return
      // REQ-845 / #167: never drop a typed message on a closed/connecting socket. Keep
      // it in the per-conversation queue; the drain effect sends it on reopen.
      // (#1149: queued rows stay in the queue pane — no echo here; the echo
      // happens when the row actually drains through this function.)
      if (status !== 'open') {
        const fallbackText = composeOutboundDisplayText(trimmed, pendingAttachments)
        if (fallbackText) {
          queued.enqueue(fallbackText)
          // #1168: a resend attempted while the socket is down hands the text
          // to the queue — drop the failed row so it does not linger.
          if (resendKey) {
            setThreads((prev) => ({
              ...prev,
              [threadKey]: (prev[threadKey] ?? []).filter((m) => m.key !== resendKey),
            }))
          } else {
            addToast({
              type: 'info',
              title: 'Queued',
              message: 'Chat is reconnecting — your message will send when the socket is back.',
            })
          }
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
        // ADR-017 PR-5: a member-targeted team send serialises on the
        // MEMBER server-side (team#member lock) — it must not queue behind
        // the whole team. All-members composes keep the team-wide queue.
        const memberDirectSend =
          Boolean(teamFromUrl) &&
          memberTarget !== ALL_MEMBERS_TARGET &&
          memberTarget.trim() !== ''
        if (!apiSeatProven && !memberDirectSend) {
          const fallbackText = composeOutboundDisplayText(trimmed, pendingAttachments)
          if (fallbackText) {
            queued.enqueue(fallbackText)
          }
          return
        }
      }
      // #1149: optimistic echo — the user's own words render immediately on
      // the real-send path, marked pending; the server's user_echo upgrades
      // the row instead of duplicating it (see useChatWsDispatcher).
      // #1168: resend reuses the ORIGINAL echo row (same key) instead of
      // appending a duplicate — the failed row flips back to pending.
      const echoText = composeOutboundDisplayText(trimmed, pendingAttachments)
      let echoKey: string | null = resendKey ?? null
      if (echoText && !echoKey) {
        optimisticEchoCounterRef.current += 1
        echoKey = `user-pending-${optimisticEchoCounterRef.current}-${Date.now()}`
        setThreads((prev) => ({
          ...prev,
          [threadKey]: [
            ...(prev[threadKey] ?? []),
            {
              key: echoKey as string,
              role: 'user' as const,
              text: echoText,
              streaming: false,
              pending: true,
              ts: new Date().toISOString(),
            },
          ],
        }))
      } else if (echoKey) {
        setThreads((prev) => ({
          ...prev,
          [threadKey]: restorePendingSend(prev[threadKey] ?? [], echoKey as string),
        }))
      }
      setAwaitingAssistant(true)
      if (!sendText(trimmed)) {
        setAwaitingAssistant(false)
        // #1168: the frame was NOT handed to the socket (stale socket race —
        // status flipped after the 'open' check). Fail the echo immediately:
        // a pending row that can never be confirmed is worse than an honest
        // failure with a resend affordance.
        if (echoKey) {
          setThreads((prev) => ({
            ...prev,
            [threadKey]: (prev[threadKey] ?? []).map((m) =>
              m.key === echoKey ? { ...m, sendFailed: true } : m,
            ),
          }))
        }
        return
      }
      // #1168: arm the grace watchdog — if no server bookend arrives within
      // PENDING_SEND_GRACE_MS, still-pending echoes are declared lost.
      if (pendingSendTimerRef.current) clearTimeout(pendingSendTimerRef.current)
      pendingSendTimerRef.current = setTimeout(() => {
        pendingSendTimerRef.current = null
        setThreads((prev) => ({
          ...prev,
          [threadKey]: failStalePendingSends(prev[threadKey] ?? []),
        }))
        // The turn never started server-side — release the composer instead
        // of leaving the seat locked on a send that was lost.
        setAwaitingAssistant(false)
      }, PENDING_SEND_GRACE_MS)
    },
    [
      addToast,
      awaitingAssistant,
      memberTarget,
      messages,
      pendingAttachments,
      queued,
      selectedAgent,
      selectedBlueprint,
      sendText,
      status,
      teamFromUrl,
      threadKey,
    ],
  )

  // #1168: resend a lost send — the SAME echo row flips back to pending and
  // the text is pushed through the normal gate again (no duplicate row).
  const resendUserText = useCallback(
    (key: string, text: string) => {
      submitUserText(text, key)
    },
    [submitUserText],
  )

  // #856 slice 20: slash catalog & streaming-lifecycle wiring moved
  // verbatim to features/chat/useSlashLifecycle.ts.
  const {
    isSlashOpen,
    slashQuery,
    filteredSlashItems,
    handleInputChange,
    speechSettings,
    streamingMessage,
    isWorking,
    seatToolCalls,
    generationContexts,
    chipsDisabled,
    demoMode,
    demoChips,
    supportJourneyChips,
    showSupportJourneyChips,
    showDemoChips,
    showSuggestionChips,
    chooseSuggestion,
    gettingStartedFlow,
    gettingStartedChips,
    showGettingStartedFlow,
    handleSend,
  } = useSlashLifecycle({
    hasSendableDraft,
    replyTarget,
    setReplyTarget,
    setSkillCatalog,
    setDynamicSkills,
    isCliAgent,
    // #1230: the `/compact` slash action follows the same API-only gate as the
    // `+` menu item, so a CLI/remote seat never lists a compact at all.
    compactAvailable: isApiAgent,
    currentCli,
    selectedCli,
    cliQueryData: cliQuery.data,
    dynamicSkills,
    recentSlashIds,
    input,
    slashDismissed,
    composerWrapRef,
    setInput,
    setSlashSelectedIndex,
    setSlashDismissed,
    voiceBind,
    speechQueryData: speechQuery.data,
    plusOpen,
    plusRef,
    setPlusOpen,
    setPluginsPanelOpen,
    messages,
    awaitingAssistant,
    conversationId,
    selectedAgentName,
    status,
    activeChatAgentId,
    threadKey,
    threadReady,
    teamFromUrl,
    selectedBlueprint,
    useSuggestions,
    supportSelected,
    suggestionChips,
    setSuggestionChips,
    isRemoteAgent,
    isRemoteBackedTeam,
    queued,
    queuedHoldIds,
    drainLockRef,
    streamSeenRef,
    sendText,
    setAwaitingAssistant,
    setThreads,
    conversationIdRef,
    submitUserText,
  })

  const showCliSessionRecovery =
    threadReady && !awaitingAssistant && lastTurnNeedsRecovery(messages)
  // #499: the banner's primary action opens Settings on the section that can
  // actually resolve the failure — session actions stay as secondary options.
  const cliRecoveryConfigTarget = showCliSessionRecovery
    ? lastRecoveryTarget(messages)
    : undefined

  // #856 slice 16: CLI session ops, interrupt, chips, edit-save moved
  // verbatim to features/chat/useChatTurnOps.ts.
  const {
    startFreshCliSession,
    retryCliSession,
    clearCliSessionHistory,
    interruptRunningTurn,
    saveEditedMessage,
    toggleMessageReaction,
  } = useChatTurnOps({
    selectedBlueprint,
    setSearchParams,
    messages,
    submitUserText,
    conversationId,
    threadKey,
    threads,
    setThreads,
    wsRef,
    lastUserTextRef,
    conversationIdRef,
    messagesEditable,
    setAwaitingAssistant,
    setEditingKey,
    addToast,
  })

  // ADR-017 PR-2: the row stop resolves the agent's live turn from the
  // bookend registry, so the cancel frame names the exact turn_id. Bare
  // (no live turn known) keeps #1096's agent-scoped shape.
  const stopActiveAgentTurn = useCallback(() => {
    const live = activeTurnFor(agentTurns, activeChatAgentId || '')
    if (live) {
      interruptRunningTurn(live.agentId, live.turnId)
    } else {
      interruptRunningTurn(activeChatAgentId || undefined)
    }
  }, [agentTurns, activeChatAgentId, interruptRunningTurn])

  // #856 slice 15: compact/summary turn commands moved verbatim to
  // features/chat/useChatCompact.ts.
  const {
    handleCompact,
    applyStartFromHere,
    handleContextToHere,
  } = useChatCompact({
    messages,
    conversationId,
    selectedBlueprint,
    teamFromUrl,
    threadKey,
    cullTriggerPct,
    contextStrategy,
    contextMaxRef,
    setSummariesByThread,
    setContextMeta,
    setContextUsage,
    setStartFromHereWarning,
    setPlusOpen,
    setContextMenu,
    addToast,
  })

  // #856: composer command/session wiring moved verbatim to
  // features/chat/useComposerCommands.ts.
  const slashHook = useComposerCommands({
    isCliAgent,
    currentCli,
    selectedBlueprint,
    addToast,
    handleCompact,
    setInput,
    setSlashDismissed,
    setRecentSlashIds,
    composerRef,
    setSearchParams,
  })
  // #856: slash-command picking moved verbatim to features/chat/useComposerCommands.ts.
  const handleSelectSlashItem = slashHook.handleSelectSlashItem
  const resumeComposerSession = slashHook.resumeComposerSession

  const tokenCount = estimateTokensInContext(contextTextsForMeter(messages, summaries))

  // #1700 (3): the first-run tip, from the one host fact the server owns and
  // nothing else reads (`GET /v1/support/context/`). `firstVanillaTip` fails
  // open on a missing payload, so a failed read produces no tip rather than a
  // guess, and it stands down while the #1703 host-CLI tip owns the slot.
  //
  // Deliberately NOT gated on the seat in the URL. ChatPage writes
  // `?blueprint=support` as its default a moment after mount, so a
  // "did the operator ask for a seat?" check reads that default and the tip
  // never fires on a greenfield install — which is the one case it exists for.
  // A first-run banner is also the right thing on a deep link: without a
  // provider the very next turn is what fails, and the tip is why.
  const vanillaTip = firstVanillaTip({
    supportContext: supportContextQuery.data ?? null,
    cliAgents: cliQuery.data ?? null,
    defaultLlmReady: llmProfilesQuery.data?.default_llm_ready,
    dismissedIds: vanillaTipDismissed ? [CONFIGURE_API_TIP_ID] : [],
  })
  const vanillaTipNode = vanillaTip ? (
    <VanillaSetupTip tip={vanillaTip} onDismiss={dismissVanillaTip} />
  ) : null

  // #856 slice 19: routing-picker inputs & derived chat metrics moved
  // verbatim to features/chat/useChatDerived.ts.
  const {
    selectedModelId,
    contextMax,
    sendNowHint,
    showDefaultLlmTip,
    tokenDiagOpen,
    setTokenDiagOpen,
    inputTokens,
    outputTokens,
    toolCallsCount,
    userMessageCount,
    assistantMessageCount,
    composerPlaceholder,
    workingTip,
    statusLabel,
    setComposerSessionsOpen,
    composerSources,
    composerProviders,
  } = useChatDerived({
    searchParams,
    isCliAgent,
    currentCli,
    currentCliModel,
    persistedDropdown,
    companyRoute: companyRouteQuery.data,
    llmProfilesQuery,
    llmDefaultProfile: llmProfilesQuery.data?.default_llm_profile,
    input,
    queuedRows: queued.rows,
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
  })

  // #856 slice 17: composer input controls (handleMic, handleComposerKeyDown)
  // moved verbatim to features/chat/useComposerControls.ts.
  const {
    handleMic,
    handleComposerKeyDown,
    handleMicPointerDown,
    handleMicPointerUp,
    handleMicPointerCancel,
    voiceNoteRecording,
    voiceNoteOffer,
    sendVoiceNote,
    cancelVoiceNote,
    chooseVoiceNoteTranscription,
  } = useComposerControls({
    sttListening,
    speechSettings,
    activeChatAgentId,
    setInput,
    addToast,
    sttStopRef,
    setSttListening,
    setSttPathUsed,
    isSlashOpen,
    filteredSlashItems,
    slashSelectedIndex,
    setSlashSelectedIndex,
    handleSelectSlashItem,
    setSlashDismissed,
    plusOpen,
    setPlusOpen,
    replyTarget,
    setReplyTarget,
    input,
    showRoleTip,
    dismissRoleTip,
    pendingAttachments,
    submitUserText,
    queuedRows: queued.rows,
    queuedHoldIds,
    interruptRunningTurn,
    enqueueComposerFiles,
  })

  // #856 slice P: the six pass-through props objects collapse into one
  // spreadable scope record. Each extracted module (ChatHeader,
  // ChatTranscriptShell, ChatOverlays, ChatMessageList, ChatBottomDock)
  // destructures exactly these names, so spreading one record preserves
  // behaviour. renderRoutingPicker rides inside as a callable - the dock
  // invokes it rather than spreads it.
  const renderRoutingPicker = () =>
    renderRoutingPickerImpl(allChatScope as unknown as Record<string, any>)

  const allChatScope = {
    AgentAvatar,
    GroupAvatar,
    ChatMessageActions,
    ChatMessageBubble,
    ChatNewRule,
    CliSessionRecoveryBanner,
    DemoTourBanner,
    IrcNoticeLine,
    MessageRowActions,
    PrOpenedCard,
    QuestionCard,
    RateLimitStatusLine,
    ReadAloudButton,
    SHOW_MESSAGE_ACTIONS,
    START_CONTEXT_FROM_HERE_LABEL,
    SubagentFanOutBlock,
    SuggestionChips,
    SummaryBlock,
    SystemPreloadPill,
    TeammateTaskCard,
    ToolCallPopup,
    activeChatAgentId,
    activeSelectionRef,
    agentIdFromBlueprint,
    attachToolToThread,
    awaitingAssistant,
    blueprints,
    bubbleTheme,
    cacheRowSelection,
    CarriedSummaryBlock,
    chipsDisabled,
    chooseSuggestion,
    clearCliSessionHistory,
    cliAgents,
    cliRecoveryConfigTarget,
    composerRef,
    configuredRemotes,
    contextMeta,
    contextStrategy,
    conversationId,
    demoMode,
    displayItems,
    editedAgentLabel,
    editingKey,
    expandedThinkingKeys,
    extractThinkingBlock,
    formatGapLabel,
    formatRateLimitNotice,
    getBubbleTheme,
    handleBubbleContextMenu,
    interruptRunningTurn: stopActiveAgentTurn,
    fanOutLegs,
    stopFanOutLeg,
    handleContextToHere,
    handleSaveSummary,
    handleToggleSummaryContext,
    hiddenMessageKeys,
    hiddenSummaryIds,
    hydrateError,
    isApiAgent,
    isRemoteBackedTeam,
    navbarCapabilities,
    hideUnsupportedAgentPicker: navbarPickerPrefs.hideUnsupportedAgentPicker,
    hideUnsupportedSessionPicker: navbarPickerPrefs.hideUnsupportedSessionPicker,
    isHerdrSeat,
    isStatusRole,
    jumpToPrOpener,
    lastUserTextRef,
    listEndRef,
    messages,
    messagesEditable,
    newBeforeKey,
    nowMs,
    openSettingsSheet,
    parseCreatedAtMs,
    personaForAgentMessage,
    rawOffsetForMessage,
    rememberAlwaysAllow,
    remotesListQuery,
    resolveReplyQuote,
    restoreNotice,
    retryCliSession,
    saveEditedMessage,
    toggleMessageReaction,
    selectedAgent,
    selectedAgentName,
    selectedBlueprint,
    selectedTeam,
    sendQuestionAnswer,
    sendText,
    sendToolDecision,
    onResendSend: resendUserText,
    setEditingKey,
    setHiddenMessageKeys,
    setHiddenSummaryIds,
    setOpenSkillName,
    setRawResponseModalText,
    setReplyTarget,
    setThreads,
    settingsTargetForProvider,
    showCliSessionRecovery,
    showSupportJourneyChips,
    showGettingStartedFlow,
    gettingStartedFlow,
    gettingStartedChips,
    skillCatalog,
    startFreshCliSession,
    streamingMessage,
    summaryMap,
    supportJourneyChips,
    teamFromUrl,
    themeUsesIrcGutter,
    threadKey,
    threadReady,
    toggleThinking,
    voiceBind,
    workingTip,
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
    capabilityCatalog: seatCapabilitiesQuery.data ?? null,
    warnBeforeEngineSwitch,
    applyTeamMemberSessionParam,
    availableCliModels,
    // #1356: API/LiteLLM profile ids — the foreign namespace a CLI seat must
    // never offer (renderRoutingPicker forwards this to NavbarRoutingPicker).
    foreignModelIds: [...apiProfileModelIds],
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
    isCliAgent,
    isRemoteAction,
    llmProfilesQuery,
    memberOptionLabel,
    memberTarget,
    navigateToPaletteAgent,
    ombSelectedBotId,
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
    companyRouteSource:
      isApiAgent &&
      companyRouteQuery.data?.applied &&
      companyRouteQuery.data.model &&
      selectedModelId === companyRouteQuery.data.model.trim()
        ? companyRouteQuery.data.source
        : '',
    selectedRemoteId,
    sessionFromUrl,
    setComposerSessionsOpen,
    setMemberTarget,
    setSearchParams,
    setSelectedRemoteId,
    showEmptyRemoteChrome,
    showRemotesControl,
    status,
    ArrowUp,
    ChatMessageInput,
    ComposerAttachChips,
    ComposerPluginsBadge,
    ComposerPluginsPanel,
    ComposerSlashPopup,
    ContextUsageBadge,
    Layers,
    Mic,
    Paperclip,
    Plug,
    Plus,
    Sparkles,
    QueuedSendPane,
    Reply,
    Square,
    addToast,
    authRejected,
    bottomDockRef,
    composerBusy,
    composerDragOver,
    composerMenu,
    composerPlaceholder,
    composerWrapRef,
    contextUsage,
    demoChips,
    describeSpeechPath,
    enqueueComposerFiles,
    fileInputRef,
    filesFromList,
    filteredSlashItems,
    generationIsInFlight,
    handleCompact,
    handleComposerDragEnter,
    handleComposerDragLeave,
    handleComposerDragOver,
    handleComposerDrop,
    handleComposerKeyDown,
    handleComposerPaste,
    handleInputChange,
    handleMic,
    handleMicPointerDown,
    handleMicPointerUp,
    handleMicPointerCancel,
    voiceNoteRecording,
    voiceNoteOffer,
    sendVoiceNote,
    cancelVoiceNote,
    chooseVoiceNoteTranscription,
    handleSelectSlashItem,
    handleSend,
    hasSendableDraft,
    input,
    isSlashOpen,
    // #1070: Send-now mirrors the composer's Enter-on-empty contract —
    // interrupt the running turn; the drain effect promotes the queued row.
    onSendNow: interruptRunningTurn,
    // #1232: per-row immediate send — promote the picked row to the queue
    // head, then interrupt if a turn is in flight so the drain sends it now.
    // Other queued rows stay queued (out-of-order send without dropping).
    onSendQueuedImmediately: useCallback(
      (id: string) => {
        queued.moveToTop(id)
        if (generationIsInFlight(messages, awaitingAssistant)) {
          interruptRunningTurn()
        }
      },
      [queued, messages, awaitingAssistant, interruptRunningTurn],
    ),
    pendingAttachments,
    pluginsPanelOpen,
    plusOpen,
    plusRef,
    queued,
    queuedPaneMaxHeightPx,
    recentSlashIds,
    removeAttachment,
    replyTarget,
    sendNowHint,
    setInput,
    setPluginsPanelOpen,
    setPlusOpen,
    setQueuedHoldIds,
    setSlashSelectedIndex,
    setTokenDiagOpen,
    showContextUsage,
    showDemoChips,
    showSuggestionChips,
    slashQuery,
    slashSelectedIndex,
    sttListening,
    sttPathUsed,
    suggestionChips,
    transcriptHeightPx,
    ApiSessionSwitcher,
    AuxActivityIndicator,
    CliSessionSwitcher,
    ComputerControlStub,
    OPEN_SETTINGS_EVENT,
    Folder,
    PanelLeft,
    Pencil,
    PersonaRoster,
    RemoteSessionSwitcher,
    Settings,
    ThemeToggle,
    activeRemoteId,
    auxTasks,
    cliQuery,
    cliRemoteSession,
    generationsOpen,
    headerFaceAgentId,
    headerSeat,
    headerGroupMembers,
    headerFaceAvatarSrc,
    headerRole,
    headerRoleLabel,
    headerWorking,
    identityTitleRef,
    isChiefOfStaff,
    isExampleRole,
    isRemoteCapableCli,
    isWorking,
    mobileHeaderHidden,
    narrow,
    openAgentEditor,
    openRail,
    openTeamEditor,
    railOpen,
    requestAuxCancel,
    roleCssClass,
    searchParams,
    selectedRemote,
    setGenerationsOpen,
    showHeaderRole,
    teamChatMemberId,
    teamDeclaredRoster,
    workspaceSubtitle,
    workspaceSubtitleDisplay,
    workspaceFolderEditable,
    workspaceFolderPickerSeat,
    wsRef,
    COPY_EMPTY_MESSAGE,
    COPY_EMPTY_TITLE,
    COPY_FAILED_MESSAGE,
    COPY_FAILED_TITLE,
    ConfirmModal,
    Copy,
    FoldVertical,
    GenerationsPanel,
    RawResponseModal,
    START_CONTEXT_FROM_HERE_TOOLTIP,
    SessionPicker,
    SkillPopup,
    TokenDiagnosticsModal,
    agentKind,
    applyStartFromHere,
    assistantMessageCount,
    contextMax,
    contextMenu,
    copyTextToClipboard,
    generationContexts,
    inputTokens,
    openSkillName,
    outputTokens,
    rawResponseModalText,
    remoteThreadPicker,
    seatToolCalls,
    setContextMenu,
    setRemoteThreadPicker,
    setStartFromHereWarning,
    startFromHereWarning,
    summaries,
    toastError,
    tokenCount,
    tokenDiagOpen,
    toolCallsCount,
    userMessageCount,
    ChatBottomDock,
    ChatMessageList,
    ConsumerPills,
    DefaultLlmTip,
    HostCliTip,
    RoleAgentTip,
    VanillaSetupTip: vanillaTipNode,
    composerInsetCustomProperty,
    composerInsetPx,
    dismissDefaultLlmTip,
    dismissHostCliTip,
    dismissRoleTip,
    handleTranscriptScroll,
    hostCliTipName,
    ircGutterDragging,
    ircGutterPx,
    isRemoteAgent,
    neverShowHostCliTip,
    onIrcRailDoubleClick,
    onIrcRailPointerDown,
    onIrcRailPointerMove,
    onIrcRailPointerUp,
    scrollBoxRef,
    showDefaultLlmTip,
    showHostCliTip,
    showRoleTip,
    statusLabel,
    renderRoutingPicker,
  }

  return (
    <div className="os-chat flex h-full min-h-0 w-full flex-col">
      {/* Mounted-but-hidden only while it holds focus (gear restore); otherwise
          the header is unmounted so no stale identity is queryable. */}
      <div ref={headerWrapRef} hidden={showChatHeader ? undefined : true}>
        {renderChatHeader && (
        <>
        {activeRemoteOffline && (
          // #1196: warn before the send fails, not after — the backing gateway
          // for this seat is unreachable right now.
          <div
            role="alert"
            className="alert alert-warning py-2 px-3 text-sm rounded-none"
            data-testid="remote-offline-banner"
          >
            <span className="min-w-0 flex-1">
              Remote backend <strong>{selectedRemote?.title || selectedRemote?.id}</strong> appears
              to be offline. Message delivery or streaming may fail.
            </span>
            <button
              type="button"
              className="btn btn-xs btn-outline"
              data-testid="remote-offline-manage"
              onClick={() => openSettingsSheet({ section: 'remotes' })}
            >
              Manage Remotes
            </button>
          </div>
        )}
        {/* #445: no `overflow-hidden` here. It clipped the routing flyout to the
            header's box (the flyout is an absolutely-positioned child of the
            picker inside this header), leaving only its first row reachable.
            Titles still clamp in `.os-navbar-identity-label`. */}
        <ChatHeader {...allChatScope} />
        </>
        )}
      </div>
      <ChatTranscriptShell {...allChatScope} />
      <ChatOverlays {...allChatScope} />

    </div>
  )
}

export default ChatPage
