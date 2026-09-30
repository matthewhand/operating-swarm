import { apiGet, apiPatch, apiPost } from './api'
import { agentIdFromBlueprint } from './agentChat'
import { parseVoiceBind, type AgentVoiceBind } from './agentVoiceBind'
import { parseProfileFromUnknown, rememberProfile, type AgentProfile } from './agentProfile'
import {
  hydrateEnabledPluginToolIds,
  loadEnabledPluginToolIds,
  persistEnabledPluginToolIds,
} from './chatPluginTools'

/** DaisyUI tooltip copy — keep in sync with Issue #393 / REQ-65. */
export const NEW_CHAT_PER_TASK_LABEL = 'New chat per task'

export const NEW_CHAT_PER_TASK_TOOLTIP =
  'Agents reuse one session by default so they remember the thread. Turn this on for a worker that scales out: each task gets a fresh chat, and several can run at once.'

export { USE_SUGGESTIONS_LABEL, USE_SUGGESTIONS_TOOLTIP } from './suggestions'

export const AGENT_SETTINGS_CHANGED_EVENT = 'swarm:agent-settings-changed'
export const AGENT_DROPDOWNS_CHANGED_EVENT = 'swarm:agent-dropdowns-changed'
export const OPEN_AGENT_EDITOR_EVENT = 'swarm:open-agent-editor'

const STORAGE_PREFIX = 'swarm_agent_settings:'
export const AGENT_DROPDOWNS_STORAGE_KEY = 'swarm_agent_dropdowns'

/** Header dropdown fields that persist per agent (REQ-180 / #636, REQ-200 effort). */
export const AGENT_DROPDOWN_FIELDS = ['cli', 'model', 'remote', 'blueprint', 'api', 'effort'] as const
export type AgentDropdownField = (typeof AGENT_DROPDOWN_FIELDS)[number]
export type AgentDropdownChoice = Partial<Record<AgentDropdownField, string>>
export type AgentDropdowns = Record<string, AgentDropdownChoice>

/** #1312: per-bot exact command allowlist. Empty lists = inactive (allow all). */
export interface CommandAllowlist {
  allow: string[]
  deny: string[]
  ask: string[]
}

export const EMPTY_COMMAND_ALLOWLIST: CommandAllowlist = { allow: [], deny: [], ask: [] }

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  for (const item of value) {
    if (typeof item !== 'string') continue
    const trimmed = item.trim()
    if (trimmed) out.push(trimmed)
  }
  return out
}

export function parseCommandAllowlist(value: unknown): CommandAllowlist {
  const rec = asRecord(value)
  if (!rec) return { ...EMPTY_COMMAND_ALLOWLIST }
  return {
    allow: asStringList(rec.allow),
    deny: asStringList(rec.deny),
    ask: asStringList(rec.ask),
  }
}

export function isCommandAllowlistActive(value: CommandAllowlist): boolean {
  return value.allow.length > 0 || value.deny.length > 0 || value.ask.length > 0
}

export interface AgentSettings extends AgentVoiceBind {
  agent_id: string
  new_chat_per_task: boolean
  use_suggestions: boolean
  cli_session_id?: string | null
  remote_session_id?: string | null
  folder?: string | null
  command_allowlist: CommandAllowlist
  /** #1313: persisted per-bot MCP / connector tool grants. */
  mcp_tool_grants: string[]
  /**
   * True once the operator has saved a grant list, including an explicit empty
   * list (every connector tool Off). False means the server has no policy yet.
   */
  mcp_tool_grants_set: boolean
  active_sessions?: string[]
  /** #1388/#1389 storefront identity — present on settings GET. */
  display_name?: string
  description?: string
  title?: string
  role?: string
  avatar_shape?: string
  avatar_color?: string
  avatar_path?: string | null
  profile?: AgentProfile
}

export type AgentSettingsPatch = Partial<
  Pick<
    AgentSettings,
    'new_chat_per_task' | 'use_suggestions' | 'folder' | 'command_allowlist' | 'mcp_tool_grants'
  > &
    AgentVoiceBind
>

export interface OpenAgentEditorDetail {
  agentId: string
  agentName?: string
}

export interface AgentSettingsChangedDetail extends Partial<AgentVoiceBind> {
  agentId: string
  new_chat_per_task?: boolean
  use_suggestions?: boolean
}

