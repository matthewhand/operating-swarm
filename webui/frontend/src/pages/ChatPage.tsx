import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChatBottomDock } from '../features/chat/ChatBottomDock'
import { ChatOverlays } from '../features/chat/ChatOverlays'
import { ChatTranscriptShell } from '../features/chat/ChatTranscriptShell'
import { renderRoutingPickerImpl } from '../features/chat/renderRoutingPicker'
import { ChatHeader } from '../features/chat/ChatHeader'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Copy, FoldVertical, Layers, Mic, PanelLeft, Paperclip, Pencil, Plug, Plus, Reply, Settings, Square } from 'lucide-react'
import AgentAvatar from '../components/AgentAvatar'
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
} from '../components/SettingsSheet'
import RateLimitStatusLine from '../components/RateLimitStatusLine'



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
  parseContextStrategy,
  parseCullTriggerPct,
  type ContextMeta,
  type ContextStrategy,
} from '../lib/contextCull'
import { persistableMessages, putAgentChatSession } from '../lib/agentChatSessions'

import { useRailChrome } from '../components/RailChrome'
import { ComputerControlStub } from '../components/ComputerControlStub'
import { NavbarRoutingPicker } from '../components/NavbarRoutingPicker'

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

import SessionPicker from '../components/SessionPicker'
import CliSessionSwitcher from '../components/CliSessionSwitcher'
import ApiSessionSwitcher from '../components/ApiSessionSwitcher'
import RemoteSessionSwitcher from '../components/RemoteSessionSwitcher'
import {
  fetchRemoteThreadSessions,
  mostRecentRemoteSession,
  remoteAgentsFromOperate,
  remoteListsSessions,
} from '../lib/remoteSessions'
import type { MemberSession } from '../lib/sessionPicker'

// #856 slice 2: summary card tree moved verbatim to features/chat/SummaryBlock.tsx.

import { ComposerSlashPopup } from '../components/ComposerSlashPopup'
import ComposerAttachChips from '../components/ComposerAttachChips'
import {
  attachmentCaption,
  filesFromList,
  readyAttachmentIds,
} from '../lib/chatAttachments'
import { composerMenuCapabilities } from '../lib/composerMenu'
import { applyRemoteRoutingChange } from '../lib/remoteRouting'
import { ComposerPluginsPanel } from '../components/ComposerPluginsPanel'
import {
  buildSlashCatalog,
  filterSlashItems,
  getRecentSlashIds,
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
import {
  buildQuestionAnswerFrame,
  buildToolDecisionFrame,
} from '../lib/chatWs'
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

import type { DecisionQuestion } from '../lib/decisionQuestion'

import GenerationsPanel, { type PanelToolCall } from '../components/GenerationsPanel'


import { SuggestionChips } from '../components/SuggestionChips'
import ConsumerPills from '../components/ConsumerPills'
import ComposerPluginsBadge from '../components/ComposerPluginsBadge'

import { isDemoMode } from '../lib/demo/mode'
import { demoSuggestionChips } from '../lib/demo/scenarios'
import {
  openerChatSearch,
  type PrOpenedOpener,
} from '../lib/prOpened'
import SubagentFanOutBlock from '../components/SubagentFanOutBlock'

import { TokenDiagnosticsModal } from '../components/TokenDiagnosticsModal'
import { RawResponseModal } from '../components/RawResponseModal'
import { isHerdrAgent } from '../lib/railHotkeys'
import {
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
  OMB_NO_AGENTS_WARNING,
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
import { useChatWebSocket } from '../features/chat/useChatWebSocket'
import { useChatWsDispatcher } from '../features/chat/useChatWsDispatcher'
import { useChatSend } from '../features/chat/useChatSend'
import { useComposerCommands } from '../features/chat/useComposerCommands'
import { useChatCompact } from '../features/chat/useChatCompact'
import { useChatTurnOps } from '../features/chat/useChatTurnOps'
import { useComposerControls } from '../features/chat/useComposerControls'
import { useTranscriptLayout } from '../features/chat/useTranscriptLayout'
import { useChatDerived } from '../features/chat/useChatDerived'
import { useChatRouting } from '../features/chat/useChatRouting'
import { useComposerAttachments } from '../features/chat/useComposerAttachments'
import { ChatMessageList } from '../features/chat/ChatMessageList'
import { ChatMessageActions } from '../experimental/ChatMessageActions'
import { ChatMessageBubble } from '../components/ChatMessageBubble'
import { ChatNewRule } from '../components/ChatLogMarkers'
import CliSessionRecoveryBanner from '../components/CliSessionRecoveryBanner'
import { DemoTourBanner } from '../components/DemoTourBanner'
import { IrcNoticeLine } from '../components/IrcNoticeLine'
import { PrOpenedCard } from '../components/PrOpenedCard'
import { QuestionCard } from '../components/QuestionCard'
import { SummaryBlock } from '../features/chat/SummaryBlock'
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
  agentHasRole,
  agentRole,
  exampleRoleAgents,
  isChiefOfStaff,
  isExampleRole,
  roleBadgeLabel,
  roleCssClass,
} from '../lib/agentRoles'
import { assignedBlueprintId, AGENT_EDITS_CHANGED_EVENT, editedAgentLabel, loadAgentEdit } from '../lib/agentEdits'
import { cliRemoteSessionChoices, isRemoteCapableCli } from '../lib/cliRemote'
import { navbarWorkspaceSubtitle } from '../lib/agentWorkspace'
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
} from '../lib/cliSessions'
import {
  CLI_SESSION_HOPPED_EVENT,
} from '../lib/cliSessionHop'
// #636: CLI-seat compact orchestration (summary + fresh session carrying it).
import {
  drainHoldUntilStreamStarts,
  generationIsInFlight,
  nextDrainableQueuedSend,
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
  MANAGE_CLI_VALUE,
} from '../lib/cliAgentContext'
import { isHiddenRoutingLabel, type RoutingSeatKind } from '../lib/routingPath'
import {
  seatParamsForPick,
  type SeatPickKind,
} from '../lib/seatRouting'

