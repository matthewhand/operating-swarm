/** #856 slice A — teams endpoints (moved verbatim from lib/api.ts). */
import {
  apiDelete,
  apiGet,
  apiPost,
} from './client'
import type {
  LibraryEntry,
  ListResponse,
} from './types'

export function fetchLibrary(): Promise<ListResponse<LibraryEntry>> {
  return apiGet<ListResponse<LibraryEntry>>('/v1/library/')
}
export function addToLibrary(name: string): Promise<LibraryEntry> {
  return apiPost<LibraryEntry>('/v1/library/', { name })
}
export function removeFromLibrary(name: string): Promise<void> {
  return apiDelete(`/v1/library/${encodeURIComponent(name)}/`)
}
