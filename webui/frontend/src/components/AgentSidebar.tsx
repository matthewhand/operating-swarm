import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type TouchEvent as ReactTouchEvent,
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
export const OPEN_CALENDAR_EVENT = 'open-calendar-view'
import AddAgentWizard, { type AgentKind } from './AddAgentWizard'
import {
  UNREAD_CHANGED_EVENT,
  loadUnreadAgentIds,
  markAgentRead,
  markAgentUnread,
} from '../lib/unreadAgents'
import {
  createCustomBlueprint,
  createRemote,
  createTeamRoster,
  deleteCustomBlueprint,
  deleteRemote,
  deleteTeamRoster,
  fetchBlueprints,
  fetchCliAgents,
  fetchCliRunStatus,
  fetchDesignedAgents,
  fetchHerdrAgents,
  fetchRemotes,
  terminateCliRun,
  type Blueprint,
  type CliRailAgent,
  type HerdrAgent,
  type RemoteConnection,
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
  canHideAgent,
  hasHiddenAgentsStorage,
  hideAgentId,
  loadHiddenAgentIds,
  loadOrSeedHiddenAgentIds,
  reconcileHiddenAgentIds,
  unhideAgentId,
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
  beginRailDrag,
  bumpRailIdToTop,
  endRailDrag,
  generationCompleteAgentId,
  generationCompleteDetail,
  insertRailIdAfter,
  loadRailOrder,
  mergeRailOrder,
  moveRailId,
  moveRailIdAfter,
  dropHalfFromClientY,
  peekRailDrag,
  saveRailOrder,
} from '../lib/railOrder'
import {
  FOCUS_AGENT_EVENT,
  NOTIFY_CHANGED_EVENT,
  NOTIFY_HINT_COPY,
  chatHrefForRowId,
  disableAgentNotify,
  enableAgentNotifications,
  isAgentNotifyEnabled,
  loadNotifyAgentIds,
  maybeNotifyAgentTurn,
} from '../lib/agentNotifications'
import type { NotifyEnableOutcome } from '../lib/agentNotifications'
import {
  BUMP_COMPLETED_EVENT,
  BUMP_SCOPE_EVENT,
  loadBumpCompleted,
  loadBumpScope,
  type BumpScope,
  saveHostnameOverride,
} from '../lib/settingsPrefs'
import { computeRailHotkeyTargets, herdrChatHref } from '../lib/railHotkeys'
import {
  endAgentDrag,
  excludePinnedFromList,
  loadOrSeedPinnedAgents,
  movePinnedAgent,
  parseAgentDragPayload,
  pinAgent,
  type PinnedAgent,
  unpinAgent,
  writeAgentDragPayload,
} from '../lib/pinnedAgents'
import { hydrateRailPrefs, persistAgentDropdownChoice, saveUserPrefs } from '../lib/userPrefs'
import {
  loadAllAgentSessions,
  SCALE_OUT_SESSIONS_EVENT,
  sessionHref,
  shouldOpenSessionPicker,
  type AgentSession,
} from '../lib/scaleOutSessions'
import { agentLabel, defaultBlueprintId, isSupportAgent } from '../lib/supportAgent'
import { seatHasSessions } from '../lib/seatCapabilities'
import { AGENT_CHAT_SESSIONS_EVENT } from '../lib/agentChatSessions'
import {
  agentBubbleThemeOverrides,
  loadBubbleTheme,
  setAgentBubbleTheme,
  type BubbleTheme,
} from '../lib/bubbleTheme'
import { formatRailTimestamp, getRowLastMessage } from '../lib/chatTime'
import { fetchTeamRosters, parseTeamRosters, teamHideId, type TeamRoster } from '../lib/teamRosters'
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId, type RemoteEntry } from '../lib/remotesCatalog'
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
  type StackFace,
} from '../lib/avatarStack'
import {
  defaultSessionForRemote,
  defaultSessionForTeam,
  sessionsForRemote,
  sessionsForTeam,
  shouldShowSelectAgent,
  stackFacesForRemote,
  stackFacesForTeam,
  type MemberSession,
} from '../lib/sessionPicker'
import {
  AGENT_SETTINGS_CHANGED_EVENT,
  loadLocalNewChatPerTask,
  openAgentEditor,
} from '../lib/agentSettings'
import { createAgentSession, loadPickerSessions } from '../lib/agentSessions'
import {
  AGENT_CONVERSATION_EVENT,
  activeTaskSessionCount,
  agentChatHref,
  conversationIdForAgent,
  setConversationIdForAgent,
} from '../lib/agentChat'
import {
  RAIL_LONG_PRESS_MS,
  copyableConversationId,
  duplicateName,
  duplicateRemoteId,
  isRailMenuKey,
  paneMenuItems,
  railMenuItems,
  sectionMenuItems,
  type RailMenuItemId,
  type RailMenuKind,
} from '../lib/railContextMenu'
import {
  NEW_SECTION_TARGET,
  createSection,
  createSectionWithAgent,
  deleteSection,
  isUnassignedSection,
  loadRailSections,
  railSectionsHasContent,
  moveAgentToSection,
  moveSection,
  partitionRowsBySection,
  removeSectionMembership,
  renameSection,
  sectionIdForAgent,
  toggleSectionCollapsed,
  toggleSectionInternalOnly,
  UNASSIGNED_SECTION_ID,
  type RailSectionsState,
} from '../lib/railSections'
import { copyTextToClipboard } from '../lib/clipboard'
import {
  isRailIdDeleted,
  loadDeletedRailIds,
  markRailIdDeleted,
} from '../lib/deletedRailIds'
import { openSearchPalette, type HiddenRailRow } from './SearchPalette'
import { isMacPlatform, searchShortcutLabel } from '../lib/keybindingTips'
import {
  AGENT_EDITS_CHANGED_EVENT,
  assignedBlueprintId,
  loadAgentEdit,
  saveAgentEdit,
} from '../lib/agentEdits'
import { persistSessionWorkspace } from '../lib/agentWorkspace'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import { declaredRosterForTeam, type DeclaredTeamRoster } from '../lib/declaredRoster'
import { openTeamEditor } from './TeamEditor'
import PersonaRoster from './PersonaRoster'
import SessionPicker from './SessionPicker'
import CliSessionPicker from './CliSessionPicker'
import {
  dispatchCliSessionSwitched,
  fetchCliSessions,
  latestCliActivityMs,
  selectCliSession,
  type CliProviderSession,
} from '../lib/cliSessions'
import {
  dispatchCliSessionHopped,
  hopCliSession,
  hopContinueTargets,
} from '../lib/cliSessionHop'
import { FALLBACK_CLIS } from '../lib/chatStatus'
import PluginsPopup from './PluginsPopup'
import { OPEN_TEAM_COMPOSER_EVENT, TEAM_CREATED_EVENT } from './TeamComposer'
import { openSettingsSheet } from './SettingsSheet'
import { OPEN_PLUGINS_EVENT } from '../lib/chromeOverlay'
import { useCurrentAgent, isSwarmOwnedSeat } from '../lib/currentAgent'
import { ConfirmModal } from './DaisyUI'
import RailContextMenu from './RailContextMenu'
import RailSectionHeader, { RailSectionEmpty } from './RailSectionHeader'
import StackedAvatars from './StackedAvatars'
import {
  clampRailWidth,
  snapRailWidth,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  MIN_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  DEFAULT_RAIL_WIDTH,
  isFullyCollapsedWidth,
  COLLAPSED_RAIL_WIDTH,
} from '../lib/railResize'
import { loadRailSide, RAIL_SIDE_EVENT, type RailSide } from '../lib/railSide'
import { SidebarConcealButton, SidebarExpandButton } from './SidepaneConceal'
import RailRowSlot from './RailRowSlot'

const EMPTY_BLUEPRINTS: Blueprint[] = []

/** REQ-912 (#511): verbatim copy requested for the disabled hover/reason. */
const API_ONLY_REASON = 'Currently only supported for OS API agents'

export interface AgentSidebarProps {
  /** Mobile drawer open. Desktop (lg+) is always visible. */
  open?: boolean
  /** Below Tailwind `lg` — drawer + inert when closed. */
  narrow?: boolean
  onClose?: () => void
  /** Agent / conversation / team pick — parent may tuck the rail (REQ-54). */
  onPick?: () => void
  onOpenSearch?: () => void
  blueprints?: Blueprint[]
}

interface ContextMenuState {
  agentId: string
  agentName: string
  hidden: boolean
  pinned: boolean
  x: number
  y: number
  kind: RailMenuKind
  entityId: string
  sessions?: MemberSession[]
  isCli?: boolean
  cli?: string
}

interface SectionMenuState {
  sectionId: string
  sectionName: string
  x: number
  y: number
}

interface CliPickerState {
  agentId: string
  agentName: string
  cli: string
  sessions: CliProviderSession[]
  canList: boolean
  emptyReason: string | null
  loading: boolean
}

interface SessionPickerState {
  agentId: string
  agentName: string
  sessions: AgentSession[]
}

/**
 * Rail seat view of a Blueprint. `kind` widens to `string | null` to match the
 * wire type (GET /v1/blueprints/ rows may send kind: null).
 */
type SidebarAgent = Blueprint & {
  kind?: string | null
  remote?: string
  cli?: string | null
}

type RailRow =
  | { kind: 'agent'; id: string; agent: SidebarAgent }
  | { kind: 'team'; id: string; team: TeamRoster }
  | { kind: 'remote'; id: string; remote: RemoteEntry }

function isHerdrAgent(agent: { id: string; kind?: string | null }): boolean {
  return agent.kind === 'herdr' || String(agent.id).startsWith('herdr:')
}

/** #546: which permission outcome to explain, and for which seat. */
interface NotifyOutcomeHint {
  agentId: string
  outcome: Exclude<NotifyEnableOutcome, 'granted'>
  requestFailed: boolean
}

function sidebarHref(agent: { id: string; kind?: string | null }): string {
  // #543: a herdr seat chats like every other kind — the agent name rides the
  // remote-harness session param. Settings' member roster stays reachable from
  // the row menu, not from stealing the row's primary click.
  if (isHerdrAgent(agent)) return herdrChatHref(agent.id)
  return agentChatHref(agent.id)
}

function toSidebarCli(row: CliRailAgent): SidebarAgent {
  const kind = row.kind === 'api' ? 'api' : 'cli'
  return {
    id: row.id,
    object: 'blueprint',
    name: row.name,
    description:
      kind === 'cli' && !row.installed ? `${row.description} (not on PATH)` : row.description,
    abbreviation: null,
    required_mcp_servers: [],
    tags: [kind],
    installed: row.installed,
    compiled: true,
    kind,
    cli: row.cli,
    rail: true,
  }
}

/** Named kind rows (cli_agent, api_agent) stay on the rail. */
function isCliRailAgent(agent: { id?: string; kind?: string | null }): boolean {
  return agent.kind === 'cli'
}

