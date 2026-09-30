import { describe, it, expect } from 'vitest'
import {
  apiModelOptionsFromProfiles,
  cliModelOptionsFor,
  designedCliSeat,
  discoverChatClis,
  honestChatCliModels,
  isApiBlueprintId,
  isCliAgentContext,
  isCliBlueprintId,
  preferredChatCli,
} from '../cliAgentContext'

describe('isCliBlueprintId', () => {
  it('matches cli_agent and the cli_* family', () => {
    expect(isCliBlueprintId('cli_agent')).toBe(true)
    expect(isCliBlueprintId('cli_fusion')).toBe(true)
    expect(isCliBlueprintId('cli_map')).toBe(true)
    expect(isCliBlueprintId('CLI_ORCHESTRATOR')).toBe(true)
  })

  it('rejects blueprint-mode slugs', () => {
    expect(isCliBlueprintId('codey')).toBe(false)
    expect(isCliBlueprintId('hybrid_team')).toBe(false)
    expect(isCliBlueprintId('swarm_ensemble')).toBe(false)
    expect(isCliBlueprintId('')).toBe(false)
  })
})

describe('isCliAgentContext', () => {
  it('detects cli_* blueprint ids', () => {
    expect(isCliAgentContext({ blueprintId: 'cli_agent' })).toBe(true)
    expect(isCliAgentContext({ blueprintId: 'cli_fusion' })).toBe(true)
  })

  it('detects explicit ?mode=cli / ?mode=cli_agent', () => {
    expect(
      isCliAgentContext({ searchParams: new URLSearchParams('mode=cli') }),
    ).toBe(true)
    expect(
      isCliAgentContext({ searchParams: new URLSearchParams('mode=cli_agent') }),
    ).toBe(true)
  })

  it('detects explicit ?cli=<name>', () => {
    expect(
      isCliAgentContext({ searchParams: new URLSearchParams('cli=grok') }),
    ).toBe(true)
  })

  it('never treats an API seat as CLI, even with a leftover ?cli= (#108)', () => {
    expect(
      isCliAgentContext({
        blueprintId: 'api_agent',
        searchParams: new URLSearchParams('blueprint=api_agent&cli=grok'),
      }),
    ).toBe(false)
    expect(
      isCliAgentContext({
        blueprintId: 'api_agent',
        searchParams: new URLSearchParams('mode=cli'),
      }),
    ).toBe(false)
  })

  it('stays in blueprint mode without those signals', () => {
    expect(isCliAgentContext({ blueprintId: 'codey' })).toBe(false)
    expect(
      isCliAgentContext({
        blueprintId: 'hybrid_team',
        searchParams: new URLSearchParams('blueprint=hybrid_team'),
      }),
    ).toBe(false)
    expect(isCliAgentContext({ searchParams: new URLSearchParams() })).toBe(false)
    expect(
      isCliAgentContext({ searchParams: new URLSearchParams('cli=') }),
    ).toBe(false)
  })
})

describe('isApiBlueprintId', () => {
  it('matches api_agent and api-prefixed ids (#108)', () => {
    expect(isApiBlueprintId('api_agent')).toBe(true)
    expect(isApiBlueprintId('API_AGENT')).toBe(true)
    expect(isApiBlueprintId('api')).toBe(true)
    expect(isApiBlueprintId('api:orchestration')).toBe(true)
  })

  it('rejects CLI and blueprint slugs', () => {
    expect(isApiBlueprintId('cli_agent')).toBe(false)
    expect(isApiBlueprintId('codey')).toBe(false)
    expect(isApiBlueprintId('')).toBe(false)
    expect(isApiBlueprintId(null)).toBe(false)
  })
})