export function openAgentEditor(detail: OpenAgentEditorDetail): void {
  window.dispatchEvent(new CustomEvent<OpenAgentEditorDetail>(OPEN_AGENT_EDITOR_EVENT, { detail }))
}

export function localSettingsKey(agentId: string): string {
  return `${STORAGE_PREFIX}${agentIdFromBlueprint(agentId)}`
}

function readLocalSettings(agentId: string): Record<string, unknown> {
  try {
    const raw = window.localStorage.getItem(localSettingsKey(agentId))
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Record<string, unknown>
  } catch {
    return {}
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function parseAgentDropdownChoice(value: unknown): AgentDropdownChoice | null {
  const rec = asRecord(value)
  if (!rec) return null
  const choice: AgentDropdownChoice = {}
  for (const field of AGENT_DROPDOWN_FIELDS) {
    const raw = rec[field]
    if (typeof raw !== 'string') continue
    const trimmed = raw.trim()
    if (!trimmed) continue
    choice[field] = trimmed
  }
  return Object.keys(choice).length > 0 ? choice : null
}

export function parseAgentDropdowns(raw: unknown): AgentDropdowns {
  const rec = asRecord(raw)
  if (!rec) return {}
  const out: AgentDropdowns = {}
  for (const [agentId, value] of Object.entries(rec)) {
    const id = agentId.trim()
    if (!id) continue
    const choice = parseAgentDropdownChoice(value)
    if (choice) out[id] = choice
  }
  return out
}

function readDropdownMap(): AgentDropdowns {
  try {
    const raw = window.localStorage.getItem(AGENT_DROPDOWNS_STORAGE_KEY)
    if (!raw) return {}
    return parseAgentDropdowns(JSON.parse(raw))
  } catch {
    return {}
  }
}

function writeDropdownMap(map: AgentDropdowns): void {
  try {
    window.localStorage.setItem(AGENT_DROPDOWNS_STORAGE_KEY, JSON.stringify(map))
  } catch {
    /* persistence is best-effort */
  }
}

function emitDropdownsChanged(agentId?: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent(AGENT_DROPDOWNS_CHANGED_EVENT, { detail: { agentId } }),
    )
  } catch {
    /* tests / non-browser */
  }
}

function readLegacyJson(key: string): Record<string, unknown> {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return {}
    return asRecord(JSON.parse(raw)) ?? {}
  } catch {
    return {}
  }
}

/** Import /agents overlay keys so one prefs bag covers both chat surfaces. */
export function seedAgentDropdownsFromLegacyStore(): AgentDropdowns {
  const backends = readLegacyJson('agent_backends')
  const models = readLegacyJson('agent_cli_models')
  const llms = readLegacyJson('agent_llm_profiles')
  const remotes = readLegacyJson('agent_remote_members')
  const blueprints = readLegacyJson('agent_blueprints')
  const ids = new Set([
    ...Object.keys(backends),
    ...Object.keys(models),
    ...Object.keys(llms),
    ...Object.keys(remotes),
    ...Object.keys(blueprints),
  ])
  const out: AgentDropdowns = {}
  for (const id of ids) {
    const choice: AgentDropdownChoice = {}
    const backend = typeof backends[id] === 'string' ? backends[id].trim() : ''
    if (backend.startsWith('cli:')) choice.cli = backend.slice(4)
    if (typeof models[id] === 'string' && models[id].trim()) choice.model = models[id].trim()
    if (typeof llms[id] === 'string' && llms[id].trim()) choice.api = llms[id].trim()
    if (typeof remotes[id] === 'string' && remotes[id].trim()) choice.remote = remotes[id].trim()
    if (typeof blueprints[id] === 'string' && blueprints[id].trim()) {
      choice.blueprint = blueprints[id].trim()
    }
    if (Object.keys(choice).length > 0) out[id] = choice
  }
  return out
}

export function loadAllLocalAgentDropdowns(): AgentDropdowns {
  const stored = readDropdownMap()
  if (Object.keys(stored).length > 0) return stored
  const seeded = seedAgentDropdownsFromLegacyStore()
  if (Object.keys(seeded).length > 0) writeDropdownMap(seeded)
  return seeded
}

export function loadAgentDropdownChoice(agentId: string): AgentDropdownChoice {
  const agent = agentIdFromBlueprint(agentId)
  return loadAllLocalAgentDropdowns()[agent] ?? {}
}

