/** Per-agent skills CRUD + pack client (#1393 consumes #1392). */

import { apiDelete, apiGet, apiPatch, apiPost } from './client'
import type {
  AgentGettingStarted,
  AgentPack,
  AgentSkillRecord,
  AgentSkillsList,
} from './types'

export function agentSkillsUrl(agentId: string): string {
  return `/v1/agents/${encodeURIComponent(agentId)}/skills/`
}

export function agentSkillUrl(agentId: string, name: string): string {
  return `/v1/agents/${encodeURIComponent(agentId)}/skills/${encodeURIComponent(name)}/`
}

export function agentPackUrl(agentId: string): string {
  return `/v1/agents/${encodeURIComponent(agentId)}/pack/`
}

export function agentPackImportUrl(agentId: string): string {
  return `/v1/agents/${encodeURIComponent(agentId)}/pack/import/`
}

export const AGENT_PACK_VALIDATE_URL = '/v1/agent-packs/validate/'

export function isAgentSkillsList(raw: unknown): raw is AgentSkillsList {
  if (!raw || typeof raw !== 'object') return false
  const body = raw as Record<string, unknown>
  return body.object === 'agent_skill_list' && Array.isArray(body.skills)
}

export function isAgentPack(raw: unknown): raw is AgentPack {
  if (!raw || typeof raw !== 'object') return false
  const body = raw as Record<string, unknown>
  return body.kind === 'swarm-agent-pack' && Array.isArray(body.skills)
}

export function fetchAgentSkills(agentId: string): Promise<AgentSkillsList> {
  return apiGet<AgentSkillsList>(agentSkillsUrl(agentId))
}

export function createAgentSkill(
  agentId: string,
  body: {
    name?: string
    description?: string
    instructions?: string
    attach?: string
    gettingStarted?: boolean | AgentGettingStarted
  },
): Promise<AgentSkillRecord> {
  return apiPost<AgentSkillRecord>(agentSkillsUrl(agentId), body)
}

export function updateAgentSkill(
  agentId: string,
  name: string,
  body: Partial<Pick<AgentSkillRecord, 'name' | 'description' | 'instructions'>>,
): Promise<AgentSkillRecord> {
  return apiPatch<AgentSkillRecord>(agentSkillUrl(agentId, name), body)
}

export function deleteAgentSkill(agentId: string, name: string): Promise<void> {
  return apiDelete(agentSkillUrl(agentId, name))
}

export function setAgentGettingStarted(
  agentId: string,
  gettingStarted: AgentGettingStarted | null,
  firstRun?: boolean,
): Promise<AgentSkillsList> {
  const body: Record<string, unknown> = { gettingStarted }
  if (typeof firstRun === 'boolean') body.first_run = firstRun
  return apiPatch<AgentSkillsList>(agentSkillsUrl(agentId), body)
}

export function exportAgentPack(
  agentId: string,
  body: { skills: string[]; gettingStarted: AgentGettingStarted },
): Promise<AgentPack> {
  return apiPost<AgentPack>(agentPackUrl(agentId), body)
}

export function importAgentPack(agentId: string, pack: unknown): Promise<AgentSkillsList> {
  return apiPost<AgentSkillsList>(agentPackImportUrl(agentId), { pack })
}

export function validateAgentPack(pack: unknown): Promise<AgentPack> {
  return apiPost<AgentPack>(AGENT_PACK_VALIDATE_URL, pack)
}