function isApiRailAgent(agent: { id?: string; kind?: string | null }): boolean {
  return agent.kind === 'api' || agent.id === 'api_agent'
}

function isBlueprintRailAgent(agent: { id?: string; kind?: string | null }): boolean {
  return agent.kind === 'blueprint'
}

function toSidebarHerdr(row: HerdrAgent): SidebarAgent {
  return {
    id: `herdr:${row.name}`,
    object: 'blueprint',
    name: row.name,
    description: row.remote ? `Herdr · ${row.remote}` : 'Herdr · localhost',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    kind: 'herdr',
    remote: row.remote || '',
    rail: true,
  }
}

function toSidebarDynamic(subagent: DynamicSubagent): SidebarAgent {
  return {
    id: subagent.id,
    object: 'blueprint',
    name: subagent.name || subagent.id,
    description:
      subagent.summary || subagent.task || `Dynamic subagent (${subagent.role || 'subagent'})`,
    abbreviation: null,
    required_mcp_servers: [],
    tags: ['subagent', 'dynamic'],
    installed: true,
    compiled: true,
    role: subagent.role || 'subagent',
    kind: 'subagent',
    rail: true,
    avatar_path: subagent.avatar_path,
    // #843: spawn/execution time feeds the rail's time slot — previously
    // dropped here, which is why subagent rows never showed a timestamp.
    last_message_at: subagent.timestamp ?? null,
  }
}