export function applyLocalAgentDropdowns(map: AgentDropdowns): AgentDropdowns {
  const next = parseAgentDropdowns(map)
  writeDropdownMap(next)
  applyAgentDropdownsToLegacyStore(next)
  emitDropdownsChanged()
  return next
}

function applyAgentDropdownsToLegacyStore(map: AgentDropdowns): void {
  const backends = { ...readLegacyJson('agent_backends') }
  const models = { ...readLegacyJson('agent_cli_models') }
  const llms = { ...readLegacyJson('agent_llm_profiles') }
  const remotes = { ...readLegacyJson('agent_remote_members') }
  const blueprints = { ...readLegacyJson('agent_blueprints') }
  for (const [agentId, choice] of Object.entries(map)) {
    if (choice.cli) backends[agentId] = `cli:${choice.cli}`
    if (choice.model) models[agentId] = choice.model
    if (choice.api) llms[agentId] = choice.api
    if (choice.remote) remotes[agentId] = choice.remote
    if (choice.blueprint) blueprints[agentId] = choice.blueprint
  }
  const write = (key: string, value: Record<string, unknown>) => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* best-effort */
    }
  }
  write('agent_backends', backends)
  write('agent_cli_models', models)
  write('agent_llm_profiles', llms)
  write('agent_remote_members', remotes)
  write('agent_blueprints', blueprints)
}

export function saveLocalAgentDropdown(
  agentId: string,
  patch: AgentDropdownChoice,
): AgentDropdownChoice {
  const agent = agentIdFromBlueprint(agentId)
  const map = loadAllLocalAgentDropdowns()
  const current = { ...(map[agent] ?? {}) }
  for (const field of AGENT_DROPDOWN_FIELDS) {
    if (patch[field] === undefined) continue
    const trimmed = patch[field].trim()
    if (!trimmed) delete current[field]
    else current[field] = trimmed
  }
  if (Object.keys(current).length === 0) delete map[agent]
  else map[agent] = current
  writeDropdownMap(map)
  emitDropdownsChanged(agent)
  return current
}

export function loadLocalNewChatPerTask(agentId: string): boolean {
  return readLocalSettings(agentId).new_chat_per_task === true
}

export function loadLocalUseSuggestions(agentId: string): boolean {
  return readLocalSettings(agentId).use_suggestions === true
}

function writeLocalSettings(
  agentId: string,
  patch: AgentSettingsPatch,
): void {
  const agent = agentIdFromBlueprint(agentId)
  try {
    const key = localSettingsKey(agent)
    const parsed = readLocalSettings(agent)
    window.localStorage.setItem(key, JSON.stringify({ ...parsed, ...patch }))
  } catch {
    /* persistence is best-effort */
  }
  try {
    window.dispatchEvent(
      new CustomEvent<AgentSettingsChangedDetail>(AGENT_SETTINGS_CHANGED_EVENT, {
        detail: { agentId: agent, ...patch },
      }),
    )
  } catch {
    /* tests / non-browser */
  }
}

export function saveLocalNewChatPerTask(agentId: string, value: boolean): void {
  writeLocalSettings(agentId, { new_chat_per_task: value })
}

export function saveLocalUseSuggestions(agentId: string, value: boolean): void {
  writeLocalSettings(agentId, { use_suggestions: value })
}

function asSettings(
  agent: string,
  data: Partial<AgentSettings> | null | undefined,
  fallback: { new_chat_per_task: boolean; use_suggestions: boolean },
): AgentSettings {
  const bind = parseVoiceBind(data)
  return {
    agent_id: typeof data?.agent_id === 'string' ? data.agent_id : agent,
    new_chat_per_task:
      typeof data?.new_chat_per_task === 'boolean' ? data.new_chat_per_task : fallback.new_chat_per_task,
    use_suggestions:
      typeof data?.use_suggestions === 'boolean' ? data.use_suggestions : fallback.use_suggestions,
    cli_session_id: data?.cli_session_id ?? null,
    remote_session_id: data?.remote_session_id ?? null,
    folder: typeof data?.folder === 'string' && data.folder.trim() ? data.folder.trim() : null,
    command_allowlist: parseCommandAllowlist(data?.command_allowlist),
    mcp_tool_grants: asStringList(data?.mcp_tool_grants),
    mcp_tool_grants_set: data?.mcp_tool_grants_set === true,
    active_sessions: Array.isArray(data?.active_sessions) ? data.active_sessions : [],
    ...bind,
  }
}

