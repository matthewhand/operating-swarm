/** #1399 — agent template pack APIs from #1398. SPA gallery / installer only. */

import { apiGet, apiPost } from './client'

export interface AgentTemplateProfile {
  display_name: string
  description: string
  title: string
  role: string
  avatar_shape: string
  avatar_color: string
  avatar_path: string | null
}

export interface AgentTemplateMemory {
  kind: string
  title: string
  body: string
}

export interface AgentTemplateSkill {
  name: string
  description: string
  instructions: string
}

export interface AgentTemplateGettingStarted {
  skill: string
}

export interface AgentTemplatePack {
  object?: 'agent_template'
  schema: number
  kind: 'agent_template'
  agent_id?: string
  profile: AgentTemplateProfile
  memories: AgentTemplateMemory[]
  skills: AgentTemplateSkill[]
  gettingStarted: AgentTemplateGettingStarted | null
  routines: unknown[]
  plugins: unknown[]
}

export interface GrokBotAvatar {
  shape?: string
  color?: string
  path?: string | null
}

export interface GrokBotTemplate {
  object?: 'grok_bot_template'
  schema: number
  kind: 'grok_bot_template'
  name: string
  description: string
  title: string
  role: string
  avatar?: GrokBotAvatar
  memories: AgentTemplateMemory[]
  skills: AgentTemplateSkill[]
  gettingStarted: AgentTemplateGettingStarted | null
  routines: unknown[]
  plugins: unknown[]
}

export type TemplatePayload = AgentTemplatePack | GrokBotTemplate | Record<string, unknown>

export interface AgentTemplateApplied {
  profile: boolean
  memories: number
  skills: number
  routines: number
  plugins: number
}

export interface TemplateFillIn {
  key: string
  label?: string
  required?: boolean
  status?: string
}

export interface AgentTemplateImportResult {
  object: 'agent_template_import'
  agent_id: string
  created?: boolean
  template: AgentTemplatePack
  applied: AgentTemplateApplied
  pending_enable?: boolean
  fill_ins_remaining?: TemplateFillIn[]
  plugins_missing?: string[]
}

function agentPath(agentId: string): string {
  return encodeURIComponent(agentId)
}

export function fetchAgentTemplate(agentId: string): Promise<AgentTemplatePack> {
  return apiGet<AgentTemplatePack>(`/v1/agents/${agentPath(agentId)}/template/`)
}

export function fetchAgentTemplateGrok(agentId: string): Promise<GrokBotTemplate> {
  return apiGet<GrokBotTemplate>(`/v1/agents/${agentPath(agentId)}/template/grok/`)
}

export function importAgentTemplate(
  agentId: string,
  pack: TemplatePayload,
): Promise<AgentTemplateImportResult> {
  return apiPost<AgentTemplateImportResult>(
    `/v1/agents/${agentPath(agentId)}/template/import/`,
    pack,
  )
}

export function validateAgentTemplate(pack: TemplatePayload): Promise<AgentTemplatePack> {
  return apiPost<AgentTemplatePack>('/v1/agent-templates/validate/', pack)
}

export function fromGrokTemplate(pack: TemplatePayload): Promise<AgentTemplatePack> {
  return apiPost<AgentTemplatePack>('/v1/agent-templates/from-grok/', pack)
}

export function createAgentFromTemplate(
  pack: TemplatePayload,
): Promise<AgentTemplateImportResult> {
  return apiPost<AgentTemplateImportResult>('/v1/agent-templates/import/', pack)
}
