import { describe, expect, it } from 'vitest'
import { canEditAgentMessages, classifyAgentKind, isSwarmOwnedAgent } from '../agentKind'

describe('classifyAgentKind', () => {
  it('treats discovered blueprints as API (including cli_agent)', () => {
    expect(classifyAgentKind('jeeves')).toBe('api')
    expect(classifyAgentKind('cli_agent')).toBe('api')
    expect(classifyAgentKind('support')).toBe('api')
    expect(canEditAgentMessages('codey')).toBe(true)
  })

  it('classifies CLI and remote source prefixes', () => {
    expect(classifyAgentKind('cli:grok')).toBe('cli')
    expect(classifyAgentKind('remote:acp')).toBe('remote')
    expect(classifyAgentKind('placeholder:remote:acp')).toBe('remote')
    expect(canEditAgentMessages('cli:grok')).toBe(false)
    expect(canEditAgentMessages('remote:acp')).toBe(false)
  })

  it('lets an explicit kind win', () => {
    expect(classifyAgentKind('jeeves', 'cli')).toBe('cli')
    expect(classifyAgentKind('cli:grok', 'api')).toBe('api')
  })

  it('treats Herdr and remotes impls as Remote, not a fifth kind', () => {
    expect(classifyAgentKind('herdr')).toBe('remote')
    expect(classifyAgentKind('herdr:w3:p1')).toBe('remote')
    expect(classifyAgentKind('pane', 'herdr')).toBe('remote')
    expect(classifyAgentKind('hermes')).toBe('remote')
    expect(classifyAgentKind('omb')).toBe('remote')
    expect(classifyAgentKind('swarm')).toBe('api')
    expect(canEditAgentMessages('herdr')).toBe(false)
  })

  it('treats blueprint as a first-class swarm-owned kind', () => {
    expect(classifyAgentKind('jeeves', 'blueprint')).toBe('blueprint')
    expect(classifyAgentKind('blueprint:planner')).toBe('blueprint')
    expect(canEditAgentMessages('blueprint:planner')).toBe(true)
    expect(isSwarmOwnedAgent('blueprint:planner')).toBe(true)
    expect(isSwarmOwnedAgent('cli:grok')).toBe(false)
  })
})