export async function fetchAgentSettings(agentId: string): Promise<AgentSettings> {
  const agent = agentIdFromBlueprint(agentId)
  const localNew = loadLocalNewChatPerTask(agent)
  const localSuggest = loadLocalUseSuggestions(agent)
  try {
    const data = await apiGet<AgentSettings>(
      `/v1/agents/${encodeURIComponent(agent)}/settings/`,
    )
    rememberProfile(agent, parseProfileFromUnknown(data))
    const on = data?.new_chat_per_task === true
    const suggest = data?.use_suggestions === true
    saveLocalNewChatPerTask(agent, on)
    saveLocalUseSuggestions(agent, suggest)
    const settings = asSettings(agent, data, { new_chat_per_task: on, use_suggestions: suggest })
    applyFetchedMcpToolGrants(agent, settings.mcp_tool_grants, settings.mcp_tool_grants_set)
    return settings
  } catch {
    return {
      agent_id: agent,
      new_chat_per_task: localNew,
      use_suggestions: localSuggest,
      command_allowlist: parseCommandAllowlist(readLocalSettings(agent).command_allowlist),
      mcp_tool_grants: loadEnabledPluginToolIds(agent),
      mcp_tool_grants_set: false,
      active_sessions: [],
      ...parseVoiceBind(readLocalSettings(agent)),
    }
  }
}

export async function saveAgentSettings(
  agentId: string,
  patch: AgentSettingsPatch,
): Promise<AgentSettings> {
  const agent = agentIdFromBlueprint(agentId)
  if (patch.new_chat_per_task !== undefined) {
    saveLocalNewChatPerTask(agent, patch.new_chat_per_task)
  }
  if (patch.use_suggestions !== undefined) {
    saveLocalUseSuggestions(agent, patch.use_suggestions)
  }
  writeLocalSettings(agent, patch)
  try {
    const data = await apiPatch<AgentSettings>(
      `/v1/agents/${encodeURIComponent(agent)}/settings/`,
      patch,
    )
    rememberProfile(agent, parseProfileFromUnknown(data))
    const settings = asSettings(agent, data, {
      new_chat_per_task: patch.new_chat_per_task === true || loadLocalNewChatPerTask(agent),
      use_suggestions: patch.use_suggestions === true || loadLocalUseSuggestions(agent),
    })
    if (patch.mcp_tool_grants !== undefined) {
      hydrateEnabledPluginToolIds(agent, settings.mcp_tool_grants)
    }
    return settings
  } catch {
    return {
      agent_id: agent,
      new_chat_per_task: patch.new_chat_per_task ?? loadLocalNewChatPerTask(agent),
      use_suggestions: patch.use_suggestions ?? loadLocalUseSuggestions(agent),
      command_allowlist: parseCommandAllowlist(
        patch.command_allowlist ?? readLocalSettings(agent).command_allowlist,
      ),
      mcp_tool_grants: patch.mcp_tool_grants ?? loadEnabledPluginToolIds(agent),
      mcp_tool_grants_set: patch.mcp_tool_grants !== undefined,
      active_sessions: [],
      ...parseVoiceBind({ ...readLocalSettings(agent), ...patch }),
    }
  }
}

/**
 * #1313: a saved server policy wins, including an explicit empty list.
 * Migrate the local #516 cache up only while the server has never stored one.
 */
export function applyFetchedMcpToolGrants(
  agentId: string,
  grants: readonly string[],
  configured = false,
): string[] {
  const agent = agentIdFromBlueprint(agentId)
  const server = asStringList(grants)
  if (configured || server.length > 0) {
    return hydrateEnabledPluginToolIds(agent, server)
  }
  const local = loadEnabledPluginToolIds(agent)
  if (local.length > 0) {
    void persistEnabledPluginToolIds(agent, local)
  }
  return local
}

export interface AllocatedTaskSession {
  agent_id: string
  conversation_id: string
  new_chat_per_task: boolean
  empty: boolean
  resume_external: boolean
}

export async function allocateAgentTaskSession(
  agentId: string,
  taskId?: string,
): Promise<AllocatedTaskSession | null> {
  const agent = agentIdFromBlueprint(agentId)
  try {
    return await apiPost<AllocatedTaskSession>(
      `/v1/agents/${encodeURIComponent(agent)}/sessions/`,
      taskId ? { task_id: taskId } : {},
    )
  } catch {
    return null
  }
}
