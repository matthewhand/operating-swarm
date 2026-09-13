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
import { Plug, Plus, Search, Server, Users, X } from 'lucide-react'
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
  type RouterDesign,
} from '../lib/api'
import { useOptionalToast } from './DaisyUI'
import {
  CLI_PROCESS_STOPPED_TOAST,
  CLI_RUN_STATE_EVENT,
  cliRunStateFromEvent,
  notifyCliTerminated,
  peekCliRunning,
} from '../lib/cliRunState'
import AgentAvatar from './AgentAvatar'
import {
  agentRole,
  isChiefOfStaff,
  roleBadgeLabel,
  roleCssClass,
  roleFromAgent,
} from '../lib/agentRoles'
import { isNonCatalogRailPinId, railSeatAgents } from '../lib/railSeats'
import {
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
  loadRailOrder,
  mergeRailOrder,
  moveRailId,
  peekRailDrag,
  saveRailOrder,
} from '../lib/railOrder'
import {
  FOCUS_AGENT_EVENT,
  NOTIFY_CHANGED_EVENT,
  chatHrefForRowId,
  disableAgentNotify,
  enableAgentNotifications,
  isAgentNotifyEnabled,
  loadNotifyAgentIds,
  maybeNotifyAgentTurn,
} from '../lib/agentNotifications'
import {
  BUMP_COMPLETED_EVENT,
  loadBumpCompleted,
  saveHostnameOverride,
} from '../lib/settingsPrefs'
import { computeRailHotkeyTargets } from '../lib/railHotkeys'
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
import { AGENT_CHAT_SESSIONS_EVENT } from '../lib/agentChatSessions'
import { formatRailTimestamp, getRowLastMessage } from '../lib/chatTime'
import { fetchTeamRosters, parseTeamRosters, teamHideId, type TeamRoster } from '../lib/teamRosters'
import { fetchConfiguredRemotes, remoteDisplayName, remoteHideId, type RemoteEntry } from '../lib/remotesCatalog'
import { configuredRemotes } from '../lib/remotes'
import RemoteSessionsPopup from './RemoteSessionsPopup'
import UpdateChrome from './UpdateChrome'
import {
  CHAT_CONNECTION_EVENT,
  getChatConnection,
  type ChatConnectionStatus,
} from '../lib/chatConnection'
import { selectStackedFaces, teamSidepaneStack } from '../lib/avatarStack'
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
  isRailMenuKey,
  paneMenuItems,
  railMenuItems,
  sectionMenuItems,
  type RailMenuItemId,
  type RailMenuKind,
} from '../lib/railContextMenu'
import {
  NEW_SECTION_TARGET,
  UNASSIGNED_SECTION_ID,
  createSection,
  createSectionWithAgent,
  deleteSection,
  isUnassignedSection,
  loadRailSections,
  moveAgentToSection,
  moveSection,
  partitionRowsBySection,
  removeSectionMembership,
  renameSection,
  sectionIdForAgent,
  toggleSectionCollapsed,
  type RailSectionsState,
} from '../lib/railSections'
import { copyTextToClipboard } from '../lib/clipboard'
import {
  isRailIdDeleted,
  loadDeletedRailIds,
  markRailIdDeleted,
} from '../lib/deletedRailIds'
import { openSearchPalette } from './SearchPalette'
import { isMacPlatform, searchShortcutLabel } from '../lib/keybindingTips'
import {
  AGENT_EDITS_CHANGED_EVENT,
  assignedBlueprintId,
  loadAgentEdit,
  saveAgentEdit,
} from '../lib/agentEdits'
import { TEAM_EDITS_CHANGED_EVENT } from '../lib/teamEdits'
import { declaredRosterForTeam } from '../lib/declaredRoster'
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
import { OPEN_TEAM_COMPOSER_EVENT } from './TeamComposer'
import { openSettingsSheet } from './SettingsSheet'
import { OPEN_PLUGINS_EVENT } from '../lib/chromeOverlay'
import { ConfirmModal } from './DaisyUI'
import RailContextMenu from './RailContextMenu'
import RailSectionHeader, { RailSectionEmpty } from './RailSectionHeader'
import AvatarStack from './AvatarStack'
import StackedAvatars from './StackedAvatars'
import {
  clampRailWidth,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  MIN_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  AVATAR_ONLY_THRESHOLD,
} from '../lib/railResize'

const EMPTY_BLUEPRINTS: Blueprint[] = []

