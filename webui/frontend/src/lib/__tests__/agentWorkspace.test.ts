import { afterEach, describe, expect, it } from 'vitest'
import { AGENT_EDITS_KEY, saveAgentEdit } from '../agentEdits'
import {
  FOLDER_FORMAT_ERROR,
  GITHUB_REPO_FORMAT_ERROR,
  emptyWorkspaceFields,
  formatNavbarWorkspaceSubtitle,
  isValidFolderPath,
  isValidGithubRepo,
  loadAgentWorkspace,
  navbarWorkspaceSubtitle,
  persistSessionWorkspace,
  saveAgentWorkspace,
} from '../agentWorkspace'

describe('agentWorkspace (REQ-166 Phase 0)', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
  })

  it('starts empty and persists folder + repo without enabling workspaces', () => {
    expect(loadAgentWorkspace('cli_agent')).toEqual(emptyWorkspaceFields())
    const saved = saveAgentWorkspace('cli_agent', {
      folder: '  /home/dev/tool  ',
      githubRepo: '  acme/app  ',
      workspacesEnabled: true,
    })
    expect(saved).toEqual({
      folder: '/home/dev/tool',
      githubRepo: 'acme/app',
      workspacesEnabled: true,
    })
    expect(loadAgentWorkspace('cli_agent')).toEqual(saved)
  })

  it('clears workspaces when repo is blank or invalid', () => {
    saveAgentEdit('cli_agent', { githubRepo: 'acme/app', workspacesEnabled: true })
    expect(saveAgentWorkspace('cli_agent', { githubRepo: '' }).workspacesEnabled).toBe(false)
    saveAgentEdit('cli_agent', { githubRepo: 'acme/app', workspacesEnabled: true })
    expect(saveAgentWorkspace('cli_agent', { githubRepo: 'not a repo' }).workspacesEnabled).toBe(false)
  })

  it('validates folder path format chrome', () => {
    expect(isValidFolderPath('')).toBe(true)
    expect(isValidFolderPath('/home/dev/tool')).toBe(true)
    expect(isValidFolderPath('./project')).toBe(true)
    expect(isValidFolderPath('/invalid/*/path')).toBe(false)
    expect(FOLDER_FORMAT_ERROR).toMatch(/valid directory path/i)
  })

  it('validates GitHub repo format chrome', () => {
    expect(isValidGithubRepo('')).toBe(true)
    expect(isValidGithubRepo('acme/app')).toBe(true)
    expect(isValidGithubRepo('https://github.com/acme/app')).toBe(true)
    expect(isValidGithubRepo('https://github.com/acme/app.git')).toBe(true)
    expect(isValidGithubRepo('not a repo')).toBe(false)
    expect(isValidGithubRepo('https://example.com/acme/app')).toBe(false)
    expect(GITHUB_REPO_FORMAT_ERROR).toMatch(/owner\/repo/i)
  })
})

describe('navbar workspace subtitle (#65)', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
  })

  it('formats folder, workspace, and branch without an empty line', () => {
    expect(formatNavbarWorkspaceSubtitle({})).toBe('')
    expect(formatNavbarWorkspaceSubtitle({ folder: '  ', branch: '  ' })).toBe('')
    expect(formatNavbarWorkspaceSubtitle({ folder: '/home/dev/tool' })).toBe('/home/dev/tool')
    expect(formatNavbarWorkspaceSubtitle({ workspace: 'acme/app' })).toBe('acme/app')
    expect(formatNavbarWorkspaceSubtitle({ branch: 'main' })).toBe('branch: main')
    expect(
      formatNavbarWorkspaceSubtitle({ folder: '/home/dev/tool', branch: 'main' }),
    ).toBe('/home/dev/tool — branch: main')
    expect(
      formatNavbarWorkspaceSubtitle({
        folder: '',
        workspace: 'acme/app',
        branch: 'feat/x',
      }),
    ).toBe('acme/app — branch: feat/x')
  })

  it('prefers folder over github repo and reads the live agent edit', () => {
    expect(navbarWorkspaceSubtitle('')).toBe('')
    expect(navbarWorkspaceSubtitle('cli_agent')).toBe('')
    saveAgentEdit('cli_agent', { githubRepo: 'acme/app', gitBranch: 'main' })
    expect(navbarWorkspaceSubtitle('cli_agent')).toBe('acme/app — branch: main')
    saveAgentEdit('cli_agent', { folder: '/home/dev/tool', gitBranch: 'main' })
    expect(navbarWorkspaceSubtitle('cli_agent')).toBe('/home/dev/tool — branch: main')
  })

  it('persists session cwd and branch onto the agent edit', () => {
    persistSessionWorkspace('cli_agent', {
      folder: ' /home/dev/tool ',
      gitBranch: ' feat/x ',
    })
    expect(loadAgentWorkspace('cli_agent').folder).toBe('/home/dev/tool')
    expect(navbarWorkspaceSubtitle('cli_agent')).toBe('/home/dev/tool — branch: feat/x')
  })
})
