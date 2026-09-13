/**
 * Minimal typed fetch wrapper for the Open Swarm backend API.
 *
 * In dev, requests to /v1/* are proxied to the Django backend by Vite
 * (see vite.config.ts). An optional bearer token is read from localStorage
 * under the key "swarm_api_token".
 */

export const API_TOKEN_STORAGE_KEY = 'swarm_api_token'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Thrown when the backend rejects a request with 401/403. A matching
 * AUTH_ERROR_EVENT is dispatched on `window` for any listener (banner / CTA).
 * SPA Settings token UI was deleted with ADR-001; REST still reads
 * localStorage bearer when present.
 */
export class ApiAuthError extends ApiError {
  constructor(status: number, message: string) {
    super(status, message)
    this.name = 'ApiAuthError'
  }
}

export function isAuthError(error: unknown): error is ApiAuthError {
  return error instanceof ApiAuthError
}

export interface AuthErrorDetail {
  status: number
  message: string
}

export const AUTH_ERROR_EVENT = 'swarm:auth-error'

function getAuthToken(): string | null {
  try {
    return window.localStorage.getItem(API_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

function getCookie(name: string): string | null {
  try {
    const match = document.cookie
      .split('; ')
      .find((row) => row.startsWith(`${name}=`))
    return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : null
  } catch {
    return null
  }
}

function buildHeaders(hasBody: boolean): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getAuthToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (hasBody) {
    headers['Content-Type'] = 'application/json'
  }
  // Django session auth enforces CSRF on unsafe methods; include the token
  // when the cookie is present (harmless for token/anonymous access).
  const csrfToken = getCookie('csrftoken')
  if (csrfToken) {
    headers['X-CSRFToken'] = csrfToken
  }
  return headers
}

async function throwApiError(path: string, response: Response): Promise<never> {
  let detail = ''
  try {
    const body = await response.json()
    detail = body?.error ?? body?.detail ?? ''
  } catch {
    // Non-JSON error body; fall through to generic message.
  }
  const message =
    detail || `Request to ${path} failed with status ${response.status}`

  if (response.status === 401 || response.status === 403) {
    const eventDetail: AuthErrorDetail = { status: response.status, message }
    try {
      window.dispatchEvent(
        new CustomEvent<AuthErrorDetail>(AUTH_ERROR_EVENT, {
          detail: eventDetail,
        }),
      )
    } catch {
      // Non-browser environment (tests); the typed error below still surfaces.
    }
    throw new ApiAuthError(response.status, message)
  }

  throw new ApiError(response.status, message)
}

/** Session/bearer fetch used by Agent Router (`agent-api.ts`). */
export async function fetchWithAuth(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = {
    ...buildHeaders(Boolean(init.body)),
    ...(init.headers as Record<string, string> | undefined),
  }
  return fetch(path, { ...init, headers, credentials: 'include' })
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: buildHeaders(false) })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'PATCH',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'PUT',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}

