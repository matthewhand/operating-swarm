import { RailSections } from './sidebar/RailSections'
import { createRowRenderers } from './sidebar/rowsRender'
import {
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
  Plug,
  Plus,
  Search,
  Server,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import AgentCalendarView from './AgentCalendarView'
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
import { computeRailHotkeyTargets } from '../lib/railHotkeys'
import {
  excludePinnedFromList,
  loadOrSeedPinnedAgents,
  parseAgentDragPayload,
  type PinnedAgent,
} from '../lib/pinnedAgents'
import { hydrateRailPrefs, saveUserPrefs } from '../lib/userPrefs'
import {
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
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId,   } from '../lib/remotesCatalog'
import {
  activeRailId,
  herdrRowIdFromParams,
  railSelectionFromParams,
} from '../lib/railActive'
import { configuredRemotes } from '../lib/remotes'
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
  isUnassignedSection,
  loadRailSections,
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
import { openSearchPalette, type HiddenRailRow } from './SearchPalette'
import { isMacPlatform, searchShortcutLabel } from '../lib/keybindingTips'
import {
  AGENT_EDITS_CHANGED_EVENT,
} from '../lib/agentEdits'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import { declaredRosterForTeam,   } from '../lib/declaredRoster'
import PersonaRoster from './PersonaRoster'
import SessionPicker from './SessionPicker'
import CliSessionPicker from './CliSessionPicker'
import {
  fetchCliSessions,
  latestCliActivityMs,
} from '../lib/cliSessions'
import {
  hopContinueTargets,
} from '../lib/cliSessionHop'
import { FALLBACK_CLIS } from '../lib/chatStatus'
import PluginsPopup from './PluginsPopup'
import { OPEN_TEAM_COMPOSER_EVENT, TEAM_CREATED_EVENT } from './TeamComposer'
import { openSettingsSheet } from './SettingsSheet'
import { OPEN_PLUGINS_EVENT } from '../lib/chromeOverlay'
import { useCurrentAgent, isSwarmOwnedSeat } from '../lib/currentAgent'
import RailContextMenu from './RailContextMenu'
import RailSectionHeader, { RailSectionEmpty } from './RailSectionHeader'
import StackedAvatars from './StackedAvatars'
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
  sidebarHref,
  toSidebarCli,
  toSidebarDynamic,
  toSidebarHerdr,
} from '../features/sidebar/rows'
import { useRailRowOps } from '../features/sidebar/useRailRowOps'
import { useRailMenuOpeners } from '../features/sidebar/useRailMenuOpeners'
import { useRailDragCommands } from '../features/sidebar/useRailDragCommands'
import { useRailMenuCommands } from '../features/sidebar/useRailMenuCommands'
import { useRailSessionCommands } from '../features/sidebar/useRailSessionCommands'
import { useRailResize } from './sidebar/useRailResize'
import type { AgentKind } from './AddAgentWizard'
import { RailOverlays } from './sidebar/RailOverlays'
export const OPEN_CALENDAR_EVENT = 'open-calendar-view'
export default function AgentSidebar({
  open = false,
  narrow = false,
  onClose,
  onPick,
  onOpenSearch,
  blueprints: propBlueprints,
}: AgentSidebarProps) {
  const [dynamicSubagents, setDynamicSubagents] = useState<DynamicSubagent[]>(() =>
    loadDynamicSubagents(),
  )
  const [subagentsCollapsed, setSubagentsCollapsed] = useState(false)

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
  const activeRail = onChat ? activeRailId(railSelectionFromParams(searchParams)) : ''
  // #543: when the chat targets a herdr agent, that row is the active one.
  const activeHerdrRow = onChat ? herdrRowIdFromParams(searchParams) : ''
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
  const {
    railSide,
    railWidth,
    isResizing,
    isAvatarOnly,
    isCollapsed,
    handlePillToggle,
    beginResizeDrag,
    handleResizeStart,
    handleResizeKeyDown,
    pillDraggedRef,
  } = useRailResize({ narrow, onClose })
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
    }
    window.addEventListener(SCALE_OUT_SESSIONS_EVENT, onChange)
    window.addEventListener(AGENT_CHAT_SESSIONS_EVENT, onChange)
    window.addEventListener(AGENT_CONVERSATION_EVENT, onChange)
    window.addEventListener(GENERATION_COMPLETE_EVENT, onChange)
    window.addEventListener(HIDDEN_AGENTS_CHANGED_EVENT, onChange)
    window.addEventListener('storage', onChange)
    return () => {
      window.removeEventListener(SCALE_OUT_SESSIONS_EVENT, onChange)
      window.removeEventListener(AGENT_CHAT_SESSIONS_EVENT, onChange)
      window.removeEventListener(AGENT_CONVERSATION_EVENT, onChange)
      window.removeEventListener(GENERATION_COMPLETE_EVENT, onChange)
      window.removeEventListener(HIDDEN_AGENTS_CHANGED_EVENT, onChange)
      window.removeEventListener('storage', onChange)
    }
  }, [])

  useEffect(() => {
    const onEdits = () => setEditsTick((tick) => tick + 1)
    window.addEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
    window.addEventListener(TEAM_EDITS_CHANGED_EVENT, onEdits)
    return () => {
      window.removeEventListener(AGENT_EDITS_CHANGED_EVENT, onEdits)
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
          kind: 'design' as const,
        })),
    [designsQuery.data],
  )
  const catalog = propBlueprints ?? blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS
  const teams = parseTeamRosters(teamsQuery.data ?? [])
  const remotes = remotesQuery.data ?? []
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
    const namedIds = new Set(named.map((a) => a.id))
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
    const merged = [...support, ...named, ...catalogApi, ...rest]
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
      await Promise.all(
        cliAgentsForActivity.map(async ({ id, cli }) => {
          try {
            const ms = latestCliActivityMs(await fetchCliSessions(id, cli))
            if (ms != null) out[id] = ms
          } catch {
            /* honest gap: row simply shows no timestamp */
          }
        }),
      )
      return out
    },
    enabled: cliAgentsForActivity.length > 0,
    staleTime: 5 * 60 * 1000,
  })
  const cliActivityByAgent = cliActivityQuery.data ?? {}
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
  const resolvedHiddenIds = railDataPending
    ? hiddenIds ?? []
    : reconcileHiddenAgentIds(
        hiddenIds ?? loadOrSeedHiddenAgentIds(agents),
        liveRowIds,
        pins.map((pin) => pin.id),
      )

  useEffect(() => {
    if (hiddenIds !== null || blueprintsQuery.isPending) return
    setHiddenIds(loadOrSeedHiddenAgentIds(agents))
  }, [hiddenIds, blueprintsQuery.isPending, agents])

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
  useEffect(() => {
    if (!prefsReady) return
    if (skipPrefsSave.current) {
      skipPrefsSave.current = false
      return
    }
    const handle = window.setTimeout(() => {
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
    }, 300)
    return () => window.clearTimeout(handle)
  }, [pins, resolvedHiddenIds, hostname, sectionState, prefsReady])

  useEffect(() => {
    const onSettings = () => setSettingsTick((n) => n + 1)
    window.addEventListener(AGENT_SETTINGS_CHANGED_EVENT, onSettings)
    return () => window.removeEventListener(AGENT_SETTINGS_CHANGED_EVENT, onSettings)
  }, [])

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
    return excludePinnedFromList(
      [...supportRows, ...cliRows, ...apiRows, ...teamRows, ...remoteRows, ...otherRows],
      pins,
    )
  }, [supportAgents, cliAgents, apiAgents, visibleRootTeams, visibleRemotes, otherAgents, pins])
  const orderedRows = useMemo(
    () => applyRailOrder(catalogRows, railOrder),
    [catalogRows, railOrder],
  )
  const sectionBlocks = useMemo(() => {
    const baseBlocks = partitionRowsBySection(orderedRows, sectionState)
    if (dynamicSubagents.length === 0) return baseBlocks

    const dynamicIds = new Set(dynamicSubagents.map((s) => s.id))
    const subagentRows: RailRow[] = []

    const updatedBlocks = baseBlocks.map((block) => {
      if (block.id === UNASSIGNED_SECTION_ID) {
        const standardRows: RailRow[] = []
        for (const row of block.rows) {
          if (dynamicIds.has(row.id)) {
            subagentRows.push(row)
          } else {
            standardRows.push(row)
          }
        }
        return { ...block, rows: standardRows }
      }
      return block
    })

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
  }, [orderedRows, sectionState, dynamicSubagents, subagentsCollapsed])
  const visibleRowIds = useMemo(() => orderedRows.map((row) => row.id), [orderedRows])
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
    () => computeRailHotkeyTargets({ visiblePins, orderedRows }),
    [visiblePins, orderedRows],
  )

  const navScrollRef = useRef<HTMLElement | null>(null)
  const [canScroll, setCanScroll] = useState(false)

  const updateCanScroll = useCallback(() => {
    const el = navScrollRef.current
    if (!el) return
    const scrollable = el.scrollHeight > el.clientHeight
    setCanScroll(scrollable)
  }, [])

  useEffect(() => {
    updateCanScroll()
    const el = navScrollRef.current
    if (!el) return
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(updateCanScroll)
      ro.observe(el)
      return () => ro.disconnect()
    }
    return undefined
  }, [updateCanScroll, orderedRows.length, visiblePins.length])

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
    const onAltDigit = (event: KeyboardEvent) => {
      if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey && /^[1-9]$/.test(event.key)) {
        const idx = parseInt(event.key, 10) - 1
        const target = hotkeyTargets[idx]
        if (target) {
          event.preventDefault()
          if (target.isHerdr) {
            window.location.assign('/teams/#herdr-members')
          } else {
            navigate(target.href)
          }
          onClose?.()
        }
      }
    }
    window.addEventListener('keydown', onAltDigit)
    return () => window.removeEventListener('keydown', onAltDigit)
  }, [visiblePins, hotkeyTargets, navigate, onClose])

  const {
    openGroupPicker,
    closePicker,
    openCliSessionPicker,
    applyCliSession,
    continueCliSessionOn,
    selectSession,
    openAgentSessionPicker,
    startNewAgentSession,
  } = railSession

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

  const menuItems = menu
    ? railMenuItems({
        kind: menu.kind,
        pinned: menu.pinned,
        hidden: menu.hidden,
        unread: unreadIds.includes(menu.agentId),
        hasSelectAgent: shouldShowSelectAgent(menu.sessions),
        // #580: one declared capability drives the rail menu AND the navbar.
        hasSelectSession: seatHasSessions(menu),
        hasNewSession: seatHasSessions(menu),
        notifyEnabled: notifyIds.includes(menu.agentId),
        canCopyId:
          menu.kind === 'cli' || menu.kind === 'remote'
            ? Boolean(copyableConversationId(menu.kind, menu.agentId, menu.entityId))
            : true,
        cliRunning:
          cliRunningIds.has(menu.agentId) || peekCliRunning(menu.agentId),
        moveTo: {
          sections: sectionState.sections,
          currentSectionId: sectionIdForAgent(menu.agentId, sectionState),
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
    Link,
    NEEDS_APPROVAL_LABEL,
    PersonaRoster,
    RailRowSlot,
    StackedAvatars,
    Users,
    activeHerdrRow,
    activeRail,
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
    unreadIds,
    __ctx: null as unknown,
  })
  const railSectionsProps = {
    AgentAvatar,
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
      <button
        type="button"
        className={`fixed inset-0 z-30 bg-black/50 lg:hidden ${open ? '' : 'hidden'}`}
        hidden={!open}
        aria-label="Close agents sidebar"
        onClick={onClose}
      />

      <aside
        className={`os-agent-sidebar os-agent-sidebar--${railSide} fixed inset-y-0 ${
          railSide === 'right' ? 'right-0' : 'left-0'
        } z-40 flex shrink-0 flex-col transition-transform duration-200 lg:static lg:z-0 lg:translate-x-0 ${
          open
            ? 'translate-x-0'
            : railSide === 'right'
              ? 'translate-x-full'
              : '-translate-x-full'            } ${isAvatarOnly ? 'os-agent-sidebar--avatar-only' : ''} ${
          isCollapsed ? 'os-agent-sidebar--collapsed' : ''
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
          >
            {/* #555: collapse/expand lives on the divider, not in the pane
                header — the bee mark was doing the brand mark's job and the
                collapse button's job at once, and read as a logo that
                happened to collapse the pane. The pill overlays the edge (no
                width taken from the pane) and stays in the tab order: it
                reveals on hover *and* on focus, plus unconditionally on
                coarse pointers where hover does not exist. Its own
                pointerdown never reaches the resizer, so a drag that starts
                on the pill cannot resize. */}
            {/* #741: the pill is a handle now, not a click-only button that
                blocks the divider. Pointer-down records the origin and the
                window listeners watch for movement: past the slop it becomes
                a resize (funnelling into the same drag body as the strip).
                The toggle itself is intent-gated in handlePillToggle — the
                trailing click after a drag is the end of the resize, not a
                toggle. */}
            <span
              className="os-rail-divider-pill"
              data-testid="rail-divider-pill"
              onPointerDown={(event) => {
                if (narrow) return
                event.stopPropagation()
                const startX = event.clientX
                const pointerId = event.pointerId
                // React nulls currentTarget after the handler returns — the
                // drag body needs the element for pointer capture.
                const pillEl = event.currentTarget
                pillDraggedRef.current = false
                const onMove = (e: PointerEvent) => {
                  if (pillDraggedRef.current || Math.abs(e.clientX - startX) > 4) {
                    pillDraggedRef.current = true
                    window.removeEventListener('pointermove', onMove)
                    window.removeEventListener('pointerup', onUp)
                    beginResizeDrag(startX, pointerId, pillEl)
                  }
                }
                const onUp = () => {
                  window.removeEventListener('pointermove', onMove)
                  window.removeEventListener('pointerup', onUp)
                }
                window.addEventListener('pointermove', onMove)
                window.addEventListener('pointerup', onUp)
              }}
            >
              {isAvatarOnly ? (
                <SidebarExpandButton onClick={handlePillToggle} />
              ) : (
                <SidebarConcealButton onClick={handlePillToggle} />
              )}
            </span>
          </div>
        ) : null}
        {/* #555: the top of the pane is content now (search, sections, rows).
            Only the narrow-overlay drawer keeps a header, and only for its
            dismiss affordance. */}
        <div className="flex items-center justify-end gap-2 px-3 pt-3 lg:hidden">
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle lg:hidden"
            aria-label="Close agents sidebar"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
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
          <button
            type="button"
            className="os-search-add-btn"
            aria-label="Add agent"
            title="Add agent"
            data-testid="add-agent-button"
            onClick={() => setAddWizardOpen(true)}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

          <div
            className={`os-rail-scroll-fade pointer-events-none transition-opacity duration-150 ${
              canScroll ? 'opacity-100' : 'opacity-0'
            }`}
            data-testid="rail-scroll-fade"
            data-can-scroll={canScroll ? 'true' : 'false'}
            aria-hidden="true"
          />

          <RailSections {...railSectionsProps} />

        <div
          className={`os-hidden-bots ${hiddenCount === 0 ? 'os-hidden-bots--empty' : 'os-hide-drop--has-hidden'} ${
            hideDropActive ? 'os-hidden-bots--active' : ''
          }`}
          data-testid="hidden-bots-row"
          data-empty={hiddenCount === 0 ? 'true' : 'false'}
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
              <span className="os-hidden-bots-label font-medium">Hidden Agents</span>
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
          ) : null}
        </div>

        <div className="border-t border-base-300/70 px-3 py-3" data-testid="sidebar-footer-container">
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
              {/* #182: Teams entry lives in the rail footer, directly above Plugins. */}
              <button
                type="button"
                className="os-rail-footer-btn flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
                onClick={() => window.dispatchEvent(new CustomEvent(OPEN_TEAM_COMPOSER_EVENT))}
                title="Teams"
                aria-label="Teams"
                aria-haspopup="dialog"
                data-testid="os-teams-button"
              >
                <Users className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="os-teams-label">Teams</span>
              </button>
              <button
                type="button"
                className="os-rail-footer-btn flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
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
                className="os-rail-footer-btn flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
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
                  className="os-rail-hostname-icon btn btn-ghost btn-xs btn-square h-5 w-5 min-h-0 text-base-content/60 hover:text-base-content relative"
                  aria-label="Remote sessions"
                  aria-expanded={remotesPopupOpen}
                  aria-haspopup="menu"
                  data-testid="rail-server-icon"
                  onClick={() => setRemotesPopupOpen((open) => !open)}
                >
                  <Server className="h-3.5 w-3.5" aria-hidden="true" />
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

      <PluginsPopup open={pluginsOpen} onClose={() => setPluginsOpen(false)} />
      <AgentCalendarView
        open={calendarOpen}
        onClose={() => setCalendarOpen(false)}
        agents={agents}
      />

      <SessionPicker
        open={Boolean(picker)}
        title={picker?.title ?? ''}
        sessions={picker?.sessions ?? []}
        onClose={closePicker}
        onSelect={selectSession}
      />

      <SessionPicker
        open={sessionPicker !== null}
        agentName={sessionPicker?.agentName ?? ''}
        sessions={sessionPicker?.sessions ?? []}
        onClose={() => setSessionPicker(null)}
        onNewSession={() => {
          const agentId = sessionPicker?.agentId
          if (agentId) void startNewAgentSession(agentId)
        }}
        onSelect={(session) => {
          const agentId = sessionPicker?.agentId || session.agentId
          setConversationIdForAgent(agentId, session.id)
          navigate(sessionHref(agentId, session.id))
          onClose?.()
        }}
      />

      <CliSessionPicker
        open={cliPicker !== null}
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