describe('discoverChatClis', () => {
  it('lists discovered host CLIs plus configured names, never the static catalog', () => {
    expect(
      discoverChatClis({
        clis: ['claude', 'codex', 'gemini', 'grok', 'opencode', 'pi'],
        known: ['claude', 'codex', 'gemini', 'grok', 'opencode', 'pi'],
        installed: ['grok', 'claude'],
        discovered: ['grok', 'claude'],
        configured: ['grok', 'my_custom_cli'],
        native_consensus: {},
        catalog: {},
        rail: [
          {
            id: 'cli_agent',
            object: 'cli.agent',
            name: 'cli_agent',
            cli: 'grok',
            kind: 'cli',
            description: 'Host CLI',
            installed: true,
          },
        ],
      }),
    ).toEqual(['grok', 'claude', 'my_custom_cli'])
  })

  it('starts from discovered CLIs when nothing is configured (pi absent stays absent)', () => {
    expect(
      discoverChatClis({
        clis: ['grok', 'claude', 'pi'],
        known: ['grok', 'claude', 'pi'],
        installed: ['grok'],
        discovered: ['grok'],
        configured: [],
        native_consensus: {},
        catalog: {},
      }),
    ).toEqual(['grok'])
  })

  it('returns empty when the payload is missing', () => {
    expect(discoverChatClis(undefined)).toEqual([])
  })

  it('includes a selected/running CLI that is outside the static catalog', () => {
    expect(
      discoverChatClis(
        {
          clis: ['claude', 'codex', 'gemini', 'grok', 'opencode'],
          installed: ['grok'],
          configured: ['grok'],
          native_consensus: {},
          catalog: {},
        },
        'antigravity',
      ),
    ).toEqual(['grok', 'antigravity'])
  })

  it('lists only the selected CLI when discovery is empty', () => {
    expect(discoverChatClis(undefined, 'antigravity')).toEqual(['antigravity'])
  })
})

describe('preferredChatCli', () => {
  it('keeps a current selection that is still available', () => {
    expect(preferredChatCli(['claude', 'grok'], 'claude')).toBe('claude')
  })

  it('keeps a running CLI even when it is outside the discovered list', () => {
    expect(preferredChatCli(['grok', 'claude'], 'antigravity')).toBe('antigravity')
  })

  it('prefers grok when nothing is selected', () => {
    expect(preferredChatCli(['claude', 'grok'], '')).toBe('grok')
  })

  it('takes the first name when grok is absent', () => {
    expect(preferredChatCli(['claude', 'gemini'], '')).toBe('claude')
  })
})

describe('honestChatCliModels', () => {
  it('drops default / You and keeps live ids', () => {
    expect(
      honestChatCliModels({
        models: ['grok-4.5', 'default', 'You', ''],
        warning: undefined,
      }),
    ).toEqual({ models: ['grok-4.5'], warning: null })
  })

  it('keeps an empty probe empty and surfaces the warning', () => {
    expect(
      honestChatCliModels({
        models: [],
        warning: 'grok: CLI not installed (no \'grok\' on PATH)',
      }),
    ).toEqual({
      models: [],
      warning: "grok: CLI not installed (no 'grok' on PATH)",
    })
  })

  it('does not invent default when the payload is missing', () => {
    expect(honestChatCliModels(undefined)).toEqual({ models: [], warning: null })
  })

  it('keeps pi provider/model ids and still drops default', () => {
    expect(
      honestChatCliModels({
        models: ['openai/gpt-4o', 'anthropic/claude-sonnet-4-6', 'default'],
        warning: undefined,
      }),
    ).toEqual({
      models: ['openai/gpt-4o', 'anthropic/claude-sonnet-4-6'],
      warning: null,
    })
  })
})

