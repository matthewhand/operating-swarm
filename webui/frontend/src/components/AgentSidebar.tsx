import { RailSections } from './sidebar/RailSections'
import { createRowRenderers } from './sidebar/rowsRender'
import RailBulkBar from './RailBulkBar'
import {
  EMPTY_RAIL_SELECTION,
  selectRailRange,
  toggleRailSelection,
  type RailSelectionState,
} from '../features/sidebar/railSelection'
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Calendar,
  ChevronRight,
  EyeOff,
  Plug,
  Search,
  Server,
  Pin,
  PinOff,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import {
  UNREAD_CHANGED_EVENT,
  loadUnreadAgentIds,
  markAgentRead,
  markAgentUnread,
} from '../lib/unreadAgents'
import {
  fetchBlueprints,
  fetchCliAgents,
  fetchDesignedAgents,
  fetchHerdrAgents,
  fetchRemotes,
  terminateCliRun,
  type RouterDesign,
} from '../lib/api'
import {
  DYNAMIC_SUBAGENT_SPAWNED_EVENT,
  loadDynamicSubagents,
  type DynamicSubagent,
} from '../lib/dynamicSubagents'
import { useOptionalToast } from './DaisyUI'
import {
  CLI_PROCESS_STOPPED_TOAST,
  CLI_RUN_STATE_EVENT,
  cliRunStateFromEvent,
  notifyCliTerminated,
  peekCliRunning,
} from '../lib/cliRunState'
import {
  AGENT_ATTENTION_EVENT,
  NEEDS_APPROVAL_LABEL,
  approvalWaitFromEvent,
  peekApprovalWait,
} from '../lib/agentAttention'
import { useAgentTurns } from '../lib/agentTurns'
import AgentAvatar from './AgentAvatar'
import { remoteThemeFace } from './RemoteThemeFace'
import {
  agentRole,
  isChiefOfStaff,
  roleBadgeLabel,
  roleCssClass,
  roleFromAgent,
} from '../lib/agentRoles'
import { isNonCatalogRailPinId, railSeatAgents } from '../lib/railSeats'
import {
  HIDDEN_AGENTS_CHANGED_EVENT,
  hasHiddenAgentsStorage,
  hideAllAgentIds,
  loadHiddenAgentIds,
  loadOrSeedHiddenAgentIds,
  reconcileHiddenAgentIds,
} from '../lib/hiddenAgents'
import {
  defaultHostname,
  loadHostname,
  saveHostname,
  HOSTNAME_CHANGED_EVENT,
  dispatchHostnameChanged,
} from '../lib/hostname'
import {
  GENERATION_COMPLETE_EVENT,
  applyRailOrder,
  bumpRailIdToTop,
  generationCompleteAgentId,
  generationCompleteDetail,
  insertRailIdAfter,
  loadRailOrder,
  mergeRailOrder,
  moveRailId,
  moveRailIdAfter,
  peekRailDrag,
  saveRailOrder,
} from '../lib/railOrder'
import {
  FOCUS_AGENT_EVENT,
  NOTIFY_CHANGED_EVENT,
  chatHrefForRowId,
  loadNotifyAgentIds,
  maybeNotifyAgentTurn,
} from '../lib/agentNotifications'
import {
  BUMP_COMPLETED_EVENT,
  BUMP_SCOPE_EVENT,
  loadBumpCompleted,
  loadBumpScope,
  type BumpScope,
  saveHostnameOverride,
} from '../lib/settingsPrefs'
import {
  activeRailNavIndex,
  computeRailNavSequence,
  stepRailNav,
} from '../lib/railHotkeys'
// #1726: chat rows are DERIVED rail rows (an id that names the seat and the
// session), so they flow through the same order/section/menu machinery as
// every other row instead of a parallel list.
import {
  RAIL_CHAT_ROWS_EVENT,
  addRailChatRow,
  isRailChatRowId,
  loadRailChatRows,
  parseRailChatRowId,
  railChatRowId,
} from '../lib/railChatRows'
// #1740: Alt+Arrow reorder. `railReorderIntent` is the single gate for the
// gesture, mirroring the window navigation handler's guard so the two can
// never both claim a keypress. The pin-grid helpers describe Pinned as one
// more sibling scope, so a pinned tile reorders by the same rules.
import {
  RAIL_PIN_GRID_ID,
  movePinToAdjacentSection,
  moveToAdjacentSection,
  railReorderIntent,
  reorderWithinPinGrid,
  reorderWithinSection,
} from '../features/sidebar/railReorder'
import {
  PINNED_AGENTS_CHANGED_EVENT,
  excludePinnedFromList,
  hasPinnedAgentsStorage,
  loadOrSeedPinnedAgents,
  loadPinnedAgents,
  parseAgentDragPayload,
  savePinnedAgents,
  unpinAgent,
  type PinnedAgent,
} from '../lib/pinnedAgents'
import { hydrateRailPrefs, saveUserPrefs } from '../lib/userPrefs'
import {
  listAgentSessions,
  loadAllAgentSessions,
  SCALE_OUT_SESSIONS_EVENT,
  sessionHref,
  shouldOpenSessionPicker,
} from '../lib/scaleOutSessions'
import { agentLabel, defaultBlueprintId, isSupportAgent } from '../lib/supportAgent'
import { seatHasSessions } from '../lib/seatCapabilities'
import { AGENT_CHAT_SESSIONS_EVENT } from '../lib/agentChatSessions'
import {
  agentBubbleThemeOverrides,
  loadBubbleTheme,
} from '../lib/bubbleTheme'
import { formatRailTimestamp, getRowLastMessage } from '../lib/chatTime'
import { fetchTeamRosters, parseTeamRosters, teamHideId,   } from '../lib/teamRosters'
import {
  fetchConfiguredRemotes,
  remoteDisplayName,
  remoteHideId,
  type RemoteEntry,
} from '../lib/remotesCatalog'
import { emptyArray, emptyObject } from '../lib/stableEmpty'
import {
  activeCliRailAgentId,
  activeRailId,
  herdrRowIdFromParams,
  railSelectionFromParams,
} from '../lib/railActive'
import { configuredRemotes } from '../lib/remotes'
import { configuredCliNames, discoveredCliNames } from '../lib/cliAgents'
import RemoteSessionsPopup from './RemoteSessionsPopup'
import UpdateChrome from './UpdateChrome'
import {
  CHAT_CONNECTION_EVENT,
  getChatConnection,
  type ChatConnectionStatus,
} from '../lib/chatConnection'
import {
  markStackWorking,
  orderedFacesByRecency,
  railTeamStackLayout,
  teamChatFaceStack,
  teamSidepaneStack,
} from '../lib/avatarStack'
import {
  defaultSessionForRemote,
  defaultSessionForTeam,
  sessionsForRemote,
  sessionsForTeam,
  shouldShowSelectAgent,
  stackFacesForRemote,
  stackFacesForTeam,
} from '../lib/sessionPicker'
import {
  AGENT_SETTINGS_CHANGED_EVENT,
  loadLocalNewChatPerTask,
} from '../lib/agentSettings'
import {
  REMOTE_HEALTH_CHANGED_EVENT,
  isRemoteOffline,
  startRemoteHealthPolling,
  stopRemoteHealthPolling,
} from '../lib/remoteHealth' // #1196
import { stopTrackingSeatHealth, trackSeatHealth, type SeatRef } from '../lib/seatHealth' // #1658
import {
  AGENT_CONVERSATION_EVENT,
  activeTaskSessionCount,
  agentChatHref,
  setConversationIdForAgent,
} from '../lib/agentChat'
import {
  copyableConversationId,
  paneMenuItems,
  railMenuItems,
  sectionMenuItems,
  type RailMenuItemId,
} from '../lib/railContextMenu'
import {
  isAutoSectionId,
  isUnassignedSection,
  loadRailSections,
  moveAgentToSection,
  railMoveToDestinations,
  railSectionsHasContent,
  partitionRowsBySection,
  sectionIdForAgent,
  toggleSectionCollapsed,
  toggleSectionInternalOnly,
  UNASSIGNED_SECTION_ID,
  type RailSectionsState,
} from '../lib/railSections'
import {
  isRailIdDeleted,
  loadDeletedRailIds,
} from '../lib/deletedRailIds'
import { openSearchPalette, type HiddenRailRow } from './searchPaletteKernel'
import { isMacPlatform, searchShortcutLabel } from '../lib/keybindingTips'
import {
  AGENT_EDITS_CHANGED_EVENT,
} from '../lib/agentEdits'
import { AGENT_PROFILE_CHANGED_EVENT } from '../lib/agentProfile'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import { declaredRosterForTeam,   } from '../lib/declaredRoster'
import PersonaRoster from './PersonaRoster'
import {
  fetchCliSessions,
  latestCliActivityMs,
} from '../lib/cliSessions'
import {
  hopContinueTargets,
} from '../lib/cliSessionHop'
import { FALLBACK_CLIS } from '../lib/chatStatus'
import { OPEN_TEAM_COMPOSER_EVENT, TEAM_CREATED_EVENT } from './teamComposerKernel'
import { openSettingsSheet } from './settings/kernel'
import { OPEN_PLUGINS_EVENT } from '../lib/chromeOverlay'
import { useCurrentAgent, isSwarmOwnedSeat } from '../lib/currentAgent'
import RailContextMenu from './RailContextMenu'
import RailSectionHeader, { RailSectionEmpty } from './RailSectionHeader'
import StackedAvatars from './StackedAvatars'
import GroupAvatar from './GroupAvatar'
import {
  MIN_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  COLLAPSED_RAIL_WIDTH,
} from '../lib/railResize'
import { SidebarConcealButton, SidebarExpandButton } from './SidepaneConceal'
import RailRowSlot from './RailRowSlot'

// #856 slice 3: module-scope rail-row surface moved verbatim to
// features/sidebar/rows.ts; re-imported here so the component body and the
// './AgentSidebar' import surface are unchanged.
import {
  API_ONLY_REASON,
  EMPTY_BLUEPRINTS,
  type AgentSidebarProps,
  type CliPickerState,
  type ContextMenuState,
  type NotifyOutcomeHint,
  type PickerState,
  type RailRow,
  type SectionMenuState,
  type SessionPickerState,
  type SidebarAgent,
  isApiRailAgent,
  isBlueprintRailAgent,
  isCliRailAgent,
  isHerdrAgent,
  isRemoteRailAgent,
  sidebarHref,
  toSidebarCli,
  toSidebarCliName,
  toSidebarDynamic,
  toSidebarHerdr,
} from '../features/sidebar/rows'
import { useRailRowOps } from '../features/sidebar/useRailRowOps'
import { railMenuKindForRow, useRailMenuOpeners } from '../features/sidebar/useRailMenuOpeners'
import { useRailDragCommands } from '../features/sidebar/useRailDragCommands'
import { useRailMenuCommands } from '../features/sidebar/useRailMenuCommands'
import { useRailSessionCommands } from '../features/sidebar/useRailSessionCommands'
import { useRailReveal } from '../features/sidebar/useRailReveal'
import { sideAwarePopupAlign } from '../lib/railSide'
import { useRailResize } from './sidebar/useRailResize'
import type { AgentKind } from './AddAgentWizard'
import AddBotMenu from './AddBotMenu'
import { RailOverlays } from './sidebar/RailOverlays'

const AgentCalendarView = lazy(() => import('./AgentCalendarView'))
const SessionPicker = lazy(() => import('./SessionPicker'))
const CliSessionPicker = lazy(() => import('./CliSessionPicker'))
const PluginsPopup = lazy(() => import('./PluginsPopup'))

export const OPEN_CALENDAR_EVENT = 'open-calendar-view'
/**
 * #1784 — how many CLI session reads the rail-activity fan-out keeps in flight.
 *
 * One per CLI rail row, so a busy host queues twenty-plus of them the instant
 * the query key settles. They all go through `apiGet`, which inherits
 * `pacedApiGet`'s shared `MAX_CONCURRENT_GETS = 4` gate — but that gate PACES a
 * burst, it does not reduce the request COUNT, so the rail's own reads occupy
 * every slot and the rest of the cold mount queues behind them. Two-wide keeps
 * the activity timestamps arriving without monopolising the gate.
 */
