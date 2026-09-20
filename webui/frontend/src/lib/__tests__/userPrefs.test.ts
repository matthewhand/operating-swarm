import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../hiddenAgents'
import { DEFAULT_PINNED_SUPPORT, PINNED_AGENTS_STORAGE_KEY } from '../pinnedAgents'
import { HOSTNAME_OVERRIDE_KEY } from '../settingsPrefs'
import { AGENT_DROPDOWNS_STORAGE_KEY } from '../agentSettings'
import {
  USER_PREFS_CHANGED_EVENT,
  USER_PREFS_PATH,
  __resetUserPrefsCacheForTests,
  hydrateRailPrefs,
  parseAutoCompressPct,
  parseUserPrefs,
  saveUserPrefs,
} from '../userPrefs'

function jsonResponse(body: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 400,
    json: async () => body,
  } as Response
}

describe('userPrefs', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('defaults auto-compress percent to 80 and clamps 1–99', () => {
    expect(parseAutoCompressPct(undefined)).toBe(80)
    expect(parseAutoCompressPct(50)).toBe(50)
    expect(parseAutoCompressPct(0)).toBe(1)
    expect(parseAutoCompressPct(150)).toBe(99)
    expect(
      parseUserPrefs({
        object: 'user_preferences',
        empty: false,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
        context_auto_compress_pct: 50,
      })?.context_auto_compress_pct,
    ).toBe(50)
  })

  it('parses a user_preferences payload and rejects other shapes', () => {
    expect(parseUserPrefs({ object: 'list', data: [] })).toBeNull()
    expect(
      parseUserPrefs({
        object: 'user_preferences',
        principal: 'user:alice',
        guest: false,
        empty: false,
        favourites: [{ id: 'codey', name: 'Codey' }, { id: 'codey' }, 'stewie'],
        hidden_agents: ['gate', '', 'skeptic'],
        hostname_override: '  lab-box  ',
      }),
    ).toEqual({
      object: 'user_preferences',
      principal: 'user:alice',
      guest: false,
      empty: false,
      favourites: [
        { id: 'codey', name: 'Codey' },
        { id: 'stewie', name: 'stewie' },
      ],
      hidden_agents: ['gate', 'skeptic'],
      hostname_override: 'lab-box',
      context_auto_compress_pct: 80,
      context_strategy: 'compress',
      context_cull_trigger_pct: 90,
      context_cull_fraction_pct: 50,
      values: {},
      agent_dropdowns: {},
    })
  })

  it('reads agent_dropdowns from values and top-level', () => {
    expect(
      parseUserPrefs({
        object: 'user_preferences',
        empty: false,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
        values: {
          agent_dropdowns: {
            cli_agent: { cli: 'grok', model: 'grok-4', api_key: 'sk-nope' },
            '': { cli: 'agy' },
          },
        },
      })?.agent_dropdowns,
    ).toEqual({ cli_agent: { cli: 'grok', model: 'grok-4' } })
    expect(
      parseUserPrefs({
        object: 'user_preferences',
        empty: false,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
        agent_dropdowns: { starter: { remote: 'omb', blueprint: 'codey' } },
      })?.agent_dropdowns,
    ).toEqual({ starter: { remote: 'omb', blueprint: 'codey' } })
  })

  it('applies server agent_dropdowns onto the local cache', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          object: 'user_preferences',
          empty: false,
          favourites: [{ id: 'support', name: 'Support' }],
          hidden_agents: [],
          hostname_override: '',
          values: { agent_dropdowns: { cli_agent: { cli: 'antigravity', model: 'grok-4' } } },
        }),
      ),
    )
    const next = await hydrateRailPrefs()
    expect(next.source).toBe('server')
    expect(JSON.parse(localStorage.getItem(AGENT_DROPDOWNS_STORAGE_KEY) || '{}')).toEqual({
      cli_agent: { cli: 'antigravity', model: 'grok-4' },
    })
  })

  it('uses the server bag when it is not empty (server wins)', async () => {
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, JSON.stringify([{ id: 'old', name: 'Old' }]))
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['stale']))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          object: 'user_preferences',
          principal: 'user:alice',
          empty: false,
          favourites: [{ id: 'codey', name: 'Codey' }, { id: 'support', name: 'Support' }],
          hidden_agents: ['gate'],
          hostname_override: 'lab-box',
        }),
      ),
    )

    const next = await hydrateRailPrefs([{ id: 'gate', name: 'Gate' }])
    expect(next.source).toBe('server')
    expect(next.pins.map((pin) => pin.id)).toEqual(['codey', 'support'])
    expect(next.hidden).toEqual(['gate'])
    expect(next.hostnameOverride).toBe('lab-box')
    expect(localStorage.getItem(HOSTNAME_OVERRIDE_KEY)).toBe('lab-box')
    expect(JSON.parse(localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) || '[]').map((p: { id: string }) => p.id)).toEqual([
      'codey',
      'support',
    ])
    expect(JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')).toEqual(['gate'])
  })

  it('imports localStorage once when the server bag is empty', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'codey', name: 'Codey' }]),
    )
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['skeptic']))
    localStorage.setItem(HOSTNAME_OVERRIDE_KEY, 'old-host')
    const fetchMock = vi.fn().mockImplementation(async (_url: RequestInfo, init?: RequestInit) => {
      if (init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body || '{}'))
        return jsonResponse({
          object: 'user_preferences',
          empty: false,
          favourites: body.favourites,
          hidden_agents: body.hidden_agents,
          hostname_override: body.hostname_override,
        })
      }
      return jsonResponse({
        object: 'user_preferences',
        empty: true,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const next = await hydrateRailPrefs()
    expect(next.source).toBe('import')
    expect(next.pins).toEqual([{ id: 'codey', name: 'Codey' }])
    expect(next.hidden).toEqual(['skeptic'])
    expect(next.hostnameOverride).toBe('old-host')
    const patchCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PATCH')
    expect(patchCall?.[0]).toContain(USER_PREFS_PATH)
    const sent = JSON.parse(String(patchCall?.[1]?.body || '{}'))
    expect(sent.favourites).toEqual([{ id: 'codey', name: 'Codey' }])
    expect(sent.hidden_agents).toEqual(['skeptic'])
    expect(sent.hostname_override).toBe('old-host')
  })

  it('seeds Support + default hidden, then imports, when both stores are empty', async () => {
    const fetchMock = vi.fn().mockImplementation(async (_url: RequestInfo, init?: RequestInit) => {
      if (init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body || '{}'))
        return jsonResponse({
          object: 'user_preferences',
          empty: false,
          favourites: body.favourites,
          hidden_agents: body.hidden_agents,
        })
      }
      return jsonResponse({
        object: 'user_preferences',
        empty: true,
        favourites: [],
        hidden_agents: [],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const catalog = [
      { id: 'support', name: 'Support' },
      { id: 'tool_gate', name: 'Gate' },
      { id: 'skeptic', name: 'Skeptic' },
    ]
    const next = await hydrateRailPrefs(catalog)
    expect(next.source).toBe('import')
    expect(next.pins).toEqual([DEFAULT_PINNED_SUPPORT])
    expect(next.hidden).toEqual(['tool_gate', 'skeptic'])
  })

  it('keeps localStorage when the API is offline or the shape is wrong', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'codey', name: 'Codey' }]),
    )
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['codey']))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ object: 'list', data: [] })),
    )

    const next = await hydrateRailPrefs()
    expect(next.source).toBe('local')
    expect(next.pins).toEqual([{ id: 'codey', name: 'Codey' }])
    expect(next.hidden).toEqual(['codey'])
  })

  it('saveUserPrefs writes the PATCH body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        object: 'user_preferences',
        empty: false,
        favourites: [{ id: 'support', name: 'Support' }],
        hidden_agents: ['gate'],
        hostname_override: 'lab-box',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const saved = await saveUserPrefs({
      favourites: [{ id: 'support', name: 'Support' }],
      hidden_agents: ['gate'],
      hostname_override: 'lab-box',
    })
    expect(saved?.favourites).toEqual([{ id: 'support', name: 'Support' }])
    expect(saved?.hostname_override).toBe('lab-box')
    expect(fetchMock).toHaveBeenCalled()
    const call = fetchMock.mock.calls.find((entry) => entry[1]?.method === 'PATCH')
    expect(call).toBeTruthy()
    expect(String(call?.[0])).toContain(USER_PREFS_PATH)
    expect(JSON.parse(String(call?.[1]?.body || '{}')).hostname_override).toBe('lab-box')
  })

  it('saveUserPrefs writes agent_dropdowns inside values', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        object: 'user_preferences',
        empty: false,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
        values: { agent_dropdowns: { cli_agent: { cli: 'grok' } } },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const saved = await saveUserPrefs({
      agent_dropdowns: { cli_agent: { cli: 'grok' } },
    })
    expect(saved?.agent_dropdowns).toEqual({ cli_agent: { cli: 'grok' } })
    const call = fetchMock.mock.calls.find((entry) => entry[1]?.method === 'PATCH')
    expect(JSON.parse(String(call?.[1]?.body || '{}')).values).toEqual({
      agent_dropdowns: { cli_agent: { cli: 'grok' } },
    })
  })

  it('saveUserPrefs dispatches USER_PREFS_CHANGED_EVENT when PATCH returns prefs', async () => {
    const seen: unknown[] = []
    const onChange = (event: Event) => {
      seen.push((event as CustomEvent).detail)
    }
    window.addEventListener(USER_PREFS_CHANGED_EVENT, onChange)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          object: 'user_preferences',
          empty: false,
          favourites: [],
          hidden_agents: [],
          hostname_override: '',
          context_strategy: 'cull',
        }),
      ),
    )
    const saved = await saveUserPrefs({ context_strategy: 'cull' })
    window.removeEventListener(USER_PREFS_CHANGED_EVENT, onChange)
    expect(saved?.context_strategy).toBe('cull')
    expect(seen).toHaveLength(1)
    expect((seen[0] as { context_strategy?: string }).context_strategy).toBe('cull')
  })

  it('saveUserPrefs returns null and does not dispatch when PATCH fails', async () => {
    const seen: unknown[] = []
    const onChange = (event: Event) => {
      seen.push((event as CustomEvent).detail)
    }
    window.addEventListener(USER_PREFS_CHANGED_EVENT, onChange)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ error: 'nope' }, false)),
    )
    const saved = await saveUserPrefs({ hostname_override: 'lab-box' })
    window.removeEventListener(USER_PREFS_CHANGED_EVENT, onChange)
    expect(saved).toBeNull()
    expect(seen).toHaveLength(0)
  })
})
