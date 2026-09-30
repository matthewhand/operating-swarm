/** #1311 — org-shared bot library (presets + whole-team share). */
import { apiDelete, apiGet, apiPost } from './client'
import type {
  ListResponse,
  OrgLibraryBot,
  OrgLibraryPublishBody,
  OrgLibraryShare,
} from './types'

export function fetchOrgLibrary(teamId?: string): Promise<ListResponse<OrgLibraryBot>> {
  const query = teamId ? `?team_id=${encodeURIComponent(teamId)}` : ''
  return apiGet<ListResponse<OrgLibraryBot>>(`/v1/org-library/${query}`)
}

export function fetchOrgLibraryBot(id: string): Promise<OrgLibraryBot> {
  return apiGet<OrgLibraryBot>(`/v1/org-library/${encodeURIComponent(id)}/`)
}

export function publishOrgLibraryBot(body: OrgLibraryPublishBody): Promise<OrgLibraryBot> {
  return apiPost<OrgLibraryBot>('/v1/org-library/', body)
}

export function removeOrgLibraryBot(id: string): Promise<void> {
  return apiDelete(`/v1/org-library/${encodeURIComponent(id)}/`)
}

/** Share a library bot with every member of one team roster. */
export function shareOrgLibraryBotWithTeam(id: string, teamId: string): Promise<OrgLibraryShare> {
  return apiPost<OrgLibraryShare>(`/v1/org-library/${encodeURIComponent(id)}/share/`, {
    scope: 'team',
    team_id: teamId,
  })
}