// #856 slice 1: module-scope message/session types and helpers moved verbatim to
// features/chat/chatMessages.ts; re-imported here so the component body and the
// '../ChatPage' import surface are unchanged.
import {
  chatLoginHref,
  hydrateThreadRows,
  type ChatMessage,
} from '../features/chat/chatMessages'

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
  /** Consecutive auto-reconnect attempts since last successful open. */
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

  /* #736: product-modes gating is retired — surfaces are always-on if
     configured. The remote control shows for any remote-backed seat. */
  const showRemotesControl =
    Boolean(remoteFromUrl) || Boolean(isRemoteAgent || isRemoteBackedTeam)
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
  const { recordDropdownChange, reconfigureProviderForSeat, applyCliRoutingChange, applyApiRoutingChange } = routingHook

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

  const pinnedToBottomRef = useRef(true)


  // #856 slice 5: the WS frame dispatcher moved verbatim to
  // features/chat/useChatWsDispatcher.ts.
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
    setAuxTasks,
    setSuggestionChips,
    setThreads,
    setUnreadIds,
    selectedBlueprint,
    userKeyCounterRef,
    notifyCtxRef,
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
  })
  const { reconnect } = wsControls

  // #856 slice 18: transcript layout & read-state effects moved verbatim to
  // features/chat/useTranscriptLayout.tsx.
  const { handleTranscriptScroll, composerBusy, identityTitleRef } = useTranscriptLayout({
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
    agentKind,
    selectedAgentName,
    searchParams,
    teamFromUrl,
    memberTarget,
    newChatPerTask,
    messages,
    remoteFromUrl,
    sessionFromUrl,
    addToast,
    activeChatAgentId,
  })

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
    isCliAgent,
    currentCli,
    selectedCli,
    llmDefaultReady: llmProfilesQuery.data?.default_llm_ready === true,
    cliCompactCapableMap: cliQuery.data?.cli_compact as Record<string, unknown> | undefined,
    cullTriggerPct,
    contextStrategy,
    contextMaxRef,
    setSummariesByThread,
    setContextMeta,
    setContextUsage,
    setStartFromHereWarning,
    setPlusOpen,
    setContextMenu,
    setConversationId,
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
  const { handleMic, handleComposerKeyDown } = useComposerControls({
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
  })

  const chatMessageListProps = {
    AgentAvatar,
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
      agentKind,
    attachToolToThread,
    awaitingAssistant,
    blueprints,
    bubbleTheme,
    cacheRowSelection,
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
    handleContextToHere,
    handleSaveSummary,
    handleToggleSummaryContext,
    hiddenMessageKeys,
    hiddenSummaryIds,
    hydrateError,
    isApiAgent,
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
    selectedAgent,
    selectedAgentName,
    selectedBlueprint,
    selectedTeam,
    sendQuestionAnswer,
    sendText,
    sendToolDecision,
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
    __self: null as unknown,
  }

  const renderRoutingPickerProps = {
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
  }

  const renderRoutingPicker = () =>
    renderRoutingPickerImpl(renderRoutingPickerProps)

  const chatBottomDockProps = {
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
    QueuedSendPane,
    Reply,
    Square,
    SuggestionChips,
    addToast,
    authRejected,
    awaitingAssistant,
    bottomDockRef,
    chipsDisabled,
    chooseSuggestion,
    composerBusy,
    composerDragOver,
    composerMenu,
    composerPlaceholder,
    composerRef,
    composerWrapRef,
    contextUsage,
    conversationId,
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
    handleSelectSlashItem,
    handleSend,
    hasSendableDraft,
    input,
    interruptRunningTurn,
    isApiAgent,
    isSlashOpen,
    messages,
    pendingAttachments,
    pluginsPanelOpen,
    plusOpen,
    plusRef,
    queued,
    queuedPaneMaxHeightPx,
    recentSlashIds,
    removeAttachment,
    renderRoutingPicker,
    replyTarget,
    selectedBlueprint,
    sendNowHint,
    setInput,
    setPluginsPanelOpen,
    setPlusOpen,
    setQueuedHoldIds,
    setReplyTarget,
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
    __ctx: null as unknown,
  }

  const chatHeaderProps = {
    AgentAvatar,
    ApiSessionSwitcher,
    AuxActivityIndicator,
    CliSessionSwitcher,
    ComputerControlStub,
    OPEN_SETTINGS_EVENT,
    PanelLeft,
    Pencil,
    PersonaRoster,
    RemoteSessionSwitcher,
    Settings,
    ThemeToggle,
    activeChatAgentId,
    activeRemoteId,
    auxTasks,
    cliQuery,
    cliRemoteSession,
    configuredRemoteRows,
    currentCli,
    generationsOpen,
    headerFaceAgentId,
    headerRole,
    headerRoleLabel,
    identityTitleRef,
    isApiAgent,
    isChiefOfStaff,
    isCliAgent,
    isExampleRole,
    isRemoteCapableCli,
    isWorking,
    narrow,
    openAgentEditor,
    openRail,
    openSettingsSheet,
    openTeamEditor,
    railOpen,
    requestAuxCancel,
    roleCssClass,
    searchParams,
    selectedAgent,
    selectedAgentName,
    selectedBlueprint,
    selectedRemote,
    selectedTeam,
    setGenerationsOpen,
    setSearchParams,
    showEmptyRemoteChrome,
    showHeaderRole,
    showRemotesControl,
    teamChatMemberId,
    teamDeclaredRoster,
    teamFromUrl,
    workspaceSubtitle,
    wsRef,
    __ctx: null as unknown,
  }
  const chatOverlaysProps = {
    COPY_EMPTY_MESSAGE,
    COPY_EMPTY_TITLE,
    COPY_FAILED_MESSAGE,
    COPY_FAILED_TITLE,
    ConfirmModal,
    Copy,
    FoldVertical,
    GenerationsPanel,
    RawResponseModal,
    Reply,
    START_CONTEXT_FROM_HERE_LABEL,
    START_CONTEXT_FROM_HERE_TOOLTIP,
    SessionPicker,
    SkillPopup,
    TokenDiagnosticsModal,
    agentKind,
    applyStartFromHere,
    assistantMessageCount,
    composerRef,
    contextMax,
    contextMenu,
    contextMeta,
    contextStrategy,
    conversationId,
    copyTextToClipboard,
    generationContexts,
    generationsOpen,
    handleContextToHere,
    headerFaceAgentId,
    inputTokens,
    isApiAgent,
    messages,
    openSkillName,
    outputTokens,
    rawResponseModalText,
    remoteFromUrl,
    remoteThreadPicker,
    seatToolCalls,
    selectedAgentName,
    setContextMenu,
    setGenerationsOpen,
    setOpenSkillName,
    setRawResponseModalText,
    setRemoteThreadPicker,
    setReplyTarget,
    setSearchParams,
    setStartFromHereWarning,
    setTokenDiagOpen,
    skillCatalog,
    startFromHereWarning,
    summaries,
    toastError,
    tokenCount,
    tokenDiagOpen,
    toolCallsCount,
    userMessageCount,
  }

  const chatShellProps = {
    ChatBottomDock,
    ChatMessageList,
    ConsumerPills,
    DefaultLlmTip,
    RoleAgentTip,
    activeChatAgentId,
    agentKind,
    bubbleTheme,
    chatBottomDockProps,
    chatMessageListProps,
    composerInsetCustomProperty,
    composerInsetPx,
    dismissDefaultLlmTip,
    dismissRoleTip,
    getBubbleTheme,
    handleTranscriptScroll,
    ircGutterDragging,
    ircGutterPx,
    isCliAgent,
    isRemoteAgent,
    messagesEditable,
    onIrcRailDoubleClick,
    onIrcRailPointerDown,
    onIrcRailPointerMove,
    onIrcRailPointerUp,
    remoteFromUrl,
    scrollBoxRef,
    showDefaultLlmTip,
    showRoleTip,
    statusLabel,
    themeUsesIrcGutter,
  }

  return (
    <div className="os-chat flex h-full min-h-0 w-full flex-col">
      {/* #445: no `overflow-hidden` here. It clipped the routing flyout to the
          header's box (the flyout is an absolutely-positioned child of the
          picker inside this header), leaving only its first row reachable.
          Titles still clamp in `.os-navbar-identity-label`. */}
      <ChatHeader {...chatHeaderProps} />
      <ChatTranscriptShell {...chatShellProps} />
      <ChatOverlays {...chatOverlaysProps} />

    </div>
  )
}

export default ChatPage