/** Multipart POST. Do not set Content-Type — the browser supplies the boundary. */
export async function apiPostForm<T>(path: string, body: FormData): Promise<T> {
  const headers = buildHeaders(false)
  const response = await fetch(path, {
    method: 'POST',
    headers,
    body,
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(path, {
    method: 'DELETE',
    headers: buildHeaders(false),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }
}

// ---------------------------------------------------------------------------
// Endpoint types (shapes verified against src/swarm/views/api_views.py)
// ---------------------------------------------------------------------------

export interface ListResponse<T> {
  object: 'list'
  data: T[]
}

/** Visual / wiring role on a Team member (REQ-9 / REQ-25 / REQ-28 / REQ-42 / REQ-75). */
export type AgentRole =
  | 'default'
  | 'support'
  | 'gate'
  | 'skeptic'
  | 'chief_of_staff'
  | 'engineer'
  | 'suggestions'

/** Optional openai-agents workflow hint on a blueprint (REQ-75). */
export type BlueprintWorkflow = 'handoff' | 'as_tool'

export interface BlueprintAgent {
  name: string
  role: AgentRole
}

/** GET /v1/blueprints/ (BlueprintsListView) */
export interface Blueprint {
  id: string
  object: 'blueprint'
  name: string
  description: string
  abbreviation: string | null
  required_mcp_servers: string[]
  tags: string[]
  installed: boolean | null
  compiled: boolean | null
  /** First-class role for sidepane highlighting when the API sends it. */
  role?: AgentRole | string | null
  agents?: BlueprintAgent[]
  gate_agent?: string | null
  skeptic_agent?: string | null
  chief_of_staff_agent?: string | null
  suggestions_agent?: string | null
  /** Optional openai-agents workflow hint (handoff / as_tool). Metadata only. */
  workflow?: BlueprintWorkflow | string | null
  /** Leftover webui/django-chat recipe. Pickers must hide these (REQ-75). */
  webui?: boolean | null
  /** REQ-170: true = AGENTS rail seat. Missing/false = catalog-only. */
  rail?: boolean | null
  kind?: string | null
  /** REQ-171B: first-class CLI command on Add-agent seats (not a code comment). */
  command?: string | null
  cli?: string | null
  source?: string | null
  user_created?: boolean | null
  urls_module?: string | null
  url_prefix?: string | null
  /** Optional custom face URL. Missing/blank → SPA bland (or Bert) default. */
  avatar_path?: string | null
  /** Declared openai-agents personas from a static source parse (REQ-81). */
  persona_count?: number
  personas?: Array<{ name: string }>
  /** Navbar items contributed by this blueprint (e.g. token counter for API agents). */
  navbar_items?: Array<{ id: string; kind: string; label?: string; [key: string]: any }> | null
}

/** GET /v1/support/context/ — live agents + inference for the System → Support pill. */
export interface SupportChip {
  label: string
  href: string
}

export interface SupportContext {
  object: 'support.context'
  agents: Array<Pick<Blueprint, 'id' | 'name' | 'description' | 'role'>>
  agent_count: number
  inference: {
    configured: boolean
    profiles: string[]
    env_signals: string[]
    quickstart: {
      doc: string
      anchor: string
      settings: string
      profiles: string
      cli: string
    }
  }
  create: Record<string, string>
  chips?: Record<string, SupportChip>
  /** Compressed intel for the System → Support pill popover. */
  briefing?: string
  /** Back-compat alias of briefing. */
  welcome?: string
}

export function fetchSupportContext(): Promise<SupportContext> {
  return apiGet<SupportContext>('/v1/support/context/')
}

/** GET /v1/models/ (OpenAI-style model list) */
export interface Model {
  id: string
  object: 'model'
  created: number
  owned_by: string
}

/** GET/POST /v1/teams/ and DELETE /v1/teams/<id>/ (swarm/views/teams_api.py) */
export interface Team {
  id: string
  object: 'team'
  description: string
  llm_profile: string
}

export interface CreateTeamRequest {
  name: string
  description?: string
  llm_profile?: string
}

/**
 * GET/POST /v1/library/ and DELETE /v1/library/<name>/
 * (swarm/views/library_api.py). Backed by the same blueprint_library.json
 * used by the server-rendered /blueprint-library/ pages.
 */
export interface LibraryEntry {
  id: string
  object: 'library.blueprint'
  name: string
  description: string
}

export function fetchBlueprints(): Promise<ListResponse<Blueprint>> {
  return apiGet<ListResponse<Blueprint>>('/v1/blueprints/')
}

/** GET /v1/runtime/ — REQ-45 app runtime banner (AllowAny, no secrets). */
export function fetchRuntimeBanner(): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>('/v1/runtime/')
}

/** GET /v1/browser-control/ — REQ-45 provider catalog (this-machine default). */
export function fetchBrowserControl(): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>('/v1/browser-control/')
}

export function fetchModels(): Promise<ListResponse<Model>> {
  return apiGet<ListResponse<Model>>('/v1/models/')
}

/** Task-class roles for REQ-43. These are not required model ids. */
export const LLM_TASK_CLASSES = ['orchestration', 'auxiliary', 'delegation'] as const
export type LlmTaskClass = (typeof LLM_TASK_CLASSES)[number]

export interface LlmProfile {
  id: string
  object: 'llm_profile'
  source: string
  owned_by: string
  name?: string
  model?: string
  base_url?: string
  intelligence?: number
  speed?: number
  cost?: number
  context_length?: number
  context_window?: number
  max_context?: number
}

export interface LlmTaskRoute {
  profile: string
  task_class: string
  used_fallback: boolean
  warning: string | null
  override_on: boolean
  source: string
}

/** GET/POST/PUT/PATCH /v1/llm-profiles/ — named profiles + settings.default_llm_profile SoT. */
export interface LlmProfilesSettings {
  object: 'llm_profiles'
  profiles: LlmProfile[]
  default_llm_profile: string
  default_is_auto: boolean
  override_per_task: boolean
  task_llm_profiles: Partial<Record<LlmTaskClass, string>>
  auto_picks: Partial<Record<LlmTaskClass | 'default', string>>
  aliases_used?: string[]
  warnings: string[]
  routes: Partial<Record<LlmTaskClass, LlmTaskRoute>>
  task_classes: LlmTaskClass[]
  persisted_to?: string
  /** req44 when #360 helper is present; stub = /v1/models + fixtures. */
  list_models_source?: 'req44' | 'stub'
  cli_model_lists?: Array<{ cli: string; models: string[]; warning?: string }>
  force_env?: boolean
  provenance?: {
    default_llm_profile?: import('./configOwnership').EnvBadge
  }
}

export interface PatchLlmProfilesRequest {
  default_llm_profile?: string
  override_per_task?: boolean
  task_llm_profiles?: Partial<Record<LlmTaskClass, string>>
}

export function fetchLlmProfiles(): Promise<LlmProfilesSettings> {
  return apiGet<LlmProfilesSettings>('/v1/llm-profiles/')
}

export function patchLlmProfiles(
  body: PatchLlmProfilesRequest,
): Promise<LlmProfilesSettings> {
  return apiPatch<LlmProfilesSettings>('/v1/llm-profiles/', body)
}

export interface UpsertLlmProfileRequest {
  id: string
  model: string
  base_url?: string
  provider?: string
  api_key?: string
  set_default?: boolean
}

export function upsertLlmProfile(
  body: UpsertLlmProfileRequest,
): Promise<LlmProfilesSettings> {
  return apiPost<LlmProfilesSettings>('/v1/llm-profiles/', body)
}

export function putLlmProfile(
  body: UpsertLlmProfileRequest,
): Promise<LlmProfilesSettings> {
  return apiPut<LlmProfilesSettings>('/v1/llm-profiles/', body)
}

/** GET/PATCH /v1/rate-limits/ — user-defined provider caps (local config, not Neon). */
export type RateLimitRuleKey =
  | 'messages_per_minute'
  | 'requests_per_minute'
  | 'tokens_per_minute'
  | 'tokens_per_day'

export type RateLimitRules = Record<RateLimitRuleKey, number | null>

export interface ProviderRateLimitRow {
  id: string
  kind: 'cli' | 'llm' | 'remote' | string
  name: string
  object: 'provider_rate_limits'
  rules: RateLimitRules
  settings?: {
    section?: string
    provider_id?: string
    focus?: string
    field_id?: string
  }
}

export interface RateLimitsPayload {
  object: 'provider_rate_limits'
  data: ProviderRateLimitRow[]
  rules?: RateLimitRuleKey[]
  note?: string
  saved?: RateLimitRules
  provider?: string
  persisted_to?: string
  warnings?: string[]
}

export function fetchRateLimits(): Promise<RateLimitsPayload> {
  return apiGet<RateLimitsPayload>('/v1/rate-limits/')
}

export function patchRateLimits(
  provider: string,
  rules: Partial<RateLimitRules>,
): Promise<RateLimitsPayload> {
  return apiPatch<RateLimitsPayload>('/v1/rate-limits/', { provider, rules })
}

export function fetchTeams(): Promise<ListResponse<Team>> {
  return apiGet<ListResponse<Team>>('/v1/teams/')
}

/** GET /v1/team-rosters/ — composition contract (not LLM-profile aliases). */
export interface TeamRosterRecord {
  id: string
  object: 'team_roster'
  name: string
  members: Array<{
    id: string
    name?: string
    kind: string
    role: string
    source: string
    team_id?: string
  }>
  wires: { handoff: boolean; as_tool: boolean }
  blueprint_id?: string
  persona_count?: number
  personas?: Array<{ name: string }>
  chief_of_staff_id?: string | null
  chief_of_staff_instructions?: string
}

export interface RoleDescriptor {
  name: string
  label: string
  aliases: string[]
  allow_all: boolean
  mechanism: string
  mechanism_detail: string
  css_class: string
}

export async function fetchRoles(): Promise<{ object: string; data: RoleDescriptor[] }> {
  return apiGet<{ object: string; data: RoleDescriptor[] }>('/v1/roles/')
}

export function fetchTeamRosters(): Promise<ListResponse<TeamRosterRecord>> {
  return apiGet<ListResponse<TeamRosterRecord>>('/v1/team-rosters/')
}

export interface CreateTeamRosterRequest {
  name: string
  members?: TeamRosterRecord['members']
  wires?: TeamRosterRecord['wires']
  blueprint_id?: string
  chief_of_staff_id?: string | null
  chief_of_staff_instructions?: string
}

/** GET /v1/team-agents/ — designer palette (REQ-20 / REQ-107). */
export type TeamMemberRole =
  | 'default'
  | 'support'
  | 'gate'
  | 'skeptic'
  | 'chief_of_staff'
  | 'suggestions'

export interface TeamAgent {
  id: string
  name: string
  kind: 'api' | 'cli' | 'remote' | 'team' | 'herdr'
  source: string
  placeholder?: boolean
}

export function fetchTeamAgents(): Promise<ListResponse<TeamAgent>> {
  return apiGet<ListResponse<TeamAgent>>('/v1/team-agents/')
}

export function createTeamRoster(
  roster: CreateTeamRosterRequest,
): Promise<TeamRosterRecord> {
  return apiPost<TeamRosterRecord>('/v1/team-rosters/', roster)
}

export function updateTeamRoster(
  rosterId: string,
  roster: CreateTeamRosterRequest,
): Promise<TeamRosterRecord> {
  return apiPut<TeamRosterRecord>(
    `/v1/team-rosters/${encodeURIComponent(rosterId)}/`,
    roster,
  )
}

export function deleteTeamRoster(rosterId: string): Promise<void> {
  return apiDelete(`/v1/team-rosters/${encodeURIComponent(rosterId)}/`)
}

export function createTeam(team: CreateTeamRequest): Promise<Team> {
  return apiPost<Team>('/v1/teams/', team)
}

export function deleteTeam(teamId: string): Promise<void> {
  return apiDelete(`/v1/teams/${encodeURIComponent(teamId)}/`)
}

export function fetchLibrary(): Promise<ListResponse<LibraryEntry>> {
  return apiGet<ListResponse<LibraryEntry>>('/v1/library/')
}

export function addToLibrary(name: string): Promise<LibraryEntry> {
  return apiPost<LibraryEntry>('/v1/library/', { name })
}

export function removeFromLibrary(name: string): Promise<void> {
  return apiDelete(`/v1/library/${encodeURIComponent(name)}/`)
}

/**
 * GET/POST /v1/remotes/ and POST /v1/remotes/<id>/health|operate/
 * (swarm/views/remotes_api.py). Catalog is opt-in: empty until + Add remote.
 * Kind id ``omb`` is labelled OpenMousBot in UI copy — never OMB.
 * Auth is an env-var *name* only; never send a live token.
 */
export type RemoteKindId = 'hermes' | 'omb' | 'rakazo' | 'herdr' | 'open-swarm' | 'swarm'

export interface RemoteKind {
  id: string
  label: string
  /** User-facing harness kind. Always ``remote`` (REQ-203). */
  kind?: 'remote' | string
  /** Implementation discriminator under Remote. */
  impl?: string
  transport?: string
  capabilities?: {
    list?: boolean
    send?: boolean
    health?: boolean
    operate?: boolean
    interrogate?: boolean
    transport?: string
  }
  title?: string
  complete?: boolean
  fields?: string[]
  list_paths?: string[]
  send_path?: string
  health_path?: string
  api_key_env_default?: string
}

export interface RemoteConnection {
  id: string
  kind?: string
  label?: string
  title: string
  host_label?: string
  base_url: string
  ui_url?: string
  api_key_env?: string
  api_key_set?: boolean
  cookie_set?: boolean
  health_path?: string
  version_path?: string
  notes?: string
  source?: string
  added?: boolean
  herdr_mode?: 'local' | 'ssh' | string
  ssh_host?: string
  ssh_user?: string
  ssh_port?: number
  ssh_identity_env?: string
  ssh_agent?: boolean
  transport?: 'local' | 'ssh' | string
  ssh_shaped?: boolean
  hop_model?: string
  provenance?: {
    base_url?: import('./configOwnership').EnvBadge
    ui_url?: import('./configOwnership').EnvBadge
    api_key?: import('./configOwnership').EnvBadge
  }
}

export interface RemotesListResponse {
  object: 'list'
  data?: RemoteConnection[]
  kinds?: RemoteKind[]
  configured?: RemoteConnection[]
  team_members?: unknown[]
  vocabulary?: Record<string, string>
}

export interface AddRemoteRequest {
  kind: string
  base_url?: string
  api_key_env?: string
  api_key?: string
  ui_url?: string
  cookie?: string
  herdr_mode?: 'local' | 'ssh' | string
  ssh_host?: string
  ssh_user?: string
  ssh_port?: number | string
  ssh_identity_env?: string
  ssh_agent?: boolean
}

export type CreateRemoteRequest = AddRemoteRequest

export interface RemoteHealthResult {
  remote: string
  ok: boolean
  state: string
  detail: string
  http_status?: number | null
  version?: unknown
  latency_ms?: number | null
  url?: string
}

export interface RemoteOperateResult {
  remote: string
  op: string
  ok: boolean
  detail: string
  http_status?: number | null
  data?: unknown
  gap?: string
}

export function fetchRemotes(): Promise<RemotesListResponse> {
  return apiGet<RemotesListResponse>('/v1/remotes/')
}

export function addRemote(body: AddRemoteRequest): Promise<RemoteConnection> {
  return apiPost<RemoteConnection>('/v1/remotes/', body)
}

export function createRemote(remote: CreateRemoteRequest): Promise<RemoteConnection> {
  return addRemote(remote)
}

export function deleteRemote(remoteId: string): Promise<void> {
  return apiDelete(`/v1/remotes/${encodeURIComponent(remoteId)}/`)
}

export function probeRemoteHealth(remoteId: string): Promise<RemoteHealthResult> {
  return apiPost<RemoteHealthResult>(
    `/v1/remotes/${encodeURIComponent(remoteId)}/health/`,
    {},
  )
}

export interface OperateRemoteOptions {
  timeoutMs?: number
}

/**
 * REQ-131: Operate remote (list/send) with bounded timeout (<=10-15s).
 * Prevents endless spinner if remote hangs or is unresponsive.
 */
export async function operateRemote(
  remoteId: string,
  body: { op: 'list' | 'send' | 'interrogate'; prompt?: string; target?: string },
  options?: OperateRemoteOptions,
): Promise<RemoteOperateResult> {
  const timeoutMs = options?.timeoutMs ?? 12000
  const controller = new AbortController()
  const timer = setTimeout(() => {
    controller.abort()
  }, timeoutMs)

  try {
    const response = await fetch(`/v1/remotes/${encodeURIComponent(remoteId)}/operate/`, {
      method: 'POST',
      headers: buildHeaders(true),
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      await throwApiError(`/v1/remotes/${encodeURIComponent(remoteId)}/operate/`, response)
    }

    return (await response.json()) as RemoteOperateResult
  } catch (err: unknown) {
    if (controller.signal.aborted) {
      throw new Error(
        `OpenMousBot list operation timed out after ${Math.round(timeoutMs / 1000)}s. Remote server is slow or hung.`,
      )
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/**
 * GET/POST /v1/herdr-agents/ and DELETE /v1/herdr-agents/<id>/
 * (swarm/views/herdr_api.py). DaisyUI settings sheet is not in this tree
 * (ADR-001); Django /settings/ and admin list/add/remove these rows.
 * Empty `remote` means localhost (no `herdr --remote`).
 */
export interface HerdrAgent {
  id: number
  object: 'herdr.agent'
  kind: 'herdr'
  name: string
  remote: string
  created_at: string
  updated_at: string
}

export interface HerdrDiscoverMember {
  object: 'herdr.member'
  kind: 'herdr'
  name: string
  remote: string
  source: 'agent' | 'workspace'
  state: string | null
  added?: boolean
}

export interface CreateHerdrAgentRequest {
  name: string
  remote?: string
}

export function fetchHerdrAgents(): Promise<ListResponse<HerdrAgent>> {
  return apiGet<ListResponse<HerdrAgent>>('/v1/herdr-agents/')
}

export function createHerdrAgent(
  agent: CreateHerdrAgentRequest,
): Promise<HerdrAgent> {
  return apiPost<HerdrAgent>('/v1/herdr-agents/', agent)
}

export function deleteHerdrAgent(agentId: string | number): Promise<void> {
  return apiDelete(`/v1/herdr-agents/${encodeURIComponent(String(agentId))}/`)
}

export function discoverHerdrAgents(
  remote?: string,
): Promise<ListResponse<HerdrDiscoverMember> & { herdr_available?: boolean }> {
  const qs = remote ? `?remote=${encodeURIComponent(remote)}` : ''
  return apiGet(`/v1/herdr-agents/discover/${qs}`)
}

// ---------------------------------------------------------------------------
// Agent creator (swarm/views/agent_creator_views.py)
//
// /agent-creator/generate/ and /agent-creator/validate/ are plain Django POST
// views protected by CsrfViewMiddleware (verified: they 403 without a CSRF
// cookie + X-CSRFToken header). ensureCsrfCookie() primes the cookie via a
// cheap GET to /login/ (which sets csrftoken); buildHeaders() then attaches
// the matching X-CSRFToken header automatically.
//
// Saving deliberately uses POST /v1/blueprints/custom/ (a DRF view, CSRF-free
// for token/anonymous access) instead of /agent-creator/save/: the latter
// writes loose files under user_blueprints/ with no list/delete API, whereas
// the custom-blueprints library gives the page a coherent list/save/delete
// story against a single store.
// ---------------------------------------------------------------------------

/**
 * Make sure Django's csrftoken cookie is set before calling CSRF-protected
 * (non-DRF) endpoints. No-op when the cookie already exists.
 */
export async function ensureCsrfCookie(): Promise<void> {
  if (getCookie('csrftoken')) return
  try {
    await fetch('/login/', { headers: { Accept: 'text/html' } })
  } catch {
    // Network failure: the subsequent POST will surface a real error.
  }
}

/** Validation report returned by generate/validate (BlueprintCodeValidator). */
export interface CodeValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  syntax_valid: boolean
  structure_valid: boolean
  lint_clean: boolean
}

/** POST /agent-creator/generate/ request body (name/description/instructions required). */
export interface GenerateAgentRequest {
  name: string
  description: string
  instructions: string
  personality?: string
  expertise?: string[]
  communication_style?: string
  tags?: string[]
}

export interface GenerateAgentResponse {
  success: boolean
  code: string
  validation: CodeValidationResult
}

export interface ValidateAgentResponse {
  success: boolean
  validation: CodeValidationResult
}

export async function generateAgentCode(
  spec: GenerateAgentRequest,
): Promise<GenerateAgentResponse> {
  await ensureCsrfCookie()
  return apiPost<GenerateAgentResponse>('/agent-creator/generate/', spec)
}

export async function validateAgentCode(
  code: string,
): Promise<ValidateAgentResponse> {
  await ensureCsrfCookie()
  return apiPost<ValidateAgentResponse>('/agent-creator/validate/', { code })
}

// ---------------------------------------------------------------------------
// Custom blueprints CRUD (/v1/blueprints/custom/, swarm/views/api_views.py)
// ---------------------------------------------------------------------------

export interface CustomBlueprint {
  id: string
  name: string
  description: string
  category: string
  tags: string[]
  requirements: string
  code: string
  required_mcp_servers: string[]
  env_vars: string[]
  /** REQ-171B: Add-agent CLI/API seats persist kind + command + rail. */
  kind?: 'cli' | 'api' | string
  command?: string
  cli?: string
  rail?: boolean
  source?: string
}

export interface CreateCustomBlueprintRequest {
  name: string
  description?: string
  code?: string
  category?: string
  tags?: string[]
  kind?: 'cli' | 'api' | 'blueprint'
  command?: string
  rail?: boolean
  source?: string
}

export function fetchCustomBlueprints(): Promise<ListResponse<CustomBlueprint>> {
  return apiGet<ListResponse<CustomBlueprint>>('/v1/blueprints/custom/')
}

export function createCustomBlueprint(
  blueprint: CreateCustomBlueprintRequest,
): Promise<CustomBlueprint> {
  return apiPost<CustomBlueprint>('/v1/blueprints/custom/', blueprint)
}

export function deleteCustomBlueprint(blueprintId: string): Promise<void> {
  return apiDelete(`/v1/blueprints/custom/${encodeURIComponent(blueprintId)}/`)
}

// ---------------------------------------------------------------------------
// Server settings (read-only; swarm/views/settings_views.py)
// ---------------------------------------------------------------------------

/** One entry inside a settings group (SettingsManager.collect_all_settings). */
export interface ServerSettingEntry {
  value: unknown
  env_var: string | null
  type: string
  description: string
  category: string
  sensitive: boolean
}

export interface ServerSettingsGroup {
  title: string
  description: string
  icon: string
  settings: Record<string, ServerSettingEntry>
}

/** GET /settings/api/ */
export interface ServerSettingsResponse {
  success: boolean
  settings: Record<string, ServerSettingsGroup>
}

/** GET /settings/environment/ */
export interface EnvironmentVariablesResponse {
  success: boolean
  environment_variables: Record<string, string>
  count: number
}

export function fetchServerSettings(): Promise<ServerSettingsResponse> {
  return apiGet<ServerSettingsResponse>('/settings/api/')
}

export function fetchEnvironmentVariables(): Promise<EnvironmentVariablesResponse> {
  return apiGet<EnvironmentVariablesResponse>('/settings/environment/')
}

/** GET /v1/system/ — Settings System section (REQ-56). Read-only local store facts. */
export interface LocalStoreFacts {
  path: string
  size_bytes: number
  size_label: string
  created: boolean
  conversation_count: number
  message_count: number
}

export const EMPTY_LOCAL_STORE: LocalStoreFacts = {
  path: 'not created yet',
  size_bytes: 0,
  size_label: 'not created yet',
  created: false,
  conversation_count: 0,
  message_count: 0,
}

export function fetchLocalStore(): Promise<LocalStoreFacts> {
  return apiGet<LocalStoreFacts>('/v1/system/')
}

/**
 * GET/PATCH /v1/image-gen/ and POST /v1/agents/<id>/avatar/generate/
 * (swarm/views/image_gen_api.py). Opt-in OpenAI-compat image endpoint.
 * Auth is an env-var *name* only; never send a live token.
 */
export interface ImageGenSettings {
  object?: 'image_gen'
  configured: boolean
  base_url: string
  model: string
  api_key_env: string
  api_key_set?: boolean
  status?: string
  detail?: string
  avatars?: Record<string, string>
  source?: string
}

export interface ImageGenPatchRequest {
  base_url?: string
  model?: string
  api_key_env?: string
}

export interface GeneratedAgentAvatar {
  object?: 'agent_avatar'
  agent_id: string
  avatar_path: string
  still: boolean
  prompt?: string
}

export const EMPTY_IMAGE_GEN: ImageGenSettings = {
  object: 'image_gen',
  configured: false,
  base_url: '',
  model: '',
  api_key_env: '',
  api_key_set: false,
  status: 'off',
  detail: 'Image generation is off. No host is used until you set a base URL.',
  avatars: {},
}

export function fetchImageGenSettings(probe = true): Promise<ImageGenSettings> {
  const q = probe ? '' : '?probe=0'
  return apiGet<ImageGenSettings>(`/v1/image-gen/${q}`)
}

export function patchImageGenSettings(body: ImageGenPatchRequest): Promise<ImageGenSettings> {
  return apiPatch<ImageGenSettings>('/v1/image-gen/', body)
}

export function generateAgentAvatar(
  agentId: string,
  body: { prompt?: string; name?: string; role?: string } = {},
): Promise<GeneratedAgentAvatar> {
  return apiPost<GeneratedAgentAvatar>(
    `/v1/agents/${encodeURIComponent(agentId)}/avatar/generate/`,
    body,
  )
}

/**
 * GET/PATCH /v1/speech/ plus custom transcribe/speak (REQ-77 / #422).
 * Auth is an env-var *name* only; never send a live token.
 */
export type SpeechSource = 'system' | 'custom'

export interface SpeechEndpointSettings {
  kind?: 'stt' | 'tts'
  source: SpeechSource
  configured: boolean
  base_url: string
  model: string
  api_key_env: string
  api_key_set?: boolean
  status?: string
  detail?: string
}

export interface SpeechSettings {
  object?: 'speech'
  stt: SpeechEndpointSettings
  tts: SpeechEndpointSettings
}

export interface SpeechEndpointPatch {
  source?: SpeechSource
  base_url?: string
  model?: string
  api_key_env?: string
}

export interface SpeechPatchRequest {
  stt?: SpeechEndpointPatch
  tts?: SpeechEndpointPatch
}

export interface SpeechTranscription {
  object?: 'transcription'
  text: string
  path: 'custom'
}

export const EMPTY_SPEECH_ENDPOINT: SpeechEndpointSettings = {
  source: 'system',
  configured: false,
  base_url: '',
  model: '',
  api_key_env: '',
  api_key_set: false,
  status: 'system',
  detail: 'Using the browser/OS implementation. No custom host is called.',
}

export const EMPTY_SPEECH: SpeechSettings = {
  object: 'speech',
  stt: { ...EMPTY_SPEECH_ENDPOINT, kind: 'stt' },
  tts: { ...EMPTY_SPEECH_ENDPOINT, kind: 'tts' },
}

export function fetchSpeechSettings(probe = true): Promise<SpeechSettings> {
  const q = probe ? '' : '?probe=0'
  return apiGet<SpeechSettings>(`/v1/speech/${q}`)
}

export function patchSpeechSettings(body: SpeechPatchRequest): Promise<SpeechSettings> {
  return apiPatch<SpeechSettings>('/v1/speech/', body)
}

export function transcribeSpeechAudio(file: Blob, filename = 'audio.webm'): Promise<SpeechTranscription> {
  const form = new FormData()
  form.append('file', file, filename)
  return apiPostForm<SpeechTranscription>('/v1/speech/transcribe/', form)
}

export async function speakSpeechText(text: string, voice = ''): Promise<Blob> {
  const response = await fetch('/v1/speech/speak/', {
    method: 'POST',
    headers: buildHeaders(true),
    body: JSON.stringify({ text, ...(voice ? { voice } : {}) }),
    credentials: 'include',
  })
  if (!response.ok) {
    await throwApiError('/v1/speech/speak/', response)
  }
  return response.blob()
}

/** GET/PUT /v1/blueprints/<id>/source — blueprint source (file list + content). */
export interface BlueprintSource {
  id: string
  files: { name: string; path: string }[]
  primary: string | null
  selected: string | null
  content: string
  persona_count?: number
  personas?: Array<{ name: string }>
  /** REQ-211: user-dir / custom-library rows are writable; bundled / marketplace are not. */
  editable?: boolean
  origin?: 'user' | 'custom' | 'bundled' | 'marketplace' | string | null
  readonly_reason?: string | null
}

export function fetchBlueprintSource(id: string, file?: string): Promise<BlueprintSource> {
  const q = file ? `?file=${encodeURIComponent(file)}` : ''
  return apiGet<BlueprintSource>(`/v1/blueprints/${encodeURIComponent(id)}/source${q}`)
}

export function updateBlueprintSource(
  id: string,
  body: { content: string; file?: string },
): Promise<BlueprintSource> {
  const q = body.file ? `?file=${encodeURIComponent(body.file)}` : ''
  return apiPut<BlueprintSource>(`/v1/blueprints/${encodeURIComponent(id)}/source${q}`, {
    content: body.content,
    ...(body.file ? { file: body.file } : {}),
  })
}

/** GET /v1/blueprints/<id>/personas — declared openai-agents roster (REQ-81). */
export interface BlueprintPersonas {
  object: 'blueprint.personas'
  id: string
  count: number
  personas: Array<{ name: string }>
  parsed?: boolean
}

export function fetchBlueprintPersonas(id: string): Promise<BlueprintPersonas> {
  return apiGet<BlueprintPersonas>(`/v1/blueprints/${encodeURIComponent(id)}/personas`)
}

/** GET /v1/cli-agents/ — CLI catalog + native (built-in) consensus capability. */
export interface CliRailAgent {
  id: string
  object: 'cli.agent'
  name: string
  cli: string
  kind: 'cli' | 'api'
  description: string
  installed: boolean
}

export interface CliAgentsInfo {
  clis: string[]
  known?: string[]
  /** Opt-in names from swarm_config.cli_agents — empty until the user adds. */
  configured?: string[]
  /** PATH / known-location seed. No auth check. */
  discovered?: string[]
  /** Alias of discovered (chat dropdown / older clients). */
  installed?: string[]
  /** Discovered-minus-configured catalog entries for one-click add. */
  suggestions?: Record<string, Record<string, unknown>>
  default_cli?: string
  native_consensus: Record<string, string[]>
  catalog: Record<string, Record<string, unknown>>
  rail?: CliRailAgent[]
  /** Argv table for list-models probes — not live model ids. */
  list_models?: Record<string, string[]>
  list_sessions?: Record<string, unknown>
}

export function fetchCliAgents(): Promise<CliAgentsInfo> {
  return apiGet<CliAgentsInfo>('/v1/cli-agents/')
}

/** One designer-created agent (Agent Router design, router_designs.json). */
export interface RouterDesign {
  agent_id: string
  name: string
  kind: string
  agent_type?: string
  specialty?: string
  description?: string
  color?: string
  icon?: string
  group?: string
  cli?: string
  framework?: string
}

/** GET /v1/agents/designs/ — fast rail feed (no blueprint init). */
export function fetchDesignedAgents(): Promise<{ object: 'list'; data: RouterDesign[] }> {
  return apiGet<{ object: 'list'; data: RouterDesign[] }>('/v1/agents/designs/')
}

export interface CliRunStatus {
  object: 'cli_run_status'
  agent: string
  running: boolean
  count?: number
}

export interface CliRunTerminateResult {
  object: 'cli_run_terminate'
  agent: string
  status: 'terminated' | 'not_running'
  running: boolean
}

/** GET /v1/cli-agents/runs/?agent= — tracked CLI subprocess for a rail row. */
export function fetchCliRunStatus(agent: string): Promise<CliRunStatus> {
  const q = new URLSearchParams({ agent })
  return apiGet<CliRunStatus>(`/v1/cli-agents/runs/?${q.toString()}`)
}

/** POST /v1/cli-agents/runs/terminate/ — SIGTERM then SIGKILL that CLI group. */
export function terminateCliRun(body: {
  agent: string
  conversation_id?: string
}): Promise<CliRunTerminateResult> {
  return apiPost<CliRunTerminateResult>('/v1/cli-agents/runs/terminate/', body)
}

export interface CliModelsResponse {
  cli: string
  models: string[]
  warning?: string
}

export function fetchCliModels(cli: string): Promise<CliModelsResponse> {
  return apiGet<CliModelsResponse>(`/v1/cli-agents/${encodeURIComponent(cli)}/models/`)
}

/** A 0..1 capability/priority vector over inference traits. */
export type TraitVector = Record<string, number>

/** GET /v1/config-options/ — everything the Builder needs to configure the
 *  skills / inference-profile / tool-capability decoupling features. */
export interface SkillRecord {
  name: string
  id?: string
  description: string
  path?: string
  assets: string[]
  instructions?: string
  found?: boolean
  error?: string
}

export interface SkillsList {
  object: 'list'
  data: SkillRecord[]
}

export function fetchSkills(): Promise<SkillsList> {
  return apiGet<SkillsList>('/v1/skills/')
}

export async function fetchSkill(name: string): Promise<SkillRecord> {
  try {
    return await apiGet<SkillRecord>(`/v1/skills/${encodeURIComponent(name)}/`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return {
        name,
        id: name,
        description: '',
        assets: [],
        found: false,
        error: error.message,
      }
    }
    throw error
  }
}

export interface ConfigOptions {
  skills: SkillRecord[]
  inference: {
    traits: string[]
    cli_traits: Record<string, TraitVector>
    model_traits: Record<string, TraitVector>
    model_flags: Record<string, string>
  }
  tools: {
    capabilities: string[]
    mcp_catalog: {
      name: string
      provides: string[]
      command: string
      args: string[]
      needs_auth: boolean
      auth_env: string[]
      note: string
    }[]
  }
}

export function fetchConfigOptions(): Promise<ConfigOptions> {
  return apiGet<ConfigOptions>('/v1/config-options/')
}

/** GET /v1/blueprints/<id>/tools — a blueprint's capability requirements
 *  resolved to concrete MCP providers (non-auth preferred, auto-provisioned). */
export interface BlueprintTools {
  blueprint: string
  requirements: Record<string, 'mandatory' | 'optional'>
  servers: Record<string, { command: string; args: string[]; provides?: string[] }>
  satisfied: Record<string, string>
  missing_mandatory: string[]
  skipped_optional: string[]
  ok: boolean
}

export function fetchBlueprintTools(id: string): Promise<BlueprintTools> {
  return apiGet<BlueprintTools>(`/v1/blueprints/${encodeURIComponent(id)}/tools`)
}

export function updateCustomBlueprint(
  blueprintId: string,
  body: Partial<CustomBlueprint>,
): Promise<CustomBlueprint> {
  return apiPatch<CustomBlueprint>(
    `/v1/blueprints/custom/${encodeURIComponent(blueprintId)}/`,
    body,
  )
}

/** GET /v1/config-ownership/ — #776 Full coverage inventory + force-env. */
export function fetchConfigOwnership(): Promise<
  import('./configOwnership').ConfigOwnershipPayload
> {
  return apiGet('/v1/config-ownership/')
}

export function fetchConfigSection(
  section: string,
): Promise<import('./configOwnership').ConfigSectionPayload> {
  return apiGet(`/v1/config/sections/${encodeURIComponent(section)}/`)
}

export function patchConfigSection(
  section: string,
  body: {
    entries?: Record<string, unknown>
    upsert?: Record<string, unknown>
    delete?: string | string[]
  },
): Promise<import('./configOwnership').ConfigSectionPayload> {
  return apiPatch(`/v1/config/sections/${encodeURIComponent(section)}/`, body)
}

/** GET /v1/mcp-plugins/ — #502 Plugins manage (redacted MCP servers + tools). */
export interface McpPluginTool {
  name: string
  description: string
}

export interface McpPluginServer {
  name: string
  label?: string
  kind: 'local' | 'remote'
  source?: 'generic' | 'openapi'
  enabled: boolean
  command: string
  args: string[]
  url: string
  openapi_spec_url?: string
  type?: string
  cwd?: string
  env: Record<string, string>
  headers: Record<string, string>
  provides: string[]
  note: string
  tools: McpPluginTool[]
}

export interface McpPluginsPayload {
  object: 'mcp_plugins'
  scope: string
  servers: McpPluginServer[]
}

export interface McpPluginDiscoverPayload {
  object: 'mcp_plugin_tools'
  name: string
  kind: 'local' | 'remote'
  source?: 'generic' | 'openapi'
  tools: McpPluginTool[]
}

export function fetchMcpPlugins(): Promise<McpPluginsPayload> {
  return apiGet<McpPluginsPayload>('/v1/mcp-plugins/')
}

export function upsertMcpPlugin(body: Record<string, unknown>): Promise<McpPluginsPayload> {
  return apiPost<McpPluginsPayload>('/v1/mcp-plugins/', body)
}

export async function deleteMcpPlugin(name: string): Promise<McpPluginsPayload> {
  await apiDelete(`/v1/mcp-plugins/${encodeURIComponent(name)}/`)
  return fetchMcpPlugins()
}

export function discoverMcpPluginTools(
  body: Record<string, unknown>,
): Promise<McpPluginDiscoverPayload> {
  return apiPost<McpPluginDiscoverPayload>('/v1/mcp-plugins/discover/', body)
}
