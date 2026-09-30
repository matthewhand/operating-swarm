import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Modal, Select, Textarea, useToast } from './DaisyUI'
import LlmProfileAddForm from './LlmProfileAddForm'
import InferenceOrderList, { type InferenceCatalogOption } from './InferenceOrderList'
import {
  fetchBlueprints,
  fetchBlueprintPersonas,
  fetchCliAgents,
  fetchCliModels,
  fetchLlmProfiles,
  fetchImageGenSettings,
  fetchRemotes,
  generateAgentAvatar,
  type AgentRole,
  type Blueprint,
} from '../lib/api'
import PersonaAvatarThemePicker from './PersonaAvatarThemePicker'
import { RemoteSelect } from './RemoteSelect'
import { configuredRemotes } from '../lib/remotes'
import {
  loadAgentRemoteBinding,
  remotesListForSelect,
  saveAgentRemoteBinding,
} from '../lib/agentRemote'
import {
  assignedBlueprintId,
  loadAgentEdit,
  loadInferenceList,
  saveAgentEdit,
  saveInferenceList,
} from '../lib/agentEdits'
import {
  apiModelOptionsFromProfiles,
  cliModelOptionsFor,
  isApiBlueprintId,
  isApiNamespaceProfile,
} from '../lib/cliAgentContext'
import { FOLDER_FORMAT_ERROR, isValidFolderPath } from '../lib/agentFolder'
import {
  GITHUB_REPO_FORMAT_ERROR,
  emptyWorkspaceFields,
  isValidGithubRepo,
  type AgentWorkspaceFields,
} from '../lib/agentWorkspace'
import AgentWorkspaceBinding from './AgentWorkspaceBinding'
import type { InferenceSeat } from '../lib/inferenceList'
import {
  EMPTY_COMMAND_ALLOWLIST,
  NEW_CHAT_PER_TASK_LABEL,
  NEW_CHAT_PER_TASK_TOOLTIP,
  USE_SUGGESTIONS_LABEL,
  USE_SUGGESTIONS_TOOLTIP,
  fetchAgentSettings,
  parseCommandAllowlist,
  saveAgentSettings,
  type CommandAllowlist,
} from '../lib/agentSettings'
import CommandAllowlistEditor from './settings/CommandAllowlistEditor'
import AgentMcpToolTree from './AgentMcpToolTree'
import AgentSkillsPanel from './AgentSkillsPanel'
import {
  EMPTY_VOICE_BIND,
  parseSpeechMode,
  parseVoiceBind,
  type AgentVoiceBind,
  type SpeechMode,
} from '../lib/agentVoiceBind'
import {
  STREAM_REPLIES_SEAT_LABEL,
  STREAM_REPLIES_SEAT_TOOLTIP,
  loadSeatStreamReplies,
  parseSeatStreamReplies,
  saveSeatStreamReplies,
  type SeatStreamReplies,
} from '../lib/streamReplies'
import {
  agentRole,
  applyBlueprintAssignment,
  assignableBlueprints,
  catalogPickerLabel,
  exampleRoleAgents,
  // #1706 D.14/D.15 — the single "may this seat carry a role?" decision.
  roleEditableForSeat,
  roleAllowedOnSeatKind,
  ROLE_FIELD_UNAVAILABLE_REASON,
} from '../lib/agentRoles'
import { displayNameMatchesBlueprint } from '../lib/railSeats'
import { ROLE_BRIEFS } from '../lib/definitionExplain'
import { agentLabel, sessionKindForAgent } from '../lib/supportAgent'
import { isCliBlueprintId } from '../lib/cliAgentContext'
import { rememberGeneratedAvatar } from '../lib/agentAvatars'
import { defaultAvatarPrompt, isImageGenConfigured, parseImageGenSettings } from '../lib/imageGenSettings'
import {
  AVATAR_SHAPES,
  DEFAULT_AVATAR_SHAPE,
  MAX_DESCRIPTION,
  MAX_DISPLAY_NAME,
  MAX_TITLE,
  defaultProfile,
  fetchAgentProfile,
  normalizeAvatarColor,
  replaceAgentProfile,
  saveAgentProfile,
  type AgentProfile,
  type AvatarShape,
} from '../lib/agentProfile'
import AgentAvatar from './AgentAvatar'
import AgentProfilePreview from './AgentProfilePreview'
import AgentTemplatePackPanel from './AgentTemplatePackPanel'
import { openSettingsSheet } from './settings/kernel'
import { openChromeOverlay } from '../lib/chromeOverlay'
import MailboxAclEditor from './MailboxAclEditor'
import {
  ROLE_CONSUMERS_CHANGED_EVENT,
  loadRoleConsumers,
  saveRoleConsumers,
} from '../lib/roleConsumers'
import { ContextUsageDetail } from './ContextUsageDetail'
import { peekConversationIdForAgent } from '../lib/agentChat'
import CreateRoleModal from './CreateRoleModal'
import {
  CUSTOM_ROLES_UPDATED_EVENT,
  findCustomRole,
  loadCustomRoles,
} from '../lib/customRoles'
import AgentMemoryPanel from './AgentMemoryPanel'
import InlineEditText from './InlineEditText'
import AgentMediaPanel from './AgentMediaPanel'

/** Window event so the rail hover-edit and tests can open the agent editor. */
export const OPEN_AGENT_EDITOR_EVENT = 'swarm:open-agent-editor'

export interface OpenAgentEditorDetail {
  agentId: string
}

export function openAgentEditor(detail: OpenAgentEditorDetail): void {
  window.dispatchEvent(
    new CustomEvent<OpenAgentEditorDetail>(OPEN_AGENT_EDITOR_EVENT, { detail }),
  )
}

const ROLE_OPTIONS: { value: AgentRole; label: string }[] = [
  // #532: the default role is a Worker — 'none' read like a misconfiguration.
  { value: 'default', label: 'Worker (default)' },
  { value: 'support', label: 'support' },
  { value: 'gate', label: 'gate' },
  { value: 'skeptic', label: 'skeptic' },
  { value: 'chief_of_staff', label: 'cos' },
  { value: 'engineer', label: 'engineer' },
  { value: 'suggestions', label: 'suggestions' },
]

const EMPTY_BLUEPRINTS: Blueprint[] = []

/** #1127: the editor's vertical tab rail — the surface is tall, not wide, so
 * sections group into side tabs. Inactive panels stay mounted-but-hidden so
 * in-progress edits (#592) survive tab switches. #1391 adds Memory. */
const EDITOR_TABS = [
  { id: 'identity', label: 'Identity' },
  // #1678: per-agent media. Reads the conversation attachment index; see the
  // design note on the issue for what counts as media and the forget semantics.
  { id: 'media', label: 'Media' },
  { id: 'role', label: 'Role & wiring' },
  { id: 'model', label: 'Model & inference' },
  { id: 'memory', label: 'Memory' },
  { id: 'advanced', label: 'Advanced' },
] as const

type EditorTabId = (typeof EDITOR_TABS)[number]['id']

const EDITOR_TAB_STORAGE_KEY = 'swarm_agent_editor_tab'

