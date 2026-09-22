/** #856 slice A — blueprints endpoints (moved verbatim from lib/api.ts). */
import {
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  ensureCsrfCookie,
} from './client'
import type {
  BlueprintSource,
  BlueprintTools,
  CustomBlueprint,
  GenerateAgentRequest,
  GenerateAgentResponse,
  GeneratedAgentAvatar,
  RouterDesign,
  ValidateAgentResponse,
} from './types'

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
export function generateAgentAvatar(
  agentId: string,
  body: { prompt?: string; name?: string; role?: string } = {},
): Promise<GeneratedAgentAvatar> {
  return apiPost<GeneratedAgentAvatar>(
    `/v1/agents/${encodeURIComponent(agentId)}/avatar/generate/`,
    body,
  )
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
/**
 * POST /v1/blueprints/<id>/source/format — #537 pretty-print proposal.
 * Returns the formatted draft; the caller fills the editor and the user
 * still presses Save. Rejects with ApiError (400/501) otherwise.
 */
export function formatBlueprintSource(
  id: string,
  body: { content: string; file?: string },
): Promise<{ formatted: string; file?: string | null }> {
  return apiPost<{ formatted: string; file?: string | null }>(
    `/v1/blueprints/${encodeURIComponent(id)}/source/format`,
    { content: body.content, ...(body.file ? { file: body.file } : {}) },
  )
}
/** GET /v1/agents/designs/ — fast rail feed (no blueprint init). */
export function fetchDesignedAgents(): Promise<{ object: 'list'; data: RouterDesign[] }> {
  return apiGet<{ object: 'list'; data: RouterDesign[] }>('/v1/agents/designs/')
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