export interface AgentSidebarProps {
  /** Mobile drawer open. Desktop (lg+) is always visible. */
  open?: boolean
  /** Below Tailwind `lg` — drawer + inert when closed. */
  narrow?: boolean
  onClose?: () => void
  /** Agent / conversation / team pick — parent may tuck the rail (REQ-54). */
  onPick?: () => void
  onOpenSearch?: () => void
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

type SidebarAgent = Blueprint & {
  kind?: string
  remote?: string
  cli?: string
}

type RailRow =
  | { kind: 'agent'; id: string; agent: SidebarAgent }
  | { kind: 'team'; id: string; team: TeamRoster }
  | { kind: 'remote'; id: string; remote: RemoteEntry }

function isHerdrAgent(agent: { id: string; kind?: string }): boolean {
  return agent.kind === 'herdr' || String(agent.id).startsWith('herdr:')
}

function sidebarHref(agent: { id: string; kind?: string }): string {
  if (isHerdrAgent(agent)) return '/teams/#herdr-members'
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
function isCliRailAgent(agent: { id?: string; kind?: string }): boolean {
  return agent.kind === 'cli'
}

function isApiRailAgent(agent: { id?: string; kind?: string }): boolean {
  return agent.kind === 'api' || agent.id === 'api_agent'
}

function isBlueprintRailAgent(agent: { id?: string; kind?: string }): boolean {
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
}: AgentSidebarProps) {
  const pickOrClose = onPick ?? onClose
  const drawerHidden = Boolean(narrow && !open)
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const onChat = pathname.startsWith('/chat') || pathname === '/'
  const selectedTeamId = onChat ? (searchParams.get('team') ?? '') : ''
  const selectedRemoteId = onChat ? (searchParams.get('remote') ?? '') : ''
  const selectedId =
    selectedTeamId || selectedRemoteId
      ? ''
      : defaultBlueprintId(onChat ? searchParams.get('blueprint') : '')

  const [hiddenIds, setHiddenIds] = useState<string[] | null>(() =>
    hasHiddenAgentsStorage() ? loadHiddenAgentIds() : null,
  )
  const [deletedIds, setDeletedIds] = useState<string[]>(() => loadDeletedRailIds())
  const [deleteConfirm, setDeleteConfirm] = useState<ContextMenuState | null>(null)
  const [pins, setPins] = useState<PinnedAgent[]>(() => loadOrSeedPinnedAgents())
  const [hoveringHidden, setHoveringHidden] = useState(false)
  const [pluginsOpen, setPluginsOpen] = useState(false)
  const [remotesPopupOpen, setRemotesPopupOpen] = useState(false)
  const [localWsStatus, setLocalWsStatus] = useState<ChatConnectionStatus>(() => getChatConnection())
  const [cliRunningIds, setCliRunningIds] = useState<Set<string>>(() => new Set())
  const toast = useOptionalToast()

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
    const onOpenPlugins = () => setPluginsOpen(true)
    window.addEventListener(OPEN_PLUGINS_EVENT, onOpenPlugins)
    return () => window.removeEventListener(OPEN_PLUGINS_EVENT, onOpenPlugins)
  }, [])

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
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [picker, setPicker] = useState<PickerState | null>(null)
  const [, setEditsTick] = useState(0)
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)
  const [railOrder, setRailOrder] = useState<string[]>(() => loadRailOrder())
  const [bumpCompleted, setBumpCompleted] = useState(() => loadBumpCompleted())
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
  const [notifyDeniedHint, setNotifyDeniedHint] = useState(false)
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
    if (!notifyDeniedHint) return
    const timer = window.setTimeout(() => setNotifyDeniedHint(false), 6000)
    return () => window.clearTimeout(timer)
  }, [notifyDeniedHint])

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

  const [railWidth, setRailWidth] = useState(() => loadRailWidth())
  const [isResizing, setIsResizing] = useState(false)
  const isAvatarOnly = !narrow && isAvatarOnlyWidth(railWidth)

  const startDragXRef = useRef(0)
  const startWidthRef = useRef(railWidth)

  const handleResizeStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      setIsResizing(true)
      startDragXRef.current = event.clientX
      startWidthRef.current = railWidth
      const target = event.currentTarget
      try {
        target.setPointerCapture(event.pointerId)
      } catch {}

      const handlePointerMove = (e: PointerEvent) => {
        const delta = e.clientX - startDragXRef.current
        const next = clampRailWidth(startWidthRef.current + delta, window.innerWidth)
        setRailWidth(next)
      }

      const handlePointerUp = (e: PointerEvent) => {
        setIsResizing(false)
        try {
          target.releasePointerCapture(e.pointerId)
        } catch {}
        window.removeEventListener('pointermove', handlePointerMove)
        window.removeEventListener('pointerup', handlePointerUp)
        window.removeEventListener('pointercancel', handlePointerUp)
        const finalDelta = e.clientX - startDragXRef.current
        const finalWidth = clampRailWidth(startWidthRef.current + finalDelta, window.innerWidth)
        setRailWidth(finalWidth)
        saveRailWidth(finalWidth)
      }

      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', handlePointerUp)
      window.addEventListener('pointercancel', handlePointerUp)
    },
    [railWidth],
  )

  const handleResizeKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      setRailWidth((prev) => {
        const next = clampRailWidth(prev - 12, window.innerWidth)
        saveRailWidth(next)
        return next
      })
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      setRailWidth((prev) => {
        const next = clampRailWidth(prev + 12, window.innerWidth)
        saveRailWidth(next)
        return next
      })
    } else if (event.key === 'Home') {
      event.preventDefault()
      setRailWidth(MIN_RAIL_WIDTH)
      saveRailWidth(MIN_RAIL_WIDTH)
    } else if (event.key === 'End') {
      event.preventDefault()
      const max = clampRailWidth(MAX_RAIL_WIDTH, window.innerWidth)
      setRailWidth(max)
      saveRailWidth(max)
    }
  }, [])

  useEffect(() => {
    const onChange = () => {
      setSessionTick((n) => n + 1)
      // Search Hidden Bots unhides in localStorage and fires `storage` (same tab).
      if (hasHiddenAgentsStorage()) {
        setHiddenIds(loadHiddenAgentIds())
      }
    }
    window.addEventListener(SCALE_OUT_SESSIONS_EVENT, onChange)
    window.addEventListener(AGENT_CHAT_SESSIONS_EVENT, onChange)
    window.addEventListener(AGENT_CONVERSATION_EVENT, onChange)
    window.addEventListener(GENERATION_COMPLETE_EVENT, onChange)
    window.addEventListener('storage', onChange)
    return () => {
      window.removeEventListener(SCALE_OUT_SESSIONS_EVENT, onChange)
      window.removeEventListener(AGENT_CHAT_SESSIONS_EVENT, onChange)
      window.removeEventListener(AGENT_CONVERSATION_EVENT, onChange)
      window.removeEventListener(GENERATION_COMPLETE_EVENT, onChange)
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
    retry: 1,
  })
  const configuredRemotesList = useMemo(
    () => configuredRemotes(fullRemotesQuery.data),
    [fullRemotesQuery.data],
  )
  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    retry: 1,
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
  const catalog = blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS
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
    const list = [...fromRosters, ...fromBlueprintsNoCli, ...herdr, ...designed]
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
      return 4
    }
    return merged.sort((a, b) => railRank(a) - railRank(b))
  }, [catalog, cliQuery.data, herdrQuery.data, teams, designedAgents])
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
    retry: 1,
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
    blueprintsQuery.isPending ||
    teamsQuery.isPending ||
    remotesQuery.isPending ||
    cliQuery.isPending ||
    herdrQuery.isPending ||
    designsQuery.isPending
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
      })
    }, 300)
    return () => window.clearTimeout(handle)
  }, [pins, resolvedHiddenIds, hostname, prefsReady])

  useEffect(() => {
    const onSettings = () => setSettingsTick((n) => n + 1)
    window.addEventListener(AGENT_SETTINGS_CHANGED_EVENT, onSettings)
    return () => window.removeEventListener(AGENT_SETTINGS_CHANGED_EVENT, onSettings)
  }, [])

  const visibleAgents = useMemo(
    () =>
      agents.filter(
        (agent) =>
          !isRailIdDeleted(agent.id, deletedIds) &&
          (isCliRailAgent(agent) || isApiRailAgent(agent) || !resolvedHiddenIds.includes(agent.id)),
      ),
    [agents, resolvedHiddenIds, deletedIds],
  )
  const hiddenAgents = useMemo(
    () =>
      agents.filter(
        (agent) =>
          !isRailIdDeleted(agent.id, deletedIds) &&
          !isCliRailAgent(agent) &&
          !isApiRailAgent(agent) &&
          resolvedHiddenIds.includes(agent.id),
      ),
    [agents, resolvedHiddenIds, deletedIds],
  )
  const visibleTeams = useMemo(
    () =>
      teams.filter(
        (team) =>
          !isRailIdDeleted(teamHideId(team.id), deletedIds) &&
          !isRailIdDeleted(team.id, deletedIds) &&
          !resolvedHiddenIds.includes(teamHideId(team.id)),
      ),
    [teams, resolvedHiddenIds, deletedIds],
  )
  const visibleRootTeams = useMemo(
    () =>
      rootTeams.filter(
        (team) =>
          !isRailIdDeleted(teamHideId(team.id), deletedIds) &&
          !isRailIdDeleted(team.id, deletedIds) &&
          !resolvedHiddenIds.includes(teamHideId(team.id)),
      ),
    [rootTeams, resolvedHiddenIds, deletedIds],
  )
  const hiddenTeams = useMemo(
    () =>
      teams.filter(
        (team) =>
          !isRailIdDeleted(teamHideId(team.id), deletedIds) &&
          !isRailIdDeleted(team.id, deletedIds) &&
          resolvedHiddenIds.includes(teamHideId(team.id)),
      ),
    [teams, resolvedHiddenIds, deletedIds],
  )
  const visibleRemotes = useMemo(
    () =>
      remotes.filter(
        (remote) =>
          !isRailIdDeleted(remoteHideId(remote.id), deletedIds) &&
          !isRailIdDeleted(remote.id, deletedIds) &&
          !resolvedHiddenIds.includes(remoteHideId(remote.id)),
      ),
    [remotes, resolvedHiddenIds, deletedIds],
  )
  const hiddenRemotes = useMemo(
    () =>
      remotes.filter(
        (remote) =>
          !isRailIdDeleted(remoteHideId(remote.id), deletedIds) &&
          !isRailIdDeleted(remote.id, deletedIds) &&
          resolvedHiddenIds.includes(remoteHideId(remote.id)),
      ),
    [remotes, resolvedHiddenIds, deletedIds],
  )
  const hiddenCount = hiddenAgents.length + hiddenTeams.length + hiddenRemotes.length
  const visibleCount = visibleAgents.length + visibleTeams.length + visibleRemotes.length
  const loadingList = blueprintsQuery.isPending && teamsQuery.isPending
  const loadFailed = blueprintsQuery.isError && teamsQuery.isError && visibleCount === 0
  const supportAgents = visibleAgents.filter((agent) => isSupportAgent(agent))
  const cliAgents = visibleAgents.filter((agent) => isCliRailAgent(agent))
  const apiAgents = visibleAgents.filter((agent) => isApiRailAgent(agent))
  const otherAgents = visibleAgents.filter(
    (agent) => !isSupportAgent(agent) && !isCliRailAgent(agent) && !isApiRailAgent(agent),
  )
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
  const sectionBlocks = useMemo(
    () => partitionRowsBySection(orderedRows, sectionState),
    [orderedRows, sectionState],
  )
  const visibleRowIds = useMemo(() => orderedRows.map((row) => row.id), [orderedRows])
  const knownRailIds = useMemo(() => new Set(agents.map((agent) => agent.id)), [agents])
  const catalogById = useMemo(() => new Map(catalog.map((row) => [row.id, row])), [catalog])
  const catalogReady = !blueprintsQuery.isPending
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
      if (result.permission !== 'granted') {
        setNotifyDeniedHint(true)
      }
    },
    [closeMenu, notifyIds],
  )

  const openPalette = useCallback(() => {
    onOpenSearch?.()
    openSearchPalette()
  }, [onOpenSearch])

  const openGroupPicker = useCallback((title: string, sessions: MemberSession[]) => {
    setPicker({ title, sessions })
  }, [])

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
        if (effectiveFolder) saveAgentEdit(opts.agentId, { folder: effectiveFolder })
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

  const handleAgentSelected = useCallback(
    (agentId: string) => {
      setAddWizardOpen(false)
      navigate(`/chat?blueprint=${encodeURIComponent(agentId)}`)
      onClose?.()
    },
    [navigate, onClose],
  )

  useEffect(() => {
    const onBump = () => setBumpCompleted(loadBumpCompleted())
    window.addEventListener(BUMP_COMPLETED_EVENT, onBump)
    return () => window.removeEventListener(BUMP_COMPLETED_EVENT, onBump)
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
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(bumpRailIdToTop(base, agentId))
    }
    window.addEventListener(GENERATION_COMPLETE_EVENT, onComplete)
    return () => window.removeEventListener(GENERATION_COMPLETE_EVENT, onComplete)
  }, [
    bumpCompleted,
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
        const pin = visiblePins[idx]
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
    if (agent && isHerdrAgent(agent)) return 'remote'
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
    hideDropDepth.current = 0
  }

  const isPinnedId = (id: string | null | undefined) =>
    Boolean(id && pins.some((pin) => pin.id === id))

  /**
   * Hide conceals the id from the conversation list and the visible favourite
   * grid. The pin stays in swarm_pinned_agents so Unhide restores the same
   * favourite slot. Role agents (support, gate, skeptic) are not exempt.
   */
  const hideFromRail = (id: string) => {
    if (!id) return
    if (
      agents.some(
        (agent) => agent.id === id && (isCliRailAgent(agent) || isApiRailAgent(agent)),
      )
    )
      return
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
      if (isPinnedId(fromId)) {
        setPins((current) => unpinAgent(fromId, current))
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

  const openEditor = (agent: Blueprint) => {
    openAgentEditor({ agentId: agent.id })
    onClose?.()
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
        const base = mergeRailOrder(railOrder, visibleRowIds)
        persistVisibleOrder(bumpRailIdToTop(base, createdHide))
        closeMenu()
        return
      }
      if (row.kind === 'remote') {
        const source = configuredRemotesList.find((remote) => remote.id === row.entityId)
        const created = await createRemote({
          kind: source?.kind || row.entityId,
          base_url: source?.base_url,
          api_key_env: source?.api_key_env,
          ui_url: source?.ui_url,
        })
        await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
        await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
        await queryClient.invalidateQueries({ queryKey: ['settings-remotes'] })
        const createdHide = remoteHideId(created.id)
        const base = mergeRailOrder(railOrder, visibleRowIds)
        persistVisibleOrder(bumpRailIdToTop(base, createdHide))
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
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(bumpRailIdToTop(base, created.id))
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
    setDeletedIds((current) => {
      let next = markRailIdDeleted(hideId, current)
      if (row.entityId !== hideId) next = markRailIdDeleted(row.entityId, next)
      return next
    })
    setSectionState((current) => {
      let next = removeSectionMembership(current, hideId)
      if (row.entityId !== hideId) next = removeSectionMembership(next, row.entityId)
      return next
    })
    setDeleteConfirm(null)
  }

  const handleMenuSelect = (id: RailMenuItemId) => {
    if (!menu) return
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
        hasSelectSession: menu.kind === 'api' || menu.kind === 'cli' || Boolean(menu.isCli),
        hasNewSession: menu.kind === 'api' || menu.kind === 'cli' || Boolean(menu.isCli),
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
      })
    : []

  const sectionMenuItemsForOpen = sectionMenu
    ? sectionMenuItems({
        canMoveUp:
          sectionState.sections.findIndex((section) => section.id === sectionMenu.sectionId) > 0,
        canMoveDown:
          sectionState.sections.findIndex((section) => section.id === sectionMenu.sectionId) <
          sectionState.sections.length - 1,
      })
    : []

  const renderAgentRow = (agent: SidebarAgent, hidden: boolean, spillSlot?: number) => {
    const name = agentLabel(agent)
    const herdr = isHerdrAgent(agent)
    const sessions = sessionsByAgent[agent.id] ?? []
    const scaleOut = !herdr && shouldOpenSessionPicker(sessions)
    const active = !herdr && selectedId === agent.id
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
      agent as any,
      cliActivityByAgent[agent.id] ?? null,
    )
    const timestampLabel = formatRailTimestamp(timestamp)
    const unread = unreadIds.includes(agent.id)
    const mark = (
      scaleOut ? (
        // Teams/remotes (#398) must not be stacked here — import AvatarStack there.
        <StackedAvatars sessions={sessions} />
      ) : (
        <AgentAvatar
          src={agent.avatar_path}
          agentId={agent.id}
          size="sm"
        />
      )
    )
    const roleBadgeNode = badge ? (
      <span
        className={`os-agent-role-badge shrink-0 ${roleCssClass(role)}`}
        data-role={role}
        data-definition-id={agent.id}
        role="button"
        tabIndex={0}
        aria-label={`Open ${role} settings`}
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
          openDefinition('role', agent.id, { blueprintId: agent.id })
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            event.stopPropagation()
            openDefinition('role', agent.id, { blueprintId: agent.id })
          }
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
          <span className="flex min-w-0 items-center justify-between gap-1.5">
            <span className="block truncate text-sm font-semibold leading-5">{name}</span>
            <span className="flex items-center gap-1 shrink-0 relative">
              {spillSlot ? (
                <span
                  className="os-rail-shortcut text-[10px] font-mono text-base-content/40 opacity-70 group-hover/row:inline-block hidden"
                  aria-label={`Shortcut ${isMac ? '⌥' : 'Alt+'}${spillSlot}`}
                  data-testid="spill-hotkey"
                >
                  {isMac ? `⌥${spillSlot}` : `Alt+${spillSlot}`}
                </span>
              ) : null}
              {unread ? (
                <span
                  className={`os-rail-unread-dot inline-block h-2 w-2 rounded-full bg-sky-500 shrink-0 ${
                    spillSlot ? 'group-hover/row:hidden' : ''
                  }`}
                  aria-label="Unread"
                  data-testid="rail-unread-dot"
                />
              ) : roleBadgeNode ? (
                roleBadgeNode
              ) : timestampLabel ? (
                <span
                  className={`os-rail-timestamp text-xs text-base-content/40 tabular-nums ${
                    spillSlot ? 'group-hover/row:hidden' : ''
                  }`}
                  data-testid="rail-row-timestamp"
                >
                  {timestampLabel}
                </span>
              ) : null}
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span className="block truncate min-w-0 flex-1">
              {snippet || agent.description}
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
          onClick={pickOrClose}
          {...rowMenuHandlers(agent.id, name, hidden, isHerdrAgent(agent) ? 'remote' : 'api')}
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
            onClick={() => {
              setSessionPicker({ agentId: agent.id, agentName: name, sessions })
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
          onClick={pickOrClose}
        >
          {body}
        </Link>
      </div>
    )
  }

  const renderTeamLink = (team: TeamRoster, hidden: boolean, nested = false, spillSlot?: number) => {
    const name = team.name || team.id
    const hideId = teamHideId(team.id)
    const active = selectedTeamId === team.id
    const sessions = sessionsForTeam(team)
    const declared = declaredRosterForTeam(team, catalog)
    const declaredFaces = declared ? null : teamSidepaneStack(stackFacesForTeam(team))
    const stacked = declaredFaces || { faces: [], remainder: 0 }
    const totalMembers = declared
      ? declared.parsed
        ? declared.count
        : 1
      : team.members
        ? team.members.length
        : stacked.faces.length + (stacked.remainder || 0)
    const singleMember = !declared && totalMembers === 1
    const singleFace = stacked.faces[0]
    const dragging = draggingId === hideId
    const dropping = dropTargetId === hideId
    const { snippet: teamSnippet, timestamp: teamTime } = getRowLastMessage(
      teamHideId(team.id),
      sessions as any,
      team as any,
    )
    const teamTimestampLabel = formatRailTimestamp(teamTime)
    const unread = unreadIds.includes(hideId)
    // Team badge lives in the name row's right slot (unread → badge → timestamp),
    // matching the agent/CoS/support pill placement — not an avatar overlay.
    const teamBadgeNode = (
      <span
        className="os-agent-role-badge shrink-0 badge badge-ghost badge-xs font-medium uppercase tracking-wide text-base-content/55"
        data-kind="team"
        role="button"
        tabIndex={0}
        aria-label={`Open ${name} team settings`}
        data-definition-id={team.id}
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
          openDefinition('team', team.id, { teamId: team.id })
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            event.stopPropagation()
            openDefinition('team', team.id, { teamId: team.id })
          }
        }}
      >
        Team
      </span>
    )
    return (
      <Link
        to={`/chat?team=${encodeURIComponent(team.id)}`}
        className={`os-team-item os-agent-row group/row os-agent-row--team ${
          active ? 'os-agent-row--active' : ''
        } ${nested ? 'os-agent-row--nested' : ''} ${dragging ? 'os-agent-row--dragging' : ''} ${
          dropping ? 'os-agent-row--drop' : ''
        }`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (team)`}
        data-agent-id={hideId}
        data-kind="team"
        data-hotkey={spillSlot}
        data-stack-count={String(declared ? (declared.parsed ? declared.count : 1) : stacked.faces.length)}
        data-remainder={String(declared ? 0 : stacked.remainder)}
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
          {declared ? (
            <PersonaRoster roster={declared} groupId={team.id} label={`${name} declared members`} />
          ) : totalMembers >= 2 ? (
            <AvatarStack
              faces={stacked.faces}
              remainder={stacked.remainder}
              animate
              label={`${name} members`}
            />
          ) : singleMember && singleFace ? (
            <AgentAvatar
              src={singleFace.avatarSrc || singleFace.src}
              agentId={singleFace.id}
              alt={singleFace.name || name}
              size="sm"
            />
          ) : (
            <span
              className="os-team-mark os-agent-team-icon flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-base-300 text-base-content/80"
              aria-hidden="true"
            >
              <Users className="h-3.5 w-3.5" />
            </span>
          )}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 items-center justify-between gap-1.5">
            <span className="block truncate text-sm font-semibold leading-5">{name}</span>
            <span className="flex items-center gap-1 shrink-0 relative">
              {spillSlot ? (
                <span
                  className="os-rail-shortcut text-[10px] font-mono text-base-content/40 opacity-70 group-hover/row:inline-block hidden"
                  aria-label={`Shortcut ${isMac ? '⌥' : 'Alt+'}${spillSlot}`}
                  data-testid="spill-hotkey"
                >
                  {isMac ? `⌥${spillSlot}` : `Alt+${spillSlot}`}
                </span>
              ) : null}
              {unread ? (
                <span
                  className={`os-rail-unread-dot inline-block h-2 w-2 rounded-full bg-sky-500 shrink-0 ${
                    spillSlot ? 'group-hover/row:hidden' : ''
                  }`}
                  aria-label="Unread"
                  data-testid="rail-unread-dot"
                />
              ) : teamBadgeNode ? (
                teamBadgeNode
              ) : teamTimestampLabel ? (
                <span
                  className={`os-rail-timestamp shrink-0 text-xs text-base-content/40 tabular-nums ${
                    spillSlot ? 'group-hover/row:hidden' : ''
                  }`}
                  data-testid="rail-row-timestamp"
                >
                  {teamTimestampLabel}
                </span>
              ) : null}
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span className="block truncate min-w-0 flex-1">
              {teamSnippet || team.description}
            </span>
          </span>
        </span>
      </Link>
    )
  }

  const renderRemoteRow = (remote: RemoteEntry, hidden: boolean, spillSlot?: number) => {
    const name = remote.title
    const hideId = remoteHideId(remote.id)
    const active = selectedRemoteId === remote.id
    const dragging = draggingId === hideId
    const sessions = sessionsForRemote(remote)
    const stacked = teamSidepaneStack(stackFacesForRemote(remote))
    const totalMembers = remote.agents ? remote.agents.length : (stacked.faces.length + (stacked.remainder || 0))
    const singleMember = totalMembers === 1
    const singleFace = stacked.faces[0]
    const { snippet: remoteSnippet, timestamp: remoteTime } = getRowLastMessage(
      hideId,
      sessions as any,
      remote as any,
    )
    const remoteTimestampLabel = formatRailTimestamp(remoteTime)
    const unread = unreadIds.includes(hideId)
    // Remote badge aligns right on the name row like the Team/agent pills.
    const remoteBadgeNode = (
      <span
        className="os-agent-role-badge shrink-0 badge badge-ghost badge-xs font-medium uppercase tracking-wide text-base-content/55"
        data-kind="remote"
        style={{
          fontSize: '0.55rem',
          padding: '0 0.25rem',
          lineHeight: '1.2',
          height: '0.9rem',
          boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
          whiteSpace: 'nowrap',
        }}
      >
        Remote
      </span>
    )
    return (
      <Link
        to={`/chat?remote=${encodeURIComponent(remote.id)}`}
        className={`os-remote-item os-agent-row group/row os-agent-row--remote ${
          active ? 'os-agent-row--active' : ''
        } ${dragging ? 'os-agent-row--dragging' : ''}`}
        aria-current={active ? 'page' : undefined}
        aria-label={`${name} (remote)`}
        data-agent-id={hideId}
        data-kind="remote"
        data-hotkey={spillSlot}
        data-remote-id={remote.id}
        data-stack-count={String(stacked.faces.length)}
        data-remainder={String(stacked.remainder)}
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
          const def = defaultSessionForRemote(remote)
          if (def) {
            navigate(def.href)
            onClose?.()
          } else {
            openGroupPicker(name, sessions)
          }
        }}
        {...rowMenuHandlers(hideId, name, hidden, 'remote', sessions, remote.id)}
      >
        <span className="os-agent-row__avatar-slot relative inline-flex shrink-0 items-center justify-center">
          {totalMembers >= 2 ? (
            <AvatarStack
              faces={stacked.faces}
              remainder={stacked.remainder}
              animate
              label={`${name} members`}
            />
          ) : singleMember && singleFace ? (
            <AgentAvatar
              src={singleFace.avatarSrc || singleFace.src}
              agentId={singleFace.id}
              alt={singleFace.name || name}
              size="sm"
            />
          ) : (
            <span
              className="os-team-mark os-agent-team-icon flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-base-300 text-base-content/80"
              aria-hidden="true"
            >
              <Users className="h-3.5 w-3.5" />
            </span>
          )}
        </span>
        <span className="os-agent-row__label-col min-w-0 flex-1">
          <span className="flex min-w-0 items-center justify-between gap-1.5">
            <span className="block truncate text-sm font-semibold leading-5">{name}</span>
            <span className="flex items-center gap-1 shrink-0 relative">
              {spillSlot ? (
                <span
                  className="os-rail-shortcut text-[10px] font-mono text-base-content/40 opacity-70 group-hover/row:inline-block hidden"
                  aria-label={`Shortcut ${isMac ? '⌥' : 'Alt+'}${spillSlot}`}
                  data-testid="spill-hotkey"
                >
                  {isMac ? `⌥${spillSlot}` : `Alt+${spillSlot}`}
                </span>
              ) : null}
              {unread ? (
                <span
                  className={`os-rail-unread-dot inline-block h-2 w-2 rounded-full bg-sky-500 shrink-0 ${
                    spillSlot ? 'group-hover/row:hidden' : ''
                  }`}
                  aria-label="Unread"
                  data-testid="rail-unread-dot"
                />
              ) : remoteBadgeNode ? (
                remoteBadgeNode
              ) : remoteTimestampLabel ? (
                <span
                  className={`os-rail-timestamp text-xs text-base-content/40 tabular-nums ${
                    spillSlot ? 'group-hover/row:hidden' : ''
                  }`}
                  data-testid="rail-row-timestamp"
                >
                  {remoteTimestampLabel}
                </span>
              ) : null}
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center justify-between gap-1.5 text-xs text-base-content/45">
            <span className="block truncate min-w-0 flex-1">
              {remoteSnippet || (remote as any).description || 'Remote team'}
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
        className={`os-agent-sidebar fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col transition-transform duration-200 lg:static lg:z-0 lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        } ${isAvatarOnly ? 'os-agent-sidebar--avatar-only' : ''}`}
        style={!narrow ? { width: `${railWidth}px` } : { width: '16rem' }}
        aria-label="Agents"
        data-testid="os-agent-rail"
        data-rail-open={open ? 'true' : 'false'}
        data-avatar-only={isAvatarOnly ? 'true' : 'false'}
        aria-hidden={drawerHidden || undefined}
        {...(drawerHidden ? { inert: '' } : {})}
      >
        {!narrow ? (
          <div
            className={`os-rail-resizer ${isResizing ? 'os-rail-resizer--active' : ''}`}
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
        <div className="flex items-center justify-end px-3 pt-3 lg:hidden">
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            aria-label="Close agents sidebar"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="os-rail-search-row flex items-center gap-1.5 px-3 pb-2 pt-3">
          <label className="sr-only" htmlFor="os-rail-search">
            Search
          </label>
          <div
            className="os-rail-search min-w-0 flex-1 cursor-pointer"
            data-testid="rail-search-trigger"
            role="button"
            tabIndex={0}
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
              className="h-3.5 w-3.5 shrink-0 text-base-content/40 cursor-pointer"
              aria-hidden="true"
              data-testid="rail-search-icon"
              onClick={(event) => {
                event.stopPropagation()
                openPalette()
              }}
            />
            <input
              id="os-rail-search"
              type="search"
              className="os-rail-search__input"
              placeholder="Search"
              readOnly
              tabIndex={isAvatarOnly ? -1 : 0}
              autoComplete="off"
              onFocus={(event) => {
                event.currentTarget.blur()
                openPalette()
              }}
              onClick={(event) => {
                event.stopPropagation()
                openPalette()
              }}
            />
            <kbd className="os-rail-search__kbd kbd kbd-xs">{searchShortcut}</kbd>
          </div>
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
            const pinName = live ? agentLabel(live) : pin.name || pin.id
            const role = live ? agentRole(live) : 'default'
            const badge = live ? roleBadgeLabel(role) : ''
            const pinActive = Boolean(selectedId && selectedId === pin.id)
            const pinUnread = unreadIds.includes(pin.id)
            const pinClass = `os-fav-tile group/tile ${
              draggingId === pin.id ? 'os-fav-tile--dragging' : ''
            } ${dropTargetId === pin.id ? 'os-fav-tile--drop' : ''} ${
              pinActive ? 'os-fav-tile--active' : ''
            }`
            const pinFace = (
              <>
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
                <AgentAvatar
                  src={live?.avatar_path}
                  agentId={pin.id}
                  size="lg"
                  className="os-fav-tile__avatar"
                />
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
                  return
                }
                event.preventDefault()
                navigate(agentChatHref(pin.id))
                pickOrClose?.()
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
            className="min-h-0 flex-1 overflow-y-auto px-2 pb-3"
            aria-label="Agent list"
            onContextMenu={(event) => {
              const target = event.target as HTMLElement
              if (target.closest('[data-rail-id], .os-rail-section, .os-pin')) return
              event.preventDefault()
              openPaneMenuAt(event.clientX, event.clientY)
            }}
          >
            <div
              className={`os-agent-list ${listDropActive ? 'os-agent-list--unfav' : ''}`}
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
                      >
                        {isAvatarOnly ? null : (
                          <RailSectionHeader
                            sectionId={block.id}
                            name={block.name}
                            count={block.rows.length}
                            collapsed={block.collapsed}
                            custom={block.custom}
                            editing={editingSectionId === block.id}
                            editValue={editingSectionId === block.id ? editingSectionName : block.name}
                            dropActive={sectionDropId === block.id}
                            onToggle={() =>
                              setSectionState((current) => toggleSectionCollapsed(current, block.id))
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
          aria-label="Hidden Bots"
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
              aria-label={`Hidden Bots ${hiddenCount} (${hiddenCount} hidden)`}
              data-testid="os-hidden-bots-button"
              onClick={() => openSearchPalette({ filterHidden: true })}
              onMouseEnter={() => setHoveringHidden(true)}
              onMouseLeave={() => setHoveringHidden(false)}
            >
              <span className="os-hidden-bots-label font-medium">Hidden Bots</span>
              <span className="os-hidden-bots-tail font-mono text-xs" data-testid="os-hidden-bots-tail">
                <span
                  className={`os-hidden-bots-count ${hoveringHidden ? 'hidden' : 'inline group-hover:hidden'}`}
                  data-testid="os-hidden-bots-count"
                >
                  {hiddenCount}
                </span>
                <span
                  className={`os-hidden-bots-chevron ${hoveringHidden ? 'inline' : 'hidden group-hover:inline'}`}
                  aria-hidden="true"
                  data-testid="os-hidden-bots-chevron"
                >
                  &gt;
                </span>
              </span>
            </button>
          ) : null}
        </div>

        <div className="border-t border-base-300/70 px-3 py-3">
          {/* #182: Teams entry lives in the rail footer, directly above Plugins. */}
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
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
            className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm text-base-content/60 hover:bg-base-300/30 hover:text-base-content"
            onClick={() => setPluginsOpen(true)}
            title="Plugins"
            aria-label="Plugins"
            data-testid="os-plugins-button"
          >
            <Plug className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="os-plugins-label">Plugins</span>
          </button>
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
        </div>
      </aside>

      <PluginsPopup open={pluginsOpen} onClose={() => setPluginsOpen(false)} />

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
                : 'This deletes the local entity and removes it from the rail. This cannot be undone from Hidden Bots.'}
          </p>
        </ConfirmModal>
      )}
      {notifyDeniedHint ? (
        <div
          role="status"
          data-testid="notify-permission-hint"
          className="fixed bottom-4 right-4 z-50 max-w-xs rounded-lg border border-base-300 bg-neutral px-3 py-2 text-sm shadow-xl"
        >
          Notifications are blocked. Enable them in the browser site settings for this page.
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
