/** #856 slice A — endpoint types (moved verbatim from lib/api.ts). */
import type {
  LlmTaskClass,
} from './llm'
import type { CliSlashCommandSpec } from '../slashMenu'

// ---------------------------------------------------------------------------

export interface ListResponse<T> {
  object: 'list'
  data: T[]
}
/** Visual / wiring role on a Team member (REQ-9 / REQ-25 / REQ-28 / REQ-42 / REQ-75). */
export type AgentRole =
  | 'default'
  | 'admin'
  | 'support'
  | 'gate'
  | 'belay'
  | 'skeptic'
  | 'advisor'
  | 'chief_of_staff'
  | 'engineer'
  | 'suggestions'
  | (string & {})
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
  /** Library grouping (blueprint library); optional — plain /v1/blueprints rows may omit it. */
  category?: string | null
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
  /** #932: agent popup inline customisation (API seats). */
  instructions?: string | null
  provider?: string | null
  model?: string | null
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
  /** #1317: Company attached when this seat was created as a bot. */
  company_id?: string | null
  company_slug?: string | null
  company_name?: string | null
  /** #843: newest persisted-thread instant for this seat (ISO-8601 or epoch ms). Missing = no activity yet. */
  last_message_at?: string | number | null
  /** #844: newest human-visible turn text (server-derived snippet). Missing = snippet only from local sessions. */
  last_message?: string | null
  /** #1441: ``error`` when that snippet is a failure preview. Absent for ordinary replies. */
  last_message_class?: 'error' | null
  /** Navbar items contributed by this blueprint (e.g. token counter for API agents). */
  navbar_items?: Array<{ id: string; kind: string; label?: string; [key: string]: any }> | null
  /**
   * #1699 / #1700 — the server's admission + readiness verdict for this row.
   *
   * Every field is optional: a backend older than the gate sends none, and a
   * missing field must read as "listed and ready" so an old server never hides
   * a working seat. Read them through `lib/blueprintSeats.ts`, never ad hoc.
   */
  /** Server-resolved seat kind (`api` / `cli` / `remote` / `team` / `blueprint`). */
  seat_kind?: SeatKindName | null
  /** `discovery` (shipped recipe) or `user` (created by the operator). */
  seat_source?: 'discovery' | 'user' | null
  /** false = must not appear as a seat in the rail or the agent picker (#1699). */
  seat_listed?: boolean | null
  /** false = visible but not a silent chat target; read `unavailable_reason` (#1700). */
  chat_ready?: boolean | null
  /** Why the seat cannot run a turn, in operator words. Empty when ready. */
  unavailable_reason?: string | null
  /** In-product routes that repair it (settings deep links). Empty when ready. */
  manage_links?: SeatManageLink[] | null
}

/** #1700: a repair route the UI can act on, not a prose suggestion. */
export interface SeatManageLink {
  href: string
  label: string
}

/**
 * The seat kinds `swarm.core.vanilla_seats` resolves. Mirrors
 * `kind_bases.KIND_*` plus the `blueprint` recipe identity from `agent_kind`.
 */
export type SeatKindName = 'api' | 'cli' | 'remote' | 'team' | 'blueprint'

