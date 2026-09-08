/**
 * REQ-166 / #589 — Agent workspace binding (Phase 0 chrome).
 *
 * Folder is the CLI working-directory field (persist is cheap and already
 * used by later cwd work). GitHub repo + Workspaces are designed here as
 * coming-soon chrome: persist locally if the operator types a value, but
 * do not start a session cwd, checkout, or worktree from these fields.
 */

import { loadAgentEdit, saveAgentEdit } from './agentEdits'
import { FOLDER_FORMAT_ERROR, isValidFolderPath } from './agentFolder'

export { FOLDER_FORMAT_ERROR, isValidFolderPath }

export type AgentWorkspaceKind = 'cli' | 'api' | 'remote' | 'blueprint'

export interface AgentWorkspaceFields {
  folder: string
  githubRepo: string
  workspacesEnabled: boolean
}

export const WORKSPACE_SECTION_TITLE = 'Where this agent works'

export const WORKSPACE_SECTION_LEAD =
  'Optional bind for this agent. Folder is the local working directory. GitHub repo checkout and worktrees are coming soon.'

export const FOLDER_LABEL = 'Folder'
export const FOLDER_OPTIONAL = '(optional)'
export const FOLDER_PLACEHOLDER = '/path/to/working/directory or ./project'
export const FOLDER_HELP =
  'Working directory for this CLI agent. Absolute path (/home/you/project) or relative (./project). No wildcards.'
export const FOLDER_EMPTY_STATE =
  'No folder set. This CLI agent starts in the default working directory.'
export const FOLDER_COMING_SOON_HELP =
  'Folder as a host working directory is for CLI agents. API and Remote will get a start instruction instead of owning the filesystem.'

export const GITHUB_REPO_LABEL = 'GitHub repo'
export const GITHUB_REPO_PLACEHOLDER = 'owner/repo or https://github.com/owner/repo'
export const GITHUB_REPO_HELP =
  'Bind a repository. Checkout will land in a per-agent scratch, or in the Folder above if set. Not applied yet.'
export const GITHUB_REPO_FORMAT_ERROR =
  'Use owner/repo or a GitHub URL (e.g. acme/app or https://github.com/acme/app)'
export const GITHUB_REPO_EMPTY_STATE = 'No repo bound. Checkout and worktrees stay off until a later phase.'

export const WORKSPACES_LABEL = 'Workspaces'
export const WORKSPACES_HELP =
  'When a GitHub repo is bound, each scale-out instance gets its own git worktree. Not applied yet.'
export const WORKSPACES_DISABLED_HINT = 'Bind a GitHub repo first. Worktrees are coming soon.'

export const COMING_SOON_LABEL = 'Coming soon'

export const API_REMOTE_WORKSPACE_LEAD =
  'Folder, GitHub repo, and worktrees are not available for this kind yet. API and Remote agents will receive a start instruction instead of owning the host filesystem.'

const OWNER_REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

export function emptyWorkspaceFields(): AgentWorkspaceFields {
  return { folder: '', githubRepo: '', workspacesEnabled: false }
}

export function isValidGithubRepo(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return true
  if (/[\0*?"<>|\s]/.test(trimmed)) return false
  if (OWNER_REPO.test(trimmed)) return true
  try {
    const url = new URL(trimmed)
    const host = url.hostname.toLowerCase()
    if (host !== 'github.com' && host !== 'www.github.com') return false
    const parts = url.pathname.replace(/\.git$/i, '').split('/').filter(Boolean)
    return parts.length >= 2 && OWNER_REPO.test(`${parts[0]}/${parts[1]}`)
  } catch {
    return false
  }
}

export function loadAgentWorkspace(agentId: string): AgentWorkspaceFields {
  if (!agentId) return emptyWorkspaceFields()
  const edit = loadAgentEdit(agentId)
  return {
    folder: (edit.folder || '').trim(),
    githubRepo: (edit.githubRepo || '').trim(),
    workspacesEnabled: edit.workspacesEnabled === true,
  }
}

export function saveAgentWorkspace(
  agentId: string,
  fields: Partial<AgentWorkspaceFields>,
): AgentWorkspaceFields {
  if (!agentId) return emptyWorkspaceFields()
  const current = loadAgentWorkspace(agentId)
  const next: AgentWorkspaceFields = {
    folder: (fields.folder !== undefined ? fields.folder : current.folder).trim(),
    githubRepo: (fields.githubRepo !== undefined ? fields.githubRepo : current.githubRepo).trim(),
    workspacesEnabled:
      fields.workspacesEnabled !== undefined ? fields.workspacesEnabled : current.workspacesEnabled,
  }
  if (next.githubRepo.trim() && !isValidGithubRepo(next.githubRepo)) {
    next.workspacesEnabled = false
  }
  if (!next.githubRepo.trim()) {
    next.workspacesEnabled = false
  }
  saveAgentEdit(agentId, {
    folder: next.folder,
    githubRepo: next.githubRepo,
    workspacesEnabled: next.workspacesEnabled,
  })
  return next
}