describe('cliModelOptionsFor', () => {
  it('uses the CLI probe payload only, never API profile ids', () => {
    // The CLI's own list. An API/LLM-profile id (e.g. litellm/orchestration)
    // is a different namespace and must not appear unless the CLI listed it.
    expect(
      cliModelOptionsFor({
        models: ['gpt-4o', 'o1-mini'],
        warning: undefined,
      }),
    ).toEqual({ models: ['gpt-4o', 'o1-mini'], warning: null })
  })

  it('falls back to that CLI catalog presets when the probe is empty', () => {
    expect(
      cliModelOptionsFor(
        { models: [], warning: 'agy: CLI not installed' },
        ['gemini-3.8-flash-high', 'claude-sonnet-4-6'],
      ),
    ).toEqual({
      models: ['gemini-3.8-flash-high', 'claude-sonnet-4-6'],
      warning: 'agy: CLI not installed',
    })
  })

  it('never invents a fallback when there are no presets', () => {
    expect(cliModelOptionsFor({ models: [], warning: undefined })).toEqual({
      models: [],
      warning: null,
    })
  })

  it('drops hidden routing labels and dedupes', () => {
    expect(
      cliModelOptionsFor({
        models: ['gpt-4o', 'default', 'You', 'gpt-4o', ''],
        warning: undefined,
      }),
    ).toEqual({ models: ['gpt-4o'], warning: null })
  })
})

describe('apiModelOptionsFromProfiles', () => {
  it('lists profile ids and model fields, never default', () => {
    expect(
      apiModelOptionsFromProfiles(
        [
          { id: 'orchestration', name: 'User chat', model: 'gpt-4o' },
          { id: 'default', name: 'Default' },
        ],
        ['auxiliary'],
      ),
    ).toEqual([
      { id: 'orchestration', label: 'User chat' },
      { id: 'gpt-4o', label: 'gpt-4o' },
      { id: 'auxiliary', label: 'auxiliary' },
    ])
  })

  it('excludes CLI / remote / list_models namespaces from the API control', () => {
    const options = apiModelOptionsFromProfiles([
      {
        id: 'auxiliary',
        name: 'Auxiliary',
        model: 'gpt-4o-mini',
        source: 'config',
        namespace: 'api',
      },
      { id: 'agy', name: 'agy', source: 'cli', namespace: 'cli' },
      {
        id: 'opencode-go/x',
        model: 'opencode-go/x',
        source: 'list_models',
        namespace: 'cli',
      },
      { id: 'hermes', name: 'hermes', source: 'remote', namespace: 'remote' },
      // Older server, no explicit namespace: source still excludes it.
      { id: 'legacy-cli', name: 'legacy-cli', source: 'cli' },
      // Config profile from an older server (no namespace/source) stays.
      { id: 'custom', name: 'Custom' },
    ])
    expect(options.map((row) => row.id)).toEqual([
      'auxiliary',
      'gpt-4o-mini',
      'custom',
    ])
  })
})

describe('designedCliSeat', () => {
  const designs = [
    { agent_id: 'hass-eng', name: 'hass-eng', cli: 'opencode', description: 'engineer' },
    { agent_id: 'antigravity', name: 'AntiGravity', cli: 'agy', specialty: 'agy CLI' },
    { agent_id: 'planner', name: 'Planner', description: 'api design' },
  ]

  it('resolves a designer-created CLI seat to its declared cli', () => {
    expect(designedCliSeat('hass-eng', designs)).toEqual({
      id: 'hass-eng',
      name: 'hass-eng',
      cli: 'opencode',
      description: 'engineer',
    })
    // Rail id `antigravity` runs the `agy` catalog binary.
    expect(designedCliSeat('antigravity', designs)?.cli).toBe('agy')
    // `specialty` stands in for the description when `description` is absent.
    expect(designedCliSeat('antigravity', designs)?.description).toBe('agy CLI')
  })

  it('returns null for API designs, unknown ids, blank ids, and no designs', () => {
    expect(designedCliSeat('planner', designs)).toBeNull()
    expect(designedCliSeat('missing', designs)).toBeNull()
    expect(designedCliSeat('', designs)).toBeNull()
    expect(designedCliSeat('hass-eng', null)).toBeNull()
  })
})
