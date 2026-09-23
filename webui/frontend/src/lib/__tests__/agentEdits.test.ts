import { afterEach, describe, expect, it } from 'vitest'
import {
  AGENT_EDITS_KEY,
  assignedBlueprintId,
  editedAgentLabel,
  loadAgentEdit,
  saveAgentEdit,
} from '../agentEdits'

describe('agentEdits', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
  })

  it('defaults the assigned blueprint to the agent id', () => {
    expect(assignedBlueprintId('support')).toBe('support')
    expect(loadAgentEdit('support')).toEqual({})
  })

  it('persists a blueprint assignment on that agent', () => {
    saveAgentEdit('support', { blueprintId: 'codey' })
    expect(assignedBlueprintId('support')).toBe('codey')
    expect(JSON.parse(localStorage.getItem(AGENT_EDITS_KEY) || '{}')).toEqual({
      support: { blueprintId: 'codey' },
    })
    expect(assignedBlueprintId('codey')).toBe('codey')
  })

  it('clears a self-assignment so the seat uses its own id', () => {
    saveAgentEdit('support', { blueprintId: 'codey' })
    saveAgentEdit('support', { blueprintId: 'support' })
    expect(assignedBlueprintId('support')).toBe('support')
    expect(localStorage.getItem(AGENT_EDITS_KEY)).toBe('{}')
  })

  it('persists name and role overrides', () => {
    saveAgentEdit('support', { name: '  Desk  ', role: 'gate' })
    expect(editedAgentLabel({ id: 'support', name: 'Support' })).toBe('Desk')
    expect(loadAgentEdit('support')).toEqual({ name: 'Desk', role: 'gate' })
  })

  it('persists CLI Folder on the agent record', () => {
    saveAgentEdit('cli_agent', { folder: '  /home/dev/tool  ' })
    expect(loadAgentEdit('cli_agent')).toEqual({ folder: '/home/dev/tool' })
    saveAgentEdit('cli_agent', { folder: '' })
    expect(loadAgentEdit('cli_agent')).toEqual({})
  })

  it('persists git branch for the navbar subtitle and clears it when folder changes', () => {
    saveAgentEdit('cli_agent', { folder: '/home/dev/tool', gitBranch: 'main' })
    expect(loadAgentEdit('cli_agent')).toEqual({ folder: '/home/dev/tool', gitBranch: 'main' })
    saveAgentEdit('cli_agent', { folder: '/home/dev/other' })
    expect(loadAgentEdit('cli_agent')).toEqual({ folder: '/home/dev/other' })
    saveAgentEdit('cli_agent', { folder: '/home/dev/other', gitBranch: 'feat/x' })
    expect(loadAgentEdit('cli_agent')).toEqual({ folder: '/home/dev/other', gitBranch: 'feat/x' })
    saveAgentEdit('cli_agent', { folder: '', gitBranch: '' })
    expect(loadAgentEdit('cli_agent')).toEqual({})
  })

  it('persists GitHub repo bind chrome on the agent record', () => {
    saveAgentEdit('cli_agent', { githubRepo: '  acme/app  ', workspacesEnabled: true })
    expect(loadAgentEdit('cli_agent')).toEqual({
      githubRepo: 'acme/app',
      workspacesEnabled: true,
    })
    saveAgentEdit('cli_agent', { githubRepo: '', workspacesEnabled: false })
    expect(loadAgentEdit('cli_agent')).toEqual({})
  })

  it('persists attached skills on the agent record', () => {
    saveAgentEdit('chatbot', { skills: [' conventional-commit ', 'writing-changelog'] })
    expect(loadAgentEdit('chatbot')).toEqual({
      skills: ['conventional-commit', 'writing-changelog'],
    })
    saveAgentEdit('chatbot', { skills: [] })
    expect(loadAgentEdit('chatbot')).toEqual({})
  })

  it('records an explicit role override separately from the value', () => {
    saveAgentEdit('codey', { role: 'engineer', roleOverridden: true, workflow: 'handoff' })
    expect(loadAgentEdit('codey')).toEqual({
      role: 'engineer',
      roleOverridden: true,
      workflow: 'handoff',
    })
  })
})
