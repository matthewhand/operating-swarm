import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  formatContextCarriedStatus,
  hopContinueTargets,
  hopCliSession,
  isContextCarriedStatus,
} from '../cliSessionHop'
import { DEFAULT_HOP_MODE, loadHopPrefs, saveHopPrefs } from '../sessionHopPrefs'

describe('cliSessionHop', () => {
  afterEach(() => {
    window.localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('formats a carried-context line distinct from the dropdown-change chrome', () => {
    const line = formatContextCarriedStatus('grok', 'agy', 'summary', 847)
    expect(line).toBe(
      'Started a new agy session (grok → agy). Carried summary context (847 tokens).',
    )
    expect(isContextCarriedStatus(line)).toBe(true)
    expect(isContextCarriedStatus('CLI: grok → agy')).toBe(false)
  })

  it('lists continue-on targets without the current CLI', () => {
    expect(hopContinueTargets('grok', ['grok', 'agy', 'opencode'])).toEqual(['agy', 'opencode'])
  })

  it('posts hop with prefs and no secret-shaped payload', async () => {
    saveHopPrefs({ mode: 'summary', tokenBudget: 4000 })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        object: 'cli_session_hop',
        agent_id: 'cli_agent',
        conversation_id: 'thread-1',
        from_cli: 'grok',
        to_cli: 'agy',
        kind: 'cli',
        cli_session_id: null,
        mode: 'summary',
        tokens: 12,
        token_budget: 4000,
        omitted: ['secrets', 'tool_noise'],
        empty: false,
        status:
          'Started a new agy session (grok → agy). Carried summary context (12 tokens).',
        export_warning: null,
        import: 'swarm',
        injection: { text: 'seed', mode: 'summary', tokens: 12, empty: false },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const result = await hopCliSession({
      agentId: 'cli_agent',
      fromCli: 'grok',
      toCli: 'agy',
      conversationId: 'thread-1',
    })
    expect(result.cli_session_id).toBeNull()
    expect(result.status).toContain('Carried summary context')
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const body = JSON.parse(String(init.body || '{}'))
    expect(body.from_cli).toBe('grok')
    expect(body.to_cli).toBe('agy')
    expect(body.mode).toBe(DEFAULT_HOP_MODE)
    expect(JSON.stringify(body)).not.toMatch(/sk-[A-Za-z0-9]/)
  })
})

describe('sessionHopPrefs', () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  it('defaults to summary and persists full', () => {
    expect(loadHopPrefs()).toEqual({ mode: 'summary', tokenBudget: 4000 })
    saveHopPrefs({ mode: 'full', tokenBudget: 8000 })
    expect(loadHopPrefs()).toEqual({ mode: 'full', tokenBudget: 8000 })
  })
})
