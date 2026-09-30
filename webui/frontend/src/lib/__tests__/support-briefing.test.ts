import { describe, expect, it } from 'vitest'
import { buildSupportBriefing, inferenceConfigured, supportQuickstarts } from '../support-briefing'
import type { Agent } from '../../types/agent'

const agents: Agent[] = [
  {
    agent_id: 'starter-support',
    name: 'Support',
    specialty: '',
    color: '#f5c542',
    icon: '🛟',
    type: 'specialist',
    role: 'support',
    kind: 'api',
    agent_type: 'api',
  },
  {
    agent_id: 'starter-cli',
    name: 'CLI agent',
    specialty: '',
    color: '#22c55e',
    icon: '⌨️',
    type: 'specialist',
    kind: 'cli',
    agent_type: 'cli',
  },
]

describe('support briefing', () => {
  it('lists non-support agents and flags missing inference', () => {
    expect(inferenceConfigured({ llmProfiles: [], defaultLlm: '', clis: [] })).toBe(false)
    const text = buildSupportBriefing({
      agents,
      llmProfiles: [],
      defaultLlm: '',
      clis: [],
    })
    expect(text).toContain('CLI agent')
    expect(text).not.toMatch(/^- \*\*Support\*\*/m)
    expect(text).toContain('No inference configured')
    expect(text).toContain('/chat?settings=llm-profiles')
    expect(text).toContain('/chat?settings=true')
    expect(text).not.toContain('](/settings/)')
    expect(supportQuickstarts(false).map((p) => p.label)).toContain('Configure inference')
    expect(supportQuickstarts(true).map((p) => p.label)).toContain('Create a team')
    expect(supportQuickstarts(true).map((p) => p.label)).toContain(
      'Create a BA → Engineer → Tester workflow',
    )
    expect(supportQuickstarts(true).map((p) => p.label)).toContain('Add a remote')
    expect(supportQuickstarts(true).map((p) => p.label)).toContain('Wire a CLI')
    expect(text).toContain('create a team')
    expect(text).toContain('add a remote')
    expect(text).toContain('wire a CLI')
  })
})
