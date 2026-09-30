/** #1311 scoped library + roster pack client. */
import { apiGet, apiPost } from './client'
import type {
  LibraryScope,
  ListResponse,
  PresetRailSeat,
  RosterPackRecord,
  SharedLibraryImport,
  SharedLibraryItem,
} from './types'

function scopeQuery(scope: LibraryScope, teamId?: string): string {
  const params = new URLSearchParams({ scope })
  if (teamId) params.set('team_id', teamId)
  return `?${params.toString()}`
}

export function fetchScopedLibrary(
  scope: LibraryScope,
  teamId?: string,
): Promise<ListResponse<SharedLibraryItem>> {
  return apiGet<ListResponse<SharedLibraryItem>>(`/v1/library/${scopeQuery(scope, teamId)}`)
}

export function publishLibraryItem(body: {
  kind: 'blueprint' | 'plugin' | 'team'
  id: string
  scope: LibraryScope
  name?: string
  team_id?: string
  payload?: Record<string, unknown>
}): Promise<SharedLibraryItem> {
  return apiPost<SharedLibraryItem>('/v1/library/', { action: 'publish', ...body })
}

export function unpublishLibraryItem(id: string): Promise<SharedLibraryItem> {
  return apiPost<SharedLibraryItem>('/v1/library/', { action: 'unpublish', id })
}

export function importLibraryItem(id: string, teamId?: string): Promise<SharedLibraryImport> {
  return apiPost<SharedLibraryImport>('/v1/library/', {
    action: 'import',
    id,
    ...(teamId ? { team_id: teamId } : {}),
  })
}

export function createPresetBot(presetId: string): Promise<PresetRailSeat> {
  return apiPost<PresetRailSeat>('/v1/library/', { action: 'create_preset', preset_id: presetId })
}

export function fetchRosterPacks(
  scope: Exclude<LibraryScope, 'personal'>,
  teamId?: string,
): Promise<ListResponse<SharedLibraryItem>> {
  return apiGet<ListResponse<SharedLibraryItem>>(`/v1/team-rosters/${scopeQuery(scope, teamId)}`)
}

export function publishRosterPack(body: {
  roster_id: string
  scope: Exclude<LibraryScope, 'personal'>
  team_id?: string
  skill_ids?: string[]
  mcp_server_ids?: string[]
}): Promise<SharedLibraryItem> {
  return apiPost<SharedLibraryItem>('/v1/team-rosters/', { action: 'publish', ...body })
}

export function importRosterPack(
  id: string,
  teamId?: string,
): Promise<SharedLibraryImport & { roster?: RosterPackRecord }> {
  return apiPost(`/v1/team-rosters/`, {
    action: 'import',
    id,
    ...(teamId ? { team_id: teamId } : {}),
  })
}