interface PickerState {
  title: string
  sessions: MemberSession[]
}

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

  // #816: which edge the rail docks to ('left' historical default).
  const [railSide, setRailSideState] = useState<RailSide>(() => loadRailSide())
  useEffect(() => {
    // The setting can flip from the settings sheet — follow it live.
    const sync = () => setRailSideState(loadRailSide())
    window.addEventListener(RAIL_SIDE_EVENT, sync)
    return () => window.removeEventListener(RAIL_SIDE_EVENT, sync)
  }, [])

  const [railWidth, setRailWidth] = useState(() => loadRailWidth())
  const [isResizing, setIsResizing] = useState(false)
  const isAvatarOnly = !narrow && isAvatarOnlyWidth(railWidth)
  // #765: the divider-only state — the pane body collapses entirely and only
  // the border spine + the expand pill remain (a strict subset of avatar-only).
  const isCollapsed = !narrow && isFullyCollapsedWidth(railWidth)

  const concealSidebar = useCallback(() => {
    if (narrow) {
      onClose?.()
      return
    }
    // #765: conceal now means the full edge collapse — 0px, divider only.
    setRailWidth(COLLAPSED_RAIL_WIDTH)
    saveRailWidth(COLLAPSED_RAIL_WIDTH)
  }, [narrow, onClose])

  const expandSidebar = useCallback(() => {
    setRailWidth(DEFAULT_RAIL_WIDTH)
    saveRailWidth(DEFAULT_RAIL_WIDTH)
  }, [])

  // #741: the pill button's click is intent-gated — after a drag from the
  // pill, the trailing click gesture is the END of the resize, not a toggle.
  const handlePillToggle = useCallback(() => {
    if (pillDraggedRef.current) {
      pillDraggedRef.current = false
      return
    }
    if (isAvatarOnly) {
      expandSidebar()
    } else {
      concealSidebar()
    }
  }, [isAvatarOnly, expandSidebar, concealSidebar])

  const startDragXRef = useRef(0)
  const startWidthRef = useRef(railWidth)
  // #741: set when a drag started on the pill — the follow-up click must be
  // swallowed so the toggle does not fire at drag end.
  const pillDraggedRef = useRef(false)

  // #741: shared drag body — the resizer strip and the pill (via intent
  // detection) both funnel here, so a grab anywhere on the divider resizes.
  const beginResizeDrag = useCallback(
    (startClientX: number, pointerId: number, target: HTMLElement | null) => {
      setIsResizing(true)
      startDragXRef.current = startClientX
      startWidthRef.current = railWidth
      try {
        target?.setPointerCapture(pointerId)
      } catch {}

      // #816: on the right edge the row grows leftwards, so the pointer
      // vector mirrors (negative delta = wider).
      const direction = railSide === 'right' ? -1 : 1

      const handlePointerMove = (e: PointerEvent) => {
        const delta = e.clientX - startDragXRef.current
        // #806: snapping clamp — the avatar-only dead zone is gone.
        const next = snapRailWidth(
          startWidthRef.current + direction * delta,
          window.innerWidth,
        )
        setRailWidth(next)
      }

      const handlePointerUp = (e: PointerEvent) => {
        setIsResizing(false)
        try {
          target?.releasePointerCapture(e.pointerId)
        } catch {}
        window.removeEventListener('pointermove', handlePointerMove)
        window.removeEventListener('pointerup', handlePointerUp)
        window.removeEventListener('pointercancel', handlePointerUp)
        const finalDelta = e.clientX - startDragXRef.current
        // #806: snap on release too, so persistence agrees with the drag.
        const finalWidth = snapRailWidth(
          startWidthRef.current + direction * finalDelta,
          window.innerWidth,
        )
        setRailWidth(finalWidth)
        saveRailWidth(finalWidth)
      }

      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', handlePointerUp)
      window.addEventListener('pointercancel', handlePointerUp)
    },
    [railWidth, railSide],
  )

  const handleResizeStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      beginResizeDrag(event.clientX, event.pointerId, event.currentTarget)
    },
    [beginResizeDrag],
  )

  const handleResizeKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      // #816: arrows mirror on the right rail — the grow arrow always points
      // toward the content side.
      const growDelta = railSide === 'right' ? -12 : 12
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setRailWidth((prev) => {
          const next = clampRailWidth(prev - growDelta, window.innerWidth)
          saveRailWidth(next)
          return next
        })
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setRailWidth((prev) => {
          const next = clampRailWidth(prev + growDelta, window.innerWidth)
          saveRailWidth(next)
          return next
        })
      } else if (event.key === 'Home') {
        event.preventDefault()
        // #765: Home walks all the way to the collapsed divider-only state.
        setRailWidth(COLLAPSED_RAIL_WIDTH)
        saveRailWidth(COLLAPSED_RAIL_WIDTH)
      } else if (event.key === 'End') {
        event.preventDefault()
        const max = clampRailWidth(MAX_RAIL_WIDTH, window.innerWidth)
        setRailWidth(max)
        saveRailWidth(max)
      }
    },
    [railSide],
  )

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

  useEffect(() => {
    if (!prefsReady) return
    if (skipPrefsSave.current) {
      skipPrefsSave.current = false
      return
    }
    const handle = window.setTimeout(() => {
      const override =
        hostname.trim() === defaultHostname() ? '' : hostname.trim()
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

  const closeMenu = useCallback(() => {
    setMenu(null)
    setSectionMenu(null)
    setPaneMenu(null)
  }, [])

  const commitSectionRename = useCallback(() => {
    if (!editingSectionId) return
    setSectionState((current) => renameSection(current, editingSectionId, editingSectionName))
    setEditingSectionId(null)
    setEditingSectionName('')
  }, [editingSectionId, editingSectionName])

  const cancelSectionRename = useCallback(() => {
    setEditingSectionId(null)
    setEditingSectionName('')
  }, [])

  const startSectionRename = useCallback((sectionId: string, name: string) => {
    setEditingSectionId(sectionId)
    setEditingSectionName(name)
    setSectionMenu(null)
  }, [])

  const handleMoveTo = useCallback(
    (agentId: string, target: string) => {
      if (!agentId) return
      // #801: a pinned agent moved to a section must LEAVE the pin grid —
      // excludePinnedFromList strips pinned ids from the section lists, so
      // keeping the pin would park the agent in limbo (membership set, row
      // rendered nowhere). Unpinning matches drag-to-section behavior.
      const wasPinned = isPinnedId(agentId)
      if (wasPinned) {
        setPins((current) =>
          current.some((pin) => pin.id === agentId) ? unpinAgent(agentId, current) : current,
        )
      }
      if (target === NEW_SECTION_TARGET) {
        const created = createSectionWithAgent(sectionState, agentId)
        setSectionState(created.state)
        startSectionRename(created.section.id, created.section.name)
        closeMenu()
        return
      }
      setSectionState((current) => moveAgentToSection(current, agentId, target))
      closeMenu()
    },
    [closeMenu, sectionState, startSectionRename],
  )

  /** #724: dispatch the per-agent bubble-theme override from the rail menu. */
  const handleBubbleTheme = useCallback(
    (agentId: string, theme: string) => {
      if (!agentId) return
      setAgentBubbleTheme(agentId, theme === '__default__' ? null : (theme as BubbleTheme))
      closeMenu()
    },
    [closeMenu],
  )

  const openSectionMenuAt = useCallback(
    (sectionId: string, sectionName: string, clientX: number, clientY: number) => {
      if (isUnassignedSection(sectionId)) return
      const pad = 8
      const width = 200
      const height = 220
      const x = Math.min(clientX, window.innerWidth - width - pad)
      const y = Math.min(clientY, window.innerHeight - height - pad)
      setMenu(null)
      setSectionMenu({
        sectionId,
        sectionName,
        x: Math.max(pad, x),
        y: Math.max(pad, y),
      })
    },
    [],
  )

  const handleSectionMenuSelect = useCallback(
    (id: RailMenuItemId) => {
      if (!sectionMenu) return
      const { sectionId, sectionName } = sectionMenu
      if (id === 'section-create') {
        const created = createSection(sectionState)
        setSectionState(created.state)
        closeMenu()
        startSectionRename(created.section.id, created.section.name)
        return
      }
      if (id === 'section-rename') {
        startSectionRename(sectionId, sectionName)
        return
      }
      if (id === 'section-talk-lock') {
        setSectionState((current) => toggleSectionInternalOnly(current, sectionId))
        closeMenu()
        return
      }
      if (id === 'section-move-up') {
        setSectionState((current) => moveSection(current, sectionId, 'up'))
        closeMenu()
        return
      }
      if (id === 'section-move-down') {
        setSectionState((current) => moveSection(current, sectionId, 'down'))
        closeMenu()
        return
      }
      if (id === 'section-delete') {
        setSectionState((current) => deleteSection(current, sectionId))
        if (editingSectionId === sectionId) cancelSectionRename()
        closeMenu()
      }
    },
    [cancelSectionRename, closeMenu, editingSectionId, sectionMenu, sectionState, startSectionRename],
  )

  // #172: right-click the rail background to create a fresh empty section.
  // Drag any agent/pin onto its header to move it in (dropOnSection accepts
  // both rows and pinned ids), so sections can group a "locked comms" roster.
  const openPaneMenuAt = useCallback((clientX: number, clientY: number) => {
    const pad = 8
    const width = 200
    const height = 160
    const x = Math.min(clientX, window.innerWidth - width - pad)
    const y = Math.min(clientY, window.innerHeight - height - pad)
    setMenu(null)
    setSectionMenu(null)
    setPaneMenu({ x: Math.max(pad, x), y: Math.max(pad, y) })
  }, [])

  const handlePaneMenuSelect = useCallback(
    (id: RailMenuItemId) => {
      if (id !== 'section-create') return
      const created = createSection(sectionState)
      setSectionState(created.state)
      closeMenu()
      startSectionRename(created.section.id, created.section.name)
    },
    [closeMenu, sectionState, startSectionRename],
  )

  const toggleNotify = useCallback(
    async (agentId: string) => {
      if (!agentId) {
        closeMenu()
        return
      }
      if (isAgentNotifyEnabled(agentId, notifyIds)) {
        setNotifyIds(disableAgentNotify(agentId, notifyIds))
        closeMenu()
        return
      }
      const result = await enableAgentNotifications(agentId)
      setNotifyIds(result.ids)
      closeMenu()
      if (result.outcome !== 'granted') {
        setNotifyHint({
          agentId,
          outcome: result.outcome,
          requestFailed: result.requestFailed,
        })
      }
    },
    [closeMenu, notifyIds],
  )

  /** #546: re-ask. `never-asked` means the prompt did not appear, so it is worth
   *  another attempt rather than a dead-end sentence. */
  const retryNotifyPermission = useCallback(async () => {
    if (!notifyHint) return
    const result = await enableAgentNotifications(notifyHint.agentId)
    setNotifyIds(result.ids)
    if (result.outcome === 'granted') {
      setNotifyHint(null)
      return
    }
    setNotifyHint({
      agentId: notifyHint.agentId,
      outcome: result.outcome,
      requestFailed: result.requestFailed,
    })
  }, [notifyHint])

  const openPalette = useCallback(() => {
    onOpenSearch?.()
    // #549: keep the palette's hidden universe in sync with the badge even when
    // the palette is opened from search rather than the Hidden Agents row.
    openSearchPalette({ hiddenIds: resolvedHiddenIds, hiddenRows: hiddenRailRows })
  }, [onOpenSearch, resolvedHiddenIds, hiddenRailRows])

  const openGroupPicker = useCallback((title: string, sessions: MemberSession[]) => {
    setPicker({ title, sessions })
  }, [])

  // #748: the rail no longer hosts a remote session browser — rows navigate
  // immediately and the chat header owns session switching.
  const closePicker = useCallback(() => setPicker(null), [])

  const openCliSessionPicker = useCallback(
    async (agentId: string, agentName: string, cli: string) => {
      const cliName = cli || 'grok'
      setCliPicker({
        agentId,
        agentName,
        cli: cliName,
        sessions: [],
        canList: false,
        emptyReason: null,
        loading: true,
      })
      try {
        const list = await fetchCliSessions(agentId, cliName)
        setCliPicker({
          agentId,
          agentName,
          cli: list.cli || cliName,
          sessions: list.sessions,
          canList: list.can_list,
          emptyReason: list.empty_reason,
          loading: false,
        })
      } catch (err) {
        const message = err instanceof Error && err.message
          ? err.message
          : "This CLI can't list sessions"
        const folderFailed = /folder/i.test(message)
        if (folderFailed) {
          toast?.error('Could not list CLI sessions', message)
        }
        setCliPicker({
          agentId,
          agentName,
          cli: cliName,
          sessions: [],
          canList: false,
          emptyReason: folderFailed ? message : "This CLI can't list sessions",
          loading: false,
        })
      }
    },
    [toast],
  )

  const applyCliSession = useCallback(
    async (opts: {
      agentId: string
      cli: string
      session?: CliProviderSession
      startNew?: boolean
    }) => {
      try {
        const hintFolder = (opts.session?.folder || '').trim()
        // Provider folder hints may be escaped slugs (qwen), not real paths —
        // only forward/persist values that look like paths; the backend
        // resolves the session cwd otherwise.
        const sessionFolder =
          hintFolder.startsWith('/') || hintFolder.startsWith('~') ? hintFolder : ''
        const result = await selectCliSession({
          agentId: opts.agentId,
          cli: opts.cli,
          sessionId: opts.session?.id,
          startNew: opts.startNew,
          fromConversationId: conversationIdForAgent(opts.agentId),
          title: opts.session?.title,
          snippet: opts.session?.snippet,
          folder: sessionFolder || undefined,
        })
        const resultFolder = (result.folder || '').trim()
        const effectiveFolder = resultFolder || sessionFolder
        persistSessionWorkspace(opts.agentId, {
          folder: effectiveFolder,
          gitBranch: result.git_branch,
        })
        dispatchCliSessionSwitched({
          agentId: opts.agentId,
          conversationId: result.conversation_id,
          status: result.status,
        })
        navigate(sessionHref(opts.agentId, result.conversation_id))
        onClose?.()
      } catch (err) {
        const message = err instanceof Error && err.message
          ? err.message
          : 'Could not switch session'
        toast?.error('Could not start CLI session', message)
        setCliPicker((current) =>
          current
            ? { ...current, emptyReason: message }
            : current,
        )
      }
    },
    [navigate, onClose, toast],
  )

  const continueCliSessionOn = useCallback(
    async (opts: { agentId: string; fromCli: string; session: CliProviderSession; toCli: string }) => {
      try {
        const hop = await hopCliSession({
          agentId: opts.agentId,
          fromCli: opts.fromCli,
          toCli: opts.toCli,
          conversationId: conversationIdForAgent(opts.agentId),
          importSessionId: opts.session.id,
          kind: 'cli',
        })
        dispatchCliSessionHopped({
          agentId: opts.agentId,
          conversationId: hop.conversation_id,
          status: hop.status,
          fromCli: hop.from_cli,
          toCli: hop.to_cli,
        })
        persistAgentDropdownChoice(opts.agentId, { cli: opts.toCli })
        const href = sessionHref(
          opts.agentId,
          hop.conversation_id || conversationIdForAgent(opts.agentId),
        )
        navigate(`${href}&cli=${encodeURIComponent(opts.toCli)}`)
        onClose?.()
      } catch {
        setCliPicker((current) =>
          current
            ? {
                ...current,
                emptyReason:
                  current.emptyReason ||
                  `${opts.fromCli} cannot export that session — try summary hop from the CLI dropdown.`,
              }
            : current,
        )
      }
    },
    [navigate, onClose],
  )

  const selectSession = useCallback(
    (session: MemberSession) => {
      setPicker(null)
      navigate(session.href)
      onClose?.()
    },
    [navigate, onClose],
  )

  const openAgentSessionPicker = useCallback(
    async (agentId: string, agentName: string) => {
      const sessions = await loadPickerSessions(agentId)
      setSessionPicker({ agentId, agentName, sessions })
    },
    [],
  )

  const startNewAgentSession = useCallback(
    async (agentId: string) => {
      const created = await createAgentSession(agentId)
      const nextId = created?.id
      if (!nextId) return
      navigate(sessionHref(agentId, nextId))
      onClose?.()
    },
    [navigate, onClose],
  )

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

  const resolveMenuKind = (hideId: string, hinted?: RailMenuKind): RailMenuKind => {
    if (hinted) return hinted
    if (hideId.startsWith('team:')) return 'team'
    if (hideId.startsWith('remote:')) return 'remote'
    const agent = agents.find((row) => row.id === hideId)
    if (agent && isCliRailAgent(agent)) return 'cli'
    // #543: herdr rows get their own menu kind — no Edit/Duplicate (no
    // swarm-owned profile), no swarm conversation id, matching 'remote'.
    if (agent && isHerdrAgent(agent)) return 'herdr'
    if ((agent as unknown as { kind?: string })?.kind === 'blueprint') return 'blueprint'
    return 'api'
  }

  const openMenuAt = (
    clientX: number,
    clientY: number,
    hideId: string,
    label: string,
    hidden: boolean,
    kind?: RailMenuKind,
    sessions?: MemberSession[],
    entityId?: string,
  ) => {
    const pad = 8
    const width = 220
    const height = 320
    const x = Math.min(clientX, window.innerWidth - width - pad)
    const y = Math.min(clientY, window.innerHeight - height - pad)
    const resolvedKind = resolveMenuKind(hideId, kind)
    const row = agents.find((agent) => agent.id === hideId)
    const isCli = resolvedKind === 'cli' || Boolean(row && isCliRailAgent(row))
    const cliFromUrl = searchParams.get('cli') || ''
    const cliName = (isCli && (cliFromUrl || row?.cli)) || ''
    setSectionMenu(null)
    setMenu({
      agentId: hideId,
      agentName: label,
      hidden,
      pinned: pins.some((pin) => pin.id === hideId),
      x: Math.max(pad, x),
      y: Math.max(pad, y),
      kind: resolvedKind,
      entityId: entityId || hideId,
      sessions,
      isCli,
      cli: cliName,
    })
    if (isCli) {
      void fetchCliRunStatus(hideId)
        .then((status) => {
          setCliRunningIds((current) => {
            const next = new Set(current)
            if (status.running) next.add(hideId)
            else next.delete(hideId)
            return next
          })
        })
        .catch(() => {
          /* keep event-sourced state */
        })
    }
  }

  const clearLongPress = () => {
    if (longPressRef.current.timer != null) {
      window.clearTimeout(longPressRef.current.timer)
      longPressRef.current.timer = null
    }
  }

  const rowMenuHandlers = (
    hideId: string,
    label: string,
    hidden: boolean,
    kind?: RailMenuKind,
    sessions?: MemberSession[],
    entityId?: string,
  ) => ({
    onContextMenu: (event: ReactMouseEvent) => {
      event.preventDefault()
      openMenuAt(event.clientX, event.clientY, hideId, label, hidden, kind, sessions, entityId)
    },
    onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => {
      if (!isRailMenuKey(event)) return
      event.preventDefault()
      const rect = event.currentTarget.getBoundingClientRect()
      openMenuAt(rect.left + 12, rect.bottom, hideId, label, hidden, kind, sessions, entityId)
    },
    onTouchStart: (event: ReactTouchEvent<HTMLElement>) => {
      const touch = event.touches[0]
      if (!touch) return
      longPressRef.current.opened = false
      clearLongPress()
      longPressRef.current.timer = window.setTimeout(() => {
        longPressRef.current.opened = true
        openMenuAt(touch.clientX, touch.clientY, hideId, label, hidden, kind, sessions, entityId)
      }, RAIL_LONG_PRESS_MS)
    },
    onTouchEnd: (event: ReactTouchEvent<HTMLElement>) => {
      clearLongPress()
      if (longPressRef.current.opened) {
        event.preventDefault()
      }
    },
    onTouchMove: () => {
      clearLongPress()
    },
  })

  const finishDrag = () => {
    endAgentDrag()
    endRailDrag()
    setDraggingId(null)
    setDropTargetId(null)
    setSectionDropId(null)
    setDropActive(false)
    setListDropActive(false)
    setHideDropActive(false)
    setBinDragOver(false)
    hideDropDepth.current = 0
  }

  // #725: global safety net — if the browser never delivers `onDragEnd` to the
  // React element (pointer left the window, OS cancelled the drag, or a
  // re-render during a 429 storm orphaned the handler) draggingId would stay
  // set forever. The window-level listener catches it regardless of source.
  useEffect(() => {
    if (!draggingId) return
    const onGlobalDragEnd = () => finishDrag()
    const onVisibilityHide = () => { if (document.visibilityState === 'hidden') finishDrag() }
    window.addEventListener('dragend', onGlobalDragEnd)
    document.addEventListener('visibilitychange', onVisibilityHide)
    return () => {
      window.removeEventListener('dragend', onGlobalDragEnd)
      document.removeEventListener('visibilitychange', onVisibilityHide)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draggingId])


  const isPinnedId = (id: string | null | undefined) =>
    Boolean(id && pins.some((pin) => pin.id === id))

  /**
   * Hide conceals the id from the conversation list and the visible favourite
   * grid. The pin stays in swarm_pinned_agents so Unhide restores the same
   * favourite slot. Role agents (support, gate, skeptic) are not exempt.
   */
  const hideFromRail = (id: string) => {
    if (!id || !canHideAgent(id)) return
    setHiddenIds((current) => hideAgentId(id, current ?? resolvedHiddenIds))
  }

  const hideAgent = (id: string) => {
    hideFromRail(id)
    closeMenu()
  }

  const unhideAgent = (id: string) => {
    setHiddenIds((current) => unhideAgentId(id, current ?? resolvedHiddenIds))
    closeMenu()
  }

  const togglePin = (agent: { id: string; name: string }) => {
    setPins((current) =>
      current.some((pin) => pin.id === agent.id)
        ? unpinAgent(agent.id, current)
        : pinAgent(agent, current),
    )
    closeMenu()
  }

  const dropPin = (event: ReactDragEvent) => {
    event.preventDefault()
    const payload = parseAgentDragPayload(event.dataTransfer)
    setDropActive(false)
    finishDrag()
    if (!payload) return
    // Already-pinned drops on empty grid space are a no-op; tile drops reorder.
    setPins((current) =>
      current.some((pin) => pin.id === payload.id) ? current : pinAgent(payload, current),
    )
  }

  const dropPinReorder = (event: ReactDragEvent, beforeId: string) => {
    event.preventDefault()
    event.stopPropagation()
    const payload = parseAgentDragPayload(event.dataTransfer)
    finishDrag()
    if (!payload?.id || payload.id === beforeId) return
    setPins((current) => {
      if (current.some((pin) => pin.id === payload.id)) {
        return movePinnedAgent(payload.id, beforeId, current)
      }
      return pinAgent(payload, current)
    })
  }

  const dropUnfavourite = (event: ReactDragEvent) => {
    event.preventDefault()
    const payload = parseAgentDragPayload(event.dataTransfer)
    finishDrag()
    if (!payload?.id) return
    setPins((current) =>
      current.some((pin) => pin.id === payload.id) ? unpinAgent(payload.id, current) : current,
    )
  }

  const allowListUnfavourite = (event: ReactDragEvent) => {
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (!isPinnedId(fromId)) return
    event.preventDefault()
    try {
      event.dataTransfer.dropEffect = 'move'
    } catch {
      /* synthetic events may omit dataTransfer */
    }
    setListDropActive(true)
  }

  const dropHide = (event: ReactDragEvent) => {
    event.preventDefault()
    const payload = parseAgentDragPayload(event.dataTransfer)
    finishDrag()
    if (!payload?.id) return
    // Already hidden (or a drop that never left the source row) is a no-op.
    if (resolvedHiddenIds.includes(payload.id)) return
    hideFromRail(payload.id)
  }

  const allowRowDrop = (event: ReactDragEvent, targetId: string) => {
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (!fromId || fromId === targetId) {
      try {
        event.dataTransfer.dropEffect = 'none'
      } catch {
        /* synthetic events may omit dataTransfer */
      }
      return
    }
    event.preventDefault()
    try {
      event.dataTransfer.dropEffect = 'move'
    } catch {
      /* synthetic events may omit dataTransfer */
    }
    setDropTargetId(targetId)
  }

  const dropReorder = (event: ReactDragEvent, targetId: string) => {
    event.preventDefault()
    event.stopPropagation()
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (fromId && fromId !== targetId) {
      const targetSection = sectionIdForAgent(targetId, sectionState)
      setSectionState((current) => moveAgentToSection(current, fromId, targetSection))
      // #761: relative placement — the pointer's half of the target row
      // decides above/below; dropping onto any row of a section also assigns
      // into that section (above). Pinned drops unpin into place either way.
      const half = dropHalfFromClientY(event.clientY, event.currentTarget.getBoundingClientRect())
      if (isPinnedId(fromId)) {
        setPins((current) => unpinAgent(fromId, current))
      }
      if (half === 'below') {
        reorderAfter(fromId, targetId)
      } else {
        reorderBefore(fromId, targetId)
      }
    }
    finishDrag()
  }

  const allowSectionDrop = (event: ReactDragEvent, sectionId: string) => {
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (!fromId) {
      try {
        event.dataTransfer.dropEffect = 'none'
      } catch {
        /* synthetic events may omit dataTransfer */
      }
      return
    }
    event.preventDefault()
    try {
      event.dataTransfer.dropEffect = 'move'
    } catch {
      /* synthetic events may omit dataTransfer */
    }
    setSectionDropId(sectionId)
  }

  const dropOnSection = (event: ReactDragEvent, sectionId: string) => {
    event.preventDefault()
    event.stopPropagation()
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (fromId) {
      if (isPinnedId(fromId)) {
        setPins((current) => unpinAgent(fromId, current))
      }
      setSectionState((current) => moveAgentToSection(current, fromId, sectionId))
    }
    finishDrag()
  }

  const dropOnSelf = (event: ReactDragEvent) => {
    event.preventDefault()
    event.stopPropagation()
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (isPinnedId(fromId)) {
      setPins((current) => unpinAgent(fromId!, current))
    }
    finishDrag()
  }

  const beginRowDrag = (event: ReactDragEvent, agent: { id: string; name: string }) => {
    try {
      event.dataTransfer.clearData('text/uri-list')
      event.dataTransfer.clearData('URL')
      event.dataTransfer.clearData('text/html')
    } catch {
      /* jsdom DataTransfer may be a stub */
    }
    writeAgentDragPayload(event.dataTransfer, agent)
    beginRailDrag(agent.id)
    try {
      event.dataTransfer.effectAllowed = 'copyMove'
      event.dataTransfer.clearData('text/uri-list')
      event.dataTransfer.clearData('URL')
      event.dataTransfer.clearData('text/html')
    } catch {
      /* jsdom DataTransfer may be a stub */
    }
    setDraggingId(agent.id)
  }

  const openDefinition = (
    kind: 'role' | 'blueprint' | 'team',
    id: string,
    extras?: { blueprintId?: string; teamId?: string },
  ) => {
    openSettingsSheet({
      section: 'definition',
      definitionKind: kind,
      definitionId: id,
      blueprintId: extras?.blueprintId,
      teamId: extras?.teamId,
    })
    onClose?.()
  }

  const openAgentSettings = (agent: { id: string; name: string }) => {
    openAgentEditor({ agentId: agent.id, agentName: agent.name })
    closeMenu()
    onClose?.()
  }

  const editMenuRow = (row: ContextMenuState) => {
    if (row.kind === 'cli') return
    if (row.kind === 'team') {
      openTeamEditor({ teamId: row.entityId, teamName: row.agentName })
      closeMenu()
      return
    }
    if (row.kind === 'remote') {
      openSettingsSheet({ section: 'remotes' })
      closeMenu()
      onClose?.()
      return
    }
    openAgentSettings({ id: row.entityId, name: row.agentName })
  }

  const duplicateMenuRow = async (row: ContextMenuState) => {
    const name = duplicateName(row.agentName)
    try {
      if (row.kind === 'cli') return

      let sourceSectionId = sectionIdForAgent(row.agentId, sectionState)
      if (isUnassignedSection(sourceSectionId) && row.entityId && row.entityId !== row.agentId) {
        sourceSectionId = sectionIdForAgent(row.entityId, sectionState)
      }

      if (row.kind === 'team') {
        const source = teams.find((team) => team.id === row.entityId)
        const created = await createTeamRoster({
          name,
          members: (source?.members ?? []).map((member) => ({
            id: member.id,
            kind: member.kind || 'api',
            role: member.role || 'default',
            source: member.kind === 'team' ? `team:${member.team_id || member.id}` : `blueprint:${member.id}`,
            team_id: member.team_id,
          })),
        })
        await queryClient.invalidateQueries({ queryKey: ['team-rosters'] })
        const createdHide = teamHideId(created.id)
        if (!isUnassignedSection(sourceSectionId)) {
          setSectionState((current) => moveAgentToSection(current, createdHide, sourceSectionId))
        }
        const base = mergeRailOrder(railOrder, visibleRowIds)
        // #793: the duplicate lands at the top of the Unassigned order so it
        // is immediately visible (source section membership is preserved).
        persistVisibleOrder(bumpRailIdToTop(base, createdHide))
        closeMenu()
        return
      }
      if (row.kind === 'remote') {
        const source: Partial<RemoteConnection> | undefined =
          configuredRemotesList.find((remote) => remote.id === row.entityId) ||
          remotes.find((r) => r.id === row.entityId) ||
          fullRemotesQuery.data?.data?.find((r) => r.id === row.entityId)

        const existingRemoteIds = new Set<string>()
        for (const r of configuredRemotesList) if (r.id) existingRemoteIds.add(r.id)
        for (const r of remotes) if (r.id) existingRemoteIds.add(r.id)
        for (const r of fullRemotesQuery.data?.data ?? []) if (r.id) existingRemoteIds.add(r.id)
        for (const r of fullRemotesQuery.data?.configured ?? []) if (r.id) existingRemoteIds.add(r.id)

        const newId = duplicateRemoteId(row.entityId, existingRemoteIds)
        const created = await createRemote({
          id: newId,
          title: name,
          kind: source?.kind || (row.entityId ? row.entityId.split('_')[0] : 'generic'),
          base_url: source?.base_url,
          api_key_env: source?.api_key_env,
          ui_url: source?.ui_url,
          herdr_mode: (source as any)?.herdr_mode,
          ssh_host: (source as any)?.ssh_host,
          ssh_user: (source as any)?.ssh_user,
          ssh_port: (source as any)?.ssh_port,
          ssh_identity_env: (source as any)?.ssh_identity_env,
          ssh_agent: (source as any)?.ssh_agent,
        })
        await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
        await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
        await queryClient.invalidateQueries({ queryKey: ['settings-remotes'] })
        const createdHide = remoteHideId(created.id)
        if (!isUnassignedSection(sourceSectionId)) {
          setSectionState((current) => moveAgentToSection(current, createdHide, sourceSectionId))
        }
        const base = mergeRailOrder(railOrder, visibleRowIds)
        persistVisibleOrder(insertRailIdAfter(base, createdHide, row.agentId))
        closeMenu()
        return
      }
      const sourceEdit = loadAgentEdit(row.entityId)
      const created = await createCustomBlueprint({
        name,
        description: `Copy of ${row.agentName}`,
        category: 'ai_assistants',
        tags: ['api'],
        kind: 'api',
        rail: true,
        source: 'add-agent',
        code: `# Copy of ${assignedBlueprintId(row.entityId)}\n`,
      })
      saveAgentEdit(created.id, {
        name,
        blueprintId: sourceEdit.blueprintId || assignedBlueprintId(row.entityId),
        role: sourceEdit.role,
        llmOverride: sourceEdit.llmOverride,
      })
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
      if (!isUnassignedSection(sourceSectionId)) {
        setSectionState((current) => moveAgentToSection(current, created.id, sourceSectionId))
      }
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(insertRailIdAfter(base, created.id, row.agentId))
    } catch {
      /* caller / tests mock fetch; failures stay on the current row */
    }
    closeMenu()
  }

  const copyMenuConversationId = async (row: ContextMenuState) => {
    const id = copyableConversationId(row.kind, row.agentId, row.entityId)
    if (!id) {
      closeMenu()
      return
    }
    await copyTextToClipboard(id)
    closeMenu()
  }

  const handleDropOnRecycleBin = (fromId: string) => {
    const row = orderedRows.find((item) => item.id === fromId)
    const pin = pins.find((p) => p.id === fromId)
    const agent = agents.find((a) => a.id === fromId)
    const remote = remotes.find((r) => remoteHideId(r.id) === fromId || r.id === fromId)
    const team = teams.find((t) => teamHideId(t.id) === fromId || t.id === fromId)

    let kind: RailMenuKind = resolveMenuKind(fromId)
    let entityId = fromId
    let agentName = fromId

    if (row) {
      if (row.kind === 'remote') {
        kind = 'remote'
        entityId = row.remote.id
        agentName = row.remote.title
      } else if (row.kind === 'team') {
        kind = 'team'
        entityId = row.team.id
        agentName = row.team.name
      } else {
        kind = row.agent.kind === 'cli' ? 'cli' : resolveMenuKind(fromId)
        entityId = row.agent.id
        agentName = row.agent.name
      }
    } else if (remote) {
      kind = 'remote'
      entityId = remote.id
      agentName = remote.title
    } else if (team) {
      kind = 'team'
      entityId = team.id
      agentName = team.name
    } else if (agent) {
      kind = agent.kind === 'cli' ? 'cli' : resolveMenuKind(fromId)
      entityId = agent.id
      agentName = agent.name
    } else if (pin) {
      agentName = pin.name
      entityId = pin.id
    }

    setDeleteConfirm({
      agentId: fromId,
      agentName,
      hidden: false,
      pinned: isPinnedId(fromId),
      x: 0,
      y: 0,
      kind,
      entityId,
    })
  }

  const requestDelete = (row: ContextMenuState) => {
    closeMenu()
    setDeleteConfirm(row)
  }

  const confirmDeleteRow = async () => {
    const row = deleteConfirm
    if (!row) return
    const hideId = row.agentId
    setPins((current) =>
      current.some((pin) => pin.id === hideId) ? unpinAgent(hideId, current) : current,
    )
    if (row.kind === 'remote') {
      try {
        await deleteRemote(row.entityId)
      } catch {
        /* local remove still applies */
      }
      await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
      await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
      await queryClient.invalidateQueries({ queryKey: ['settings-remotes'] })
    } else if (row.kind === 'team') {
      try {
        await deleteTeamRoster(row.entityId)
      } catch {
        /* local remove still applies */
      }
      await queryClient.invalidateQueries({ queryKey: ['team-rosters'] })
    } else if (row.kind === 'api') {
      try {
        await deleteCustomBlueprint(row.entityId)
      } catch {
        /* catalog seats are removed locally only */
      }
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
    }
    // CLI: hide-or-remove from rail only — do not uninstall the binary.
    // #687 invariant: mark ONLY this row's rail id. The old double-mark of
    // row.entityId leaked a bare agent id into the shared deleted list, which
    // the (now namespaced-only) team/remote filters used to honor — deleting
    // one agent could remove a same-id remote/team row with it.
    setDeletedIds((current) => markRailIdDeleted(hideId, current))
    setSectionState((current) => removeSectionMembership(current, hideId))
    setDeleteConfirm(null)
  }

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

  const renderAgentRow = (agent: SidebarAgent, hidden: boolean, spillSlot?: number) => {
    const name = agentLabel(agent)
    const herdr = isHerdrAgent(agent)
    const sessions = sessionsByAgent[agent.id] ?? []
    const scaleOut = !herdr && shouldOpenSessionPicker(sessions)
    // #543: herdr seats are URL-addressable now (`herdrRowIdFromParams`), so
    // the targeted agent's row goes active exactly like a remote row.
    const active = Boolean(activeHerdrRow && herdr && activeHerdrRow === agent.id) ||
      Boolean(activeRail && !herdr && activeRail === agent.id)
    const role = agentRole(agent)
    const dragging = draggingId === agent.id
    const dropping = dropTargetId === agent.id
    const badge = roleBadgeLabel(role)
    const taskCount = settingsTick >= 0 && loadLocalNewChatPerTask(agent.id)
      ? activeTaskSessionCount(agent.id)
      : 0
    const dataRole = role !== 'default' ? role : undefined
    const className = `os-agent-row group/row ${active ? 'os-agent-row--active' : ''} ${
      dragging ? 'os-agent-row--dragging' : ''
    } ${dropping ? 'os-agent-row--drop' : ''}`
    const { snippet, timestamp } = getRowLastMessage(
      agent.id,
      sessions,
      agent, // #601: typed RowActivityMeta — no `as any`
      cliActivityByAgent[agent.id] ?? null,
    )
    const timestampLabel = formatRailTimestamp(timestamp)
    const unread = unreadIds.includes(agent.id)
    const needsApproval = approvalWaitIds.has(agent.id) || peekApprovalWait(agent.id)
    const mark = (
      scaleOut ? (
        // Teams/remotes (#398) must not be stacked here — import AvatarStack there.
        <StackedAvatars sessions={sessions} />
      ) : (
        <AgentAvatar
          src={agent.avatar_path}
          agentId={agent.id}
          size="sm"
          active={cliRunningIds.has(agent.id) || peekCliRunning(agent.id)}
          status={cliRunningIds.has(agent.id) || peekCliRunning(agent.id) ? 'working' : 'idle'}
        />
      )
    )
    const roleBadgeNode = badge ? (
      <span
        className={`os-agent-role-badge shrink-0 ${roleCssClass(role)}`}
        data-role={role}
        data-definition-id={agent.id}
        style={{
          fontSize: '0.55rem',
          padding: '0 0.25rem',
          lineHeight: '1.2',
          height: '0.9rem',
          boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
          whiteSpace: 'nowrap',
        }}
      >
        {badge}
      </span>
    ) : null
    const body = (
      <>
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {mark}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            {/* #500/#501: name and slot share one line, so the tip layers over
                the time instead of occupying a line of its own. */}
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={name} data-testid="rail-agent-name">{name}</span>
              <RailRowSlot
                spillSlot={spillSlot}
                isMac={isMac}
                unread={unread}
                badge={roleBadgeNode}
                timestampLabel={timestampLabel}
              />
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span
              className={`block truncate min-w-0 flex-1${needsApproval ? ' os-rail-attention' : ''}`}
              data-testid={needsApproval ? 'rail-needs-approval' : undefined}
            >
              {needsApproval ? NEEDS_APPROVAL_LABEL : snippet || agent.description}
            </span>
            {taskCount > 1 ? (
              <span
                className="badge badge-sm badge-outline shrink-0"
                data-task-sessions={taskCount}
                title={`${taskCount} running chats`}
              >
                {taskCount} chats
              </span>
            ) : null}
          </span>
        </span>
      </>
    )
    if (herdr) {
      return (
        <a
          href={sidebarHref(agent)}
          className={className}
          data-agent-id={agent.id}
          data-role={dataRole}
          data-hotkey={spillSlot}
          draggable={!hidden}
          onDragStart={(event) => beginRowDrag(event, { id: agent.id, name })}
          onDragEnd={finishDrag}
          onDragOver={(event) => allowRowDrop(event, agent.id)}
          onDrop={(event) => dropReorder(event, agent.id)}
          onClick={(event) => {
            pickOrClose?.()
            event.currentTarget.blur()
          }}
          onMouseLeave={(event) => event.currentTarget.blur()}
          {...rowMenuHandlers(agent.id, name, hidden, isHerdrAgent(agent) ? 'herdr' : 'api')}
        >
          {body}
        </a>
      )
    }
    const dragHandlers = {
      draggable: !hidden,
      onDragStart: (event: ReactDragEvent) => beginRowDrag(event, { id: agent.id, name }),
      onDragEnd: finishDrag,
      onDragOver: (event: ReactDragEvent) => allowRowDrop(event, agent.id),
      onDrop: (event: ReactDragEvent) => dropReorder(event, agent.id),
      onMouseLeave: (event: ReactMouseEvent<HTMLElement>) => {
        event.currentTarget.blur()
      },
      ...rowMenuHandlers(
        agent.id,
        name,
        hidden,
        isCliRailAgent(agent) ? 'cli' : isHerdrAgent(agent) ? 'remote' : 'api',
      ),
    }

    if (scaleOut) {
      return (
        <div
          className="os-agent-row-wrap"
          data-role={role}
          data-scale-out="true"
        >
          <button
            type="button"
            className={`${className} w-full`}
            data-agent-id={agent.id}
            data-role={dataRole}
            data-hotkey={spillSlot}
            data-scale-out="true"
            aria-haspopup="dialog"
            aria-current={active ? 'page' : undefined}
            aria-label={`${name}, ${sessions.length} sessions`}
            {...dragHandlers}
            onClick={(event) => {
              setSessionPicker({ agentId: agent.id, agentName: name, sessions })
              event.currentTarget.blur()
            }}
          >
            {body}
          </button>
        </div>
      )
    }

    return (
      <div
        className="os-agent-row-wrap"
        data-role={role}
      >
        <Link
          to={sidebarHref(agent)}
          className={className}
          data-agent-id={agent.id}
          data-role={dataRole}
          data-hotkey={spillSlot}
          aria-current={active ? 'page' : undefined}
          {...dragHandlers}
          onClick={(event) => {
            pickOrClose?.()
            event.currentTarget.blur()
          }}
        >
          {body}
        </Link>
      </div>
    )
  }

  /**
   * #438: one face — the member you are talking to — plus a compact `+N` for
   * everyone else. No fan of overlapping faces at rail size. `remainder` is
   * omitted entirely for a one-member team, and a team whose roster has not
   * resolved keeps the generic team mark rather than inventing a member.
   */
  const renderTeamAvatar = ({
    name,
    face,
    remainder,
    declared,
    teamId,
    recencyFaces,
    collapsed,
    remoteKind,
  }: {
    name: string
    face?: StackFace | null
    remainder: number
    declared?: DeclaredTeamRoster | null
    teamId?: string
    /** #639: recency-ordered faces for the graduated mini row (wide rail). */
    recencyFaces?: StackFace[]
    /** #639: collapsed (avatar-width) rail — one face only. */
    collapsed?: boolean
    /** #747: remote platform kind — themes the face-less fallback. */
    remoteKind?: string | null
  }) => {
    if (declared) {
      return <PersonaRoster roster={declared} groupId={teamId || name} label={`${name} declared members`} />
    }
    if (!face) {
      // #747: remotes with no member faces render their platform-themed
      // face (Letta, Slack, AnythingLLM, …) instead of the generic Users mark.
      if (remoteKind) {
        return (
          <AgentAvatar
            agentId={teamId || name}
            alt={name}
            size="sm"
            remoteKind={remoteKind}
          />
        )
      }
      return (
        <span
          className="os-team-mark os-agent-team-icon flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-base-300 text-base-content/80"
          aria-hidden="true"
        >
          <Users className="h-3.5 w-3.5" />
        </span>
      )
    }
    // face — collapsed shows the most recently active member, wide shows the
    // chat target — and the `+N` remainder sticker (roster minus the face)
    // rides along in both. The graduated mini row is retired.
    const layout = railTeamStackLayout(recencyFaces ?? [], Boolean(collapsed))
    if (collapsed) {
      const solo = layout.faces[0] ?? face
      return (
        <span
          className="os-team-face relative inline-flex shrink-0 items-center justify-center"
          data-testid="team-chat-face"
          data-remainder={String(remainder)}
          data-stack-count="1"
          data-rail-collapsed="true"
        >
          <AgentAvatar
            src={solo.avatarSrc || solo.src}
            agentId={solo.agentId || solo.id}
            alt={solo.name || name}
            size="sm"
            status={solo.working ? 'working' : 'idle'}
            active={Boolean(solo.working)}
          />
          {remainder > 0 ? (
            <span className="os-team-face__remainder" data-testid="team-remainder" aria-hidden="true">
              +{remainder}
            </span>
          ) : null}
        </span>
      )
    }
    return (
      <span
        className="os-team-face relative inline-flex shrink-0 items-center justify-center"
        data-testid="team-chat-face"
        data-remainder={String(remainder)}
        data-stack-count="1"
        data-rail-collapsed="false"
      >
        <span className="inline-flex items-end justify-center">
          <span
            className="relative inline-flex shrink-0"
            style={{ width: 32, height: 32 }}
          >
            <AgentAvatar
              src={face.avatarSrc || face.src}
              agentId={face.agentId || face.id}
              alt={face.name || name}
              size="sm"
              className="os-team-face__large"
            />
          </span>
        </span>
        {remainder > 0 ? (
          <span
            className="os-team-face__remainder"
            data-testid="team-remainder"
            aria-hidden="true"
          >
            +{remainder}
          </span>
        ) : null}
      </span>
    )
  }

  const renderTeamLink = (team: TeamRoster, hidden: boolean, nested = false, spillSlot?: number) => {
    const name = team.name || team.id
    const hideId = teamHideId(team.id)
    const active = Boolean(activeRail) && activeRail === hideId
    const sessions = sessionsForTeam(team)
    const declared = declaredRosterForTeam(team, catalog)
    const rawFaces = stackFacesForTeam(team)
    const marked = markStackWorking(
      rawFaces,
      (id) => cliRunningIds.has(id) || peekCliRunning(id),
    )
    const teamWorkerBusy = Boolean(
      marked.anyWorking ||
      cliRunningIds.has(hideId) ||
      peekCliRunning(hideId),
    )
    // #438: the face is the team's chat target — `chief_of_staff_id`, else the
    // CoS-roled member, else the first. `defaultSessionForTeam` already owns
    // that rule, so the rail reads it rather than inventing a second one.
    const chatTargetId = defaultSessionForTeam(team)?.memberId ?? ''
    // NOTE: `teamSidepaneStack` caps the list at STACK_FACE_LIMIT, so it cannot
    // be the source of the remainder — a 5-member team would report +2. The
    // remainder is the *roster* minus the one face, which is what #438 specifies.
    const chatFace = declared
      ? null
      : teamChatFaceStack(teamSidepaneStack(marked.faces, teamWorkerBusy).faces, chatTargetId)
        .face
    const totalMembers = declared
      ? declared.parsed
        ? declared.count
        : 1
      : team.members
        ? team.members.length
        : rawFaces.length
    const singleMember = !declared && totalMembers === 1
    const teamRemainder = declared || totalMembers <= 1 ? 0 : totalMembers - 1
    const dragging = draggingId === hideId
    const dropping = dropTargetId === hideId
    // #438: the roster is no longer fanned into faces, so "needs approval" is the
    // chat face's state (the member the row represents) rather than any member.
    const teamNeedsApproval =
      approvalWaitIds.has(teamHideId(team.id)) ||
      peekApprovalWait(teamHideId(team.id)) ||
      Boolean(
        chatFace &&
          (approvalWaitIds.has(chatFace.id) || peekApprovalWait(chatFace.id)),
      )
    const { snippet: teamSnippet, timestamp: teamTime } = getRowLastMessage(
      teamHideId(team.id),
      sessions,
      team, // #601: TeamRoster.lastMessageAt — no `as any`
    )
    const teamTimestampLabel = formatRailTimestamp(teamTime)
    const unread = unreadIds.includes(hideId)
    // #639 (REQ-909) as revised by #817: recency-ordered faces — every state
    // renders one face (most recently active when collapsed, chat target when
    // wide) plus the roster `+N` sticker. No mini row in either state.
    const teamRecencyFaces = orderedFacesByRecency(marked.faces)
    // #525: no `Team` badge. Team membership is not a role, so the pill was
    // claiming role status — same reason #496 removed `Remote`. The right slot
    // now falls through to the row's timestamp.
    return (
      <Link
        to={`/chat?team=${encodeURIComponent(team.id)}`}
        className={`os-team-item os-agent-row group/row os-agent-row--team ${
          active ? 'os-agent-row--active' : ''
        } ${nested ? 'os-agent-row--nested' : ''} ${dragging ? 'os-agent-row--dragging' : ''} ${
          dropping ? 'os-agent-row--drop' : ''
        } ${teamWorkerBusy ? 'os-agent-row--working-stack' : ''}`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (team)`}
        data-agent-id={hideId}
        data-kind="team"
        data-hotkey={spillSlot}
        data-stack-count={String(declared ? (declared.parsed ? declared.count : 1) : singleMember ? 1 : chatFace ? 1 : 0)}
        data-remainder={String(teamRemainder)}
        data-persona-count={declared ? String(declared.parsed ? declared.count : 1) : undefined}
        data-roster={declared ? 'declared' : undefined}
        draggable={!hidden}
        onDragStart={(event) => beginRowDrag(event, { id: hideId, name })}
        onDragEnd={finishDrag}
        onDragOver={(event) => allowRowDrop(event, hideId)}
        onDrop={(event) => dropReorder(event, hideId)}
        onClick={(event) => {
          event.preventDefault()
          const def = defaultSessionForTeam(team)
          if (def) {
            navigate(def.href)
            onClose?.()
          } else {
            openGroupPicker(name, sessions)
          }
        }}
        {...rowMenuHandlers(hideId, name, hidden, 'team', sessions, team.id)}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {renderTeamAvatar({
            name,
            face: chatFace,
            remainder: teamRemainder,
            declared,
            teamId: team.id,
            recencyFaces: teamRecencyFaces,
            collapsed: isAvatarOnly,
          })}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={name} data-testid="rail-agent-name">{name}</span>
              <RailRowSlot
                spillSlot={spillSlot}
                isMac={isMac}
                unread={unread}
                timestampLabel={teamTimestampLabel}
              />
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span
              className={`block truncate min-w-0 flex-1${teamNeedsApproval ? ' os-rail-attention' : ''}`}
              data-testid={teamNeedsApproval ? 'rail-needs-approval' : undefined}
            >
              {teamNeedsApproval ? NEEDS_APPROVAL_LABEL : teamSnippet || team.description}
            </span>
          </span>
        </span>
      </Link>
    )
  }

  const renderRemoteRow = (remote: RemoteEntry, hidden: boolean, spillSlot?: number) => {
    const name = remote.title
    const hideId = remoteHideId(remote.id)
    const active = Boolean(activeRail) && activeRail === hideId
    const dragging = draggingId === hideId
    const sessions = sessionsForRemote(remote)
    const rawFaces = stackFacesForRemote(remote)
    const marked = markStackWorking(
      rawFaces,
      (id) => cliRunningIds.has(id) || peekCliRunning(id),
    )
    const remoteWorkerBusy = Boolean(
      marked.anyWorking ||
      cliRunningIds.has(hideId) ||
      peekCliRunning(hideId),
    )
    // #438: a remote has no CoS concept, so its chat face is the default talk-to
    // member — first, in the ordering the working-aware stack already produced.
    // The remainder comes from the member total, never from the capped list.
    const chatFace = teamChatFaceStack(
      teamSidepaneStack(marked.faces, remoteWorkerBusy).faces,
      defaultSessionForRemote(remote)?.memberId ?? '',
    ).face
    // #747: sessionsForRemote fabricates a member for empty remotes, so the
    // face is rarely null — the themed face applies whenever the chat face
    // carries no custom avatar (uploaded faces always win).
    const chatFaceHasAvatar = Boolean(chatFace && (chatFace.avatarSrc || chatFace.src))
    const totalMembers = remote.agents ? remote.agents.length : rawFaces.length
    const singleMember = totalMembers === 1
    const remoteRemainder = totalMembers <= 1 ? 0 : totalMembers - 1
    const remoteNeedsApproval =
      approvalWaitIds.has(hideId) ||
      peekApprovalWait(hideId) ||
      Boolean(
        chatFace &&
          (approvalWaitIds.has(chatFace.id) || peekApprovalWait(chatFace.id)),
      )
    const { snippet: remoteSnippet, timestamp: remoteTime } = getRowLastMessage(
      hideId,
      sessions,
      remote, // #601: RemoteEntry.lastMessageAt — no `as any`
    )
    const remoteTimestampLabel = formatRailTimestamp(remoteTime)
    const unread = unreadIds.includes(hideId)
    // #496: no `Remote` badge. Remote is a seat kind (transport), not a role, so
    // the pill was claiming role status. The kind stays on the row itself —
    // `data-kind="remote"`, `os-agent-row--remote`, and the `(remote)` aria
    // label all remain. The right slot now falls through to the timestamp.
    return (
      <Link
        to={`/chat?remote=${encodeURIComponent(remote.id)}`}
        className={`os-remote-item os-agent-row group/row os-agent-row--remote ${
          active ? 'os-agent-row--active' : ''
        } ${dragging ? 'os-agent-row--dragging' : ''} ${
          remoteWorkerBusy ? 'os-agent-row--working-stack' : ''
        }`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (remote)`}
        data-agent-id={hideId}
        data-kind="remote"
        data-hotkey={spillSlot}
        data-remote-id={remote.id}
        data-stack-count={String(singleMember ? 1 : chatFace ? 1 : 0)}
        data-remainder={String(remoteRemainder)}
        draggable={!hidden}
        onDragStart={(event) => beginRowDrag(event, { id: hideId, name })}
        onDragEnd={finishDrag}
        onDragOver={(event) => {
          const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
          if (isPinnedId(fromId)) {
            allowRowDrop(event, hideId)
            return
          }
          try {
            event.dataTransfer.dropEffect = 'none'
          } catch {
            /* synthetic events may omit dataTransfer */
          }
        }}
        onDrop={dropOnSelf}
        onClick={(event) => {
          event.preventDefault()
          // #748: rail rows are launch surfaces — every row navigates
          // immediately, session-capable remotes included. The default is the
          // most recent session when one exists; otherwise the remote chat.
          // Session *switching* stays in the chat header, not the rail.
          const def = defaultSessionForRemote(remote)
          navigate(def?.href || `/chat?remote=${encodeURIComponent(remote.id)}`)
          onClose?.()
        }}
        {...rowMenuHandlers(hideId, name, hidden, 'remote', sessions, remote.id)}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {!chatFaceHasAvatar && remoteThemeFace(remote.kind) ? (
            // #747: platform-themed face (Letta, Slack, AnythingLLM, …) —
            // only for kinds the registry actually covers, so omb/herdr and
            // other stack remotes keep their existing member-face rendering.
            <AgentAvatar
              agentId={remote.id}
              alt={name}
              size="sm"
              remoteKind={remote.kind}
              active={remoteWorkerBusy}
              status={remoteWorkerBusy ? 'working' : 'idle'}
            />
          ) : (
            renderTeamAvatar({
              name,
              face: chatFace,
              remainder: remoteRemainder,
              teamId: remote.id,
              remoteKind: remote.kind,
            })
          )}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="os-rail-name-line text-sm font-semibold leading-5">
              <span className="os-rail-row-name" title={name} data-testid="rail-agent-name">{name}</span>
              <RailRowSlot
                spillSlot={spillSlot}
                isMac={isMac}
                unread={unread}
                timestampLabel={remoteTimestampLabel}
              />
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span
              className={`block truncate min-w-0 flex-1${remoteNeedsApproval ? ' os-rail-attention' : ''}`}
              data-testid={remoteNeedsApproval ? 'rail-needs-approval' : undefined}
            >
              {remoteNeedsApproval
                ? NEEDS_APPROVAL_LABEL
                : remoteSnippet || (remote as any).description || 'Remote team'}
            </span>
          </span>
        </span>
      </Link>
    )
  }

  const renderTeamRow = (
    team: TeamRoster,
    nested = false,
    seen: string[] = [],
    spillSlot?: number,
    railIndex?: number,
  ) => {
    const hidden = resolvedHiddenIds.includes(teamHideId(team.id))
    if (hidden && !nested) return null
    const childSlots = team.members.filter((m) => m.kind === 'team')
    return (
      <li
        key={`team-${team.id}`}
        data-rail-id={nested ? undefined : teamHideId(team.id)}
        data-rail-index={nested ? undefined : railIndex}
      >
        {hidden ? null : renderTeamLink(team, false, nested, spillSlot)}
        {childSlots.length > 0 && !seen.includes(team.id) ? (
          <ul className="os-agent-team-nest">
            {childSlots.map((m) => {
              const child = rosterById.get(m.team_id || m.id)
              if (child) return renderTeamRow(child, true, seen.concat(team.id))
              return (
                <li key={`team-slot-${m.id}`}>
                  <span className="os-agent-row os-agent-row--team os-agent-row--nested">
                    <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
                      <Users className="os-agent-team-icon h-4 w-4 shrink-0" aria-hidden="true" />
                    </span>
                    <span className="os-agent-row__label-col min-w-0 flex-1">
                      <span className="flex min-w-0 items-center justify-between gap-1.5">
                        <span className="block truncate text-sm font-semibold leading-5">
                          {m.team_id || m.id}
                        </span>
                        <span className="flex items-center gap-1 shrink-0">
                          <span
                            className="os-agent-role-badge shrink-0"
                            data-kind="team"
                            data-definition-id={m.team_id || m.id}
                            role="button"
                            tabIndex={0}
                            aria-label={`Open ${m.team_id || m.id} team settings`}
                            style={{
                              fontSize: '0.55rem',
                              padding: '0 0.25rem',
                              lineHeight: '1.2',
                              height: '0.9rem',
                              boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
                              whiteSpace: 'nowrap',
                            }}
                            onClick={(event) => {
                              event.preventDefault()
                              event.stopPropagation()
                              const teamId = m.team_id || m.id
                              openDefinition('team', teamId, { teamId })
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                event.stopPropagation()
                                const teamId = m.team_id || m.id
                                openDefinition('team', teamId, { teamId })
                              }
                            }}
                          >
                            Team
                          </span>
                        </span>
                      </span>
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>
        ) : null}
      </li>
    )
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
          className={`os-fav-grid ${dropActive ? 'os-fav-grid--active' : ''} ${
            visiblePins.length === 0 &&
            !dropActive &&
            !(draggingId && !isPinnedId(draggingId))
              ? 'os-fav-grid--bare'
              : ''
          } ${visiblePins.length === 0 ? 'os-fav-grid--empty' : ''}`}
            aria-label="Pinned agents"
            data-fav-layout="2-up"
            data-testid="agent-fav-grid"
            data-fav-empty={visiblePins.length === 0 ? 'true' : 'false'}
            onDragOver={(event) => {
              event.preventDefault()
              try {
                event.dataTransfer.dropEffect = 'move'
              } catch {
                /* synthetic events may omit dataTransfer */
              }
              setDropActive(true)
            }}
            onDragLeave={() => setDropActive(false)}
            onDrop={dropPin}
          >
            {visiblePins.length === 0 ? (
              <div
                className="os-fav-grid__hint"
                data-testid="fav-empty-hint"
              >
                {dropActive || (draggingId && !isPinnedId(draggingId)) ? 'drop' : '+'}
              </div>
            ) : null}
          {visiblePins.map((pin, pinIdx) => {
            const live = agents.find((agent) => agent.id === pin.id)
            const pinTeam = pin.id.startsWith('team:')
              ? teams.find((item) => teamHideId(item.id) === pin.id || item.id === pin.id.slice(5))
              : undefined
            const pinName = live ? agentLabel(live) : pinTeam?.name || pin.name || pin.id
            const role = live ? agentRole(live) : 'default'
            const badge = live ? roleBadgeLabel(role) : ''
            const pinActive = Boolean(activeRail && activeRail === pin.id)
            const pinUnread = unreadIds.includes(pin.id)
            const pinTeamPlan = pinTeam
              ? (() => {
                  const rawFaces = stackFacesForTeam(pinTeam)
                  const marked = markStackWorking(
                    rawFaces,
                    (id) => cliRunningIds.has(id) || peekCliRunning(id),
                  )
                  const busy = Boolean(
                    marked.anyWorking ||
                      cliRunningIds.has(pin.id) ||
                      peekCliRunning(pin.id),
                  )
                  // The remainder is the roster minus the one shown face — not
                  // the capped stack length, which would under-report.
                  const memberTotal = pinTeam.members ? pinTeam.members.length : marked.faces.length
                  const face = teamChatFaceStack(
                    teamSidepaneStack(marked.faces, busy).faces,
                    defaultSessionForTeam(pinTeam)?.memberId ?? '',
                  ).face
                  return {
                    ...marked,
                    anyWorking: busy,
                    remainder: memberTotal > 1 ? memberTotal - 1 : 0,
                    face,
                  }
                })()
              : null
            const pinWorkerBusy = Boolean(
              pinTeamPlan?.anyWorking ||
                cliRunningIds.has(pin.id) ||
                peekCliRunning(pin.id),
            )
            const pinNeedsApproval = Boolean(
              approvalWaitIds.has(pin.id) ||
                peekApprovalWait(pin.id) ||
                Boolean(
                  pinTeamPlan?.face &&
                    (approvalWaitIds.has(pinTeamPlan.face.id) ||
                      peekApprovalWait(pinTeamPlan.face.id)),
                ),
            )
            const pinClass = `os-fav-tile group/tile ${
              draggingId === pin.id ? 'os-fav-tile--dragging' : ''
            } ${dropTargetId === pin.id ? 'os-fav-tile--drop' : ''} ${
              pinActive ? 'os-fav-tile--active' : ''
            } ${pinWorkerBusy ? 'os-fav-tile--working-stack' : ''}`
            const pinFace = (
              <>
                {pinNeedsApproval ? (
                  <span
                    className="os-fav-tile__attention"
                    data-testid="pin-needs-approval"
                  >
                    {NEEDS_APPROVAL_LABEL}
                  </span>
                ) : null}
                {pinUnread && (
                  <span
                    className="os-rail-unread-dot absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-sky-500 z-10 group-hover/tile:hidden"
                    aria-label="Unread"
                    data-testid="rail-unread-dot"
                  />
                )}
                {badge ? (
                  <span
                    className={`os-fav-tile__badge os-agent-role-badge ${roleCssClass(role)}`}
                    data-role={role}
                    data-definition-id={pin.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open ${role} settings`}
                    onClick={(event) => {
                      event.preventDefault()
                      event.stopPropagation()
                      openDefinition('role', pin.id, { blueprintId: pin.id })
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        event.stopPropagation()
                        openDefinition('role', pin.id, { blueprintId: pin.id })
                      }
                    }}
                  >
                    {badge}
                  </span>
                ) : null}
                {/* #438: one full-size face + a corner `+N` overlay.
                    #689 (supersedes #523's graduated stack): exactly ONE
                    avatar + the +N counter on pinned team seats — the second
                    face read as a second agent at pin size. The face is
                    still the most recently active member (#523 ordering),
                    just no longer stacked. */}
                <span
                  className="os-fav-tile__face relative inline-flex shrink-0 items-center justify-center"
                  data-testid="pin-team-face"
                  data-remainder={String(pinTeamPlan?.remainder ?? 0)}
                >
                  <AgentAvatar
                    src={pinTeamPlan?.face?.avatarSrc || pinTeamPlan?.face?.src || live?.avatar_path}
                    agentId={pinTeamPlan?.face?.agentId || pinTeamPlan?.face?.id || pin.id}
                    alt={pinTeamPlan?.face?.name || pinName}
                    size="lg"
                    className="os-fav-tile__avatar"
                    status={pinWorkerBusy ? 'working' : 'idle'}
                    active={pinWorkerBusy}
                  />
                  {pinTeamPlan && pinTeamPlan.remainder > 0 ? (
                    <span
                      className="os-fav-tile__remainder"
                      data-testid="pin-team-remainder"
                      aria-hidden="true"
                    >
                      +{pinTeamPlan.remainder}
                    </span>
                  ) : null}
                </span>
                <span className="os-fav-tile__name">{pinName}</span>
                {pinIdx < 9 && (
                  <span
                    className="os-fav-tile__shortcut"
                    aria-label={`Shortcut ${isMac ? '⌥' : 'Alt+'}${pinIdx + 1}`}
                  >
                    {isMac ? `⌥${pinIdx + 1}` : `Alt+${pinIdx + 1}`}
                  </span>
                )}
              </>
            )
            const pinKind = resolveMenuKind(pin.id)
            const pinEntityId = pin.id.replace(/^(team|remote):/, '')
            const pinHandlers = {
              draggable: true as const,
              onDragStart: (event: ReactDragEvent) => beginRowDrag(event, pin),
              onDragEnd: finishDrag,
              onDragOver: (event: ReactDragEvent) => allowRowDrop(event, pin.id),
              onDrop: (event: ReactDragEvent) => dropPinReorder(event, pin.id),
              onClick: (event: ReactMouseEvent<HTMLElement>) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
                  pickOrClose?.()
                  event.currentTarget.blur()
                  return
                }
                event.preventDefault()
                navigate(agentChatHref(pin.id))
                pickOrClose?.()
                event.currentTarget.blur()
              },
              onMouseLeave: (event: ReactMouseEvent<HTMLElement>) => {
                event.currentTarget.blur()
              },
              ...rowMenuHandlers(
                pin.id,
                pinName,
                resolvedHiddenIds.includes(pin.id),
                pinKind,
                undefined,
                pinEntityId,
              ),
            }
            if (isHerdrAgent(pin)) {
              return (
                <a
                  key={pin.id}
                  href="/teams/#herdr-members"
                  className={pinClass}
                  title={pinName}
                  aria-label={pinName}
                  data-agent-id={pin.id}
                  {...pinHandlers}
                >
                  {pinFace}
                </a>
              )
            }
            return (
              <Link
                key={pin.id}
                to={agentChatHref(pin.id)}
                className={pinClass}
                title={pinName}
                aria-label={pinName}
                data-agent-id={pin.id}
                {...pinHandlers}
              >
                {pinFace}
              </Link>
            )
          })}
          </div>


        <div className="relative min-h-0 flex-1 flex flex-col">
          <nav
            ref={navScrollRef}
            onScroll={updateCanScroll}
            className={`os-rail-scroller min-h-0 flex-1 overflow-y-auto px-2 ${
              /* #729: the 4rem bottom pad exists to clear the drag ghost; it
                 is dead space when idle — active rows get the height back. */
              draggingId ? 'pb-16' : 'pb-4'
            }`}
            data-testid="rail-agent-scroller"
            aria-label="Agent list"
            onContextMenu={(event) => {
              const target = event.target as HTMLElement
              if (target.closest('[data-rail-id], .os-rail-section, .os-pin')) return
              event.preventDefault()
              openPaneMenuAt(event.clientX, event.clientY)
            }}
          >
            {/* #685: a disabled provider kind is COMPLETELY absent — no notice,
                no badge, no "enable in Settings" copy anywhere outside Settings.
                The old #594 rail notice advertised the withheld surfaces and was
                exactly the informative noise this ticket bans. Product modes are
                still discoverable where they belong: Settings → Rail. */}
            <div
              className={`os-agent-list ${listDropActive ? 'os-agent-list--unfav' : ''} ${
                /* #729: the 3rem floor is a drop affordance, not an idle
                   requirement — reserve it only while a drag can use it. */
                draggingId ? 'os-agent-list--dragging' : ''
              }`}
              data-testid="agent-list-drop"
              data-unfavourite-target="true"
              onDragOver={allowListUnfavourite}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node)) {
                  setListDropActive(false)
                }
              }}
              onDrop={dropUnfavourite}
            >
              {loadingList ? (
                <p className="px-2 py-3 text-sm text-base-content/45">Loading agents…</p>
              ) : loadFailed ? (
                <p className="px-2 py-3 text-sm text-base-content/45">Could not load agents.</p>
              ) : visibleCount === 0 ? (
                <p className="px-2 py-3 text-sm text-base-content/45">
                  {isPinnedId(draggingId) ? 'drop here to unfavourite' : 'No agents yet.'}
                </p>
              ) : (
                <ul className="os-rail-sections space-y-1">
                  {sectionBlocks.map((block) => {
                    // #688: an emptied Unassigned section is not a permanent
                    // empty block. It hides until it has rows again — or until
                    // a drag starts, when it reappears as a drop target (its
                    // drop handler below is live the whole time). "Move to →
                    // Unassigned" in the context menu works either way.
                    if (
                      isUnassignedSection(block.id) &&
                      block.rows.length === 0 &&
                      !draggingId
                    ) {
                      return null
                    }
                    const showMembers = isAvatarOnly || !block.collapsed
                    return (
                      <li
                        key={block.id}
                        className={`os-rail-section ${
                          sectionDropId === block.id ? 'os-rail-section--drop' : ''
                        }`}
                        data-testid="rail-section"
                        data-section-id={block.id}
                        data-section-custom={block.custom ? 'true' : 'false'}
                        data-collapsed={block.collapsed ? 'true' : 'false'}
                        data-internal-only={block.internalOnly ? 'true' : 'false'}
                        /* #564: the whole section block accepts a drop, not just
                           its header and its empty hint. Without this, a drop
                           on the padding or the gap between rows bubbled to the
                           list container's `dropUnfavourite`, which unpins but
                           never assigns — so a dragged pin landed in
                           Unassigned however carefully you aimed. */
                        onDragOver={(event) => allowSectionDrop(event, block.id)}
                        onDrop={(event) => dropOnSection(event, block.id)}
                      >
                        {isAvatarOnly ? null : (
                          <RailSectionHeader
                            sectionId={block.id}
                            name={block.name}
                            count={block.rows.length}
                            collapsed={block.collapsed}
                            custom={block.custom}
                            internalOnly={Boolean(block.internalOnly)}
                            editing={editingSectionId === block.id}
                            editValue={editingSectionId === block.id ? editingSectionName : block.name}
                            dropActive={sectionDropId === block.id}
                            onToggle={() => {
                              if (block.id === 'subagents') {
                                setSubagentsCollapsed((current) => !current)
                              } else {
                                setSectionState((current) => toggleSectionCollapsed(current, block.id))
                              }
                            }}
                            onToggleTalkLock={
                              block.custom
                                ? () =>
                                    setSectionState((current) =>
                                      toggleSectionInternalOnly(current, block.id),
                                    )
                                : undefined
                            }
                            onContextMenu={
                              block.custom
                                ? ({ clientX, clientY }) =>
                                    openSectionMenuAt(block.id, block.name, clientX, clientY)
                                : undefined
                            }
                            onEditChange={setEditingSectionName}
                            onEditCommit={commitSectionRename}
                            onEditCancel={cancelSectionRename}
                            onDragOver={(event) => allowSectionDrop(event, block.id)}
                            onDrop={(event) => dropOnSection(event, block.id)}
                          />
                        )}
                        {showMembers ? (
                          <ul className="space-y-0.5">
                            {block.rows.length === 0 && !isAvatarOnly ? (
                              <li>
                                <RailSectionEmpty
                                  dropActive={sectionDropId === block.id}
                                  onDragOver={(event) => allowSectionDrop(event, block.id)}
                                  onDrop={(event) => dropOnSection(event, block.id)}
                                  unassigned={block.id === UNASSIGNED_SECTION_ID}
                                />
                              </li>
                            ) : (
                              block.rows.map((row) => {
                                const index = orderedRows.findIndex((item) => item.id === row.id)
                                const spillSlot =
                                  index >= 0 && index < 9 - visiblePins.length
                                    ? visiblePins.length + index + 1
                                    : undefined
                                if (row.kind === 'team') {
                                  return renderTeamRow(row.team, false, [], spillSlot, index)
                                }
                                return (
                                  <li key={row.id} data-rail-id={row.id} data-rail-index={index}>
                                    {row.kind === 'remote'
                                      ? renderRemoteRow(row.remote, false, spillSlot)
                                      : renderAgentRow(row.agent, false, spillSlot)}
                                  </li>
                                )
                              })
                            )}
                          </ul>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </nav>
          <div
            className={`os-rail-scroll-fade pointer-events-none transition-opacity duration-150 ${
              canScroll ? 'opacity-100' : 'opacity-0'
            }`}
            data-testid="rail-scroll-fade"
            data-can-scroll={canScroll ? 'true' : 'false'}
            aria-hidden="true"
          />
        </div>

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
      {paneMenu && (
        <RailContextMenu
          agentName="Side pane"
          x={paneMenu.x}
          y={paneMenu.y}
          items={paneMenuItems()}
          menuRef={menuRef}
          onSelect={handlePaneMenuSelect}
        />
      )}
      {deleteConfirm && (
        <ConfirmModal
          isOpen
          onClose={() => setDeleteConfirm(null)}
          onConfirm={confirmDeleteRow}
          title={`Delete ${deleteConfirm.agentName}?`}
          confirmText="Delete"
          cancelText="Cancel"
          confirmVariant="error"
        >
          <p>
            {deleteConfirm.kind === 'cli'
              ? 'This removes the CLI agent from the rail. It does not uninstall the CLI on this machine.'
              : deleteConfirm.kind === 'remote'
                ? 'This removes the configured remote from swarm. It does not change the far-side host.'
                : 'This deletes the local entity and removes it from the rail. This cannot be undone from Hidden Agents.'}
          </p>
        </ConfirmModal>
      )}
      {notifyHint ? (
        <div
          role="status"
          data-testid="notify-permission-hint"
          data-outcome={notifyHint.outcome}
          className="fixed bottom-4 right-4 z-50 max-w-xs rounded-lg border border-base-300 bg-neutral px-3 py-2 text-sm shadow-xl"
        >
          <span className="block">
            {notifyHint.requestFailed
              ? 'The browser blocked the permission request before it could show a prompt. Try again.'
              : NOTIFY_HINT_COPY[notifyHint.outcome]}
          </span>
          <span className="mt-1 flex items-center gap-2">
            {notifyHint.outcome === 'never-asked' ? (
              <button
                type="button"
                className="link link-primary text-xs"
                data-testid="notify-permission-retry"
                onClick={() => void retryNotifyPermission()}
              >
                Try again
              </button>
            ) : null}
            <button
              type="button"
              className="link text-xs opacity-70"
              data-testid="notify-permission-dismiss"
              onClick={() => setNotifyHint(null)}
            >
              Dismiss
            </button>
          </span>
        </div>
      ) : null}
      <AddAgentWizard
        isOpen={addWizardOpen}
        onClose={() => setAddWizardOpen(false)}
        onCreated={handleAgentCreated}
        onSelectAgent={handleAgentSelected}
      />
    </>
  )
}