/** #1699 / #1700 — the host facts the gate resolved, published once per listing. */
export interface BlueprintHostFacts {
  configured_remotes: string[]
  on_path_clis: string[]
  inference_ready: boolean
  resolved_profiles: string[]
  /** True when the server could not read the host; every gate then fails open. */
  unreadable: boolean
  notes: string[]
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
  /** Roster label; rail rows prefer `name` and fall back to the slug id. */
  name?: string
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
/** #1311 — org-shared bot library recipe (not a live computer). */
export type OrgLibraryVisibility = 'org' | 'team' | 'private'
export interface OrgLibraryBot {
  id: string
  object: 'org_library.bot'
  name: string
  description: string
  kind: string
  role: AgentRole | string
  instructions: string
  preset: boolean
  visibility: OrgLibraryVisibility | string
  team_ids: string[]
  source: string
  created_by: string
  updated_at: string
}
export interface OrgLibraryShare {
  object: 'org_library.share'
  scope: 'team'
  team_id: string
  roster_id: string
  bot: OrgLibraryBot
}
export interface OrgLibraryPublishBody {
  id?: string
  name: string
  description?: string
  kind?: string
  role?: string
  instructions?: string
  visibility?: OrgLibraryVisibility | string
  team_id?: string
}

/** #1311 — Mine / Team / Organisation. Default personal keeps the file library. */
export type LibraryScope = 'personal' | 'team' | 'org'
export interface SharedLibraryItem {
  id: string
  object: 'shared_library.item'
  scope: LibraryScope
  kind: 'blueprint' | 'plugin' | 'team'
  item_key: string
  title: string
  owner_principal: string
  owner_team: string
  published: boolean
  payload: Record<string, unknown>
}
export interface RosterPackMember {
  id: string
  name?: string
  kind: string
  role: string
  source?: string
  blueprint_id?: string
}
export interface RosterPackRecord {
  object: 'team_roster_pack' | 'team_roster'
  id: string
  name: string
  members: RosterPackMember[]
  blueprint_ids?: string[]
  mcp_server_ids?: string[]
  skill_ids?: string[]
  needs_configuration?: Array<{ id: string; reason: string }>
  imported?: boolean
}
export interface SharedLibraryImport {
  object: 'shared_library.import'
  imported: boolean
  item: SharedLibraryItem
  roster?: RosterPackRecord
  needs_configuration?: Array<{ id: string; reason: string }>
}
export interface PresetRailSeat {
  id: string
  name: string
  kind: string
  rail: boolean
  provider?: string | null
  model?: string | null
  plugins?: string[]
  preset_id?: string
}
/**
 * #1745 — a model *type*, alongside the `provider` vendor axis. `chat` emits
 * tokens; `categorizer` is a System1 gate (filter-in / filter-out seats) and
 * must never appear on a chat surface.
 */
export type LlmModelType = 'chat' | 'categorizer'
export interface LlmProfile {
  id: string
  object: 'llm_profile'
  source: string
  /** Model namespace (`api` / `cli` / `remote`). API seats only offer `api`. */
  namespace?: string
  /** #1745 `chat` / `categorizer`. Absent on older servers ⇒ `chat`. */
  model_type?: LlmModelType
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
  /** #1745 the resolved profile's model type, so a gate is never read as chat. */
  model_type?: LlmModelType
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
  /** #1745 the model types the backend registry knows (`chat` / `categorizer`). */
  model_types?: LlmModelType[]
  persisted_to?: string
  /** req44 when #360 helper is present; stub = /v1/models + fixtures. */
  list_models_source?: 'req44' | 'stub'
  cli_model_lists?: Array<{ cli: string; models: string[]; warning?: string }>
  force_env?: boolean
  /** REQ-853 / #207: effective default profile resolves to a usable LLM endpoint. */
  default_llm_ready?: boolean
  provenance?: {
    default_llm_profile?: import('.././configOwnership').EnvBadge
  }
}
export interface PatchLlmProfilesRequest {
  default_llm_profile?: string
  override_per_task?: boolean
  task_llm_profiles?: Partial<Record<LlmTaskClass, string>>
}
export interface UpsertLlmProfileRequest {
  id: string
  model: string
  base_url?: string
  provider?: string
  /** #1745 omit ⇒ `chat`; `categorizer` registers a System1 gate. */
  model_type?: LlmModelType
  api_key?: string
  set_default?: boolean
}
export type LlmProfileProbeAction = 'test' | 'list_models'
export interface LlmProfileProbeRequest {
  base_url: string
  api_key_env?: string
  api_key_ref?: string
  model?: string
  action?: LlmProfileProbeAction
}
export interface LlmProfileProbeResult {
  object?: 'llm_profile_probe'
  ok: boolean
  latency_ms: number
  error_class: string | null
  hint?: string
  state?: 'ok' | 'warn' | 'error'
  action?: string
  models?: string[]
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
  tools?: Array<
    | { type: 'handoff'; to: string; from?: string }
    | { type: 'as_tool'; agent: string }
    | { type: 'mcp'; server: string; agents: string[] }
  >
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
  custom?: boolean
}
export interface CreateRoleRequest {
  name: string
  label?: string
  aliases?: string[]
  allow_all?: boolean
  mechanism?: string
  mechanism_detail?: string
  css_class?: string
}
export interface CreateTeamRosterRequest {
  name: string
  members?: TeamRosterRecord['members']
  wires?: TeamRosterRecord['wires']
  tools?: TeamRosterRecord['tools']
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
/**
 * GET/POST /v1/remotes/ and POST /v1/remotes/<id>/health|operate/
 * (swarm/views/remotes_api.py). Catalog is opt-in: empty until + Add remote.
 * Kind id ``omb`` is labelled OpenMousBot in UI copy — never OMB.
 * Auth is an env-var *name* only; never send a live token.
 */
export type RemoteKindId =
  | 'hermes'
  | 'anythingllm'
  | 'openwebui'
  | 'flowise'
  | 'n8n'
  | 'omb'
  | 'rakazo'
  | 'herdr'
  | 'open-swarm'
  | 'swarm'
export interface RemoteKind {
  id: string
  label: string
  /** User-facing harness kind. Always ``remote`` (REQ-203). */
  kind?: 'remote' | string
  /** Implementation discriminator under Remote. */
  impl?: string
  transport?: string
  capabilities?: RemoteCapabilities
  title?: string
  complete?: boolean
  fields?: string[]
  list_paths?: string[]
  send_path?: string
  health_path?: string
  api_key_env_default?: string
}
export interface RemoteCapabilities {
  list?: boolean
  send?: boolean
  health?: boolean
  /**
   * #1672: there is deliberately no `operate` here. The backend classified
   * OMB / Rakazo with it but never published anything a client could do with
   * it — the computer verb answers `computer_operate_unwired` for every
   * remote (ADR-007 Phase 3 is parked). A key the SPA cannot act on is a
   * promise it cannot keep, so the server dropped it from the payload and the
   * client model follows. Do not re-add it without a control that reads it.
   */
  interrogate?: boolean
  routines?: boolean
  sessions?: boolean
  transport?: string
  server_managed_context?: boolean
  serverManagedContext?: boolean
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
  /** Operator added this remote (persisted entry or env bootstrap). */
  configured?: boolean
  /** ``base_url`` is a documentation address / discard port — never an instance. */
  base_url_placeholder?: boolean
  /** ``configured`` AND has a probeable address: the one question a seat answers. */
  usable?: boolean
  health_path?: string
  version_path?: string
  notes?: string
  source?: string
  added?: boolean
  capabilities?: RemoteCapabilities
  herdr_mode?: 'local' | 'ssh' | string
  ssh_host?: string
  ssh_user?: string
  ssh_port?: number
  ssh_identity_env?: string
  ssh_agent?: boolean
  /** #1317: Company attached when this remote was created as a new bot. */
  company_id?: string
  company_slug?: string
  company_name?: string
  model?: string
  transport?: 'local' | 'ssh' | string
  ssh_shaped?: boolean
  hop_model?: string
  provenance?: {
    base_url?: import('.././configOwnership').EnvBadge
    ui_url?: import('.././configOwnership').EnvBadge
    api_key?: import('.././configOwnership').EnvBadge
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
  id?: string
  title?: string
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
  source?: string
  company_id?: string
  company?: string
  model?: string
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
  /**
   * Machine-readable "nothing was probed" code from `HealthResult.gap`.
   * `remote_not_added` / `remote_base_url_placeholder` mean the seat has no
   * instance to reach, so it must read as *not configured*, never as offline.
   */
  gap?: string
}
export interface RemoteOperateResult {
  remote: string
  op: string
  ok: boolean
  detail: string
  http_status?: number | null
  data?: unknown
  gap?: string
  /** #494: machine-readable remedy for a classified failure (absent otherwise). */
  action?: {
    kind: 'settings'
    section: 'remotes'
    remote?: string
    field?: string
  } | null
}
export interface TestRemoteCandidateParams {
  kind: string
  id?: string
  base_url?: string
  api_key?: string
  api_key_env?: string
  herdr_mode?: string
  ssh_target?: string
  ssh_host?: string
  ssh_user?: string
  ssh_port?: string
  ssh_identity_env?: string
  ssh_agent?: boolean
}
export interface OperateRemoteOptions {
  timeoutMs?: number
}
export interface RemoteRoutineLastRun {
  id?: string
  name?: string
  scheduled_for?: string
  status?: 'scheduled' | 'triggered' | 'failed' | string
}
export interface RemoteRoutine {
  id?: string
  name: string
  agent?: string
  cron?: string
  timezone?: string
  task?: string
  status?: string
  created_at?: string
  last_run?: RemoteRoutineLastRun | null
}
export interface RemoteRoutinesResult {
  remote: string
  op: string
  ok: boolean
  detail: string
  http_status?: number | null
  data?: {
    routines?: RemoteRoutine[]
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
  /** Issue #180: optional remote serve endpoint for opencode/kilocode. */
  remote?: {
    host?: string
    port?: number
    username?: string
    password_env?: string
    box?: string
  }
  /** #1317: Company attached when this row is a new bot. */
  company_id?: string
  company_slug?: string
  company_name?: string
  model?: string
}

/** GET /v1/companies/ — Company model policy (#1315) + bot attach (#1317). */
export interface CompanyModelPolicy {
  mode: 'allow_all' | 'allowlist' | 'denylist' | string
  allowed_models: string[]
  denied_models: string[]
  default_model: string
}
export interface Company {
  object: 'company'
  id: string
  name: string
  slug: string
  model_policy: CompanyModelPolicy
  default_model: string
  created_at?: string | null
  updated_at?: string | null
}
export interface CreateCustomBlueprintRequest {
  id?: string
  name: string
  description?: string
  code?: string
  category?: string
  tags?: string[]
  kind?: 'cli' | 'api' | 'blueprint'
  command?: string
  rail?: boolean
  source?: string
  company_id?: string
  company?: string
  model?: string
  remote?: {
    host?: string
    port?: number
    username?: string
    password_env?: string
    box?: string
  }
}
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
/** GET /v1/system/ — Settings System section (REQ-56). Read-only local store facts. */
export interface LocalStoreFacts {
  path: string
  size_bytes: number
  size_label: string
  created: boolean
  conversation_count: number
  message_count: number
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
export type SpeakSpeechOpts = {
  voice?: string
  instruction?: string
  agentId?: string
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
/** GET /v1/blueprints/<id>/personas — declared openai-agents roster (REQ-81). */
export interface BlueprintPersonas {
  object: 'blueprint.personas'
  id: string
  count: number
  personas: Array<{ name: string }>
  parsed?: boolean
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
  /** Absolute executable path per discovered CLI (name -> path). */
  paths?: Record<string, string>
  /** Discovered-minus-configured catalog entries for one-click add. */
  suggestions?: Record<string, Record<string, unknown>>
  default_cli?: string
  /** CLI-first product modes (#151). Missing → client treats as legacy all-on. */
  modes?: {
    cli?: boolean
    api?: boolean
    blueprint?: boolean
    team?: boolean
    remote?: boolean
  }
  mode_limitations?: Record<string, string>
  native_consensus: Record<string, string[]>
  catalog: Record<string, Record<string, unknown>>
  rail?: CliRailAgent[]
  /** Argv table for list-models probes — not live model ids. */
  list_models?: Record<string, string[]>
  list_sessions?: Record<string, unknown>
  /** #641: per-CLI provider-declared native slash commands. */
  slash_commands?: Record<string, CliSlashCommandSpec[]>
  /** #636: per-CLI provider-native compact hooks (argv templates). */
  cli_compact?: Record<string, string>
  /** #551 / #1374: per-kind seat capability declarations — the gate
   * channel for attach/compact/plugins/routines/parallel_fan_out.
   * Absent capability = not offered. */
  seat_capabilities?: Record<string, Record<string, { enabled: boolean; reason: string }>>
  /** Issue #180: per-CLI remote/headless capability (serve / ssh / api / none). */
  remote?: Record<string, {
    capability?: string
    how?: string
    serve_cmd?: string[] | null
    attach_flag?: string | null
    default_port?: number | null
    default_hostname?: string | null
    auth?: string | null
    notes?: string
  }>
  remote_boxes?: Array<{
    id?: string
    host?: string
    port?: number
    username?: string
    password_env?: string
    box?: string
  }>
}
export interface CliCandidatesResult {
  name: string
  candidates: string[]
}
export interface CliProbeResult {
  ok: boolean
  version?: string
  message?: string
}
export interface CliDriverDescriptor {
  name: string
  display_name: string
  default_binary: string
  list_capability: string
  candidates: string[]
}
export interface ChatRetentionChatRow {
  agent_id: string
  message_count: number
  updated_at: string
}
export interface ChatRetentionTrashRow {
  agent_id: string
  message_count: number
  filename: string
}
export interface ChatRetentionStats {
  store_dir: string
  format: string
  active_count: number
  trash_count: number
  bytes_used: number
  bytes_label: string
  max_age_days: number
  auto_archive_enabled: boolean
  chats: ChatRetentionChatRow[]
  trash: ChatRetentionTrashRow[]
  env_dir?: string
  env_max_age?: string
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
export interface CliModelsResponse {
  cli: string
  models: string[]
  warning?: string
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

/** Per-agent prose skill (#1392 / #1393). Description is the when-to-use hint. */
export type AgentSkillSource = 'authored' | 'library' | 'pack'

export interface AgentSkillRecord {
  name: string
  description: string
  instructions: string
  source?: AgentSkillSource | string
  first_run?: boolean
  agent_id?: string
  object?: 'agent_skill'
}

export interface AgentGettingStarted {
  skill: string
}

export interface AgentSkillsList {
  object: 'agent_skill_list'
  agent_id: string
  skills: AgentSkillRecord[]
  gettingStarted: AgentGettingStarted | null
  first_run_pending: boolean
}

export interface AgentPackSkill {
  name: string
  description: string
  instructions: string
}

export interface AgentPack {
  object: 'agent_pack'
  kind: 'swarm-agent-pack'
  skills: AgentPackSkill[]
  gettingStarted: AgentGettingStarted
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
/** GET /v1/agents/<id>/plugins/pack/ — ids only, no tokens (#1396 / #1397). */
export interface AgentPluginIdRow {
  pluginId: string
  name: string
  description: string
}
export type AgentPluginHostStatus =
  | 'enabled'
  | 'missing'
  | 'missing-auth'
  | 'missing-plugin'
export interface AgentPluginStatusRow extends AgentPluginIdRow {
  status: AgentPluginHostStatus
  /** Env *names* only. Values never belong here. */
  required_env?: string[]
}
/** Custom MCP that is named in memory, not packed as a plugin id. */
export interface AgentPluginMemoryNamed {
  name: string
  note: string
}
export interface AgentPluginPack {
  object: 'agent_plugin_pack'
  schema: number
  kind: string
  plugins: AgentPluginIdRow[]
  agent_id?: string
  memory_named?: AgentPluginMemoryNamed[]
}
export interface AgentPluginsStatus {
  object: 'agent_plugins' | 'agent_plugin_pack_import'
  agent_id: string
  plugins: AgentPluginStatusRow[]
  enabled: string[]
  missing: string[]
  missing_auth?: string[]
  missing_plugins?: string[]
  memory_named?: AgentPluginMemoryNamed[]
  pack?: {
    object: string
    schema: number
    kind: string
    plugins: AgentPluginIdRow[]
    memory_named?: AgentPluginMemoryNamed[]
  }
}
export type MarketplaceCatalogKind = 'teams' | 'plugins' | 'skills'
export interface MarketplaceCatalogItem {
  id: string
  kind: MarketplaceCatalogKind
  name: string
  summary: string
  source: string
  source_label: string
  external: boolean
  installable: boolean
  installed: boolean
  install_hint?: string
  html_url?: string
  stars?: number
  topics?: string[]
  required_env?: string[]
  tools_provided?: string[]
  danger_notes?: string[]
  plugin?: {
    name?: string
    kind?: 'local' | 'remote'
    command?: string
    args?: string[]
    url?: string
    env?: Record<string, string>
  }
  skill?: Record<string, unknown>
  team?: Record<string, unknown>
}
export interface MarketplaceSourceStatus {
  source: string
  source_label?: string
  enabled?: boolean
  stalled_reason?: string | null
  cached?: boolean
  item_count?: number
}
export interface MarketplaceCatalogResponse {
  object: 'marketplace_catalog'
  kind: MarketplaceCatalogKind
  sources: string[]
  external: boolean
  items: MarketplaceCatalogItem[]
  warnings: string[]
  // #1327: per-source stall reasons so the UI can show why a source stalled
  // instead of silently hiding its results.
  source_status?: MarketplaceSourceStatus[]
  stalled_reason?: string | null
}
export interface MarketplaceInstallResponse {
  object: 'marketplace_install'
  kind: MarketplaceCatalogKind
  id: string
  installed: boolean
  already_installed?: boolean
  health?: 'up' | 'down' | 'unknown'
  message?: string
  required_env?: string[]
  tools?: { name: string; description: string }[]
  skill?: { name: string; assets?: string[] }
  roster?: Record<string, unknown>
  needs_configuration?: { id: string; reason: string }[]
}

/**
 * GET/PATCH `/v1/preferences/` (REQ-144).
 *
 * #1202: `hide_unsupported_agent_picker` / `hide_unsupported_session_picker`
 * let a power user unmount a navbar selector the active seat cannot support
 * instead of leaving it greyed. Both default `false`. The server may surface
 * them top-level or inside the `values` bag (older rows) — read both.
 */
export interface UserPreferences {
  object: 'user_preferences'
  principal: string
  guest: boolean
  empty: boolean
  hide_unsupported_agent_picker?: boolean
  hide_unsupported_session_picker?: boolean
  operator_profile?: {
    name?: string
    timezone?: string
    about?: string
  }
  /** #1323: global operator note injected as [Operator profile]. */
  about_me?: string
  /** #1314: who can read GET /v1/activity/ (off | operator | all). */
  activity_log_visibility?: ActivityLogVisibility
  values?: Record<string, unknown>
}

/** GET/POST /v1/activity/ — operator ActivityEvent feed (#1314). */
export type ActivityLogVisibility = 'off' | 'operator' | 'all'

export interface ActivityEvent {
  id: string
  actor_type: string
  actor_id: string
  action: string
  entity_type: string
  entity_id: string
  agent_id?: string | null
  run_id?: string | null
  responsible_user_id?: string | null
  detail?: Record<string, unknown> | null
  created_at: string
}

export interface ActivityList {
  object: 'activity_list'
  items: ActivityEvent[]
  count: number
  visibility: ActivityLogVisibility
}