function loadEditorTab(): EditorTabId {
  try {
    const stored = sessionStorage.getItem(EDITOR_TAB_STORAGE_KEY)
    if (stored && EDITOR_TABS.some((tab) => tab.id === stored)) return stored as EditorTabId
  } catch {
    /* storage unavailable */
  }
  return 'identity'
}

export interface AgentEditorProps {
  isOpen: boolean
  onClose: () => void
  agentId: string | null
}

/**
 * Agent-scoped editor overlay (REQ-58 / REQ-124).
 *
 * Name, role with explanation, which catalog blueprint this seat uses,
 * kind-appropriate LLM override (disabled for remotes, CLI->model for CLIs,
 * profile->model for API).
 */
export default function AgentEditor({ isOpen, onClose, agentId }: AgentEditorProps) {
  const id = agentId || ''
  const toggleId = useId()
  const suggestionsToggleId = useId()
  const autoSpeakId = useId()
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [storefrontDescription, setStorefrontDescription] = useState('')
  const [profileTitle, setProfileTitle] = useState('')
  const [avatarShape, setAvatarShape] = useState<AvatarShape>(DEFAULT_AVATAR_SHAPE)
  const [avatarColor, setAvatarColor] = useState('')
  const [avatarColorError, setAvatarColorError] = useState<string | null>(null)
  const [role, setRole] = useState<AgentRole>('default')
  // #532: agents wired to *use* this seat for its role (wire-up UI + diagram).
  const [wiredConsumers, setWiredConsumers] = useState<string[]>([])
  const [blueprintId, setBlueprintId] = useState('')
  const [llmOverride, setLlmOverride] = useState('')
  const [cliOverride, setCliOverride] = useState('')
  const [profileOverride, setProfileOverride] = useState('')
  const [newChatPerTask, setNewChatPerTask] = useState(false)
  const [useSuggestions, setUseSuggestions] = useState(false)
  const [commandAllowlist, setCommandAllowlist] = useState<CommandAllowlist>(
    EMPTY_COMMAND_ALLOWLIST,
  )
  const [voiceBind, setVoiceBind] = useState<AgentVoiceBind>(EMPTY_VOICE_BIND)
  // #592: set the moment the user edits one of these fields; hydration skips
  // touched groups so a late settings fetch cannot overwrite in-progress edits.
  const seatTogglesTouchedRef = useRef(false)
  const voiceTouchedRef = useRef(false)
  const commandAllowlistTouchedRef = useRef(false)
  const profileTouchedRef = useRef(false)
  const [streamReplies, setStreamReplies] = useState<SeatStreamReplies>(null)
  const streamRepliesId = useId()
  const [savingSettings, setSavingSettings] = useState(false)
  const [boundRemoteId, setBoundRemoteId] = useState('')
  const [inferenceSeats, setInferenceSeats] = useState<InferenceSeat[]>([])
  const [avatarPrompt, setAvatarPrompt] = useState('')
  const [folder, setFolder] = useState('')
  const [folderError, setFolderError] = useState<string | null>(null)
  const [githubRepo, setGithubRepo] = useState('')
  const [repoError, setRepoError] = useState<string | null>(null)
  const [addingProfile, setAddingProfile] = useState(false)
  const [customRoles, setCustomRoles] = useState(() => loadCustomRoles())
  const [isCreateRoleModalOpen, setIsCreateRoleModalOpen] = useState(false)
  // #1127: selected tab persists across open/close within the session.
  const [activeTab, setActiveTab] = useState<EditorTabId>(loadEditorTab)
  const activeTabRef = useRef<HTMLButtonElement>(null)
  // #1676: opening the pane must actually move focus INTO it. The navbar pill
  // (and the rail's pencil, and every other entry point) dispatches an event;
  // nothing in the browser moves focus for us, and a pane that opens with
  // focus still sitting in the navbar is worse than no pill at all — the
  // keyboard user is still in the header with a dialog on top of it. Focusing
  // the selected tab is the ARIA-correct landing spot for a tabbed surface:
  // the tablist is announced, not a random field.
  useEffect(() => {
    if (!isOpen) return
    activeTabRef.current?.focus()
  }, [isOpen, id])
  const selectTab = (next: EditorTabId) => {
    setActiveTab(next)
    try {
      sessionStorage.setItem(EDITOR_TAB_STORAGE_KEY, next)
    } catch {
      /* storage unavailable */
    }
  }

  useEffect(() => {
    const handleCustomRoles = () => setCustomRoles(loadCustomRoles())
    window.addEventListener(CUSTOM_ROLES_UPDATED_EVENT, handleCustomRoles)
    return () => window.removeEventListener(CUSTOM_ROLES_UPDATED_EVENT, handleCustomRoles)
  }, [])

  // #532: wire-ups may change from another editor instance / ChatPage pills.
  useEffect(() => {
    const sync = () => {
      if (id && isOpen) setWiredConsumers(loadRoleConsumers(id, role))
    }
    window.addEventListener(ROLE_CONSUMERS_CHANGED_EVENT, sync)
    return () => window.removeEventListener(ROLE_CONSUMERS_CHANGED_EVENT, sync)
  }, [id, isOpen, role])

const handleRoleSelect = (val: string) => {
    if (val === '__new_role__') {
      setIsCreateRoleModalOpen(true)
      return
    }
    persistRole(val as AgentRole)
  }

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    enabled: isOpen,
    retry: 1,
  })

  const catalog = useMemo(
    () => assignableBlueprints(exampleRoleAgents(blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS)),
    [blueprintsQuery.data],
  )
  // #532: friendly seat label for the role diagram / checkbox rows.
  const labelFor = (seatId: string): string => {
    if (!seatId) return ''
    const edited = loadAgentEdit(seatId).name
    if (edited) return edited
    const row = catalog.find((item) => item.id === seatId)
    return row?.name || seatId
  }
  // #527: a blueprint that declares ≥2 openai-agents personas gets one
  // avatar picker per persona (single-persona seats have nothing to switch).
  // D6: the persona roster only exists for swarm blueprints. The seat id is
  // used as a fallback recipe id, so the generic API gateway (`api_agent`)
  // must not fire `GET /v1/blueprints/api_agent/personas` — it has no source
  // and would 404 on every editor open. Skip the fetch for those ids.
  const editorRecipeId = blueprintId || id
  const personasQuery = useQuery({
    queryKey: ['blueprint-personas', editorRecipeId],
    queryFn: () => fetchBlueprintPersonas(editorRecipeId),
    enabled: Boolean(editorRecipeId) && isOpen && !isApiBlueprintId(editorRecipeId),
    retry: 1,
  })
  const declaredPersonas = useMemo(() => {
    const list = personasQuery.data?.personas ?? []
    return list.length >= 2 ? list : []
  }, [personasQuery.data])
  const agent = catalog.find((item) => item.id === id)
  const catalogName = agent ? agentLabel({ id: agent.id, name: agent.name }) : id
  const title = id ? `Edit ${catalogName}` : 'Edit agent'

  const agentKind = useMemo(() => {
    if (!id) return 'api'
    const lowerId = id.toLowerCase()
    if (lowerId.startsWith('remote-') || agent?.tags?.includes('remote') || lowerId.includes('remote')) {
      return 'remote'
    }
    if (
      lowerId.startsWith('cli-') ||
      isCliBlueprintId(id) ||
      agent?.tags?.includes('cli') ||
      lowerId.includes('cli')
    ) {
      return 'cli'
    }
    return sessionKindForAgent({ id, tags: agent?.tags })
  }, [id, agent])

  /* #1706 D.14/D.15 — a team or a dedicated chat cannot be assigned a role,
   * so the editor must not offer the field. The pill already refuses to render
   * a badge in those modes (`agentPillLabels`), and the API already rejects
   * the write (`validate_role_for_kind`); this asks the ONE FE decision point
   * so the three cannot drift. The reason string is rendered, not implied. */
  const roleAvailability = useMemo(
    () => roleEditableForSeat(id, agentKind),
    [id, agentKind],
  )

  const allRoleOptions = useMemo(() => {
    const options: { value: string; label: string }[] = [
      ...ROLE_OPTIONS,
      { value: 'advisor', label: 'advisor' },
    ]
    for (const cr of customRoles) {
      if (!options.some((o) => o.value === cr.name)) {
        options.push({ value: cr.name, label: cr.label || cr.name })
      }
    }
    // #853: the support option only renders for API-kind seats — hide rather
    // than disable so the picker never advertises a broken configuration.
    // #1706: the filter is the single FE rule, not a second `role === 'support'`
    // test, so it cannot drift from `roleAllowedOnSeatKind`'s other callers.
    return options.filter((option) =>
      roleAllowedOnSeatKind(option.value, roleAvailability.seatKind),
    )
  }, [customRoles, roleAvailability.seatKind])

  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    enabled: isOpen,
    retry: 1,
  })

  const activeCli = cliOverride || cliQuery.data?.clis?.[0] || ''

  const cliModelsQuery = useQuery({
    queryKey: ['cli-models', activeCli],
    queryFn: () => (activeCli ? fetchCliModels(activeCli) : Promise.resolve({ cli: '', models: [] })),
    enabled: Boolean(isOpen && agentKind === 'cli' && activeCli),
    retry: 1,
    // #612: the per-CLI probe is expensive; reuse the cached list across
    // re-opens (backend also TTL-caches per CLI in swarm.core.cli_models).
    staleTime: 5 * 60 * 1000,
  })

  const llmProfilesQuery = useQuery({
    queryKey: ['llm-profiles'],
    queryFn: fetchLlmProfiles,
    enabled: isOpen,
    retry: 1,
  })

  const remotesQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    enabled: isOpen,
    retry: 1,
  })

  const imageGenQuery = useQuery({
    queryKey: ['image-gen-settings'],
    queryFn: () => fetchImageGenSettings(false),
    enabled: isOpen,
    retry: 1,
  })
  const imageGen = parseImageGenSettings(imageGenQuery.data)
  const canGenerateAvatar = isImageGenConfigured(imageGen)
  const remotesCatalog = remotesListForSelect(
    remotesQuery.data,
    null,
    boundRemoteId ? loadAgentRemoteBinding(id) : null,
  )
  const configuredRemoteRows = configuredRemotes(remotesCatalog)

  const catalogAgentIds = useMemo(
    () => new Set(catalog.map((item) => item.id.toLowerCase())),
    [catalog],
  )

  const availableClis = useMemo(() => {
    return (cliQuery.data?.clis ?? []).filter((c) => !catalogAgentIds.has(c.toLowerCase()))
  }, [cliQuery.data, catalogAgentIds])

  const cliModelOptions = useMemo(
    () => cliModelOptionsFor(cliModelsQuery.data),
    [cliModelsQuery.data],
  )

  const availableCliModels = useMemo(() => {
    return cliModelOptions.models.filter((m) => !catalogAgentIds.has(m.toLowerCase()))
  }, [cliModelOptions.models, catalogAgentIds])

  const availableApiModels = useMemo(() => {
    return apiModelOptionsFromProfiles(llmProfilesQuery.data?.profiles, [
      llmProfilesQuery.data?.default_llm_profile ?? '',
    ]).filter((row) => !catalogAgentIds.has(row.id.toLowerCase()))
  }, [llmProfilesQuery.data, catalogAgentIds])

  useEffect(() => {
    profileTouchedRef.current = false
  }, [isOpen, id])

  useEffect(() => {
    if (!isOpen || !id) return
    const edit = loadAgentEdit(id)
    const catalogAgent = exampleRoleAgents(blueprintsQuery.data?.data ?? []).find(
      (item) => item.id === id,
    )
    setName(edit.name || catalogAgent?.name || id)
    const resolvedRole = edit.role || agentRole({ id, name: catalogAgent?.name, role: catalogAgent?.role })
    setRole(resolvedRole)
    setWiredConsumers(loadRoleConsumers(id, resolvedRole))
    setBlueprintId(edit.blueprintId || id)
    setLlmOverride(edit.llmOverride || '')
    setCliOverride(edit.cliOverride || '')
    setProfileOverride(edit.profileOverride || '')
    setBoundRemoteId(loadAgentRemoteBinding(id)?.id || '')
    setInferenceSeats(loadInferenceList(id))
    setFolder(edit.folder || '')
    setFolderError(null)
    setGithubRepo(edit.githubRepo || '')
    setRepoError(null)
    const catalogNameForPrompt = catalogAgent?.name || id
    const roleForPrompt = edit.role || agentRole({ id, name: catalogAgent?.name, role: catalogAgent?.role })
    setAvatarPrompt(defaultAvatarPrompt(edit.name || catalogNameForPrompt, roleForPrompt))

    let cancelled = false
    ;(async () => {
      const [settings, profile] = await Promise.all([
        fetchAgentSettings(id),
        fetchAgentProfile(id),
      ])
      if (!cancelled) {
        // #592: hydration never clobbers an edit the user already made. The
        // fetch (and a late `blueprintsQuery.data`) can resolve *after* the
        // user toggled/typed — server defaults must not win over them.
        if (!seatTogglesTouchedRef.current) {
          setNewChatPerTask(settings.new_chat_per_task)
          setUseSuggestions(settings.use_suggestions)
        }
        if (!voiceTouchedRef.current) {
          setVoiceBind(parseVoiceBind(settings))
        }
        if (!commandAllowlistTouchedRef.current) {
          setCommandAllowlist(parseCommandAllowlist(settings.command_allowlist))
        }
        if (!profileTouchedRef.current) {
          applyHydratedProfile(profile.profile, {
            catalogName: catalogAgent?.name || id,
            editName: edit.name,
          })
        }
        setStreamReplies(loadSeatStreamReplies(id))
        if (!edit.folder && settings.folder) {
          setFolder(settings.folder)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen, id, blueprintsQuery.data])

  const handleToggleNewChat = async (next: boolean) => {
    seatTogglesTouchedRef.current = true
    setNewChatPerTask(next)
    if (!id) return
    setSavingSettings(true)
    try {
      await saveAgentSettings(id, { new_chat_per_task: next })
    } finally {
      setSavingSettings(false)
    }
  }

  const handleToggleSuggestions = async (next: boolean) => {
    seatTogglesTouchedRef.current = true
    setUseSuggestions(next)
    if (!id) return
    setSavingSettings(true)
    try {
      await saveAgentSettings(id, { use_suggestions: next })
    } finally {
      setSavingSettings(false)
    }
  }

  const persistCommandAllowlist = async (next: CommandAllowlist) => {
    commandAllowlistTouchedRef.current = true
    setCommandAllowlist(next)
    if (!id) return
    setSavingSettings(true)
    try {
      await saveAgentSettings(id, { command_allowlist: next })
    } finally {
      setSavingSettings(false)
    }
  }

  const persistVoicePatch = async (patch: Partial<AgentVoiceBind>) => {
    voiceTouchedRef.current = true
    setVoiceBind((prev) => ({ ...prev, ...patch }))
    if (!id) return
    setSavingSettings(true)
    try {
      await saveAgentSettings(id, patch)
    } finally {
      setSavingSettings(false)
    }
  }

  const persistBlueprint = (nextId: string) => {
    setBlueprintId(nextId)
    const picked = catalog.find((item) => item.id === nextId)
    const next = applyBlueprintAssignment(id, {
      id: nextId,
      role: picked?.role,
      workflow: picked?.workflow,
    })
    if (!next.roleOverridden) {
      setRole(next.role || 'default')
    }
  }

  const applyHydratedProfile = (
    profile: AgentProfile,
    opts: { catalogName: string; editName?: string },
  ) => {
    if (profile.display_name.trim()) {
      setName(profile.display_name)
      saveAgentEdit(id, { name: profile.display_name })
    } else if (!opts.editName) {
      setName(opts.catalogName)
    }
    setStorefrontDescription(profile.description)
    setProfileTitle(profile.title)
    setAvatarShape(profile.avatar_shape || DEFAULT_AVATAR_SHAPE)
    setAvatarColor(profile.avatar_color)
    setAvatarColorError(null)
  }

  const persistProfilePatch = async (patch: Partial<AgentProfile>) => {
    if (!id) return
    profileTouchedRef.current = true
    setSavingSettings(true)
    try {
      await saveAgentProfile(id, patch)
    } catch (err) {
      toastError(
        'Could not save profile',
        err instanceof Error ? err.message : 'Profile save failed.',
      )
    } finally {
      setSavingSettings(false)
    }
  }

  /* ---- #1677 click-to-edit fields ------------------------------------
     These three are now committed through `InlineEditText`, which waits for
     the write and keeps the editor open if it fails. That forces the ordering
     rule the old per-keystroke handlers got wrong: the local value is adopted
     ONLY after the server accepted it. Optimistically setting `name` and then
     firing a patch meant a rejected write left the whole editor (and the
     rail/header rename) showing a value that was never stored. Here a rejection
     propagates to the inline editor, which surfaces the reason and leaves
     `name`/`profileTitle`/`storefrontDescription` exactly where they were. */
  const commitDisplayName = async (next: string) => {
    if (!id) return
    profileTouchedRef.current = true
    setSavingSettings(true)
    try {
      await saveAgentProfile(id, { display_name: next })
      setName(next)
      // The navbar/rail rename is local chrome; it is only written once the
      // profile write has actually landed.
      saveAgentEdit(id, { name: next })
    } finally {
      setSavingSettings(false)
    }
  }

  const commitDescription = async (next: string) => {
    if (!id) return
    profileTouchedRef.current = true
    setSavingSettings(true)
    try {
      await saveAgentProfile(id, { description: next })
      setStorefrontDescription(next)
    } finally {
      setSavingSettings(false)
    }
  }

  const commitTitle = async (next: string) => {
    if (!id) return
    profileTouchedRef.current = true
    setSavingSettings(true)
    try {
      await saveAgentProfile(id, { title: next })
      setProfileTitle(next)
    } finally {
      setSavingSettings(false)
    }
  }

  const persistAvatarShape = (next: AvatarShape) => {
    setAvatarShape(next)
    void persistProfilePatch({ avatar_shape: next })
  }

  const persistAvatarColor = (next: string) => {
    const trimmed = next.trim()
    if (!trimmed) {
      setAvatarColor('')
      setAvatarColorError(null)
      void persistProfilePatch({ avatar_color: '' })
      return
    }
    try {
      const normalized = normalizeAvatarColor(trimmed)
      setAvatarColor(normalized)
      setAvatarColorError(null)
      void persistProfilePatch({ avatar_color: normalized })
    } catch (err) {
      setAvatarColor(trimmed)
      setAvatarColorError(err instanceof Error ? err.message : 'Invalid color.')
    }
  }

  const applyImportedPack = async (pack: { profile: AgentProfile }) => {
    if (!id) return
    profileTouchedRef.current = true
    const next = pack.profile || defaultProfile()
    setName(next.display_name || name)
    setStorefrontDescription(next.description)
    setProfileTitle(next.title)
    setAvatarShape(next.avatar_shape || DEFAULT_AVATAR_SHAPE)
    setAvatarColor(next.avatar_color)
    setAvatarColorError(null)
    if (next.display_name.trim()) saveAgentEdit(id, { name: next.display_name })
    await replaceAgentProfile(id, next)
  }

  const persistRole = (next: AgentRole) => {
    // #853 / #1706 D.16 — one guard for the whole rule. #853: 'support' is
    // exclusive to API-kind seats (structured function-calling hooks that
    // CLI/remote seats lack). #1706: a team or a chat carries no role at all.
    // Bailing here means the local store is never written with a role the
    // backend would reject, so the editor and the API cannot disagree even if
    // this handler is reached by a path that forgot to hide the field.
    if (!roleAllowedOnSeatKind(next, roleAvailability.seatKind)) {
      toastError(
        'Role unavailable',
        roleAvailability.editable
          ? 'Support role is exclusively available to API agents'
          : ROLE_FIELD_UNAVAILABLE_REASON,
      )
      return
    }
    setRole(next)
    saveAgentEdit(id, { role: next, roleOverridden: true })
    if (id) setWiredConsumers(loadRoleConsumers(id, next))
    setAvatarPrompt((current) => {
      const derived = defaultAvatarPrompt(name || catalogName, next)
      if (!current.trim() || current === defaultAvatarPrompt(name || catalogName, role)) {
        return derived
      }
      return current
    })
  }

  const generateAvatar = useMutation({
    mutationFn: () =>
      generateAgentAvatar(id, {
        prompt: avatarPrompt.trim() || defaultAvatarPrompt(name || catalogName, role),
        name: name || catalogName,
        role,
      }),
    onSuccess: (result) => {
      rememberGeneratedAvatar(id, result.avatar_path)
      void persistProfilePatch({ avatar_path: result.avatar_path })
      void queryClient.invalidateQueries({ queryKey: ['image-gen-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      success('Avatar generated', 'Still image stored for this agent.')
    },
    onError: (err: Error) => {
      toastError('Could not generate avatar', err.message)
    },
  })

  const openImageGenSettings = () => {
    onClose()
    openSettingsSheet({ section: 'image-gen' })
  }

  const persistInference = (next: InferenceSeat[]) => {
    setInferenceSeats(next)
    saveInferenceList(id, next)
  }

  const inferenceCatalog = useMemo<InferenceCatalogOption[]>(() => {
    const rows: InferenceCatalogOption[] = []
    const profiles = llmProfilesQuery.data?.profiles ?? []
    if (profiles.length) {
      for (const p of profiles) {
        rows.push({ id: p.id, kind: 'llm', label: p.name || p.id })
      }
    } else {
      for (const id of ['orchestration', 'auxiliary', 'delegation']) {
        rows.push({ id, kind: 'llm', label: id })
      }
    }
    for (const cli of cliQuery.data?.clis ?? []) {
      rows.push({ id: cli, kind: 'cli', label: cli })
    }
    for (const remote of configuredRemoteRows) {
      rows.push({
        id: remote.id,
        kind: 'remote',
        label: remote.label || remote.id,
      })
    }
    return rows
  }, [llmProfilesQuery.data, cliQuery.data, configuredRemoteRows])

  const defaultInferenceLabel =
    llmProfilesQuery.data?.default_llm_profile || 'orchestration'

  const openBlueprintInSettings = () => {
    const assigned = assignedBlueprintId(id) || blueprintId || id
    onClose()
    openSettingsSheet({ section: 'blueprint', blueprintId: assigned })
  }

  const recipeId = blueprintId || id
  const assignedRecipe = catalog.find((item) => item.id === recipeId)
  const nameMatchesRecipe = displayNameMatchesBlueprint(
    name,
    recipeId,
    assignedRecipe?.name,
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      placement="end"
      size="lg"
      className="flex min-h-0 flex-col"
    >
      <div
        id="os-agent-editor"
        className="flex min-h-0 flex-1 gap-4"
        data-agent-id={id || undefined}
      >
        {/* #1127: vertical tab rail — the editor is tall, not wide. */}
        <div
          className="flex w-40 shrink-0 flex-col gap-1 border-r border-base-300 pr-2"
          role="tablist"
          aria-orientation="vertical"
          data-testid="agent-editor-tabs"
        >
          {EDITOR_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`agent-editor-tab-${tab.id}`}
              ref={tab.id === activeTab ? activeTabRef : undefined}
              aria-selected={activeTab === tab.id}
              aria-controls={`agent-editor-panel-${tab.id}`}
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={`rounded-md px-3 py-2 text-left text-sm ${
                activeTab === tab.id
                  ? 'bg-base-200 font-semibold'
                  : 'text-base-content/70 hover:bg-base-200/50'
              }`}
              onClick={() => selectTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="min-w-0 flex-1 overflow-y-auto pr-1">
        <p className="text-sm text-base-content/70">
          This pane is only about this agent. Blueprint picks a catalog recipe
          for this seat — it is not Settings.
        </p>

        <div
          role="tabpanel"
          id="agent-editor-panel-identity"
          aria-labelledby="agent-editor-tab-identity"
          hidden={activeTab !== 'identity' ? true : undefined}
          className="space-y-4"
        >
        {/* #1677: Name / Description / Title are click-to-edit. The idle state
            is a labelled button, the editing state a real input/textarea, and
            both commit through the awaited handlers above so a rejected write
            surfaces instead of being adopted optimistically. */}
        <InlineEditText
          testId="agent-field-name"
          label="Name"
          value={name}
          placeholder="Name this agent"
          maxLength={MAX_DISPLAY_NAME}
          onSave={commitDisplayName}
          hint={`Shown in the rail, the navbar pill, and every message. Up to ${MAX_DISPLAY_NAME} characters.`}
        />
        <InlineEditText
          testId="agent-field-description"
          label="Description"
          value={storefrontDescription}
          placeholder="Add a description"
          multiline
          rows={2}
          allowEmpty
          maxLength={MAX_DESCRIPTION}
          onSave={commitDescription}
          hint="A short blurb for the storefront. Enter adds a line; blur or Cmd/Ctrl+Enter saves."
        />
        <InlineEditText
          testId="agent-field-title"
          label="Title"
          value={profileTitle}
          placeholder="Add a label"
          allowEmpty
          maxLength={MAX_TITLE}
          onSave={commitTitle}
          hint={`The short line under the name. Up to ${MAX_TITLE} characters.`}
        />

        <div
          className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
          data-testid="agent-editor-profile-chrome"
        >
          <span className="text-sm font-semibold text-base-content/80">Avatar chrome</span>
          <p className="text-xs text-base-content/60 mt-0.5">
            Shape and color wrap the rail and chat-header face. Empty color keeps the theme default.
          </p>
          <Select
            label="Avatar shape"
            name="agent-avatar-shape"
            value={avatarShape}
            onChange={(event) => persistAvatarShape(event.target.value as AvatarShape)}
          >
            {AVATAR_SHAPES.map((shape) => (
              <option key={shape} value={shape}>
                {shape}
              </option>
            ))}
          </Select>
          <div className="flex flex-wrap items-end gap-2">
            <Input
              label="Avatar color"
              name="agent-avatar-color"
              value={avatarColor}
              onChange={(event) => persistAvatarColor(event.target.value)}
              placeholder="#f59e0b"
              autoComplete="off"
              spellCheck={false}
              error={avatarColorError || undefined}
            />
            <input
              type="color"
              aria-label="Pick avatar color"
              data-testid="agent-avatar-color-picker"
              className="h-10 w-12 cursor-pointer rounded-md border border-base-300 bg-transparent p-0"
              value={/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(avatarColor) ? avatarColor : '#888888'}
              onChange={(event) => persistAvatarColor(event.target.value)}
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={!avatarColor}
              onClick={() => persistAvatarColor('')}
            >
              Clear color
            </Button>
          </div>
        </div>

        <AgentProfilePreview
          agentId={id}
          profile={{
            display_name: name,
            description: storefrontDescription,
            title: profileTitle,
            role: role === 'default' ? '' : role,
            avatar_shape: avatarShape,
            avatar_color: avatarColorError ? '' : avatarColor,
            avatar_path: null,
          }}
          fallbackName={catalogName}
          caption="Rail / header preview"
        />

        {declaredPersonas.length >= 2 ? (
          <div
            className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
            data-testid="agent-editor-persona-avatars"
          >
            <span className="text-sm font-semibold text-base-content/80">
              Persona avatars
            </span>
            <p className="text-xs text-base-content/60 mt-0.5">
              One face per openai-agents persona — messages from each mode show
              its own avatar in the transcript.
            </p>
            {declaredPersonas.map((persona) => (
              <PersonaAvatarThemePicker
                key={persona.name}
                agentId={editorRecipeId}
                persona={persona.name}
              />
            ))}
          </div>
        ) : null}

        <div
          className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
          data-testid="agent-editor-avatar"
        >
          <div className="flex items-start gap-3">
            <AgentAvatar
              agentId={id}
              alt=""
              size="lg"
              className="shrink-0"
            />
            <div className="min-w-0 flex-1">
              <span className="text-sm font-semibold text-base-content/80">Still avatar</span>
              <p className="text-xs text-base-content/60 mt-0.5">
                Generated stills apply on Bland. Blobs with eyes stay a separate
                Rail theme and ignore generated stills.
              </p>
            </div>
          </div>
          <Textarea
            label="Avatar prompt"
            name="agent-avatar-prompt"
            value={avatarPrompt}
            onChange={(event) => setAvatarPrompt(event.target.value)}
            rows={3}
            spellCheck={false}
          />
          {canGenerateAvatar ? (
            <Button
              type="button"
              variant="primary"
              size="sm"
              disabled={!id || generateAvatar.isPending}
              onClick={() => generateAvatar.mutate()}
            >
              {generateAvatar.isPending ? 'Generating…' : 'Generate avatar'}
            </Button>
          ) : (
            <div className="space-y-2">
              <Button type="button" variant="primary" size="sm" disabled>
                Generate avatar
              </Button>
              <p className="text-xs text-base-content/60" data-testid="generate-avatar-disabled-hint">
                Set a base URL in{' '}
                <button
                  type="button"
                  className="link link-hover font-medium"
                  onClick={openImageGenSettings}
                >
                  Settings → Image generation
                </button>{' '}
                first. Empty/off does not guess a host.
              </p>
            </div>
          )}
        </div>

        <AgentTemplatePackPanel
          agentId={id}
          profile={{
            display_name: name,
            description: storefrontDescription,
            title: profileTitle,
            role: role === 'default' ? '' : role,
            avatar_shape: avatarShape,
            avatar_color: avatarColorError ? '' : avatarColor,
            avatar_path: null,
          }}
          fallbackName={catalogName}
          onApplyPack={applyImportedPack}
        />

        </div>

        {/* #1678: Media. Stays mounted-but-hidden like every other panel so a
            tab switch does not reset it, but the index is only read while this
            tab is selected — opening the editor on Identity does not spend a
            request on media nobody asked for. */}
        <div
          role="tabpanel"
          id="agent-editor-panel-media"
          aria-labelledby="agent-editor-tab-media"
          hidden={activeTab !== 'media' ? true : undefined}
          className="space-y-4"
        >
          <AgentMediaPanel agentId={id} active={activeTab === 'media'} />
        </div>

        <div
          role="tabpanel"
          id="agent-editor-panel-role"
          aria-labelledby="agent-editor-tab-role"
          hidden={activeTab !== 'role' ? true : undefined}
          className="space-y-4"
        >
        <div className="form-control">
          {roleAvailability.editable ? (
            <Select
              label="Role"
              name="agent-role"
              value={role}
              onChange={(event) => handleRoleSelect(event.target.value)}
            >
              {allRoleOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
              <option value="__new_role__">+ Create new role…</option>
            </Select>
          ) : (
            /* #1706 D.14/D.15 — the field is removed, not merely disabled, so a
             * keyboard user cannot tab into a control the API would reject. The
             * reason is real text next to where the field was, and it is
             * announced (`role="status"`) rather than left as a silent gap. */
            <div data-testid="role-field-unavailable" className="space-y-1">
              <span className="text-sm font-medium">Role</span>
              <p
                id="agent-role-unavailable-reason"
                role="status"
                className="text-xs text-base-content/60"
              >
                {ROLE_FIELD_UNAVAILABLE_REASON}
              </p>
            </div>
          )}
          <p className="text-xs text-base-content/70 mt-1" data-testid="role-explanation">
            {ROLE_BRIEFS[role] || findCustomRole(role)?.mechanism_detail || ROLE_BRIEFS.default}
          </p>
          <p className="text-xs text-base-content/55 mt-1" data-testid="role-override-rule">
            Changing Role here wins over the blueprint default. Re-picking a
            blueprint restores that recipe&apos;s role unless you have overridden
            it.
          </p>
        </div>

        {id && role !== 'default' && roleAvailability.editable ? (
          <div
            className="rounded-lg border border-base-300 bg-base-200/40 p-3 space-y-2"
            data-testid="role-consumer-wireup"
          >
            <p className="text-xs font-semibold">
              {catalogName || name || id} is the{' '}
              <span className="uppercase tracking-wide">{role}</span> provider
            </p>
            {wiredConsumers.length === 0 ? (
              <p className="text-xs text-base-content/60" data-testid="role-unused-hint">
                This role is unused until it has been linked to another agent.
              </p>
            ) : (
              <p className="text-xs text-base-content/80" data-testid="role-verb-diagram">
                {wiredConsumers.map((cid) => labelFor(cid) || cid).join(', ')}{' '}
                {wiredConsumers.length === 1 ? 'consults' : 'consult'}{' '}
                {catalogName || name || id} as its {role} provider.
              </p>
            )}
            <div className="space-y-1">
              <span className="text-xs text-base-content/70">Wired agents:</span>
              {catalog.length === 0 ? (
                <p className="text-xs text-base-content/50">Catalog unavailable.</p>
              ) : (
                catalog
                  .filter((item) => item.id !== id)
                  .map((item) => {
                    const checked = wiredConsumers.includes(item.id)
                    return (
                      <label
                        key={item.id}
                        className="flex cursor-pointer items-center gap-2 text-xs"
                      >
                        <input
                          type="checkbox"
                          className="checkbox checkbox-xs"
                          checked={checked}
                          onChange={() => {
                            if (!id) return
                            const next = checked
                              ? wiredConsumers.filter((c) => c !== item.id)
                              : [...wiredConsumers, item.id]
                            setWiredConsumers(saveRoleConsumers(id, role, next))
                          }}
                          data-testid={`wire-consumer-${item.id}`}
                        />
                        <span>{catalogPickerLabel(item)}</span>
                      </label>
                    )
                  })
              )}
            </div>
          </div>
        ) : null}

        {id ? <MailboxAclEditor agentId={id} role={role} /> : null}

        </div>

        <div
          role="tabpanel"
          id="agent-editor-panel-model"
          aria-labelledby="agent-editor-tab-model"
          hidden={activeTab !== 'model' ? true : undefined}
          className="space-y-4"
        >
        <div className="space-y-1">
          <Select
            label={nameMatchesRecipe ? undefined : 'Blueprint'}
            aria-label="Blueprint"
            name="agent-blueprint"
            value={blueprintId}
            onChange={(event) => persistBlueprint(event.target.value)}
          >
            {catalog.length === 0 || !catalog.some((item) => item.id === recipeId) ? (
              <option value={recipeId}>{recipeId || 'Loading…'}</option>
            ) : null}
            {catalog.map((item) => (
              <option key={item.id} value={item.id}>
                {catalogPickerLabel(item)}
              </option>
            ))}
          </Select>
          {nameMatchesRecipe ? (
            <p
              className="text-xs text-base-content/60"
              data-testid="blueprint-recipe-meta"
            >
              Recipe: {recipeId}
            </p>
          ) : null}
        </div>

        <InferenceOrderList
          seats={inferenceSeats}
          catalog={inferenceCatalog}
          defaultLabel={defaultInferenceLabel}
          onChange={persistInference}
        />

        {agentKind !== 'remote' ? (
          <AgentSkillsPanel agentId={id} enabled={isOpen} />
        ) : null}

        </div>

        <div
          role="tabpanel"
          id="agent-editor-panel-memory"
          aria-labelledby="agent-editor-tab-memory"
          hidden={activeTab !== 'memory' ? true : undefined}
          className="space-y-4"
        >
          {id && isOpen ? <AgentMemoryPanel agentId={id} /> : null}
        </div>

        <div
          role="tabpanel"
          id="agent-editor-panel-advanced"
          aria-labelledby="agent-editor-tab-advanced"
          hidden={activeTab !== 'advanced' ? true : undefined}
          className="space-y-4"
        >
        {id ? <AgentMcpToolTree agentId={id} active={activeTab === 'advanced'} /> : null}
        <div
          className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
          data-testid="agent-editor-voice"
        >
          <div>
            <span className="text-sm font-semibold text-base-content/80">Voice</span>
            <p className="text-xs text-base-content/60 mt-0.5">
              This robot&apos;s voice chat. Inherit uses Settings → Speech. Empty bind
              stays on the global path.
            </p>
          </div>
          <Select
            label="Speech mode"
            name="agent-speech-mode"
            size="sm"
            aria-label="Speech mode"
            value={voiceBind.speech_mode}
            disabled={!id || savingSettings}
            onChange={(event) => {
              const next = parseSpeechMode(event.target.value)
              void persistVoicePatch({ speech_mode: next as SpeechMode })
            }}
          >
            <option value="inherit">Inherit global speech</option>
            <option value="voice">Voice (this agent)</option>
            <option value="endpoint">This robot&apos;s audio endpoint</option>
          </Select>
          {voiceBind.speech_mode !== 'inherit' ? (
            <>
              <Input
                label="TTS voice"
                name="agent-tts-voice"
                size="sm"
                value={voiceBind.tts_voice}
                disabled={!id || savingSettings}
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, tts_voice: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ tts_voice: event.target.value.trim() })
                }}
                spellCheck={false}
              />
              <Textarea
                label="Voice instruction"
                name="agent-tts-voice-instruction"
                value={voiceBind.tts_voice_instruction}
                disabled={!id || savingSettings}
                onChange={(event) =>
                  setVoiceBind((prev) => ({
                    ...prev,
                    tts_voice_instruction: event.target.value,
                  }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ tts_voice_instruction: event.target.value.trim() })
                }}
                rows={3}
                spellCheck={false}
              />
            </>
          ) : null}
          {voiceBind.speech_mode === 'endpoint' ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Input
                label="STT base URL"
                name="agent-stt-base-url"
                size="sm"
                value={voiceBind.stt_base_url}
                disabled={!id || savingSettings}
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, stt_base_url: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ stt_base_url: event.target.value.trim() })
                }}
                spellCheck={false}
              />
              <Input
                label="STT model"
                name="agent-stt-model"
                size="sm"
                value={voiceBind.stt_model}
                disabled={!id || savingSettings}
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, stt_model: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ stt_model: event.target.value.trim() })
                }}
                spellCheck={false}
              />
              <Input
                label="STT API key env"
                name="agent-stt-api-key-env"
                size="sm"
                value={voiceBind.stt_api_key_env}
                disabled={!id || savingSettings}
                placeholder="STT_API_KEY"
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, stt_api_key_env: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ stt_api_key_env: event.target.value.trim() })
                }}
                spellCheck={false}
              />
              <Input
                label="TTS base URL"
                name="agent-tts-base-url"
                size="sm"
                value={voiceBind.tts_base_url}
                disabled={!id || savingSettings}
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, tts_base_url: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ tts_base_url: event.target.value.trim() })
                }}
                spellCheck={false}
              />
              <Input
                label="TTS model"
                name="agent-tts-model"
                size="sm"
                value={voiceBind.tts_model}
                disabled={!id || savingSettings}
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, tts_model: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ tts_model: event.target.value.trim() })
                }}
                spellCheck={false}
              />
              <Input
                label="TTS API key env"
                name="agent-tts-api-key-env"
                size="sm"
                value={voiceBind.tts_api_key_env}
                disabled={!id || savingSettings}
                placeholder="TTS_API_KEY"
                onChange={(event) =>
                  setVoiceBind((prev) => ({ ...prev, tts_api_key_env: event.target.value }))
                }
                onBlur={(event) => {
                  void persistVoicePatch({ tts_api_key_env: event.target.value.trim() })
                }}
                spellCheck={false}
              />
            </div>
          ) : null}
          <label
            htmlFor={autoSpeakId}
            className="label cursor-pointer items-center justify-between gap-4 px-0 py-1"
          >
            <span className="label-text text-sm">Auto-speak replies</span>
            <input
              id={autoSpeakId}
              type="checkbox"
              className="toggle toggle-primary toggle-sm"
              role="switch"
              aria-label="Auto-speak replies"
              checked={voiceBind.auto_speak_replies}
              disabled={!id || savingSettings}
              onChange={(event) => {
                void persistVoicePatch({ auto_speak_replies: event.target.checked })
              }}
            />
          </label>
        </div>

        {/* LLM Override Picker by Kind (REQ-124) */}
        {agentKind === 'remote' && (
          <div className="space-y-3">
            {configuredRemoteRows.length === 0 ? (
              <div className="rounded-box border border-base-300 bg-base-200/40 p-3">
                <span className="text-sm font-semibold">Remote</span>
                <p className="text-xs text-base-content/60 mt-1">
                  Add a remote before this agent is usable.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    onClose()
                    openSettingsSheet({ section: 'remotes', addRemote: true })
                  }}
                >
                  Add remote
                </Button>
              </div>
            ) : (
              <RemoteSelect
                remotes={remotesCatalog}
                value={boundRemoteId}
                onChange={(nextId) => {
                  setBoundRemoteId(nextId)
                  const remote = configuredRemoteRows.find((row) => row.id === nextId)
                  saveAgentRemoteBinding(
                    id,
                    remote ? { id: remote.id, kind: remote.kind || remote.id } : null,
                  )
                }}
                label="Remote"
              />
            )}
            <div className="rounded-box border border-base-300 bg-base-200/40 p-3 opacity-60">
              <span className="text-sm font-semibold text-base-content/70">LLM override</span>
              <p className="text-xs text-base-content/60 mt-1">Remotes keep their own models</p>
            </div>
          </div>
        )}

        {agentKind === 'cli' && (
          <div className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3">
            <div>
              <span className="text-sm font-semibold text-base-content/80">LLM override</span>
              <p className="text-xs text-base-content/60 mt-0.5" data-testid="default-llm-label">
                Default would be: {availableClis[0] || 'CLI default'} / {availableCliModels[0] || 'none'}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">CLI</span>
                </label>
                <select
                  aria-label="CLI override"
                  className="select select-bordered select-sm w-full"
                  value={cliOverride}
                  onChange={(e) => {
                    const nextCli = e.target.value
                    setCliOverride(nextCli)
                    saveAgentEdit(id, { cliOverride: nextCli, llmOverride })
                  }}
                >
                  <option value="">Default CLI</option>
                  {availableClis.map((cli) => (
                    <option key={cli} value={cli}>
                      {cli}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Model</span>
                </label>
                <select
                  aria-label="Model override"
                  className="select select-bordered select-sm w-full"
                  value={llmOverride}
                  onChange={(e) => {
                    const nextModel = e.target.value
                    setLlmOverride(nextModel)
                    saveAgentEdit(id, { cliOverride, llmOverride: nextModel })
                  }}
                >
                  <option value="">Default model</option>
                  {availableCliModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {agentKind === 'api' && (
          <div className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3">
            <div>
              <span className="text-sm font-semibold text-base-content/80">LLM override</span>
              <p className="text-xs text-base-content/60 mt-0.5" data-testid="default-llm-label">
                Default would be:{' '}
                {llmProfilesQuery.data?.default_llm_profile || 'orchestration'}
                {availableApiModels.length > 0 ? ` / ${availableApiModels[0].label}` : ''}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">API / LLM profile</span>
                </label>
                <select
                  aria-label="API profile override"
                  className="select select-bordered select-sm w-full"
                  value={profileOverride}
                  onChange={(e) => {
                    const nextProfile = e.target.value
                    setProfileOverride(nextProfile)
                    saveAgentEdit(id, { profileOverride: nextProfile, llmOverride })
                  }}
                >
                  <option value="">Default profile</option>
                  <option value="orchestration">User chat / orchestration</option>
                  <option value="auxiliary">Auxiliary (code summary)</option>
                  <option value="delegation">Delegation (design / coding)</option>
                  {(llmProfilesQuery.data?.profiles ?? [])
                    .filter((p) => isApiNamespaceProfile(p))
                    .filter((p) => !['orchestration', 'auxiliary', 'delegation'].includes(p.id))
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name || p.id}
                      </option>
                    ))}
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Model</span>
                </label>
                <select
                  aria-label="Model override"
                  className="select select-bordered select-sm w-full"
                  value={llmOverride}
                  onChange={(e) => {
                    const nextModel = e.target.value
                    setLlmOverride(nextModel)
                    saveAgentEdit(id, { profileOverride, llmOverride: nextModel })
                  }}
                >
                  <option value="">Default model</option>
                  {availableApiModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {addingProfile ? (
              <LlmProfileAddForm
                className="space-y-3 rounded-box border border-base-300 bg-base-100 p-3"
                onCancel={() => setAddingProfile(false)}
                onSaved={async () => {
                  setAddingProfile(false)
                  await llmProfilesQuery.refetch()
                }}
              />
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setAddingProfile(true)}
              >
                Add LLM profile
              </Button>
            )}
          </div>
        )}

        <AgentWorkspaceBinding
          kind={agentKind === 'cli' || agentKind === 'remote' ? agentKind : 'api'}
          value={
            agentKind === 'cli'
              ? { folder, githubRepo, workspacesEnabled: false }
              : emptyWorkspaceFields()
          }
          folderError={folderError}
          repoError={repoError}
          onChange={(next: AgentWorkspaceFields) => {
            if (agentKind !== 'cli' || !id) return
            setFolder(next.folder)
            setGithubRepo(next.githubRepo)
            if (next.folder && !isValidFolderPath(next.folder)) {
              setFolderError(FOLDER_FORMAT_ERROR)
              return
            }
            setFolderError(null)
            if (next.githubRepo && !isValidGithubRepo(next.githubRepo)) {
              setRepoError(GITHUB_REPO_FORMAT_ERROR)
              saveAgentEdit(id, { folder: next.folder, githubRepo: next.githubRepo, workspacesEnabled: false })
              return
            }
            setRepoError(null)
            saveAgentEdit(id, {
              folder: next.folder,
              githubRepo: next.githubRepo,
              workspacesEnabled: false,
            })
            void saveAgentSettings(id, { folder: next.folder.trim() })
          }}
        />

        {id ? (
          <ContextUsageDetail
            agentId={id}
            conversationId={peekConversationIdForAgent(id)}
          />
        ) : null}

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={NEW_CHAT_PER_TASK_TOOLTIP}
        >
          <label
            htmlFor={toggleId}
            className="label cursor-pointer items-center justify-between gap-4 rounded-box border border-base-300 bg-base-200/60 px-4 py-3"
          >
            <span className="label-text text-base font-semibold">{NEW_CHAT_PER_TASK_LABEL}</span>
            <input
              id={toggleId}
              type="checkbox"
              className="toggle toggle-primary"
              role="switch"
              aria-label={NEW_CHAT_PER_TASK_LABEL}
              checked={newChatPerTask}
              disabled={!id || savingSettings}
              onChange={(event) => handleToggleNewChat(event.target.checked)}
            />
          </label>
        </div>

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={USE_SUGGESTIONS_TOOLTIP}
        >
          <label
            htmlFor={suggestionsToggleId}
            className="label cursor-pointer items-center justify-between gap-4 rounded-box border border-base-300 bg-base-200/60 px-4 py-3"
          >
            <span className="label-text text-base font-semibold">{USE_SUGGESTIONS_LABEL}</span>
            <input
              id={suggestionsToggleId}
              type="checkbox"
              className="toggle toggle-primary"
              role="switch"
              aria-label={USE_SUGGESTIONS_LABEL}
              checked={useSuggestions}
              disabled={!id || savingSettings}
              onChange={(event) => handleToggleSuggestions(event.target.checked)}
            />
          </label>
        </div>

        <CommandAllowlistEditor
          value={commandAllowlist}
          disabled={!id || savingSettings}
          onChange={(next) => void persistCommandAllowlist(next)}
        />

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={STREAM_REPLIES_SEAT_TOOLTIP}
        >
          <label htmlFor={streamRepliesId} className="label py-0">
            <span className="label-text text-base font-semibold">{STREAM_REPLIES_SEAT_LABEL}</span>
          </label>
          <select
            id={streamRepliesId}
            className="select select-bordered w-full"
            aria-label={STREAM_REPLIES_SEAT_LABEL}
            data-testid="seat-stream-replies"
            value={streamReplies === null ? 'inherit' : streamReplies ? 'on' : 'off'}
            disabled={!id}
            onChange={(event) => {
              const next = parseSeatStreamReplies(
                event.target.value === 'inherit' ? 'inherit' : event.target.value,
              )
              setStreamReplies(next)
              if (id) saveSeatStreamReplies(id, next)
            }}
          >
            <option value="inherit">Inherit user preference</option>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={!id}
            onClick={openBlueprintInSettings}
          >
            Edit blueprint…
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={!id}
            data-testid="agent-editor-templates"
            onClick={() => {
              onClose()
              openChromeOverlay('templates')
            }}
          >
            Templates…
          </Button>
        </div>
        </div>
      </div>

      <div className="modal-action mt-4">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>

      <CreateRoleModal
        isOpen={isCreateRoleModalOpen}
        onClose={() => setIsCreateRoleModalOpen(false)}
        onCreated={(newRoleName) => {
          persistRole(newRoleName as AgentRole)
        }}
      />
    </Modal>
  )
}
