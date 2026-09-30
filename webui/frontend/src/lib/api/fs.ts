/** Issue #1256 — server filesystem directory picker (agent Folder field). */
import { apiGet } from './client'

export interface FsDirectoryEntry {
  name: string
  path: string
  is_git_repo: boolean
}

export interface FsDirectoryListing {
  /** Absolute path currently listed. */
  path: string
  /** Parent path for the Up control, or null at a browse boundary. */
  parent: string | null
  /** Roots the caller is allowed to browse (home + workspaces). */
  roots: string[]
  entries: FsDirectoryEntry[]
}

/**
 * GET /v1/fs/directories/ — child directories of a server path.
 * Omitting `path` defaults to the user's home directory.
 */
export function fetchDirectories(path?: string): Promise<FsDirectoryListing> {
  const trimmed = (path || '').trim()
  const query = trimmed ? `?${new URLSearchParams({ path: trimmed }).toString()}` : ''
  return apiGet<FsDirectoryListing>(`/v1/fs/directories/${query}`)
}