const CLI_ACTIVITY_READ_WIDTH = 2
export default function AgentSidebar({
  open = false,
  narrow = false,
  onClose,
  onPick,
  onOpenSearch,
  blueprints: propBlueprints,
  tabletDocked = false,
  onToggleTabletDock,
}: AgentSidebarProps) {
  const [dynamicSubagents, setDynamicSubagents] = useState<DynamicSubagent[]>(() =>
    loadDynamicSubagents(),
  )
  const [subagentsCollapsed, setSubagentsCollapsed] = useState(false)
  const [cliCollapsed, setCliCollapsed] = useState(false)
  const [remoteCollapsed, setRemoteCollapsed] = useState(false)
  const [apiCollapsed, setApiCollapsed] = useState(false)
  const [osCollapsed, setOsCollapsed] = useState(false)

  useEffect(() => {
    const onSpawned = () => {
      setDynamicSubagents(loadDynamicSubagents())
    }
    window.addEventListener(DYNAMIC_SUBAGENT_SPAWNED_EVENT, onSpawned)
    return () => window.removeEventListener(DYNAMIC_SUBAGENT_SPAWNED_EVENT, onSpawned)
  }, [])
  const pickOrClose = onPick ?? onClose
  const drawerHidden = Boolean(narrow && !open)
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const onChat = pathname.startsWith('/chat') || pathname === '/'
  const selectedTeamId = onChat ? (searchParams.get('team') ?? '') : ''
  const selectedRemoteId = onChat ? (searchParams.get('remote') ?? '') : ''
  const selectedId = defaultBlueprintId(onChat ? searchParams.get('blueprint') : '')
  // #542: the rail's active state comes from the URL, not from `selectedId`
  // (which team/remote scopes used to blank out, so those pins could never
  // light up). `activeRail` carries the `team:` / `remote:` id shape the pins
  // and rows are stored under.
  // #1726: the session the URL names, if any. A chat row is the row the pane
  // is showing when this matches its own session, which is also why the seat
  // row stands down — the URL names a seat, but the operator is in a chat.
  const activeSessionId = onChat ? (searchParams.get('session') ?? '').trim() : ''
  const activeRail = onChat ? activeRailId(railSelectionFromParams(searchParams)) : ''
  // #543: when the chat targets a herdr agent, that row is the active one.
  const activeHerdrRow = onChat ? herdrRowIdFromParams(searchParams) : ''
  // A `?blueprint=cli_agent&cli=<cli>` URL names a derived `<cli>_agent` row;
  // `activeRail` alone would only light the generic `cli_agent` seat.
  const activeCliRail = onChat ? activeCliRailAgentId(searchParams) : ''
  const [hiddenIds, setHiddenIds] = useState<string[] | null>(() =>
    hasHiddenAgentsStorage() ? loadHiddenAgentIds() : null,
  )
  const [deletedIds, setDeletedIds] = useState<string[]>(() => loadDeletedRailIds())
  const [deleteConfirm, setDeleteConfirm] = useState<ContextMenuState | null>(null)
  const [pins, setPins] = useState<PinnedAgent[]>(() => loadOrSeedPinnedAgents())
  const [hoveringHidden, setHoveringHidden] = useState(false)
  const [pluginsOpen, setPluginsOpen] = useState(false)
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [remotesPopupOpen, setRemotesPopupOpen] = useState(false)
  const [localWsStatus, setLocalWsStatus] = useState<ChatConnectionStatus>(() => getChatConnection())
  const [cliRunningIds, setCliRunningIds] = useState<Set<string>>(() => new Set())
  const [approvalWaitIds, setApprovalWaitIds] = useState<Set<string>>(() => new Set())
  const agentTurns = useAgentTurns()
  const toast = useOptionalToast()

  // REQ-912 (#511): Plugins and Calendar only work for swarm-run seats. The
  // selected seat is published by ChatPage (see lib/currentAgent.ts); the
  // signal is reactive so switching seats re-evaluates the gate without a
  // remount. Unknown/unresolved selection stays ENABLED (issue §6) so a
  // transient load state cannot lock the operator out. Teams is not gated.
  const currentAgent = useCurrentAgent()
  const pluginsCalendarSupported = currentAgent === null || isSwarmOwnedSeat(currentAgent)
  const openPlugins = useCallback(() => {
    if (!pluginsCalendarSupported) return
    setPluginsOpen(true)
  }, [pluginsCalendarSupported])
  const openCalendar = useCallback(() => {
    if (!pluginsCalendarSupported) return
    setCalendarOpen(true)
  }, [pluginsCalendarSupported])

  useEffect(() => {
    const onOpenCalendar = () => openCalendar()
    window.addEventListener(OPEN_CALENDAR_EVENT, onOpenCalendar)
    return () => window.removeEventListener(OPEN_CALENDAR_EVENT, onOpenCalendar)
  }, [openCalendar])

  useEffect(() => {
    const onRunState = (event: Event) => {
      const detail = cliRunStateFromEvent(event)
      if (!detail) return
      setCliRunningIds((current) => {
        const next = new Set(current)
        if (detail.running) next.add(detail.agentId)
        else next.delete(detail.agentId)
        return next
      })
    }
    window.addEventListener(CLI_RUN_STATE_EVENT, onRunState)
    return () => window.removeEventListener(CLI_RUN_STATE_EVENT, onRunState)
  }, [])

  useEffect(() => {
    const onAttention = (event: Event) => {
      const detail = approvalWaitFromEvent(event)
      if (!detail) return
      setApprovalWaitIds((current) => {
        // Plain tool_status frames emit `waiting: false` for tools that never
        // waited, and they arrive continuously — bail out so the rail is not
        // re-rendered on every one of them.
        if (current.has(detail.agentId) === detail.waiting) return current
        const next = new Set(current)
        if (detail.waiting) next.add(detail.agentId)
        else next.delete(detail.agentId)
        return next
      })
    }
    window.addEventListener(AGENT_ATTENTION_EVENT, onAttention)
    return () => window.removeEventListener(AGENT_ATTENTION_EVENT, onAttention)
  }, [])

  useEffect(() => {
    const handleStatus = (event: Event) => {
      const customEvent = event as CustomEvent<ChatConnectionStatus>
      if (customEvent.detail) {
        setLocalWsStatus(customEvent.detail)
      }
    }
    window.addEventListener(CHAT_CONNECTION_EVENT, handleStatus)
    return () => {
      window.removeEventListener(CHAT_CONNECTION_EVENT, handleStatus)
    }
  }, [])

  useEffect(() => {
    const onHostnameChanged = (event: Event) => {
      const custom = event as CustomEvent<{ hostname?: string }>
      const updated = custom.detail?.hostname
      if (typeof updated === 'string') {
        setHostname(updated || defaultHostname())
      } else {
        setHostname(loadHostname())
      }
    }
    window.addEventListener(HOSTNAME_CHANGED_EVENT, onHostnameChanged)
    return () => window.removeEventListener(HOSTNAME_CHANGED_EVENT, onHostnameChanged)
  }, [])

  useEffect(() => {
    const onOpenPlugins = () => openPlugins()
    window.addEventListener(OPEN_PLUGINS_EVENT, onOpenPlugins)
    return () => window.removeEventListener(OPEN_PLUGINS_EVENT, onOpenPlugins)
  }, [openPlugins])

  const localWsDown = localWsStatus === 'closed' || localWsStatus === 'failed'
  const [hostname, setHostname] = useState(() => loadHostname())
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [sectionMenu, setSectionMenu] = useState<SectionMenuState | null>(null)
  const [paneMenu, setPaneMenu] = useState<{ x: number; y: number } | null>(null)
  const [sectionState, setSectionState] = useState<RailSectionsState>(() => loadRailSections())
  const [editingSectionId, setEditingSectionId] = useState<string | null>(null)
  const [editingSectionName, setEditingSectionName] = useState('')
  const [sectionDropId, setSectionDropId] = useState<string | null>(null)
  const [settingsTick, setSettingsTick] = useState(0)
  const [dropActive, setDropActive] = useState(false)
  const [listDropActive, setListDropActive] = useState(false)
  const [hideDropActive, setHideDropActive] = useState(false)
  const [binDragOver, setBinDragOver] = useState(false)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [picker, setPicker] = useState<PickerState | null>(null)
  const [, setEditsTick] = useState(0)
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)
  const [railOrder, setRailOrder] = useState<string[]>(() => loadRailOrder())
  const [bumpCompleted, setBumpCompleted] = useState(() => loadBumpCompleted())
  const [bumpScope, setBumpScope] = useState<BumpScope>(() => loadBumpScope())
  const [sessionTick, setSessionTick] = useState(0)
  // #1726: bumped by the chat-row store's own event, so a chat created from
  // the row menu ("New session") and one created from "+ Add bot" land in the
  // sidepane through the SAME tick — that is what makes the two paths one.
  const [chatRowTick, setChatRowTick] = useState(0)
  const [sessionPicker, setSessionPicker] = useState<SessionPickerState | null>(null)
  const [cliPicker, setCliPicker] = useState<CliPickerState | null>(null)
  const menuRef = useRef<HTMLUListElement | null>(null)
  const longPressRef = useRef<{ timer: number | null; opened: boolean }>({
    timer: null,
    opened: false,
  })
  const hideDropDepth = useRef(0)
  const prefsHydrated = useRef(false)
  const skipPrefsSave = useRef(true)
  const [prefsReady, setPrefsReady] = useState(false)
  const isMac = isMacPlatform()
  const searchShortcut = searchShortcutLabel()
  const [addWizardOpen, setAddWizardOpen] = useState(false)
  const sessionsByAgent = useMemo(() => loadAllAgentSessions(), [sessionTick])
  // #1726: the chat rows the sidepane shows. `sessionTick` re-reads the
  // scale-out cache, so this reads the same store and the same tick — a chat
  // created in one surface cannot appear in the rail before it appears in the
  // picker.
  const chatRows = useMemo(() => loadRailChatRows(), [sessionTick, chatRowTick])
  const [unreadIds, setUnreadIds] = useState<string[]>(() => loadUnreadAgentIds())
  const [notifyIds, setNotifyIds] = useState<string[]>(() => loadNotifyAgentIds())
  // #546: the *outcome*, not a boolean. `permission !== 'granted'` collapsed
  // "blocked", "never asked" and "no API here" into one message that was only
  // correct for the first.
  const [notifyHint, setNotifyHint] = useState<NotifyOutcomeHint | null>(null)
  const currentTargetId = selectedTeamId || selectedRemoteId || selectedId
  const prevTargetRef = useRef(currentTargetId)

  useEffect(() => {
    const onNotifyChange = () => {
      setNotifyIds(loadNotifyAgentIds())
    }
    window.addEventListener(NOTIFY_CHANGED_EVENT, onNotifyChange)
    return () => window.removeEventListener(NOTIFY_CHANGED_EVENT, onNotifyChange)
  }, [])

  useEffect(() => {
    if (!notifyHint) return
    // #546: `never-asked` and `unsupported` carry an action (try again, or the
    // real reason), so they get longer on screen than the old 6s denial toast.
    const ttl = notifyHint.outcome === 'denied' ? 6000 : 15000
    const timer = window.setTimeout(() => setNotifyHint(null), ttl)
    return () => window.clearTimeout(timer)
  }, [notifyHint])

  useEffect(() => {
    const onFocusAgent = (event: Event) => {
      const agentId = (event as CustomEvent<{ agentId?: string }>).detail?.agentId
      if (!agentId) return
      navigate(chatHrefForRowId(agentId))
      onClose?.()
    }
    window.addEventListener(FOCUS_AGENT_EVENT, onFocusAgent)
    return () => window.removeEventListener(FOCUS_AGENT_EVENT, onFocusAgent)
  }, [navigate, onClose])

  useEffect(() => {
    const onUnreadChange = () => {
      setUnreadIds(loadUnreadAgentIds())
    }
    window.addEventListener(UNREAD_CHANGED_EVENT, onUnreadChange)
    window.addEventListener('storage', onUnreadChange)
    return () => {
      window.removeEventListener(UNREAD_CHANGED_EVENT, onUnreadChange)
      window.removeEventListener('storage', onUnreadChange)
    }
  }, [])

  useEffect(() => {
    if (currentTargetId && currentTargetId !== prevTargetRef.current) {
      prevTargetRef.current = currentTargetId
    }
  }, [currentTargetId])

  // #856 slice C: resize/dock state machine moved to sidebar/useRailResize.
  // #1683: `pins` is the rail's own canonical pinned-agents state (the same
  // list RailSections renders the pinned tile grid from), so the resize hook
  // reads the pin count from here rather than from a second source. It is the
  // conservative half of the truth: a pin that is currently hidden or deleted
  // renders no tile but still keeps the column detents, which can only make a
  // drag stiffer than it needs to be, never wobblier.
  const {
    railSide,
    railWidth,
    isResizing,
    isAvatarOnly,
    isCollapsed,
    concealSidebar,
    expandSidebar,
    handleResizeStart,
    handleResizeKeyDown,
  } = useRailResize({ narrow, onClose, pinnedCount: pins.length })
  useEffect(() => {
    // #1726: the chat-row store announces its own writes (it is written from
    // two surfaces — the row menu's "New session" and "+ Add bot"), so the
    // sidepane has one subscription rather than two call-sites guessing when
    // to re-read.
    const onChatRowsChange = () => setChatRowTick((n) => n + 1)
    window.addEventListener(RAIL_CHAT_ROWS_EVENT, onChatRowsChange)
    return () => window.removeEventListener(RAIL_CHAT_ROWS_EVENT, onChatRowsChange)
  }, [])

  useEffect(() => {
    const onChange = () => {
      setSessionTick((n) => n + 1)
      // #507: any same-tab write to the canonical hidden-id store dispatches
      // HIDDEN_AGENTS_CHANGED_EVENT (the DOM `storage` event only fires in
      // *other* documents, never the tab that wrote). The `storage` listener
      // below is kept for cross-tab writes only.
      if (hasHiddenAgentsStorage()) {
        // Change-guarded: a stale echo must not dirty state (the store's own
        // write already notified it synchronously before this guard existed).
        const next = loadHiddenAgentIds()
        setHiddenIds((current) =>
          JSON.stringify(current ?? []) === JSON.stringify(next) ? current : next,
        )
      }
      // #1217: cross-tab / same-tab storage synchronization for pinned agents
      if (hasPinnedAgentsStorage()) {
        const nextPins = loadPinnedAgents()
        setPins((current) => {
          if (JSON.stringify(current) === JSON.stringify(nextPins)) return current
          skipPrefsSave.current = true
          return nextPins
        })
      }
    }
    window.addEventListener(SCALE_OUT_SESSIONS_EVENT, onChange)
    window.addEventListener(AGENT_CHAT_SESSIONS_EVENT, onChange)
    window.addEventListener(AGENT_CONVERSATION_EVENT, onChange)
    window.addEventListener(GENERATION_COMPLETE_EVENT, onChange)
    window.addEventListener(HIDDEN_AGENTS_CHANGED_EVENT, onChange)
    window.addEventListener(PINNED_AGENTS_CHANGED_EVENT, onChange)
    window.addEventListener('storage', onChange)
    return () => {
      window.removeEventListener(SCALE_OUT_SESSIONS_EVENT, onChange)
      window.removeEventListener(AGENT_CHAT_SESSIONS_EVENT, onChange)
      window.removeEventListener(AGENT_CONVERSATION_EVENT, onChange)
      window.removeEventListener(GENERATION_COMPLETE_EVENT, onChange)
      window.removeEventListener(HIDDEN_AGENTS_CHANGED_EVENT, onChange)
      window.removeEventListener(PINNED_AGENTS_CHANGED_EVENT, onChange)
      window.removeEventListener('storage', onChange)
    }
  }, [])

  useEffect(() => {
    const onEdits = () => setEditsTick((tick) => tick + 1)
    window.addEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
    window.addEventListener(AGENT_PROFILE_CHANGED_EVENT, onEdits)
    window.addEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
    return () => {
      window.removeEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
      window.removeEventListener(AGENT_PROFILE_CHANGED_EVENT, onEdits)
      window.removeEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
    }
  }, [])

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    retry: 1,
  })
  const teamsQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
    retry: 1,
  })
  const herdrQuery = useQuery({
    queryKey: ['herdr-agents'],
    queryFn: fetchHerdrAgents,
    retry: 1,
  })
  const remotesQuery = useQuery({
    queryKey: ['configured-remotes'],
    queryFn: fetchConfiguredRemotes,
    retry: 1,
  })
  const fullRemotesQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    // #726: remotes change infrequently — share the 60s cache with ChatPage
    staleTime: 60_000,
  })
  const configuredRemotesList = useMemo(
    () => configuredRemotes(fullRemotesQuery.data),
    [fullRemotesQuery.data],
  )
  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    // #726: shares the same queryKey as ChatPage — coalesced, 60s fresh
    staleTime: 60_000,
  })
  // Designer-created Agent Router agents (router_designs.json). Fast feed —
  // /v1/agents/ would init the router blueprint (~55s) just to list them.
  const designsQuery = useQuery({
    queryKey: ['router-designs'],
    queryFn: fetchDesignedAgents,
    retry: 1,
    staleTime: 60 * 1000,
  })
  const designedAgents = useMemo<SidebarAgent[]>(
    () =>
      (designsQuery.data?.data ?? [])
        .filter((design: RouterDesign) => typeof design?.agent_id === 'string' && design.agent_id)
        .map((design: RouterDesign) => ({
          id: design.agent_id,
          object: 'blueprint' as const,
          name: design.name || design.agent_id,
          description: design.description || design.specialty || 'Designer-created agent.',
          abbreviation: null,
          required_mcp_servers: [],
          tags: [design.kind],
          installed: true,
          compiled: true,
          cli:
            typeof design.cli === 'string' && design.cli.trim()
              ? design.cli.trim()
              : null,
          kind: 'design' as const,
        })),
    [designsQuery.data],
  )
  const catalog = propBlueprints ?? blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS
  // `?? []` here would allocate a fresh array every render while the query is
  // empty, and `parseTeamRosters` returns fresh objects besides — so `teams`
  // would miss every memo and re-run every effect that lists it. Keyed on the
  // query data, which is the thing that actually changes.
  const teams = useMemo(() => parseTeamRosters(teamsQuery.data), [teamsQuery.data])
  const remotes = useMemo(
    () => remotesQuery.data ?? emptyArray<RemoteEntry>(),
    [remotesQuery.data],
  )
  const agents = useMemo<SidebarAgent[]>(() => {
    const fromBlueprints = railSeatAgents(catalog)
    const seen = new Set(fromBlueprints.map((a) => a.id))
    const fromRosters: SidebarAgent[] = []
    for (const roster of teams) {
      for (const member of roster.members) {
        if (member.kind === 'team' || seen.has(member.id)) continue
        if (!isChiefOfStaff(member.role) && member.id !== 'cos') continue
        seen.add(member.id)
        fromRosters.push({
          id: member.id,
          object: 'blueprint',
          name:
            (member.name && member.name.trim()) ||
            (member.id === 'cos' ? 'Chief of Staff' : member.id),
          description: 'Talks to any available team.',
          abbreviation: 'CoS',
          required_mcp_servers: [],
          tags: [],
          installed: true,
          compiled: true,
          role: 'chief_of_staff',
          rail: true,
        })
      }
    }
    const herdr = (herdrQuery.data?.data ?? []).map(toSidebarHerdr)
    const named = (cliQuery.data?.rail ?? []).map(toSidebarCli)
    // One row per discovered/configured CLI the wire rail does not already
    // name. The generic `cli_agent`/`api_agent` rows are skipped as coverage
    // sources (their `cli` is only a default pick), so a dedicated row is
    // still derived for the default CLI.
    const railCliCovered = new Set<string>()
    for (const row of cliQuery.data?.rail ?? []) {
      if (row.id === 'cli_agent') continue
      const nm = String(row.name ?? '').trim()
      if (nm) railCliCovered.add(nm)
      const c = String(row.cli ?? '').trim()
      if (c) railCliCovered.add(c)
    }
    const derivedCliNames = [
      ...new Set([...discoveredCliNames(cliQuery.data), ...configuredCliNames(cliQuery.data)]),
    ]
      .map((name) => name.trim())
      .filter((name) => name && !railCliCovered.has(name))
      .sort((a, b) => a.localeCompare(b))
    const derivedCli = derivedCliNames.map(toSidebarCliName)
    const namedIds = new Set([...named, ...derivedCli].map((a) => a.id))
    const fromBlueprintsNoCli = fromBlueprints.filter((a) => !namedIds.has(a.id) && a.id !== 'api_agent')
    // Designed (router) agents join the rail; skip ids a live row already owns.
    const designed = designedAgents.filter((a) => !seen.has(a.id) && !namedIds.has(a.id))
    const dynamicSidebar = dynamicSubagents.map(toSidebarDynamic)
    const list = [
      ...fromRosters,
      ...fromBlueprintsNoCli,
      ...herdr,
      ...designed,
      ...dynamicSidebar.filter((a) => !seen.has(a.id) && !namedIds.has(a.id)),
    ]
    const support = list.filter((a) => isSupportAgent(a))
    // Named api_agent comes from /v1/cli-agents/. Add-agent API customs stay
    // in the catalog with rail+kind and must not be dropped here (REQ-171B).
    const catalogApi = list.filter(
      (a) => (isApiRailAgent(a) || isBlueprintRailAgent(a)) && !isSupportAgent(a),
    )
    const rest = list.filter((a) => !isSupportAgent(a) && !isApiRailAgent(a))
    const merged = [...support, ...named, ...derivedCli, ...catalogApi, ...rest]
    const railRank = (a: SidebarAgent) => {
      if (isSupportAgent(a)) return 0
      if (isCliRailAgent(a)) return 1
      if (a.kind === 'design') return 2
      if (isApiRailAgent(a) || isBlueprintRailAgent(a)) return 2
      if (isChiefOfStaff(roleFromAgent(a))) return 3
      if (a.kind === 'subagent') return 5
      return 4
    }
    return merged.sort((a, b) => railRank(a) - railRank(b))
  }, [catalog, cliQuery.data, herdrQuery.data, teams, designedAgents, dynamicSubagents])
  const cliAgentsForActivity = useMemo(
    () =>
      agents
        .filter((a) => a.kind === 'cli' && typeof a.cli === 'string' && a.cli.length > 0)
        .map((a) => ({ id: a.id, cli: a.cli as string })),
    [agents],
  )
  const cliActivityQuery = useQuery({
    queryKey: [
      'cli-rail-activity',
      cliAgentsForActivity.map((a) => `${a.id}:${a.cli}`).join('|'),
    ],
    queryFn: async () => {
      const out: Record<string, number> = {}
      // #1784: read the seats two at a time instead of all at once, writing into
      // the same `out` record. The per-seat try/catch is unchanged, so a failure
      // is still an honest gap (the row shows no timestamp) rather than a
      // rejection that loses the whole map. Deliberately no `delay()` between
      // windows: that would only trade the burst for a slow rail.
      for (let i = 0; i < cliAgentsForActivity.length; i += CLI_ACTIVITY_READ_WIDTH) {
        const window = cliAgentsForActivity.slice(i, i + CLI_ACTIVITY_READ_WIDTH)
        await Promise.all(
          window.map(async ({ id, cli }) => {
            try {
              const ms = latestCliActivityMs(await fetchCliSessions(id, cli))
              if (ms != null) out[id] = ms
            } catch {
              /* honest gap: row simply shows no timestamp */
            }
          }),
        )
      }
      return out
    },
    enabled: cliAgentsForActivity.length > 0,
    staleTime: 5 * 60 * 1000,
  })
  const cliActivityByAgent = useMemo(
    () => cliActivityQuery.data ?? emptyObject<Record<string, number>>(),
    [cliActivityQuery.data],
  )
  const rosterById = useMemo(() => new Map(teams.map((r) => [r.id, r])), [teams])
  const childTeamIds = useMemo(() => {
    const ids = new Set<string>()
    for (const team of teams) {
      for (const member of team.members) {
        if (member.kind === 'team') ids.add(member.team_id || member.id)
      }
    }
    return ids
  }, [teams])
  const rootTeams = useMemo(
    () => teams.filter((team) => !childTeamIds.has(team.id)),
    [teams, childTeamIds],
  )
  const liveRowIds = useMemo(() => {
    const ids = new Set<string>()
    for (const agent of agents) ids.add(agent.id)
    for (const team of teams) {
      ids.add(teamHideId(team.id))
      ids.add(team.id)
    }
    for (const remote of remotes) {
      ids.add(remoteHideId(remote.id))
      ids.add(remote.id)
    }
    return ids
  }, [agents, teams, remotes])
  // #170: reconcile stale hide ids against the live rail (teams/agents/remotes
  // that no longer exist) so old server prefs can't keep rows hidden forever.
  // Pinned ids stay hideable. Skip reconciliation until ALL rail feeds
  // (blueprints, rosters, remotes, cli, herdr) settle so a mid-load drop can
  // neither flash rows visible nor persist a trimmed hide list to prefs.
  const railDataPending =
    !propBlueprints &&
    (blueprintsQuery.isPending ||
      teamsQuery.isPending ||
      remotesQuery.isPending ||
      cliQuery.isPending ||
      herdrQuery.isPending ||
      designsQuery.isPending)
  // `?? []` and `reconcileHiddenAgentIds` (a `filter`) both allocate a fresh
  // array per render, and this is in the dep list of ~15 memos/callbacks/effects
  // — including the two health polls, so the churn reached the network. Memoized
  // on the things that decide its contents; `pins` only contributes ids, so its
  // own array identity must not be a key or the memo would never hit.
  const resolvedPinnedIds = useMemo(() => pins.map((pin) => pin.id), [pins])
  const resolvedHiddenIds = useMemo(
    () =>
      railDataPending
        ? (hiddenIds ?? emptyArray<string>())
        : reconcileHiddenAgentIds(
            hiddenIds ?? loadOrSeedHiddenAgentIds(agents),
            liveRowIds,
            resolvedPinnedIds,
          ),
    [railDataPending, hiddenIds, agents, liveRowIds, resolvedPinnedIds],
  )

  useEffect(() => {
    if (hiddenIds !== null || blueprintsQuery.isPending) return
    setHiddenIds(loadOrSeedHiddenAgentIds(agents))
  }, [hiddenIds, blueprintsQuery.isPending, agents])

  /* #1705 — Ctrl/Shift multi-select with a visible outcome.
   *
   * The gesture model is the documented one (click = single, Ctrl/Cmd+click =
   * toggle, Shift+click = contiguous range from the anchor, Escape = clear,
   * Space = toggle from the keyboard); the RANGE order is read back from the
   * rendered DOM so "contiguous" means what the operator sees between the
   * anchor and the target — section grouping and seat kind included — rather
   * than a second ordering that could drift from the list. */
  const [multiSelection, setMultiSelection] = useState<RailSelectionState>(
    EMPTY_RAIL_SELECTION,
  )
  const railRootRef = useRef<HTMLElement | null>(null)
  const railSelectableOrder = useCallback(() => {
    const root = railRootRef.current
    if (!root) return [] as string[]
    // Only the row roots: the pinned-tile grid and the per-row avatar glyphs
    // carry `data-agent-id` too and are not part of this selection.
    return Array.from(root.querySelectorAll('.os-agent-row[data-agent-id]'))
      .map((node) => node.getAttribute('data-agent-id') || '')
      .filter((id) => id.length > 0)
  }, [])
  const isRailRowSelected = useCallback(
    (id: string) => multiSelection.ids.includes(id),
    [multiSelection.ids],
  )
  const isRailRowSelectable = useCallback((id: string) => Boolean(id), [])
  const toggleRailRowSelection = useCallback((id: string) => {
    setMultiSelection((current) => toggleRailSelection(current, id))
  }, [])
  const selectRailRowRange = useCallback(
    (id: string) => {
      const order = railSelectableOrder()
      setMultiSelection((current) => selectRailRange(current, id, order))
    },
    [railSelectableOrder],
  )
  const clearMultiSelection = useCallback(() => setMultiSelection(EMPTY_RAIL_SELECTION), [])
  /* Escape clears wherever focus is. Capture phase, so a pane that stops
     propagation on Escape cannot swallow it, and never while the operator is
     typing (a form field owns Escape there). */
  useEffect(() => {
    if (multiSelection.ids.length === 0) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.isContentEditable ||
          ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
      ) {
        return
      }
      event.preventDefault()
      setMultiSelection(EMPTY_RAIL_SELECTION)
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [multiSelection.ids.length])

  /* Bulk actions. Both reuse the SAME store writers the per-row context menu
     uses, so a bulk edit lands in localStorage through one code path — and the
     rail's existing debounced `flushPrefsSave` then PATCHes the same
     `favourites` / `hidden_agents` arrays to /v1/preferences/, which is how a
     single-row hide/pin already syncs. There is no separate bulk route. */
  const bulkHideSelected = useCallback(() => {
    const ids = multiSelection.ids
    if (ids.length < 1) return
    setHiddenIds((current) => hideAllAgentIds([...(current ?? resolvedHiddenIds), ...ids]))
    setMultiSelection(EMPTY_RAIL_SELECTION)
  }, [multiSelection.ids, resolvedHiddenIds, setHiddenIds])
  const bulkUnpinSelected = useCallback(() => {
    const ids = multiSelection.ids
    if (ids.length < 1) return
    const doomed = new Set(ids)
    setPins((current) => {
      const next = current.filter((pin) => !doomed.has(pin.id))
      if (next.length === current.length) return current
      savePinnedAgents(next)
      return next
    })
    setMultiSelection(EMPTY_RAIL_SELECTION)
  }, [multiSelection.ids, setPins])
  const bulkHiddenCount = useMemo(
    () => multiSelection.ids.filter((id) => resolvedHiddenIds.includes(id)).length,
    [multiSelection.ids, resolvedHiddenIds],
  )
  const bulkPinnedCount = useMemo(
    () => multiSelection.ids.filter((id) => pins.some((pin) => pin.id === id)).length,
    [multiSelection.ids, pins],
  )

  useEffect(() => {
    if (prefsHydrated.current || blueprintsQuery.isPending) return
    let cancelled = false
    void hydrateRailPrefs(agents).then((next) => {
      if (cancelled) return
      prefsHydrated.current = true
      skipPrefsSave.current = true
      setPins(next.pins)
      setHiddenIds(next.hidden)
      setHostname(next.hostnameOverride || defaultHostname())
      // #786: the server bag wins when it actually defines a layout; an
      // empty server default never clobbers this browser's local sections —
      // the debounced sync below pushes the local bag up instead.
      if (railSectionsHasContent(next.sections)) {
        setSectionState(next.sections as RailSectionsState)
      }
      setPrefsReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [blueprintsQuery.isPending, agents])

  // #1041: content-addressed save guard. Two identities conspired into a
  // PATCH write-loop (~2.4/s → anon 429s): reconcileHiddenAgentIds() hands
  // this effect a fresh array every render, and each PATCH response is
  // echoed back via applyPrefsToLocal() → state churn → effect refires.
  // The signature is taken INSIDE the debounce so identity churn from
  // re-renders never cancels a legitimate pending save, and an echoed bag
  // (identical content) never re-saves.
  const lastPrefsSignature = useRef('')
  const pendingPrefsTimer = useRef<number | null>(null)

  const flushPrefsSave = useCallback(() => {
    if (!prefsReady) return
    const override =
      hostname.trim() === defaultHostname() ? '' : hostname.trim()
    const signature = JSON.stringify([pins, resolvedHiddenIds, override, sectionState])
    if (signature === lastPrefsSignature.current) return
    lastPrefsSignature.current = signature
    void saveUserPrefs({
      favourites: pins,
      hidden_agents: resolvedHiddenIds,
      hostname_override: override,
      // #786: sidepane layout syncs with the same debounce.
      rail_sections: sectionState,
    })
  }, [pins, resolvedHiddenIds, hostname, sectionState, prefsReady])

  useEffect(() => {
    if (!prefsReady) return
    if (skipPrefsSave.current) {
      skipPrefsSave.current = false
      return
    }
    const override =
      hostname.trim() === defaultHostname() ? '' : hostname.trim()
    const signature = JSON.stringify([pins, resolvedHiddenIds, override, sectionState])
    if (signature === lastPrefsSignature.current) return

    if (pendingPrefsTimer.current !== null) {
      window.clearTimeout(pendingPrefsTimer.current)
    }
    pendingPrefsTimer.current = window.setTimeout(() => {
      pendingPrefsTimer.current = null
      flushPrefsSave()
    }, 300)

    return () => {
      if (pendingPrefsTimer.current !== null) {
        window.clearTimeout(pendingPrefsTimer.current)
        pendingPrefsTimer.current = null
      }
    }
  }, [pins, resolvedHiddenIds, hostname, sectionState, prefsReady, flushPrefsSave])

  useEffect(() => {
    const onBeforeUnload = () => {
      if (pendingPrefsTimer.current !== null) {
        window.clearTimeout(pendingPrefsTimer.current)
        pendingPrefsTimer.current = null
        flushPrefsSave()
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('pagehide', onBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('pagehide', onBeforeUnload)
    }
  }, [flushPrefsSave])

  useEffect(() => {
    const onSettings = () => setSettingsTick((n) => n + 1)
    window.addEventListener(AGENT_SETTINGS_CHANGED_EVENT, onSettings)
    // #1196: remote health is a shared store now — a probe finishing re-renders
    // the rows so offline dots appear/disappear without a poll of their own.
    window.addEventListener(REMOTE_HEALTH_CHANGED_EVENT, onSettings)
    return () => window.removeEventListener(REMOTE_HEALTH_CHANGED_EVENT, onSettings)
  }, [])

  // #1196: the sidebar starts the shared health poll once remotes are known.
  // Two effects, deliberately, for the same reason as the seat poll below:
  // publishing the ids belongs to the id list (the store decides from what
  // CHANGED in the list whether that is worth traffic, so a `remotes` poll
  // handing over a fresh array with the same ids costs nothing), and owning
  // the poll's lifetime belongs to the rail's lifetime. A cleanup on the list
  // effect would release and re-acquire on every `remotes` poll.
  useEffect(() => {
    startRemoteHealthPolling(
      remotes.map((r) => r.id),
      'sidebar',
    )
  }, [remotes])
  // Without this the rail's subscription outlives the rail.
  useEffect(() => () => stopRemoteHealthPolling('sidebar'), [])

  // #507: Hide and Unhide are inverses for every rail kind — the old
  // force-visible exemption for CLI/API seats (#321/#621) turned Hide into a
  // silent no-op that no UI could undo. canHideAgent() is now the single
  // policy: any rail row is hideable, and a hidden CLI/API seat lands in the
  // Hidden tail like any other.
  const visibleAgents = useMemo(
    () =>
      agents.filter(
        (agent) =>
          !isRailIdDeleted(agent.id, deletedIds) &&
          !resolvedHiddenIds.includes(agent.id),
      ),
    [agents, resolvedHiddenIds, deletedIds],
  )
  const hiddenAgents = useMemo(
    () =>
      agents.filter(
        (agent) =>
          !isRailIdDeleted(agent.id, deletedIds) &&
          resolvedHiddenIds.includes(agent.id),
      ),
    [agents, resolvedHiddenIds, deletedIds],
  )

  // #1658 follow-up: one health verdict for every seat kind, so a dead agent
  // is labelled broken wherever its name appears (rail rows, pickers, composer,
  // navbar). `trackSeatHealth` owns the 60s poll and is idempotent; the seat
  // list is rebuilt from what the rail already renders, so nothing is probed
  // that the operator cannot see.
  //
  // Two effects, deliberately. Publishing the seats belongs to the seat list:
  // the store decides from the *set* of `kind:seat_id` keys whether that is a
  // change worth traffic, so a new array with the same seats costs nothing.
  // Owning the poll's lifetime belongs to the rail's lifetime, and must not
  // re-run per rebuild — a cleanup on the list effect would unsubscribe and
  // resubscribe on every `remotes` poll, which is the burst this replaces.
  useEffect(() => {
    const seats: SeatRef[] = []
    for (const row of remotes) {
      if (row.id) seats.push({ kind: 'remote', seatId: row.id })
    }
    for (const agent of [...visibleAgents, ...hiddenAgents]) {
      if (isCliRailAgent(agent)) {
        seats.push({ kind: 'cli', seatId: agent.id, cli: (agent as { cli?: string }).cli })
      } else {
        seats.push({ kind: 'api', seatId: agent.id })
      }
    }
    trackSeatHealth(seats)
  }, [remotes, visibleAgents, hiddenAgents])

  // The interval must not outlive the rail: nothing else calls
  // `stopTrackingSeatHealth`, so without this a closed sidebar keeps polling.
  useEffect(() => () => stopTrackingSeatHealth(), [])
  const visibleTeams = useMemo(
    () =>
      teams.filter(
        (team) =>
          // #687: team rows answer ONLY to their namespaced rail id
          // (team:<id>). A bare-id delete belongs to an agent seat — honoring
          // it here too is how deleting one agent made a same-id team
          // disappear (1 delete removed >1 seat).
          !isRailIdDeleted(teamHideId(team.id), deletedIds) &&
          !resolvedHiddenIds.includes(teamHideId(team.id)),
      ),
    [teams, resolvedHiddenIds, deletedIds],
  )
  const visibleRootTeams = useMemo(
    () =>
      rootTeams.filter(
        (team) =>
          // #687: namespaced rail id only — see visibleTeams.
          !isRailIdDeleted(teamHideId(team.id), deletedIds) &&
          !resolvedHiddenIds.includes(teamHideId(team.id)),
      ),
    [rootTeams, resolvedHiddenIds, deletedIds],
  )
  const hiddenTeams = useMemo(
    () =>
      teams.filter(
        (team) =>
          // #687: namespaced rail id only — see visibleTeams.
          !isRailIdDeleted(teamHideId(team.id), deletedIds) &&
          resolvedHiddenIds.includes(teamHideId(team.id)),
      ),
    [teams, resolvedHiddenIds, deletedIds],
  )
  const visibleRemotes = useMemo(
    () =>
      remotes.filter(
        (remote) =>
          // #687: remote rows answer ONLY to remote:<id>. This bare-id check
          // is the showstopper: deleting the Hermes *agent* seat marked the
          // bare id and the Hermes *remote* vanished with it.
          !isRailIdDeleted(remoteHideId(remote.id), deletedIds) &&
          !resolvedHiddenIds.includes(remoteHideId(remote.id)),
      ),
    [remotes, resolvedHiddenIds, deletedIds],
  )
  const hiddenRemotes = useMemo(
    () =>
      remotes.filter(
        (remote) =>
          // #687: namespaced rail id only — see visibleRemotes.
          !isRailIdDeleted(remoteHideId(remote.id), deletedIds) &&
          resolvedHiddenIds.includes(remoteHideId(remote.id)),
      ),
    [remotes, resolvedHiddenIds, deletedIds],
  )
  const hiddenCount = hiddenAgents.length + hiddenTeams.length + hiddenRemotes.length
  // #549: the badge counts agents + teams + remotes, but the palette's universe
  // is recipe rows only — so a hidden team, remote or CLI/herdr seat counted and
  // was never listed. Hand the palette the rows it cannot derive, and the
  // reconciled id list the badge itself used.
  const hiddenRailRows = useMemo<HiddenRailRow[]>(() => {
    const rows: HiddenRailRow[] = []
    for (const team of hiddenTeams) {
      rows.push({
        id: teamHideId(team.id),
        name: team.name || team.id,
        description: team.description || 'Team hidden from the rail',
        href: `/chat?team=${encodeURIComponent(team.id)}`,
        tab: 'Agents',
      })
    }
    for (const remote of hiddenRemotes) {
      rows.push({
        id: remoteHideId(remote.id),
        name: remote.title,
        description: remoteDisplayName(remote) || 'Remote hidden from the rail',
        href: `/chat?remote=${encodeURIComponent(remote.id)}`,
        tab: 'Agents',
      })
    }
    for (const agent of hiddenAgents) {
      rows.push({
        id: agent.id,
        name: agentLabel(agent),
        description: agent.description || 'Agent hidden from the rail',
        href: agentChatHref(agent.id),
        avatarPath: agent.avatar_path ?? null,
        tab: 'Agents',
      })
    }
    return rows
  }, [hiddenTeams, hiddenRemotes, hiddenAgents])
  const visibleCount = visibleAgents.length + visibleTeams.length + visibleRemotes.length
  const loadingList = !propBlueprints && blueprintsQuery.isPending && teamsQuery.isPending
  const loadFailed = blueprintsQuery.isError && teamsQuery.isError && visibleCount === 0
  /* #736: product-modes gating is retired — surfaces are always-on if
     configured. Every group renders from the payloads alone. */
  const supportAgents = visibleAgents.filter((agent) => isSupportAgent(agent))
  const cliAgents = visibleAgents.filter((agent) => isCliRailAgent(agent))
  const apiAgents = visibleAgents.filter((agent) => isApiRailAgent(agent))
  const otherAgents = visibleAgents.filter((agent) => {
    if (isSupportAgent(agent) || isCliRailAgent(agent) || isApiRailAgent(agent)) return false
    return true
  })
  const catalogRows = useMemo<RailRow[]>(() => {
    const supportRows: RailRow[] = supportAgents.map((agent) => ({
      kind: 'agent',
      id: agent.id,
      agent,
    }))
    const cliRows: RailRow[] = cliAgents.map((agent) => ({
      kind: 'agent',
      id: agent.id,
      agent,
    }))
    const apiRows: RailRow[] = apiAgents.map((agent) => ({
      kind: 'agent',
      id: agent.id,
      agent,
    }))
    const teamRows: RailRow[] = visibleRootTeams.map((team) => ({
      kind: 'team',
      id: teamHideId(team.id),
      team,
    }))
    const remoteRows: RailRow[] = visibleRemotes.map((remote) => ({
      kind: 'remote',
      id: remoteHideId(remote.id),
      remote,
    }))
    const otherRows: RailRow[] = otherAgents.map((agent) => ({
      kind: 'agent',
      id: agent.id,
      agent,
    }))
    /* #1726: chat rows are ordinary `RailRow`s with a distinct rail id, so
     * `applyRailOrder`, `partitionRowsBySection`, the kind buckets, the
     * Move-to submenu and the renderers all handle them with no special case
     * at the rail level. They are placed directly after the seat they belong
     * to (the flat order is applied on top), a chat whose seat is gone or
     * hidden is dropped rather than rendered as an orphan, and a chat never
     * enters `agents` — so it cannot be pinned, duplicated, or offered by
     * "+ Add bot". */
    const seatById = new Map(
      [...supportAgents, ...cliAgents, ...apiAgents, ...otherAgents].map((agent) => [
        agent.id,
        agent,
      ]),
    )
    const chatsBySeat = new Map<string, RailRow[]>()
    for (const chat of chatRows) {
      const seat = seatById.get(chat.agentId)
      if (!seat) continue
      if (resolvedHiddenIds.includes(chat.agentId)) continue
      /* The chat rides ON ITS OWN ROW, tagged via `railChat` on the row's agent
       * object. It is NOT a seat-keyed lookup: a lookup would also hand the
       * chat to the seat's own row, and one of the two would then be wearing
       * the other's identity — which is how the first attempt at this silently
       * deleted the seat row. #1709's "one row per seat" stays literally true:
       * the seat row is still there, still carries the stacked session faces,
       * and still owns the active state; the chat is a second row beside it. */
      const chatAgent = { ...seat, railChat: chat } as typeof seat
      const row: RailRow = { kind: 'agent', id: chat.id, agent: chatAgent }
      const bucket = chatsBySeat.get(chat.agentId)
      if (bucket) bucket.push(row)
      else chatsBySeat.set(chat.agentId, [row])
    }
    const seatRows: RailRow[] = [
      ...supportRows,
      ...cliRows,
      ...apiRows,
      ...teamRows,
      ...remoteRows,
      ...otherRows,
    ]
    const withChats: RailRow[] = []
    for (const row of seatRows) {
      withChats.push(row)
      for (const chat of chatsBySeat.get(row.id) ?? []) withChats.push(chat)
    }
    return excludePinnedFromList(
      withChats,
      pins,
    )
  }, [
    supportAgents,
    cliAgents,
    apiAgents,
    visibleRootTeams,
    visibleRemotes,
    otherAgents,
    pins,
    chatRows,
    resolvedHiddenIds,
  ])
  const orderedRows = useMemo(
    () => applyRailOrder(catalogRows, railOrder),
    [catalogRows, railOrder],
  )
  // #1714: the synthetic kind buckets only harvest Unassigned. A row a user
  // explicitly filed into a custom section honours that membership and stays
  // put, so custom sections keep working exactly as before.
  //
  // This is the ONE definition of "which auto section claims this row", shared
  // with the Move-to submenu below. It used to live inline in the `sectionBlocks`
  // memo, which is why the menu could not know about the auto sections at all:
  // it read `state.sections` instead, and `os` / `remote` / `cli` / `api` /
  // `subagents` are not in that bag. Hoisted so both surfaces agree by
  // construction.
  const autoSectionOfRow = useCallback(
    (row: RailRow, dynamicIds: Set<string>): string | null => {
      // Open Swarm instances (`kind: swarm`) get their own "OS" block; every
      // other remote stays under "Remote".
      if (row.kind === 'remote') {
        // `impl` is a legacy alias the old inline `remoteKindOf` read off an
        // untyped shape; `RemoteEntry` declares `kind` and `id`.
        const remoteKind = String(row.remote?.kind || row.remote?.id || '')
          .trim()
          .toLowerCase()
        return remoteKind === 'swarm' ? 'os' : 'remote'
      }
      if (row.kind !== 'agent') return dynamicIds.has(row.id) ? 'subagents' : null
      // Kind precedence: a remote-impl seat is Remote even if it also carries
      // an api-shaped id; a CLI seat bound to a remote endpoint stays CLI.
      if (isRemoteRailAgent(row.agent)) return 'remote'
      if (isCliRailAgent(row.agent)) return 'cli'
      if (isApiRailAgent(row.agent)) return 'api'
      return dynamicIds.has(row.id) ? 'subagents' : null
    },
    [],
  )

  const sectionBlocks = useMemo(() => {
    const baseBlocks = partitionRowsBySection(orderedRows, sectionState)
    const dynamicIds = new Set(dynamicSubagents.map((s) => s.id))
    const osRows: RailRow[] = []
    const remoteRows: RailRow[] = []
    const cliRows: RailRow[] = []
    const apiRows: RailRow[] = []
    const subagentRows: RailRow[] = []

    const updatedBlocks = baseBlocks.map((block) => {
      if (block.id !== UNASSIGNED_SECTION_ID) return block
      const standardRows: RailRow[] = []
      for (const row of block.rows) {
        const bucket = autoSectionOfRow(row, dynamicIds)
        if (bucket === 'os') osRows.push(row)
        else if (bucket === 'remote') remoteRows.push(row)
        else if (bucket === 'cli') cliRows.push(row)
        else if (bucket === 'api') apiRows.push(row)
        else if (dynamicIds.has(row.id)) subagentRows.push(row)
        else standardRows.push(row)
      }
      return { ...block, rows: standardRows }
    })

    // OS / Remote / CLI / API lead the list; existing sections (custom +
    // Subagents) and Unassigned keep their relative order underneath.
    const kindBlocks = (
      [
        { id: 'os', name: 'OS', collapsed: osCollapsed, rows: osRows },
        { id: 'remote', name: 'Remote', collapsed: remoteCollapsed, rows: remoteRows },
        { id: 'cli', name: 'CLI', collapsed: cliCollapsed, rows: cliRows },
        { id: 'api', name: 'API', collapsed: apiCollapsed, rows: apiRows },
      ] as Array<{
        id: string
        name: string
        collapsed: boolean
        rows: RailRow[]
      }>
    )
      .filter((block) => block.rows.length > 0)
      .map((block) => ({ ...block, custom: false }))
    updatedBlocks.splice(0, 0, ...kindBlocks)

    if (subagentRows.length > 0) {
      const subagentsBlock = {
        id: 'subagents',
        name: 'Subagents',
        collapsed: subagentsCollapsed,
        rows: subagentRows,
        custom: false,
      }
      const unassignedIdx = updatedBlocks.findIndex((b) => b.id === UNASSIGNED_SECTION_ID)
      if (unassignedIdx >= 0) {
        updatedBlocks.splice(unassignedIdx, 0, subagentsBlock)
      } else {
        updatedBlocks.push(subagentsBlock)
      }
    }

    return updatedBlocks
  }, [
    orderedRows,
    sectionState,
    dynamicSubagents,
    autoSectionOfRow,
    subagentsCollapsed,
    cliCollapsed,
    remoteCollapsed,
    apiCollapsed,
    osCollapsed,
  ])
  const visibleRowIds = useMemo(() => orderedRows.map((row) => row.id), [orderedRows])

  // #1714: the section block each row is rendered under, derived from the very
  // blocks the rail renders. The Move-to submenu reads this so its list is a
  // subset of the visible sections BY CONSTRUCTION — the old code rebuilt the
  // list from `sectionState.sections` and silently dropped every auto section.
  const autoSectionByRowId = useMemo(() => {
    const map = new Map<string, string>()
    for (const block of sectionBlocks) {
      for (const row of block.rows) {
        map.set(row.id, block.id)
      }
    }
    return map
  }, [sectionBlocks])
  const knownRailIds = useMemo(() => new Set(agents.map((agent) => agent.id)), [agents])
  const catalogById = useMemo(() => new Map(catalog.map((row) => [row.id, row])), [catalog])
  const catalogReady = Boolean(propBlueprints) || !blueprintsQuery.isPending
  const visiblePins = useMemo(
    () =>
      pins.filter((pin) => {
        if (resolvedHiddenIds.includes(pin.id) || isRailIdDeleted(pin.id, deletedIds)) {
          return false
        }
        if (knownRailIds.has(pin.id) || isNonCatalogRailPinId(pin.id)) return true
        if (!catalogReady) return true
        const catalogRow = catalogById.get(pin.id)
        if (catalogRow && catalogRow.rail !== true) return false
        return true
      }),
    [pins, resolvedHiddenIds, deletedIds, knownRailIds, catalogReady, catalogById],
  )
  const hotkeyTargets = useMemo(
    () => computeRailNavSequence({ visiblePins, orderedRows }),
    [visiblePins, orderedRows],
  )

  const navScrollRef = useRef<HTMLElement | null>(null)
  const [canScroll, setCanScroll] = useState(false)
  // #1247: directional scrollability for the avatar-only chevrons. The native
  // scrollbar is concealed there, so these two flags drive the faint up/down
  // affordances.
  const [canScrollUp, setCanScrollUp] = useState(false)
  const [canScrollDown, setCanScrollDown] = useState(false)

  const updateCanScroll = useCallback(() => {
    const el = navScrollRef.current
    if (!el) return
    const scrollable = el.scrollHeight > el.clientHeight
    setCanScroll(scrollable)
    setCanScrollUp(el.scrollTop > 4)
    setCanScrollDown(el.scrollTop + el.clientHeight < el.scrollHeight - 4)
  }, [])

  useEffect(() => {
    updateCanScroll()
    const el = navScrollRef.current
    if (!el) return
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(updateCanScroll)
      ro.observe(el)
      // #1247: rows/sections collapse changes scrollHeight without a scroll
      // event, so re-derive the chevron flags from the container's box too.
      if (el.firstElementChild) ro.observe(el.firstElementChild)
      return () => ro.disconnect()
    }
    return undefined
  }, [updateCanScroll, orderedRows.length, visiblePins.length])

  // #1709: adding a chat with an existing seat must leave the rail SHOWING it
  // — section expanded, row scrolled into view, row lit as the active seat.
  // Without this the URL moved and the rail looked untouched.
  // #1805: the scroll inside that hook is once per SELECTION — Alt+Arrow
  // browse, a created agent, a click-select — so rebuilding `visibleRowIds`
  // here (a health tick, a remotes refresh, a refocus refetch) can no longer
  // drag a free-scrolling operator back to the selected seat.
  useRailReveal({
    activeRail,
    sectionBlocks,
    visibleRowIds,
    navScrollRef,
    setSectionState,
    setOsCollapsed,
    setRemoteCollapsed,
    setCliCollapsed,
    setApiCollapsed,
    setSubagentsCollapsed,
  })

  const openPalette = useCallback(() => {
    onOpenSearch?.()
    // #549: keep the palette's hidden universe in sync with the badge even when
    // the palette is opened from search rather than the Hidden Agents row.
    openSearchPalette({ hiddenIds: resolvedHiddenIds, hiddenRows: hiddenRailRows })
  }, [onOpenSearch, resolvedHiddenIds, hiddenRailRows])

  const isPinnedId = (id: string | null | undefined) =>
    Boolean(id && pins.some((pin) => pin.id === id))

  // #856 slice 11: menu/section/notify commands live in the hook below; the
  // menu states stay page-owned so the overlay JSX below is unchanged.
  const railMenu = useRailMenuCommands({
    menu,
    sectionMenu,
    paneMenu,
    sectionState,
    editingSectionId,
    editingSectionName,
    notifyIds,
    notifyHint,
    isPinnedId,
    setMenu,
    setSectionMenu,
    setPaneMenu,
    setSectionState,
    setEditingSectionId,
    setEditingSectionName,
    setPins,
    setNotifyIds,
    setNotifyHint,
  })
  const {
    closeMenu,
    commitSectionRename,
    cancelSectionRename,
    handleMoveTo,
    handleBubbleTheme,
    openSectionMenuAt,
    handleSectionMenuSelect,
    openPaneMenuAt,
    handlePaneMenuSelect,
    toggleNotify,
    retryNotifyPermission,
  } = railMenu

  // #856 slice 10: session-picker commands live in the hook below; the
  // picker states stay page-owned so the overlay JSX below is unchanged.
  const railSession = useRailSessionCommands({
    onClose,
    setPicker,
    setCliPicker,
    setSessionPicker,
  })

  const persistVisibleOrder = useCallback((nextVisible: string[]) => {
    setRailOrder(saveRailOrder(nextVisible))
  }, [])

  const reorderBefore = useCallback(
    (fromId: string, beforeId: string) => {
      if (!fromId || !beforeId || fromId === beforeId) return
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(moveRailId(base, fromId, beforeId))
    },
    [railOrder, visibleRowIds, persistVisibleOrder],
  )

  // #761: bottom-half drop — the moved row lands immediately BELOW the target.
  const reorderAfter = useCallback(
    (fromId: string, afterId: string) => {
      if (!fromId || !afterId || fromId === afterId) return
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(moveRailIdAfter(base, fromId, afterId))
    },
    [railOrder, visibleRowIds, persistVisibleOrder],
  )

  /* ---------------------------------------------------------------------
   * #1740 — Alt+Arrow reordering, from one focused row.
   *
   * The full key map, and what it coexists with:
   *
   *   Alt+ArrowUp / Down   reorder among siblings in the SAME section
   *   Alt+ArrowLeft/Right  move the row to the ADJACENT section
   *   Alt+Arrow on a pin   the same two verbs in the PIN GRID's scope — see
   *                        `railPinKeyboardReorder` below. It used to be
   *                        #1088's sequential navigation, which is what a pin
   *                        fell through to when this only owned section rows.
   *   Space                #1705's selection toggle (it excludes altKey)
   *   Enter                untouched — the row opens
   *   Shift+F10 / Menu     untouched — forwarded to `rowMenu.onKeyDown`
   *   Escape               #1705's clear-selection, unchanged
   *   Ctrl/Cmd+Arrow       not a gesture here (the gate requires no second
   *                        modifier) — Alt+Arrow never fires for it
   *
   * Returns true when it CLAIMED the key, which is what makes the row's
   * onKeyDown `preventDefault` it and lets the window navigation handler
   * (`onAltArrow`, above) stand down via its `defaultPrevented` bail.
   */
  const [reorderAnnouncement, setReorderAnnouncement] = useState('')
  // #1740 §3: selection stays on the moved item. A cross-section move
  // unmounts the row from one block and mounts it in another, so focus has to
  // be re-taken once the new block has rendered.
  const pendingReorderFocus = useRef<string | null>(null)
  useEffect(() => {
    const id = pendingReorderFocus.current
    if (!id) return
    const root = railRootRef.current
    const node = root?.querySelector<HTMLElement>(`[data-agent-id="${id.replace(/"/g, '\\"')}"]`)
    if (!node) return
    pendingReorderFocus.current = null
    node.focus()
    // `pins` joins because a pin reorder re-orders the GRID: the tile keeps the
    // same node but moves, and a grid that never re-rendered would leave the
    // announcement claiming a move the operator cannot see.
  }, [pins, sectionBlocks, railOrder, sectionState])

  const railKeyboardReorder = useCallback(
    (rowId: string, event: { key: string; altKey: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }) => {
      const intent = railReorderIntent(event)
      if (!intent) return false
      const block = sectionBlocks.find((candidate) =>
        candidate.rows.some((row) => row.id === rowId),
      )
      if (!block) return false
      if (block.collapsed) return false
      const base = mergeRailOrder(railOrder, visibleRowIds)
      const orderBase = railOrder.length > 0 ? base : visibleRowIds
      if (intent.direction === 'up' || intent.direction === 'down') {
        const outcome = reorderWithinSection({
          order: orderBase,
          blocks: sectionBlocks,
          rowId,
          direction: intent.direction,
        })
        if (outcome.moved) {
          persistVisibleOrder(outcome.order)
          pendingReorderFocus.current = rowId
        }
        setReorderAnnouncement(outcome.announcement)
        return true
      }
      // #1714: the destination list is the rail's OWN blocks, so Alt+Left /
      // Right cannot land on a section the Move-to submenu would have refused.
      const currentSectionId = block.id
      const outcome = moveToAdjacentSection({
        order: orderBase,
        destinations: railMoveToDestinations({
          blocks: sectionBlocks,
          currentSectionId,
          autoGroup: isAutoSectionId(currentSectionId) ? currentSectionId : null,
        }),
        blocks: sectionBlocks,
        rowId,
        currentSectionId,
        direction: intent.direction,
      })
      if (outcome.moved && outcome.targetId) {
        // A pinned row must LEAVE the pin grid to be filed, or its membership
        // would park it in limbo — same rule as drag-to-section and Move-to.
        if (isPinnedId(rowId)) {
          setPins((current) =>
            current.some((pin) => pin.id === rowId) ? unpinAgent(rowId, current) : current,
          )
        }
        setSectionState((current) => moveAgentToSection(current, rowId, outcome.targetId as string))
        if (outcome.order) persistVisibleOrder(outcome.order)
        pendingReorderFocus.current = rowId
      }
      setReorderAnnouncement(outcome.announcement)
      return true
    },
    [
      isPinnedId,
      persistVisibleOrder,
      railOrder,
      sectionBlocks,
      sectionState,
      setPins,
      setSectionState,
      visibleRowIds,
    ],
  )

  /* ---------------------------------------------------------------------
   * #1740 — the same two verbs, in the PIN GRID's scope.
   *
   * A pinned tile is a different row class from a section row: it is rendered
   * above every section, out of its own store (`lib/pinnedAgents`), and it
   * never went through `railKeyboardReorder` above. So Alt+Down on a focused
   * pin fell through to #1088's sequential navigation and paged away to the
   * next seat — the one place the issue's §1 ("reorder among siblings in the
   * same section, including Pinned") did not hold.
   *
   * Nothing here is a second rule set: the gate is the same `railReorderIntent`,
   * the arithmetic is `reorderWithinPinGrid` / `movePinToAdjacentSection` in
   * `features/sidebar/railReorder`, the announcement is the same
   * `reorderAnnouncement` live region, and the return value means the same
   * thing — the tile claimed the key, so `RailSections` `preventDefault`s it
   * and the window `onAltArrow` stands down via its `defaultPrevented` bail.
   * ------------------------------------------------------------------- */
  const railPinKeyboardReorder = useCallback(
    (
      pinId: string,
      event: { key: string; altKey: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
    ) => {
      const intent = railReorderIntent(event)
      if (!intent) return false
      // The tile already proved it is a pin by calling us; a row id that is
      // not pinned (a chat row, a stale tile mid-unpin) is not the grid's.
      if (!isPinnedId(pinId)) return false
      if (intent.direction === 'up' || intent.direction === 'down') {
        const outcome = reorderWithinPinGrid({
          pins,
          visiblePins,
          pinId,
          direction: intent.direction,
        })
        if (outcome.moved) {
          // The grid's storage is the pin list itself, so the swapped id order
          // is written back with the store drag-to-pin already uses (#1217's
          // same-tab `savePinnedAgents`). Hidden pins keep their own slots.
          const byId = new Map(pins.map((pin) => [pin.id, pin]))
          const next = outcome.order
            .map((id) => byId.get(id))
            .filter((pin): pin is PinnedAgent => Boolean(pin))
          setPins(next)
          savePinnedAgents(next)
          pendingReorderFocus.current = pinId
        }
        setReorderAnnouncement(outcome.announcement)
        return true
      }
      const base = mergeRailOrder(railOrder, visibleRowIds)
      const orderBase = railOrder.length > 0 ? base : visibleRowIds
      const outcome = movePinToAdjacentSection({
        order: orderBase,
        // #1714's own destination list, so a pin is filed exactly where the
        // Move-to submenu would file it.
        sectionDestinations: railMoveToDestinations({
          blocks: sectionBlocks,
          currentSectionId: RAIL_PIN_GRID_ID,
        }),
        blocks: sectionBlocks,
        visiblePins,
        pinId,
        direction: intent.direction,
      })
      if (outcome.moved && outcome.targetId) {
        // #801: filing a pin LEAVES the grid. `excludePinnedFromList` strips
        // pinned ids from the section rows, so a pin that stayed would be
        // rendered nowhere at all — the same rule drag-to-section follows.
        setPins((current) =>
          current.some((pin) => pin.id === pinId) ? unpinAgent(pinId, current) : current,
        )
        setSectionState((current) => moveAgentToSection(current, pinId, outcome.targetId as string))
        if (outcome.order) persistVisibleOrder(outcome.order)
        pendingReorderFocus.current = pinId
      }
      setReorderAnnouncement(outcome.announcement)
      return true
    },
    [
      isPinnedId,
      persistVisibleOrder,
      pins,
      railOrder,
      sectionBlocks,
      setPins,
      setSectionState,
      visiblePins,
      visibleRowIds,
    ],
  )

  // #856 slice 12: drag/pin/hide interactions live in the hook below; the
  // drag states stay page-owned so the row render props are unchanged.
  const railDrag = useRailDragCommands({
    draggingId,
    resolvedHiddenIds: resolvedHiddenIds ?? [],
    sectionState,
    isPinnedId,
    reorderBefore,
    reorderAfter,
    closeMenu,
    setDraggingId,
    setDropTargetId,
    setSectionDropId,
    setDropActive,
    setListDropActive,
    setHideDropActive,
    setBinDragOver,
    setPins,
    setHiddenIds,
    setSectionState,
    hideDropDepth,
  })
  const {
    finishDrag,
    hideAgent,
    unhideAgent,
    togglePin,
    dropPin,
    dropPinReorder,
    dropUnfavourite,
    allowListUnfavourite,
    dropHide,
    allowRowDrop,
    dropReorder,
    allowSectionDrop,
    dropOnSection,
    dropOnSelf,
    beginRowDrag,
  } = railDrag

  const handleAgentCreated = useCallback(
    (created: { id: string; name: string; kind: AgentKind }) => {
      setAddWizardOpen(false)
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(bumpRailIdToTop(base, created.id))
      if (created.kind === 'remote') {
        navigate(`/chat?remote=${encodeURIComponent(created.id)}`)
      } else {
        navigate(`/chat?blueprint=${encodeURIComponent(created.id)}`)
      }
      onClose?.()
    },
    [navigate, onClose, railOrder, visibleRowIds, persistVisibleOrder],
  )

  // #793: newly created teams land at the TOP of Unassigned — never appended
  // below the fold where creation looks like it failed.
  useEffect(() => {
    const onTeamCreated = (event: Event) => {
      const detail = (event as CustomEvent<{ id?: string }>).detail
      const id = detail?.id ? teamHideId(detail.id) : ''
      if (!id) return
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(bumpRailIdToTop(base, id))
    }
    window.addEventListener(TEAM_CREATED_EVENT, onTeamCreated)
    return () => window.removeEventListener(TEAM_CREATED_EVENT, onTeamCreated)
  }, [railOrder, visibleRowIds, persistVisibleOrder])

  const handleAgentSelected = useCallback(
    (agentId: string) => {
      setAddWizardOpen(false)
      navigate(`/chat?blueprint=${encodeURIComponent(agentId)}`)
      onClose?.()
    },
    [navigate, onClose],
  )

  useEffect(() => {
    const onBump = () => {
      setBumpCompleted(loadBumpCompleted())
      setBumpScope(loadBumpScope())
    }
    window.addEventListener(BUMP_COMPLETED_EVENT, onBump)
    window.addEventListener(BUMP_SCOPE_EVENT, onBump)
    return () => {
      window.removeEventListener(BUMP_COMPLETED_EVENT, onBump)
      window.removeEventListener(BUMP_SCOPE_EVENT, onBump)
    }
  }, [])

  const rowDisplayName = useCallback(
    (id: string, fallback?: string) => {
      if (!id) return fallback || ''
      const pin = pins.find((item) => item.id === id)
      if (pin?.name) return pin.name
      const agent = agents.find((item) => item.id === id)
      if (agent?.name) return agent.name
      if (id.startsWith('team:')) {
        const team = teams.find((item) => teamHideId(item.id) === id)
        if (team?.name) return team.name
      }
      if (id.startsWith('remote:')) {
        const remote = remotes.find((item) => remoteHideId(item.id) === id)
        if (remote) return remoteDisplayName(remote)
      }
      return fallback || id
    },
    [agents, pins, remotes, teams],
  )

  // #1674: the Add-bot menu lists the SAME `agents` the rail renders — no
  // second registry. Display names go through `rowDisplayName` so a pin rename
  // reads identically in the menu and in the rail.
  const addBotMenuAgents = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.id,
        label: rowDisplayName(agent.id, agent.name) || agent.id,
        avatarSrc: agent.avatar_path ?? null,
        remoteKind: typeof agent.kind === 'string' ? agent.kind : null,
      })),
    [agents, rowDisplayName],
  )

  useEffect(() => {
    const onComplete = (event: Event) => {
      const detail = generationCompleteDetail(event)
      const agentId = detail?.agentId ?? generationCompleteAgentId(event)
      if (detail) {
        maybeNotifyAgentTurn({
          agentId: detail.agentId,
          agentName: detail.agentName || rowDisplayName(detail.agentId),
          snippet: detail.snippet,
          failed: detail.failed,
          selectedAgentId: currentTargetId,
        })
      }
      if (agentId && agentId !== currentTargetId) {
        setUnreadIds(markAgentUnread(agentId))
      }
      if (!bumpCompleted) return
      if (!agentId || !visibleRowIds.includes(agentId)) return
      // #552: by default the bump is confined to Unassigned, so an agent the
      // operator placed in a section keeps the position they gave it. This
      // guards the automatic bump only — a manual drag is not gated by it.
      if (
        bumpScope === 'unassigned' &&
        sectionIdForAgent(agentId, sectionState) !== UNASSIGNED_SECTION_ID
      ) {
        return
      }
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(bumpRailIdToTop(base, agentId))
    }
    window.addEventListener(GENERATION_COMPLETE_EVENT, onComplete)
    return () => window.removeEventListener(GENERATION_COMPLETE_EVENT, onComplete)
  }, [
    bumpCompleted,
    bumpScope,
    sectionState,
    visibleRowIds,
    railOrder,
    persistVisibleOrder,
    currentTargetId,
    rowDisplayName,
  ])
  useEffect(() => {
    if (!menu && !sectionMenu && !paneMenu) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu()
    }
    const onPointer = (event: Event) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        closeMenu()
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onPointer)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onPointer)
    }
  }, [menu, sectionMenu, paneMenu, closeMenu])

  useEffect(() => {
    // #1088: Alt+Up / Alt+Down sequential navigation (Herdr parity) replaces
    // REQ-172's Alt+1..9 slots, which collided with native browser tab
    // switching. The anchor is whichever row the URL currently points at.
    // #1218: a focused popup owns Alt+Arrow for its own list — the rail
    // handler yields whenever the event originates inside an overlay.
    //
    // #1740: this handler used to claim EVERY Alt+Arrow and read anything that
    // was not ArrowDown as "up", so Alt+Left / Alt+Right silently navigated
    // backwards. Two changes, both load-bearing:
    //  - only Up/Down remain navigation keys; Left/Right are #1740's
    //    "change section" pair and are left to the focused row;
    //  - `defaultPrevented` is honoured, so the row's own reorder handler
    //    (which runs first, on React's root inside this window) wins outright
    //    instead of both acting on one keypress.
    const onAltArrow = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return
      if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
      const el = event.target instanceof Element ? event.target : null
      if (el?.closest('.os-search-palette, dialog[open], [role="dialog"]')) return
      const dir: 1 | -1 = event.key === 'ArrowDown' ? 1 : -1
      const currentIdx = activeRailNavIndex(hotkeyTargets, window.location.search)
      const target2 = stepRailNav(hotkeyTargets, currentIdx, dir)
      if (target2) {
        event.preventDefault()
        // #1195: every target chats via its computed href — herdr pins included
        // (#543: `?remote=herdr&session=<name>` IS the conversation). The old
        // `window.location.assign('/teams/#herdr-members')` override fought
        // the sequence data and hard-reloaded the SPA mid-navigation.
        navigate(target2.href)
        onClose?.()
      }
    }
    window.addEventListener('keydown', onAltArrow)
    return () => window.removeEventListener('keydown', onAltArrow)
  }, [hotkeyTargets, navigate, onClose])

  const {
    openGroupPicker,
    closePicker,
    openCliSessionPicker,
    applyCliSession,
    continueCliSessionOn,
    selectSession,
    openAgentSessionPicker,
    startNewAgentSession: railStartNewAgentSession,
  } = railSession

  /* #1726 — the ONE "New session" command, now shared by BOTH surfaces.
   *
   * The row context menu's "New session" and `AddBotMenu.onStartChat` already
   * called the same `startNewAgentSession`; what was missing was the visible
   * result. This wrapper keeps that single command and adds the two things the
   * issue asks for, in this order:
   *
   *   1. a DUPLICATE sidepane row (the chat row), filed right under its seat,
   *      so the twin is where the operator is already looking; and
   *   2. the main-pane switch, which the underlying command already did.
   *
   * Because both call sites go through here, "New session" and "+ Add bot" are
   * the same code path by construction — there is no second session model to
   * drift. A failure to create the session leaves the rail untouched rather
   * than adding a row for a chat that does not exist. */
  const startNewAgentSession = useCallback(
    async (agentId: string) => {
      if (!agentId) return
      let sessionId = ''
      let title = 'New chat'
      try {
        await railStartNewAgentSession(agentId)
        // #1726: `createAgentSession` already writes the new session into the
        // scale-out cache (#1709 did that so the rail could show it), so the
        // id is read back from the SAME store rather than inventing a second
        // return channel. `listAgentSessions` sorts newest-first, which is the
        // row we just made.
        const newest = listAgentSessions(agentId)[0]
        sessionId = newest?.id || ''
        title = newest?.title || title
      } catch {
        return
      }
      if (!sessionId) return
      const chatId = railChatRowId(agentId, sessionId)
      addRailChatRow({ id: chatId, agentId, sessionId, title, createdAt: Date.now() })
      // Put the twin directly after its seat so it is visible without a
      // scroll, and inherit the seat's section so it is not left in limbo by
      // an order that has never heard of it.
      setSectionState((current) =>
        moveAgentToSection(current, chatId, sectionIdForAgent(agentId, current)),
      )
      setRailOrder((current) =>
        saveRailOrder(
          insertRailIdAfter(mergeRailOrder(current, visibleRowIds), chatId, agentId),
        ),
      )
    },
    [railStartNewAgentSession, setRailOrder, setSectionState, visibleRowIds],
  )

  // #856 slice 13: menu-opener surface lives in the hook below; the menu
  // state stays page-owned so handleMenuSelect and the overlays are unchanged.
  const railOpeners = useRailMenuOpeners({
    agents,
    searchParams,
    pins,
    longPressRef,
    setMenu,
    setSectionMenu,
    setCliRunningIds,
    onClose,
    closeMenu,
  })
  const {
    resolveMenuKind,
    openAgentSettings,
    openDefinition,
    rowMenuHandlers,
  } = railOpeners

  // #856 slice 14: row edit/duplicate/copy/delete ops live in the hook
  // below; deleteConfirm stays page-owned so the dialog JSX is unchanged.
  const railRowOps = useRailRowOps({
    agents,
    orderedRows,
    pins,
    teams,
    remotes,
    configuredRemotesList,
    fullRemotesData: fullRemotesQuery.data ?? {},
    railOrder,
    visibleRowIds,
    sectionState,
    deleteConfirm,
    isPinnedId,
    resolveMenuKind,
    openAgentSettings,
    closeMenu,
    persistVisibleOrder,
    queryClient,
    setDeleteConfirm,
    setDeletedIds,
    setSectionState,
    setPins,
    onClose,
  })
  const {
    editMenuRow,
    duplicateMenuRow,
    copyMenuConversationId,
    handleDropOnRecycleBin,
    requestDelete,
    confirmDeleteRow,
  } = railRowOps

  const handleMenuSelect = (id: RailMenuItemId) => {
    if (!menu) return
    if (id === 'select-agent' && menu.kind === 'remote') {
      const remote =
        remotesQuery.data?.find((row) => row.id === menu.entityId) ||
        configuredRemotesList.find((row) => row.id === menu.entityId)
      closeMenu()
      // #748: no async session fetch on this path. A multi-agent remote keeps
      // its bot-choice picker (choosing WHICH agent is a different axis from
      // sessions) using the rows already in the menu payload; everything else
      // navigates immediately.
      if (menu.sessions && menu.sessions.length > 0) {
        openGroupPicker(menu.agentName, menu.sessions)
        return
      }
      if (remote) {
        navigate(`/chat?remote=${encodeURIComponent(remote.id)}`)
        onClose?.()
      }
      return
    }
    if (id === 'select-agent' && menu.sessions && menu.sessions.length > 0) {
      const title = menu.agentName
      const sessions = menu.sessions
      closeMenu()
      openGroupPicker(title, sessions)
      return
    }
    if (id === 'select-session') {
      const agentId = menu.agentId
      const name = menu.agentName
      const cli = menu.cli || 'grok'
      const cliRow = Boolean(menu.isCli || menu.kind === 'cli')
      closeMenu()
      if (cliRow) {
        void openCliSessionPicker(agentId, name, cli)
      } else {
        void openAgentSessionPicker(agentId, name)
      }
      return
    }
    if (id === 'new-session') {
      const agentId = menu.agentId
      const cli = menu.cli || 'grok'
      const cliRow = Boolean(menu.isCli || menu.kind === 'cli')
      closeMenu()
      if (cliRow) {
        void applyCliSession({ agentId, cli, startNew: true })
      } else {
        void startNewAgentSession(agentId)
      }
      return
    }
    if (id === 'unpin' || id === 'pin') {
      togglePin({ id: menu.agentId, name: menu.agentName })
      return
    }
    if (id === 'unread') {
      if (unreadIds.includes(menu.agentId)) {
        setUnreadIds(markAgentRead(menu.agentId))
      } else {
        setUnreadIds(markAgentUnread(menu.agentId))
      }
      closeMenu()
      return
    }
    if (id === 'edit') {
      editMenuRow(menu)
      return
    }
    if (id === 'duplicate') {
      void duplicateMenuRow(menu)
      return
    }
    if (id === 'copy-id') {
      void copyMenuConversationId(menu)
      return
    }
    if (id === 'terminate') {
      const agentId = menu.agentId
      const conversationId =
        copyableConversationId(menu.kind, menu.agentId, menu.entityId) || undefined
      closeMenu()
      void (async () => {
        try {
          const result = await terminateCliRun({
            agent: agentId,
            conversation_id: conversationId,
          })
          if (result.status === 'terminated') {
            notifyCliTerminated(agentId, conversationId)
            toast?.success(CLI_PROCESS_STOPPED_TOAST, 'This cannot be undone.')
          }
        } catch {
          toast?.error('Could not stop process', 'The CLI subprocess was not terminated.')
        }
      })()
      return
    }
    if (id === 'hide') {
      hideAgent(menu.agentId)
      return
    }
    if (id === 'unhide') {
      unhideAgent(menu.agentId)
      return
    }
    if (id === 'notify') {
      void toggleNotify(menu.agentId)
      return
    }
    if (id === 'delete') {
      requestDelete(menu)
    }
  }

  /* #1726 — the seat a chat row belongs to, for the capability predicates.
   *
   * A chat is a session, and the session store it lives in belongs to the
   * agent, so `seatHasSessions` must be asked about the SEAT: `kind: 'chat'` is
   * a rail-menu concept, not a seat kind, and no capability is declared
   * against it.
   *
   * The kind is read from the MENU — which `resolveMenuKind`/`railMenuKindForRow`
   * already resolved — and never from the catalog row's raw `kind` field. That
   * field is a wire value the rail groups by (`'design'`, `'subagent'`); letting
   * it answer made Select session / New session vanish from a designed rail
   * seat. Only the two fields `seatHasSessions` reads are projected, so nothing
   * else on a menu or a Blueprint row can shadow them. */
  const seat = useMemo(() => {
    if (!menu) return { kind: null as string | null, isCli: false }
    const chat = isRailChatRowId(menu.agentId) ? parseRailChatRowId(menu.agentId) : null
    return {
      kind: chat ? railMenuKindForRow(chat.agentId, agents) : menu.kind,
      isCli: Boolean(menu.isCli),
    }
  }, [menu, agents])
  const menuItems = menu
    ? railMenuItems({
        kind: menu.kind,
        pinned: menu.pinned,
        hidden: menu.hidden,
        unread: unreadIds.includes(menu.agentId),
        hasSelectAgent: shouldShowSelectAgent(menu.sessions),
        // #580: one declared capability drives the rail menu AND the navbar.
        // #1726: a chat row follows its SEAT's capability — the session store
        // belongs to the agent, and "New session" from a chat row means
        // "another chat with this agent", which is the point of the twin.
        hasSelectSession: seatHasSessions(seat),
        hasNewSession: seatHasSessions(seat),
        notifyEnabled: notifyIds.includes(menu.agentId),
        canCopyId:
          menu.kind === 'cli' || menu.kind === 'remote' || menu.kind === 'herdr'
            ? Boolean(copyableConversationId(menu.kind, menu.agentId, menu.entityId))
            : true,
        cliRunning:
          cliRunningIds.has(menu.agentId) || peekCliRunning(menu.agentId),
        // #1714: enumerate the rail's OWN blocks, not `sectionState.sections`, so
        // every section the operator can see in the sidepane is in the menu (and a
        // section removed from the rail is gone from the menu). `autoGroup` is the
        // derived section the row actually sits under, which is what the check mark
        // must name — a CLI row is rendered under "CLI", so ticking "Unassigned"
        // was a lie, and choosing "Unassigned" for it was a silent no-op.
        moveTo: {
          destinations: railMoveToDestinations({
            blocks: sectionBlocks,
            currentSectionId: sectionIdForAgent(menu.agentId, sectionState),
            // Only a real auto section counts as an auto group. A row rendered
            // under Unassigned is in no group at all, so Unassigned stays a
            // genuine destination for it — passing the block id blindly would
            // disable the one move that works.
            autoGroup: isAutoSectionId(autoSectionByRowId.get(menu.agentId))
              ? (autoSectionByRowId.get(menu.agentId) as string)
              : null,
          }),
        },
        // #724: per-agent bubble theme override picker (agent-presentation
        // setting belongs on the agent row's menu, not the message's).
        bubbleTheme: agentBubbleThemeOverrides()[menu.agentId],
        bubbleThemeDefault: loadBubbleTheme(),
      })
    : []

  const sectionMenuItemsForOpen = sectionMenu
    ? sectionMenuItems({
        canMoveUp:
          sectionState.sections.findIndex((section) => section.id === sectionMenu.sectionId) > 0,
        canMoveDown:
          sectionState.sections.findIndex((section) => section.id === sectionMenu.sectionId) <
          sectionState.sections.length - 1,
        internalOnly: Boolean(
          sectionState.sections.find((section) => section.id === sectionMenu.sectionId)
            ?.internalOnly,
        ),
      })
    : []

  // #856 slice G: row renderers moved verbatim to sidebar/rowsRender.tsx.

  const { renderAgentRow, renderRemoteRow, renderTeamRow } = createRowRenderers({
    AgentAvatar,
    agentTurns,
    Link,
    NEEDS_APPROVAL_LABEL,
    GroupAvatar,
    PersonaRoster,
    RailRowSlot,
    StackedAvatars,
    Users,
    activeHerdrRow,
    activeCliRail,
    activeRail,
    activeSessionId, // #1726
    railKeyboardReorder, // #1740
    activeTaskSessionCount,
    agentLabel,
    agentRole,
    allowRowDrop,
    approvalWaitIds,
    beginRowDrag,
    catalog,
    cliActivityByAgent,
    cliRunningIds,
    declaredRosterForTeam,
    defaultSessionForRemote,
    defaultSessionForTeam,
    draggingId,
    dropOnSelf,
    dropReorder,
    dropTargetId,
    finishDrag,
    formatRailTimestamp,
    getRowLastMessage,
    isAvatarOnly,
    isCliRailAgent,
    isHerdrAgent,
    isMac,
    isPinnedId,
    isRailRowSelectable, // #1705: Ctrl/Shift multi-select
    isRailRowSelected,
    isRemoteOffline, // #1196: row dot for offline backing remotes
    loadLocalNewChatPerTask,
    markStackWorking,
    navigate,
    onClose,
    openDefinition,
    openGroupPicker,
    orderedFacesByRecency,
    parseAgentDragPayload,
    peekApprovalWait,
    peekCliRunning,
    peekRailDrag,
    pickOrClose,
    railTeamStackLayout,
    remoteHideId,
    remoteThemeFace,
    resolvedHiddenIds,
    roleBadgeLabel,
    roleCssClass,
    rosterById,
    rowMenuHandlers,
    selectRailRowRange,
    sessionsByAgent,
    sessionsForRemote,
    sessionsForTeam,
    setSessionPicker,
    settingsTick,
    shouldOpenSessionPicker,
    sidebarHref,
    stackFacesForRemote,
    stackFacesForTeam,
    teamChatFaceStack,
    teamHideId,
    teamSidepaneStack,
    toggleRailRowSelection, // #1705: Ctrl/Shift multi-select
    unreadIds,
    __ctx: null as unknown,
  })
  const railSectionsProps = {
    AgentAvatar,
    agentTurns,
    canScroll,
    canScrollUp,
    canScrollDown,
    Link,
    NEEDS_APPROVAL_LABEL,
    RailSectionEmpty,
    RailSectionHeader,
    UNASSIGNED_SECTION_ID,
    activeRail,
    agentChatHref,
    agentLabel,
    agentRole,
    agents,
    allowListUnfavourite,
    allowRowDrop,
    allowSectionDrop,
    approvalWaitIds,
    beginRowDrag,
    cancelSectionRename,
    cliRunningIds,
    commitSectionRename,
    defaultSessionForTeam,
    draggingId,
    dropActive,
    dropOnSection,
    dropPin,
    dropPinReorder,
    dropTargetId,
    dropUnfavourite,
    editingSectionId,
    editingSectionName,
    finishDrag,
    isAvatarOnly,
    isHerdrAgent,
    isMac,
    isPinnedId,
    isRemoteOffline, // #1196: pin dot for offline backing remotes
    isUnassignedSection,
    listDropActive,
    loadFailed,
    loadingList,
    markStackWorking,
    navScrollRef,
    navigate,
    openDefinition,
    openPaneMenuAt,
    openSectionMenuAt,
    orderedRows,
    peekApprovalWait,
    peekCliRunning,
    pickOrClose,
    railPinKeyboardReorder, // #1740: the pin grid is a sibling scope of its own
    remoteHideId,
    remotes,
    renderAgentRow,
    renderRemoteRow,
    renderTeamRow,
    resolveMenuKind,
    resolvedHiddenIds,
    roleBadgeLabel,
    roleCssClass,
    rowMenuHandlers,
    sectionBlocks,
    sectionDropId,
    setDropActive,
    setEditingSectionName,
    setListDropActive,
    setSectionState,
    setCliCollapsed,
    setRemoteCollapsed,
    setApiCollapsed,
    setOsCollapsed,
    setSubagentsCollapsed,
    stackFacesForTeam,
    teamChatFaceStack,
    teamHideId,
    teamSidepaneStack,
    teams,
    toggleSectionCollapsed,
    toggleSectionInternalOnly,
    unreadIds,
    updateCanScroll,
    visibleCount,
    visiblePins,
    __ctx: null as unknown,
  }

  return (
    <>
      {/* #1073: a docked tablet rail is in-flow chrome — no overlay backdrop. */}
      {!tabletDocked && (
        <button
          type="button"
          className={`fixed inset-0 z-30 bg-black/50 lg:hidden ${open ? '' : 'hidden'}`}
          hidden={!open}
          aria-label="Close agents sidebar"
          onClick={onClose}
        />
      )}

      <aside
        ref={railRootRef}
        className={`os-agent-sidebar os-agent-sidebar--${railSide} fixed inset-y-0 ${
          railSide === 'right' ? 'right-0' : 'left-0'
        } z-40 flex shrink-0 flex-col transition-transform duration-200 lg:relative lg:z-30 lg:translate-x-0 ${
          open
            ? 'translate-x-0'
            : railSide === 'right'
              ? 'translate-x-full'
              : '-translate-x-full'            } ${isAvatarOnly ? 'os-agent-sidebar--avatar-only' : ''} ${
          isCollapsed ? 'os-agent-sidebar--collapsed' : ''
        } ${tabletDocked ? 'os-agent-sidebar--tablet-docked' : ''} ${
          !narrow ? 'os-agent-sidebar--animated' : ''
        }`}
        style={
          !narrow
            ? isCollapsed
              ? { width: `${COLLAPSED_RAIL_WIDTH}px` }
              : { width: `${railWidth}px` }
            : { width: '16rem' }
        }
        aria-label="Agents"
        data-testid="os-agent-rail"
        data-rail-open={open ? 'true' : 'false'}
        data-avatar-only={isAvatarOnly ? 'true' : 'false'}
        data-collapsed={isCollapsed ? 'true' : 'false'}
        aria-hidden={drawerHidden || undefined}
        {...(drawerHidden ? { inert: '' } : {})}
      >
        {/* #1246: the expansion affordance for the fully-collapsed (0px)
            pane. It rides the top of the divider spine — immediately left of
            the chat header's agent avatar — instead of the retired mid-pane
            pill. Visible without hover: it is the only way back. */}
        {isCollapsed && !narrow ? (
          <span className="os-rail-collapsed-expand">
            <SidebarExpandButton onClick={expandSidebar} />
          </span>
        ) : null}
        {!narrow ? (
          <div
            className={`os-rail-resizer ${
              railSide === 'right' ? 'os-rail-resizer--right' : ''
            } ${isResizing ? 'os-rail-resizer--active' : ''}`}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize agent sidebar"
            aria-valuenow={railWidth}
            aria-valuemin={MIN_RAIL_WIDTH}
            aria-valuemax={MAX_RAIL_WIDTH}
            tabIndex={0}
            data-testid="rail-resize-handle"
            onPointerDown={handleResizeStart}
            onKeyDown={handleResizeKeyDown}
          />
        ) : null}
        {/* #1349: in ultra-compact (avatar-only) mode the expand control is the
            top-most element of the pane, above the search row. The search row
            stacks vertically here and used to push the control to the bottom;
            hoisting it to the pane top keeps recovery reachable, and it is
            centred so it reads identically in either dock. */}
        {!narrow && isAvatarOnly && !isCollapsed ? (
          <div
            className="os-rail-top-toggle"
            data-testid="rail-top-toggle"
            data-rail-side={railSide}
          >
            <SidebarExpandButton onClick={expandSidebar} />
          </div>
        ) : null}
        {/* #555: the top of the pane is content now (search, sections, rows).
            Only the narrow-overlay drawer keeps a header, and only for its
            dismiss affordance. */}
        {/* #1073: drawer header — X on the LEFT; the tablet pin toggle sits
            on the RIGHT (hidden on mobile: no room to dock). Desktop hides
            the whole header; collapse lives in the search row (#1246). */}
        <div className="flex items-center justify-between gap-2 px-3 pt-3 lg:hidden">
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle lg:hidden"
            aria-label="Close agents sidebar"
            data-testid="rail-drawer-close"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
          {onToggleTabletDock ? (
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle hidden sm:inline-flex"
              aria-label={tabletDocked ? 'Unpin agents sidebar' : 'Pin agents sidebar'}
              aria-pressed={tabletDocked}
              data-testid="rail-tablet-dock-toggle"
              onClick={onToggleTabletDock}
            >
              {tabletDocked ? <PinOff className="h-4 w-4" aria-hidden="true" /> : <Pin className="h-4 w-4" aria-hidden="true" />}
            </button>
          ) : null}
        </div>

        <div className="os-rail-search-row flex items-center gap-1.5 px-3 pb-2 pt-3">
          <button
            type="button"
            className="os-rail-search min-w-0 flex-1 cursor-pointer"
            data-testid="rail-search-trigger"
            aria-label="Search"
            onClick={openPalette}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                openPalette()
              }
            }}
          >
            <Search
              className="h-3.5 w-3.5 shrink-0 text-base-content/40"
              aria-hidden="true"
              data-testid="rail-search-icon"
            />
            <span className="os-rail-search__input os-rail-search__placeholder">Search</span>
            <kbd className="os-rail-search__kbd kbd kbd-xs">{searchShortcut}</kbd>
          </button>
          {/* #1674: `+` is now a menu, not a detour. It offers the two create
              actions plus the rail's own agent list, and picking an agent
              starts a NEW session with it (the same `startNewAgentSession` the
              row context menu's "New session" uses). One registry: the rows
              below are the same `agents` the rail already renders. */}
          <AddBotMenu
            triggerLabel="Add agent"
            className="os-rail-add-menu"
            activeAgentId={selectedId}
            agents={addBotMenuAgents}
            onCreateBot={() => setAddWizardOpen(true)}
            onCreateGroupChat={() =>
              window.dispatchEvent(new CustomEvent(OPEN_TEAM_COMPOSER_EVENT))
            }
            onStartChat={(agentId) => {
              void startNewAgentSession(agentId)
            }}
          />
          {/* #1246: pane collapse lives top-right of the search row; #1349:
              ultra-compact uses the top-of-pane expand control instead. */}
          {!narrow && !isAvatarOnly ? (
            <SidebarConcealButton onClick={concealSidebar} />
          ) : null}
        </div>

          <RailSections {...railSectionsProps} />

        <div
          className={`os-hidden-bots ${hiddenCount === 0 ? 'os-hidden-bots--empty' : 'os-hide-drop--has-hidden'} ${
            hideDropActive ? 'os-hidden-bots--active' : ''
          } ${hiddenCount === 0 && !draggingId ? 'os-hidden-bots--collapsed' : ''}`}
          data-testid="hidden-bots-row"
          data-empty={hiddenCount === 0 ? 'true' : 'false'}
          data-collapsed={hiddenCount === 0 && !draggingId ? 'true' : 'false'}
          data-drag-over={hideDropActive ? 'true' : undefined}
          role="region"
          aria-label="Hidden Agents"
          onDragEnter={(event) => {
            event.preventDefault()
            hideDropDepth.current += 1
            setHideDropActive(true)
          }}
          onDragOver={(event) => {
            event.preventDefault()
            try {
              event.dataTransfer.dropEffect = 'move'
            } catch {
              /* synthetic events may omit dataTransfer */
            }
            setHideDropActive(true)
          }}
          onDragLeave={() => {
            hideDropDepth.current -= 1
            if (hideDropDepth.current <= 0) {
              hideDropDepth.current = 0
              setHideDropActive(false)
            }
          }}
          onDrop={dropHide}
        >
          {hiddenCount > 0 ? (
            <button
              type="button"
              className="os-hide-drop__action os-hidden-bots-row group"
              aria-haspopup="dialog"
              aria-label={`Hidden Agents ${hiddenCount} (${hiddenCount} hidden)`}
              title={`Hidden Agents (${hiddenCount})`}
              data-testid="os-hidden-bots-button"
              onClick={() =>
                openSearchPalette({
                  filterHidden: true,
                  hiddenIds: resolvedHiddenIds,
                  hiddenRows: hiddenRailRows,
                })
              }
              onMouseEnter={() => setHoveringHidden(true)}
              onMouseLeave={() => setHoveringHidden(false)}
            >
              <span className="os-hidden-bots-lead flex items-center gap-1.5 min-w-0">
                <EyeOff
                  className="os-hidden-bots-icon h-3.5 w-3.5 shrink-0"
                  aria-hidden="true"
                  data-testid="os-hidden-bots-icon"
                />
                <span className="os-hidden-bots-label font-medium truncate">Hidden Agents</span>
              </span>
              <span className="os-hidden-bots-tail font-mono text-xs" data-testid="os-hidden-bots-tail">
                <span
                  className={`os-hidden-bots-count ${hoveringHidden ? 'hidden' : 'inline group-hover:hidden'}`}
                  data-testid="os-hidden-bots-count"
                >
                  {hiddenCount}
                </span>
                {/* #557: this row opens the Hidden Agents **dialog**
                    (`aria-haspopup="dialog"` → `openSearchPalette({ filterHidden })`),
                    so it is a navigation affordance and a right chevron is correct —
                    deliberately NOT a `DisclosureChevron`, which would imply an inline
                    expand. Only the glyph changes: a lucide icon instead of the literal
                    `>` character, so weight/size match the rest of the set. */}
                <span
                  className={`os-hidden-bots-chevron ${hoveringHidden ? 'inline' : 'hidden group-hover:inline'}`}
                  data-testid="os-hidden-bots-chevron"
                >
                  <ChevronRight className="h-3 w-3" aria-hidden="true" />
                </span>
              </span>
            </button>
          ) : (
            /* #1076: an empty Hidden Agents slot collapses away while idle —
               but a drag in flight needs a reliable target, so the drop zone
               (label + icon, fixed min-height) reveals while draggingId is
               set. The container keeps its drag handlers either way. */
            draggingId ? (
              <div
                className="flex min-h-9 items-center justify-center gap-1.5 rounded-md border border-dashed border-base-content/25 px-2 py-1 text-xs text-base-content/55"
                data-testid="hidden-drop-zone"
              >
                <EyeOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="os-hidden-drop-label">Drop here to hide</span>
              </div>
            ) : null
          )}
        </div>

        <div className="border-t border-base-300/70 px-3 py-3" data-testid="sidebar-footer-container">
          {/* #1705: the bulk-action bar. It lives at the TOP of the footer
              (which is the pane's last flex child) so showing it shrinks the
              scroller instead of shifting the rows above it, and it renders
              itself only at two or more selected seats. A drag in flight hides
              it: the recycle bin reserves the exact height of the cluster it
              replaces (#783), and the bar would break that reservation. */}
          {draggingId ? null : (
            <RailBulkBar
              selectedIds={multiSelection.ids}
              hiddenCount={bulkHiddenCount}
              pinnedCount={bulkPinnedCount}
              onClear={clearMultiSelection}
              onHide={bulkHideSelected}
              onUnpin={bulkUnpinSelected}
            />
          )}
          {/* #1740: the reorder announcement. A keyboard-only gesture that
              moves a row has to SAY so — the pointer user sees the row land,
              the keyboard user has no such cue, and an edge no-op is
              indistinguishable from a dropped keypress without it. It is a
              polite live region, visually hidden, and lives on the rail so it
              is announced from the pane the operator is in. */}
          <div
            className="sr-only"
            role="status"
            aria-live="polite"
            data-testid="rail-reorder-announce"
          >
            {reorderAnnouncement}
          </div>
          {draggingId ? (
            <div
              /* #783: the bin reserves the exact height of the menu cluster it
                 conceals (see --os-footer-cluster-h below), so engaging the
                 drag never jolts the rail. */
              style={{ ['--os-footer-cluster-h' as string]: '10rem' }}
              className={`os-recycle-bin flex w-full flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed py-3 px-2 transition-all cursor-pointer ${
                binDragOver
                  ? 'border-error bg-error/20 text-error scale-[1.02]'
                  : 'border-error/40 bg-error/5 text-error/80 hover:border-error hover:bg-error/10 hover:text-error'
              }`}
              data-testid="os-recycle-bin"
              role="region"
              aria-label="Delete"
              onDragOver={(event) => {
                event.preventDefault()
                try {
                  event.dataTransfer.dropEffect = 'move'
                } catch {
                  /* synthetic/jsdom */
                }
                setBinDragOver(true)
              }}
              onDragLeave={() => setBinDragOver(false)}
              onDrop={(event) => {
                event.preventDefault()
                event.stopPropagation()
                setBinDragOver(false)
                const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id || draggingId
                if (fromId) {
                  handleDropOnRecycleBin(fromId)
                }
                finishDrag()
              }}
            >
              <Trash2 className="h-5 w-5 shrink-0" aria-hidden="true" />
              <span className="os-bin-label text-xs font-semibold uppercase tracking-wider">Delete</span>
            </div>
          ) : (
            <>
              {/* #182: Group-chat entry lives in the rail footer, directly above Plugins. */}
              <button
                type="button"
                className="os-rail-footer-btn os-rail-icon-badge flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
                onClick={() => window.dispatchEvent(new CustomEvent(OPEN_TEAM_COMPOSER_EVENT))}
                title="Group chats"
                aria-label="Group chats"
                aria-haspopup="dialog"
                data-testid="os-teams-button"
              >
                <Users className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="os-teams-label">Group chats</span>
              </button>
              <button
                type="button"
                className="os-rail-footer-btn os-rail-icon-badge flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
                onClick={openPlugins}
                title={pluginsCalendarSupported ? 'Plugins' : API_ONLY_REASON}
                aria-label={pluginsCalendarSupported ? 'Plugins' : `Plugins: ${API_ONLY_REASON}`}
                aria-disabled={pluginsCalendarSupported ? undefined : 'true'}
                aria-describedby={pluginsCalendarSupported ? undefined : 'os-plugins-gate-reason'}
                data-testid="os-plugins-button"
                data-disabled={pluginsCalendarSupported ? undefined : 'true'}
              >
                <Plug className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="os-plugins-label">Plugins</span>
              </button>
              {/* #511: the reason is a real element so the explanation is
                  reachable by keyboard and screen reader even in avatar-only
                  mode, where the label spans are hidden. */}
              <span id="os-plugins-gate-reason" hidden>
                {API_ONLY_REASON}
              </span>
              <button
                type="button"
                className="os-rail-footer-btn os-rail-icon-badge flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
                onClick={openCalendar}
                title={pluginsCalendarSupported ? 'Routines' : API_ONLY_REASON}
                aria-label={pluginsCalendarSupported ? 'Routines' : `Routines: ${API_ONLY_REASON}`}
                aria-disabled={pluginsCalendarSupported ? undefined : 'true'}
                aria-describedby={pluginsCalendarSupported ? undefined : 'os-calendar-gate-reason'}
                data-testid="os-calendar-button"
                data-disabled={pluginsCalendarSupported ? undefined : 'true'}
              >
                <Calendar className="h-4 w-4 shrink-0" aria-hidden="true" />
                {/* REQ-913 / #512: the entry reads Routines. The class stays
                    `os-calendar-label` — index.css's avatar-only rule hides it
                    in slim mode, and renaming the class without moving that
                    rule would re-expose the label in the slim rail. */}
                <span className="os-calendar-label">Routines</span>
              </button>
              <span id="os-calendar-gate-reason" hidden>
                {API_ONLY_REASON}
              </span>
              <div className="relative os-rail-hostname-row">
                <button
                  type="button"
                  className="os-rail-hostname-icon os-rail-icon-badge btn btn-ghost btn-xs btn-square h-4 w-4 min-h-0 text-base-content/60 hover:text-base-content relative"
                  aria-label="Remote sessions"
                  aria-expanded={remotesPopupOpen}
                  aria-haspopup="menu"
                  data-testid="rail-server-icon"
                  onClick={() => setRemotesPopupOpen((open) => !open)}
                >
                  <Server className="h-4 w-4" aria-hidden="true" />
                  {localWsDown && (
                    <span
                      data-testid="local-server-status-dot"
                      className="absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full bg-error ring-1 ring-base-100"
                    />
                  )}
                </button>
                {!isAvatarOnly ? (
                  <>
                <label className="sr-only" htmlFor="os-rail-hostname">
                  Hostname
                </label>
                <input
                  id="os-rail-hostname"
                  type="text"
                  className="os-rail-hostname"
                  value={hostname}
                  spellCheck={false}
                  onChange={(event) => setHostname(event.target.value)}
                  onBlur={() => {
                    const next = saveHostname(hostname)
                    setHostname(next)
                    const override = next === defaultHostname() ? '' : next
                    saveHostnameOverride(override)
                    dispatchHostnameChanged(override)
                    void saveUserPrefs({ hostname_override: override })
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.currentTarget.blur()
                    }
                    if (event.key === 'Escape') {
                      setHostname(loadHostname() || defaultHostname())
                      event.currentTarget.blur()
                    }
                  }}
                />
                <UpdateChrome />
                  </>
                ) : null}
                {remotesPopupOpen && (
                  <RemoteSessionsPopup
                    isOpen={remotesPopupOpen}
                    onClose={() => setRemotesPopupOpen(false)}
                    remotes={configuredRemotesList}
                    align={sideAwarePopupAlign(railSide)}
                    onOpenSettingsRemotes={() => {
                      setRemotesPopupOpen(false)
                      openSettingsSheet({ section: 'remotes' })
                    }}
                  />
                )}
              </div>
            </>
          )}
        </div>
      </aside>

      {pluginsOpen ? (
        <Suspense fallback={null}>
          <PluginsPopup open={pluginsOpen} onClose={() => setPluginsOpen(false)} />
        </Suspense>
      ) : null}
      {calendarOpen ? (
        <Suspense fallback={null}>
          <AgentCalendarView
            open={calendarOpen}
            onClose={() => setCalendarOpen(false)}
            agents={agents}
          />
        </Suspense>
      ) : null}

      {picker ? (
        <Suspense fallback={null}>
          <SessionPicker
            open
            title={picker.title ?? ''}
            sessions={picker.sessions ?? []}
            onClose={closePicker}
            onSelect={selectSession}
          />
        </Suspense>
      ) : null}

      {sessionPicker ? (
        <Suspense fallback={null}>
          <SessionPicker
            open
            agentName={sessionPicker.agentName ?? ''}
            sessions={sessionPicker.sessions ?? []}
            onClose={() => setSessionPicker(null)}
            onNewSession={() => {
              const agentId = sessionPicker.agentId
              if (agentId) void startNewAgentSession(agentId)
            }}
            onSelect={(session) => {
              const agentId = sessionPicker.agentId || session.agentId
              setConversationIdForAgent(agentId, session.id)
              navigate(sessionHref(agentId, session.id))
              onClose?.()
            }}
          />
        </Suspense>
      ) : null}

      {cliPicker ? (
      <Suspense fallback={null}>
      <CliSessionPicker
        open
        agentName={cliPicker?.agentName ?? ''}
        cli={cliPicker?.cli ?? ''}
        sessions={cliPicker?.sessions ?? []}
        canList={cliPicker?.canList ?? false}
        emptyReason={cliPicker?.emptyReason}
        loading={cliPicker?.loading}
        continueTargets={hopContinueTargets(
          cliPicker?.cli ?? '',
          cliQuery.data?.clis?.length ? cliQuery.data.clis : FALLBACK_CLIS,
        )}
        onClose={() => setCliPicker(null)}
        onSelect={(session) => {
          if (!cliPicker) return
          void applyCliSession({
            agentId: cliPicker.agentId,
            cli: cliPicker.cli,
            session,
          })
        }}
        onStartNew={() => {
          if (!cliPicker) return
          void applyCliSession({
            agentId: cliPicker.agentId,
            cli: cliPicker.cli,
            startNew: true,
          })
        }}
        onContinueOn={(session, targetCli) => {
          if (!cliPicker) return
          void continueCliSessionOn({
            agentId: cliPicker.agentId,
            fromCli: cliPicker.cli,
            session,
            toCli: targetCli,
          })
        }}
      />
      </Suspense>
      ) : null}

      {menu && (
        <RailContextMenu
          agentName={menu.agentName}
          x={menu.x}
          y={menu.y}
          items={menuItems}
          menuRef={menuRef}
          onSelect={handleMenuSelect}
          onSubSelect={(parentId, childId) => {
            if (parentId === 'move-to') handleMoveTo(menu.agentId, childId)
            if (parentId === 'bubble-theme') handleBubbleTheme(menu.agentId, childId)
          }}
        />
      )}
      {sectionMenu && (
        <RailContextMenu
          agentName={sectionMenu.sectionName || 'section'}
          x={sectionMenu.x}
          y={sectionMenu.y}
          items={sectionMenuItemsForOpen}
          menuRef={menuRef}
          onSelect={handleSectionMenuSelect}
        />
      )}
      <RailOverlays
        paneMenu={paneMenu}
        paneMenuItems={paneMenuItems}
        onPaneMenuSelect={handlePaneMenuSelect}
        deleteConfirm={deleteConfirm}
        onDeleteCancel={() => setDeleteConfirm(null)}
        onDeleteConfirm={confirmDeleteRow}
        notifyHint={notifyHint}
        onNotifyRetry={() => void retryNotifyPermission()}
        onNotifyDismiss={() => setNotifyHint(null)}
        addWizardOpen={addWizardOpen}
        onAddWizardClose={() => setAddWizardOpen(false)}
        onAddWizardCreated={handleAgentCreated}
        onAddWizardSelect={handleAgentSelected}
        menuRef={menuRef}
      />
    </>
  )
}
