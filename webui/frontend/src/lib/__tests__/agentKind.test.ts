import { describe, expect, it } from 'vitest'
import { canEditAgentMessages, classifyAgentKind, isSwarmOwnedAgent } from '../agentKind'

describe('classifyAgentKind', () => {
  it('treats discovered blueprints as API', () => {
    expect(classifyAgentKind('jeeves')).toBe('api')
    expect(classifyAgentKind('support')).toBe('api')
    expect(canEditAgentMessages('codey')).toBe(true)
  })

  it('#534: recipe blueprints classify as their payload kind', () => {
    // The SPA sends `blueprint: remote_harness` when a remote seat chats, so
    // the recipe id is what every send-path gate sees. `cli_agent` is the
    // CLI-fleet recipe for the same reason.
    expect(classifyAgentKind('remote_harness')).toBe('remote')
    expect(classifyAgentKind('cli_agent')).toBe('cli')
    expect(canEditAgentMessages('remote_harness')).toBe(false)
    expect(canEditAgentMessages('cli_agent')).toBe(true)
    // Plain API seats keep their classification:
    expect(classifyAgentKind('api_agent')).toBe('api')
    expect(classifyAgentKind('chatbot')).toBe('api')
  })

  it('classifies CLI and remote source prefixes', () => {
    expect(classifyAgentKind('cli:grok')).toBe('cli')
    expect(classifyAgentKind('remote:acp')).toBe('remote')
    expect(classifyAgentKind('placeholder:remote:acp')).toBe('remote')
    // REQ-808: CLI edits restart the provider session, so they are allowed.
    expect(canEditAgentMessages('cli:grok')).toBe(true)
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
    expect(classifyAgentKind('openwebui')).toBe('remote')
    expect(classifyAgentKind('open-webui')).toBe('remote')
    expect(classifyAgentKind('omb')).toBe('remote')
    expect(classifyAgentKind('trueforge')).toBe('remote')
    expect(classifyAgentKind('n8n')).toBe('remote')
    expect(classifyAgentKind('swarm')).toBe('api')
    expect(canEditAgentMessages('herdr')).toBe(false)
    expect(canEditAgentMessages('trueforge')).toBe(false)
  })

  it('treats blueprint as a first-class swarm-owned kind', () => {
    expect(classifyAgentKind('jeeves', 'blueprint')).toBe('blueprint')
    expect(classifyAgentKind('blueprint:planner')).toBe('blueprint')
    expect(canEditAgentMessages('blueprint:planner')).toBe(true)
    expect(isSwarmOwnedAgent('blueprint:planner')).toBe(true)
    expect(isSwarmOwnedAgent('cli:grok')).toBe(false)
  })
})
