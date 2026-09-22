/** #856 slice A — settings endpoints (moved verbatim from lib/api.ts). */
import {
  ApiError,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPostForm,
  apiPut,
  buildHeaders,
  throwApiError,
} from './client'
import type {
  Blueprint,
  BlueprintPersonas,
  ChatRetentionStats,
  CliAgentsInfo,
  CliCandidatesResult,
  CliDriverDescriptor,
  CliModelsResponse,
  CliProbeResult,
  CliRunStatus,
  CliRunTerminateResult,
  ConfigOptions,
  CreateCustomBlueprintRequest,
  CreateRoleRequest,
  CreateTeamRequest,
  CreateTeamRosterRequest,
  CustomBlueprint,
  EnvironmentVariablesResponse,
  ImageGenPatchRequest,
  ImageGenSettings,
  ListResponse,
  LlmProfileProbeRequest,
  LlmProfileProbeResult,
  LlmProfilesSettings,
  LocalStoreFacts,
  PatchLlmProfilesRequest,
  RemoteRoutinesResult,
  RoleDescriptor,
  ServerSettingsResponse,
  SkillRecord,
  SkillsList,
  SpeakSpeechOpts,
  SpeechEndpointSettings,
  SpeechPatchRequest,
  SpeechSettings,
  SpeechTranscription,
  Team,
  TeamAgent,
  TeamRosterRecord,
  UpsertLlmProfileRequest,
} from './types'

export function fetchBlueprints(): Promise<ListResponse<Blueprint>> {
  return apiGet<ListResponse<Blueprint>>('/v1/blueprints/')
}
export function fetchLlmProfiles(): Promise<LlmProfilesSettings> {
  return apiGet<LlmProfilesSettings>('/v1/llm-profiles/')
}
export function patchLlmProfiles(
  body: PatchLlmProfilesRequest,
): Promise<LlmProfilesSettings> {
  return apiPatch<LlmProfilesSettings>('/v1/llm-profiles/', body)
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
/** POST /v1/llm-profiles/test — live key/model probe. Never persists. */
export function testLlmProfile(
  body: LlmProfileProbeRequest,
): Promise<LlmProfileProbeResult> {
  return apiPost<LlmProfileProbeResult>('/v1/llm-profiles/test/', body)
}
export function fetchTeams(): Promise<ListResponse<Team>> {
  return apiGet<ListResponse<Team>>('/v1/teams/')
}
export async function fetchRoles(): Promise<{ object: string; data: RoleDescriptor[] }> {
  return apiGet<{ object: string; data: RoleDescriptor[] }>('/v1/roles/')
}
export async function createRole(request: CreateRoleRequest): Promise<RoleDescriptor> {
  return apiPost<RoleDescriptor>('/v1/roles/', request)
}
export async function deleteRole(roleName: string): Promise<void> {
  return apiDelete(`/v1/roles/${encodeURIComponent(roleName)}/`)
}
export function fetchTeamRosters(): Promise<ListResponse<TeamRosterRecord>> {
  return apiGet<ListResponse<TeamRosterRecord>>('/v1/team-rosters/')
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
export function fetchRemoteRoutines(remoteId: string): Promise<RemoteRoutinesResult> {
  return apiGet<RemoteRoutinesResult>(`/v1/remotes/${encodeURIComponent(remoteId)}/routines/`)
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
export function fetchServerSettings(): Promise<ServerSettingsResponse> {
  return apiGet<ServerSettingsResponse>('/settings/api/')
}
export function fetchEnvironmentVariables(): Promise<EnvironmentVariablesResponse> {
  return apiGet<EnvironmentVariablesResponse>('/settings/environment/')
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
export function transcribeSpeechAudio(
  file: Blob,
  filename = 'audio.webm',
  opts?: { agentId?: string },
): Promise<SpeechTranscription> {
  const form = new FormData()
  form.append('file', file, filename)
  const agentId = (opts?.agentId || '').trim()
  if (agentId) form.append('agent_id', agentId)
  return apiPostForm<SpeechTranscription>('/v1/speech/transcribe/', form)
}
export async function speakSpeechText(
  text: string,
  voiceOrOpts: string | SpeakSpeechOpts = '',
): Promise<Blob> {
  const opts: SpeakSpeechOpts =
    typeof voiceOrOpts === 'string' ? { voice: voiceOrOpts } : voiceOrOpts || {}
  const body: Record<string, string> = { text }
  if (opts.voice) body.voice = opts.voice
  if (opts.instruction) body.instruction = opts.instruction
  if (opts.agentId) body.agent_id = opts.agentId
  const response = await fetch('/v1/speech/speak/', {
    method: 'POST',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
    credentials: 'include',
  })
  if (!response.ok) {
    await throwApiError('/v1/speech/speak/', response)
  }
  return response.blob()
}
export function fetchBlueprintPersonas(id: string): Promise<BlueprintPersonas> {
  return apiGet<BlueprintPersonas>(`/v1/blueprints/${encodeURIComponent(id)}/personas`)
}
export function fetchCliAgents(): Promise<CliAgentsInfo> {
  return apiGet<CliAgentsInfo>('/v1/cli-agents/')
}
export function fetchCliCandidates(name: string): Promise<CliCandidatesResult> {
  const q = new URLSearchParams({ name })
  return apiGet<CliCandidatesResult>(`/v1/cli-agents/candidates?${q.toString()}`)
}
export function testCliBinary(cli: string): Promise<CliProbeResult> {
  return apiPost<CliProbeResult>('/v1/cli-agents/test/', { cli })
}
export function fetchCliDrivers(): Promise<{ drivers: CliDriverDescriptor[] }> {
  return apiGet<{ drivers: CliDriverDescriptor[] }>('/v1/cli-agents/drivers/')
}
export function fetchChatRetentionStats(): Promise<ChatRetentionStats> {
  return apiGet<ChatRetentionStats>('/v1/chat/retention/stats/')
}
export function triggerChatRetentionAction(
  action: 'archive' | 'archive_all' | 'restore' | 'empty_trash',
  agentId?: string,
): Promise<{ success: boolean; error?: string; archived?: unknown; restored?: unknown; removed?: unknown }> {
  return apiPost('/v1/chat/retention/action/', { action, agent_id: agentId })
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
export function fetchCliModels(cli: string): Promise<CliModelsResponse> {
  return apiGet<CliModelsResponse>(`/v1/cli-agents/${encodeURIComponent(cli)}/models/`)
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
export function fetchConfigOptions(): Promise<ConfigOptions> {
  return apiGet<ConfigOptions>('/v1/config-options/')
}
/** GET /v1/config-ownership/ — #776 Full coverage inventory + force-env. */
export function fetchConfigOwnership(): Promise<
  import('.././configOwnership').ConfigOwnershipPayload
> {
  return apiGet('/v1/config-ownership/')
}
export function fetchConfigSection(
  section: string,
): Promise<import('.././configOwnership').ConfigSectionPayload> {
  return apiGet(`/v1/config/sections/${encodeURIComponent(section)}/`)
}
export function patchConfigSection(
  section: string,
  body: {
    entries?: Record<string, unknown>
    upsert?: Record<string, unknown>
    delete?: string | string[]
  },
): Promise<import('.././configOwnership').ConfigSectionPayload> {
  return apiPatch(`/v1/config/sections/${encodeURIComponent(section)}/`, body)
}
