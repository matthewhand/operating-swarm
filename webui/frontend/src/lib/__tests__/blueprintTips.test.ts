import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  OPENAI_AGENTS_TIP_PREF_KEY,
  OPENAI_AGENTS_TIP_STORAGE_KEY,
  TEAM_BLUEPRINT_TIP_PREF_KEY,
  TEAM_BLUEPRINT_TIP_STORAGE_KEY,
  blueprintTipKindFor,
  hydrateBlueprintTipsDismissed,
  isBlueprintTipDismissed,
  isOpenAiAgentsBlueprint,
  isTeamBlueprint,
  persistBlueprintTipDismissed,
  prefsBlueprintTipDismissed,
} from '../blueprintTips'
import { __resetUserPrefsCacheForTests } from '../userPrefs'

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function prefsPayload(values: Record<string, unknown> = {}, empty = false) {
  return {
    object: 'user_preferences',
    principal: 'session:test',
    guest: true,
    empty,
    favourites: [],
    hidden_agents: [],
    hostname_override: '',
    values,
  }
}

describe('#1252 blueprintTips detection', () => {
  it('detects openai-agents by blueprint id/name, swarm kind, or 2+ personas', () => {
    expect(isOpenAiAgentsBlueprint(null, { id: 'openai-agents' })).toBe(true)
    expect(isOpenAiAgentsBlueprint({ kind: 'swarm' })).toBe(true)
    expect(isOpenAiAgentsBlueprint({ personas: [{}, {}] })).toBe(true)
    expect(isOpenAiAgentsBlueprint({ persona_count: 2 })).toBe(true)
    expect(isOpenAiAgentsBlueprint({ id: 'codey' }, { id: 'codey' })).toBe(false)
    expect(isOpenAiAgentsBlueprint({ personas: [{}] })).toBe(false)
  })

  it('detects team seats from the team url or team kind', () => {
    expect(isTeamBlueprint('office')).toBe(true)
    expect(isTeamBlueprint(undefined, { kind: 'team' })).toBe(true)
    expect(isTeamBlueprint(undefined, { kind: 'api' })).toBe(false)
  })

  it('team wins over openai-agents when both apply', () => {
    expect(
      blueprintTipKindFor({ teamId: 'office', blueprint: { id: 'openai-agents' } }),
    ).toBe('team')
    expect(blueprintTipKindFor({ blueprint: { id: 'openai-agents' } })).toBe('openai-agents')
    expect(blueprintTipKindFor({ agent: { id: 'codey' } })).toBeNull()
  })
})

describe('#1252 blueprintTips persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  it('plain dismiss never writes localStorage', async () => {
    await persistBlueprintTipDismissed('team', false)
    expect(localStorage.getItem(TEAM_BLUEPRINT_TIP_STORAGE_KEY)).toBeNull()
    expect(isBlueprintTipDismissed('team')).toBe(false)
  })

  it('never-show-again persists locally and PATCHes the prefs extras bag', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(prefsPayload({ [TEAM_BLUEPRINT_TIP_PREF_KEY]: true })),
    )
    vi.stubGlobal('fetch', fetchMock)
    await persistBlueprintTipDismissed('team', true)
    expect(localStorage.getItem(TEAM_BLUEPRINT_TIP_STORAGE_KEY)).toBe('1')
    expect(isBlueprintTipDismissed('team')).toBe(true)
    const patchCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/v1/preferences/') && (call[1] as RequestInit)?.method === 'PATCH',
    )
    expect(patchCall).toBeTruthy()
  })

  it('reads dismissed from the prefs extras bag', () => {
    expect(prefsBlueprintTipDismissed({ values: {} }, 'openai-agents')).toBe(false)
    expect(
      prefsBlueprintTipDismissed(
        { values: { [OPENAI_AGENTS_TIP_PREF_KEY]: true } },
        'openai-agents',
      ),
    ).toBe(true)
  })

  it('hydrates dismissed state from the server bag and mirrors to localStorage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(prefsPayload({ [TEAM_BLUEPRINT_TIP_PREF_KEY]: true }))),
    )
    const bag = await hydrateBlueprintTipsDismissed()
    expect(bag.team).toBe(true)
    expect(localStorage.getItem(TEAM_BLUEPRINT_TIP_STORAGE_KEY)).toBe('1')
  })

  it('keeps both kinds independent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(prefsPayload({ [OPENAI_AGENTS_TIP_PREF_KEY]: true })),
      ),
    )
    const bag = await hydrateBlueprintTipsDismissed()
    expect(bag['openai-agents']).toBe(true)
    expect(bag.team).toBe(false)
    expect(localStorage.getItem(OPENAI_AGENTS_TIP_STORAGE_KEY)).toBe('1')
    expect(localStorage.getItem(TEAM_BLUEPRINT_TIP_STORAGE_KEY)).toBeNull()
  })
})
