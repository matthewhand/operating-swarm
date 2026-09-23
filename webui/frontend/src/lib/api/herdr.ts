/** #856 slice A — herdr endpoints (moved verbatim from lib/api.ts). */
import {
  apiDelete,
  apiGet,
  apiPost,
} from './client'
import type {
  CreateHerdrAgentRequest,
  HerdrAgent,
  HerdrDiscoverMember,
  ListResponse,
} from './types'

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
